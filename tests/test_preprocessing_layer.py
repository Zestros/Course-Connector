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
from course_connector.preprocessing_layer.token_budget import (
    PreprocessingBudgetError,
    recommended_chunk_tokens,
)


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


def test_yaml_course_topics_are_chunked_as_educational_entities() -> None:
    context = prepare_analysis_context(
        _payload(),
        config=PreprocessingConfig(enabled=True, retrieval=RetrievalConfig(enabled=False, mode="none")),
    )

    topics = [chunk for chunk in context["chunks"]["course_a"] if chunk["source_type"] == "topic"]

    assert topics
    assert topics[0]["title"] == "Python basics"
    assert topics[0]["locator"] == {"kind": "object_path", "object_path": "topics[0]"}
    assert topics[0]["skill_ids"] == ["python_basics"]


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


def test_keyword_retrieval_ignores_unrelated_generated_outcome_positions() -> None:
    context = prepare_analysis_context(
        _unrelated_outcomes_payload(),
        config=PreprocessingConfig(
            enabled=True,
            retrieval=RetrievalConfig(enabled=True, mode="keyword", top_k=3),
        ),
    )

    assert context["retrieved_pairs"] == []


def test_keyword_retrieval_does_not_treat_course_a_assessment_as_course_b_evidence() -> None:
    context = prepare_analysis_context(
        _course_id_assessments_payload(),
        config=PreprocessingConfig(
            enabled=True,
            retrieval=RetrievalConfig(enabled=True, mode="keyword", top_k=5),
        ),
    )

    pairs = context["retrieved_pairs"]

    assert pairs
    assert all("course_a a1" not in pair["course_b_text"] for pair in pairs)
    assert any("course_b b1" in pair["course_b_text"] for pair in pairs)


def test_selected_chunks_expand_assessment_support_by_skill_and_course() -> None:
    context = prepare_analysis_context(
        _markdown_assessment_support_payload(),
        config=PreprocessingConfig(
            enabled=True,
            retrieval=RetrievalConfig(enabled=True, mode="keyword", top_k=1),
        ),
    )

    selected_chunks = context["selected_chunks"]
    selected_text = " ".join(chunk["text"] for chunk in selected_chunks)
    selected_roles = {chunk["source_role"] for chunk in selected_chunks}

    assert "Assessment A2" in selected_text
    assert "conflict markers" in selected_text
    assert "GitHub review workflow" not in selected_text
    assert "course_b" not in selected_roles


def test_preprocessing_config_rejects_invalid_context_budget() -> None:
    payload = dict(_payload())
    payload["config"] = {
        "parsed_data": {
            "preprocessing": {
                "token_budget": {
                    "max_input_tokens": 100,
                    "reserve_output_tokens": 100,
                }
            }
        }
    }

    with pytest.raises(PreprocessingConfigurationError, match="reserve_output_tokens"):
        PreprocessingConfig.from_input_payload(payload)


def test_recommended_chunk_size_scales_with_model_context() -> None:
    small = PreprocessingConfig(
        enabled=True,
        token_budget=TokenBudgetConfig(max_input_tokens=10_000, reserve_output_tokens=1_500),
    )
    large = PreprocessingConfig(
        enabled=True,
        token_budget=TokenBudgetConfig(max_input_tokens=1_000_000, reserve_output_tokens=1_500),
    )

    assert recommended_chunk_tokens(small) < recommended_chunk_tokens(large)


def test_chunk_sizing_auto_adjusts_unsafe_character_limit() -> None:
    context = prepare_analysis_context(
        _payload(),
        config=PreprocessingConfig(
            enabled=True,
            chunking=ChunkingConfig(max_chunk_chars=10_000, min_chunk_tokens=100),
            retrieval=RetrievalConfig(enabled=False, mode="none"),
            token_budget=TokenBudgetConfig(max_input_tokens=1_500, reserve_output_tokens=300),
        ),
    )

    assert context["metrics"]["recommended_chunk_chars"] < 10_000
    assert any("Auto-adjusted chunk size" in warning for warning in context["warnings"])


def test_chunk_sizing_strict_mode_rejects_unsafe_character_limit() -> None:
    with pytest.raises(PreprocessingBudgetError) as exc_info:
        prepare_analysis_context(
            _payload(),
            config=PreprocessingConfig(
                enabled=True,
                chunking=ChunkingConfig(max_chunk_chars=10_000, min_chunk_tokens=100, strict=True),
                retrieval=RetrievalConfig(enabled=False, mode="none"),
                token_budget=TokenBudgetConfig(max_input_tokens=1_500, reserve_output_tokens=300),
            ),
        )

    assert exc_info.value.code == "chunk_too_large_for_model"


def test_large_module_is_split_into_parented_subchunks() -> None:
    context = prepare_analysis_context(
        _large_module_payload(),
        config=PreprocessingConfig(
            enabled=True,
            chunking=ChunkingConfig(max_chunk_chars=120, min_chunk_tokens=20),
            retrieval=RetrievalConfig(enabled=False, mode="none"),
        ),
    )

    module_parts = [chunk for chunk in context["chunks"]["course_a"] if chunk["source_type"] == "module_part"]

    assert len(module_parts) >= 2
    assert all(len(chunk["text"]) <= 120 for chunk in module_parts)
    assert all(chunk["parent_id"] == "course_a_module_01" for chunk in module_parts)
    assert all(chunk["chunk_index"] >= 1 for chunk in module_parts)
    assert all(chunk["split_strategy"] for chunk in module_parts)


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


def test_token_budget_rejects_context_too_small_for_prompt_wrapper() -> None:
    with pytest.raises(PreprocessingBudgetError) as exc_info:
        prepare_analysis_context(
            _payload(),
            config=PreprocessingConfig(
                enabled=True,
                retrieval=RetrievalConfig(enabled=True, mode="keyword", top_k=10),
                chunking=ChunkingConfig(max_pair_text_chars=20),
                token_budget=TokenBudgetConfig(max_input_tokens=10, reserve_output_tokens=5),
            ),
        )

    assert exc_info.value.code == "model_context_too_small"


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


def test_evidence_first_prompt_omits_full_raw_course_text() -> None:
    payload = _payload_with_raw_tail("UNIQUE_RAW_TAIL_SHOULD_NOT_APPEAR")
    context = prepare_analysis_context(
        payload,
        config=PreprocessingConfig(
            enabled=True,
            retrieval=RetrievalConfig(enabled=True, mode="keyword", top_k=2),
        ),
    )
    payload = dict(payload)
    payload["preprocessing"] = context

    prompt = build_prompt(build_prompt_context(payload))

    assert "Selected evidence chunks:" in prompt
    assert "UNIQUE_RAW_TAIL_SHOULD_NOT_APPEAR" not in prompt


def test_pipeline_rejects_oversized_legacy_prompt_before_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_analyze_courses(payload: dict[str, object]) -> dict[str, object]:
        nonlocal called
        called = True
        return {"status": "completed", "relations": [], "warnings": []}

    monkeypatch.setattr("course_connector.pipeline.analyze_courses", fake_analyze_courses)
    course_a = _write(tmp_path / "course_a.md", "# A\n" + ("very long text " * 300))
    course_b = _write(tmp_path / "course_b.md", "# B\n" + ("another long text " * 300))
    skill_dictionary = _write(tmp_path / "skills.yaml", _skills_yaml())
    assessments = _write(tmp_path / "assessments.csv", "title,skill\nCLI task,python_basics\n")
    config = _write(
        tmp_path / "config.yaml",
        """
preprocessing:
  enabled: false
  token_budget:
    enabled: true
    max_input_tokens: 500
    reserve_output_tokens: 100
""",
    )
    payload = load_input_payload(
        course_a=course_a,
        course_b=course_b,
        skill_dictionary=skill_dictionary,
        assessments=assessments,
        config=config,
    )

    with pytest.raises(PreprocessingBudgetError) as exc_info:
        run_pipeline(payload, tmp_path / "outputs")

    assert exc_info.value.code == "input_too_large_without_chunking"
    assert called is False


def test_pipeline_rejects_oversized_prompt_with_assessment_support(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_analyze_courses(payload: dict[str, object]) -> dict[str, object]:
        nonlocal called
        called = True
        return {"status": "completed", "relations": [], "warnings": []}

    monkeypatch.setattr("course_connector.pipeline.analyze_courses", fake_analyze_courses)
    course_a = _write(
        tmp_path / "course_a.md",
        (
            "# Course A\n"
            "## Intro\n"
            "Python basics introduction.\n"
            "## Skill One\n"
            f"{'Python basics details. ' * 60}\n"
            "## Skill Two\n"
            f"{'Command line details. ' * 60}\n"
        ),
    )
    course_b = _write(tmp_path / "course_b.md", "# Course B\nUnrelated review workflow.\n")
    skill_dictionary = _write(
        tmp_path / "skills.yaml",
        """
skills:
  - id: python_basics
    title: Python basics
    aliases: [Python basics]
  - id: cli_usage
    title: Command line
    aliases: [Command line]
""",
    )
    assessments = _write(
        tmp_path / "assessments.md",
        (
            "# Assessments\n"
            "## Assessment A1\n"
            "- Course: Course A\n"
            "- Skill IDs: python_basics, cli_usage\n"
            "Python basics command line assessment.\n"
        ),
    )
    config = _write(
        tmp_path / "config.yaml",
        """
preprocessing:
  enabled: true
  retrieval:
    enabled: true
    mode: keyword
    top_k: 1
  token_budget:
    enabled: true
    max_input_tokens: 2100
    reserve_output_tokens: 300
""",
    )
    payload = load_input_payload(
        course_a=course_a,
        course_b=course_b,
        skill_dictionary=skill_dictionary,
        assessments=assessments,
        config=config,
    )

    with pytest.raises(PreprocessingBudgetError) as exc_info:
        run_pipeline(payload, tmp_path / "outputs")

    assert exc_info.value.code == "prompt_budget_exceeded_after_chunking"
    assert called is False


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
    assert (tmp_path / "outputs" / "selected_chunks.json").is_file()
    assert (tmp_path / "outputs" / "retrieved_pairs.json").is_file()
    assert (tmp_path / "outputs" / "preprocessing_summary.json").is_file()
    assert result_json["preprocessing"]["enabled"] is True
    assert result_json["preprocessing"]["metrics"]["retrieved_pairs"] <= 2
    assert result_json["preprocessing"]["metrics"]["available_input_tokens"] > 0
    assert result_json["preprocessing"]["metrics"]["prompt_overhead_tokens"] > 0
    assert result_json["preprocessing"]["metrics"]["recommended_chunk_chars"] > 0
    assert result_json["preprocessing"]["metrics"]["selected_chunks"] > 0
    assert result_json["preprocessing"]["metrics"]["estimated_prompt_tokens"] > 0


def _payload() -> dict[str, object]:
    return {
        "course_a": {
            "source_path": "course_a.yaml",
            "format": "yaml",
            "raw_text": _course_yaml(),
            "normalized_text": _course_yaml(),
            "parsed_data": {
                "topics": ["Python basics"],
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
topics:
  - Python basics
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


def _unrelated_outcomes_payload() -> dict[str, object]:
    payload = dict(_payload())
    payload["course_a"] = {
        "source_path": "course_a.yaml",
        "format": "yaml",
        "raw_text": "learning_outcomes:\n  - Читать простые наборы данных\n",
        "normalized_text": "learning_outcomes:\n  - Читать простые наборы данных\n",
        "parsed_data": {"learning_outcomes": ["Читать простые наборы данных"]},
    }
    payload["course_b"] = {
        "source_path": "course_b.yaml",
        "format": "yaml",
        "raw_text": "learning_outcomes:\n  - Запускать локальные CLI-инструменты\n",
        "normalized_text": "learning_outcomes:\n  - Запускать локальные CLI-инструменты\n",
        "parsed_data": {"learning_outcomes": ["Запускать локальные CLI-инструменты"]},
    }
    payload["assessments"] = {
        "source_path": "assessments.csv",
        "format": "csv",
        "raw_text": "title,skill\nБез совпадений,totally_different\n",
        "normalized_text": "title,skill\nБез совпадений,totally_different",
        "parsed_data": [{"title": "Без совпадений", "skill": "totally_different"}],
    }
    return payload


def _course_id_assessments_payload() -> dict[str, object]:
    payload = dict(_payload())
    payload["course_a"] = {
        "source_path": "course_a.yaml",
        "format": "yaml",
        "raw_text": "id: course_a\ntopics:\n  - Data processing\n",
        "normalized_text": "id: course_a\ntopics:\n  - Data processing\n",
        "parsed_data": {"id": "course_a", "topics": ["Data processing"]},
    }
    payload["course_b"] = {
        "source_path": "course_b.yaml",
        "format": "yaml",
        "raw_text": "id: course_b\ntopics:\n  - Data processing\n",
        "normalized_text": "id: course_b\ntopics:\n  - Data processing\n",
        "parsed_data": {"id": "course_b", "topics": ["Data processing"]},
    }
    payload["skill_dictionary"] = {
        "source_path": "skills.yaml",
        "format": "yaml",
        "raw_text": "skills:\n  - id: data_processing\n    title: Data processing\n",
        "parsed_data": {
            "skills": [
                {
                    "id": "data_processing",
                    "title": "Data processing",
                    "aliases": [],
                }
            ]
        },
    }
    payload["assessments"] = {
        "source_path": "assessments.csv",
        "format": "csv",
        "raw_text": (
            "course_id,assessment_id,title,skill_id,type\n"
            "course_a,a1,Course A data task,data_processing,project\n"
            "course_b,b1,Course B data task,data_processing,project\n"
        ),
        "normalized_text": (
            "course_id,assessment_id,title,skill_id,type\n"
            "course_a,a1,Course A data task,data_processing,project\n"
            "course_b,b1,Course B data task,data_processing,project\n"
        ),
        "parsed_data": [
            {
                "course_id": "course_a",
                "assessment_id": "a1",
                "title": "Course A data task",
                "skill_id": "data_processing",
                "type": "project",
            },
            {
                "course_id": "course_b",
                "assessment_id": "b1",
                "title": "Course B data task",
                "skill_id": "data_processing",
                "type": "project",
            },
        ],
    }
    return payload


def _markdown_assessment_support_payload() -> dict[str, object]:
    payload = dict(_payload())
    payload["course_a"] = {
        "source_path": "course_a.md",
        "format": "markdown",
        "raw_text": (
            "# Course A\n"
            "## Branching\n"
            "Students create feature branches and merge them back into main.\n"
            "## Conflict Resolution\n"
            "Students inspect conflict markers and resolve merge conflicts by preserving both useful changes.\n"
        ),
        "normalized_text": (
            "# Course A\n"
            "## Branching\n"
            "Students create feature branches and merge them back into main.\n"
            "## Conflict Resolution\n"
            "Students inspect conflict markers and resolve merge conflicts by preserving both useful changes.\n"
        ),
    }
    payload["course_b"] = {
        "source_path": "course_b.md",
        "format": "markdown",
        "raw_text": (
            "# Course B\n"
            "## Pull Request Review\n"
            "GitHub review workflow appears here, but it belongs to Course B and should not support Course A assessment.\n"
        ),
        "normalized_text": (
            "# Course B\n"
            "## Pull Request Review\n"
            "GitHub review workflow appears here, but it belongs to Course B and should not support Course A assessment.\n"
        ),
    }
    payload["skill_dictionary"] = {
        "source_path": "skills.yaml",
        "format": "yaml",
        "raw_text": (
            "skills:\n"
            "  - id: git_branching\n"
            "    title: Git branching\n"
            "    aliases: [branching, feature branches]\n"
            "  - id: git_merge_conflict_resolution\n"
            "    title: Git merge conflict resolution\n"
            "    aliases: [merge conflicts, conflict markers]\n"
        ),
        "parsed_data": {
            "skills": [
                {
                    "id": "git_branching",
                    "title": "Git branching",
                    "aliases": ["branching", "feature branches"],
                },
                {
                    "id": "git_merge_conflict_resolution",
                    "title": "Git merge conflict resolution",
                    "aliases": ["merge conflicts", "conflict markers"],
                },
            ]
        },
    }
    payload["assessments"] = {
        "source_path": "assessments.md",
        "format": "markdown",
        "raw_text": (
            "# Assessments\n"
            "## Assessment A2\n"
            "- Course: Course A\n"
            "- Skill IDs: git_branching, git_merge_conflict_resolution\n"
            "Students create a feature branch and resolve a merge conflict.\n"
        ),
        "normalized_text": (
            "# Assessments\n"
            "## Assessment A2\n"
            "- Course: Course A\n"
            "- Skill IDs: git_branching, git_merge_conflict_resolution\n"
            "Students create a feature branch and resolve a merge conflict.\n"
        ),
    }
    return payload


def _large_module_payload() -> dict[str, object]:
    payload = dict(_payload())
    long_description = " ".join(f"paragraph sentence {index}." for index in range(80))
    payload["course_a"] = {
        "source_path": "course_a.yaml",
        "format": "yaml",
        "raw_text": f"modules:\n  - id: module_01\n    title: Big Module\n    description: {long_description}\n",
        "normalized_text": f"modules:\n  - id: module_01\n    title: Big Module\n    description: {long_description}\n",
        "parsed_data": {
            "modules": [
                {
                    "id": "module_01",
                    "title": "Big Module",
                    "description": long_description,
                    "skills": ["python_basics"],
                }
            ]
        },
    }
    return payload


def _payload_with_raw_tail(tail: str) -> dict[str, object]:
    payload = dict(_payload())
    course_a = dict(payload["course_a"])  # type: ignore[arg-type]
    course_a["raw_text"] = f"{course_a['raw_text']}\n{tail}\n"
    course_a["normalized_text"] = f"{course_a['normalized_text']}\n{tail}\n"
    payload["course_a"] = course_a
    return payload


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path
