"""Configuration for the LLM analysis layer."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class LLMConfigurationError(ValueError):
    """Raised when LLM configuration cannot be used."""


@dataclass(frozen=True)
class LLMConfig:
    """Runtime settings for provider selection and generation options."""

    provider: str = "mock"
    model: str = "openai/gpt-oss-120b:free"
    temperature: float = 0.0
    timeout_seconds: float = 60.0
    debug: bool = False
    prompt_template: str = "default_analysis_prompt.md"
    output_language: str = "ru"
    api_key_file: Path | None = None
    api_base_url: str = "https://openrouter.ai/api/v1/chat/completions"

    @classmethod
    def from_input_payload(cls, input_payload: dict[str, Any] | None = None) -> "LLMConfig":
        """Build config from defaults, optional input config, and environment overrides."""
        payload = input_payload or {}
        data = _llm_section_from_payload(payload)
        config = cls(
            provider=str(data.get("provider") or cls.provider).strip() or cls.provider,
            model=str(data.get("model") or cls.model),
            temperature=_float_setting(data.get("temperature"), cls.temperature, "temperature"),
            timeout_seconds=_float_setting(data.get("timeout_seconds"), cls.timeout_seconds, "timeout_seconds"),
            debug=_bool_setting(data.get("debug"), cls.debug),
            prompt_template=str(data.get("prompt_template") or cls.prompt_template),
            output_language=_language_setting(
                data.get("output_language") or _top_level_setting(payload, "output_language"),
                cls.output_language,
            ),
            api_key_file=_optional_path(data.get("api_key_file")),
            api_base_url=str(data.get("api_base_url") or cls.api_base_url),
        )
        return config.with_environment_overrides()

    def with_environment_overrides(self) -> "LLMConfig":
        """Apply non-secret environment overrides."""
        return LLMConfig(
            provider=os.getenv("COURSE_CONNECTOR_LLM_PROVIDER", self.provider),
            model=os.getenv("OPENROUTER_MODEL", self.model),
            temperature=_float_setting(
                os.getenv("COURSE_CONNECTOR_LLM_TEMPERATURE"),
                self.temperature,
                "COURSE_CONNECTOR_LLM_TEMPERATURE",
            ),
            timeout_seconds=_float_setting(
                os.getenv("COURSE_CONNECTOR_LLM_TIMEOUT_SECONDS"),
                self.timeout_seconds,
                "COURSE_CONNECTOR_LLM_TIMEOUT_SECONDS",
            ),
            debug=_bool_setting(os.getenv("COURSE_CONNECTOR_LLM_DEBUG"), self.debug),
            prompt_template=os.getenv("COURSE_CONNECTOR_LLM_PROMPT_TEMPLATE", self.prompt_template),
            output_language=_language_setting(
                os.getenv("COURSE_CONNECTOR_OUTPUT_LANGUAGE") or os.getenv("COURSE_CONNECTOR_LLM_OUTPUT_LANGUAGE"),
                self.output_language,
            ),
            api_key_file=_optional_path(os.getenv("OPENROUTER_API_KEY_FILE")) or self.api_key_file,
            api_base_url=os.getenv("OPENROUTER_API_BASE_URL", self.api_base_url),
        )

    def load_openrouter_api_key(self) -> str:
        """Load OpenRouter API key without exposing it in errors or metadata."""
        key = os.getenv("OPENROUTER_API_KEY")
        if key and key.strip():
            return key.strip()
        if self.api_key_file is not None and self.api_key_file.is_file():
            key = self.api_key_file.read_text(encoding="utf-8").strip()
            if key:
                return key
        raise LLMConfigurationError(
            "OpenRouter provider requires OPENROUTER_API_KEY or configured api_key_file."
        )


def _llm_section_from_payload(input_payload: dict[str, Any]) -> dict[str, Any]:
    config_entry = input_payload.get("config")
    parsed_data = config_entry.get("parsed_data") if isinstance(config_entry, dict) else None
    if not isinstance(parsed_data, dict):
        return {}
    llm_data = parsed_data.get("llm")
    return dict(llm_data) if isinstance(llm_data, dict) else {}


def _top_level_setting(input_payload: dict[str, Any], name: str) -> Any:
    config_entry = input_payload.get("config")
    parsed_data = config_entry.get("parsed_data") if isinstance(config_entry, dict) else None
    if not isinstance(parsed_data, dict):
        return None
    return parsed_data.get(name)


def _float_setting(value: Any, default: float, name: str) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise LLMConfigurationError(f"LLM setting `{name}` must be numeric.") from exc


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
    raise LLMConfigurationError("LLM boolean setting must be true or false.")


def _language_setting(value: Any, default: str) -> str:
    if value is None or value == "":
        return default
    normalized = str(value).strip().lower()
    aliases = {
        "russian": "ru",
        "русский": "ru",
        "ru": "ru",
        "english": "en",
        "английский": "en",
        "en": "en",
    }
    language = aliases.get(normalized)
    if language is None:
        raise LLMConfigurationError("LLM output language must be `ru` or `en`.")
    return language


def _optional_path(value: Any) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    return Path(str(value)).expanduser()
