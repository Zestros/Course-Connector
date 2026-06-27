"""Build prompt context from the single Input layer payload boundary."""

from __future__ import annotations

import json
from typing import Any


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


def _clip(text: str, max_chars: int) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= max_chars else compact[:max_chars].rstrip() + "..."
