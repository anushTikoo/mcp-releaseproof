# Vultr Agent Rush Hackathon Requirements

## Official event

Vultr Agent Rush Hackathon, Challenge 1: **Blast Radius Zero**.

Official pages:
- Vultr Community event: https://community.vultr.com/e/vultr-agent-rush-hackathon
- LabLab event: https://lablab.build/ai-hackathons/vultr-hackathon

The event page describes an online build period of 3–8 November 2026 and an on-site phase on 8 November 2026. Check the official pages for current status, deadlines, eligibility, and submission instructions because event details can change.

## Challenge requirement

Build a web-based agent that performs real work—writing and running code or operating a real browser—while actions are contained inside an isolated sandbox running on Vultr.

The challenge emphasizes:
- Real task execution, not chat-only responses.
- A system that plans work and dispatches it to isolated environments.
- Verifiable output.
- Containment-first architecture.

## Chosen pattern

**Pattern A: Sandboxed code execution.**

MCP ReleaseProof uses Vultr Serverless Inference to generate a constrained Python test harness. The generated code executes against a real MCP server inside a disposable sandbox on Vultr Compute. Actual execution results and telemetry return to the application.

Do not claim Pattern A compliance if the model only generates prose or a JSON plan and no model-generated code is executed.

## Deliverables listed on the event pages

- Public GitHub repository with setup and documentation.
- Backend deployed on a Vultr VM.
- LLM calls through Vultr Serverless Inference.
- Public demo URL with a product-style experience.
- Recorded demo video containing a real containment moment.
- Clear architecture and use-case explanation.
- LabLab submission with project title, short and long descriptions, technology/category tags, cover image, video presentation, slide presentation, hosting platform and application URL.

The official page says the Vultr integration should be explained in the public GitHub README, including services/infrastructure, backend/deployment architecture, use case, and real execution. Check the current LabLab submission form for any additional fields.

## Judging criteria

The event page lists four criteria:
1. Application of Technology — how effectively chosen models are integrated.
2. Presentation — clarity and effectiveness of the presentation.
3. Business Value — practical impact and fit into business areas.
4. Originality — uniqueness and creativity.

Do not assume fixed score weights unless the official current rules publish them.

## How ReleaseProof maps to the challenge

| Requirement | Project implementation |
|---|---|
| Web-based agent | React + Vite app |
| Real work | MCP server test execution |
| Pattern A | AI-generated executable Python harness |
| Vultr inference | Test planning, harness generation, evidence explanation |
| Vultr VM | Control-plane backend and sandbox worker |
| Isolation | Disposable Docker containers with host-enforced restrictions |
| Verifiable output | Tool calls, telemetry, event correlation and report |
| Containment moment | Real outbound connection attempt blocked by host policy |
| Public repo | This source repository |
| Public demo | Deployed app URL |
| Video | Recorded end-to-end workflow |

## Accuracy requirement

The project must distinguish implemented features from planned features. Do not claim that Docker is unbreakable, that all MCP servers are supported, or that a clean scan proves complete safety.

The hackathon pages are the authority for current participation and submission rules. This document summarizes the published challenge requirements and is not a replacement for reading the official rules.
