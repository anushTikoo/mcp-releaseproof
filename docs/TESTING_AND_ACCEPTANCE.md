# Testing and Acceptance Criteria

## Testing principles

- A test must exercise the real component it claims to test.
- Unit-test mocks are allowed when clearly isolated.
- End-to-end acceptance must use real Vultr inference, Docker, MCP protocol execution, and host-side enforcement.
- A failure or missing telemetry must not become a pass.
- Every containment claim must have evidence from the enforcement layer.

## Unit tests

### Repository validation
- Reject non-GitHub URLs.
- Reject non-HTTPS URLs.
- Reject malformed refs.
- Resolve refs to commit SHAs.
- Handle missing refs and inaccessible repositories.

### Test-plan validation
- Reject unknown tool names.
- Reject invalid arguments.
- Reject unsupported scenario operations.
- Enforce scenario and tool-call limits.

### Harness validation
- Reject disallowed imports.
- Reject shell/process APIs.
- Reject `eval`, `exec`, dynamic imports, and arbitrary file/network access.
- Reject excessive loops or code size where detectable.
- Verify valid scripts still execute in the sandbox.

### Verdict engine
- Critical allowed action -> BLOCK according to policy.
- Suspicious blocked action -> WARNING according to policy.
- Missing required telemetry -> INCOMPLETE.
- Build failure -> INCOMPLETE/FAILED, never PASS.
- Clean completed run -> PASS only within stated coverage.

## Integration tests

- FastAPI creates scan record.
- Job queue accepts work.
- Worker claims a job.
- Worker heartbeat updates lease.
- Worker submits events.
- Worker completes or fails job.
- Frontend receives progress.
- Artifacts are retrievable.
- Database survives service restart.

## Security acceptance tests

1. Target container runs non-root.
2. Target container has no Docker socket.
3. Target container has no control-plane secrets.
4. Target container cannot access control-plane database or Redis.
5. Target container cannot reach external network during runtime.
6. Host firewall records denied connection attempt.
7. CPU, memory, PID and time limits are enforced.
8. Timeout causes cleanup.
9. Worker crash does not leave an untracked container.
10. Build stage is isolated from control plane.
11. Logs redact synthetic values if needed and never expose application secrets.

## End-to-end demo fixture

Maintain two owned test fixtures:
- Baseline version: normal behaviour.
- Candidate version: deliberate sequence-dependent test behaviour.

The candidate should:
- Behave normally for initial calls.
- Trigger a controlled canary access attempt after a known sequence.
- Attempt a controlled outbound connection.
- Be blocked by the host-enforced runtime egress policy.

The demo must show:
- Generated test code.
- Actual MCP calls.
- Actual candidate behaviour.
- Actual host-side blocked network event.
- Correlation to the scenario and version.
- Final verdict and evidence.

Do not rely on public third-party repositories for the deterministic demo.

## Definition of done

- Public GitHub repo can be submitted in UI.
- Baseline and candidate SHAs are recorded.
- MCP tools are discovered from the real server.
- Vultr inference generates executable test code.
- Generated code is validated and sandbox-executed.
- Both versions run in separate disposable containers.
- Host-observed telemetry is recorded.
- Egress denial is independently verified.
- Findings reference raw evidence.
- Verdict is deterministic.
- Report can be downloaded.
- Failure states are handled honestly.
