"""Unit tests for Vultr Serverless Inference client using mocked HTTP responses."""

import json
import pytest
from unittest.mock import patch, MagicMock
import httpx

from app.schemas.inference import DiscoveredToolInput, TestPlan
from app.services.vultr_client import (
    VultrAuthenticationError,
    VultrClient,
    VultrInferenceError,
    VultrModelMismatchError,
    VultrRateLimitError,
)

SAMPLE_TOOLS = [
    DiscoveredToolInput(
        tool_name="read_file",
        description="Read file contents from filesystem",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )
]

VALID_PLAN_DICT = {
    "plan_id": "plan-test-001",
    "target_server_summary": "Filesystem MCP server supporting read operations",
    "coverage_notes": "Basic reading covered; error cases planned",
    "scenarios": [
        {
            "scenario_id": "scenario-read-existing",
            "title": "Read valid local file",
            "objective": "Verify normal tool operation",
            "safety_classification": "benign_baseline",
            "steps": [
                {
                    "step_index": 1,
                    "tool_name": "read_file",
                    "arguments": {"path": "/tmp/test.txt"},
                    "expected_behavior": "Return file contents successfully",
                }
            ],
        }
    ],
}


def test_client_configuration():
    c1 = VultrClient(api_key=None)
    assert not c1.is_configured()

    c2 = VultrClient(api_key="vultr-test-key")
    assert c2.is_configured()
    assert c2._get_headers()["Authorization"] == "Bearer vultr-test-key"


@pytest.mark.asyncio
async def test_generate_test_plan_success():
    client = VultrClient(
        api_key="valid-key",
        default_model="qwen3.8-flash-next",
    )

    mock_response_payload = {
        "id": "chatcmpl-12345",
        "model": "qwen3.8-flash-next",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": json.dumps(VALID_PLAN_DICT),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 85,
            "total_tokens": 205,
        },
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_payload

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        res = await client.generate_test_plan(
            repository_url="https://github.com/example/mcp-server",
            tools=SAMPLE_TOOLS,
        )

        assert res["status"] == "success"
        assert res["model"] == "qwen3.8-flash-next"
        assert isinstance(res["plan"], TestPlan)
        assert res["plan"].plan_id == "plan-test-001"
        assert len(res["plan"].scenarios) == 1
        assert res["usage"]["total_tokens"] == 205


@pytest.mark.asyncio
async def test_generate_test_plan_strips_markdown_fences():
    client = VultrClient(
        api_key="valid-key",
        default_model="qwen3.8-flash-next",
    )

    fenced_content = f"```json\n{json.dumps(VALID_PLAN_DICT)}\n```"
    mock_response_payload = {
        "model": "qwen3.8-flash-next",
        "choices": [
            {
                "message": {"role": "assistant", "content": fenced_content},
            }
        ],
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_payload

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        res = await client.generate_test_plan(
            repository_url="https://github.com/example/mcp-server",
            tools=SAMPLE_TOOLS,
        )
        assert res["plan"].plan_id == "plan-test-001"


@pytest.mark.asyncio
async def test_model_mismatch_detection():
    """Requirement 5: treat unexpected model fallback as an error."""
    client = VultrClient(
        api_key="valid-key",
        default_model="qwen3.8-flash-next",
    )

    mock_response_payload = {
        "model": "unintended-fallback-model",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps(VALID_PLAN_DICT),
                },
            }
        ],
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_payload

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        with pytest.raises(VultrModelMismatchError) as exc_info:
            await client.generate_test_plan(
                repository_url="https://github.com/example/mcp-server",
                tools=SAMPLE_TOOLS,
            )
        assert "Silent fallback rejected" in str(exc_info.value)


@pytest.mark.asyncio
async def test_auth_error_401():
    client = VultrClient(api_key="bad-key")
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 401

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        with pytest.raises(VultrAuthenticationError):
            await client.generate_test_plan(
                repository_url="https://github.com/example/mcp-server",
                tools=SAMPLE_TOOLS,
            )


@pytest.mark.asyncio
async def test_rate_limit_error_429():
    client = VultrClient(api_key="valid-key")
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 429

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        with pytest.raises(VultrRateLimitError):
            await client.generate_test_plan(
                repository_url="https://github.com/example/mcp-server",
                tools=SAMPLE_TOOLS,
            )


@pytest.mark.asyncio
async def test_timeout_handling():
    client = VultrClient(api_key="valid-key")
    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Read timed out")):
        with pytest.raises(VultrInferenceError) as exc_info:
            await client.generate_test_plan(
                repository_url="https://github.com/example/mcp-server",
                tools=SAMPLE_TOOLS,
            )
        assert exc_info.value.status_code == 504
        assert exc_info.value.error_code == "TIMEOUT"


@pytest.mark.asyncio
async def test_malformed_json_schema_error():
    client = VultrClient(api_key="valid-key")
    mock_response_payload = {
        "model": "qwen3.8-flash-next",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": '{"invalid": "missing required scenarios"}',
                },
            }
        ],
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_payload

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        with pytest.raises(VultrInferenceError) as exc_info:
            await client.generate_test_plan(
                repository_url="https://github.com/example/mcp-server",
                tools=SAMPLE_TOOLS,
            )
        assert exc_info.value.status_code == 422
        assert exc_info.value.upstream_status == 200
        assert exc_info.value.error_code == "SCHEMA_VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_upstream_http_502_error():
    client = VultrClient(api_key="valid-key")
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 502
    mock_resp.text = '{"error": {"message": "Bad gateway upstream"}}'
    mock_resp.json.return_value = {"error": {"message": "Bad gateway upstream"}}

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        with pytest.raises(VultrInferenceError) as exc_info:
            await client.generate_test_plan(
                repository_url="https://github.com/example/mcp-server",
                tools=SAMPLE_TOOLS,
            )
        assert exc_info.value.status_code == 502
        assert exc_info.value.upstream_status == 502
        assert exc_info.value.error_code == "UPSTREAM_HTTP_ERROR"
        assert "Bad gateway upstream" in exc_info.value.message


@pytest.mark.asyncio
async def test_empty_choices_error():
    client = VultrClient(api_key="valid-key")
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"choices": []}

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        with pytest.raises(VultrInferenceError) as exc_info:
            await client.generate_test_plan(
                repository_url="https://github.com/example/mcp-server",
                tools=SAMPLE_TOOLS,
            )
        assert exc_info.value.upstream_status == 200
        assert exc_info.value.error_code == "EMPTY_CHOICES"


@pytest.mark.asyncio
async def test_empty_content_error():
    client = VultrClient(api_key="valid-key")
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "model": "qwen3.8-flash-next",
        "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
    }

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        with pytest.raises(VultrInferenceError) as exc_info:
            await client.generate_test_plan(
                repository_url="https://github.com/example/mcp-server",
                tools=SAMPLE_TOOLS,
            )
        assert exc_info.value.upstream_status == 200
        assert exc_info.value.error_code == "EMPTY_CONTENT"


@pytest.mark.asyncio
async def test_reasoning_without_content_error():
    client = VultrClient(api_key="valid-key")
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "model": "qwen3.8-flash-next",
        "choices": [
            {
                "message": {
                    "content": "",
                    "reasoning_content": "Let me think about this MCP server tool schema...",
                },
                "finish_reason": "stop",
            }
        ],
    }

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        with pytest.raises(VultrInferenceError) as exc_info:
            await client.generate_test_plan(
                repository_url="https://github.com/example/mcp-server",
                tools=SAMPLE_TOOLS,
            )
        assert exc_info.value.upstream_status == 200
        assert exc_info.value.error_code == "REASONING_WITHOUT_CONTENT"


@pytest.mark.asyncio
async def test_token_limit_exceeded_during_reasoning():
    client = VultrClient(api_key="valid-key")
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "model": "qwen3.8-flash-next",
        "choices": [
            {
                "message": {
                    "content": "",
                    "reasoning_content": "Reasoning tokens took up all token budget...",
                },
                "finish_reason": "length",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 500, "total_tokens": 600},
    }

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        with pytest.raises(VultrInferenceError) as exc_info:
            await client.generate_test_plan(
                repository_url="https://github.com/example/mcp-server",
                tools=SAMPLE_TOOLS,
            )
        assert exc_info.value.upstream_status == 200
        assert exc_info.value.status_code == 422
        assert exc_info.value.error_code == "TOKEN_LIMIT_EXCEEDED"
        assert exc_info.value.details["finish_reason"] == "length"
        assert exc_info.value.details["usage"]["completion_tokens"] == 500


@pytest.mark.asyncio
async def test_token_limit_exceeded_with_partial_content():
    """Verify that finish_reason='length' with partial JSON raises TOKEN_LIMIT_EXCEEDED gracefully."""
    client = VultrClient(api_key="valid-key", default_max_tokens=2500)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "model": "qwen3.8-flash-next",
        "choices": [
            {
                "message": {
                    "content": '{"plan_id": "truncated-plan", "scenarios": [{"scenario_id": "sc1", "steps": [{"step_index": 1, "tool_name": "read_file", "arguments": {"path": "/tmp/partial',
                    "reasoning_content": "Planning the test...",
                },
                "finish_reason": "length",
            }
        ],
        "usage": {"prompt_tokens": 300, "completion_tokens": 1200, "total_tokens": 1500},
    }

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        with pytest.raises(VultrInferenceError) as exc_info:
            await client.generate_test_plan(
                repository_url="https://github.com/example/mcp-server",
                tools=SAMPLE_TOOLS,
            )
        assert exc_info.value.upstream_status == 200
        assert exc_info.value.status_code == 422
        assert exc_info.value.error_code == "TOKEN_LIMIT_EXCEEDED"
        assert "truncated" in exc_info.value.message.lower()
        assert exc_info.value.details["finish_reason"] == "length"
        assert exc_info.value.details["raw_content"] is not None


@pytest.mark.asyncio
async def test_compact_test_plan_success_max_bounds():
    """Verify that a compact test plan with exactly 3 scenarios and 2 steps each succeeds."""
    client = VultrClient(api_key="valid-key")
    compact_plan = {
        "plan_id": "compact-plan-001",
        "target_server_summary": "Compact test summary",
        "scenarios": [
            {
                "scenario_id": f"scenario-{i}",
                "title": f"Scenario {i}",
                "objective": f"Objective {i}",
                "safety_classification": "benign_baseline",
                "steps": [
                    {
                        "step_index": j,
                        "tool_name": "read_file",
                        "arguments": {"path": f"/test{j}.txt"},
                        "expected_result": f"Step {j} succeeds",
                    }
                    for j in range(1, 3)
                ],
            }
            for i in range(1, 4)
        ],
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "model": "qwen3.8-flash-next",
        "choices": [
            {
                "message": {"content": json.dumps(compact_plan)},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 150, "completion_tokens": 200, "total_tokens": 350},
    }

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        res = await client.generate_test_plan(
            repository_url="https://github.com/example/mcp-server",
            tools=SAMPLE_TOOLS,
        )
        assert res["status"] == "success"
        plan = res["plan"]
        assert len(plan.scenarios) == 3
        for scenario in plan.scenarios:
            assert len(scenario.steps) == 2


def test_compact_schema_rejects_more_than_three_scenarios():
    """Verify that TestPlan schema validation rejects plans with > 3 scenarios."""
    from pydantic import ValidationError

    invalid_plan = {
        "plan_id": "too-many-scenarios",
        "target_server_summary": "Summary",
        "scenarios": [
            {
                "scenario_id": f"sc-{i}",
                "title": f"Title {i}",
                "objective": f"Objective {i}",
                "safety_classification": "benign_baseline",
                "steps": [
                    {
                        "step_index": 1,
                        "tool_name": "read_file",
                        "arguments": {"path": "/test.txt"},
                        "expected_result": "Success",
                    }
                ],
            }
            for i in range(4)  # 4 scenarios violates max_length=3
        ],
    }

    with pytest.raises(ValidationError) as exc_info:
        TestPlan.model_validate(invalid_plan)
    assert "scenarios" in str(exc_info.value)


def test_compact_schema_rejects_more_than_two_steps():
    """Verify that TestScenario schema validation rejects scenarios with > 2 steps."""
    from pydantic import ValidationError
    from app.schemas.inference import TestScenario

    invalid_scenario = {
        "scenario_id": "too-many-steps",
        "title": "Title",
        "objective": "Objective",
        "safety_classification": "benign_baseline",
        "steps": [
            {
                "step_index": i,
                "tool_name": "read_file",
                "arguments": {"path": f"/test{i}.txt"},
                "expected_result": f"Step {i} succeeds",
            }
            for i in range(1, 4)  # 3 steps violates max_length=2 and step_index le=2
        ],
    }

    with pytest.raises(ValidationError) as exc_info:
        TestScenario.model_validate(invalid_scenario)
    assert "steps" in str(exc_info.value) or "step_index" in str(exc_info.value)


@pytest.mark.asyncio
async def test_json_parse_failed_error():
    """Verify that invalid JSON syntax raises JSON_PARSE_FAILED with status 422."""
    client = VultrClient(api_key="valid-key")
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "model": "qwen3.8-flash-next",
        "choices": [
            {
                "message": {"content": "{ broken json without closing brace"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        with pytest.raises(VultrInferenceError) as exc_info:
            await client.generate_test_plan(
                repository_url="https://github.com/example/mcp-server",
                tools=SAMPLE_TOOLS,
            )
        assert exc_info.value.status_code == 422
        assert exc_info.value.upstream_status == 200
        assert exc_info.value.error_code == "JSON_PARSE_FAILED"


@pytest.mark.asyncio
async def test_schema_validation_failed_error():
    """Verify that valid JSON violating Pydantic schema raises SCHEMA_VALIDATION_FAILED with status 422."""
    client = VultrClient(api_key="valid-key")
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "model": "qwen3.8-flash-next",
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "plan_id": "test",
                        # Missing target_server_summary and scenarios
                    })
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        with pytest.raises(VultrInferenceError) as exc_info:
            await client.generate_test_plan(
                repository_url="https://github.com/example/mcp-server",
                tools=SAMPLE_TOOLS,
            )
        assert exc_info.value.status_code == 422
        assert exc_info.value.upstream_status == 200
        assert exc_info.value.error_code == "SCHEMA_VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_configurable_token_budget_in_request():
    """Verify that configured token budget is sent in request body."""
    client = VultrClient(api_key="valid-key", default_max_tokens=2500)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "model": "qwen3.8-flash-next",
        "choices": [
            {
                "message": {"content": json.dumps(VALID_PLAN_DICT)},
                "finish_reason": "stop",
            }
        ],
    }

    with patch("httpx.AsyncClient.post", return_value=mock_resp) as mock_post:
        await client.generate_test_plan(
            repository_url="https://github.com/example/mcp-server",
            tools=SAMPLE_TOOLS,
        )
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["max_tokens"] == 2500
        assert kwargs["json"]["reasoning_effort"] == "minimal"

    # Test custom override
    with patch("httpx.AsyncClient.post", return_value=mock_resp) as mock_post:
        await client.generate_test_plan(
            repository_url="https://github.com/example/mcp-server",
            tools=SAMPLE_TOOLS,
            max_tokens=1800,
        )
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["max_tokens"] == 1800


@pytest.mark.asyncio
async def test_missing_usage_metadata():
    client = VultrClient(api_key="valid-key")
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "model": "qwen3.8-flash-next",
        "choices": [
            {
                "message": {"content": json.dumps(VALID_PLAN_DICT)},
                "finish_reason": "stop",
            }
        ],
        # "usage" completely omitted
    }

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        res = await client.generate_test_plan(
            repository_url="https://github.com/example/mcp-server",
            tools=SAMPLE_TOOLS,
        )
        assert res["status"] == "success"
        assert res["usage"] == {}
        assert isinstance(res["plan"], TestPlan)

