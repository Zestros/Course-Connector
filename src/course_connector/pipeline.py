"""Minimal pipeline orchestration for Course Connector."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from course_connector.llm_layer import analyze_courses
from course_connector.preprocessing_layer import prepare_analysis_context, write_intermediate_outputs
from course_connector.report_layer import build_json_result, render_markdown_report, write_json_result


@dataclass(frozen=True)
class PipelineResult:
    """Files produced by the pipeline."""

    report_md: Path
    result_json: Path


def run_pipeline(input_payload: dict[str, Any], output_dir: Path) -> PipelineResult:
    """Run the pipeline and write output files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis_context = prepare_analysis_context(input_payload)
    intermediate_outputs = write_intermediate_outputs(output_dir, analysis_context)
    analysis_payload = _analysis_payload(input_payload, analysis_context)
    analysis = analyze_courses(analysis_payload)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    run_id = generated_at.replace("+00:00", "Z").replace(":", "").replace("-", "")

    result = PipelineResult(
        report_md=output_dir / "report.md",
        result_json=output_dir / "result.json",
    )
    output_paths = {
        "report_md": result.report_md,
        "result_json": result.result_json,
        **intermediate_outputs,
    }
    result.report_md.write_text(
        render_markdown_report(
            input_payload,
            analysis,
            analysis_context=analysis_context,
            run_id=run_id,
            generated_at=generated_at,
        ),
        encoding="utf-8",
    )
    write_json_result(
        result.result_json,
        build_json_result(
            input_payload,
            analysis,
            output_paths,
            analysis_context=analysis_context,
            run_id=run_id,
            generated_at=generated_at,
        ),
    )
    return result


def _analysis_payload(input_payload: dict[str, Any], analysis_context: dict[str, Any]) -> dict[str, Any]:
    payload = dict(input_payload)
    if analysis_context.get("enabled"):
        payload["preprocessing"] = analysis_context
        payload["warnings"] = [
            *list(input_payload.get("warnings") or []),
            *list(analysis_context.get("warnings") or []),
        ]
    return payload
