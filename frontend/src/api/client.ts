export interface HealthStatusResponse {
  status: string;
  app: string;
  version: string;
  timestamp: string;
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

