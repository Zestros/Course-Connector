"""Minimal pipeline orchestration for Course Connector."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from course_connector.llm_layer import analyze_courses
from course_connector.llm_layer.context import build_prompt_context
from course_connector.preprocessing_layer.config import PreprocessingConfig
from course_connector.preprocessing_layer import prepare_analysis_context, write_intermediate_outputs
from course_connector.preprocessing_layer.token_budget import (
    estimate_prompt_tokens_from_context,
    validate_prompt_size,
)
from course_connector.report_layer import build_json_result, render_markdown_report, write_json_result


@dataclass(frozen=True)
class PipelineResult:
    """Files produced by the pipeline."""

    report_md: Path
    result_json: Path


def run_pipeline(input_payload: dict[str, Any], output_dir: Path) -> PipelineResult:
    """Run the pipeline and write output files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    preprocessing_config = PreprocessingConfig.from_input_payload(input_payload)
    analysis_context = prepare_analysis_context(input_payload, config=preprocessing_config)
    analysis_payload = _analysis_payload(input_payload, analysis_context)
    _validate_analysis_prompt_budget(analysis_payload, preprocessing_config)
    intermediate_outputs = write_intermediate_outputs(output_dir, analysis_context)
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


def _validate_analysis_prompt_budget(
    analysis_payload: dict[str, Any],
    preprocessing_config: PreprocessingConfig,
) -> None:
    if not preprocessing_config.token_budget.enabled:
        return
    prompt_context = build_prompt_context(analysis_payload)
    estimated_tokens = estimate_prompt_tokens_from_context(prompt_context)
    evidence_first = bool(
        analysis_payload.get("preprocessing", {}).get("selected_chunks")
        or analysis_payload.get("preprocessing", {}).get("retrieved_pairs")
    )
    code = "prompt_budget_exceeded_after_chunking" if evidence_first else "input_too_large_without_chunking"
    validate_prompt_size(estimated_tokens, preprocessing_config, code)
    preprocessing = analysis_payload.get("preprocessing")
    if isinstance(preprocessing, dict):
        metrics = preprocessing.setdefault("metrics", {})
        metrics["estimated_prompt_tokens"] = estimated_tokens
