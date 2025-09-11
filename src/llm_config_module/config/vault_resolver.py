"""Vault secret resolver for LLM Config Module."""

from typing import Dict, Any, Optional, List
from loguru import logger

from rag_config_manager.vault import VaultClient, ConnectionManager
from rag_config_manager.models import ProviderType, Connection
from llm_config_module.exceptions import ConfigurationError


class VaultSecretResolver:
    """Resolves secrets from HashiCorp Vault for LLM providers."""

    def __init__(self, vault_url: str, vault_token: str):
        """Initialize the vault secret resolver.

        Args:
            vault_url: Vault server URL
            vault_token: Vault access token

        Raises:
            ConfigurationError: If vault connection fails
        """
        try:
            self.vault_client = VaultClient(vault_url=vault_url, token=vault_token)
            self.connection_manager = ConnectionManager(self.vault_client)

            if not self.vault_client.is_vault_available():
                raise ConfigurationError("Vault is not available")

            logger.info("Connected to Vault successfully")

        except Exception as e:
            raise ConfigurationError(f"Failed to connect to Vault: {e}") from e

    def discover_available_providers(
        self, environment: str, connection_id: Optional[str] = None
    ) -> Dict[str, Connection]:
        """Discover available providers for the given environment.

        Args:
            environment: Environment ("production", "development", "test")
            connection_id: Connection ID (required for development/test)

        Returns:
            Dictionary mapping provider names to their connections

        Raises:
            ConfigurationError: If no providers are available
        """
        available_providers: Dict[str, Connection] = {}

        try:
            if environment == "production":
                logger.info("Searching for production connections...")

                # Get all connections and filter for production ones
                all_connections: List[Connection] = self._get_all_connections()
                production_connections: List[Connection] = [
                    conn
                    for conn in all_connections
                    if conn.metadata.environment == "production"
                ]

                if not production_connections:
                    raise ConfigurationError("No production connections found in vault")

                # Group by provider - use the first connection found for each provider
                for connection in production_connections:
                    provider_name: str = connection.metadata.provider.value
                    if provider_name not in available_providers:
                        available_providers[provider_name] = connection
                        logger.info(
                            f"Found production provider: {provider_name} (connection: {connection.metadata.id})"
                        )

            elif environment in ["development", "test"]:
                if not connection_id:
                    raise ConfigurationError(
                        f"connection_id is required for {environment} environment"
                    )

                # For dev/test, use the specific connection
                connection = self._find_connection_by_id(connection_id)
                if connection:
                    provider_name = connection.metadata.provider.value
                    available_providers[provider_name] = connection
                    logger.info(
                        f"Found {environment} provider: {provider_name} (connection: {connection_id})"
                    )
                else:
                    raise ConfigurationError(f"Connection not found: {connection_id}")

            else:
                raise ConfigurationError(
                    f"Invalid environment: {environment}. "
                    f"Must be one of: production, development, test"
                )

            if not available_providers:
                raise ConfigurationError(
                    f"No providers available for {environment} environment"
                    + (f" with connection_id {connection_id}" if connection_id else "")
                )

            logger.info(
                f"Discovered {len(available_providers)} providers for {environment}: {list(available_providers.keys())}"
            )
            return available_providers

        except Exception as e:
            logger.error(f"Failed to discover providers for {environment}: {e}")
            raise ConfigurationError(f"Failed to discover providers: {e}") from e

    def _get_all_connections(self) -> List[Connection]:
        """Get all connections from vault regardless of user.

        This method discovers connections dynamically without relying on
        specific user names, supporting a truly user-independent architecture.

        Returns:
            List of all connections found in vault
        """
        all_connections: List[Connection] = []

        try:
            # Try to use connection manager's method to get all connections across all users
            # Check if the method exists first
            if hasattr(self.connection_manager, "get_all_connections"):
                all_connections = getattr(
                    self.connection_manager, "get_all_connections"
                )()
            else:
                # Fallback: discover connections dynamically without hardcoded users
                all_connections = self._discover_connections_dynamically()

            logger.info(f"Found total of {len(all_connections)} connections in vault")
            return all_connections

        except Exception as e:
            logger.error(f"Failed to get all connections: {e}")
            return []

    def _discover_connections_dynamically(self) -> List[Connection]:
        """Dynamically discover connections without hardcoded user names.

        This method explores the vault structure to find all users and their connections
        without relying on predefined user lists.

        Returns:
            List of all connections found
        """
        all_connections: List[Connection] = []

        try:
            # Try to list all users dynamically from the vault structure
            # Based on the logs, the structure is "users/" not "secret/users"
            users_path = "users"

            # List all user directories
            user_ids = self.vault_client.list_secrets(users_path)

            if user_ids:
                logger.debug(f"Discovered {len(user_ids)} users in vault")

                for user_id in user_ids:
                    user_id = user_id.rstrip("/")
                    try:
                        user_connections = (
                            self.connection_manager.list_user_connections(user_id)
                        )
                        if user_connections:
                            all_connections.extend(user_connections)
                            logger.debug(
                                f"Found {len(user_connections)} connections for user {user_id}"
                            )
                        else:
                            logger.debug(f"No connections found for user {user_id}")
                    except Exception as e:
                        logger.debug(
                            f"Could not list connections for user {user_id}: {e}"
                        )
            else:
                logger.warning("No users found in vault at path: users")
                # Alternative approach: try to discover connections through provider paths
                all_connections = self._discover_connections_by_providers()

            return all_connections

        except Exception as e:
            logger.error(f"Dynamic connection discovery failed: {e}")
            # Last resort: try provider-based discovery
            return self._discover_connections_by_providers()

    def _discover_connections_by_providers(self) -> List[Connection]:
        """Discover connections by exploring provider-specific paths.

        This is a last-resort method when user-based discovery fails.

        Returns:
            List of connections found through provider paths
        """
        all_connections: List[Connection] = []

        try:
            logger.warning("Provider-based connection discovery not yet implemented")
            logger.info(
                "Consider implementing get_all_connections() in ConnectionManager for better performance"
            )

            return all_connections

        except Exception as e:
            logger.error(f"Provider-based connection discovery failed: {e}")
            return []

    def resolve_provider_secrets(
        self, provider: str, environment: str, connection_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Resolve secrets for a specific provider and environment.

        Args:
            provider: Provider name (e.g., "azure_openai", "aws_bedrock")
            environment: Environment ("production", "development", "test")
            connection_id: Connection ID (required for development/test)

        Returns:
            Dictionary containing provider secrets

        Raises:
            ConfigurationError: If secrets cannot be resolved
        """
        try:
            # Validate provider
            if provider not in [p.value for p in ProviderType]:
                raise ConfigurationError(f"Unsupported provider: {provider}")

            # Get connection based on environment
            if environment == "production":
                # For production, find the connection from our discovered providers
                connection = self._find_production_connection(provider)
                if not connection:
                    raise ConfigurationError(
                        f"No production connection found for provider: {provider}"
                    )
            elif environment in ["development", "test"]:
                if not connection_id:
                    raise ConfigurationError(
                        f"connection_id is required for {environment} environment"
                    )
                # For dev/test, we need to search across all users since we don't filter by user
                connection = self._find_connection_by_id(connection_id)
                if not connection:
                    raise ConfigurationError(f"Connection not found: {connection_id}")
                # Validate provider matches
                if connection.metadata.provider.value != provider:
                    raise ConfigurationError(
                        f"Connection {connection_id} is for {connection.metadata.provider.value}, "
                        f"not {provider}"
                    )
            else:
                raise ConfigurationError(
                    f"Invalid environment: {environment}. "
                    f"Must be one of: production, development, test"
                )

            # Extract secrets from connection data
            secrets = self._extract_provider_secrets(connection, provider)

            logger.info(
                f"Resolved secrets for {provider} in {environment} environment "
                f"(connection: {connection.metadata.id})"
            )

            return secrets

        except Exception as e:
            logger.error(f"Failed to resolve secrets for {provider}: {e}")
            raise ConfigurationError(
                f"Failed to resolve secrets for {provider}: {e}"
            ) from e

    def _find_connection_by_id(self, connection_id: str):
        """Find connection by ID across all users without hardcoded user names.

        Args:
            connection_id: Connection identifier

        Returns:
            Connection object or None if not found
        """
        try:
            # Get all connections and search for the specific connection_id
            all_connections = self._get_all_connections()

            for connection in all_connections:
                if connection.metadata.id == connection_id:
                    logger.debug(f"Found connection {connection_id}")
                    return connection

            logger.debug(f"Connection {connection_id} not found")
            return None

        except Exception as e:
            logger.error(f"Error finding connection {connection_id}: {e}")
            return None

    def _find_production_connection(self, provider: str):
        """Find production connection for a specific provider.

        Args:
            provider: Provider name

        Returns:
            Connection object or None if not found
        """
        try:
            # Get all connections and filter for production environment and provider
            all_connections = self._get_all_connections()

            for connection in all_connections:
                # Check if this is the right provider and production environment
                if (
                    connection.metadata.provider.value == provider
                    and connection.metadata.environment == "production"
                ):
                    logger.debug(
                        f"Found production connection for {provider}: {connection.metadata.id}"
                    )
                    return connection

            logger.debug(f"No production connection found for provider {provider}")
            return None

        except Exception as e:
            logger.error(f"Error finding production connection for {provider}: {e}")
            return None

    def _extract_provider_secrets(
        self, connection: Connection, provider: str
    ) -> Dict[str, Any]:
        """Extract secrets from connection data based on provider type.

        Args:
            connection: Connection object
            provider: Provider name

        Returns:
            Dictionary of provider-specific secrets
        """
        connection_data = connection.connection_data

        if provider == "azure_openai":
            return {
                "endpoint": connection_data.get("endpoint", ""),
                "api_key": connection_data.get("api_key", ""),
                "deployment_name": connection_data.get("deployment_name", ""),
            }

        elif provider == "aws_bedrock":
            return {
                "region": connection_data.get("region", ""),
                "access_key_id": connection_data.get("access_key_id", ""),
                "secret_access_key": connection_data.get("secret_access_key", ""),
            }

        else:
            raise ConfigurationError(f"Unknown provider secrets format: {provider}")
