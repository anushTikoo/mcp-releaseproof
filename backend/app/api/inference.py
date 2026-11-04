"""Inference API endpoints."""

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, status

from app.config import get_settings
from app.schemas.inference import (
    GenerationRequest,
    GenerationResponse,
    InferenceConfigStatus,
)
from app.services.vultr_client import (
    DEFAULT_BENCHMARK_MODELS,
    VultrAuthenticationError,
    VultrInferenceError,
    VultrModelMismatchError,
    VultrRateLimitError,
    VultrClient,
)

router = APIRouter(prefix="/inference", tags=["inference"])


def get_vultr_client() -> VultrClient:
    settings = get_settings()
    return VultrClient(
        base_url=settings.VULTR_INFERENCE_BASE_URL or "https://api.vultrinference.com/v1",
        api_key=settings.VULTR_INFERENCE_API_KEY,
        default_model=settings.VULTR_INFERENCE_MODEL or "qwen3.8-flash-next",
        default_max_tokens=settings.VULTR_INFERENCE_MAX_TOKENS,
    )


@router.get("/status", response_model=InferenceConfigStatus)
async def get_inference_status() -> InferenceConfigStatus:
    """Check inference configuration without making paid inference calls."""
    settings = get_settings()
    client = get_vultr_client()
    return InferenceConfigStatus(
        api_key_configured=client.is_configured(),
        configured_model=settings.VULTR_INFERENCE_MODEL or "qwen3.8-flash-next",
        base_url=settings.VULTR_INFERENCE_BASE_URL or "https://api.vultrinference.com/v1",
        benchmark_models=DEFAULT_BENCHMARK_MODELS,
    )


@router.get("/catalog")
async def get_model_catalog() -> Dict[str, Any]:
    """Retrieve the live Vultr Serverless Inference model catalog (free metadata endpoint)."""
    client = get_vultr_client()
    try:
        models = await client.list_models()
        return {
            "status": "success",
            "count": len(models),
            "benchmark_models": [
                m for m in models if m.get("id") in DEFAULT_BENCHMARK_MODELS
            ],
            "models": [
                {
                    "id": m.get("id"),
                    "name": m.get("name"),
                    "description": m.get("description"),
                }
                for m in models
            ],
        }
    except VultrInferenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/generate-plan", response_model=GenerationResponse)
async def generate_plan(request: GenerationRequest) -> GenerationResponse:
    """Generate a structured test plan for MCP tools using Vultr Serverless Inference."""
    client = get_vultr_client()

    if not client.is_configured():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vultr Inference API key is not configured. Please set VULTR_INFERENCE_API_KEY in the backend environment.",
        )

    try:
        result = await client.generate_test_plan(
            repository_url=request.repository_url,
            tools=request.tools,
            model_id=request.model_id,
            max_tokens=request.max_tokens,
        )
        return GenerationResponse(
            status="success",
            model=result["model"],
            plan=result["plan"],
            usage=result.get("usage"),
            duration_ms=result["duration_ms"],
        )
    except VultrAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Vultr inference authentication failed. Verify VULTR_INFERENCE_API_KEY.",
        ) from exc
    except VultrRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Vultr inference rate limit reached. Please retry shortly.",
        ) from exc
    except VultrModelMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=exc.message,
        ) from exc
    except VultrInferenceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.error_code,
                "message": exc.message,
                "upstream_status": exc.upstream_status,
            },
        ) from exc

