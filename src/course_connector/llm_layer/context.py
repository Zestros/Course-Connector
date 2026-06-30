"""Build prompt context from the single Input layer payload boundary."""

from __future__ import annotations

import json
from typing import Any


def build_prompt_context(input_payload: dict[str, Any]) -> dict[str, Any]:
    """Build prompt context from the single Input layer payload boundary."""
    preprocessing = input_payload.get("preprocessing") if isinstance(input_payload.get("preprocessing"), dict) else {}
    evidence_first = _has_selected_evidence(preprocessing)
    return {
        "course_a": _evidence_placeholder(input_payload.get("course_a")) if evidence_first else _entry_context(input_payload.get("course_a")),
        "course_b": _evidence_placeholder(input_payload.get("course_b")) if evidence_first else _entry_context(input_payload.get("course_b")),
        "skill_dictionary": _entry_context(input_payload.get("skill_dictionary")),
        "assessments": _evidence_placeholder(input_payload.get("assessments")) if evidence_first else _entry_context(input_payload.get("assessments")),
        "config": _entry_context(input_payload.get("config")),
        "selected_chunks": _selected_chunks_context(preprocessing),
        "retrieved_pairs": _retrieved_pairs_context(preprocessing),
        "preprocessing_metrics": preprocessing.get("metrics", {}) if preprocessing.get("enabled") else {},
        "warnings": list(input_payload.get("warnings") or []),
    }


def _entry_context(entry: Any, max_chars: int | None = None) -> dict[str, Any]:
    if entry is None:
        return {"source_path": None, "format": None, "text": ""}
    text = entry.get("normalized_text") or entry.get("raw_text") or ""
    if not text and "parsed_data" in entry:
        text = json.dumps(entry["parsed_data"], ensure_ascii=False, indent=2)
    text_value = str(text)
    return {
        "source_path": entry.get("source_path"),
        "format": entry.get("format"),
        "text": _clip(text_value, max_chars=max_chars) if max_chars is not None else text_value,
    }


def _evidence_placeholder(entry: Any) -> dict[str, Any]:
    if entry is None:
        return {"source_path": None, "format": None, "text": ""}
    return {
        "source_path": entry.get("source_path"),
        "format": entry.get("format"),
        "text": "Preprocessing enabled. Use selected evidence chunks and retrieved evidence pairs below as detailed evidence.",
    }


def _clip(text: str, max_chars: int) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= max_chars else compact[:max_chars].rstrip() + "..."


def _has_selected_evidence(preprocessing: dict[str, Any]) -> bool:
    if not preprocessing.get("enabled"):
        return False
    return bool(
        preprocessing.get("selected_chunks")
        or preprocessing.get("retrieved_pairs")
        or preprocessing.get("skill_batches")
    )


def _selected_chunks_context(preprocessing: dict[str, Any]) -> dict[str, Any]:
    chunks = preprocessing.get("selected_chunks") if preprocessing.get("enabled") else []
    if not chunks:
        return {"enabled": False, "text": "[]"}
    compact_chunks = []
    for chunk in chunks:
        compact_chunks.append({
            "chunk_id": chunk.get("chunk_id"),
            "source_role": chunk.get("source_role"),
            "source_path": chunk.get("source_path"),
            "source_type": chunk.get("source_type"),
            "parent_id": chunk.get("parent_id"),
            "chunk_index": chunk.get("chunk_index"),
            "split_strategy": chunk.get("split_strategy"),
            "title": chunk.get("title"),
            "text": chunk.get("text"),
            "skill_ids": chunk.get("skill_ids", []),
            "locator": chunk.get("locator", {}),
        })
    return {"enabled": True, "text": json.dumps(compact_chunks, ensure_ascii=False, indent=2)}


def _retrieved_pairs_context(preprocessing: dict[str, Any]) -> dict[str, Any]:
    pairs = preprocessing.get("retrieved_pairs") if preprocessing.get("enabled") else []
    if not pairs:
        return {"enabled": False, "text": "[]"}
    compact_pairs = []
    for pair in pairs:
        compact_pairs.append({
            "pair_id": pair.get("pair_id"),
            "candidate_relation_hint": pair.get("candidate_relation_hint"),
            "retrieval_reason": pair.get("retrieval_reason"),
            "course_a_chunk_id": pair.get("course_a_chunk_id"),
            "course_b_chunk_id": pair.get("course_b_chunk_id"),
            "course_a_title": pair.get("course_a_title"),
            "course_b_title": pair.get("course_b_title"),
            "course_a_text": pair.get("course_a_text"),
            "course_b_text": pair.get("course_b_text"),
            "matched_skill_ids": pair.get("matched_skill_ids", []),
            "evidence_refs": pair.get("evidence_refs", []),
        })
    return {"enabled": True, "text": json.dumps(compact_pairs, ensure_ascii=False, indent=2)}
