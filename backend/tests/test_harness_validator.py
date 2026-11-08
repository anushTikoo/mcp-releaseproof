"""Unit tests for Phase 5 static AST security and structural validator."""

import pytest

from app.schemas.harness import HarnessValidationResult
from app.schemas.inference import DiscoveredToolInput, TestPlan, TestScenario, TestStep
from app.services.harness_validator import HarnessValidator


@pytest.fixture
def sample_tools() -> list[DiscoveredToolInput]:
    return [
        DiscoveredToolInput(
            tool_name="read_file",
            description="Read file contents from allowed path",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Target relative file path"}
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        ),
        DiscoveredToolInput(
            tool_name="list_files",
            description="List files in a directory",
            input_schema={
                "type": "object",
                "properties": {
                    "directory": {"type": "string"}
                },
                "required": [],
            },
        ),
    ]


@pytest.fixture
def sample_test_plan() -> TestPlan:
    return TestPlan(
        plan_id="plan-1",
        target_server_summary="Filesystem test plan",
        scenarios=[
            TestScenario(
                scenario_id="SCENARIO-01",
                title="Read existing file",
                objective="Verify file read",
                steps=[
                    TestStep(
                        step_index=1,
                        tool_name="read_file",
                        arguments={"path": "README.md"},
                        expected_result="File contents returned",
                    )
                ],
            )
        ],
    )


VALID_HARNESS = """
import pytest
import asyncio
from typing import Any, Dict
from mcp import ClientSession

@pytest.mark.asyncio
async def test_read_file_success(session: ClientSession):
    \"\"\"SCENARIO-01: Verify file read capability.\"\"\"
    result = await session.call_tool("read_file", {"path": "README.md"})
    assert result is not None
    assert not result.is_error

@pytest.mark.asyncio
async def test_list_files(session: ClientSession):
    result = await session.call_tool("list_files", {"directory": "."})
    assert result is not None
"""


def test_validator_valid_harness(sample_tools, sample_test_plan):
    validator = HarnessValidator()
    res = validator.validate(VALID_HARNESS, tools=sample_tools, test_plan=sample_test_plan)

    assert res.is_valid is True
    assert res.syntax_valid is True
    assert res.security_valid is True
    assert res.structure_valid is True
    assert res.schema_valid is True
    assert len(res.rejection_reasons) == 0
    assert "read_file" in res.identified_tool_calls
    assert "list_files" in res.identified_tool_calls
    assert "pytest" in res.identified_imports
    assert res.ast_node_count > 0
    assert res.line_count > 0


def test_validator_empty_code():
    validator = HarnessValidator()
    res = validator.validate("   \n\t  ")

    assert res.is_valid is False
    assert res.syntax_valid is False
    assert "Empty or whitespace-only" in res.rejection_reasons[0]


def test_validator_syntax_error():
    validator = HarnessValidator()
    bad_code = "def test_broken(:\n    pass"
    res = validator.validate(bad_code)

    assert res.is_valid is False
    assert res.syntax_valid is False
    assert any("Syntax error" in r for r in res.rejection_reasons)


@pytest.mark.parametrize(
    "bad_import,expected_mod",
    [
        ("import os", "os"),
        ("import sys", "sys"),
        ("import subprocess", "subprocess"),
        ("import socket", "socket"),
        ("import requests", "requests"),
        ("import urllib.request", "urllib.request"),
        ("import pathlib", "pathlib"),
        ("from os import environ", "os"),
        ("from subprocess import Popen", "subprocess"),
        ("from pathlib import Path", "pathlib"),
    ],
)
def test_validator_prohibited_imports(bad_import, expected_mod, sample_tools):
    validator = HarnessValidator()
    code = f"""
{bad_import}
import pytest

@pytest.mark.asyncio
async def test_something():
    assert True
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any(f"Prohibited module import '{expected_mod}'" in r for r in res.rejection_reasons)


def test_validator_relative_import():
    validator = HarnessValidator()
    code = """
from .local_module import something
import pytest

def test_fn():
    pass
"""
    res = validator.validate(code)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("Prohibited relative import" in r for r in res.rejection_reasons)


@pytest.mark.parametrize(
    "dangerous_call",
    [
        "eval('2 + 2')",
        "exec('import os')",
        "compile('x = 1', '<string>', 'exec')",
        "open('some_file.txt', 'r')",
        "__import__('os')",
        "getattr(object, 'attr')",
        "breakpoint()",
    ],
)
def test_validator_prohibited_calls(dangerous_call, sample_tools):
    validator = HarnessValidator()
    code = f"""
import pytest

@pytest.mark.asyncio
async def test_exploit():
    {dangerous_call}
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("Prohibited dangerous function call" in r for r in res.rejection_reasons)


@pytest.mark.parametrize(
    "prohibited_attr",
    [
        "obj.__builtins__",
        "cls.__subclasses__()",
        "fn.__globals__",
        "fn.__code__",
        "target.environ",
    ],
)
def test_validator_prohibited_attributes(prohibited_attr):
    validator = HarnessValidator()
    code = f"""
import pytest

def test_attr():
    val = {prohibited_attr}
"""
    res = validator.validate(code)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("Prohibited attribute" in r or "Prohibited callable attribute" in r or "reflection escape" in r for r in res.rejection_reasons)


def test_validator_missing_test_functions():
    validator = HarnessValidator()
    code = """
import pytest

def helper_function():
    return 42
"""
    res = validator.validate(code)
    assert res.is_valid is False
    assert res.structure_valid is False
    assert any("No test functions found" in r for r in res.rejection_reasons)


def test_validator_unknown_tool_call(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_unknown(session: ClientSession):
    await session.call_tool("delete_system_database", {"id": 123})
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.schema_valid is False
    assert any("Referenced unknown MCP tool 'delete_system_database'" in r for r in res.rejection_reasons)


def test_validator_tool_schema_missing_required_property(sample_tools):
    validator = HarnessValidator()
    # read_file requires 'path'
    code = """
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_schema_violation(session: ClientSession):
    await session.call_tool("read_file", {})
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.schema_valid is False
    assert any("missing required argument 'path'" in r for r in res.rejection_reasons)


def test_validator_tool_schema_additional_properties_false(sample_tools):
    validator = HarnessValidator()
    # read_file has additionalProperties: False, passing 'extra_field'
    code = """
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_extra_property(session: ClientSession):
    await session.call_tool("read_file", {"path": "safe.txt", "extra_field": "malicious"})
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.schema_valid is False
    assert any("specifies undeclared arguments" in r for r in res.rejection_reasons)


def test_validator_line_limit():
    validator = HarnessValidator(max_lines=10)
    lines = ["import pytest\n"] + [f"# line {i}\n" for i in range(15)] + [
        "def test_ok():\n    pass\n"
    ]
    code = "".join(lines)
    res = validator.validate(code)
    assert res.is_valid is False
    assert any("exceeds maximum source line limit" in r for r in res.rejection_reasons)


def test_validator_ast_node_limit():
    validator = HarnessValidator(max_ast_nodes=15)
    code = """
import pytest

def test_long():
    a = 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8 + 9 + 10
    b = a * 2 * 3 * 4 * 5
    assert a != b
"""
    res = validator.validate(code)
    assert res.is_valid is False
    assert any("exceeds AST complexity limit" in r for r in res.rejection_reasons)


# --- Regression Tests for Security & Schema Review Findings ---


@pytest.mark.parametrize(
    "prohibited_ident",
    [
        "open",
        "eval",
        "exec",
        "compile",
        "__import__",
        "__builtins__",
        "globals",
        "locals",
        "breakpoint",
    ],
)
def test_validator_bare_prohibited_identifiers_and_aliasing(prohibited_ident, sample_tools):
    validator = HarnessValidator()
    code = f"""
import pytest
from mcp import ClientSession

alias_var = {prohibited_ident}

@pytest.mark.asyncio
async def test_poc(session: ClientSession):
    \"\"\"SCENARIO-01: Exploit attempt.\"\"\"
    assert alias_var is not None
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any(f"Prohibited identifier reference '{prohibited_ident}'" in r for r in res.rejection_reasons)


def test_validator_prohibits_pytest_importorskip(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_importorskip(session: ClientSession):
    \"\"\"SCENARIO-01: Dynamic import attempt.\"\"\"
    os = pytest.importorskip("os")
    assert os is not None
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("Prohibited attribute or reflection escape 'importorskip'" in r or "importorskip" in r for r in res.rejection_reasons)


@pytest.mark.parametrize(
    "reflection_snippet",
    [
        "().__getattribute__('__class__')",
        "object.__dict__",
        "().__reduce__()",
        "().__reduce_ex__(2)",
        "object.__annotations__",
    ],
)
def test_validator_reflection_and_dunder_escapes(reflection_snippet, sample_tools):
    validator = HarnessValidator()
    code = f"""
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_reflection(session: ClientSession):
    \"\"\"SCENARIO-01: Reflection probe.\"\"\"
    leak = {reflection_snippet}
    assert leak is not None
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("Prohibited dunder attribute access" in r or "reflection escape" in r for r in res.rejection_reasons)


@pytest.mark.parametrize(
    "prohibited_stmt",
    [
        "while True:\n    break",
        "for i in range(10):\n    pass",
        "print('arbitrary top-level call')",
    ],
)
def test_validator_rejects_top_level_executable_statements(prohibited_stmt, sample_tools):
    validator = HarnessValidator()
    code = f"""
import pytest

{prohibited_stmt}

@pytest.mark.asyncio
async def test_sample():
    assert True
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert any("Prohibited top-level statement" in r for r in res.rejection_reasons)


def test_validator_rejects_primitive_type_mismatch(sample_tools):
    validator = HarnessValidator()
    # read_file requires 'path' as string; pass integer instead
    code = """
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_type_error(session: ClientSession):
    \"\"\"SCENARIO-01: Type violation.\"\"\"
    await session.call_tool("read_file", {"path": 12345})
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.schema_valid is False
    assert any("expected type 'string', got int" in r for r in res.rejection_reasons)


def test_validator_rejects_dynamic_arguments(sample_tools):
    validator = HarnessValidator()
    # Passing dynamic variable as arguments to call_tool
    code = """
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_dynamic_args(session: ClientSession):
    \"\"\"SCENARIO-01: Dynamic argument pass.\"\"\"
    dyn_args = {"path": "test.txt"}
    await session.call_tool("read_file", dyn_args)
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.schema_valid is False
    assert any("passes dynamic, non-literal arguments" in r for r in res.rejection_reasons)


def test_validator_nested_object_and_array_schema():
    complex_tool = DiscoveredToolInput(
        tool_name="configure_service",
        description="Configure complex service settings",
        input_schema={
            "type": "object",
            "properties": {
                "config": {
                    "type": "object",
                    "properties": {
                        "host": {"type": "string"},
                        "port": {"type": "integer"},
                    },
                    "required": ["host", "port"],
                    "additionalProperties": False,
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "mode": {
                    "type": "string",
                    "enum": ["read_only", "read_write"],
                },
            },
            "required": ["config", "mode"],
            "additionalProperties": False,
        },
    )

    validator = HarnessValidator()

    # 1. Valid nested call
    valid_code = """
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_cfg(session: ClientSession):
    await session.call_tool("configure_service", {
        "config": {"host": "localhost", "port": 8080},
        "tags": ["web", "api"],
        "mode": "read_write"
    })
"""
    res = validator.validate(valid_code, tools=[complex_tool])
    assert res.is_valid is True

    # 2. Invalid nested object missing required 'port'
    missing_nested = """
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_cfg(session: ClientSession):
    await session.call_tool("configure_service", {
        "config": {"host": "localhost"},
        "mode": "read_write"
    })
"""
    res = validator.validate(missing_nested, tools=[complex_tool])
    assert res.is_valid is False
    assert res.schema_valid is False
    assert any("missing required argument 'config.port'" in r for r in res.rejection_reasons)

    # 3. Invalid array item type (int instead of string in tags)
    bad_array_item = """
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_cfg(session: ClientSession):
    await session.call_tool("configure_service", {
        "config": {"host": "localhost", "port": 8080},
        "tags": ["valid", 999],
        "mode": "read_write"
    })
"""
    res = validator.validate(bad_array_item, tools=[complex_tool])
    assert res.is_valid is False
    assert res.schema_valid is False
    assert any("expected type 'string', got int" in r for r in res.rejection_reasons)

    # 4. Invalid enum value
    bad_enum = """
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_cfg(session: ClientSession):
    await session.call_tool("configure_service", {
        "config": {"host": "localhost", "port": 8080},
        "mode": "unauthorized_admin"
    })
"""
    res = validator.validate(bad_enum, tools=[complex_tool])
    assert res.is_valid is False
    assert res.schema_valid is False
    assert any("not in allowed enum" in r for r in res.rejection_reasons)


def test_validator_rejects_when_tool_inventory_is_empty():
    validator = HarnessValidator()
    code = """
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_call(session: ClientSession):
    await session.call_tool("read_file", {"path": "test.txt"})
"""
    # Empty tools list
    res = validator.validate(code, tools=[])
    assert res.is_valid is False
    assert res.schema_valid is False
    assert any("inventory is empty or unavailable" in r for r in res.rejection_reasons)


def test_validator_enforces_scenario_coverage(sample_tools, sample_test_plan):
    validator = HarnessValidator()

    # Harness does not implement SCENARIO-01
    code = """
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_unrelated_scenario(session: ClientSession):
    \"\"\"Unrelated test without scenario mapping.\"\"\"
    await session.call_tool("read_file", {"path": "test.txt"})
"""
    res = validator.validate(code, tools=sample_tools, test_plan=sample_test_plan)
    assert res.is_valid is False
    assert res.structure_valid is False
    assert any("does not implement any declared scenarios" in r for r in res.rejection_reasons)


# --- Security Review Regression Tests ---


def test_validator_rejects_asyncio_create_subprocess_shell(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest
import asyncio

@pytest.mark.asyncio
async def test_exploit(session):
    proc = await asyncio.create_subprocess_shell("cat /etc/passwd")
    await proc.communicate()
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("create_subprocess_shell" in r for r in res.rejection_reasons)


def test_validator_rejects_asyncio_create_subprocess_exec(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest
import asyncio

@pytest.mark.asyncio
async def test_exploit(session):
    proc = await asyncio.create_subprocess_exec("whoami")
    await proc.communicate()
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("create_subprocess_exec" in r for r in res.rejection_reasons)


def test_validator_rejects_asyncio_subprocess_module_import(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest
from asyncio.subprocess import PIPE

@pytest.mark.asyncio
async def test_exploit(session):
    pass
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("subprocess" in r for r in res.rejection_reasons)


def test_validator_rejects_asyncio_open_connection(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest
import asyncio

@pytest.mark.asyncio
async def test_network_exploit(session):
    reader, writer = await asyncio.open_connection("169.254.169.254", 80)
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("open_connection" in r for r in res.rejection_reasons)


def test_validator_rejects_asyncio_start_server(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest
import asyncio

@pytest.mark.asyncio
async def test_server_exploit(session):
    server = await asyncio.start_server(None, "127.0.0.1", 8888)
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("start_server" in r for r in res.rejection_reasons)


def test_validator_rejects_asyncio_open_unix_connection(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest
import asyncio

@pytest.mark.asyncio
async def test_unix_exploit(session):
    reader, writer = await asyncio.open_unix_connection("/var/run/docker.sock")
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("open_unix_connection" in r for r in res.rejection_reasons)


def test_validator_rejects_event_loop_create_connection(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest
import asyncio

@pytest.mark.asyncio
async def test_loop_socket(session):
    loop = asyncio.get_running_loop()
    await loop.create_connection(lambda: None, "10.0.0.1", 443)
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("create_connection" in r for r in res.rejection_reasons)


def test_validator_rejects_aliased_importorskip(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest
from pytest import importorskip as safe_load

@pytest.mark.asyncio
async def test_exploit(session):
    mod = safe_load("shutil")
    return mod
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("importorskip" in r for r in res.rejection_reasons)


def test_validator_rejects_wildcard_imports(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest
from pytest import *

@pytest.mark.asyncio
async def test_func(session):
    pass
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("Wildcard import" in r for r in res.rejection_reasons)


def test_validator_rejects_prohibited_symbol_import_with_alias(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest
from asyncio import create_subprocess_shell as my_shell

@pytest.mark.asyncio
async def test_exploit(session):
    pass
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("create_subprocess_shell" in r for r in res.rejection_reasons)


def test_validator_rejects_prohibited_alias_name(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest
from pytest import fixture as eval

@pytest.mark.asyncio
async def test_func(session):
    pass
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("Prohibited alias 'eval'" in r for r in res.rejection_reasons)


def test_validator_rejects_class_body_loops(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest

class ExploitSuite:
    for i in range(10):
        pass

    def test_pass(self):
        pass
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.structure_valid is False
    assert any("Prohibited executable statement 'For' inside class 'ExploitSuite'" in r for r in res.rejection_reasons)


def test_validator_rejects_class_body_expressions(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest

class ExploitSuite:
    print("Executing at import time")

    def test_pass(self):
        pass
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.structure_valid is False
    assert any("inside class 'ExploitSuite'" in r for r in res.rejection_reasons)


def test_validator_rejects_class_body_dynamic_assignments(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest

class ExploitSuite:
    computed = [x for x in range(5)]

    def test_pass(self):
        pass
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.structure_valid is False
    assert any("Prohibited dynamic assignment inside class 'ExploitSuite'" in r for r in res.rejection_reasons)


def test_validator_allows_safe_test_class_structure(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest
from mcp import ClientSession

class TestFilesystemSuite:
    \"\"\"Valid test suite docstring.\"\"\"
    pytestmark = pytest.mark.asyncio
    timeout: int = 30

    async def test_read_file(self, session: ClientSession):
        await session.call_tool("read_file", {"path": "README.md"})
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is True
    assert res.structure_valid is True
    assert res.security_valid is True
    assert len(res.rejection_reasons) == 0


def test_validator_fails_closed_on_anyof_schema():
    validator = HarnessValidator()
    tool_schema = {
        "type": "object",
        "properties": {
            "data": {
                "anyOf": [{"type": "string"}, {"type": "integer"}]
            }
        },
        "required": ["data"]
    }
    tool = DiscoveredToolInput(tool_name="send_data", input_schema=tool_schema)
    code = """
import pytest

@pytest.mark.asyncio
async def test_call(session):
    await session.call_tool("send_data", {"data": "test"})
"""
    res = validator.validate(code, tools=[tool])
    assert res.is_valid is False
    assert res.schema_valid is False
    assert any("unsupported construct 'anyOf'" in r for r in res.rejection_reasons)


def test_validator_fails_closed_on_oneof_schema():
    validator = HarnessValidator()
    tool_schema = {
        "type": "object",
        "properties": {
            "data": {
                "oneOf": [{"type": "string"}, {"type": "integer"}]
            }
        },
        "required": ["data"]
    }
    tool = DiscoveredToolInput(tool_name="send_data", input_schema=tool_schema)
    code = """
import pytest

@pytest.mark.asyncio
async def test_call(session):
    await session.call_tool("send_data", {"data": 123})
"""
    res = validator.validate(code, tools=[tool])
    assert res.is_valid is False
    assert res.schema_valid is False
    assert any("unsupported construct 'oneOf'" in r for r in res.rejection_reasons)


def test_validator_fails_closed_on_allof_schema():
    validator = HarnessValidator()
    tool_schema = {
        "type": "object",
        "properties": {
            "data": {
                "allOf": [{"type": "object"}]
            }
        },
        "required": ["data"]
    }
    tool = DiscoveredToolInput(tool_name="send_data", input_schema=tool_schema)
    code = """
import pytest

@pytest.mark.asyncio
async def test_call(session):
    await session.call_tool("send_data", {"data": {}})
"""
    res = validator.validate(code, tools=[tool])
    assert res.is_valid is False
    assert res.schema_valid is False
    assert any("unsupported construct 'allOf'" in r for r in res.rejection_reasons)


def test_validator_fails_closed_on_ref_schema():
    validator = HarnessValidator()
    tool_schema = {
        "type": "object",
        "properties": {
            "user": {"$ref": "#/definitions/User"}
        },
        "required": ["user"]
    }
    tool = DiscoveredToolInput(tool_name="create_user", input_schema=tool_schema)
    code = """
import pytest

@pytest.mark.asyncio
async def test_call(session):
    await session.call_tool("create_user", {"user": {}})
"""
    res = validator.validate(code, tools=[tool])
    assert res.is_valid is False
    assert res.schema_valid is False
    assert any("unsupported construct '$ref'" in r for r in res.rejection_reasons)


def test_validator_fails_closed_on_pattern_and_format_schema():
    validator = HarnessValidator()
    tool_schema = {
        "type": "object",
        "properties": {
            "email": {"type": "string", "format": "email"},
            "code": {"type": "string", "pattern": "^[0-9]{6}$"}
        },
        "required": ["email", "code"]
    }
    tool = DiscoveredToolInput(tool_name="verify", input_schema=tool_schema)
    code = """
import pytest

@pytest.mark.asyncio
async def test_call(session):
    await session.call_tool("verify", {"email": "test@example.com", "code": "123456"})
"""
    res = validator.validate(code, tools=[tool])
    assert res.is_valid is False
    assert res.schema_valid is False
    assert any("unsupported construct" in r for r in res.rejection_reasons)


def test_validator_fails_closed_on_union_type_schema():
    validator = HarnessValidator()
    tool_schema = {
        "type": "object",
        "properties": {
            "value": {"type": ["string", "null"]}
        },
        "required": ["value"]
    }
    tool = DiscoveredToolInput(tool_name="set_val", input_schema=tool_schema)
    code = """
import pytest

@pytest.mark.asyncio
async def test_call(session):
    await session.call_tool("set_val", {"value": "hello"})
"""
    res = validator.validate(code, tools=[tool])
    assert res.is_valid is False
    assert res.schema_valid is False
    assert any("union type" in r for r in res.rejection_reasons)


def test_validator_fails_closed_on_unsupported_type_schema():
    validator = HarnessValidator()
    tool_schema = {
        "type": "object",
        "properties": {
            "raw": {"type": "custom_binary_payload"}
        },
        "required": ["raw"]
    }
    tool = DiscoveredToolInput(tool_name="upload", input_schema=tool_schema)
    code = """
import pytest

@pytest.mark.asyncio
async def test_call(session):
    await session.call_tool("upload", {"raw": "abc"})
"""
    res = validator.validate(code, tools=[tool])
    assert res.is_valid is False
    assert res.schema_valid is False
    assert any("specifies unsupported type 'custom_binary_payload'" in r for r in res.rejection_reasons)


def test_validator_fails_closed_on_untyped_array_schema():
    validator = HarnessValidator()
    tool_schema = {
        "type": "object",
        "properties": {
            "tags": {"type": "array"}
        },
        "required": ["tags"]
    }
    tool = DiscoveredToolInput(tool_name="tag", input_schema=tool_schema)
    code = """
import pytest

@pytest.mark.asyncio
async def test_call(session):
    await session.call_tool("tag", {"tags": ["a", "b"]})
"""
    res = validator.validate(code, tools=[tool])
    assert res.is_valid is False
    assert res.schema_valid is False
    assert any("lacks a valid 'items' object schema" in r for r in res.rejection_reasons)


def test_validator_scenario_matching_rejects_substring_collision(sample_tools):
    validator = HarnessValidator()
    plan = TestPlan(
        plan_id="p-read",
        target_server_summary="read server",
        scenarios=[
            TestScenario(
                scenario_id="read",
                title="Perform read action",
                objective="Read test",
                steps=[TestStep(step_index=1, tool_name="read_file", arguments={"path": "a.txt"}, expected_result="ok")]
            )
        ]
    )
    # Function is named test_thread - contains 'read' as substring of 'thread'
    code = """
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_thread(session: ClientSession):
    \"\"\"This tests thread execution without implementing read scenario.\"\"\"
    await session.call_tool("read_file", {"path": "a.txt"})
"""
    res = validator.validate(code, tools=sample_tools, test_plan=plan)
    assert res.is_valid is False
    assert res.structure_valid is False
    assert any("does not implement any declared scenarios" in r for r in res.rejection_reasons)
    assert "read" not in res.identified_scenarios


def test_validator_scenario_matching_accepts_explicit_decorator(sample_tools):
    validator = HarnessValidator()
    plan = TestPlan(
        plan_id="p-dec",
        target_server_summary="decorator plan",
        scenarios=[
            TestScenario(
                scenario_id="SCENARIO-01",
                title="Read file scenario",
                objective="Read test",
                steps=[TestStep(step_index=1, tool_name="read_file", arguments={"path": "a.txt"}, expected_result="ok")]
            )
        ]
    )
    code = """
import pytest
from mcp import ClientSession

@pytest.mark.scenario("SCENARIO-01")
@pytest.mark.asyncio
async def test_read_operation(session: ClientSession):
    await session.call_tool("read_file", {"path": "a.txt"})
"""
    res = validator.validate(code, tools=sample_tools, test_plan=plan)
    assert res.is_valid is True
    assert res.structure_valid is True
    assert "SCENARIO-01" in res.identified_scenarios


def test_validator_rejects_loop_subprocess_shell(sample_tools):
    validator = HarnessValidator()
    code = """
import asyncio

async def test_exploit(session):
    loop = asyncio.get_running_loop()
    await loop.subprocess_shell(None, "cat /etc/passwd")
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("subprocess_shell" in r for r in res.rejection_reasons)


def test_validator_rejects_loop_subprocess_exec(sample_tools):
    validator = HarnessValidator()
    code = """
import asyncio

async def test_exploit(session):
    loop = asyncio.get_running_loop()
    await loop.subprocess_exec(None, "whoami")
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("subprocess_exec" in r for r in res.rejection_reasons)


def test_validator_rejects_mcp_client_stdio_import(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest
from mcp.client.stdio import stdio_client

@pytest.mark.asyncio
async def test_exploit(session):
    pass
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("stdio" in r for r in res.rejection_reasons)


def test_validator_rejects_mcp_client_sse_import(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest
from mcp.client.sse import sse_client

@pytest.mark.asyncio
async def test_exploit(session):
    pass
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("sse" in r for r in res.rejection_reasons)


def test_validator_rejects_coroutine_frame_reflection(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest

async def dummy():
    pass

@pytest.mark.asyncio
async def test_coro_frame(session):
    c = dummy()
    frame = c.cr_frame
    b = frame.f_builtins
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("cr_frame" in r for r in res.rejection_reasons)


def test_validator_rejects_dynamic_default_argument_comprehension(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest

@pytest.mark.asyncio
async def test_exploit(session, x=[i for i in range(1000)]):
    pass
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("Prohibited dynamic default argument" in r for r in res.rejection_reasons)


def test_validator_rejects_dynamic_annotation_comprehension(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest

@pytest.mark.asyncio
async def test_exploit(session: [i for i in range(100)]):
    pass
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("inside type annotation" in r for r in res.rejection_reasons)


def test_validator_rejects_dynamic_decorator_expression(sample_tools):
    validator = HarnessValidator()
    code = """
import pytest

@[i for i in range(10)][0]
def test_exploit(session):
    pass
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("Prohibited dynamic or executable decorator" in r for r in res.rejection_reasons)


def test_validator_fails_closed_on_nested_array_unsupported_schema_with_empty_argument():
    validator = HarnessValidator()
    tool_schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "anyOf": [{"type": "string"}, {"type": "integer"}]
                }
            }
        },
        "required": ["items"]
    }
    code = """
import pytest

@pytest.mark.asyncio
async def test_call(session):
    await session.call_tool("send_items", {"items": []})
"""
    tools = [DiscoveredToolInput(tool_name="send_items", input_schema=tool_schema)]
    res = validator.validate(code, tools=tools)
    assert res.is_valid is False
    assert res.schema_valid is False
    assert any("unsupported construct 'anyOf'" in r for r in res.rejection_reasons)


def test_validator_scenario_matching_accepts_docstring_tag(sample_tools):
    validator = HarnessValidator()
    plan = TestPlan(
        plan_id="p-doc",
        target_server_summary="docstring plan",
        scenarios=[
            TestScenario(
                scenario_id="SCENARIO-01",
                title="Read file scenario",
                objective="Read test",
                steps=[TestStep(step_index=1, tool_name="read_file", arguments={"path": "a.txt"}, expected_result="ok")]
            )
        ]
    )
    code = """
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_read_operation(session: ClientSession):
    \"\"\"Scenario: SCENARIO-01 - Verifies file read operation.\"\"\"
    await session.call_tool("read_file", {"path": "a.txt"})
"""
    res = validator.validate(code, tools=sample_tools, test_plan=plan)
    assert res.is_valid is True
    assert res.structure_valid is True
    assert "SCENARIO-01" in res.identified_scenarios


def test_validator_scenario_matching_accepts_scenario_function_name(sample_tools):
    validator = HarnessValidator()
    plan = TestPlan(
        plan_id="p-name",
        target_server_summary="function name plan",
        scenarios=[
            TestScenario(
                scenario_id="SCENARIO-01",
                title="Read file scenario",
                objective="Read test",
                steps=[TestStep(step_index=1, tool_name="read_file", arguments={"path": "a.txt"}, expected_result="ok")]
            )
        ]
    )
    code = """
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_scenario_SCENARIO_01_read(session: ClientSession):
    await session.call_tool("read_file", {"path": "a.txt"})
"""
    res = validator.validate(code, tools=sample_tools, test_plan=plan)
    assert res.is_valid is True
    assert res.structure_valid is True
    assert "SCENARIO-01" in res.identified_scenarios


# ==============================================================================
# AUDIT REGRESSION TESTS (F1 - F5)
# ==============================================================================

@pytest.mark.parametrize(
    "prohibited_transport_import",
    [
        "from mcp.client.streamable_http import StreamableHTTPTransport",
        "import mcp.client.streamable_http",
        "from mcp.client import streamable_http",
        "from mcp.client.sse import sse_client",
        "import mcp.client.sse",
        "from mcp.client.websocket import WebSocketClient",
        "import mcp.client.websocket",
        "from mcp.client.stdio import stdio_client",
        "import mcp.client.stdio",
        "from mcp import streamable_http",
    ],
)
def test_audit_f1_rejects_network_and_process_transports(prohibited_transport_import, sample_tools):
    """F1: Ensure all network-capable and process transports are rejected regardless of import syntax."""
    validator = HarnessValidator()
    code = f"""
import pytest
{prohibited_transport_import}

@pytest.mark.asyncio
async def test_tool_call(session):
    await session.call_tool("read_file", {{"path": "test.txt"}})
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("Prohibited" in r for r in res.rejection_reasons)


@pytest.mark.parametrize(
    "executable_annotation",
    [
        "x: [i for i in range(10)] = 1",
        "x: {i: i for i in range(5)} = {}",
        "x: {i for i in range(5)} = set()",
        "x: (i for i in range(5)) = None",
        "x: eval('1+1') = 2",
        "x: (lambda: 1)() = 1",
    ],
)
def test_audit_f2_rejects_executable_module_annotations(executable_annotation, sample_tools):
    """F2: Ensure executable module-scope annotations are rejected."""
    validator = HarnessValidator()
    code = f"""
import pytest
from typing import Optional

{executable_annotation}

@pytest.mark.asyncio
async def test_sample(session):
    await session.call_tool("read_file", {{"path": "file.txt"}})
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("Prohibited executable" in r for r in res.rejection_reasons)


def test_audit_f2_rejects_executable_class_annotations(sample_tools):
    """F2: Ensure executable class-body annotations are rejected."""
    validator = HarnessValidator()
    code = """
import pytest

class TestSuite:
    bad_field: [x for x in range(3)] = 1

    @pytest.mark.asyncio
    async def test_method(self, session):
        await session.call_tool("read_file", {"path": "file.txt"})
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert any("Prohibited executable expression in annotated assignment" in r for r in res.rejection_reasons)


def test_audit_f2_accepts_safe_static_type_annotations(sample_tools):
    """F2: Ensure standard safe typing annotations are accepted."""
    validator = HarnessValidator()
    code = """
import pytest
from typing import Dict, List, Optional, Any
from mcp.types import CallToolResult

val_str: str = "safe"
val_int: int = 42
val_opt: Optional[Dict[str, Any]] = None
val_union: int | None = None
forward_ref: "CallToolResult" = None

@pytest.mark.asyncio
async def test_annotated_fn(session: Any) -> None:
    await session.call_tool("read_file", {"path": "a.txt"})
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is True
    assert res.security_valid is True


def test_audit_f3_additional_properties_false_with_empty_properties():
    """F3: Ensure additionalProperties: false rejects undeclared arguments even when properties is empty."""
    validator = HarnessValidator()
    tool = DiscoveredToolInput(
        tool_name="no_args_tool",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    )
    code = """
import pytest

@pytest.mark.asyncio
async def test_extra_arg(session):
    await session.call_tool("no_args_tool", {"unexpected": "value"})
"""
    res = validator.validate(code, tools=[tool])
    assert res.is_valid is False
    assert res.schema_valid is False
    assert any("additionalProperties is False" in r for r in res.rejection_reasons)


def test_audit_f3_enforces_string_min_max_length():
    """F3: Ensure minLength and maxLength are enforced on string parameters."""
    validator = HarnessValidator()
    tool = DiscoveredToolInput(
        tool_name="user_tag",
        input_schema={
            "type": "object",
            "properties": {
                "tag": {"type": "string", "minLength": 3, "maxLength": 8},
            },
            "required": ["tag"],
        },
    )
    # Too short
    code_short = """
import pytest

@pytest.mark.asyncio
async def test_short(session):
    await session.call_tool("user_tag", {"tag": "ab"})
"""
    res_short = validator.validate(code_short, tools=[tool])
    assert res_short.is_valid is False
    assert any("is less than minLength (3)" in r for r in res_short.rejection_reasons)

    # Too long
    code_long = """
import pytest

@pytest.mark.asyncio
async def test_long(session):
    await session.call_tool("user_tag", {"tag": "toolongtagname"})
"""
    res_long = validator.validate(code_long, tools=[tool])
    assert res_long.is_valid is False
    assert any("exceeds maxLength (8)" in r for r in res_long.rejection_reasons)


def test_audit_f3_enforces_numeric_min_max():
    """F3: Ensure minimum and maximum are enforced on integer and number parameters."""
    validator = HarnessValidator()
    tool = DiscoveredToolInput(
        tool_name="set_limit",
        input_schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["limit"],
        },
    )
    # Below min
    code_below = """
import pytest

@pytest.mark.asyncio
async def test_below(session):
    await session.call_tool("set_limit", {"limit": 0})
"""
    res = validator.validate(code_below, tools=[tool])
    assert res.is_valid is False
    assert any("is less than minimum (1)" in r for r in res.rejection_reasons)

    # Above max
    code_above = """
import pytest

@pytest.mark.asyncio
async def test_above(session):
    await session.call_tool("set_limit", {"limit": 101})
"""
    res = validator.validate(code_above, tools=[tool])
    assert res.is_valid is False
    assert any("exceeds maximum (100)" in r for r in res.rejection_reasons)


def test_audit_f3_enforces_array_min_max_items():
    """F3: Ensure minItems and maxItems are enforced on array parameters."""
    validator = HarnessValidator()
    tool = DiscoveredToolInput(
        tool_name="batch_process",
        input_schema={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 2,
                },
            },
            "required": ["items"],
        },
    )
    # Too few items
    code_few = """
import pytest

@pytest.mark.asyncio
async def test_few(session):
    await session.call_tool("batch_process", {"items": []})
"""
    res = validator.validate(code_few, tools=[tool])
    assert res.is_valid is False
    assert any("is less than minItems (1)" in r for r in res.rejection_reasons)

    # Too many items
    code_many = """
import pytest

@pytest.mark.asyncio
async def test_many(session):
    await session.call_tool("batch_process", {"items": ["a", "b", "c"]})
"""
    res = validator.validate(code_many, tools=[tool])
    assert res.is_valid is False
    assert any("exceeds maxItems (2)" in r for r in res.rejection_reasons)


def test_audit_f3_rejects_unsupported_schema_keywords_upfront():
    """F3: Ensure schema containing unsupported keywords fails closed upfront."""
    validator = HarnessValidator()
    tool = DiscoveredToolInput(
        tool_name="unknown_kw_tool",
        input_schema={
            "type": "object",
            "properties": {
                "field": {"type": "string", "customUnsupportedKeyword": "val"},
            },
        },
    )
    code = """
import pytest

@pytest.mark.asyncio
async def test_ok(session):
    await session.call_tool("unknown_kw_tool", {"field": "test"})
"""
    res = validator.validate(code, tools=[tool])
    assert res.is_valid is False
    assert any("unsupported construct" in r for r in res.rejection_reasons)


def test_audit_f4_rejects_empty_test_claiming_scenario(sample_tools):
    """F4: Ensure empty test functions claiming scenario coverage are rejected."""
    validator = HarnessValidator()
    plan = TestPlan(
        plan_id="p-1",
        target_server_summary="plan",
        scenarios=[
            TestScenario(
                scenario_id="SCENARIO-01",
                title="Read",
                objective="Read",
                steps=[TestStep(step_index=1, tool_name="read_file", arguments={"path": "a.txt"}, expected_result="ok")]
            )
        ]
    )
    code = """
import pytest

@pytest.mark.scenario("SCENARIO-01")
async def test_scenario_01():
    pass
"""
    res = validator.validate(code, tools=sample_tools, test_plan=plan)
    assert res.is_valid is False
    assert res.structure_valid is False
    assert any("empty test body" in r for r in res.rejection_reasons)


def test_audit_f4_rejects_claimed_scenario_with_mismatched_arguments(sample_tools):
    """F4: Ensure test claiming scenario but passing mismatched arguments is rejected."""
    validator = HarnessValidator()
    plan = TestPlan(
        plan_id="p-1",
        target_server_summary="plan",
        scenarios=[
            TestScenario(
                scenario_id="SCENARIO-01",
                title="Read",
                objective="Read",
                steps=[TestStep(step_index=1, tool_name="read_file", arguments={"path": "expected.txt"}, expected_result="ok")]
            )
        ]
    )
    code = """
import pytest

@pytest.mark.scenario("SCENARIO-01")
async def test_scenario_01(session):
    await session.call_tool("read_file", {"path": "different.txt"})
"""
    res = validator.validate(code, tools=sample_tools, test_plan=plan)
    assert res.is_valid is False
    assert res.structure_valid is False
    assert any("does not invoke expected tool 'read_file' with arguments {'path': 'expected.txt'}" in r for r in res.rejection_reasons)


def test_audit_f4_rejects_duplicate_scenario_ids_in_test_plan(sample_tools):
    """F4: Ensure test plan containing duplicate scenario IDs is rejected."""
    validator = HarnessValidator()
    plan = TestPlan(
        plan_id="p-dup",
        target_server_summary="dup plan",
        scenarios=[
            TestScenario(
                scenario_id="SCENARIO-01",
                title="Read 1",
                objective="Read 1",
                steps=[TestStep(step_index=1, tool_name="read_file", arguments={"path": "a.txt"}, expected_result="ok")]
            ),
            TestScenario(
                scenario_id="SCENARIO-01",
                title="Read 2",
                objective="Read 2",
                steps=[TestStep(step_index=1, tool_name="read_file", arguments={"path": "b.txt"}, expected_result="ok")]
            ),
        ]
    )
    code = """
import pytest

@pytest.mark.scenario("SCENARIO-01")
async def test_scenario_01(session):
    await session.call_tool("read_file", {"path": "a.txt"})
"""
    res = validator.validate(code, tools=sample_tools, test_plan=plan)
    assert res.is_valid is False
    assert any("duplicate, empty, or ambiguous scenario identifiers" in r for r in res.rejection_reasons)


def test_audit_f5_rejects_harness_exceeding_byte_limit(sample_tools):
    """F5: Ensure harness exceeding 64KB byte limit is rejected upfront."""
    validator = HarnessValidator()
    huge_comment = "# " + ("A" * 70_000)
    code = f"""
import pytest
{huge_comment}

@pytest.mark.asyncio
async def test_tool(session):
    await session.call_tool("read_file", {{"path": "a.txt"}})
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert any("exceeds maximum byte length limit" in r for r in res.rejection_reasons)


def test_audit_f5_rejects_harness_exceeding_line_length_limit(sample_tools):
    """F5: Ensure harness with a line exceeding 2000 characters is rejected upfront."""
    validator = HarnessValidator()
    long_line = "# " + ("B" * 2_500)
    code = f"""
import pytest
{long_line}

@pytest.mark.asyncio
async def test_tool(session):
    await session.call_tool("read_file", {{"path": "a.txt"}})
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert any("exceeds maximum line length limit" in r for r in res.rejection_reasons)


# --- Second Independent Security Audit Regression Tests (F1 - F4) ---


def test_audit2_f1_rejects_executable_forward_ref_type_annotations(sample_tools):
    """F1: Ensure executable code hidden in forward-reference string type annotations is rejected."""
    validator = HarnessValidator()
    code = """
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_tool(session: "__import__('subprocess').run(['id'])"):
    await session.call_tool("read_file", {"path": "test.txt"})
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("Prohibited" in r for r in res.rejection_reasons)


def test_audit2_f1_allows_safe_forward_ref_type_annotations(sample_tools):
    """F1: Ensure legitimate static forward-reference type annotations are permitted."""
    validator = HarnessValidator()
    code = """
import pytest
from typing import Optional
from mcp import ClientSession

@pytest.mark.asyncio
async def test_tool(session: "Optional[ClientSession]"):
    await session.call_tool("read_file", {"path": "test.txt"})
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is True
    assert res.security_valid is True


def test_audit2_f1_rejects_pydantic_import_string(sample_tools):
    """F1: Ensure Pydantic ImportString is rejected on import and attribute lookup."""
    validator = HarnessValidator()
    code = """
import pytest
from pydantic import ImportString

@pytest.mark.asyncio
async def test_tool(session):
    await session.call_tool("read_file", {"path": "test.txt"})
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert any("ImportString" in r for r in res.rejection_reasons)


def test_audit2_f1_rejects_pydantic_type_adapter(sample_tools):
    """F1: Ensure Pydantic TypeAdapter is rejected on import and attribute lookup."""
    validator = HarnessValidator()
    code = """
import pytest
from pydantic import TypeAdapter

@pytest.mark.asyncio
async def test_tool(session):
    await session.call_tool("read_file", {"path": "test.txt"})
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert any("TypeAdapter" in r for r in res.rejection_reasons)


def test_audit2_f1_rejects_unittest_mock_importer(sample_tools):
    """F1: Ensure private symbols starting with leading underscore are rejected on import."""
    validator = HarnessValidator()
    code = """
import pytest
from unittest.mock import _importer

@pytest.mark.asyncio
async def test_tool(session):
    await session.call_tool("read_file", {"path": "test.txt"})
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert any("Prohibited private symbol import '_importer'" in r or "_importer" in r for r in res.rejection_reasons)


def test_audit2_f1_rejects_pytest_plugins_assignment(sample_tools):
    """F1: Ensure module-level pytest_plugins assignment is rejected."""
    validator = HarnessValidator()
    code = """
import pytest

pytest_plugins = "subprocess"

@pytest.mark.asyncio
async def test_tool(session):
    await session.call_tool("read_file", {"path": "test.txt"})
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert any("pytest_plugins" in r for r in res.rejection_reasons)


def test_audit2_f2_rejects_dead_branch_scenario_coverage(sample_tools, sample_test_plan):
    """F2: Ensure tool calls inside dead branches (if False:) cannot satisfy scenario coverage."""
    validator = HarnessValidator()
    code = """
import pytest

@pytest.mark.scenario("SCENARIO-01")
async def test_scenario_01(session):
    if False:
        await session.call_tool("read_file", {"path": "README.md"})
    assert True
"""
    res = validator.validate(code, tools=sample_tools, test_plan=sample_test_plan)
    assert res.is_valid is False
    assert res.structure_valid is False
    assert any("does not invoke expected tool 'read_file'" in r for r in res.rejection_reasons)


def test_audit2_f2_rejects_uncalled_nested_helper_scenario_coverage(sample_tools, sample_test_plan):
    """F2: Ensure tool calls inside uncalled nested helper functions cannot satisfy scenario coverage."""
    validator = HarnessValidator()
    code = """
import pytest

@pytest.mark.scenario("SCENARIO-01")
async def test_scenario_01(session):
    async def helper():
        await session.call_tool("read_file", {"path": "README.md"})
    assert True
"""
    res = validator.validate(code, tools=sample_tools, test_plan=sample_test_plan)
    assert res.is_valid is False
    assert res.structure_valid is False
    assert any("does not invoke expected tool 'read_file'" in r for r in res.rejection_reasons)


def test_audit2_f2_rejects_unawaited_tool_call_scenario_coverage(sample_tools, sample_test_plan):
    """F2: Ensure unawaited tool calls (session.call_tool without await) cannot satisfy scenario coverage."""
    validator = HarnessValidator()
    code = """
import pytest

@pytest.mark.scenario("SCENARIO-01")
async def test_scenario_01(session):
    session.call_tool("read_file", {"path": "README.md"})
    assert True
"""
    res = validator.validate(code, tools=sample_tools, test_plan=sample_test_plan)
    assert res.is_valid is False
    assert res.structure_valid is False
    assert any("does not invoke expected tool 'read_file'" in r for r in res.rejection_reasons)


def test_audit2_f3_schema_valued_additional_properties():
    """F3: Ensure schema-valued additionalProperties is recursively enforced on undeclared keys."""
    validator = HarnessValidator()
    tool = DiscoveredToolInput(
        tool_name="add_props_tool",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
            "additionalProperties": {
                "type": "integer",
                "minimum": 0,
            },
        },
    )

    # 1. Valid additional property matching schema
    valid_code = """
import pytest

@pytest.mark.asyncio
async def test_valid(session):
    await session.call_tool("add_props_tool", {"name": "alice", "custom_count": 42})
"""
    res_valid = validator.validate(valid_code, tools=[tool])
    assert res_valid.is_valid is True

    # 2. Invalid additional property failing type check
    bad_type_code = """
import pytest

@pytest.mark.asyncio
async def test_bad_type(session):
    await session.call_tool("add_props_tool", {"name": "alice", "custom_count": "forty-two"})
"""
    res_bad_type = validator.validate(bad_type_code, tools=[tool])
    assert res_bad_type.is_valid is False
    assert any("expected type 'integer', got str" in r for r in res_bad_type.rejection_reasons)

    # 3. Invalid additional property failing numeric bounds
    bad_bounds_code = """
import pytest

@pytest.mark.asyncio
async def test_bad_bounds(session):
    await session.call_tool("add_props_tool", {"name": "alice", "custom_count": -5})
"""
    res_bad_bounds = validator.validate(bad_bounds_code, tools=[tool])
    assert res_bad_bounds.is_valid is False
    assert any("is less than minimum (0)" in r for r in res_bad_bounds.rejection_reasons)


def test_audit2_f4_malformed_enum_fails_closed_safely():
    """F4: Ensure malformed enum schema (e.g. enum: 42) fails closed without TypeError."""
    validator = HarnessValidator()
    tool = DiscoveredToolInput(
        tool_name="bad_enum_tool",
        input_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": 42},
            },
        },
    )
    code = """
import pytest

@pytest.mark.asyncio
async def test_tool(session):
    await session.call_tool("bad_enum_tool", {"status": "active"})
"""
    res = validator.validate(code, tools=[tool])
    assert res.is_valid is False
    assert any("invalid enum" in r or "malformed 'enum'" in r for r in res.rejection_reasons)


def test_audit2_f4_deeply_nested_schema_depth_limit():
    """F4: Ensure deeply nested schemas exceed depth limit and fail closed without RecursionError."""
    validator = HarnessValidator()
    # Build a schema nested 60 levels deep
    curr: Dict[str, Any] = {"type": "string"}
    for _ in range(60):
        curr = {"type": "object", "properties": {"nested": curr}}

    tool = DiscoveredToolInput(
        tool_name="deep_tool",
        input_schema=curr,
    )
    code = """
import pytest

@pytest.mark.asyncio
async def test_tool(session):
    await session.call_tool("deep_tool", {})
"""
    res = validator.validate(code, tools=[tool])
    assert res.is_valid is False
    assert any("exceeds maximum allowable nesting depth" in r for r in res.rejection_reasons)


def test_audit2_f4_lone_surrogate_unicode_fails_closed_safely(sample_tools):
    """F4: Ensure lone surrogate character in source code is rejected safely without UnicodeEncodeError."""
    validator = HarnessValidator()
    code = "import pytest\n# Lone surrogate: \ud800\nasync def test_foo(): pass\n"
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert any("Unicode" in r or "surrogate" in r for r in res.rejection_reasons)


# ==============================================================================
# Phase 5 Independent Review Regression Tests (R1 - R5)
# ==============================================================================

def test_r1_unittest_mock_patch_get_original_rejected(sample_tools):
    """R1: patch('subprocess.run').get_original() must be rejected."""
    validator = HarnessValidator()
    code = """
import pytest
from unittest.mock import patch

def test_escape():
    patch("subprocess.run").get_original()
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("unittest" in r or "patch" in r for r in res.rejection_reasons)


def test_r1_class_base_call_rejected(sample_tools):
    """R1: Class base that invokes a function call must be rejected."""
    validator = HarnessValidator()
    code = """
import pytest

class Evil(patch("subprocess.run").get_original()):
    pass

def test_something():
    pass
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("class base" in r for r in res.rejection_reasons)


def test_r1_decorator_patch_rejected(sample_tools):
    """R1: @patch decorator on test function must be rejected."""
    validator = HarnessValidator()
    code = """
import pytest

@patch("subprocess.run")
def test_something():
    pass
"""
    res = validator.validate(code, tools=sample_tools)
    assert res.is_valid is False
    assert res.security_valid is False
    assert any("decorator" in r for r in res.rejection_reasons)


def test_r1_bare_mock_names_rejected(sample_tools):
    """R1: Bare identifier references to mock symbols must be rejected."""
    validator = HarnessValidator()
    for bad_id in ("patch", "get_original", "Mock", "MagicMock", "mock_open", "NonCallableMock", "PropertyMock"):
        code = f"""
import pytest

def test_identifier():
    x = {bad_id}
"""
        res = validator.validate(code, tools=sample_tools)
        assert res.is_valid is False
        assert res.security_valid is False
        assert any(bad_id in r for r in res.rejection_reasons)


def test_r2_scenario_empty_tuple_loop_rejected(sample_tools):
    """R2: Tool call placed inside statically empty loop `for _ in ():` must not match scenario."""
    validator = HarnessValidator()
    plan = TestPlan(
        plan_id="p1",
        target_server_summary="fs",
        scenarios=[
            TestScenario(
                scenario_id="S1",
                title="read",
                objective="read",
                steps=[TestStep(step_index=1, tool_name="read_file", arguments={"path": "a"})],
            )
        ],
    )
    code = """
import pytest

@pytest.mark.scenario("S1")
async def test_empty_loop(session):
    for _ in ():
        await session.call_tool("read_file", {"path": "a"})
"""
    res = validator.validate(code, tools=sample_tools, test_plan=plan)
    assert res.is_valid is False
    assert "S1" not in res.identified_scenarios


def test_r2_scenario_unreachable_try_handler_rejected(sample_tools):
    """R2: Tool call placed inside `except:` handler must not match scenario."""
    validator = HarnessValidator()
    plan = TestPlan(
        plan_id="p1",
        target_server_summary="fs",
        scenarios=[
            TestScenario(
                scenario_id="S1",
                title="read",
                objective="read",
                steps=[TestStep(step_index=1, tool_name="read_file", arguments={"path": "a"})],
            )
        ],
    )
    code = """
import pytest

@pytest.mark.scenario("S1")
async def test_except_block(session):
    try:
        pass
    except Exception:
        await session.call_tool("read_file", {"path": "a"})
"""
    res = validator.validate(code, tools=sample_tools, test_plan=plan)
    assert res.is_valid is False
    assert "S1" not in res.identified_scenarios


def test_r2_scenario_reversed_execution_order_rejected(sample_tools):
    """R2: Calling tools in reversed order compared to declared scenario steps must be rejected."""
    validator = HarnessValidator()
    plan = TestPlan(
        plan_id="p1",
        target_server_summary="fs",
        scenarios=[
            TestScenario(
                scenario_id="S1",
                title="multi-step",
                objective="multi-step",
                steps=[
                    TestStep(step_index=1, tool_name="read_file", arguments={"path": "a"}),
                    TestStep(step_index=2, tool_name="write_file", arguments={"path": "b", "content": "c"}),
                ],
            )
        ],
    )
    # Reversed call order: write_file then read_file
    code = """
import pytest

@pytest.mark.scenario("S1")
async def test_reversed(session):
    await session.call_tool("write_file", {"path": "b", "content": "c"})
    await session.call_tool("read_file", {"path": "a"})
"""
    res = validator.validate(code, tools=sample_tools, test_plan=plan)
    assert res.is_valid is False
    assert "S1" not in res.identified_scenarios
    assert any("order" in r or "sequentially" in r for r in res.rejection_reasons)


def test_r2_scenario_extra_unplanned_arguments_rejected(sample_tools):
    """R2: Calling tool with extra unplanned arguments must not match scenario."""
    validator = HarnessValidator()
    plan = TestPlan(
        plan_id="p1",
        target_server_summary="fs",
        scenarios=[
            TestScenario(
                scenario_id="S1",
                title="read",
                objective="read",
                steps=[TestStep(step_index=1, tool_name="read_file", arguments={"path": "a"})],
            )
        ],
    )
    code = """
import pytest

@pytest.mark.scenario("S1")
async def test_extra_args(session):
    await session.call_tool("read_file", {"path": "a", "extra_flag": True})
"""
    res = validator.validate(code, tools=sample_tools, test_plan=plan)
    assert res.is_valid is False
    assert "S1" not in res.identified_scenarios


def test_r2_scenario_dynamic_arguments_rejected_from_coverage(sample_tools):
    """R2: Calling tool with dynamic variable arguments must not match scenario."""
    validator = HarnessValidator()
    plan = TestPlan(
        plan_id="p1",
        target_server_summary="fs",
        scenarios=[
            TestScenario(
                scenario_id="S1",
                title="read",
                objective="read",
                steps=[TestStep(step_index=1, tool_name="read_file", arguments={"path": "a"})],
            )
        ],
    )
    code = """
import pytest

@pytest.mark.scenario("S1")
async def test_dynamic_args(session):
    arg = {"path": "a"}
    await session.call_tool("read_file", arg)
"""
    res = validator.validate(code, tools=sample_tools, test_plan=plan)
    assert res.is_valid is False
    assert "S1" not in res.identified_scenarios


def test_r3_null_minimum_rejected():
    """R3: Schema keyword 'minimum: null' must be rejected upfront."""
    validator = HarnessValidator()
    tool = DiscoveredToolInput(
        tool_name="null_min_tool",
        input_schema={
            "type": "object",
            "properties": {
                "count": {"type": "integer", "minimum": None},
            },
        },
    )
    code = """
import pytest

@pytest.mark.asyncio
async def test_call(session):
    await session.call_tool("null_min_tool", {"count": 1})
"""
    res = validator.validate(code, tools=[tool])
    assert res.is_valid is False
    assert res.schema_valid is False
    assert any("null minimum" in r or "invalid or null minimum" in r for r in res.rejection_reasons)


def test_r3_root_null_type_rejected():
    """R3: Root schema with 'type: null' must be rejected upfront."""
    validator = HarnessValidator()
    tool = DiscoveredToolInput(
        tool_name="null_root_type_tool",
        input_schema={
            "type": None,
            "properties": {"x": {"type": "string"}},
        },
    )
    code = "import pytest\nasync def test_noop(): pass\n"
    res = validator.validate(code, tools=[tool])
    assert res.is_valid is False
    assert any("null 'type'" in r for r in res.rejection_reasons)


def test_r3_unexercised_property_null_type_rejected():
    """R3: Unexercised schema property with 'type: null' must be rejected upfront."""
    validator = HarnessValidator()
    tool = DiscoveredToolInput(
        tool_name="partial_tool",
        input_schema={
            "type": "object",
            "properties": {
                "valid_field": {"type": "string"},
                "unexercised_field": {"type": None},
            },
        },
    )
    code = """
import pytest

@pytest.mark.asyncio
async def test_call(session):
    await session.call_tool("partial_tool", {"valid_field": "hello"})
"""
    res = validator.validate(code, tools=[tool])
    assert res.is_valid is False
    assert any("unexercised_field" in r and "null 'type'" in r for r in res.rejection_reasons)


def test_r3_malformed_required_rejected():
    """R3: Schema with nested list in 'required' must be cleanly rejected without unhandled exception."""
    validator = HarnessValidator()
    tool = DiscoveredToolInput(
        tool_name="bad_req_tool",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path", ["nested"]],
        },
    )
    code = "import pytest\nasync def test_noop(): pass\n"
    res = validator.validate(code, tools=[tool])
    assert res.is_valid is False
    assert any("required" in r for r in res.rejection_reasons)


def test_r4_tool_count_limit_rejected():
    """R4: Tool inventory exceeding 100 tools must be rejected."""
    validator = HarnessValidator()
    tools = [
        DiscoveredToolInput(
            tool_name=f"tool_{i}",
            input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
        )
        for i in range(101)
    ]
    code = "import pytest\nasync def test_noop(): pass\n"
    res = validator.validate(code, tools=tools)
    assert res.is_valid is False
    assert any("exceeds maximum tool count limit" in r for r in res.rejection_reasons)


def test_r4_single_tool_schema_bytes_limit_rejected():
    """R4: Tool schema exceeding 32 KB serialized size must be rejected."""
    validator = HarnessValidator()
    huge_schema = {
        "type": "object",
        "properties": {f"prop_{i}": {"type": "string", "description": "x" * 200} for i in range(200)},
    }
    tool = DiscoveredToolInput(tool_name="huge_schema_tool", input_schema=huge_schema)
    code = "import pytest\nasync def test_noop(): pass\n"
    res = validator.validate(code, tools=[tool])
    assert res.is_valid is False
    assert any("exceeds maximum limit" in r and "bytes" in r for r in res.rejection_reasons)


def test_r4_per_tool_node_budget_rejected():
    """R4: Tool schema exceeding 500 AST nodes must be rejected."""
    validator = HarnessValidator()
    props = {f"k_{i}": {"type": "string"} for i in range(600)}
    tool = DiscoveredToolInput(tool_name="many_props_tool", input_schema={"type": "object", "properties": props})
    code = "import pytest\nasync def test_noop(): pass\n"
    res = validator.validate(code, tools=[tool])
    assert res.is_valid is False
    assert any("exceeds per-tool node budget" in r for r in res.rejection_reasons)


def test_r4_nesting_depth_limit_rejected():
    """R4: Tool schema exceeding nesting depth 20 must be rejected."""
    validator = HarnessValidator()
    curr: Dict[str, Any] = {"type": "string"}
    for _ in range(25):
        curr = {"type": "object", "properties": {"nested": curr}}
    tool = DiscoveredToolInput(tool_name="deep_tool", input_schema=curr)
    code = "import pytest\nasync def test_noop(): pass\n"
    res = validator.validate(code, tools=[tool])
    assert res.is_valid is False
    assert any("nesting depth" in r for r in res.rejection_reasons)


def test_r5_validator_catches_unhandled_error_with_correlation_id(monkeypatch):
    """R5: Validator catches unexpected exceptions, logs correlation ID, and does not leak raw exception detail."""
    validator = HarnessValidator()

    def crash(*args, **kwargs):
        raise TypeError("unhashable type: 'list'")

    monkeypatch.setattr(validator, "_validate_impl", crash)
    res = validator.validate("import pytest\ndef test_fn(): pass")
    assert res.is_valid is False
    assert any("val-err-" in r for r in res.rejection_reasons)
    assert not any("unhashable type" in r for r in res.rejection_reasons)


# =========================================================================
# R2: Control-Flow and Dead-Code Elimination Regression Tests
# =========================================================================


def test_r2_unreachable_call_after_break_rejected(sample_tools, sample_test_plan):
    """R2: Exact reproduction - tool call placed after unconditional break must NOT match scenario."""
    validator = HarnessValidator()
    code = """
import pytest

@pytest.mark.scenario("SCENARIO-01")
async def test_s1(session):
    while True:
        break
        await session.call_tool("read_file", {"path": "README.md"})
"""
    res = validator.validate(code, tools=sample_tools, test_plan=sample_test_plan)
    assert res.is_valid is False
    assert "SCENARIO-01" not in res.identified_scenarios
    assert any("does not invoke expected tool 'read_file'" in r for r in res.rejection_reasons)


def test_r2_tool_call_before_break_matched(sample_tools, sample_test_plan):
    """R2: Tool call placed before unconditional break inside while True executes once and must match."""
    validator = HarnessValidator()
    code = """
import pytest

@pytest.mark.scenario("SCENARIO-01")
async def test_s1(session):
    while True:
        await session.call_tool("read_file", {"path": "README.md"})
        break
"""
    res = validator.validate(code, tools=sample_tools, test_plan=sample_test_plan)
    assert res.is_valid is True
    assert "SCENARIO-01" in res.identified_scenarios


def test_r2_infinite_while_without_break_subsequent_dead_rejected(sample_tools, sample_test_plan):
    """R2: Tool call placed after while True without break is dead code and must NOT match."""
    validator = HarnessValidator()
    code = """
import pytest

@pytest.mark.scenario("SCENARIO-01")
async def test_s1(session):
    while True:
        pass
    await session.call_tool("read_file", {"path": "README.md"})
"""
    res = validator.validate(code, tools=sample_tools, test_plan=sample_test_plan)
    assert res.is_valid is False
    assert "SCENARIO-01" not in res.identified_scenarios
    assert any("does not invoke expected tool 'read_file'" in r for r in res.rejection_reasons)


def test_r2_while_with_break_subsequent_reachable_matched(sample_tools, sample_test_plan):
    """R2: Tool call placed after while True that breaks is reachable and must match."""
    validator = HarnessValidator()
    code = """
import pytest

@pytest.mark.scenario("SCENARIO-01")
async def test_s1(session):
    while True:
        break
    await session.call_tool("read_file", {"path": "README.md"})
"""
    res = validator.validate(code, tools=sample_tools, test_plan=sample_test_plan)
    assert res.is_valid is True
    assert "SCENARIO-01" in res.identified_scenarios


def test_r2_nested_loops_break_terminates_inner_loop_only(sample_tools, sample_test_plan):
    """R2: Break in inner loop terminates only inner loop, not outer loop."""
    validator = HarnessValidator()
    code = """
import pytest

@pytest.mark.scenario("SCENARIO-01")
async def test_s1(session):
    while True:
        while True:
            break
            await session.call_tool("read_file", {"path": "dead.md"})
        await session.call_tool("read_file", {"path": "README.md"})
        break
"""
    res = validator.validate(code, tools=sample_tools, test_plan=sample_test_plan)
    assert res.is_valid is True
    assert "SCENARIO-01" in res.identified_scenarios


def test_r2_break_inside_statically_true_if_terminates_loop(sample_tools, sample_test_plan):
    """R2: Break inside statically True if branch terminates enclosing loop."""
    validator = HarnessValidator()
    code = """
import pytest

@pytest.mark.scenario("SCENARIO-01")
async def test_s1(session):
    while True:
        if True:
            break
        await session.call_tool("read_file", {"path": "README.md"})
"""
    res = validator.validate(code, tools=sample_tools, test_plan=sample_test_plan)
    assert res.is_valid is False
    assert "SCENARIO-01" not in res.identified_scenarios


def test_r2_tool_call_after_continue_dead_rejected(sample_tools, sample_test_plan):
    """R2: Tool call placed immediately after continue is dead code and must NOT match."""
    validator = HarnessValidator()
    code = """
import pytest

@pytest.mark.scenario("SCENARIO-01")
async def test_s1(session):
    while True:
        continue
        await session.call_tool("read_file", {"path": "README.md"})
"""
    res = validator.validate(code, tools=sample_tools, test_plan=sample_test_plan)
    assert res.is_valid is False
    assert "SCENARIO-01" not in res.identified_scenarios


def test_r2_dynamic_if_branch_calls_not_guaranteed(sample_tools, sample_test_plan):
    """R2: Tool call inside dynamic if branch cannot be guaranteed to execute."""
    validator = HarnessValidator()
    code = """
import pytest

@pytest.mark.scenario("SCENARIO-01")
async def test_s1(session):
    if len("dynamic") > 3:
        await session.call_tool("read_file", {"path": "README.md"})
"""
    res = validator.validate(code, tools=sample_tools, test_plan=sample_test_plan)
    assert res.is_valid is False
    assert "SCENARIO-01" not in res.identified_scenarios


def test_r2_try_finally_both_executed(sample_tools):
    """R2: Calls in try and finally both execute nominally."""
    test_plan = TestPlan(
        plan_id="plan-p2",
        target_server_summary="Two-step plan",
        scenarios=[
            TestScenario(
                scenario_id="S-MULTI",
                title="Multi step",
                objective="Try and finally execution",
                steps=[
                    TestStep(step_index=1, tool_name="read_file", arguments={"path": "README.md"}),
                    TestStep(step_index=2, tool_name="list_files", arguments={"directory": "src"}),
                ],
            )
        ],
    )
    validator = HarnessValidator()
    code = """
import pytest

@pytest.mark.scenario("S-MULTI")
async def test_s_multi(session):
    try:
        await session.call_tool("read_file", {"path": "README.md"})
    finally:
        await session.call_tool("list_files", {"directory": "src"})
"""
    res = validator.validate(code, tools=sample_tools, test_plan=test_plan)
    assert res.is_valid is True
    assert "S-MULTI" in res.identified_scenarios


def test_r2_return_in_try_skips_after_finally(sample_tools, sample_test_plan):
    """R2: Return in try block executes finally but makes code after try-finally unreachable."""
    validator = HarnessValidator()
    code = """
import pytest

@pytest.mark.scenario("SCENARIO-01")
async def test_s1(session):
    try:
        return
    finally:
        pass
    await session.call_tool("read_file", {"path": "README.md"})
"""
    res = validator.validate(code, tools=sample_tools, test_plan=sample_test_plan)
    assert res.is_valid is False
    assert "SCENARIO-01" not in res.identified_scenarios



