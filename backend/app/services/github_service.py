"""GitHub integration service for URL validation, ref resolution, and commit comparison."""

import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple
import httpx

from app.schemas.github import (
    ChangedFile,
    CommitMetadata,
    ComparisonSummary,
    RepositoryMetadata,
)


class GitHubError(Exception):
    """Base exception for GitHub API and integration failures."""

    def __init__(
        self,
        message: str,
        status_code: int = 502,
        error_code: str = "GITHUB_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}


class InvalidRepositoryURLError(GitHubError):
    """Raised when repository URL does not point to a valid public GitHub repository."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=400,
            error_code="INVALID_REPOSITORY_URL",
            details=details,
        )


class RepositoryNotFoundError(GitHubError):
    """Raised when the target repository does not exist or is not public."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=404,
            error_code="REPOSITORY_NOT_FOUND",
            details=details,
        )


class RefNotFoundError(GitHubError):
    """Raised when a baseline or candidate git reference cannot be resolved."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=404,
            error_code="REF_NOT_FOUND",
            details=details,
        )


class GitHubRateLimitError(GitHubError):
    """Raised when GitHub API rate limits are exceeded."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=429,
            error_code="GITHUB_RATE_LIMITED",
            details=details,
        )


class GitHubTimeoutError(GitHubError):
    """Raised when an outbound GitHub API call times out."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=504,
            error_code="GITHUB_TIMEOUT",
            details=details,
        )


# Strict regex for GitHub owner and repository names
# Owner: 1-39 alphanumeric or hyphen characters (cannot start or end with hyphen)
# Repo: alphanumeric, hyphen, underscore, dot (max 100 characters)
GITHUB_OWNER_PATTERN = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}$")
GITHUB_REPO_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{1,100}$")


def parse_github_repository_url(url: str) -> Tuple[str, str, str]:
    """Validate and parse a public GitHub repository URL.
    
    Returns:
        Tuple of (owner, repo_name, canonical_https_url)
    
    Raises:
        InvalidRepositoryURLError on invalid format, non-HTTPS scheme, or unexpected host.
    """
    if not url or not isinstance(url, str):
        raise InvalidRepositoryURLError("Repository URL is required and must be a non-empty string.")

    cleaned_url = url.strip()

    try:
        parsed = urllib.parse.urlparse(cleaned_url)
    except Exception as exc:
        raise InvalidRepositoryURLError(f"Malformed repository URL: {str(exc)}") from exc

    # 1. Enforce HTTPS scheme
    if parsed.scheme.lower() != "https":
        raise InvalidRepositoryURLError(
            f"Invalid URL scheme '{parsed.scheme}'. Only public HTTPS GitHub URLs ('https://github.com/owner/repo') are supported."
        )

    # 2. Reject credentials in URL (e.g. https://user:pass@github.com)
    if parsed.username or parsed.password:
        raise InvalidRepositoryURLError("Repository URL must not contain embedded user credentials.")

    # 3. Enforce github.com host (reject arbitrary hosts, IP addresses, subdomains like gist.github.com)
    hostname = (parsed.hostname or "").lower()
    if hostname not in ("github.com", "www.github.com"):
        raise InvalidRepositoryURLError(
            f"Unsupported host '{hostname}'. Only public repositories hosted on 'github.com' are supported."
        )

    # 4. Reject query parameters or fragments
    if parsed.query or parsed.fragment:
        raise InvalidRepositoryURLError("Repository URL must not contain query parameters or URL fragments.")

    # 5. Extract path segments
    path_segments = [seg for seg in parsed.path.strip("/").split("/") if seg]
    if len(path_segments) != 2:
        raise InvalidRepositoryURLError(
            "Invalid GitHub repository URL path. Expected format: 'https://github.com/owner/repository'."
        )

    owner, raw_repo = path_segments

    # Strip optional .git suffix from repository name
    repo = raw_repo[:-4] if raw_repo.lower().endswith(".git") else raw_repo

    if not GITHUB_OWNER_PATTERN.match(owner):
        raise InvalidRepositoryURLError(
            f"Invalid GitHub owner/organization name '{owner}'."
        )

    if not GITHUB_REPO_PATTERN.match(repo) or repo in (".", ".."):
        raise InvalidRepositoryURLError(
            f"Invalid GitHub repository name '{repo}'."
        )

    canonical_url = f"https://github.com/{owner}/{repo}"
    return owner, repo, canonical_url


class GitHubService:
    """Client for interacting with GitHub REST API for repository and commit operations."""

    def __init__(
        self,
        base_url: str = "https://api.github.com",
        github_token: Optional[str] = None,
        timeout_seconds: float = 20.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.github_token = github_token.strip() if github_token else None
        self.timeout = timeout_seconds

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "MCP-ReleaseProof/0.1.0",
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers

    def _handle_response_errors(self, response: httpx.Response, context: str) -> None:
        """Translate upstream HTTP error status into structured domain exceptions."""
        if response.status_code == 200:
            return

        if response.status_code == 404:
            raise RepositoryNotFoundError(f"Resource not found on GitHub: {context}")

        if response.status_code == 422:
            raise RefNotFoundError(
                f"Reference query was rejected by GitHub: {context} (422 Unprocessable Entity).",
                details={"context": context},
            )

        if response.status_code in (403, 429):
            remaining = response.headers.get("x-ratelimit-remaining")
            if remaining == "0" or "rate limit" in response.text.lower():
                reset_time = response.headers.get("x-ratelimit-reset", "unknown")
                raise GitHubRateLimitError(
                    f"GitHub API rate limit exceeded. Reset timestamp: {reset_time}.",
                    details={"reset": reset_time},
                )
            raise GitHubError(
                f"GitHub API access forbidden: {context} ({response.status_code})",
                status_code=403,
                error_code="GITHUB_FORBIDDEN",
            )

        if response.status_code == 401:
            raise GitHubError(
                "GitHub authentication failed. Configured GITHUB_TOKEN is invalid or expired.",
                status_code=401,
                error_code="GITHUB_AUTH_FAILED",
            )

        raise GitHubError(
            f"GitHub API returned error {response.status_code} while accessing {context}.",
            status_code=502,
            error_code="GITHUB_UPSTREAM_ERROR",
            details={"status_code": response.status_code},
        )

    async def get_repository_metadata(self, owner: str, repo: str) -> RepositoryMetadata:
        """Fetch repository metadata from GitHub REST API."""
        url = f"{self.base_url}/repos/{owner}/{repo}"
        transport = httpx.AsyncHTTPTransport(retries=0)

        async with httpx.AsyncClient(transport=transport, timeout=self.timeout) as client:
            try:
                response = await client.get(url, headers=self._get_headers())
            except httpx.TimeoutException as exc:
                raise GitHubTimeoutError(
                    f"Timed out fetching repository metadata for '{owner}/{repo}' after {self.timeout}s"
                ) from exc
            except httpx.RequestError as exc:
                raise GitHubError(
                    f"Network error connecting to GitHub: {str(exc)}",
                    status_code=502,
                    error_code="GITHUB_NETWORK_ERROR",
                ) from exc

        if response.status_code == 404:
            raise RepositoryNotFoundError(
                f"Public repository '{owner}/{repo}' not found on GitHub. Verify the repository exists and is public."
            )

        self._handle_response_errors(response, f"repos/{owner}/{repo}")

        data = response.json()
        if data.get("private", False):
            raise RepositoryNotFoundError(
                f"Repository '{owner}/{repo}' is private. Only public GitHub repositories are supported."
            )

        return RepositoryMetadata(
            owner=data.get("owner", {}).get("login", owner),
            name=data.get("name", repo),
            full_name=data.get("full_name", f"{owner}/{repo}"),
            description=data.get("description"),
            html_url=data.get("html_url", f"https://github.com/{owner}/{repo}"),
            default_branch=data.get("default_branch", "main"),
            is_private=data.get("private", False),
            stars_count=data.get("stargazers_count", 0),
            forks_count=data.get("forks_count", 0),
            open_issues_count=data.get("open_issues_count", 0),
        )

    async def resolve_ref(
        self, owner: str, repo: str, ref: str, ref_label: Optional[str] = None
    ) -> CommitMetadata:
        """Resolve a branch name, git tag, or commit SHA to an exact immutable commit SHA."""
        clean_ref = ref.strip()
        label_prefix = f"{ref_label.capitalize()} reference" if ref_label else "Reference"
        if not clean_ref:
            raise RefNotFoundError(f"{label_prefix} cannot be empty.")

        transport = httpx.AsyncHTTPTransport(retries=0)

        # Attempt 1: Query /repos/{owner}/{repo}/commits/{ref}
        # GitHub's commits endpoint natively resolves branches, tags, short SHAs, and full SHAs
        url = f"{self.base_url}/repos/{owner}/{repo}/commits/{clean_ref}"

        async with httpx.AsyncClient(transport=transport, timeout=self.timeout) as client:
            try:
                response = await client.get(url, headers=self._get_headers())
            except httpx.TimeoutException as exc:
                raise GitHubTimeoutError(
                    f"Timed out resolving {label_prefix.lower()} '{clean_ref}' for '{owner}/{repo}'"
                ) from exc
            except httpx.RequestError as exc:
                raise GitHubError(
                    f"Network error connecting to GitHub: {str(exc)}",
                    status_code=502,
                    error_code="GITHUB_NETWORK_ERROR",
                ) from exc

        if response.status_code == 200:
            data = response.json()
            return self._parse_commit_metadata(clean_ref, data, owner, repo)

        # If 404 or 422, check if it's an annotated tag object that needs dereferencing
        if response.status_code in (404, 422):
            dereferenced = await self._dereference_tag_ref(owner, repo, clean_ref)
            if dereferenced:
                return dereferenced

            raise RefNotFoundError(
                f"{label_prefix} '{clean_ref}' could not be resolved to a commit in repository '{owner}/{repo}'.",
                details={"ref": clean_ref, "ref_label": ref_label},
            )

        self._handle_response_errors(response, f"commits/{clean_ref}")
        raise RefNotFoundError(f"Failed to resolve {label_prefix.lower()} '{clean_ref}'")

    async def _dereference_tag_ref(
        self, owner: str, repo: str, tag_name: str
    ) -> Optional[CommitMetadata]:
        """Attempt to dereference an annotated tag object via git refs API."""
        transport = httpx.AsyncHTTPTransport(retries=0)
        url = f"{self.base_url}/repos/{owner}/{repo}/git/ref/tags/{tag_name}"

        async with httpx.AsyncClient(transport=transport, timeout=self.timeout) as client:
            try:
                ref_resp = await client.get(url, headers=self._get_headers())
                if ref_resp.status_code != 200:
                    return None

                ref_data = ref_resp.json()
                obj = ref_data.get("object", {})
                obj_type = obj.get("type")
                obj_sha = obj.get("sha")

                target_commit_sha = None
                if obj_type == "commit":
                    target_commit_sha = obj_sha
                elif obj_type == "tag" and obj_sha:
                    # Query tag object to find target commit
                    tag_url = f"{self.base_url}/repos/{owner}/{repo}/git/tags/{obj_sha}"
                    tag_resp = await client.get(tag_url, headers=self._get_headers())
                    if tag_resp.status_code == 200:
                        tag_data = tag_resp.json()
                        target_commit_sha = tag_data.get("object", {}).get("sha")

                if target_commit_sha:
                    commit_url = f"{self.base_url}/repos/{owner}/{repo}/commits/{target_commit_sha}"
                    commit_resp = await client.get(commit_url, headers=self._get_headers())
                    if commit_resp.status_code == 200:
                        return self._parse_commit_metadata(
                            tag_name, commit_resp.json(), owner, repo
                        )
            except Exception:
                return None

        return None

    def _parse_commit_metadata(
        self, ref: str, data: Dict[str, Any], owner: str, repo: str
    ) -> CommitMetadata:
        sha = data.get("sha", "")
        short_sha = sha[:7] if len(sha) >= 7 else sha
        commit = data.get("commit", {})
        author = commit.get("author") or {}
        committer = commit.get("committer") or {}

        author_name = author.get("name") or "Unknown"
        author_date = author.get("date")
        committer_name = committer.get("name") or author_name
        committed_at = committer.get("date") or author_date or ""
        message = commit.get("message") or ""
        html_url = data.get("html_url") or f"https://github.com/{owner}/{repo}/commit/{sha}"

        return CommitMetadata(
            ref=ref,
            sha=sha,
            short_sha=short_sha,
            message=message,
            author_name=author_name,
            author_date=author_date,
            committer_name=committer_name,
            committed_at=committed_at,
            html_url=html_url,
        )

    async def compare_commits(
        self,
        owner: str,
        repo: str,
        baseline_sha: str,
        candidate_sha: str,
    ) -> ComparisonSummary:
        """Compare two resolved commits via GitHub REST API."""
        if baseline_sha == candidate_sha:
            return ComparisonSummary(
                status="identical",
                ahead_by=0,
                behind_by=0,
                total_commits=0,
                files_changed_count=0,
                additions=0,
                deletions=0,
                is_identical=True,
                is_truncated=False,
                files=[],
            )

        url = f"{self.base_url}/repos/{owner}/{repo}/compare/{baseline_sha}...{candidate_sha}"
        transport = httpx.AsyncHTTPTransport(retries=0)

        async with httpx.AsyncClient(transport=transport, timeout=self.timeout) as client:
            try:
                response = await client.get(url, headers=self._get_headers())
            except httpx.TimeoutException as exc:
                raise GitHubTimeoutError(
                    f"Timed out comparing commits {baseline_sha[:7]}...{candidate_sha[:7]} in '{owner}/{repo}'"
                ) from exc
            except httpx.RequestError as exc:
                raise GitHubError(
                    f"Network error connecting to GitHub: {str(exc)}",
                    status_code=502,
                    error_code="GITHUB_NETWORK_ERROR",
                ) from exc

        if response.status_code in (404, 422):
            raise RefNotFoundError(
                f"Unable to compare {baseline_sha[:7]}...{candidate_sha[:7]} in '{owner}/{repo}'. One or both commits do not exist."
            )

        self._handle_response_errors(response, f"compare/{baseline_sha}...{candidate_sha}")

        data = response.json()
        raw_files = data.get("files") or []
        parsed_files: List[ChangedFile] = []

        total_additions = 0
        total_deletions = 0

        for f in raw_files:
            filename = f.get("filename", "")
            status = f.get("status", "modified")
            adds = f.get("additions", 0)
            dels = f.get("deletions", 0)
            changes = f.get("changes", adds + dels)
            patch = f.get("patch")
            previous_filename = f.get("previous_filename")

            total_additions += adds
            total_deletions += dels

            parsed_files.append(
                ChangedFile(
                    filename=filename,
                    status=status,
                    additions=adds,
                    deletions=dels,
                    changes=changes,
                    patch=patch,
                    previous_filename=previous_filename,
                )
            )

        status = data.get("status", "ahead")
        ahead_by = data.get("ahead_by", 0)
        behind_by = data.get("behind_by", 0)
        total_commits = data.get("total_commits", 0)

        # Check if GitHub truncated comparison results (limit of 300 files)
        is_truncated = len(raw_files) >= 300 or bool(data.get("truncated", False))

        return ComparisonSummary(
            status=status,
            ahead_by=ahead_by,
            behind_by=behind_by,
            total_commits=total_commits,
            files_changed_count=len(parsed_files),
            additions=total_additions,
            deletions=total_deletions,
            is_identical=(status == "identical" or (ahead_by == 0 and behind_by == 0 and len(parsed_files) == 0)),
            is_truncated=is_truncated,
            files=parsed_files,
        )

    async def get_commit_tree(
        self, owner: str, repo: str, commit_sha: str
    ) -> List[Dict[str, Any]]:
        """Fetch the recursive git tree for a given commit SHA.
        
        Returns:
            List of tree objects containing 'path', 'type', 'size', and 'sha'.
        """
        clean_sha = commit_sha.strip()
        url = f"{self.base_url}/repos/{owner}/{repo}/git/trees/{clean_sha}?recursive=1"
        transport = httpx.AsyncHTTPTransport(retries=0)

        async with httpx.AsyncClient(transport=transport, timeout=self.timeout) as client:
            try:
                response = await client.get(url, headers=self._get_headers())
            except httpx.TimeoutException as exc:
                raise GitHubTimeoutError(
                    f"Timed out fetching git tree for '{owner}/{repo}@{clean_sha[:7]}'"
                ) from exc
            except httpx.RequestError as exc:
                raise GitHubError(
                    f"Network error connecting to GitHub: {str(exc)}",
                    status_code=502,
                    error_code="GITHUB_NETWORK_ERROR",
                ) from exc

        if response.status_code == 404:
            raise RefNotFoundError(
                f"Commit or tree '{clean_sha[:7]}' not found in repository '{owner}/{repo}'."
            )

        self._handle_response_errors(response, f"git/trees/{clean_sha}")

        data = response.json()
        tree_entries = data.get("tree", [])
        return tree_entries

    async def get_file_content(
        self,
        owner: str,
        repo: str,
        file_path: str,
        commit_sha: str,
        max_size_bytes: int = 524288,  # 512 KB
    ) -> Optional[str]:
        """Fetch raw text content of a file at a specific commit SHA without executing or importing it.
        
        Enforces path safety checks and maximum file size limits to prevent abuse.
        """
        clean_path = file_path.strip().lstrip("/")
        if not clean_path or ".." in clean_path.split("/") or "\0" in clean_path:
            raise InvalidRepositoryURLError(f"Unsafe file path requested: '{file_path}'")

        encoded_path = urllib.parse.quote(clean_path)
        clean_sha = commit_sha.strip()
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{encoded_path}?ref={clean_sha}"

        headers = self._get_headers()
        # Request raw file contents directly from GitHub
        headers["Accept"] = "application/vnd.github.v3.raw"

        transport = httpx.AsyncHTTPTransport(retries=0)

        async with httpx.AsyncClient(transport=transport, timeout=self.timeout) as client:
            try:
                response = await client.get(url, headers=headers)
            except httpx.TimeoutException as exc:
                raise GitHubTimeoutError(
                    f"Timed out fetching file '{clean_path}' at {clean_sha[:7]}"
                ) from exc
            except httpx.RequestError as exc:
                raise GitHubError(
                    f"Network error connecting to GitHub: {str(exc)}",
                    status_code=502,
                    error_code="GITHUB_NETWORK_ERROR",
                ) from exc

        if response.status_code == 404:
            return None

        self._handle_response_errors(response, f"contents/{clean_path}")

        raw_bytes = response.content
        if len(raw_bytes) > max_size_bytes:
            # File exceeds safe parsing limit; do not process huge files
            raise GitHubError(
                f"File '{clean_path}' exceeds maximum size limit of {max_size_bytes} bytes (got {len(raw_bytes)} bytes).",
                status_code=400,
                error_code="FILE_SIZE_LIMIT_EXCEEDED",
            )

        try:
            return raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return raw_bytes.decode("utf-8", errors="replace")


