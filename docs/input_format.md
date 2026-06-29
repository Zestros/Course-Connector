# Input Format

Course Connector accepts file-based inputs. The CLI currently expects five paths: course A, course B, skill dictionary, assessment materials, and optional config.

```bash
course-connector run \
  --course-a path/to/course_a.yaml \
  --course-b path/to/course_b.yaml \
  --skill-dictionary path/to/skill_dictionary.yaml \
  --assessments path/to/assessments.csv \
  --config path/to/config.yaml \
  --output-dir outputs/demo
```

## Course Files

Supported extensions:

- `.md`
- `.yaml`
- `.yml`

Minimal YAML shape:

```yaml
id: course_a
title: Основы анализа учебных данных
description: Курс учит читать небольшие таблицы и готовить короткий отчет.
topics:
  - Python basics
  - Data processing
learning_outcomes:
  - text: Читать простые наборы данных с помощью python_basics.
    skills:
      - python_basics
competencies:
  - python_basics
modules:
  - id: module_01
    title: Python Basics
    description: Introductory Python practice.
    skills:
      - python_basics
assessments:
  - id: assessment_01
    title: CLI task
    checked_skills:
      - python_basics
    evidence: Student submits a working CLI run log.
```

Structured YAML may also contain educational entities used by preprocessing:

```yaml
modules:
  - id: module_01
    title: Python Basics
    description: Introductory Python practice.
    skills:
      - python_basics
learning_outcomes:
  - text: Use python_basics in small programs.
assessments:
  - id: assessment_01
    title: CLI task
    checked_skills:
      - python_basics
```

Before preprocessing starts, both course files must pass input preflight validation. A course must include:

- `title`;
- `description`;
- non-empty `topics`;
- non-empty `learning_outcomes`;
- competencies or skill links in modules, outcomes, or assessments;
- non-empty `assessments`;
- evidence, either as top-level `evidence` or assessment-level evidence fields;
- at least one skill id that exists in the skill dictionary.

Markdown course files are treated as text, but they still need a title heading and these sections:

```markdown
# Course title

## Description
...

## Topics
...

## Learning Outcomes
...

## Competencies
...

## Assessments
...

## Evidence
...
```

Headings are used as coarse sections for chunking when preprocessing is enabled.

## Skill Dictionary

Supported extensions:

- `.yaml`
- `.yml`
- `.json`

YAML example:

```yaml
skills:
  - id: python_basics
    title: Python basics
    description: Базовое чтение и обработка данных на Python.
    aliases:
      - Python basics
```

The `id` field is the stable reference used by course chunks, assessment rows, retrieval, and reports.

## Assessments

Supported extensions:

- `.md`
- `.yaml`
- `.yml`
- `.csv`

CSV example:

```csv
course_id,assessment_id,title,skill_id,type
course_a,a1,Мини-отчет по набору данных,data_processing,project
course_b,b1,CLI-проверка входных файлов,file_validation,practical
```

CSV rows become evidence chunks. The row number is preserved as a locator for review.

## Config

Supported extensions:

- `.yaml`
- `.yml`

Minimal config:

```yaml
output_language: ru
include_summary: true
llm:
  provider: mock
  output_language: ru
preprocessing:
  enabled: true
  retrieval:
    enabled: true
    mode: keyword
    top_k: 8
```

The config can select `mock` for deterministic local runs or `openrouter` for real API analysis.
