"""Pydantic schemas for GitHub repository integration, ref resolution, and commit comparison."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ResolveRefsRequest(BaseModel):
    """Request payload to validate a repository and resolve git refs to immutable commit SHAs."""
    repository_url: str = Field(
        description="Public HTTPS GitHub repository URL (e.g. https://github.com/owner/repo)"
    )
    baseline_ref: str = Field(
        min_length=1,
        description="Baseline git reference (branch name, tag, or commit SHA)",
    )
    candidate_ref: str = Field(
        min_length=1,
        description="Candidate git reference (branch name, tag, or commit SHA)",
    )


class CompareCommitsRequest(BaseModel):
    """Request payload to resolve refs and compare baseline against candidate."""
    repository_url: str = Field(
        description="Public HTTPS GitHub repository URL (e.g. https://github.com/owner/repo)"
    )
    baseline_ref: str = Field(
        min_length=1,
        description="Baseline git reference (branch name, tag, or commit SHA)",
    )
    candidate_ref: str = Field(
        min_length=1,
        description="Candidate git reference (branch name, tag, or commit SHA)",
    )


class RepositoryMetadata(BaseModel):
    """Structured GitHub repository metadata."""
    owner: str = Field(description="Repository owner / organization login")
    name: str = Field(description="Repository name")
    full_name: str = Field(description="Full name in owner/repo format")
    description: Optional[str] = Field(default=None, description="Repository description")
    html_url: str = Field(description="Public web URL to the repository on GitHub")
    default_branch: str = Field(default="main", description="Default branch name")
    is_private: bool = Field(default=False, description="Whether the repository is private")
    stars_count: int = Field(default=0, description="Stargazer count")
    forks_count: int = Field(default=0, description="Fork count")
    open_issues_count: int = Field(default=0, description="Open issues count")


class CommitMetadata(BaseModel):
    """Immutable commit metadata resolved from a git ref."""
    ref: str = Field(description="Original user-provided ref string")
    sha: str = Field(description="Exact 40-character commit SHA")
    short_sha: str = Field(description="7-character short commit SHA")
    message: str = Field(description="Commit message")
    author_name: str = Field(description="Commit author name")
    author_date: Optional[str] = Field(default=None, description="Authored ISO-8601 timestamp")
    committer_name: str = Field(description="Committer name")
    committed_at: str = Field(description="Committed ISO-8601 timestamp")
    html_url: str = Field(description="Public GitHub URL to inspect this commit")


class ChangedFile(BaseModel):
    """Details of a single file modified between baseline and candidate commits."""
    filename: str = Field(description="Relative path of the changed file")
    status: str = Field(
        description="Change classification: added, modified, removed, renamed"
    )
    additions: int = Field(default=0, description="Number of lines added")
    deletions: int = Field(default=0, description="Number of lines deleted")
    changes: int = Field(default=0, description="Total number of line changes")
    patch: Optional[str] = Field(
        default=None,
        description="Unified diff patch text, or None if binary or omitted by GitHub",
    )
    previous_filename: Optional[str] = Field(
        default=None, description="Original filename if renamed"
    )


class ComparisonSummary(BaseModel):
    """Structured comparison between baseline and candidate commits."""
    status: str = Field(
        description="Relationship status: ahead, behind, identical, diverged"
    )
    ahead_by: int = Field(default=0, description="Number of commits candidate is ahead of baseline")
    behind_by: int = Field(default=0, description="Number of commits candidate is behind baseline")
    total_commits: int = Field(default=0, description="Total number of commits in comparison")
    files_changed_count: int = Field(default=0, description="Total count of files changed")
    additions: int = Field(default=0, description="Total line additions across all files")
    deletions: int = Field(default=0, description="Total line deletions across all files")
    is_identical: bool = Field(default=False, description="True if baseline and candidate commits are identical")
    is_truncated: bool = Field(default=False, description="True if diff/files exceeded GitHub API comparison limits")
    files: List[ChangedFile] = Field(default_factory=list, description="List of changed files with diff information")


class ResolveRefsResponse(BaseModel):
    """Response payload for ref resolution."""
    status: str = Field(default="success", description="Operation status")
    repository: RepositoryMetadata = Field(description="Repository metadata")
    baseline: CommitMetadata = Field(description="Resolved baseline commit")
    candidate: CommitMetadata = Field(description="Resolved candidate commit")
    is_identical: bool = Field(description="True if both refs resolved to the same commit SHA")


class CompareCommitsResponse(BaseModel):
    """Response payload for commit comparison."""
    status: str = Field(default="success", description="Operation status")
    repository: RepositoryMetadata = Field(description="Repository metadata")
    baseline: CommitMetadata = Field(description="Resolved baseline commit")
    candidate: CommitMetadata = Field(description="Resolved candidate commit")
    comparison: ComparisonSummary = Field(description="Detailed comparison between commits")

