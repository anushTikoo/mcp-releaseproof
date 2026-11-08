"""API endpoints for Phase 5 test harness generation and static security validation."""

import logging
import uuid
from fastapi import APIRouter, HTTPException, status

from app.api.inference import get_vultr_client
from app.schemas.harness import (
    GenerateHarnessRequest,
    GenerateHarnessResponse,
    ValidateHarnessRequest,
    ValidateHarnessResponse,
)
from app.services.harness_generator import HarnessGenerator
from app.services.harness_validator import HarnessValidator
from app.services.vultr_client import (
    VultrAuthenticationError,
    VultrInferenceError,
    VultrRateLimitError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/harness", tags=["harness"])

_validator = HarnessValidator()


def get_harness_generator() -> HarnessGenerator:
    client = get_vultr_client()
    return HarnessGenerator(vultr_client=client, validator=_validator)


@router.post("/generate", response_model=GenerateHarnessResponse)
async def generate_harness(request: GenerateHarnessRequest) -> GenerateHarnessResponse:
    """Generate an executable test harness using Vultr inference and statically validate it."""
    client = get_vultr_client()
    if not client.is_configured():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vultr Inference API key is not configured. Please set VULTR_INFERENCE_API_KEY in the backend environment.",
        )

    # Check inventory and schema resource limits upfront
    limit_err = _validator.check_inventory_limits(request.tools)
    if limit_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=limit_err,
        )

    generator = get_harness_generator()
    try:
        response = await generator.generate_harness(request)
        return response
    except VultrAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Vultr inference authentication failed. Verify VULTR_INFERENCE_API_KEY.",
        ) from exc
    except VultrRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Vultr inference rate limit exceeded.",
        ) from exc
    except VultrInferenceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"Harness generation error ({exc.error_code}): {exc.message}",
        ) from exc
    except Exception as exc:
        gen_err_id = f"gen-err-{uuid.uuid4().hex[:8]}"
        logger.exception("[%s] Unexpected internal error during test harness generation: %s", gen_err_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test harness generation failed due to internal error [{gen_err_id}]. Please report this correlation ID.",
        )


@router.post("/validate", response_model=ValidateHarnessResponse)
async def validate_harness(request: ValidateHarnessRequest) -> ValidateHarnessResponse:
    """Statically audit a Python test harness using AST without executing it."""
    # Check inventory and schema resource limits upfront
    limit_err = _validator.check_inventory_limits(request.tools)
    if limit_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=limit_err,
        )

    try:
        validation_result = _validator.validate(
            code=request.harness_code,
            tools=request.tools,
            test_plan=request.test_plan,
        )
        return ValidateHarnessResponse(
            status="valid" if validation_result.is_valid else "rejected",
            validation=validation_result,
        )
    except Exception as exc:
        err_id = f"val-err-{uuid.uuid4().hex[:8]}"
        logger.exception("[%s] Unexpected internal error in harness validation endpoint: %s", err_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Static validation failed due to internal validator error [{err_id}]. Please report this correlation ID.",
        )

