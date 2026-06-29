from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from course_connector.input_layer import load_input_payload
from course_connector.llm_layer import StaticLLMProvider, analyze_courses
from course_connector.llm_layer.context import build_prompt_context
from course_connector.llm_layer.prompts import build_prompt
from course_connector.pipeline import run_pipeline
from course_connector.preprocessing_layer import PreprocessingConfig, prepare_analysis_context
from course_connector.preprocessing_layer.config import (
    ChunkingConfig,
    EmbeddingsConfig,
    PreprocessingConfigurationError,
    RetrievalConfig,
    TokenBudgetConfig,
)
from course_connector.preprocessing_layer.embeddings.local_sentence_transformer import (
    LocalSentenceTransformerEmbeddingProvider,
)
from course_connector.preprocessing_layer.retrieval import keyword_retrieve


def test_default_preprocessing_config_is_lightweight() -> None:
    assert "sentence_transformers" not in sys.modules

    config = PreprocessingConfig.from_input_payload(_payload())
    context = prepare_analysis_context(_payload(), config=config)

    assert config.enabled is False
    assert config.embeddings.enabled is False
    assert context["enabled"] is False
    assert "sentence_transformers" not in sys.modules


def test_chunking_creates_source_locators_for_yaml_markdown_and_csv() -> None:
    context = prepare_analysis_context(
        _payload(),
        config=PreprocessingConfig(enabled=True, retrieval=RetrievalConfig(enabled=False, mode="none")),
    )

    course_chunk = context["chunks"]["course_a"][0]
    markdown_chunk = context["chunks"]["course_b"][0]
    assessment_chunk = context["chunks"]["assessments"][0]

    assert course_chunk["locator"]["kind"] == "object_path"
    assert markdown_chunk["locator"]["kind"] == "line_range"
    assert assessment_chunk["locator"] == {"kind": "row_index", "row_index": 1}
    assert course_chunk["source_path"] == "course_a.yaml"
    assert "python_basics" in course_chunk["skill_ids"]


def test_keyword_retrieval_returns_balanced_top_k_pairs_with_refs() -> None:
    context = prepare_analysis_context(
        _payload(),
        config=PreprocessingConfig(
            enabled=True,
            retrieval=RetrievalConfig(enabled=True, mode="keyword", top_k=3),
        ),
    )

    pairs = context["retrieved_pairs"]

    assert 1 <= len(pairs) <= 3
    assert pairs[0]["pair_id"] == "retrieved_001"
    assert pairs[0]["candidate_relation_hint"]
    assert pairs[0]["evidence_refs"]
    assert context["metrics"]["retrieved_pairs"] == len(pairs)


def test_local_embeddings_can_fallback_to_keyword_without_dependency() -> None:
    context = prepare_analysis_context(
        _payload(),
        config=PreprocessingConfig(
            enabled=True,
            retrieval=RetrievalConfig(enabled=True, mode="local_embeddings", fallback_mode="keyword", top_k=2),
            embeddings=EmbeddingsConfig(enabled=False),
        ),
    )

    assert context["retrieved_pairs"]
    assert "Local embeddings unavailable; fell back to keyword retrieval." in context["warnings"]


def test_local_embedding_provider_raises_clear_error_when_dependency_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)

    with pytest.raises(PreprocessingConfigurationError, match="sentence-transformers"):
        LocalSentenceTransformerEmbeddingProvider(EmbeddingsConfig(enabled=True))


def test_local_embedding_provider_embeds_with_lazy_sentence_transformer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSentenceTransformer:
        calls: list[tuple[str, bool]] = []

        def __init__(self, model: str, local_files_only: bool = True) -> None:
            self.calls.append((model, local_files_only))

        def encode(
            self,
            texts: list[str],
            convert_to_numpy: bool,
            show_progress_bar: bool,
        ) -> list[list[float]]:
            assert texts == ["python", "cli"]
            assert convert_to_numpy is False
            assert show_progress_bar is False
            return [[1, 2.5], [3, 4]]

    fake_module = types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    provider = LocalSentenceTransformerEmbeddingProvider(
        EmbeddingsConfig(enabled=True, model="local-model", local_files_only=False)
    )

    assert provider.embed(["python", "cli"]) == [[1.0, 2.5], [3.0, 4.0]]
    assert FakeSentenceTransformer.calls == [("local-model", False)]


def test_local_embedding_provider_retries_when_constructor_does_not_accept_local_files_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSentenceTransformer:
        calls: list[tuple[str, object]] = []

        def __init__(self, model: str, **kwargs: object) -> None:
            if "local_files_only" in kwargs:
                self.calls.append((model, kwargs["local_files_only"]))
                raise TypeError("unexpected keyword")
            self.calls.append((model, "fallback"))

        def encode(
            self,
            texts: list[str],
            convert_to_numpy: bool,
            show_progress_bar: bool,
        ) -> list[list[float]]:
            return [[0]]

    fake_module = types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    provider = LocalSentenceTransformerEmbeddingProvider(EmbeddingsConfig(enabled=True, model="legacy-model"))

    assert provider.embed(["text"]) == [[0.0]]
    assert FakeSentenceTransformer.calls == [("legacy-model", True), ("legacy-model", "fallback")]


@pytest.mark.skipif(
    os.getenv("COURSE_CONNECTOR_RUN_LOCAL_EMBEDDING_TESTS") != "1",
    reason="Local embedding integration test is opt-in.",
)
def test_local_embedding_provider_optional_integration() -> None:
    provider = LocalSentenceTransformerEmbeddingProvider(
        EmbeddingsConfig(
            enabled=True,
            model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            local_files_only=True,
        )
    )

    vectors = provider.embed(["python basics", "cli assessment"])

    assert len(vectors) == 2
    assert vectors[0]


def test_token_budget_compacts_retrieved_pairs() -> None:
    context = prepare_analysis_context(
        _payload(),
        config=PreprocessingConfig(
            enabled=True,
            retrieval=RetrievalConfig(enabled=True, mode="keyword", top_k=10),
            chunking=ChunkingConfig(max_pair_text_chars=20),
            token_budget=TokenBudgetConfig(max_input_tokens=10, reserve_output_tokens=5),
        ),
    )

    assert context["metrics"]["estimated_input_tokens"] <= 5
    assert any("Token budget" in warning for warning in context["warnings"])


def test_llm_prompt_uses_retrieved_pairs_when_present() -> None:
    context = prepare_analysis_context(
        _payload(),
        config=PreprocessingConfig(
            enabled=True,
            retrieval=RetrievalConfig(enabled=True, mode="keyword", top_k=2),
        ),
    )
    payload = dict(_payload())
    payload["preprocessing"] = context

    prompt = build_prompt(build_prompt_context(payload))

    assert "Retrieved evidence pairs:" in prompt
    assert "retrieved_001" in prompt
    assert "evidence_refs" in prompt


def test_relation_normalization_preserves_evidence_refs() -> None:
    response = json.dumps({
        "summary": "S",
        "relations": [
            {
                "type": "useful_repetition",
                "course_a_fragment": "A",
                "course_b_fragment": "B",
                "explanation": "E",
                "confidence": 0.8,
                "evidence_refs": [{"chunk_id": "course_a_module_01"}],
            }
        ],
        "warnings": [],
    })

    analysis = analyze_courses(_payload(), provider=StaticLLMProvider(response))

    assert analysis["relations"][0]["evidence_refs"] == [{"chunk_id": "course_a_module_01"}]


def test_pipeline_writes_preprocessing_outputs_when_enabled(tmp_path: Path) -> None:
    course_a = _write(tmp_path / "course_a.yaml", _course_yaml())
    course_b = _write(tmp_path / "course_b.md", "# Course B\nPython basics in CLI tasks.\n")
    skill_dictionary = _write(tmp_path / "skills.yaml", _skills_yaml())
    assessments = _write(tmp_path / "assessments.csv", "title,skill\nCLI task,python_basics\n")
    config = _write(
        tmp_path / "config.yaml",
        """
preprocessing:
  enabled: true
  write_intermediate_outputs: true
  retrieval:
    enabled: true
    mode: keyword
    top_k: 2
""",
    )
    payload = load_input_payload(
        course_a=course_a,
        course_b=course_b,
        skill_dictionary=skill_dictionary,
        assessments=assessments,
        config=config,
    )

    result = run_pipeline(payload, tmp_path / "outputs")
    result_json = json.loads(result.result_json.read_text(encoding="utf-8"))

    assert (tmp_path / "outputs" / "chunks_course_a.json").is_file()
    assert (tmp_path / "outputs" / "chunks_course_b.json").is_file()
    assert (tmp_path / "outputs" / "retrieved_pairs.json").is_file()
    assert (tmp_path / "outputs" / "preprocessing_summary.json").is_file()
    assert result_json["preprocessing"]["enabled"] is True
    assert result_json["preprocessing"]["metrics"]["retrieved_pairs"] <= 2


def _payload() -> dict[str, object]:
    return {
        "course_a": {
            "source_path": "course_a.yaml",
            "format": "yaml",
            "raw_text": _course_yaml(),
            "normalized_text": _course_yaml(),
            "parsed_data": {
                "modules": [
                    {
                        "id": "module_01",
                        "title": "Python Basics",
                        "skills": ["python_basics"],
                    }
                ],
                "learning_outcomes": [{"text": "Use python_basics in small programs."}],
            },
        },
        "course_b": {
            "source_path": "course_b.md",
            "format": "markdown",
            "raw_text": "# Course B\nPython basics in CLI tasks.\n",
            "normalized_text": "# Course B\nPython basics in CLI tasks.",
        },
        "skill_dictionary": {
            "source_path": "skills.yaml",
            "format": "yaml",
            "raw_text": _skills_yaml(),
            "parsed_data": {
                "skills": [
                    {
                        "id": "python_basics",
                        "title": "Python basics",
                        "aliases": ["Python basics"],
                    }
                ]
            },
        },
        "assessments": {
            "source_path": "assessments.csv",
            "format": "csv",
            "raw_text": "title,skill\nCLI task,python_basics\n",
            "normalized_text": "title,skill\nCLI task,python_basics",
            "parsed_data": [{"title": "CLI task", "skill": "python_basics"}],
        },
        "config": None,
        "warnings": [],
    }


def _course_yaml() -> str:
    return """
modules:
  - id: module_01
    title: Python Basics
    skills:
      - python_basics
learning_outcomes:
  - text: Use python_basics in small programs.
"""


def _skills_yaml() -> str:
    return """
skills:
  - id: python_basics
    title: Python basics
    aliases:
      - Python basics
"""


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path
