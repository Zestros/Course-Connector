"""Create providers from LLM configuration."""

from __future__ import annotations

from course_connector.llm_layer.config import LLMConfig, LLMConfigurationError
from course_connector.llm_layer.providers.base import LLMProvider
from course_connector.llm_layer.providers.mock_provider import MockLLMProvider
from course_connector.llm_layer.providers.openrouter_provider import OpenRouterProvider


def create_provider(config: LLMConfig) -> LLMProvider:
    """Create an LLM provider for the configured provider name."""
    provider = config.provider.strip().lower()
    if provider == "mock":
        return MockLLMProvider()
    if provider == "openrouter":
        return OpenRouterProvider(config=config)
    raise LLMConfigurationError(
        f"Unsupported LLM provider `{config.provider}`. Supported providers: mock, openrouter."
    )
