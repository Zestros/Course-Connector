"""Simple LLM-style analysis layer for Course Connector."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


ALLOWED_RELATION_TYPES = (
    "useful_repetition",
    "probable_duplication",
    "probable_gap",
)


@dataclass(frozen=True)
class LLMResponse:
    """Text response returned by an LLM provider."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Minimal provider contract for LLM-style analysis."""

    @abstractmethod
    def generate(self, prompt: str) -> LLMResponse:
        """Generate a response for a prompt."""


class MockLLMProvider(LLMProvider):
    """Deterministic local provider for tests and demos."""

    def generate(self, prompt: str) -> LLMResponse:
        response = {
            "summary": "Mock analysis found candidate relations between the two course inputs.",
            "relations": [
                {
                    "type": "useful_repetition",
                    "course_a_fragment": "Course A introduces a skill that appears again in Course B.",
                    "course_b_fragment": "Course B reuses the skill in a more applied context.",
                    "explanation": "The repeated topic can reinforce learning when coordinated between courses.",
                    "confidence": 0.72,
                },
                {
                    "type": "probable_duplication",
                    "course_a_fragment": "Both courses include overlapping introductory material.",
                    "course_b_fragment": "The same introductory material appears without clear progression.",
                    "explanation": "This may duplicate effort unless Course B adds a new level of practice.",
                    "confidence": 0.62,
                },
                {
                    "type": "probable_gap",
                    "course_a_fragment": "Course A preparation evidence is limited for one later assessment skill.",
                    "course_b_fragment": "Course B assessment expects the skill during practical work.",
                    "explanation": "The later assessment may need explicit preparation in Course A or bridging material.",
                    "confidence": 0.58,
                },
            ],
            "warnings": [],
        }
        return LLMResponse(
            text=json.dumps(response, ensure_ascii=False, indent=2),
            metadata={"provider": "mock", "mode": "mock"},
        )


class StaticLLMProvider(LLMProvider):
    """Test provider that returns a fixed response."""

    def __init__(self, text: str, metadata: dict[str, Any] | None = None) -> None:
        self.text = text
        self.metadata = metadata or {"provider": "static", "mode": "test"}

    def generate(self, prompt: str) -> LLMResponse:
        return LLMResponse(text=self.text, metadata=self.metadata)


def analyze_courses(
    input_payload: dict[str, Any],
    provider: LLMProvider | None = None,
    debug: bool = False,
) -> dict[str, Any]:
    """Analyze prepared course inputs and return structured relation candidates."""
    provider = provider or MockLLMProvider()
    context = build_prompt_context(input_payload)
    prompt = build_prompt(context)
    response = provider.generate(prompt)
    analysis = _parse_provider_response(response.text)
    analysis["warnings"] = [
        *list(input_payload.get("warnings") or []),
        *list(analysis.get("warnings") or []),
    ]
    analysis["relations"] = _normalize_relations(analysis.get("relations") or [], analysis["warnings"])
    analysis["provider"] = response.metadata.get("provider", "unknown")
    analysis["provider_mode"] = response.metadata.get("mode", analysis["provider"])
    if debug:
        analysis["raw_response"] = response.text
        analysis["prompt"] = prompt
    return analysis


def build_prompt_context(input_payload: dict[str, Any]) -> dict[str, Any]:
    """Build prompt context from the single Input layer payload boundary."""
    return {
        "course_a": _entry_context(input_payload.get("course_a")),
        "course_b": _entry_context(input_payload.get("course_b")),
        "skill_dictionary": _entry_context(input_payload.get("skill_dictionary")),
        "assessments": _entry_context(input_payload.get("assessments")),
        "config": _entry_context(input_payload.get("config")),
        "warnings": list(input_payload.get("warnings") or []),
    }


def build_prompt(context: dict[str, Any]) -> str:
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
            }
        ],
        "warnings": [],
    }
    return f"""# Course-Connector MVP Analysis Prompt

Analyze two course inputs and identify candidate relations for human review.

Return only valid JSON. Do not wrap the JSON in Markdown.

Allowed relation types:
- useful_repetition
- probable_duplication
- probable_gap

Required JSON response format:
{json.dumps(response_schema, ensure_ascii=False, indent=2)}

Course A:
{context["course_a"]["text"]}

Course B:
{context["course_b"]["text"]}

Skill dictionary:
{context["skill_dictionary"]["text"]}

Assessments:
{context["assessments"]["text"]}

Input warnings:
{json.dumps(context["warnings"], ensure_ascii=False, indent=2)}
"""


def _entry_context(entry: Any, max_chars: int = 1200) -> dict[str, Any]:
    if entry is None:
        return {"source_path": None, "format": None, "text": ""}
    text = entry.get("normalized_text") or entry.get("raw_text") or ""
    if not text and "parsed_data" in entry:
        text = json.dumps(entry["parsed_data"], ensure_ascii=False, indent=2)
    return {
        "source_path": entry.get("source_path"),
        "format": entry.get("format"),
        "text": _clip(str(text), max_chars=max_chars),
    }


def _parse_provider_response(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return {
            "summary": "Provider response could not be parsed as JSON.",
            "relations": [],
            "warnings": [f"Provider JSON could not be parsed: {exc.msg}."],
        }
    if not isinstance(parsed, dict):
        return {
            "summary": "Provider response was JSON but not an object.",
            "relations": [],
            "warnings": ["Provider JSON must be an object with summary, relations, and warnings."],
        }
    warnings = parsed.get("warnings") if isinstance(parsed.get("warnings"), list) else []
    return {
        "summary": str(parsed.get("summary") or ""),
        "relations": parsed.get("relations") if isinstance(parsed.get("relations"), list) else [],
        "warnings": [str(warning) for warning in warnings],
    }


def _normalize_relations(relations: list[Any], warnings: list[str]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, relation in enumerate(relations, start=1):
        if not isinstance(relation, dict):
            warnings.append(f"Relation #{index} is not an object and was skipped.")
            continue
        relation_type = str(relation.get("type") or "")
        if relation_type not in ALLOWED_RELATION_TYPES:
            warnings.append(f"Unsupported relation type `{relation_type}` in relation #{index}.")
            continue
        confidence = _confidence(relation.get("confidence"), warnings, index)
        normalized.append(
            {
                "type": relation_type,
                "course_a_fragment": str(relation.get("course_a_fragment") or ""),
                "course_b_fragment": str(relation.get("course_b_fragment") or ""),
                "explanation": str(relation.get("explanation") or ""),
                "confidence": confidence,
            }
        )
    return normalized


def _confidence(value: Any, warnings: list[str], index: int) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        warnings.append(f"Relation #{index} confidence is not numeric; normalized to 0.0.")
        return 0.0
    if confidence < 0.0 or confidence > 1.0:
        warnings.append(f"Relation #{index} confidence is outside 0.0..1.0 and was clamped.")
    return max(0.0, min(1.0, confidence))


def _clip(text: str, max_chars: int) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= max_chars else compact[:max_chars].rstrip() + "..."
