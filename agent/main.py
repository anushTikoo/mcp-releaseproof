"""FastAPI application entrypoint for Sandbox Execution Agent."""

import logging
from typing import Optional
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from agent.auth import (
    HEADER_NONCE,
    HEADER_SIGNATURE,
    HEADER_TIMESTAMP,
    AuthenticationError,
    verify_request_signature,
)
from agent.config import get_agent_settings
from agent.driver.base import ISandboxExecutionDriver
from agent.driver.docker_driver import DockerExecutionDriver
from agent.driver.mock_driver import MockSandboxExecutionDriver
from agent.manager import SandboxLifecycleManager
from backend.app.schemas.sandbox import (
    SandboxCapabilitiesResponse,
    SandboxExecutionRequest,
    SandboxExecutionResult,
)

logger = logging.getLogger(__name__)

settings = get_agent_settings()

# Default to Docker driver in production on worker host; can be injected with mock driver for tests
_driver: Optional[ISandboxExecutionDriver] = None
_manager: Optional[SandboxLifecycleManager] = None


def get_driver() -> ISandboxExecutionDriver:
    global _driver
    if _driver is None:
        _driver = DockerExecutionDriver()
    return _driver


def set_driver(driver: ISandboxExecutionDriver) -> None:
    global _driver, _manager
    _driver = driver
    _manager = SandboxLifecycleManager(driver=driver, settings=settings)


def get_manager() -> SandboxLifecycleManager:
    global _manager
    if _manager is None:
        _manager = SandboxLifecycleManager(driver=get_driver(), settings=settings)
    return _manager


def create_agent_app() -> FastAPI:
    app = FastAPI(
        title="MCP ReleaseProof Sandbox Execution Agent",
        description="Narrowly scoped execution agent running on Vultr Compute worker host.",
        version="0.1.0",
    )

    async def verify_hmac_auth(
        request: Request,
        x_releaseproof_signature: Optional[str] = Header(None, alias=HEADER_SIGNATURE),
        x_releaseproof_timestamp: Optional[str] = Header(None, alias=HEADER_TIMESTAMP),
        x_releaseproof_nonce: Optional[str] = Header(None, alias=HEADER_NONCE),
    ) -> None:
        """Enforce HMAC signature, timestamp expiry, and replay protection."""
        secret = settings.WORKER_SHARED_SECRET
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Worker shared secret is not configured on the agent host.",
            )

        body_bytes = await request.body()
        try:
            verify_request_signature(
                secret=secret,
                method=request.method,
                path=request.url.path,
                body=body_bytes,
                signature=x_releaseproof_signature,
                timestamp_str=x_releaseproof_timestamp,
                nonce=x_releaseproof_nonce,
            )
        except AuthenticationError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
            )

    @app.get("/agent/health")
    async def agent_health():
        """Public probe reporting agent status and pre-warmed dependencies."""
        return {
            "status": "healthy",
            "service": "mcp-sandbox-agent",
            "driver": type(get_driver()).__name__,
            "prewarmed_dependencies": settings.PREWARMED_PACKAGES,
        }

    @app.get("/agent/capabilities", response_model=SandboxCapabilitiesResponse)
    async def agent_capabilities():
        """Public capabilities reporting supported limits and isolation features."""
        return SandboxCapabilitiesResponse(
            prewarmed_dependencies=settings.PREWARMED_PACKAGES,
            runtime_network_mode="none",
            mcp_transport="stdio",
            default_timeout_seconds=60,
            max_timeout_seconds=settings.MAX_JOB_TIMEOUT_SECONDS,
            default_memory_mb=512,
            max_memory_mb=2048,
            enforced_security_features=[
                f"non-root user ({settings.SANDBOX_CONTAINER_USER})",
                "no-new-privileges:true",
                "cap-drop ALL",
                "read-only rootfs",
                "stdio MCP transport",
                "no network egress (--network none)",
                "no docker socket mounted",
                "ephemeral tmpfs on /tmp",
            ],
        )

    @app.post("/agent/jobs/submit", response_model=SandboxExecutionResult)
    async def submit_job(
        request_data: SandboxExecutionRequest,
        _auth: None = Depends(verify_hmac_auth),
    ) -> SandboxExecutionResult:
        """Execute a validated test harness within the isolated sandbox container."""
        manager = get_manager()
        result = await manager.execute_job(request_data)
        return result

    @app.get("/agent/jobs/{job_id}/status", response_model=SandboxExecutionResult)
    async def get_job_status(
        job_id: str,
        _auth: None = Depends(verify_hmac_auth),
    ) -> SandboxExecutionResult:
        """Query execution and audit state for a specific job."""
        manager = get_manager()
        job = manager.get_job(job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job '{job_id}' not found.",
            )
        return job

    @app.post("/agent/jobs/{job_id}/abort", response_model=SandboxExecutionResult)
    async def abort_job(
        job_id: str,
        _auth: None = Depends(verify_hmac_auth),
    ) -> SandboxExecutionResult:
        """Abort an in-flight job, terminating its container and cleaning its workspace."""
        manager = get_manager()
        result = await manager.abort_job(job_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job '{job_id}' not found.",
            )
        return result

    return app


agent_app = create_agent_app()
