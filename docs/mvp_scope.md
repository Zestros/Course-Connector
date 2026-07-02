# MVP Scope

Course Connector MVP сравнивает два курса через навыки, результаты обучения и проверочные задания. Модуль готовит кандидаты для методиста, но не меняет курсы автоматически.

## Входит в MVP

- Загрузка Course A из Markdown/YAML.
- Загрузка Course B из Markdown/YAML.
- Загрузка одного общего skill dictionary.
- Загрузка assessment evidence из Markdown/YAML/CSV.
- Проверка минимальной структуры входных файлов.
- Chunking учебных материалов.
- Keyword retrieval без ML-зависимостей.
- Smart batch анализ больших материалов.
- LLM providers: `mock`, `openai`, `openrouter`, `routerai`.
- Relation types: `useful_repetition`, `probable_duplication`, `probable_gap`.
- Markdown report.
- JSON result.
- Evidence refs на исходные фрагменты.
- Docker-запуск demo и real API сценария.

## Не входит в MVP

- Автоматическое редактирование курсов.
- Web UI.
- База данных.
- Полная интеграция с Moodle.
- Синхронизация с LMS.
- Многопользовательское согласование.
- Автоматическая публикация в Redmine, OpenProject, Nextcloud или Evidence Locker.

## Критерий готовности

MVP считается рабочим, если:

- `make demo` завершается успешно;
- создаются `report.md` и `result.json`;
- в отчете есть relation candidates;
- у кандидатов есть объяснение и evidence refs, когда они доступны;
- `make docker-demo` запускает тот же сценарий в контейнере;
- `make docker-api OPENAI_API_KEY=...` запускает real API проверку.

Demo на `big_course` не обязан возвращать все три типа relation одновременно. Он проверяет работоспособность pipeline на большом учебном примере.
