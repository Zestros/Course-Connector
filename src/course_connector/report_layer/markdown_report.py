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

    lines.extend(["## Warnings", ""])
    warnings = list(analysis.get("warnings") or [])
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


def _format_confidence(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "unknown"
