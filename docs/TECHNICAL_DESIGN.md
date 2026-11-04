# Technical Design

## Repository and version ingestion

Input:
- Public GitHub HTTPS repository URL.
- Baseline ref.
- Candidate ref.

Requirements:
- Validate host is `github.com`.
- Reject arbitrary URL schemes and local paths.
- Resolve refs to immutable commit SHAs.
- Record repository URL, refs, SHAs, timestamps, and source hashes.
- Do not execute repository code during ingestion.
- Use bounded clone/fetch operations and timeouts.
- Do not support private repositories in the initial product.

## Build profile

Initial profile:
- Python only.
- Detect `pyproject.toml`, `requirements.txt`, or a documented supported layout.
- Prefer lockfiles and pinned dependencies.
- Require explicit startup command if auto-detection is ambiguous.
- Build in a separate disposable environment.
- Build-time dependency installation is untrusted and must be isolated.
- Record dependency versions and build logs.
- Runtime network policy must be stricter than build-time policy.
- Unsupported build profiles return `UNSUPPORTED_BUILD`.

Do not claim arbitrary Python repository compatibility.

## MCP discovery

Use the official MCP Python SDK as the client implementation.

For stdio:
- Launch the MCP server only within the target execution boundary.
- Connect through stdio transport.
- Request server/tool metadata.
- Record tool name, description, input schema, and protocol metadata.
- Call only tools accepted by the validated test plan.
- Apply per-call and total-call timeouts.
- Record request and response with sensitive data redaction.

The application must not assume every server implements optional MCP capabilities.

## Test plan and harness generation

The model receives:
- Repository summary.
- Tool inventory.
- Input schemas.
- Version diff.
- Supported test objectives.
- Explicit safety constraints.
- Available synthetic resources.

The model returns structured JSON and generated Python source.

Validation:
- Parse JSON against a strict schema.
- Reject unknown tools.
- Validate arguments against tool schemas.
- Limit number of scenarios and calls.
- Parse generated Python with AST.
- Restrict imports and syntax to the approved harness API.
- Reject shell, process, arbitrary network, arbitrary file, dynamic import, eval/exec, and reflection capabilities in generated harness code.
- Execute inside the target sandbox regardless of validation.

The generated harness should use a fixed helper library. The helper exposes only MCP connection, list tools, call tool, record event, assertion, and scenario result functions.

## Runtime execution

Baseline and candidate:
- Separate container IDs.
- Separate writable layers and temporary directories.
- Separate synthetic canary values.
- Same scenario intent where compatible.
- Resource limits and wall-clock timeout.
- Non-root execution.
- Read-only root filesystem where practical.
- Dropped capabilities.
- `no-new-privileges`.
- No Docker socket.
- No host networking.
- Default-deny runtime egress.
- Always cleanup containers and volumes.

## Telemetry

MVP telemetry:
- MCP tool calls and results from the test client.
- Docker lifecycle events.
- Container CPU/memory usage.
- Process creation/exit events where validated.
- Outbound connection attempts and firewall verdicts.
- Canary-file access only if host-side audit has been validated.

Each event:
- `event_id`
- `scan_id`
- `job_id`
- `version`
- `scenario_id` if known
- `timestamp_utc`
- `event_type`
- `source`
- `payload`
- `correlation_id`

Telemetry sources must be identified. Do not label application-generated logs as host-observed events.

## Evidence correlation

Correlate using:
- Scan ID.
- Job ID.
- Scenario ID.
- Test-step ID.
- MCP call ID.
- Container ID.
- Process identity/cgroup where available.
- Timestamps.

Correlation should preserve uncertainty. If an OS event cannot be linked confidently to a tool call, mark it as uncorrelated rather than guessing.

## Deterministic verdict

The verdict engine consumes validated findings and coverage data. It does not ask the LLM to decide whether the release is safe.

Suggested states:
- PASS
- WARNING
- BLOCK
- INCOMPLETE

A blocked outbound attempt remains a finding. The action was contained, but the attempt occurred.

## Artifact handling

Artifacts include:
- Build logs.
- Generated test plan.
- Generated harness source.
- Harness validation result.
- MCP interaction records.
- Host telemetry.
- Firewall logs.
- Final report.

Use scan-scoped directories and generated IDs. Do not use user-controlled filenames directly. Apply retention and size limits.
