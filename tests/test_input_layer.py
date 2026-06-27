from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from course_connector.input_layer import InputLayerError, load_input_payload


def test_load_input_payload_loads_full_mvp_input_set(tmp_path: Path) -> None:
    course_a = _write(tmp_path / "course_a.md", "# Course A  \n\n\n## Topics\n\nPython basics\n")
    course_b = _write(tmp_path / "course_b.yaml", "title: Course B\ntopics:\n  - CLI tools\n")
    skill_dictionary = _write(tmp_path / "skill_dictionary.json", '{"skills": [{"id": "cli_tools"}]}\n')
    assessments = _write(tmp_path / "assessments.csv", "course_id,title\ncourse_b,CLI task\n")
    config = _write(tmp_path / "config.yaml", "output_language: ru\n")

    payload = load_input_payload(
        course_a=course_a,
        course_b=course_b,
        skill_dictionary=skill_dictionary,
        assessments=assessments,
        config=config,
    )

    assert sorted(payload.keys()) == [
        "assessments",
        "config",
        "course_a",
        "course_b",
        "skill_dictionary",
        "warnings",
    ]
    assert payload["course_a"]["source_path"] == str(course_a)
    assert payload["course_a"]["format"] == "markdown"
    assert payload["course_a"]["raw_text"].startswith("# Course A")
    assert payload["course_a"]["normalized_text"] == "# Course A\n\n\n## Topics\n\nPython basics"
    assert payload["course_b"]["format"] == "yaml"
    assert payload["course_b"]["parsed_data"]["title"] == "Course B"
    assert payload["course_b"]["normalized_text"].startswith("title: Course B")
    assert payload["skill_dictionary"]["format"] == "json"
    assert payload["skill_dictionary"]["parsed_data"]["skills"][0]["id"] == "cli_tools"
    assert payload["assessments"]["format"] == "csv"
    assert payload["assessments"]["parsed_data"] == [{"course_id": "course_b", "title": "CLI task"}]
    assert payload["assessments"]["normalized_text"].startswith("course_id,title")
    assert payload["config"]["parsed_data"]["output_language"] == "ru"
    assert payload["warnings"] == []


def test_load_input_payload_warns_when_config_is_omitted(tmp_path: Path) -> None:
    payload = load_input_payload(
        course_a=_write(tmp_path / "course_a.md", "# Course A\n"),
        course_b=_write(tmp_path / "course_b.yaml", "title: Course B\n"),
        skill_dictionary=_write(tmp_path / "skill_dictionary.yaml", "skills: []\n"),
        assessments=_write(tmp_path / "assessments.md", "# Assessments\n"),
    )

    assert payload["config"] is None
    assert "Optional input `config` was not provided." in payload["warnings"]


def test_load_input_payload_errors_when_required_file_is_missing(tmp_path: Path) -> None:
    with pytest.raises(InputLayerError) as exc_info:
        load_input_payload(
            course_a=tmp_path / "missing.md",
            course_b=_write(tmp_path / "course_b.yaml", "title: Course B\n"),
            skill_dictionary=_write(tmp_path / "skill_dictionary.yaml", "skills: []\n"),
            assessments=_write(tmp_path / "assessments.md", "# Assessments\n"),
        )

    assert "course_a" in str(exc_info.value)
    assert "missing.md" in str(exc_info.value)


def test_load_input_payload_errors_when_format_is_unsupported(tmp_path: Path) -> None:
    with pytest.raises(InputLayerError) as exc_info:
        load_input_payload(
            course_a=_write(tmp_path / "course_a.txt", "Course A\n"),
            course_b=_write(tmp_path / "course_b.yaml", "title: Course B\n"),
            skill_dictionary=_write(tmp_path / "skill_dictionary.yaml", "skills: []\n"),
            assessments=_write(tmp_path / "assessments.md", "# Assessments\n"),
        )

    message = str(exc_info.value)
    assert "course_a" in message
    assert "unsupported extension" in message
    assert ".md, .yaml, .yml" in message


def test_load_input_payload_warns_for_empty_csv_assessments(tmp_path: Path) -> None:
    payload = load_input_payload(
        course_a=_write(tmp_path / "course_a.md", "# Course A\n"),
        course_b=_write(tmp_path / "course_b.yaml", "title: Course B\n"),
        skill_dictionary=_write(tmp_path / "skill_dictionary.yaml", "skills: []\n"),
        assessments=_write(tmp_path / "assessments.csv", "course_id,title\n"),
    )

    assert payload["assessments"]["parsed_data"] == []
    assert any("Assessment materials are empty" in warning for warning in payload["warnings"])


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path
