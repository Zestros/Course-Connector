from __future__ import annotations

import json
import os
import sys
import urllib.error
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
from course_connector.llm_layer.batch_analyzer import analyze_batches
from course_connector.llm_layer.findings_merge import merge_findings
from course_connector.llm_layer.parsing import normalize_relations, parse_provider_response
from course_connector.llm_layer.providers import openrouter_provider as openrouter_module
from course_connector.llm_layer.providers import openai_provider as openai_module
from course_connector.llm_layer.providers import routerai_provider as routerai_module
from course_connector.llm_layer.providers.factory import create_provider
from course_connector.llm_layer.providers.openai_provider import OpenAIProvider
from course_connector.llm_layer.providers.openrouter_provider import OpenRouterProvider
from course_connector.llm_layer.providers.routerai_provider import RouterAIProvider


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


def test_strict_evidence_prompt_requires_pair_level_findings() -> None:
    payload = _payload()
    payload["preprocessing"] = {
        "enabled": True,
        "selected_chunks": [
            {
                "chunk_id": "course_a_section_001",
                "source_role": "course_a",
                "source_path": "course_a.md",
                "source_type": "raw_section",
                "title": "Practice",
                "text": "Course A teaches git_status_diff.",
                "skill_ids": ["git_status_diff"],
                "locator": {"kind": "line_range", "line_start": 1, "line_end": 3},
            }
        ],
        "retrieved_pairs": [
            {
                "pair_id": "retrieved_001",
                "candidate_relation_hint": "useful_repetition_candidate",
                "retrieval_reason": "keyword retrieval",
                "course_a_chunk_id": "course_a_section_001",
                "course_b_chunk_id": "course_b_section_001",
                "course_a_title": "Practice",
                "course_b_title": "Review",
                "course_a_text": "Course A teaches git_status_diff.",
                "course_b_text": "Course B reviews pull request diffs.",
                "matched_skill_ids": ["git_status_diff"],
                "evidence_refs": [{"chunk_id": "course_a_section_001"}],
            }
        ],
        "metrics": {"retrieved_pairs": 1, "selected_chunks": 1},
    }

    prompt = build_prompt(
        build_prompt_context(payload),
        template_name="strict_evidence_analysis_prompt.md",
    )

    assert "Inspect every retrieved evidence pair before writing the answer." in prompt
    assert "Do not collapse different skills" in prompt
    assert "Prefer 4 to 8 relations" in prompt
    assert "Each relation must cite evidence_refs" in prompt
    assert "retrieved_001" in prompt
    assert "git_status_diff" in prompt


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


def test_full_input_context_does_not_truncate_after_legacy_preview_limit() -> None:
    payload = _payload()
    tail_marker = "TAIL_SKILL_AFTER_1200_CHARS"
    long_text = "# Course A\n" + ("filler text " * 180) + tail_marker
    payload["course_a"]["normalized_text"] = long_text

    prompt = build_prompt(build_prompt_context(payload))

    assert tail_marker in prompt


def test_batch_analyzer_preserves_successful_results_when_one_batch_fails() -> None:
    class OneFailureProvider(StaticLLMProvider):
        def __init__(self) -> None:
            super().__init__("")
            self.calls = 0

        def generate(self, prompt: str):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("simulated reset")
            return super().generate(prompt)

    response = json.dumps({
        "summary": "batch ok",
        "findings": [
            {
                "type": "probable_gap",
                "course_a_fragment": "A",
                "course_b_fragment": "B",
                "explanation": "E",
                "confidence": 0.7,
                "skill_ids": ["skill_a"],
                "evidence_refs": ["chunk_a"],
            }
        ],
        "warnings": [],
    })
    provider = OneFailureProvider()
    provider.text = response
    payload = _payload()
    payload["preprocessing"] = {
        "enabled": True,
        "analysis_mode": "smart_batch",
        "skill_batches": [_batch("batch_001"), _batch("batch_002")],
        "metrics": {},
    }

    analysis, updates = analyze_batches(payload, provider=provider)

    assert len(analysis["relations"]) == 1
    assert analysis["relations"][0]["batch_id"] == "batch_001"
    assert updates["metrics"]["executed_batches"] == 2
    assert updates["metrics"]["failed_batches"] == 1
    assert any("batch_002" in warning for warning in analysis["warnings"])


def test_batch_analyzer_skips_diagnostic_only_batches_without_provider_call() -> None:
    class CountingProvider(StaticLLMProvider):
        def __init__(self) -> None:
            super().__init__(json.dumps({"summary": "", "findings": [], "warnings": []}))
            self.calls = 0

        def generate(self, prompt: str):  # type: ignore[no-untyped-def]
            self.calls += 1
            return super().generate(prompt)

    provider = CountingProvider()
    batch = _batch("general_course_b_001")
    batch["diagnostic_only"] = True
    payload = _payload()
    payload["preprocessing"] = {
        "enabled": True,
        "analysis_mode": "smart_batch",
        "skill_batches": [batch],
        "metrics": {},
    }

    analysis, updates = analyze_batches(payload, provider=provider)

    assert provider.calls == 0
    assert analysis["status"] == "completed"
    assert analysis["relations"] == []
    assert updates["batch_results"][0]["status"] == "diagnostic_only"
    assert updates["metrics"]["diagnostic_only_batches"] == 1
    assert updates["metrics"]["executed_batches"] == 0


def test_batch_analyzer_filters_one_sided_repetition_findings() -> None:
    response = json.dumps({
        "summary": "batch ok",
        "findings": [
            {
                "type": "useful_repetition",
                "course_a_fragment": "",
                "course_b_fragment": "B",
                "explanation": "Internal repeat",
                "confidence": 0.9,
                "skill_ids": ["skill_a"],
                "evidence_refs": ["chunk_b"],
            },
            {
                "type": "useful_repetition",
                "course_a_fragment": "A",
                "course_b_fragment": "B",
                "explanation": "Cross-course repeat",
                "confidence": 0.8,
                "skill_ids": ["skill_a"],
                "evidence_refs": ["chunk_a", "chunk_b"],
            },
        ],
        "warnings": [],
    })
    payload = _payload()
    payload["preprocessing"] = {
        "enabled": True,
        "analysis_mode": "smart_batch",
        "skill_batches": [_batch("batch_001")],
        "metrics": {},
    }

    analysis, updates = analyze_batches(payload, provider=StaticLLMProvider(response))

    assert len(analysis["relations"]) == 1
    assert analysis["relations"][0]["explanation"] == "Cross-course repeat"
    assert len(updates["batch_results"][0]["findings"]) == 1
    assert updates["batch_results"][0]["findings"][0]["explanation"] == "Cross-course repeat"
    assert any("without Course A and Course B evidence" in warning for warning in analysis["warnings"])


def test_batch_analyzer_adds_gap_for_course_b_only_skill_batch() -> None:
    response = json.dumps({"summary": "batch ok", "findings": [], "warnings": []})
    batch = _batch("skill_001_github_actions_ci")
    batch["skill_ids"] = ["github_actions_ci"]
    batch["skill_dictionary_subset"] = [{"id": "github_actions_ci", "title": "GitHub Actions CI", "aliases": []}]
    batch["course_profiles"] = {
        "course_a": {
            "description": "Course A mentions GitHub Actions only as context.",
            "excluded_topics": ["Course A does not teach GitHub Actions in detail."],
            "profile_chunk_ids": ["course_a_section_002"],
        }
    }
    batch["course_a_chunks"] = [
        {
            "chunk_id": "course_a_section_002",
            "text": "GitHub Actions are mentioned only as context and are not the main subject.",
            "source_role": "course_a",
        }
    ]
    batch["course_a_chunk_ids"] = ["course_a_section_002"]
    batch["course_b_chunks"] = [
        {
            "chunk_id": "course_b_section_022",
            "text": "Students add a GitHub Actions workflow and fix failed checks.",
            "source_role": "course_b",
        }
    ]
    batch["course_b_chunk_ids"] = ["course_b_section_022"]
    payload = _payload()
    payload["preprocessing"] = {
        "enabled": True,
        "analysis_mode": "smart_batch",
        "skill_batches": [batch],
        "metrics": {},
    }

    analysis, updates = analyze_batches(payload, provider=StaticLLMProvider(response))

    assert len(analysis["relations"]) == 1
    relation = analysis["relations"][0]
    assert relation["type"] == "probable_gap"
    assert relation["skill_ids"] == ["github_actions_ci"]
    assert relation["evidence_refs"] == ["course_a_section_002", "course_b_section_022"]
    assert updates["metrics"]["executed_batches"] == 1


def test_findings_merge_keeps_distinct_skills_separate() -> None:
    findings = [
        {
            "type": "probable_gap",
            "skill_ids": ["skill_a"],
            "evidence_refs": ["chunk_a"],
            "confidence": 0.6,
            "batch_id": "batch_a",
        },
        {
            "type": "probable_gap",
            "skill_ids": ["skill_b"],
            "evidence_refs": ["chunk_b"],
            "confidence": 0.8,
            "batch_id": "batch_b",
        },
    ]

    assert len(merge_findings(findings)) == 2


def test_config_selects_mock_by_default() -> None:
    config = LLMConfig.from_input_payload(_payload())

    assert config.provider == "mock"
    assert isinstance(create_provider(config), MockLLMProvider)


def test_project_default_config_uses_openai_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COURSE_CONNECTOR_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("COURSE_CONNECTOR_LLM_MODEL", raising=False)
    monkeypatch.delenv("COURSE_CONNECTOR_LLM_API_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    config_path = PROJECT_ROOT / "configs" / "default.yaml"
    payload = _payload()
    payload["config"] = {
        "source_path": str(config_path),
        "format": "yaml",
        "raw_text": config_path.read_text(encoding="utf-8"),
        "parsed_data": yaml.safe_load(config_path.read_text(encoding="utf-8")),
    }

    config = LLMConfig.from_input_payload(payload)

    assert config.provider == "openai"
    assert config.model == "gpt-5.4-mini"
    assert config.api_key_file == Path("LLM_apikey/openai-key.txt")
    assert config.api_base_url == "https://api.openai.com/v1"
    assert isinstance(create_provider(config), OpenAIProvider)


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


def test_config_can_select_routerai_without_changing_input_boundary() -> None:
    payload = _payload()
    payload["config"] = {
        "source_path": "config.yaml",
        "format": "yaml",
        "raw_text": "llm:\n  provider: routerai\n",
        "parsed_data": {
            "llm": {
                "provider": "routerai",
                "model": "openai/gpt-5.4-mini",
                "temperature": 0.1,
                "api_key_file": "LLM_apikey/routerai_key.txt",
                "api_base_url": "https://routerai.ru/api/v1",
            }
        },
    }

    config = LLMConfig.from_input_payload(payload)
    provider = create_provider(config)

    assert config.provider == "routerai"
    assert config.model == "openai/gpt-5.4-mini"
    assert config.temperature == 0.1
    assert config.api_base_url == "https://routerai.ru/api/v1"
    assert isinstance(provider, RouterAIProvider)


def test_config_can_select_openai_without_changing_input_boundary() -> None:
    payload = _payload()
    payload["config"] = {
        "source_path": "config.yaml",
        "format": "yaml",
        "raw_text": "llm:\n  provider: openai\n",
        "parsed_data": {
            "llm": {
                "provider": "openai",
                "model": "gpt-5.4-mini",
                "temperature": 0.1,
                "api_key_file": "LLM_apikey/openai-key.txt",
                "api_base_url": "https://api.openai.com/v1",
            }
        },
    }

    config = LLMConfig.from_input_payload(payload)
    provider = create_provider(config)

    assert config.provider == "openai"
    assert config.model == "gpt-5.4-mini"
    assert config.temperature == 0.1
    assert config.api_base_url == "https://api.openai.com/v1"
    assert isinstance(provider, OpenAIProvider)


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


def test_openrouter_missing_key_error_does_not_expose_secret_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    config = LLMConfig(provider="openrouter", api_key_file=tmp_path / "missing-key.txt")

    with pytest.raises(LLMConfigurationError) as exc_info:
        config.load_openrouter_api_key()

    assert "missing-key.txt" not in str(exc_info.value)
    assert "OPENROUTER_API_KEY" in str(exc_info.value)


def test_openrouter_generate_posts_prompt_and_extracts_text(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"choices": [{"message": {"content": "provider text"}}]}).encode("utf-8")

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(openrouter_module.urllib.request, "urlopen", fake_urlopen)

    response = OpenRouterProvider(
        LLMConfig(provider="openrouter", model="test-model", timeout_seconds=12)
    ).generate("hello prompt")

    request = captured["request"]
    payload = json.loads(request.data.decode("utf-8"))  # type: ignore[attr-defined]
    assert payload["model"] == "test-model"
    assert payload["messages"][0]["content"] == "hello prompt"
    assert request.get_header("Authorization") == "Bearer test-key"  # type: ignore[attr-defined]
    assert captured["timeout"] == 12
    assert response.text == "provider text"
    assert response.metadata == {"provider": "openrouter", "mode": "api", "model": "test-model"}


def test_openai_key_prefers_environment_and_is_not_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_file = tmp_path / "openai-key.txt"
    key_file.write_text("file-key", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")

    config = LLMConfig(provider="openai", api_key_file=key_file)

    assert config.load_openai_api_key() == "env-key"
    provider = OpenAIProvider(config)
    assert "env-key" not in repr(provider)


def test_openai_missing_key_error_does_not_expose_secret_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("COURSE_CONNECTOR_LLM_API_KEY", raising=False)
    config = LLMConfig(provider="openai", api_key_file=tmp_path / "missing-openai-key.txt")

    with pytest.raises(LLMConfigurationError) as exc_info:
        config.load_openai_api_key()

    assert "missing-openai-key.txt" not in str(exc_info.value)
    assert "OPENAI_API_KEY" in str(exc_info.value)


def test_openai_generate_posts_prompt_and_extracts_text(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"output_text": "provider text"}).encode("utf-8")

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(openai_module.urllib.request, "urlopen", fake_urlopen)

    response = OpenAIProvider(
        LLMConfig(
            provider="openai",
            model="gpt-5.4-mini",
            timeout_seconds=12,
            api_base_url="https://api.openai.com/v1",
        )
    ).generate("hello prompt")

    request = captured["request"]
    payload = json.loads(request.data.decode("utf-8"))  # type: ignore[attr-defined]
    assert request.full_url == "https://api.openai.com/v1/responses"  # type: ignore[attr-defined]
    assert payload == {"model": "gpt-5.4-mini", "input": "hello prompt"}
    assert request.get_header("Authorization") == "Bearer test-key"  # type: ignore[attr-defined]
    assert captured["timeout"] == 12
    assert response.text == "provider text"
    assert response.metadata == {"provider": "openai", "mode": "api", "model": "gpt-5.4-mini"}


def test_openai_extract_text_reads_nested_responses_content() -> None:
    response_data = {
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": "first "},
                    {"type": "output_text", "text": "second"},
                ]
            }
        ]
    }

    assert openai_module._extract_text(response_data) == "first second"


def test_openai_extract_text_rejects_malformed_response() -> None:
    with pytest.raises(RuntimeError, match="did not include text output"):
        openai_module._extract_text({"output": []})


def test_routerai_key_prefers_environment_and_is_not_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_file = tmp_path / "routerai-key.txt"
    key_file.write_text("file-key", encoding="utf-8")
    monkeypatch.setenv("ROUTERAI_API_KEY", "env-key")

    config = LLMConfig(provider="routerai", api_key_file=key_file)

    assert config.load_routerai_api_key() == "env-key"
    provider = RouterAIProvider(config)
    assert "env-key" not in repr(provider)


def test_routerai_missing_key_error_does_not_expose_secret_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ROUTERAI_API_KEY", raising=False)
    monkeypatch.delenv("COURSE_CONNECTOR_LLM_API_KEY", raising=False)
    config = LLMConfig(provider="routerai", api_key_file=tmp_path / "missing-routerai-key.txt")

    with pytest.raises(LLMConfigurationError) as exc_info:
        config.load_routerai_api_key()

    assert "missing-routerai-key.txt" not in str(exc_info.value)
    assert "ROUTERAI_API_KEY" in str(exc_info.value)


def test_routerai_generate_posts_prompt_and_extracts_text(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"choices": [{"message": {"content": "provider text"}}]}).encode("utf-8")

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("ROUTERAI_API_KEY", "test-key")
    monkeypatch.setattr(routerai_module.urllib.request, "urlopen", fake_urlopen)

    response = RouterAIProvider(
        LLMConfig(
            provider="routerai",
            model="openai/gpt-5.4-mini",
            timeout_seconds=12,
            api_base_url="https://routerai.ru/api/v1",
        )
    ).generate("hello prompt")

    request = captured["request"]
    payload = json.loads(request.data.decode("utf-8"))  # type: ignore[attr-defined]
    assert request.full_url == "https://routerai.ru/api/v1/chat/completions"  # type: ignore[attr-defined]
    assert payload["model"] == "openai/gpt-5.4-mini"
    assert payload["messages"][0]["content"] == "hello prompt"
    assert request.get_header("Authorization") == "Bearer test-key"  # type: ignore[attr-defined]
    assert captured["timeout"] == 12
    assert response.text == "provider text"
    assert response.metadata == {"provider": "routerai", "mode": "api", "model": "openai/gpt-5.4-mini"}


def test_routerai_default_url_is_used_when_openrouter_default_is_still_on_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"choices": [{"message": {"content": "provider text"}}]}).encode("utf-8")

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        captured["url"] = request.full_url  # type: ignore[attr-defined]
        return FakeResponse()

    monkeypatch.setenv("ROUTERAI_API_KEY", "test-key")
    monkeypatch.setattr(routerai_module.urllib.request, "urlopen", fake_urlopen)

    RouterAIProvider(LLMConfig(provider="routerai")).generate("hello prompt")

    assert captured["url"] == "https://routerai.ru/api/v1/chat/completions"


@pytest.mark.parametrize(
    ("response_data", "message"),
    [
        ({}, "did not include choices"),
        ({"choices": []}, "did not include choices"),
        ({"choices": ["bad"]}, "choice was not an object"),
        ({"choices": [{}]}, "did not include a message"),
        ({"choices": [{"message": {}}]}, "did not include text content"),
    ],
)
def test_openrouter_extract_text_rejects_malformed_responses(
    response_data: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(RuntimeError, match=message):
        openrouter_module._extract_text(response_data)


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (
            urllib.error.HTTPError(url="", code=429, msg="Too Many Requests", hdrs=None, fp=None),
            "HTTP 429",
        ),
        (urllib.error.URLError("dns failed"), "before receiving a response"),
        (TimeoutError("slow"), "timed out"),
    ],
)
def test_openrouter_generate_wraps_transport_errors(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    message: str,
) -> None:
    def fake_urlopen(request: object, timeout: float) -> object:
        raise error

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(openrouter_module.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match=message):
        OpenRouterProvider(LLMConfig(provider="openrouter")).generate("prompt")


def test_openrouter_generate_rejects_non_json_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"not json"

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(openrouter_module.urllib.request, "urlopen", lambda request, timeout: FakeResponse())

    with pytest.raises(RuntimeError, match="not valid JSON"):
        OpenRouterProvider(LLMConfig(provider="openrouter")).generate("prompt")


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


def _batch(batch_id: str) -> dict[str, object]:
    return {
        "batch_id": batch_id,
        "batch_type": "skill",
        "skill_ids": ["skill_a"],
        "skill_dictionary_subset": [{"id": "skill_a", "title": "Skill A", "aliases": []}],
        "course_profiles": {},
        "course_a_chunks": [{"chunk_id": "chunk_a", "text": "A", "source_role": "course_a"}],
        "course_b_chunks": [{"chunk_id": "chunk_b", "text": "B", "source_role": "course_b"}],
        "assessment_chunks": [],
        "course_a_chunk_ids": ["chunk_a"],
        "course_b_chunk_ids": ["chunk_b"],
        "assessment_chunk_ids": [],
    }
