"""Pydantic schemas for Phase 6 Vultr Compute Sandbox Execution."""

from enum import Enum
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class ExecutionLifecycleState(str, Enum):
    """Explicit lifecycle stages of a sandbox execution job."""
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CLEANUP_FAILED = "CLEANUP_FAILED"


class TestVerdict(str, Enum):
    """Outcome of the executed test harness."""
    __test__ = False
    PASSED = "PASSED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    ERROR = "ERROR"
    NOT_RUN = "NOT_RUN"


class SecurityEnforcementStatus(str, Enum):
    """Result of independent post-launch container security inspection."""
    VERIFIED = "VERIFIED"
    INCOMPLETE = "INCOMPLETE"
    VIOLATED = "VIOLATED"


class CleanupStatus(str, Enum):
    """Outcome of container and workspace teardown."""
    VERIFIED_CLEAN = "VERIFIED_CLEAN"
    CLEANUP_FAILED = "CLEANUP_FAILED"
    PENDING = "PENDING"


class VerificationVerdict(str, Enum):
    """Overall release verification outcome synthesizing test, security, and cleanup verdicts."""
    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"
    REGRESSION_DETECTED = "REGRESSION_DETECTED"
    SECURITY_VIOLATION = "SECURITY_VIOLATION"
    EXECUTION_TIMEOUT = "EXECUTION_TIMEOUT"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"
    UNSUPPORTED_DEPENDENCIES = "UNSUPPORTED_DEPENDENCIES"


# Characters prohibited in command arguments to prevent shell injection or subshell spawning
PROHIBITED_CMD_CHARS_PATTERN = re.compile(r"[`;&|<>$()]|\n|\r")


class SecurityControlItem(BaseModel):
    """Audit evidence for an individual container isolation control."""
    __test__ = False
    control_name: str = Field(description="Name of security control (e.g. non_root_user, network_isolation)")
    requested: str = Field(description="Policy requested value")
    observed: Optional[str] = Field(default=None, description="Actual observed value from docker inspect")
    status: SecurityEnforcementStatus = Field(description="Verification verdict for this control")
    details: Optional[str] = Field(default=None, description="Diagnostic observation details")


class SecurityEnforcementReport(BaseModel):
    """Comprehensive dual-verification security report comparing requested vs inspected controls."""
    __test__ = False
    overall_status: SecurityEnforcementStatus = Field(description="Composite verification verdict")
    controls: List[SecurityControlItem] = Field(default_factory=list, description="Per-control audit records")
    verified_at: Optional[str] = Field(default=None, description="ISO-8601 timestamp of inspection")
    summary: str = Field(default="", description="Summary of security enforcement results")


class SandboxExecutionRequest(BaseModel):
    """Request payload to execute a test harness against an MCP server inside an isolated sandbox."""
    __test__ = False
    repository_url: str = Field(
        pattern=r"^https:\/\/github\.com\/[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+(?:\/)?$",
        description="Public HTTPS GitHub repository URL",
    )
    commit_sha: str = Field(
        pattern=r"^[0-9a-fA-F]{40}$",
        description="Immutable 40-character hexadecimal commit SHA",
    )
    ref: Optional[str] = Field(default=None, description="Optional Git reference label (tag, branch)")
    harness_code: str = Field(
        min_length=1,
        max_length=65_536,
        description="Clean Python test harness code (max 64KB)",
    )
    server_entrypoint: str = Field(
        default="server.py",
        description="Relative entrypoint path within repository (e.g. server.py, src/main.py)",
    )
    server_args: List[str] = Field(
        default_factory=list,
        max_length=20,
        description="Structured command line arguments for the server (no shell strings)",
    )
    environment_variables: Dict[str, str] = Field(
        default_factory=dict,
        description="Optional synthetic test environment variables (no host secrets)",
    )
    timeout_seconds: int = Field(
        default=60,
        ge=5,
        le=300,
        description="Execution wall-clock timeout in seconds (default: 60s, max: 300s)",
    )
    memory_limit_mb: int = Field(
        default=512,
        ge=128,
        le=2048,
        description="Memory budget limit in megabytes (default: 512MB)",
    )
    cpu_limit: float = Field(
        default=1.0,
        ge=0.5,
        le=4.0,
        description="CPU core limit budget (default: 1.0 core)",
    )
    pids_limit: int = Field(
        default=64,
        ge=16,
        le=256,
        description="Maximum process PID budget ceiling (default: 64)",
    )

    @field_validator("server_entrypoint")
    @classmethod
    def validate_server_entrypoint(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("server_entrypoint cannot be empty")
        if clean.startswith("/") or clean.startswith("\\"):
            raise ValueError("server_entrypoint must be a relative path within the repository")
        parts = clean.replace("\\", "/").split("/")
        if any(p == ".." or p == "." for p in parts if p):
            raise ValueError("server_entrypoint cannot traverse directories with '..'")
        if PROHIBITED_CMD_CHARS_PATTERN.search(clean):
            raise ValueError("server_entrypoint contains prohibited characters")
        return clean

    @field_validator("server_args")
    @classmethod
    def validate_server_args(cls, args: List[str]) -> List[str]:
        for idx, arg in enumerate(args):
            if PROHIBITED_CMD_CHARS_PATTERN.search(arg):
                raise ValueError(f"server_args[{idx}] contains prohibited shell metacharacters")
            if len(arg) > 256:
                raise ValueError(f"server_args[{idx}] exceeds maximum argument length of 256 characters")
        return args

    @field_validator("environment_variables")
    @classmethod
    def validate_env_vars(cls, env: Dict[str, str]) -> Dict[str, str]:
        for k, v in env.items():
            if not re.match(r"^[A-Z0-9_]{1,64}$", k):
                raise ValueError(f"Environment variable name '{k}' is invalid (must be alphanumeric/uppercase)")
            if len(v) > 1024:
                raise ValueError(f"Environment variable value for '{k}' exceeds maximum length (1024 chars)")
            if any(secret_term in k.lower() for secret_term in ("secret", "token", "password", "key", "vultr")):
                raise ValueError(f"Environment variable '{k}' resembles a credential; credentials are prohibited inside the sandbox")
        return env


class SandboxExecutionResult(BaseModel):
    """Complete structured execution result and security audit verdict."""
    __test__ = False
    job_id: str = Field(description="Unique job UUID")
    repository_url: str = Field(description="Target repository URL")
    commit_sha: str = Field(description="Executed immutable commit SHA")
    lifecycle_status: ExecutionLifecycleState = Field(description="Final lifecycle state")
    test_verdict: TestVerdict = Field(description="Harness test verdict (PASSED/FAILED/TIMED_OUT)")
    security_status: SecurityEnforcementStatus = Field(description="Inspected security status")
    cleanup_status: CleanupStatus = Field(description="Verified container and workspace cleanup status")
    verification_verdict: VerificationVerdict = Field(description="Composite release verification outcome")
    exit_code: Optional[int] = Field(default=None, description="Harness process exit code")
    stdout: str = Field(default="", max_length=65_536, description="Harness stdout (max 64KB)")
    stderr: str = Field(default="", max_length=65_536, description="Harness stderr (max 64KB)")
    duration_ms: float = Field(default=0.0, description="Total execution duration in milliseconds")
    start_time: Optional[str] = Field(default=None, description="ISO-8601 start timestamp")
    end_time: Optional[str] = Field(default=None, description="ISO-8601 end timestamp")
    security_report: SecurityEnforcementReport = Field(description="Detailed security enforcement evidence")
    cleanup_details: Optional[str] = Field(default=None, description="Details of cleanup verification")
    error_code: Optional[str] = Field(default=None, description="Error code if execution failed")
    error_message: Optional[str] = Field(default=None, description="Sanitized diagnostic error message")


class SandboxCapabilitiesResponse(BaseModel):
    """Capabilities and security configurations supported by the sandbox execution system."""
    __test__ = False
    prewarmed_dependencies: List[str] = Field(description="Packages pre-warmed in the immutable base image")
    runtime_network_mode: str = Field(default="none", description="Network isolation mode (default-deny)")
    mcp_transport: str = Field(default="stdio", description="Job-scoped MCP communication transport")
    default_timeout_seconds: int = Field(default=60, description="Default execution timeout")
    max_timeout_seconds: int = Field(default=300, description="Maximum execution timeout")
    default_memory_mb: int = Field(default=512, description="Default memory limit")
    max_memory_mb: int = Field(default=2048, description="Maximum memory limit")
    enforced_security_features: List[str] = Field(description="Active containment features")
