"""Facade for preprocessing before LLM analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from course_connector.preprocessing_layer.chunking import build_chunks
from course_connector.preprocessing_layer.config import PreprocessingConfig
from course_connector.preprocessing_layer.retrieval import retrieve_pairs
from course_connector.preprocessing_layer.token_budget import apply_token_budget


def prepare_analysis_context(
    input_payload: dict[str, Any],
    config: PreprocessingConfig | None = None,
) -> dict[str, Any]:
    """Prepare chunks and retrieved evidence pairs for LLM analysis."""
    config = config or PreprocessingConfig.from_input_payload(input_payload)
    if not config.enabled:
        return {
            "enabled": False,
            "mode": "disabled",
            "input_payload": input_payload,
            "chunks": {"course_a": [], "course_b": [], "skill_dictionary": [], "assessments": []},
            "retrieved_pairs": [],
            "evidence_refs": {},
            "metrics": {
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

    chunks, chunk_warnings = build_chunks(input_payload, config.chunking)
    pairs, retrieval_warnings = retrieve_pairs(chunks, config)
    pairs, budget_metrics, budget_warnings = apply_token_budget(pairs, config)
    evidence_refs = _evidence_refs(chunks, pairs)
    metrics = {
        **budget_metrics,
        "chunks_course_a": len(chunks.get("course_a", [])),
        "chunks_course_b": len(chunks.get("course_b", [])),
        "chunks_assessments": len(chunks.get("assessments", [])),
        "retrieved_pairs": len(pairs),
        "retrieval_mode": config.retrieval.mode if config.retrieval.enabled else "none",
        "embedding_model": config.embeddings.model if config.embeddings.enabled else None,
    }
    return {
        "enabled": True,
        "mode": metrics["retrieval_mode"],
        "input_payload": input_payload,
        "chunks": chunks,
        "retrieved_pairs": pairs,
        "evidence_refs": evidence_refs,
        "metrics": metrics,
        "warnings": [*chunk_warnings, *retrieval_warnings, *budget_warnings],
        "write_intermediate_outputs": config.write_intermediate_outputs,
    }


def write_intermediate_outputs(output_dir: Path, analysis_context: dict[str, Any]) -> dict[str, str]:
    """Write preprocessing artifacts for diagnostics when enabled."""
    if not analysis_context.get("enabled") or not analysis_context.get("write_intermediate_outputs"):
        return {}
    chunks = analysis_context.get("chunks", {})
    outputs = {
        "chunks_course_a": output_dir / "chunks_course_a.json",
        "chunks_course_b": output_dir / "chunks_course_b.json",
        "retrieved_pairs": output_dir / "retrieved_pairs.json",
        "preprocessing_summary": output_dir / "preprocessing_summary.json",
    }
    outputs["chunks_course_a"].write_text(_json(chunks.get("course_a", [])), encoding="utf-8")
    outputs["chunks_course_b"].write_text(_json(chunks.get("course_b", [])), encoding="utf-8")
    outputs["retrieved_pairs"].write_text(_json(analysis_context.get("retrieved_pairs", [])), encoding="utf-8")
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


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
