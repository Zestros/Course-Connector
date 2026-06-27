"""OpenRouter provider using only the Python standard library."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from course_connector.llm_layer.config import LLMConfig
from course_connector.llm_layer.providers.base import LLMProvider, LLMResponse


class OpenRouterProvider(LLMProvider):
    """Provider for OpenRouter chat completions."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def generate(self, prompt: str) -> LLMResponse:
        api_key = self.config.load_openrouter_api_key()
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
            self.config.api_base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/Zestros/Course-Connector",
                "X-Title": "Course Connector",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"OpenRouter request failed with HTTP {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("OpenRouter request failed before receiving a response.") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("OpenRouter returned a response that was not valid JSON.") from exc

        return LLMResponse(
            text=_extract_text(response_data),
            metadata={
                "provider": "openrouter",
                "mode": "api",
                "model": self.config.model,
            },
        )


def _extract_text(response_data: dict[str, object]) -> str:
    choices = response_data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("OpenRouter response did not include choices.")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise RuntimeError("OpenRouter response choice was not an object.")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("OpenRouter response choice did not include a message.")
    content = message.get("content")
    if not isinstance(content, str):
        raise RuntimeError("OpenRouter response message did not include text content.")
    return content
