## Why

Сейчас проект уже умеет получать курсы из Moodle REST API и приводить их к нормализованному виду, но ещё не определяет главное: где между дисциплинами есть полезное повторение, дублирование, пробелы и разрывы. Если просто отправлять весь Moodle dump в LLM, модель будет получать много служебного шума, тратить лишние токены и чаще делать неподтверждённые выводы.

Нужно спроектировать слой сравнения, в котором LLM работает не с сырыми курсами, а с компактными evidence-based фрагментами: компетенциями, навыками, результатами обучения, типами проверочных заданий, критериями и ссылками на источники.

## What Changes

- Добавить capability для сравнения двух нормализованных курсов через LLM-assisted pipeline.
- Разделить deterministic preprocessing и LLM reasoning:
  - deterministic слой выбирает кандидаты для сравнения и готовит малые payloads;
  - LLM проверяет смысловые связи, классифицирует спорные случаи и формирует объяснение;
  - post-processing валидирует JSON, confidence, evidence и review flags.
- Зафиксировать четыре типа выводов:
  - `reinforcement` — полезное повторение;
  - `duplication` — вероятное дублирование;
  - `internal_gap` — заявленная компетенция не подтверждается материалами, практикой, тестом или критериями;
  - `course_break` — разрыв между курсами, когда последующий курс требует компетенцию, которую предыдущий курс не покрывает или покрывает слабо.
- Описать формат входа для LLM: только нормализованные units, candidate pairs, assessment evidence и краткие source references.
- Описать формат результата: JSON/Markdown report с confidence, evidence, rationale и `review_required`.
- Не добавлять полноценный CASE REST на этом этапе; использовать локальный словарь/граф навыков как future-compatible замену, если потребуется явно описывать prerequisites.

## Capabilities

### New Capabilities

- `llm-course-comparison`: сравнение двух нормализованных курсов по компетенциям, навыкам, проверочным заданиям, критериям и evidence с использованием LLM только на компактных кандидатах.

### Modified Capabilities

Нет.

## Impact

- Затронуты будущие скрипты поверх текущих файлов:
  - `normalize_moodle_course.py` как источник нормализованных course graph;
  - новый слой подготовки кандидатов, например `prepare_course_comparison.py`;
  - новый LLM verification слой, например `llm_verify_course_comparison.py`;
  - новый renderer отчёта, например `render_course_comparison_report.py`.
- Входные данные: `normalized/*.course.normalized.json`.
- Выходные данные: machine-readable comparison JSON, Markdown-отчёт, возможно JSONL с audit events.
- Возможные зависимости: клиент LLM API, JSON Schema validation, dotenv/env-конфиг для ключей и модели.
