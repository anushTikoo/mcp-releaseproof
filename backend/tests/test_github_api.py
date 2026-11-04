"""Integration tests for GitHub API endpoints (/api/github/resolve and /api/github/compare)."""

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch, MagicMock

from app.main import create_app
from app.schemas.github import (
    CommitMetadata,
    ComparisonSummary,
    RepositoryMetadata,
)
from app.services.github_service import (
    GitHubRateLimitError,
    GitHubTimeoutError,
    RefNotFoundError,
    RepositoryNotFoundError,
)

SAMPLE_REPO_META = RepositoryMetadata(
    owner="modelcontextprotocol",
    name="servers",
    full_name="modelcontextprotocol/servers",
    description="Reference MCP servers repository",
    html_url="https://github.com/modelcontextprotocol/servers",
    default_branch="main",
    is_private=False,
    stars_count=1500,
    forks_count=300,
    open_issues_count=10,
)

SAMPLE_COMMIT_A = CommitMetadata(
    ref="v1.0.0",
    sha="1111111111111111111111111111111111111111",
    short_sha="1111111",
    message="Release v1.0.0",
    author_name="Alice Dev",
    author_date="2026-11-01T12:00:00Z",
    committer_name="Alice Dev",
    committed_at="2026-11-01T12:00:00Z",
    html_url="https://github.com/modelcontextprotocol/servers/commit/1111111",
)

SAMPLE_COMMIT_B = CommitMetadata(
    ref="v1.1.0",
    sha="2222222222222222222222222222222222222222",
    short_sha="2222222",
    message="Release v1.1.0 with security patches",
    author_name="Bob Dev",
    author_date="2026-11-04T12:00:00Z",
    committer_name="Bob Dev",
    committed_at="2026-11-04T12:00:00Z",
    html_url="https://github.com/modelcontextprotocol/servers/commit/2222222",
)

SAMPLE_COMPARISON = ComparisonSummary(
    status="ahead",
    ahead_by=1,
    behind_by=0,
    total_commits=1,
    files_changed_count=1,
    additions=10,
    deletions=2,
    is_identical=False,
    is_truncated=False,
    files=[
        {
            "filename": "src/server.py",
            "status": "modified",
            "additions": 10,
            "deletions": 2,
            "changes": 12,
            "patch": "@@ -1,2 +1,10 @@",
        }
    ],
)


@pytest.mark.asyncio
async def test_resolve_refs_success():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.services.github_service.GitHubService.get_repository_metadata", return_value=SAMPLE_REPO_META), \
             patch("app.services.github_service.GitHubService.resolve_ref", side_effect=[SAMPLE_COMMIT_A, SAMPLE_COMMIT_B]):
            
            resp = await client.post(
                "/api/github/resolve",
                json={
                    "repository_url": "https://github.com/modelcontextprotocol/servers",
                    "baseline_ref": "v1.0.0",
                    "candidate_ref": "v1.1.0",
                },
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert data["repository"]["full_name"] == "modelcontextprotocol/servers"
            assert data["baseline"]["sha"] == "1111111111111111111111111111111111111111"
            assert data["candidate"]["sha"] == "2222222222222222222222222222222222222222"
            assert data["is_identical"] is False


@pytest.mark.asyncio
async def test_resolve_refs_identical():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.services.github_service.GitHubService.get_repository_metadata", return_value=SAMPLE_REPO_META), \
             patch("app.services.github_service.GitHubService.resolve_ref", side_effect=[SAMPLE_COMMIT_A, SAMPLE_COMMIT_A]):
            
            resp = await client.post(
                "/api/github/resolve",
                json={
                    "repository_url": "https://github.com/modelcontextprotocol/servers",
                    "baseline_ref": "v1.0.0",
                    "candidate_ref": "v1.0.0",
                },
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["is_identical"] is True


@pytest.mark.asyncio
async def test_resolve_refs_invalid_url():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/github/resolve",
            json={
                "repository_url": "http://insecure-github.com/owner/repo",
                "baseline_ref": "main",
                "candidate_ref": "dev",
            },
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["code"] == "INVALID_REPOSITORY_URL"


@pytest.mark.asyncio
async def test_resolve_refs_repo_not_found():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.services.github_service.GitHubService.get_repository_metadata", side_effect=RepositoryNotFoundError("Repo not found")):
            resp = await client.post(
                "/api/github/resolve",
                json={
                    "repository_url": "https://github.com/nonexistent/repo",
                    "baseline_ref": "main",
                    "candidate_ref": "dev",
                },
            )
            assert resp.status_code == 404
            assert resp.json()["detail"]["code"] == "REPOSITORY_NOT_FOUND"


@pytest.mark.asyncio
async def test_resolve_refs_ref_not_found():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.services.github_service.GitHubService.get_repository_metadata", return_value=SAMPLE_REPO_META), \
             patch("app.services.github_service.GitHubService.resolve_ref", side_effect=RefNotFoundError("Ref not found")):
            resp = await client.post(
                "/api/github/resolve",
                json={
                    "repository_url": "https://github.com/modelcontextprotocol/servers",
                    "baseline_ref": "bad-ref",
                    "candidate_ref": "main",
                },
            )
            assert resp.status_code == 404
            assert resp.json()["detail"]["code"] == "REF_NOT_FOUND"


@pytest.mark.asyncio
async def test_compare_commits_success():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.services.github_service.GitHubService.get_repository_metadata", return_value=SAMPLE_REPO_META), \
             patch("app.services.github_service.GitHubService.resolve_ref", side_effect=[SAMPLE_COMMIT_A, SAMPLE_COMMIT_B]), \
             patch("app.services.github_service.GitHubService.compare_commits", return_value=SAMPLE_COMPARISON):
            
            resp = await client.post(
                "/api/github/compare",
                json={
                    "repository_url": "https://github.com/modelcontextprotocol/servers",
                    "baseline_ref": "v1.0.0",
                    "candidate_ref": "v1.1.0",
                },
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert data["comparison"]["status"] == "ahead"
            assert data["comparison"]["files_changed_count"] == 1
            assert len(data["comparison"]["files"]) == 1
            assert data["comparison"]["files"][0]["filename"] == "src/server.py"


@pytest.mark.asyncio
async def test_compare_commits_rate_limited():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.services.github_service.GitHubService.get_repository_metadata", side_effect=GitHubRateLimitError("Rate limit exceeded")):
            resp = await client.post(
                "/api/github/compare",
                json={
                    "repository_url": "https://github.com/modelcontextprotocol/servers",
                    "baseline_ref": "v1.0.0",
                    "candidate_ref": "v1.1.0",
                },
            )
            assert resp.status_code == 429
            assert resp.json()["detail"]["code"] == "GITHUB_RATE_LIMITED"


@pytest.mark.asyncio
async def test_compare_commits_timeout():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.services.github_service.GitHubService.get_repository_metadata", side_effect=GitHubTimeoutError("GitHub timed out")):
            resp = await client.post(
                "/api/github/compare",
                json={
                    "repository_url": "https://github.com/modelcontextprotocol/servers",
                    "baseline_ref": "v1.0.0",
                    "candidate_ref": "v1.1.0",
                },
            )
            assert resp.status_code == 504
            assert resp.json()["detail"]["code"] == "GITHUB_TIMEOUT"

