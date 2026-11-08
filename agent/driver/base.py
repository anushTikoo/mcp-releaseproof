"""Abstract execution driver interface for Sandbox Execution Agent."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ContainerConfig:
    """Strongly typed container launch specification."""
    image: str
    user: str
    command: List[str]
    network_mode: str
    read_only_rootfs: bool
    cap_drop: List[str]
    security_opt: List[str]
    memory_limit_bytes: int
    cpu_quota: int
    cpu_period: int
    pids_limit: int
    binds: Dict[str, str] = field(default_factory=dict)
    tmpfs: Dict[str, str] = field(default_factory=dict)
    environment: Dict[str, str] = field(default_factory=dict)


@dataclass
class ContainerInspectResult:
    """Actual live configuration queried from docker inspect after container creation."""
    container_id: str
    user: str
    privileged: bool
    network_mode: str
    read_only_rootfs: bool
    cap_drop: List[str]
    security_opt: List[str]
    memory_bytes: int
    cpu_quota: int
    cpu_period: int
    pids_limit: int
    binds: List[str] = field(default_factory=list)
    is_running: bool = False
    exit_code: Optional[int] = None


@dataclass
class ExecutionRunResult:
    """Execution output and timing captured upon container termination."""
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool = False


class ISandboxExecutionDriver(ABC):
    """Abstract interface isolating Docker engine operations from the lifecycle manager."""

    @abstractmethod
    async def create_and_start_container(
        self,
        job_id: str,
        config: ContainerConfig,
    ) -> str:
        """Create and start an execution container, returning the container ID."""
        pass

    @abstractmethod
    async def inspect_container(
        self,
        container_id: str,
    ) -> ContainerInspectResult:
        """Inspect the live container state to audit enforced isolation controls."""
        pass

    @abstractmethod
    async def wait_for_completion(
        self,
        container_id: str,
        timeout_seconds: float,
    ) -> ExecutionRunResult:
        """Wait for the container to exit or kill it upon timeout, returning captured outputs."""
        pass

    @abstractmethod
    async def kill_container(
        self,
        container_id: str,
    ) -> bool:
        """Send SIGKILL to the container."""
        pass

    @abstractmethod
    async def remove_container(
        self,
        container_id: str,
    ) -> bool:
        """Remove the container and its anonymous volumes."""
        pass

    @abstractmethod
    async def cleanup_workspace(
        self,
        workspace_path: str,
    ) -> bool:
        """Securely wipe the ephemeral job workspace from disk."""
        pass
