"""Facade for preprocessing before LLM analysis."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from course_connector.preprocessing_layer.batch_planner import plan_skill_batches
from course_connector.preprocessing_layer.chunking import build_chunks
from course_connector.preprocessing_layer.config import PreprocessingConfig
from course_connector.preprocessing_layer.course_profiles import build_course_profiles
from course_connector.preprocessing_layer.retrieval import retrieve_pairs
from course_connector.preprocessing_layer.token_budget import apply_chunk_sizing_policy, apply_token_budget


MAX_SUPPORT_CHUNKS_PER_SKILL = 1


def prepare_analysis_context(
    input_payload: dict[str, Any],
    config: PreprocessingConfig | None = None,
) -> dict[str, Any]:
    """Prepare chunks and retrieved evidence pairs for LLM analysis."""
    config = config or PreprocessingConfig.from_input_payload(input_payload)
    if not config.enabled:
        return {
            "enabled": False,
            "mode": "full_input",
            "analysis_mode": "full_input",
            "input_payload": input_payload,
            "chunks": {"course_a": [], "course_b": [], "skill_dictionary": [], "assessments": []},
            "retrieved_pairs": [],
            "course_profiles": {},
            "skill_batches": [],
            "batch_results": [],
            "merged_findings": [],
            "evidence_refs": {},
            "metrics": {
                "analysis_mode": "full_input",
                "chunks_course_a": 0,
                "chunks_course_b": 0,
                "chunks_assessments": 0,
                "retrieved_pairs": 0,
                "retrieval_mode": "disabled",
                "embedding_model": None,
            },
            "warnings": [],
            "write_intermediate_outputs": False,
        }

    effective_config, sizing_metrics, sizing_warnings = apply_chunk_sizing_policy(config)
    chunks, chunk_warnings = build_chunks(input_payload, effective_config.chunking)
    profile_data, profile_warnings = build_course_profiles(input_payload, chunks)
    if effective_config.analysis_mode == "smart_batch":
        pairs = []
        retrieval_warnings = []
        budget_metrics = sizing_metrics
        budget_warnings = []
        selected_chunks = []
        skill_batches, batch_metrics, batch_warnings = plan_skill_batches(
            input_payload,
            chunks,
            profile_data,
            effective_config,
        )
    else:
        pairs, retrieval_warnings = retrieve_pairs(chunks, effective_config)
        pairs, budget_metrics, budget_warnings = apply_token_budget(pairs, effective_config)
        selected_chunks = _selected_chunks(chunks, pairs)
        skill_batches = []
        batch_metrics = {}
        batch_warnings = []
    evidence_refs = _evidence_refs(chunks, pairs)
    evidence_warnings = []
    if not selected_chunks and not pairs and not skill_batches:
        evidence_warnings.append(
            "no_evidence_selected: preprocessing did not select evidence chunks; "
            "the pipeline will use a budget-validated fallback context if it fits."
        )
    metrics = {
        **sizing_metrics,
        **budget_metrics,
        **batch_metrics,
        "analysis_mode": effective_config.analysis_mode,
        "chunks_course_a": len(chunks.get("course_a", [])),
        "chunks_course_b": len(chunks.get("course_b", [])),
        "chunks_assessments": len(chunks.get("assessments", [])),
        "selected_chunks": len(selected_chunks),
        "retrieved_pairs": len(pairs),
        "skill_batches": len(skill_batches),
        "merge_strategy": effective_config.batch.merge_strategy,
        "retrieval_mode": effective_config.retrieval.mode if effective_config.retrieval.enabled else "none",
        "embedding_model": effective_config.embeddings.model if effective_config.embeddings.enabled else None,
    }
    return {
        "enabled": True,
        "mode": effective_config.analysis_mode,
        "analysis_mode": effective_config.analysis_mode,
        "input_payload": input_payload,
        "chunks": chunks,
        "course_profiles": profile_data,
        "selected_chunks": selected_chunks,
        "retrieved_pairs": pairs,
        "skill_batches": skill_batches,
        "batch_results": [],
        "merged_findings": [],
        "evidence_refs": evidence_refs,
        "metrics": metrics,
        "warnings": [
            *sizing_warnings,
            *chunk_warnings,
            *profile_warnings,
            *retrieval_warnings,
            *budget_warnings,
            *batch_warnings,
            *evidence_warnings,
        ],
        "write_intermediate_outputs": effective_config.write_intermediate_outputs,
    }


def write_intermediate_outputs(output_dir: Path, analysis_context: dict[str, Any]) -> dict[str, str]:
    """Write preprocessing artifacts for diagnostics when enabled."""
    if not analysis_context.get("enabled") or not analysis_context.get("write_intermediate_outputs"):
        return {}
    chunks = analysis_context.get("chunks", {})
    outputs = {
        "chunks_course_a": output_dir / "chunks_course_a.json",
        "chunks_course_b": output_dir / "chunks_course_b.json",
        "selected_chunks": output_dir / "selected_chunks.json",
        "retrieved_pairs": output_dir / "retrieved_pairs.json",
        "course_profiles": output_dir / "course_profiles.json",
        "skill_batches": output_dir / "skill_batches.json",
        "batch_results": output_dir / "batch_results.json",
        "merged_findings": output_dir / "merged_findings.json",
        "preprocessing_summary": output_dir / "preprocessing_summary.json",
    }
    outputs["chunks_course_a"].write_text(_json(chunks.get("course_a", [])), encoding="utf-8")
    outputs["chunks_course_b"].write_text(_json(chunks.get("course_b", [])), encoding="utf-8")
    outputs["selected_chunks"].write_text(_json(analysis_context.get("selected_chunks", [])), encoding="utf-8")
    outputs["retrieved_pairs"].write_text(_json(analysis_context.get("retrieved_pairs", [])), encoding="utf-8")
    outputs["course_profiles"].write_text(_json(analysis_context.get("course_profiles", {})), encoding="utf-8")
    outputs["skill_batches"].write_text(_json(analysis_context.get("skill_batches", [])), encoding="utf-8")
    outputs["batch_results"].write_text(_json(analysis_context.get("batch_results", [])), encoding="utf-8")
    outputs["merged_findings"].write_text(_json(analysis_context.get("merged_findings", [])), encoding="utf-8")
    outputs["preprocessing_summary"].write_text(
        _json({
            "enabled": analysis_context.get("enabled"),
            "mode": analysis_context.get("mode"),
            "metrics": analysis_context.get("metrics", {}),
            "warnings": analysis_context.get("warnings", []),
        }),
        encoding="utf-8",
    )
    return {name: str(path) for name, path in outputs.items()}


def _evidence_refs(chunks: dict[str, list[dict[str, Any]]], pairs: list[dict[str, Any]]) -> dict[str, Any]:
    chunk_refs = {
        chunk["chunk_id"]: {
            "source_role": chunk["source_role"],
            "source_path": chunk["source_path"],
            "source_type": chunk["source_type"],
            "locator": chunk["locator"],
        }
        for chunk_list in chunks.values()
        for chunk in chunk_list
    }
    pair_refs = {
        pair["pair_id"]: pair.get("evidence_refs", [])
        for pair in pairs
        if pair.get("pair_id")
    }
    return {"chunks": chunk_refs, "pairs": pair_refs}


def _selected_chunks(
    chunks: dict[str, list[dict[str, Any]]],
    pairs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {
        chunk["chunk_id"]: chunk
        for role in ("course_a", "course_b", "assessments")
        for chunk in chunks.get(role, [])
    }
    if pairs:
        selected_ids: list[str] = []
        for pair in pairs:
            for key in ("course_a_chunk_id", "course_b_chunk_id"):
                chunk_id = pair.get(key)
                if chunk_id and chunk_id not in selected_ids:
                    selected_ids.append(chunk_id)
        selected_ids.extend(_assessment_support_chunk_ids(chunks, by_id, selected_ids))
        return [by_id[chunk_id] for chunk_id in selected_ids if chunk_id in by_id]
    return [chunk for role in ("course_a", "course_b") for chunk in chunks.get(role, [])]


def _assessment_support_chunk_ids(
    chunks: dict[str, list[dict[str, Any]]],
    by_id: dict[str, dict[str, Any]],
    selected_ids: list[str],
) -> list[str]:
    """Add course chunks that directly teach selected assessment skill IDs."""
    selected = set(selected_ids)
    support_ids: list[str] = []
    for chunk_id in selected_ids:
        assessment = by_id.get(chunk_id)
        if not assessment or assessment.get("source_role") != "assessments":
            continue
        skill_ids = list(assessment.get("skill_ids") or [])
        if not skill_ids:
            continue
        for role in _assessment_course_roles(assessment):
            for skill_id in skill_ids:
                matches = _rank_support_chunks(chunks.get(role, []), assessment, skill_id)
                added_for_skill = 0
                for match in matches:
                    match_id = match.get("chunk_id")
                    if not match_id or match_id in selected:
                        continue
                    selected.add(match_id)
                    support_ids.append(match_id)
                    added_for_skill += 1
                    if added_for_skill >= MAX_SUPPORT_CHUNKS_PER_SKILL:
                        break
    return support_ids


def _assessment_course_roles(assessment: dict[str, Any]) -> list[str]:
    course_id = str(assessment.get("course_id") or "").strip().lower()
    text = " ".join([str(assessment.get("title") or ""), str(assessment.get("text") or "")])
    course_label = _markdown_course_label(text)
    if course_id in {"course_a", "a"} or course_label == "course a":
        return ["course_a"]
    if course_id in {"course_b", "b"} or course_label == "course b":
        return ["course_b"]
    if course_id == "both" or course_label == "both":
        return ["course_a", "course_b"]
    return ["course_a", "course_b"]


def _markdown_course_label(text: str) -> str:
    match = re.search(r"(?:^|\s)-?\s*Course\s*:\s*(Course\s+[AB]|Both)\b", text, flags=re.IGNORECASE)
    return match.group(1).lower() if match else ""


def _rank_support_chunks(
    course_chunks: list[dict[str, Any]],
    assessment: dict[str, Any],
    skill_id: str,
) -> list[dict[str, Any]]:
    assessment_keywords = set(assessment.get("keywords") or [])
    candidates = [
        chunk
        for chunk in course_chunks
        if skill_id in set(chunk.get("skill_ids") or [])
        and chunk.get("source_type") not in {"assessment", "row"}
    ]
    return sorted(
        candidates,
        key=lambda chunk: (
            _support_source_type_rank(str(chunk.get("source_type") or "")),
            _support_title_rank(str(chunk.get("title") or "")),
            -len(assessment_keywords & set(chunk.get("keywords") or [])),
            len(str(chunk.get("text") or "")),
            str(chunk.get("chunk_id") or ""),
        ),
    )


def _support_source_type_rank(source_type: str) -> int:
    if source_type in {"raw_section", "module", "topic", "outcome"}:
        return 0
    if source_type.endswith("_part"):
        return 1
    return 2


def _support_title_rank(title: str) -> int:
    normalized = title.strip().lower()
    if normalized in {"практика", "practice", "теория", "theory"}:
        return 0
    if normalized in {"результаты обучения", "learning outcomes", "цели курса", "course goals"}:
        return 2
    return 1


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
