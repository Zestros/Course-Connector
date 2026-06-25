## 1. Подготовка входов и контрактов

- [x] 1.1 За 30 минут зафиксировать JSON Schema для comparison candidates в новом файле `schemas/course_comparison_candidates.schema.json`, включая поля `candidate_id`, `candidate_type`, `course_a`, `course_b`, `evidence_refs`, `preliminary_score`, `review_required`.
- [x] 1.2 За 30 минут зафиксировать JSON Schema для итогового отчёта в `schemas/course_comparison_report.schema.json`, включая `reinforcement`, `duplication`, `internal_gap`, `course_break`, `uncertain`.
- [x] 1.3 За 20 минут добавить в `README.md` краткое описание pipeline: Moodle export → normalization → candidate preparation → LLM verification → report.

## 2. Deterministic candidate preparation

- [x] 2.1 За 60 минут создать `prepare_course_comparison.py`, который принимает два `normalized/*.course.normalized.json` и отказывает на raw Moodle JSON с понятной ошибкой.
- [x] 2.2 За 90 минут реализовать генерацию `internal_gap` candidates на основе `competency_coverage`, `assessment_tasks`, `success_criteria` и evidence.
- [x] 2.3 За 120 минут реализовать inter-course candidate generation по `competencies`, `skills`, `learning_outcomes`, token overlap и assessment evidence.
- [x] 2.4 За 60 минут добавить опциональную загрузку `skills_graph.json` для prerequisite/related связей, не делая файл обязательным.
- [x] 2.5 За 45 минут сохранить результат подготовки в `comparison/candidates.<course_a>__<course_b>.json` и проверить, что payload не содержит служебных Moodle-полей.

## 3. LLM verification layer

- [x] 3.1 За 60 минут создать `llm_verify_course_comparison.py` с режимом `--dry-run`, который сохраняет prompts/payloads без вызова LLM.
- [x] 3.2 За 90 минут описать prompts для `coverage_verification` и `alignment_verification`, требующие строгий JSON и запрет фактов вне evidence.
- [x] 3.3 За 120 минут подключить LLM-клиент через переменные окружения, сохранив модель, prompt version, input hash и raw response для аудита.
- [x] 3.4 За 60 минут реализовать post-processing: проверка JSON Schema, существования `evidence_refs`, confidence thresholds и `review_required`.

## 4. Report rendering

- [x] 4.1 За 60 минут создать `render_course_comparison_report.py`, который строит machine-readable JSON report из verified candidates.
- [x] 4.2 За 90 минут добавить Markdown renderer с группировкой выводов по `reinforcement`, `duplication`, `internal_gap`, `course_break`, `uncertain`.
- [x] 4.3 За 45 минут добавить в Markdown краткое объяснение methodology на русском: deterministic preprocessing, evidence-only LLM, review policy.

## 5. Проверка на текущих курсах

- [x] 5.1 За 30 минут заново выполнить `python3 normalize_moodle_course.py SQL101 DB_DESIGN101` и убедиться, что созданы `normalized/SQL101.course.normalized.json` и `normalized/DB_DESIGN101.course.normalized.json`.
- [x] 5.2 За 45 минут выполнить `python3 prepare_course_comparison.py normalized/DB_DESIGN101.course.normalized.json normalized/SQL101.course.normalized.json --out-dir comparison`.
- [x] 5.3 За 45 минут выполнить `python3 llm_verify_course_comparison.py comparison/candidates.DB_DESIGN101__SQL101.json --dry-run --out-dir comparison/llm`.
- [x] 5.4 За 60 минут выполнить полный LLM-прогон при наличии API-ключа и сохранить verified JSON; если API-ключа нет, приложить dry-run payloads как проверяемый результат.
- [x] 5.5 За 45 минут выполнить `python3 render_course_comparison_report.py comparison/verified.DB_DESIGN101__SQL101.json --out-dir comparison/report`.

## 6. Тесты и контроль качества

- [x] 6.1 За 30 минут запустить `python3 -m py_compile normalize_moodle_course.py prepare_course_comparison.py llm_verify_course_comparison.py render_course_comparison_report.py`.
- [x] 6.2 За 60 минут добавить минимальные fixture-тесты для candidate generation на малых JSON-файлах в `tests/fixtures/`.
- [x] 6.3 За 45 минут проверить, что ни один high-confidence вывод не создаётся без `evidence_refs`.
- [x] 6.4 За 30 минут проверить, что Markdown-отчёт содержит все четыре группы выводов или явно пишет, что группа пуста.
- [x] 6.5 За 30 минут запустить итоговые проверки: normalizer run, candidate preparation, dry-run LLM verification, report rendering, `py_compile`.
