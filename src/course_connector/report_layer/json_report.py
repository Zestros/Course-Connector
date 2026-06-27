"""Build and write machine-readable Course Connector reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


INPUT_ROLES = ("course_a", "course_b", "skill_dictionary", "assessments", "config")


def build_json_result(
    input_payload: dict[str, Any],
    analysis: dict[str, Any],
    output_paths: dict[str, Path],
    *,
    run_id: str,
    generated_at: str,
) -> dict[str, Any]:
    """Build the stable MVP JSON result object."""
    return {
        "status": "completed",
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
