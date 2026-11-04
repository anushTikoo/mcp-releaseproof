# MCP ReleaseProof

AI-assisted, sandboxed release verification for Model Context Protocol (MCP) servers.

> **Product promise:** Execute an MCP server, test its behaviour, observe what it actually does, and produce reproducible evidence before a developer releases a new version.

## What it does

A developer submits a public GitHub repository and two refs: a baseline release and a candidate release. ReleaseProof:

1. Resolves and downloads both versions.
2. Builds supported Python MCP servers in isolated environments.
3. Discovers their MCP tools and input schemas.
4. Uses Vultr Serverless Inference to generate a constrained, executable Python test harness.
5. Runs the baseline and candidate in separate disposable Docker containers on Vultr Compute.
6. Collects MCP interaction records and host-observed runtime telemetry.
7. Compares behaviour and produces an evidence-backed release verdict.

The MVP focuses on Python MCP servers using stdio transport. It does not claim to prove that a server is completely safe.

## Hackathon fit

The project targets **Vultr Agent Rush — Challenge 1: Blast Radius Zero**, using Pattern A: sandboxed code execution. The model must generate executable code, that code must run in a Vultr-hosted sandbox, and actual results must return to the application. The product is a web application, not a chat-only demo.

Official event pages:
- https://community.vultr.com/e/vultr-agent-rush-hackathon
- https://lablab.build/ai-hackathons/vultr-hackathon

## Technology

- Frontend: React, Vite, TypeScript
- Backend/control plane: Python, FastAPI
- AI: Vultr Serverless Inference
- MCP: Official MCP Python SDK
- Execution: Docker on Vultr Compute
- Database: PostgreSQL
- Queue: Redis
- Live updates: WebSockets or Server-Sent Events
- Artifacts: local persistent storage initially; Vultr Object Storage is optional

## Start here

Read these documents in order:

1. `docs/AI_IDE_CONTEXT_AND_RULES.md`
2. `docs/PROJECT_BRIEF.md`
3. `docs/PRODUCT_SPECIFICATION.md`
4. `docs/ARCHITECTURE.md`
5. `docs/TECHNICAL_DESIGN.md`
6. `docs/VULTR_INFRASTRUCTURE_AND_DEPLOYMENT.md`
7. `docs/ENVIRONMENT_AND_SECRETS.md`
8. `docs/SANDBOX_SECURITY_MODEL.md`
9. `docs/API_CONTRACT.md`
10. `docs/DATA_MODEL.md`
11. `docs/AI_INFERENCE_DESIGN.md`
12. `docs/TESTING_AND_ACCEPTANCE.md`
13. `docs/DEMO_AND_PRESENTATION.md`
14. `docs/HACKATHON_REQUIREMENTS.md`
15. `docs/DECISIONS_AND_OPEN_QUESTIONS.md`

## Important security and implementation boundaries

- Never execute submitted repository code on the control-plane VM.
- Never put the Vultr inference key, database credentials, GitHub credentials, or worker shared secret inside an untrusted sandbox.
- Never mount the Docker socket inside an untrusted container.
- Do not treat AST validation as a sandbox. It is only an additional restriction on generated test code.
- Do not claim a containment event unless the host-side enforcement and evidence actually show it.
- Do not treat a failed or unsupported scan as a pass.
- Do not silently substitute mocked output for real Vultr inference, MCP execution, Docker execution, or telemetry.
- The initial MVP accepts public GitHub repositories only and supports Python + stdio only.

## Status

This repository is a product specification and engineering context pack. It is not a claim that the application has already been implemented.
