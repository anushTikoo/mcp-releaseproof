"""API tests for Control Plane /api/sandbox endpoints."""

import pytest
from starlette.testclient import TestClient

from app.main import create_app

VALID_REQ = {
    "repository_url": "https://github.com/modelcontextprotocol/servers",
    "commit_sha": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
    "harness_code": "import pytest\ndef test_api_run(): pass\n",
    "server_entrypoint": "server.py",
    "timeout_seconds": 30,
}


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_api_get_sandbox_capabilities(client):
    """Verify capabilities endpoint reports pre-warmed dependencies and security settings."""
    res = client.get("/api/sandbox/capabilities")
    assert res.status_code == 200
    data = res.json()
    assert any("mcp" in d for d in data["prewarmed_dependencies"])
    assert data["runtime_network_mode"] == "none"
    assert data["mcp_transport"] == "stdio"
    assert any("non-root" in f for f in data["enforced_security_features"])


def test_api_execute_harness_success(client):
    """Verify POST /api/sandbox/execute dispatches and returns structured verification verdict."""
    res = client.post("/api/sandbox/execute", json=VALID_REQ)
    assert res.status_code == 200
    data = res.json()
    assert data["lifecycle_status"] == "COMPLETED"
    assert data["test_verdict"] == "PASSED"
    assert data["security_status"] == "VERIFIED"
    assert data["cleanup_status"] == "VERIFIED_CLEAN"
    assert data["verification_verdict"] == "VERIFIED_SUCCESS"

    # Verify querying status for that job_id succeeds
    job_id = data["job_id"]
    status_res = client.get(f"/api/sandbox/jobs/{job_id}")
    assert status_res.status_code == 200
    assert status_res.json()["job_id"] == job_id


def test_api_execute_harness_syntax_invalid_rejected_422(client):
    """Verify pre-flight screening rejects Python syntax errors with 422 before sandbox dispatch."""
    bad_req = dict(VALID_REQ)
    bad_req["harness_code"] = "def def syntax error !!!"
    res = client.post("/api/sandbox/execute", json=bad_req)
    assert res.status_code == 422
    assert "syntax" in res.json()["detail"].lower()


def test_api_execute_harness_oversized_payload_rejected_413(client):
    """Verify RequestBodyLimitMiddleware rejects requests exceeding 512KB with HTTP 413."""
    res = client.post(
        "/api/sandbox/execute",
        headers={"Content-Length": "600000", "Content-Type": "application/json"},
        content=b"{}",
    )
    assert res.status_code == 413
    assert "exceeds maximum allowed size" in res.json()["detail"]


def test_api_get_unknown_job_returns_404(client):
    """Verify querying non-existent job ID returns 404."""
    res = client.get("/api/sandbox/jobs/job-unknown-999")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_api_abort_job_endpoint(client):
    """Verify control plane POST /api/sandbox/jobs/{job_id}/abort operates correctly."""
    res = client.post("/api/sandbox/execute", json=VALID_REQ)
    assert res.status_code == 200
    job_id = res.json()["job_id"]

    abort_res = client.post(f"/api/sandbox/jobs/{job_id}/abort")
    assert abort_res.status_code == 200
    assert abort_res.json()["job_id"] == job_id

    unknown_res = client.post("/api/sandbox/jobs/job-unknown000/abort")
    assert unknown_res.status_code == 404
