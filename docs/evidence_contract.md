# Evidence Contract

Course Connector evidence is methodological evidence. It is not student assessment data and it is not a final judgment that a course is correct or incorrect.

## Purpose

Evidence links explain why a relation candidate was produced. They should allow a human reviewer to inspect the source material behind a candidate relation.

## Event Shape

Future event exports should follow this high-level contract:

```yaml
actor: teacher | methodologist | course-connector
action: uploaded | compared | detected | confirmed | rejected
object: course | competency | assessment | course-link | gap | duplication
timestamp: ISO-8601 timestamp
context:
  program: optional program identifier
  course_a: course A identifier or path
  course_b: course B identifier or path
  skill_dictionary: dictionary identifier or path
  run_id: Course Connector run id
evidence_links:
  - source_path: path to source file
    source_role: course_a | course_b | skill_dictionary | assessments | report
    source_type: module | outcome | assessment | row | raw_section | coarse_file
    locator:
      kind: line_range | object_path | row_index | coarse_file
```

## Current Evidence Reference Shape

The current JSON result can include compact evidence refs on relation candidates:

```json
{
  "chunk_id": "course_a_module_01",
  "source_role": "course_a",
  "source_path": "data/examples/course_a/course.yaml",
  "source_type": "module",
  "locator": {
    "kind": "object_path",
    "object_path": "modules[0]"
  }
}
```

## Locator Kinds

`line_range`:

```json
{
  "kind": "line_range",
  "line_start": 3,
  "line_end": 8
}
```

`object_path`:

```json
{
  "kind": "object_path",
  "object_path": "learning_outcomes[0]"
}
```

`row_index`:

```json
{
  "kind": "row_index",
  "row_index": 2
}
```

`coarse_file`:

```json
{
  "kind": "coarse_file"
}
```

## Human Review Status

Human review should not overwrite the original candidate. It should add a review decision:

```json
{
  "relation_id": "relation_001",
  "review_status": "confirmed",
  "reviewed_by": "methodologist",
  "reviewed_at": "2026-06-27T08:05:45+00:00",
  "review_note": "Useful repetition because Course B applies the skill in a project context."
}
```

Allowed review statuses:

- `confirmed`
- `rejected`
- `requires_discussion`

## Safety Rules

- Do not store API keys or passwords in evidence links.
- Do not include private student data in relation evidence.
- Do not publish reports to shared systems without human confirmation.
- Keep relation labels cautious: candidate, probable gap, probable duplication.
- Preserve enough source context for review, but avoid copying full private course material into external systems.
