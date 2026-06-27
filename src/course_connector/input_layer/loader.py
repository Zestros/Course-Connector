"""Load and normalize MVP input files for Course Connector."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class InputLayerError(ValueError):
    """Raised when an MVP input file cannot be loaded."""


@dataclass(frozen=True)
class InputRole:
    """Validation and parsing rules for one input role."""

    name: str
    path: Path | None
    allowed_suffixes: tuple[str, ...]
    required: bool = True


TEXT_ROLES = {"course_a", "course_b", "assessments"}


def load_input_payload(
    *,
    course_a: Path,
    course_b: Path,
    skill_dictionary: Path,
    assessments: Path,
    config: Path | None = None,
) -> dict[str, Any]:
    """Load all MVP input files into one payload for the next pipeline layer."""
    warnings: list[str] = []
    roles = (
        InputRole("course_a", course_a, (".md", ".yaml", ".yml")),
        InputRole("course_b", course_b, (".md", ".yaml", ".yml")),
        InputRole("skill_dictionary", skill_dictionary, (".yaml", ".yml", ".json")),
        InputRole("assessments", assessments, (".md", ".yaml", ".yml", ".csv")),
        InputRole("config", config, (".yaml", ".yml"), required=False),
    )

    payload: dict[str, Any] = {"warnings": warnings}
    for role in roles:
        payload[role.name] = _load_role(role, warnings)
    return payload


def _load_role(role: InputRole, warnings: list[str]) -> dict[str, Any] | None:
    if role.path is None:
        if role.required:
            raise InputLayerError(f"Input `{role.name}` is required.")
        warnings.append("Optional input `config` was not provided.")
        return None

    if not role.path.is_file():
        raise InputLayerError(f"Input `{role.name}` file not found: {role.path}")

    suffix = role.path.suffix.lower()
    if suffix not in role.allowed_suffixes:
        allowed = ", ".join(role.allowed_suffixes)
        raise InputLayerError(
            f"Input `{role.name}` has unsupported extension `{suffix}` for {role.path}. "
            f"Allowed extensions: {allowed}."
        )

    file_format = _format_from_suffix(suffix)
    raw_text = role.path.read_text(encoding="utf-8")
    if not raw_text.strip():
        warnings.append(f"Input `{role.name}` is empty: {role.path}")

    entry: dict[str, Any] = {
        "source_path": str(role.path),
        "format": file_format,
        "raw_text": raw_text,
    }

    if file_format == "markdown":
        entry["normalized_text"] = _normalize_text(raw_text)
        return entry

    if file_format == "yaml":
        entry["parsed_data"] = _parse_yaml(raw_text, role)
        if role.name in {"course_a", "course_b"}:
            entry["normalized_text"] = _normalize_text(raw_text)
        return entry

    if file_format == "json":
        entry["parsed_data"] = _parse_json(raw_text, role)
        return entry

    if file_format == "csv":
        rows = _parse_csv(raw_text, role)
        entry["parsed_data"] = rows
        entry["normalized_text"] = _normalize_text(raw_text)
        if not rows:
            warnings.append(f"Assessment materials are empty: {role.path}")
        return entry

    raise InputLayerError(f"Input `{role.name}` has unsupported format: {file_format}")


def _format_from_suffix(suffix: str) -> str:
    if suffix == ".md":
        return "markdown"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    if suffix == ".json":
        return "json"
    if suffix == ".csv":
        return "csv"
    return suffix.lstrip(".")


def _parse_yaml(raw_text: str, role: InputRole) -> Any:
    if not raw_text.strip():
        return {}
    try:
        parsed = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise InputLayerError(f"Input `{role.name}` has invalid YAML: {role.path}") from exc
    return {} if parsed is None else parsed


def _parse_json(raw_text: str, role: InputRole) -> Any:
    if not raw_text.strip():
        return {}
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise InputLayerError(f"Input `{role.name}` has invalid JSON: {role.path}") from exc


def _parse_csv(raw_text: str, role: InputRole) -> list[dict[str, str]]:
    if not raw_text.strip():
        return []
    reader = csv.DictReader(raw_text.splitlines())
    if reader.fieldnames is None:
        raise InputLayerError(f"Input `{role.name}` has invalid CSV headers: {role.path}")
    return [dict(row) for row in reader]


def _normalize_text(text: str) -> str:
    normalized_lines = [" ".join(line.rstrip().split()) for line in text.splitlines()]
    collapsed: list[str] = []
    blank_count = 0
    for line in normalized_lines:
        if line:
            blank_count = 0
            collapsed.append(line)
            continue
        blank_count += 1
        if blank_count <= 2:
            collapsed.append("")
    return "\n".join(collapsed).strip()
