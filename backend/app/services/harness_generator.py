"""Pipeline for AI test harness generation and static security validation."""

import logging
import re
from typing import Optional

from app.schemas.harness import (
    GenerateHarnessRequest,
    GenerateHarnessResponse,
    HarnessMetadata,
)
from app.services.harness_validator import HarnessValidator
from app.services.vultr_client import VultrClient

logger = logging.getLogger(__name__)


def clean_python_code(code: str) -> str:
    """Strip markdown code block fences and trailing/leading whitespace."""
    cleaned = (code or "").strip()
    if cleaned.startswith("```python"):
        cleaned = cleaned[len("```python"):].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    return cleaned


class HarnessGenerator:
    """Coordinates Vultr inference code generation with static AST security validation."""

    def __init__(
        self,
        vultr_client: VultrClient,
        validator: Optional[HarnessValidator] = None,
    ):
        self.vultr_client = vultr_client
        self.validator = validator or HarnessValidator()

    async def generate_harness(
        self, request: GenerateHarnessRequest
    ) -> GenerateHarnessResponse:
        """Generate test harness code via Vultr and run static security validation."""
        inference_result = await self.vultr_client.generate_test_harness(
            repository_url=request.repository_url,
            commit_sha=request.commit_sha,
            tools=request.tools,
            test_plan=request.test_plan,
            ref=request.ref,
            server_name=request.server_name,
            model_id=request.model_id,
            max_tokens=request.max_tokens,
        )

        payload = inference_result["payload"]
        raw_code = payload.harness_code if payload else ""
        cleaned_code = clean_python_code(raw_code)

        # Run static AST security and structural validation
        validation = self.validator.validate(
            code=cleaned_code,
            tools=request.tools,
            test_plan=request.test_plan,
        )

        # Identify test functions count from AST
        test_func_matches = re.findall(
            r"^\s*(?:async\s+)?def\s+(test_\w+)\s*\(", cleaned_code, flags=re.MULTILINE
        )
        test_count = len(test_func_matches)

        # Derive ground-truth metadata strictly from AST validation
        known_tool_names = {t.tool_name for t in request.tools}
        verified_tools = [t for t in validation.identified_tool_calls if t in known_tool_names]
        verified_scenarios = list(validation.identified_scenarios)

        metadata = HarnessMetadata(
            test_count=test_count,
            scenarios_covered=verified_scenarios,
            tools_tested=list(dict.fromkeys(verified_tools)),
            framework="pytest-asyncio",
            summary=(
                payload.summary
                if payload and payload.summary
                else "Generated pytest-asyncio test harness"
            ),
        )

        # Validation status: 'success' if is_valid, 'rejected' if any security/structural checks failed
        status_verdict = "success" if validation.is_valid else "rejected"

        return GenerateHarnessResponse(
            status=status_verdict,
            repository_url=request.repository_url,
            commit_sha=request.commit_sha,
            model=inference_result.get("model", "qwen3.8-flash-next"),
            harness_code=cleaned_code,
            metadata=metadata,
            validation=validation,
            usage=inference_result.get("usage"),
            duration_ms=inference_result.get("duration_ms", 0.0),
        )
