"""Build deterministic course profiles for smart batch analysis."""

from __future__ import annotations

from typing import Any


PROFILE_TITLES = {
    "description": {"description", "описание", "описание курса"},
    "goals": {"goals", "цели", "цели курса"},
    "topics": {"topics", "темы", "модуль", "modules"},
    "assessments": {"assessments", "оценивание", "задания", "итоговый проект"},
    "prerequisites": {"prerequisites", "предпосылки", "требования"},
    "excluded_topics": {"excluded topics", "не является", "не обучает"},
}


def build_course_profiles(
    input_payload: dict[str, Any],
    chunks: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Build compact course profiles from loaded inputs and chunks."""
    warnings: list[str] = []
    profiles = {
        "course_a": _course_profile("course_a", input_payload.get("course_a"), chunks.get("course_a", []), warnings),
        "course_b": _course_profile("course_b", input_payload.get("course_b"), chunks.get("course_b", []), warnings),
    }
    return profiles, warnings


def _course_profile(
    role: str,
    entry: Any,
    course_chunks: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    source_path = entry.get("source_path") if isinstance(entry, dict) else None
    source_format = entry.get("format") if isinstance(entry, dict) else None
    data = entry.get("parsed_data") if isinstance(entry, dict) else None
    profile = {
        "source_role": role,
        "source_path": source_path,
        "source_format": source_format,
        "title": _title_from_entry(entry, role),
        "description": "",
        "goals": [],
        "topics": [],
        "assessment_overview": [],
        "prerequisites": [],
        "excluded_topics": [],
        "profile_chunk_ids": [],
        "coarse": False,
    }
    if isinstance(data, dict):
        profile.update(_yaml_profile_fields(data))

    for chunk in course_chunks:
        title = str(chunk.get("title") or "").strip()
        text = str(chunk.get("text") or "").strip()
        normalized_title = title.lower()
        bucket = _profile_bucket(normalized_title, text.lower())
        if bucket is None:
            continue
        profile["profile_chunk_ids"].append(chunk.get("chunk_id"))
        if bucket == "description" and not profile["description"]:
            profile["description"] = text
        elif bucket == "goals":
            profile["goals"].append(text)
        elif bucket == "topics":
            profile["topics"].append(text)
        elif bucket == "assessments":
            profile["assessment_overview"].append(text)
        elif bucket == "prerequisites":
            profile["prerequisites"].append(text)
        elif bucket == "excluded_topics":
            profile["excluded_topics"].append(text)

    if not profile["description"] and course_chunks:
        first = course_chunks[0]
        profile["description"] = str(first.get("text") or "")
        profile["profile_chunk_ids"].append(first.get("chunk_id"))
        profile["coarse"] = True
        warnings.append(f"coarse_profile: `{role}` profile was built from available chunks.")
    return profile


def _yaml_profile_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(data.get("title") or data.get("id") or ""),
        "description": str(data.get("description") or ""),
        "topics": [str(item.get("title") if isinstance(item, dict) else item) for item in data.get("topics", []) if item],
        "assessment_overview": [
            str(item.get("title") or item.get("id") or item)
            for item in data.get("assessments", [])
            if item
        ],
    }


def _title_from_entry(entry: Any, fallback: str) -> str:
    if not isinstance(entry, dict):
        return fallback
    data = entry.get("parsed_data")
    if isinstance(data, dict) and data.get("title"):
        return str(data["title"])
    text = str(entry.get("normalized_text") or entry.get("raw_text") or "")
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _profile_bucket(title: str, text: str) -> str | None:
    for bucket, aliases in PROFILE_TITLES.items():
        if any(alias in title for alias in aliases):
            return bucket
    if "не является основным предметом" in text or "не обучает" in text:
        return "excluded_topics"
    return None
