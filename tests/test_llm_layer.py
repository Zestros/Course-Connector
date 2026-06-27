from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from course_connector.llm_layer import (
    ALLOWED_RELATION_TYPES,
    LLMConfig,
    LLMConfigurationError,
    MockLLMProvider,
    StaticLLMProvider,
    analyze_courses,
    build_prompt,
    build_prompt_context,
)
from course_connector.llm_layer.parsing import normalize_relations, parse_provider_response
from course_connector.llm_layer.providers.factory import create_provider
from course_connector.llm_layer.providers.openrouter_provider import OpenRouterProvider


class FailingProvider(StaticLLMProvider):
    def __init__(self) -> None:
        super().__init__("")

    def generate(self, prompt: str):  # type: ignore[no-untyped-def]
        raise RuntimeError("simulated provider failure")


def test_mock_provider_returns_deterministic_analysis_shape() -> None:
    payload = _payload()

    first = analyze_courses(payload, provider=MockLLMProvider())
    second = analyze_courses(payload, provider=MockLLMProvider())

    assert first["summary"]
    assert first["relations"] == second["relations"]
    assert {relation["type"] for relation in first["relations"]} == set(ALLOWED_RELATION_TYPES)
    assert first["provider_mode"] == "mock"


def test_prompt_contains_inputs_and_allowed_relation_types() -> None:
    prompt = build_prompt(build_prompt_context(_payload()))

    assert "Course A introduces Python basics" in prompt
    assert "Course B validates CLI files" in prompt
    assert "python_basics" in prompt
    assert "CLI practical task" in prompt
    assert "Return only valid JSON" in prompt
    for relation_type in ALLOWED_RELATION_TYPES:
        assert relation_type in prompt


def test_prompt_uses_configured_output_language() -> None:
    context = build_prompt_context(_payload())

    russian_prompt = build_prompt(context, output_language="ru")
    english_prompt = build_prompt(context, output_language="en")

    assert "Write all natural-language JSON values in Russian." in russian_prompt
    assert "Write all natural-language JSON values in English." in english_prompt


def test_valid_provider_json_is_parsed_and_normalized() -> None:
    response = {
        "summary": "Parsed summary",
        "relations": [
            {
                "type": "useful_repetition",
                "course_a_fragment": "A",
                "course_b_fragment": "B",
                "explanation": "Repeated skill",
                "confidence": "0.8",
            }
        ],
        "warnings": ["provider warning"],
    }

    analysis = analyze_courses(_payload(), provider=StaticLLMProvider(json.dumps(response)))

    assert analysis["summary"] == "Parsed summary"
    assert analysis["relations"] == [
        {
            "type": "useful_repetition",
            "course_a_fragment": "A",
            "course_b_fragment": "B",
            "explanation": "Repeated skill",
            "confidence": 0.8,
        }
    ]
    assert "provider warning" in analysis["warnings"]


def test_invalid_provider_json_returns_fallback_warning() -> None:
    analysis = analyze_courses(_payload(), provider=StaticLLMProvider("not json"))

    assert analysis["relations"] == []
    assert analysis["summary"] == "Provider response could not be parsed as JSON."
    assert any("Provider JSON could not be parsed" in warning for warning in analysis["warnings"])


def test_provider_failure_returns_stable_error_result() -> None:
    analysis = analyze_courses(_payload(), provider=FailingProvider(), config=LLMConfig(provider="openrouter"))

    assert analysis["status"] == "provider_error"
    assert analysis["relations"] == []
    assert analysis["provider"] == "openrouter"
    assert analysis["provider_mode"] == "error"
    assert any("simulated provider failure" in warning for warning in analysis["warnings"])


def test_unsupported_relation_type_is_reported() -> None:
    response = {
        "summary": "Unsupported relation",
        "relations": [
            {
                "type": "possible_gap",
                "course_a_fragment": "A",
                "course_b_fragment": "B",
                "explanation": "Wrong terminology",
                "confidence": 0.5,
            }
        ],
        "warnings": [],
    }

    analysis = analyze_courses(_payload(), provider=StaticLLMProvider(json.dumps(response)))

    assert analysis["relations"] == []
    assert any("Unsupported relation type `possible_gap`" in warning for warning in analysis["warnings"])


def test_debug_mode_includes_raw_response_and_default_mode_omits_it() -> None:
    response = json.dumps({"summary": "S", "relations": [], "warnings": []})
    default = analyze_courses(_payload(), provider=StaticLLMProvider(response))
    debug = analyze_courses(_payload(), provider=StaticLLMProvider(response), debug=True)
    positional_debug = analyze_courses(_payload(), StaticLLMProvider(response), True)

    assert "raw_response" not in default
    assert "prompt" not in default
    assert debug["raw_response"] == response
    assert "Course-Connector MVP Analysis Prompt" in debug["prompt"]
    assert positional_debug["raw_response"] == response


def test_context_builder_uses_input_payload_without_file_paths() -> None:
    payload = _payload()
    payload["course_a"]["source_path"] = "/tmp/deleted-course-a.yaml"

    context = build_prompt_context(payload)

    assert context["course_a"]["text"] == "Course A introduces Python basics."
    assert context["course_a"]["source_path"] == "/tmp/deleted-course-a.yaml"


def test_config_selects_mock_by_default() -> None:
    config = LLMConfig.from_input_payload(_payload())

    assert config.provider == "mock"
    assert isinstance(create_provider(config), MockLLMProvider)


def test_project_default_config_uses_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COURSE_CONNECTOR_LLM_PROVIDER", raising=False)
    config_path = PROJECT_ROOT / "configs" / "default.yaml"
    payload = _payload()
    payload["config"] = {
        "source_path": str(config_path),
        "format": "yaml",
        "raw_text": config_path.read_text(encoding="utf-8"),
        "parsed_data": yaml.safe_load(config_path.read_text(encoding="utf-8")),
    }

    config = LLMConfig.from_input_payload(payload)

    assert config.provider == "mock"
    assert config.api_key_file is None
    assert isinstance(create_provider(config), MockLLMProvider)


def test_config_can_select_openrouter_without_changing_input_boundary() -> None:
    payload = _payload()
    payload["config"] = {
        "source_path": "config.yaml",
        "format": "yaml",
        "raw_text": "llm:\n  provider: openrouter\n",
        "parsed_data": {
            "llm": {
                "provider": "openrouter",
                "model": "openai/gpt-oss-120b:free",
                "temperature": 0.1,
                "output_language": "en",
                "api_key_file": "LLM_apikey/key.txt",
            }
        },
    }

    config = LLMConfig.from_input_payload(payload)
    provider = create_provider(config)

    assert config.provider == "openrouter"
    assert config.model == "openai/gpt-oss-120b:free"
    assert config.temperature == 0.1
    assert config.output_language == "en"
    assert isinstance(provider, OpenRouterProvider)


def test_config_uses_top_level_output_language_as_llm_fallback() -> None:
    payload = _payload()
    payload["config"] = {
        "source_path": "config.yaml",
        "format": "yaml",
        "raw_text": "output_language: en\nllm:\n  provider: mock\n",
        "parsed_data": {
            "output_language": "en",
            "llm": {
                "provider": "mock",
            },
        },
    }

    config = LLMConfig.from_input_payload(payload)

    assert config.output_language == "en"


def test_invalid_output_language_has_clear_configuration_error() -> None:
    payload = _payload()
    payload["config"] = {
        "source_path": "config.yaml",
        "format": "yaml",
        "raw_text": "llm:\n  output_language: de\n",
        "parsed_data": {
            "llm": {
                "output_language": "de",
            },
        },
    }

    with pytest.raises(LLMConfigurationError, match="output language"):
        LLMConfig.from_input_payload(payload)


def test_unknown_provider_has_clear_configuration_error() -> None:
    with pytest.raises(LLMConfigurationError, match="Unsupported LLM provider"):
        create_provider(LLMConfig(provider="missing-provider"))


def test_prompt_template_is_loaded_from_package_resources() -> None:
    prompt = build_prompt(build_prompt_context(_payload()))

    assert "# Course-Connector MVP Analysis Prompt" in prompt
    assert "{course_a_text}" not in prompt
    assert "Course A introduces Python basics" in prompt


def test_parser_and_normalizer_keep_stable_shape() -> None:
    parsed = parse_provider_response(
        json.dumps(
            {
                "summary": "S",
                "relations": [
                    {
                        "type": "useful_repetition",
                        "course_a_fragment": "A",
                        "course_b_fragment": "B",
                        "explanation": "E",
                        "confidence": 3,
                    },
                    "bad relation",
                ],
                "warnings": ["W"],
            }
        )
    )
    warnings = list(parsed["warnings"])
    relations = normalize_relations(parsed["relations"], warnings)

    assert parsed["summary"] == "S"
    assert relations[0]["confidence"] == 1.0
    assert any("clamped" in warning for warning in warnings)
    assert any("not an object" in warning for warning in warnings)


def test_openrouter_key_prefers_environment_and_is_not_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_file = tmp_path / "key.txt"
    key_file.write_text("file-key", encoding="utf-8")
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")

    config = LLMConfig(provider="openrouter", api_key_file=key_file)

    assert config.load_openrouter_api_key() == "env-key"
    provider = OpenRouterProvider(config)
    assert "env-key" not in repr(provider)


def test_openrouter_missing_key_error_does_not_expose_secret_path(tmp_path: Path) -> None:
    config = LLMConfig(provider="openrouter", api_key_file=tmp_path / "missing-key.txt")

    with pytest.raises(LLMConfigurationError) as exc_info:
        config.load_openrouter_api_key()

    assert "missing-key.txt" not in str(exc_info.value)
    assert "OPENROUTER_API_KEY" in str(exc_info.value)


def _openrouter_key_file() -> Path:
    return PROJECT_ROOT / "LLM_apikey" / "key.txt"


@pytest.mark.skipif(os.getenv("COURSE_CONNECTOR_RUN_API_TESTS") != "1", reason="API tests are opt-in.")
@pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY") and not _openrouter_key_file().is_file(),
    reason="OpenRouter smoke test requires OPENROUTER_API_KEY or LLM_apikey/key.txt.",
)
def test_openrouter_optional_smoke() -> None:
    response = OpenRouterProvider(
        LLMConfig(
            provider="openrouter",
            model=os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b:free"),
            api_key_file=_openrouter_key_file(),
        )
    ).generate("Return only JSON: {\"summary\":\"ok\",\"relations\":[],\"warnings\":[]}")

    parsed = parse_provider_response(response.text)

    assert "summary" in parsed
    assert response.metadata["provider"] == "openrouter"


def _payload() -> dict[str, object]:
    return {
        "course_a": {
            "source_path": "course_a.yaml",
            "format": "yaml",
            "raw_text": "title: A\n",
            "normalized_text": "Course A introduces Python basics.",
            "parsed_data": {"title": "A"},
        },
        "course_b": {
            "source_path": "course_b.yaml",
            "format": "yaml",
            "raw_text": "title: B\n",
            "normalized_text": "Course B validates CLI files.",
            "parsed_data": {"title": "B"},
        },
        "skill_dictionary": {
            "source_path": "skill_dictionary.yaml",
            "format": "yaml",
            "raw_text": "skills:\n- id: python_basics\n",
            "parsed_data": {"skills": [{"id": "python_basics"}]},
        },
        "assessments": {
            "source_path": "assessments.csv",
            "format": "csv",
            "raw_text": "title\nCLI practical task\n",
            "normalized_text": "CLI practical task",
            "parsed_data": [{"title": "CLI practical task"}],
        },
        "config": None,
        "warnings": [],
    }
