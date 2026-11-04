import React, { useState } from "react";
import {
  compareMCPTools,
  CompareMCPToolsResponse,
  discoverMCPServer,
  DiscoverMCPResponse,
  ExtractedTool,
  GitHubApiError,
  MCPServerDiscovery,
  ToolDifference,
} from "../api/client";

interface ErrorDisplayInfo {
  title: string;
  message: string;
  code?: string;
  status?: number;
  suggestion?: string;
}

interface MCPServerInspectorProps {
  onToolsExtracted?: (tools: ExtractedTool[], repoUrl: string) => void;
}

export const MCPServerInspector: React.FC<MCPServerInspectorProps> = ({
  onToolsExtracted,
}) => {
  const [repoUrl, setRepoUrl] = useState<string>(
    "https://github.com/example/filesystem-mcp-server"
  );
  const [baselineRef, setBaselineRef] = useState<string>("v0.1.0");
  const [candidateRef, setCandidateRef] = useState<string>("v0.2.0");

  const [loadingAction, setLoadingAction] = useState<"discover" | "compare" | null>(null);
  const [errorDisplay, setErrorDisplay] = useState<ErrorDisplayInfo | null>(null);

  const [discoverResult, setDiscoverResult] = useState<DiscoverMCPResponse | null>(null);
  const [compareResult, setCompareResult] = useState<CompareMCPToolsResponse | null>(null);

  const [expandedSchemas, setExpandedSchemas] = useState<Record<string, boolean>>({});
  const [showIndicators, setShowIndicators] = useState<boolean>(false);

  const validateInputs = (requireBothRefs: boolean = false): string | null => {
    const trimmedUrl = repoUrl.trim();
    if (!trimmedUrl) {
      return "Repository URL is required.";
    }

    const githubRegex = /^https:\/\/github\.com\/([a-zA-Z0-9_.-]+)\/([a-zA-Z0-9_.-]+)(?:\/)?$/;
    if (!githubRegex.test(trimmedUrl)) {
      return "Repository URL must be a valid public HTTPS GitHub repository URL (e.g. https://github.com/owner/repo).";
    }

    if (requireBothRefs) {
      if (!baselineRef.trim()) {
        return "Baseline ref is required.";
      }
      if (!candidateRef.trim()) {
        return "Candidate ref is required.";
      }
    } else {
      if (!candidateRef.trim() && !baselineRef.trim()) {
        return "At least one Git ref is required to discover tools.";
      }
    }

    return null;
  };

  const handleDiscover = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorDisplay(null);

    const validationError = validateInputs(false);
    if (validationError) {
      setErrorDisplay({
        title: "Validation Error",
        message: validationError,
        code: "VALIDATION_ERROR",
      });
      return;
    }

    const targetRef = candidateRef.trim() || baselineRef.trim();
    setLoadingAction("discover");
    try {
      const response = await discoverMCPServer({
        repository_url: repoUrl.trim(),
        ref: targetRef,
      });
      setDiscoverResult(response);
      setCompareResult(null);

      if (onToolsExtracted && response.discovery.extracted_tools.length > 0) {
        onToolsExtracted(response.discovery.extracted_tools, repoUrl.trim());
      }
    } catch (err: unknown) {
      handleApiError(err, "MCP Discovery Failed");
    } finally {
      setLoadingAction(null);
    }
  };

  const handleCompare = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorDisplay(null);

    const validationError = validateInputs(true);
    if (validationError) {
      setErrorDisplay({
        title: "Validation Error",
        message: validationError,
        code: "VALIDATION_ERROR",
      });
      return;
    }

    setLoadingAction("compare");
    try {
      const response = await compareMCPTools({
        repository_url: repoUrl.trim(),
        baseline_ref: baselineRef.trim(),
        candidate_ref: candidateRef.trim(),
      });
      setCompareResult(response);
      setDiscoverResult(null);

      if (onToolsExtracted && response.candidate_discovery.extracted_tools.length > 0) {
        onToolsExtracted(response.candidate_discovery.extracted_tools, repoUrl.trim());
      }
    } catch (err: unknown) {
      handleApiError(err, "MCP Tool Comparison Failed");
    } finally {
      setLoadingAction(null);
    }
  };

  const handleApiError = (err: unknown, defaultTitle: string) => {
    if (err instanceof GitHubApiError) {
      let suggestion: string | undefined;

      switch (err.code) {
        case "INVALID_REPOSITORY_URL":
          suggestion =
            "Ensure the URL uses HTTPS and points to a valid public GitHub repository: https://github.com/owner/repo";
          break;
        case "REPOSITORY_NOT_FOUND":
          suggestion =
            "Verify the repository exists, is public, and that owner/repo spelling is correct.";
          break;
        case "REF_NOT_FOUND":
          suggestion =
            "Check that the branch, tag, or commit SHA exists in the remote repository.";
          break;
        case "GITHUB_RATE_LIMITED":
          suggestion =
            "GitHub rate limit exceeded. Set a GITHUB_TOKEN in backend/.env for up to 5,000 requests/hour.";
          break;
        case "GITHUB_TIMEOUT":
          suggestion =
            "GitHub took too long to respond. The repository might be experiencing high latency or large trees.";
          break;
        default:
          suggestion = "Inspect backend logs or check GitHub service status.";
      }

      setErrorDisplay({
        title: `${defaultTitle} (${err.status})`,
        message: err.message,
        code: err.code,
        status: err.status,
        suggestion,
      });
    } else if (err instanceof Error) {
      setErrorDisplay({
        title: defaultTitle,
        message: err.message,
        code: "NETWORK_ERROR",
        suggestion: "Ensure the backend service is running and accessible.",
      });
    } else {
      setErrorDisplay({
        title: defaultTitle,
        message: "An unexpected error occurred.",
        code: "UNKNOWN_ERROR",
      });
    }
  };

  const toggleSchema = (toolName: string) => {
    setExpandedSchemas((prev) => ({
      ...prev,
      [toolName]: !prev[toolName],
    }));
  };

  const isLoading = loadingAction !== null;
  const activeDiscovery: MCPServerDiscovery | null =
    compareResult?.candidate_discovery || discoverResult?.discovery || null;

  return (
    <section className="generator-card" data-testid="mcp-server-inspector">
      <div className="generator-header">
        <div>
          <h3 className="generator-title">MCP Server Discovery & Schema Extraction</h3>
          <p className="generator-subtitle">
            Statically discover MCP SDK implementations, extract available tools and JSON Schemas,
            and inspect version changes.
          </p>
        </div>
        <span className="badge badge-primary">Phase 4</span>
      </div>

      <form className="generator-form">
        <div className="form-group">
          <label htmlFor="mcp-repo-url-input" className="form-label">
            Target GitHub Repository
          </label>
          <input
            id="mcp-repo-url-input"
            type="text"
            className="form-input"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            placeholder="https://github.com/owner/repository"
            disabled={isLoading}
          />
        </div>

        <div className="grid-2-col">
          <div className="form-group">
            <label htmlFor="mcp-baseline-ref-input" className="form-label">
              Baseline Ref (Tag / Branch / SHA)
            </label>
            <input
              id="mcp-baseline-ref-input"
              type="text"
              className="form-input font-mono"
              value={baselineRef}
              onChange={(e) => setBaselineRef(e.target.value)}
              placeholder="e.g. v0.1.0 or main"
              disabled={isLoading}
            />
          </div>

          <div className="form-group">
            <label htmlFor="mcp-candidate-ref-input" className="form-label">
              Candidate Ref (Tag / Branch / SHA)
            </label>
            <input
              id="mcp-candidate-ref-input"
              type="text"
              className="form-input font-mono"
              value={candidateRef}
              onChange={(e) => setCandidateRef(e.target.value)}
              placeholder="e.g. v0.2.0 or commit SHA"
              disabled={isLoading}
            />
          </div>
        </div>

        <div className="button-group">
          <button
            type="button"
            className="btn btn-primary"
            data-testid="mcp-compare-btn"
            onClick={handleCompare}
            disabled={isLoading}
          >
            {loadingAction === "compare" ? (
              <>
                <span className="spinner" /> Comparing Tool Inventories...
              </>
            ) : (
              "Compare Tool Inventories"
            )}
          </button>

          <button
            type="button"
            className="btn btn-secondary"
            data-testid="mcp-discover-btn"
            onClick={handleDiscover}
            disabled={isLoading}
          >
            {loadingAction === "discover" ? (
              <>
                <span className="spinner" /> Discovering Tools...
              </>
            ) : (
              "Discover Tools (Candidate Only)"
            )}
          </button>
        </div>
      </form>

      {/* Error Display Banner */}
      {errorDisplay && (
        <div className="error-banner" data-testid="mcp-error-banner">
          <div className="error-banner-header">
            <strong>{errorDisplay.title}</strong>
            {errorDisplay.code && (
              <span className="error-code-badge">[{errorDisplay.code}]</span>
            )}
          </div>
          <p className="error-message">{errorDisplay.message}</p>
          {errorDisplay.suggestion && (
            <p className="error-suggestion">
              💡 <strong>Suggestion:</strong> {errorDisplay.suggestion}
            </p>
          )}
        </div>
      )}

      {/* Discovery Metadata & Framework Status Card */}
      {activeDiscovery && (
        <div className="mcp-discovery-card" data-testid="mcp-discovery-status">
          <div className="mcp-discovery-header">
            <div className="discovery-badges">
              <span className={`confidence-pill confidence-${activeDiscovery.confidence}`}>
                {activeDiscovery.confidence.toUpperCase()} MCP SERVER
              </span>
              {activeDiscovery.has_mcp_client && (
                <span className="client-badge" data-testid="mcp-client-badge">
                  MCP Client Detected
                </span>
              )}
              <span className="framework-pill">
                Framework: {activeDiscovery.framework.toUpperCase()}
              </span>
              <span className="language-pill">Language: {activeDiscovery.language}</span>
              <span
                className={`extraction-status-pill extraction-${activeDiscovery.extraction_status.toLowerCase()}`}
                data-testid="extraction-status-pill"
              >
                Extraction: {activeDiscovery.extraction_status.toUpperCase()}
              </span>
            </div>

            <button
              type="button"
              className="btn-toggle-indicators"
              onClick={() => setShowIndicators(!showIndicators)}
            >
              {showIndicators ? "Hide Evidence" : `View Evidence (${activeDiscovery.indicators.length})`}
            </button>
          </div>

          {/* Explicit Extraction Status Alert for Partial or Failed Statuses */}
          {(activeDiscovery.extraction_status === "FAILED" || activeDiscovery.extraction_status === "PARTIAL") && (
            <div
              className={`status-alert-box alert-${activeDiscovery.extraction_status.toLowerCase()}`}
              data-testid="extraction-status-alert"
            >
              <strong>Extraction Status: {activeDiscovery.extraction_status}</strong>
              {activeDiscovery.extraction_warnings.map((w, idx) => (
                <p key={idx} className="warning-text" style={{ marginTop: "0.25rem" }}>
                  ⚠️ {w}
                </p>
              ))}
            </div>
          )}

          {/* Likely Entrypoints */}
          {activeDiscovery.server_entrypoints.length > 0 && (
            <div className="entrypoints-container" data-testid="server-entrypoints">
              <span className="entrypoints-label">Identified Server Entrypoints:</span>
              <div className="entrypoints-tags">
                {activeDiscovery.server_entrypoints.map((ep, idx) => (
                  <code key={idx} className="entrypoint-tag">
                    {ep}
                  </code>
                ))}
              </div>
            </div>
          )}

          {/* MCP Client Entrypoints */}
          {activeDiscovery.client_entrypoints && activeDiscovery.client_entrypoints.length > 0 && (
            <div className="entrypoints-container" data-testid="client-entrypoints">
              <span className="entrypoints-label">Identified Client Scripts:</span>
              <div className="entrypoints-tags">
                {activeDiscovery.client_entrypoints.map((ep, idx) => (
                  <code key={idx} className="entrypoint-tag client-tag" style={{ borderColor: "#f59e0b", color: "#f59e0b" }}>
                    {ep}
                  </code>
                ))}
              </div>
            </div>
          )}

          {/* Discovered Server Implementations Breakdown */}
          {activeDiscovery.servers && activeDiscovery.servers.length > 0 && (
            <div className="discovered-servers-section" data-testid="discovered-servers-section">
              <h5 className="servers-section-title">
                Discovered Server Implementations ({activeDiscovery.servers.length}):
              </h5>
              <div className="servers-grid">
                {activeDiscovery.servers.map((srv) => (
                  <div key={srv.server_id} className="server-card" data-testid={`server-card-${srv.server_id}`}>
                    <div className="server-card-header">
                      <strong className="server-name">{srv.name}</strong>
                      <span className="server-framework-badge">{srv.framework}</span>
                    </div>
                    <div className="server-entrypoint font-mono text-muted">{srv.entrypoint}</div>
                    <div className="server-tool-count text-accent">
                      {srv.tools.length} tool{srv.tools.length === 1 ? "" : "s"} registered
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Warnings & Security Boundaries */}
          <div className="security-notice-box">
            <span className="notice-icon">🛡️</span>
            <div>
              <strong>Static AST Extraction Complete</strong>
              <p>
                Extracted tools and schemas via static syntax analysis without executing repository code.
                Runtime MCP verification and live tool negotiation will be executed within disposable Docker
                sandboxes in Phase 6.
              </p>
              {activeDiscovery.extraction_warnings.length > 0 && (
                <ul className="warnings-list">
                  {activeDiscovery.extraction_warnings.map((w, idx) => (
                    <li key={idx} className="warning-item">
                      ⚠️ {w}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {/* Indicators List (Expandable) */}
          {showIndicators && (
            <div className="indicators-drawer" data-testid="indicators-drawer">
              <h5 className="indicators-heading">Detection Evidence & Indicators:</h5>
              <div className="indicators-list">
                {activeDiscovery.indicators.map((ind, idx) => (
                  <div key={idx} className="indicator-row">
                    <span className="indicator-badge">{ind.indicator_type}</span>
                    <span className="indicator-file">
                      {ind.file_path}
                      {ind.line_number ? `:${ind.line_number}` : ""}
                    </span>
                    <span className="indicator-details">{ind.details}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Comparison Summary Metrics */}
      {compareResult && (
        <div className="mcp-summary-bar" data-testid="mcp-comparison-summary">
          <div className="mcp-summary-metric">
            <span className="metric-label">Baseline Tools</span>
            <span className="metric-value font-mono">
              {compareResult.summary.total_baseline_tools}
            </span>
          </div>

          <div className="mcp-summary-metric">
            <span className="metric-label">Candidate Tools</span>
            <span className="metric-value font-mono">
              {compareResult.summary.total_candidate_tools}
            </span>
          </div>

          <div className="mcp-summary-metric text-green">
            <span className="metric-label">Added</span>
            <span className="metric-value font-mono">+{compareResult.summary.added_count}</span>
          </div>

          <div className="mcp-summary-metric text-red">
            <span className="metric-label">Removed</span>
            <span className="metric-value font-mono">-{compareResult.summary.removed_count}</span>
          </div>

          <div className="mcp-summary-metric text-purple">
            <span className="metric-label">Modified</span>
            <span className="metric-value font-mono">~{compareResult.summary.modified_count}</span>
          </div>

          <div className="mcp-summary-metric text-muted">
            <span className="metric-label">Unchanged</span>
            <span className="metric-value font-mono">={compareResult.summary.unchanged_count}</span>
          </div>

          {compareResult.summary.is_complete === false && (
            <div
              className="incomplete-verification-banner"
              data-testid="incomplete-verification-banner"
              style={{ width: "100%", marginTop: "0.5rem" }}
            >
              <span className="badge badge-warning" style={{ color: "#f59e0b", background: "rgba(245, 158, 11, 0.15)", border: "1px solid rgba(245, 158, 11, 0.3)" }}>
                ⚠️ Incomplete Verification: Discovery was PARTIAL due to inspection limits. Some source files were omitted.
              </span>
            </div>
          )}
        </div>
      )}

      {/* Per-Server Comparisons Breakdown */}
      {compareResult && compareResult.server_comparisons && compareResult.server_comparisons.length > 0 && (
        <div className="server-comparisons-section" data-testid="server-comparisons-section">
          <h4 className="servers-section-title">
            Server Inventory Comparison Breakdown ({compareResult.server_comparisons.length})
          </h4>
          <div className="server-comparisons-list">
            {compareResult.server_comparisons.map((sc) => (
              <div key={sc.server_id} className="server-comparison-card" data-testid={`server-comparison-${sc.server_id}`}>
                <div className="server-comparison-header">
                  <div>
                    <strong className="server-comparison-name">{sc.server_name}</strong>
                    <span className="text-muted font-mono" style={{ marginLeft: "8px", fontSize: "0.85rem" }}>
                      ({sc.candidate_entrypoint || sc.baseline_entrypoint})
                    </span>
                  </div>
                  <span className={`status-badge status-${sc.status}`}>{sc.status.toUpperCase()}</span>
                </div>
                <div className="server-comparison-summary font-mono text-muted" style={{ fontSize: "0.8rem" }}>
                  Baseline: {sc.summary.total_baseline_tools} | Candidate: {sc.summary.total_candidate_tools} | +{sc.summary.added_count} -{sc.summary.removed_count} ~{sc.summary.modified_count} ={sc.summary.unchanged_count}
                </div>
                {sc.status === "ambiguous" && (
                  <p className="ambiguous-warning text-warning" style={{ fontSize: "0.8rem", marginTop: "0.35rem", color: "#f59e0b" }}>
                    ⚠️ Ambiguous server identity: multiple server implementations share this name across different entrypoints.
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tool Inventory and Diffs List */}
      {(compareResult || discoverResult) && (
        <div className="tool-inventory-container" data-testid="tool-inventory">
          <h4 className="inventory-title">
            {compareResult
              ? `Tool Changes & Inventory (${compareResult.differences.length})`
              : `Discovered MCP Tools (${discoverResult?.discovery.extracted_tools.length || 0})`}
          </h4>

          {/* Render Diff List if Comparison was run */}
          {compareResult && (
            <div className="tool-diff-list">
              {compareResult.differences.map((diff: ToolDifference) => {
                const tool = diff.candidate_tool || diff.baseline_tool;
                const isExpanded = !!expandedSchemas[diff.tool_name];

                return (
                  <div
                    key={diff.tool_name}
                    className={`tool-card tool-change-${diff.change_type}`}
                    data-testid={`tool-card-${diff.tool_name}`}
                  >
                    <div className="tool-card-header">
                      <div className="tool-identity">
                        <span className={`tool-status-badge badge-${diff.change_type}`}>
                          {diff.change_type.replace("_", " ").toUpperCase()}
                        </span>
                        <code className="tool-name">{diff.tool_name}</code>
                      </div>

                      <button
                        type="button"
                        className="btn-toggle-schema"
                        onClick={() => toggleSchema(diff.tool_name)}
                      >
                        {isExpanded ? "Hide Schema" : "View JSON Schema"}
                      </button>
                    </div>

                    {tool?.description && (
                      <p className="tool-description">{tool.description}</p>
                    )}

                    {/* Detected Differences */}
                    {diff.changes_detected.length > 0 && (
                      <div className="diff-changes-box">
                        <span className="changes-label">Changes:</span>
                        <ul className="changes-list">
                          {diff.changes_detected.map((change, cIdx) => (
                            <li key={cIdx} className="change-item">
                              • {change}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Parameter List */}
                    {tool && tool.parameters.length > 0 && (
                      <div className="parameters-table-container">
                        <table className="parameters-table">
                          <thead>
                            <tr>
                              <th>Parameter</th>
                              <th>Type</th>
                              <th>Required</th>
                              <th>Default</th>
                              <th>Description</th>
                            </tr>
                          </thead>
                          <tbody>
                            {tool.parameters.map((param) => (
                              <tr key={param.name}>
                                <td className="font-mono font-bold text-accent">{param.name}</td>
                                <td>
                                  <span className="type-badge">{param.type}</span>
                                </td>
                                <td>
                                  {param.required ? (
                                    <span className="req-pill-yes">Required</span>
                                  ) : (
                                    <span className="req-pill-no">Optional</span>
                                  )}
                                </td>
                                <td className="font-mono text-muted">
                                  {param.default !== undefined && param.default !== null
                                    ? String(param.default)
                                    : "—"}
                                </td>
                                <td className="param-desc">{param.description || "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {/* Expandable JSON Schema */}
                    {isExpanded && tool && (
                      <div className="schema-view-container">
                        <span className="schema-label">Normalized JSON Schema:</span>
                        <pre className="schema-pre">
                          <code>{JSON.stringify(tool.input_schema, null, 2)}</code>
                        </pre>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Render Standalone Discovered Tools if Discover was run */}
          {discoverResult && (
            <div className="tool-diff-list">
              {discoverResult.discovery.extracted_tools.map((tool: ExtractedTool) => {
                const isExpanded = !!expandedSchemas[tool.name];

                return (
                  <div
                    key={tool.name}
                    className="tool-card tool-change-unchanged"
                    data-testid={`tool-card-${tool.name}`}
                  >
                    <div className="tool-card-header">
                      <div className="tool-identity">
                        <span className="tool-status-badge badge-unchanged">DISCOVERED</span>
                        <code className="tool-name">{tool.name}</code>
                      </div>

                      <button
                        type="button"
                        className="btn-toggle-schema"
                        onClick={() => toggleSchema(tool.name)}
                      >
                        {isExpanded ? "Hide Schema" : "View JSON Schema"}
                      </button>
                    </div>

                    {tool.description && (
                      <p className="tool-description">{tool.description}</p>
                    )}

                    {/* Parameters Table */}
                    {tool.parameters.length > 0 && (
                      <div className="parameters-table-container">
                        <table className="parameters-table">
                          <thead>
                            <tr>
                              <th>Parameter</th>
                              <th>Type</th>
                              <th>Required</th>
                              <th>Default</th>
                              <th>Description</th>
                            </tr>
                          </thead>
                          <tbody>
                            {tool.parameters.map((param) => (
                              <tr key={param.name}>
                                <td className="font-mono font-bold text-accent">{param.name}</td>
                                <td>
                                  <span className="type-badge">{param.type}</span>
                                </td>
                                <td>
                                  {param.required ? (
                                    <span className="req-pill-yes">Required</span>
                                  ) : (
                                    <span className="req-pill-no">Optional</span>
                                  )}
                                </td>
                                <td className="font-mono text-muted">
                                  {param.default !== undefined && param.default !== null
                                    ? String(param.default)
                                    : "—"}
                                </td>
                                <td className="param-desc">{param.description || "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {isExpanded && (
                      <div className="schema-view-container">
                        <span className="schema-label">Normalized JSON Schema:</span>
                        <pre className="schema-pre">
                          <code>{JSON.stringify(tool.input_schema, null, 2)}</code>
                        </pre>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </section>
  );
};

