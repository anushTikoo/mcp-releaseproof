"""Unit tests for DockerExecutionDriver argument generation and Mock driver."""

import pytest

from agent.driver.base import ContainerConfig
from agent.driver.docker_driver import DockerExecutionDriver
from agent.driver.mock_driver import MockSandboxExecutionDriver


def test_docker_driver_build_run_args_enforces_mandatory_isolation_flags():
    """Verify that DockerExecutionDriver builds command line args with all required isolation flags."""
    driver = DockerExecutionDriver()
    config = ContainerConfig(
        image="mcp-releaseproof-runner:latest",
        user="10001:10001",
        command=["python", "-m", "pytest", "-q", "/workspace/test_harness.py"],
        network_mode="none",
        read_only_rootfs=True,
        cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"],
        memory_limit_bytes=536870912,
        cpu_quota=100000,
        cpu_period=100000,
        pids_limit=64,
        binds={"/tmp/workspaces/job-1": "/workspace:ro"},
        tmpfs={"/tmp": "size=64m,noexec,nosuid,nodev"},
        environment={"TEST_VAR": "1"},
    )

    args = driver.build_run_args("mcp-sandbox-job-1", config)

    # 1. Non-root user
    assert "--user" in args
    user_idx = args.index("--user")
    assert args[user_idx + 1] == "10001:10001"

    # 2. Network mode none
    assert "--network" in args
    net_idx = args.index("--network")
    assert args[net_idx + 1] == "none"

    # 3. Read-only rootfs
    assert "--read-only" in args

    # 4. Capabilities dropped
    assert "--cap-drop" in args
    cap_idx = args.index("--cap-drop")
    assert args[cap_idx + 1] == "ALL"

    # 5. No new privileges
    assert "--security-opt" in args
    sec_idx = args.index("--security-opt")
    assert args[sec_idx + 1] == "no-new-privileges:true"

    # 6. Resource limits
    assert "--memory" in args
    assert "536870912" in args
    assert "--cpu-quota" in args
    assert "100000" in args
    assert "--pids-limit" in args
    assert "64" in args

    # 7. tmpfs mount
    assert "--tmpfs" in args
    tmpfs_idx = args.index("--tmpfs")
    assert args[tmpfs_idx + 1] == "/tmp:size=64m,noexec,nosuid,nodev"


def test_docker_driver_rejects_docker_socket_mount():
    """Verify that attempting to bind mount /var/run/docker.sock raises an explicit security error."""
    driver = DockerExecutionDriver()
    config = ContainerConfig(
        image="mcp-releaseproof-runner:latest",
        user="10001:10001",
        command=["python", "test.py"],
        network_mode="none",
        read_only_rootfs=True,
        cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"],
        memory_limit_bytes=536870912,
        cpu_quota=100000,
        cpu_period=100000,
        pids_limit=64,
        binds={"/var/run/docker.sock": "/var/run/docker.sock:ro"},
    )

    with pytest.raises(ValueError, match="Security violation: Docker socket cannot be mounted"):
        driver.build_run_args("mcp-sandbox-job-1", config)


@pytest.mark.asyncio
async def test_mock_driver_lifecycle_recording():
    """Verify mock driver records created, inspected, killed, and cleaned containers."""
    driver = MockSandboxExecutionDriver()
    config = ContainerConfig(
        image="runner:latest",
        user="10001:10001",
        command=["pytest"],
        network_mode="none",
        read_only_rootfs=True,
        cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"],
        memory_limit_bytes=536870912,
        cpu_quota=100000,
        cpu_period=100000,
        pids_limit=64,
    )

    cid = await driver.create_and_start_container("job-123", config)
    assert cid in driver.created_containers

    inspect = await driver.inspect_container(cid)
    assert inspect.user == "10001:10001"
    assert inspect.network_mode == "none"
    assert inspect.read_only_rootfs is True

    run_res = await driver.wait_for_completion(cid, timeout_seconds=10)
    assert run_res.exit_code == 0
    assert not run_res.timed_out

    assert await driver.kill_container(cid) is True
    assert cid in driver.killed_containers

    assert await driver.remove_container(cid) is True
    assert cid in driver.removed_containers

    assert await driver.cleanup_workspace("/tmp/test-workspace") is True
    assert "/tmp/test-workspace" in driver.cleaned_workspaces


def test_docker_driver_rejects_sensitive_host_mounts():
    """Verify that attempting to bind mount sensitive host directories raises security errors."""
    driver = DockerExecutionDriver()
    for sensitive_path in ["/etc", "/proc", "/sys", "/root", "/boot", "/dev"]:
        config = ContainerConfig(
            image="mcp-releaseproof-runner:latest",
            user="10001:10001",
            command=["python", "test.py"],
            network_mode="none",
            read_only_rootfs=True,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            memory_limit_bytes=536870912,
            cpu_quota=100000,
            cpu_period=100000,
            pids_limit=64,
            binds={sensitive_path: "/workspace:ro"},
        )
        with pytest.raises(ValueError, match="Security violation: Sensitive path"):
            driver.build_run_args("mcp-sandbox-job-test", config)


def test_docker_driver_rejects_unauthorized_image():
    """Verify that specifying an unauthorized container image raises a security error."""
    driver = DockerExecutionDriver()
    config = ContainerConfig(
        image="malicious-image:latest",
        user="10001:10001",
        command=["python", "test.py"],
        network_mode="none",
        read_only_rootfs=True,
        cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"],
        memory_limit_bytes=536870912,
        cpu_quota=100000,
        cpu_period=100000,
        pids_limit=64,
    )
    with pytest.raises(ValueError, match="Security violation: Unauthorized container image"):
        driver.build_run_args("mcp-sandbox-job-test", config)


def test_docker_driver_rejects_invalid_env_vars():
    """Verify that invalid environment variable names or null bytes are rejected."""
    driver = DockerExecutionDriver()
    config_bad_key = ContainerConfig(
        image="mcp-releaseproof-runner:latest",
        user="10001:10001",
        command=["python", "test.py"],
        network_mode="none",
        read_only_rootfs=True,
        cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"],
        memory_limit_bytes=536870912,
        cpu_quota=100000,
        cpu_period=100000,
        pids_limit=64,
        environment={"BAD KEY; rm -rf /": "value"},
    )
    with pytest.raises(ValueError, match="Security violation: Invalid environment variable name"):
        driver.build_run_args("mcp-sandbox-job-test", config_bad_key)

    config_null_byte = ContainerConfig(
        image="mcp-releaseproof-runner:latest",
        user="10001:10001",
        command=["python", "test.py"],
        network_mode="none",
        read_only_rootfs=True,
        cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"],
        memory_limit_bytes=536870912,
        cpu_quota=100000,
        cpu_period=100000,
        pids_limit=64,
        environment={"TEST_VAR": "val\x00injection"},
    )
    with pytest.raises(ValueError, match="Security violation: Environment variable value contains null byte"):
        driver.build_run_args("mcp-sandbox-job-test", config_null_byte)


def test_runner_dockerfile_and_pinned_requirements():
    """Verify that agent/Dockerfile and agent/requirements-sandbox.txt exist and are properly configured."""
    import os
    dockerfile_path = os.path.join(os.path.dirname(__file__), "../../agent/Dockerfile")
    requirements_path = os.path.join(os.path.dirname(__file__), "../../agent/requirements-sandbox.txt")

    assert os.path.isfile(dockerfile_path), "agent/Dockerfile must exist"
    assert os.path.isfile(requirements_path), "agent/requirements-sandbox.txt must exist"

    with open(dockerfile_path, "r", encoding="utf-8") as f:
        dockerfile_content = f.read()

    assert "USER 10001:10001" in dockerfile_content
    assert "requirements-sandbox.txt" in dockerfile_content
    assert "--no-cache-dir" in dockerfile_content

    with open(requirements_path, "r", encoding="utf-8") as f:
        req_lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    expected_pkgs = ["mcp", "fastmcp", "pydantic", "pytest", "pytest-asyncio", "httpx", "anyio", "typing_extensions"]
    for pkg in expected_pkgs:
        assert any(line.startswith(f"{pkg}==") for line in req_lines), f"Package {pkg} must be pinned in requirements-sandbox.txt"
