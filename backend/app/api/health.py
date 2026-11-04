"""Health check endpoints."""

from datetime import datetime, timezone
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import __version__

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response payload."""
    status: str = Field(default="ok", description="Service health status")
    app: str = Field(default="mcp-releaseproof", description="Application identifier")
    version: str = Field(default=__version__, description="Application version")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Current UTC timestamp",
    )


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Return application health and version information."""
    return HealthResponse()

