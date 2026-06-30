# Course Connector

Course Connector запускает pipeline для сопоставления учебных курсов, поиска возможных повторов, дублирования и пробелов между материалами.

Текущая цепочка:

```text
input files -> preprocessing -> LLM -> report/output layer
```

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

Или через Makefile:

```bash
cp .env.example .env
make install
make test
make demo
```

Основные команды:

```bash
make install      # создает .venv и устанавливает dev-зависимости
make test         # запускает pytest
make demo         # запускает воспроизводимый mock-demo и проверяет result.json
make run-cli      # показывает справку CLI
make docker-build # собирает Docker-образ
make docker-up    # запускает demo через docker compose
```

Для обычного `keyword` retrieval и OpenRouter дополнительные ML-зависимости не нужны.

## Входные файлы

Команда `course-connector run` принимает пять входов:

```bash
course-connector run \
  --course-a data/examples/real_api_demo/course_a/course.yaml \
  --course-b data/examples/real_api_demo/course_b/course.yaml \
  --skill-dictionary data/examples/real_api_demo/skill_dictionary.yaml \
  --assessments data/examples/real_api_demo/assessments.csv \
  --config configs/default.yaml \
  --output-dir outputs/real-api-demo
```

После запуска создаются:

- `report.md` - человекочитаемый отчет
- `result.json` - машинно-читаемый JSON для output layer
- `chunks_course_a.json`, `chunks_course_b.json`, `retrieved_pairs.json`, `preprocessing_summary.json`, если preprocessing включен

## Текущий default

Сейчас [configs/default.yaml](configs/default.yaml) настроен на воспроизводимый mock-запуск без внешних сервисов:

```yaml
llm:
  provider: mock
  model: openai/gpt-oss-120b:free

preprocessing:
  enabled: true
  retrieval:
    enabled: true
    mode: keyword
    top_k: 8
  embeddings:
    enabled: false
```

То есть default:

- работает без API-ключей, сети и внешних сервисов
- возвращает стабильные mock relation-кандидаты
- включает lightweight preprocessing
- использует `keyword` retrieval без embedding-модели
- не загружает `sentence-transformers`

## API ключ

Рекомендуемый способ:

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
```

Локальный fallback:

```text
LLM_apikey/key.txt
```

В config это задается так:

```yaml
llm:
  provider: openrouter
  api_key_file: LLM_apikey/key.txt
```

`OPENROUTER_API_KEY` имеет приоритет над `api_key_file`.

Файлы с ключами нельзя коммитить. `.gitignore` исключает `.env`, `LLM_apikey/`, `*.key`, `key.txt`.

## Mock режим

Mock режим нужен для локальной проверки без API, интернета и ключей.

В config:

```yaml
llm:
  provider: mock
  output_language: ru
```

Mock provider возвращает стабильные тестовые relation-кандидаты. Он используется в unit-тестах и удобен, когда не нужно тратить API-запросы.

## OpenRouter режим

Минимальная настройка:

```yaml
llm:
  provider: openrouter
  model: openai/gpt-oss-120b:free
  temperature: 0.0
  timeout_seconds: 60
  output_language: ru
  api_key_file: LLM_apikey/key.txt
```

Если сервер не ответил, вернул `429` или произошел timeout, программа не падает traceback-ом. Она записывает `result.json` со статусом `provider_error`, пустым `relations` и понятным warning.

## OpenAI режим

Прямой OpenAI provider использует Responses API. Для официального OpenAI API модель указывается без provider-prefix: `gpt-5.4-mini`, а не `openai/gpt-5.4-mini`.

Минимальная настройка через переменную окружения:

```bash
export OPENAI_API_KEY="..."
```

```yaml
llm:
  provider: openai
  model: gpt-5.4-mini
  timeout_seconds: 180
  output_language: ru
  api_base_url: https://api.openai.com/v1
```

Вместо переменной окружения можно указать `api_key_file`, например `LLM_apikey/openai-key.txt`. `OPENAI_API_KEY` имеет приоритет над `api_key_file`.

## RouterAI режим

RouterAI использует OpenAI-compatible API. Минимальная настройка:

```bash
export ROUTERAI_API_KEY="..."
```

```yaml
llm:
  provider: routerai
  model: openai/gpt-5.4-mini
  temperature: 0.0
  timeout_seconds: 60
  output_language: ru
  api_base_url: https://routerai.ru/api/v1
```

Вместо переменной окружения можно указать `api_key_file`. `ROUTERAI_API_KEY` имеет приоритет над `api_key_file`.

Пример:

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

## Язык ответа

Поддерживаются:

```yaml
output_language: ru
```

или:

```yaml
output_language: en
```

Можно задавать на верхнем уровне config или внутри `llm`:

```yaml
llm:
  output_language: ru
```

## Preprocessing

Preprocessing layer стоит между input layer и LLM layer. В проекте есть три режима анализа:

- `full_input`: preprocessing выключен, LLM получает все входные файлы целиком. Если полный prompt не помещается в token budget, pipeline останавливается до LLM-вызова и предлагает включить `smart_batch`.
- `retrieval_single_shot`: текущий быстрый evidence-first режим. Система строит chunks, выбирает `top_k` evidence pairs и отправляет их одним LLM-запросом.
- `smart_batch`: полный chunk-based режим. Система строит profile курса, группирует chunks по `skill_id`, добавляет assessment evidence и отправляет несколько batch-запросов, чтобы покрыть курс по навыкам, а не только по top-k совпадениям.

Он делает:

- выделение chunks
- поиск candidate evidence pairs
- планирование smart batches по skill ids и assessment evidence
- token budget
- автоматический подбор безопасного размера chunk под context window модели
- сохранение ссылок на исходные места для human review

Пример config:

```yaml
preprocessing:
  enabled: true
  analysis_mode: smart_batch
  write_intermediate_outputs: true
  chunking:
    enabled: true
    strategy: educational_entities
    sizing_mode: auto
    min_chunk_tokens: 300
    overlap_tokens: 80
    strict: false
    max_chunk_chars: 900
    max_pair_text_chars: 160
  retrieval:
    enabled: true
    mode: keyword
    top_k: 8
    fallback_mode: keyword
  batch:
    max_skills_per_batch: 1
    max_chunks_per_skill: 6
    max_assessment_chunks_per_skill: 4
    max_batch_input_tokens: 9000
    include_course_profile: true
    merge_strategy: local_dedup
  embeddings:
    enabled: false
  token_budget:
    enabled: true
    max_input_tokens: 10000
    reserve_output_tokens: 1500
```

Пользователь задает размер context window и политику chunking, но не считает размер системного prompt вручную. Course Connector сам оценивает prompt wrapper, рекомендует безопасный размер chunk и пишет метрики в `preprocessing_summary.json`.

Если полный вход не помещается и chunking выключен, pipeline останавливается до LLM-вызова и просит включить:

```yaml
preprocessing:
  enabled: true
  analysis_mode: smart_batch
```

Если отдельный module слишком большой, chunking дробит его на subchunks с `parent_id`, `chunk_index`, `split_strategy` и source locator.

### Retrieval modes

`none`:

```yaml
preprocessing:
  enabled: false
```

или:

```yaml
preprocessing:
  enabled: true
  retrieval:
    enabled: false
    mode: none
```

`keyword`:

```yaml
preprocessing:
  enabled: true
  retrieval:
    enabled: true
    mode: keyword
    top_k: 8
  embeddings:
    enabled: false
```

Работает без ML-зависимостей. Использует `skill_ids`, aliases, titles, keywords и source types.

### Smart batch mode

`smart_batch` нужен для больших учебных материалов, где важно покрытие всего курса, а не общий summary. Batch строится вокруг skill:

- compact profile Course A и Course B;
- запись skill из `skill_dictionary`;
- chunks Course A по этому skill;
- chunks Course B по этому skill;
- assessment chunks, которые проверяют этот skill.

Если batch не помещается в `preprocessing.batch.max_batch_input_tokens`, он режется на sub-batches с `parent_batch_id` и `split_reason`. Chunks без уверенного skill match не удаляются молча: они получают coverage status и попадают в profile/general context или diagnostics.

Во время `smart_batch` запуска CLI печатает прогресс по каждому batch в stderr, например `Smart batch 3/17 started`. При `write_intermediate_outputs: true` файл `batch_results.json` обновляется после каждого завершенного batch, поэтому можно видеть, что программа продолжает работать.

При `write_intermediate_outputs: true` появляются дополнительные файлы:

- `course_profiles.json`
- `skill_batches.json`
- `batch_results.json`
- `merged_findings.json`

`local_embeddings`:

```yaml
preprocessing:
  enabled: true
  retrieval:
    enabled: true
    mode: local_embeddings
    top_k: 18
    fallback_mode: keyword
  embeddings:
    enabled: true
    provider: local_sentence_transformer
    model: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
    local_files_only: true
```

Для этого режима нужны optional dependencies:

```bash
python3 -m pip install -e ".[local-embeddings]"
```

При `local_files_only: true` модель должна быть уже в локальном кэше. Обычный запуск не скачивает модель и не импортирует `sentence-transformers`.

## Evidence refs

`result.json` содержит ссылки на места, которыми LLM подтверждает relation:

```json
"evidence_refs": [
  {
    "chunk_id": "course_a_assessment_02",
    "source_role": "course_a",
    "source_path": "data/examples/real_api_demo/course_a/course.yaml",
    "source_type": "assessment",
    "locator": {
      "kind": "object_path",
      "object_path": "assessments[1]"
    }
  }
]
```

Как читать:

- `source_path` - какой файл открыть
- `source_role` - `course_a`, `course_b`, `assessments`
- `source_type` - тип места: `module`, `assessment`, `row`
- `locator.kind: object_path` - путь внутри YAML
- `locator.kind: row_index` - строка CSV без учета заголовка
- `locator.kind: line_range` - диапазон строк Markdown

## Тесты

Обычный набор тестов:

```bash
.venv/bin/python -m pytest -p no:cacheprovider
```

OpenRouter smoke-test запускается только явно:

```bash
COURSE_CONNECTOR_RUN_API_TESTS=1 \
  .venv/bin/python -m pytest -p no:cacheprovider tests/test_llm_layer.py
```

Он возьмет ключ из `OPENROUTER_API_KEY` или из `LLM_apikey/key.txt`.

Local embeddings integration test тоже opt-in:

```bash
COURSE_CONNECTOR_RUN_LOCAL_EMBEDDING_TESTS=1 \
  .venv/bin/python -m pytest -p no:cacheprovider tests/test_preprocessing_layer.py
```

## Частые проблемы

`OpenRouter request failed with HTTP 429`:

Сработал rate limit OpenRouter. Pipeline завершится без traceback и запишет `result.json` со статусом `provider_error`.

`OpenRouter provider requires OPENROUTER_API_KEY or configured api_key_file`:

Не найден API ключ. Задайте `OPENROUTER_API_KEY` или создайте локальный `LLM_apikey/key.txt`.

`Local embedding retrieval requires optional dependency sentence-transformers`:

Вы включили `retrieval.mode: local_embeddings`, но не установили optional dependencies. Используйте `keyword` или установите:

```bash
python3 -m pip install -e ".[local-embeddings]"
```
