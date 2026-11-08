"""Pydantic schemas for Phase 5 AI-generated test harness and static security validation."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.inference import DiscoveredToolInput, TestPlan

# Maximum HTTP request body size for harness generation and validation endpoints (512 KB)
MAX_HARNESS_REQUEST_BODY_BYTES: int = 524_288


class HarnessMetadata(BaseModel):
    """Metadata regarding the generated test harness structure and coverage."""
    __test__ = False
    test_count: int = Field(default=0, description="Number of discovered test functions in harness")
    scenarios_covered: List[str] = Field(
        default_factory=list, description="IDs of test scenarios implemented in the harness"
    )
    tools_tested: List[str] = Field(
        default_factory=list, description="Names of MCP tools invoked by the harness"
    )
    framework: str = Field(default="pytest-asyncio", description="Test framework target")
    summary: str = Field(default="", description="High-level description of generated test cases")


class HarnessValidationResult(BaseModel):
    """Static security and structural validation results for a Python test harness."""
    __test__ = False
    is_valid: bool = Field(description="True if harness passes all AST and security checks")
    syntax_valid: bool = Field(description="True if code parsed successfully into a valid Python AST")
    security_valid: bool = Field(description="True if no prohibited calls, imports, or escapes detected")
    structure_valid: bool = Field(description="True if harness conforms to test function structure")
    schema_valid: bool = Field(description="True if tool arguments match discovered tool schemas")
    rejection_reasons: List[str] = Field(
        default_factory=list, description="Specific reasons for rejection if validation failed"
    )
    warnings: List[str] = Field(
        default_factory=list, description="Non-fatal warnings or analysis notes"
    )
    identified_imports: List[str] = Field(
        default_factory=list, description="All module imports identified in AST"
    )
    identified_tool_calls: List[str] = Field(
        default_factory=list, description="All MCP tool names invoked in the harness"
    )
    identified_scenarios: List[str] = Field(
        default_factory=list, description="Static scenario matches (runtime execution unverified)"
    )
    ast_node_count: int = Field(default=0, description="Total number of AST nodes analyzed")
    line_count: int = Field(default=0, description="Number of source lines in harness")


class GeneratedHarnessPayload(BaseModel):
    """Structured LLM completion payload for Python test harness generation."""
    __test__ = False
    harness_code: str = Field(
        description="Clean, executable Python test harness source code using pytest-asyncio and MCP client"
    )
    scenarios_covered: List[str] = Field(
        default_factory=list, description="List of scenario IDs covered by the code"
    )
    tools_tested: List[str] = Field(
        default_factory=list, description="List of MCP tool names called by the test functions"
    )
    summary: str = Field(
        default="", description="One to two sentence summary of test cases implemented"
    )


class GenerateHarnessRequest(BaseModel):
    """Client request to generate and statically validate an executable test harness."""
    __test__ = False
    repository_url: str = Field(
        pattern=r"^https:\/\/github\.com\/[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+(?:\/)?$",
        description="Public HTTPS GitHub repository URL",
    )
    commit_sha: str = Field(
        pattern=r"^[0-9a-fA-F]{40}$",
        description="Resolved immutable 40-character hexadecimal commit SHA",
    )
    ref: Optional[str] = Field(default=None, description="Git reference label (tag, branch)")
    server_name: Optional[str] = Field(
        default=None, description="Optional specific server implementation name"
    )
    tools: List[DiscoveredToolInput] = Field(
        min_length=1, max_length=100, description="Discovered MCP tools to formulate test harness for"
    )
    test_plan: TestPlan = Field(
        description="Structured test plan from Phase 2 defining scenarios and steps"
    )
    model_id: Optional[str] = Field(
        default=None, description="Optional Vultr model ID override"
    )
    max_tokens: Optional[int] = Field(
        default=None, description="Optional token budget limit (default: 2500, max: 3500)"
    )


class GenerateHarnessResponse(BaseModel):
    """Response containing generated test harness code and static security validation verdict."""
    __test__ = False
    status: str = Field(
        description="Outcome status: success (validated) or rejected (validation failed)"
    )
    repository_url: str = Field(description="Target repository URL")
    commit_sha: str = Field(description="Target commit SHA")
    model: str = Field(description="Vultr inference model used")
    harness_code: str = Field(description="Generated Python test harness code")
    metadata: HarnessMetadata = Field(description="Harness metadata and scenario mapping")
    validation: HarnessValidationResult = Field(
        description="Detailed static security and schema validation verdict"
    )
    inventory_origin: str = Field(
        default="caller_supplied_unverified",
        description="Origin of tool definitions and schemas evaluated by the harness",
    )
    trust_boundary_notice: str = Field(
        default=(
            "Tool inventories and test plans were supplied by the caller without cryptographic binding "
            "to the resolved commit. Constraints may have been modified or weakened by the caller. "
            "Independent sandbox isolation remains mandatory in Phase 6."
        ),
        description="Notice explaining security trust boundary of caller-supplied inventories",
    )
    usage: Optional[Dict[str, Any]] = Field(
        default=None, description="Inference token usage details"
    )
    duration_ms: float = Field(description="Inference and validation duration in milliseconds")


class ValidateHarnessRequest(BaseModel):
    """Request to statically validate a Python test harness without executing it."""
    __test__ = False
    harness_code: str = Field(
        min_length=1, max_length=65_536, description="Python test harness source code (max 64KB)"
    )
    tools: List[DiscoveredToolInput] = Field(
        default_factory=list, max_length=100, description="Discovered MCP tools to validate references against"
    )
    test_plan: Optional[TestPlan] = Field(
        default=None, description="Optional test plan to cross-reference scenario IDs"
    )


class ValidateHarnessResponse(BaseModel):
    """Response from static harness security validator."""
    __test__ = False
    status: str = Field(description="Validation outcome: valid or rejected")
    validation: HarnessValidationResult = Field(description="Static security validation results")
    inventory_origin: str = Field(
        default="caller_supplied_unverified",
        description="Origin of tool definitions and schemas evaluated by the harness",
    )
    trust_boundary_notice: str = Field(
        default=(
            "Tool inventories and test plans were supplied by the caller without cryptographic binding "
            "to the resolved commit. Constraints may have been modified or weakened by the caller. "
            "Independent sandbox isolation remains mandatory in Phase 6."
        ),
        description="Notice explaining security trust boundary of caller-supplied inventories",
    )

