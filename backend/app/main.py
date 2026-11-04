"""FastAPI application entrypoint for MCP ReleaseProof control plane."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.health import get_health, router as health_router
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="MCP ReleaseProof Control Plane",
        description="AI-assisted, sandboxed release verification for Model Context Protocol servers.",
        version=__version__,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes (prefixed with /api per docs/API_CONTRACT.md)
    app.include_router(health_router, prefix="/api")

    # Root health probe alias (/health)
    app.add_api_route("/health", get_health, methods=["GET"], tags=["health"])

    return app


app = create_app()

