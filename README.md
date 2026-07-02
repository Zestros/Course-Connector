# Course Connector

Course Connector сравнивает два учебных курса и показывает кандидаты на:

- полезное повторение;
- вероятное дублирование;
- вероятный пробел между подготовкой и проверкой навыка.

Результат сохраняется как Markdown-отчет и JSON.

## Быстрый запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
make install
make demo
```

`make demo` запускает локальный mock-сценарий без API-ключей и сети. Используются файлы из `data/examples/big_course`.

Результаты:

```text
outputs/demo/report.md
outputs/demo/result.json
```

## Docker

Mock-запуск в контейнере:

```bash
make docker-demo
```

Real API запуск через OpenAI:

```bash
make docker-api OPENAI_API_KEY="sk-..."
```

Результаты real API запуска:

```text
outputs/big_course_api/report.md
outputs/big_course_api/result.json
```

## Входные файлы

CLI принимает пять путей:

```bash
course-connector run \
  --course-a data/examples/big_course/course_git.md \
  --course-b data/examples/big_course/course_github.md \
  --skill-dictionary data/examples/big_course/skill_dictionary.yaml \
  --assessments data/examples/big_course/assessments.md \
  --config data/examples/big_course/config.yaml \
  --output-dir outputs/demo
```

Поддерживаются:

- курсы: `.md`, `.yaml`, `.yml`;
- словарь навыков: `.yaml`, `.yml`, `.json`;
- задания: `.md`, `.yaml`, `.yml`, `.csv`;
- config: `.yaml`, `.yml`.

## Конфиги

`data/examples/big_course/config.yaml`:

- mock provider;
- подходит для локальной проверки;
- не требует ключей;
- пишет intermediate-файлы.

`configs/default.yaml`:

- OpenAI provider;
- smart batch анализ;
- подходит для реальной проверки через API;
- требует `OPENAI_API_KEY`.

## Основные команды

```bash
make install       # создать .venv и установить зависимости
make test          # запустить pytest
make demo          # локальный mock-demo
make run-cli       # справка CLI
make docker-build  # собрать образ
make docker-demo   # mock-demo в Docker
make docker-api    # real API запуск в Docker
```

## Где смотреть результат

Главные файлы:

- `report.md` - отчет для человека;
- `result.json` - машинно-читаемый результат.

При `smart_batch` также создаются:

- `chunks_course_a.json`;
- `chunks_course_b.json`;
- `course_profiles.json`;
- `skill_batches.json`;
- `batch_results.json`;
- `merged_findings.json`;
- `preprocessing_summary.json`.

## Безопасность

- Не коммитьте `.env`, `LLM_apikey/`, `*.key`, `key.txt`.
- Не публикуйте отчет с приватными курсами без ручной проверки.
- Candidate relations не являются окончательным методическим решением.
