"""LLM layer package."""

from course_connector.llm_layer.analyzer import (
    ALLOWED_RELATION_TYPES,
    analyze_courses,
    build_prompt,
    build_prompt_context,
)
from course_connector.llm_layer.config import LLMConfig, LLMConfigurationError
from course_connector.llm_layer.providers import (
    LLMProvider,
    LLMResponse,
    MockLLMProvider,
    StaticLLMProvider,
)

__all__ = [
    "ALLOWED_RELATION_TYPES",
    "LLMConfig",
    "LLMConfigurationError",
    "LLMProvider",
    "LLMResponse",
    "MockLLMProvider",
    "StaticLLMProvider",
    "analyze_courses",
    "build_prompt",
    "build_prompt_context",
]
