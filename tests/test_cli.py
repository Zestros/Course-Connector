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
    course_a = _write(tmp_path / "course_a.md", _valid_course_markdown("Course A", "cli_tools"))
    course_b = _write(tmp_path / "course_b.yaml", _valid_course_yaml("Course B", "cli_tools"))
    skill_dictionary = _write(tmp_path / "skill_dictionary.yaml", _valid_skill_dictionary("cli_tools"))
    assessments = _write(tmp_path / "assessments.csv", "course_id,title,skill_id\ncourse_b,CLI task,cli_tools\n")
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
    report = (output_dir / "report.md").read_text(encoding="utf-8")
    assert result["summary"]
    assert result["relations"]
    assert result["warnings"] == []
    assert result["provider_mode"] == "mock"
    assert result["inputs"]["skill_dictionary"]["source_path"] == str(skill_dictionary)
    assert result["inputs"]["assessments"]["format"] == "csv"
    assert "## Analysis Summary" in report
    assert "## Relations" in report
    assert "useful_repetition" in report


def test_run_command_allows_omitted_config(tmp_path: Path) -> None:
    course_a = _write(tmp_path / "course_a.md", _valid_course_markdown("Course A", "cli_tools"))
    course_b = _write(tmp_path / "course_b.yaml", _valid_course_yaml("Course B", "cli_tools"))
    skill_dictionary = _write(tmp_path / "skill_dictionary.yaml", _valid_skill_dictionary("cli_tools"))
    assessments = _write(tmp_path / "assessments.md", "# Assessments\n\nCLI task checks cli_tools.\n")
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


def test_run_command_stops_before_pipeline_when_course_template_is_invalid(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_run_pipeline(*args: object, **kwargs: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("pipeline should not run for invalid input")

    monkeypatch.setattr("course_connector.cli.run_pipeline", fake_run_pipeline)

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "run",
                "--course-a",
                str(_write(tmp_path / "course_a.md", "# Course A\n")),
                "--course-b",
                str(_write(tmp_path / "course_b.yaml", _valid_course_yaml("Course B", "cli_tools"))),
                "--skill-dictionary",
                str(_write(tmp_path / "skill_dictionary.yaml", _valid_skill_dictionary("cli_tools"))),
                "--assessments",
                str(_write(tmp_path / "assessments.csv", "course_id,title,skill_id\ncourse_b,CLI task,cli_tools\n")),
                "--output-dir",
                str(tmp_path / "outputs"),
            ]
        )

    assert exc_info.value.code == 2
    assert called is False
    assert "Input preflight validation failed" in capsys.readouterr().err


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


def _valid_skill_dictionary(skill_id: str) -> str:
    return f"""
skills:
  - id: {skill_id}
    title: {skill_id}
"""


def _valid_course_yaml(title: str, skill_id: str) -> str:
    return f"""
title: {title}
description: Course description.
topics:
  - CLI tools
learning_outcomes:
  - text: Use {skill_id} in a practical task.
    skills:
      - {skill_id}
competencies:
  - {skill_id}
modules:
  - id: module_01
    title: Module
    description: Module description.
    skills:
      - {skill_id}
assessments:
  - id: assessment_01
    title: CLI task
    checked_skills:
      - {skill_id}
    evidence: Student submits a working CLI run log.
"""


def _valid_course_markdown(title: str, skill_id: str) -> str:
    return f"""# {title}

## Description

Course description with {skill_id}.

## Topics

- CLI tools

## Learning Outcomes

- Use {skill_id} in a practical task.

## Competencies

- {skill_id}

## Assessments

- CLI task checks {skill_id}.

## Evidence

- Student submits a working CLI run log for {skill_id}.
"""
