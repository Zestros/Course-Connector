# Output Format

Course Connector writes a human-readable Markdown report and a machine-readable JSON result into the selected output directory.

## Files

Required outputs:

- `report.md`
- `result.json`

Optional preprocessing outputs when preprocessing and intermediate writes are enabled:

- `chunks_course_a.json`
- `chunks_course_b.json`
- `retrieved_pairs.json`
- `preprocessing_summary.json`

## JSON Result

Top-level shape:

```json
{
  "status": "completed",
  "run_id": "20260627T080545Z",
  "generated_at": "2026-06-27T08:05:45+00:00",
  "pipeline_stage": "mvp_llm_analysis_layer",
  "summary": "Mock analysis found candidate relations between the two course inputs.",
  "relations": [],
  "warnings": [],
  "provider": "mock",
  "provider_mode": "mock",
  "inputs": {},
  "outputs": {}
}
```

Relation shape:

```json
{
  "type": "useful_repetition",
  "course_a_fragment": "Course A introduces a skill that appears again in Course B.",
  "course_b_fragment": "Course B reuses the skill in a more applied context.",
  "explanation": "The repeated topic can reinforce learning when coordinated between courses.",
  "confidence": 0.72,
  "evidence_refs": []
}
```

Supported relation types:

- `useful_repetition`
- `probable_duplication`
- `probable_gap`

Provider error shape:

```json
{
  "status": "provider_error",
  "summary": "LLM provider did not return a usable response. See warnings for details.",
  "relations": [],
  "provider": "openrouter",
  "provider_mode": "error",
  "warnings": [
    "LLM provider `openrouter` failed: OpenRouter request failed with HTTP 429."
  ]
}
```

## Markdown Report

The Markdown report includes:

- run metadata;
- analysis summary;
- relations grouped by type;
- confidence values;
- Course A and Course B fragments;
- evidence references when available;
- preprocessing metrics when enabled;
- warnings;
- source file list.

## Evidence References

Evidence references point to source files and locators. Current locator kinds:

- `line_range` for Markdown sections;
- `object_path` for structured YAML objects;
- `row_index` for CSV rows;
- `coarse_file` when no precise locator is available.

Example:

```json
{
  "chunk_id": "assessments_row_003",
  "source_role": "assessments",
  "source_path": "data/examples/assessments.csv",
  "source_type": "row",
  "locator": {
    "kind": "row_index",
    "row_index": 3
  }
}
```
