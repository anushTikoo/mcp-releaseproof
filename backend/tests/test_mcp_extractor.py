"""Unit tests for static AST MCP extractor and schema parser."""

import pytest
from app.services.mcp_extractor import (
    MCPExtractor,
    map_ast_type_to_json_schema,
    parse_docstring_params,
    safe_eval_ast_literal,
)
import ast


def test_parse_docstring_google_style():
    doc = """Execute a database query securely.
    
    Args:
        query: SQL statement to execute
        timeout_seconds: Maximum query execution time in seconds
        dry_run: Whether to simulate without executing
    """
    desc, params = parse_docstring_params(doc)
    assert desc == "Execute a database query securely."
    assert params["query"] == "SQL statement to execute"
    assert params["timeout_seconds"] == "Maximum query execution time in seconds"
    assert params["dry_run"] == "Whether to simulate without executing"


def test_parse_docstring_sphinx_style():
    doc = """Fetch records from API.
    
    :param endpoint: Target resource path
    :param limit: Maximum number of records to return
    """
    desc, params = parse_docstring_params(doc)
    assert desc == "Fetch records from API."
    assert params["endpoint"] == "Target resource path"
    assert params["limit"] == "Maximum number of records to return"


def test_safe_eval_ast_literal():
    expr = ast.parse("{'a': 1, 'b': ['hello', True, None, -42]}", mode="eval").body
    val = safe_eval_ast_literal(expr)
    assert val == {"a": 1, "b": ["hello", True, None, -42]}

    # Test dynamic node returns fallback placeholder
    dyn_expr = ast.parse("os.getenv('VAR')", mode="eval").body
    dyn_val = safe_eval_ast_literal(dyn_expr)
    assert dyn_val == "<getenv()>"


def test_map_ast_type_to_json_schema():
    # Simple str
    node_str = ast.parse("str", mode="eval").body
    t, is_opt, extra = map_ast_type_to_json_schema(node_str)
    assert t == "string" and not is_opt and extra is None

    # Optional[int]
    node_opt = ast.parse("Optional[int]", mode="eval").body
    t, is_opt, extra = map_ast_type_to_json_schema(node_opt)
    assert t == "integer" and is_opt and extra is None

    # List[str]
    node_list = ast.parse("List[str]", mode="eval").body
    t, is_opt, extra = map_ast_type_to_json_schema(node_list)
    assert t == "array" and not is_opt and extra == {"items": {"type": "string"}}

    # Python 3.10+ union: float | None
    node_union = ast.parse("float | None", mode="eval").body
    t, is_opt, extra = map_ast_type_to_json_schema(node_union)
    assert t == "number" and is_opt


def test_extract_fastmcp_server_and_tools():
    source = '''
from mcp.server.fastmcp import FastMCP, Context

mcp = FastMCP("demo-server")

@mcp.tool()
def read_file(path: str, max_bytes: int = 1024, ctx: Context = None) -> str:
    """Read contents from file.
    
    Args:
        path: Path to target file
        max_bytes: Maximum bytes to read
    """
    return "content"

@mcp.tool(name="custom_fetch", description="Custom fetch tool")
def fetch_url(url: str, headers: list[str] = None):
    pass
'''
    extractor = MCPExtractor("owner", "repo", "sha123")
    extractor.analyze_python_source("server.py", source)

    report = extractor.generate_discovery_report()
    assert report.has_mcp_server is True
    assert report.confidence == "confirmed"
    assert report.framework == "fastmcp"
    assert len(report.extracted_tools) == 2

    # Verify read_file
    read_tool = next(t for t in report.extracted_tools if t.name == "read_file")
    assert read_tool.description == "Read contents from file."
    assert "path" in read_tool.input_schema["properties"]
    assert "max_bytes" in read_tool.input_schema["properties"]
    assert "ctx" not in read_tool.input_schema["properties"]  # Context skipped
    assert read_tool.input_schema["required"] == ["path"]
    assert read_tool.input_schema["properties"]["max_bytes"]["default"] == 1024
    assert read_tool.input_schema["properties"]["path"]["description"] == "Path to target file"

    # Verify custom_fetch
    fetch_tool = next(t for t in report.extracted_tools if t.name == "custom_fetch")
    assert fetch_tool.description == "Custom fetch tool"
    assert "url" in fetch_tool.input_schema["required"]


def test_extract_lowlevel_server_tools():
    source = '''
from mcp.server import Server
import mcp.types as types

server = Server("lowlevel-demo")

@server.list_tools()
async def handle_tools():
    return [
        types.Tool(
            name="query_db",
            description="Execute SQL query",
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL statement"},
                    "limit": {"type": "integer", "default": 50}
                },
                "required": ["sql"]
            }
        )
    ]
'''
    extractor = MCPExtractor("owner", "repo", "sha123")
    extractor.analyze_python_source("main.py", source)

    report = extractor.generate_discovery_report()
    assert report.has_mcp_server is True
    assert report.confidence == "confirmed"
    assert report.framework == "mcp_lowlevel"
    assert len(report.extracted_tools) == 1

    tool = report.extracted_tools[0]
    assert tool.name == "query_db"
    assert tool.description == "Execute SQL query"
    assert "sql" in tool.input_schema["required"]
    assert tool.input_schema["properties"]["limit"]["default"] == 50


def test_manifest_inspection_pyproject_and_requirements():
    pyproject_content = """
[project]
name = "sample-mcp-server"
version = "0.1.0"
dependencies = [
    "mcp>=1.2.0",
    "httpx>=0.27.0"
]
[project.scripts]
sample-server = "sample_mcp_server:main"
"""
    extractor = MCPExtractor("owner", "repo", "sha123")
    extractor.inspect_dependencies("pyproject.toml", pyproject_content)

    assert any(ind.indicator_type == "pyproject_mcp_dependency" for ind in extractor.indicators)
    assert any("sample-server" in ep for ep in extractor.entrypoints)

    requirements_content = """
# Dependencies
mcp>=1.0.0
pytest>=8.0.0
"""
    extractor.inspect_dependencies("requirements.txt", requirements_content)
    assert any(ind.indicator_type == "requirements_mcp_dependency" for ind in extractor.indicators)


def test_detect_typescript_mcp_sdk_unsupported():
    pkg_json = """
{
  "name": "ts-mcp-server",
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.0.0"
  }
}
"""
    extractor = MCPExtractor("owner", "repo", "sha123")
    extractor.inspect_dependencies("package.json", pkg_json)

    report = extractor.generate_discovery_report()
    assert report.has_mcp_server is True
    assert report.confidence == "unsupported"
    assert report.framework == "typescript_sdk"
    assert report.language == "typescript"
    assert report.extraction_status == "UNSUPPORTED"


def test_syntax_error_resilience():
    bad_code = "def invalid_syntax( { : not valid python"
    extractor = MCPExtractor("owner", "repo", "sha123")
    extractor.analyze_python_source("broken.py", bad_code)

    assert len(extractor.warnings) > 0
    assert "SyntaxError in broken.py" in extractor.warnings[0]
    report = extractor.generate_discovery_report()
    assert report.has_mcp_server is False
    assert report.confidence == "inconclusive"



def test_client_only_repository_detection():
    client_code = '''
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def run_client():
    server_params = StdioServerParameters(command="uv", args=["run", "server.py"])
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(tools)
'''
    extractor = MCPExtractor("owner", "client-repo", "sha123")
    extractor.analyze_python_source("client_app.py", client_code)

    report = extractor.generate_discovery_report()
    assert report.has_mcp_client is True
    assert report.has_mcp_server is False
    assert report.confidence == "inconclusive"
    assert "client_app.py" in report.client_entrypoints
    assert len(report.server_entrypoints) == 0
    assert len(report.extracted_tools) == 0


def test_mixed_client_and_server_repository():
    client_code = '''
from mcp import ClientSession
def start_client():
    session = ClientSession(None, None)
'''
    server_code = '''
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("my_service")

@mcp.tool()
def echo(msg: str) -> str:
    """Echo a message."""
    return msg
'''
    extractor = MCPExtractor("owner", "mixed-repo", "sha123")
    extractor.analyze_python_source("src/client.py", client_code)
    extractor.analyze_python_source("src/server.py", server_code)

    report = extractor.generate_discovery_report()
    assert report.has_mcp_client is True
    assert report.has_mcp_server is True
    assert report.confidence == "confirmed"
    assert "src/client.py" in report.client_entrypoints
    assert "src/server.py" in report.server_entrypoints
    assert len(report.extracted_tools) == 1
    assert report.extracted_tools[0].name == "echo"


def test_multiple_independent_mcp_servers_grouping():
    server1_code = '''
from mcp.server.fastmcp import FastMCP
weather = FastMCP("weather_server")

@weather.tool()
def get_forecast(city: str) -> str:
    """Get forecast."""
    return "rain"

@weather.tool()
def get_temperature(city: str) -> float:
    """Get temp."""
    return 21.5
'''
    server2_code = '''
from mcp.server.fastmcp import FastMCP
database = FastMCP("db_server")

@database.tool()
def query_sql(sql: str) -> list[str]:
    """Execute SQL query."""
    return []
'''
    extractor = MCPExtractor("owner", "multi-server-repo", "sha123")
    extractor.analyze_python_source("src/weather.py", server1_code)
    extractor.analyze_python_source("src/database.py", server2_code)

    report = extractor.generate_discovery_report()
    assert report.has_mcp_server is True
    assert len(report.servers) == 2

    server_names = {s.name for s in report.servers}
    assert server_names == {"weather_server", "db_server"}

    weather_srv = next(s for s in report.servers if s.name == "weather_server")
    db_srv = next(s for s in report.servers if s.name == "db_server")

    assert len(weather_srv.tools) == 2
    assert {t.name for t in weather_srv.tools} == {"get_forecast", "get_temperature"}

    assert len(db_srv.tools) == 1
    assert db_srv.tools[0].name == "query_sql"

    # Verify repository-wide tools list has all 3
    assert len(report.extracted_tools) == 3


def test_test_files_excluded_from_tool_extraction():
    test_mock_code = '''
from mcp.server.fastmcp import FastMCP
mock_app = FastMCP("mock_server")

@mock_app.tool()
def mock_dummy_tool(x: int) -> int:
    """Mock tool inside test suite."""
    return x
'''
    extractor = MCPExtractor("owner", "repo", "sha123")
    # File in tests/ directory
    extractor.analyze_python_source("tests/test_fastmcp.py", test_mock_code)

    report = extractor.generate_discovery_report()
    assert len(report.servers) == 0
    assert len(report.extracted_tools) == 0
    assert report.has_mcp_server is False


def test_simple_chatbot_client_manifest_script_not_classified_as_server():
    """Regression test: examples/clients/simple-chatbot/pyproject.toml [script: mcp-simple-chatbot]

    Must be classified as a client entrypoint, never a server entrypoint.
    """
    pyproject_content = """
[project]
name = "mcp-simple-chatbot"
version = "0.1.0"
dependencies = [
    "mcp",
]

[project.scripts]
mcp-simple-chatbot = "mcp_simple_chatbot.chat:main"
"""
    client_code = """
import asyncio
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

async def main():
    async with stdio_client(["server"]) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
"""
    extractor = MCPExtractor("modelcontextprotocol", "python-sdk", "sha123")
    extractor.inspect_dependencies(
        "examples/clients/simple-chatbot/pyproject.toml", pyproject_content
    )
    extractor.analyze_python_source(
        "examples/clients/simple-chatbot/mcp_simple_chatbot/chat.py", client_code
    )

    report = extractor.generate_discovery_report()

    # Client classification must succeed
    assert report.has_mcp_client is True
    assert report.has_mcp_server is False
    assert report.confidence == "inconclusive"
    # Script entrypoint must be in client_entrypoints
    assert any("mcp-simple-chatbot" in ep for ep in report.client_entrypoints)
    # Client-only script must NEVER appear in server_entrypoints
    assert not any("mcp-simple-chatbot" in ep for ep in report.server_entrypoints)
    assert len(report.server_entrypoints) == 0
    assert len(report.servers) == 0
    assert len(report.extracted_tools) == 0


def test_servers_with_identical_tool_names_not_merged():
    """Verify tools from unrelated example servers with identical names are not merged."""
    sqlite_server = """
from mcp.server.fastmcp import FastMCP
sqlite = FastMCP("sqlite-server")

@sqlite.tool()
def query(sql: str) -> str:
    \"\"\"Execute SQL.\"\"\"
    return sql
"""
    postgres_server = """
from mcp.server.fastmcp import FastMCP
postgres = FastMCP("postgres-server")

@postgres.tool()
def query(sql: str, db: str = "main") -> str:
    \"\"\"Execute Postgres SQL.\"\"\"
    return sql
"""
    extractor = MCPExtractor("owner", "repo", "sha123")
    extractor.analyze_python_source("examples/servers/sqlite/server.py", sqlite_server)
    extractor.analyze_python_source("examples/servers/postgres/server.py", postgres_server)

    report = extractor.generate_discovery_report()
    assert len(report.servers) == 2
    # Both tools are extracted into individual server inventories
    sqlite_srv = next(s for s in report.servers if s.name == "sqlite-server")
    postgres_srv = next(s for s in report.servers if s.name == "postgres-server")

    assert len(sqlite_srv.tools) == 1
    assert sqlite_srv.tools[0].name == "query"
    assert sqlite_srv.tools[0].server_name == "sqlite-server"

    assert len(postgres_srv.tools) == 1
    assert postgres_srv.tools[0].name == "query"
    assert postgres_srv.tools[0].server_name == "postgres-server"

    # Repository-wide tool inventory holds both distinct tools
    assert len(report.extracted_tools) == 2
