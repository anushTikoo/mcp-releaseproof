import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { TestHarnessGenerator } from "./TestHarnessGenerator";

const MOCK_VALID_HARNESS_CODE = `
import pytest
from mcp import ClientSession

@pytest.mark.asyncio
async def test_read_file(session: ClientSession):
    \"\"\"SCENARIO-01: Verify file read capability.\"\"\"
    result = await session.call_tool("read_file", {"path": "README.md"})
    assert result is not None
`;

const MOCK_GENERATE_SUCCESS = {
  status: "success",
  repository_url: "https://github.com/example/filesystem-mcp-server",
  commit_sha: "a1b2c3d4e5f67890123456789012345678901234",
  model: "qwen3.8-flash-next",
  harness_code: MOCK_VALID_HARNESS_CODE.trim(),
  metadata: {
    test_count: 1,
    scenarios_covered: ["SCENARIO-01"],
    tools_tested: ["read_file"],
    framework: "pytest-asyncio",
    summary: "Generated pytest-asyncio harness testing read_file",
  },
  validation: {
    is_valid: true,
    syntax_valid: true,
    security_valid: true,
    structure_valid: true,
    schema_valid: true,
    rejection_reasons: [],
    warnings: [],
    identified_imports: ["pytest", "mcp"],
    identified_tool_calls: ["read_file"],
    ast_node_count: 42,
    line_count: 9,
  },
  usage: { total_tokens: 280 },
  duration_ms: 380.5,
};

const MOCK_GENERATE_REJECTED = {
  status: "rejected",
  repository_url: "https://github.com/example/filesystem-mcp-server",
  commit_sha: "a1b2c3d4e5f67890123456789012345678901234",
  model: "qwen3.8-flash-next",
  harness_code: "import os\n\ndef test_bad():\n    os.system('ls')",
  metadata: {
    test_count: 1,
    scenarios_covered: [],
    tools_tested: [],
    framework: "pytest-asyncio",
    summary: "Generated harness with forbidden import",
  },
  validation: {
    is_valid: false,
    syntax_valid: true,
    security_valid: false,
    structure_valid: true,
    schema_valid: true,
    rejection_reasons: [
      "Prohibited module import 'os' at line 1. Only safe testing modules are permitted.",
      "Prohibited callable attribute 'system()' at line 4.",
    ],
    warnings: [],
    identified_imports: ["os"],
    identified_tool_calls: [],
    ast_node_count: 18,
    line_count: 4,
  },
  usage: { total_tokens: 150 },
  duration_ms: 210.0,
};

describe("TestHarnessGenerator Component", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("renders form elements with default values", () => {
    render(<TestHarnessGenerator />);

    expect(
      screen.getByText("AI Test Harness Generator & Static Validator")
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Repository Target")).toHaveValue(
      "https://github.com/example/filesystem-mcp-server"
    );
    expect(screen.getByLabelText("Commit SHA")).toHaveValue(
      "a1b2c3d4e5f67890123456789012345678901234"
    );
    expect(screen.getByLabelText("Git Reference")).toHaveValue("v1.0.0");
    expect(
      screen.getByRole("button", { name: "Generate Executable Test Harness" })
    ).toBeInTheDocument();
  });

  it("successfully generates harness and displays valid security verdict and code", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/harness/generate")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_GENERATE_SUCCESS,
        });
      }
      return Promise.reject(new Error(`Unhandled: ${url}`));
    });

    const { container } = render(<TestHarnessGenerator />);

    const generateBtn = screen.getByRole("button", {
      name: "Generate Executable Test Harness",
    });
    fireEvent.click(generateBtn);

    await waitFor(() => {
      expect(screen.getByText("✓ VALID")).toBeInTheDocument();
    });

    expect(screen.getByText("test_harness.py")).toBeInTheDocument();
    const editor = container.querySelector(".harness-source-editor") as HTMLTextAreaElement;
    expect(editor).not.toBeNull();
    expect(editor.value).toContain("async def test_read_file");
    expect(screen.getByText("Static AST Validation Only:")).toBeInTheDocument();
    expect(
      screen.getByText("Generated pytest-asyncio harness testing read_file")
    ).toBeInTheDocument();
    expect(screen.getByText("42 AST nodes")).toBeInTheDocument();
    expect(screen.getByText("9 lines")).toBeInTheDocument();
  });

  it("handles rejected harness and displays rejection reasons", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/harness/generate")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_GENERATE_REJECTED,
        });
      }
      return Promise.reject(new Error(`Unhandled: ${url}`));
    });

    render(<TestHarnessGenerator />);

    const generateBtn = screen.getByRole("button", {
      name: "Generate Executable Test Harness",
    });
    fireEvent.click(generateBtn);

    await waitFor(() => {
      expect(screen.getByText("✗ REJECTED")).toBeInTheDocument();
    });

    expect(
      screen.getByText("Security & Schema Violations (2)")
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Prohibited module import 'os' at line 1/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Prohibited callable attribute 'system\(\)' at line 4/)
    ).toBeInTheDocument();
  });

  it("handles token limit exceeded error gracefully", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/harness/generate")) {
        return Promise.resolve({
          ok: false,
          status: 422,
          statusText: "Unprocessable Entity",
          json: async () => ({
            detail:
              "Inference output was truncated because it reached the maximum token budget (2500 tokens). Finish reason: length. TOKEN_LIMIT_EXCEEDED",
          }),
        });
      }
      return Promise.reject(new Error(`Unhandled: ${url}`));
    });

    render(<TestHarnessGenerator />);

    const generateBtn = screen.getByRole("button", {
      name: "Generate Executable Test Harness",
    });
    fireEvent.click(generateBtn);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });

    expect(screen.getByText("Inference Error (422)")).toBeInTheDocument();
    expect(screen.getAllByText(/TOKEN_LIMIT_EXCEEDED/)[0]).toBeInTheDocument();
  });

  it("shows error on malformed tools JSON input", async () => {
    render(<TestHarnessGenerator />);

    const toolsInput = screen.getByLabelText(
      "Discovered MCP Tools (JSON Schema)"
    );
    fireEvent.change(toolsInput, { target: { value: "{ not valid json }" } });

    const generateBtn = screen.getByRole("button", {
      name: "Generate Executable Test Harness",
    });
    fireEvent.click(generateBtn);

    expect(screen.getByText("Invalid Tools JSON")).toBeInTheDocument();
  });

  it("shows error on malformed test plan JSON input", async () => {
    render(<TestHarnessGenerator />);

    const planInput = screen.getByLabelText(
      "Structured Test Plan (Phase 2 Output)"
    );
    fireEvent.change(planInput, { target: { value: "{ invalid json }" } });

    const generateBtn = screen.getByRole("button", {
      name: "Generate Executable Test Harness",
    });
    fireEvent.click(generateBtn);

    expect(screen.getByText("Invalid Test Plan JSON")).toBeInTheDocument();
  });

  it("allows auditing current code via direct validation", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/harness/generate")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_GENERATE_SUCCESS,
        });
      }
      if (url.includes("/harness/validate")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            status: "valid",
            validation: {
              is_valid: true,
              syntax_valid: true,
              security_valid: true,
              structure_valid: true,
              schema_valid: true,
              rejection_reasons: [],
              warnings: [],
              identified_imports: ["pytest"],
              identified_tool_calls: ["read_file"],
              ast_node_count: 50,
              line_count: 10,
            },
          }),
        });
      }
      return Promise.reject(new Error(`Unhandled: ${url}`));
    });

    render(<TestHarnessGenerator />);

    // Generate first
    const generateBtn = screen.getByRole("button", {
      name: "Generate Executable Test Harness",
    });
    fireEvent.click(generateBtn);

    await waitFor(() => {
      expect(screen.getByText("✓ VALID")).toBeInTheDocument();
    });

    // Now audit current code
    const auditBtn = screen.getByRole("button", { name: "Audit Current Code" });
    fireEvent.click(auditBtn);

    await waitFor(() => {
      expect(screen.getByText("50 AST nodes")).toBeInTheDocument();
    });
  });

  it("copies code to clipboard when Copy Code is clicked", async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/harness/generate")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_GENERATE_SUCCESS,
        });
      }
      return Promise.reject(new Error(`Unhandled: ${url}`));
    });

    render(<TestHarnessGenerator />);

    fireEvent.click(
      screen.getByRole("button", { name: "Generate Executable Test Harness" })
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Copy Code" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Copy Code" }));

    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith(MOCK_VALID_HARNESS_CODE.trim());
      expect(screen.getByText("✓ Copied!")).toBeInTheDocument();
    });
  });

  it("integrates with Phase 4 discovered tools and Phase 2 test plans via props", () => {
    const liveTools = [
      {
        tool_name: "custom_live_tool",
        description: "Discovered live in Phase 4",
        input_schema: { type: "object", properties: { q: { type: "string" } } },
      },
    ];
    const livePlan = {
      plan_id: "plan-live-999",
      target_server_summary: "Live server verification",
      scenarios: [
        {
          scenario_id: "SCENARIO-LIVE",
          title: "Verify custom tool",
          objective: "Live tool execution",
          safety_classification: "benign_baseline",
          steps: [
            {
              step_index: 1,
              tool_name: "custom_live_tool",
              arguments: { q: "live" },
              expected_result: "Success",
            },
          ],
        },
      ],
    };

    render(
      <TestHarnessGenerator
        discoveredTools={liveTools}
        testPlan={livePlan}
        repositoryUrl="https://github.com/my-org/live-server"
        commitSha="b2c3d4e5f6789012345678901234567890123456"
        refLabel="v2.0.0"
      />
    );

    expect(screen.getByText("✓ Connected to Phase 4 Discovery")).toBeInTheDocument();
    expect(screen.getByText("✓ Connected to Phase 2 Plan")).toBeInTheDocument();
    expect(screen.getByLabelText("Repository Target")).toHaveValue("https://github.com/my-org/live-server");
    expect(screen.getByLabelText("Commit SHA")).toHaveValue("b2c3d4e5f6789012345678901234567890123456");
    expect(screen.getByLabelText("Git Reference")).toHaveValue("v2.0.0");

    // Click reset to demo button
    const resetBtn = screen.getByRole("button", {
      name: "Reset Inputs to Demonstration Fallback",
    });
    fireEvent.click(resetBtn);

    expect(
      screen.getAllByText("⚠️ Demonstration Sample Data")[0]
    ).toBeInTheDocument();
  });

  it("clears valid status and marks code as modified when user edits the source editor (F6 regression)", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/harness/generate")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_GENERATE_SUCCESS,
        });
      }
      if (url.includes("/harness/validate")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            status: "rejected",
            validation: {
              is_valid: false,
              syntax_valid: true,
              security_valid: false,
              structure_valid: true,
              schema_valid: true,
              rejection_reasons: ["Prohibited module import 'os' at line 1."],
              warnings: [],
              identified_imports: ["os"],
              identified_tool_calls: [],
              ast_node_count: 10,
              line_count: 4,
            },
          }),
        });
      }
      return Promise.reject(new Error(`Unhandled: ${url}`));
    });

    const { container } = render(<TestHarnessGenerator />);

    const generateBtn = screen.getByRole("button", {
      name: "Generate Executable Test Harness",
    });
    fireEvent.click(generateBtn);

    await waitFor(() => {
      expect(screen.getByText("✓ VALID")).toBeInTheDocument();
    });

    const editor = container.querySelector(".harness-source-editor") as HTMLTextAreaElement;
    expect(editor).not.toBeNull();

    // User edits the code in the editor
    fireEvent.change(editor, { target: { value: "import os\n\ndef test_injected(): os.system('echo pwned')" } });

    // The status must NOT show VALID anymore; it must show MODIFIED (UNVALIDATED)
    expect(screen.queryByText("✓ VALID")).not.toBeInTheDocument();
    expect(screen.getByText("⚠️ MODIFIED (UNVALIDATED)")).toBeInTheDocument();
    expect(screen.getByText("Source Code Modified:")).toBeInTheDocument();

    // Click Audit Current Code to re-validate
    const auditBtn = screen.getByRole("button", { name: "Audit Current Code" });
    fireEvent.click(auditBtn);

    await waitFor(() => {
      expect(screen.getByText("✗ REJECTED")).toBeInTheDocument();
      expect(screen.getByText("Prohibited module import 'os' at line 1.")).toBeInTheDocument();
    });
  });

  it("clears valid status and marks verdict as modified when user edits tool schemas or test plan JSON (F5 regression)", async () => {
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/harness/generate")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            status: "success",
            repository_url: "https://github.com/example/filesystem-mcp-server",
            commit_sha: "a1b2c3d4e5f67890123456789012345678901234",
            model: "qwen3.8-flash-next",
            harness_code:
              'import pytest\nfrom mcp import ClientSession\n\n@pytest.mark.asyncio\nasync def test_read(session: ClientSession):\n    """SCENARIO-01: Read."""\n    await session.call_tool("read_file", {"path": "test.txt"})\n',
            metadata: {
              test_count: 1,
              scenarios_covered: ["SCENARIO-01"],
              tools_tested: ["read_file"],
              framework: "pytest-asyncio",
              summary: "Generated test",
            },
            validation: {
              is_valid: true,
              syntax_valid: true,
              security_valid: true,
              structure_valid: true,
              schema_valid: true,
              rejection_reasons: [],
              warnings: [],
              identified_imports: ["pytest", "mcp"],
              identified_tool_calls: ["read_file"],
              ast_node_count: 20,
              line_count: 7,
            },
          }),
        } as Response);
      }
      return Promise.reject(new Error(`Unhandled: ${url}`));
    });

    render(
      <TestHarnessGenerator
        discoveredTools={[
          {
            tool_name: "read_file",
            description: "Read file",
            input_schema: { type: "object", properties: { path: { type: "string" } }, required: ["path"] },
          },
        ]}
        testPlan={{
          plan_id: "plan-1",
          target_server_summary: "Server",
          scenarios: [
            {
              scenario_id: "SCENARIO-01",
              title: "Read",
              objective: "Read",
              safety_classification: "benign_baseline",
              steps: [{ step_index: 1, tool_name: "read_file", arguments: { path: "test.txt" }, expected_result: "ok" }],
            },
          ],
        }}
      />
    );

    expect(screen.getByText("✓ Connected to Phase 4 Discovery")).toBeInTheDocument();
    expect(screen.getByText("✓ Connected to Phase 2 Plan")).toBeInTheDocument();

    const generateBtn = screen.getByRole("button", {
      name: "Generate Executable Test Harness",
    });
    fireEvent.click(generateBtn);

    await waitFor(() => {
      expect(screen.getByText("✓ VALID")).toBeInTheDocument();
    });

    const toolsTextarea = screen.getByLabelText("Discovered MCP Tools (JSON Schema)");
    fireEvent.change(toolsTextarea, {
      target: { value: JSON.stringify([{ tool_name: "custom_tool" }], null, 2) },
    });

    expect(screen.queryByText("✓ VALID")).not.toBeInTheDocument();
    expect(screen.getByText("⚠️ MODIFIED (UNVALIDATED)")).toBeInTheDocument();
    expect(screen.getByText("⚠️ User-Edited Tool Schemas (Caller-Supplied)")).toBeInTheDocument();
  });

  it("clears valid status and marks scenario coverage as unverified when changing only the test plan", async () => {
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/harness/generate")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            status: "success",
            repository_url: "https://github.com/example/filesystem-mcp-server",
            commit_sha: "a1b2c3d4e5f67890123456789012345678901234",
            model: "qwen3.8-flash-next",
            harness_code:
              'import pytest\nfrom mcp import ClientSession\n\n@pytest.mark.asyncio\nasync def test_read(session: ClientSession):\n    """SCENARIO-01: Read."""\n    await session.call_tool("read_file", {"path": "test.txt"})\n',
            metadata: {
              test_count: 1,
              scenarios_covered: ["SCENARIO-01"],
              tools_tested: ["read_file"],
              framework: "pytest-asyncio",
              summary: "Generated test",
            },
            validation: {
              is_valid: true,
              syntax_valid: true,
              security_valid: true,
              structure_valid: true,
              schema_valid: true,
              rejection_reasons: [],
              warnings: [],
              identified_imports: ["pytest", "mcp"],
              identified_tool_calls: ["read_file"],
              identified_scenarios: ["SCENARIO-01"],
              ast_node_count: 20,
              line_count: 7,
            },
          }),
        } as Response);
      }
      return Promise.reject(new Error(`Unhandled: ${url}`));
    });

    render(
      <TestHarnessGenerator
        discoveredTools={[
          {
            tool_name: "read_file",
            description: "Read file",
            input_schema: { type: "object", properties: { path: { type: "string" } }, required: ["path"] },
          },
        ]}
        testPlan={{
          plan_id: "plan-1",
          target_server_summary: "Server",
          scenarios: [
            {
              scenario_id: "SCENARIO-01",
              title: "Read",
              objective: "Read",
              safety_classification: "benign_baseline",
              steps: [{ step_index: 1, tool_name: "read_file", arguments: { path: "test.txt" }, expected_result: "ok" }],
            },
          ],
        }}
      />
    );

    const generateBtn = screen.getByRole("button", {
      name: "Generate Executable Test Harness",
    });
    fireEvent.click(generateBtn);

    await waitFor(() => {
      expect(screen.getByText("✓ VALID")).toBeInTheDocument();
    });

    expect(screen.getByText("SCENARIO-01")).toBeInTheDocument();

    // User modifies ONLY the test plan JSON
    const planTextarea = screen.getByLabelText("Structured Test Plan (Phase 2 Output)");
    fireEvent.change(planTextarea, {
      target: {
        value: JSON.stringify(
          {
            plan_id: "plan-modified",
            target_server_summary: "Server",
            scenarios: [
              {
                scenario_id: "SCENARIO-MODIFIED",
                title: "Modified",
                objective: "Modified",
                safety_classification: "benign_baseline",
                steps: [],
              },
            ],
          },
          null,
          2
        ),
      },
    });

    // The status must NOT show VALID anymore
    expect(screen.queryByText("✓ VALID")).not.toBeInTheDocument();
    expect(screen.getByText("⚠️ MODIFIED (UNVALIDATED)")).toBeInTheDocument();
    expect(screen.getByText("⚠️ User-Edited Test Plan (Caller-Supplied)")).toBeInTheDocument();
    expect(screen.getByText("Unverified (Inputs modified)")).toBeInTheDocument();
    expect(
      screen.getByText(/The tool schemas or test plan have been modified since validation/)
    ).toBeInTheDocument();
  });
});
