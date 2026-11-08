import React, { useEffect, useState } from "react";
import {
  DiscoveredToolInput,
  fetchInferenceStatus,
  generateTestPlan,
  GenerationResponse,
  InferenceApiError,
  InferenceConfigStatus,
  TestPlan,
} from "../api/client";

interface ErrorDisplayInfo {
  title: string;
  message: string;
  code?: string;
  status?: number;
  suggestion?: string;
}

export interface TestPlanGeneratorProps {
  initialTools?: DiscoveredToolInput[] | null;
  initialRepoUrl?: string;
  onPlanGenerated?: (plan: TestPlan, repoUrl: string) => void;
}

const DEFAULT_SAMPLE_TOOLS = [
  {
    tool_name: "read_file",
    description: "Read file contents from the allowed directory",
    input_schema: {
      type: "object",
      properties: {
        path: { type: "string", description: "Relative or absolute path" },
      },
      required: ["path"],
    },
  },
  {
    tool_name: "list_directory",
    description: "List directory files and folders",
    input_schema: {
      type: "object",
      properties: {
        path: { type: "string", description: "Directory to inspect" },
      },
      required: ["path"],
    },
  },
];

export const TestPlanGenerator: React.FC<TestPlanGeneratorProps> = ({
  initialTools,
  initialRepoUrl,
  onPlanGenerated,
}) => {
  const [configStatus, setConfigStatus] = useState<InferenceConfigStatus | null>(null);
  const [selectedModel, setSelectedModel] = useState<string>("qwen3.8-flash-next");
  const [repoUrl, setRepoUrl] = useState<string>(
    initialRepoUrl || "https://github.com/example/filesystem-mcp-server"
  );
  const [toolsJson, setToolsJson] = useState<string>(
    initialTools && initialTools.length > 0
      ? JSON.stringify(initialTools, null, 2)
      : JSON.stringify(DEFAULT_SAMPLE_TOOLS, null, 2)
  );
  const [loading, setLoading] = useState<boolean>(false);
  const [errorDisplay, setErrorDisplay] = useState<ErrorDisplayInfo | null>(null);
  const [result, setResult] = useState<GenerationResponse | null>(null);

  useEffect(() => {
    if (initialTools && initialTools.length > 0) {
      setToolsJson(JSON.stringify(initialTools, null, 2));
    }
  }, [initialTools]);

  useEffect(() => {
    if (initialRepoUrl) {
      setRepoUrl(initialRepoUrl);
    }
  }, [initialRepoUrl]);

  useEffect(() => {
    fetchInferenceStatus()
      .then((data) => {
        setConfigStatus(data);
        if (data.configured_model) {
          setSelectedModel(data.configured_model);
        }
      })
      .catch((err: unknown) => {
        console.error("Failed to fetch inference configuration:", err);
      });
  }, []);

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorDisplay(null);
    setResult(null);

    let parsedTools;
    try {
      parsedTools = JSON.parse(toolsJson);
      if (!Array.isArray(parsedTools) || parsedTools.length === 0) {
        throw new Error("Tools must be a non-empty JSON array of tool definitions.");
      }
    } catch (err: unknown) {
      setErrorDisplay({
        title: "Invalid Input",
        message:
          err instanceof Error
            ? `Invalid Tools JSON: ${err.message}`
            : "Invalid Tools JSON format",
      });
      return;
    }

    setLoading(true);
    try {
      const response = await generateTestPlan({
        repository_url: repoUrl,
        tools: parsedTools,
        model_id: selectedModel,
      });
      setResult(response);
      if (onPlanGenerated && response.plan) {
        onPlanGenerated(response.plan, repoUrl);
      }
    } catch (err: unknown) {
      if (err instanceof InferenceApiError) {
        if (err.code === "TOKEN_LIMIT_EXCEEDED") {
          setErrorDisplay({
            title: "Generation Truncated (Token Limit Reached)",
            message: "The model output was truncated. Try a more compact test plan.",
            code: err.code,
            status: err.status,
            suggestion:
              "The model reached the token budget before finishing the structured plan. Reduce tool arguments or simplify the test requirements.",
          });
        } else if (
          err.code === "EMPTY_CONTENT" ||
          err.code === "EMPTY_CHOICES" ||
          err.code === "REASONING_WITHOUT_CONTENT"
        ) {
          setErrorDisplay({
            title: "Empty Model Response",
            message: "The model returned an empty response without generating test content.",
            code: err.code,
            status: err.status,
            suggestion: "The inference provider returned an empty completion. Please retry the request.",
          });
        } else if (err.code === "JSON_PARSE_FAILED") {
          setErrorDisplay({
            title: "JSON Parsing Failure",
            message: "The model output could not be parsed as valid JSON.",
            code: err.code,
            status: err.status,
            suggestion: "The raw response contained invalid JSON syntax. Retrying typically resolves output syntax glitches.",
          });
        } else if (err.code === "SCHEMA_VALIDATION_FAILED") {
          setErrorDisplay({
            title: "Pydantic Validation Failure",
            message: "The generated JSON failed schema validation (check scenario and step limits).",
            code: err.code,
            status: err.status,
            suggestion: "Ensure scenarios (max 3) and steps per scenario (max 2) fit the schema.",
          });
        } else if (err.status >= 500) {
          setErrorDisplay({
            title: `Upstream HTTP Error (${err.upstreamStatus || err.status})`,
            message: err.message,
            code: err.code,
            status: err.status,
            suggestion: "An issue occurred communicating with Vultr Serverless Inference. Verify network access and provider status.",
          });
        } else {
          setErrorDisplay({
            title: `Inference Error (${err.status})`,
            message: err.message,
            code: err.code,
            status: err.status,
          });
        }
      } else {
        const msg = err instanceof Error ? err.message : "Inference request failed";
        setErrorDisplay({
          title: "Inference Error",
          message: msg,
        });
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="inference-container" data-testid="test-plan-generator">
      <div className="inference-header">
        <h3 className="section-title">Vultr Serverless Inference — AI Test Planning</h3>
        <div className="config-badge-group">
          {configStatus?.api_key_configured ? (
            <span className="badge badge-success" data-testid="key-status-badge">
              ✓ API Key Configured (Backend)
            </span>
          ) : (
            <span className="badge badge-warning" data-testid="key-status-badge">
              ⚠ Vultr API Key Unconfigured in .env
            </span>
          )}
        </div>
      </div>

      <form onSubmit={handleGenerate} className="inference-form">
        <div className="form-row">
          <div className="form-group flex-2">
            <label htmlFor="repo-url">Repository Target</label>
            <input
              id="repo-url"
              type="text"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              required
              className="text-input"
              placeholder="https://github.com/user/mcp-server"
            />
          </div>

          <div className="form-group flex-1">
            <label htmlFor="model-select">Benchmark Model</label>
            <select
              id="model-select"
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="select-input"
            >
              <option value="qwen3.8-flash-next">
                qwen3.8-flash-next (262K Context, $0.10/$0.20 per 1M)
              </option>
              <option value="deepseek-v4.1-flash-1017">
                deepseek-v4.1-flash-1017 (1M Context)
              </option>
            </select>
          </div>
        </div>

        <div className="form-group">
          <label htmlFor="tools-json">
            Discovered MCP Tool Definitions (JSON)
          </label>
          <textarea
            id="tools-json"
            rows={8}
            value={toolsJson}
            onChange={(e) => setToolsJson(e.target.value)}
            className="code-textarea"
            spellCheck={false}
          />
        </div>

        <button
          type="submit"
          className="submit-btn"
          disabled={loading}
          data-testid="generate-plan-btn"
        >
          {loading ? (
            <>
              <span className="btn-spinner"></span>
              Generating Plan via Vultr Serverless...
            </>
          ) : (
            "Generate Structured Test Plan"
          )}
        </button>
      </form>

      {errorDisplay && (
        <div className="error-banner" data-testid="inference-error-banner">
          <div className="error-title">{errorDisplay.title}</div>
          <p className="error-detail">{errorDisplay.message}</p>
          {errorDisplay.suggestion && (
            <div className="error-hint">
              <strong>Tip:</strong> {errorDisplay.suggestion}
            </div>
          )}
          {!configStatus?.api_key_configured && (
            <div className="error-hint">
              <strong>Tip:</strong> Set <code>VULTR_INFERENCE_API_KEY</code> in <code>backend/.env</code> to enable live serverless inference calls.
            </div>
          )}
        </div>
      )}

      {result && result.plan && (
        <div className="plan-results" data-testid="plan-results">
          <div className="results-header">
            <h4>Generated Plan: {result.plan.plan_id}</h4>
            <div className="results-meta">
              <span className="meta-tag">Model: {result.model}</span>
              <span className="meta-tag">Duration: {result.duration_ms} ms</span>
              {result.usage && (
                <span className="meta-tag">
                  Tokens: {result.usage.total_tokens}
                </span>
              )}
            </div>
          </div>

          <div className="summary-section">
            <p className="server-summary">
              <strong>Server Summary:</strong> {result.plan.target_server_summary}
            </p>
            {result.plan.coverage_notes && (
              <p className="coverage-notes">
                <strong>Coverage Notes:</strong> {result.plan.coverage_notes}
              </p>
            )}
          </div>

          <div className="scenarios-list">
            <h5>Test Scenarios ({result.plan.scenarios.length})</h5>
            {result.plan.scenarios.map((sc) => (
              <div key={sc.scenario_id} className="scenario-card">
                <div className="scenario-header">
                  <span className="scenario-title">{sc.title}</span>
                  <span className="scenario-badge">{sc.safety_classification}</span>
                </div>
                <p className="scenario-objective">{sc.objective}</p>

                <div className="steps-container">
                  <span className="steps-heading">Tool Sequence:</span>
                  <ol className="steps-list">
                    {sc.steps.map((st) => (
                      <li key={st.step_index} className="step-item">
                        <span className="step-tool">{st.tool_name}</span>
                        <code className="step-args">
                          {JSON.stringify(st.arguments)}
                        </code>
                        <span className="step-expected">
                          → {st.expected_result || st.expected_behavior}
                        </span>
                      </li>
                    ))}
                  </ol>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

