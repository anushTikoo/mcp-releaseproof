"""Lifecycle manager orchestrating sandbox preparation, execution, audit, and teardown."""

import ast
from datetime import datetime, timezone
import logging
import os
import re
import time
from typing import Dict, List, Optional, Set
import uuid

from agent.config import AgentSettings, get_agent_settings
from agent.driver.base import (
    ContainerConfig,
    ContainerInspectResult,
    ExecutionRunResult,
    ISandboxExecutionDriver,
)
from backend.app.schemas.sandbox import (
    CleanupStatus,
    ExecutionLifecycleState,
    SandboxExecutionRequest,
    SandboxExecutionResult,
    SecurityControlItem,
    SecurityEnforcementReport,
    SecurityEnforcementStatus,
    TestVerdict,
    VerificationVerdict,
)

logger = logging.getLogger(__name__)


class SandboxLifecycleManager:
    """Orchestrates job lifecycle states, isolation auditing, and guaranteed teardown."""

    def __init__(
        self,
        driver: ISandboxExecutionDriver,
        settings: Optional[AgentSettings] = None,
    ):
        self.driver = driver
        self.settings = settings or get_agent_settings()
        self._active_jobs: Dict[str, SandboxExecutionResult] = {}
        self._active_containers: Dict[str, str] = {}
        self._active_workspaces: Dict[str, str] = {}
        self._aborted_jobs: Set[str] = set()

    def get_job(self, job_id: str) -> Optional[SandboxExecutionResult]:
        return self._active_jobs.get(job_id)

    async def abort_job(self, job_id: str) -> Optional[SandboxExecutionResult]:
        """Abort an in-flight job, terminating its container and cleaning up resources.

        Guarantees idempotent behavior:
        - Unknown job ID: returns None (404)
        - Already completed or aborted: returns existing result (200)
        - Active job: terminates process/container, cleans workspace, updates status to FAILED
        - Cleanup failure: marks cleanup_status=CLEANUP_FAILED and lifecycle_status=CLEANUP_FAILED
        """
        # Validate job_id shape
        if not re.match(r"^job-[0-9a-fA-F]{8,32}$", job_id):
            return None

        result = self._active_jobs.get(job_id)
        if result is None:
            return None

        terminal_states = {
            ExecutionLifecycleState.COMPLETED,
            ExecutionLifecycleState.FAILED,
            ExecutionLifecycleState.TIMED_OUT,
            ExecutionLifecycleState.CLEANUP_FAILED,
        }
        if result.lifecycle_status in terminal_states:
            # Idempotent response for already-terminated jobs
            return result

        # Mark aborted
        self._aborted_jobs.add(job_id)
        result.lifecycle_status = ExecutionLifecycleState.FAILED
        result.test_verdict = TestVerdict.ERROR
        result.error_code = "JOB_ABORTED"
        result.error_message = "Job execution was aborted by client request."
        result.end_time = datetime.now(timezone.utc).isoformat()
        result.verification_verdict = VerificationVerdict.INFRASTRUCTURE_FAILURE

        # Terminate active container
        container_id = self._active_containers.pop(job_id, None)
        cleaned_container = True
        if container_id:
            try:
                await self.driver.kill_container(container_id)
                cleaned_container = await self.driver.remove_container(container_id)
            except Exception as exc:
                logger.error("Error terminating container '%s' during abort: %s", container_id, exc)
                cleaned_container = False

        # Cleanup active workspace
        workspace_path = self._active_workspaces.pop(job_id, None)
        cleaned_disk = True
        if workspace_path:
            try:
                cleaned_disk = await self.driver.cleanup_workspace(workspace_path)
            except Exception as exc:
                logger.error("Error cleaning workspace '%s' during abort: %s", workspace_path, exc)
                cleaned_disk = False

        if cleaned_container and cleaned_disk:
            result.cleanup_status = CleanupStatus.VERIFIED_CLEAN
            result.cleanup_details = "Container and ephemeral workspace removed cleanly on abort."
        else:
            result.cleanup_status = CleanupStatus.CLEANUP_FAILED
            result.lifecycle_status = ExecutionLifecycleState.CLEANUP_FAILED
            result.error_code = "JOB_ABORTED_CLEANUP_FAILED"
            result.cleanup_details = f"Abort cleanup failed: container_removed={cleaned_container}, disk_removed={cleaned_disk}"

        return result

    def check_dependency_requirements(self, harness_code: str) -> Optional[str]:
        """Verify that requested imports are satisfied by pre-warmed image without network egress."""
        # Check against pre-warmed package capability list
        # Prohibited dynamic dependency installation in pre-warmed image mode
        prewarmed_root_modules = {
            "pytest",
            "pytest_asyncio",
            "mcp",
            "pydantic",
            "fastmcp",
            "httpx",
            "anyio",
            "asyncio",
            "typing",
            "typing_extensions",
            "dataclasses",
            "json",
            "sys",
            "os",
            "math",
            "re",
        }
        import ast
        try:
            tree = ast.parse(harness_code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        if top not in prewarmed_root_modules:
                            return f"Unsupported dependency '{top}'. Pre-warmed image only supports {sorted(list(prewarmed_root_modules))}."
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        top = node.module.split(".")[0]
                        if top not in prewarmed_root_modules:
                            return f"Unsupported dependency '{top}'. Pre-warmed image only supports {sorted(list(prewarmed_root_modules))}."
        except Exception:
            pass
        return None

    def evaluate_security_inspection(
        self,
        requested: ContainerConfig,
        inspected: ContainerInspectResult,
    ) -> SecurityEnforcementReport:
        """Independently audit live container inspection fields against policy requirements."""
        controls: List[SecurityControlItem] = []
        is_all_verified = True
        any_violated = False

        # 1. Non-root user
        if not inspected.user:
            user_status = SecurityEnforcementStatus.INCOMPLETE
            is_all_verified = False
        elif inspected.user == requested.user and inspected.user not in ("0", "0:0", "root"):
            user_status = SecurityEnforcementStatus.VERIFIED
        else:
            user_status = SecurityEnforcementStatus.VIOLATED
            is_all_verified = False
            any_violated = True

        controls.append(
            SecurityControlItem(
                control_name="non_root_user",
                requested=requested.user,
                observed=inspected.user,
                status=user_status,
                details="Container must execute under unprivileged UID 10001",
            )
        )

        # 2. Privileged container mode
        if inspected.privileged:
            priv_status = SecurityEnforcementStatus.VIOLATED
            is_all_verified = False
            any_violated = True
        else:
            priv_status = SecurityEnforcementStatus.VERIFIED

        controls.append(
            SecurityControlItem(
                control_name="no_privileged_mode",
                requested="privileged=false",
                observed=f"privileged={inspected.privileged}",
                status=priv_status,
                details="Privileged mode must be explicitly false",
            )
        )

        # 3. Network isolation
        if not inspected.network_mode:
            net_status = SecurityEnforcementStatus.INCOMPLETE
            is_all_verified = False
        elif inspected.network_mode == "none":
            net_status = SecurityEnforcementStatus.VERIFIED
        else:
            net_status = SecurityEnforcementStatus.VIOLATED
            is_all_verified = False
            any_violated = True

        controls.append(
            SecurityControlItem(
                control_name="network_isolation",
                requested="network=none",
                observed=f"network={inspected.network_mode}",
                status=net_status,
                details="Network access during runtime must be default-deny (mode 'none')",
            )
        )

        # 4. Read-only root filesystem
        if inspected.read_only_rootfs is True:
            ro_status = SecurityEnforcementStatus.VERIFIED
        elif inspected.read_only_rootfs is False and inspected.is_running:
            ro_status = SecurityEnforcementStatus.VIOLATED
            is_all_verified = False
            any_violated = True
        else:
            ro_status = SecurityEnforcementStatus.INCOMPLETE
            is_all_verified = False

        controls.append(
            SecurityControlItem(
                control_name="read_only_rootfs",
                requested="read_only=true",
                observed=f"read_only={inspected.read_only_rootfs}",
                status=ro_status,
                details="Root filesystem must be mounted read-only",
            )
        )

        # 5. Capabilities dropped
        if "ALL" in inspected.cap_drop:
            caps_status = SecurityEnforcementStatus.VERIFIED
        elif inspected.cap_drop:
            caps_status = SecurityEnforcementStatus.VIOLATED
            is_all_verified = False
            any_violated = True
        else:
            caps_status = SecurityEnforcementStatus.INCOMPLETE
            is_all_verified = False

        controls.append(
            SecurityControlItem(
                control_name="capabilities_dropped",
                requested="cap_drop=['ALL']",
                observed=f"cap_drop={inspected.cap_drop}",
                status=caps_status,
                details="All Linux capabilities must be dropped",
            )
        )

        # 6. No-new-privileges
        nnp_ok = any("no-new-privileges:true" in opt or "no-new-privileges" in opt for opt in inspected.security_opt)
        if nnp_ok:
            nnp_status = SecurityEnforcementStatus.VERIFIED
        elif inspected.security_opt:
            nnp_status = SecurityEnforcementStatus.VIOLATED
            is_all_verified = False
            any_violated = True
        else:
            nnp_status = SecurityEnforcementStatus.INCOMPLETE
            is_all_verified = False

        controls.append(
            SecurityControlItem(
                control_name="no_new_privileges",
                requested="security_opt=['no-new-privileges:true']",
                observed=f"security_opt={inspected.security_opt}",
                status=nnp_status,
                details="PR_SET_NO_NEW_PRIVS bit must be active",
            )
        )

        # 7. No Docker socket mounted
        docker_sock_mounted = any("docker.sock" in b for b in inspected.binds)
        if docker_sock_mounted:
            sock_status = SecurityEnforcementStatus.VIOLATED
            is_all_verified = False
            any_violated = True
        else:
            sock_status = SecurityEnforcementStatus.VERIFIED

        controls.append(
            SecurityControlItem(
                control_name="no_docker_socket",
                requested="docker.sock=excluded",
                observed="docker.sock=mounted" if docker_sock_mounted else "docker.sock=excluded",
                status=sock_status,
                details="Docker daemon socket must never be exposed inside sandbox",
            )
        )

        # 8. Resource limits
        mem_ok = inspected.memory_bytes == requested.memory_limit_bytes
        pids_ok = inspected.pids_limit == requested.pids_limit
        if mem_ok and pids_ok:
            res_status = SecurityEnforcementStatus.VERIFIED
        else:
            res_status = SecurityEnforcementStatus.INCOMPLETE
            is_all_verified = False

        controls.append(
            SecurityControlItem(
                control_name="resource_limits",
                requested=f"memory={requested.memory_limit_bytes}, pids={requested.pids_limit}",
                observed=f"memory={inspected.memory_bytes}, pids={inspected.pids_limit}",
                status=res_status,
                details="Memory and PID ceilings must match configured limits",
            )
        )

        if any_violated:
            overall = SecurityEnforcementStatus.VIOLATED
            summary = "One or more mandatory security containment controls were violated."
        elif not is_all_verified:
            overall = SecurityEnforcementStatus.INCOMPLETE
            summary = "Security containment controls could not be completely verified from container inspection."
        else:
            overall = SecurityEnforcementStatus.VERIFIED
            summary = (
                "Container configuration verified via Docker Engine inspect (non-root UID, network none, "
                "read-only rootfs, dropped capabilities, no-new-privileges, resource limits). "
                "Note: Docker inspect confirms container launch configuration parameters, but host-level kernel "
                "seccomp enforcement, eBPF telemetry, and external firewall packet filtering remain external host-level boundaries."
            )

        return SecurityEnforcementReport(
            overall_status=overall,
            controls=controls,
            verified_at=datetime.now(timezone.utc).isoformat(),
            summary=summary,
        )

    async def execute_job(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        """Execute full sandbox lifecycle with state machine, timeout, and cleanup guarantees."""
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        # Initial default result record
        result = SandboxExecutionResult(
            job_id=job_id,
            repository_url=request.repository_url,
            commit_sha=request.commit_sha,
            lifecycle_status=ExecutionLifecycleState.QUEUED,
            test_verdict=TestVerdict.NOT_RUN,
            security_status=SecurityEnforcementStatus.INCOMPLETE,
            cleanup_status=CleanupStatus.PENDING,
            verification_verdict=VerificationVerdict.INFRASTRUCTURE_FAILURE,
            start_time=now_iso,
            security_report=SecurityEnforcementReport(
                overall_status=SecurityEnforcementStatus.INCOMPLETE,
                controls=[],
                summary="Security inspection pending",
            ),
        )
        self._active_jobs[job_id] = result

        # Check pre-warmed dependency requirements
        dep_err = self.check_dependency_requirements(request.harness_code)
        if dep_err:
            result.lifecycle_status = ExecutionLifecycleState.FAILED
            result.error_code = "UNSUPPORTED_DEPENDENCIES"
            result.error_message = dep_err
            result.verification_verdict = VerificationVerdict.UNSUPPORTED_DEPENDENCIES
            result.cleanup_status = CleanupStatus.VERIFIED_CLEAN
            result.end_time = datetime.now(timezone.utc).isoformat()
            return result

        # Enforce workspace root containment against path traversal
        real_root = os.path.realpath(self.settings.SANDBOX_WORKSPACE_ROOT)
        workspace_path = os.path.realpath(os.path.join(real_root, job_id))
        if not workspace_path.startswith(real_root + os.sep):
            result.lifecycle_status = ExecutionLifecycleState.FAILED
            result.error_code = "INVALID_WORKSPACE_PATH"
            result.error_message = "Workspace path traversal attempt detected."
            result.verification_verdict = VerificationVerdict.INFRASTRUCTURE_FAILURE
            result.cleanup_status = CleanupStatus.VERIFIED_CLEAN
            result.end_time = datetime.now(timezone.utc).isoformat()
            return result

        container_id: Optional[str] = None

        try:
            if job_id in self._aborted_jobs:
                return self._active_jobs[job_id]

            # 1. State: PREPARING
            result.lifecycle_status = ExecutionLifecycleState.PREPARING
            os.makedirs(workspace_path, exist_ok=True)
            self._active_workspaces[job_id] = workspace_path

            # Write test harness into workspace
            harness_path = os.path.join(workspace_path, "test_harness.py")
            with open(harness_path, "w", encoding="utf-8") as f:
                f.write(request.harness_code)

            # Configure container launch specification (immutable pre-warmed image, non-root)
            container_config = ContainerConfig(
                image=self.settings.SANDBOX_BASE_IMAGE,
                user=self.settings.SANDBOX_CONTAINER_USER,
                command=["python", "-m", "pytest", "-q", "/workspace/test_harness.py"],
                network_mode="none",
                read_only_rootfs=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                memory_limit_bytes=request.memory_limit_mb * 1024 * 1024,
                cpu_quota=int(request.cpu_limit * 100000),
                cpu_period=100000,
                pids_limit=request.pids_limit,
                binds={workspace_path: "/workspace:ro"},
                tmpfs={"/tmp": "size=64m,noexec,nosuid,nodev"},
                environment=request.environment_variables,
            )

            # Check if aborted before container launch
            if job_id in self._aborted_jobs:
                return self._active_jobs[job_id]

            # 2. Launch container & inspect
            container_id = await self.driver.create_and_start_container(job_id=job_id, config=container_config)
            self._active_containers[job_id] = container_id

            if job_id in self._aborted_jobs:
                return self._active_jobs[job_id]

            inspect_result = await self.driver.inspect_container(container_id)
            sec_report = self.evaluate_security_inspection(requested=container_config, inspected=inspect_result)
            result.security_report = sec_report
            result.security_status = sec_report.overall_status

            if sec_report.overall_status != SecurityEnforcementStatus.VERIFIED:
                logger.error("Security enforcement failed for job '%s': %s", job_id, sec_report.summary)
                result.lifecycle_status = ExecutionLifecycleState.FAILED
                result.error_code = "SECURITY_ENFORCEMENT_FAILED"
                result.error_message = sec_report.summary
                result.verification_verdict = VerificationVerdict.SECURITY_VIOLATION
                return result

            # 3. State: RUNNING
            result.lifecycle_status = ExecutionLifecycleState.RUNNING
            run_res: ExecutionRunResult = await self.driver.wait_for_completion(
                container_id=container_id,
                timeout_seconds=request.timeout_seconds,
            )

            if job_id in self._aborted_jobs:
                return self._active_jobs[job_id]

            result.exit_code = run_res.exit_code
            result.stdout = run_res.stdout[: self.settings.MAX_OUTPUT_BYTES]
            result.stderr = run_res.stderr[: self.settings.MAX_OUTPUT_BYTES]
            result.duration_ms = run_res.duration_ms

            if run_res.timed_out:
                result.lifecycle_status = ExecutionLifecycleState.TIMED_OUT
                result.test_verdict = TestVerdict.TIMED_OUT
                result.error_code = "EXECUTION_TIMEOUT"
                result.error_message = f"Job execution exceeded wall-clock limit of {request.timeout_seconds}s."
                result.verification_verdict = VerificationVerdict.EXECUTION_TIMEOUT
            elif run_res.exit_code == 0:
                result.lifecycle_status = ExecutionLifecycleState.COMPLETED
                result.test_verdict = TestVerdict.PASSED
            else:
                result.lifecycle_status = ExecutionLifecycleState.COMPLETED
                result.test_verdict = TestVerdict.FAILED
                result.verification_verdict = VerificationVerdict.REGRESSION_DETECTED

        except Exception as exc:
            if job_id in self._aborted_jobs:
                return self._active_jobs[job_id]
            logger.exception("Unexpected execution error in job '%s': %s", job_id, exc)
            result.lifecycle_status = ExecutionLifecycleState.FAILED
            result.test_verdict = TestVerdict.ERROR
            result.error_code = "INTERNAL_ERROR"
            result.error_message = f"Execution failed due to internal error: {str(exc)}"
            result.verification_verdict = VerificationVerdict.INFRASTRUCTURE_FAILURE

        finally:
            self._active_containers.pop(job_id, None)
            self._active_workspaces.pop(job_id, None)

            # Mandatory Cleanup Phase (if not already handled by abort)
            if job_id not in self._aborted_jobs:
                cleaned_container = True
                if container_id:
                    cleaned_container = await self.driver.remove_container(container_id)

                cleaned_disk = await self.driver.cleanup_workspace(workspace_path)
                result.end_time = datetime.now(timezone.utc).isoformat()

                if cleaned_container and cleaned_disk:
                    result.cleanup_status = CleanupStatus.VERIFIED_CLEAN
                    result.cleanup_details = "Container and ephemeral workspace removed cleanly."
                else:
                    result.cleanup_status = CleanupStatus.CLEANUP_FAILED
                    result.lifecycle_status = ExecutionLifecycleState.CLEANUP_FAILED
                    result.cleanup_details = f"Cleanup failed: container_removed={cleaned_container}, disk_removed={cleaned_disk}"
                    result.verification_verdict = VerificationVerdict.INFRASTRUCTURE_FAILURE

                # 5. Overall Verification Verdict Determination
                if (
                    result.test_verdict == TestVerdict.PASSED
                    and result.security_status == SecurityEnforcementStatus.VERIFIED
                    and result.cleanup_status == CleanupStatus.VERIFIED_CLEAN
                ):
                    result.verification_verdict = VerificationVerdict.VERIFIED_SUCCESS
                elif result.test_verdict == TestVerdict.FAILED:
                    result.verification_verdict = VerificationVerdict.REGRESSION_DETECTED
                elif result.test_verdict == TestVerdict.TIMED_OUT or result.lifecycle_status == ExecutionLifecycleState.TIMED_OUT:
                    result.verification_verdict = VerificationVerdict.EXECUTION_TIMEOUT
                elif result.security_status != SecurityEnforcementStatus.VERIFIED:
                    result.verification_verdict = VerificationVerdict.SECURITY_VIOLATION
                elif result.cleanup_status == CleanupStatus.CLEANUP_FAILED:
                    result.verification_verdict = VerificationVerdict.INFRASTRUCTURE_FAILURE

        return result
