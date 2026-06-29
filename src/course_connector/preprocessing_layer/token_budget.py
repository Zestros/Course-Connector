"""Token-budget estimation and compaction for LLM context."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from course_connector.llm_layer.prompts.renderer import build_prompt
from course_connector.preprocessing_layer.config import (
    ChunkingConfig,
    PreprocessingConfig,
    PreprocessingConfigurationError,
)


CHARS_PER_TOKEN = 3
DEFAULT_EVIDENCE_ITEMS = 8
MIN_PROMPT_PAYLOAD_TOKENS = 64


class PreprocessingBudgetError(PreprocessingConfigurationError):
    """Raised when input cannot fit the configured model context."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def apply_token_budget(
    pairs: list[dict[str, Any]],
    config: PreprocessingConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    """Compact retrieved pairs to fit the configured prompt budget."""
    warnings: list[str] = []
    metrics = budget_metrics(config)
    if not config.token_budget.enabled:
        return pairs, {**metrics, "estimated_input_tokens": _estimate_pairs_tokens(pairs)}, warnings

    compacted = [_clip_pair_text(pair, config.chunking.max_pair_text_chars) for pair in pairs]
    available_tokens = available_input_tokens(config)
    while _estimate_pairs_tokens(compacted) > available_tokens and compacted:
        removed = compacted.pop()
        warnings.append(f"Token budget removed retrieved pair `{removed.get('pair_id')}` from LLM context.")
    if len(compacted) < len(pairs):
        warnings.append(
            f"Token budget compacted retrieved pairs from {len(pairs)} to {len(compacted)}."
        )
    return compacted, {**metrics, "estimated_input_tokens": _estimate_pairs_tokens(compacted)}, warnings


def budget_metrics(config: PreprocessingConfig) -> dict[str, Any]:
    """Return model-context metrics that can be written to diagnostics."""
    overhead_tokens = estimate_prompt_wrapper_tokens()
    recommended_tokens = recommended_chunk_tokens(config, prompt_overhead_tokens=overhead_tokens)
    return {
        "max_input_tokens": config.token_budget.max_input_tokens,
        "reserve_output_tokens": config.token_budget.reserve_output_tokens,
        "available_input_tokens": available_input_tokens(config),
        "prompt_overhead_tokens": overhead_tokens,
        "recommended_chunk_tokens": recommended_tokens,
        "recommended_chunk_chars": tokens_to_chars(recommended_tokens),
    }


def available_input_tokens(config: PreprocessingConfig) -> int:
    """Return tokens available for prompt input after output reserve."""
    return config.token_budget.max_input_tokens - config.token_budget.reserve_output_tokens


def estimate_tokens(text: str) -> int:
    """Approximate token count conservatively for mixed Russian/English text."""
    value = str(text)
    if not value:
        return 0
    word_estimate = int(round(len(value.split()) * 1.3))
    char_estimate = int((len(value) + CHARS_PER_TOKEN - 1) / CHARS_PER_TOKEN)
    return max(1, word_estimate, char_estimate)


def estimate_prompt_wrapper_tokens() -> int:
    """Estimate static prompt wrapper tokens without user course content."""
    marker_context = {
        "course_a": {"text": ""},
        "course_b": {"text": ""},
        "skill_dictionary": {"text": ""},
        "assessments": {"text": ""},
        "retrieved_pairs": {"text": "[]"},
        "warnings": [],
    }
    return estimate_tokens(build_prompt(marker_context))


def recommended_chunk_tokens(
    config: PreprocessingConfig,
    *,
    prompt_overhead_tokens: int | None = None,
    evidence_items: int = DEFAULT_EVIDENCE_ITEMS,
) -> int:
    """Calculate a safe chunk size from model budget and prompt overhead."""
    overhead = prompt_overhead_tokens if prompt_overhead_tokens is not None else estimate_prompt_wrapper_tokens()
    available = available_input_tokens(config) - overhead
    if available < config.chunking.min_chunk_tokens + MIN_PROMPT_PAYLOAD_TOKENS:
        raise PreprocessingBudgetError(
            "model_context_too_small",
            "Model context is too small for the prompt wrapper plus one minimum chunk. "
            "Increase `preprocessing.token_budget.max_input_tokens` or reduce output reserve.",
        )
    safe_items = max(1, evidence_items)
    raw_recommended = max(config.chunking.min_chunk_tokens, available // (safe_items * 2))
    if config.chunking.max_chunk_tokens is not None:
        raw_recommended = min(raw_recommended, config.chunking.max_chunk_tokens)
    if config.chunking.target_chunk_tokens is not None:
        raw_recommended = min(raw_recommended, config.chunking.target_chunk_tokens)
    return max(config.chunking.min_chunk_tokens, raw_recommended)


def tokens_to_chars(tokens: int) -> int:
    """Convert token budget to conservative character budget."""
    return max(1, tokens * CHARS_PER_TOKEN)


def apply_chunk_sizing_policy(config: PreprocessingConfig) -> tuple[PreprocessingConfig, dict[str, Any], list[str]]:
    """Return a config with safe chunk char limits and diagnostics."""
    metrics = budget_metrics(config)
    safe_chars = metrics["recommended_chunk_chars"]
    configured_chars = config.chunking.max_chunk_chars
    warnings: list[str] = []
    if configured_chars <= safe_chars:
        return config, metrics, warnings

    message = (
        "`preprocessing.chunking.max_chunk_chars` exceeds the safe limit for this model context "
        f"({configured_chars} configured, {safe_chars} recommended)."
    )
    if config.chunking.strict:
        raise PreprocessingBudgetError(
            "chunk_too_large_for_model",
            f"{message} Reduce chunk size or increase `preprocessing.token_budget.max_input_tokens`.",
        )
    warnings.append(f"{message} Auto-adjusted chunk size to {safe_chars}.")
    return (
        replace(config, chunking=replace(config.chunking, max_chunk_chars=safe_chars)),
        metrics,
        warnings,
    )


def validate_prompt_size(estimated_tokens: int, config: PreprocessingConfig, code: str) -> None:
    """Raise a user-facing budget error when a prompt estimate exceeds budget."""
    available = available_input_tokens(config)
    if not config.token_budget.enabled or estimated_tokens <= available:
        return
    if code == "input_too_large_without_chunking":
        message = (
            "Input is too large for the configured model context without chunking. "
            "Enable `preprocessing.enabled` and `preprocessing.chunking.enabled`, "
            "or increase `preprocessing.token_budget.max_input_tokens`."
        )
    else:
        message = (
            "Prompt still exceeds the configured model context after chunking. "
            "Reduce `preprocessing.retrieval.top_k`, reduce chunk size, or increase "
            "`preprocessing.token_budget.max_input_tokens`."
        )
    raise PreprocessingBudgetError(code, message)


def estimate_prompt_tokens_from_context(context: dict[str, Any]) -> int:
    """Estimate tokens for a rendered LLM prompt context."""
    return estimate_tokens(build_prompt(context))


def _clip_pair_text(pair: dict[str, Any], max_chars: int) -> dict[str, Any]:
    item = dict(pair)
    item["course_a_text"] = _clip(str(item.get("course_a_text", "")), max_chars)
    item["course_b_text"] = _clip(str(item.get("course_b_text", "")), max_chars)
    return item


def _estimate_pairs_tokens(pairs: list[dict[str, Any]]) -> int:
    return estimate_tokens(" ".join(
        f"{pair.get('course_a_title', '')} {pair.get('course_a_text', '')} "
        f"{pair.get('course_b_title', '')} {pair.get('course_b_text', '')}"
        for pair in pairs
    ))


def _clip(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "..."
