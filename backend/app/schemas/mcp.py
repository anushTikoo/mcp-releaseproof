"""Pydantic schemas for MCP server discovery, static tool extraction, and schema comparison."""

import hashlib
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


def compute_schema_hash(schema: Dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash of a normalized JSON Schema dictionary."""
    normalized_json = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized_json.encode("utf-8")).hexdigest()


class ToolParameter(BaseModel):
    """Normalized representation of a single tool input parameter."""
    name: str = Field(description="Parameter name")
    type: str = Field(
        default="string",
        description="JSON Schema data type (string, integer, number, boolean, array, object, any)",
    )
    description: Optional[str] = Field(default=None, description="Parameter description")
    required: bool = Field(default=True, description="Whether the parameter is required")
    default: Optional[Any] = Field(default=None, description="Default value if optional")
    enum_values: Optional[List[Any]] = Field(default=None, description="Enum constraint values if defined")
    items: Optional[Dict[str, Any]] = Field(
        default=None, description="Item schema definition if parameter is an array"
    )
    properties: Optional[Dict[str, Any]] = Field(
        default=None, description="Nested property definitions if parameter is an object"
    )


class ExtractedTool(BaseModel):
    """Structured representation of an extracted MCP tool definition."""
    name: str = Field(description="Tool identifier/name")
    description: Optional[str] = Field(default=None, description="Tool purpose and behavior description")
    input_schema: Dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}, "required": []},
        description="Standard JSON Schema describing accepted arguments",
    )
    parameters: List[ToolParameter] = Field(
        default_factory=list,
        description="Normalized list of extracted parameters for structured inspection",
    )
    source_file: Optional[str] = Field(default=None, description="Path of the source file where defined")
    source_line: Optional[int] = Field(default=None, description="Line number where defined in source file")
    server_name: Optional[str] = Field(default=None, description="Associated server implementation name")
    schema_hash: str = Field(
        default="",
        description="SHA-256 hash of normalized input schema for deterministic diffing",
    )

    def model_post_init(self, __context: Any) -> None:
        if not self.schema_hash and self.input_schema:
            self.schema_hash = compute_schema_hash(self.input_schema)


class MCPServerIndicator(BaseModel):
    """Evidence or heuristic indicator identifying an MCP server or client implementation."""
    category: str = Field(
        description="Indicator category: sdk_dependency, server_initialization, client_usage, tool_decorator, lowlevel_handler, entrypoint_script, configuration"
    )
    indicator_type: str = Field(description="Specific indicator tag (e.g. fastmcp_instance, client_session)")
    confidence: str = Field(
        description="Indicator confidence: confirmed, probable, inconclusive"
    )
    file_path: str = Field(description="File where indicator was detected")
    line_number: Optional[int] = Field(default=None, description="Line number if applicable")
    details: str = Field(description="Human-readable description of detected indicator")


class DiscoveredServer(BaseModel):
    """An individual MCP server implementation discovered within the repository."""
    server_id: str = Field(description="Unique server identifier (e.g. server name or entrypoint relative path)")
    name: str = Field(description="Server name from FastMCP('name'), Server('name'), or filename")
    entrypoint: str = Field(description="Entrypoint or implementation source file path")
    framework: str = Field(default="fastmcp", description="Detected framework: fastmcp, mcp_lowlevel, custom")
    description: Optional[str] = Field(default=None, description="Server description if available")
    tools: List[ExtractedTool] = Field(default_factory=list, description="Tools registered on this specific server")


class MCPServerDiscovery(BaseModel):
    """Overall discovery report for a repository version."""
    has_mcp_server: bool = Field(
        description="True if confirmed or probable MCP server indicators were found"
    )
    has_mcp_client: bool = Field(
        default=False,
        description="True if MCP client usage or ClientSession was identified in the repository",
    )
    confidence: str = Field(
        description="Discovery classification: confirmed, probable, inconclusive, unsupported"
    )
    framework: str = Field(
        description="Detected framework: fastmcp, mcp_lowlevel, typescript_sdk, custom, unknown"
    )
    language: str = Field(
        default="python",
        description="Primary server language: python, typescript, unknown",
    )
    server_entrypoints: List[str] = Field(
        default_factory=list,
        description="Likely server entrypoint files (e.g. server.py, main.py)",
    )
    client_entrypoints: List[str] = Field(
        default_factory=list,
        description="Identified MCP client entrypoints or client scripts",
    )
    servers: List[DiscoveredServer] = Field(
        default_factory=list,
        description="Individually grouped MCP server instances discovered in repository",
    )
    indicators: List[MCPServerIndicator] = Field(
        default_factory=list,
        description="List of detected evidence indicators",
    )
    extracted_tools: List[ExtractedTool] = Field(
        default_factory=list,
        description="Repository-wide inventory of extracted MCP tools",
    )
    extraction_status: str = Field(
        default="COMPLETE",
        description="Explicit status: COMPLETE, PARTIAL, FAILED, UNSUPPORTED",
    )
    extraction_warnings: List[str] = Field(
        default_factory=list,
        description="Warnings regarding dynamic decorators, external schemas, or static analysis blind spots",
    )
    runtime_verification_required: bool = Field(
        default=True,
        description="Always true for static extraction, indicating Docker sandbox runtime execution is required for definitive proof (Phase 6)",
    )


class DiscoverMCPRequest(BaseModel):
    """Request payload to discover MCP servers and extract tools from a GitHub repository ref."""
    repository_url: str = Field(
        description="Public HTTPS GitHub repository URL (e.g. https://github.com/owner/repo)"
    )
    ref: str = Field(
        min_length=1,
        description="Git reference (branch name, tag, or commit SHA)",
    )


class DiscoverMCPResponse(BaseModel):
    """Response payload for MCP server discovery and tool extraction."""
    status: str = Field(default="success", description="Response status")
    repository_url: str = Field(description="Canonical repository URL")
    ref: str = Field(description="User-supplied Git ref")
    commit_sha: str = Field(description="Resolved immutable commit SHA")
    discovery: MCPServerDiscovery = Field(description="Detailed discovery and extraction results")


class ToolDifference(BaseModel):
    """Detailed diff for a single MCP tool between baseline and candidate versions."""
    tool_name: str = Field(description="Name of the tool")
    server_id: Optional[str] = Field(default=None, description="Server ID where tool belongs")
    change_type: str = Field(
        description="Change classification: added, removed, modified_schema, modified_description, modified_both, unchanged"
    )
    baseline_tool: Optional[ExtractedTool] = Field(
        default=None, description="Tool definition in baseline version, if present"
    )
    candidate_tool: Optional[ExtractedTool] = Field(
        default=None, description="Tool definition in candidate version, if present"
    )
    changes_detected: List[str] = Field(
        default_factory=list,
        description="List of specific changes (e.g. added required parameter 'path', description updated)",
    )


class ToolComparisonSummary(BaseModel):
    """Summary counts of tool changes between baseline and candidate versions."""
    total_baseline_tools: int = Field(default=0, description="Total tools in baseline")
    total_candidate_tools: int = Field(default=0, description="Total tools in candidate")
    added_count: int = Field(default=0, description="Tools present in candidate but not baseline")
    removed_count: int = Field(default=0, description="Tools present in baseline but not candidate")
    modified_count: int = Field(default=0, description="Tools present in both with schema or description changes")
    unchanged_count: int = Field(default=0, description="Tools present in both with identical schema and description")
    is_complete: bool = Field(
        default=True,
        description="False if either baseline or candidate extraction was PARTIAL, FAILED, or omitted files.",
    )


class ServerComparison(BaseModel):
    """Comparison between baseline and candidate versions of a specific MCP server."""
    server_id: str = Field(description="Matched server identifier")
    server_name: str = Field(description="Human-readable server name")
    baseline_entrypoint: Optional[str] = Field(default=None, description="Baseline entrypoint path")
    candidate_entrypoint: Optional[str] = Field(default=None, description="Candidate entrypoint path")
    status: str = Field(description="Server status: matched, added, removed, ambiguous")
    summary: ToolComparisonSummary = Field(description="Summary of tool changes for this server")
    differences: List[ToolDifference] = Field(default_factory=list, description="Tool differences for this server")


class CompareMCPToolsRequest(BaseModel):
    """Request payload to compare MCP tools between baseline and candidate refs."""
    repository_url: str = Field(
        description="Public HTTPS GitHub repository URL (e.g. https://github.com/owner/repo)"
    )
    baseline_ref: str = Field(
        min_length=1,
        description="Baseline Git ref (branch name, tag, or commit SHA)",
    )
    candidate_ref: str = Field(
        min_length=1,
        description="Candidate Git ref (branch name, tag, or commit SHA)",
    )


class CompareMCPToolsResponse(BaseModel):
    """Response payload comparing MCP tools between baseline and candidate versions."""
    status: str = Field(default="success", description="Response status")
    repository_url: str = Field(description="Canonical repository URL")
    baseline_ref: str = Field(description="Baseline Git ref")
    baseline_sha: str = Field(description="Resolved baseline commit SHA")
    candidate_ref: str = Field(description="Candidate Git ref")
    candidate_sha: str = Field(description="Resolved candidate commit SHA")
    baseline_discovery: MCPServerDiscovery = Field(description="Baseline discovery results")
    candidate_discovery: MCPServerDiscovery = Field(description="Candidate discovery results")
    summary: ToolComparisonSummary = Field(description="Repository-wide comparison summary counts")
    differences: List[ToolDifference] = Field(
        default_factory=list,
        description="Repository-wide list of per-tool differences, ordered deterministically by tool name",
    )
    server_comparisons: List[ServerComparison] = Field(
        default_factory=list,
        description="Per-server comparison breakdowns between baseline and candidate",
    )
