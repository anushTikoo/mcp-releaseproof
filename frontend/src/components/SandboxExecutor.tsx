import React, { useState } from "react";
import {
  executeHarnessInSandbox,
  SandboxExecutionResult,
  SecurityControlItem,
} from "../api/client";

interface SandboxExecutorProps {
  repositoryUrl: string;
  commitSha: string;
  refName?: string;
  harnessCode: string;
  serverEntrypoint?: string;
}

export const SandboxExecutor: React.FC<SandboxExecutorProps> = ({
  repositoryUrl,
  commitSha,
  refName,
  harnessCode,
  serverEntrypoint = "server.py",
}) => {
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [executionResult, setExecutionResult] = useState<SandboxExecutionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"stdout" | "stderr" | "security">("stdout");

  const handleExecute = async () => {
    setIsRunning(true);
    setError(null);

    try {
      const result = await executeHarnessInSandbox({
        repository_url: repositoryUrl,
        commit_sha: commitSha,
        ref: refName,
        harness_code: harnessCode,
        server_entrypoint: serverEntrypoint,
        timeout_seconds: 60,
        memory_limit_mb: 512,
        cpu_limit: 1.0,
        pids_limit: 64,
      });
      setExecutionResult(result);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    } finally {
      setIsRunning(false);
    }
  };

  const getVerdictBadgeClass = (verdict: string) => {
    switch (verdict) {
      case "VERIFIED_SUCCESS":
      case "PASSED":
      case "VERIFIED":
      case "VERIFIED_CLEAN":
        return "badge-success";
      case "REGRESSION_DETECTED":
      case "FAILED":
      case "VIOLATED":
      case "CLEANUP_FAILED":
        return "badge-danger";
      case "TIMED_OUT":
      case "EXECUTION_TIMEOUT":
      case "SECURITY_VIOLATION":
      case "INCOMPLETE":
      case "UNSUPPORTED_DEPENDENCIES":
        return "badge-warning";
      default:
        return "badge-neutral";
    }
  };

  return (
    <div className="sandbox-executor-card" data-testid="sandbox-executor">
      <div className="sandbox-header">
        <div>
          <h3>Vultr Compute Sandbox Execution</h3>
          <p className="section-description">
            Execute the validated test harness against the candidate MCP server inside an isolated,
            network-disconnected Docker container on Vultr Compute.
          </p>
        </div>
        <button
          className="btn btn-primary btn-execute"
          onClick={handleExecute}
          disabled={isRunning || !harnessCode.trim()}
          data-testid="execute-sandbox-btn"
        >
          {isRunning ? "Executing in Sandbox..." : "Execute in Sandbox"}
        </button>
      </div>

      {error && (
        <div className="alert alert-danger" data-testid="sandbox-error-alert">
          <strong>Execution Error:</strong> {error}
        </div>
      )}

      {executionResult && (
        <div className="sandbox-results" data-testid="sandbox-results">
          {/* Top-Level Verification Banner */}
          <div
            className={`verification-banner ${
              executionResult.verification_verdict === "VERIFIED_SUCCESS"
                ? "banner-success"
                : executionResult.verification_verdict === "REGRESSION_DETECTED"
                ? "banner-danger"
                : "banner-warning"
            }`}
            data-testid="verification-banner"
          >
            <div className="banner-title">
              Overall Verdict:{" "}
              <span className={`badge ${getVerdictBadgeClass(executionResult.verification_verdict)}`}>
                {executionResult.verification_verdict}
              </span>
            </div>
            <div className="banner-details">
              {executionResult.verification_verdict === "VERIFIED_SUCCESS" && (
                <p>
                  Behavior verified compatible. Test harness passed, all security containment
                  controls were independently observed, and container was cleaned up.
                </p>
              )}
              {executionResult.verification_verdict === "REGRESSION_DETECTED" && (
                <p>
                  <strong>Behavioral regression detected:</strong> Test assertions failed against the
                  candidate MCP server. Exit code: {executionResult.exit_code}.
                </p>
              )}
              {executionResult.verification_verdict === "SECURITY_VIOLATION" && (
                <p>
                  <strong>Security violation:</strong> One or more container containment policies were
                  violated or could not be verified.
                </p>
              )}
              {executionResult.verification_verdict === "EXECUTION_TIMEOUT" && (
                <p>
                  <strong>Execution timed out:</strong> Test process exceeded wall-clock budget and was
                  forcefully killed with SIGKILL.
                </p>
              )}
              {executionResult.verification_verdict === "INFRASTRUCTURE_FAILURE" && (
                <p>
                  <strong>Infrastructure or cleanup failure:</strong> {executionResult.cleanup_details || "Host error."}
                </p>
              )}
              {executionResult.verification_verdict === "UNSUPPORTED_DEPENDENCIES" && (
                <p>
                  <strong>Unsupported dependencies:</strong> {executionResult.error_message}
                </p>
              )}
            </div>
          </div>

          {/* Individual Status Metrics */}
          <div className="status-grid" data-testid="status-grid">
            <div className="status-item">
              <span className="status-label">Lifecycle State</span>
              <span className={`badge ${getVerdictBadgeClass(executionResult.lifecycle_status)}`} data-testid="lifecycle-badge">
                {executionResult.lifecycle_status}
              </span>
            </div>
            <div className="status-item">
              <span className="status-label">Test Verdict</span>
              <span className={`badge ${getVerdictBadgeClass(executionResult.test_verdict)}`} data-testid="test-verdict-badge">
                {executionResult.test_verdict}
              </span>
            </div>
            <div className="status-item">
              <span className="status-label">Security Audit</span>
              <span className={`badge ${getVerdictBadgeClass(executionResult.security_status)}`} data-testid="security-badge">
                {executionResult.security_status}
              </span>
            </div>
            <div className="status-item">
              <span className="status-label">Cleanup Status</span>
              <span className={`badge ${getVerdictBadgeClass(executionResult.cleanup_status)}`} data-testid="cleanup-badge">
                {executionResult.cleanup_status}
              </span>
            </div>
            <div className="status-item">
              <span className="status-label">Duration</span>
              <span className="status-value">{executionResult.duration_ms.toFixed(1)} ms</span>
            </div>
            <div className="status-item">
              <span className="status-label">Exit Code</span>
              <span className="status-value">
                {executionResult.exit_code !== null && executionResult.exit_code !== undefined
                  ? executionResult.exit_code
                  : "N/A"}
              </span>
            </div>
          </div>

          {/* Tab Navigation */}
          <div className="tabs sandbox-tabs">
            <button
              className={`tab-btn ${activeTab === "stdout" ? "active" : ""}`}
              onClick={() => setActiveTab("stdout")}
              data-testid="tab-stdout"
            >
              Harness Output (stdout)
            </button>
            <button
              className={`tab-btn ${activeTab === "stderr" ? "active" : ""}`}
              onClick={() => setActiveTab("stderr")}
              data-testid="tab-stderr"
            >
              Diagnostic Log (stderr)
            </button>
            <button
              className={`tab-btn ${activeTab === "security" ? "active" : ""}`}
              onClick={() => setActiveTab("security")}
              data-testid="tab-security"
            >
              Security Audit Evidence ({executionResult.security_report.controls.length})
            </button>
          </div>

          {/* Tab Content */}
          <div className="tab-content">
            {activeTab === "stdout" && (
              <div className="output-panel" data-testid="stdout-panel">
                <pre className="code-block log-block">
                  {executionResult.stdout || "(No stdout output captured)"}
                </pre>
              </div>
            )}

            {activeTab === "stderr" && (
              <div className="output-panel" data-testid="stderr-panel">
                <pre className="code-block log-block">
                  {executionResult.stderr || "(No stderr output captured)"}
                </pre>
              </div>
            )}

            {activeTab === "security" && (
              <div className="security-audit-panel" data-testid="security-panel">
                <p className="audit-summary">{executionResult.security_report.summary}</p>
                <table className="security-audit-table">
                  <thead>
                    <tr>
                      <th>Control</th>
                      <th>Requested Setting</th>
                      <th>Observed from Inspection</th>
                      <th>Verdict</th>
                    </tr>
                  </thead>
                  <tbody>
                    {executionResult.security_report.controls.map((ctrl: SecurityControlItem, idx: number) => (
                      <tr key={idx} data-testid={`security-control-${ctrl.control_name}`}>
                        <td>
                          <strong>{ctrl.control_name}</strong>
                          {ctrl.details && <div className="control-details">{ctrl.details}</div>}
                        </td>
                        <td><code>{ctrl.requested}</code></td>
                        <td><code>{ctrl.observed || "Not observed"}</code></td>
                        <td>
                          <span className={`badge ${getVerdictBadgeClass(ctrl.status)}`}>
                            {ctrl.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
