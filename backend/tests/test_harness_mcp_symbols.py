"""Regression tests verifying MCP symbol correctness, ToolErrorResult removal, and the hard execution gate."""

# Pydantic 2.14 compatibility shim for mcp==1.2.1 package imports
try:
    import pydantic._internal._typing_extra as _te
    if not hasattr(_te, "eval_type_backport"):
        _te.eval_type_backport = getattr(_te, "eval_type_lenient", lambda val, *args, **kwargs: val)
except Exception:
    pass

import ast
import importlib
from unittest.mock import AsyncMock, patch
import pytest
from starlette.testclient import TestClient

from agent.driver.mock_driver import MockSandboxExecutionDriver
from agent.manager import SandboxLifecycleManager
from app.config import get_settings
from app.main import create_app
from app.schemas.harness import GenerateHarnessRequest, GeneratedHarnessPayload
from app.schemas.inference import DiscoveredToolInput, TestPlan, TestScenario, TestStep
from app.schemas.sandbox import ExecutionLifecycleState, SandboxExecutionRequest, VerificationVerdict
from app.services.harness_generator import HarnessGenerator, sanitize_mcp_harness_types
from app.services.harness_validator import HarnessValidator
from app.services.sandbox_service import SandboxService
from app.services.vultr_client import VultrClient

SAMPLE_TOOLS = [
    DiscoveredToolInput(
        tool_name="read_file",
        description="Read file contents.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )
]

SAMPLE_PLAN = TestPlan(
    plan_id="plan-1",
    target_server_summary="File server testing",
    scenarios=[
        TestScenario(
            scenario_id="SCENARIO-01",
            title="Read File Valid",
            objective="Read file from valid path",
            steps=[
                TestStep(
                    step_index=1,
                    tool_name="read_file",
                    arguments={"path": "test.txt"},
                    expected_result="file contents",
                )
            ],
        )
    ]
)


def test_sanitize_mcp_harness_types_removes_tool_error_result():
    """Verify ToolErrorResult is replaced with CallToolResult, TextContent, and isError."""
    code_with_tool_error = """import pytest
from mcp.types import CallToolResult, ToolErrorResult

@pytest.mark.asyncio
async def test_tool_failure(session):
    result = await session.call_tool("read_file", {"path": "/nonexistent"})
    assert isinstance(result, ToolErrorResult)
"""
    sanitized = sanitize_mcp_harness_types(code_with_tool_error)

    assert "ToolErrorResult" not in sanitized
    assert "from mcp.types import CallToolResult, TextContent" in sanitized
    assert "assert result.isError is True" in sanitized

    # Verify AST parses cleanly
    tree = ast.parse(sanitized)
    assert tree is not None


def test_sanitize_mcp_harness_types_bare_import():
    """Verify ToolErrorResult import alone gets transformed to CallToolResult, TextContent."""
    code = """import pytest
from mcp.types import ToolErrorResult

@pytest.mark.asyncio
async def test_err(session):
    res: ToolErrorResult = await session.call_tool("read_file", {"path": ""})
    assert not isinstance(res, ToolErrorResult)
"""
    sanitized = sanitize_mcp_harness_types(code)
    assert "ToolErrorResult" not in sanitized
    assert "from mcp.types import CallToolResult, TextContent" in sanitized
    assert "res: CallToolResult" in sanitized
    assert "assert not res.isError" in sanitized


@pytest.mark.asyncio
async def test_generate_harness_all_imported_mcp_symbols_exist_in_mcp_package():
    """Verify all imported symbols in a generated harness exist in the pinned mcp==1.2.1 package."""
    mock_llm_code = """import pytest
from mcp.types import CallToolResult, ToolErrorResult, TextContent

@pytest.mark.scenario("SCENARIO-01")
@pytest.mark.asyncio
async def test_scenario_01_read(session):
    res = await session.call_tool("read_file", {"path": "test.txt"})
    if isinstance(res, ToolErrorResult):
        assert res.isError is True
    else:
        assert not res.isError
"""
    mock_payload = GeneratedHarnessPayload(
        harness_code=mock_llm_code,
        summary="Test harness reading a file",
    )
    mock_inference_result = {
        "payload": mock_payload,
        "model": "qwen3.8-flash-next",
        "duration_ms": 250.0,
        "usage": {"total_tokens": 120},
    }

    mock_vultr = AsyncMock(spec=VultrClient)
    mock_vultr.generate_test_harness.return_value = mock_inference_result
    mock_vultr.default_model = "qwen3.8-flash-next"

    generator = HarnessGenerator(vultr_client=mock_vultr)
    req = GenerateHarnessRequest(
        repository_url="https://github.com/modelcontextprotocol/servers",
        commit_sha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        tools=SAMPLE_TOOLS,
        test_plan=SAMPLE_PLAN,
    )

    resp = await generator.generate_harness(req)

    # 1. ToolErrorResult must not be in the output code
    assert "ToolErrorResult" not in resp.harness_code
    assert "from mcp.types import CallToolResult, TextContent" in resp.harness_code

    # 2. Parse AST and verify every imported symbol from mcp* modules exists in the real mcp package
    tree = ast.parse(resp.harness_code)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("mcp"):
            # Import the module from the environment
            mod = importlib.import_module(node.module)
            for alias in node.names:
                sym_name = alias.name
                assert sym_name != "ToolErrorResult", f"ToolErrorResult must not be imported from {node.module}"
                assert hasattr(mod, sym_name), f"Imported symbol '{sym_name}' does not exist in {node.module} (mcp==1.2.1)"


def test_validator_rejects_tool_error_result():
    """Verify HarnessValidator rejects any attempt to import or reference ToolErrorResult."""
    validator = HarnessValidator()

    code_import = """import pytest
from mcp.types import ToolErrorResult

@pytest.mark.asyncio
async def test_fn(session):
    pass
"""
    res1 = validator.validate(code_import, tools=SAMPLE_TOOLS)
    assert res1.is_valid is False
    assert res1.security_valid is False
    assert any("ToolErrorResult" in r for r in res1.rejection_reasons)

    code_bare_name = """import pytest

@pytest.mark.asyncio
async def test_fn(session):
    x = ToolErrorResult
"""
    res2 = validator.validate(code_bare_name, tools=SAMPLE_TOOLS)
    assert res2.is_valid is False
    assert res2.security_valid is False
    assert any("ToolErrorResult" in r for r in res2.rejection_reasons)


def test_hard_execution_gate_blocks_rejected_harness_in_api():
    """Verify POST /api/sandbox/execute blocks static-verdict REJECTED harnesses with HTTP 422."""
    app = create_app()
    with TestClient(app) as client:
        # 1. Security violation: import os
        bad_req = {
            "repository_url": "https://github.com/modelcontextprotocol/servers",
            "commit_sha": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "harness_code": "import os\ndef test_bad(): os.system('ls')\n",
        }
        res = client.post("/api/sandbox/execute", json=bad_req)
        assert res.status_code == 422
        assert "Execution gate rejected" in res.json()["detail"]

        # 2. Syntax error
        syntax_err_req = {
            "repository_url": "https://github.com/modelcontextprotocol/servers",
            "commit_sha": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "harness_code": "def def bad syntax : : :",
        }
        res2 = client.post("/api/sandbox/execute", json=syntax_err_req)
        assert res2.status_code == 422
        assert "Execution gate rejected" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_hard_execution_gate_blocks_rejected_harness_in_service():
    """Verify SandboxService.execute_harness raises ValueError on a statically rejected harness."""
    service = SandboxService()
    req = SandboxExecutionRequest(
        repository_url="https://github.com/modelcontextprotocol/servers",
        commit_sha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        harness_code="import socket\ndef test_net(): socket.socket()\n",
    )
    with pytest.raises(ValueError, match="Execution gate rejected"):
        await service.execute_harness(req)


@pytest.mark.asyncio
async def test_hard_execution_gate_blocks_rejected_harness_in_agent_manager():
    """Verify SandboxLifecycleManager.execute_job fails immediately on a statically rejected harness."""
    driver = MockSandboxExecutionDriver()
    manager = SandboxLifecycleManager(driver=driver)

    req = SandboxExecutionRequest(
        repository_url="https://github.com/modelcontextprotocol/servers",
        commit_sha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        harness_code="import os\ndef test_bad(): os.system('id')\n",
    )
    result = await manager.execute_job(req)

    assert result.lifecycle_status == ExecutionLifecycleState.FAILED
    assert result.error_code == "STATIC_VALIDATION_REJECTED"
    assert result.verification_verdict == VerificationVerdict.SECURITY_VIOLATION
    # Verify no container was created
    assert len(driver.created_containers) == 0


def test_pytest_runner_command_includes_no_cacheprovider():
    """Verify runner command disables pytest cache provider to avoid warnings on read-only /workspace."""
    driver = MockSandboxExecutionDriver()
    manager = SandboxLifecycleManager(driver=driver)

    # Inspect runner command in manager.execute_job via driver last_config
    import inspect
    source = inspect.getsource(manager.execute_job)
    assert "-p" in source
    assert "no:cacheprovider" in source
