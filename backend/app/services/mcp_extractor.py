"""Static AST-based MCP server discovery and tool/schema extraction engine.

Strictly analyzes repository structure and source code using Python's built-in AST.
NEVER imports, executes, or runs any repository code on the control plane.
Distinguishes MCP servers from MCP clients and groups tools by server implementation.
"""

import ast
import os
import re
import tomllib
from typing import Any, Dict, List, Optional, Set, Tuple

from app.schemas.mcp import (
    compute_schema_hash,
    DiscoveredServer,
    ExtractedTool,
    MCPServerDiscovery,
    MCPServerIndicator,
    ToolParameter,
)

# Regex for parsing Google-style docstrings: "Args:\n    param (type): description"
GOOGLE_ARG_PATTERN = re.compile(
    r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)(?:\s*\([^)]*\))?\s*:\s*(.+)$"
)
# Regex for parsing Sphinx-style docstrings: ":param param_name: description"
SPHINX_ARG_PATTERN = re.compile(
    r"^:param\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.+)$"
)


def is_test_file(file_path: str) -> bool:
    """Check if file path belongs to test directories or test files."""
    parts = file_path.lower().replace("\\", "/").split("/")
    filename = parts[-1]
    # Check directory parts
    for part in parts[:-1]:
        if part in ("tests", "test", "testing", "__tests__", "fixtures"):
            return True
    # Check filename
    if filename.startswith("test_") or filename.endswith("_test.py") or filename == "conftest.py":
        return True
    return False


def safe_eval_ast_literal(node: ast.AST) -> Any:
    """Safely convert AST literal nodes into Python primitives without code execution.
    
    If the node is non-literal or dynamic, returns a descriptive placeholder string.
    """
    if isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.List):
        return [safe_eval_ast_literal(elt) for elt in node.elts]
    elif isinstance(node, ast.Tuple):
        return tuple(safe_eval_ast_literal(elt) for elt in node.elts)
    elif isinstance(node, ast.Dict):
        result = {}
        for k, v in zip(node.keys, node.values):
            if k is not None:
                key_val = safe_eval_ast_literal(k)
                if isinstance(key_val, (str, int, float, bool)):
                    result[str(key_val)] = safe_eval_ast_literal(v)
        return result
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        val = safe_eval_ast_literal(node.operand)
        if isinstance(val, (int, float)):
            return -val
    elif isinstance(node, ast.Name):
        if node.id in ("True", "False", "None"):
            return {"True": True, "False": False, "None": None}[node.id]
        return f"<variable:{node.id}>"
    elif isinstance(node, ast.Call):
        func_name = "<call>"
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        return f"<{func_name}()>"
    return "<dynamic_expr>"


def parse_docstring_params(docstring: Optional[str]) -> Tuple[Optional[str], Dict[str, str]]:
    """Extract tool description and per-parameter descriptions from docstring.
    
    Supports Google-style, Sphinx-style, and plain docstrings.
    """
    if not docstring or not isinstance(docstring, str):
        return None, {}

    lines = docstring.strip().split("\n")
    cleaned_lines = [l.rstrip() for l in lines]

    desc_lines = []
    param_descs: Dict[str, str] = {}
    in_args_section = False

    for line in cleaned_lines:
        stripped = line.strip()
        lower = stripped.lower()

        if lower in ("args:", "arguments:", "parameters:"):
            in_args_section = True
            continue

        if stripped.startswith(":") and ":param" in stripped:
            m = SPHINX_ARG_PATTERN.match(stripped)
            if m:
                param_descs[m.group(1)] = m.group(2).strip()
            continue

        if in_args_section:
            if lower in ("returns:", "return:", "raises:", "examples:", "example:", "notes:"):
                in_args_section = False
                continue

            m = GOOGLE_ARG_PATTERN.match(line)
            if m:
                param_name = m.group(1)
                param_desc = m.group(2).strip()
                param_descs[param_name] = param_desc
            elif param_descs and (line.startswith("        ") or line.startswith("\t\t")):
                last_param = list(param_descs.keys())[-1]
                param_descs[last_param] += " " + stripped
        else:
            if not param_descs and not stripped.startswith(":"):
                desc_lines.append(stripped)

    raw_desc = " ".join([l for l in desc_lines if l]).strip()
    return (raw_desc if raw_desc else None), param_descs


def map_ast_type_to_json_schema(node: Optional[ast.AST]) -> Tuple[str, bool, Optional[Dict[str, Any]]]:
    """Map a Python AST type annotation to (json_type, is_optional, extra_schema_dict)."""
    if node is None:
        return "string", False, None

    if isinstance(node, ast.Name):
        t_id = node.id
        if t_id in ("str", "Text"):
            return "string", False, None
        elif t_id in ("int", "Integer"):
            return "integer", False, None
        elif t_id in ("float", "Number"):
            return "number", False, None
        elif t_id in ("bool", "Boolean"):
            return "boolean", False, None
        elif t_id in ("list", "List", "Sequence", "Iterable", "Set", "set"):
            return "array", False, {"items": {"type": "string"}}
        elif t_id in ("dict", "Dict", "Mapping"):
            return "object", False, None
        elif t_id == "Any":
            return "any", False, None
        elif t_id == "None":
            return "null", True, None
        return "string", False, None

    if isinstance(node, ast.Subscript):
        base_id = ""
        if isinstance(node.value, ast.Name):
            base_id = node.value.id
        elif isinstance(node.value, ast.Attribute):
            base_id = node.value.attr

        slice_node = node.slice

        if base_id in ("Optional", "Union"):
            if base_id == "Optional":
                inner_type, _, extra = map_ast_type_to_json_schema(slice_node)
                return inner_type, True, extra
            elif base_id == "Union":
                elts = slice_node.elts if isinstance(slice_node, ast.Tuple) else [slice_node]
                has_none = any(
                    (isinstance(e, ast.Constant) and e.value is None)
                    or (isinstance(e, ast.Name) and e.id == "None")
                    for e in elts
                )
                non_none = [
                    e for e in elts
                    if not ((isinstance(e, ast.Constant) and e.value is None) or (isinstance(e, ast.Name) and e.id == "None"))
                ]
                if non_none:
                    inner_type, _, extra = map_ast_type_to_json_schema(non_none[0])
                    return inner_type, has_none, extra
                return "string", has_none, None

        if base_id in ("List", "Sequence", "Iterable", "Set"):
            inner_type, _, inner_extra = map_ast_type_to_json_schema(slice_node)
            item_schema = {"type": inner_type}
            if inner_extra:
                item_schema.update(inner_extra)
            return "array", False, {"items": item_schema}

        if base_id in ("Dict", "Mapping"):
            return "object", False, None

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left_type, left_opt, left_extra = map_ast_type_to_json_schema(node.left)
        right_type, right_opt, right_extra = map_ast_type_to_json_schema(node.right)
        is_optional = (
            left_opt
            or right_opt
            or (isinstance(node.right, ast.Constant) and node.right.value is None)
            or (isinstance(node.right, ast.Name) and node.right.id == "None")
        )
        primary_type = left_type if left_type != "null" else right_type
        return primary_type, is_optional, (left_extra or right_extra)

    return "string", False, None


class MCPExtractor:
    """Safe, static AST extractor for Model Context Protocol servers.
    
    Identifies servers, tools, and clients separately and groups tools by their actual
    server implementation.
    """

    def __init__(self, owner: str, repo: str, commit_sha: str):
        self.owner = owner
        self.repo = repo
        self.commit_sha = commit_sha
        self.indicators: List[MCPServerIndicator] = []
        self.warnings: List[str] = []
        self.server_entrypoints: List[str] = []
        self.client_entrypoints: List[str] = []
        self.has_mcp_client: bool = False
        self.detected_framework: str = "unknown"
        self.detected_language: str = "python"
        self.extraction_status: str = "COMPLETE"

        # Discovered servers mapped by server_id (usually entrypoint or server name)
        self.servers_map: Dict[str, DiscoveredServer] = {}

        # Internal registries for correlating manifest scripts with source AST
        self._manifest_scripts: List[Dict[str, Any]] = []
        self._analyzed_files: Dict[str, Dict[str, Any]] = {}

    @property
    def entrypoints(self) -> List[str]:
        """Backwards compatibility alias for server_entrypoints."""
        self._resolve_manifest_scripts()
        return self.server_entrypoints

    def inspect_dependencies(self, file_path: str, content: str) -> None:
        """Inspect build/dependency manifests for MCP SDK declarations."""
        lower_path = file_path.lower()

        # 1. pyproject.toml
        if lower_path.endswith("pyproject.toml"):
            try:
                data = tomllib.loads(content)
                dependencies = []

                project = data.get("project", {})
                if isinstance(project, dict):
                    dependencies.extend(project.get("dependencies", []))
                    opt_deps = project.get("optional-dependencies", {})
                    if isinstance(opt_deps, dict):
                        for group in opt_deps.values():
                            if isinstance(group, list):
                                dependencies.extend(group)

                    # Scripts / entry points: record and defer classification until source is analyzed
                    scripts = project.get("scripts", {})
                    if isinstance(scripts, dict):
                        for script_name, entry_str in scripts.items():
                            self._manifest_scripts.append({
                                "manifest_path": file_path,
                                "script_name": str(script_name),
                                "entry_str": str(entry_str) if entry_str is not None else "",
                                "kind": "script",
                            })

                tool = data.get("tool", {})
                if isinstance(tool, dict):
                    poetry = tool.get("poetry", {})
                    if isinstance(poetry, dict):
                        poetry_deps = poetry.get("dependencies", {})
                        if isinstance(poetry_deps, dict):
                            dependencies.extend(poetry_deps.keys())

                        poetry_scripts = poetry.get("scripts", {})
                        if isinstance(poetry_scripts, dict):
                            for sname, entry_str in poetry_scripts.items():
                                self._manifest_scripts.append({
                                    "manifest_path": file_path,
                                    "script_name": str(sname),
                                    "entry_str": str(entry_str) if entry_str is not None else "",
                                    "kind": "poetry",
                                })

                # Check for mcp dependency - mark as PROBABLE, not confirmed server
                for dep in dependencies:
                    dep_str = str(dep).strip().lower()
                    if re.match(r"^mcp(\[.*\])?([=<>!~].*)?$", dep_str) or dep_str == "mcp":
                        self.indicators.append(
                            MCPServerIndicator(
                                category="sdk_dependency",
                                indicator_type="pyproject_mcp_dependency",
                                confidence="probable",
                                file_path=file_path,
                                details=f"MCP SDK declared in dependencies ({file_path}): '{dep}'. Does not confirm server implementation.",
                            )
                        )
            except Exception as exc:
                self.warnings.append(f"Failed to parse {file_path}: {str(exc)}")
                self.extraction_status = "PARTIAL"

        # 2. requirements.txt
        elif "requirements" in lower_path and lower_path.endswith(".txt"):
            for line_no, line in enumerate(content.splitlines(), start=1):
                clean_line = line.strip().lower()
                if clean_line.startswith("#") or not clean_line:
                    continue
                if re.match(r"^mcp(\[.*\])?([=<>!~].*)?$", clean_line) or clean_line == "mcp":
                    self.indicators.append(
                        MCPServerIndicator(
                            category="sdk_dependency",
                            indicator_type="requirements_mcp_dependency",
                            confidence="probable",
                            file_path=file_path,
                            line_number=line_no,
                            details=f"MCP SDK listed in {file_path}: '{line.strip()}'. Does not confirm server implementation.",
                        )
                    )

        # 3. package.json (Detect TypeScript MCP SDK)
        elif lower_path.endswith("package.json"):
            if "@modelcontextprotocol/sdk" in content:
                self.detected_language = "typescript"
                self.detected_framework = "typescript_sdk"
                self.extraction_status = "UNSUPPORTED"
                self.indicators.append(
                    MCPServerIndicator(
                        category="sdk_dependency",
                        indicator_type="package_json_mcp_sdk",
                        confidence="probable",
                        file_path=file_path,
                        details="Detected TypeScript MCP SDK (@modelcontextprotocol/sdk). Only Python stdio servers are supported in MVP.",
                    )
                )

    def analyze_python_source(self, file_path: str, content: str) -> None:
        """Parse Python source file into AST to identify MCP servers, clients, and tools."""
        # Strictly skip test files to prevent test mocks/fixtures from polluting production tool inventories
        if is_test_file(file_path):
            return

        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError as exc:
            self.warnings.append(
                f"SyntaxError in {file_path}:{exc.lineno}: {exc.msg}. Skipped AST extraction for this file."
            )
            self.extraction_status = "PARTIAL"
            return
        except Exception as exc:
            self.warnings.append(
                f"Could not parse AST for {file_path}: {str(exc)}"
            )
            self.extraction_status = "PARTIAL"
            return

        visitor = _MCPSourceVisitor(file_path, self)
        visitor.visit(tree)
        visitor.finalize_file_servers()
        self._analyzed_files[file_path] = {
            "has_client": visitor.file_has_client,
            "has_server": visitor.file_has_server,
            "server_name": visitor.server_name,
            "tools_count": len(visitor.extracted_tools_for_file),
        }

    def _resolve_manifest_scripts(self) -> None:
        """Associate manifest script entrypoints with their actual implementation."""
        resolved_server: List[str] = [
            ep for ep in self.server_entrypoints
            if " [script: " not in ep and " [poetry: " not in ep
        ]
        resolved_client: List[str] = [
            ep for ep in self.client_entrypoints
            if " [script: " not in ep and " [poetry: " not in ep
        ]

        for item in self._manifest_scripts:
            manifest_path = item["manifest_path"]
            script_name = item["script_name"]
            entry_str = item["entry_str"]
            kind = item["kind"]

            manifest_dir = os.path.dirname(manifest_path)
            tag = f"{manifest_path} [{kind}: {script_name}]"

            # Check associated analyzed source files
            associated_files = [
                info for path, info in self._analyzed_files.items()
                if (manifest_dir and (path.startswith(manifest_dir + "/") or path == manifest_dir))
                or (entry_str and entry_str.split(":")[0].replace(".", "/") in path)
            ]

            has_client_source = any(f["has_client"] for f in associated_files)
            has_server_source = any(f["has_server"] or f["tools_count"] > 0 for f in associated_files)

            path_lower = manifest_path.lower()
            name_lower = script_name.lower()
            entry_lower = entry_str.lower()

            is_client_path = any(k in path_lower for k in ("/clients/", "/client/", "_client/", "client-"))
            is_client_name = "client" in name_lower or "client" in entry_lower
            is_server_path = any(k in path_lower for k in ("/servers/", "/server/", "_server/", "server-"))
            is_server_name = "server" in name_lower or "server" in entry_lower

            # Classification logic with client precedence:
            if (has_client_source and not has_server_source) or (is_client_path and not has_server_source) or (is_client_name and not has_server_source):
                resolved_client.append(tag)
                self.has_mcp_client = True
            elif has_server_source or is_server_path or is_server_name:
                resolved_server.append(tag)
            elif "chatbot" in name_lower and is_client_path:
                resolved_client.append(tag)
                self.has_mcp_client = True
            else:
                pass

        # Final client precedence safety filter:
        # Client-only scripts must NEVER appear as server entrypoints!
        client_set = set(resolved_client)
        self.server_entrypoints = sorted(list(set(
            ep for ep in resolved_server
            if ep not in client_set
            and not any(k in ep.lower() for k in ("/clients/", "/client/"))
        )))
        self.client_entrypoints = sorted(list(set(resolved_client)))

    def generate_discovery_report(self) -> MCPServerDiscovery:
        """Aggregate indicators, servers, and tools into a final validated MCPServerDiscovery report."""
        # Correlate deferred manifest scripts with AST results
        self._resolve_manifest_scripts()

        has_confirmed_server = any(
            ind.confidence == "confirmed"
            and ind.category in ("server_initialization", "tool_decorator", "lowlevel_handler")
            for ind in self.indicators
        )
        has_probable_server = any(
            ind.confidence == "probable" and ind.category == "server_initialization"
            for ind in self.indicators
        )

        all_servers = list(self.servers_map.values())
        total_tools = sum(len(s.tools) for s in all_servers)

        has_server = has_confirmed_server or len(all_servers) > 0 or total_tools > 0

        # Classify confidence
        if self.detected_framework == "typescript_sdk":
            has_server = True
            confidence = "unsupported"
            self.extraction_status = "UNSUPPORTED"
            self.warnings.append(
                "Repository appears to be a TypeScript MCP project. Only Python MCP servers are supported in the MVP."
            )
        elif has_confirmed_server or total_tools > 0:
            confidence = "confirmed"
        elif has_probable_server:
            confidence = "probable"
        else:
            confidence = "inconclusive"

        # Check client-only scenario
        if self.has_mcp_client and not has_server:
            confidence = "inconclusive"
            self.warnings.append(
                "Repository contains MCP client implementation (ClientSession), but no MCP server implementation or tools were found."
            )

        # Sort tools inside each server and assemble flattened tools list
        flattened_tools: List[ExtractedTool] = []
        for s in all_servers:
            s.tools.sort(key=lambda t: t.name)
            flattened_tools.extend(s.tools)

        flattened_tools.sort(key=lambda t: t.name)

        # Ensure extraction status conforms to strict states: COMPLETE, PARTIAL, FAILED, UNSUPPORTED
        final_status = self.extraction_status
        if final_status not in ("COMPLETE", "PARTIAL", "FAILED", "UNSUPPORTED"):
            final_status = "COMPLETE" if not self.warnings else "PARTIAL"

        return MCPServerDiscovery(
            has_mcp_server=has_server,
            has_mcp_client=self.has_mcp_client,
            confidence=confidence,
            framework=self.detected_framework,
            language=self.detected_language,
            server_entrypoints=sorted(list(set(self.server_entrypoints))),
            client_entrypoints=sorted(list(set(self.client_entrypoints))),
            servers=sorted(all_servers, key=lambda s: s.name),
            indicators=self.indicators,
            extracted_tools=flattened_tools,
            extraction_status=final_status,
            extraction_warnings=self.warnings,
            runtime_verification_required=True,
        )


class _MCPSourceVisitor(ast.NodeVisitor):
    """AST NodeVisitor to discover MCP imports, server instances, tool decorators, and tool definitions."""

    def __init__(self, file_path: str, extractor: MCPExtractor):
        self.file_path = file_path
        self.extractor = extractor
        self.file_has_server = False
        self.file_has_client = False
        self.server_name: Optional[str] = None
        self.server_framework: str = "fastmcp"
        self.server_var_names: Set[str] = set()
        self.extracted_tools_for_file: List[ExtractedTool] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.name
            if name.startswith("mcp.client") or name == "mcp.client":
                self.file_has_client = True
                self.extractor.has_mcp_client = True
                self.extractor.indicators.append(
                    MCPServerIndicator(
                        category="client_usage",
                        indicator_type="client_import",
                        confidence="confirmed",
                        file_path=self.file_path,
                        line_number=node.lineno,
                        details=f"Imports MCP Client module '{name}'",
                    )
                )
            elif name.startswith("mcp.server") or name == "mcp.server":
                self.file_has_server = True
                self.extractor.indicators.append(
                    MCPServerIndicator(
                        category="server_initialization",
                        indicator_type="server_import",
                        confidence="probable",
                        file_path=self.file_path,
                        line_number=node.lineno,
                        details=f"Imports MCP Server module '{name}'",
                    )
                )
            elif name == "mcp":
                self.extractor.indicators.append(
                    MCPServerIndicator(
                        category="sdk_dependency",
                        indicator_type="mcp_import",
                        confidence="probable",
                        file_path=self.file_path,
                        line_number=node.lineno,
                        details="Imports top-level 'mcp' module",
                    )
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = node.module or ""
        # Client imports
        if "client" in mod or any(alias.name in ("ClientSession", "stdio_client", "sse_client") for alias in node.names):
            self.file_has_client = True
            self.extractor.has_mcp_client = True
            self.extractor.indicators.append(
                MCPServerIndicator(
                    category="client_usage",
                    indicator_type="client_import",
                    confidence="confirmed",
                    file_path=self.file_path,
                    line_number=node.lineno,
                    details=f"Imports MCP client components from '{mod}'",
                )
            )

        # Server imports
        if mod == "mcp" or mod.startswith("mcp."):
            for alias in node.names:
                name = alias.name
                if name == "FastMCP":
                    self.server_framework = "fastmcp"
                    if self.extractor.detected_framework == "unknown":
                        self.extractor.detected_framework = "fastmcp"
                    self.extractor.indicators.append(
                        MCPServerIndicator(
                            category="server_initialization",
                            indicator_type="fastmcp_import",
                            confidence="probable",
                            file_path=self.file_path,
                            line_number=node.lineno,
                            details="Imports FastMCP from official SDK",
                        )
                    )
                elif name == "Server":
                    self.server_framework = "mcp_lowlevel"
                    if self.extractor.detected_framework == "unknown":
                        self.extractor.detected_framework = "mcp_lowlevel"
                    self.extractor.indicators.append(
                        MCPServerIndicator(
                            category="server_initialization",
                            indicator_type="lowlevel_server_import",
                            confidence="probable",
                            file_path=self.file_path,
                            line_number=node.lineno,
                            details="Imports low-level Server from official SDK",
                        )
                    )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Detect server vs client variable instantiation."""
        if isinstance(node.value, ast.Call):
            call = node.value
            func_name = ""
            if isinstance(call.func, ast.Name):
                func_name = call.func.id
            elif isinstance(call.func, ast.Attribute):
                func_name = call.func.attr

            # 1. Client instantiation: ClientSession(...)
            if func_name == "ClientSession":
                self.file_has_client = True
                self.extractor.has_mcp_client = True
                self.extractor.indicators.append(
                    MCPServerIndicator(
                        category="client_usage",
                        indicator_type="client_session_instance",
                        confidence="confirmed",
                        file_path=self.file_path,
                        line_number=node.lineno,
                        details="Instantiates ClientSession client object",
                    )
                )

            # 2. Server instantiation: FastMCP(...) or Server(...)
            elif func_name in ("FastMCP", "Server"):
                is_fastmcp = func_name == "FastMCP"
                self.file_has_server = True
                framework_name = "fastmcp" if is_fastmcp else "mcp_lowlevel"
                self.server_framework = framework_name
                self.extractor.detected_framework = framework_name

                # Extract server name from first positional argument if string literal
                extracted_name = None
                if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
                    extracted_name = call.args[0].value
                elif call.keywords:
                    for kw in call.keywords:
                        if kw.arg in ("name", "server_name") and isinstance(kw.value, ast.Constant):
                            extracted_name = str(kw.value.value)

                if extracted_name:
                    self.server_name = extracted_name
                else:
                    # Fallback to file basename
                    base = os.path.basename(self.file_path)
                    self.server_name = base[:-3] if base.endswith(".py") else base

                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.server_var_names.add(target.id)
                        self.extractor.indicators.append(
                            MCPServerIndicator(
                                category="server_initialization",
                                indicator_type=f"{framework_name}_instance",
                                confidence="confirmed",
                                file_path=self.file_path,
                                line_number=node.lineno,
                                details=f"Instantiates {framework_name.capitalize()} server '{self.server_name}' (var: {target.id})",
                            )
                        )

        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function_for_tools(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_function_for_tools(node)
        self._check_lowlevel_list_tools(node)
        self.generic_visit(node)

    def _check_function_for_tools(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        is_tool_decorator = False
        tool_custom_name: Optional[str] = None
        tool_custom_desc: Optional[str] = None

        for dec in node.decorator_list:
            call_node: Optional[ast.Call] = None
            func_node: ast.AST = dec

            if isinstance(dec, ast.Call):
                call_node = dec
                func_node = dec.func

            if isinstance(func_node, ast.Attribute) and func_node.attr == "tool":
                is_tool_decorator = True
                if isinstance(func_node.value, ast.Name):
                    self.server_var_names.add(func_node.value.id)
            elif isinstance(func_node, ast.Name) and func_node.id == "tool":
                is_tool_decorator = True

            if is_tool_decorator and call_node:
                for kw in call_node.keywords:
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                        tool_custom_name = str(kw.value.value)
                    elif kw.arg == "description" and isinstance(kw.value, ast.Constant):
                        tool_custom_desc = str(kw.value.value)

            if is_tool_decorator:
                break

        if not is_tool_decorator:
            return

        self.file_has_server = True
        self.extractor.indicators.append(
            MCPServerIndicator(
                category="tool_decorator",
                indicator_type="fastmcp_tool_decorator",
                confidence="confirmed",
                file_path=self.file_path,
                line_number=node.lineno,
                details=f"Tool function '{node.name}' decorated with @tool",
            )
        )

        tool_name = tool_custom_name or node.name
        # Avoid duplicate tools in the same file
        if any(t.name == tool_name for t in self.extracted_tools_for_file):
            return

        raw_docstring = ast.get_docstring(node)
        doc_desc, param_descs = parse_docstring_params(raw_docstring)
        tool_desc = tool_custom_desc or doc_desc

        args_schema, parameters = self._extract_function_parameters(node, param_descs)

        extracted = ExtractedTool(
            name=tool_name,
            description=tool_desc,
            input_schema=args_schema,
            parameters=parameters,
            source_file=self.file_path,
            source_line=node.lineno,
            server_name=self.server_name,
        )
        self.extracted_tools_for_file.append(extracted)

    def _extract_function_parameters(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        param_descs: Dict[str, str],
    ) -> Tuple[Dict[str, Any], List[ToolParameter]]:
        properties: Dict[str, Any] = {}
        required: List[str] = []
        parameters: List[ToolParameter] = []

        all_args = node.args.args
        kwonly_args = node.args.kwonlyargs

        num_pos = len(all_args)
        num_defaults = len(node.args.defaults)
        defaults_offset = num_pos - num_defaults

        for idx, arg in enumerate(all_args):
            name = arg.arg
            if name in ("self", "cls", "ctx", "context"):
                continue

            has_default = idx >= defaults_offset
            default_val = None
            if has_default:
                default_node = node.args.defaults[idx - defaults_offset]
                default_val = safe_eval_ast_literal(default_node)

            param_type, is_optional_annotated, extra = map_ast_type_to_json_schema(arg.annotation)
            is_required = (not has_default) and (not is_optional_annotated)
            description = param_descs.get(name)

            prop_schema: Dict[str, Any] = {"type": param_type}
            if description:
                prop_schema["description"] = description
            if has_default and default_val is not None:
                prop_schema["default"] = default_val
            if extra:
                prop_schema.update(extra)

            properties[name] = prop_schema
            if is_required:
                required.append(name)

            parameters.append(
                ToolParameter(
                    name=name,
                    type=param_type,
                    description=description,
                    required=is_required,
                    default=default_val,
                    items=extra.get("items") if extra else None,
                    properties=extra.get("properties") if extra else None,
                )
            )

        for idx, arg in enumerate(kwonly_args):
            name = arg.arg
            if name in ("self", "cls", "ctx", "context"):
                continue

            default_node = node.args.kw_defaults[idx] if idx < len(node.args.kw_defaults) else None
            has_default = default_node is not None
            default_val = safe_eval_ast_literal(default_node) if has_default else None

            param_type, is_optional_annotated, extra = map_ast_type_to_json_schema(arg.annotation)
            is_required = (not has_default) and (not is_optional_annotated)
            description = param_descs.get(name)

            prop_schema = {"type": param_type}
            if description:
                prop_schema["description"] = description
            if has_default and default_val is not None:
                prop_schema["default"] = default_val
            if extra:
                prop_schema.update(extra)

            properties[name] = prop_schema
            if is_required:
                required.append(name)

            parameters.append(
                ToolParameter(
                    name=name,
                    type=param_type,
                    description=description,
                    required=is_required,
                    default=default_val,
                    items=extra.get("items") if extra else None,
                    properties=extra.get("properties") if extra else None,
                )
            )

        schema = {
            "type": "object",
            "properties": properties,
            "required": required,
        }
        return schema, parameters

    def _check_lowlevel_list_tools(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        is_list_tools = False
        for dec in node.decorator_list:
            func = dec.func if isinstance(dec, ast.Call) else dec
            if isinstance(func, ast.Attribute) and func.attr == "list_tools":
                is_list_tools = True
                break

        if not is_list_tools:
            return

        self.file_has_server = True
        self.server_framework = "mcp_lowlevel"
        self.extractor.detected_framework = "mcp_lowlevel"
        self.extractor.indicators.append(
            MCPServerIndicator(
                category="lowlevel_handler",
                indicator_type="list_tools_handler",
                confidence="confirmed",
                file_path=self.file_path,
                line_number=node.lineno,
                details=f"Low-level MCP tool handler registered in function '{node.name}'",
            )
        )

        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Return) and stmt.value:
                tool_list_node: Optional[ast.List] = None
                if isinstance(stmt.value, ast.List):
                    tool_list_node = stmt.value

                if tool_list_node:
                    for elt in tool_list_node.elts:
                        tool_item = self._extract_lowlevel_tool_item(elt)
                        if tool_item and not any(t.name == tool_item.name for t in self.extracted_tools_for_file):
                            tool_item.server_name = self.server_name
                            self.extracted_tools_for_file.append(tool_item)

    def _extract_lowlevel_tool_item(self, node: ast.AST) -> Optional[ExtractedTool]:
        name: Optional[str] = None
        desc: Optional[str] = None
        input_schema: Dict[str, Any] = {"type": "object", "properties": {}, "required": []}

        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    name = str(kw.value.value)
                elif kw.arg == "description" and isinstance(kw.value, ast.Constant):
                    desc = str(kw.value.value)
                elif kw.arg in ("inputSchema", "input_schema"):
                    schema_val = safe_eval_ast_literal(kw.value)
                    if isinstance(schema_val, dict):
                        input_schema = schema_val

        elif isinstance(node, ast.Dict):
            dict_val = safe_eval_ast_literal(node)
            if isinstance(dict_val, dict):
                name = dict_val.get("name")
                desc = dict_val.get("description")
                schema_cand = dict_val.get("inputSchema") or dict_val.get("input_schema")
                if isinstance(schema_cand, dict):
                    input_schema = schema_cand

        if not name:
            return None

        parameters: List[ToolParameter] = []
        props = input_schema.get("properties", {})
        required_list = input_schema.get("required", [])

        if isinstance(props, dict):
            for p_name, p_def in props.items():
                if isinstance(p_def, dict):
                    p_type = p_def.get("type", "string")
                    p_desc = p_def.get("description")
                    p_req = p_name in required_list
                    p_default = p_def.get("default")
                    p_enum = p_def.get("enum")
                    p_items = p_def.get("items")
                    p_properties = p_def.get("properties")

                    parameters.append(
                        ToolParameter(
                            name=p_name,
                            type=str(p_type),
                            description=p_desc,
                            required=p_req,
                            default=p_default,
                            enum_values=p_enum,
                            items=p_items,
                            properties=p_properties,
                        )
                    )

        return ExtractedTool(
            name=name,
            description=desc,
            input_schema=input_schema,
            parameters=parameters,
            source_file=self.file_path,
            source_line=getattr(node, "lineno", None),
            server_name=self.server_name,
        )

    def finalize_file_servers(self) -> None:
        """Register discovered server implementation or client entrypoint."""
        # Client precedence: if file is demonstrably a client and defines no tools, classify strictly as client
        if self.file_has_client and len(self.extracted_tools_for_file) == 0:
            self.extractor.client_entrypoints.append(self.file_path)
            self.extractor.has_mcp_client = True
            return

        if self.file_has_server:
            self.extractor.server_entrypoints.append(self.file_path)

            server_name = self.server_name
            if not server_name or server_name.lower() in ("server", "main", "app", "__init__"):
                dir_name = os.path.basename(os.path.dirname(self.file_path))
                if dir_name and dir_name not in (".", "", "/"):
                    server_name = dir_name
                else:
                    base = os.path.basename(self.file_path)
                    server_name = base[:-3] if base.endswith(".py") else base

            server_id = f"{server_name}:{self.file_path}"
            if server_id not in self.extractor.servers_map:
                self.extractor.servers_map[server_id] = DiscoveredServer(
                    server_id=server_id,
                    name=server_name,
                    entrypoint=self.file_path,
                    framework=self.server_framework,
                    tools=[],
                )

            # Associate extracted tools with this server
            for tool in self.extracted_tools_for_file:
                tool.server_name = server_name
                # Avoid duplicates in same server
                if not any(t.name == tool.name for t in self.extractor.servers_map[server_id].tools):
                    self.extractor.servers_map[server_id].tools.append(tool)

        elif self.file_has_client:
            self.extractor.client_entrypoints.append(self.file_path)
