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
class PreprocessingConfig:
    enabled: bool = False
    write_intermediate_outputs: bool = True
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    embeddings: EmbeddingsConfig = field(default_factory=EmbeddingsConfig)
    token_budget: TokenBudgetConfig = field(default_factory=TokenBudgetConfig)

    @classmethod
    def from_input_payload(cls, input_payload: dict[str, Any]) -> "PreprocessingConfig":
        """Build preprocessing config from the optional parsed config input."""
        data = _preprocessing_section(input_payload)
        return cls(
            enabled=_bool_setting(data.get("enabled"), cls.enabled),
            write_intermediate_outputs=_bool_setting(
                data.get("write_intermediate_outputs"),
                cls.write_intermediate_outputs,
            ),
            chunking=ChunkingConfig(
                enabled=_bool_setting(_nested(data, "chunking").get("enabled"), ChunkingConfig.enabled),
                strategy=str(_nested(data, "chunking").get("strategy") or ChunkingConfig.strategy),
                max_chunk_chars=_positive_int(
                    _nested(data, "chunking").get("max_chunk_chars"),
                    ChunkingConfig.max_chunk_chars,
                    "preprocessing.chunking.max_chunk_chars",
                ),
                max_pair_text_chars=_positive_int(
                    _nested(data, "chunking").get("max_pair_text_chars"),
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
                enabled=_bool_setting(_nested(data, "token_budget").get("enabled"), TokenBudgetConfig.enabled),
                max_input_tokens=_positive_int(
                    _nested(data, "token_budget").get("max_input_tokens"),
                    TokenBudgetConfig.max_input_tokens,
                    "preprocessing.token_budget.max_input_tokens",
                ),
                reserve_output_tokens=_positive_int(
                    _nested(data, "token_budget").get("reserve_output_tokens"),
                    TokenBudgetConfig.reserve_output_tokens,
                    "preprocessing.token_budget.reserve_output_tokens",
                ),
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


def _retrieval_mode(value: Any) -> str:
    mode = str(value).strip().lower()
    if mode not in {"none", "keyword", "local_embeddings"}:
        raise PreprocessingConfigurationError(f"Unsupported retrieval mode `{value}`.")
    return mode
