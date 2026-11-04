# User Flows

## Flow 1 — Create a release verification

1. User visits dashboard.
2. User clicks "Verify a release".
3. User enters public GitHub repository URL.
4. User enters baseline ref.
5. User enters candidate ref.
6. User optionally enters supported startup command.
7. User submits.
8. Backend validates and creates scan.
9. User is redirected to progress view.

## Flow 2 — Monitor execution

The page receives progress events:
- Repository validation.
- Ref resolution.
- Build.
- MCP startup.
- Tool discovery.
- Test generation.
- Harness validation.
- Baseline execution.
- Candidate execution.
- Telemetry collection.
- Evidence correlation.
- Verdict generation.

The UI must show failures and unsupported stages explicitly.

## Flow 3 — Inspect result

User sees:
- Verdict.
- Versions and SHAs.
- Scenario coverage.
- Findings.
- Tool/schema differences.
- Evidence timeline.

User opens a finding and sees exact evidence references and reproduction details.

## Flow 4 — Export

User downloads JSON report. The report includes coverage limitations and all relevant version identifiers.

## Empty and error states

- No scans: show an empty state and CTA.
- Invalid repository: explain why.
- Unsupported language: show unsupported profile.
- Build failure: show build log reference.
- Worker unavailable: show queue/worker failure.
- Telemetry unavailable: show INCOMPLETE, not PASS.
- Scan timeout: show timeout and cleanup state.
- Partial results: label them as partial.
