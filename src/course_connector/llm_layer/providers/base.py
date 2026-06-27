"""Shared provider contract for the LLM layer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LLMResponse:
    """Text response returned by an LLM provider."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Minimal provider contract for LLM-style analysis."""

    @abstractmethod
    def generate(self, prompt: str) -> LLMResponse:
        """Generate a response for a prompt."""
