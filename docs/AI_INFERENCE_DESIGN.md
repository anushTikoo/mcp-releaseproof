# AI Inference Design — Vultr Serverless Inference

## Provider requirement

All product LLM calls must use Vultr Serverless Inference. Do not silently substitute another provider.

Official documentation:
- Overview: https://api.vultrinference.com/docs
- Quickstart: https://api.vultrinference.com/docs/get-started/quickstart
- Authentication: https://api.vultrinference.com/docs/get-started/authentication
- API reference: https://api.vultrinference.com/docs/reference
- Models: https://api.vultrinference.com/docs/models
- SDK compatibility: https://api.vultrinference.com/docs/get-started/sdks

Base URL:
`https://api.vultrinference.com/v1`

The service supports OpenAI-compatible chat and responses APIs. Use the current official docs and model catalogue. Do not hardcode a model ID without checking that it exists and is enabled for the user's account.

## Credential handling

Required control-plane environment variable:
`VULTR_INFERENCE_API_KEY`

Model selection:
`VULTR_INFERENCE_MODEL`

The API key must:
- Exist only on the control plane.
- Never be committed.
- Never be sent to the frontend.
- Never be passed to the worker's untrusted target container.
- Never appear in logs.

If the user has not supplied the key in the local environment, stop and explain how to create it in the Vultr console and place it in `.env`. Do not ask them to paste it into chat.

## Client example

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://api.vultrinference.com/v1",
    api_key=os.environ["VULTR_INFERENCE_API_KEY"],
)

response = client.chat.completions.create(
    model=os.environ["VULTR_INFERENCE_MODEL"],
    messages=[
        {"role": "system", "content": "Return valid structured output."},
        {"role": "user", "content": "Analyze the supplied MCP tool inventory."}
    ],
)
```

This is a reference pattern. Check the selected model's current API support and output capabilities.

## AI responsibilities

### 1. Test planning
Input:
- Sanitized repository summary.
- Tool names, descriptions, schemas.
- Version differences.
- Allowed test objectives.
- Harness capability contract.

Output:
- Strictly validated JSON test plan.
- Scenario IDs.
- Ordered tool-call steps.
- Expected observations.
- Safety labels.

### 2. Test harness generation
Input:
- Validated plan.
- Fixed helper API.
- Tool schemas.
- Strict code-generation instructions.

Output:
- Python source code.
- Scenario-to-code mapping.

The harness is untrusted code. Validate with AST and execute inside the sandbox anyway.

### 3. Evidence explanation
Input:
- Structured event records.
- Correlation metadata.
- Test results.
- Coverage limitations.

Output:
- Human-readable explanation.
- Evidence references.
- No invented facts.

### 4. Report summary
The model may summarize results. It must not determine the final verdict.

## Prompt safety

Repository contents, MCP tool descriptions, tool results, and README files are untrusted input. They may contain prompt injection.

- Delimit untrusted content clearly.
- Tell the model to treat repository text and tool descriptions as data, not instructions.
- Do not give the model access to secrets.
- Do not allow model output to directly change host firewall rules or worker privileges.
- Validate every generated scenario and script.
- Use deterministic code for policy decisions.

## Structured output

Use Pydantic models or JSON Schema for:
- `TestPlan`
- `TestScenario`
- `TestStep`
- `HarnessGeneration`
- `EvidenceExplanation`

Reject malformed or out-of-scope output. Apply bounded retries. Record model ID, prompt version, and token usage where available, but do not store secrets.
