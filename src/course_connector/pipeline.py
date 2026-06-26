"""Minimal pipeline orchestration for course connector."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class PipelineInputs:
    """Validated input files for the pipeline."""

    course_a: Path
    course_b: Path
    mapping: Path
    source_pack: Path
    config: Path | None = None


@dataclass(frozen=True)
class PipelineResult:
    """Files produced by the pipeline."""

    report_md: Path
    summary_json: Path


def run_pipeline(inputs: PipelineInputs, output_dir: Path) -> PipelineResult:
    """Run a minimal local pipeline and write placeholder output files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    result = PipelineResult(
        report_md=output_dir / "report.md",
        summary_json=output_dir / "summary.json",
    )

    result.report_md.write_text(
        _build_markdown_report(inputs),
        encoding="utf-8",
    )
    result.summary_json.write_text(
        json.dumps(_build_summary(inputs, result), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return result


def _build_markdown_report(inputs: PipelineInputs) -> str:
    return (
        "# Course Connector Report\n\n"
        "Pipeline reached successfully.\n\n"
        "## Inputs\n\n"
        f"- Course A: `{inputs.course_a}`\n"
        f"- Course B: `{inputs.course_b}`\n"
        f"- Mapping: `{inputs.mapping}`\n"
        f"- Source pack: `{inputs.source_pack}`\n"
        f"- Config: `{inputs.config}`\n"
    )


def _build_summary(inputs: PipelineInputs, result: PipelineResult) -> dict[str, object]:
    return {
        "status": "completed",
        "inputs": {
            key: str(value) if value is not None else None
            for key, value in asdict(inputs).items()
        },
        "outputs": {
            "report_md": str(result.report_md),
            "summary_json": str(result.summary_json),
        },
    }
