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
    course_a = _write(tmp_path / "course_a.md", _valid_course_markdown("Course A", "cli_tools"))
    course_b = _write(tmp_path / "course_b.yaml", _valid_course_yaml("Course B", "cli_tools"))
    skill_dictionary = _write(tmp_path / "skill_dictionary.json", '{"skills": [{"id": "cli_tools"}]}\n')
    assessments = _write(tmp_path / "assessments.csv", "course_id,title,skill_id\ncourse_b,CLI task,cli_tools\n")
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
    assert "## Topics" in payload["course_a"]["normalized_text"]
    assert payload["course_b"]["format"] == "yaml"
    assert payload["course_b"]["parsed_data"]["title"] == "Course B"
    assert payload["course_b"]["normalized_text"].startswith("title: Course B")
    assert payload["skill_dictionary"]["format"] == "json"
    assert payload["skill_dictionary"]["parsed_data"]["skills"][0]["id"] == "cli_tools"
    assert payload["assessments"]["format"] == "csv"
    assert payload["assessments"]["parsed_data"] == [{"course_id": "course_b", "title": "CLI task", "skill_id": "cli_tools"}]
    assert payload["assessments"]["normalized_text"].startswith("course_id,title")
    assert payload["config"]["parsed_data"]["output_language"] == "ru"
    assert payload["warnings"] == []


def test_load_input_payload_warns_when_config_is_omitted(tmp_path: Path) -> None:
    payload = load_input_payload(
        course_a=_write(tmp_path / "course_a.md", _valid_course_markdown("Course A", "cli_tools")),
        course_b=_write(tmp_path / "course_b.yaml", _valid_course_yaml("Course B", "cli_tools")),
        skill_dictionary=_write(tmp_path / "skill_dictionary.yaml", _valid_skill_dictionary("cli_tools")),
        assessments=_write(tmp_path / "assessments.md", "# Assessments\n\nCLI task checks cli_tools.\n"),
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


def test_load_input_payload_errors_for_empty_csv_assessments(tmp_path: Path) -> None:
    with pytest.raises(InputLayerError) as exc_info:
        load_input_payload(
            course_a=_write(tmp_path / "course_a.md", _valid_course_markdown("Course A", "cli_tools")),
            course_b=_write(tmp_path / "course_b.yaml", _valid_course_yaml("Course B", "cli_tools")),
            skill_dictionary=_write(tmp_path / "skill_dictionary.yaml", _valid_skill_dictionary("cli_tools")),
            assessments=_write(tmp_path / "assessments.csv", "course_id,title,skill_id\n"),
        )

    assert "assessments" in str(exc_info.value)
    assert "at least one assessment row" in str(exc_info.value)


def test_load_input_payload_rejects_course_before_processing_when_template_is_missing(tmp_path: Path) -> None:
    with pytest.raises(InputLayerError) as exc_info:
        load_input_payload(
            course_a=_write(tmp_path / "course_a.md", "# Course A\n"),
            course_b=_write(tmp_path / "course_b.yaml", _valid_course_yaml("Course B", "cli_tools")),
            skill_dictionary=_write(tmp_path / "skill_dictionary.yaml", _valid_skill_dictionary("cli_tools")),
            assessments=_write(tmp_path / "assessments.csv", "course_id,title,skill_id\ncourse_b,CLI task,cli_tools\n"),
        )

    message = str(exc_info.value)
    assert "Input preflight validation failed" in message
    assert "course_a" in message
    assert "description" in message
    assert "learning_outcomes" in message


def test_load_input_payload_rejects_unknown_course_skill_refs(tmp_path: Path) -> None:
    with pytest.raises(InputLayerError) as exc_info:
        load_input_payload(
            course_a=_write(tmp_path / "course_a.yaml", _valid_course_yaml("Course A", "missing_skill")),
            course_b=_write(tmp_path / "course_b.yaml", _valid_course_yaml("Course B", "cli_tools")),
            skill_dictionary=_write(tmp_path / "skill_dictionary.yaml", _valid_skill_dictionary("cli_tools")),
            assessments=_write(tmp_path / "assessments.csv", "course_id,title,skill_id\ncourse_b,CLI task,cli_tools\n"),
        )

    assert "unknown skill ids: missing_skill" in str(exc_info.value)


def test_big_course_example_passes_input_preflight_validation() -> None:
    example_dir = PROJECT_ROOT / "data" / "examples" / "big_course"

    payload = load_input_payload(
        course_a=example_dir / "course_git.md",
        course_b=example_dir / "course_github.md",
        skill_dictionary=example_dir / "skill_dictionary.yaml",
        assessments=example_dir / "assessments.md",
    )

    assert payload["course_a"]["format"] == "markdown"
    assert payload["course_b"]["format"] == "markdown"
    assert "git_repository_model" in payload["course_a"]["normalized_text"]
    assert "github_pull_request_workflow" in payload["course_b"]["normalized_text"]


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
