"""Render prompts for smart batch analysis."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from course_connector.llm_layer.prompts.renderer import _language_name


DEFAULT_SKILL_BATCH_TEMPLATE = "skill_batch_analysis_prompt.md"
DEFAULT_FINAL_SYNTHESIS_TEMPLATE = "final_findings_synthesis_prompt.md"


def build_skill_batch_prompt(
    batch: dict[str, Any],
    *,
    template_name: str = DEFAULT_SKILL_BATCH_TEMPLATE,
    output_language: str = "ru",
) -> str:
    """Build a JSON-oriented prompt for one smart analysis batch."""
    response_schema = {
        "summary": "Short batch summary",
        "findings": [
            {
                "type": "useful_repetition",
                "course_a_fragment": "",
                "course_b_fragment": "",
                "explanation": "",
                "confidence": 0.7,
                "skill_ids": [],
                "evidence_refs": [],
                "batch_id": batch.get("batch_id", ""),
            }
        ],
        "warnings": [],
    }
    template = (
        resources.files("course_connector.llm_layer.prompts")
        .joinpath(template_name)
        .read_text(encoding="utf-8")
    )
    return template.format(
        output_language=_language_name(output_language),
        response_schema=json.dumps(response_schema, ensure_ascii=False, indent=2),
        batch_metadata_json=json.dumps(_batch_metadata(batch), ensure_ascii=False, indent=2),
        course_profiles_json=json.dumps(batch.get("course_profiles", {}), ensure_ascii=False, indent=2),
        skill_dictionary_subset_json=json.dumps(batch.get("skill_dictionary_subset", []), ensure_ascii=False, indent=2),
        course_a_chunks_json=json.dumps(batch.get("course_a_chunks", []), ensure_ascii=False, indent=2),
        course_b_chunks_json=json.dumps(batch.get("course_b_chunks", []), ensure_ascii=False, indent=2),
        assessment_chunks_json=json.dumps(batch.get("assessment_chunks", []), ensure_ascii=False, indent=2),
        warnings_json=json.dumps(batch.get("warnings", []), ensure_ascii=False, indent=2),
    )


def build_final_findings_synthesis_prompt(
    *,
    course_profiles: dict[str, Any],
    findings: list[dict[str, Any]],
    warnings: list[str],
    output_language: str = "ru",
    template_name: str = DEFAULT_FINAL_SYNTHESIS_TEMPLATE,
) -> str:
    """Build a prompt that synthesizes normalized findings without new evidence."""
    response_schema = {
        "summary": "Short final summary",
        "relations": [
            {
                "type": "useful_repetition",
                "course_a_fragment": "",
                "course_b_fragment": "",
                "explanation": "",
                "confidence": 0.7,
                "skill_ids": [],
                "evidence_refs": [],
            }
        ],
        "warnings": [],
    }
    template = (
        resources.files("course_connector.llm_layer.prompts")
        .joinpath(template_name)
        .read_text(encoding="utf-8")
    )
    return template.format(
        output_language=_language_name(output_language),
        response_schema=json.dumps(response_schema, ensure_ascii=False, indent=2),
        course_profiles_json=json.dumps(course_profiles, ensure_ascii=False, indent=2),
        findings_json=json.dumps(findings, ensure_ascii=False, indent=2),
        warnings_json=json.dumps(warnings, ensure_ascii=False, indent=2),
    )
def _batch_metadata(batch: dict[str, Any]) -> dict[str, Any]:
    return {
        "batch_id": batch.get("batch_id"),
        "parent_batch_id": batch.get("parent_batch_id"),
        "batch_type": batch.get("batch_type"),
        "skill_ids": batch.get("skill_ids", []),
        "split_reason": batch.get("split_reason"),
        "course_a_chunk_ids": batch.get("course_a_chunk_ids", []),
        "course_b_chunk_ids": batch.get("course_b_chunk_ids", []),
        "assessment_chunk_ids": batch.get("assessment_chunk_ids", []),
        "coverage_status": batch.get("coverage_status", {}),
    }
