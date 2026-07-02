# Input Format

Course Connector работает с файлами. Основной запуск:

```bash
course-connector run \
  --course-a path/to/course_a.md \
  --course-b path/to/course_b.md \
  --skill-dictionary path/to/skill_dictionary.yaml \
  --assessments path/to/assessments.md \
  --config path/to/config.yaml \
  --output-dir outputs/run
```

## Course Files

Поддерживаются:

- `.md`;
- `.yaml`;
- `.yml`.

Минимально курс должен содержать:

- title;
- description;
- topics;
- learning outcomes;
- competencies или skill ids;
- assessments;
- evidence.

Markdown-курс должен иметь понятные разделы:

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

В `big_course` используются Markdown-файлы:

- `data/examples/big_course/course_git.md`;
- `data/examples/big_course/course_github.md`.

## Skill Dictionary

Поддерживаются:

- `.yaml`;
- `.yml`;
- `.json`.

Пример:

```yaml
skills:
  - id: git_commit_quality
    title: Commit quality
    aliases:
      - commit message
      - atomic commit
```

`id` должен быть стабильным. Эти id используются в курсах, заданиях, retrieval и отчете.

## Assessments

Поддерживаются:

- `.md`;
- `.yaml`;
- `.yml`;
- `.csv`.

В `big_course` задания лежат в:

```text
data/examples/big_course/assessments.md
```

Для smart batch полезно явно указывать skill ids в описании заданий.

## Config

Demo config:

```text
data/examples/big_course/config.yaml
```

Real API config:

```text
configs/default.yaml
```

Config выбирает provider, режим preprocessing, retrieval и token budget.
