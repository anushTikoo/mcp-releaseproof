"""API integration tests for inference endpoints using FastAPI TestClient."""

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch

from app.main import create_app
from app.schemas.inference import TestPlan
from app.services.vultr_client import (
    VultrAuthenticationError,
    VultrModelMismatchError,
    VultrRateLimitError,
)

SAMPLE_REQUEST = {
    "repository_url": "https://github.com/example/mcp-server",
    "tools": [
        {
            "tool_name": "query_db",
            "description": "Execute database read query",
            "input_schema": {
                "type": "object",
                "properties": {"sql": {"type": "string"}},
            },
        }
    ],
}

MOCK_PLAN = TestPlan(
    plan_id="plan-api-123",
    target_server_summary="DB query MCP server",
    coverage_notes="Tests basic SELECT query",
    scenarios=[
        {
            "scenario_id": "scenario-basic-query",
            "title": "Execute basic select",
            "objective": "Verify normal DB query execution",
            "safety_classification": "benign_baseline",
            "steps": [
                {
                    "step_index": 1,
                    "tool_name": "query_db",
                    "arguments": {"sql": "SELECT 1;"},
                    "expected_behavior": "Return rows",
                }
            ],
        }
    ],
)


@pytest.mark.asyncio
async def test_get_inference_status_unconfigured():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.config.Settings.safe_dict"):
            resp = await client.get("/api/inference/status")
            assert resp.status_code == 200
            data = resp.json()
            assert "api_key_configured" in data
            assert "benchmark_models" in data
            assert "qwen3.8-flash-next" in data["benchmark_models"]


@pytest.mark.asyncio
async def test_generate_plan_fails_when_unconfigured():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.services.vultr_client.VultrClient.is_configured", return_value=False):
            resp = await client.post("/api/inference/generate-plan", json=SAMPLE_REQUEST)
            assert resp.status_code == 400
            assert "Vultr Inference API key is not configured" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_generate_plan_success():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        mock_result = {
            "status": "success",
            "model": "qwen3.8-flash-next",
            "plan": MOCK_PLAN,
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 80,
                "total_tokens": 200,
                "prompt_tokens_details": {"cached_tokens": 0},
                "completion_tokens_details": {"reasoning_tokens": 144},
            },
            "duration_ms": 350.5,
        }
        with patch("app.services.vultr_client.VultrClient.is_configured", return_value=True), \
             patch("app.services.vultr_client.VultrClient.generate_test_plan", return_value=mock_result):
            resp = await client.post("/api/inference/generate-plan", json=SAMPLE_REQUEST)
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert data["model"] == "qwen3.8-flash-next"
            assert data["plan"]["plan_id"] == "plan-api-123"
            assert len(data["plan"]["scenarios"]) == 1


@pytest.mark.asyncio
async def test_generate_plan_auth_error_handling():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.services.vultr_client.VultrClient.is_configured", return_value=True), \
             patch("app.services.vultr_client.VultrClient.generate_test_plan", side_effect=VultrAuthenticationError()):
            resp = await client.post("/api/inference/generate-plan", json=SAMPLE_REQUEST)
            assert resp.status_code == 401
            assert "authentication failed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_generate_plan_rate_limit_handling():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.services.vultr_client.VultrClient.is_configured", return_value=True), \
             patch("app.services.vultr_client.VultrClient.generate_test_plan", side_effect=VultrRateLimitError()):
            resp = await client.post("/api/inference/generate-plan", json=SAMPLE_REQUEST)
            assert resp.status_code == 429
            assert "rate limit reached" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_generate_plan_model_mismatch_handling():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.services.vultr_client.VultrClient.is_configured", return_value=True), \
             patch("app.services.vultr_client.VultrClient.generate_test_plan", side_effect=VultrModelMismatchError("qwen3.8-flash-next", "wrong-model")):
            resp = await client.post("/api/inference/generate-plan", json=SAMPLE_REQUEST)
            assert resp.status_code == 502
            assert "Model mismatch" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_generate_plan_truncated_output_handling():
    from app.services.vultr_client import VultrInferenceError

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        trunc_err = VultrInferenceError(
            "Inference output was truncated because it reached the maximum token budget (2500 tokens). Finish reason: length.",
            status_code=422,
            upstream_status=200,
            error_code="TOKEN_LIMIT_EXCEEDED",
        )
        with patch("app.services.vultr_client.VultrClient.is_configured", return_value=True), \
             patch("app.services.vultr_client.VultrClient.generate_test_plan", side_effect=trunc_err):
            resp = await client.post("/api/inference/generate-plan", json=SAMPLE_REQUEST)
            assert resp.status_code == 422
            data = resp.json()["detail"]
            assert data["code"] == "TOKEN_LIMIT_EXCEEDED"
            assert "truncated" in data["message"].lower()

