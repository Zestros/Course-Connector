from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from course_connector.cli import main


def test_run_command_creates_expected_outputs(tmp_path: Path) -> None:
    course_a = _write(tmp_path / "course_a.md", "# Course A\n")
    course_b = _write(tmp_path / "course_b.yaml", "title: Course B\n")
    skill_dictionary = _write(tmp_path / "skill_dictionary.yaml", "skills: []\n")
    assessments = _write(tmp_path / "assessments.csv", "course_id,title\ncourse_b,CLI task\n")
    config = _write(tmp_path / "config.yaml", "include_summary: true\n")
    output_dir = tmp_path / "outputs"

    exit_code = main(
        [
            "run",
            "--course-a",
            str(course_a),
            "--course-b",
            str(course_b),
            "--skill-dictionary",
            str(skill_dictionary),
            "--assessments",
            str(assessments),
            "--config",
            str(config),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert (output_dir / "report.md").is_file()
    assert (output_dir / "result.json").is_file()
    assert sorted(path.name for path in output_dir.iterdir()) == ["report.md", "result.json"]
    result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
    assert result["inputs"]["skill_dictionary"]["source_path"] == str(skill_dictionary)
    assert result["inputs"]["assessments"]["format"] == "csv"


def test_run_command_allows_omitted_config(tmp_path: Path) -> None:
    course_a = _write(tmp_path / "course_a.md", "# Course A\n")
    course_b = _write(tmp_path / "course_b.yaml", "title: Course B\n")
    skill_dictionary = _write(tmp_path / "skill_dictionary.yaml", "skills: []\n")
    assessments = _write(tmp_path / "assessments.md", "# Assessments\n")
    output_dir = tmp_path / "outputs"

    exit_code = main(
        [
            "run",
            "--course-a",
            str(course_a),
            "--course-b",
            str(course_b),
            "--skill-dictionary",
            str(skill_dictionary),
            "--assessments",
            str(assessments),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
    assert result["inputs"]["config"] is None
    assert "Optional input `config` was not provided." in result["warnings"]


def test_run_command_errors_when_required_file_is_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    course_b = _write(tmp_path / "course_b.yaml", "title: Course B\n")
    skill_dictionary = _write(tmp_path / "skill_dictionary.yaml", "skills: []\n")
    assessments = _write(tmp_path / "assessments.md", "# Assessments\n")

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "run",
                "--course-a",
                str(tmp_path / "missing.md"),
                "--course-b",
                str(course_b),
                "--skill-dictionary",
                str(skill_dictionary),
                "--assessments",
                str(assessments),
                "--output-dir",
                str(tmp_path / "outputs"),
            ]
        )

    assert exc_info.value.code == 2
    error_output = capsys.readouterr().err
    assert "Input `course_a` file not found" in error_output
    assert "missing.md" in error_output


def test_run_command_errors_when_config_is_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    course_a = _write(tmp_path / "course_a.md", "# Course A\n")
    course_b = _write(tmp_path / "course_b.yaml", "title: Course B\n")
    skill_dictionary = _write(tmp_path / "skill_dictionary.yaml", "skills: []\n")
    assessments = _write(tmp_path / "assessments.md", "# Assessments\n")

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "run",
                "--course-a",
                str(course_a),
                "--course-b",
                str(course_b),
                "--skill-dictionary",
                str(skill_dictionary),
                "--assessments",
                str(assessments),
                "--config",
                str(tmp_path / "missing.yaml"),
                "--output-dir",
                str(tmp_path / "outputs"),
            ]
        )

    assert exc_info.value.code == 2
    assert "Input `config` file not found" in capsys.readouterr().err


def test_run_command_errors_when_extension_is_unsupported(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    course_a = _write(tmp_path / "course_a.txt", "Course A\n")
    course_b = _write(tmp_path / "course_b.yaml", "title: Course B\n")
    skill_dictionary = _write(tmp_path / "skill_dictionary.yaml", "skills: []\n")
    assessments = _write(tmp_path / "assessments.md", "# Assessments\n")

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "run",
                "--course-a",
                str(course_a),
                "--course-b",
                str(course_b),
                "--skill-dictionary",
                str(skill_dictionary),
                "--assessments",
                str(assessments),
                "--output-dir",
                str(tmp_path / "outputs"),
            ]
        )

    assert exc_info.value.code == 2
    error_output = capsys.readouterr().err
    assert "Input `course_a` has unsupported extension" in error_output
    assert ".md, .yaml, .yml" in error_output


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path
