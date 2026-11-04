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

