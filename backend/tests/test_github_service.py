"""Unit tests for GitHub service: URL parsing, ref resolution, and commit comparison."""

import pytest
from unittest.mock import patch, MagicMock
import httpx

from app.schemas.github import (
    ChangedFile,
    CommitMetadata,
    ComparisonSummary,
    RepositoryMetadata,
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


# --- URL Parsing Tests ---

def test_parse_valid_github_urls():
    # Standard format
    owner, repo, canonical = parse_github_repository_url("https://github.com/modelcontextprotocol/servers")
    assert owner == "modelcontextprotocol"
    assert repo == "servers"
    assert canonical == "https://github.com/modelcontextprotocol/servers"

    # With .git suffix
    owner, repo, canonical = parse_github_repository_url("https://github.com/owner/my-repo.git")
    assert owner == "owner"
    assert repo == "my-repo"
    assert canonical == "https://github.com/owner/my-repo"

    # With trailing slash
    owner, repo, canonical = parse_github_repository_url("https://github.com/owner/my-repo/")
    assert owner == "owner"
    assert repo == "my-repo"
    assert canonical == "https://github.com/owner/my-repo"

    # With www.github.com
    owner, repo, canonical = parse_github_repository_url("https://www.github.com/owner/my-repo")
    assert owner == "owner"
    assert repo == "my-repo"
    assert canonical == "https://github.com/owner/my-repo"


def test_parse_invalid_github_urls():
    # Non-HTTPS
    with pytest.raises(InvalidRepositoryURLError) as exc:
        parse_github_repository_url("http://github.com/owner/repo")
    assert "scheme" in str(exc.value).lower()

    with pytest.raises(InvalidRepositoryURLError) as exc:
        parse_github_repository_url("git@github.com:owner/repo.git")
    assert "scheme" in str(exc.value).lower()

    # Unsupported hosts
    with pytest.raises(InvalidRepositoryURLError) as exc:
        parse_github_repository_url("https://gitlab.com/owner/repo")
    assert "unsupported host" in str(exc.value).lower()

    with pytest.raises(InvalidRepositoryURLError) as exc:
        parse_github_repository_url("https://gist.github.com/owner/repo")
    assert "unsupported host" in str(exc.value).lower()

    # Embedded credentials
    with pytest.raises(InvalidRepositoryURLError) as exc:
        parse_github_repository_url("https://user:pass@github.com/owner/repo")
    assert "credentials" in str(exc.value).lower()

    # Query params and fragments
    with pytest.raises(InvalidRepositoryURLError) as exc:
        parse_github_repository_url("https://github.com/owner/repo?ref=main")
    assert "query" in str(exc.value).lower()

    with pytest.raises(InvalidRepositoryURLError) as exc:
        parse_github_repository_url("https://github.com/owner/repo#readme")
    assert "fragments" in str(exc.value).lower()

    # Path traversal / invalid segments
    with pytest.raises(InvalidRepositoryURLError) as exc:
        parse_github_repository_url("https://github.com/owner")
    assert "expected format" in str(exc.value).lower()

    with pytest.raises(InvalidRepositoryURLError) as exc:
        parse_github_repository_url("https://github.com/owner/repo/subpath")
    assert "expected format" in str(exc.value).lower()

    with pytest.raises(InvalidRepositoryURLError) as exc:
        parse_github_repository_url("https://github.com/owner/..")
    assert "invalid" in str(exc.value).lower()

    # Empty / null
    with pytest.raises(InvalidRepositoryURLError):
        parse_github_repository_url("")


# --- Repository Metadata Tests ---

@pytest.mark.asyncio
async def test_get_repository_metadata_success():
    service = GitHubService()
    mock_payload = {
        "owner": {"login": "testowner"},
        "name": "testrepo",
        "full_name": "testowner/testrepo",
        "description": "A sample MCP server repository",
        "html_url": "https://github.com/testowner/testrepo",
        "default_branch": "main",
        "private": False,
        "stargazers_count": 42,
        "forks_count": 5,
        "open_issues_count": 1,
    }
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        repo_meta = await service.get_repository_metadata("testowner", "testrepo")
        assert repo_meta.owner == "testowner"
        assert repo_meta.name == "testrepo"
        assert repo_meta.stars_count == 42
        assert repo_meta.default_branch == "main"
        assert not repo_meta.is_private


@pytest.mark.asyncio
async def test_get_repository_metadata_not_found():
    service = GitHubService()
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 404
    mock_resp.text = '{"message": "Not Found"}'

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        with pytest.raises(RepositoryNotFoundError) as exc:
            await service.get_repository_metadata("nonexistent", "repo")
        assert "not found" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_get_repository_metadata_private_rejected():
    service = GitHubService()
    mock_payload = {
        "owner": {"login": "secretorg"},
        "name": "secretrepo",
        "private": True,
    }
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        with pytest.raises(RepositoryNotFoundError) as exc:
            await service.get_repository_metadata("secretorg", "secretrepo")
        assert "private" in str(exc.value).lower()


# --- Ref Resolution Tests ---

@pytest.mark.asyncio
async def test_resolve_ref_branch_or_sha():
    service = GitHubService()
    mock_payload = {
        "sha": "9f837782e3f20b49ec46746d3e353b32121e8009",
        "commit": {
            "message": "Fix security vulnerability in MCP stdio read\n\nCloses #10",
            "author": {"name": "Alice Developer", "date": "2026-11-04T10:00:00Z"},
            "committer": {"name": "Alice Developer", "date": "2026-11-04T10:05:00Z"},
        },
        "html_url": "https://github.com/owner/repo/commit/9f837782e3f20b49ec46746d3e353b32121e8009",
    }
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        commit = await service.resolve_ref("owner", "repo", "main")
        assert commit.ref == "main"
        assert commit.sha == "9f837782e3f20b49ec46746d3e353b32121e8009"
        assert commit.short_sha == "9f83778"
        assert "security vulnerability" in commit.message
        assert commit.author_name == "Alice Developer"
        assert commit.committed_at == "2026-11-04T10:05:00Z"


@pytest.mark.asyncio
async def test_resolve_annotated_tag_dereferencing():
    service = GitHubService()
    
    # First call to /commits/v1.0.0 returns 404
    resp_commits_404 = MagicMock(spec=httpx.Response)
    resp_commits_404.status_code = 404
    resp_commits_404.text = "Not Found"

    # Second call to /git/ref/tags/v1.0.0 returns tag ref pointing to tag object
    resp_tag_ref = MagicMock(spec=httpx.Response)
    resp_tag_ref.status_code = 200
    resp_tag_ref.json.return_value = {
        "object": {
            "type": "tag",
            "sha": "tag_object_sha_12345",
        }
    }

    # Third call to /git/tags/tag_object_sha_12345 returns target commit SHA
    resp_tag_obj = MagicMock(spec=httpx.Response)
    resp_tag_obj.status_code = 200
    resp_tag_obj.json.return_value = {
        "object": {
            "sha": "dereferenced_commit_sha_67890",
            "type": "commit",
        }
    }

    # Fourth call to /commits/dereferenced_commit_sha_67890 returns commit metadata
    resp_commit_final = MagicMock(spec=httpx.Response)
    resp_commit_final.status_code = 200
    resp_commit_final.json.return_value = {
        "sha": "dereferenced_commit_sha_67890",
        "commit": {
            "message": "Release v1.0.0",
            "author": {"name": "Release Bot", "date": "2026-11-01T00:00:00Z"},
            "committer": {"name": "Release Bot", "date": "2026-11-01T00:00:00Z"},
        },
        "html_url": "https://github.com/owner/repo/commit/dereferenced_commit_sha_67890",
    }

    def mock_get(url, *args, **kwargs):
        if "git/ref/tags" in url:
            return resp_tag_ref
        elif "git/tags" in url:
            return resp_tag_obj
        elif "dereferenced_commit_sha" in url:
            return resp_commit_final
        return resp_commits_404

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        commit = await service.resolve_ref("owner", "repo", "v1.0.0")
        assert commit.ref == "v1.0.0"
        assert commit.sha == "dereferenced_commit_sha_67890"
        assert commit.message == "Release v1.0.0"


@pytest.mark.asyncio
async def test_resolve_ref_not_found():
    service = GitHubService()
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 404
    mock_resp.text = "Not Found"

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        with pytest.raises(RefNotFoundError) as exc:
            await service.resolve_ref("owner", "repo", "unknown-ref")
        assert "unknown-ref" in str(exc.value)


@pytest.mark.asyncio
async def test_resolve_ref_422_mapped_to_ref_not_found_with_baseline_label():
    service = GitHubService()
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 422
    mock_resp.text = '{"message": "No commit found for SHA: invalid-ref", "documentation_url": "https://docs.github.com"}'

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        with pytest.raises(RefNotFoundError) as exc:
            await service.resolve_ref("owner", "repo", "invalid-baseline", ref_label="baseline")
        assert exc.value.status_code == 404
        assert exc.value.error_code == "REF_NOT_FOUND"
        assert "Baseline reference 'invalid-baseline' could not be resolved" in str(exc.value)
        # Verify raw upstream GitHub error payload is NOT leaked in the exception message
        assert "documentation_url" not in str(exc.value)


@pytest.mark.asyncio
async def test_resolve_ref_422_mapped_to_ref_not_found_with_candidate_label():
    service = GitHubService()
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 422
    mock_resp.text = '{"message": "No commit found for SHA: invalid-candidate", "documentation_url": "https://docs.github.com"}'

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        with pytest.raises(RefNotFoundError) as exc:
            await service.resolve_ref("owner", "repo", "invalid-candidate", ref_label="candidate")
        assert exc.value.status_code == 404
        assert exc.value.error_code == "REF_NOT_FOUND"
        assert "Candidate reference 'invalid-candidate' could not be resolved" in str(exc.value)
        assert "documentation_url" not in str(exc.value)


@pytest.mark.asyncio
async def test_compare_commits_422_mapped_to_ref_not_found():
    service = GitHubService()
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 422
    mock_resp.text = '{"message": "No common ancestor between commits"}'

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        with pytest.raises(RefNotFoundError) as exc:
            await service.compare_commits("owner", "repo", "1111111111111111111111111111111111111111", "2222222222222222222222222222222222222222")
        assert exc.value.status_code == 404
        assert exc.value.error_code == "REF_NOT_FOUND"


# --- Commit Comparison Tests ---

@pytest.mark.asyncio
async def test_compare_identical_commits():
    service = GitHubService()
    # When baseline and candidate SHAs are identical, compare_commits returns without network call
    sha = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    comparison = await service.compare_commits("owner", "repo", sha, sha)
    assert comparison.status == "identical"
    assert comparison.is_identical is True
    assert comparison.ahead_by == 0
    assert comparison.behind_by == 0
    assert comparison.total_commits == 0
    assert comparison.files_changed_count == 0
    assert comparison.files == []


@pytest.mark.asyncio
async def test_compare_different_commits_success():
    service = GitHubService()
    mock_compare_payload = {
        "status": "ahead",
        "ahead_by": 2,
        "behind_by": 0,
        "total_commits": 2,
        "files": [
            {
                "filename": "server.py",
                "status": "modified",
                "additions": 15,
                "deletions": 3,
                "changes": 18,
                "patch": "@@ -10,3 +10,15 @@\n+def new_tool(): pass\n",
            },
            {
                "filename": "tools/calc.py",
                "status": "added",
                "additions": 40,
                "deletions": 0,
                "changes": 40,
                "patch": "@@ -0,0 +1,40 @@\n+print('calculator')\n",
            },
            {
                "filename": "assets/logo.png",
                "status": "added",
                "additions": 0,
                "deletions": 0,
                "changes": 0,
                "patch": None,  # Binary file diff omitted by GitHub
            },
        ],
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_compare_payload

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        comp = await service.compare_commits(
            "owner", "repo", "1111111111111111111111111111111111111111", "2222222222222222222222222222222222222222"
        )
        assert comp.status == "ahead"
        assert comp.ahead_by == 2
        assert comp.behind_by == 0
        assert comp.files_changed_count == 3
        assert comp.additions == 55
        assert comp.deletions == 3
        assert comp.is_identical is False
        assert comp.is_truncated is False
        
        # Verify files
        assert comp.files[0].filename == "server.py"
        assert comp.files[0].status == "modified"
        assert comp.files[0].patch is not None
        
        # Verify binary file handling
        assert comp.files[2].filename == "assets/logo.png"
        assert comp.files[2].patch is None


@pytest.mark.asyncio
async def test_compare_rate_limit_exceeded():
    service = GitHubService()
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 403
    mock_resp.headers = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1730720000"}
    mock_resp.text = '{"message": "API rate limit exceeded for ip"}'

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        with pytest.raises(GitHubRateLimitError) as exc:
            await service.get_repository_metadata("owner", "repo")
        assert "rate limit exceeded" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_network_timeout():
    service = GitHubService(timeout_seconds=5.0)

    with patch("httpx.AsyncClient.get", side_effect=httpx.TimeoutException("Connection timed out")):
        with pytest.raises(GitHubTimeoutError) as exc:
            await service.get_repository_metadata("owner", "repo")
        assert "timed out" in str(exc.value).lower()

