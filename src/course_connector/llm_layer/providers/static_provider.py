"""Static provider used by unit tests."""

from __future__ import annotations

from typing import Any

from course_connector.llm_layer.providers.base import LLMProvider, LLMResponse


class StaticLLMProvider(LLMProvider):
    """Test provider that returns a fixed response."""

    def __init__(self, text: str, metadata: dict[str, Any] | None = None) -> None:
        self.text = text
        self.metadata = metadata or {"provider": "static", "mode": "test"}

    def generate(self, prompt: str) -> LLMResponse:
        return LLMResponse(text=self.text, metadata=self.metadata)
