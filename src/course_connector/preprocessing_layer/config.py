"""Configuration for preprocessing and retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class PreprocessingConfigurationError(ValueError):
    """Raised when preprocessing configuration cannot be used."""


@dataclass(frozen=True)
class ChunkingConfig:
    enabled: bool = True
    strategy: str = "educational_entities"
    sizing_mode: str = "auto"
    target_chunk_tokens: int | None = None
    min_chunk_tokens: int = 300
    max_chunk_tokens: int | None = None
    overlap_tokens: int = 80
    strict: bool = False
    max_chunk_chars: int = 900
    max_pair_text_chars: int = 160


@dataclass(frozen=True)
class RetrievalConfig:
    enabled: bool = False
    mode: str = "none"
    top_k: int = 18
    fallback_mode: str = "keyword"


@dataclass(frozen=True)
class EmbeddingsConfig:
    enabled: bool = False
    provider: str = "local_sentence_transformer"
    model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    local_files_only: bool = True


@dataclass(frozen=True)
class TokenBudgetConfig:
    enabled: bool = True
    max_input_tokens: int = 80000
    reserve_output_tokens: int = 8000


@dataclass(frozen=True)
class BatchConfig:
    max_skills_per_batch: int = 1
    max_chunks_per_skill: int = 6
    max_assessment_chunks_per_skill: int = 4
    max_batch_input_tokens: int | None = 9000
    include_course_profile: bool = True
    merge_strategy: str = "local_dedup"


@dataclass(frozen=True)
class PreprocessingConfig:
    enabled: bool = False
    analysis_mode: str = "retrieval_single_shot"
    write_intermediate_outputs: bool = True
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    embeddings: EmbeddingsConfig = field(default_factory=EmbeddingsConfig)
    token_budget: TokenBudgetConfig = field(default_factory=TokenBudgetConfig)
    batch: BatchConfig = field(default_factory=BatchConfig)

    @classmethod
    def from_input_payload(cls, input_payload: dict[str, Any]) -> "PreprocessingConfig":
        """Build preprocessing config from the optional parsed config input."""
        data = _preprocessing_section(input_payload)
        chunking_data = _nested(data, "chunking")
        batch_data = _nested(data, "batch")
        token_budget_data = _nested(data, "token_budget")
        max_input_tokens = _positive_int(
            token_budget_data.get("max_input_tokens"),
            TokenBudgetConfig.max_input_tokens,
            "preprocessing.token_budget.max_input_tokens",
        )
        reserve_output_tokens = _positive_int(
            token_budget_data.get("reserve_output_tokens"),
            TokenBudgetConfig.reserve_output_tokens,
            "preprocessing.token_budget.reserve_output_tokens",
        )
        if reserve_output_tokens >= max_input_tokens:
            raise PreprocessingConfigurationError(
                "`preprocessing.token_budget.reserve_output_tokens` must be smaller than "
                "`preprocessing.token_budget.max_input_tokens`."
            )
        return cls(
            enabled=_bool_setting(data.get("enabled"), cls.enabled),
            analysis_mode=_analysis_mode(data.get("analysis_mode") or cls.analysis_mode),
            write_intermediate_outputs=_bool_setting(
                data.get("write_intermediate_outputs"),
                cls.write_intermediate_outputs,
            ),
            chunking=ChunkingConfig(
                enabled=_bool_setting(chunking_data.get("enabled"), ChunkingConfig.enabled),
                strategy=str(chunking_data.get("strategy") or ChunkingConfig.strategy),
                sizing_mode=_chunk_sizing_mode(chunking_data.get("sizing_mode") or ChunkingConfig.sizing_mode),
                target_chunk_tokens=_optional_positive_int(
                    chunking_data.get("target_chunk_tokens"),
                    "preprocessing.chunking.target_chunk_tokens",
                ),
                min_chunk_tokens=_positive_int(
                    chunking_data.get("min_chunk_tokens"),
                    ChunkingConfig.min_chunk_tokens,
                    "preprocessing.chunking.min_chunk_tokens",
                ),
                max_chunk_tokens=_optional_positive_int(
                    chunking_data.get("max_chunk_tokens"),
                    "preprocessing.chunking.max_chunk_tokens",
                ),
                overlap_tokens=_non_negative_int(
                    chunking_data.get("overlap_tokens"),
                    ChunkingConfig.overlap_tokens,
                    "preprocessing.chunking.overlap_tokens",
                ),
                strict=_bool_setting(chunking_data.get("strict"), ChunkingConfig.strict),
                max_chunk_chars=_positive_int(
                    chunking_data.get("max_chunk_chars"),
                    ChunkingConfig.max_chunk_chars,
                    "preprocessing.chunking.max_chunk_chars",
                ),
                max_pair_text_chars=_positive_int(
                    chunking_data.get("max_pair_text_chars"),
                    ChunkingConfig.max_pair_text_chars,
                    "preprocessing.chunking.max_pair_text_chars",
                ),
            ),
            retrieval=RetrievalConfig(
                enabled=_bool_setting(_nested(data, "retrieval").get("enabled"), RetrievalConfig.enabled),
                mode=_retrieval_mode(_nested(data, "retrieval").get("mode") or RetrievalConfig.mode),
                top_k=_positive_int(
                    _nested(data, "retrieval").get("top_k"),
                    RetrievalConfig.top_k,
                    "preprocessing.retrieval.top_k",
                ),
                fallback_mode=_retrieval_mode(
                    _nested(data, "retrieval").get("fallback_mode") or RetrievalConfig.fallback_mode
                ),
            ),
            embeddings=EmbeddingsConfig(
                enabled=_bool_setting(_nested(data, "embeddings").get("enabled"), EmbeddingsConfig.enabled),
                provider=str(_nested(data, "embeddings").get("provider") or EmbeddingsConfig.provider),
                model=str(_nested(data, "embeddings").get("model") or EmbeddingsConfig.model),
                local_files_only=_bool_setting(
                    _nested(data, "embeddings").get("local_files_only"),
                    EmbeddingsConfig.local_files_only,
                ),
            ),
            token_budget=TokenBudgetConfig(
                enabled=_bool_setting(token_budget_data.get("enabled"), TokenBudgetConfig.enabled),
                max_input_tokens=max_input_tokens,
                reserve_output_tokens=reserve_output_tokens,
            ),
            batch=BatchConfig(
                max_skills_per_batch=_positive_int(
                    batch_data.get("max_skills_per_batch"),
                    BatchConfig.max_skills_per_batch,
                    "preprocessing.batch.max_skills_per_batch",
                ),
                max_chunks_per_skill=_positive_int(
                    batch_data.get("max_chunks_per_skill"),
                    BatchConfig.max_chunks_per_skill,
                    "preprocessing.batch.max_chunks_per_skill",
                ),
                max_assessment_chunks_per_skill=_positive_int(
                    batch_data.get("max_assessment_chunks_per_skill"),
                    BatchConfig.max_assessment_chunks_per_skill,
                    "preprocessing.batch.max_assessment_chunks_per_skill",
                ),
                max_batch_input_tokens=_optional_positive_int(
                    batch_data.get("max_batch_input_tokens"),
                    "preprocessing.batch.max_batch_input_tokens",
                ),
                include_course_profile=_bool_setting(
                    batch_data.get("include_course_profile"),
                    BatchConfig.include_course_profile,
                ),
                merge_strategy=_merge_strategy(batch_data.get("merge_strategy") or BatchConfig.merge_strategy),
            ),
        )


def _preprocessing_section(input_payload: dict[str, Any]) -> dict[str, Any]:
    config_entry = input_payload.get("config")
    parsed_data = config_entry.get("parsed_data") if isinstance(config_entry, dict) else None
    if not isinstance(parsed_data, dict):
        return {}
    section = parsed_data.get("preprocessing")
    return dict(section) if isinstance(section, dict) else {}


def _nested(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _bool_setting(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise PreprocessingConfigurationError("Preprocessing boolean setting must be true or false.")


def _positive_int(value: Any, default: int, name: str) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PreprocessingConfigurationError(f"`{name}` must be an integer.") from exc
    if parsed <= 0:
        raise PreprocessingConfigurationError(f"`{name}` must be positive.")
    return parsed


def _optional_positive_int(value: Any, name: str) -> int | None:
    if value is None or value == "":
        return None
    return _positive_int(value, 1, name)


def _non_negative_int(value: Any, default: int, name: str) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PreprocessingConfigurationError(f"`{name}` must be an integer.") from exc
    if parsed < 0:
        raise PreprocessingConfigurationError(f"`{name}` must be zero or positive.")
    return parsed


def _chunk_sizing_mode(value: Any) -> str:
    mode = str(value).strip().lower()
    if mode not in {"auto", "fixed"}:
        raise PreprocessingConfigurationError(f"Unsupported chunk sizing mode `{value}`.")
    return mode


def _analysis_mode(value: Any) -> str:
    mode = str(value).strip().lower()
    if mode not in {"full_input", "retrieval_single_shot", "smart_batch"}:
        raise PreprocessingConfigurationError(f"Unsupported preprocessing analysis mode `{value}`.")
    return mode


def _retrieval_mode(value: Any) -> str:
    mode = str(value).strip().lower()
    if mode not in {"none", "keyword", "local_embeddings"}:
        raise PreprocessingConfigurationError(f"Unsupported retrieval mode `{value}`.")
    return mode


def _merge_strategy(value: Any) -> str:
    strategy = str(value).strip().lower()
    if strategy not in {"local_dedup", "llm_synthesis"}:
        raise PreprocessingConfigurationError(f"Unsupported batch merge strategy `{value}`.")
    return strategy
