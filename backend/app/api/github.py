"""GitHub repository and commit comparison API routes."""

from fastapi import APIRouter, HTTPException, status

from app.config import get_settings
from app.schemas.github import (
    CompareCommitsRequest,
    CompareCommitsResponse,
    ResolveRefsRequest,
    ResolveRefsResponse,
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

router = APIRouter(prefix="/github", tags=["github"])


def get_github_service() -> GitHubService:
    settings = get_settings()
    return GitHubService(
        base_url=settings.GITHUB_API_BASE_URL,
        github_token=settings.GITHUB_TOKEN,
    )


@router.post("/resolve", response_model=ResolveRefsResponse)
async def resolve_refs(request: ResolveRefsRequest) -> ResolveRefsResponse:
    """Validate a public GitHub repository URL and resolve baseline and candidate refs to immutable commit SHAs."""
    try:
        owner, repo, canonical_url = parse_github_repository_url(request.repository_url)
    except InvalidRepositoryURLError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.error_code, "message": exc.message},
        ) from exc

    service = get_github_service()

    try:
        repo_metadata = await service.get_repository_metadata(owner, repo)
        baseline_commit = await service.resolve_ref(
            owner, repo, request.baseline_ref, ref_label="baseline"
        )
        candidate_commit = await service.resolve_ref(
            owner, repo, request.candidate_ref, ref_label="candidate"
        )

        is_identical = baseline_commit.sha == candidate_commit.sha

        return ResolveRefsResponse(
            status="success",
            repository=repo_metadata,
            baseline=baseline_commit,
            candidate=candidate_commit,
            is_identical=is_identical,
        )
    except (InvalidRepositoryURLError, RepositoryNotFoundError, RefNotFoundError, GitHubRateLimitError, GitHubTimeoutError, GitHubError) as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.error_code, "message": exc.message},
        ) from exc


@router.post("/compare", response_model=CompareCommitsResponse)
async def compare_commits(request: CompareCommitsRequest) -> CompareCommitsResponse:
    """Resolve baseline and candidate refs and retrieve comparison, commit metadata, and changed files."""
    try:
        owner, repo, canonical_url = parse_github_repository_url(request.repository_url)
    except InvalidRepositoryURLError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.error_code, "message": exc.message},
        ) from exc

    service = get_github_service()

    try:
        repo_metadata = await service.get_repository_metadata(owner, repo)
        baseline_commit = await service.resolve_ref(
            owner, repo, request.baseline_ref, ref_label="baseline"
        )
        candidate_commit = await service.resolve_ref(
            owner, repo, request.candidate_ref, ref_label="candidate"
        )

        comparison = await service.compare_commits(
            owner, repo, baseline_commit.sha, candidate_commit.sha
        )

        return CompareCommitsResponse(
            status="success",
            repository=repo_metadata,
            baseline=baseline_commit,
            candidate=candidate_commit,
            comparison=comparison,
        )
    except (InvalidRepositoryURLError, RepositoryNotFoundError, RefNotFoundError, GitHubRateLimitError, GitHubTimeoutError, GitHubError) as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.error_code, "message": exc.message},
        ) from exc

