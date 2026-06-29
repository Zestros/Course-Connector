"""Render prompt templates for LLM providers."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any


DEFAULT_PROMPT_TEMPLATE = "default_analysis_prompt.md"


def build_prompt(
    context: dict[str, Any],
    template_name: str = DEFAULT_PROMPT_TEMPLATE,
    output_language: str = "ru",
) -> str:
    """Build a compact JSON-oriented prompt for the provider."""
    response_schema = {
        "summary": "Short comparison summary",
        "relations": [
            {
                "type": "useful_repetition",
                "course_a_fragment": "",
                "course_b_fragment": "",
                "explanation": "",
                "confidence": 0.7,
                "evidence_refs": [],
            }
        ],
        "warnings": [],
    }
    template = _load_template(template_name)
    return template.format(
        response_schema=json.dumps(response_schema, ensure_ascii=False, indent=2),
        output_language=_language_name(output_language),
        course_a_text=context["course_a"]["text"],
        course_b_text=context["course_b"]["text"],
        skill_dictionary_text=context["skill_dictionary"]["text"],
        assessments_text=context["assessments"]["text"],
        selected_chunks_text=context.get("selected_chunks", {}).get("text", "[]"),
        retrieved_pairs_text=context.get("retrieved_pairs", {}).get("text", "[]"),
        preprocessing_metrics_json=json.dumps(context.get("preprocessing_metrics", {}), ensure_ascii=False, indent=2),
        warnings_json=json.dumps(context["warnings"], ensure_ascii=False, indent=2),
    )


def _load_template(template_name: str) -> str:
    return (
        resources.files("course_connector.llm_layer.prompts")
        .joinpath(template_name)
        .read_text(encoding="utf-8")
    )


def _language_name(output_language: str) -> str:
    if output_language == "en":
        return "English"
    return "Russian"
