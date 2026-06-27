"""Minimal pipeline orchestration for Course Connector."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from course_connector.llm_layer import analyze_courses


INPUT_ROLES = ("course_a", "course_b", "skill_dictionary", "assessments", "config")


@dataclass(frozen=True)
class PipelineResult:
    """Files produced by the pipeline."""

    report_md: Path
    result_json: Path


def run_pipeline(input_payload: dict[str, Any], output_dir: Path) -> PipelineResult:
    """Run a minimal local pipeline and write MVP output files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis = analyze_courses(input_payload)

    result = PipelineResult(
        report_md=output_dir / "report.md",
        result_json=output_dir / "result.json",
    )
    result.report_md.write_text(_build_markdown_report(input_payload, analysis), encoding="utf-8")
    result.result_json.write_text(
        json.dumps(_build_result(input_payload, analysis, result), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def _build_markdown_report(input_payload: dict[str, Any], analysis: dict[str, Any]) -> str:
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
    else:
        lines.append("- None")

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

    warnings = input_payload.get("warnings") or []
    lines.extend(["", "## Warnings", ""])
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def _build_result(input_payload: dict[str, Any], analysis: dict[str, Any], result: PipelineResult) -> dict[str, Any]:
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
        "outputs": {
            "report_md": str(result.report_md),
            "result_json": str(result.result_json),
        },
    }


def _input_summary(entry: Any) -> dict[str, Any] | None:
    if entry is None:
        return None
    return {
        "source_path": entry.get("source_path"),
        "format": entry.get("format"),
    }
