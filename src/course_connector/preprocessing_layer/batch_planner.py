"""Plan smart skill batches from chunks and course profiles."""

from __future__ import annotations

import json
import re
from typing import Any

from course_connector.llm_layer.prompts.batch_renderer import build_skill_batch_prompt
from course_connector.preprocessing_layer.config import PreprocessingConfig
from course_connector.preprocessing_layer.token_budget import available_input_tokens, estimate_tokens


COURSE_ROLES = ("course_a", "course_b")


def plan_skill_batches(
    input_payload: dict[str, Any],
    chunks: dict[str, list[dict[str, Any]]],
    course_profiles: dict[str, dict[str, Any]],
    config: PreprocessingConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    """Create budget-aware smart batches grouped by skill id."""
    skill_index = _skill_index(input_payload)
    warnings: list[str] = []
    coverage = _initial_coverage(chunks)
    batches: list[dict[str, Any]] = []

    for skill_id, skill in skill_index.items():
        course_a_chunks, matches_a = _matching_chunks(chunks.get("course_a", []), skill_id, skill)
        course_b_chunks, matches_b = _matching_chunks(chunks.get("course_b", []), skill_id, skill)
        assessment_chunks, assessment_matches, assessment_warnings = _matching_assessments(
            chunks.get("assessments", []),
            skill_id,
            skill,
        )
        warnings.extend(assessment_warnings)
        if not course_a_chunks and not course_b_chunks and not assessment_chunks:
            continue

        batch = _batch(
            batch_id=f"skill_{len(batches) + 1:03d}_{skill_id}",
            batch_type="skill",
            skill_ids=[skill_id],
            skill_dictionary_subset=[_skill_subset(skill_id, skill)],
            course_profiles=course_profiles if config.batch.include_course_profile else {},
            course_a_chunks=course_a_chunks[: config.batch.max_chunks_per_skill],
            course_b_chunks=course_b_chunks[: config.batch.max_chunks_per_skill],
            assessment_chunks=assessment_chunks[: config.batch.max_assessment_chunks_per_skill],
            matched_by={**matches_a, **matches_b, **assessment_matches},
        )
        for chunk in batch["course_a_chunks"]:
            coverage["course_a"][chunk["chunk_id"]] = "assigned_to_skill_batch"
        for chunk in batch["course_b_chunks"]:
            coverage["course_b"][chunk["chunk_id"]] = "assigned_to_skill_batch"
        batches.extend(_split_to_budget(batch, config, warnings))

    general_batches = _general_batches(chunks, course_profiles, coverage, config)
    batches.extend(general_batches)
    coverage_metrics = _coverage_metrics(chunks, coverage, skill_index, batches)
    return batches, coverage_metrics, warnings


def _batch(
    *,
    batch_id: str,
    batch_type: str,
    skill_ids: list[str],
    skill_dictionary_subset: list[dict[str, Any]],
    course_profiles: dict[str, dict[str, Any]],
    course_a_chunks: list[dict[str, Any]],
    course_b_chunks: list[dict[str, Any]],
    assessment_chunks: list[dict[str, Any]],
    matched_by: dict[str, str] | None = None,
    parent_batch_id: str | None = None,
    split_reason: str | None = None,
) -> dict[str, Any]:
    item = {
        "batch_id": batch_id,
        "parent_batch_id": parent_batch_id,
        "batch_type": batch_type,
        "skill_ids": skill_ids,
        "skill_dictionary_subset": skill_dictionary_subset,
        "course_profiles": course_profiles,
        "course_a_chunks": [_prompt_chunk(chunk) for chunk in course_a_chunks],
        "course_b_chunks": [_prompt_chunk(chunk) for chunk in course_b_chunks],
        "assessment_chunks": [_prompt_chunk(chunk) for chunk in assessment_chunks],
        "course_a_chunk_ids": [chunk["chunk_id"] for chunk in course_a_chunks],
        "course_b_chunk_ids": [chunk["chunk_id"] for chunk in course_b_chunks],
        "assessment_chunk_ids": [chunk["chunk_id"] for chunk in assessment_chunks],
        "matched_by": matched_by or {},
        "split_reason": split_reason,
        "warnings": [],
    }
    item["estimated_prompt_tokens"] = _batch_prompt_tokens(item)
    return item


def _split_to_budget(
    batch: dict[str, Any],
    config: PreprocessingConfig,
    warnings: list[str],
) -> list[dict[str, Any]]:
    max_tokens = _max_batch_tokens(config)
    if batch["estimated_prompt_tokens"] <= max_tokens:
        return [batch]

    chunk_groups = {
        "course_a_chunks": list(batch.get("course_a_chunks", [])),
        "course_b_chunks": list(batch.get("course_b_chunks", [])),
        "assessment_chunks": list(batch.get("assessment_chunks", [])),
    }
    non_empty_groups = {name: items for name, items in chunk_groups.items() if items}
    max_group_size = max((len(items) for items in non_empty_groups.values()), default=0)
    if max_group_size <= 1:
        skipped = dict(batch)
        skipped["omitted_with_reason"] = "batch_prompt_exceeds_budget"
        warnings.append(f"smart_batch_omitted: `{batch['batch_id']}` exceeds max batch prompt tokens.")
        return []

    result: list[dict[str, Any]] = []
    slice_size = max(1, (max_group_size + 1) // 2)
    for part_index, start in enumerate(range(0, max_group_size, slice_size), start=1):
        sub_batch = _batch(
            batch_id=f"{batch['batch_id']}_part_{part_index:02d}",
            batch_type=batch.get("batch_type", "skill"),
            skill_ids=list(batch.get("skill_ids") or []),
            skill_dictionary_subset=list(batch.get("skill_dictionary_subset") or []),
            course_profiles=batch.get("course_profiles", {}),
            course_a_chunks=chunk_groups["course_a_chunks"][start:start + slice_size],
            course_b_chunks=chunk_groups["course_b_chunks"][start:start + slice_size],
            assessment_chunks=chunk_groups["assessment_chunks"][start:start + slice_size],
            matched_by=dict(batch.get("matched_by") or {}),
            parent_batch_id=batch["batch_id"],
            split_reason="max_batch_input_tokens",
        )
        if sub_batch["estimated_prompt_tokens"] > max_tokens:
            result.extend(_split_to_budget(sub_batch, config, warnings))
        else:
            result.append(sub_batch)
    return result


def _general_batches(
    chunks: dict[str, list[dict[str, Any]]],
    course_profiles: dict[str, dict[str, Any]],
    coverage: dict[str, dict[str, str]],
    config: PreprocessingConfig,
) -> list[dict[str, Any]]:
    batches: list[dict[str, Any]] = []
    for role in COURSE_ROLES:
        profile_ids = set(course_profiles.get(role, {}).get("profile_chunk_ids") or [])
        general = []
        for chunk in chunks.get(role, []):
            chunk_id = chunk.get("chunk_id")
            if coverage[role].get(chunk_id) == "assigned_to_skill_batch":
                continue
            if chunk_id in profile_ids:
                coverage[role][chunk_id] = "profile_only"
                continue
            coverage[role][chunk_id] = "assigned_to_general_batch"
            general.append(chunk)
        for index, slice_items in enumerate(_chunk_slices(general, config.batch.max_chunks_per_skill), start=1):
            planned = _split_to_budget(
                _batch(
                    batch_id=f"general_{role}_{index:03d}",
                    batch_type="general",
                    skill_ids=[],
                    skill_dictionary_subset=[],
                    course_profiles=course_profiles if config.batch.include_course_profile else {},
                    course_a_chunks=slice_items if role == "course_a" else [],
                    course_b_chunks=slice_items if role == "course_b" else [],
                    assessment_chunks=[],
                ),
                config,
                [],
            )
            for batch in planned:
                batch["diagnostic_only"] = True
            batches.extend(planned)
    return batches


def _matching_chunks(
    chunks: list[dict[str, Any]],
    skill_id: str,
    skill: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    aliases = _skill_aliases(skill_id, skill)
    result = []
    matched_by = {}
    for chunk in chunks:
        chunk_id = str(chunk.get("chunk_id") or "")
        text = _chunk_search_text(chunk)
        if skill_id in set(chunk.get("skill_ids") or []):
            result.append(chunk)
            matched_by[chunk_id] = "explicit_skill_id"
        elif any(_candidate_matches(text, alias) for alias in aliases):
            result.append(chunk)
            matched_by[chunk_id] = "alias"
    return result, matched_by


def _matching_assessments(
    chunks: list[dict[str, Any]],
    skill_id: str,
    skill: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str], list[str]]:
    matches, matched_by = _matching_chunks(chunks, skill_id, skill)
    warnings = []
    aliases = _skill_aliases(skill_id, skill)
    for chunk in chunks:
        chunk_id = str(chunk.get("chunk_id") or "")
        if chunk in matches:
            continue
        text = _chunk_search_text(chunk)
        if any(_candidate_matches(text, alias) for alias in aliases):
            matches.append(chunk)
            matched_by[chunk_id] = "keyword_fallback"
            warnings.append(f"assessment_match_uncertain: `{chunk_id}` matched `{skill_id}` by alias text.")
    return matches, matched_by, warnings


def _coverage_metrics(
    chunks: dict[str, list[dict[str, Any]]],
    coverage: dict[str, dict[str, str]],
    skill_index: dict[str, dict[str, Any]],
    batches: list[dict[str, Any]],
) -> dict[str, Any]:
    covered = sorted({skill_id for batch in batches for skill_id in batch.get("skill_ids", [])})
    assigned_ids = {
        role: {
            chunk_id
            for batch in batches
            for chunk_id in batch.get(f"{role}_chunk_ids", [])
        }
        for role in COURSE_ROLES
    }
    statuses: dict[str, int] = {}
    for role in COURSE_ROLES:
        for chunk in chunks.get(role, []):
            chunk_id = chunk["chunk_id"]
            status = coverage[role].get(chunk_id, "omitted_with_reason")
            if status.startswith("assigned_to") and chunk_id not in assigned_ids[role]:
                status = "omitted_with_reason"
                coverage[role][chunk_id] = status
            statuses[status] = statuses.get(status, 0) + 1
    return {
        "covered_skill_ids": covered,
        "uncovered_skill_ids": sorted(set(skill_index) - set(covered)),
        "chunk_coverage": coverage,
        "chunk_coverage_counts": statuses,
        "planned_batches": len(batches),
        "split_batches": len([batch for batch in batches if batch.get("parent_batch_id")]),
    }


def _initial_coverage(chunks: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, str]]:
    return {
        role: {chunk["chunk_id"]: "omitted_with_reason" for chunk in chunks.get(role, [])}
        for role in COURSE_ROLES
    }


def _skill_index(input_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entry = input_payload.get("skill_dictionary")
    data = entry.get("parsed_data") if isinstance(entry, dict) else None
    skills = data.get("skills") if isinstance(data, dict) else []
    result = {}
    if isinstance(skills, list):
        for skill in skills:
            if not isinstance(skill, dict) or not skill.get("id"):
                continue
            result[str(skill["id"])] = dict(skill)
    return result


def _skill_subset(skill_id: str, skill: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": skill_id,
        "title": skill.get("title") or skill_id,
        "description": skill.get("description"),
        "aliases": list(skill.get("aliases") or []),
    }


def _skill_aliases(skill_id: str, skill: dict[str, Any]) -> list[str]:
    return [
        str(item).lower()
        for item in [skill_id, skill.get("title"), *list(skill.get("aliases") or [])]
        if item
    ]


def _candidate_matches(text: str, candidate: str) -> bool:
    candidate = candidate.strip()
    if not candidate:
        return False
    if candidate.lower() == "workflow":
        lower = text.lower()
        return "github actions" in lower or ".github/workflows" in lower
    return re.search(rf"(?<![\w-]){re.escape(candidate)}(?![\w-])", text, flags=re.IGNORECASE) is not None


def _chunk_search_text(chunk: dict[str, Any]) -> str:
    return " ".join([
        str(chunk.get("title") or ""),
        str(chunk.get("text") or ""),
        " ".join(str(item) for item in chunk.get("skill_ids") or []),
        " ".join(str(item) for item in chunk.get("keywords") or []),
    ]).lower()


def _prompt_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": chunk.get("chunk_id"),
        "source_role": chunk.get("source_role"),
        "source_path": chunk.get("source_path"),
        "source_type": chunk.get("source_type"),
        "title": chunk.get("title"),
        "text": chunk.get("text"),
        "skill_ids": chunk.get("skill_ids", []),
        "locator": chunk.get("locator", {}),
    }


def _chunk_slices(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    if not items:
        return []
    return [items[index:index + max(1, size)] for index in range(0, len(items), max(1, size))]


def _batch_prompt_tokens(batch: dict[str, Any]) -> int:
    try:
        return estimate_tokens(build_skill_batch_prompt(batch))
    except Exception:
        return estimate_tokens(json.dumps(batch, ensure_ascii=False))


def _max_batch_tokens(config: PreprocessingConfig) -> int:
    return config.batch.max_batch_input_tokens or available_input_tokens(config)
