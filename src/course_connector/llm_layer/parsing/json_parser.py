"""Parse raw provider responses into a minimal analysis dictionary."""

from __future__ import annotations

import json
from typing import Any


def parse_provider_response(text: str) -> dict[str, Any]:
    """Parse provider JSON while preserving a stable fallback shape."""
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
