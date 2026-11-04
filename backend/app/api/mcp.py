"""MCP server discovery, tool extraction, and version diffing API endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.config import get_settings
from app.schemas.mcp import (
    CompareMCPToolsRequest,
    CompareMCPToolsResponse,
    DiscoverMCPRequest,
    DiscoverMCPResponse,
)
from app.services.github_service import (
    GitHubError,
    GitHubRateLimitError,
    GitHubService,
    GitHubTimeoutError,
    InvalidRepositoryURLError,
    RefNotFoundError,
    RepositoryNotFoundError,
    parse_github_repository_url,
)
from app.services.mcp_service import MCPService

router = APIRouter(prefix="/mcp", tags=["mcp"])


def get_mcp_service() -> MCPService:
    settings = get_settings()
    github = GitHubService(
        base_url=settings.GITHUB_API_BASE_URL,
        github_token=settings.GITHUB_TOKEN,
    )
    return MCPService(github)


@router.post("/discover", response_model=DiscoverMCPResponse)
async def discover_mcp_server(request: DiscoverMCPRequest) -> DiscoverMCPResponse:
    """Discover MCP server indicators and statically extract available tools and input schemas from a Git ref."""
    try:
        parse_github_repository_url(request.repository_url)
    except InvalidRepositoryURLError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.error_code, "message": exc.message},
        ) from exc

    service = get_mcp_service()
    try:
        return await service.discover_tools_for_ref(
            repository_url=request.repository_url,
            ref=request.ref,
        )
    except (
        InvalidRepositoryURLError,
        RepositoryNotFoundError,
        RefNotFoundError,
        GitHubRateLimitError,
        GitHubTimeoutError,
        GitHubError,
    ) as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.error_code, "message": exc.message},
        ) from exc


@router.post("/compare", response_model=CompareMCPToolsResponse)
async def compare_mcp_tools(request: CompareMCPToolsRequest) -> CompareMCPToolsResponse:
    """Discover and compare MCP tool definitions and schemas between baseline and candidate Git refs."""
    try:
        parse_github_repository_url(request.repository_url)
    except InvalidRepositoryURLError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.error_code, "message": exc.message},
        ) from exc

    service = get_mcp_service()
    try:
        return await service.compare_tools_between_refs(
            repository_url=request.repository_url,
            baseline_ref=request.baseline_ref,
            candidate_ref=request.candidate_ref,
        )
    except (
        InvalidRepositoryURLError,
        RepositoryNotFoundError,
        RefNotFoundError,
        GitHubRateLimitError,
        GitHubTimeoutError,
        GitHubError,
    ) as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.error_code, "message": exc.message},
        ) from exc

