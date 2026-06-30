"""OpenAI provider using the Responses API."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

from course_connector.llm_layer.config import LLMConfig, OPENAI_API_BASE_URL
from course_connector.llm_layer.providers.base import LLMProvider, LLMResponse


class OpenAIProvider(LLMProvider):
    """Provider for direct OpenAI Responses API calls."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def generate(self, prompt: str) -> LLMResponse:
        api_key = self.config.load_openai_api_key()
        payload = {
            "model": self.config.model,
            "input": prompt,
        }
        request = urllib.request.Request(
            _responses_url(self.config.api_base_url),
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
            raise RuntimeError(f"OpenAI request failed with HTTP {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("OpenAI request failed before receiving a response.") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise RuntimeError("OpenAI request timed out before receiving a response.") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("OpenAI returned a response that was not valid JSON.") from exc

        return LLMResponse(
            text=_extract_text(response_data),
            metadata={
                "provider": "openai",
                "mode": "api",
                "model": self.config.model,
            },
        )


def _responses_url(api_base_url: str) -> str:
    normalized = (api_base_url or OPENAI_API_BASE_URL).rstrip("/")
    if normalized.endswith("/responses"):
        return normalized
    return f"{normalized}/responses"


def _extract_text(response_data: dict[str, object]) -> str:
    output_text = response_data.get("output_text")
    if isinstance(output_text, str) and output_text:
        return output_text

    fragments: list[str] = []
    output = response_data.get("output")
    if isinstance(output, list):
        for output_item in output:
            if not isinstance(output_item, dict):
                continue
            content = output_item.get("content")
            if not isinstance(content, list):
                continue
            for content_item in content:
                if not isinstance(content_item, dict):
                    continue
                if content_item.get("type") not in {"output_text", "text"}:
                    continue
                text = content_item.get("text")
                if isinstance(text, str) and text:
                    fragments.append(text)

    if fragments:
        return "".join(fragments)
    raise RuntimeError("OpenAI response did not include text output.")
