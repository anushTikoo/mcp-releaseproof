"""Unit and integration tests for Sandbox Execution Agent standalone FastAPI service."""

import pytest
from starlette.testclient import TestClient

from agent.auth import sign_request
from agent.config import get_agent_settings
from agent.driver.mock_driver import MockSandboxExecutionDriver
from agent.main import create_agent_app, set_driver

SECRET = "agent-test-secret-12345"


@pytest.fixture
def agent_client():
    settings = get_agent_settings()
    settings.WORKER_SHARED_SECRET = SECRET
    mock_driver = MockSandboxExecutionDriver()
    set_driver(mock_driver)
    app = create_agent_app()
    with TestClient(app) as client:
        yield client


def test_agent_health_unauthenticated(agent_client):
    """Verify health probe is accessible without authentication."""
    res = agent_client.get("/agent/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "mcp-sandbox-agent"


def test_agent_capabilities_unauthenticated(agent_client):
    """Verify capabilities endpoint reports limits and features without auth."""
    res = agent_client.get("/agent/capabilities")
    assert res.status_code == 200
    data = res.json()
    assert any("mcp" in d for d in data["prewarmed_dependencies"])
    assert data["runtime_network_mode"] == "none"


def test_agent_submit_job_without_auth_rejected_401(agent_client):
    """Verify submitting job without HMAC headers returns 401 Unauthorized."""
    res = agent_client.post("/agent/jobs/submit", json={"dummy": "value"})
    assert res.status_code == 401
    assert "Missing required authentication headers" in res.json()["detail"]


def test_agent_submit_job_with_signed_hmac_success(agent_client):
    """Verify submitting job with valid HMAC signature succeeds and executes via manager."""
    payload = {
        "repository_url": "https://github.com/modelcontextprotocol/servers",
        "commit_sha": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        "harness_code": "import pytest\ndef test_agent_call(): pass\n",
        "server_entrypoint": "server.py",
        "timeout_seconds": 30,
    }
    import json
    body_bytes = json.dumps(payload).encode("utf-8")
    headers, _ = sign_request(
        secret=SECRET,
        method="POST",
        path="/agent/jobs/submit",
        body=body_bytes,
    )
    headers["Content-Type"] = "application/json"

    res = agent_client.post("/agent/jobs/submit", content=body_bytes, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["lifecycle_status"] == "COMPLETED"
    assert data["test_verdict"] == "PASSED"
    assert data["verification_verdict"] == "VERIFIED_SUCCESS"

    # Query status with GET
    job_id = data["job_id"]
    get_path = f"/agent/jobs/{job_id}/status"
    get_headers, _ = sign_request(secret=SECRET, method="GET", path=get_path, body=b"")
    get_res = agent_client.get(get_path, headers=get_headers)
    assert get_res.status_code == 200
    assert get_res.json()["job_id"] == job_id


def test_agent_abort_unauthenticated_rejected_401(agent_client):
    """Verify aborting without HMAC headers returns 401."""
    res = agent_client.post("/agent/jobs/job-1234567890ab/abort")
    assert res.status_code == 401


def test_agent_abort_unknown_job_returns_404(agent_client):
    """Verify aborting an unknown job returns 404."""
    path = "/agent/jobs/job-unknown12345/abort"
    headers, _ = sign_request(secret=SECRET, method="POST", path=path, body=b"")
    res = agent_client.post(path, headers=headers)
    assert res.status_code == 404


def test_agent_abort_active_job_and_repeated_abort(agent_client):
    """Verify aborting job cleans up, and repeated abort is idempotent."""
    payload = {
        "repository_url": "https://github.com/modelcontextprotocol/servers",
        "commit_sha": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        "harness_code": "import pytest\ndef test_agent_abort(): pass\n",
        "server_entrypoint": "server.py",
        "timeout_seconds": 30,
    }
    import json
    body_bytes = json.dumps(payload).encode("utf-8")
    submit_headers, _ = sign_request(secret=SECRET, method="POST", path="/agent/jobs/submit", body=body_bytes)
    submit_headers["Content-Type"] = "application/json"
    submit_res = agent_client.post("/agent/jobs/submit", content=body_bytes, headers=submit_headers)
    assert submit_res.status_code == 200
    job_id = submit_res.json()["job_id"]

    abort_path = f"/agent/jobs/{job_id}/abort"
    abort_headers, _ = sign_request(secret=SECRET, method="POST", path=abort_path, body=b"")
    abort_res = agent_client.post(abort_path, headers=abort_headers)
    assert abort_res.status_code == 200
    assert abort_res.json()["job_id"] == job_id

    # Repeated abort on same job is also idempotent 200
    abort_headers2, _ = sign_request(secret=SECRET, method="POST", path=abort_path, body=b"")
    abort_res2 = agent_client.post(abort_path, headers=abort_headers2)
    assert abort_res2.status_code == 200
    assert abort_res2.json()["job_id"] == job_id
