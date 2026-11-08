"""Unit tests for Phase 6 Sandbox Pydantic schemas and validation."""

import pytest
from pydantic import ValidationError

from app.schemas.sandbox import (
    CleanupStatus,
    ExecutionLifecycleState,
    SandboxExecutionRequest,
    SandboxExecutionResult,
    SecurityEnforcementReport,
    SecurityEnforcementStatus,
    TestVerdict,
    VerificationVerdict,
)

VALID_REQ_DATA = {
    "repository_url": "https://github.com/modelcontextprotocol/servers",
    "commit_sha": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
    "ref": "v1.0.0",
    "harness_code": "import pytest\ndef test_ok(): pass\n",
    "server_entrypoint": "src/server.py",
    "server_args": ["--port", "8080"],
    "environment_variables": {"TEST_VAR": "synthetic_value"},
    "timeout_seconds": 60,
    "memory_limit_mb": 512,
    "cpu_limit": 1.0,
    "pids_limit": 64,
}


def test_valid_sandbox_execution_request():
    """Verify standard valid execution request parses correctly."""
    req = SandboxExecutionRequest(**VALID_REQ_DATA)
    assert req.commit_sha == "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
    assert req.server_entrypoint == "src/server.py"
    assert req.server_args == ["--port", "8080"]


def test_reject_floating_ref_as_commit_sha():
    """Verify non-hex or floating refs like 'main' or 'HEAD' are rejected as commit_sha."""
    data = dict(VALID_REQ_DATA)
    data["commit_sha"] = "main"
    with pytest.raises(ValidationError):
        SandboxExecutionRequest(**data)

    data["commit_sha"] = "short-sha-123"
    with pytest.raises(ValidationError):
        SandboxExecutionRequest(**data)


def test_reject_non_github_repository_url():
    """Verify non-GitHub repository URLs are rejected."""
    data = dict(VALID_REQ_DATA)
    data["repository_url"] = "http://gitlab.com/evil/repo"
    with pytest.raises(ValidationError):
        SandboxExecutionRequest(**data)


def test_reject_entrypoint_path_traversal():
    """Verify directory traversal attempts in server_entrypoint are rejected."""
    data = dict(VALID_REQ_DATA)
    for bad_path in ("../evil.py", "/etc/passwd", "src/../../evil.py", "\\windows\\system32"):
        data["server_entrypoint"] = bad_path
        with pytest.raises(ValidationError, match="server_entrypoint"):
            SandboxExecutionRequest(**data)


def test_reject_shell_metacharacters_in_server_args():
    """Verify shell metacharacters in structured arguments are rejected."""
    data = dict(VALID_REQ_DATA)
    for bad_arg in ("--arg; rm -rf /", "--arg | cat", "--arg && evil", "$(whoami)", "`id`", "foo\nbar"):
        data["server_args"] = ["--flag", bad_arg]
        with pytest.raises(ValidationError, match="shell metacharacters"):
            SandboxExecutionRequest(**data)


def test_reject_credential_like_environment_variables():
    """Verify environment variables containing secret or key terms are rejected."""
    data = dict(VALID_REQ_DATA)
    for bad_key in ("API_KEY", "VULTR_TOKEN", "SECRET_PASSWORD", "DB_SECRET"):
        data["environment_variables"] = {bad_key: "value"}
        with pytest.raises(ValidationError, match="resembles a credential"):
            SandboxExecutionRequest(**data)


def test_verification_verdict_only_success_when_all_three_criteria_met():
    """Verify VERIFIED_SUCCESS is strictly assigned only when test passes, security verified, and clean."""
    res = SandboxExecutionResult(
        job_id="job-1",
        repository_url="https://github.com/org/repo",
        commit_sha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        lifecycle_status=ExecutionLifecycleState.COMPLETED,
        test_verdict=TestVerdict.PASSED,
        security_status=SecurityEnforcementStatus.VERIFIED,
        cleanup_status=CleanupStatus.VERIFIED_CLEAN,
        verification_verdict=VerificationVerdict.VERIFIED_SUCCESS,
        security_report=SecurityEnforcementReport(
            overall_status=SecurityEnforcementStatus.VERIFIED,
            controls=[],
            summary="All verified",
        ),
    )
    assert res.verification_verdict == VerificationVerdict.VERIFIED_SUCCESS
