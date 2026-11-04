import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { GitHubComparator } from "./GitHubComparator";

const MOCK_REPO_DATA = {
  owner: "example",
  name: "filesystem-mcp-server",
  full_name: "example/filesystem-mcp-server",
  description: "Secure filesystem MCP server implementation",
  html_url: "https://github.com/example/filesystem-mcp-server",
  default_branch: "main",
  stars_count: 1240,
  forks_count: 85,
  open_issues_count: 12,
  is_private: false,
};

const MOCK_BASELINE_COMMIT = {
  ref: "v0.1.0",
  sha: "1111111111111111111111111111111111111111",
  short_sha: "1111111",
  message: "feat: initial v0.1.0 release\n\nDetailed release notes.",
  author_name: "Release Bot",
  author_date: "2026-01-10T12:00:00Z",
  committer_name: "Release Bot",
  committed_at: "2026-01-10T12:00:00Z",
  html_url: "https://github.com/example/filesystem-mcp-server/commit/1111111111111111111111111111111111111111",
};

const MOCK_CANDIDATE_COMMIT = {
  ref: "v0.2.0",
  sha: "2222222222222222222222222222222222222222",
  short_sha: "2222222",
  message: "feat: update to v0.2.0 with security guards",
  author_name: "Security Lead",
  author_date: "2026-02-15T16:30:00Z",
  committer_name: "Security Lead",
  committed_at: "2026-02-15T16:30:00Z",
  html_url: "https://github.com/example/filesystem-mcp-server/commit/2222222222222222222222222222222222222222",
};

const MOCK_RESOLVE_RESPONSE = {
  status: "success",
  repository: MOCK_REPO_DATA,
  baseline: MOCK_BASELINE_COMMIT,
  candidate: MOCK_CANDIDATE_COMMIT,
  is_identical: false,
};

const MOCK_COMPARE_RESPONSE = {
  status: "success",
  repository: MOCK_REPO_DATA,
  baseline: MOCK_BASELINE_COMMIT,
  candidate: MOCK_CANDIDATE_COMMIT,
  comparison: {
    status: "ahead",
    ahead_by: 5,
    behind_by: 0,
    total_commits: 5,
    files_changed_count: 2,
    additions: 120,
    deletions: 15,
    is_identical: false,
    is_truncated: false,
    files: [
      {
        filename: "src/server.ts",
        status: "modified",
        additions: 100,
        deletions: 10,
        changes: 110,
        patch: "@@ -1,5 +1,7 @@\n+import { sanitizePath } from './security';\n const server = new Server();",
      },
      {
        filename: "src/security.ts",
        status: "added",
        additions: 20,
        deletions: 5,
        changes: 25,
        patch: "@@ -0,0 +1,20 @@\n+export function sanitizePath(p: string) { return p; }",
      },
    ],
  },
};

const MOCK_IDENTICAL_COMPARE_RESPONSE = {
  status: "success",
  repository: MOCK_REPO_DATA,
  baseline: { ...MOCK_BASELINE_COMMIT, ref: "main" },
  candidate: { ...MOCK_BASELINE_COMMIT, ref: "1111111" },
  comparison: {
    status: "identical",
    ahead_by: 0,
    behind_by: 0,
    total_commits: 0,
    files_changed_count: 0,
    additions: 0,
    deletions: 0,
    is_identical: true,
    is_truncated: false,
    files: [],
  },
};

describe("GitHubComparator Component", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("renders form elements with default values", () => {
    render(<GitHubComparator />);

    expect(screen.getByText("GitHub Version Comparison")).toBeInTheDocument();
    expect(screen.getByLabelText(/Public GitHub Repository URL/i)).toHaveValue(
      "https://github.com/example/filesystem-mcp-server"
    );
    expect(screen.getByLabelText(/Baseline Ref/i)).toHaveValue("v0.1.0");
    expect(screen.getByLabelText(/Candidate Ref/i)).toHaveValue("v0.2.0");
    expect(screen.getByTestId("compare-btn")).toBeInTheDocument();
    expect(screen.getByTestId("resolve-btn")).toBeInTheDocument();
  });

  it("validates repository URL on client-side without calling fetch", async () => {
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock;

    render(<GitHubComparator />);

    const urlInput = screen.getByLabelText(/Public GitHub Repository URL/i);
    fireEvent.change(urlInput, { target: { value: "http://insecure-domain.com/owner/repo" } });

    const compareBtn = screen.getByTestId("compare-btn");
    await act(async () => {
      fireEvent.click(compareBtn);
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByTestId("github-error-banner")).toBeInTheDocument();
    expect(
      screen.getByText(/Repository URL must be a valid public HTTPS GitHub repository URL/i)
    ).toBeInTheDocument();
  });

  it("validates missing baseline ref without calling fetch", async () => {
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock;

    render(<GitHubComparator />);

    const baselineInput = screen.getByLabelText(/Baseline Ref/i);
    fireEvent.change(baselineInput, { target: { value: "   " } });

    const resolveBtn = screen.getByTestId("resolve-btn");
    await act(async () => {
      fireEvent.click(resolveBtn);
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByTestId("github-error-banner")).toBeInTheDocument();
    expect(screen.getByText(/Baseline ref is required/i)).toBeInTheDocument();
  });

  it("successfully resolves refs and displays repository card and resolved commits", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/github/resolve")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_RESOLVE_RESPONSE,
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<GitHubComparator />);

    const resolveBtn = screen.getByTestId("resolve-btn");
    await act(async () => {
      fireEvent.click(resolveBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("repo-metadata")).toBeInTheDocument();
    });

    expect(screen.getByText("example/filesystem-mcp-server ↗")).toBeInTheDocument();
    expect(screen.getByText(/⭐ 1,240/)).toBeInTheDocument();
    expect(screen.getByText("1111111")).toBeInTheDocument();
    expect(screen.getByText("2222222")).toBeInTheDocument();
    expect(screen.getByText("feat: initial v0.1.0 release")).toBeInTheDocument();
    expect(screen.getByText("feat: update to v0.2.0 with security guards")).toBeInTheDocument();
  });

  it("successfully compares releases and displays comparison summary and diffs", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/github/compare")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_COMPARE_RESPONSE,
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<GitHubComparator />);

    const compareBtn = screen.getByTestId("compare-btn");
    await act(async () => {
      fireEvent.click(compareBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("comparison-results")).toBeInTheDocument();
    });

    expect(screen.getByText("Status: AHEAD")).toBeInTheDocument();
    expect(screen.getByText(/Ahead by 5, Behind by 0/i)).toBeInTheDocument();
    expect(screen.getByText("+120")).toBeInTheDocument();
    expect(screen.getByText("-15")).toBeInTheDocument();
    expect(screen.getByText("src/server.ts")).toBeInTheDocument();
    expect(screen.getByText("src/security.ts")).toBeInTheDocument();

    // Verify diff toggle
    const viewDiffButtons = screen.getAllByRole("button", { name: "View Diff" });
    expect(viewDiffButtons.length).toBe(2);

    await act(async () => {
      fireEvent.click(viewDiffButtons[0]);
    });

    expect(
      screen.getByText("+import { sanitizePath } from './security';")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide Diff" })).toBeInTheDocument();
  });

  it("displays identical banner when commits are identical", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/github/compare")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_IDENTICAL_COMPARE_RESPONSE,
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<GitHubComparator />);

    const compareBtn = screen.getByTestId("compare-btn");
    await act(async () => {
      fireEvent.click(compareBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("identical-banner")).toBeInTheDocument();
    });

    expect(screen.getByText("Commits are identical")).toBeInTheDocument();
    expect(screen.queryByText("Changed Files")).not.toBeInTheDocument();
  });

  it("renders structured error banner for REPOSITORY_NOT_FOUND (404)", async () => {
    globalThis.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: false,
        status: 404,
        statusText: "Not Found",
        json: async () => ({
          detail: {
            code: "REPOSITORY_NOT_FOUND",
            message: "Repository nonexistent/repo not found on GitHub or is private.",
          },
        }),
      })
    );

    render(<GitHubComparator />);

    const compareBtn = screen.getByTestId("compare-btn");
    await act(async () => {
      fireEvent.click(compareBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("github-error-banner")).toBeInTheDocument();
    });

    expect(screen.getByText("[REPOSITORY_NOT_FOUND]")).toBeInTheDocument();
    expect(
      screen.getByText("Repository nonexistent/repo not found on GitHub or is private.")
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Verify the repository exists, is public, and that owner\/repo spelling is correct/i)
    ).toBeInTheDocument();
  });

  it("renders rate limit error with suggestion for GITHUB_RATE_LIMITED (429)", async () => {
    globalThis.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: false,
        status: 429,
        statusText: "Too Many Requests",
        json: async () => ({
          detail: {
            code: "GITHUB_RATE_LIMITED",
            message: "GitHub API rate limit exceeded.",
          },
        }),
      })
    );

    render(<GitHubComparator />);

    const resolveBtn = screen.getByTestId("resolve-btn");
    await act(async () => {
      fireEvent.click(resolveBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("github-error-banner")).toBeInTheDocument();
    });

    expect(screen.getByText("[GITHUB_RATE_LIMITED]")).toBeInTheDocument();
    expect(
      screen.getByText(/Set a GITHUB_TOKEN in backend\/\.env for up to 5,000 requests\/hour/i)
    ).toBeInTheDocument();
  });

  it("copies commit sha to clipboard when copy button is clicked", async () => {
    const clipboardSpy = vi.fn();
    Object.assign(navigator, {
      clipboard: {
        writeText: clipboardSpy,
      },
    });

    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/github/resolve")) {
        return Promise.resolve({
          ok: true,
          json: async () => MOCK_RESOLVE_RESPONSE,
        });
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(<GitHubComparator />);

    const resolveBtn = screen.getByTestId("resolve-btn");
    await act(async () => {
      fireEvent.click(resolveBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("resolved-commits")).toBeInTheDocument();
    });

    const copyButtons = screen.getAllByTitle("Copy full SHA");
    expect(copyButtons.length).toBe(2);

    await act(async () => {
      fireEvent.click(copyButtons[0]);
    });

    expect(clipboardSpy).toHaveBeenCalledWith(MOCK_BASELINE_COMMIT.sha);
    expect(screen.getByText("Copied!")).toBeInTheDocument();
  });
});
