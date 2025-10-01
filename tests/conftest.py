import os
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Generator

import pytest
import hvac
import requests
from loguru import logger
from testcontainers.compose import DockerCompose  # type: ignore


# ===================== VaultAgentClient =====================

class VaultAgentClient:
    """Client for interacting with Vault using a token written by Vault Agent"""
    
    def __init__(
        self,
        vault_url: str,
        token_path: Path = Path("test-vault/agent-out/token"),
        mount_point: str = "secret",
        timeout: int = 10,
    ):
        self.vault_url = vault_url
        self.token_path = token_path
        self.mount_point = mount_point

        self.client = hvac.Client(url=self.vault_url, timeout=timeout)
        self._load_token()

    def _load_token(self) -> None:
        """Load token from file written by Vault Agent"""
        if not self.token_path.exists():
            raise FileNotFoundError(f"Vault token file missing: {self.token_path}")
        token = self.token_path.read_text().strip()
        if not token:
            raise ValueError("Vault token file is empty")
        self.client.token = token

    def is_authenticated(self) -> bool:
        """Check if the current token is valid"""
        try:
            return self.client.is_authenticated()
        except Exception as e:
            logger.warning(f"Vault token is not valid: {e}")
            return False

    def is_vault_available(self) -> bool:
        """Check if Vault is initialized and unsealed"""
        try:
            status = self.client.sys.read_health_status(method="GET")
            return isinstance(status, dict) and status.get("initialized", False) and not status.get("sealed", True)
        except Exception as e:
            logger.warning(f"Vault availability check failed: {e}")
            return False

    def get_secret(self, path: str) -> dict:
        """Read a secret from Vault KV v2"""
        try:
            result = self.client.secrets.kv.v2.read_secret_version(path=path, mount_point=self.mount_point)
            return result["data"]["data"]
        except Exception as e:
            logger.error(f"Failed to read Vault secret at {path}: {e}")
            raise


# ===================== RAGStackTestContainers =====================

class RAGStackTestContainers:
    """Manages test containers for RAG stack including Vault, Qdrant, and LLM orchestration service"""
    
    def __init__(self, compose_file_name: str = "docker-compose-test.yml"):
        self.project_root = Path(__file__).parent.parent
        self.compose_file_path = self.project_root / compose_file_name
        self.compose: Optional[DockerCompose] = None
        self.services_info: Dict[str, Dict[str, Any]] = {}

        if not self.compose_file_path.exists():
            raise FileNotFoundError(f"Docker compose file not found: {self.compose_file_path}")

    def start(self) -> None:
        """Start all test containers and bootstrap Vault"""
        logger.info("Starting RAG Stack testcontainers...")

        # Prepare Vault Agent directories
        agent_in = self.project_root / "test-vault" / "agents" / "llm"
        agent_out = self.project_root / "test-vault" / "agent-out"
        agent_in.mkdir(parents=True, exist_ok=True)
        agent_out.mkdir(parents=True, exist_ok=True)

        # Clean up any stale files from previous runs
        for f in ["role_id", "secret_id", "token", "pidfile", "dummy"]:
            (agent_in / f).unlink(missing_ok=True)
            (agent_out / f).unlink(missing_ok=True)

        # Start all Docker Compose services
        logger.info("Starting Docker Compose services...")
        self.compose = DockerCompose(
            str(self.project_root),
            compose_file_name=self.compose_file_path.name,
            pull=False
        )
        self.compose.start()

        # Get Vault connection details
        vault_url = self._get_vault_url()
        logger.info(f"Vault URL: {vault_url}")
        
        # Wait for Vault to be ready
        self._wait_for_vault_ready(vault_url)
        
        # Configure Vault with AppRole, policies, and test secrets
        self._bootstrap_vault_dev(agent_in, vault_url)

        # Verify credentials were written successfully
        role_id = (agent_in / "role_id").read_text().strip()
        secret_id = (agent_in / "secret_id").read_text().strip()
        logger.info(f"AppRole credentials written: role_id={role_id[:8]}..., secret_id={secret_id[:8]}...")

        # Wait for Vault Agent to authenticate and write token
        logger.info("Waiting for vault-agent to authenticate...")
        self._wait_for_valid_token(agent_out / "token", vault_url, max_attempts=20)

        logger.info("Vault Agent authenticated successfully")

        # Wait for other services to be ready
        self._wait_for_services()
        self._collect_service_info()

        logger.info("RAG Stack testcontainers ready")

    def stop(self) -> None:
        """Stop all test containers"""
        if self.compose:
            logger.info("Stopping RAG Stack testcontainers...")
            self.compose.stop()
            logger.info("Testcontainers stopped")

    def _get_vault_url(self) -> str:
        """Get the mapped Vault URL accessible from the host"""
        if not self.compose:
            raise RuntimeError("Docker Compose not initialized")
        host = self.compose.get_service_host("vault", 8200)
        port = self.compose.get_service_port("vault", 8200)
        return f"http://{host}:{port}"

    def _wait_for_vault_ready(self, vault_url: str, timeout: int = 60) -> None:
        """Wait for Vault to be initialized and unsealed"""
        logger.info("Waiting for Vault to be available...")
        client = hvac.Client(url=vault_url, token="root", timeout=10)
        
        start = time.time()
        while time.time() - start < timeout:
            try:
                status = client.sys.read_health_status(method="GET")
                if status.get("initialized", False) and not status.get("sealed", True):
                    logger.info("Vault is available and unsealed")
                    return
            except Exception:
                pass
            time.sleep(2)
        
        raise TimeoutError("Vault did not become available within 60s")

    def _bootstrap_vault_dev(self, agent_in: Path, vault_url: str) -> None:
        """
        Bootstrap Vault dev instance with:
        - AppRole auth method
        - Policy for LLM orchestration service
        - AppRole role and credentials
        - Test secrets
        """
        logger.info("Bootstrapping Vault with AppRole...")
        client = hvac.Client(url=vault_url, token="root")

        # Enable AppRole authentication method
        if "approle/" not in client.sys.list_auth_methods():
            client.sys.enable_auth_method("approle")
            logger.info("AppRole enabled")

        # Create policy with permissions for:
        # - Reading secrets from secret/data/llm/*
        # - Token self-lookup and renewal (required for token validation)
        policy = """
path "secret/metadata/llm/*" { capabilities = ["list"] }
path "secret/data/llm/*"     { capabilities = ["read"] }
path "auth/token/lookup-self" { capabilities = ["read"] }
path "auth/token/renew-self" { capabilities = ["update"] }
"""
        client.sys.create_or_update_policy("llm-orchestration", policy)
        logger.info("Policy 'llm-orchestration' created")

        # Create AppRole role with service token type
        role_name = "llm-orchestration-service"
        client.write(f"auth/approle/role/{role_name}", **{
            "token_policies": "llm-orchestration",
            "secret_id_ttl": "24h",
            "token_ttl": "1h",
            "token_max_ttl": "24h",
            "secret_id_num_uses": 0,  # Unlimited uses for testing
            "bind_secret_id": True,
            "token_no_default_policy": True,  # Use only our custom policy
            "token_type": "service"  # Service tokens (not batch tokens)
        })
        logger.info(f"AppRole '{role_name}' created")

        # Generate credentials for the AppRole
        role_id = client.read(f"auth/approle/role/{role_name}/role-id")["data"]["role_id"]
        secret_id = client.write(f"auth/approle/role/{role_name}/secret-id")["data"]["secret_id"]

        # Write credentials to files that Vault Agent will read
        (agent_in / "role_id").write_text(role_id, encoding="utf-8")
        (agent_in / "secret_id").write_text(secret_id, encoding="utf-8")
        logger.info("AppRole credentials written to agent-in/")

        # Write test secret for LLM orchestration service
        kv_path = "llm/connections/azure_openai/production/gpt-4o-mini"
        secret_data = {
            "connection_id": "evalconnection-1",
            "endpoint": os.getenv("AZURE_OPENAI_ENDPOINT", "https://fake-endpoint"),
            "api_key": os.getenv("AZURE_OPENAI_API_KEY", "TEST_API_KEY"),
            "deployment_name": os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
            "environment": "production",
            "model": "gpt-4o-mini",
            "api_version": "2024-05-01-preview",
            "tags": "azure,production"
        }

        client.secrets.kv.v2.create_or_update_secret(
            mount_point="secret",
            path=kv_path,
            secret=secret_data
        )
        logger.info(f"Secret written to {kv_path}")

    def _wait_for_valid_token(self, token_path: Path, vault_url: str, max_attempts: int = 20) -> None:
        """Wait for Vault Agent to write a valid token and verify it works"""
        for attempt in range(max_attempts):
            if token_path.exists() and token_path.stat().st_size > 0:
                token = token_path.read_text().strip()
                
                # Validate the token by attempting to use it
                client = hvac.Client(url=vault_url, token=token)
                try:
                    # Lookup token to verify it's valid
                    client.lookup_token()
                    
                    if client.is_authenticated():
                        logger.info(f"Valid token obtained (attempt {attempt + 1})")
                        # Verify token can read secrets
                        self._verify_token_permissions(client)
                        return
                except Exception as e:
                    if attempt < max_attempts - 1:  # Don't log on last attempt
                        logger.debug(f"Token validation error (attempt {attempt + 1}): {type(e).__name__}")
            
            time.sleep(2)
        
        # If we get here, all attempts failed - log detailed debugging info
        logger.error("Failed to obtain valid Vault token")
        self._check_agent_logs()
        
        raise TimeoutError(f"Failed to obtain valid Vault token after {max_attempts} attempts")
    
    def _verify_token_permissions(self, client: hvac.Client) -> None:
        """Verify the token has correct permissions to read secrets"""
        try:
            client.secrets.kv.v2.read_secret_version(
                path="llm/connections/azure_openai/production/gpt-4o-mini",
                mount_point="secret"
            )
            logger.info("Token has correct permissions to read secrets")
        except Exception as e:
            logger.error(f"Token cannot read secrets: {e}")
            raise
    
    def _check_agent_logs(self) -> None:
        """Check vault-agent logs for debugging authentication issues"""
        result = subprocess.run(
            ["docker", "logs", "--tail", "50", "vault-agent-llm"],
            capture_output=True,
            text=True
        )
        logger.error(f"Vault Agent Logs:\n{result.stdout}\n{result.stderr}")

    def _wait_for_services(self, total_timeout: int = 300) -> None:
        """Wait for all services to be healthy"""
        services = [
            ("qdrant", 6333, self._check_qdrant, 60),
            ("llm-orchestration-service", 8100, self._check_orchestration, 180)
        ]
        start = time.time()
        for name, port, check, timeout in services:
            self._wait_single(name, port, check, timeout, start, total_timeout)

    def _wait_single(self, name: str, port: int, check: Any, timeout: int, global_start: float, total_timeout: int) -> None:
        """Wait for a single service to be ready"""
        if self.compose is None:
            return
        
        logger.info(f"Waiting for {name}...")
        start = time.time()
        while time.time() - start < timeout:
            try:
                host = self.compose.get_service_host(name, port)
                mapped_port = self.compose.get_service_port(name, port)
                if check(host, mapped_port):
                    logger.info(f"{name} ready at {host}:{mapped_port}")
                    self.services_info[name] = {
                        "host": host,
                        "port": mapped_port,
                        "url": f"http://{host}:{mapped_port}"
                    }
                    return
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"Timeout waiting for {name}")

    def _check_qdrant(self, host: str, port: int) -> bool:
        """Check if Qdrant is ready"""
        try:
            r = requests.get(f"http://{host}:{port}/collections", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def _check_orchestration(self, host: str, port: int) -> bool:
        """Check if LLM orchestration service is healthy"""
        try:
            r = requests.get(f"http://{host}:{port}/health", timeout=5)
            return r.status_code == 200 and r.json().get("status") == "healthy"
        except Exception:
            return False

    def _collect_service_info(self) -> None:
        """Collect service connection information"""
        if self.compose:
            self.services_info["vault"] = {
                "host": self.compose.get_service_host("vault", 8200),
                "port": self.compose.get_service_port("vault", 8200),
                "url": self._get_vault_url()
            }

    def get_orchestration_service_url(self) -> str:
        """Get the URL for the LLM orchestration service"""
        return self.services_info["llm-orchestration-service"]["url"]

    def get_qdrant_url(self) -> str:
        """Get the URL for Qdrant"""
        return self.services_info["qdrant"]["url"]

    def get_vault_url(self) -> str:
        """Get the URL for Vault"""
        return self.services_info["vault"]["url"]

    def is_service_available(self, service_name: str) -> bool:
        """Check if a service is available"""
        return service_name in self.services_info


# ===================== Pytest Fixtures =====================

@pytest.fixture(scope="session")
def rag_stack() -> Generator[RAGStackTestContainers, None, None]:
    """
    Session-scoped fixture that starts all test containers once per test session.
    Containers are automatically stopped after all tests complete.
    """
    stack = RAGStackTestContainers()
    try:
        stack.start()
        yield stack
    finally:
        stack.stop()


@pytest.fixture(scope="function")
def orchestration_client(rag_stack: RAGStackTestContainers) -> Any:
    """
    Function-scoped fixture that provides a configured requests session
    for testing the LLM orchestration service API.
    """
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Accept": "application/json"
    })
    setattr(session, "base_url", rag_stack.get_orchestration_service_url())
    return session