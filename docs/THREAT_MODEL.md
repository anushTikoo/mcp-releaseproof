# Threat Model

## Assets to protect

- Vultr inference API key.
- Database credentials and scan records.
- Worker authentication secret.
- Control-plane integrity.
- Worker host integrity.
- Other tenants' or users' scan data if multi-user support is added.
- Evidence integrity.
- Availability and cost budget.

## Adversaries and untrusted inputs

- Malicious MCP repository author.
- Compromised package/dependency.
- Malicious tool description or README containing prompt injection.
- Malicious MCP tool response.
- Malicious generated harness output.
- Accidental infinite loop or resource exhaustion.
- External network endpoint contacted by target code.

## Trust assumptions

- Vultr infrastructure and host OS are trusted for this project.
- Control-plane services are trusted but must be hardened.
- Submitted source, dependency install scripts, server process, tool descriptions, tool results, and generated code are untrusted.
- Host telemetry is only trusted after its collection path has been validated.

## Attack paths and mitigations

### Prompt injection through repository content
Mitigations:
- Treat repository content as data.
- Do not let it override system instructions.
- No secrets in model context unless strictly required (none are required).
- Validate model output.

### Malicious generated code
Mitigations:
- Strict harness API.
- AST validation.
- No arbitrary shell or process access.
- Execute only inside sandbox.
- Resource limits.

### Container escape
Mitigations:
- Non-root.
- Dropped capabilities.
- No privileged mode.
- No Docker socket.
- Patched host kernel and Docker.
- Separate worker VM.
- Consider stronger isolation runtime only if actually configured and validated.

Residual risk remains.

### Network exfiltration
Mitigations:
- Runtime egress deny.
- Host-level firewall enforcement.
- No secrets in container.
- No cloud metadata access.
- Verify denial from the host logs.

### Resource exhaustion
Mitigations:
- CPU, memory, PID, disk and wall-clock limits.
- Job concurrency limit.
- Per-repository size limit.
- Worker cleanup.

### Evidence tampering
Mitigations:
- Host-side collection.
- Structured events.
- Timestamps and correlation IDs.
- Artifact hashes.
- Separate target and evidence storage.
- Do not trust target-generated logs as sole proof.

## Residual limitations

This is a hackathon MVP. It is not a certified malware analysis environment. Container isolation has kernel-level residual risk. Test coverage is finite. Results must be described as observed evidence, not a guarantee of safety.
