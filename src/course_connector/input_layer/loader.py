"""Load and normalize MVP input files for Course Connector."""

from __future__ import annotations

import csv
import json
import re
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
REQUIRED_MARKDOWN_SECTIONS = {
    "description": ("description", "описание"),
    "topics": ("topics", "темы"),
    "learning_outcomes": ("learning outcomes", "learning_outcomes", "результаты обучения"),
    "competencies": ("competencies", "компетенции"),
    "assessments": ("assessments", "оценивание", "задания"),
    "evidence": ("evidence", "доказательства", "свидетельства"),
}


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
    _validate_input_payload(payload)
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


def _validate_input_payload(payload: dict[str, Any]) -> None:
    skill_ids = _skill_dictionary_ids(payload.get("skill_dictionary"))
    errors: list[str] = []
    if not skill_ids:
        errors.append("Input `skill_dictionary` must define at least one skill with `id`.")
    for role in ("course_a", "course_b"):
        errors.extend(_validate_course_entry(role, payload.get(role), skill_ids))
    errors.extend(_validate_assessment_input(payload.get("assessments"), skill_ids))
    if errors:
        bullet_list = "\n".join(f"- {error}" for error in errors)
        raise InputLayerError(f"Input preflight validation failed:\n{bullet_list}")


def _skill_dictionary_ids(entry: Any) -> set[str]:
    if not isinstance(entry, dict):
        return set()
    parsed = entry.get("parsed_data")
    if not isinstance(parsed, dict):
        return set()
    skills = parsed.get("skills")
    if not isinstance(skills, list):
        return set()
    return {
        str(skill.get("id")).strip()
        for skill in skills
        if isinstance(skill, dict) and str(skill.get("id") or "").strip()
    }


def _validate_course_entry(role: str, entry: Any, skill_ids: set[str]) -> list[str]:
    if not isinstance(entry, dict):
        return [f"Input `{role}` must be provided."]
    if entry.get("format") == "yaml":
        return _validate_yaml_course(role, entry, skill_ids)
    if entry.get("format") == "markdown":
        return _validate_markdown_course(role, entry, skill_ids)
    return [f"Input `{role}` must be a Markdown or YAML course file."]


def _validate_yaml_course(role: str, entry: dict[str, Any], skill_ids: set[str]) -> list[str]:
    data = entry.get("parsed_data")
    if not isinstance(data, dict):
        return [f"Input `{role}` YAML course must be an object."]

    errors: list[str] = []
    for field in ("title", "description"):
        if not _has_text(data.get(field)):
            errors.append(f"Input `{role}` must include non-empty `{field}`.")
    for field in ("topics", "learning_outcomes", "assessments"):
        if not _has_non_empty_list(data.get(field)):
            errors.append(f"Input `{role}` must include non-empty `{field}`.")

    referenced_skills = _course_skill_refs(data)
    if not _has_non_empty_list(data.get("competencies")) and not referenced_skills:
        errors.append(
            f"Input `{role}` must include `competencies` or skill links in modules/outcomes/assessments."
        )
    if not _course_has_evidence(data):
        errors.append(f"Input `{role}` must include evidence in `evidence` or assessment evidence fields.")

    missing_skill_ids = sorted(referenced_skills - skill_ids)
    if missing_skill_ids:
        errors.append(
            f"Input `{role}` references unknown skill ids: {', '.join(missing_skill_ids)}."
        )
    if skill_ids and not referenced_skills:
        errors.append(f"Input `{role}` must link at least one course item to a known skill id.")
    elif skill_ids and not (referenced_skills & skill_ids):
        errors.append(f"Input `{role}` must reference at least one skill from `skill_dictionary`.")
    return errors


def _validate_markdown_course(role: str, entry: dict[str, Any], skill_ids: set[str]) -> list[str]:
    text = str(entry.get("normalized_text") or entry.get("raw_text") or "")
    errors: list[str] = []
    if not re.search(r"(?m)^#\s+\S+", text):
        errors.append(f"Input `{role}` Markdown course must start with a title heading.")
    headings = _markdown_headings(text)
    for field, aliases in REQUIRED_MARKDOWN_SECTIONS.items():
        if not any(alias in headings for alias in aliases):
            errors.append(f"Input `{role}` Markdown course must include a `{field}` section.")

    referenced_skills = {skill_id for skill_id in skill_ids if re.search(rf"\b{re.escape(skill_id)}\b", text)}
    if skill_ids and not referenced_skills:
        errors.append(f"Input `{role}` Markdown course must mention at least one skill id from `skill_dictionary`.")
    return errors


def _validate_assessment_input(entry: Any, skill_ids: set[str]) -> list[str]:
    if not isinstance(entry, dict):
        return ["Input `assessments` must be provided."]
    if entry.get("format") == "csv":
        rows = entry.get("parsed_data")
        if not isinstance(rows, list) or not rows:
            return ["Input `assessments` CSV must include at least one assessment row."]
        referenced = {
            value
            for row in rows
            if isinstance(row, dict)
            for value in _skill_values(row)
        }
        if skill_ids and not (referenced & skill_ids):
            return ["Input `assessments` must reference at least one skill id from `skill_dictionary`."]
    elif not _has_text(entry.get("raw_text")):
        return ["Input `assessments` must include assessment evidence text."]
    return []


def _course_skill_refs(data: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for key in ("skills", "skill_ids", "checked_skills", "competencies"):
        refs.update(_string_values(data.get(key)))
    for collection_name in ("topics", "modules", "learning_outcomes", "assessments", "evidence"):
        collection = data.get(collection_name)
        if not isinstance(collection, list):
            continue
        for item in collection:
            if isinstance(item, dict):
                for key in ("skills", "skill_ids", "skill_id", "checked_skills", "competencies", "competency_ids"):
                    refs.update(_string_values(item.get(key)))
    return refs


def _course_has_evidence(data: dict[str, Any]) -> bool:
    if _has_non_empty_list(data.get("evidence")) or _has_text(data.get("evidence")):
        return True
    assessments = data.get("assessments")
    if not isinstance(assessments, list):
        return False
    for assessment in assessments:
        if isinstance(assessment, dict) and (
            _has_text(assessment.get("evidence"))
            or _has_text(assessment.get("description"))
            or _has_text(assessment.get("task"))
            or _has_text(assessment.get("rubric"))
        ):
            return True
    return False


def _skill_values(row: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for key in ("skill_id", "skill", "skills", "skill_ids", "checked_skills", "competency_id", "competencies"):
        values.update(_string_values(row.get(key)))
    return values


def _string_values(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        return {item for element in value for item in _string_values(element)}
    if isinstance(value, dict):
        return {item for element in value.values() for item in _string_values(element)}
    return {
        part.strip()
        for part in re.split(r"[,;\s]+", str(value))
        if part.strip()
    }


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _has_non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value)


def _markdown_headings(text: str) -> set[str]:
    headings = set()
    for match in re.finditer(r"(?m)^#{2,6}\s+(.+?)\s*$", text):
        heading = re.sub(r"[_-]+", " ", match.group(1).strip().lower())
        headings.add(heading)
    return headings
