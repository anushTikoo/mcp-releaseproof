# Data Model

Use PostgreSQL. UUID primary keys are recommended. Store structured event payloads as JSONB.

## scans

- `id` UUID primary key
- `repository_url` TEXT
- `repository_owner` TEXT
- `repository_name` TEXT
- `baseline_ref` TEXT
- `candidate_ref` TEXT
- `baseline_sha` TEXT nullable until resolved
- `candidate_sha` TEXT nullable until resolved
- `transport` TEXT
- `test_profile` TEXT
- `status` TEXT
- `verdict` TEXT nullable
- `created_at` TIMESTAMPTZ
- `started_at` TIMESTAMPTZ nullable
- `completed_at` TIMESTAMPTZ nullable
- `failure_code` TEXT nullable
- `failure_message` TEXT nullable

## jobs

- `id` UUID primary key
- `scan_id` UUID foreign key
- `version_label` TEXT (`baseline` or `candidate`)
- `status` TEXT
- `worker_id` TEXT nullable
- `lease_expires_at` TIMESTAMPTZ nullable
- `started_at` TIMESTAMPTZ nullable
- `completed_at` TIMESTAMPTZ nullable
- `container_id` TEXT nullable
- `exit_code` INTEGER nullable

## discovered_tools

- `id` UUID primary key
- `scan_id` UUID foreign key
- `version_label` TEXT
- `tool_name` TEXT
- `description` TEXT
- `input_schema` JSONB
- `schema_hash` TEXT
- `discovered_at` TIMESTAMPTZ

## test_scenarios

- `id` UUID primary key
- `scan_id` UUID foreign key
- `scenario_key` TEXT
- `title` TEXT
- `objective` TEXT
- `scenario_json` JSONB
- `generated_code_artifact` TEXT nullable
- `validation_status` TEXT
- `created_at` TIMESTAMPTZ

## test_steps

- `id` UUID primary key
- `scenario_id` UUID foreign key
- `step_index` INTEGER
- `tool_name` TEXT
- `arguments_redacted` JSONB
- `status` TEXT
- `result_reference` TEXT nullable
- `started_at` TIMESTAMPTZ nullable
- `completed_at` TIMESTAMPTZ nullable

## events

- `id` UUID primary key
- `scan_id` UUID foreign key
- `job_id` UUID nullable
- `scenario_id` UUID nullable
- `timestamp` TIMESTAMPTZ
- `event_type` TEXT
- `source` TEXT
- `severity` TEXT nullable
- `correlation_id` TEXT nullable
- `payload` JSONB

## findings

- `id` UUID primary key
- `scan_id` UUID foreign key
- `scenario_id` UUID nullable
- `severity` TEXT
- `title` TEXT
- `description` TEXT
- `version_label` TEXT
- `triggering_tool` TEXT nullable
- `enforcement` TEXT (`blocked`, `allowed`, `unknown`, `not_applicable`)
- `evidence_event_ids` JSONB
- `created_at` TIMESTAMPTZ

## artifacts

- `id` UUID primary key
- `scan_id` UUID foreign key
- `job_id` UUID nullable
- `artifact_type` TEXT
- `storage_key` TEXT
- `sha256` TEXT
- `size_bytes` BIGINT
- `created_at` TIMESTAMPTZ

## Data handling

- Never store production credentials.
- Redact secrets and sensitive tool arguments.
- Set retention limits for source checkouts and artifacts.
- Store artifact hashes to detect accidental modification.
- Do not expose raw host paths to frontend users.
- Apply per-scan size limits.
