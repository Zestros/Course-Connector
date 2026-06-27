"""Facade for the Course Connector LLM analysis layer."""

from __future__ import annotations

from typing import Any

from course_connector.llm_layer.config import LLMConfig
from course_connector.llm_layer.context import build_prompt_context
from course_connector.llm_layer.parsing.json_parser import parse_provider_response
from course_connector.llm_layer.parsing.relation_normalizer import (
    ALLOWED_RELATION_TYPES,
    normalize_relations,
)
from course_connector.llm_layer.prompts.renderer import build_prompt
from course_connector.llm_layer.providers.base import LLMProvider, LLMResponse
from course_connector.llm_layer.providers.factory import create_provider
from course_connector.llm_layer.providers.mock_provider import MockLLMProvider
from course_connector.llm_layer.providers.static_provider import StaticLLMProvider


def analyze_courses(
    input_payload: dict[str, Any],
    provider: LLMProvider | None = None,
    debug: bool = False,
    config: LLMConfig | None = None,
) -> dict[str, Any]:
    """Analyze prepared course inputs and return structured relation candidates."""
    config = config or LLMConfig.from_input_payload(input_payload)
    provider = provider or create_provider(config)
    context = build_prompt_context(input_payload)
    prompt = build_prompt(
        context,
        template_name=config.prompt_template,
        output_language=config.output_language,
    )
    response = provider.generate(prompt)
    analysis = parse_provider_response(response.text)
    analysis["warnings"] = [
        *list(input_payload.get("warnings") or []),
        *list(analysis.get("warnings") or []),
    ]
    analysis["relations"] = normalize_relations(analysis.get("relations") or [], analysis["warnings"])
    analysis["provider"] = response.metadata.get("provider", "unknown")
    analysis["provider_mode"] = response.metadata.get("mode", analysis["provider"])
    if debug or config.debug:
        analysis["raw_response"] = response.text
        analysis["prompt"] = prompt
    return analysis
