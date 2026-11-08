import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SandboxExecutor } from "./SandboxExecutor";
import * as client from "../api/client";

const mockSuccessResult: client.SandboxExecutionResult = {
  job_id: "job-test-1234",
  repository_url: "https://github.com/modelcontextprotocol/servers",
  commit_sha: "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
  lifecycle_status: "COMPLETED",
  test_verdict: "PASSED",
  security_status: "VERIFIED",
  cleanup_status: "VERIFIED_CLEAN",
  verification_verdict: "VERIFIED_SUCCESS",
  exit_code: 0,
  stdout: "===== 2 passed in 0.12s =====",
  stderr: "",
  duration_ms: 125.4,
  start_time: "2026-11-09T01:00:00Z",
  end_time: "2026-11-09T01:00:01Z",
  security_report: {
    overall_status: "VERIFIED",
    summary: "All mandatory security containment controls independently verified in running container.",
    controls: [
      {
        control_name: "non_root_user",
        requested: "10001:10001",
        observed: "10001:10001",
        status: "VERIFIED",
        details: "Container must execute under unprivileged UID 10001",
      },
      {
        control_name: "network_isolation",
        requested: "network=none",
        observed: "network=none",
        status: "VERIFIED",
        details: "Network access during runtime must be default-deny",
      },
      {
        control_name: "read_only_rootfs",
        requested: "read_only=true",
        observed: "read_only=true",
        status: "VERIFIED",
        details: "Root filesystem must be mounted read-only",
      },
    ],
  },
  cleanup_details: "Container and ephemeral workspace removed cleanly.",
};

describe("SandboxExecutor Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the execute button and description", () => {
    render(
      <SandboxExecutor
        repositoryUrl="https://github.com/modelcontextprotocol/servers"
        commitSha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        harnessCode="import pytest\ndef test_fn(): pass\n"
      />
    );

    expect(screen.getByTestId("execute-sandbox-btn")).toBeInTheDocument();
    expect(screen.getByText("Vultr Compute Sandbox Execution")).toBeInTheDocument();
  });

  it("disables button when harnessCode is empty", () => {
    render(
      <SandboxExecutor
        repositoryUrl="https://github.com/modelcontextprotocol/servers"
        commitSha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        harnessCode=""
      />
    );

    const btn = screen.getByTestId("execute-sandbox-btn");
    expect(btn).toBeDisabled();
  });

  it("triggers execution and displays VERIFIED_SUCCESS results", async () => {
    const executeSpy = vi
      .spyOn(client, "executeHarnessInSandbox")
      .mockResolvedValueOnce(mockSuccessResult);

    render(
      <SandboxExecutor
        repositoryUrl="https://github.com/modelcontextprotocol/servers"
        commitSha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        harnessCode="import pytest\ndef test_fn(): pass\n"
      />
    );

    const btn = screen.getByTestId("execute-sandbox-btn");
    fireEvent.click(btn);

    await waitFor(() => {
      expect(screen.getByTestId("verification-banner")).toBeInTheDocument();
    });

    expect(executeSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        repository_url: "https://github.com/modelcontextprotocol/servers",
        commit_sha: "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
      })
    );

    expect(screen.getByTestId("verification-banner")).toHaveTextContent("VERIFIED_SUCCESS");
    expect(screen.getByTestId("lifecycle-badge")).toHaveTextContent("COMPLETED");
    expect(screen.getByTestId("test-verdict-badge")).toHaveTextContent("PASSED");
    expect(screen.getByTestId("security-badge")).toHaveTextContent("VERIFIED");
    expect(screen.getByTestId("cleanup-badge")).toHaveTextContent("VERIFIED_CLEAN");
  });

  it("displays regression detected banner when test verdict is FAILED", async () => {
    const failedResult: client.SandboxExecutionResult = {
      ...mockSuccessResult,
      test_verdict: "FAILED",
      verification_verdict: "REGRESSION_DETECTED",
      exit_code: 1,
      stdout: "1 failed",
    };

    vi.spyOn(client, "executeHarnessInSandbox").mockResolvedValueOnce(failedResult);

    render(
      <SandboxExecutor
        repositoryUrl="https://github.com/modelcontextprotocol/servers"
        commitSha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        harnessCode="import pytest\ndef test_fn(): pass\n"
      />
    );

    fireEvent.click(screen.getByTestId("execute-sandbox-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("verification-banner")).toBeInTheDocument();
    });

    expect(screen.getByTestId("verification-banner")).toHaveTextContent("REGRESSION_DETECTED");
    expect(screen.getByTestId("test-verdict-badge")).toHaveTextContent("FAILED");
  });

  it("toggles between stdout, stderr, and security evidence tabs", async () => {
    vi.spyOn(client, "executeHarnessInSandbox").mockResolvedValueOnce(mockSuccessResult);

    render(
      <SandboxExecutor
        repositoryUrl="https://github.com/modelcontextprotocol/servers"
        commitSha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        harnessCode="import pytest\ndef test_fn(): pass\n"
      />
    );

    fireEvent.click(screen.getByTestId("execute-sandbox-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("stdout-panel")).toBeInTheDocument();
    });

    expect(screen.getByTestId("stdout-panel")).toHaveTextContent("2 passed in 0.12s");

    // Click stderr tab
    fireEvent.click(screen.getByTestId("tab-stderr"));
    expect(screen.getByTestId("stderr-panel")).toBeInTheDocument();

    // Click security tab
    fireEvent.click(screen.getByTestId("tab-security"));
    expect(screen.getByTestId("security-panel")).toBeInTheDocument();
    expect(screen.getByTestId("security-control-non_root_user")).toBeInTheDocument();
    expect(screen.getByTestId("security-control-network_isolation")).toBeInTheDocument();
  });
});
