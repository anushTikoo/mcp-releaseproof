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
export interface HarnessMetadata {
  test_count: number;
  scenarios_covered: string[];
  tools_tested: string[];
  framework: string;
  summary: string;
}

export interface HarnessValidationResult {
  is_valid: boolean;
  syntax_valid: boolean;
  security_valid: boolean;
  structure_valid: boolean;
  schema_valid: boolean;
  rejection_reasons: string[];
  warnings: string[];
  identified_imports: string[];
  identified_tool_calls: string[];
  identified_scenarios?: string[];
  ast_node_count: number;
  line_count: number;
}

export interface GenerateHarnessRequest {
  repository_url: string;
  commit_sha: string;
  ref?: string;
  server_name?: string;
  tools: DiscoveredToolInput[];
  test_plan: TestPlan;
  model_id?: string;
  max_tokens?: number;
}

export interface GenerateHarnessResponse {
  status: string; // 'success' | 'rejected'
  repository_url: string;
  commit_sha: string;
  model: string;
  harness_code: string;
  metadata: HarnessMetadata;
  validation: HarnessValidationResult;
  inventory_origin?: string;
  trust_boundary_notice?: string;
  usage?: Record<string, unknown>;
  duration_ms: number;
}

export interface ValidateHarnessRequest {
  harness_code: string;
  tools?: DiscoveredToolInput[];
  test_plan?: TestPlan;
}

export interface ValidateHarnessResponse {
  status: string; // 'valid' | 'rejected'
  validation: HarnessValidationResult;
  inventory_origin?: string;
  trust_boundary_notice?: string;
}

export async function generateTestHarness(
  request: GenerateHarnessRequest,
  signal?: AbortSignal
): Promise<GenerateHarnessResponse> {
  const url = `${API_BASE_URL.replace(/\/+$/, "")}/harness/generate`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
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
          if (errJson.detail.includes("TOKEN_LIMIT_EXCEEDED")) {
            errorCode = "TOKEN_LIMIT_EXCEEDED";
          }
        }
      }
    } catch {
      // Use default status text
    }

    throw new InferenceApiError(response.status, errorMessage, errorCode);
  }

  return response.json();
}
export async function validateTestHarness(
  request: ValidateHarnessRequest,
  signal?: AbortSignal
): Promise<ValidateHarnessResponse> {
  const url = `${API_BASE_URL.replace(/\/+$/, "")}/harness/validate`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    let errorMessage = response.statusText;
    try {
      const errJson = await response.json();
      if (errJson && errJson.detail) {
        errorMessage = typeof errJson.detail === "string" ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {
      // default
    }
    throw new InferenceApiError(response.status, errorMessage, "VALIDATION_ERROR");
  }

  return response.json();
}

// =========================================================================
// Phase 6: Vultr Compute Sandbox Execution Types & Functions
// =========================================================================

export type ExecutionLifecycleState =
  | "QUEUED"
  | "PREPARING"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "TIMED_OUT"
  | "CLEANUP_FAILED";

export type TestVerdict =
  | "PASSED"
  | "FAILED"
  | "TIMED_OUT"
  | "ERROR"
  | "NOT_RUN";

export type SecurityEnforcementStatus =
  | "VERIFIED"
  | "INCOMPLETE"
  | "VIOLATED";

export type CleanupStatus =
  | "VERIFIED_CLEAN"
  | "CLEANUP_FAILED"
  | "PENDING";

export type VerificationVerdict =
  | "VERIFIED_SUCCESS"
  | "REGRESSION_DETECTED"
  | "SECURITY_VIOLATION"
  | "EXECUTION_TIMEOUT"
  | "INFRASTRUCTURE_FAILURE"
  | "UNSUPPORTED_DEPENDENCIES";

export interface SecurityControlItem {
  control_name: string;
  requested: string;
  observed?: string | null;
  status: SecurityEnforcementStatus;
  details?: string | null;
}

export interface SecurityEnforcementReport {
  overall_status: SecurityEnforcementStatus;
  controls: SecurityControlItem[];
  verified_at?: string | null;
  summary: string;
}

export interface SandboxExecutionRequest {
  repository_url: string;
  commit_sha: string;
  ref?: string;
  harness_code: string;
  server_entrypoint?: string;
  server_args?: string[];
  environment_variables?: Record<string, string>;
  timeout_seconds?: number;
  memory_limit_mb?: number;
  cpu_limit?: number;
  pids_limit?: number;
}

export interface SandboxExecutionResult {
  job_id: string;
  repository_url: string;
  commit_sha: string;
  lifecycle_status: ExecutionLifecycleState;
  test_verdict: TestVerdict;
  security_status: SecurityEnforcementStatus;
  cleanup_status: CleanupStatus;
  verification_verdict: VerificationVerdict;
  exit_code?: number | null;
  stdout: string;
  stderr: string;
  duration_ms: number;
  start_time?: string | null;
  end_time?: string | null;
  security_report: SecurityEnforcementReport;
  cleanup_details?: string | null;
  error_code?: string | null;
  error_message?: string | null;
}

export interface SandboxCapabilitiesResponse {
  prewarmed_dependencies: string[];
  runtime_network_mode: string;
  mcp_transport: string;
  default_timeout_seconds: number;
  max_timeout_seconds: number;
  default_memory_mb: number;
  max_memory_mb: number;
  enforced_security_features: string[];
}

export async function fetchSandboxCapabilities(
  signal?: AbortSignal
): Promise<SandboxCapabilitiesResponse> {
  const url = `${API_BASE_URL.replace(/\/+$/, "")}/sandbox/capabilities`;
  const response = await fetch(url, {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
    signal,
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch sandbox capabilities (${response.status})`);
  }

  return response.json();
}

export async function executeHarnessInSandbox(
  request: SandboxExecutionRequest,
  signal?: AbortSignal
): Promise<SandboxExecutionResult> {
  const url = `${API_BASE_URL.replace(/\/+$/, "")}/sandbox/execute`;
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
    let errorMessage = response.statusText;
    try {
      const errJson = await response.json();
      if (errJson && errJson.detail) {
        errorMessage = typeof errJson.detail === "string" ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {
      // default
    }
    throw new Error(`Sandbox execution failed (${response.status}): ${errorMessage}`);
  }

  return response.json();
}

export async function fetchSandboxJobStatus(
  jobId: string,
  signal?: AbortSignal
): Promise<SandboxExecutionResult> {
  const url = `${API_BASE_URL.replace(/\/+$/, "")}/sandbox/jobs/${encodeURIComponent(jobId)}`;
  const response = await fetch(url, {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
    signal,
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch job status (${response.status})`);
  }

  return response.json();
}

export async function abortSandboxJob(
  jobId: string,
  signal?: AbortSignal
): Promise<SandboxExecutionResult> {
  const url = `${API_BASE_URL.replace(/\/+$/, "")}/sandbox/jobs/${encodeURIComponent(jobId)}/abort`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/json",
    },
    signal,
  });

  if (!response.ok) {
    throw new Error(`Failed to abort sandbox job (${response.status})`);
  }

  return response.json();
}
