from __future__ import annotations

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
    mapping = _write(tmp_path / "mapping.json", "{}\n")
    source_pack = _write(tmp_path / "source_pack.csv", "kind,title\n")
    config = _write(tmp_path / "config.yaml", "include_summary: true\n")
    output_dir = tmp_path / "outputs"

    exit_code = main(
        [
            "run",
            "--course-a",
            str(course_a),
            "--course-b",
            str(course_b),
            "--mapping",
            str(mapping),
            "--source-pack",
            str(source_pack),
            "--config",
            str(config),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert (output_dir / "report.md").is_file()
    assert (output_dir / "summary.json").is_file()
    assert sorted(path.name for path in output_dir.iterdir()) == ["report.md", "summary.json"]


def test_run_command_allows_omitted_config(tmp_path: Path) -> None:
    course_a = _write(tmp_path / "course_a.md", "# Course A\n")
    course_b = _write(tmp_path / "course_b.yaml", "title: Course B\n")
    mapping = _write(tmp_path / "mapping.json", "{}\n")
    source_pack = _write(tmp_path / "source_pack.csv", "kind,title\n")
    output_dir = tmp_path / "outputs"

    exit_code = main(
        [
            "run",
            "--course-a",
            str(course_a),
            "--course-b",
            str(course_b),
            "--mapping",
            str(mapping),
            "--source-pack",
            str(source_pack),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert (output_dir / "report.md").is_file()
    assert (output_dir / "summary.json").is_file()


def test_run_command_errors_when_required_file_is_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    course_b = _write(tmp_path / "course_b.yaml", "title: Course B\n")
    mapping = _write(tmp_path / "mapping.json", "{}\n")
    source_pack = _write(tmp_path / "source_pack.csv", "kind,title\n")

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "run",
                "--course-a",
                str(tmp_path / "missing.md"),
                "--course-b",
                str(course_b),
                "--mapping",
                str(mapping),
                "--source-pack",
                str(source_pack),
                "--output-dir",
                str(tmp_path / "outputs"),
            ]
        )

    assert exc_info.value.code == 2
    assert "--course-a file not found" in capsys.readouterr().err


def test_run_command_errors_when_config_is_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    course_a = _write(tmp_path / "course_a.md", "# Course A\n")
    course_b = _write(tmp_path / "course_b.yaml", "title: Course B\n")
    mapping = _write(tmp_path / "mapping.json", "{}\n")
    source_pack = _write(tmp_path / "source_pack.csv", "kind,title\n")

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "run",
                "--course-a",
                str(course_a),
                "--course-b",
                str(course_b),
                "--mapping",
                str(mapping),
                "--source-pack",
                str(source_pack),
                "--config",
                str(tmp_path / "missing.yaml"),
                "--output-dir",
                str(tmp_path / "outputs"),
            ]
        )

    assert exc_info.value.code == 2
    assert "--config file not found" in capsys.readouterr().err


def test_run_command_errors_when_extension_is_unsupported(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    course_a = _write(tmp_path / "course_a.txt", "Course A\n")
    course_b = _write(tmp_path / "course_b.yaml", "title: Course B\n")
    mapping = _write(tmp_path / "mapping.json", "{}\n")
    source_pack = _write(tmp_path / "source_pack.csv", "kind,title\n")

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "run",
                "--course-a",
                str(course_a),
                "--course-b",
                str(course_b),
                "--mapping",
                str(mapping),
                "--source-pack",
                str(source_pack),
                "--output-dir",
                str(tmp_path / "outputs"),
            ]
        )

    assert exc_info.value.code == 2
    error_output = capsys.readouterr().err
    assert "--course-a has unsupported file extension" in error_output
    assert ".md, .yaml" in error_output


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path
