"""Merge smart batch findings into final relation candidates."""

from __future__ import annotations

from typing import Any


def merge_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge duplicate findings while preserving evidence and batch references."""
    merged: list[dict[str, Any]] = []
    for finding in findings:
        target = _find_duplicate(merged, finding)
        if target is None:
            item = dict(finding)
            if item.get("batch_id") and not item.get("source_batch_ids"):
                item["source_batch_ids"] = [item["batch_id"]]
            merged.append(item)
            continue
        target["confidence"] = max(float(target.get("confidence") or 0.0), float(finding.get("confidence") or 0.0))
        target["evidence_refs"] = _unique_list([*target.get("evidence_refs", []), *finding.get("evidence_refs", [])])
        target["skill_ids"] = _unique_list([*target.get("skill_ids", []), *finding.get("skill_ids", [])])
        target["source_batch_ids"] = _unique_list([
            *target.get("source_batch_ids", []),
            *finding.get("source_batch_ids", []),
            *([finding["batch_id"]] if finding.get("batch_id") else []),
        ])
    return merged


def _find_duplicate(items: list[dict[str, Any]], candidate: dict[str, Any]) -> dict[str, Any] | None:
    candidate_skills = set(candidate.get("skill_ids") or [])
    candidate_refs = {_ref_key(ref) for ref in candidate.get("evidence_refs") or []}
    for item in items:
        if item.get("type") != candidate.get("type"):
            continue
        item_skills = set(item.get("skill_ids") or [])
        item_refs = {_ref_key(ref) for ref in item.get("evidence_refs") or []}
        if candidate_skills and item_skills and not (candidate_skills & item_skills):
            continue
        if candidate_refs and item_refs and not (candidate_refs & item_refs):
            continue
        return item
    return None


def _ref_key(ref: Any) -> str:
    if isinstance(ref, dict):
        return str(ref.get("chunk_id") or ref)
    return str(ref)


def _unique_list(items: list[Any]) -> list[Any]:
    result = []
    seen = set()
    for item in items:
        key = _ref_key(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
