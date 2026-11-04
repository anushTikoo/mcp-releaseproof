import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { HealthStatus } from "./HealthStatus";

describe("HealthStatus component", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("renders success state when backend health check succeeds", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        status: "ok",
        app: "mcp-releaseproof",
        version: "0.1.0",
        timestamp: "2026-11-04T12:00:00Z",
      }),
    });

    render(<HealthStatus />);

    await waitFor(() => {
      expect(screen.getByTestId("status-ok")).toBeInTheDocument();
    });

    expect(screen.getByText("mcp-releaseproof")).toBeInTheDocument();
    expect(screen.getByText("0.1.0")).toBeInTheDocument();
    expect(screen.getByText("2026-11-04T12:00:00Z")).toBeInTheDocument();
  });

  it("renders error state when backend health check fails", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error("Failed to fetch"));

    render(<HealthStatus />);

    await waitFor(() => {
      expect(screen.getByTestId("status-error")).toBeInTheDocument();
    });

    expect(
      screen.getByText("Failed to fetch")
    ).toBeInTheDocument();
  });

  it("re-queries health status when recheck button is clicked", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        status: "ok",
        app: "mcp-releaseproof",
        version: "0.1.0",
        timestamp: "2026-11-04T12:00:00Z",
      }),
    });
    globalThis.fetch = fetchMock;

    render(<HealthStatus />);

    await waitFor(() => {
      expect(screen.getByTestId("status-ok")).toBeInTheDocument();
    });

    const recheckBtn = screen.getByRole("button", {
      name: /recheck backend health/i,
    });
    await act(async () => {
      fireEvent.click(recheckBtn);
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
