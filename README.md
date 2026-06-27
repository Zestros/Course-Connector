# Course Connector

Course Connector запускает локальный pipeline для сопоставления учебных материалов и генерации отчетов.

## Локальный запуск

Установите проект в editable-режиме:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

Запустите pipeline на демонстрационных данных. По умолчанию используется локальный mock LLM mode, поэтому для demo не нужны API-ключи и интернет:

```bash
course-connector run \
  --course-a data/examples/course_a/course.yaml \
  --course-b data/examples/course_b/course.yaml \
  --skill-dictionary data/examples/skill_dictionary.yaml \
  --assessments data/examples/assessments.csv \
  --config configs/default.yaml \
  --output-dir outputs/
```

После успешного запуска в `outputs/` будут созданы человекочитаемый Markdown-отчет и машинно-читаемый JSON-результат:

- `report.md`
- `result.json`

`result.json` содержит краткое резюме анализа, список найденных relation-кандидатов, warnings, provider mode и сводку входных файлов.

## LLM слой

LLM слой разделен на независимые части:

- `llm_layer/config.py` выбирает provider, model, temperature, prompt template и timeout.
- `llm_layer/providers/` хранит provider-контракты и реализации `mock` / `openrouter`.
- `llm_layer/prompts/default_analysis_prompt.md` хранит prompt отдельно от Python-кода.
- `llm_layer/context.py` собирает prompt context только из единого `input_payload`.
- `llm_layer/parsing/` парсит JSON-ответ и нормализует relation-кандидаты.

Публичный вход остается прежним: `analyze_courses(input_payload, provider=None, debug=False)`. Поэтому input layer и pipeline не нужно менять при замене mock provider на API provider.

### Mock режим

`configs/default.yaml` содержит секцию:

```yaml
llm:
  provider: mock
  model: openai/gpt-oss-120b:free
  temperature: 0.0
  timeout_seconds: 60
  debug: false
  output_language: ru
  prompt_template: default_analysis_prompt.md
```

`provider: mock` возвращает стабильный локальный JSON и используется в обычных тестах.
`output_language` управляет языком естественного текста в JSON-ответе LLM. Поддерживаются значения `ru` и `en`; если `llm.output_language` не задан, используется верхнеуровневый `output_language`.

### OpenRouter режим

Чтобы включить OpenRouter, задайте provider в config:

```yaml
llm:
  provider: openrouter
  model: openai/gpt-oss-120b:free
  temperature: 0.0
  output_language: ru
```

Ключ передается через environment:

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
```

Допустим fallback через локальный файл, если путь явно указан в config:

```yaml
llm:
  provider: openrouter
  api_key_file: LLM_apikey/key.txt
```

Файлы с ключами нельзя коммитить. `.gitignore` уже исключает `.env`, `LLM_apikey/`, `*.key` и `key.txt`.

Optional smoke-test с реальным API запускается только явно:

```bash
COURSE_CONNECTOR_RUN_API_TESTS=1 OPENROUTER_API_KEY="sk-or-v1-..." \
  .venv/bin/python -m pytest -p no:cacheprovider tests/test_llm_layer.py
```

Если `OPENROUTER_API_KEY` не задан, smoke-test может взять ключ из `LLM_apikey/key.txt`.
