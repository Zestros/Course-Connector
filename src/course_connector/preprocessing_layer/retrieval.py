"""Select compact evidence pairs before LLM analysis."""

from __future__ import annotations

import math
from typing import Any

from course_connector.preprocessing_layer.config import PreprocessingConfig, PreprocessingConfigurationError
from course_connector.preprocessing_layer.embeddings.base import EmbeddingProvider
from course_connector.preprocessing_layer.embeddings.local_sentence_transformer import (
    LocalSentenceTransformerEmbeddingProvider,
)
from course_connector.preprocessing_layer.evidence_refs import evidence_ref


def retrieve_pairs(
    chunks: dict[str, list[dict[str, Any]]],
    config: PreprocessingConfig,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Retrieve candidate evidence pairs using the configured retrieval mode."""
    warnings: list[str] = []
    if not config.retrieval.enabled or config.retrieval.mode == "none":
        return [], warnings
    if config.retrieval.mode == "keyword":
        return keyword_retrieve(chunks, config), warnings
    if config.retrieval.mode == "local_embeddings":
        try:
            provider = _embedding_provider(config)
            return embedding_retrieve(chunks, config, provider), warnings
        except PreprocessingConfigurationError:
            if config.retrieval.fallback_mode == "keyword":
                warnings.append("Local embeddings unavailable; fell back to keyword retrieval.")
                return keyword_retrieve(chunks, config), warnings
            raise
    raise PreprocessingConfigurationError(f"Unsupported retrieval mode `{config.retrieval.mode}`.")


def keyword_retrieve(chunks: dict[str, list[dict[str, Any]]], config: PreprocessingConfig) -> list[dict[str, Any]]:
    """Rank pairs by skill, keyword, title, and source-type evidence."""
    scored = []
    comparison_chunks = _comparison_chunks(chunks)
    for chunk_a in chunks.get("course_a", []):
        for chunk_b in comparison_chunks:
            score = _keyword_score(chunk_a, chunk_b)
            if score <= 0:
                continue
            scored.append(_pair(
                chunk_a,
                chunk_b,
                score=score,
                hint=_hint_for_pair(chunk_a, chunk_b, score),
                reason="keyword retrieval: matched skills, keywords, titles, or source-type evidence",
            ))
    scored.sort(key=lambda pair: pair["similarity_score"], reverse=True)
    return _balanced_selection(scored, config.retrieval.top_k)


def embedding_retrieve(
    chunks: dict[str, list[dict[str, Any]]],
    config: PreprocessingConfig,
    provider: EmbeddingProvider,
) -> list[dict[str, Any]]:
    """Retrieve pairs with embedding cosine similarity and balanced selection."""
    chunks_a = chunks.get("course_a", [])
    chunks_b = _comparison_chunks(chunks)
    embeddings_a = provider.embed([_embedding_text(chunk) for chunk in chunks_a])
    embeddings_b = provider.embed([_embedding_text(chunk) for chunk in chunks_b])
    scored = []
    for index_a, embedding_a in enumerate(embeddings_a):
        for index_b, embedding_b in enumerate(embeddings_b):
            chunk_a = chunks_a[index_a]
            chunk_b = chunks_b[index_b]
            score = _cosine_similarity(embedding_a, embedding_b)
            scored.append(_pair(
                chunk_a,
                chunk_b,
                score=score,
                hint=_hint_for_pair(chunk_a, chunk_b, score),
                reason="local embedding cosine similarity",
            ))
    scored.sort(key=lambda pair: pair["similarity_score"], reverse=True)
    return _balanced_selection(scored, config.retrieval.top_k)


def _embedding_provider(config: PreprocessingConfig) -> EmbeddingProvider:
    if not config.embeddings.enabled:
        raise PreprocessingConfigurationError("Retrieval mode `local_embeddings` requires `embeddings.enabled: true`.")
    if config.embeddings.provider != "local_sentence_transformer":
        raise PreprocessingConfigurationError(f"Unsupported embedding provider `{config.embeddings.provider}`.")
    return LocalSentenceTransformerEmbeddingProvider(config.embeddings)


def _comparison_chunks(chunks: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    course_a_ids = _course_ids(chunks.get("course_a", []))
    course_b_ids = _course_ids(chunks.get("course_b", []))
    assessment_chunks = [
        chunk
        for chunk in chunks.get("assessments", [])
        if _assessment_belongs_to_comparison_side(chunk, course_a_ids, course_b_ids)
    ]
    return [*chunks.get("course_b", []), *assessment_chunks]


def _course_ids(chunks: list[dict[str, Any]]) -> set[str]:
    return {
        str(chunk.get("course_id"))
        for chunk in chunks
        if chunk.get("course_id")
    }


def _assessment_belongs_to_comparison_side(
    chunk: dict[str, Any],
    course_a_ids: set[str],
    course_b_ids: set[str],
) -> bool:
    course_id = str(chunk.get("course_id") or "").strip()
    if not course_id:
        return True
    if course_b_ids:
        return course_id in course_b_ids
    return course_id not in course_a_ids


def _pair(
    chunk_a: dict[str, Any],
    chunk_b: dict[str, Any],
    score: float,
    hint: str,
    reason: str,
) -> dict[str, Any]:
    matched_skills = sorted(set(chunk_a.get("skill_ids", [])) & set(chunk_b.get("skill_ids", [])))
    return {
        "pair_id": "",
        "course_a_chunk_id": chunk_a["chunk_id"],
        "course_b_chunk_id": chunk_b["chunk_id"],
        "course_a_title": chunk_a["title"],
        "course_b_title": chunk_b["title"],
        "course_a_text": chunk_a["text"],
        "course_b_text": chunk_b["text"],
        "course_a_source_type": chunk_a["source_type"],
        "course_b_source_type": chunk_b["source_type"],
        "matched_skill_ids": matched_skills,
        "candidate_relation_hint": hint,
        "similarity_score": round(score, 4),
        "retrieval_reason": reason,
        "evidence_refs": [evidence_ref(chunk_a), evidence_ref(chunk_b)],
    }


def _balanced_selection(scored: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    buckets = {
        "useful_repetition_candidate": [],
        "probable_duplication_candidate": [],
        "probable_gap_candidate": [],
    }
    for pair in scored:
        buckets.setdefault(pair["candidate_relation_hint"], []).append(pair)

    selected = []
    seen = set()
    order = ["useful_repetition_candidate", "probable_gap_candidate", "probable_duplication_candidate"]
    cursor = 0
    while len(selected) < top_k and any(buckets.values()):
        bucket = buckets[order[cursor % len(order)]]
        while bucket:
            pair = bucket.pop(0)
            key = (pair["course_a_chunk_id"], pair["course_b_chunk_id"])
            if key not in seen:
                seen.add(key)
                selected.append(pair)
                break
        cursor += 1
        if cursor > top_k * len(order) * 4:
            break

    if len(selected) < top_k:
        for pair in scored:
            key = (pair["course_a_chunk_id"], pair["course_b_chunk_id"])
            if key in seen:
                continue
            seen.add(key)
            selected.append(pair)
            if len(selected) >= top_k:
                break

    for index, pair in enumerate(selected, start=1):
        pair["pair_id"] = f"retrieved_{index:03d}"
    return selected[:top_k]


def _keyword_score(chunk_a: dict[str, Any], chunk_b: dict[str, Any]) -> float:
    skills_a = set(chunk_a.get("skill_ids", []))
    skills_b = set(chunk_b.get("skill_ids", []))
    keywords_a = set(chunk_a.get("keywords", []))
    keywords_b = set(chunk_b.get("keywords", []))
    title_score = 0.2 if chunk_a.get("title") and chunk_a.get("title") == chunk_b.get("title") else 0.0
    base_score = (
        len(skills_a & skills_b) * 1.0
        + len(keywords_a & keywords_b) * 0.15
        + title_score
    )
    if base_score <= 0:
        return 0.0
    return base_score + _source_type_bonus(chunk_a, chunk_b)


def _source_type_bonus(chunk_a: dict[str, Any], chunk_b: dict[str, Any]) -> float:
    source_a = chunk_a.get("source_type")
    source_b = chunk_b.get("source_type")
    if source_b in {"assessment", "row"} and source_a in {"module", "outcome", "raw_section", "coarse_file"}:
        return 0.25
    if source_a == source_b:
        return 0.15
    return 0.0


def _hint_for_pair(chunk_a: dict[str, Any], chunk_b: dict[str, Any], score: float) -> str:
    if chunk_b.get("source_type") in {"assessment", "row"}:
        return "probable_gap_candidate"
    if chunk_a.get("source_type") == chunk_b.get("source_type") and score >= 1.1:
        return "probable_duplication_candidate"
    return "useful_repetition_candidate"


def _embedding_text(chunk: dict[str, Any]) -> str:
    return "\n".join([
        str(chunk.get("title", "")),
        str(chunk.get("text", "")),
        " ".join(chunk.get("skill_ids", [])),
        " ".join(chunk.get("keywords", [])),
    ])


def _cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vector_a, vector_b))
    norm_a = math.sqrt(sum(a * a for a in vector_a))
    norm_b = math.sqrt(sum(b * b for b in vector_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
