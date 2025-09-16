"""Connection manager for RAG Config Manager with Vault integration."""

from datetime import datetime
from typing import Dict, List, Optional, Any
from loguru import logger

from rag_config_manager.vault.client import VaultClient
from rag_config_manager.models import (
    AzureOpenAIConnection,
    AWSConnection,
    QdrantConnection,
    Connection,
    ConnectionMetadata,
    ProviderType,
    Environment,
    UsageStats,
)
from rag_config_manager.exceptions import (
    ConnectionNotFoundError,
    InvalidConnectionDataError,
    VaultConnectionError,
)


class ConnectionManager:
    """Manages connections in HashiCorp Vault with multi-user support."""

    def __init__(self, vault_client: VaultClient):
        """Initialize connection manager.

        Args:
            vault_client: Vault client instance
        """
        self.vault = vault_client
        logger.info("Connection manager initialized")

    def _get_user_connection_path(
        self, user_id: str, provider: ProviderType, connection_id: str
    ) -> str:
        """Get the full path for a user's connection."""
        return f"users/{user_id}/{provider.value}/{connection_id}"

    def _get_user_provider_path(self, user_id: str, provider: ProviderType) -> str:
        """Get the path for all connections of a user's provider."""
        return f"users/{user_id}/{provider.value}"

    def create_connection(
        self,
        user_id: str,
        name: str,
        provider: ProviderType,
        connection_data: Dict[str, Any],
        description: str = "",
        environment: Environment = Environment.DEVELOPMENT,
        tags: Optional[List[str]] = None,
        is_default: bool = False,
    ) -> str:
        """Create a new connection for a user.

        Args:
            user_id: User identifier
            name: Connection name
            provider: Provider type
            connection_data: Connection configuration data
            description: Optional description
            environment: Environment type
            tags: Optional tags list
            is_default: Whether this is the default connection

        Returns:
            Connection ID

        Raises:
            InvalidConnectionDataError: If connection data is invalid
            VaultConnectionError: If Vault operation fails
        """
        try:
            # Validate connection data based on provider
            if provider == ProviderType.AZURE_OPENAI:
                connection_obj = AzureOpenAIConnection(**connection_data)
            elif provider == ProviderType.AWS_BEDROCK:
                connection_obj = AWSConnection(**connection_data)
            elif provider == ProviderType.QDRANT:
                connection_obj = QdrantConnection(**connection_data)
            else:
                raise InvalidConnectionDataError(f"Unsupported provider: {provider}")

            # Create metadata
            metadata = ConnectionMetadata(
                name=name,
                description=description,
                provider=provider,
                environment=environment,
                created_by=user_id,
                tags=tags or [],
                is_default=is_default,
            )

            # Create connection object
            connection = Connection(
                metadata=metadata, connection_data=connection_obj.model_dump()
            )

            # Store in Vault
            path = self._get_user_connection_path(user_id, provider, metadata.id)
            # Convert Pydantic model to dict - this will handle the serialization in VaultClient
            connection_dict = connection.model_dump(mode="json")
            success = self.vault.put_secret(path, connection_dict)

            if not success:
                raise VaultConnectionError("Failed to store connection in Vault")

            logger.info(f"Created connection {metadata.id} for user {user_id}")
            return metadata.id

        except Exception as e:
            logger.error(f"Error creating connection: {e}")
            raise

    def get_connection(self, user_id: str, connection_id: str) -> Optional[Connection]:
        """Get a connection by ID.

        Args:
            user_id: User identifier
            connection_id: Connection identifier

        Returns:
            Connection object or None if not found
        """
        try:
            # Try all providers since we don't know the provider from connection_id alone
            for provider in ProviderType:
                path = self._get_user_connection_path(user_id, provider, connection_id)
                data = self.vault.get_secret(path)

                if data:
                    connection = Connection(**data)
                    logger.debug(f"Found connection {connection_id} for user {user_id}")
                    return connection

            logger.debug(f"Connection {connection_id} not found for user {user_id}")
            return None

        except Exception as e:
            logger.error(f"Error retrieving connection {connection_id}: {e}")
            return None

    def get_connection_by_name(
        self, user_id: str, name: str, provider: Optional[ProviderType] = None
    ) -> Optional[Connection]:
        """Get a connection by name.

        Args:
            user_id: User identifier
            name: Connection name
            provider: Optional provider filter

        Returns:
            First connection found with matching name or None
        """
        try:
            providers = [provider] if provider else list(ProviderType)

            for prov in providers:
                connections = self.list_user_connections(user_id, prov)
                for conn in connections:
                    if conn.metadata.name == name:
                        logger.debug(f"Found connection '{name}' for user {user_id}")
                        return conn

            logger.debug(f"Connection '{name}' not found for user {user_id}")
            return None

        except Exception as e:
            logger.error(f"Error retrieving connection by name '{name}': {e}")
            return None

    def list_user_connections(
        self, user_id: str, provider: Optional[ProviderType] = None
    ) -> List[Connection]:
        """List all connections for a user.

        Args:
            user_id: User identifier
            provider: Optional provider filter

        Returns:
            List of connections
        """
        try:
            connections: List[Connection] = []
            providers = [provider] if provider else list(ProviderType)

            for prov in providers:
                path = self._get_user_provider_path(user_id, prov)
                connection_ids = self.vault.list_secrets(path)

                if connection_ids:
                    for conn_id in connection_ids:
                        # Remove trailing slash if present (from directory listing)
                        conn_id = conn_id.rstrip("/")
                        connection = self.get_connection(user_id, conn_id)
                        if connection:
                            connections.append(connection)

            logger.debug(f"Found {len(connections)} connections for user {user_id}")
            return connections

        except Exception as e:
            logger.error(f"Error listing connections for user {user_id}: {e}")
            return []

    def list_connections_by_environment(
        self, user_id: str, environment: Environment
    ) -> List[Connection]:
        """List connections filtered by environment.

        Args:
            user_id: User identifier
            environment: Environment filter

        Returns:
            List of connections matching environment
        """
        try:
            all_connections = self.list_user_connections(user_id)
            filtered_connections = [
                conn
                for conn in all_connections
                if conn.metadata.environment == environment
            ]

            logger.debug(
                f"Found {len(filtered_connections)} {environment} connections for user {user_id}"
            )
            return filtered_connections

        except Exception as e:
            logger.error(f"Error listing connections by environment: {e}")
            return []

    def update_connection(
        self, user_id: str, connection_id: str, updates: Dict[str, Any]
    ) -> bool:
        """Update connection data.

        Args:
            user_id: User identifier
            connection_id: Connection identifier
            updates: Dictionary of updates

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get existing connection
            connection = self.get_connection(user_id, connection_id)
            if not connection:
                raise ConnectionNotFoundError(f"Connection {connection_id} not found")

            # Update connection data
            if "connection_data" in updates:
                connection.connection_data.update(updates["connection_data"])

            # Update metadata
            if "metadata" in updates:
                for key, value in updates["metadata"].items():
                    if hasattr(connection.metadata, key):
                        setattr(connection.metadata, key, value)

            # Special handling for usage_count
            if "usage_count" in updates.get("metadata", {}):
                connection.metadata.usage_count = updates["metadata"]["usage_count"]

            # Update timestamp
            connection.metadata.updated_at = datetime.now()

            # Store updated connection
            path = self._get_user_connection_path(
                user_id, connection.metadata.provider, connection_id
            )
            success = self.vault.put_secret(path, connection.model_dump(mode="json"))

            if success:
                logger.info(f"Updated connection {connection_id} for user {user_id}")
            return success

        except Exception as e:
            logger.error(f"Error updating connection {connection_id}: {e}")
            return False

    def delete_connection(self, user_id: str, connection_id: str) -> bool:
        """Delete a connection.

        Args:
            user_id: User identifier
            connection_id: Connection identifier

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get connection to find provider
            connection = self.get_connection(user_id, connection_id)
            if not connection:
                logger.warning(f"Connection {connection_id} not found for deletion")
                return True  # Already deleted

            # Delete from Vault
            path = self._get_user_connection_path(
                user_id, connection.metadata.provider, connection_id
            )
            success = self.vault.delete_secret(path)

            if success:
                logger.info(f"Deleted connection {connection_id} for user {user_id}")
            return success

        except Exception as e:
            logger.error(f"Error deleting connection {connection_id}: {e}")
            return False

    def record_connection_usage(self, user_id: str, connection_id: str) -> bool:
        """Record connection usage for statistics.

        Args:
            user_id: User identifier
            connection_id: Connection identifier

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get current connection to increment usage_count
            connection = self.get_connection(user_id, connection_id)
            if not connection:
                return False

            # Update connection metadata with new usage info
            connection.metadata.last_used = datetime.now()
            connection.metadata.usage_count += 1
            connection.metadata.updated_at = datetime.now()

            # Store updated connection
            path = self._get_user_connection_path(
                user_id, connection.metadata.provider, connection_id
            )
            # Convert to dict with JSON mode for proper serialization
            connection_dict = connection.model_dump(mode="json")
            success = self.vault.put_secret(path, connection_dict)

            if success:
                logger.info(f"Recorded usage for connection {connection_id}")
            return success

            return False

        except Exception as e:
            logger.error(f"Error recording connection usage: {e}")
            return False

    def get_connection_usage_stats(
        self, user_id: str, connection_id: str
    ) -> Optional[UsageStats]:
        """Get connection usage statistics.

        Args:
            user_id: User identifier
            connection_id: Connection identifier

        Returns:
            Usage statistics or None if not found
        """
        try:
            connection = self.get_connection(user_id, connection_id)
            if not connection:
                return None

            return UsageStats(
                connection_id=connection_id,
                total_usage=connection.metadata.usage_count,
                last_used=connection.metadata.last_used,
            )

        except Exception as e:
            logger.error(
                f"Error getting usage stats for connection {connection_id}: {e}"
            )
            return None

    def find_production_connection(self, provider: str) -> Optional[Connection]:
        """Find the production connection for a given provider across all users.

        Args:
            provider: Provider name (e.g., "azure_openai", "aws_bedrock")

        Returns:
            Production connection or None if not found
        """
        try:
            # Convert string to ProviderType enum
            try:
                provider_enum = ProviderType(provider)
            except ValueError:
                logger.error(f"Invalid provider: {provider}")
                return None

            # List all users by checking the root secrets path
            users_path = "users"  # Updated to match actual vault structure
            user_ids = self.vault.list_secrets(users_path)

            if not user_ids:
                logger.debug("No users found in vault")
                return None

            # Search through all users for production connections
            for user_id in user_ids:
                user_id = user_id.rstrip("/")  # Remove trailing slash
                connections = self.list_connections_by_environment(
                    user_id, Environment.PRODUCTION
                )

                # Find connection matching the provider
                for connection in connections:
                    if connection.metadata.provider == provider_enum:
                        logger.info(
                            f"Found production connection for {provider}: {connection.metadata.id}"
                        )
                        return connection

            logger.warning(f"No production connection found for provider: {provider}")
            return None

        except Exception as e:
            logger.error(f"Error finding production connection for {provider}: {e}")
            return None

    def get_all_connections(self) -> List[Connection]:
        """Get all connections across all users.

        Returns:
            List of all connections found in vault
        """
        all_connections: List[Connection] = []

        try:
            # List all users
            users_path = "users"
            user_ids = self.vault.list_secrets(users_path)

            if not user_ids:
                logger.debug("No users found in vault")
                return all_connections

            # Get connections for each user
            for user_id in user_ids:
                user_id = user_id.rstrip("/")  # Remove trailing slash
                try:
                    user_connections = self.list_user_connections(user_id)
                    if user_connections:
                        all_connections.extend(user_connections)
                        logger.debug(
                            f"Found {len(user_connections)} connections for user {user_id}"
                        )
                except Exception as e:
                    logger.debug(f"Could not list connections for user {user_id}: {e}")

            logger.info(f"Found total of {len(all_connections)} connections in vault")
            return all_connections

        except Exception as e:
            logger.error(f"Failed to get all connections: {e}")
            return []
