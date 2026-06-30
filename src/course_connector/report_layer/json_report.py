"""Build and write machine-readable Course Connector reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


INPUT_ROLES = ("course_a", "course_b", "skill_dictionary", "assessments", "config")


def build_json_result(
    input_payload: dict[str, Any],
    analysis: dict[str, Any],
    output_paths: dict[str, Path | str],
    *,
    run_id: str,
    generated_at: str,
    analysis_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the stable MVP JSON result object."""
    result = {
        "status": analysis.get("status", "completed"),
        "run_id": run_id,
        "generated_at": generated_at,
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
            name: str(path)
            for name, path in output_paths.items()
        },
    }
    if analysis_context is not None:
        result["preprocessing"] = _preprocessing_summary(analysis_context, output_paths)
    return result


def write_json_result(path: Path, result: dict[str, Any]) -> None:
    """Write the machine-readable result file."""
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _input_summary(entry: Any) -> dict[str, Any] | None:
    if entry is None:
        return None
    return {
        "source_path": entry.get("source_path"),
        "format": entry.get("format"),
    }


def _preprocessing_summary(
    analysis_context: dict[str, Any],
    output_paths: dict[str, Path | str],
) -> dict[str, Any]:
    intermediate_outputs = {
        name: str(path)
        for name, path in output_paths.items()
        if name not in {"report_md", "result_json"}
    }
    return {
        "enabled": bool(analysis_context.get("enabled")),
        "mode": analysis_context.get("mode", "disabled"),
        "analysis_mode": analysis_context.get("analysis_mode", analysis_context.get("mode", "disabled")),
        "metrics": analysis_context.get("metrics", {}),
        "warnings": analysis_context.get("warnings", []),
        "outputs": intermediate_outputs,
    }
