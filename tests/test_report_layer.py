from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from course_connector.report_layer import build_json_result, render_markdown_report, write_json_result


def test_markdown_report_groups_relations_by_type() -> None:
    report = render_markdown_report(
        _payload(),
        _analysis(),
        run_id="run_001",
        generated_at="2026-06-27T00:00:00+00:00",
    )

    assert "## Analysis Summary" in report
    assert "## Useful Repetitions" in report
    assert "## Probable Duplications" in report
    assert "## Probable Gaps" in report
    assert "## Warnings" in report
    assert "## Source Files" in report
    assert "`useful_repetition` confidence 0.80" in report
    assert "`probable_duplication` confidence 0.60" in report
    assert "`probable_gap` confidence 0.50" in report
    assert "- Course A: `course_a.yaml` (yaml)" in report
    assert "- Course B: `course_b.yaml` (yaml)" in report
    assert "Provider warning" in report


def test_markdown_report_prints_human_readable_evidence_refs() -> None:
    analysis = _analysis()
    analysis["relations"][0]["evidence_refs"] = [
        {
            "chunk_id": "course_a_assessment_02",
            "source_role": "course_a",
            "source_path": "data/examples/course_a/course.yaml",
            "source_type": "assessment",
            "locator": {
                "kind": "object_path",
                "object_path": "assessments[1]",
            },
        },
        {
            "chunk_id": "assessments_row_003",
            "source_role": "assessments",
            "source_path": "data/examples/assessments.csv",
            "source_type": "row",
            "locator": {
                "kind": "row_index",
                "row_index": 3,
            },
        },
    ]

    report = render_markdown_report(
        _payload(),
        analysis,
        run_id="run_001",
        generated_at="2026-06-27T00:00:00+00:00",
    )

    assert "  - Evidence:" in report
    assert "`course_a` `assessment` `course_a_assessment_02`: `data/examples/course_a/course.yaml` -> `assessments[1]`" in report
    assert "`assessments` `row` `assessments_row_003`: `data/examples/assessments.csv` -> `row 3`" in report


def test_markdown_report_handles_string_evidence_refs() -> None:
    analysis = _analysis()
    analysis["relations"][0]["evidence_refs"] = ["retrieved_001"]

    report = render_markdown_report(
        _payload(),
        analysis,
        run_id="run_001",
        generated_at="2026-06-27T00:00:00+00:00",
    )

    assert "    - `retrieved_001`" in report


def test_json_result_contains_relations_sources_and_run_metadata(tmp_path: Path) -> None:
    output_paths = {
        "report_md": tmp_path / "report.md",
        "result_json": tmp_path / "result.json",
    }

    result = build_json_result(
        _payload(),
        _analysis(),
        output_paths,
        run_id="run_001",
        generated_at="2026-06-27T00:00:00+00:00",
    )
    write_json_result(output_paths["result_json"], result)

    saved = json.loads(output_paths["result_json"].read_text(encoding="utf-8"))
    assert saved["run_id"] == "run_001"
    assert saved["generated_at"] == "2026-06-27T00:00:00+00:00"
    assert saved["relations"] == _analysis()["relations"]
    assert saved["warnings"] == ["Provider warning"]
    assert saved["inputs"]["course_a"]["source_path"] == "course_a.yaml"
    assert saved["inputs"]["course_b"]["source_path"] == "course_b.yaml"
    assert saved["outputs"]["report_md"] == str(output_paths["report_md"])
    assert saved["outputs"]["result_json"] == str(output_paths["result_json"])


def _payload() -> dict[str, object]:
    return {
        "course_a": {"source_path": "course_a.yaml", "format": "yaml"},
        "course_b": {"source_path": "course_b.yaml", "format": "yaml"},
        "skill_dictionary": {"source_path": "skills.yaml", "format": "yaml"},
        "assessments": {"source_path": "assessments.csv", "format": "csv"},
        "config": None,
        "warnings": [],
    }


def _analysis() -> dict[str, object]:
    return {
        "summary": "Report summary",
        "relations": [
            {
                "type": "useful_repetition",
                "course_a_fragment": "A repeated skill",
                "course_b_fragment": "B applies skill",
                "explanation": "Useful repeat",
                "confidence": 0.8,
            },
            {
                "type": "probable_duplication",
                "course_a_fragment": "A duplicate",
                "course_b_fragment": "B duplicate",
                "explanation": "Likely duplicate",
                "confidence": 0.6,
            },
            {
                "type": "probable_gap",
                "course_a_fragment": "A weak prep",
                "course_b_fragment": "B expects skill",
                "explanation": "Likely gap",
                "confidence": 0.5,
            },
        ],
        "warnings": ["Provider warning"],
        "provider": "static",
        "provider_mode": "test",
    }
