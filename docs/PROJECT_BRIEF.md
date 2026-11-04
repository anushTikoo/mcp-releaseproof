# Project Brief — MCP ReleaseProof

## Overview

MCP ReleaseProof is an AI-assisted security release-verification platform for MCP servers. It helps developers compare a known baseline version with a proposed candidate release by executing both under controlled conditions and collecting evidence of their runtime behaviour.

## Problem

MCP servers expose tools and capabilities to AI agents. They may interact with files, databases, APIs, and other services. Static source inspection and tool-schema inspection cannot establish every action a server will perform at runtime. Behaviour may depend on call order, arguments, persistent process state, environment, dependencies, or version changes.

Developers need a repeatable way to test a candidate release before approving it.

## Solution

ReleaseProof:
1. Accepts a public repository and two refs.
2. Resolves exact commit SHAs.
3. Builds supported versions in isolated build environments.
4. Starts each server in a disposable runtime container.
5. Discovers MCP tools and schemas.
6. Uses Vultr Serverless Inference to generate a constrained test plan and executable Python harness.
7. Runs the harness against both versions.
8. Collects MCP-level events and host-observed runtime telemetry.
9. Correlates the test sequence with observed behaviour.
10. Produces a version comparison and evidence-backed release verdict.

## Target users

### Primary
- MCP server maintainers and publishers.
- Developers building MCP integrations.
- AI platform teams approving third-party MCP servers.

### Secondary
- Application security teams.
- AI security engineers.
- Organizations maintaining internal MCP server registries.

## Core value proposition

"Execute it, test its behaviour, contain suspicious actions, and show exactly what happened before release."

## Differentiation hypothesis

The product is not claiming that sandboxing, fuzzing, MCP scanning, or runtime monitoring are new. The proposed product value is an integrated release-verification workflow that links:
- Version-specific test scenarios.
- Actual MCP tool interactions.
- Host-observed runtime events.
- Enforcement outcomes.
- Reproducible evidence.

This differentiation is a hypothesis and must not be represented as proven market uniqueness.

## Initial supported scope

- Public GitHub repository.
- Python MCP server.
- stdio transport.
- Baseline and candidate refs.
- Supported Python dependency installation profiles.
- MCP tool discovery.
- AI-generated constrained Python test harness.
- Separate Docker containers.
- Synthetic canary resources.
- Host-side process/container/network evidence.
- Version comparison and report.

## Out of scope initially

- Private repositories.
- Arbitrary languages.
- All MCP transports.
- Production credentials.
- Arbitrary remote MCP endpoints.
- Automated patching.
- Full CI/CD product.
- Enterprise SSO and billing.
- Claims of complete security or proof of absence of malicious behaviour.

## Product outcome

The developer receives:
- A clear PASS, WARNING, BLOCK, or INCOMPLETE result.
- The exact repository commit SHAs tested.
- Tool and schema differences.
- Test scenarios and execution status.
- Findings with evidence references.
- A chronological event timeline.
- A clear account of whether an action was allowed, blocked, or unknown.
- Explicit coverage limitations.
