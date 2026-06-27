"""Deterministic provider for local tests and demos."""

from __future__ import annotations

import json

from course_connector.llm_layer.providers.base import LLMProvider, LLMResponse


class MockLLMProvider(LLMProvider):
    """Deterministic local provider for tests and demos."""

    def generate(self, prompt: str) -> LLMResponse:
        response = {
            "summary": "Mock analysis found candidate relations between the two course inputs.",
            "relations": [
                {
                    "type": "useful_repetition",
                    "course_a_fragment": "Course A introduces a skill that appears again in Course B.",
                    "course_b_fragment": "Course B reuses the skill in a more applied context.",
                    "explanation": "The repeated topic can reinforce learning when coordinated between courses.",
                    "confidence": 0.72,
                },
                {
                    "type": "probable_duplication",
                    "course_a_fragment": "Both courses include overlapping introductory material.",
                    "course_b_fragment": "The same introductory material appears without clear progression.",
                    "explanation": "This may duplicate effort unless Course B adds a new level of practice.",
                    "confidence": 0.62,
                },
                {
                    "type": "probable_gap",
                    "course_a_fragment": "Course A preparation evidence is limited for one later assessment skill.",
                    "course_b_fragment": "Course B assessment expects the skill during practical work.",
                    "explanation": "The later assessment may need explicit preparation in Course A or bridging material.",
                    "confidence": 0.58,
                },
            ],
            "warnings": [],
        }
        return LLMResponse(
            text=json.dumps(response, ensure_ascii=False, indent=2),
            metadata={"provider": "mock", "mode": "mock"},
        )
