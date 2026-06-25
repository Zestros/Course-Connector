# Course Connector MVP

Этот проект собирает прототип Course Connector для сравнения двух учебных курсов. Текущий pipeline устроен так:

1. `scripts/export_moodle_raw_course_tree.py` получает курс из Moodle REST API и сохраняет raw-ответы, секции, модули и скачиваемый HTML-контент в `data/raw-courses/`.
2. `scripts/normalize_moodle_course.py` превращает Moodle-дерево в компактный `*.course.normalized.json`: темы, навыки, компетенции, результаты обучения, заявленные типы проверки, задания, критерии и evidence.
3. `scripts/prepare_course_comparison.py` строит компактные candidates для сравнения двух нормализованных курсов.
4. `scripts/llm_verify_course_comparison.py` проверяет candidates через LLM или сохраняет dry-run payloads без вызова API.
5. `scripts/render_course_comparison_report.py` формирует JSON и Markdown-отчёт по `reinforcement`, `duplication`, `internal_gap`, `course_break` и `uncertain`.

LLM не получает сырой Moodle dump. Она работает только с evidence-based candidate payloads, чтобы уменьшить число токенов и снизить риск галлюцинаций.

## Структура папок

- `scripts/` — исполняемые слои pipeline.
- `schemas/` — JSON Schema для candidates и итогового отчёта.
- `tests/` — минимальные тесты и fixtures.
- `openspec/` — OpenSpec planning artifacts, не перемещать вручную.
- `data/` — локальные Moodle exports, нормализованные курсы и результаты сравнения; папка игнорируется git.
- `local_notes/` — исследовательские заметки и deep research материалы; папка игнорируется git.

## Быстрый локальный прогон

```bash
python3 scripts/normalize_moodle_course.py data/raw-courses/SQL101 data/raw-courses/DB_DESIGN101
python3 scripts/prepare_course_comparison.py data/normalized/DB_DESIGN101.course.normalized.json data/normalized/SQL101.course.normalized.json
python3 scripts/llm_verify_course_comparison.py data/comparison/candidates.DB_DESIGN101__SQL101.json --dry-run
python3 scripts/render_course_comparison_report.py data/comparison/verified.DB_DESIGN101__SQL101.json
```
