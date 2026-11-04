# Operations and Failure Handling

## Scan lifecycle

States:
- QUEUED
- INGESTING
- BUILDING
- DISCOVERING
- GENERATING_TESTS
- VALIDATING_HARNESS
- EXECUTING_BASELINE
- EXECUTING_CANDIDATE
- ANALYSING
- COMPLETED
- FAILED
- CANCELLED (optional)

A scan can be `COMPLETED` with a verdict of `WARNING`, `BLOCK`, or `INCOMPLETE`. Completion describes pipeline execution, not security status.

## Failure rules

- Repository not found: fail with `REF_NOT_FOUND`.
- Unsupported language: fail with `UNSUPPORTED_LANGUAGE`.
- Dependency install failure: fail or mark unsupported; never pass.
- MCP startup failure: fail.
- Tool discovery failure: fail.
- Inference failure: bounded retry, then fail.
- Invalid generated code: reject and bounded regenerate; never execute unvalidated output.
- Container timeout: terminate and cleanup.
- Telemetry failure: mark scan INCOMPLETE.
- Worker disappears: expire lease, inspect and cleanup orphan containers.
- Artifact upload failure: preserve status as incomplete/failure; do not discard silently.

## Worker reliability

- Worker claims jobs using a lease.
- Worker sends heartbeat.
- Each job has a unique ID and idempotency key.
- Duplicate completion events should be safe.
- Worker startup performs orphan cleanup based on ReleaseProof labels.
- Worker must never delete unrelated Docker resources.

## Logging

Use structured JSON logs. Include:
- timestamp
- service
- scan_id
- job_id
- stage
- event
- duration
- error_code

Never log secrets, full environment dumps, or sensitive user data.

## Resource limits

Enforce:
- Max repository size.
- Max build duration.
- Max scan duration.
- Max scenarios.
- Max tool calls.
- Max output bytes.
- Max artifact size.
- Max concurrent jobs per worker.

Actual values should be configurable and validated against available VM capacity; do not assume that one VM can handle unlimited parallel jobs.

## Cleanup

Use `finally`-style cleanup and worker startup reconciliation:
- Stop containers.
- Remove scan-specific containers.
- Remove scan-specific volumes.
- Remove temporary source directories according to retention policy.
- Preserve evidence artifacts.
- Record cleanup result.
