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
    for relation_type, title in RELATION_SECTIONS:
        lines.extend([f"## {title}", ""])
        _append_relations(lines, [relation for relation in relations if relation.get("type") == relation_type])
        lines.append("")

    other_relations = [
        relation
        for relation in relations
        if relation.get("type") not in {relation_type for relation_type, _ in RELATION_SECTIONS}
    ]
    if other_relations:
        lines.extend(["## Other Relations", ""])
        _append_relations(lines, other_relations)
        lines.append("")

    if analysis_context and analysis_context.get("enabled"):
        metrics = analysis_context.get("metrics", {})
        lines.extend([
            "## Preprocessing",
            "",
            f"- Mode: `{analysis_context.get('mode')}`",
            f"- Chunks course A: `{metrics.get('chunks_course_a', 0)}`",
            f"- Chunks course B: `{metrics.get('chunks_course_b', 0)}`",
            f"- Retrieved pairs: `{metrics.get('retrieved_pairs', 0)}`",
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


def _append_relations(lines: list[str], relations: list[dict[str, Any]]) -> None:
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
                lines.append(f"    - {_format_evidence_ref(evidence_ref)}")


def _format_confidence(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "unknown"


def _format_evidence_ref(evidence_ref: dict[str, Any]) -> str:
    role = evidence_ref.get("source_role") or "unknown"
    source_type = evidence_ref.get("source_type") or "source"
    source_path = evidence_ref.get("source_path") or "unknown source"
    chunk_id = evidence_ref.get("chunk_id") or "unknown chunk"
    locator = _format_locator(evidence_ref.get("locator"))
    return f"`{role}` `{source_type}` `{chunk_id}`: `{source_path}` -> `{locator}`"


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
