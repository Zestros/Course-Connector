"""RouterAI provider using an OpenAI-compatible chat completions API."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

from course_connector.llm_layer.config import LLMConfig, OPENROUTER_API_BASE_URL, ROUTERAI_API_BASE_URL
from course_connector.llm_layer.providers.base import LLMProvider, LLMResponse


class RouterAIProvider(LLMProvider):
    """Provider for RouterAI chat completions."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def generate(self, prompt: str) -> LLMResponse:
        api_key = self.config.load_routerai_api_key()
        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": self.config.temperature,
        }
        request = urllib.request.Request(
            _chat_completions_url(self.config.api_base_url),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"RouterAI request failed with HTTP {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("RouterAI request failed before receiving a response.") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise RuntimeError("RouterAI request timed out before receiving a response.") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("RouterAI returned a response that was not valid JSON.") from exc

        return LLMResponse(
            text=_extract_text(response_data),
            metadata={
                "provider": "routerai",
                "mode": "api",
                "model": self.config.model,
            },
        )


def _chat_completions_url(api_base_url: str) -> str:
    normalized = api_base_url.rstrip("/")
    if normalized == OPENROUTER_API_BASE_URL.rstrip("/"):
        normalized = ROUTERAI_API_BASE_URL
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _extract_text(response_data: dict[str, object]) -> str:
    choices = response_data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("RouterAI response did not include choices.")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise RuntimeError("RouterAI response choice was not an object.")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("RouterAI response choice did not include a message.")
    content = message.get("content")
    if not isinstance(content, str):
        raise RuntimeError("RouterAI response message did not include text content.")
    return content
