"""Production Docker execution driver for Vultr Compute worker VM."""

import asyncio
import json
import logging
import os
import shutil
import time
from typing import List, Optional
from agent.driver.base import (
    ContainerConfig,
    ContainerInspectResult,
    ExecutionRunResult,
    ISandboxExecutionDriver,
)

logger = logging.getLogger(__name__)


class DockerExecutionDriver(ISandboxExecutionDriver):
    """Executes sandboxes using Docker CLI on the worker host with mandatory containment."""

    def __init__(self, docker_binary: str = "docker"):
        self.docker_binary = docker_binary

    def build_run_args(self, container_name: str, config: ContainerConfig) -> List[str]:
        """Construct the exact list of command line arguments passed to 'docker create'."""
        args = [
            self.docker_binary,
            "create",
            "--name", container_name,
            "--user", config.user,
            "--network", config.network_mode,
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true",
            "--memory", str(config.memory_limit_bytes),
            "--cpu-quota", str(config.cpu_quota),
            "--cpu-period", str(config.cpu_period),
            "--pids-limit", str(config.pids_limit),
        ]

        if config.read_only_rootfs:
            args.append("--read-only")

        # tmpfs mounts
        for mount_path, mount_opts in config.tmpfs.items():
            args.extend(["--tmpfs", f"{mount_path}:{mount_opts}"])

        # Volume binds (strictly verified against Docker socket and sensitive host paths)
        prohibited_host_subdirs = {"docker.sock", "/proc", "/sys", "/etc", "/root", "/boot", "/dev"}
        for host_path, container_path in config.binds.items():
            norm_host = os.path.normcase(os.path.normpath(host_path))
            if "docker.sock" in norm_host or "docker.sock" in container_path:
                raise ValueError("Security violation: Docker socket cannot be mounted in sandbox container")
            for prohibited in prohibited_host_subdirs:
                if prohibited in norm_host or prohibited in container_path:
                    raise ValueError(f"Security violation: Sensitive path '{prohibited}' cannot be mounted in sandbox container")
            args.extend(["-v", f"{host_path}:{container_path}"])

        # Environment variables (strict key and value validation)
        import re
        for k, v in config.environment.items():
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", k):
                raise ValueError(f"Security violation: Invalid environment variable name '{k}'")
            if "\x00" in str(v):
                raise ValueError("Security violation: Environment variable value contains null byte")
            args.extend(["-e", f"{k}={v}"])

        # Working directory inside container
        args.extend(["-w", "/workspace"])

        # Base image and entrypoint command (image lock)
        if config.image != "mcp-releaseproof-runner:latest" and not config.image.startswith("mcp-releaseproof-runner:"):
            raise ValueError(f"Security violation: Unauthorized container image '{config.image}'")
        args.append(config.image)
        args.extend(config.command)

        return args

    async def create_and_start_container(
        self,
        job_id: str,
        config: ContainerConfig,
    ) -> str:
        container_name = f"mcp-sandbox-{job_id[:12]}"
        run_args = self.build_run_args(container_name=container_name, config=config)

        # 1. Create container
        proc = await asyncio.create_subprocess_exec(
            *run_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Failed to create sandbox container: {err_msg}")

        container_id = stdout.decode("utf-8", errors="replace").strip()

        # 2. Start container
        start_proc = await asyncio.create_subprocess_exec(
            self.docker_binary, "start", container_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, start_err = await start_proc.communicate()
        if start_proc.returncode != 0:
            err_msg = start_err.decode("utf-8", errors="replace").strip()
            # Attempt best-effort cleanup of created container
            await self.remove_container(container_id)
            raise RuntimeError(f"Failed to start sandbox container: {err_msg}")

        return container_id

    async def inspect_container(
        self,
        container_id: str,
    ) -> ContainerInspectResult:
        proc = await asyncio.create_subprocess_exec(
            self.docker_binary, "inspect", container_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Failed to inspect container '{container_id}': {err_msg}")

        try:
            inspect_data = json.loads(stdout.decode("utf-8"))[0]
        except Exception as exc:
            raise RuntimeError(f"Failed to parse docker inspect output: {exc}")

        cfg = inspect_data.get("Config", {})
        host_cfg = inspect_data.get("HostConfig", {})
        state = inspect_data.get("State", {})

        return ContainerInspectResult(
            container_id=container_id,
            user=cfg.get("User", ""),
            privileged=host_cfg.get("Privileged", False),
            network_mode=host_cfg.get("NetworkMode", ""),
            read_only_rootfs=host_cfg.get("ReadonlyRootfs", False),
            cap_drop=host_cfg.get("CapDrop") or [],
            security_opt=host_cfg.get("SecurityOpt") or [],
            memory_bytes=host_cfg.get("Memory", 0),
            cpu_quota=host_cfg.get("CpuQuota", 0),
            cpu_period=host_cfg.get("CpuPeriod", 0),
            pids_limit=host_cfg.get("PidsLimit", 0),
            binds=host_cfg.get("Binds") or [],
            is_running=state.get("Running", False),
            exit_code=state.get("ExitCode"),
        )

    async def wait_for_completion(
        self,
        container_id: str,
        timeout_seconds: float,
    ) -> ExecutionRunResult:
        start_time = time.time()
        try:
            # Wait for container process to exit within the timeout budget
            wait_coro = asyncio.create_subprocess_exec(
                self.docker_binary, "wait", container_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            proc = await asyncio.wait_for(wait_coro, timeout=timeout_seconds)
            stdout, _ = await proc.communicate()
            exit_code_str = stdout.decode("utf-8", errors="replace").strip()
            exit_code = int(exit_code_str) if exit_code_str.isdigit() else 1
            duration_ms = (time.time() - start_time) * 1000.0

            # Capture stdout and stderr
            logs_proc = await asyncio.create_subprocess_exec(
                self.docker_binary, "logs", container_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            log_out, log_err = await logs_proc.communicate()

            return ExecutionRunResult(
                exit_code=exit_code,
                stdout=log_out.decode("utf-8", errors="replace")[:65536],
                stderr=log_err.decode("utf-8", errors="replace")[:65536],
                duration_ms=duration_ms,
                timed_out=False,
            )

        except asyncio.TimeoutError:
            duration_ms = (time.time() - start_time) * 1000.0
            logger.warning("Job container '%s' exceeded timeout of %ss; sending SIGKILL", container_id, timeout_seconds)
            await self.kill_container(container_id)

            # Retrieve any logs output before timeout
            logs_proc = await asyncio.create_subprocess_exec(
                self.docker_binary, "logs", container_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            log_out, log_err = await logs_proc.communicate()

            return ExecutionRunResult(
                exit_code=137,
                stdout=log_out.decode("utf-8", errors="replace")[:65536],
                stderr=(log_err.decode("utf-8", errors="replace") + f"\n[TIMEOUT] Execution exceeded {timeout_seconds}s limit.")[:65536],
                duration_ms=duration_ms,
                timed_out=True,
            )

    async def kill_container(self, container_id: str) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                self.docker_binary, "kill", container_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        except Exception as exc:
            logger.error("Failed to kill container '%s': %s", container_id, exc)
            return False

    async def remove_container(self, container_id: str) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                self.docker_binary, "rm", "-f", "-v", container_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        except Exception as exc:
            logger.error("Failed to remove container '%s': %s", container_id, exc)
            return False

    async def cleanup_workspace(self, workspace_path: str) -> bool:
        try:
            if os.path.exists(workspace_path):
                shutil.rmtree(workspace_path)
            return True
        except Exception as exc:
            logger.error("Failed to cleanup workspace '%s': %s", workspace_path, exc)
            return False
