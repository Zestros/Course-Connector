"""Minimal pipeline orchestration for Course Connector."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from course_connector.llm_layer import analyze_courses
from course_connector.report_layer import build_json_result, render_markdown_report, write_json_result


@dataclass(frozen=True)
class PipelineResult:
    """Files produced by the pipeline."""

    report_md: Path
    result_json: Path


def run_pipeline(input_payload: dict[str, Any], output_dir: Path) -> PipelineResult:
    """Run a minimal local pipeline and write MVP output files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis = analyze_courses(input_payload)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    run_id = generated_at.replace("+00:00", "Z").replace(":", "").replace("-", "")

    result = PipelineResult(
        report_md=output_dir / "report.md",
        result_json=output_dir / "result.json",
    )
    output_paths = {
        "report_md": result.report_md,
        "result_json": result.result_json,
    }
    result.report_md.write_text(
        render_markdown_report(input_payload, analysis, run_id=run_id, generated_at=generated_at),
        encoding="utf-8",
    )
    write_json_result(
        result.result_json,
        build_json_result(
            input_payload,
            analysis,
            output_paths,
            run_id=run_id,
            generated_at=generated_at,
        ),
    )
    return result
