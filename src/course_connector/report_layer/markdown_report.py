"""Render human-readable Markdown Course Connector reports."""

from __future__ import annotations

from typing import Any

from course_connector.report_layer.json_report import INPUT_ROLES


RELATION_SECTIONS = (
    ("useful_repetition", "Useful Repetitions"),
    ("probable_duplication", "Probable Duplications"),
    ("probable_gap", "Probable Gaps"),
)


def render_markdown_report(
    input_payload: dict[str, Any],
    analysis: dict[str, Any],
    *,
    run_id: str,
    generated_at: str,
    analysis_context: dict[str, Any] | None = None,
) -> str:
    """Render a readable MVP report grouped by relation type."""
    lines = [
        "# Course Connector Report",
        "",
        f"- Run ID: `{run_id}`",
        f"- Generated at: `{generated_at}`",
        "",
        "## Analysis Summary",
        "",
        analysis.get("summary") or "No summary returned.",
        "",
        "## Relations",
        "",
    ]

    relations = list(analysis.get("relations") or [])
    chunk_texts = _chunk_texts(analysis_context)
    for relation_type, title in RELATION_SECTIONS:
        lines.extend([f"## {title}", ""])
        _append_relations(
            lines,
            [relation for relation in relations if relation.get("type") == relation_type],
            chunk_texts,
        )
        lines.append("")

    other_relations = [
        relation
        for relation in relations
        if relation.get("type") not in {relation_type for relation_type, _ in RELATION_SECTIONS}
    ]
    if other_relations:
        lines.extend(["## Other Relations", ""])
        _append_relations(lines, other_relations, chunk_texts)
        lines.append("")

    if analysis_context and analysis_context.get("enabled"):
        metrics = analysis_context.get("metrics", {})
        lines.extend([
            "## Preprocessing",
            "",
            f"- Mode: `{analysis_context.get('mode')}`",
            f"- Analysis mode: `{analysis_context.get('analysis_mode', analysis_context.get('mode'))}`",
            f"- Chunks course A: `{metrics.get('chunks_course_a', 0)}`",
            f"- Chunks course B: `{metrics.get('chunks_course_b', 0)}`",
            f"- Retrieved pairs: `{metrics.get('retrieved_pairs', 0)}`",
            f"- Skill batches: `{metrics.get('skill_batches', 0)}`",
            f"- Executed batches: `{metrics.get('executed_batches', 0)}`",
            f"- Failed batches: `{metrics.get('failed_batches', 0)}`",
            f"- Covered skills: `{len(metrics.get('covered_skill_ids', []) or [])}`",
            f"- Uncovered skills: `{len(metrics.get('uncovered_skill_ids', []) or [])}`",
            f"- Estimated input tokens: `{metrics.get('estimated_input_tokens', 0)}`",
            "",
        ])

    lines.extend(["## Warnings", ""])
    warnings = _dedupe_warnings([
        *list(analysis.get("warnings") or []),
        *list((analysis_context or {}).get("warnings") or []),
    ])
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- None")

    lines.extend(["", "## Source Files", ""])
    for role in INPUT_ROLES:
        entry = input_payload.get(role)
        label = role.replace("_", " ").title()
        if entry is None:
            lines.append(f"- {label}: not provided")
            continue
        lines.append(f"- {label}: `{entry['source_path']}` ({entry['format']})")

    lines.append("")
    return "\n".join(lines)


def _append_relations(
    lines: list[str],
    relations: list[dict[str, Any]],
    chunk_texts: dict[str, str],
) -> None:
    if not relations:
        lines.append("- None")
        return

    for relation in relations:
        confidence = _format_confidence(relation.get("confidence"))
        lines.extend(
            [
                f"- `{relation.get('type')}` confidence {confidence}: {relation.get('explanation') or 'No explanation returned.'}",
                f"  - Course A: {relation.get('course_a_fragment') or 'Not provided.'}",
                f"  - Course B: {relation.get('course_b_fragment') or 'Not provided.'}",
            ]
        )
        if relation.get("evidence_refs"):
            lines.append("  - Evidence:")
            for evidence_ref in relation["evidence_refs"]:
                lines.append(f"    - {_format_evidence_ref(evidence_ref, chunk_texts)}")


def _format_confidence(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "unknown"


def _format_evidence_ref(evidence_ref: Any, chunk_texts: dict[str, str] | None = None) -> str:
    chunk_texts = chunk_texts or {}
    if not isinstance(evidence_ref, dict):
        chunk_id = str(evidence_ref)
        return _format_evidence_with_chunk_text(f"`{chunk_id}`", chunk_id, chunk_texts)
    role = evidence_ref.get("source_role") or "unknown"
    source_type = evidence_ref.get("source_type") or "source"
    source_path = evidence_ref.get("source_path") or "unknown source"
    chunk_id = evidence_ref.get("chunk_id") or "unknown chunk"
    locator = _format_locator(evidence_ref.get("locator"))
    formatted = f"`{role}` `{source_type}` `{chunk_id}`: `{source_path}` -> `{locator}`"
    return _format_evidence_with_chunk_text(formatted, str(chunk_id), chunk_texts)


def _format_evidence_with_chunk_text(formatted_ref: str, chunk_id: str, chunk_texts: dict[str, str]) -> str:
    chunk_text = chunk_texts.get(chunk_id)
    if not chunk_text:
        return formatted_ref
    return f"{formatted_ref}: {chunk_text}"


def _chunk_texts(analysis_context: dict[str, Any] | None) -> dict[str, str]:
    if not analysis_context:
        return {}
    chunks = analysis_context.get("chunks")
    if not isinstance(chunks, dict):
        return {}
    result: dict[str, str] = {}
    for chunk_list in chunks.values():
        if not isinstance(chunk_list, list):
            continue
        for chunk in chunk_list:
            if not isinstance(chunk, dict):
                continue
            chunk_id = str(chunk.get("chunk_id") or "").strip()
            text = _normalize_chunk_text(chunk.get("text"))
            if chunk_id and text:
                result[chunk_id] = text
    return result


def _normalize_chunk_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _format_locator(locator: Any) -> str:
    if not isinstance(locator, dict):
        return "unknown"
    kind = locator.get("kind")
    if kind == "object_path":
        return str(locator.get("object_path") or "object_path")
    if kind == "row_index":
        return f"row {locator.get('row_index')}"
    if kind == "line_range":
        return f"lines {locator.get('line_start')}..{locator.get('line_end')}"
    if kind == "coarse_file":
        return "whole file"
    return str(kind or "unknown")


def _dedupe_warnings(warnings: list[Any]) -> list[str]:
    result = []
    seen = set()
    for warning in warnings:
        text = str(warning)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
