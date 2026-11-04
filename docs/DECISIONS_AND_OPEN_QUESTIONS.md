# Decisions and Open Questions

## Decisions

### Product
- Name: MCP ReleaseProof.
- Product type: web-based MCP release-verification platform.
- Main workflow: compare baseline and candidate versions.
- Differentiation hypothesis: evidence-backed runtime release verification.

### Scope
- Public GitHub repositories only.
- Python only.
- stdio transport only.
- Two versions per scan.
- AI-generated constrained Python test harness.
- Disposable Docker containers.
- Host-side telemetry and runtime egress enforcement.
- JSON report.

### Stack
- React + Vite + TypeScript.
- FastAPI.
- Vultr Serverless Inference.
- Official MCP Python SDK.
- Docker on Vultr Compute.
- PostgreSQL.
- Redis.
- WebSocket or SSE progress stream.

### Infrastructure
Preferred:
- One control-plane VM.
- One sandbox-worker VM.
- No secrets inside target container.
- Inference key only on control plane.

## Open questions that must not be guessed

1. Which Vultr region will be used?
2. What control-plane VM plan and OS will be provisioned?
3. What worker VM plan and OS will be provisioned?
4. Is the Vultr Serverless Inference subscription active?
5. Which current model ID will be selected?
6. Has the inference API key been created?
7. Will PostgreSQL and Redis run on the control-plane VM or use separate services?
8. Will a domain name be used for public HTTPS?
9. Which host firewall implementation is available on the selected worker OS?
10. Which host-side file/process monitoring mechanism can be reliably validated?
11. Will artifacts remain on local persistent storage or use Vultr Object Storage?
12. What are the actual deployment IPs, ports and firewall rules?

## Risks

- MCP server build compatibility is limited.
- Dependency installation is itself untrusted.
- Docker is not an absolute security boundary.
- Host telemetry may be incomplete on some OS configurations.
- Generated tests may not discover all malicious behaviour.
- The candidate fixture may overfit the demo if not tested against meaningful scenarios.
- Inference output may be malformed or unsafe; validation is mandatory.
- Network policy misconfiguration can invalidate the containment demonstration.

## Product claims to avoid

Do not claim:
- "We prove an MCP server is safe."
- "We support every MCP server."
- "Docker makes escape impossible."
- "Our technology is the first MCP dynamic scanner."
- "All malicious behaviour is detected."
- "A blocked action means the server did not attempt it."

## Preferred language

Use:
- "Evidence-backed runtime verification."
- "Observed behaviour under configured test scenarios."
- "Attempted action blocked by host-enforced policy."
- "Coverage limitations."
- "Release risk assessment."
