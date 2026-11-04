"""Integration tests for MCP API endpoints (/api/mcp/discover and /api/mcp/compare)."""

from unittest.mock import patch
from httpx import ASGITransport, AsyncClient
import pytest

from app.main import create_app
from app.schemas.github import CommitMetadata
from app.services.github_service import (
    GitHubRateLimitError,
    GitHubTimeoutError,
    RefNotFoundError,
    RepositoryNotFoundError,
)

SAMPLE_COMMIT_A = CommitMetadata(
    ref="v1.0.0",
    sha="1111111111111111111111111111111111111111",
    short_sha="1111111",
    message="Release v1.0.0",
    author_name="Alice Dev",
    committed_at="2026-11-01T12:00:00Z",
    committer_name="Alice Dev",
    html_url="https://github.com/example/mcp-server/commit/1111111",
)

SAMPLE_COMMIT_B = CommitMetadata(
    ref="v1.1.0",
    sha="2222222222222222222222222222222222222222",
    short_sha="2222222",
    message="Release v1.1.0",
    author_name="Alice Dev",
    committed_at="2026-11-04T12:00:00Z",
    committer_name="Alice Dev",
    html_url="https://github.com/example/mcp-server/commit/2222222",
)

SAMPLE_TREE = [
    {"path": "pyproject.toml", "type": "blob", "size": 150},
    {"path": "server.py", "type": "blob", "size": 500},
]

SAMPLE_PYPROJECT = """
[project]
name = "demo-server"
dependencies = ["mcp>=1.0.0"]
"""

SAMPLE_SERVER_A = '''
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("demo")

@mcp.tool()
def read_data(path: str) -> str:
    """Read data file."""
    return "ok"
'''

SAMPLE_SERVER_B = '''
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("demo")

@mcp.tool()
def read_data(path: str, max_records: int = 100) -> str:
    """Read data file with limits."""
    return "ok"

@mcp.tool()
def write_data(path: str, payload: str) -> str:
    """Write data to file."""
    return "ok"
'''


@pytest.mark.asyncio
async def test_discover_mcp_server_success():
    app = create_app()

    async def fake_get_file_content(owner, repo, file_path, commit_sha, max_size_bytes=524288):
        if file_path == "pyproject.toml":
            return SAMPLE_PYPROJECT
        if file_path == "server.py":
            return SAMPLE_SERVER_A
        return None

    with patch("app.services.github_service.GitHubService.resolve_ref", return_value=SAMPLE_COMMIT_A), \
         patch("app.services.github_service.GitHubService.get_commit_tree", return_value=SAMPLE_TREE), \
         patch("app.services.github_service.GitHubService.get_file_content", side_effect=fake_get_file_content):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/mcp/discover",
                json={
                    "repository_url": "https://github.com/example/mcp-server",
                    "ref": "v1.0.0",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["commit_sha"] == SAMPLE_COMMIT_A.sha
        discovery = data["discovery"]
        assert discovery["has_mcp_server"] is True
        assert discovery["confidence"] == "confirmed"
        assert discovery["framework"] == "fastmcp"
        assert len(discovery["extracted_tools"]) == 1
        assert discovery["extracted_tools"][0]["name"] == "read_data"


@pytest.mark.asyncio
async def test_discover_mcp_server_invalid_url():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/mcp/discover",
            json={
                "repository_url": "http://invalid-url.com/no-https",
                "ref": "main",
            },
        )

    assert resp.status_code == 400
    data = resp.json()
    assert data["detail"]["code"] == "INVALID_REPOSITORY_URL"


@pytest.mark.asyncio
async def test_discover_mcp_server_ref_not_found():
    app = create_app()

    with patch("app.services.github_service.GitHubService.resolve_ref", side_effect=RefNotFoundError("Ref 'nonexistent' not found")):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/mcp/discover",
                json={
                    "repository_url": "https://github.com/example/mcp-server",
                    "ref": "nonexistent",
                },
            )

        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["code"] == "REF_NOT_FOUND"


@pytest.mark.asyncio
async def test_compare_mcp_tools_success():
    app = create_app()

    async def fake_resolve_ref(owner, repo, ref, ref_label=None):
        if ref == "v1.0.0":
            return SAMPLE_COMMIT_A
        return SAMPLE_COMMIT_B

    async def fake_get_file_content(owner, repo, file_path, commit_sha, max_size_bytes=524288):
        if file_path == "pyproject.toml":
            return SAMPLE_PYPROJECT
        if file_path == "server.py":
            if commit_sha == SAMPLE_COMMIT_A.sha:
                return SAMPLE_SERVER_A
            return SAMPLE_SERVER_B
        return None

    with patch("app.services.github_service.GitHubService.resolve_ref", side_effect=fake_resolve_ref), \
         patch("app.services.github_service.GitHubService.get_commit_tree", return_value=SAMPLE_TREE), \
         patch("app.services.github_service.GitHubService.get_file_content", side_effect=fake_get_file_content):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/mcp/compare",
                json={
                    "repository_url": "https://github.com/example/mcp-server",
                    "baseline_ref": "v1.0.0",
                    "candidate_ref": "v1.1.0",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        summary = data["summary"]
        assert summary["total_baseline_tools"] == 1
        assert summary["total_candidate_tools"] == 2
        assert summary["added_count"] == 1  # write_data added
        assert summary["modified_count"] == 1  # read_data modified

        diffs = {d["tool_name"]: d for d in data["differences"]}
        assert diffs["write_data"]["change_type"] == "added"
        assert diffs["read_data"]["change_type"] in ("modified_both", "modified_schema")


@pytest.mark.asyncio
async def test_compare_mcp_tools_identical_refs():
    app = create_app()

    async def fake_get_file_content(owner, repo, file_path, commit_sha, max_size_bytes=524288):
        if file_path == "server.py":
            return SAMPLE_SERVER_A
        return SAMPLE_PYPROJECT

    with patch("app.services.github_service.GitHubService.resolve_ref", return_value=SAMPLE_COMMIT_A), \
         patch("app.services.github_service.GitHubService.get_commit_tree", return_value=SAMPLE_TREE), \
         patch("app.services.github_service.GitHubService.get_file_content", side_effect=fake_get_file_content):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/mcp/compare",
                json={
                    "repository_url": "https://github.com/example/mcp-server",
                    "baseline_ref": "main",
                    "candidate_ref": SAMPLE_COMMIT_A.sha,
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["unchanged_count"] == 1
        assert data["summary"]["added_count"] == 0
        assert data["summary"]["modified_count"] == 0
        assert data["differences"][0]["change_type"] == "unchanged"


@pytest.mark.asyncio
async def test_compare_mcp_tools_invalid_baseline_ref_422():
    app = create_app()

    async def fake_resolve_ref(owner, repo, ref, ref_label=None):
        label_prefix = f"{ref_label.capitalize()} reference" if ref_label else "Reference"
        if ref == "invalid-baseline":
            raise RefNotFoundError(
                f"{label_prefix} '{ref}' could not be resolved to a commit in repository '{owner}/{repo}'.",
                details={"ref": ref, "ref_label": ref_label},
            )
        return SAMPLE_COMMIT_B

    with patch("app.services.github_service.GitHubService.resolve_ref", side_effect=fake_resolve_ref):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/mcp/compare",
                json={
                    "repository_url": "https://github.com/example/mcp-server",
                    "baseline_ref": "invalid-baseline",
                    "candidate_ref": "v1.1.0",
                },
            )

        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["code"] == "REF_NOT_FOUND"
        assert "Baseline reference 'invalid-baseline' could not be resolved" in data["detail"]["message"]


@pytest.mark.asyncio
async def test_compare_mcp_tools_invalid_candidate_ref_422():
    app = create_app()

    async def fake_resolve_ref(owner, repo, ref, ref_label=None):
        label_prefix = f"{ref_label.capitalize()} reference" if ref_label else "Reference"
        if ref == "invalid-candidate":
            raise RefNotFoundError(
                f"{label_prefix} '{ref}' could not be resolved to a commit in repository '{owner}/{repo}'.",
                details={"ref": ref, "ref_label": ref_label},
            )
        return SAMPLE_COMMIT_A

    with patch("app.services.github_service.GitHubService.resolve_ref", side_effect=fake_resolve_ref):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/mcp/compare",
                json={
                    "repository_url": "https://github.com/example/mcp-server",
                    "baseline_ref": "v1.0.0",
                    "candidate_ref": "invalid-candidate",
                },
            )

        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["code"] == "REF_NOT_FOUND"
        assert "Candidate reference 'invalid-candidate' could not be resolved" in data["detail"]["message"]


@pytest.mark.asyncio
async def test_discover_mcp_client_only_repo():
    app = create_app()

    client_tree = [
        {"path": "pyproject.toml", "type": "blob", "size": 150},
        {"path": "client.py", "type": "blob", "size": 400},
    ]

    client_code = """
import asyncio
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

async def run():
    async with stdio_client(["server"]) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
"""

    async def fake_get_file_content(owner, repo, file_path, commit_sha, max_size_bytes=524288):
        if file_path == "pyproject.toml":
            return SAMPLE_PYPROJECT
        if file_path == "client.py":
            return client_code
        return None

    with patch("app.services.github_service.GitHubService.resolve_ref", return_value=SAMPLE_COMMIT_A), \
         patch("app.services.github_service.GitHubService.get_commit_tree", return_value=client_tree), \
         patch("app.services.github_service.GitHubService.get_file_content", side_effect=fake_get_file_content):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/mcp/discover",
                json={
                    "repository_url": "https://github.com/example/mcp-client",
                    "ref": "v1.0.0",
                },
            )

        assert resp.status_code == 200
        disc = resp.json()["discovery"]
        assert disc["has_mcp_server"] is False
        assert disc["has_mcp_client"] is True
        assert "client.py" in disc["client_entrypoints"]
        assert len(disc["extracted_tools"]) == 0
        assert len(disc["servers"]) == 0


@pytest.mark.asyncio
async def test_discover_mcp_multi_server_grouping():
    app = create_app()

    multi_tree = [
        {"path": "pyproject.toml", "type": "blob", "size": 150},
        {"path": "servers/sqlite_server.py", "type": "blob", "size": 400},
        {"path": "servers/git_server.py", "type": "blob", "size": 400},
    ]

    sqlite_code = """
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("sqlite-service")

@mcp.tool()
def query_db(sql: str) -> str:
    return "ok"
"""

    git_code = """
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("git-service")

@mcp.tool()
def get_status() -> str:
    return "clean"
"""

    async def fake_get_file_content(owner, repo, file_path, commit_sha, max_size_bytes=524288):
        if file_path == "pyproject.toml":
            return SAMPLE_PYPROJECT
        if file_path == "servers/sqlite_server.py":
            return sqlite_code
        if file_path == "servers/git_server.py":
            return git_code
        return None

    with patch("app.services.github_service.GitHubService.resolve_ref", return_value=SAMPLE_COMMIT_A), \
         patch("app.services.github_service.GitHubService.get_commit_tree", return_value=multi_tree), \
         patch("app.services.github_service.GitHubService.get_file_content", side_effect=fake_get_file_content):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/mcp/discover",
                json={
                    "repository_url": "https://github.com/example/multi-server",
                    "ref": "main",
                },
            )

        assert resp.status_code == 200
        disc = resp.json()["discovery"]
        assert disc["has_mcp_server"] is True
        assert len(disc["servers"]) == 2

        server_names = {s["name"] for s in disc["servers"]}
        assert "sqlite-service" in server_names
        assert "git-service" in server_names
        assert len(disc["extracted_tools"]) == 2


@pytest.mark.asyncio
async def test_discover_mcp_non_server_with_dependency_only():
    app = create_app()

    tree = [
        {"path": "pyproject.toml", "type": "blob", "size": 150},
        {"path": "utils.py", "type": "blob", "size": 200},
    ]

    async def fake_get_file_content(owner, repo, file_path, commit_sha, max_size_bytes=524288):
        if file_path == "pyproject.toml":
            return SAMPLE_PYPROJECT
        if file_path == "utils.py":
            return "def helper(): return 42"
        return None

    with patch("app.services.github_service.GitHubService.resolve_ref", return_value=SAMPLE_COMMIT_A), \
         patch("app.services.github_service.GitHubService.get_commit_tree", return_value=tree), \
         patch("app.services.github_service.GitHubService.get_file_content", side_effect=fake_get_file_content):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/mcp/discover",
                json={
                    "repository_url": "https://github.com/example/non-server",
                    "ref": "main",
                },
            )

        assert resp.status_code == 200
        disc = resp.json()["discovery"]
        # Dependency is present, but has_mcp_server is False because no server code exists
        assert disc["has_mcp_server"] is False
        assert disc["confidence"] == "inconclusive"
        assert len(disc["server_entrypoints"]) == 0
        assert len(disc["extracted_tools"]) == 0


@pytest.mark.asyncio
async def test_discover_mcp_rate_limit_failed_status():
    app = create_app()

    with patch("app.services.github_service.GitHubService.resolve_ref", return_value=SAMPLE_COMMIT_A), \
         patch("app.services.github_service.GitHubService.get_commit_tree", side_effect=GitHubRateLimitError("Rate limit exceeded")):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/mcp/discover",
                json={
                    "repository_url": "https://github.com/example/mcp-server",
                    "ref": "main",
                },
            )

        assert resp.status_code == 200
        disc = resp.json()["discovery"]
        assert disc["extraction_status"] == "FAILED"
        assert any("rate limit" in w.lower() for w in disc["extraction_warnings"])


@pytest.mark.asyncio
async def test_discover_mcp_partial_file_read_error():
    app = create_app()

    tree = [
        {"path": "pyproject.toml", "type": "blob", "size": 150},
        {"path": "server.py", "type": "blob", "size": 300},
        {"path": "broken.py", "type": "blob", "size": 300},
    ]

    async def fake_get_file_content(owner, repo, file_path, commit_sha, max_size_bytes=524288):
        if file_path == "pyproject.toml":
            return SAMPLE_PYPROJECT
        if file_path == "server.py":
            return SAMPLE_SERVER_A
        if file_path == "broken.py":
            raise RuntimeError("Corrupted file on GitHub")
        return None

    with patch("app.services.github_service.GitHubService.resolve_ref", return_value=SAMPLE_COMMIT_A), \
         patch("app.services.github_service.GitHubService.get_commit_tree", return_value=tree), \
         patch("app.services.github_service.GitHubService.get_file_content", side_effect=fake_get_file_content):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/mcp/discover",
                json={
                    "repository_url": "https://github.com/example/mcp-server",
                    "ref": "main",
                },
            )

        assert resp.status_code == 200
        disc = resp.json()["discovery"]
        assert disc["extraction_status"] == "PARTIAL"
        assert any("broken.py" in w for w in disc["extraction_warnings"])
        assert len(disc["extracted_tools"]) == 1
