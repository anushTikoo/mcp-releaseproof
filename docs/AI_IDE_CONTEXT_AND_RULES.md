# AI IDE Context and Operating Rules

This document is the primary instruction source for any AI coding IDE working on MCP ReleaseProof.

## 1. Product identity

Build **MCP ReleaseProof**, a web-based, AI-assisted security release-verification platform for Model Context Protocol (MCP) servers.

The developer submits:
- A public GitHub repository URL.
- A baseline Git ref (tag, branch, or commit).
- A candidate Git ref.
- An optional startup command override.

The application compares the two versions by running generated MCP interaction tests in isolated Vultr-hosted execution environments and collecting runtime evidence.

## 2. Non-negotiable instruction: do not assume missing information

Do not invent, guess, fabricate, or silently assume any of the following:

- Vultr account identifiers, API keys, VM IDs, regions, IP addresses, firewall IDs, VPC IDs, SSH keys, server sizes, or billing configuration.
- Vultr Serverless Inference model IDs, subscription state, API key values, rate limits, or account entitlements.
- GitHub usernames, repository names, tokens, commit SHAs, branch names, or permissions.
- Hostnames, DNS records, TLS certificates, ports already open, or public URLs.
- Database credentials, Redis passwords, worker secrets, storage credentials, or environment variable values.
- Whether a service is installed, running, reachable, or configured.
- Whether a security control works merely because configuration code exists.
- Whether a test passed if it did not execute successfully.

When required information is missing:
1. Explain exactly what information or manual action is required.
2. Ask the user for the missing value or ask them to perform the manual step.
3. State where the value should be obtained (for example, Vultr console, Serverless Inference dashboard, DNS provider, or local terminal).
4. Provide the exact environment variable name or configuration field.
5. Never ask the user to paste secrets into chat if they can place them in a local `.env` file instead.
6. Use placeholders in documentation and `.env.example`, never real secrets.

Do not continue by substituting a guessed value or fake service.

## 3. No fake integrations

Do not:
- Replace Vultr Serverless Inference with a local model or another provider without explicit approval.
- Replace Docker execution with simulated logs.
- Replace MCP protocol calls with hardcoded example responses.
- Replace host-observed network enforcement with a frontend animation or a fabricated event.
- Mark a scan as passed when build, execution, telemetry, or evidence collection failed.
- Populate the dashboard with fabricated scan metrics and present them as real customer activity.

Mocks may be used in isolated unit tests and must be clearly labelled as test fixtures. The end-to-end product and demo must use real services.

## 4. Project boundaries

Initial supported profile:
- Public GitHub repositories only.
- Python MCP servers only.
- MCP stdio transport only.
- Two versions: baseline and candidate.
- Separate disposable containers for each version.
- A constrained generated Python test harness.
- Host-side telemetry for the supported signals.
- Real egress-denial enforcement for the containment demonstration.

Do not silently expand this scope.

## 5. Security rules

- Submitted repository code is untrusted.
- Never run repository code on the control-plane host.
- Never put application secrets into the target container.
- Never mount `/var/run/docker.sock` into the target container.
- Never run target containers as privileged.
- Never use host networking for target containers.
- Never give target containers access to worker control APIs or internal metadata services.
- Default-deny outbound network access at runtime.
- Keep build-time dependency downloads separate from runtime execution.
- Apply CPU, memory, PID, and wall-clock limits.
- Destroy containers and temporary writable volumes after every run.
- Host-side monitoring and enforcement must remain outside the target container.
- Record raw evidence with timestamps and correlation IDs.
- Be explicit about unsupported scenarios and telemetry blind spots.

## 6. Secrets and environment configuration

- Commit `.env.example` only.
- `.env` must be ignored by Git.
- Never print secrets in logs.
- Never place secrets in frontend variables. Vite variables prefixed with `VITE_` are public.
- The Vultr inference key belongs only on the control plane.
- The worker should authenticate using a separately generated worker shared secret.
- The target MCP container receives neither secret.
- Ask the user to create and populate required secrets locally.

## 7. Infrastructure assumptions are prohibited

Do not assume Vultr resources already exist. Before deployment, verify:
- Control-plane VM exists and is reachable.
- Worker VM exists and is reachable.
- OS and Docker versions are known.
- Firewall rules are configured and verified.
- Worker-to-control-plane connectivity works.
- DNS and HTTPS configuration exist if a public hostname is required.
- Vultr Serverless Inference key and selected model are available.
- PostgreSQL and Redis are reachable.
- Disk space and VM resource capacity are sufficient.

If any check fails, stop and report the exact blocker.

## 8. Technical quality

- Prefer typed request/response schemas.
- Use structured logs.
- Use explicit scan state transitions.
- Use idempotent worker job handling.
- Add timeouts and bounded retries.
- Validate all external input.
- Keep API, orchestration, inference, sandboxing, telemetry, and report generation separate.
- Add tests for failure paths, not only happy paths.
- Do not add unnecessary infrastructure or dependencies.
- Keep README and technical documentation aligned with actual implementation.

## 9. Evidence and verdict integrity

Every finding must distinguish:
- Observed fact.
- Inference or interpretation.
- Enforcement result.
- Evidence source.
- Confidence or limitation.

The model may explain evidence, but deterministic code computes the release verdict. The model must not invent event IDs, timestamps, network destinations, file paths, or successful containment.

A blocked attempt is still a finding. A blocked action is not the same as no attempted action.

## 10. Working agreement

Treat this context pack as the product specification. If code and documentation conflict, identify the conflict rather than silently choosing one. If a requested change would weaken isolation or contradict the product boundaries, explain the risk and request confirmation before proceeding.
