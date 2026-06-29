"""Lightweight educational chunking for loaded input payloads."""

from __future__ import annotations

import re
from typing import Any

from course_connector.preprocessing_layer.config import ChunkingConfig
from course_connector.preprocessing_layer.evidence_refs import (
    coarse_file_locator,
    line_range_locator,
    object_path_locator,
    row_locator,
)


CHUNK_ROLES = ("course_a", "course_b", "skill_dictionary", "assessments")


def build_chunks(input_payload: dict[str, Any], config: ChunkingConfig) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Build chunks for all analysis inputs."""
    if not config.enabled:
        return {role: [] for role in CHUNK_ROLES}, []

    skill_index = _build_skill_index(input_payload.get("skill_dictionary"))
    warnings: list[str] = []
    chunks = {
        "course_a": _course_chunks("course_a", input_payload.get("course_a"), skill_index, config, warnings),
        "course_b": _course_chunks("course_b", input_payload.get("course_b"), skill_index, config, warnings),
        "skill_dictionary": _skill_chunks(input_payload.get("skill_dictionary"), skill_index, config),
        "assessments": _assessment_chunks(input_payload.get("assessments"), skill_index, config, warnings),
    }
    return chunks, warnings


def _course_chunks(
    role: str,
    entry: dict[str, Any] | None,
    skill_index: dict[str, dict[str, Any]],
    config: ChunkingConfig,
    warnings: list[str],
) -> list[dict[str, Any]]:
    if entry is None:
        return []
    parsed = entry.get("parsed_data")
    if entry.get("format") == "yaml" and isinstance(parsed, dict):
        return _course_yaml_chunks(role, entry, parsed, skill_index, config, warnings)
    return _markdown_chunks(role, entry, "raw_section", skill_index, config)


def _course_yaml_chunks(
    role: str,
    entry: dict[str, Any],
    data: dict[str, Any],
    skill_index: dict[str, dict[str, Any]],
    config: ChunkingConfig,
    warnings: list[str],
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    topics = data.get("topics") if isinstance(data.get("topics"), list) else []
    for index, topic in enumerate(topics, start=1):
        text = str(topic.get("title") if isinstance(topic, dict) else topic)
        skills = _infer_skill_ids(text, skill_index)
        chunks.extend(_entity_chunks(
            role=role,
            entry=entry,
            chunk_id=f"{role}_topic_{index:02d}",
            source_type="topic",
            parent_id=None,
            title=text,
            text=text,
            skill_ids=skills,
            locator=object_path_locator(f"topics[{index - 1}]"),
            config=config,
        ))

    modules = data.get("modules") if isinstance(data.get("modules"), list) else []
    for index, module in enumerate(modules, start=1):
        if not isinstance(module, dict):
            continue
        module_id = str(module.get("id") or f"module_{index:02d}")
        skills = _valid_skill_ids(module.get("skills") or [], skill_index)
        title = str(module.get("title") or module_id)
        text = _compact_text(" ".join([
            title,
            str(module.get("description") or ""),
            " ".join(_skill_titles(skills, skill_index)),
        ]))
        chunks.extend(_entity_chunks(
            role=role,
            entry=entry,
            chunk_id=f"{role}_{module_id}",
            source_type="module",
            parent_id=None,
            title=title,
            text=text,
            skill_ids=skills,
            locator=object_path_locator(f"modules[{index - 1}]"),
            config=config,
        ))

    outcomes = data.get("learning_outcomes") if isinstance(data.get("learning_outcomes"), list) else []
    for index, outcome in enumerate(outcomes, start=1):
        text = str(outcome.get("text") if isinstance(outcome, dict) else outcome)
        skills = _infer_skill_ids(text, skill_index)
        chunks.extend(_entity_chunks(
            role=role,
            entry=entry,
            chunk_id=f"{role}_outcome_{index:02d}",
            source_type="outcome",
            parent_id=None,
            title=_clip(_compact_text(text), 80),
            text=text,
            skill_ids=skills,
            locator=object_path_locator(f"learning_outcomes[{index - 1}]"),
            config=config,
        ))

    assessments = data.get("assessments") if isinstance(data.get("assessments"), list) else []
    for index, assessment in enumerate(assessments, start=1):
        if not isinstance(assessment, dict):
            continue
        title = str(assessment.get("title") or assessment.get("id") or f"assessment_{index:02d}")
        skills = _valid_skill_ids(assessment.get("checked_skills") or assessment.get("skills") or [], skill_index)
        text = _compact_text(f"{title} {' '.join(_skill_titles(skills, skill_index))}")
        chunks.extend(_entity_chunks(
            role=role,
            entry=entry,
            chunk_id=f"{role}_assessment_{index:02d}",
            source_type="assessment",
            parent_id=None,
            title=title,
            text=text,
            skill_ids=skills or _infer_skill_ids(text, skill_index),
            locator=object_path_locator(f"assessments[{index - 1}]"),
            config=config,
        ))

    if not chunks:
        warnings.append(f"Preprocessing used coarse chunking for `{role}` because structured course entities were not found.")
        chunks.append(_coarse_chunk(role, entry, skill_index, config))
    else:
        warnings.append(f"Preprocessing locators for YAML `{role}` use object paths rather than exact line ranges.")
    return chunks


def _assessment_chunks(
    entry: dict[str, Any] | None,
    skill_index: dict[str, dict[str, Any]],
    config: ChunkingConfig,
    warnings: list[str],
) -> list[dict[str, Any]]:
    if entry is None:
        return []
    if entry.get("format") == "csv":
        chunks = []
        rows = entry.get("parsed_data") if isinstance(entry.get("parsed_data"), list) else []
        for index, row in enumerate(rows, start=1):
            text = _compact_text(" ".join(str(value or "") for value in row.values()))
            title = str(row.get("title") or row.get("name") or f"Assessment row {index}")
            chunks.extend(_entity_chunks(
                role="assessments",
                entry=entry,
                chunk_id=f"assessments_row_{index:03d}",
                source_type="row",
                parent_id=None,
                title=title,
                text=text,
                skill_ids=_infer_skill_ids(text, skill_index),
                locator=row_locator(index),
                config=config,
            ))
        return chunks
    if entry.get("format") == "yaml" and isinstance(entry.get("parsed_data"), (dict, list)):
        warnings.append("Preprocessing locators for YAML `assessments` use object paths rather than exact line ranges.")
        return _structured_assessment_chunks(entry, skill_index, config)
    return _markdown_chunks("assessments", entry, "assessment", skill_index, config)


def _structured_assessment_chunks(
    entry: dict[str, Any],
    skill_index: dict[str, dict[str, Any]],
    config: ChunkingConfig,
) -> list[dict[str, Any]]:
    parsed = entry.get("parsed_data")
    items = parsed if isinstance(parsed, list) else parsed.get("assessments", []) if isinstance(parsed, dict) else []
    if not isinstance(items, list):
        return [_coarse_chunk("assessments", entry, skill_index, config)]
    chunks = []
    for index, item in enumerate(items, start=1):
        text = _compact_text(str(item))
        title = str(item.get("title") or f"Assessment {index}") if isinstance(item, dict) else f"Assessment {index}"
        chunks.extend(_entity_chunks(
            role="assessments",
            entry=entry,
            chunk_id=f"assessments_item_{index:03d}",
            source_type="assessment",
            parent_id=None,
            title=title,
            text=text,
            skill_ids=_infer_skill_ids(text, skill_index),
            locator=object_path_locator(f"assessments[{index - 1}]"),
            config=config,
        ))
    return chunks


def _markdown_chunks(
    role: str,
    entry: dict[str, Any],
    source_type: str,
    skill_index: dict[str, dict[str, Any]],
    config: ChunkingConfig,
) -> list[dict[str, Any]]:
    text = entry.get("normalized_text") or entry.get("raw_text") or ""
    sections = _markdown_sections(str(text))
    chunks = []
    for index, section in enumerate(sections, start=1):
        title = section["title"] or f"{role} section {index}"
        chunks.extend(_entity_chunks(
            role=role,
            entry=entry,
            chunk_id=f"{role}_section_{index:03d}",
            source_type=source_type,
            parent_id=None,
            title=title,
            text=section["text"],
            skill_ids=_infer_skill_ids(section["text"], skill_index),
            locator=line_range_locator(section["line_start"], section["line_end"]),
            config=config,
        ))
    return chunks or [_coarse_chunk(role, entry, skill_index, config)]


def _skill_chunks(
    entry: dict[str, Any] | None,
    skill_index: dict[str, dict[str, Any]],
    config: ChunkingConfig,
) -> list[dict[str, Any]]:
    if entry is None:
        return []
    chunks = []
    for index, (skill_id, skill) in enumerate(skill_index.items(), start=1):
        title = str(skill.get("title") or skill_id)
        text = _compact_text(" ".join([skill_id, title, " ".join(skill.get("aliases", []))]))
        chunks.extend(_entity_chunks(
            role="skill_dictionary",
            entry=entry,
            chunk_id=f"skill_{skill_id}",
            source_type="skill",
            parent_id=None,
            title=title,
            text=text,
            skill_ids=[skill_id],
            locator=object_path_locator(f"skills[{index - 1}]"),
            config=config,
        ))
    return chunks


def _chunk(
    *,
    role: str,
    entry: dict[str, Any],
    chunk_id: str,
    source_type: str,
    parent_id: str | None,
    title: str,
    text: str,
    skill_ids: list[str],
    locator: dict[str, Any],
    config: ChunkingConfig,
    chunk_index: int | None = None,
    split_strategy: str | None = None,
) -> dict[str, Any]:
    clean_text = _clip(_compact_text(text or title), config.max_chunk_chars)
    item = {
        "chunk_id": _safe_id(chunk_id),
        "source_role": role,
        "source_path": entry.get("source_path"),
        "source_format": entry.get("format"),
        "source_type": source_type,
        "parent_id": parent_id,
        "title": title,
        "text": clean_text,
        "skill_ids": skill_ids,
        "keywords": _keywords(f"{title} {clean_text} {' '.join(skill_ids)}"),
        "locator": locator,
    }
    if chunk_index is not None:
        item["chunk_index"] = chunk_index
    if split_strategy is not None:
        item["split_strategy"] = split_strategy
    return item


def _entity_chunks(
    *,
    role: str,
    entry: dict[str, Any],
    chunk_id: str,
    source_type: str,
    parent_id: str | None,
    title: str,
    text: str,
    skill_ids: list[str],
    locator: dict[str, Any],
    config: ChunkingConfig,
) -> list[dict[str, Any]]:
    compact = _compact_text(text or title)
    if len(compact) <= config.max_chunk_chars:
        return [_chunk(
            role=role,
            entry=entry,
            chunk_id=chunk_id,
            source_type=source_type,
            parent_id=parent_id,
            title=title,
            text=compact,
            skill_ids=skill_ids,
            locator=locator,
            config=config,
        )]

    parent_chunk_id = _safe_id(chunk_id)
    parts = _split_large_text(compact, config.max_chunk_chars, config.overlap_tokens * 3)
    return [
        _chunk(
            role=role,
            entry=entry,
            chunk_id=f"{parent_chunk_id}_part_{index:03d}",
            source_type=f"{source_type}_part",
            parent_id=parent_chunk_id,
            title=f"{title} part {index}",
            text=part_text,
            skill_ids=skill_ids or _infer_skill_ids(part_text, _build_skill_index(entry if role == "skill_dictionary" else None)),
            locator=locator,
            config=config,
            chunk_index=index,
            split_strategy=strategy,
        )
        for index, (part_text, strategy) in enumerate(parts, start=1)
    ]


def _coarse_chunk(
    role: str,
    entry: dict[str, Any],
    skill_index: dict[str, dict[str, Any]],
    config: ChunkingConfig,
) -> dict[str, Any]:
    text = entry.get("normalized_text") or entry.get("raw_text") or ""
    return _chunk(
        role=role,
        entry=entry,
        chunk_id=f"{role}_coarse_file",
        source_type="coarse_file",
        parent_id=None,
        title=role.replace("_", " ").title(),
        text=str(text),
        skill_ids=_infer_skill_ids(str(text), skill_index),
        locator=coarse_file_locator(),
        config=config,
    )


def _build_skill_index(entry: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    parsed = entry.get("parsed_data") if isinstance(entry, dict) else None
    data = parsed if isinstance(parsed, dict) else {}
    result = {}
    for skill in data.get("skills", []) if isinstance(data.get("skills"), list) else []:
        if not isinstance(skill, dict) or not skill.get("id"):
            continue
        skill_id = str(skill["id"])
        result[skill_id] = {
            "title": str(skill.get("title") or skill_id),
            "aliases": [str(alias) for alias in skill.get("aliases", []) or []],
        }
    return result


def _valid_skill_ids(skill_ids: Any, skill_index: dict[str, dict[str, Any]]) -> list[str]:
    result = []
    for skill_id in skill_ids if isinstance(skill_ids, list) else []:
        clean = str(skill_id)
        if clean in skill_index and clean not in result:
            result.append(clean)
    return result


def _infer_skill_ids(text: str, skill_index: dict[str, dict[str, Any]]) -> list[str]:
    lower = text.lower()
    result = []
    for skill_id, skill in skill_index.items():
        candidates = [skill_id, skill.get("title", ""), *skill.get("aliases", [])]
        if any(str(candidate).lower().strip() and str(candidate).lower().strip() in lower for candidate in candidates):
            result.append(skill_id)
    return result


def _skill_titles(skill_ids: list[str], skill_index: dict[str, dict[str, Any]]) -> list[str]:
    return [skill_index[skill_id]["title"] for skill_id in skill_ids if skill_id in skill_index]


def _markdown_sections(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines() or [text]
    headings = [index for index, line in enumerate(lines, start=1) if line.lstrip().startswith("#")]
    if not headings:
        return [{"title": "", "text": text, "line_start": 1, "line_end": max(1, len(lines))}]
    sections = []
    for position, line_start in enumerate(headings):
        line_end = headings[position + 1] - 1 if position + 1 < len(headings) else len(lines)
        section_lines = lines[line_start - 1:line_end]
        title = section_lines[0].lstrip("#").strip()
        sections.append({
            "title": title,
            "text": "\n".join(section_lines),
            "line_start": line_start,
            "line_end": line_end,
        })
    return sections


def _split_large_text(text: str, max_chars: int, overlap_chars: int) -> list[tuple[str, str]]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if len(paragraphs) > 1 and all(len(part) <= max_chars for part in paragraphs):
        return [(part, "paragraph") for part in paragraphs]

    sentences = [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+", text) if part.strip()]
    if len(sentences) > 1 and all(len(part) <= max_chars for part in sentences):
        return _pack_units(sentences, max_chars, "sentence")

    words = text.split()
    if not words:
        return [(text[:max_chars], "fixed_window")]
    parts: list[tuple[str, str]] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and len(candidate) > max_chars:
            chunk = " ".join(current)
            parts.append((chunk, "fixed_window"))
            current = _overlap_words(chunk, overlap_chars)
        current.append(word)
    if current:
        parts.append((" ".join(current), "fixed_window"))
    return parts


def _pack_units(units: list[str], max_chars: int, strategy: str) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    current: list[str] = []
    for unit in units:
        candidate = " ".join([*current, unit])
        if current and len(candidate) > max_chars:
            parts.append((" ".join(current), strategy))
            current = []
        current.append(unit)
    if current:
        parts.append((" ".join(current), strategy))
    return parts


def _overlap_words(text: str, overlap_chars: int) -> list[str]:
    if overlap_chars <= 0:
        return []
    words = text.split()
    result: list[str] = []
    total = 0
    for word in reversed(words):
        total += len(word) + 1
        if total > overlap_chars:
            break
        result.insert(0, word)
    return result


def _keywords(text: str) -> list[str]:
    words = re.findall(r"[A-Za-zА-Яа-я0-9_]+", text.lower())
    stop = {"and", "the", "для", "как", "или", "что", "это", "with", "from", "course"}
    result = []
    for word in words:
        if len(word) < 4 or word in stop or word in result:
            continue
        result.append(word)
        if len(result) >= 12:
            break
    return result


def _clip(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "..."


def _compact_text(text: str) -> str:
    return " ".join(str(text).split())


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_").lower()
