# """
# TestContainers configuration for RAG Module DeepEval Testing

# This module provides shared infrastructure for running integration tests
# with testcontainers for the RAG stack (Qdrant + LLM Orchestration Service).
# """

# import time
# import requests
# from pathlib import Path
# from typing import Dict, Any, Optional, Generator
# from testcontainers.compose import DockerCompose  # type: ignore
# import pytest
# from loguru import logger


# class RAGStackTestContainers:
#     """
#     Manages testcontainers environment for RAG Stack services
#     """
    
#     def __init__(self, compose_file_name: str = "docker-compose-test.yml"):
#         self.project_root = Path(__file__).parent.parent
#         self.compose_file_path = self.project_root / compose_file_name
#         self.compose: Optional[DockerCompose] = None
#         self.services_info: Dict[str, Dict[str, Any]] = {}
        
#         # Verify compose file exists
#         if not self.compose_file_path.exists():
#             raise FileNotFoundError(f"Docker compose file not found: {self.compose_file_path}")
    
#     def start(self) -> None:
#         """Start all services defined in docker-compose-test.yml"""
#         logger.info("Starting RAG Stack testcontainers...")

#         self.compose = DockerCompose(
#             str(self.project_root),
#             compose_file_name=self.compose_file_path.name,
#             pull=False  # Don't pull images, use local only
#         )

#         # Start the compose stack
#         self.compose.start()

#         # Wait for services to be ready and collect connection info
#         self._wait_for_services()
#         self._collect_service_info()

#         logger.info("RAG Stack testcontainers started successfully")
    
#     def stop(self) -> None:
#         """Stop all services"""
#         if self.compose:
#             logger.info("Stopping RAG Stack testcontainers...")
#             self.compose.stop()
#             logger.info("RAG Stack testcontainers stopped")
    
#     def _wait_for_services(self, total_timeout: int = 300) -> None:
#         """Wait for critical services to become available"""
#         services_to_check = [
#             ("qdrant", 6333, self._check_qdrant_service, 60),
#             ("llm-orchestration-service", 8100, self._check_orchestration_service, 180),
#         ]
        
#         overall_start_time = time.time()
        
#         for service_name, port, check_func, service_timeout in services_to_check:
#             self._wait_for_single_service(service_name, port, check_func, service_timeout, overall_start_time, total_timeout)
        
#         # Additional stabilization time for services that did start
#         logger.info("Allowing additional 15s for services to fully stabilize...")
#         time.sleep(15)
        
#         total_elapsed = time.time() - overall_start_time
#         logger.info(f"Service startup completed in {total_elapsed:.1f}s")
    
#     def _wait_for_single_service(self, service_name: str, port: int, check_func: Any, service_timeout: int, overall_start_time: float, total_timeout: int) -> None:
#         """Wait for a single service to become ready"""
#         if self.compose is None:
#             logger.error("Docker compose not initialized")
#             return
            
#         service_ready = False
#         service_start_time = time.time()
        
#         logger.info(f"Waiting up to {service_timeout}s for {service_name} to become ready...")
        
#         while not service_ready and (time.time() - service_start_time) < service_timeout:
#             try:
#                 host = self.compose.get_service_host(service_name, port)
#                 mapped_port = self.compose.get_service_port(service_name, port)
                
#                 if host and mapped_port and check_func(host, mapped_port):
#                     service_ready = True
#                     elapsed = time.time() - service_start_time
#                     logger.info(f"Service {service_name} is ready at {host}:{mapped_port} (took {elapsed:.1f}s)")
#                 else:
#                     logger.debug(f"Service {service_name} not ready yet, retrying in 5s...")
#                     time.sleep(5)
                    
#             except Exception as e:
#                 logger.debug(f"Waiting for {service_name}: {e}")
#                 time.sleep(5)
            
#             # Check overall timeout
#             if (time.time() - overall_start_time) > total_timeout:
#                 logger.warning(f"Overall timeout of {total_timeout}s reached, stopping service checks")
#                 return
        
#         if not service_ready:
#             elapsed = time.time() - service_start_time
#             logger.warning(f"Service {service_name} failed to become ready within {service_timeout}s (waited {elapsed:.1f}s)")
    
#     def _check_qdrant_service(self, host: str, port: int) -> bool:
#         try:
#             # NEW ✅ Try a real endpoint
#             response = requests.get(f"http://{host}:{port}/collections", timeout=10)
#             if response.status_code == 200:
#                 logger.debug("Qdrant is responding correctly")
#                 return True
#             else:
#                 logger.debug(f"Qdrant responded with status {response.status_code}")
#                 return False
#         except Exception as e:
#             logger.debug(f"Qdrant health check failed: {e}")
#             return False
    
#     def _check_orchestration_service(self, host: str, port: int) -> bool:
#         """Check if LLM Orchestration Service is ready and initialized"""
#         try:
#             response = requests.get(f"http://{host}:{port}/health", timeout=10)
            
#             if response.status_code == 200:
#                 health_data = response.json()
#                 # Check if orchestration service is properly initialized
#                 if (health_data.get("status") == "healthy" and 
#                     health_data.get("orchestration_service") == "initialized"):
#                     logger.debug("Orchestration service is healthy and initialized")
#                     return True
#                 else:
#                     logger.debug(f"Orchestration service not fully initialized: {health_data}")
#                     return False
#             else:
#                 logger.debug(f"Orchestration service health check returned {response.status_code}")
#                 return False
                
#         except Exception as e:
#             logger.debug(f"Orchestration service health check failed: {e}")
#             return False
    
#     def _collect_service_info(self) -> None:
#         """Collect connection information for all services"""
#         if self.compose is None:
#             logger.error("Docker compose not initialized")
#             return
            
#         services = [
#             ("qdrant", 6333),
#             ("llm-orchestration-service", 8100),
#         ]
        
#         for service_name, port in services:
#             try:
#                 host = self.compose.get_service_host(service_name, port)
#                 mapped_port = self.compose.get_service_port(service_name, port)
                
#                 if host and mapped_port:
#                     self.services_info[service_name] = {
#                         "host": host,
#                         "port": mapped_port,
#                         "url": f"http://{host}:{mapped_port}"
#                     }
#             except Exception as e:
#                 logger.warning(f"Could not get info for {service_name}: {e}")
            
#         logger.info(f"Service discovery completed. Available services: {list(self.services_info.keys())}")
    
#     def get_orchestration_service_url(self) -> str:
#         """Get the URL for the LLM orchestration service"""
#         service_name = "llm-orchestration-service"
#         if service_name not in self.services_info:
#             available_services = list(self.services_info.keys())
#             raise ValueError(f"Service {service_name} not found. Available: {available_services}")
#         return self.services_info[service_name]["url"]
    
#     def get_qdrant_url(self) -> str:
#         """Get the URL for the Qdrant service"""
#         service_name = "qdrant"
#         if service_name not in self.services_info:
#             available_services = list(self.services_info.keys())
#             raise ValueError(f"Service {service_name} not found. Available: {available_services}")
#         return self.services_info[service_name]["url"]
    
#     def is_service_available(self, service_name: str) -> bool:
#         """Check if a service is available and ready"""
#         if service_name not in self.services_info:
#             logger.debug(f"Service {service_name} not in services_info")
#             return False
        
#         service_info = self.services_info[service_name]
        
#         if service_name == "qdrant":
#             return self._check_qdrant_service(service_info['host'], service_info['port'])
#         elif service_name == "llm-orchestration-service":
#             return self._check_orchestration_service(service_info['host'], service_info['port'])
#         else:
#             logger.debug(f"Unknown service: {service_name}")
#             return False
    
#     def get_all_services_info(self) -> Dict[str, Dict[str, Any]]:
#         """Get information about all available services"""
#         return dict(self.services_info)


# @pytest.fixture(scope="session")
# def rag_stack() -> Generator[RAGStackTestContainers, None, None]:
#     """
#     Session-scoped pytest fixture for RAG Stack testcontainers
    
#     This fixture starts the entire RAG Stack once per test session
#     and tears it down at the end.
#     """
#     stack = RAGStackTestContainers()
    
#     try:
#         stack.start()
#         yield stack
#     finally:
#         stack.stop()


# @pytest.fixture(scope="function")
# def orchestration_client(rag_stack: RAGStackTestContainers) -> requests.Session:
#     """
#     Function-scoped fixture providing a configured HTTP client for the orchestration service
    
#     Returns a requests.Session configured with:
#     - Proper headers (Content-Type, Accept)
#     - Base URL as an attribute
#     - Standard timeout settings
#     """
#     base_url = rag_stack.get_orchestration_service_url()
    
#     # Create and configure a requests session
#     session = requests.Session()
#     session.headers.update({
#         'Content-Type': 'application/json',
#         'Accept': 'application/json'
#     })
    
#     # Add base URL as a custom attribute for convenience
#     setattr(session, 'base_url', base_url)
    
#     logger.debug(f"Created orchestration client for {base_url}")
#     return session
"""
TestContainers configuration for RAG Module DeepEval Testing

This module provides shared infrastructure for running integration tests
with testcontainers for the RAG stack (Qdrant + LLM Orchestration Service + Vault).
"""

import os
import json
import time
import requests
from pathlib import Path
from typing import Dict, Any, Optional, Generator
from testcontainers.compose import DockerCompose  # type: ignore
import pytest
from loguru import logger


class RAGStackTestContainers:
    """
    Manages testcontainers environment for RAG Stack services
    (Qdrant + LLM Orchestration + Vault + Vault Agent).
    """

    def __init__(self, compose_file_name: str = "docker-compose-test.yml"):
        self.project_root = Path(__file__).parent.parent
        self.compose_file_path = self.project_root / compose_file_name
        self.compose: Optional[DockerCompose] = None
        self.services_info: Dict[str, Dict[str, Any]] = {}
        if not self.compose_file_path.exists():
            raise FileNotFoundError(f"Docker compose file not found: {self.compose_file_path}")

    def start(self) -> None:
        """Start all services defined in docker-compose-test.yml"""
        logger.info("Starting RAG Stack testcontainers...")

        # Ensure Vault agent folders exist
        (self.project_root / "test-vault" / "agents" / "llm").mkdir(parents=True, exist_ok=True)
        (self.project_root / "test-vault" / "agent-out").mkdir(parents=True, exist_ok=True)

        self.compose = DockerCompose(
            str(self.project_root),
            compose_file_name=self.compose_file_path.name,
            pull=False
        )
        self.compose.start()

        # Bootstrap Vault dev: approle, policy, secrets
        self._bootstrap_vault_dev()

        # Wait for services and collect info
        self._wait_for_services()
        self._collect_service_info()
        logger.info("RAG Stack testcontainers started successfully")

    def stop(self) -> None:
        """Stop all services"""
        if self.compose:
            logger.info("Stopping RAG Stack testcontainers...")
            self.compose.stop()
            logger.info("RAG Stack testcontainers stopped")

    # -------------------- Vault bootstrap --------------------
    def _bootstrap_vault_dev(self) -> None:
        """
        Configure Vault dev for tests:
        - Enable approle
        - Write llm-orchestration policy
        - Create approle
        - Write role_id/secret_id files for Vault Agent
        - Put Azure OpenAI secret into KV v2
        """
        if self.compose is None:
            raise RuntimeError("compose not started")

        vault_host = self.compose.get_service_host("vault", 8200) or "localhost"
        vault_port = int(self.compose.get_service_port("vault", 8200) or 8200)
        base = f"http://{vault_host}:{vault_port}"
        headers = {"X-Vault-Token": "root"}  # dev token

        logger.info(f"Bootstrapping Vault at {base}")

        # Wait until Vault is healthy
        self._wait_http(f"{base}/v1/sys/health", expect_ok=True, timeout=60)

        # Enable approle if not present
        mounts = requests.get(f"{base}/v1/sys/auth", headers=headers, timeout=10).json()
        if "approle/" not in mounts:
            logger.info("Enabling approle auth method...")
            requests.post(
                f"{base}/v1/sys/auth/approle",
                headers=headers,
                json={"type": "approle"},
                timeout=10
            ).raise_for_status()

        # Write policy
        policy_name = "llm-orchestration"
        policy_hcl = """
path "secret/metadata/llm/*" { capabilities = ["list"] }
path "secret/data/llm/*"     { capabilities = ["read"] }
"""
        logger.info(f"Writing policy {policy_name}...")
        requests.put(
            f"{base}/v1/sys/policies/acl/{policy_name}",
            headers=headers,
            json={"policy": policy_hcl},
            timeout=10
        ).raise_for_status()

        # Create AppRole
        role_name = "llm-orchestration-service"
        role_body = {
            "token_policies": [policy_name],
            "token_ttl": "1h",
            "token_max_ttl": "24h",
            "secret_id_ttl": "24h",
            "secret_id_num_uses": 10,
            "bind_secret_id": True,
            "token_no_default_policy": True
        }
        logger.info(f"Creating AppRole {role_name}...")
        requests.post(
            f"{base}/v1/auth/approle/role/{role_name}",
            headers=headers,
            json=role_body,
            timeout=10
        ).raise_for_status()

        # Fetch role_id and secret_id
        rid_resp = requests.get(
            f"{base}/v1/auth/approle/role/{role_name}/role-id",
            headers=headers,
            timeout=10
        ).json()
        role_id = rid_resp["data"]["role_id"]

        sid_resp = requests.post(
            f"{base}/v1/auth/approle/role/{role_name}/secret-id",
            headers=headers,
            timeout=10
        ).json()
        secret_id = sid_resp["data"]["secret_id"]

        # Write to Vault Agent input dir
        agent_in = self.project_root / "test-vault" / "agents" / "llm"
        (agent_in / "role_id").write_text(role_id, encoding="utf-8")
        (agent_in / "secret_id").write_text(secret_id, encoding="utf-8")
        logger.info(f"Wrote role_id and secret_id to {agent_in}")

        # Write Azure OpenAI secret (values pulled from env vars or test defaults)
        endpoint = os.getenv(
            "AZURE_OPENAI_ENDPOINT"
        )
        api_key = os.getenv("AZURE_OPENAI_API_KEY", "TEST_API_KEY")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

        kv_path = "llm/connections/azure_openai/production/gpt-4o-mini"
        secret_body = {
            "data": {
                "connection_id": "1234",
                "endpoint": endpoint,
                "api_key": api_key,
                "deployment_name": deployment,
                "environment": "production",
                "model": "gpt-4o-mini",
                "api_version": "2024-05-01-preview",
                "tags": "azure,production,gpt-4o-mini"
            }
        }

        logger.info(f"Writing KV secret at secret/data/{kv_path} ...")
        requests.post(
            f"{base}/v1/secret/data/{kv_path}",
            headers=headers,
            json=secret_body,
            timeout=10
        ).raise_for_status()

        # Wait for Vault Agent token to appear
        token_path = self.project_root / "test-vault" / "agent-out" / "token"
        self._wait_for_file(token_path, timeout=90)
        logger.info(f"Vault Agent token is ready at {token_path}")

    def _wait_http(self, url: str, expect_ok: bool, timeout: int = 60) -> None:
        start = time.time()
        while time.time() - start < timeout:
            try:
                r = requests.get(url, timeout=5)
                if expect_ok and r.status_code in (200, 429):
                    return
            except Exception:
                pass
            time.sleep(1)
        raise TimeoutError(f"Timed out waiting for {url}")

    def _wait_for_file(self, path: Path, timeout: int = 60) -> None:
        start = time.time()
        while time.time() - start < timeout:
            if path.exists() and path.stat().st_size > 0:
                return
            time.sleep(1)
        raise TimeoutError(f"Timed out waiting for file: {path}")

    # -------------------- Service waits --------------------
    def _wait_for_services(self, total_timeout: int = 300) -> None:
        services_to_check = [
            ("qdrant", 6333, self._check_qdrant_service, 60),
            ("llm-orchestration-service", 8100, self._check_orchestration_service, 180),
        ]
        overall_start_time = time.time()
        for service_name, port, check_func, service_timeout in services_to_check:
            self._wait_for_single_service(
                service_name, port, check_func, service_timeout,
                overall_start_time, total_timeout
            )
        logger.info("Allowing additional 15s for services to stabilize...")
        time.sleep(15)
        total_elapsed = time.time() - overall_start_time
        logger.info(f"Service startup completed in {total_elapsed:.1f}s")

    def _wait_for_single_service(self, service_name: str, port: int, check_func: Any,
                                 service_timeout: int, overall_start_time: float, total_timeout: int) -> None:
        if self.compose is None:
            logger.error("Docker compose not initialized")
            return
        service_ready = False
        start_time = time.time()
        logger.info(f"Waiting up to {service_timeout}s for {service_name}...")
        while not service_ready and (time.time() - start_time) < service_timeout:
            try:
                host = self.compose.get_service_host(service_name, port)
                mapped_port = self.compose.get_service_port(service_name, port)
                if host and mapped_port and check_func(host, mapped_port):
                    service_ready = True
                    elapsed = time.time() - start_time
                    logger.info(f"{service_name} ready at {host}:{mapped_port} (took {elapsed:.1f}s)")
                else:
                    time.sleep(5)
            except Exception as e:
                logger.debug(f"Waiting for {service_name}: {e}")
                time.sleep(5)
            if (time.time() - overall_start_time) > total_timeout:
                logger.warning(f"Timeout reached for {service_name}")
                return
        if not service_ready:
            logger.warning(f"{service_name} failed to start in {service_timeout}s")

    def _check_qdrant_service(self, host: str, port: int) -> bool:
        try:
            r = requests.get(f"http://{host}:{port}/collections", timeout=10)
            return r.status_code == 200
        except Exception:
            return False

    def _check_orchestration_service(self, host: str, port: int) -> bool:
        try:
            r = requests.get(f"http://{host}:{port}/health", timeout=10)
            if r.status_code == 200:
                health_data = r.json()
                return (
                    health_data.get("status") == "healthy" and
                    health_data.get("orchestration_service") == "initialized"
                )
            return False
        except Exception:
            return False

    def _collect_service_info(self) -> None:
        if self.compose is None:
            return
        for service_name, port in [("qdrant", 6333), ("llm-orchestration-service", 8100)]:
            try:
                host = self.compose.get_service_host(service_name, port)
                mapped_port = self.compose.get_service_port(service_name, port)
                if host and mapped_port:
                    self.services_info[service_name] = {
                        "host": host,
                        "port": mapped_port,
                        "url": f"http://{host}:{mapped_port}"
                    }
            except Exception as e:
                logger.warning(f"Could not collect info for {service_name}: {e}")

    def get_orchestration_service_url(self) -> str:
        if "llm-orchestration-service" not in self.services_info:
            raise ValueError("llm-orchestration-service not found")
        return self.services_info["llm-orchestration-service"]["url"]

    def get_qdrant_url(self) -> str:
        if "qdrant" not in self.services_info:
            raise ValueError("qdrant not found")
        return self.services_info["qdrant"]["url"]

    def is_service_available(self, service_name: str) -> bool:
        if service_name not in self.services_info:
            return False
        svc = self.services_info[service_name]
        if service_name == "qdrant":
            return self._check_qdrant_service(svc["host"], svc["port"])
        elif service_name == "llm-orchestration-service":
            return self._check_orchestration_service(svc["host"], svc["port"])
        return False

    def get_all_services_info(self) -> Dict[str, Dict[str, Any]]:
        return dict(self.services_info)


# -------------------- Pytest fixtures --------------------
@pytest.fixture(scope="session")
def rag_stack() -> Generator[RAGStackTestContainers, None, None]:
    stack = RAGStackTestContainers()
    try:
        stack.start()
        yield stack
    finally:
        stack.stop()


@pytest.fixture(scope="function")
def orchestration_client(rag_stack: RAGStackTestContainers) -> requests.Session:
    base_url = rag_stack.get_orchestration_service_url()
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Accept": "application/json"
    })
    setattr(session, "base_url", base_url)
    return session
