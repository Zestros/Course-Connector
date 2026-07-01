# Output Format

Course Connector пишет результат в папку `--output-dir`.

## Главные файлы

- `report.md` - отчет для методиста или преподавателя.
- `result.json` - машинно-читаемый результат.

## Intermediate-файлы

При включенном preprocessing могут появиться:

- `chunks_course_a.json`;
- `chunks_course_b.json`;
- `selected_chunks.json`;
- `retrieved_pairs.json`;
- `course_profiles.json`;
- `skill_batches.json`;
- `batch_results.json`;
- `merged_findings.json`;
- `preprocessing_summary.json`.

## JSON Result

Основная структура:

```json
{
  "status": "completed",
  "run_id": "20260701T000000Z",
  "generated_at": "2026-07-01T00:00:00+00:00",
  "pipeline_stage": "mvp_llm_analysis_layer",
  "summary": "Analysis summary.",
  "relations": [],
  "warnings": [],
  "provider": "mock",
  "provider_mode": "batch_api",
  "inputs": {},
  "outputs": {},
  "preprocessing": {}
}
```

Relation:

```json
{
  "type": "probable_gap",
  "course_a_fragment": "Course A prepares only Git basics.",
  "course_b_fragment": "Course B expects pull request workflow.",
  "explanation": "Course B requires a skill that is not explicitly trained in Course A.",
  "confidence": 0.86,
  "skill_ids": ["github_pull_request_workflow"],
  "evidence_refs": ["course_a_section_002", "course_b_section_012"]
}
```

Поддерживаемые типы:

- `useful_repetition`;
- `probable_duplication`;
- `probable_gap`.

## Provider Error

Если API недоступен или вернул ошибку, pipeline пишет стабильный JSON:

```json
{
  "status": "provider_error",
  "relations": [],
  "provider_mode": "error",
  "warnings": ["LLM provider `openai` failed: ..."]
}
```

## Markdown Report

Отчет содержит:

- run metadata;
- summary;
- relation candidates по типам;
- confidence;
- фрагменты Course A и Course B;
- evidence refs;
- preprocessing metrics;
- warnings;
- список входных файлов.
