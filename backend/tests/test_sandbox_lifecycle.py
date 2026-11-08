"""Lifecycle, isolation auditing, and state machine tests for SandboxLifecycleManager."""

import pytest

from agent.driver.mock_driver import MockSandboxExecutionDriver
from agent.manager import SandboxLifecycleManager
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

BASE_REQ = SandboxExecutionRequest(
    repository_url="https://github.com/modelcontextprotocol/servers",
    commit_sha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
    harness_code="import pytest\ndef test_dummy(): pass\n",
    server_entrypoint="server.py",
    timeout_seconds=30,
)


@pytest.mark.asyncio
async def test_lifecycle_successful_verification():
    """Verify clean passing run achieves VERIFIED_SUCCESS with all 3 conditions met."""
    driver = MockSandboxExecutionDriver(simulated_exit_code=0, simulated_stdout="1 passed")
    manager = SandboxLifecycleManager(driver=driver)

    result = await manager.execute_job(BASE_REQ)

    assert result.lifecycle_status == ExecutionLifecycleState.COMPLETED
    assert result.test_verdict == TestVerdict.PASSED
    assert result.security_status == SecurityEnforcementStatus.VERIFIED
    assert result.cleanup_status == CleanupStatus.VERIFIED_CLEAN
    assert result.verification_verdict == VerificationVerdict.VERIFIED_SUCCESS
    assert result.exit_code == 0
    assert "1 passed" in result.stdout
    assert len(driver.removed_containers) == 1
    assert len(driver.cleaned_workspaces) == 1


@pytest.mark.asyncio
async def test_lifecycle_regression_detected_is_not_verified_success():
    """Verify test failure produces REGRESSION_DETECTED, not verification success."""
    driver = MockSandboxExecutionDriver(
        simulated_exit_code=1,
        simulated_stdout="1 failed",
        simulated_stderr="AssertionError: tool schema mismatched",
    )
    manager = SandboxLifecycleManager(driver=driver)

    result = await manager.execute_job(BASE_REQ)

    # Harness completed, but test failed
    assert result.lifecycle_status == ExecutionLifecycleState.COMPLETED
    assert result.test_verdict == TestVerdict.FAILED
    assert result.security_status == SecurityEnforcementStatus.VERIFIED
    assert result.cleanup_status == CleanupStatus.VERIFIED_CLEAN
    assert result.verification_verdict == VerificationVerdict.REGRESSION_DETECTED
    assert result.verification_verdict != VerificationVerdict.VERIFIED_SUCCESS
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_lifecycle_security_violation_aborts_execution():
    """Verify security violation (e.g. network enabled) aborts job and sets SECURITY_VIOLATION."""
    driver = MockSandboxExecutionDriver(simulate_security_violation="network_enabled")
    manager = SandboxLifecycleManager(driver=driver)

    result = await manager.execute_job(BASE_REQ)

    assert result.lifecycle_status == ExecutionLifecycleState.FAILED
    assert result.security_status == SecurityEnforcementStatus.VIOLATED
    assert result.verification_verdict == VerificationVerdict.SECURITY_VIOLATION
    assert result.error_code == "SECURITY_ENFORCEMENT_FAILED"


@pytest.mark.asyncio
async def test_lifecycle_incomplete_security_inspection_is_violation():
    """Verify unverifiable container controls result in INCOMPLETE and SECURITY_VIOLATION."""
    driver = MockSandboxExecutionDriver(simulate_security_violation="unverifiable")
    manager = SandboxLifecycleManager(driver=driver)

    result = await manager.execute_job(BASE_REQ)

    assert result.security_status == SecurityEnforcementStatus.INCOMPLETE
    assert result.verification_verdict == VerificationVerdict.SECURITY_VIOLATION


@pytest.mark.asyncio
async def test_lifecycle_timeout_kills_container_and_cleans_up():
    """Verify execution timeout marks TIMED_OUT and sends kill signal."""
    driver = MockSandboxExecutionDriver(simulate_timeout=True)
    manager = SandboxLifecycleManager(driver=driver)

    result = await manager.execute_job(BASE_REQ)

    assert result.lifecycle_status == ExecutionLifecycleState.TIMED_OUT
    assert result.test_verdict == TestVerdict.TIMED_OUT
    assert result.verification_verdict == VerificationVerdict.EXECUTION_TIMEOUT
    assert result.cleanup_status == CleanupStatus.VERIFIED_CLEAN
    assert len(driver.removed_containers) == 1


@pytest.mark.asyncio
async def test_lifecycle_cleanup_failure_prevents_success_verdict():
    """Verify cleanup failure sets CLEANUP_FAILED and blocks VERIFIED_SUCCESS even if tests pass."""
    driver = MockSandboxExecutionDriver(simulated_exit_code=0, simulate_cleanup_failure=True)
    manager = SandboxLifecycleManager(driver=driver)

    result = await manager.execute_job(BASE_REQ)

    assert result.test_verdict == TestVerdict.PASSED  # Test passed
    assert result.cleanup_status == CleanupStatus.CLEANUP_FAILED  # But cleanup failed
    assert result.lifecycle_status == ExecutionLifecycleState.CLEANUP_FAILED
    assert result.verification_verdict == VerificationVerdict.INFRASTRUCTURE_FAILURE
    assert result.verification_verdict != VerificationVerdict.VERIFIED_SUCCESS


@pytest.mark.asyncio
async def test_lifecycle_unsupported_dependencies_rejected_without_container_launch():
    """Verify dependencies outside pre-warmed image are rejected with UNSUPPORTED_DEPENDENCIES."""
    driver = MockSandboxExecutionDriver()
    manager = SandboxLifecycleManager(driver=driver)

    req = SandboxExecutionRequest(
        repository_url="https://github.com/modelcontextprotocol/servers",
        commit_sha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        harness_code="import torch\ndef test_fn(): pass\n",
        server_entrypoint="server.py",
    )

    result = await manager.execute_job(req)

    assert result.lifecycle_status == ExecutionLifecycleState.FAILED
    assert result.error_code == "UNSUPPORTED_DEPENDENCIES"
    assert result.verification_verdict == VerificationVerdict.UNSUPPORTED_DEPENDENCIES
    assert len(driver.created_containers) == 0  # No container was created


@pytest.mark.asyncio
async def test_lifecycle_abort_active_job_terminates_and_cleans():
    """Verify aborting an active in-flight job kills container and removes workspace."""
    driver = MockSandboxExecutionDriver()
    manager = SandboxLifecycleManager(driver=driver)

    job_id = "job-abcdef123456"
    container_id = "mock-container-abc"
    workspace_path = f"/tmp/releaseproof-workspaces/{job_id}"

    # Setup simulated in-flight job state
    initial_result = SandboxExecutionResult(
        job_id=job_id,
        repository_url="https://github.com/example/repo",
        commit_sha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        lifecycle_status=ExecutionLifecycleState.RUNNING,
        test_verdict=TestVerdict.NOT_RUN,
        security_status=SecurityEnforcementStatus.VERIFIED,
        cleanup_status=CleanupStatus.PENDING,
        verification_verdict=VerificationVerdict.INFRASTRUCTURE_FAILURE,
        start_time="2026-01-01T00:00:00Z",
        security_report=SecurityEnforcementReport(
            overall_status=SecurityEnforcementStatus.VERIFIED,
            controls=[],
            summary="Verified",
        ),
    )
    manager._active_jobs[job_id] = initial_result
    manager._active_containers[job_id] = container_id
    manager._active_workspaces[job_id] = workspace_path

    aborted_result = await manager.abort_job(job_id)

    assert aborted_result is not None
    assert aborted_result.lifecycle_status == ExecutionLifecycleState.FAILED
    assert aborted_result.error_code == "JOB_ABORTED"
    assert aborted_result.cleanup_status == CleanupStatus.VERIFIED_CLEAN
    assert aborted_result.verification_verdict == VerificationVerdict.INFRASTRUCTURE_FAILURE

    # Verify driver kill, removal, and workspace cleanup were called
    assert container_id in driver.killed_containers
    assert container_id in driver.removed_containers
    assert workspace_path in driver.cleaned_workspaces


@pytest.mark.asyncio
async def test_lifecycle_abort_cleanup_failure_reports_cleanup_failed():
    """Verify cleanup failure during abort flags CLEANUP_FAILED."""
    driver = MockSandboxExecutionDriver(simulate_cleanup_failure=True)
    manager = SandboxLifecycleManager(driver=driver)

    job_id = "job-abcdef123456"
    initial_result = SandboxExecutionResult(
        job_id=job_id,
        repository_url="https://github.com/example/repo",
        commit_sha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        lifecycle_status=ExecutionLifecycleState.RUNNING,
        test_verdict=TestVerdict.NOT_RUN,
        security_status=SecurityEnforcementStatus.VERIFIED,
        cleanup_status=CleanupStatus.PENDING,
        verification_verdict=VerificationVerdict.INFRASTRUCTURE_FAILURE,
        start_time="2026-01-01T00:00:00Z",
        security_report=SecurityEnforcementReport(
            overall_status=SecurityEnforcementStatus.VERIFIED,
            controls=[],
            summary="Verified",
        ),
    )
    manager._active_jobs[job_id] = initial_result
    manager._active_containers[job_id] = "mock-container-abc"
    manager._active_workspaces[job_id] = f"/tmp/releaseproof-workspaces/{job_id}"

    aborted_result = await manager.abort_job(job_id)

    assert aborted_result is not None
    assert aborted_result.cleanup_status == CleanupStatus.CLEANUP_FAILED
    assert aborted_result.lifecycle_status == ExecutionLifecycleState.CLEANUP_FAILED
    assert aborted_result.error_code == "JOB_ABORTED_CLEANUP_FAILED"


@pytest.mark.asyncio
async def test_lifecycle_abort_unknown_job_returns_none():
    """Verify aborting non-existent job returns None."""
    driver = MockSandboxExecutionDriver()
    manager = SandboxLifecycleManager(driver=driver)

    res = await manager.abort_job("job-000000000000")
    assert res is None


@pytest.mark.asyncio
async def test_lifecycle_abort_invalid_job_id_shape_returns_none():
    """Verify path traversal attempt in job_id is rejected by abort validation."""
    driver = MockSandboxExecutionDriver()
    manager = SandboxLifecycleManager(driver=driver)

    assert await manager.abort_job("../../etc/passwd") is None
    assert await manager.abort_job("invalid;rm -rf /") is None
