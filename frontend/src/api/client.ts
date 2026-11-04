export interface HealthStatusResponse {
  status: string;
  app: string;
  version: string;
  timestamp: string;
}

export interface DiscoveredToolInput {
  tool_name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface TestStep {
  step_index: number;
  tool_name: string;
  arguments: Record<string, unknown>;
  expected_result?: string;
  expected_behavior?: string;
}

export interface TestScenario {
  scenario_id: string;
  title: string;
  objective: string;
  safety_classification: string;
  steps: TestStep[];
}

export interface TestPlan {
  plan_id: string;
  target_server_summary: string;
  coverage_notes?: string | null;
  scenarios: TestScenario[];
}

export class InferenceApiError extends Error {
  status: number;
  code: string;
  upstreamStatus?: number | null;

  constructor(
    status: number,
    message: string,
    code: string,
    upstreamStatus?: number | null
  ) {
    super(message);
    this.name = "InferenceApiError";
    this.status = status;
    this.code = code;
    this.upstreamStatus = upstreamStatus;
  }
}

export class GitHubApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, message: string, code: string) {
    super(message);
    this.name = "GitHubApiError";
    this.status = status;
    this.code = code;
  }
}

export interface RepositoryMetadata {
  owner: string;
  name: string;
  full_name: string;
  description: string | null;
  html_url: string;
  default_branch: string;
  is_private: boolean;
  stars_count: number;
  forks_count: number;
  open_issues_count: number;
}

export interface CommitMetadata {
  ref: string;
  sha: string;
  short_sha: string;
  message: string;
  author_name: string;
  author_date?: string | null;
  committer_name: string;
  committed_at: string;
  html_url: string;
}

export interface ChangedFile {
  filename: string;
  status: "added" | "modified" | "removed" | "renamed" | string;
  additions: number;
  deletions: number;
  changes: number;
  patch?: string | null;
  previous_filename?: string | null;
}

export interface ComparisonSummary {
  status: "ahead" | "behind" | "identical" | "diverged" | string;
  ahead_by: number;
  behind_by: number;
  total_commits: number;
  files_changed_count: number;
  additions: number;
  deletions: number;
  is_identical: boolean;
  is_truncated: boolean;
  files: ChangedFile[];
}

export interface ResolveRefsRequest {
  repository_url: string;
  baseline_ref: string;
  candidate_ref: string;
}

export interface ResolveRefsResponse {
  status: string;
  repository: RepositoryMetadata;
  baseline: CommitMetadata;
  candidate: CommitMetadata;
  is_identical: boolean;
}

export interface CompareCommitsRequest {
  repository_url: string;
  baseline_ref: string;
  candidate_ref: string;
}

export interface CompareCommitsResponse {
  status: string;
  repository: RepositoryMetadata;
  baseline: CommitMetadata;
  candidate: CommitMetadata;
  comparison: ComparisonSummary;
}

export interface ToolParameter {
  name: string;
  type: string;
  description?: string | null;
  required: boolean;
  default?: unknown;
  enum_values?: unknown[] | null;
  items?: Record<string, unknown> | null;
  properties?: Record<string, unknown> | null;
}

export interface ExtractedTool {
  name: string;
  description?: string | null;
  input_schema: Record<string, unknown>;
  parameters: ToolParameter[];
  source_file?: string | null;
  source_line?: number | null;
  server_name?: string | null;
  schema_hash: string;
}

export interface MCPServerIndicator {
  category: string;
  indicator_type: string;
  confidence: string;
  file_path: string;
  line_number?: number | null;
  details: string;
}

export interface DiscoveredServer {
  server_id: string;
  name: string;
  entrypoint: string;
  framework: string;
  description?: string | null;
  tools: ExtractedTool[];
}

export interface MCPServerDiscovery {
  has_mcp_server: boolean;
  has_mcp_client: boolean;
  confidence: "confirmed" | "probable" | "inconclusive" | "unsupported" | string;
  framework: "fastmcp" | "mcp_lowlevel" | "typescript_sdk" | "custom" | "unknown" | string;
  language: string;
  server_entrypoints: string[];
  client_entrypoints: string[];
  servers: DiscoveredServer[];
  indicators: MCPServerIndicator[];
  extracted_tools: ExtractedTool[];
  extraction_status: "COMPLETE" | "PARTIAL" | "FAILED" | "UNSUPPORTED" | string;
  extraction_warnings: string[];
  runtime_verification_required: boolean;
}

export interface DiscoverMCPRequest {
  repository_url: string;
  ref: string;
}

export interface DiscoverMCPResponse {
  status: string;
  repository_url: string;
  ref: string;
  commit_sha: string;
  discovery: MCPServerDiscovery;
}

export interface ToolDifference {
  tool_name: string;
  server_id?: string | null;
  change_type: "added" | "removed" | "modified_schema" | "modified_description" | "modified_both" | "unchanged" | string;
  baseline_tool?: ExtractedTool | null;
  candidate_tool?: ExtractedTool | null;
  changes_detected: string[];
}

export interface ToolComparisonSummary {
  total_baseline_tools: number;
  total_candidate_tools: number;
  added_count: number;
  removed_count: number;
  modified_count: number;
  unchanged_count: number;
  is_complete?: boolean;
}

export interface ServerComparison {
  server_id: string;
  server_name: string;
  baseline_entrypoint?: string | null;
  candidate_entrypoint?: string | null;
  status: "matched" | "added" | "removed" | "ambiguous" | string;
  summary: ToolComparisonSummary;
  differences: ToolDifference[];
}

export interface CompareMCPToolsRequest {
  repository_url: string;
  baseline_ref: string;
  candidate_ref: string;
}

export interface CompareMCPToolsResponse {
  status: string;
  repository_url: string;
  baseline_ref: string;
  baseline_sha: string;
  candidate_ref: string;
  candidate_sha: string;
  baseline_discovery: MCPServerDiscovery;
  candidate_discovery: MCPServerDiscovery;
  summary: ToolComparisonSummary;
  differences: ToolDifference[];
  server_comparisons: ServerComparison[];
}

export interface GenerationRequest {
  repository_url: string;
  tools: DiscoveredToolInput[];
  model_id?: string;
}

export interface GenerationResponse {
  status: string;
  model: string;
  plan: TestPlan;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
    [key: string]: unknown;
  };
  duration_ms: number;
}

export interface InferenceConfigStatus {
  api_key_configured: boolean;
  configured_model: string | null;
  base_url: string;
  benchmark_models: string[];
}

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ||
  "http://localhost:8000/api";

export async function fetchHealth(
  signal?: AbortSignal
): Promise<HealthStatusResponse> {
  const url = `${API_BASE_URL.replace(/\/+$/, "")}/health`;
  const response = await fetch(url, {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
    signal,
  });

  if (!response.ok) {
    throw new Error(
      `Health check failed with HTTP ${response.status}: ${response.statusText}`
    );
  }

  return response.json();
}

export async function fetchInferenceStatus(
  signal?: AbortSignal
): Promise<InferenceConfigStatus> {
  const url = `${API_BASE_URL.replace(/\/+$/, "")}/inference/status`;
  const response = await fetch(url, {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
    signal,
  });

  if (!response.ok) {
    throw new Error(
      `Failed to fetch inference configuration status (${response.status})`
    );
  }

  return response.json();
}

export async function resolveGitHubRefs(
  request: ResolveRefsRequest,
  signal?: AbortSignal
): Promise<ResolveRefsResponse> {
  const url = `${API_BASE_URL.replace(/\/+$/, "")}/github/resolve`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    let errorCode = "UNKNOWN_ERROR";
    let errorMessage = response.statusText;

    try {
      const errJson = await response.json();
      if (errJson && errJson.detail) {
        if (typeof errJson.detail === "object" && errJson.detail !== null) {
          errorCode = errJson.detail.code || errorCode;
          errorMessage = errJson.detail.message || errorMessage;
        } else if (typeof errJson.detail === "string") {
          errorMessage = errJson.detail;
        }
      }
    } catch {
      // Keep default
    }

    throw new GitHubApiError(response.status, errorMessage, errorCode);
  }

  return response.json();
}

export async function compareGitHubCommits(
  request: CompareCommitsRequest,
  signal?: AbortSignal
): Promise<CompareCommitsResponse> {
  const url = `${API_BASE_URL.replace(/\/+$/, "")}/github/compare`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    let errorCode = "UNKNOWN_ERROR";
    let errorMessage = response.statusText;

    try {
      const errJson = await response.json();
      if (errJson && errJson.detail) {
        if (typeof errJson.detail === "object" && errJson.detail !== null) {
          errorCode = errJson.detail.code || errorCode;
          errorMessage = errJson.detail.message || errorMessage;
        } else if (typeof errJson.detail === "string") {
          errorMessage = errJson.detail;
        }
      }
    } catch {
      // Keep default
    }

    throw new GitHubApiError(response.status, errorMessage, errorCode);
  }

  return response.json();
}

export async function discoverMCPServer(
  request: DiscoverMCPRequest,
  signal?: AbortSignal
): Promise<DiscoverMCPResponse> {
  const url = `${API_BASE_URL.replace(/\/+$/, "")}/mcp/discover`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    let errorCode = "UNKNOWN_ERROR";
    let errorMessage = response.statusText;

    try {
      const errJson = await response.json();
      if (errJson && errJson.detail) {
        if (typeof errJson.detail === "object" && errJson.detail !== null) {
          errorCode = errJson.detail.code || errorCode;
          errorMessage = errJson.detail.message || errorMessage;
        } else if (typeof errJson.detail === "string") {
          errorMessage = errJson.detail;
        }
      }
    } catch {
      // Keep default
    }

    throw new GitHubApiError(response.status, errorMessage, errorCode);
  }

  return response.json();
}

export async function compareMCPTools(
  request: CompareMCPToolsRequest,
  signal?: AbortSignal
): Promise<CompareMCPToolsResponse> {
  const url = `${API_BASE_URL.replace(/\/+$/, "")}/mcp/compare`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    let errorCode = "UNKNOWN_ERROR";
    let errorMessage = response.statusText;

    try {
      const errJson = await response.json();
      if (errJson && errJson.detail) {
        if (typeof errJson.detail === "object" && errJson.detail !== null) {
          errorCode = errJson.detail.code || errorCode;
          errorMessage = errJson.detail.message || errorMessage;
        } else if (typeof errJson.detail === "string") {
          errorMessage = errJson.detail;
        }
      }
    } catch {
      // Keep default
    }

    throw new GitHubApiError(response.status, errorMessage, errorCode);
  }

  return response.json();
}

export async function generateTestPlan(
  request: GenerationRequest,
  signal?: AbortSignal
): Promise<GenerationResponse> {
  const url = `${API_BASE_URL.replace(/\/+$/, "")}/inference/generate-plan`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    let errorCode = "UNKNOWN_ERROR";
    let errorMessage = response.statusText;
    let upstreamStatus: number | null = null;

    try {
      const errJson = await response.json();
      if (errJson && errJson.detail) {
        if (typeof errJson.detail === "object" && errJson.detail !== null) {
          errorCode = errJson.detail.code || errorCode;
          errorMessage = errJson.detail.message || errorMessage;
          upstreamStatus = errJson.detail.upstream_status ?? null;
        } else if (typeof errJson.detail === "string") {
          errorMessage = errJson.detail;
          if (errJson.detail.includes("TOKEN_LIMIT_EXCEEDED")) {
            errorCode = "TOKEN_LIMIT_EXCEEDED";
          } else if (
            errJson.detail.includes("EMPTY_CONTENT") ||
            errJson.detail.includes("EMPTY_CHOICES") ||
            errJson.detail.includes("REASONING_WITHOUT_CONTENT")
          ) {
            errorCode = "EMPTY_CONTENT";
          } else if (errJson.detail.includes("JSON_PARSE_FAILED")) {
            errorCode = "JSON_PARSE_FAILED";
          } else if (errJson.detail.includes("SCHEMA_VALIDATION_FAILED")) {
            errorCode = "SCHEMA_VALIDATION_FAILED";
          } else if (errJson.detail.includes("UPSTREAM_HTTP_ERROR")) {
            errorCode = "UPSTREAM_HTTP_ERROR";
          }
        }
      }
    } catch {
      // Use statusText default
    }

    throw new InferenceApiError(
      response.status,
      errorMessage,
      errorCode,
      upstreamStatus
    );
  }

  return response.json();
}
