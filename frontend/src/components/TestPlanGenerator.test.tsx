import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { TestPlanGenerator } from "./TestPlanGenerator";

const MOCK_CONFIG_STATUS = {
  api_key_configured: true,
  configured_model: "qwen3.8-flash-next",
  base_url: "https://api.vultrinference.com/v1",
  benchmark_models: ["qwen3.8-flash-next"],
};

const MOCK_GENERATION_SUCCESS = {
  status: "success",
  model: "qwen3.8-flash-next",
  duration_ms: 450.2,
  usage: { prompt_tokens: 100, completion_tokens: 60, total_tokens: 160 },
  plan: {
    plan_id: "plan-test-01",
    target_server_summary: "Test file reader server",
    coverage_notes: "Full read coverage",
    scenarios: [
      {
        scenario_id: "sc-01",
        title: "Test File Read Normal",
        objective: "Read file with valid path",
        safety_classification: "benign_baseline",
        steps: [
          {
            step_index: 1,
            tool_name: "read_file",
            arguments: { path: "/test.txt" },
            expected_behavior: "File contents returned",
          },
        ],
      },
    ],
  },
};

describe("TestPlanGenerator Component", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("fetches and displays configuration status on mount", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/inference/status")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_CONFIG_STATUS,
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<TestPlanGenerator />);

    await waitFor(() => {
      expect(
        screen.getByText("✓ API Key Configured (Backend)")
      ).toBeInTheDocument();
    });
  });

  it("generates and renders test plan upon successful submission", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/inference/status")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_CONFIG_STATUS,
        });
      }
      if (url.includes("/inference/generate-plan")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_GENERATION_SUCCESS,
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<TestPlanGenerator />);

    await waitFor(() => {
      expect(screen.getByTestId("generate-plan-btn")).toBeInTheDocument();
    });

    const submitBtn = screen.getByTestId("generate-plan-btn");
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("plan-results")).toBeInTheDocument();
    });

    expect(screen.getByText("Generated Plan: plan-test-01")).toBeInTheDocument();
    expect(screen.getByText("Test File Read Normal")).toBeInTheDocument();
    expect(screen.getByText("read_file")).toBeInTheDocument();
  });

  it("displays error banner when generation API fails", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/inference/status")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            ...MOCK_CONFIG_STATUS,
            api_key_configured: false,
          }),
        });
      }
      if (url.includes("/inference/generate-plan")) {
        return Promise.resolve({
          ok: false,
          status: 400,
          statusText: "Bad Request",
          json: async () => ({
            detail: "Vultr Inference API key is not configured.",
          }),
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<TestPlanGenerator />);

    const submitBtn = screen.getByTestId("generate-plan-btn");
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(
        screen.getByTestId("inference-error-banner")
      ).toBeInTheDocument();
    });

    expect(
      screen.getByText(/Vultr Inference API key is not configured/i)
    ).toBeInTheDocument();
  });

  it("displays clear truncated error message when TOKEN_LIMIT_EXCEEDED occurs", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/inference/status")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_CONFIG_STATUS,
        });
      }
      if (url.includes("/inference/generate-plan")) {
        return Promise.resolve({
          ok: false,
          status: 422,
          statusText: "Unprocessable Entity",
          json: async () => ({
            detail: {
              code: "TOKEN_LIMIT_EXCEEDED",
              message: "Inference output was truncated because it reached token budget.",
              upstream_status: 200,
            },
          }),
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<TestPlanGenerator />);

    const submitBtn = await screen.findByTestId("generate-plan-btn");
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(
        screen.getByText("Generation Truncated (Token Limit Reached)")
      ).toBeInTheDocument();
    });

    expect(
      screen.getByText("The model output was truncated. Try a more compact test plan.")
    ).toBeInTheDocument();
    // Verify it is NOT labeled as HTTP 502
    expect(screen.queryByText(/Inference Error \(502\)/i)).not.toBeInTheDocument();
  });

  it("displays distinct error message for empty model responses", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/inference/status")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_CONFIG_STATUS,
        });
      }
      if (url.includes("/inference/generate-plan")) {
        return Promise.resolve({
          ok: false,
          status: 422,
          statusText: "Unprocessable Entity",
          json: async () => ({
            detail: {
              code: "EMPTY_CONTENT",
              message: "Upstream returned empty content",
              upstream_status: 200,
            },
          }),
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<TestPlanGenerator />);

    const submitBtn = await screen.findByTestId("generate-plan-btn");
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(screen.getByText("Empty Model Response")).toBeInTheDocument();
    });
  });

  it("displays distinct error message for JSON parsing failures", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/inference/status")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_CONFIG_STATUS,
        });
      }
      if (url.includes("/inference/generate-plan")) {
        return Promise.resolve({
          ok: false,
          status: 422,
          statusText: "Unprocessable Entity",
          json: async () => ({
            detail: {
              code: "JSON_PARSE_FAILED",
              message: "Model response was not valid JSON",
              upstream_status: 200,
            },
          }),
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<TestPlanGenerator />);

    const submitBtn = await screen.findByTestId("generate-plan-btn");
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(screen.getByText("JSON Parsing Failure")).toBeInTheDocument();
    });
  });

  it("displays distinct error message for Pydantic schema validation failures", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/inference/status")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_CONFIG_STATUS,
        });
      }
      if (url.includes("/inference/generate-plan")) {
        return Promise.resolve({
          ok: false,
          status: 422,
          statusText: "Unprocessable Entity",
          json: async () => ({
            detail: {
              code: "SCHEMA_VALIDATION_FAILED",
              message: "Model output failed strict TestPlan schema validation",
              upstream_status: 200,
            },
          }),
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<TestPlanGenerator />);

    const submitBtn = await screen.findByTestId("generate-plan-btn");
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(screen.getByText("Pydantic Validation Failure")).toBeInTheDocument();
    });
  });

  it("displays distinct error message for upstream HTTP errors", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/inference/status")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_CONFIG_STATUS,
        });
      }
      if (url.includes("/inference/generate-plan")) {
        return Promise.resolve({
          ok: false,
          status: 502,
          statusText: "Bad Gateway",
          json: async () => ({
            detail: {
              code: "UPSTREAM_HTTP_ERROR",
              message: "Vultr API returned error 502",
              upstream_status: 502,
            },
          }),
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<TestPlanGenerator />);

    const submitBtn = await screen.findByTestId("generate-plan-btn");
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(screen.getByText(/Upstream HTTP Error/i)).toBeInTheDocument();
    });
  });
});

