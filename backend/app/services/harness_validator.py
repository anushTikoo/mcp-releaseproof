"""Static AST security and structural validator for generated Python test harnesses.

Enforces zero-code-execution safety policies:
- Strict module import allowlist (pytest, unittest, asyncio, typing, mcp, dataclasses, json, pydantic).
- Prohibition of system/OS, shell, network, filesystem, and reflection capabilities.
- Prohibition of dynamic execution (eval, exec, compile, __import__).
- Structural requirements (at least one valid test_* function, top-level module isolation).
- Tool invocation cross-referencing and deep recursive JSON schema compliance.
- Line count and AST node complexity limits.
"""

import ast
from enum import Enum
import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from app.schemas.harness import HarnessValidationResult
from app.schemas.inference import DiscoveredToolInput, TestPlan

logger = logging.getLogger(__name__)

# Narrow positive allowlist of explicitly permitted modules and submodules
EXPLICITLY_ALLOWED_MODULES: Set[str] = {
    "pytest",
    "asyncio",
    "typing",
    "dataclasses",
    "json",
    "pydantic",
    "mcp",
    "mcp.types",
    "mcp.client.session",
    "mcp.shared.exceptions",
}

# Supported JSON Schema keywords (narrow positive allowlist)
SUPPORTED_SCHEMA_KEYWORDS: Set[str] = {
    "type",
    "description",
    "title",
    "default",
    "properties",
    "required",
    "additionalProperties",
    "minProperties",
    "maxProperties",
    "items",
    "minItems",
    "maxItems",
    "minLength",
    "maxLength",
    "enum",
    "minimum",
    "maximum",
}

# Explicit Allowlist of permissible top-level modules
ALLOWED_TOP_LEVEL_MODULES: Set[str] = {
    "pytest",
    "asyncio",
    "typing",
    "mcp",
    "dataclasses",
    "json",
    "pydantic",
}

# Submodules specifically known and permitted
ALLOWED_MODULE_PREFIXES: Tuple[str, ...] = (
    "pytest",
    "asyncio",
    "typing",
    "mcp",
    "mcp.types",
    "mcp.client.session",
    "mcp.shared.exceptions",
    "dataclasses",
    "json",
    "pydantic",
)

# Prohibited function / callable / builtin names (checked on Call, bare Name, and imports)
PROHIBITED_CALLS: Set[str] = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "open",
    "file",
    "input",
    "globals",
    "locals",
    "vars",
    "breakpoint",
    "getattr",
    "setattr",
    "delattr",
    "hasattr",
    "importorskip",
    # Subprocess and shell execution capabilities
    "create_subprocess_shell",
    "create_subprocess_exec",
    "subprocess_shell",
    "subprocess_exec",
    "subprocess",
    "system",
    "popen",
    "Popen",
    "spawn",
    "fork",
    "kill",
    "terminate",
    "execv",
    "execve",
    "execl",
    "execle",
    "execlp",
    "execvp",
    "execvpe",
    "stdio_client",
    "stdio",
    "main",
    # Network and socket capabilities
    "open_connection",
    "start_server",
    "open_unix_connection",
    "start_unix_server",
    "create_connection",
    "create_server",
    "create_unix_connection",
    "create_unix_server",
    "create_datagram_endpoint",
    "connect_accepted_socket",
    "start_tls",
    "sendfile",
    "sock_sendfile",
    "add_reader",
    "add_writer",
    "connect_read_pipe",
    "connect_write_pipe",
    "sock_recv",
    "sock_recv_into",
    "sock_recvfrom",
    "sock_recvfrom_into",
    "sock_sendall",
    "sock_sendto",
    "sock_connect",
    "sock_accept",
    "getaddrinfo",
    "getnameinfo",
    "socket",
    "connect",
    "listen",
    "bind",
    "sse_client",
    "sse",
    "SSEClient",
    "streamable_http",
    "streamable",
    "StreamableHTTPTransport",
    "websocket",
    "websockets",
    "WebSocketClient",
    "transport",
    "StdioServerParameters",
    # Data-driven dynamic imports, mocks, and reflection APIs
    "get_type_hints",
    "ImportString",
    "_importer",
    "TypeAdapter",
    "validate_python",
    "ForwardRef",
    "pytest_plugins",
    "patch",
    "get_original",
    "Mock",
    "MagicMock",
    "mock_open",
    "NonCallableMock",
    "PropertyMock",
    # Reflection, frame inspection, and executor escapes
    "cr_frame",
    "cr_code",
    "cr_await",
    "gi_frame",
    "gi_code",
    "gi_yieldfrom",
    "ag_frame",
    "ag_code",
    "ag_await",
    "tb_frame",
    "tb_next",
    "f_globals",
    "f_builtins",
    "f_locals",
    "f_code",
    "f_back",
    "f_trace",
    "run_in_executor",
}

# Prohibited attributes and reflection escapes
PROHIBITED_ATTRS: Set[str] = {
    "__builtins__",
    "__subclasses__",
    "__globals__",
    "__code__",
    "__class__",
    "__bases__",
    "__mro__",
    "__getattribute__",
    "__dict__",
    "__reduce__",
    "__reduce_ex__",
    "__annotations__",
    "__loader__",
    "__spec__",
    "environ",
    "getenv",
    "system",
    "popen",
    "Popen",
    "spawn",
    "fork",
    "importorskip",
    "mro",
    # Subprocess and shell execution capabilities
    "create_subprocess_shell",
    "create_subprocess_exec",
    "subprocess_shell",
    "subprocess_exec",
    "subprocess",
    "kill",
    "terminate",
    "execv",
    "execve",
    "execl",
    "execle",
    "execlp",
    "execvp",
    "execvpe",
    "stdio_client",
    "stdio",
    "main",
    # Network and socket capabilities
    "open_connection",
    "start_server",
    "open_unix_connection",
    "start_unix_server",
    "create_connection",
    "create_server",
    "create_unix_connection",
    "create_unix_server",
    "create_datagram_endpoint",
    "connect_accepted_socket",
    "start_tls",
    "sendfile",
    "sock_sendfile",
    "add_reader",
    "add_writer",
    "connect_read_pipe",
    "connect_write_pipe",
    "sock_recv",
    "sock_recv_into",
    "sock_recvfrom",
    "sock_recvfrom_into",
    "sock_sendall",
    "sock_sendto",
    "sock_connect",
    "sock_accept",
    "getaddrinfo",
    "getnameinfo",
    "socket",
    "connect",
    "listen",
    "bind",
    "sse_client",
    "sse",
    "SSEClient",
    "streamable_http",
    "streamable",
    "StreamableHTTPTransport",
    "websocket",
    "websockets",
    "WebSocketClient",
    "transport",
    "StdioServerParameters",
    # Data-driven dynamic imports, mocks, and reflection APIs
    "get_type_hints",
    "ImportString",
    "_importer",
    "TypeAdapter",
    "validate_python",
    "ForwardRef",
    "pytest_plugins",
    "patch",
    "get_original",
    "Mock",
    "MagicMock",
    "mock_open",
    "NonCallableMock",
    "PropertyMock",
    # Reflection, frame inspection, and executor escapes
    "cr_frame",
    "cr_code",
    "cr_await",
    "gi_frame",
    "gi_code",
    "gi_yieldfrom",
    "ag_frame",
    "ag_code",
    "ag_await",
    "tb_frame",
    "tb_next",
    "f_globals",
    "f_builtins",
    "f_locals",
    "f_code",
    "f_back",
    "f_trace",
    "run_in_executor",
}

# Unsupported JSON Schema constructs that fail closed upon detection
UNSUPPORTED_SCHEMA_CONSTRUCTS: Set[str] = {
    "anyOf",
    "oneOf",
    "allOf",
    "$ref",
    "$schema",
    "$defs",
    "definitions",
    "pattern",
    "format",
    "not",
    "patternProperties",
    "dependencies",
    "dependentRequired",
    "if",
    "then",
    "else",
}

# Explicitly permitted dunders on attribute lookups
ALLOWED_DUNDERS: Set[str] = {
    "__name__",
    "__doc__",
}

# Permissible top-level AST statement types in harness file body
ALLOWED_TOP_LEVEL_STATEMENTS = (
    ast.Import,
    ast.ImportFrom,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Assign,
    ast.AnnAssign,
)

MAX_HARNESS_BYTES: int = 65_536  # 64 KB
MAX_LINE_LENGTH: int = 2_000
MAX_HARNESS_LINES: int = 800
MAX_AST_NODES: int = 2500

# Inventory and Schema Resource Limits (R4)
MAX_TOOLS_PER_INVENTORY: int = 100
MAX_TOOL_SCHEMA_BYTES: int = 32_768  # 32 KB per tool schema
MAX_COMBINED_INVENTORY_BYTES: int = 262_144  # 256 KB combined serialized size for entire inventory
MAX_SCHEMA_NODES_PER_TOOL: int = 500
MAX_TOTAL_SCHEMA_NODES: int = 2_000
MAX_SCHEMA_NESTING_DEPTH: int = 20


def _count_schema_nodes(schema: Any, depth: int = 0) -> Tuple[int, int]:
    """Count total nodes (keys/values/elements) and max nesting depth in a schema tree."""
    if not isinstance(schema, dict):
        return (1, depth)
    nodes = 1
    max_d = depth
    for k, v in schema.items():
        nodes += 1
        if isinstance(v, dict):
            sub_nodes, sub_depth = _count_schema_nodes(v, depth + 1)
            nodes += sub_nodes
            max_d = max(max_d, sub_depth)
        elif isinstance(v, list):
            nodes += len(v)
            for item in v:
                if isinstance(item, dict):
                    sub_nodes, sub_depth = _count_schema_nodes(item, depth + 1)
                    nodes += sub_nodes
                    max_d = max(max_d, sub_depth)
    return (nodes, max_d)


class _SecurityASTVisitor(ast.NodeVisitor):
    """AST visitor that collects security violations, structural metadata, and tool calls."""

    def __init__(
        self,
        known_tools: Dict[str, DiscoveredToolInput],
        tools_available: bool = True,
    ):
        self.known_tools = known_tools
        self.tools_available = tools_available
        self.rejection_reasons: List[str] = []
        self.warnings: List[str] = []
        self.identified_imports: List[str] = []
        self.identified_tool_calls: List[str] = []
        self.test_functions: List[str] = []
        self.test_func_nodes: List[ast.AST] = []
        self.aliased_prohibited_names: Set[str] = set()
        self.node_count: int = 0
        self.syntax_valid: bool = True
        self.security_valid: bool = True
        self.structure_valid: bool = True
        self.schema_valid: bool = True

    def visit(self, node: ast.AST) -> None:
        self.node_count += 1
        super().visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            mod_name = alias.name
            asname = alias.asname
            self.identified_imports.append(mod_name)
            parts = mod_name.split(".")
            top_level = parts[0]
            if top_level not in ALLOWED_TOP_LEVEL_MODULES or mod_name not in EXPLICITLY_ALLOWED_MODULES:
                self.security_valid = False
                self.rejection_reasons.append(
                    f"Prohibited module import '{mod_name}' at line {node.lineno}. "
                    f"Only safe testing modules ({', '.join(sorted(ALLOWED_TOP_LEVEL_MODULES))}) are permitted."
                )
            for part in parts:
                if part in PROHIBITED_ATTRS or part in PROHIBITED_CALLS:
                    self.security_valid = False
                    self.rejection_reasons.append(
                        f"Prohibited module path segment '{part}' in '{mod_name}' at line {node.lineno}."
                    )
            if asname:
                if (
                    asname in PROHIBITED_CALLS
                    or asname in PROHIBITED_ATTRS
                    or (asname.startswith("__") and asname not in ALLOWED_DUNDERS)
                    or (asname.startswith("_") and asname not in ALLOWED_DUNDERS)
                    or asname == "pytest_plugins"
                ):
                    self.security_valid = False
                    self.rejection_reasons.append(
                        f"Prohibited import alias '{asname}' at line {node.lineno}."
                    )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level and node.level > 0:
            self.security_valid = False
            self.rejection_reasons.append(
                f"Prohibited relative import at line {node.lineno}. "
                "Harness must be self-contained and not access local filesystem modules."
            )
        mod_name = node.module or ""
        self.identified_imports.append(mod_name)
        parts = mod_name.split(".") if mod_name else []
        top_level = parts[0] if parts else ""
        if top_level not in ALLOWED_TOP_LEVEL_MODULES or mod_name not in EXPLICITLY_ALLOWED_MODULES:
            self.security_valid = False
            self.rejection_reasons.append(
                f"Prohibited module import '{mod_name}' at line {node.lineno}. "
                f"Only safe testing modules ({', '.join(sorted(ALLOWED_TOP_LEVEL_MODULES))}) are permitted."
            )
        for part in parts:
            if part in PROHIBITED_ATTRS or part in PROHIBITED_CALLS:
                self.security_valid = False
                self.rejection_reasons.append(
                    f"Prohibited module path segment '{part}' in '{mod_name}' at line {node.lineno}."
                )

        # Inspect all imported symbols and aliases in node.names
        for alias in node.names:
            sym_name = alias.name
            asname = alias.asname

            if sym_name == "*":
                self.security_valid = False
                self.rejection_reasons.append(
                    f"Wildcard import 'from {mod_name} import *' at line {node.lineno} is prohibited. "
                    "All imports must be explicit."
                )
                continue

            if sym_name == "ToolErrorResult" or (mod_name.startswith("mcp") and sym_name in ("ToolErrorResult", "ToolError")):
                self.security_valid = False
                self.rejection_reasons.append(
                    f"Prohibited import of unavailable symbol '{sym_name}' from '{mod_name}' at line {node.lineno}. "
                    "Use 'from mcp.types import CallToolResult, TextContent' and check 'CallToolResult.isError'."
                )

            if (sym_name.startswith("_") and sym_name not in ALLOWED_DUNDERS) or sym_name == "pytest_plugins":
                self.security_valid = False
                self.rejection_reasons.append(
                    f"Prohibited private symbol import '{sym_name}' from '{mod_name}' at line {node.lineno}."
                )
                if asname:
                    self.aliased_prohibited_names.add(asname)

            if (
                sym_name in PROHIBITED_CALLS
                or sym_name in PROHIBITED_ATTRS
                or (sym_name.startswith("__") and sym_name not in ALLOWED_DUNDERS)
            ):
                self.security_valid = False
                self.rejection_reasons.append(
                    f"Prohibited symbol import '{sym_name}' from '{mod_name}' at line {node.lineno}."
                )
                if asname:
                    self.aliased_prohibited_names.add(asname)

            if asname:
                if (
                    asname in PROHIBITED_CALLS
                    or asname in PROHIBITED_ATTRS
                    or (asname.startswith("__") and asname not in ALLOWED_DUNDERS)
                    or (asname.startswith("_") and asname not in ALLOWED_DUNDERS)
                    or asname == "pytest_plugins"
                ):
                    self.security_valid = False
                    self.rejection_reasons.append(
                        f"Prohibited alias '{asname}' for symbol '{sym_name}' at line {node.lineno}."
                    )
                if sym_name in PROHIBITED_CALLS or sym_name in PROHIBITED_ATTRS:
                    self.aliased_prohibited_names.add(asname)

        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        # Catch bare identifier references to prohibited builtins, escapes, and registered aliases
        name = node.id
        if name in ("ToolErrorResult", "ToolError"):
            self.security_valid = False
            self.rejection_reasons.append(
                f"Prohibited reference to unavailable symbol '{name}' at line {node.lineno}. "
                "Use 'CallToolResult.isError' and result content instead."
            )
        if (
            name in PROHIBITED_CALLS
            or name in PROHIBITED_ATTRS
            or name in self.aliased_prohibited_names
            or name == "__builtins__"
        ):
            self.security_valid = False
            self.rejection_reasons.append(
                f"Prohibited identifier reference '{name}' at line {node.lineno}."
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Check direct function calls (e.g. eval(), open(), safe_import())
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if (
                func_name in PROHIBITED_CALLS
                or func_name in PROHIBITED_ATTRS
                or func_name in self.aliased_prohibited_names
            ):
                self.security_valid = False
                self.rejection_reasons.append(
                    f"Prohibited dangerous function call '{func_name}()' at line {node.lineno}."
                )
        elif isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            if attr_name in PROHIBITED_CALLS or attr_name in PROHIBITED_ATTRS:
                self.security_valid = False
                self.rejection_reasons.append(
                    f"Prohibited callable attribute '{attr_name}()' at line {node.lineno}."
                )

            # Inspect tool invocation: session.call_tool("tool_name", {...})
            if attr_name == "call_tool":
                self._inspect_tool_call(node)

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        attr = node.attr
        # Strict fail-closed rule on dunders: all dunder attributes rejected except ALLOWED_DUNDERS
        if attr.startswith("__") and attr.endswith("__"):
            if attr not in ALLOWED_DUNDERS:
                self.security_valid = False
                self.rejection_reasons.append(
                    f"Prohibited attribute or reflection escape '{attr}' at line {node.lineno}."
                )
        elif attr in PROHIBITED_ATTRS or attr in PROHIBITED_CALLS:
            self.security_valid = False
            self.rejection_reasons.append(
                f"Prohibited attribute or reflection escape '{attr}' at line {node.lineno}."
            )
        self.generic_visit(node)

    def _is_safe_type_annotation(self, node: Optional[ast.AST]) -> bool:
        """Check whether an AST node is a strictly static type annotation using a narrow positive allowlist.

        Permits only:
        - ast.Name (safe identifiers, not prohibited calls/attrs/dunders/private identifiers)
        - ast.Constant (literal None, safe str forward-ref)
        - ast.Subscript (e.g. List[str], Dict[str, Any], Optional[int])
        - ast.Attribute (e.g. typing.List, mcp.types.CallToolResult with safe value & attr)
        - ast.BinOp with ast.BitOr (e.g. int | None)
        - ast.Tuple / ast.List of safe annotations (e.g. Union[int, str] slice)

        Rejects any executable expressions: Calls, comprehensions, lambdas, binops other than BitOr,
        unary ops, comparisons, walrus expressions, yields, awaits, etc.
        """
        if node is None:
            return True
        if isinstance(node, ast.Name):
            return (
                node.id not in PROHIBITED_CALLS
                and node.id not in PROHIBITED_ATTRS
                and node.id not in getattr(self, "aliased_prohibited_names", set())
                and (not node.id.startswith("__") or node.id in ALLOWED_DUNDERS)
                and not node.id.startswith("_")
            )
        if isinstance(node, ast.Constant):
            if node.value is None:
                return True
            if isinstance(node.value, str):
                clean_str = node.value.strip()
                if not clean_str or len(clean_str) > 200:
                    return False
                if any(bad in clean_str for bad in ("__", "import", "exec", "eval", "system", "subprocess", "open", ";", "\n", "\r")):
                    return False
                try:
                    parsed = ast.parse(clean_str, mode="eval")
                    return self._is_safe_type_annotation(parsed.body)
                except Exception:
                    return False
            return False
        if isinstance(node, ast.Subscript):
            return self._is_safe_type_annotation(node.value) and self._is_safe_type_annotation(node.slice)
        if isinstance(node, ast.Attribute):
            if node.attr in PROHIBITED_CALLS or node.attr in PROHIBITED_ATTRS:
                return False
            if node.attr.startswith("_") and node.attr not in ALLOWED_DUNDERS:
                return False
            return self._is_safe_type_annotation(node.value)
        if isinstance(node, ast.BinOp):
            return (
                isinstance(node.op, ast.BitOr)
                and self._is_safe_type_annotation(node.left)
                and self._is_safe_type_annotation(node.right)
            )
        if isinstance(node, (ast.Tuple, ast.List)):
            return all(self._is_safe_type_annotation(elt) for elt in node.elts)
        return False

    def _check_assign_target(self, target: ast.AST, lineno: int) -> None:
        if isinstance(target, ast.Name):
            if target.id == "pytest_plugins":
                self.security_valid = False
                self.rejection_reasons.append(
                    f"Prohibited assignment to 'pytest_plugins' at line {lineno}. "
                    "Pytest plugin injection is forbidden."
                )
            elif target.id in PROHIBITED_CALLS or target.id in PROHIBITED_ATTRS:
                self.security_valid = False
                self.rejection_reasons.append(
                    f"Prohibited assignment to protected identifier '{target.id}' at line {lineno}."
                )
        elif isinstance(target, ast.Attribute):
            if target.attr == "pytest_plugins":
                self.security_valid = False
                self.rejection_reasons.append(
                    f"Prohibited assignment to 'pytest_plugins' at line {lineno}. "
                    "Pytest plugin injection is forbidden."
                )

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._check_assign_target(target, node.lineno)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._check_assign_target(node.target, node.lineno)
        if not self._is_safe_type_annotation(node.annotation):
            self.security_valid = False
            self.rejection_reasons.append(
                f"Prohibited executable expression '{type(node.annotation).__name__}' in type annotation at line {node.lineno}. "
                "Annotations must strictly adhere to the static type allowlist."
            )
        self.generic_visit(node)

    def _is_safe_decorator(self, dec: ast.AST) -> Tuple[bool, str]:
        """Validate that a decorator is a static, safe attribute or call (e.g. pytest.mark.asyncio)."""
        if isinstance(dec, (ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp, ast.Lambda, ast.Subscript)):
            return False, f"dynamic or comprehension decorator '{type(dec).__name__}'"

        target = dec
        if isinstance(dec, ast.Call):
            target = dec.func
            # Check arguments to decorator call
            for arg in dec.args:
                if isinstance(arg, (ast.Call, ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp, ast.Lambda)):
                    return False, "dynamic call or expression inside decorator arguments"
            for kw in dec.keywords:
                if isinstance(kw.value, (ast.Call, ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp, ast.Lambda)):
                    return False, "dynamic call or expression inside decorator keyword arguments"

        # Check decorator target (must be safe identifier or attribute chain)
        if isinstance(target, ast.Name):
            name = target.id
            if name in PROHIBITED_CALLS or name in PROHIBITED_ATTRS or name in getattr(self, "aliased_prohibited_names", set()):
                return False, f"prohibited decorator identifier '{name}'"
            if name.startswith("_") and name not in ALLOWED_DUNDERS:
                return False, f"prohibited private decorator '{name}'"
            return True, ""
        elif isinstance(target, ast.Attribute):
            # Check whole attribute chain (e.g. pytest.mark.asyncio, pytest.fixture, etc.)
            curr: ast.AST = target
            while isinstance(curr, ast.Attribute):
                attr = curr.attr
                if attr in PROHIBITED_CALLS or attr in PROHIBITED_ATTRS:
                    return False, f"prohibited decorator attribute '{attr}'"
                if attr.startswith("_") and attr not in ALLOWED_DUNDERS:
                    return False, f"prohibited private decorator attribute '{attr}'"
                curr = curr.value
            if isinstance(curr, ast.Name):
                name = curr.id
                if name in PROHIBITED_CALLS or name in PROHIBITED_ATTRS:
                    return False, f"prohibited decorator base identifier '{name}'"
                if name not in ALLOWED_TOP_LEVEL_MODULES:
                    return False, f"decorator from unauthorized module '{name}'"
                return True, ""
            return False, f"unsupported decorator expression '{type(curr).__name__}'"

        return False, f"unsupported decorator expression '{type(target).__name__}'"

    def _validate_function_signature_and_decorators(self, node: ast.AST) -> None:
        """Validate decorators, default arguments, and type annotations to prevent import-time execution."""
        # 1. Decorator validation
        decorator_list = getattr(node, "decorator_list", [])
        for dec in decorator_list:
            is_safe, reason = self._is_safe_decorator(dec)
            if not is_safe:
                self.security_valid = False
                self.rejection_reasons.append(
                    f"Prohibited dynamic or executable decorator on '{getattr(node, 'name', 'callable')}' at line {getattr(dec, 'lineno', node.lineno)}: {reason}."
                )

        # 2. Default argument values validation
        args_obj = getattr(node, "args", None)
        if args_obj:
            defaults = list(args_obj.defaults) + [d for d in args_obj.kw_defaults if d is not None]
            for d in defaults:
                if not isinstance(d, ast.Constant):
                    self.security_valid = False
                    self.rejection_reasons.append(
                        f"Prohibited dynamic default argument '{type(d).__name__}' at line {node.lineno}. "
                        "Default arguments must be literal constants or None to prevent import-time execution."
                    )

            # 3. Parameter and return annotations validation
            all_annotations = [
                arg.annotation
                for arg in (args_obj.args + args_obj.posonlyargs + args_obj.kwonlyargs)
                if arg.annotation is not None
            ]
            if args_obj.vararg and args_obj.vararg.annotation:
                all_annotations.append(args_obj.vararg.annotation)
            if args_obj.kwarg and args_obj.kwarg.annotation:
                all_annotations.append(args_obj.kwarg.annotation)
            returns = getattr(node, "returns", None)
            if returns:
                all_annotations.append(returns)

            for ann in all_annotations:
                if not self._is_safe_type_annotation(ann):
                    self.security_valid = False
                    self.rejection_reasons.append(
                        f"Prohibited executable expression '{type(ann).__name__}' inside type annotation at line {node.lineno}. "
                        "Annotations must be static type expressions."
                    )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # 1. Decorator validation
        for dec in node.decorator_list:
            is_safe, reason = self._is_safe_decorator(dec)
            if not is_safe:
                self.security_valid = False
                self.rejection_reasons.append(
                    f"Prohibited class decorator on '{node.name}' at line {getattr(dec, 'lineno', node.lineno)}: {reason}."
                )

        # 2. Bases validation (reject calls like patch("..."), reflection, or dynamic expressions)
        for base in node.bases:
            if isinstance(base, ast.Call):
                self.security_valid = False
                self.rejection_reasons.append(
                    f"Prohibited dynamic call in class base for '{node.name}' at line {node.lineno}. "
                    "Class inheritance must reference static base classes."
                )
            elif isinstance(base, (ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp, ast.Lambda)):
                self.security_valid = False
                self.rejection_reasons.append(
                    f"Prohibited comprehension or lambda in class base for '{node.name}' at line {node.lineno}."
                )
            elif isinstance(base, ast.Name):
                if base.id in PROHIBITED_CALLS or base.id in PROHIBITED_ATTRS or base.id in getattr(self, "aliased_prohibited_names", set()):
                    self.security_valid = False
                    self.rejection_reasons.append(
                        f"Prohibited identifier '{base.id}' in class base for '{node.name}' at line {node.lineno}."
                    )
            elif isinstance(base, ast.Attribute):
                if base.attr in PROHIBITED_CALLS or base.attr in PROHIBITED_ATTRS:
                    self.security_valid = False
                    self.rejection_reasons.append(
                        f"Prohibited attribute '{base.attr}' in class base for '{node.name}' at line {node.lineno}."
                    )

        # 3. Class keywords validation (e.g. metaclass=...)
        for kw in node.keywords:
            if isinstance(kw.value, ast.Call):
                self.security_valid = False
                self.rejection_reasons.append(
                    f"Prohibited dynamic call in class keyword argument for '{node.name}' at line {node.lineno}."
                )

        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._validate_function_signature_and_decorators(node)
        if node.name.startswith("test_"):
            self.test_functions.append(node.name)
            self.test_func_nodes.append(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._validate_function_signature_and_decorators(node)
        if node.name.startswith("test_"):
            self.test_functions.append(node.name)
            self.test_func_nodes.append(node)
        self.generic_visit(node)

    def _find_unsupported_schema_construct(
        self, schema: Any, path: str = "root", depth: int = 0
    ) -> Optional[str]:
        """Recursively scan a JSON Schema definition for unsupported, null, or malformed constructs.

        Fails closed upfront if any unsupported keyword, null-valued keyword, union type,
        untyped array, unknown type, or inconsistent constraint bounds exist anywhere in the schema tree.
        """
        if depth > MAX_SCHEMA_NESTING_DEPTH:
            return f"Schema at '{path}' exceeds maximum allowable nesting depth ({MAX_SCHEMA_NESTING_DEPTH})."

        if not isinstance(schema, dict):
            return f"Schema at '{path}' must be a dictionary object, got {type(schema).__name__}."

        # Check explicit unsupported keywords first
        for construct in UNSUPPORTED_SCHEMA_CONSTRUCTS:
            if construct in schema:
                return f"Schema at '{path}' contains unsupported construct '{construct}'."

        # Check positive allowlist of supported keywords for any other unrecognized keywords
        unsupported_keys = set(schema.keys()) - SUPPORTED_SCHEMA_KEYWORDS
        if unsupported_keys:
            return (
                f"Schema at '{path}' contains unsupported construct(s) {sorted(list(unsupported_keys))}. "
                "Static AST validation fails closed on unsupported schema constructs."
            )

        # Check type validity if specified (distinguishing missing from explicit null)
        if "type" in schema:
            expected_type = schema["type"]
            if expected_type is None:
                return f"Schema at '{path}' specifies null 'type'."
            if isinstance(expected_type, list):
                return f"Schema at '{path}' specifies unsupported union type {expected_type}."
            if expected_type not in {"string", "integer", "number", "boolean", "array", "object"}:
                return f"Schema at '{path}' specifies unsupported type {repr(expected_type)}."
        else:
            expected_type = None

        # Check enum validity if specified
        if "enum" in schema:
            enum_val = schema["enum"]
            if enum_val is None:
                return f"Schema at '{path}' has null 'enum'."
            if not isinstance(enum_val, (list, tuple)):
                return f"Schema at '{path}' has invalid enum {repr(enum_val)} (must be a list or tuple)."
            if len(enum_val) == 0:
                return f"Schema at '{path}' has empty enum list."

        # Validate constraint bounds if present (rejecting explicit null values)
        if "minLength" in schema:
            min_len = schema["minLength"]
            if min_len is None or not isinstance(min_len, int) or isinstance(min_len, bool) or min_len < 0:
                return f"Schema at '{path}' has invalid or null minLength {repr(min_len)} (must be non-negative integer)."
        else:
            min_len = None

        if "maxLength" in schema:
            max_len = schema["maxLength"]
            if max_len is None or not isinstance(max_len, int) or isinstance(max_len, bool) or max_len < 0:
                return f"Schema at '{path}' has invalid or null maxLength {repr(max_len)} (must be non-negative integer)."
        else:
            max_len = None

        if min_len is not None and max_len is not None and min_len > max_len:
            return f"Schema at '{path}' has minLength {min_len} > maxLength {max_len}."

        if "minimum" in schema:
            min_val = schema["minimum"]
            if min_val is None or not isinstance(min_val, (int, float)) or isinstance(min_val, bool):
                return f"Schema at '{path}' has invalid or null minimum {repr(min_val)} (must be a number)."
        else:
            min_val = None

        if "maximum" in schema:
            max_val = schema["maximum"]
            if max_val is None or not isinstance(max_val, (int, float)) or isinstance(max_val, bool):
                return f"Schema at '{path}' has invalid or null maximum {repr(max_val)} (must be a number)."
        else:
            max_val = None

        if min_val is not None and max_val is not None and min_val > max_val:
            return f"Schema at '{path}' has minimum {min_val} > maximum {max_val}."

        if "minItems" in schema:
            min_items = schema["minItems"]
            if min_items is None or not isinstance(min_items, int) or isinstance(min_items, bool) or min_items < 0:
                return f"Schema at '{path}' has invalid or null minItems {repr(min_items)} (must be non-negative integer)."
        else:
            min_items = None

        if "maxItems" in schema:
            max_items = schema["maxItems"]
            if max_items is None or not isinstance(max_items, int) or isinstance(max_items, bool) or max_items < 0:
                return f"Schema at '{path}' has invalid or null maxItems {repr(max_items)} (must be non-negative integer)."
        else:
            max_items = None

        if min_items is not None and max_items is not None and min_items > max_items:
            return f"Schema at '{path}' has minItems {min_items} > maxItems {max_items}."

        if "minProperties" in schema:
            min_props = schema["minProperties"]
            if min_props is None or not isinstance(min_props, int) or isinstance(min_props, bool) or min_props < 0:
                return f"Schema at '{path}' has invalid or null minProperties {repr(min_props)} (must be non-negative integer)."
        else:
            min_props = None

        if "maxProperties" in schema:
            max_props = schema["maxProperties"]
            if max_props is None or not isinstance(max_props, int) or isinstance(max_props, bool) or max_props < 0:
                return f"Schema at '{path}' has invalid or null maxProperties {repr(max_props)} (must be non-negative integer)."
        else:
            max_props = None

        if min_props is not None and max_props is not None and min_props > max_props:
            return f"Schema at '{path}' has minProperties {min_props} > maxProperties {max_props}."

        if "required" in schema:
            req = schema["required"]
            if req is None or not isinstance(req, list):
                return f"Schema at '{path}' has invalid or null required field (must be list of non-empty strings)."
            for item in req:
                if not isinstance(item, str) or not item.strip():
                    return f"Schema at '{path}' required field contains invalid non-string or empty element: {repr(item)}."

        # Array must specify valid items schema
        if expected_type == "array":
            if "items" not in schema:
                return f"Schema at '{path}' is an array but lacks a valid 'items' object schema."
            items = schema["items"]
            if items is None or not isinstance(items, dict):
                return f"Schema at '{path}' is an array but has invalid or null 'items' schema."
            err = self._find_unsupported_schema_construct(items, f"{path}.items", depth + 1)
            if err:
                return err
        elif "items" in schema:
            items = schema["items"]
            if items is None or not isinstance(items, dict):
                return f"Schema at '{path}' has invalid or null 'items' schema."
            err = self._find_unsupported_schema_construct(items, f"{path}.items", depth + 1)
            if err:
                return err

        # Object properties
        if "properties" in schema:
            props = schema["properties"]
            if props is None or not isinstance(props, dict):
                return f"Schema at '{path}' 'properties' must be a non-null dictionary."
            for prop_name, prop_schema in props.items():
                if not isinstance(prop_name, str):
                    return f"Schema at '{path}.properties' contains non-string property key: {repr(prop_name)}."
                err = self._find_unsupported_schema_construct(prop_schema, f"{path}.{prop_name}", depth + 1)
                if err:
                    return err

        if "additionalProperties" in schema:
            add_props = schema["additionalProperties"]
            if add_props is None:
                return f"Schema at '{path}' has null 'additionalProperties'."
            if isinstance(add_props, dict):
                err = self._find_unsupported_schema_construct(add_props, f"{path}.additionalProperties", depth + 1)
                if err:
                    return err
            elif not isinstance(add_props, bool):
                return f"Schema at '{path}' has invalid additionalProperties {repr(add_props)} (must be boolean or object schema)."

        if "description" in schema:
            desc = schema["description"]
            if desc is not None and not isinstance(desc, str):
                return f"Schema at '{path}' has non-string description."

        if "title" in schema:
            title = schema["title"]
            if title is not None and not isinstance(title, str):
                return f"Schema at '{path}' has non-string title."

        return None

        return None

    def _inspect_tool_call(self, node: ast.Call) -> None:
        """Inspect arguments to call_tool(...) and validate tool existence & schemas."""
        # Fail-closed check: if tool inventory is unavailable/empty
        if not self.tools_available or not self.known_tools:
            self.schema_valid = False
            self.rejection_reasons.append(
                f"Tool call at line {node.lineno} cannot be validated because discovered tool inventory is empty or unavailable."
            )
            return

        tool_name: Optional[str] = None
        args_node: Optional[ast.AST] = None

        # Positional arguments: call_tool("name", {...})
        if node.args:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                tool_name = first_arg.value
            else:
                self.schema_valid = False
                self.rejection_reasons.append(
                    f"Dynamic or non-literal tool name passed to call_tool at line {node.lineno}. Tool names must be literal strings."
                )
                return

            if len(node.args) > 1:
                args_node = node.args[1]

        # Keyword arguments: call_tool(name="...", arguments={...})
        for kw in node.keywords:
            if kw.arg in ("name", "tool_name"):
                if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    tool_name = kw.value.value
                else:
                    self.schema_valid = False
                    self.rejection_reasons.append(
                        f"Dynamic or non-literal tool name passed to call_tool at line {node.lineno}. Tool names must be literal strings."
                    )
                    return
            elif kw.arg == "arguments":
                args_node = kw.value

        if not tool_name:
            self.schema_valid = False
            self.rejection_reasons.append(
                f"Tool invocation at line {node.lineno} did not specify a valid literal tool name."
            )
            return

        self.identified_tool_calls.append(tool_name)
        if tool_name not in self.known_tools:
            self.schema_valid = False
            valid_tools = sorted(list(self.known_tools.keys()))
            self.rejection_reasons.append(
                f"Referenced unknown MCP tool '{tool_name}' at line {node.lineno}. "
                f"Discovered tools for this server: {valid_tools}."
            )
            return

        tool_def = self.known_tools[tool_name]
        schema = tool_def.input_schema or {}

        # Scan the entire schema upfront for unsupported constructs
        schema_err = self._find_unsupported_schema_construct(schema, f"tool '{tool_name}'")
        if schema_err:
            self.schema_valid = False
            self.rejection_reasons.append(
                f"{schema_err} Static AST validation fails closed on unsupported schema constructs."
            )
            return

        # Fail closed on unsupported constructs in root schema
        for construct in UNSUPPORTED_SCHEMA_CONSTRUCTS:
            if construct in schema:
                self.schema_valid = False
                self.rejection_reasons.append(
                    f"Tool '{tool_name}' schema contains unsupported construct '{construct}'. "
                    "Static AST validation fails closed on unsupported schema constructs."
                )
                return

        # Validate arguments expression
        if args_node is not None:
            if not isinstance(args_node, ast.Dict):
                # Dynamic arguments that cannot be statically verified fail closed
                self.schema_valid = False
                self.rejection_reasons.append(
                    f"Tool call '{tool_name}' at line {node.lineno} passes dynamic, non-literal arguments "
                    f"({type(args_node).__name__}). Arguments must be statically verifiable literal dictionaries."
                )
                return
            self._validate_ast_dict_against_schema(
                tool_name=tool_name,
                path_prefix="",
                dict_node=args_node,
                schema=schema,
                lineno=node.lineno,
            )
        else:
            # No arguments passed - check if schema has required fields
            required_fields = schema.get("required") or []
            if required_fields:
                self.schema_valid = False
                self.rejection_reasons.append(
                    f"Tool call '{tool_name}' at line {node.lineno} provides no arguments, but required fields "
                    f"{required_fields} are declared."
                )

    def _validate_ast_dict_against_schema(
        self,
        tool_name: str,
        path_prefix: str,
        dict_node: ast.Dict,
        schema: Dict[str, Any],
        lineno: int,
    ) -> None:
        """Recursively validate an AST Dict literal against declared JSON Schema object constraints."""
        # Fail closed on unsupported constructs in object schema
        for construct in UNSUPPORTED_SCHEMA_CONSTRUCTS:
            if construct in schema:
                self.schema_valid = False
                self.rejection_reasons.append(
                    f"Tool '{tool_name}' {path_prefix or 'root'} schema contains unsupported construct '{construct}'. "
                    "Static AST validation fails closed on unsupported schema constructs."
                )
                return

        required_fields = schema.get("required") or []
        declared_properties = schema.get("properties") or {}
        additional_props = schema.get("additionalProperties", True)

        # Check declared properties for unsupported constructs
        for prop_name, prop_schema in declared_properties.items():
            if isinstance(prop_schema, dict):
                for construct in UNSUPPORTED_SCHEMA_CONSTRUCTS:
                    if construct in prop_schema:
                        self.schema_valid = False
                        self.rejection_reasons.append(
                            f"Tool '{tool_name}' argument '{prop_name}' schema contains unsupported construct '{construct}'. "
                            "Static AST validation fails closed on unsupported schema constructs."
                        )
                        return

        provided_keys: Set[str] = set()
        provided_pairs: List[Tuple[str, ast.AST]] = []

        for k_node, v_node in zip(dict_node.keys, dict_node.values):
            if k_node is None:
                # Dict unpacking like {**some_dict}
                self.schema_valid = False
                self.rejection_reasons.append(
                    f"Tool call '{tool_name}' at line {lineno} uses dictionary unpacking ({path_prefix or 'root'}). "
                    "Arguments must be explicit literal dictionary keys."
                )
                return
            if isinstance(k_node, ast.Constant) and isinstance(k_node.value, str):
                key_str = k_node.value
                provided_keys.add(key_str)
                provided_pairs.append((key_str, v_node))
            else:
                self.schema_valid = False
                self.rejection_reasons.append(
                    f"Tool call '{tool_name}' at line {lineno} contains non-string literal argument key. "
                    "Keys must be static string constants."
                )
                return

        # 1. Required properties check
        for req in required_fields:
            if not isinstance(req, str):
                continue
            if req not in provided_keys:
                self.schema_valid = False
                field_label = f"{path_prefix}.{req}" if path_prefix else req
                self.rejection_reasons.append(
                    f"Tool call '{tool_name}' at line {lineno} missing required argument '{field_label}' "
                    f"per declared schema (required: {required_fields})."
                )

        # 2. additionalProperties: false check
        if additional_props is False:
            unknown_keys = provided_keys - set(declared_properties.keys())
            if unknown_keys:
                self.schema_valid = False
                self.rejection_reasons.append(
                    f"Tool call '{tool_name}' at line {lineno} specifies undeclared arguments "
                    f"{sorted(list(unknown_keys))} (additionalProperties is False)."
                )

        # 3. minProperties and maxProperties checks
        min_props = schema.get("minProperties")
        if isinstance(min_props, int) and len(provided_keys) < min_props:
            self.schema_valid = False
            self.rejection_reasons.append(
                f"Tool call '{tool_name}' at line {lineno} specifies {len(provided_keys)} arguments, "
                f"which is less than minProperties ({min_props})."
            )
        max_props = schema.get("maxProperties")
        if isinstance(max_props, int) and len(provided_keys) > max_props:
            self.schema_valid = False
            self.rejection_reasons.append(
                f"Tool call '{tool_name}' at line {lineno} specifies {len(provided_keys)} arguments, "
                f"which exceeds maxProperties ({max_props})."
            )

        # 4. Recursive value validation for declared properties and schema-valued additionalProperties
        for key_str, v_node in provided_pairs:
            full_param_name = f"{path_prefix}.{key_str}" if path_prefix else key_str
            if key_str in declared_properties:
                prop_schema = declared_properties[key_str]
                if isinstance(prop_schema, dict):
                    self._validate_ast_value_against_schema(
                        tool_name=tool_name,
                        param_path=full_param_name,
                        val_node=v_node,
                        param_schema=prop_schema,
                        lineno=lineno,
                    )
            elif isinstance(additional_props, dict):
                self._validate_ast_value_against_schema(
                    tool_name=tool_name,
                    param_path=full_param_name,
                    val_node=v_node,
                    param_schema=additional_props,
                    lineno=lineno,
                )

    def _check_numeric_bounds(
        self,
        tool_name: str,
        param_path: str,
        val: Any,
        param_schema: Dict[str, Any],
        lineno: int,
    ) -> None:
        min_val = param_schema.get("minimum")
        if (isinstance(min_val, (int, float)) and not isinstance(min_val, bool)) and val < min_val:
            self.schema_valid = False
            self.rejection_reasons.append(
                f"Tool '{tool_name}' argument '{param_path}' at line {lineno} "
                f"value ({val}) is less than minimum ({min_val})."
            )
        max_val = param_schema.get("maximum")
        if (isinstance(max_val, (int, float)) and not isinstance(max_val, bool)) and val > max_val:
            self.schema_valid = False
            self.rejection_reasons.append(
                f"Tool '{tool_name}' argument '{param_path}' at line {lineno} "
                f"value ({val}) exceeds maximum ({max_val})."
            )

    def _validate_ast_value_against_schema(
        self,
        tool_name: str,
        param_path: str,
        val_node: ast.AST,
        param_schema: Dict[str, Any],
        lineno: int,
    ) -> None:
        """Validate literal AST value node against declared JSON Schema constraints (type, enum, items)."""
        # Fail closed on unsupported constructs
        for construct in UNSUPPORTED_SCHEMA_CONSTRUCTS:
            if construct in param_schema:
                self.schema_valid = False
                self.rejection_reasons.append(
                    f"Tool '{tool_name}' argument '{param_path}' schema contains unsupported construct '{construct}'. "
                    "Static AST validation fails closed on unsupported schema constructs."
                )
                return

        expected_type = param_schema.get("type")

        # Fail closed on union types (e.g. ["string", "null"])
        if isinstance(expected_type, list):
            self.schema_valid = False
            self.rejection_reasons.append(
                f"Tool '{tool_name}' argument '{param_path}' specifies unsupported union type {expected_type}. "
                "Static AST validation fails closed on union types."
            )
            return

        # Enum check
        if "enum" in param_schema:
            allowed_enums = param_schema["enum"]
            if not isinstance(allowed_enums, (list, tuple)):
                self.schema_valid = False
                self.rejection_reasons.append(
                    f"Tool '{tool_name}' argument '{param_path}' has malformed 'enum' schema (must be list or tuple)."
                )
                return
            num = self._extract_numeric_constant(val_node)
            if num is not None:
                val = num[1]
                if val not in allowed_enums:
                    self.schema_valid = False
                    self.rejection_reasons.append(
                        f"Tool '{tool_name}' argument '{param_path}' at line {lineno} "
                        f"has value {repr(val)} which is not in allowed enum {allowed_enums}."
                    )
            elif isinstance(val_node, ast.Constant):
                if val_node.value not in allowed_enums:
                    self.schema_valid = False
                    self.rejection_reasons.append(
                        f"Tool '{tool_name}' argument '{param_path}' at line {lineno} "
                        f"has value {repr(val_node.value)} which is not in allowed enum {allowed_enums}."
                    )
            else:
                self.schema_valid = False
                self.rejection_reasons.append(
                    f"Tool '{tool_name}' argument '{param_path}' at line {lineno} "
                    "passes non-literal value for enum parameter."
                )
                return

        # Primitive and composite type checks
        if expected_type == "string":
            if not (isinstance(val_node, ast.Constant) and isinstance(val_node.value, str)):
                self.schema_valid = False
                self.rejection_reasons.append(
                    f"Tool '{tool_name}' argument '{param_path}' at line {lineno} "
                    f"expected type 'string', got {self._get_ast_type_label(val_node)}."
                )
            else:
                min_len = param_schema.get("minLength")
                if isinstance(min_len, int) and len(val_node.value) < min_len:
                    self.schema_valid = False
                    self.rejection_reasons.append(
                        f"Tool '{tool_name}' argument '{param_path}' at line {lineno} "
                        f"string length ({len(val_node.value)}) is less than minLength ({min_len})."
                    )
                max_len = param_schema.get("maxLength")
                if isinstance(max_len, int) and len(val_node.value) > max_len:
                    self.schema_valid = False
                    self.rejection_reasons.append(
                        f"Tool '{tool_name}' argument '{param_path}' at line {lineno} "
                        f"string length ({len(val_node.value)}) exceeds maxLength ({max_len})."
                    )
        elif expected_type == "integer":
            num = self._extract_numeric_constant(val_node)
            if num is None or num[0] is not int:
                self.schema_valid = False
                self.rejection_reasons.append(
                    f"Tool '{tool_name}' argument '{param_path}' at line {lineno} "
                    f"expected type 'integer', got {self._get_ast_type_label(val_node)}."
                )
            else:
                self._check_numeric_bounds(tool_name, param_path, num[1], param_schema, lineno)
        elif expected_type == "number":
            num = self._extract_numeric_constant(val_node)
            if num is None:
                self.schema_valid = False
                self.rejection_reasons.append(
                    f"Tool '{tool_name}' argument '{param_path}' at line {lineno} "
                    f"expected type 'number', got {self._get_ast_type_label(val_node)}."
                )
            else:
                self._check_numeric_bounds(tool_name, param_path, num[1], param_schema, lineno)
        elif expected_type == "boolean":
            if not (isinstance(val_node, ast.Constant) and isinstance(val_node.value, bool)):
                self.schema_valid = False
                self.rejection_reasons.append(
                    f"Tool '{tool_name}' argument '{param_path}' at line {lineno} "
                    f"expected type 'boolean', got {self._get_ast_type_label(val_node)}."
                )
        elif expected_type == "array":
            if isinstance(val_node, (ast.List, ast.Tuple)):
                min_items = param_schema.get("minItems")
                if isinstance(min_items, int) and len(val_node.elts) < min_items:
                    self.schema_valid = False
                    self.rejection_reasons.append(
                        f"Tool '{tool_name}' argument '{param_path}' at line {lineno} "
                        f"array length ({len(val_node.elts)}) is less than minItems ({min_items})."
                    )
                max_items = param_schema.get("maxItems")
                if isinstance(max_items, int) and len(val_node.elts) > max_items:
                    self.schema_valid = False
                    self.rejection_reasons.append(
                        f"Tool '{tool_name}' argument '{param_path}' at line {lineno} "
                        f"array length ({len(val_node.elts)}) exceeds maxItems ({max_items})."
                    )
                item_schema = param_schema.get("items")
                if item_schema and isinstance(item_schema, dict):
                    for idx, elt in enumerate(val_node.elts):
                        self._validate_ast_value_against_schema(
                            tool_name=tool_name,
                            param_path=f"{param_path}[{idx}]",
                            val_node=elt,
                            param_schema=item_schema,
                            lineno=lineno,
                        )
                else:
                    self.schema_valid = False
                    self.rejection_reasons.append(
                        f"Tool '{tool_name}' argument '{param_path}' array schema lacks an 'items' schema definition. "
                        "Static AST validation fails closed on untyped array schemas."
                    )
            else:
                self.schema_valid = False
                self.rejection_reasons.append(
                    f"Tool '{tool_name}' argument '{param_path}' at line {lineno} "
                    f"expected type 'array', got {self._get_ast_type_label(val_node)}."
                )
        elif expected_type == "object":
            if isinstance(val_node, ast.Dict):
                self._validate_ast_dict_against_schema(
                    tool_name=tool_name,
                    path_prefix=param_path,
                    dict_node=val_node,
                    schema=param_schema,
                    lineno=lineno,
                )
            else:
                self.schema_valid = False
                self.rejection_reasons.append(
                    f"Tool '{tool_name}' argument '{param_path}' at line {lineno} "
                    f"expected type 'object', got {self._get_ast_type_label(val_node)}."
                )
        elif expected_type is None and "enum" in param_schema:
            # Pure enum constraint without explicit type was validated above
            pass
        else:
            # Fail closed on unsupported or missing schema type
            self.schema_valid = False
            self.rejection_reasons.append(
                f"Tool '{tool_name}' argument '{param_path}' has unsupported or missing schema type {repr(expected_type)}. "
                "Static AST validation fails closed on unsupported or missing schema types."
            )

    def _extract_numeric_constant(self, val_node: ast.AST) -> Optional[Tuple[type, Any]]:
        """Extract literal number (int/float) including unary signs like -5 or +3.14."""
        if isinstance(val_node, ast.Constant):
            if isinstance(val_node.value, bool):
                return None
            if isinstance(val_node.value, (int, float)):
                return (type(val_node.value), val_node.value)
        elif isinstance(val_node, ast.UnaryOp):
            if isinstance(val_node.op, ast.USub) and isinstance(val_node.operand, ast.Constant):
                if isinstance(val_node.operand.value, bool):
                    return None
                if isinstance(val_node.operand.value, (int, float)):
                    return (type(val_node.operand.value), -val_node.operand.value)
            elif isinstance(val_node.op, ast.UAdd) and isinstance(val_node.operand, ast.Constant):
                if isinstance(val_node.operand.value, bool):
                    return None
                if isinstance(val_node.operand.value, (int, float)):
                    return (type(val_node.operand.value), +val_node.operand.value)
        return None

    def _get_ast_type_label(self, node: ast.AST) -> str:
        num = self._extract_numeric_constant(node)
        if num is not None:
            return num[0].__name__
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return "boolean"
            return type(node.value).__name__
        elif isinstance(node, ast.List):
            return "array"
        elif isinstance(node, ast.Dict):
            return "object"
        return type(node).__name__


def _is_statically_false(test_node: ast.AST) -> bool:
    if isinstance(test_node, ast.Constant):
        return not bool(test_node.value)
    if isinstance(test_node, ast.UnaryOp) and isinstance(test_node.op, ast.Not):
        return _is_statically_true(test_node.operand)
    return False


def _is_statically_true(test_node: ast.AST) -> bool:
    if isinstance(test_node, ast.Constant):
        return bool(test_node.value)
    if isinstance(test_node, ast.UnaryOp) and isinstance(test_node.op, ast.Not):
        return _is_statically_false(test_node.operand)
    return False


def _is_statically_empty_iterable(iter_node: ast.AST) -> bool:
    """Check whether a loop iterable expression is statically proven to be empty."""
    if isinstance(iter_node, (ast.Tuple, ast.List, ast.Set)):
        return len(iter_node.elts) == 0
    if isinstance(iter_node, ast.Dict):
        return len(iter_node.keys) == 0
    if isinstance(iter_node, ast.Constant):
        if isinstance(iter_node.value, (str, bytes, tuple, list, set, frozenset, dict)):
            return len(iter_node.value) == 0
        return False
    if isinstance(iter_node, ast.Call):
        func = iter_node.func
        if isinstance(func, ast.Name):
            if func.id == "range":
                if len(iter_node.args) == 1:
                    arg = iter_node.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, int) and arg.value <= 0:
                        return True
                elif len(iter_node.args) >= 2:
                    a1 = iter_node.args[0]
                    a2 = iter_node.args[1]
                    if (
                        isinstance(a1, ast.Constant)
                        and isinstance(a1.value, int)
                        and isinstance(a2, ast.Constant)
                        and isinstance(a2.value, int)
                    ):
                        if len(iter_node.args) == 2 and a1.value >= a2.value:
                            return True
                        elif len(iter_node.args) == 3:
                            step = iter_node.args[2]
                            if isinstance(step, ast.Constant) and isinstance(step.value, int):
                                if step.value > 0 and a1.value >= a2.value:
                                    return True
                                if step.value < 0 and a1.value <= a2.value:
                                    return True
            elif func.id in ("list", "tuple", "set", "dict") and len(iter_node.args) == 0:
                return True
    return False


def _is_statically_non_empty_iterable(iter_node: ast.AST) -> bool:
    """Check whether a loop iterable expression is statically proven to have at least one element."""
    if isinstance(iter_node, (ast.Tuple, ast.List, ast.Set)):
        return len(iter_node.elts) > 0
    if isinstance(iter_node, ast.Dict):
        return len(iter_node.keys) > 0
    if isinstance(iter_node, ast.Constant):
        if isinstance(iter_node.value, (str, bytes, tuple, list, set, frozenset, dict)):
            return len(iter_node.value) > 0
        return False
    if isinstance(iter_node, ast.Call):
        func = iter_node.func
        if isinstance(func, ast.Name) and func.id == "range":
            if len(iter_node.args) == 1:
                arg = iter_node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, int) and arg.value > 0:
                    return True
            elif len(iter_node.args) == 2:
                a1 = iter_node.args[0]
                a2 = iter_node.args[1]
                if (
                    isinstance(a1, ast.Constant)
                    and isinstance(a1.value, int)
                    and isinstance(a2, ast.Constant)
                    and isinstance(a2.value, int)
                ):
                    return a1.value < a2.value
            elif len(iter_node.args) >= 3:
                a1 = iter_node.args[0]
                a2 = iter_node.args[1]
                step = iter_node.args[2]
                if (
                    isinstance(a1, ast.Constant)
                    and isinstance(a1.value, int)
                    and isinstance(a2, ast.Constant)
                    and isinstance(a2.value, int)
                    and isinstance(step, ast.Constant)
                    and isinstance(step.value, int)
                ):
                    if step.value > 0 and a1.value < a2.value:
                        return True
                    if step.value < 0 and a1.value > a2.value:
                        return True
    return False


def _parse_call_tool_args(call_node: ast.Call) -> Optional[Tuple[str, Optional[Dict[str, Any]]]]:
    call_tool_name: Optional[str] = None
    call_args: Optional[Dict[str, Any]] = None
    if call_node.args:
        if isinstance(call_node.args[0], ast.Constant) and isinstance(call_node.args[0].value, str):
            call_tool_name = call_node.args[0].value
        if len(call_node.args) > 1 and isinstance(call_node.args[1], ast.Dict):
            try:
                call_args = ast.literal_eval(call_node.args[1])
            except Exception:
                pass
    for kw in call_node.keywords:
        if (
            kw.arg in ("name", "tool_name")
            and isinstance(kw.value, ast.Constant)
            and isinstance(kw.value.value, str)
        ):
            call_tool_name = kw.value.value
        elif kw.arg == "arguments" and isinstance(kw.value, ast.Dict):
            try:
                call_args = ast.literal_eval(kw.value)
            except Exception:
                pass
    if call_tool_name:
        return (call_tool_name, call_args)
    return None


def _find_awaited_tool_calls_in_expr(node: ast.AST) -> List[Tuple[str, Optional[Dict[str, Any]]]]:
    calls: List[Tuple[str, Optional[Dict[str, Any]]]] = []
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
        return calls
    if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
        call_node = node.value
        if isinstance(call_node.func, ast.Attribute) and call_node.func.attr == "call_tool":
            parsed = _parse_call_tool_args(call_node)
            if parsed:
                calls.append(parsed)
    for child in ast.iter_child_nodes(node):
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            calls.extend(_find_awaited_tool_calls_in_expr(child))
    return calls


class _ControlFlow(Enum):
    NORMAL = 0
    BREAK = 1
    CONTINUE = 2
    RETURN = 3
    RAISE = 4
    TERMINATED = 5
    UNCERTAIN = 6


def _extract_block_tool_calls(
    stmts: List[ast.stmt],
    in_loop: bool = False,
) -> Tuple[List[Tuple[str, Optional[Dict[str, Any]]]], _ControlFlow]:
    calls: List[Tuple[str, Optional[Dict[str, Any]]]] = []
    status = _ControlFlow.NORMAL

    for stmt in stmts:
        if status != _ControlFlow.NORMAL:
            # Previous statement terminated block execution; subsequent statements are dead code!
            break

        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue

        elif isinstance(stmt, ast.Break):
            status = _ControlFlow.BREAK
            break

        elif isinstance(stmt, ast.Continue):
            status = _ControlFlow.CONTINUE
            break

        elif isinstance(stmt, ast.Return):
            calls.extend(_find_awaited_tool_calls_in_expr(stmt))
            status = _ControlFlow.RETURN
            break

        elif isinstance(stmt, ast.Raise):
            calls.extend(_find_awaited_tool_calls_in_expr(stmt))
            status = _ControlFlow.RAISE
            break

        elif isinstance(stmt, ast.If):
            calls.extend(_find_awaited_tool_calls_in_expr(stmt.test))
            if _is_statically_true(stmt.test):
                body_calls, body_status = _extract_block_tool_calls(stmt.body, in_loop=in_loop)
                calls.extend(body_calls)
                status = body_status
            elif _is_statically_false(stmt.test):
                else_calls, else_status = _extract_block_tool_calls(stmt.orelse, in_loop=in_loop)
                calls.extend(else_calls)
                status = else_status
            else:
                # Dynamic condition: neither branch is guaranteed to execute.
                # Calls inside dynamic branches must not contribute unjustified coverage claims!
                _, body_status = _extract_block_tool_calls(stmt.body, in_loop=in_loop)
                _, else_status = _extract_block_tool_calls(stmt.orelse, in_loop=in_loop)
                if stmt.orelse:
                    if body_status == else_status and body_status != _ControlFlow.NORMAL:
                        status = body_status
                    elif body_status in (_ControlFlow.RETURN, _ControlFlow.RAISE) and else_status in (_ControlFlow.RETURN, _ControlFlow.RAISE):
                        status = _ControlFlow.RETURN
                    elif body_status != _ControlFlow.NORMAL or else_status != _ControlFlow.NORMAL:
                        status = _ControlFlow.UNCERTAIN
                    else:
                        status = _ControlFlow.NORMAL
                else:
                    if body_status != _ControlFlow.NORMAL:
                        status = _ControlFlow.UNCERTAIN
                    else:
                        status = _ControlFlow.NORMAL

        elif isinstance(stmt, ast.While):
            calls.extend(_find_awaited_tool_calls_in_expr(stmt.test))
            if _is_statically_false(stmt.test):
                else_calls, else_status = _extract_block_tool_calls(stmt.orelse, in_loop=in_loop)
                calls.extend(else_calls)
                status = else_status
            elif _is_statically_true(stmt.test):
                body_calls, body_status = _extract_block_tool_calls(stmt.body, in_loop=True)
                calls.extend(body_calls)
                if body_status == _ControlFlow.BREAK:
                    # Unconditional break terminates this while loop; statements after loop are reachable
                    status = _ControlFlow.NORMAL
                elif body_status == _ControlFlow.RETURN:
                    status = _ControlFlow.RETURN
                elif body_status == _ControlFlow.RAISE:
                    status = _ControlFlow.RAISE
                elif body_status in (_ControlFlow.NORMAL, _ControlFlow.CONTINUE):
                    # Infinite loop without break! Subsequent statements outside the loop are unreachable
                    status = _ControlFlow.TERMINATED
                else:
                    status = _ControlFlow.UNCERTAIN
            else:
                # Dynamic while loop: condition may be False initially, so body cannot be guaranteed
                status = _ControlFlow.NORMAL

        elif isinstance(stmt, (ast.For, ast.AsyncFor)):
            calls.extend(_find_awaited_tool_calls_in_expr(stmt.iter))
            if _is_statically_empty_iterable(stmt.iter):
                else_calls, else_status = _extract_block_tool_calls(stmt.orelse, in_loop=in_loop)
                calls.extend(else_calls)
                status = else_status
            elif _is_statically_non_empty_iterable(stmt.iter):
                body_calls, body_status = _extract_block_tool_calls(stmt.body, in_loop=True)
                calls.extend(body_calls)
                if body_status == _ControlFlow.BREAK:
                    status = _ControlFlow.NORMAL
                elif body_status == _ControlFlow.RETURN:
                    status = _ControlFlow.RETURN
                elif body_status == _ControlFlow.RAISE:
                    status = _ControlFlow.RAISE
                else:
                    if stmt.orelse:
                        else_calls, else_status = _extract_block_tool_calls(stmt.orelse, in_loop=in_loop)
                        calls.extend(else_calls)
                        status = else_status
                    else:
                        status = _ControlFlow.NORMAL
            else:
                status = _ControlFlow.NORMAL

        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            calls.extend(_find_awaited_tool_calls_in_expr(stmt))
            body_calls, body_status = _extract_block_tool_calls(stmt.body, in_loop=in_loop)
            calls.extend(body_calls)
            status = body_status

        elif isinstance(stmt, ast.Try):
            body_calls, body_status = _extract_block_tool_calls(stmt.body, in_loop=in_loop)
            calls.extend(body_calls)

            nominal_status = body_status
            if body_status == _ControlFlow.NORMAL and stmt.orelse:
                else_calls, else_status = _extract_block_tool_calls(stmt.orelse, in_loop=in_loop)
                calls.extend(else_calls)
                nominal_status = else_status

            if stmt.finalbody:
                final_calls, final_status = _extract_block_tool_calls(stmt.finalbody, in_loop=in_loop)
                calls.extend(final_calls)
                if final_status != _ControlFlow.NORMAL:
                    status = final_status
                else:
                    status = nominal_status
            else:
                status = nominal_status

        else:
            calls.extend(_find_awaited_tool_calls_in_expr(stmt))
            status = _ControlFlow.NORMAL

    return (calls, status)


def _extract_statements_tool_calls(stmts: List[ast.stmt]) -> List[Tuple[str, Optional[Dict[str, Any]]]]:
    calls, _ = _extract_block_tool_calls(stmts, in_loop=False)
    return calls


def _match_scenario_steps_ordered(
    scenario_id: str,
    func_name: str,
    expected_steps: List[Any],
    func_tool_calls: List[Tuple[str, Optional[Dict[str, Any]]]],
) -> Tuple[bool, Optional[str]]:
    """Verify that expected scenario steps occur sequentially with exact argument matching."""
    if not expected_steps:
        return (True, None)

    current_idx = 0
    total_calls = len(func_tool_calls)

    for step_num, step in enumerate(expected_steps, 1):
        step_tool = step.tool_name
        step_args = step.arguments
        matched = False

        for j in range(current_idx, total_calls):
            called_tool, called_args = func_tool_calls[j]
            if called_tool != step_tool:
                continue

            # Check arguments
            if step_args is not None and isinstance(step_args, dict) and len(step_args) > 0:
                if called_args is None:
                    # Dynamic, non-literal or unparseable arguments cannot be statically verified
                    continue
                # Exact match: no extra unplanned keys, all values match
                if called_args != step_args:
                    continue
            elif step_args is None or (isinstance(step_args, dict) and len(step_args) == 0):
                if called_args is not None and len(called_args) > 0:
                    continue

            # Step matched
            current_idx = j + 1
            matched = True
            break

        if not matched:
            args_desc = f" with arguments {step_args}" if step_args else ""
            return (
                False,
                f"Test function '{func_name}' claims scenario '{scenario_id}' but does not invoke "
                f"expected tool '{step_tool}'{args_desc} in required sequential order.",
            )

    return (True, None)


def _extract_executable_tool_calls_from_func(
    func_node: ast.AST,
) -> List[Tuple[str, Optional[Dict[str, Any]]]]:
    body = getattr(func_node, "body", [])
    return _extract_statements_tool_calls(body)


class HarnessValidator:
    """Static analyzer that audits generated test harnesses against security and structural rules."""

    def __init__(
        self,
        max_lines: int = MAX_HARNESS_LINES,
        max_ast_nodes: int = MAX_AST_NODES,
    ):
        self.max_lines = max_lines
        self.max_ast_nodes = max_ast_nodes

    def _is_safe_assignment_value(self, value_node: Optional[ast.AST]) -> bool:
        """Check whether an assignment value is a safe static constant or symbol reference."""
        if value_node is None:
            return True
        if isinstance(value_node, ast.Constant):
            return True
        if isinstance(value_node, ast.Name):
            return (
                value_node.id not in PROHIBITED_CALLS
                and value_node.id not in PROHIBITED_ATTRS
                and value_node.id != "pytest_plugins"
            )
        if isinstance(value_node, ast.Attribute):
            return (
                value_node.attr not in PROHIBITED_CALLS
                and value_node.attr not in PROHIBITED_ATTRS
                and value_node.attr != "pytest_plugins"
            )
        if isinstance(value_node, (ast.List, ast.Tuple, ast.Set)):
            return all(self._is_safe_assignment_value(elt) for elt in value_node.elts)
        return False

    def _validate_class_body(
        self, class_node: ast.ClassDef, rejection_reasons: List[str]
    ) -> None:
        """Recursively validate statements inside a class definition to prevent import-time execution."""
        for stmt in class_node.body:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                # Class docstring
                continue
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Method definitions
                continue
            if isinstance(stmt, ast.AnnAssign):
                if isinstance(stmt.target, ast.Name) and stmt.target.id == "pytest_plugins":
                    rejection_reasons.append(
                        f"Prohibited assignment to 'pytest_plugins' inside class '{class_node.name}' at line {stmt.lineno}."
                    )
                if not self._is_safe_type_annotation(stmt.annotation):
                    rejection_reasons.append(
                        f"Prohibited executable expression in annotated assignment inside class '{class_node.name}' at line {stmt.lineno}."
                    )
                if not self._is_safe_assignment_value(stmt.value):
                    rejection_reasons.append(
                        f"Prohibited dynamic annotated assignment inside class '{class_node.name}' at line {stmt.lineno}. "
                        "Class attributes must be static constants."
                    )
                continue
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id == "pytest_plugins":
                        rejection_reasons.append(
                            f"Prohibited assignment to 'pytest_plugins' inside class '{class_node.name}' at line {stmt.lineno}."
                        )
                if not self._is_safe_assignment_value(stmt.value):
                    rejection_reasons.append(
                        f"Prohibited dynamic assignment inside class '{class_node.name}' at line {stmt.lineno}. "
                        "Class attributes must be static constants or mark references."
                    )
                continue
            if isinstance(stmt, ast.Pass):
                continue
            if isinstance(stmt, ast.ClassDef):
                self._validate_class_body(stmt, rejection_reasons)
                continue

            rejection_reasons.append(
                f"Prohibited executable statement '{type(stmt).__name__}' inside class '{class_node.name}' at line {stmt.lineno}. "
                "Class bodies must only contain method definitions, docstrings, or static declarations."
            )

    def _is_safe_type_annotation(self, node: Optional[ast.AST]) -> bool:
        """Helper to validate type annotations using positive allowlist."""
        if node is None:
            return True
        if isinstance(node, ast.Name):
            return (
                node.id not in PROHIBITED_CALLS
                and node.id not in PROHIBITED_ATTRS
                and (not node.id.startswith("__") or node.id in ALLOWED_DUNDERS)
                and not node.id.startswith("_")
            )
        if isinstance(node, ast.Constant):
            if node.value is None:
                return True
            if isinstance(node.value, str):
                clean_str = node.value.strip()
                if not clean_str or len(clean_str) > 200:
                    return False
                if any(bad in clean_str for bad in ("__", "import", "exec", "eval", "system", "subprocess", "open", ";", "\n", "\r")):
                    return False
                try:
                    parsed = ast.parse(clean_str, mode="eval")
                    return self._is_safe_type_annotation(parsed.body)
                except Exception:
                    return False
            return False
        if isinstance(node, ast.Subscript):
            return self._is_safe_type_annotation(node.value) and self._is_safe_type_annotation(node.slice)
        if isinstance(node, ast.Attribute):
            if node.attr in PROHIBITED_CALLS or node.attr in PROHIBITED_ATTRS:
                return False
            if node.attr.startswith("_") and node.attr not in ALLOWED_DUNDERS:
                return False
            return self._is_safe_type_annotation(node.value)
        if isinstance(node, ast.BinOp):
            return (
                isinstance(node.op, ast.BitOr)
                and self._is_safe_type_annotation(node.left)
                and self._is_safe_type_annotation(node.right)
            )
        if isinstance(node, (ast.Tuple, ast.List)):
            return all(self._is_safe_type_annotation(elt) for elt in node.elts)
        return False

    def check_inventory_limits(
        self, tools: Optional[List[DiscoveredToolInput]]
    ) -> Optional[str]:
        """Verify tool count, schema bytes, AST node complexity, and nesting depth limits."""
        if not tools:
            return None

        if len(tools) > MAX_TOOLS_PER_INVENTORY:
            return (
                f"Discovered tool inventory exceeds maximum tool count limit "
                f"({len(tools)} tools > {MAX_TOOLS_PER_INVENTORY} allowed)."
            )

        try:
            serialized_inventory = json.dumps([t.model_dump() for t in tools]).encode("utf-8")
            if len(serialized_inventory) > MAX_COMBINED_INVENTORY_BYTES:
                return (
                    f"Combined tool inventory serialized size ({len(serialized_inventory)} bytes) "
                    f"exceeds maximum limit ({MAX_COMBINED_INVENTORY_BYTES} bytes allowed)."
                )
        except Exception:
            pass

        total_nodes = 0
        for tool in tools:
            schema = tool.input_schema or {}
            try:
                schema_bytes = len(json.dumps(schema).encode("utf-8"))
                if schema_bytes > MAX_TOOL_SCHEMA_BYTES:
                    return (
                        f"Tool '{tool.tool_name}' schema serialized size ({schema_bytes} bytes) "
                        f"exceeds maximum limit ({MAX_TOOL_SCHEMA_BYTES} bytes allowed)."
                    )
            except Exception:
                pass

            nodes, depth = _count_schema_nodes(schema, depth=0)
            if depth > MAX_SCHEMA_NESTING_DEPTH:
                return (
                    f"Tool '{tool.tool_name}' schema exceeds maximum allowable nesting depth ({depth} > {MAX_SCHEMA_NESTING_DEPTH} allowed)."
                )
            if nodes > MAX_SCHEMA_NODES_PER_TOOL:
                return (
                    f"Tool '{tool.tool_name}' schema node count ({nodes}) "
                    f"exceeds per-tool node budget ({MAX_SCHEMA_NODES_PER_TOOL} allowed)."
                )
            total_nodes += nodes

        if total_nodes > MAX_TOTAL_SCHEMA_NODES:
            return (
                f"Combined schema node count across all tools ({total_nodes}) "
                f"exceeds total inventory node budget ({MAX_TOTAL_SCHEMA_NODES} allowed)."
            )

        return None

    def validate(
        self,
        code: str,
        tools: Optional[List[DiscoveredToolInput]] = None,
        test_plan: Optional[TestPlan] = None,
    ) -> HarnessValidationResult:
        """Perform static analysis on the provided Python source code.
        
        Never executes the code.
        """
        try:
            return self._validate_impl(code, tools, test_plan)
        except Exception as exc:
            err_id = f"val-err-{uuid.uuid4().hex[:8]}"
            logger.exception("[%s] Unexpected error during harness static validation: %s", err_id, exc)
            return HarnessValidationResult(
                is_valid=False,
                syntax_valid=False,
                security_valid=False,
                structure_valid=False,
                schema_valid=False,
                rejection_reasons=[
                    f"Harness validation aborted due to unexpected internal error [{err_id}]. Please report this correlation ID."
                ],
                warnings=[],
                identified_imports=[],
                identified_tool_calls=[],
                identified_scenarios=[],
                ast_node_count=0,
                line_count=0,
            )

    def _validate_impl(
        self,
        code: str,
        tools: Optional[List[DiscoveredToolInput]] = None,
        test_plan: Optional[TestPlan] = None,
    ) -> HarnessValidationResult:
        raw_code = code or ""
        try:
            raw_bytes = raw_code.encode("utf-8")
        except (UnicodeEncodeError, UnicodeError) as exc:
            return HarnessValidationResult(
                is_valid=False,
                syntax_valid=False,
                security_valid=False,
                structure_valid=False,
                schema_valid=False,
                rejection_reasons=[
                    f"Harness source contains invalid Unicode encoding or unpaired surrogates: {exc}"
                ],
                warnings=[],
                identified_imports=[],
                identified_tool_calls=[],
                identified_scenarios=[],
                ast_node_count=0,
                line_count=0,
            )
        lines = raw_code.splitlines()
        line_count = len(lines)

        # Check resource limits upfront
        limit_error = self.check_inventory_limits(tools)
        if limit_error:
            return HarnessValidationResult(
                is_valid=False,
                syntax_valid=False,
                security_valid=False,
                structure_valid=False,
                schema_valid=False,
                rejection_reasons=[limit_error],
                warnings=[],
                identified_imports=[],
                identified_tool_calls=[],
                identified_scenarios=[],
                ast_node_count=0,
                line_count=line_count,
            )

        tools_available = bool(tools is not None and len(tools) > 0)
        known_tools: Dict[str, DiscoveredToolInput] = {}
        if tools:
            for t in tools:
                known_tools[t.tool_name] = t

        # Check empty code
        if not raw_code.strip():
            return HarnessValidationResult(
                is_valid=False,
                syntax_valid=False,
                security_valid=False,
                structure_valid=False,
                schema_valid=False,
                rejection_reasons=["Empty or whitespace-only harness code provided."],
                warnings=[],
                identified_imports=[],
                identified_tool_calls=[],
                identified_scenarios=[],
                ast_node_count=0,
                line_count=0,
            )

        # Byte length limit
        if len(raw_bytes) > MAX_HARNESS_BYTES:
            return HarnessValidationResult(
                is_valid=False,
                syntax_valid=False,
                security_valid=False,
                structure_valid=False,
                schema_valid=False,
                rejection_reasons=[
                    f"Harness exceeds maximum byte length limit ({len(raw_bytes)} bytes > {MAX_HARNESS_BYTES} allowed)."
                ],
                warnings=[],
                identified_imports=[],
                identified_tool_calls=[],
                identified_scenarios=[],
                ast_node_count=0,
                line_count=line_count,
            )

        # Line length limit
        for idx, line in enumerate(lines, 1):
            if len(line) > MAX_LINE_LENGTH:
                return HarnessValidationResult(
                    is_valid=False,
                    syntax_valid=False,
                    security_valid=False,
                    structure_valid=False,
                    schema_valid=False,
                    rejection_reasons=[
                        f"Harness line {idx} exceeds maximum line length limit ({len(line)} chars > {MAX_LINE_LENGTH} allowed)."
                    ],
                    warnings=[],
                    identified_imports=[],
                    identified_tool_calls=[],
                    identified_scenarios=[],
                    ast_node_count=0,
                    line_count=line_count,
                )

        rejection_reasons: List[str] = []
        warnings: List[str] = []

        if line_count > self.max_lines:
            rejection_reasons.append(
                f"Harness exceeds maximum source line limit ({line_count} lines > {self.max_lines} allowed)."
            )

        # Upfront recursive schema check for all tools
        visitor = _SecurityASTVisitor(known_tools=known_tools, tools_available=tools_available)
        if tools:
            for tool in tools:
                tool_schema = tool.input_schema or {}
                err = visitor._find_unsupported_schema_construct(tool_schema, f"tool '{tool.tool_name}'")
                if err:
                    rejection_reasons.append(
                        f"{err} Static AST validation fails closed on unsupported or malformed schema constructs."
                    )

        # Parse AST with robust exception handling
        try:
            tree = ast.parse(raw_code)
        except SyntaxError as exc:
            logger.warning("Harness failed Python syntax parse: %s", exc)
            return HarnessValidationResult(
                is_valid=False,
                syntax_valid=False,
                security_valid=False,
                structure_valid=False,
                schema_valid=False,
                rejection_reasons=[
                    f"Syntax error at line {exc.lineno or 'unknown'}, col {exc.offset or 'unknown'}: {exc.msg}"
                ],
                warnings=[],
                identified_imports=[],
                identified_tool_calls=[],
                identified_scenarios=[],
                ast_node_count=0,
                line_count=line_count,
            )
        except (RecursionError, MemoryError) as exc:
            logger.warning("Harness aborted during AST parse: %s", exc)
            return HarnessValidationResult(
                is_valid=False,
                syntax_valid=False,
                security_valid=False,
                structure_valid=False,
                schema_valid=False,
                rejection_reasons=[
                    f"Harness parsing aborted due to excessive nesting or resource consumption: {type(exc).__name__}"
                ],
                warnings=[],
                identified_imports=[],
                identified_tool_calls=[],
                identified_scenarios=[],
                ast_node_count=0,
                line_count=line_count,
            )

        # Top-level module isolation: reject arbitrary executable statements at module scope
        for stmt in tree.body:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                # Permitted module docstring
                continue
            if isinstance(stmt, ast.ClassDef):
                self._validate_class_body(stmt, rejection_reasons)
                continue
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id == "pytest_plugins":
                        rejection_reasons.append(
                            f"Prohibited assignment to 'pytest_plugins' at line {stmt.lineno}. "
                            "Pytest plugin injection is forbidden."
                        )
                if not self._is_safe_assignment_value(stmt.value):
                    rejection_reasons.append(
                        f"Prohibited dynamic top-level assignment at line {stmt.lineno}. "
                        "Module-level variables must be static constants or mark references."
                    )
                continue
            if isinstance(stmt, ast.AnnAssign):
                if isinstance(stmt.target, ast.Name) and stmt.target.id == "pytest_plugins":
                    rejection_reasons.append(
                        f"Prohibited assignment to 'pytest_plugins' at line {stmt.lineno}. "
                        "Pytest plugin injection is forbidden."
                    )
                if not self._is_safe_type_annotation(stmt.annotation):
                    rejection_reasons.append(
                        f"Prohibited executable expression in top-level type annotation at line {stmt.lineno}."
                    )
                if not self._is_safe_assignment_value(stmt.value):
                    rejection_reasons.append(
                        f"Prohibited dynamic top-level annotated assignment at line {stmt.lineno}. "
                        "Module-level variables must be static constants."
                    )
                continue
            if isinstance(stmt, ast.Pass):
                continue
            if not isinstance(stmt, ALLOWED_TOP_LEVEL_STATEMENTS):
                rejection_reasons.append(
                    f"Prohibited top-level statement '{type(stmt).__name__}' at line {stmt.lineno}. "
                    "Harness module body must only define test functions, fixtures, imports, or declarations."
                )

        # Walk AST with security visitor
        try:
            visitor.visit(tree)
        except RecursionError:
            rejection_reasons.append("AST traversal aborted due to excessive recursion depth.")

        # Combine visitor rejection reasons
        rejection_reasons.extend(visitor.rejection_reasons)
        warnings.extend(visitor.warnings)

        # Check AST complexity limit
        if visitor.node_count > self.max_ast_nodes:
            rejection_reasons.append(
                f"Harness exceeds AST complexity limit ({visitor.node_count} nodes > {self.max_ast_nodes} allowed)."
            )

        # Structural check: at least one test_* function
        structure_valid = visitor.structure_valid and not any(
            "top-level" in r or "class body" in r or "inside class" in r for r in rejection_reasons
        )
        if not visitor.test_functions:
            structure_valid = False
            rejection_reasons.append(
                "No test functions found in harness. Must define at least one 'test_*' or 'async def test_*' function."
            )

        # Tool inventory availability check
        if not tools_available:
            rejection_reasons.append(
                "Discovered tool inventory is empty or unavailable; test harness cannot be verified."
            )

        # Scenario verification against declared TestPlan
        identified_scenarios: List[str] = []
        if test_plan and test_plan.scenarios:
            # 1. Reject duplicate, empty, or ambiguous scenario IDs
            seen_ids: Set[str] = set()
            duplicates: Set[str] = set()
            for sc in test_plan.scenarios:
                sc_id_raw = (sc.scenario_id or "").strip()
                if not sc_id_raw or sc_id_raw.lower() in seen_ids:
                    duplicates.add(sc_id_raw or "<empty>")
                seen_ids.add(sc_id_raw.lower())
            if duplicates:
                structure_valid = False
                rejection_reasons.append(
                    f"Test plan contains duplicate, empty, or ambiguous scenario identifiers: {sorted(list(duplicates))}."
                )

            valid_scenarios_map = {
                sc.scenario_id.strip(): sc for sc in test_plan.scenarios if sc.scenario_id and sc.scenario_id.strip()
            }
            lower_to_id = {k.lower(): v.scenario_id for k, v in valid_scenarios_map.items()}

            matched_scenario_ids: Set[str] = set()

            for func_node in visitor.test_func_nodes:
                func_name = getattr(func_node, "name", "")
                func_doc = ast.get_docstring(func_node) or ""
                decorators = getattr(func_node, "decorator_list", [])

                # Check if test function body is empty (only pass or docstring)
                body_stmts = [
                    s for s in getattr(func_node, "body", [])
                    if not (isinstance(s, ast.Pass) or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)))
                ]
                is_empty_func = len(body_stmts) == 0

                func_scenario_ids: Set[str] = set()

                # 1. Decorator inspection:
                for dec in decorators:
                    if isinstance(dec, ast.Call):
                        dec_name = ""
                        if isinstance(dec.func, ast.Attribute):
                            dec_name = dec.func.attr
                        elif isinstance(dec.func, ast.Name):
                            dec_name = dec.func.id

                        if dec_name in ("scenario", "scenarios"):
                            for arg in dec.args:
                                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                    val_str = arg.value.strip()
                                    if val_str.lower() in lower_to_id:
                                        func_scenario_ids.add(lower_to_id[val_str.lower()])
                                elif isinstance(arg, (ast.List, ast.Tuple)):
                                    for elt in arg.elts:
                                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                            val_str = elt.value.strip()
                                            if val_str.lower() in lower_to_id:
                                                func_scenario_ids.add(lower_to_id[val_str.lower()])

                # 2. Docstring metadata inspection:
                if func_doc:
                    tag_matches = re.findall(
                        r"(?i)(?:@scenario|scenario(?:\s+id)?|scenario_id)\s*[:=]?\s*([a-zA-Z0-9_\-\.]+)",
                        func_doc,
                    )
                    for m in tag_matches:
                        clean_m = m.strip().lower()
                        if clean_m in lower_to_id:
                            func_scenario_ids.add(lower_to_id[clean_m])

                    # Match docstring line starting with scenario ID, e.g. "SCENARIO-01: Verify file read"
                    for sc_id, sc_obj in valid_scenarios_map.items():
                        pattern = r"(?im)^\s*(?:\[?" + re.escape(sc_id) + r"\]?\s*[:\-])"
                        if re.search(pattern, func_doc):
                            func_scenario_ids.add(sc_obj.scenario_id)

                # 3. Explicit Function Name Pattern:
                for sc_id, sc_obj in valid_scenarios_map.items():
                    norm_sc_id = re.sub(r"[^a-zA-Z0-9]+", "_", sc_id).strip("_")
                    fn_pattern = r"(?i)^test_(?:scenario_)?" + re.escape(norm_sc_id) + r"(?:_.*)?$"
                    if re.match(fn_pattern, func_name):
                        func_scenario_ids.add(sc_obj.scenario_id)

                # Reject empty test functions claiming scenario coverage
                if func_scenario_ids and is_empty_func:
                    structure_valid = False
                    rejection_reasons.append(
                        f"Test function '{func_name}' claims scenario coverage ({sorted(list(func_scenario_ids))}) "
                        "but contains no executable statements (empty test body)."
                    )
                    continue

                # Extract reachable, awaited tool calls inside this test function
                func_tool_calls = _extract_executable_tool_calls_from_func(func_node)

                # Verify each claimed scenario against the actual tool calls in this function
                for sc_id in func_scenario_ids:
                    sc_obj = valid_scenarios_map[sc_id]
                    expected_steps = sc_obj.steps
                    matched_ok, match_err = _match_scenario_steps_ordered(
                        scenario_id=sc_id,
                        func_name=func_name,
                        expected_steps=expected_steps,
                        func_tool_calls=func_tool_calls,
                    )
                    if not matched_ok:
                        structure_valid = False
                        if match_err:
                            rejection_reasons.append(match_err)
                    else:
                        matched_scenario_ids.add(sc_id)

            if not matched_scenario_ids:
                structure_valid = False
                rejection_reasons.append(
                    f"Test harness does not implement any declared scenarios from the test plan "
                    f"(declared scenarios: {[sc.scenario_id for sc in test_plan.scenarios]}). "
                    "Test functions must explicitly declare scenario coverage via @pytest.mark.scenario('ID'), "
                    "'Scenario: ID' docstring metadata, or 'test_scenario_<id>_*' naming convention."
                )
            else:
                identified_scenarios = sorted(list(matched_scenario_ids))

        security_valid = visitor.security_valid and not any(
            "Prohibited" in r for r in rejection_reasons if "top-level" not in r and "inside class" not in r and "dynamic" not in r
        )
        schema_valid = visitor.schema_valid and not any(
            "unknown MCP tool" in r or "argument" in r or "inventory is empty" in r or "schema" in r for r in rejection_reasons
        )
        is_valid = bool(
            visitor.syntax_valid
            and security_valid
            and structure_valid
            and schema_valid
            and len(rejection_reasons) == 0
        )

        unique_imports = list(dict.fromkeys(visitor.identified_imports))
        unique_tools = list(dict.fromkeys(visitor.identified_tool_calls))

        return HarnessValidationResult(
            is_valid=is_valid,
            syntax_valid=visitor.syntax_valid,
            security_valid=security_valid,
            structure_valid=structure_valid,
            schema_valid=schema_valid,
            rejection_reasons=rejection_reasons,
            warnings=warnings,
            identified_imports=unique_imports,
            identified_tool_calls=unique_tools,
            identified_scenarios=identified_scenarios,
            ast_node_count=visitor.node_count,
            line_count=line_count,
        )
