"""Unit tests for MCPService and tool comparison logic."""

import pytest
from app.schemas.mcp import ExtractedTool
from app.services.mcp_service import MCPService


def test_tool_diff_addition_and_removal():
    baseline_tools = [
        ExtractedTool(
            name="tool_a",
            description="Tool A original",
            input_schema={"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
        ),
        ExtractedTool(
            name="tool_b",
            description="Tool B deprecated",
            input_schema={"type": "object", "properties": {}, "required": []},
        ),
    ]

    candidate_tools = [
        ExtractedTool(
            name="tool_a",
            description="Tool A original",
            input_schema={"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
        ),
        ExtractedTool(
            name="tool_c",
            description="Tool C newly introduced",
            input_schema={"type": "object", "properties": {"y": {"type": "integer"}}, "required": ["y"]},
        ),
    ]

    diffs, summary = MCPService.compute_tool_diff(baseline_tools, candidate_tools)

    assert summary.total_baseline_tools == 2
    assert summary.total_candidate_tools == 2
    assert summary.added_count == 1
    assert summary.removed_count == 1
    assert summary.unchanged_count == 1
    assert summary.modified_count == 0

    diff_map = {d.tool_name: d for d in diffs}
    assert diff_map["tool_c"].change_type == "added"
    assert diff_map["tool_b"].change_type == "removed"
    assert diff_map["tool_a"].change_type == "unchanged"


def test_tool_diff_schema_and_description_changes():
    baseline_tools = [
        ExtractedTool(
            name="read_file",
            description="Old description",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        ),
        ExtractedTool(
            name="list_files",
            description="List files",
            input_schema={
                "type": "object",
                "properties": {"directory": {"type": "string"}},
                "required": ["directory"],
            },
        ),
        ExtractedTool(
            name="write_file",
            description="Write file",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path"],
            },
        ),
    ]

    candidate_tools = [
        # read_file: only description changed
        ExtractedTool(
            name="read_file",
            description="Updated description with security details",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        ),
        # list_files: schema changed (added parameter 'max_depth' and changed required)
        ExtractedTool(
            name="list_files",
            description="List files",
            input_schema={
                "type": "object",
                "properties": {
                    "directory": {"type": "string"},
                    "max_depth": {"type": "integer"},
                },
                "required": ["directory", "max_depth"],
            },
        ),
        # write_file: both description and schema changed
        ExtractedTool(
            name="write_file",
            description="Write file safely with confirmation",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "overwrite": {"type": "boolean"},
                },
                "required": ["path", "content"],
            },
        ),
    ]

    diffs, summary = MCPService.compute_tool_diff(baseline_tools, candidate_tools)

    assert summary.modified_count == 3
    assert summary.unchanged_count == 0

    diff_map = {d.tool_name: d for d in diffs}
    assert diff_map["read_file"].change_type == "modified_description"
    assert "Description was updated" in diff_map["read_file"].changes_detected

    assert diff_map["list_files"].change_type == "modified_schema"
    assert any("max_depth" in c for c in diff_map["list_files"].changes_detected)

    assert diff_map["write_file"].change_type == "modified_both"


def test_tool_diff_order_independence():
    # Tools in different order in baseline vs candidate
    t1 = ExtractedTool(name="alpha", description="A", input_schema={"type": "object", "properties": {}})
    t2 = ExtractedTool(name="beta", description="B", input_schema={"type": "object", "properties": {}})
    t3 = ExtractedTool(name="gamma", description="C", input_schema={"type": "object", "properties": {}})

    baseline = [t3, t1, t2]
    candidate = [t1, t2, t3]

    diffs, summary = MCPService.compute_tool_diff(baseline, candidate)

    assert summary.unchanged_count == 3
    assert summary.modified_count == 0
    assert summary.added_count == 0
    assert summary.removed_count == 0
    # Differences must be sorted alphabetically by tool_name
    assert [d.tool_name for d in diffs] == ["alpha", "beta", "gamma"]
    for d in diffs:
        assert d.change_type == "unchanged"



def test_server_grouped_comparison():
    from app.schemas.mcp import DiscoveredServer

    tool_t1 = ExtractedTool(name="get_temp", description="T", input_schema={"type": "object", "properties": {}})
    tool_t2 = ExtractedTool(name="get_forecast", description="F", input_schema={"type": "object", "properties": {}})
    tool_db1 = ExtractedTool(name="query_sql", description="Q", input_schema={"type": "object", "properties": {}})

    base_servers = [
        DiscoveredServer(
            server_id="src/weather.py",
            name="weather_server",
            entrypoint="src/weather.py",
            framework="fastmcp",
            tools=[tool_t1],
        ),
        DiscoveredServer(
            server_id="src/db.py",
            name="db_server",
            entrypoint="src/db.py",
            framework="fastmcp",
            tools=[tool_db1],
        ),
    ]

    cand_servers = [
        # weather_server has added get_forecast
        DiscoveredServer(
            server_id="src/weather.py",
            name="weather_server",
            entrypoint="src/weather.py",
            framework="fastmcp",
            tools=[tool_t1, tool_t2],
        ),
        # db_server is identical
        DiscoveredServer(
            server_id="src/db.py",
            name="db_server",
            entrypoint="src/db.py",
            framework="fastmcp",
            tools=[tool_db1],
        ),
    ]

    comparisons = MCPService.compare_servers(base_servers, cand_servers)
    assert len(comparisons) == 2

    comp_map = {c.server_name: c for c in comparisons}
    weather_comp = comp_map["weather_server"]
    assert weather_comp.status == "matched"
    assert weather_comp.summary.added_count == 1
    assert weather_comp.summary.unchanged_count == 1
    assert weather_comp.differences[0].tool_name == "get_forecast" or weather_comp.differences[1].tool_name == "get_forecast"

    db_comp = comp_map["db_server"]
    assert db_comp.status == "matched"
    assert db_comp.summary.added_count == 0
    assert db_comp.summary.unchanged_count == 1


def test_compare_servers_ambiguous_names_reported():
    from app.schemas.mcp import DiscoveredServer

    tool_x = ExtractedTool(name="run", description="R", input_schema={"type": "object", "properties": {}})

    # Baseline has one server named "demo" at src/old_demo/server.py
    base_servers = [
        DiscoveredServer(
            server_id="demo:src/old_demo/server.py",
            name="demo",
            entrypoint="src/old_demo/server.py",
            framework="fastmcp",
            tools=[tool_x],
        ),
    ]

    # Candidate has TWO servers named "demo" at different entrypoints
    cand_servers = [
        DiscoveredServer(
            server_id="demo:src/demo_a/server.py",
            name="demo",
            entrypoint="src/demo_a/server.py",
            framework="fastmcp",
            tools=[tool_x],
        ),
        DiscoveredServer(
            server_id="demo:src/demo_b/server.py",
            name="demo",
            entrypoint="src/demo_b/server.py",
            framework="fastmcp",
            tools=[tool_x],
        ),
    ]

    comparisons = MCPService.compare_servers(base_servers, cand_servers)
    # The matching algorithm must NOT silently pick one; it reports ambiguous server identities!
    statuses = [c.status for c in comparisons]
    assert "ambiguous" in statuses
    for c in comparisons:
        assert c.status == "ambiguous"


def test_compute_tool_diff_multi_server_same_tool_name_no_collision():
    """Verify tool inventories with identical tool names across different servers do not overwrite."""
    t1_base = ExtractedTool(
        name="read",
        description="Read file",
        server_name="filesystem",
        input_schema={"type": "object", "properties": {}},
    )
    t2_base = ExtractedTool(
        name="read",
        description="Read DB record",
        server_name="database",
        input_schema={"type": "object", "properties": {}},
    )

    t1_cand = ExtractedTool(
        name="read",
        description="Read file (modified)",
        server_name="filesystem",
        input_schema={"type": "object", "properties": {}},
    )
    t2_cand = ExtractedTool(
        name="read",
        description="Read DB record",
        server_name="database",
        input_schema={"type": "object", "properties": {}},
    )

    diffs, summary = MCPService.compute_tool_diff([t1_base, t2_base], [t1_cand, t2_cand])
    assert summary.total_baseline_tools == 2
    assert summary.total_candidate_tools == 2
    assert summary.modified_count == 1  # filesystem:read
    assert summary.unchanged_count == 1  # database:read
    assert len(diffs) == 2
