"""Token-budget estimation and compaction for LLM context."""

from __future__ import annotations

from typing import Any

from course_connector.preprocessing_layer.config import PreprocessingConfig


def apply_token_budget(
    pairs: list[dict[str, Any]],
    config: PreprocessingConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    """Compact retrieved pairs to fit the configured prompt budget."""
    warnings: list[str] = []
    if not config.token_budget.enabled:
        return pairs, _metrics(pairs, config), warnings

    compacted = [_clip_pair_text(pair, config.chunking.max_pair_text_chars) for pair in pairs]
    available_tokens = max(1, config.token_budget.max_input_tokens - config.token_budget.reserve_output_tokens)
    while _estimate_pairs_tokens(compacted) > available_tokens and compacted:
        removed = compacted.pop()
        warnings.append(f"Token budget removed retrieved pair `{removed.get('pair_id')}` from LLM context.")
    metrics = _metrics(compacted, config)
    if len(compacted) < len(pairs):
        warnings.append(
            f"Token budget compacted retrieved pairs from {len(pairs)} to {len(compacted)}."
        )
    return compacted, metrics, warnings


def estimate_tokens(text: str) -> int:
    """Approximate token count from whitespace-delimited words."""
    return int(round(len(str(text).split()) * 1.3))


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


def _metrics(pairs: list[dict[str, Any]], config: PreprocessingConfig) -> dict[str, Any]:
    return {
        "estimated_input_tokens": _estimate_pairs_tokens(pairs),
        "max_input_tokens": config.token_budget.max_input_tokens,
        "reserve_output_tokens": config.token_budget.reserve_output_tokens,
    }


def _clip(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "..."
