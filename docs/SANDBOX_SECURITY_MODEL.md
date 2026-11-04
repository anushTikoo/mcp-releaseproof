# Sandbox Security Model

## Purpose

The sandbox is the core containment boundary. Submitted repositories and generated harnesses are untrusted. The control plane and worker host are trusted infrastructure; the target container is not.

## Threat model

Potentially hostile behaviour:
- Reading synthetic files outside the intended application directory.
- Attempting to read environment variables.
- Starting unexpected subprocesses.
- Consuming CPU, memory, disk, or PIDs.
- Attempting outbound network connections.
- Attempting access to internal services.
- Exploiting build scripts or dependency installation.
- Attempting to tamper with logs or evidence.
- Attempting to escape container restrictions.

## Trust zones

1. Browser: untrusted client.
2. Control plane: trusted application services and secrets.
3. Worker host: trusted execution infrastructure and host-side observer.
4. Target container: untrusted submitted MCP server and generated harness.
5. External network: denied by default during runtime.

## Required controls

### Container
- Non-root UID.
- `--cap-drop=ALL`.
- `no-new-privileges`.
- CPU, memory and PID limits.
- Wall-clock timeout.
- Read-only root filesystem where practical.
- Small tmpfs or explicitly mounted temporary writable directory.
- No Docker socket.
- No privileged mode.
- No host PID, IPC, or network namespaces.
- No host SSH keys or control-plane mounts.
- No application secrets.
- No access to worker control API.
- Unique container and volume per execution.

### Network
- Default-deny egress during runtime.
- No host networking.
- No access to cloud metadata endpoints.
- No access to control-plane database or Redis.
- Explicit allowlist only where required.
- Enforce from the host/network boundary, not from code inside the target container.
- Capture actual firewall verdicts.
- Test the policy from inside the container before relying on it.

### Build stage
Dependency installation may execute arbitrary scripts. Build must be isolated separately from runtime. If package registry access is needed, restrict it to known registries and record the exception. Never reuse the build container as the final runtime container.

### Secrets
- Inference key stays on control plane.
- Database and Redis credentials stay on control plane.
- Worker shared secret is only used by worker agent to authenticate to control plane.
- Target container gets no application secrets.
- Use synthetic canary strings and fake customer records.

## Telemetry

MVP:
- MCP calls/results from client.
- Docker events.
- CPU/memory stats.
- Process creation/exit if host monitor is validated.
- Firewall connection attempts and verdicts.
- File access only if host-side audit is validated.

A log line emitted by the target server is not independent evidence. Label event sources accurately.

## Canary demonstration

Use a synthetic canary file with a unique random per-run value. Do not use a real credential. Place it only in the controlled test filesystem. Monitor access from outside the target container.

The demo candidate may attempt a sequence-dependent read and outbound transmission. The outbound attempt must be blocked by a verified host-level policy. The application should show the matching firewall event.

## Cleanup

After each job:
- Stop target processes.
- Remove containers.
- Remove writable layers and per-run volumes.
- Remove temporary repository checkouts according to retention policy.
- Preserve only approved logs and evidence artifacts.
- Verify cleanup even after worker crash or timeout.

## Honest claims

Do not call Docker an unbreakable sandbox. State that the MVP demonstrates specific containment controls and that container isolation does not eliminate kernel escape risk. A passing test means only that configured tests did not observe a policy violation.
