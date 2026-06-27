"""Minimal pipeline orchestration for Course Connector."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from course_connector.llm_layer import analyze_courses
from course_connector.preprocessing_layer import prepare_analysis_context, write_intermediate_outputs


INPUT_ROLES = ("course_a", "course_b", "skill_dictionary", "assessments", "config")


@dataclass(frozen=True)
class PipelineResult:
    """Files produced by the pipeline."""

    report_md: Path
    result_json: Path


def run_pipeline(input_payload: dict[str, Any], output_dir: Path) -> PipelineResult:
    """Run a minimal local pipeline and write MVP output files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis_context = prepare_analysis_context(input_payload)
    intermediate_outputs = write_intermediate_outputs(output_dir, analysis_context)
    analysis_payload = _analysis_payload(input_payload, analysis_context)
    analysis = analyze_courses(analysis_payload)

    result = PipelineResult(
        report_md=output_dir / "report.md",
        result_json=output_dir / "result.json",
    )
    result.report_md.write_text(_build_markdown_report(input_payload, analysis, analysis_context), encoding="utf-8")
    result.result_json.write_text(
        json.dumps(
            _build_result(input_payload, analysis, result, analysis_context, intermediate_outputs),
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return result


def _build_markdown_report(
    input_payload: dict[str, Any],
    analysis: dict[str, Any],
    analysis_context: dict[str, Any],
) -> str:
    lines = [
        "# Course Connector Report",
        "",
        "Pipeline reached the MVP LLM analysis layer successfully.",
        "",
        "## Analysis Summary",
        "",
        analysis.get("summary") or "No summary returned.",
        "",
        "## Relations",
        "",
    ]
    relations = analysis.get("relations") or []
    if relations:
        for relation in relations:
            lines.extend(
                [
                    f"- `{relation['type']}` ({relation['confidence']:.2f}): {relation['explanation']}",
                    f"  - Course A: {relation['course_a_fragment']}",
                    f"  - Course B: {relation['course_b_fragment']}",
                ]
            )
            if relation.get("evidence_refs"):
                lines.append(f"  - Evidence refs: `{len(relation['evidence_refs'])}`")
    else:
        lines.append("- None")

    if analysis_context.get("enabled"):
        metrics = analysis_context.get("metrics", {})
        lines.extend([
            "",
            "## Preprocessing",
            "",
            f"- Mode: `{analysis_context.get('mode')}`",
            f"- Chunks course A: `{metrics.get('chunks_course_a', 0)}`",
            f"- Chunks course B: `{metrics.get('chunks_course_b', 0)}`",
            f"- Retrieved pairs: `{metrics.get('retrieved_pairs', 0)}`",
            f"- Estimated input tokens: `{metrics.get('estimated_input_tokens', 0)}`",
        ])

    lines.extend([
        "",
        "## Inputs",
        "",
    ])
    for role in INPUT_ROLES:
        entry = input_payload.get(role)
        label = role.replace("_", " ").title()
        if entry is None:
            lines.append(f"- {label}: not provided")
            continue
        lines.append(f"- {label}: `{entry['source_path']}` ({entry['format']})")

    warnings = [*list(input_payload.get("warnings") or []), *list(analysis_context.get("warnings") or [])]
    lines.extend(["", "## Warnings", ""])
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def _build_result(
    input_payload: dict[str, Any],
    analysis: dict[str, Any],
    result: PipelineResult,
    analysis_context: dict[str, Any],
    intermediate_outputs: dict[str, str],
) -> dict[str, Any]:
    return {
        "status": "completed",
        "pipeline_stage": "mvp_llm_analysis_layer",
        "summary": analysis.get("summary", ""),
        "relations": analysis.get("relations", []),
        "warnings": analysis.get("warnings", []),
        "provider": analysis.get("provider", "unknown"),
        "provider_mode": analysis.get("provider_mode", "unknown"),
        "inputs": {
            role: _input_summary(input_payload.get(role))
            for role in INPUT_ROLES
        },
        "preprocessing": _preprocessing_summary(analysis_context, intermediate_outputs),
        "outputs": {
            "report_md": str(result.report_md),
            "result_json": str(result.result_json),
            **intermediate_outputs,
        },
    }


def _input_summary(entry: Any) -> dict[str, Any] | None:
    if entry is None:
        return None
    return {
        "source_path": entry.get("source_path"),
        "format": entry.get("format"),
    }


def _analysis_payload(input_payload: dict[str, Any], analysis_context: dict[str, Any]) -> dict[str, Any]:
    payload = dict(input_payload)
    if analysis_context.get("enabled"):
        payload["preprocessing"] = analysis_context
        payload["warnings"] = [
            *list(input_payload.get("warnings") or []),
            *list(analysis_context.get("warnings") or []),
        ]
    return payload


def _preprocessing_summary(analysis_context: dict[str, Any], intermediate_outputs: dict[str, str]) -> dict[str, Any]:
    return {
        "enabled": bool(analysis_context.get("enabled")),
        "mode": analysis_context.get("mode", "disabled"),
        "metrics": analysis_context.get("metrics", {}),
        "warnings": analysis_context.get("warnings", []),
        "outputs": intermediate_outputs,
    }
