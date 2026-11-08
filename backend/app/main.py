"""FastAPI application entrypoint for MCP ReleaseProof control plane."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app import __version__
from app.api.github import router as github_router
from app.api.harness import router as harness_router
from app.api.health import get_health, router as health_router
from app.api.inference import router as inference_router
from app.api.mcp import router as mcp_router
from app.api.sandbox import router as sandbox_router
from app.config import get_settings
from app.schemas.harness import MAX_HARNESS_REQUEST_BODY_BYTES


class _PayloadTooLargeError(Exception):
    """Raised when streaming request body exceeds configured limit."""
    pass


class RequestBodyLimitMiddleware:
    """Enforces maximum payload size for /api/harness endpoints before or during streaming."""

    def __init__(
        self,
        app: ASGIApp,
        max_bytes: int = MAX_HARNESS_REQUEST_BODY_BYTES,
        path_prefix: str = "/api/harness",
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.path_prefix = path_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not (path.startswith("/api/harness") or path.startswith("/api/sandbox")):
            await self.app(scope, receive, send)
            return

        # 1. Fast path: check Content-Length header upfront to avoid receiving any body
        for k, v in scope.get("headers", []):
            if k.lower() == b"content-length":
                try:
                    content_length = int(v.decode("latin1"))
                    if content_length > self.max_bytes:
                        resp = JSONResponse(
                            status_code=413,
                            content={
                                "detail": (
                                    f"Request payload exceeds maximum allowed size of {self.max_bytes} bytes "
                                    f"(Content-Length: {content_length})."
                                )
                            },
                        )
                        await resp(scope, receive, send)
                        return
                except (ValueError, UnicodeDecodeError):
                    pass
                break

        # 2. Streaming counter: protects against missing/chunked or misleading Content-Length headers
        body_chunks = []
        received_bytes = 0
        more_body = True
        while more_body:
            message = await receive()
            if message.get("type") == "http.request":
                chunk = message.get("body", b"")
                received_bytes += len(chunk)
                if received_bytes > self.max_bytes:
                    resp = JSONResponse(
                        status_code=413,
                        content={
                            "detail": (
                                f"Request payload stream exceeded maximum allowed size of {self.max_bytes} bytes."
                            )
                        },
                    )
                    await resp(scope, receive, send)
                    return
                body_chunks.append(chunk)
                more_body = message.get("more_body", False)
            else:
                break

        full_body = b"".join(body_chunks)
        sent = False

        async def cached_receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": full_body, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, cached_receive, send)


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

    # Payload size limit middleware for harness endpoints
    app.add_middleware(RequestBodyLimitMiddleware)

    # API routes (prefixed with /api per docs/API_CONTRACT.md)
    app.include_router(health_router, prefix="/api")
    app.include_router(inference_router, prefix="/api")
    app.include_router(github_router, prefix="/api")
    app.include_router(mcp_router, prefix="/api")
    app.include_router(harness_router, prefix="/api")
    app.include_router(sandbox_router, prefix="/api")

    # Root health probe alias (/health)
    app.add_api_route("/health", get_health, methods=["GET"], tags=["health"])

    return app


app = create_app()

