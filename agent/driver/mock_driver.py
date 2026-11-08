"""Mock execution driver for isolated testing without Docker daemon or untrusted execution."""

import asyncio
from typing import List, Optional
from agent.driver.base import (
    ContainerConfig,
    ContainerInspectResult,
    ExecutionRunResult,
    ISandboxExecutionDriver,
)


class MockSandboxExecutionDriver(ISandboxExecutionDriver):
    """Deterministic mock driver simulating container lifecycles, inspects, and failures."""

    def __init__(
        self,
        simulated_exit_code: int = 0,
        simulated_stdout: str = "===== 1 passed in 0.15s =====",
        simulated_stderr: str = "",
        simulated_duration_ms: float = 150.0,
        simulate_timeout: bool = False,
        simulate_cleanup_failure: bool = False,
        simulate_security_violation: Optional[str] = None,
    ):
        self.simulated_exit_code = simulated_exit_code
        self.simulated_stdout = simulated_stdout
        self.simulated_stderr = simulated_stderr
        self.simulated_duration_ms = simulated_duration_ms
        self.simulate_timeout = simulate_timeout
        self.simulate_cleanup_failure = simulate_cleanup_failure
        self.simulate_security_violation = simulate_security_violation

        # Observable telemetry
        self.created_containers: List[str] = []
        self.killed_containers: List[str] = []
        self.removed_containers: List[str] = []
        self.cleaned_workspaces: List[str] = []
        self.last_config: Optional[ContainerConfig] = None

    async def create_and_start_container(
        self,
        job_id: str,
        config: ContainerConfig,
    ) -> str:
        self.last_config = config
        container_id = f"mock-container-{job_id[:8]}"
        self.created_containers.append(container_id)
        return container_id

    async def inspect_container(
        self,
        container_id: str,
    ) -> ContainerInspectResult:
        if self.last_config is None:
            raise RuntimeError("No container created to inspect")

        # By default, mirror exactly what was requested unless simulating a violation
        user = self.last_config.user
        privileged = False
        network_mode = self.last_config.network_mode
        read_only_rootfs = self.last_config.read_only_rootfs
        cap_drop = list(self.last_config.cap_drop)
        security_opt = list(self.last_config.security_opt)
        memory_bytes = self.last_config.memory_limit_bytes
        cpu_quota = self.last_config.cpu_quota
        cpu_period = self.last_config.cpu_period
        pids_limit = self.last_config.pids_limit
        binds = [f"{k}:{v}" for k, v in self.last_config.binds.items()]

        # Apply simulated violation if configured
        if self.simulate_security_violation == "network_enabled":
            network_mode = "bridge"
        elif self.simulate_security_violation == "root_user":
            user = "0:0"
        elif self.simulate_security_violation == "read_only_disabled":
            read_only_rootfs = False
        elif self.simulate_security_violation == "capabilities_retained":
            cap_drop = []
        elif self.simulate_security_violation == "docker_socket_mounted":
            binds.append("/var/run/docker.sock:/var/run/docker.sock:ro")
        elif self.simulate_security_violation == "unverifiable":
            return ContainerInspectResult(
                container_id=container_id,
                user="",
                privileged=False,
                network_mode="",
                read_only_rootfs=False,
                cap_drop=[],
                security_opt=[],
                memory_bytes=0,
                cpu_quota=0,
                cpu_period=0,
                pids_limit=0,
            )

        return ContainerInspectResult(
            container_id=container_id,
            user=user,
            privileged=privileged,
            network_mode=network_mode,
            read_only_rootfs=read_only_rootfs,
            cap_drop=cap_drop,
            security_opt=security_opt,
            memory_bytes=memory_bytes,
            cpu_quota=cpu_quota,
            cpu_period=cpu_period,
            pids_limit=pids_limit,
            binds=binds,
            is_running=True,
        )

    async def wait_for_completion(
        self,
        container_id: str,
        timeout_seconds: float,
    ) -> ExecutionRunResult:
        if self.simulate_timeout:
            await asyncio.sleep(0.01)
            return ExecutionRunResult(
                exit_code=137,
                stdout=self.simulated_stdout,
                stderr=self.simulated_stderr + "\nProcess timed out.",
                duration_ms=timeout_seconds * 1000.0,
                timed_out=True,
            )

        return ExecutionRunResult(
            exit_code=self.simulated_exit_code,
            stdout=self.simulated_stdout,
            stderr=self.simulated_stderr,
            duration_ms=self.simulated_duration_ms,
            timed_out=False,
        )

    async def kill_container(self, container_id: str) -> bool:
        self.killed_containers.append(container_id)
        return True

    async def remove_container(self, container_id: str) -> bool:
        if self.simulate_cleanup_failure:
            return False
        self.removed_containers.append(container_id)
        return True

    async def cleanup_workspace(self, workspace_path: str) -> bool:
        if self.simulate_cleanup_failure:
            return False
        self.cleaned_workspaces.append(workspace_path)
        return True
