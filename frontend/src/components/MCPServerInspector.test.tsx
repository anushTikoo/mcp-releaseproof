import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { MCPServerInspector } from "./MCPServerInspector";

const MOCK_DISCOVERY_CANDIDATE = {
  has_mcp_server: true,
  has_mcp_client: false,
  confidence: "confirmed",
  framework: "fastmcp",
  language: "python",
  server_entrypoints: ["server.py", "pyproject.toml [script: demo-server]"],
  client_entrypoints: [],
  servers: [
    {
      server_id: "demo_server",
      name: "demo_server",
      entrypoint: "server.py",
      framework: "fastmcp",
      description: "Demo FastMCP server",
      tools: [
        {
          name: "read_file",
          description: "Read contents of file safely",
          input_schema: {
            type: "object",
            properties: {
              path: { type: "string" },
            },
            required: ["path"],
          },
          parameters: [{ name: "path", type: "string", required: true }],
          schema_hash: "hash_read_file_v2",
        },
      ],
    },
  ],
  indicators: [
    {
      category: "sdk_dependency",
      indicator_type: "pyproject_mcp_dependency",
      confidence: "confirmed",
      file_path: "pyproject.toml",
      details: "Explicit MCP SDK dependency declared",
    },
    {
      category: "server_initialization",
      indicator_type: "fastmcp_instance",
      confidence: "confirmed",
      file_path: "server.py",
      line_number: 5,
      details: "Instantiates FastMCP server object 'mcp'",
    },
  ],
  extracted_tools: [
    {
      name: "read_file",
      description: "Read contents of file safely",
      input_schema: {
        type: "object",
        properties: {
          path: { type: "string", description: "Target file path" },
          max_bytes: { type: "integer", default: 1024 },
        },
        required: ["path"],
      },
      parameters: [
        {
          name: "path",
          type: "string",
          description: "Target file path",
          required: true,
          default: null,
        },
        {
          name: "max_bytes",
          type: "integer",
          description: null,
          required: false,
          default: 1024,
        },
      ],
      source_file: "server.py",
      source_line: 10,
      schema_hash: "hash_read_file_v2",
    },
    {
      name: "write_file",
      description: "Write content to file",
      input_schema: {
        type: "object",
        properties: {
          path: { type: "string" },
          content: { type: "string" },
        },
        required: ["path", "content"],
      },
      parameters: [
        { name: "path", type: "string", required: true },
        { name: "content", type: "string", required: true },
      ],
      source_file: "server.py",
      source_line: 25,
      schema_hash: "hash_write_file_v2",
    },
  ],
  extraction_status: "COMPLETE",
  extraction_warnings: [],
  runtime_verification_required: true,
};

const MOCK_DISCOVERY_BASELINE = {
  ...MOCK_DISCOVERY_CANDIDATE,
  extracted_tools: [
    {
      name: "read_file",
      description: "Read contents of file",
      input_schema: {
        type: "object",
        properties: {
          path: { type: "string" },
        },
        required: ["path"],
      },
      parameters: [{ name: "path", type: "string", required: true }],
      source_file: "server.py",
      source_line: 10,
      schema_hash: "hash_read_file_v1",
    },
  ],
};

const MOCK_DISCOVER_RESPONSE = {
  status: "success",
  repository_url: "https://github.com/example/filesystem-mcp-server",
  ref: "v0.2.0",
  commit_sha: "2222222222222222222222222222222222222222",
  discovery: MOCK_DISCOVERY_CANDIDATE,
};

const MOCK_COMPARE_RESPONSE = {
  status: "success",
  repository_url: "https://github.com/example/filesystem-mcp-server",
  baseline_ref: "v0.1.0",
  baseline_sha: "1111111111111111111111111111111111111111",
  candidate_ref: "v0.2.0",
  candidate_sha: "2222222222222222222222222222222222222222",
  baseline_discovery: MOCK_DISCOVERY_BASELINE,
  candidate_discovery: MOCK_DISCOVERY_CANDIDATE,
  summary: {
    total_baseline_tools: 1,
    total_candidate_tools: 2,
    added_count: 1,
    removed_count: 0,
    modified_count: 1,
    unchanged_count: 0,
  },
  differences: [
    {
      tool_name: "read_file",
      change_type: "modified_both",
      baseline_tool: MOCK_DISCOVERY_BASELINE.extracted_tools[0],
      candidate_tool: MOCK_DISCOVERY_CANDIDATE.extracted_tools[0],
      changes_detected: [
        "Description was updated",
        "Added input parameter 'max_bytes'",
      ],
    },
    {
      tool_name: "write_file",
      change_type: "added",
      baseline_tool: null,
      candidate_tool: MOCK_DISCOVERY_CANDIDATE.extracted_tools[1],
      changes_detected: ["Tool introduced in candidate version"],
    },
  ],
  server_comparisons: [
    {
      server_id: "demo_server",
      server_name: "demo_server",
      baseline_entrypoint: "server.py",
      candidate_entrypoint: "server.py",
      status: "matched",
      summary: {
        total_baseline_tools: 1,
        total_candidate_tools: 2,
        added_count: 1,
        removed_count: 0,
        modified_count: 1,
        unchanged_count: 0,
      },
      differences: [],
    },
  ],
};

describe("MCPServerInspector Component", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("renders form elements and default values", () => {
    render(<MCPServerInspector />);

    expect(
      screen.getByText("MCP Server Discovery & Schema Extraction")
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Target GitHub Repository/i)).toHaveValue(
      "https://github.com/example/filesystem-mcp-server"
    );
    expect(screen.getByLabelText(/Baseline Ref/i)).toHaveValue("v0.1.0");
    expect(screen.getByLabelText(/Candidate Ref/i)).toHaveValue("v0.2.0");
    expect(screen.getByTestId("mcp-compare-btn")).toBeInTheDocument();
    expect(screen.getByTestId("mcp-discover-btn")).toBeInTheDocument();
  });

  it("validates repository URL on client-side without calling fetch", async () => {
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock;

    render(<MCPServerInspector />);

    const urlInput = screen.getByLabelText(/Target GitHub Repository/i);
    fireEvent.change(urlInput, { target: { value: "not-a-url" } });

    const discoverBtn = screen.getByTestId("mcp-discover-btn");
    await act(async () => {
      fireEvent.click(discoverBtn);
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByTestId("mcp-error-banner")).toBeInTheDocument();
    expect(
      screen.getByText(/Repository URL must be a valid public HTTPS GitHub repository URL/i)
    ).toBeInTheDocument();
  });

  it("validates missing baseline ref when clicking compare", async () => {
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock;

    render(<MCPServerInspector />);

    const baselineInput = screen.getByLabelText(/Baseline Ref/i);
    fireEvent.change(baselineInput, { target: { value: "   " } });

    const compareBtn = screen.getByTestId("mcp-compare-btn");
    await act(async () => {
      fireEvent.click(compareBtn);
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByTestId("mcp-error-banner")).toBeInTheDocument();
    expect(screen.getByText(/Baseline ref is required/i)).toBeInTheDocument();
  });

  it("successfully discovers tools and displays discovery status", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/mcp/discover")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_DISCOVER_RESPONSE,
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<MCPServerInspector />);

    const discoverBtn = screen.getByTestId("mcp-discover-btn");
    await act(async () => {
      fireEvent.click(discoverBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("mcp-discovery-status")).toBeInTheDocument();
    });

    expect(screen.getByText("CONFIRMED MCP SERVER")).toBeInTheDocument();
    expect(screen.getByText("Framework: FASTMCP")).toBeInTheDocument();
    expect(screen.getAllByText("server.py")[0]).toBeInTheDocument();
    expect(screen.getByText("read_file")).toBeInTheDocument();
    expect(screen.getByText("write_file")).toBeInTheDocument();
    expect(screen.getByText("Read contents of file safely")).toBeInTheDocument();
  });

  it("successfully compares tool inventories and displays summary metrics and diffs", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/mcp/compare")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_COMPARE_RESPONSE,
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<MCPServerInspector />);

    const compareBtn = screen.getByTestId("mcp-compare-btn");
    await act(async () => {
      fireEvent.click(compareBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("mcp-comparison-summary")).toBeInTheDocument();
    });

    expect(screen.getByText("+1")).toBeInTheDocument(); // Added
    expect(screen.getByText("~1")).toBeInTheDocument(); // Modified
    expect(screen.getByText("MODIFIED BOTH")).toBeInTheDocument();
    expect(screen.getByText("ADDED")).toBeInTheDocument();
    expect(screen.getByText("• Description was updated")).toBeInTheDocument();
    expect(
      screen.getByText("• Added input parameter 'max_bytes'")
    ).toBeInTheDocument();
  });

  it("toggles JSON schema view open and closed", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/mcp/discover")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_DISCOVER_RESPONSE,
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<MCPServerInspector />);

    const discoverBtn = screen.getByTestId("mcp-discover-btn");
    await act(async () => {
      fireEvent.click(discoverBtn);
    });

    await waitFor(() => {
      expect(screen.getByText("read_file")).toBeInTheDocument();
    });

    const schemaButtons = screen.getAllByRole("button", { name: "View JSON Schema" });
    expect(schemaButtons.length).toBe(2);

    await act(async () => {
      fireEvent.click(schemaButtons[0]);
    });

    expect(screen.getByText("Normalized JSON Schema:")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide Schema" })).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Hide Schema" }));
    });

    expect(screen.queryByText("Normalized JSON Schema:")).not.toBeInTheDocument();
  });

  it("toggles evidence drawer open and closed", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/mcp/discover")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_DISCOVER_RESPONSE,
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<MCPServerInspector />);

    const discoverBtn = screen.getByTestId("mcp-discover-btn");
    await act(async () => {
      fireEvent.click(discoverBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("mcp-discovery-status")).toBeInTheDocument();
    });

    const evidenceBtn = screen.getByRole("button", { name: /View Evidence \(2\)/i });
    await act(async () => {
      fireEvent.click(evidenceBtn);
    });

    expect(screen.getByTestId("indicators-drawer")).toBeInTheDocument();
    expect(screen.getByText("pyproject_mcp_dependency")).toBeInTheDocument();
    expect(screen.getByText("fastmcp_instance")).toBeInTheDocument();
  });

  it("renders structured error banner on API failure", async () => {
    globalThis.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: false,
        status: 404,
        statusText: "Not Found",
        json: async () => ({
          detail: {
            code: "REF_NOT_FOUND",
            message: "Ref 'v9.9.9' could not be resolved.",
          },
        }),
      })
    );

    render(<MCPServerInspector />);

    const discoverBtn = screen.getByTestId("mcp-discover-btn");
    await act(async () => {
      fireEvent.click(discoverBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("mcp-error-banner")).toBeInTheDocument();
    });

    expect(screen.getByText("[REF_NOT_FOUND]")).toBeInTheDocument();
    expect(screen.getByText("Ref 'v9.9.9' could not be resolved.")).toBeInTheDocument();
    expect(
      screen.getByText(/Check that the branch, tag, or commit SHA exists/i)
    ).toBeInTheDocument();
  });

  it("renders MCP client badge and client entrypoints when client usage is detected", async () => {
    const clientDiscovery = {
      ...MOCK_DISCOVERY_CANDIDATE,
      has_mcp_server: false,
      has_mcp_client: true,
      confidence: "inconclusive",
      framework: "unknown",
      server_entrypoints: [],
      client_entrypoints: ["client.py", "examples/eval_client.py"],
      servers: [],
      extracted_tools: [],
    };

    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/mcp/discover")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            ...MOCK_DISCOVER_RESPONSE,
            discovery: clientDiscovery,
          }),
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<MCPServerInspector />);

    const discoverBtn = screen.getByTestId("mcp-discover-btn");
    await act(async () => {
      fireEvent.click(discoverBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("mcp-client-badge")).toBeInTheDocument();
    });

    expect(screen.getByText("MCP Client Detected")).toBeInTheDocument();
    expect(screen.getByTestId("client-entrypoints")).toBeInTheDocument();
    expect(screen.getByText("client.py")).toBeInTheDocument();
    expect(screen.getByText("examples/eval_client.py")).toBeInTheDocument();
  });

  it("renders discovered server implementations breakdown card", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/mcp/discover")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_DISCOVER_RESPONSE,
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<MCPServerInspector />);

    const discoverBtn = screen.getByTestId("mcp-discover-btn");
    await act(async () => {
      fireEvent.click(discoverBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("discovered-servers-section")).toBeInTheDocument();
    });

    expect(screen.getByTestId("server-card-demo_server")).toBeInTheDocument();
    expect(screen.getByText("demo_server")).toBeInTheDocument();
    expect(screen.getByText("1 tool registered")).toBeInTheDocument();
  });

  it("renders server comparisons breakdown section when comparing", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/mcp/compare")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_COMPARE_RESPONSE,
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<MCPServerInspector />);

    const compareBtn = screen.getByTestId("mcp-compare-btn");
    await act(async () => {
      fireEvent.click(compareBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("server-comparisons-section")).toBeInTheDocument();
    });

    expect(screen.getByTestId("server-comparison-demo_server")).toBeInTheDocument();
    expect(screen.getByText(/Server Inventory Comparison Breakdown/i)).toBeInTheDocument();
  });

  it("renders warning alert box when extraction status is PARTIAL or FAILED", async () => {
    const partialDiscovery = {
      ...MOCK_DISCOVERY_CANDIDATE,
      extraction_status: "PARTIAL",
      extraction_warnings: ["Could not read source 'problematic.py': File decode error."],
    };

    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/mcp/discover")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            ...MOCK_DISCOVER_RESPONSE,
            discovery: partialDiscovery,
          }),
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<MCPServerInspector />);

    const discoverBtn = screen.getByTestId("mcp-discover-btn");
    await act(async () => {
      fireEvent.click(discoverBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("extraction-status-alert")).toBeInTheDocument();
    });

    expect(screen.getByText("Extraction Status: PARTIAL")).toBeInTheDocument();
    expect(
      screen.getAllByText(/Could not read source 'problematic.py': File decode error/i)[0]
    ).toBeInTheDocument();
  });
});

