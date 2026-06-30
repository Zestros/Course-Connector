"""Minimal pipeline orchestration for Course Connector."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from course_connector.llm_layer import analyze_courses
from course_connector.llm_layer.batch_analyzer import analyze_batches
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
    return _run_pipeline(input_payload, output_dir, progress_callback=None)


def run_pipeline_with_progress(
    input_payload: dict[str, Any],
    output_dir: Path,
    *,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> PipelineResult:
    """Run the pipeline and report long-running smart batch progress."""
    return _run_pipeline(input_payload, output_dir, progress_callback=progress_callback)


def _run_pipeline(
    input_payload: dict[str, Any],
    output_dir: Path,
    *,
    progress_callback: Callable[[dict[str, Any]], None] | None,
) -> PipelineResult:
    """Run the pipeline and write output files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_stale_intermediate_outputs(output_dir)
    preprocessing_config = PreprocessingConfig.from_input_payload(input_payload)
    analysis_context = prepare_analysis_context(input_payload, config=preprocessing_config)
    analysis_payload = _analysis_payload(input_payload, analysis_context)
    intermediate_outputs: dict[str, str] = {}
    if analysis_context.get("analysis_mode") == "smart_batch":
        if analysis_context.get("enabled") and analysis_context.get("write_intermediate_outputs"):
            intermediate_outputs.update(write_intermediate_outputs(output_dir, analysis_context))
        analysis, context_updates = analyze_batches(
            analysis_payload,
            progress_callback=_progress_dispatcher(
                output_dir=output_dir,
                analysis_context=analysis_context,
                user_callback=progress_callback,
            ),
        )
        analysis_context.update({key: value for key, value in context_updates.items() if key != "metrics"})
        analysis_context["metrics"] = context_updates.get("metrics", analysis_context.get("metrics", {}))
    else:
        _validate_analysis_prompt_budget(analysis_payload, preprocessing_config)
        analysis = analyze_courses(analysis_payload)
    intermediate_outputs.update(write_intermediate_outputs(output_dir, analysis_context))
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


def _progress_dispatcher(
    *,
    output_dir: Path,
    analysis_context: dict[str, Any],
    user_callback: Callable[[dict[str, Any]], None] | None,
) -> Callable[[dict[str, Any]], None]:
    def dispatch(event: dict[str, Any]) -> None:
        if event.get("event") == "batch_complete" and isinstance(event.get("result"), dict):
            analysis_context.setdefault("batch_results", []).append(event["result"])
            _write_progress_outputs(output_dir, analysis_context)
        if user_callback is not None:
            user_callback(event)

    return dispatch


def _write_progress_outputs(output_dir: Path, analysis_context: dict[str, Any]) -> None:
    if not analysis_context.get("enabled") or not analysis_context.get("write_intermediate_outputs"):
        return
    _write_json(output_dir / "batch_results.json", analysis_context.get("batch_results", []))
    _write_json(
        output_dir / "preprocessing_summary.json",
        {
            "enabled": analysis_context.get("enabled"),
            "mode": analysis_context.get("mode"),
            "metrics": {
                **dict(analysis_context.get("metrics") or {}),
                "executed_batches": len(analysis_context.get("batch_results") or []),
                "failed_batches": len([
                    result
                    for result in analysis_context.get("batch_results", [])
                    if result.get("status") != "completed"
                ]),
            },
            "warnings": analysis_context.get("warnings", []),
        },
    )


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _clear_stale_intermediate_outputs(output_dir: Path) -> None:
    for name in (
        "chunks_course_a.json",
        "chunks_course_b.json",
        "selected_chunks.json",
        "retrieved_pairs.json",
        "course_profiles.json",
        "skill_batches.json",
        "batch_results.json",
        "merged_findings.json",
        "preprocessing_summary.json",
    ):
        path = output_dir / name
        if path.is_file():
            path.unlink()


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
