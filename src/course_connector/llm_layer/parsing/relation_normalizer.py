"""Normalize relation candidates returned by providers."""

from __future__ import annotations

from typing import Any


ALLOWED_RELATION_TYPES = (
    "useful_repetition",
    "probable_duplication",
    "probable_gap",
)


def normalize_relations(relations: list[Any], warnings: list[str]) -> list[dict[str, Any]]:
    """Validate relation candidates and return the stable output contract."""
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
        item = {
            "type": relation_type,
            "course_a_fragment": str(relation.get("course_a_fragment") or ""),
            "course_b_fragment": str(relation.get("course_b_fragment") or ""),
            "explanation": str(relation.get("explanation") or ""),
            "confidence": confidence,
        }
        if isinstance(relation.get("evidence_refs"), list):
            item["evidence_refs"] = relation["evidence_refs"]
        normalized.append(item)
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
