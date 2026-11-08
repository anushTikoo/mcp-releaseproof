"""Integration tests for Phase 5 test harness generation and validation API endpoints."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.harness import GeneratedHarnessPayload
from app.schemas.inference import DiscoveredToolInput, TestPlan, TestScenario, TestStep


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_generate_request_data():
    return {
        "repository_url": "https://github.com/example/filesystem-mcp-server",
        "commit_sha": "a1b2c3d4e5f67890123456789012345678901234",
        "ref": "v1.0.0",
        "server_name": "filesystem",
        "tools": [
            {
                "tool_name": "read_file",
                "description": "Read file contents",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"}
                    },
                    "required": ["path"],
                },
            }
        ],
        "test_plan": {
            "plan_id": "plan-1",
            "target_server_summary": "Filesystem server verification",
            "scenarios": [
                {
                    "scenario_id": "SCENARIO-01",
                    "title": "Read valid file",
                    "objective": "Verify file read",
                    "steps": [
                        {
                            "step_index": 1,
                            "tool_name": "read_file",
                            "arguments": {"path": "test.txt"},
                            "expected_result": "Success",
                        }
                    ],
                }
            ],
        },
    }


def test_validate_endpoint_valid_code(client):
    code = """
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_sample(session: ClientSession):
    res = await session.call_tool("read_file", {"path": "foo.txt"})
    assert res is not None
"""
    tools = [
        {
            "tool_name": "read_file",
            "description": "Read file",
            "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        }
    ]
    response = client.post(
        "/api/harness/validate",
        json={"harness_code": code, "tools": tools},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "valid"
    assert data["validation"]["is_valid"] is True
    assert data["validation"]["security_valid"] is True
    assert data["validation"]["syntax_valid"] is True


def test_validate_endpoint_rejected_code(client):
    code = """
import os
import pytest

def test_bad():
    os.system("echo bad")
"""
    response = client.post(
        "/api/harness/validate",
        json={"harness_code": code, "tools": []},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["validation"]["is_valid"] is False
    assert data["validation"]["security_valid"] is False
    assert any("Prohibited module import 'os'" in r for r in data["validation"]["rejection_reasons"])


def test_generate_endpoint_unconfigured_api_key(client, sample_generate_request_data):
    with patch("app.services.vultr_client.VultrClient.is_configured", return_value=False):
        response = client.post("/api/harness/generate", json=sample_generate_request_data)
        assert response.status_code == 400
        assert "API key is not configured" in response.json()["detail"]


def test_generate_endpoint_success(client, sample_generate_request_data):
    valid_code = """
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_read_file_scenario(session: ClientSession):
    \"\"\"SCENARIO-01: Read valid file.\"\"\"
    result = await session.call_tool("read_file", {"path": "test.txt"})
    assert result is not None
"""
    mock_payload = GeneratedHarnessPayload(
        harness_code=valid_code,
        scenarios_covered=["SCENARIO-01"],
        tools_tested=["read_file"],
        summary="Tests valid file reading capability",
    )
    mock_result = {
        "status": "success",
        "model": "qwen3.8-flash-next",
        "payload": mock_payload,
        "usage": {"total_tokens": 350},
        "duration_ms": 420.5,
        "finish_reason": "stop",
    }

    with patch("app.services.vultr_client.VultrClient.is_configured", return_value=True), \
         patch("app.services.vultr_client.VultrClient.generate_test_harness", new_callable=AsyncMock, return_value=mock_result):
        response = client.post("/api/harness/generate", json=sample_generate_request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["validation"]["is_valid"] is True
        assert data["metadata"]["test_count"] == 1
        assert "SCENARIO-01" in data["metadata"]["scenarios_covered"]
        assert "read_file" in data["metadata"]["tools_tested"]
        assert data["harness_code"] == valid_code.strip()


def test_generate_endpoint_rejected_when_llm_emits_prohibited_import(
    client, sample_generate_request_data
):
    bad_code = """
import subprocess
import pytest

@pytest.mark.asyncio
async def test_exploit():
    subprocess.run(["ls"])
"""
    mock_payload = GeneratedHarnessPayload(
        harness_code=bad_code,
        scenarios_covered=["SCENARIO-01"],
        tools_tested=["read_file"],
        summary="Unsafe exploit test",
    )
    mock_result = {
        "status": "success",
        "model": "qwen3.8-flash-next",
        "payload": mock_payload,
        "usage": {"total_tokens": 150},
        "duration_ms": 200.0,
        "finish_reason": "stop",
    }

    with patch("app.services.vultr_client.VultrClient.is_configured", return_value=True), \
         patch("app.services.vultr_client.VultrClient.generate_test_harness", new_callable=AsyncMock, return_value=mock_result):
        response = client.post("/api/harness/generate", json=sample_generate_request_data)
        assert response.status_code == 200
        data = response.json()
        # Non-modifying policy: returns original code with rejected status
        assert data["status"] == "rejected"
        assert data["validation"]["is_valid"] is False
        assert data["validation"]["security_valid"] is False
        assert any("Prohibited module import 'subprocess'" in r for r in data["validation"]["rejection_reasons"])


def test_generate_endpoint_token_limit_exceeded(client, sample_generate_request_data):
    from app.services.vultr_client import VultrInferenceError

    with patch("app.services.vultr_client.VultrClient.is_configured", return_value=True), \
         patch("app.services.vultr_client.VultrClient.generate_test_harness", new_callable=AsyncMock) as mock_gen:
        mock_gen.side_effect = VultrInferenceError(
            "Inference output was truncated because it reached maximum token budget (2500 tokens). Finish reason: length.",
            status_code=422,
            error_code="TOKEN_LIMIT_EXCEEDED",
        )
        response = client.post("/api/harness/generate", json=sample_generate_request_data)
        assert response.status_code == 422
        assert "TOKEN_LIMIT_EXCEEDED" in response.json()["detail"]


def test_generate_endpoint_invalid_commit_sha(client, sample_generate_request_data):
    bad_req = dict(sample_generate_request_data)
    bad_req["commit_sha"] = "invalid-non-hex-short-sha"
    response = client.post("/api/harness/generate", json=bad_req)
    assert response.status_code == 422


def test_generate_endpoint_invalid_repository_url(client, sample_generate_request_data):
    bad_req = dict(sample_generate_request_data)
    bad_req["repository_url"] = "http://insecure-site.com/repo"
    response = client.post("/api/harness/generate", json=bad_req)
    assert response.status_code == 422


def test_generate_endpoint_ground_truth_metadata_filters_fabrications(
    client, sample_generate_request_data
):
    code_calling_read_file = """
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_read(session: ClientSession):
    \"\"\"SCENARIO-01: Read file.\"\"\"
    await session.call_tool("read_file", {"path": "test.txt"})
"""
    # LLM payload fabricates tools and scenario IDs that do not exist or are not called
    fabricated_payload = GeneratedHarnessPayload(
        harness_code=code_calling_read_file,
        scenarios_covered=["SCENARIO-01", "FABRICATED-SCENARIO-99"],
        tools_tested=["read_file", "delete_all_files", "system_reboot"],
        summary="Fabricated claims in payload",
    )
    mock_result = {
        "status": "success",
        "model": "qwen3.8-flash-next",
        "payload": fabricated_payload,
        "usage": {"total_tokens": 120},
        "duration_ms": 150.0,
        "finish_reason": "stop",
    }

    with patch("app.services.vultr_client.VultrClient.is_configured", return_value=True), \
         patch("app.services.vultr_client.VultrClient.generate_test_harness", new_callable=AsyncMock, return_value=mock_result):
        response = client.post("/api/harness/generate", json=sample_generate_request_data)
        assert response.status_code == 200
        data = response.json()
        # Fabricated tools not called in AST are rejected from metadata
        assert "delete_all_files" not in data["metadata"]["tools_tested"]
        assert "system_reboot" not in data["metadata"]["tools_tested"]
        assert data["metadata"]["tools_tested"] == ["read_file"]
        # Fabricated scenarios not identified in test functions are rejected from metadata
        assert "FABRICATED-SCENARIO-99" not in data["metadata"]["scenarios_covered"]
        assert data["metadata"]["scenarios_covered"] == ["SCENARIO-01"]


def test_harness_endpoints_include_trust_boundary_notice(client, sample_generate_request_data):
    """Verify both generate and validate endpoints include caller-supplied trust boundary metadata."""
    # 1. Validate endpoint
    val_res = client.post(
        "/api/harness/validate",
        json={
            "harness_code": "import pytest\n\ndef test_dummy(): pass\n",
            "tools": [{"tool_name": "read_file", "description": "d", "input_schema": {}}],
        },
    )
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert val_data["inventory_origin"] == "caller_supplied_unverified"
    assert "caller without cryptographic binding" in val_data["trust_boundary_notice"]

    # 2. Generate endpoint
    mock_payload = GeneratedHarnessPayload(
        harness_code='import pytest\nfrom mcp import ClientSession\n\n@pytest.mark.asyncio\nasync def test_read(session: ClientSession):\n    """SCENARIO-01: Read."""\n    await session.call_tool("read_file", {"path": "test.txt"})\n',
        scenarios_covered=["SCENARIO-01"],
        tools_tested=["read_file"],
        summary="Test harness",
    )
    mock_result = {
        "status": "success",
        "model": "qwen3.8-flash-next",
        "payload": mock_payload,
        "usage": {"total_tokens": 100},
        "duration_ms": 120.0,
        "finish_reason": "stop",
    }
    with patch("app.services.vultr_client.VultrClient.is_configured", return_value=True), \
         patch("app.services.vultr_client.VultrClient.generate_test_harness", new_callable=AsyncMock, return_value=mock_result):
        gen_res = client.post("/api/harness/generate", json=sample_generate_request_data)
        assert gen_res.status_code == 200
        gen_data = gen_res.json()
        assert gen_data["inventory_origin"] == "caller_supplied_unverified"
        assert "caller without cryptographic binding" in gen_data["trust_boundary_notice"]


def test_validate_endpoint_rejects_oversized_payload(client):
    """Verify validate endpoint rejects request bodies with code exceeding schema max length."""
    huge_code = "# " + ("A" * 70_000)
    response = client.post("/api/harness/validate", json={"harness_code": huge_code})
    assert response.status_code == 422


def test_validate_endpoint_returns_500_with_correlation_id_on_unexpected_error(client):
    """R5: Verify validate endpoint returns HTTP 500 with correlation ID instead of leaking raw exception details."""
    with patch("app.services.harness_validator.HarnessValidator.validate", side_effect=RuntimeError("Simulated internal error")):
        response = client.post(
            "/api/harness/validate",
            json={"harness_code": "import pytest\ndef test_foo(): pass\n"},
        )
        assert response.status_code == 500
        detail = response.json()["detail"]
        assert "val-err-" in detail
        assert "Simulated internal error" not in detail


def test_validate_endpoint_rejects_oversized_inventory_with_422(client):
    """R4: Verify validate endpoint returns 422 Unprocessable Entity when tool count limit is exceeded."""
    tools = [
        {
            "tool_name": f"tool_{i}",
            "description": f"Tool {i}",
            "input_schema": {"type": "object", "properties": {"x": {"type": "string"}}},
        }
        for i in range(101)
    ]
    response = client.post(
        "/api/harness/validate",
        json={"harness_code": "import pytest\ndef test_foo(): pass\n", "tools": tools},
    )
    assert response.status_code == 422
    assert "100" in str(response.json()["detail"])

    # Test schema bytes limit (> 32 KB) caught by check_inventory_limits
    huge_tool = {
        "tool_name": "huge_tool",
        "description": "Huge",
        "input_schema": {"type": "object", "properties": {f"k_{i}": {"type": "string", "description": "a" * 200} for i in range(200)}},
    }
    res_bytes = client.post(
        "/api/harness/validate",
        json={"harness_code": "import pytest\ndef test_foo(): pass\n", "tools": [huge_tool]},
    )
    assert res_bytes.status_code == 422
    assert "exceeds maximum limit" in res_bytes.json()["detail"]


def test_generate_endpoint_rejects_oversized_inventory_with_422(client, sample_generate_request_data):
    """R4: Verify generate endpoint returns 422 Unprocessable Entity when tool count limit is exceeded."""
    tools = [
        {
            "tool_name": f"tool_{i}",
            "description": f"Tool {i}",
            "input_schema": {"type": "object", "properties": {"x": {"type": "string"}}},
        }
        for i in range(101)
    ]
    req = dict(sample_generate_request_data)
    req["tools"] = tools
    with patch("app.services.vultr_client.VultrClient.is_configured", return_value=True):
        response = client.post("/api/harness/generate", json=req)
        assert response.status_code == 422
        assert "100" in str(response.json()["detail"])

        # Test schema bytes limit (> 32 KB) caught by check_inventory_limits
        huge_tool = {
            "tool_name": "huge_tool",
            "description": "Huge",
            "input_schema": {"type": "object", "properties": {f"k_{i}": {"type": "string", "description": "a" * 200} for i in range(200)}},
        }
        req_bytes = dict(sample_generate_request_data)
        req_bytes["tools"] = [huge_tool]
        res_bytes = client.post("/api/harness/generate", json=req_bytes)
        assert res_bytes.status_code == 422
        assert "exceeds maximum limit" in res_bytes.json()["detail"]


# =========================================================================
# R4 & R5: HTTP Request Body Limits (413) & Safe Error Handling (500) Tests
# =========================================================================


def test_r4_validate_endpoint_rejects_oversized_content_length_with_413(client):
    """R4: Validate endpoint rejects requests whose Content-Length header exceeds 512 KB with HTTP 413."""
    response = client.post(
        "/api/harness/validate",
        headers={"Content-Length": "600000", "Content-Type": "application/json"},
        content=b"{}",
    )
    assert response.status_code == 413
    assert "exceeds maximum allowed size" in response.json()["detail"]


def test_r4_generate_endpoint_rejects_oversized_content_length_with_413(client):
    """R4: Generate endpoint rejects requests whose Content-Length header exceeds 512 KB with HTTP 413."""
    response = client.post(
        "/api/harness/generate",
        headers={"Content-Length": "600000", "Content-Type": "application/json"},
        content=b"{}",
    )
    assert response.status_code == 413
    assert "exceeds maximum allowed size" in response.json()["detail"]


def test_r4_validate_endpoint_rejects_oversized_streaming_body_with_413(client):
    """R4: Validate endpoint rejects chunked/streamed body exceeding 512 KB with HTTP 413."""
    class LargeStream:
        def __iter__(self):
            # Send 6 chunks of 100 KB = 600 KB total (> 512 KB)
            for _ in range(6):
                yield b" " * 102_400

    response = client.post(
        "/api/harness/validate",
        headers={"Content-Type": "application/json"},
        content=LargeStream(),
    )
    assert response.status_code == 413
    assert "exceeded maximum allowed size" in response.json()["detail"]


def test_r4_generate_endpoint_rejects_oversized_streaming_body_with_413(client):
    """R4: Generate endpoint rejects chunked/streamed body exceeding 512 KB with HTTP 413."""
    class LargeStream:
        def __iter__(self):
            for _ in range(6):
                yield b" " * 102_400

    response = client.post(
        "/api/harness/generate",
        headers={"Content-Type": "application/json"},
        content=LargeStream(),
    )
    assert response.status_code == 413
    assert "exceeded maximum allowed size" in response.json()["detail"]


def test_r5_validate_endpoint_logs_correlation_id_and_details_server_side(client, caplog):
    """R5: Unexpected internal exception returns HTTP 500, logs correlation ID and details server-side, no leak to client."""
    import logging
    with patch("app.services.harness_validator.HarnessValidator.validate", side_effect=RuntimeError("Internal AST crash")):
        with caplog.at_level(logging.ERROR):
            response = client.post(
                "/api/harness/validate",
                json={"harness_code": "import pytest\ndef test_ok(): pass\n"},
            )
            assert response.status_code == 500
            detail = response.json()["detail"]
            assert "val-err-" in detail
            assert "Internal AST crash" not in detail
            # Verify server log contains correlation ID and exception details
            assert "val-err-" in caplog.text
            assert "Internal AST crash" in caplog.text


def test_r5_generate_endpoint_returns_500_with_correlation_id_on_unexpected_error(
    client, sample_generate_request_data, caplog
):
    """R5: Unexpected internal exception in generate endpoint returns HTTP 500 with gen-err- correlation ID."""
    import logging
    with patch("app.services.vultr_client.VultrClient.is_configured", return_value=True), \
         patch("app.services.harness_generator.HarnessGenerator.generate_harness", side_effect=RuntimeError("Unforeseen pipeline failure")):
        with caplog.at_level(logging.ERROR):
            response = client.post("/api/harness/generate", json=sample_generate_request_data)
            assert response.status_code == 500
            detail = response.json()["detail"]
            assert "gen-err-" in detail
            assert "Unforeseen pipeline failure" not in detail
            assert "gen-err-" in caplog.text
            assert "Unforeseen pipeline failure" in caplog.text


def test_r5_expected_validation_failure_returns_200_not_500(client):
    """R5: Expected validation failure (security violation or syntax error) returns HTTP 200 with status='rejected', not 500."""
    response = client.post(
        "/api/harness/validate",
        json={"harness_code": "import os\n\ndef test_bad(): os.system('ls')\n"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["validation"]["is_valid"] is False
    assert data["validation"]["security_valid"] is False
    assert any("os" in r for r in data["validation"]["rejection_reasons"])



