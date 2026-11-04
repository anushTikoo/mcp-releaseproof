import React, { useState } from "react";
import {
  ChangedFile,
  compareGitHubCommits,
  CompareCommitsResponse,
  GitHubApiError,
  resolveGitHubRefs,
  ResolveRefsResponse,
} from "../api/client";

interface ErrorDisplayInfo {
  title: string;
  message: string;
  code?: string;
  status?: number;
  suggestion?: string;
}

export const GitHubComparator: React.FC = () => {
  const [repoUrl, setRepoUrl] = useState<string>(
    "https://github.com/example/filesystem-mcp-server"
  );
  const [baselineRef, setBaselineRef] = useState<string>("v0.1.0");
  const [candidateRef, setCandidateRef] = useState<string>("v0.2.0");

  const [loadingAction, setLoadingAction] = useState<"resolve" | "compare" | null>(null);
  const [errorDisplay, setErrorDisplay] = useState<ErrorDisplayInfo | null>(null);

  const [resolveResult, setResolveResult] = useState<ResolveRefsResponse | null>(null);
  const [compareResult, setCompareResult] = useState<CompareCommitsResponse | null>(null);

  const [expandedPatches, setExpandedPatches] = useState<Record<string, boolean>>({});
  const [copiedSha, setCopiedSha] = useState<string | null>(null);

  const validateInputs = (): string | null => {
    const trimmedUrl = repoUrl.trim();
    if (!trimmedUrl) {
      return "Repository URL is required.";
    }

    const githubRegex = /^https:\/\/github\.com\/([a-zA-Z0-9_.-]+)\/([a-zA-Z0-9_.-]+)(?:\/)?$/;
    if (!githubRegex.test(trimmedUrl)) {
      return "Repository URL must be a valid public HTTPS GitHub repository URL (e.g. https://github.com/owner/repo).";
    }

    if (!baselineRef.trim()) {
      return "Baseline ref is required (branch, tag, or commit SHA).";
    }

    if (!candidateRef.trim()) {
      return "Candidate ref is required (branch, tag, or commit SHA).";
    }

    return null;
  };

  const handleResolveRefs = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorDisplay(null);

    const validationError = validateInputs();
    if (validationError) {
      setErrorDisplay({
        title: "Validation Error",
        message: validationError,
        code: "VALIDATION_ERROR",
      });
      return;
    }

    setLoadingAction("resolve");
    try {
      const response = await resolveGitHubRefs({
        repository_url: repoUrl.trim(),
        baseline_ref: baselineRef.trim(),
        candidate_ref: candidateRef.trim(),
      });
      setResolveResult(response);
      setCompareResult(null); // Reset compare result when only resolving
    } catch (err: unknown) {
      handleApiError(err, "Ref Resolution Failed");
    } finally {
      setLoadingAction(null);
    }
  };

  const handleCompareCommits = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorDisplay(null);

    const validationError = validateInputs();
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
      const response = await compareGitHubCommits({
        repository_url: repoUrl.trim(),
        baseline_ref: baselineRef.trim(),
        candidate_ref: candidateRef.trim(),
      });
      setCompareResult(response);
      setResolveResult({
        status: response.status,
        repository: response.repository,
        baseline: response.baseline,
        candidate: response.candidate,
        is_identical: response.comparison.is_identical,
      });
    } catch (err: unknown) {
      handleApiError(err, "Version Comparison Failed");
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
            "GitHub took too long to respond. The repository might be experiencing high latency or large diffs.";
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

  const togglePatch = (filename: string) => {
    setExpandedPatches((prev) => ({
      ...prev,
      [filename]: !prev[filename],
    }));
  };

  const copyToClipboard = (sha: string) => {
    navigator.clipboard?.writeText(sha);
    setCopiedSha(sha);
    setTimeout(() => {
      setCopiedSha(null);
    }, 2000);
  };

  const isLoading = loadingAction !== null;
  const activeRepo = compareResult?.repository || resolveResult?.repository;
  const activeBaseline = compareResult?.baseline || resolveResult?.baseline;
  const activeCandidate = compareResult?.candidate || resolveResult?.candidate;

  return (
    <section className="generator-card" data-testid="github-comparator">
      <div className="generator-header">
        <div>
          <h3 className="generator-title">GitHub Version Comparison</h3>
          <p className="generator-subtitle">
            Resolve Git refs, inspect commit metadata, and analyze release diffs for MCP servers.
          </p>
        </div>
        <span className="badge badge-primary">Phase 3</span>
      </div>

      <form className="generator-form">
        <div className="form-group">
          <label htmlFor="repo-url-input" className="form-label">
            Public GitHub Repository URL
          </label>
          <input
            id="repo-url-input"
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
            <label htmlFor="baseline-ref-input" className="form-label">
              Baseline Ref (Tag / Branch / SHA)
            </label>
            <input
              id="baseline-ref-input"
              type="text"
              className="form-input font-mono"
              value={baselineRef}
              onChange={(e) => setBaselineRef(e.target.value)}
              placeholder="e.g. v0.1.0 or main"
              disabled={isLoading}
            />
          </div>

          <div className="form-group">
            <label htmlFor="candidate-ref-input" className="form-label">
              Candidate Ref (Tag / Branch / SHA)
            </label>
            <input
              id="candidate-ref-input"
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
            data-testid="compare-btn"
            onClick={handleCompareCommits}
            disabled={isLoading}
          >
            {loadingAction === "compare" ? (
              <>
                <span className="spinner" /> Comparing Releases...
              </>
            ) : (
              "Compare Releases"
            )}
          </button>

          <button
            type="button"
            className="btn btn-secondary"
            data-testid="resolve-btn"
            onClick={handleResolveRefs}
            disabled={isLoading}
          >
            {loadingAction === "resolve" ? (
              <>
                <span className="spinner" /> Resolving Refs...
              </>
            ) : (
              "Resolve Refs Only"
            )}
          </button>
        </div>
      </form>

      {/* Error Display Banner */}
      {errorDisplay && (
        <div className="error-banner" data-testid="github-error-banner">
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

      {/* Repository Metadata Card */}
      {activeRepo && (
        <div className="repo-metadata-card" data-testid="repo-metadata">
          <div className="repo-metadata-header">
            <div>
              <a
                href={activeRepo.html_url}
                target="_blank"
                rel="noopener noreferrer"
                className="repo-title-link"
              >
                {activeRepo.full_name} ↗
              </a>
              {activeRepo.description && (
                <p className="repo-description">{activeRepo.description}</p>
              )}
            </div>
            <div className="repo-stats-badges">
              <span className="stat-pill">⭐ {activeRepo.stars_count.toLocaleString()}</span>
              <span className="stat-pill">🌿 {activeRepo.default_branch}</span>
              {activeRepo.is_private && <span className="stat-pill pill-warning">Private</span>}
            </div>
          </div>
        </div>
      )}

      {/* Resolved Commits Cards */}
      {(activeBaseline || activeCandidate) && (
        <div className="resolved-commits-grid" data-testid="resolved-commits">
          {activeBaseline && (
            <div className="commit-card" data-testid="baseline-commit-card">
              <div className="commit-card-header">
                <span className="ref-tag-badge">Baseline: {activeBaseline.ref}</span>
                <button
                  type="button"
                  className="copy-sha-btn"
                  title="Copy full SHA"
                  onClick={() => copyToClipboard(activeBaseline.sha)}
                >
                  <code>{activeBaseline.short_sha}</code>
                  <span>{copiedSha === activeBaseline.sha ? "Copied!" : "📋"}</span>
                </button>
              </div>
              <p className="commit-message">{activeBaseline.message.split("\n")[0]}</p>
              <div className="commit-meta">
                <span>👤 {activeBaseline.author_name}</span>
                <span>📅 {new Date(activeBaseline.committed_at).toLocaleDateString()}</span>
              </div>
            </div>
          )}

          {activeCandidate && (
            <div className="commit-card" data-testid="candidate-commit-card">
              <div className="commit-card-header">
                <span className="ref-tag-badge">Candidate: {activeCandidate.ref}</span>
                <button
                  type="button"
                  className="copy-sha-btn"
                  title="Copy full SHA"
                  onClick={() => copyToClipboard(activeCandidate.sha)}
                >
                  <code>{activeCandidate.short_sha}</code>
                  <span>{copiedSha === activeCandidate.sha ? "Copied!" : "📋"}</span>
                </button>
              </div>
              <p className="commit-message">{activeCandidate.message.split("\n")[0]}</p>
              <div className="commit-meta">
                <span>👤 {activeCandidate.author_name}</span>
                <span>📅 {new Date(activeCandidate.committed_at).toLocaleDateString()}</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Comparison Results */}
      {compareResult && (
        <div className="comparison-results" data-testid="comparison-results">
          {compareResult.comparison.is_identical ? (
            <div className="identical-banner" data-testid="identical-banner">
              <span className="identical-icon">ℹ️</span>
              <div>
                <strong>Commits are identical</strong>
                <p>
                  Baseline and candidate resolve to the exact same commit SHA (
                  <code>{compareResult.baseline.short_sha}</code>). No files were changed.
                </p>
              </div>
            </div>
          ) : (
            <>
              {/* Summary Metrics Bar */}
              <div className="diff-summary-bar">
                <div className="diff-status-indicator">
                  <span className={`status-badge status-${compareResult.comparison.status}`}>
                    Status: {compareResult.comparison.status.toUpperCase()}
                  </span>
                  <span className="divergence-text">
                    Ahead by {compareResult.comparison.ahead_by}, Behind by{" "}
                    {compareResult.comparison.behind_by}
                  </span>
                </div>

                <div className="diff-metrics">
                  <span className="diff-metric-item">
                    <strong>{compareResult.comparison.total_commits}</strong> commit
                    {compareResult.comparison.total_commits === 1 ? "" : "s"}
                  </span>
                  <span className="diff-metric-item">
                    <strong>{compareResult.comparison.files_changed_count}</strong> file
                    {compareResult.comparison.files_changed_count === 1 ? "" : "s"} changed
                  </span>
                  <span className="diff-metric-item text-green">
                    +{compareResult.comparison.additions.toLocaleString()}
                  </span>
                  <span className="diff-metric-item text-red">
                    -{compareResult.comparison.deletions.toLocaleString()}
                  </span>
                </div>
              </div>

              {/* Truncated File Notice */}
              {compareResult.comparison.is_truncated && (
                <div className="warning-banner" data-testid="truncated-warning">
                  ⚠️ <strong>Notice:</strong> This comparison exceeds GitHub's 300-file limit and
                  has been truncated.
                </div>
              )}

              {/* Changed Files List */}
              <div className="changed-files-container">
                <h4 className="changed-files-title">
                  Changed Files ({compareResult.comparison.files.length})
                </h4>

                <div className="file-list">
                  {compareResult.comparison.files.map((file: ChangedFile) => {
                    const isExpanded = !!expandedPatches[file.filename];

                    return (
                      <div
                        key={file.filename}
                        className="file-diff-item"
                        data-testid={`file-diff-${file.filename}`}
                      >
                        <div className="file-diff-header">
                          <div className="file-info">
                            <span className={`file-status-badge status-${file.status}`}>
                              {file.status}
                            </span>
                            <span className="file-path">{file.filename}</span>
                            {file.previous_filename && (
                              <span className="file-previous-path">
                                (was {file.previous_filename})
                              </span>
                            )}
                          </div>

                          <div className="file-actions">
                            <span className="file-changes">
                              <span className="text-green">+{file.additions}</span>
                              <span className="text-red">-{file.deletions}</span>
                            </span>
                            <button
                              type="button"
                              className="btn-toggle-diff"
                              onClick={() => togglePatch(file.filename)}
                            >
                              {isExpanded ? "Hide Diff" : "View Diff"}
                            </button>
                          </div>
                        </div>

                        {isExpanded && (
                          <div className="file-patch-container">
                            {file.patch ? (
                              <pre className="patch-pre">
                                <code>
                                  {file.patch.split("\n").map((line: string, idx: number) => {
                                    let lineClass = "patch-line";
                                    if (line.startsWith("+")) {
                                      lineClass += " patch-added";
                                    } else if (line.startsWith("-")) {
                                      lineClass += " patch-deleted";
                                    } else if (line.startsWith("@@")) {
                                      lineClass += " patch-hunk";
                                    }
                                    return (
                                      <div key={idx} className={lineClass}>
                                        {line}
                                      </div>
                                    );
                                  })}
                                </code>
                              </pre>
                            ) : (
                              <div className="patch-omitted">
                                Patch content omitted by GitHub or binary file.
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
};
