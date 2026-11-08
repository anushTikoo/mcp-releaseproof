import React, { useEffect, useState } from "react";
import {
  DiscoveredToolInput,
  generateTestHarness,
  GenerateHarnessResponse,
  InferenceApiError,
  TestPlan,
  validateTestHarness,
  ValidateHarnessResponse,
} from "../api/client";
import { SandboxExecutor } from "./SandboxExecutor";

interface ErrorDisplayInfo {
  title: string;
  message: string;
  code?: string;
  status?: number;
}

export interface TestHarnessGeneratorProps {
  discoveredTools?: DiscoveredToolInput[] | null;
  testPlan?: TestPlan | null;
  repositoryUrl?: string;
  commitSha?: string;
  refLabel?: string;
}

const DEFAULT_SAMPLE_TOOLS = [
  {
    tool_name: "read_file",
    description: "Read file contents from the allowed directory",
    input_schema: {
      type: "object",
      properties: {
        path: { type: "string", description: "Relative file path" },
      },
      required: ["path"],
      additionalProperties: false,
    },
  },
  {
    tool_name: "list_files",
    description: "List directory contents",
    input_schema: {
      type: "object",
      properties: {
        directory: { type: "string" },
      },
      required: [],
    },
  },
];

const DEFAULT_SAMPLE_PLAN = {
  plan_id: "plan-fs-001",
  target_server_summary: "Filesystem MCP server supporting read operations",
  coverage_notes: "Baseline file read and listing operations",
  scenarios: [
    {
      scenario_id: "SCENARIO-01",
      title: "Read existing file",
      objective: "Verify normal tool execution with valid relative path",
      safety_classification: "benign_baseline",
      steps: [
        {
          step_index: 1,
          tool_name: "read_file",
          arguments: { path: "README.md" },
          expected_result: "Returns file content without error",
        },
      ],
    },
    {
      scenario_id: "SCENARIO-02",
      title: "List directory files",
      objective: "Verify listing files in working root",
      safety_classification: "benign_baseline",
      steps: [
        {
          step_index: 1,
          tool_name: "list_files",
          arguments: { directory: "." },
          expected_result: "List of files returned",
        },
      ],
    },
  ],
};

export const TestHarnessGenerator: React.FC<TestHarnessGeneratorProps> = ({
  discoveredTools,
  testPlan,
  repositoryUrl,
  commitSha: initialCommitSha,
  refLabel: initialRefLabel,
}) => {
  const [repoUrl, setRepoUrl] = useState<string>(
    repositoryUrl || "https://github.com/example/filesystem-mcp-server"
  );
  const [commitSha, setCommitSha] = useState<string>(
    initialCommitSha || "a1b2c3d4e5f67890123456789012345678901234"
  );
  const [refLabel, setRefLabel] = useState<string>(initialRefLabel || "v1.0.0");
  const [serverName, setServerName] = useState<string>("filesystem");
  const [isUsingDemoTools, setIsUsingDemoTools] = useState<boolean>(
    !discoveredTools || discoveredTools.length === 0
  );
  const [isUsingDemoPlan, setIsUsingDemoPlan] = useState<boolean>(!testPlan);
  const [toolsEditedByUser, setToolsEditedByUser] = useState<boolean>(false);
  const [planEditedByUser, setPlanEditedByUser] = useState<boolean>(false);

  const [toolsJson, setToolsJson] = useState<string>(
    discoveredTools && discoveredTools.length > 0
      ? JSON.stringify(discoveredTools, null, 2)
      : JSON.stringify(DEFAULT_SAMPLE_TOOLS, null, 2)
  );
  const [planJson, setPlanJson] = useState<string>(
    testPlan
      ? JSON.stringify(testPlan, null, 2)
      : JSON.stringify(DEFAULT_SAMPLE_PLAN, null, 2)
  );

  useEffect(() => {
    if (discoveredTools && discoveredTools.length > 0) {
      setToolsJson(JSON.stringify(discoveredTools, null, 2));
      setIsUsingDemoTools(false);
      setToolsEditedByUser(false);
    }
  }, [discoveredTools]);

  useEffect(() => {
    if (testPlan) {
      setPlanJson(JSON.stringify(testPlan, null, 2));
      setIsUsingDemoPlan(false);
      setPlanEditedByUser(false);
    }
  }, [testPlan]);

  useEffect(() => {
    if (repositoryUrl) {
      setRepoUrl(repositoryUrl);
    }
  }, [repositoryUrl]);

  useEffect(() => {
    if (initialCommitSha) {
      setCommitSha(initialCommitSha);
    }
  }, [initialCommitSha]);

  useEffect(() => {
    if (initialRefLabel) {
      setRefLabel(initialRefLabel);
    }
  }, [initialRefLabel]);

  const handleResetToDemo = () => {
    setToolsJson(JSON.stringify(DEFAULT_SAMPLE_TOOLS, null, 2));
    setPlanJson(JSON.stringify(DEFAULT_SAMPLE_PLAN, null, 2));
    setRepoUrl("https://github.com/example/filesystem-mcp-server");
    setCommitSha("a1b2c3d4e5f67890123456789012345678901234");
    setRefLabel("v1.0.0");
    setIsUsingDemoTools(true);
    setIsUsingDemoPlan(true);
    setToolsEditedByUser(false);
    setPlanEditedByUser(false);
  };

  const [loading, setLoading] = useState<boolean>(false);
  const [validating, setValidating] = useState<boolean>(false);
  const [errorDisplay, setErrorDisplay] = useState<ErrorDisplayInfo | null>(null);
  const [copied, setCopied] = useState<boolean>(false);

  const [generationResult, setGenerationResult] =
    useState<GenerateHarnessResponse | null>(null);
  const [activeCode, setActiveCode] = useState<string>("");
  const [validatedCode, setValidatedCode] = useState<string | null>(null);
  const [validatedToolsJson, setValidatedToolsJson] = useState<string | null>(null);
  const [validatedPlanJson, setValidatedPlanJson] = useState<string | null>(null);
  const [manualValidation, setManualValidation] =
    useState<ValidateHarnessResponse | null>(null);

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorDisplay(null);
    setGenerationResult(null);
    setManualValidation(null);
    setValidatedCode(null);
    setValidatedToolsJson(null);
    setValidatedPlanJson(null);
    setCopied(false);

    let parsedTools;
    try {
      parsedTools = JSON.parse(toolsJson);
      if (!Array.isArray(parsedTools) || parsedTools.length === 0) {
        throw new Error("Tools must be a non-empty JSON array of tool definitions.");
      }
    } catch (err: unknown) {
      setErrorDisplay({
        title: "Invalid Tools JSON",
        message: err instanceof Error ? err.message : String(err),
      });
      return;
    }

    let parsedPlan;
    try {
      parsedPlan = JSON.parse(planJson);
      if (!parsedPlan || !Array.isArray(parsedPlan.scenarios)) {
        throw new Error("Test plan must be a valid JSON object containing a 'scenarios' array.");
      }
    } catch (err: unknown) {
      setErrorDisplay({
        title: "Invalid Test Plan JSON",
        message: err instanceof Error ? err.message : String(err),
      });
      return;
    }

    setLoading(true);
    try {
      const res = await generateTestHarness({
        repository_url: repoUrl,
        commit_sha: commitSha,
        ref: refLabel || undefined,
        server_name: serverName || undefined,
        tools: parsedTools,
        test_plan: parsedPlan,
      });
      setGenerationResult(res);
      setActiveCode(res.harness_code);
      setValidatedCode(res.harness_code);
      setValidatedToolsJson(toolsJson);
      setValidatedPlanJson(planJson);
    } catch (err: unknown) {
      if (err instanceof InferenceApiError) {
        setErrorDisplay({
          title: `Inference Error (${err.status})`,
          message: err.message,
          code: err.code,
          status: err.status,
        });
      } else {
        setErrorDisplay({
          title: "Connection Error",
          message: err instanceof Error ? err.message : "Failed to connect to backend",
        });
      }
    } finally {
      setLoading(false);
    }
  };

  const handleValidateCurrentCode = async () => {
    if (!activeCode.trim()) return;
    setErrorDisplay(null);
    setValidating(true);

    let parsedTools;
    try {
      parsedTools = JSON.parse(toolsJson);
    } catch {
      parsedTools = [];
    }

    let parsedPlan;
    try {
      parsedPlan = JSON.parse(planJson);
    } catch {
      parsedPlan = undefined;
    }

    try {
      const res = await validateTestHarness({
        harness_code: activeCode,
        tools: parsedTools,
        test_plan: parsedPlan,
      });
      setManualValidation(res);
      setValidatedCode(activeCode);
      setValidatedToolsJson(toolsJson);
      setValidatedPlanJson(planJson);
    } catch (err: unknown) {
      setErrorDisplay({
        title: "Validation Error",
        message: err instanceof Error ? err.message : "Static validator failed",
      });
    } finally {
      setValidating(false);
    }
  };

  const handleCopyCode = async () => {
    if (!activeCode) return;
    try {
      await navigator.clipboard.writeText(activeCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch (err: unknown) {
      console.error("Clipboard copy failed:", err);
    }
  };

  const isCodeModified =
    validatedCode !== null && activeCode.trim() !== validatedCode.trim();

  const isInputStale =
    isCodeModified ||
    (validatedToolsJson !== null && toolsJson.trim() !== validatedToolsJson.trim()) ||
    (validatedPlanJson !== null && planJson.trim() !== validatedPlanJson.trim());

  const currentValidation = isInputStale
    ? null
    : manualValidation?.validation || generationResult?.validation;

  const currentStatus = isInputStale
    ? "MODIFIED"
    : manualValidation
    ? manualValidation.status === "valid"
      ? "VALID"
      : "REJECTED"
    : generationResult
    ? generationResult.status === "success"
      ? "VALID"
      : "REJECTED"
    : null;

  return (
    <section className="harness-generator-card">
      <div className="harness-header">
        <div>
          <h3 className="harness-title">AI Test Harness Generator & Static Validator</h3>
          <p className="harness-subtitle">
            Generate executable pytest-asyncio harnesses with zero code execution and strict AST security audit.
          </p>
        </div>
        <div className="security-guarantee-pill">
          <span className="security-icon">🛡️</span>
          <span>Zero-Code-Execution Boundary</span>
        </div>
      </div>

      <form onSubmit={handleGenerate} className="harness-form">
        <div className="form-row form-grid-4">
          <div className="form-group">
            <label htmlFor="harness-repo-url">Repository Target</label>
            <input
              id="harness-repo-url"
              type="url"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="https://github.com/owner/repo"
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="harness-commit-sha">Commit SHA</label>
            <input
              id="harness-commit-sha"
              type="text"
              value={commitSha}
              onChange={(e) => setCommitSha(e.target.value)}
              placeholder="Immutable 40-char SHA"
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="harness-ref-label">Git Reference</label>
            <input
              id="harness-ref-label"
              type="text"
              value={refLabel}
              onChange={(e) => setRefLabel(e.target.value)}
              placeholder="e.g. v1.0.0, main"
            />
          </div>
          <div className="form-group">
            <label htmlFor="harness-server-name">Server Name</label>
            <input
              id="harness-server-name"
              type="text"
              value={serverName}
              onChange={(e) => setServerName(e.target.value)}
              placeholder="e.g. filesystem"
            />
          </div>
        </div>

        <div className="form-row form-grid-2">
          <div className="form-group">
            <div className="label-with-source">
              <label htmlFor="harness-tools-json">
                Discovered MCP Tools (JSON Schema)
              </label>
              <span
                className={`source-badge ${
                  toolsEditedByUser
                    ? "source-edited"
                    : !isUsingDemoTools
                    ? "source-live"
                    : "source-demo"
                }`}
              >
                {toolsEditedByUser
                  ? "⚠️ User-Edited Tool Schemas (Caller-Supplied)"
                  : !isUsingDemoTools
                  ? "✓ Connected to Phase 4 Discovery"
                  : "⚠️ Demonstration Sample Data"}
              </span>
            </div>
            <textarea
              id="harness-tools-json"
              rows={7}
              value={toolsJson}
              onChange={(e) => {
                setToolsJson(e.target.value);
                setToolsEditedByUser(true);
              }}
              className="code-textarea"
            />
          </div>
          <div className="form-group">
            <div className="label-with-source">
              <label htmlFor="harness-plan-json">
                Structured Test Plan (Phase 2 Output)
              </label>
              <span
                className={`source-badge ${
                  planEditedByUser
                    ? "source-edited"
                    : !isUsingDemoPlan
                    ? "source-live"
                    : "source-demo"
                }`}
              >
                {planEditedByUser
                  ? "⚠️ User-Edited Test Plan (Caller-Supplied)"
                  : !isUsingDemoPlan
                  ? "✓ Connected to Phase 2 Plan"
                  : "⚠️ Demonstration Sample Data"}
              </span>
            </div>
            <textarea
              id="harness-plan-json"
              rows={7}
              value={planJson}
              onChange={(e) => {
                setPlanJson(e.target.value);
                setPlanEditedByUser(true);
              }}
              className="code-textarea"
            />
          </div>
        </div>

        {(!isUsingDemoTools || !isUsingDemoPlan) && (
          <div className="reset-demo-row">
            <button
              type="button"
              onClick={handleResetToDemo}
              className="reset-demo-btn"
            >
              Reset Inputs to Demonstration Fallback
            </button>
          </div>
        )}

        <div className="form-actions">
          <button
            type="submit"
            className="generate-harness-btn"
            disabled={loading || validating}
          >
            {loading ? (
              <span className="spinner-wrapper">
                <span className="btn-spinner" /> Generating & Auditing...
              </span>
            ) : (
              "Generate Executable Test Harness"
            )}
          </button>
        </div>
      </form>

      {errorDisplay && (
        <div className="harness-error-box" role="alert">
          <div className="error-title-row">
            <strong>{errorDisplay.title}</strong>
            {errorDisplay.code && (
              <span className="error-code-badge">{errorDisplay.code}</span>
            )}
          </div>
          <p className="error-message">{errorDisplay.message}</p>
        </div>
      )}

      {(generationResult || activeCode) && (
        <div className="harness-result-section">
          <div className="harness-verdict-banner">
            <div className="verdict-left">
              <span className="verdict-label">Static Security Verdict:</span>
              <span
                className={`verdict-badge ${
                  currentStatus === "VALID"
                    ? "badge-valid"
                    : currentStatus === "MODIFIED"
                    ? "badge-modified"
                    : "badge-rejected"
                }`}
              >
                {currentStatus === "VALID"
                  ? "✓ VALID"
                  : currentStatus === "MODIFIED"
                  ? "⚠️ MODIFIED (UNVALIDATED)"
                  : "✗ REJECTED"}
              </span>
            </div>

            <div className="verdict-meta">
              {currentValidation && (
                <>
                  <span className="meta-tag">
                    {currentValidation.line_count} lines
                  </span>
                  <span className="meta-tag">
                    {currentValidation.ast_node_count} AST nodes
                  </span>
                  <span className="meta-tag">
                    {currentValidation.identified_imports.length} imports
                  </span>
                </>
              )}
              {generationResult && (
                <span className="meta-tag">
                  {generationResult.duration_ms} ms
                </span>
              )}
            </div>
          </div>

          {isInputStale && (
            <div className="modified-warning-banner" role="alert">
              <span className="warning-icon">⚠️</span>
              <div>
                <strong>{isCodeModified ? "Source Code Modified:" : "Inputs Modified:"}</strong>{" "}
                {isCodeModified
                  ? "The code in the editor has been altered since it was last audited."
                  : "The tool schemas or test plan have been modified since validation."}{" "}
                Click <strong>"Audit Current Code"</strong> to statically re-verify AST security rules and JSON schemas.
              </div>
            </div>
          )}

          {(generationResult?.trust_boundary_notice || manualValidation?.trust_boundary_notice) && (
            <div className="trust-boundary-banner" role="note">
              <span className="notice-icon">🔒</span>
              <div>
                <strong>Trust Boundary Notice ({generationResult?.inventory_origin || manualValidation?.inventory_origin || "caller_supplied_unverified"}):</strong>{" "}
                {generationResult?.trust_boundary_notice || manualValidation?.trust_boundary_notice}
              </div>
            </div>
          )}

          <div className="phase5-disclaimer-notice">
            <span className="disclaimer-icon">ℹ️</span>
            <div>
              <strong>Static AST Validation Only:</strong> Code execution is NOT performed in Phase 5.
              The generated harness is strictly audited against prohibited modules, dangerous function calls,
              reflection escapes, and declared MCP tool JSON schemas.
            </div>
          </div>

          {currentValidation && !currentValidation.is_valid && (
            <div className="rejection-reasons-box">
              <h4 className="rejection-title">
                Security & Schema Violations ({currentValidation.rejection_reasons.length})
              </h4>
              <ul className="rejection-list">
                {currentValidation.rejection_reasons.map((reason, idx) => (
                  <li key={idx} className="rejection-item">
                    <span className="rejection-icon">⚠️</span>
                    <span>{reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {currentValidation && currentValidation.warnings.length > 0 && (
            <div className="warnings-box">
              <h4 className="warnings-title">Analysis Warnings</h4>
              <ul className="warnings-list">
                {currentValidation.warnings.map((warn, idx) => (
                  <li key={idx} className="warning-item">
                    <span>{warn}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {generationResult && (
            <div className="harness-summary-card">
              <h4>Harness Metadata & Coverage</h4>
              <p className="harness-summary-text">
                {generationResult.metadata.summary}
              </p>
              <div className="coverage-chips">
                <div className="chip-group">
                  <span className="chip-label">Test Functions:</span>
                  <span className="chip-val">{generationResult.metadata.test_count}</span>
                </div>
                <div className="chip-group">
                  <span className="chip-label">Static Scenario Matches (Runtime Unverified):</span>
                  <span className="chip-val">
                    {isInputStale
                      ? "Unverified (Inputs modified)"
                      : (currentValidation?.identified_scenarios?.length
                          ? currentValidation.identified_scenarios.join(", ")
                          : generationResult.metadata.scenarios_covered?.join(", ") || "None")}
                  </span>
                </div>
                <div className="chip-group">
                  <span className="chip-label">Tools Tested:</span>
                  <span className="chip-val">
                    {generationResult.metadata.tools_tested?.join(", ") || "None"}
                  </span>
                </div>
              </div>
            </div>
          )}

          <div className="code-viewer-container">
            <div className="code-viewer-header">
              <span className="code-viewer-title">test_harness.py</span>
              <div className="code-viewer-actions">
                <button
                  type="button"
                  onClick={handleValidateCurrentCode}
                  className="validate-code-btn"
                  disabled={validating}
                >
                  {validating ? "Validating AST..." : "Audit Current Code"}
                </button>
                <button
                  type="button"
                  onClick={handleCopyCode}
                  className="copy-code-btn"
                >
                  {copied ? "✓ Copied!" : "Copy Code"}
                </button>
              </div>
            </div>
            <textarea
              value={activeCode}
              onChange={(e) => {
                setActiveCode(e.target.value);
                setManualValidation(null);
              }}
              rows={16}
              className="harness-source-editor"
              spellCheck={false}
            />
          </div>

          {/* Phase 6: Vultr Compute Sandbox Execution Action & Evidence */}
          {activeCode.trim() && (
            <SandboxExecutor
              repositoryUrl={repoUrl}
              commitSha={commitSha}
              refName={refLabel}
              harnessCode={activeCode}
              serverEntrypoint="server.py"
            />
          )}
        </div>
      )}
    </section>
  );
};
