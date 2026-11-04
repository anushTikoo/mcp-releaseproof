# Demo and Presentation Plan

## Demo objective

Demonstrate this exact chain:

**Vultr inference generates executable tests → tests run against an MCP server in a Vultr-hosted sandbox → candidate attempts a suspicious action → host-enforced policy blocks it → ReleaseProof presents correlated evidence.**

The video must show a real product experience and one real containment moment.

## Demo fixture

Use an owned, deliberately vulnerable Python MCP server with two versions.

### Baseline
- Exposes `search_customer`.
- Exposes `export_report`.
- Behaves normally.

### Candidate
- Exposes equivalent normal tools.
- After a deterministic sequence of calls, attempts to access a synthetic canary resource.
- Attempts an outbound connection to a controlled test destination.
- The worker host's egress policy blocks the connection.

Do not use real customer data, real credentials, or real external targets. Do not claim the fixture represents a common real-world attack.

## 3–4 minute video storyboard

### 0:00–0:20 — Problem
Explain that source inspection alone does not establish runtime behaviour and that behaviour can depend on sequences of tool calls.

### 0:20–0:40 — Submit
Show the deployed web application.
Enter:
- Public GitHub repository.
- Baseline ref.
- Candidate ref.
- stdio profile.
Click Run Verification.

### 0:40–1:05 — AI-generated code
Show:
- MCP tool discovery.
- Tool schemas.
- Vultr inference test plan.
- Actual generated Python harness.
Explain that the generated code will execute, not merely be displayed.

### 1:05–1:30 — Isolated execution
Show separate baseline and candidate containers, runtime limits, and host-side monitoring.

### 1:30–2:05 — Containment moment
Show:
- Candidate sequence running.
- Actual outbound connection attempt.
- Host firewall denial event.
- Matching event in ReleaseProof.
Do not use a fake UI-only alert.

### 2:05–2:35 — Evidence report
Show:
- Baseline versus candidate.
- Scenario and triggering tool.
- Network destination.
- Enforcement result.
- Event timestamp and evidence reference.
- Release verdict.

### 2:35–3:05 — Architecture and close
Show the architecture and explain Vultr Serverless Inference and Vultr Compute roles.

## Suggested narration

"MCP servers give AI agents access to tools and external systems. But inspecting a server's source code does not tell us everything it will do at runtime.

MCP ReleaseProof lets a developer submit two versions of a server before release. Vultr Serverless Inference analyses the tools and generates an executable test harness.

Both versions run in separate disposable environments on Vultr Compute. ReleaseProof records the real MCP interactions and observes runtime activity from outside the target container.

Here the candidate behaves normally at first. After a specific sequence of tool calls, it attempts an outbound connection. The host-enforced network policy blocks that attempt, and ReleaseProof records the actual enforcement event.

The developer can now see which version changed, which sequence triggered the behaviour, what the server attempted, and whether the action was contained.

ReleaseProof turns MCP release security from a source-code guess into a reproducible runtime verification workflow."

## Recording checklist

- Use deployed public application.
- Use a successful pre-tested fixture.
- Show real generated code.
- Show real MCP calls.
- Show real host firewall evidence.
- Keep terminal text readable.
- Use real timestamps.
- Avoid showing secrets or API keys.
- Avoid long loading or installation sequences.
- Record a backup full run.
- Never fabricate dashboard counts or findings.

## Judge presentation structure

- Problem: 30 seconds.
- Product: 30 seconds.
- Demo: 2 minutes.
- Architecture/Vultr integration: 45 seconds.
- Business value: 30 seconds.
- Close: 15 seconds.

## Business framing

- MCP server publishers: verify releases before publishing.
- AI platform teams: test third-party servers before approving them.
- Security teams: retain reproducible runtime evidence.

Future integrations such as GitHub Actions and policy gates are roadmap items unless actually implemented.
