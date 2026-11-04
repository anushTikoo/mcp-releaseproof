# Product Specification

## Product name

MCP ReleaseProof

## Main user journey

1. User opens the web application.
2. User creates a release verification.
3. User enters a public GitHub URL.
4. User selects a baseline ref and candidate ref.
5. User optionally supplies a startup command override.
6. User submits the job.
7. The UI displays progress and events.
8. The user opens the completed result.
9. The user compares baseline and candidate.
10. The user inspects a finding and downloads the report.

## New verification form

Required:
- `repository_url`: HTTPS URL for a public GitHub repository.
- `baseline_ref`: Git tag, branch, or commit.
- `candidate_ref`: Git tag, branch, or commit.

Optional:
- `startup_command`: explicit supported startup command.
- `test_profile`: initially `standard_sequence_aware`; default may be selected by the application.
- `display_name`: user-friendly label.

Fixed in MVP:
- `transport`: `stdio`.
- `runtime`: Python.
- `repository_visibility`: public.

Do not ask users for production secrets. The application creates synthetic test values.

## Dashboard

Display actual stored data:
- Number of completed scans.
- Number of blocked releases.
- Number of warnings.
- Recent scans.
- Recent findings.

If no scans exist, show an empty state. Never display fake activity as if it were real.

## Scan progress page

Display state transitions:
- QUEUED
- INGESTING
- BUILDING
- DISCOVERING
- GENERATING_TESTS
- EXECUTING_BASELINE
- EXECUTING_CANDIDATE
- ANALYSING
- COMPLETED
- FAILED

Each progress event has timestamp, stage, message, and optional evidence reference.

## Results overview

Display:
- Repository and exact commit SHAs.
- Baseline and candidate refs.
- Completion state.
- Release verdict.
- Scenarios completed, failed, skipped, and unsupported.
- Findings by severity.
- Blocked and allowed actions.
- Build and execution errors.

## Comparison view

Compare:
- Tool names.
- Tool descriptions.
- Input schemas.
- Test scenario outcomes.
- Observed runtime events.
- Network attempts.
- Canary access observations.
- Resource use where available.

Do not infer that an unchanged schema means unchanged behaviour.

## Evidence timeline

Each event should include:
- Event ID.
- Scan ID.
- Job ID.
- Version.
- Scenario ID, if correlated.
- Timestamp.
- Event type.
- Source (MCP client, Docker, host firewall, host audit, etc.).
- Structured payload.
- Evidence integrity metadata where practical.

## Finding detail

A finding includes:
- Finding ID.
- Severity.
- Title.
- Summary.
- Version and commit.
- Triggering scenario.
- Triggering tool call, if known.
- Observed action.
- Enforcement result: `blocked`, `allowed`, `unknown`, or `not_applicable`.
- Evidence references.
- Reproduction instructions.
- Model-generated explanation clearly labelled as analysis.

## Verdict policy

Verdict is computed deterministically.

Suggested initial policy:
- `BLOCK`: at least one critical finding with an action observed as allowed, or a policy-defined critical behaviour.
- `WARNING`: suspicious behaviour was observed but successfully blocked, or high-severity findings exist.
- `INCOMPLETE`: a required build, test, or telemetry stage could not complete, or coverage was insufficient.
- `PASS`: all required scenarios completed and no configured policy finding was observed.

The exact policy must be visible in the report. A blocked attempt must never be silently treated as a clean pass.

## Report export

MVP:
- JSON report download.
- Human-readable report page.

Optional:
- PDF report.

Report includes repository metadata, refs and SHAs, environment profile, scenarios, execution status, raw event references, findings, verdict, limitations, and timestamps.
