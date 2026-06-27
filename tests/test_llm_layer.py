from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from course_connector.llm_layer import (
    ALLOWED_RELATION_TYPES,
    MockLLMProvider,
    StaticLLMProvider,
    analyze_courses,
    build_prompt,
    build_prompt_context,
)


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

    assert "raw_response" not in default
    assert "prompt" not in default
    assert debug["raw_response"] == response
    assert "Course-Connector MVP Analysis Prompt" in debug["prompt"]


def test_context_builder_uses_input_payload_without_file_paths() -> None:
    payload = _payload()
    payload["course_a"]["source_path"] = "/tmp/deleted-course-a.yaml"

    context = build_prompt_context(payload)

    assert context["course_a"]["text"] == "Course A introduces Python basics."
    assert context["course_a"]["source_path"] == "/tmp/deleted-course-a.yaml"


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
