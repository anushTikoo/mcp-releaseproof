"""Control plane service managing communication with the Vultr Compute Sandbox Agent."""

import json
import logging
from typing import Optional
import httpx

from agent.auth import sign_request
from agent.driver.mock_driver import MockSandboxExecutionDriver
from agent.manager import SandboxLifecycleManager
from app.config import get_settings
from app.schemas.sandbox import (
    SandboxCapabilitiesResponse,
    SandboxExecutionRequest,
    SandboxExecutionResult,
)
from app.services.harness_validator import HarnessValidator

logger = logging.getLogger(__name__)


class SandboxService:
    """Dispatches execution jobs to the remote agent or local mock driver."""

    def __init__(self):
        self.settings = get_settings()
        self._validator = HarnessValidator()
        # Default mock manager for local development and unit tests
        self._mock_driver = MockSandboxExecutionDriver()
        self._mock_manager = SandboxLifecycleManager(driver=self._mock_driver)

    def set_mock_driver(self, driver: MockSandboxExecutionDriver) -> None:
        """Inject configured mock driver for unit and integration testing."""
        self._mock_driver = driver
        self._mock_manager = SandboxLifecycleManager(driver=driver)

    def _create_http_client(self, timeout: float) -> httpx.AsyncClient:
        """Create httpx client with optional custom CA or mTLS certs for secure communication."""
        verify = self.settings.SANDBOX_AGENT_CA_CERT_PATH or True
        cert = None
        if self.settings.SANDBOX_AGENT_CLIENT_CERT_PATH and self.settings.SANDBOX_AGENT_CLIENT_KEY_PATH:
            cert = (self.settings.SANDBOX_AGENT_CLIENT_CERT_PATH, self.settings.SANDBOX_AGENT_CLIENT_KEY_PATH)
        return httpx.AsyncClient(timeout=timeout, verify=verify, cert=cert)

    async def execute_harness(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        """Execute harness via the configured sandbox mode (agent RPC or mock)."""
        # Hard execution gate: static verdict REJECTED must never be submitted
        preflight = self._validator.validate(code=request.harness_code, tools=request.tools, test_plan=request.test_plan)
        if not preflight.syntax_valid:
            raise ValueError(f"Execution gate rejected syntax-invalid harness: {preflight.rejection_reasons}")
        if not preflight.security_valid:
            raise ValueError(f"Execution gate rejected security-invalid harness: {preflight.rejection_reasons}")
        if not preflight.structure_valid:
            raise ValueError(f"Execution gate rejected structure-invalid harness: {preflight.rejection_reasons}")
        if request.tools and not preflight.is_valid:
            raise ValueError(f"Execution gate rejected statically invalid harness: {preflight.rejection_reasons}")

        mode = self.settings.SANDBOX_MODE.lower()

        if mode == "agent":
            # Remote agent execution over authenticated HTTPS / private VPC
            agent_url = self.settings.SANDBOX_AGENT_URL.rstrip("/")
            endpoint = f"{agent_url}/agent/jobs/submit"
            path = "/agent/jobs/submit"
            secret = self.settings.WORKER_SHARED_SECRET

            if not secret:
                raise ValueError("WORKER_SHARED_SECRET is not configured on control plane")

            body_bytes = request.model_dump_json().encode("utf-8")
            signed_headers, _ = sign_request(
                secret=secret,
                method="POST",
                path=path,
                body=body_bytes,
            )
            headers = {
                "Content-Type": "application/json",
                **signed_headers,
            }

            async with self._create_http_client(timeout=float(request.timeout_seconds + 30)) as client:
                resp = await client.post(endpoint, content=body_bytes, headers=headers)
                if resp.status_code != 200:
                    raise RuntimeError(f"Agent execution request failed ({resp.status_code}): {resp.text}")
                return SandboxExecutionResult.model_validate(resp.json())

        # Mock driver execution for zero-execution local development and testing
        return await self._mock_manager.execute_job(request)

    async def get_job_status(self, job_id: str) -> Optional[SandboxExecutionResult]:
        """Query status of a specific execution job."""
        mode = self.settings.SANDBOX_MODE.lower()

        if mode == "agent":
            agent_url = self.settings.SANDBOX_AGENT_URL.rstrip("/")
            endpoint = f"{agent_url}/agent/jobs/{job_id}/status"
            path = f"/agent/jobs/{job_id}/status"
            secret = self.settings.WORKER_SHARED_SECRET

            if not secret:
                raise ValueError("WORKER_SHARED_SECRET is not configured on control plane")

            signed_headers, _ = sign_request(
                secret=secret,
                method="GET",
                path=path,
                body=b"",
            )
            async with self._create_http_client(timeout=10.0) as client:
                resp = await client.get(endpoint, headers=signed_headers)
                if resp.status_code == 404:
                    return None
                if resp.status_code != 200:
                    raise RuntimeError(f"Agent job query failed ({resp.status_code}): {resp.text}")
                return SandboxExecutionResult.model_validate(resp.json())

        return self._mock_manager.get_job(job_id)

    async def abort_job(self, job_id: str) -> Optional[SandboxExecutionResult]:
        """Abort an in-flight job via authenticated agent RPC or local mock manager."""
        mode = self.settings.SANDBOX_MODE.lower()

        if mode == "agent":
            agent_url = self.settings.SANDBOX_AGENT_URL.rstrip("/")
            endpoint = f"{agent_url}/agent/jobs/{job_id}/abort"
            path = f"/agent/jobs/{job_id}/abort"
            secret = self.settings.WORKER_SHARED_SECRET

            if not secret:
                raise ValueError("WORKER_SHARED_SECRET is not configured on control plane")

            signed_headers, _ = sign_request(
                secret=secret,
                method="POST",
                path=path,
                body=b"",
            )
            async with self._create_http_client(timeout=15.0) as client:
                resp = await client.post(endpoint, headers=signed_headers)
                if resp.status_code == 404:
                    return None
                if resp.status_code != 200:
                    raise RuntimeError(f"Agent abort request failed ({resp.status_code}): {resp.text}")
                return SandboxExecutionResult.model_validate(resp.json())

        return await self._mock_manager.abort_job(job_id)

    def get_capabilities(self) -> SandboxCapabilitiesResponse:
        """Return supported capabilities and pre-warmed dependencies."""
        return SandboxCapabilitiesResponse(
            prewarmed_dependencies=[
                "mcp==1.2.1",
                "fastmcp==0.4.1",
                "pydantic==2.10.6",
                "pytest==8.3.4",
                "pytest-asyncio==0.25.3",
                "httpx==0.28.1",
                "anyio==4.8.0",
                "typing_extensions==4.12.2",
            ],
            runtime_network_mode="none",
            mcp_transport="stdio",
            default_timeout_seconds=self.settings.SANDBOX_DEFAULT_TIMEOUT_SECONDS,
            max_timeout_seconds=self.settings.SANDBOX_MAX_TIMEOUT_SECONDS,
            default_memory_mb=512,
            max_memory_mb=2048,
            enforced_security_features=[
                "non-root user (10001:10001)",
                "no-new-privileges:true",
                "cap-drop ALL",
                "read-only rootfs",
                "stdio MCP transport",
                "no network egress (--network none)",
                "no docker socket mounted",
                "ephemeral tmpfs on /tmp",
            ],
        )


_sandbox_service: Optional[SandboxService] = None


def get_sandbox_service() -> SandboxService:
    global _sandbox_service
    if _sandbox_service is None:
        _sandbox_service = SandboxService()
    return _sandbox_service
