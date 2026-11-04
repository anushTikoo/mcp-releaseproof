# API Contract

Base path: `/api`

All request and response bodies use JSON unless otherwise stated. Exact schemas should be implemented with Pydantic models.

## Public endpoints

### POST `/api/scans`

Create a verification job.

Request:

```json
{
  "repository_url": "https://github.com/example/my-mcp-server",
  "baseline_ref": "v1.0.0",
  "candidate_ref": "v1.1.0",
  "startup_command": "uv run server.py",
  "transport": "stdio",
  "test_profile": "standard_sequence_aware"
}
```

Response `202 Accepted`:

```json
{
  "scan_id": "uuid",
  "status": "QUEUED",
  "created_at": "2026-11-04T12:00:00Z"
}
```

Validation:
- HTTPS GitHub URL only.
- Baseline and candidate refs required.
- Refs must be resolved and stored as commit SHAs.
- `transport` must be `stdio` in MVP.
- Reject shell metacharacters and unsupported startup command forms; prefer a structured executable/argument configuration over a shell string.

### GET `/api/scans/{scan_id}`

Returns scan metadata and current state.

### GET `/api/scans/{scan_id}/events`

Returns paginated event history.

### GET `/api/scans/{scan_id}/stream`

Streams progress via WebSocket or SSE. Choose one and document it consistently.

### GET `/api/scans/{scan_id}/results`

Returns comparison summary and verdict.

### GET `/api/scans/{scan_id}/findings`

Returns findings with evidence references.

### GET `/api/scans/{scan_id}/report`

Downloads a JSON report.

## Internal worker endpoints

These endpoints require worker authentication and must not be exposed as unauthenticated public operations.

### POST `/internal/worker/claim`

Worker requests a job. Use a lease to prevent duplicate active claims.

### POST `/internal/worker/{job_id}/heartbeat`

Worker extends its lease and reports current stage.

### POST `/internal/worker/{job_id}/events`

Worker submits structured events. Validate event size and schema.

### POST `/internal/worker/{job_id}/artifacts`

Worker uploads an artifact or metadata reference. Apply size limits and safe path handling.

### POST `/internal/worker/{job_id}/complete`

Worker submits final execution status and summary.

### POST `/internal/worker/{job_id}/fail`

Worker reports a structured failure. Failure must not be translated into PASS.

## Common error shape

```json
{
  "error": {
    "code": "UNSUPPORTED_BUILD",
    "message": "The repository does not match the supported Python build profile.",
    "details": {}
  }
}
```

## Error codes

- `INVALID_REPOSITORY_URL`
- `REF_NOT_FOUND`
- `UNSUPPORTED_LANGUAGE`
- `UNSUPPORTED_TRANSPORT`
- `UNSUPPORTED_BUILD`
- `BUILD_TIMEOUT`
- `MCP_STARTUP_FAILED`
- `TOOL_DISCOVERY_FAILED`
- `TEST_GENERATION_FAILED`
- `HARNESS_VALIDATION_FAILED`
- `SANDBOX_START_FAILED`
- `EXECUTION_TIMEOUT`
- `TELEMETRY_UNAVAILABLE`
- `WORKER_UNAVAILABLE`
- `ARTIFACT_UPLOAD_FAILED`
- `INTERNAL_ERROR`

## Security requirements

- Validate ownership and access for scan IDs if authentication is introduced.
- Rate-limit public scan creation.
- Limit repository size, build time, artifact size, and concurrent jobs.
- Worker endpoints require a dedicated secret or stronger service authentication.
- Never return environment variables or secrets in API responses.
- Never expose internal host paths or raw infrastructure credentials.
