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

Сейчас [configs/default.yaml](configs/default.yaml) настроен на реальный OpenRouter-запуск:

```yaml
llm:
  provider: openrouter
  model: openai/gpt-oss-120b:free
  api_key_file: LLM_apikey/key.txt

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

- использует реальную LLM через OpenRouter
- берет ключ из `LLM_apikey/key.txt`, если `OPENROUTER_API_KEY` не задан
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

Preprocessing layer стоит между input layer и LLM layer. Он нужен, чтобы не отправлять большие курсы целиком в prompt.

Он делает:

- выделение chunks
- поиск candidate evidence pairs
- token budget
- сохранение ссылок на исходные места для human review

Пример config:

```yaml
preprocessing:
  enabled: true
  write_intermediate_outputs: true
  chunking:
    enabled: true
    strategy: educational_entities
    max_chunk_chars: 900
    max_pair_text_chars: 160
  retrieval:
    enabled: true
    mode: keyword
    top_k: 8
    fallback_mode: keyword
  embeddings:
    enabled: false
  token_budget:
    enabled: true
    max_input_tokens: 80000
    reserve_output_tokens: 8000
```

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
