"""API endpoints for Phase 6 Vultr Compute Sandbox Execution."""

import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.sandbox import (
    SandboxCapabilitiesResponse,
    SandboxExecutionRequest,
    SandboxExecutionResult,
)
from app.services.harness_validator import HarnessValidator
from app.services.sandbox_service import SandboxService, get_sandbox_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sandbox", tags=["sandbox"])
_validator = HarnessValidator()


@router.get("/capabilities", response_model=SandboxCapabilitiesResponse)
async def get_sandbox_capabilities(
    service: SandboxService = Depends(get_sandbox_service),
) -> SandboxCapabilitiesResponse:
    """Query available sandbox execution limits, pre-warmed dependencies, and security features."""
    return service.get_capabilities()


@router.post("/execute", response_model=SandboxExecutionResult)
async def execute_harness(
    request: SandboxExecutionRequest,
    service: SandboxService = Depends(get_sandbox_service),
) -> SandboxExecutionResult:
    """Dispatch a validated test harness to the isolated Vultr Compute sandbox."""
    # Hard execution gate: a harness with static verdict REJECTED must never be submitted
    preflight = _validator.validate(code=request.harness_code, tools=request.tools, test_plan=request.test_plan)
    if not preflight.syntax_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Execution gate rejected syntax-invalid harness: {preflight.rejection_reasons}",
        )
    if not preflight.security_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Execution gate rejected security-invalid harness: {preflight.rejection_reasons}",
        )
    if not preflight.structure_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Execution gate rejected structure-invalid harness: {preflight.rejection_reasons}",
        )
    if request.tools and not preflight.is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Execution gate rejected statically invalid harness: {preflight.rejection_reasons}",
        )

    try:
        result = await service.execute_harness(request)
        return result
    except Exception as exc:
        err_id = f"sbx-err-{uuid.uuid4().hex[:8]}"
        logger.exception("[%s] Unexpected sandbox execution error: %s", err_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sandbox execution dispatch failed due to internal error [{err_id}]. Please report this correlation ID.",
        )


@router.get("/jobs/{job_id}", response_model=SandboxExecutionResult)
async def get_job_status(
    job_id: str,
    service: SandboxService = Depends(get_sandbox_service),
) -> SandboxExecutionResult:
    """Retrieve execution and security audit results for a specific job."""
    job = await service.get_job_status(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sandbox job '{job_id}' not found.",
        )
    return job


@router.post("/jobs/{job_id}/abort", response_model=SandboxExecutionResult)
async def abort_job(
    job_id: str,
    service: SandboxService = Depends(get_sandbox_service),
) -> SandboxExecutionResult:
    """Abort an executing sandbox job and trigger immediate cleanup."""
    job = await service.abort_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sandbox job '{job_id}' not found.",
        )
    return job
