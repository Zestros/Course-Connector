## Context

В проекте уже есть два нижних слоя:

- `export_moodle_raw_course_tree.py` сохраняет Moodle REST responses и скачиваемый HTML-контент в дерево курса.
- `normalize_moodle_course.py` приводит дерево к компактному course graph: `units`, `skills`, `competencies`, `assessment_methods`, `learning_outcomes`, `success_criteria`, `assessment_tasks`, `competency_coverage`, `evidence`.

Следующий слой должен отвечать не за извлечение данных, а за сравнение двух дисциплин. Главная ошибка, которой нужно избежать: отправлять в LLM полный Moodle JSON или весь нормализованный курс целиком. Такой подход дорогой, плохо воспроизводимый и провоцирует выводы без evidence.

Сравнение нужно строить как evidence-first pipeline: сначала deterministic код готовит маленькие проверяемые кандидаты, затем LLM рассматривает только эти кандидаты и возвращает строгий JSON, затем post-processing проверяет схему, confidence, ссылки на evidence и выставляет `review_required`.

## Goals / Non-Goals

**Goals:**

- Сравнить два нормализованных курса по учебным сущностям, а не только по похожим словам.
- Выявить четыре типа выводов: `reinforcement`, `duplication`, `internal_gap`, `course_break`.
- Уменьшить токены LLM за счёт candidate generation и компактных prompts.
- Уменьшить галлюцинации за счёт evidence-only prompts, JSON Schema и запрета на факты вне входа.
- Сохранить объяснимость: каждый вывод должен ссылаться на unit, competency/skill, assessment task, criteria и source path.
- Оставить возможность заменить локальный prerequisite graph на CASE adapter позже, не делая CASE обязательным для MVP.

**Non-Goals:**

- Не реализовывать полноценный CASE REST, LRS или xAPI publishing в рамках этого change.
- Не строить UI для методиста.
- Не сравнивать произвольные PDF/DOCX/PPTX напрямую; входом остаются нормализованные course JSON.
- Не доверять LLM окончательное решение без schema validation и evidence checks.
- Не требовать, чтобы LLM сама извлекала структуру курса из Moodle dump.

## Decisions

### Decision 1: Двухэтапный pipeline вместо одного большого LLM-запроса

Система будет выполнять сравнение в несколько шагов:

1. `prepare_course_comparison.py` читает два `*.course.normalized.json`.
2. Deterministic слой строит:
   - intra-course checks для неподтверждённых компетенций;
   - inter-course candidate pairs для потенциального повторения, дублирования и разрыва.
3. `llm_verify_course_comparison.py` отправляет в LLM только компактные payloads.
4. Post-processing валидирует ответ LLM и отбрасывает выводы без evidence.
5. `render_course_comparison_report.py` создаёт JSON и Markdown отчёт.

Альтернатива: отправлять оба курса целиком в LLM. Она проще в прототипе, но хуже по стоимости, воспроизводимости и управлению галлюцинациями.

### Decision 2: Два типа LLM-задач

LLM не будет получать один универсальный prompt на всё сравнение. Будут разные задачи:

- `coverage_verification`: проверить, подтверждается ли заявленная компетенция материалами, практикой, тестом и критериями внутри одного unit.
- `alignment_verification`: сравнить пару unit/competency/skill из двух курсов и классифицировать связь как `reinforcement`, `duplication`, `course_break`, `unrelated` или `uncertain`.

Так prompts остаются короткими и тестируемыми. Для каждого типа можно задать отдельную JSON Schema и отдельные few-shot examples.

### Decision 3: Deterministic candidate generation перед LLM

Перед LLM система должна отобрать кандидатов:

- exact/near match по `normalized_text`;
- overlap по ключевым токенам после удаления стоп-слов;
- совпадение assessment evidence: наличие assignment, quiz, criteria, learning outcome;
- локальный prerequisite graph, если он есть;
- соседство по учебной логике: например downstream unit ссылается на понятия из upstream course.

LLM должна рассматривать только кандидатов, а не все пары всех компетенций. Это ограничивает стоимость и снижает шанс случайных смысловых связей.

### Decision 4: Assessment classifier остаётся отдельным слоем

Нормализатор уже не классифицирует проверочные задания по доменным ключевым словам. Сравнение должно использовать факты:

- `moodle_type`;
- `declared_methods`;
- `task_text`;
- `criteria`;
- `evidence`.

Если потребуется классификация проверок, она должна жить отдельно, например в `classify_assessments.py`, и писать результат в enrichment-файл. LLM-сравнение не должно зависеть от предметных keyword rules внутри нормализатора.

### Decision 5: Локальный prerequisite graph вместо обязательного CASE

Для поиска `course_break` нужен слой отношений: какие навыки являются prerequisites для других навыков. В MVP достаточно локального файла, например `skills_graph.json`, где можно указать:

- `skill_id`;
- `label`;
- `aliases`;
- `requires`;
- `related`.

CASE полезен как промышленный стандарт компетенций, но в текущем учебном прототипе он не обязателен. Архитектура должна позволить позже заменить `skills_graph.json` на CASE adapter без изменения формата отчёта.

### Decision 6: Все выводы должны иметь confidence и review policy

Каждый вывод получает:

- `relation_type`;
- `confidence`;
- `rationale`;
- `evidence_refs`;
- `llm_model`;
- `review_required`.

Правило по умолчанию:

- `confidence >= 0.85` и есть evidence с обеих сторон: можно показывать как high-confidence probable;
- `0.65 <= confidence < 0.85`: показывать как reviewable;
- `< 0.65` или нет evidence: не публиковать как итоговый вывод, отправлять в review/uncertain.

## Risks / Trade-offs

- Риск: LLM может уверенно классифицировать связь без достаточного evidence.  
  Митигирование: schema validation, обязательные `evidence_refs`, отказ принимать выводы без source references.

- Риск: deterministic candidate generation пропустит реальную смысловую связь.  
  Митигирование: использовать несколько слабых сигналов, добавлять `uncertain_candidates`, разрешить ручное добавление aliases/prerequisites.

- Риск: локальный prerequisite graph потребует предметной настройки.  
  Митигирование: сделать graph опциональным; без него система ищет `internal_gap`, `reinforcement` и `duplication`, а `course_break` помечает как менее уверенный.

- Риск: LLM-ответы будут нестабильными между запусками.  
  Митигирование: фиксировать модель, temperature, prompt version, input hash и сохранять raw LLM response.

- Риск: assessment type без отдельного classifier будет слишком грубым.  
  Митигирование: для первого этапа сравнивать по `moodle_type`, `declared_methods`, `task_text`, `criteria`; classifier добавить отдельной задачей после базового сравнения.

- Риск: нормализованный курс содержит повторяющиеся блоки из section/page/assign/quiz.  
  Митигирование: использовать `normalized_text` и evidence deduplication, а для LLM payload передавать compact summaries без повторов.

## Migration Plan

1. Оставить `export_moodle_raw_course_tree.py` и `normalize_moodle_course.py` как нижние слои.
2. Добавить подготовку comparison candidates поверх `normalized/*.course.normalized.json`.
3. Добавить LLM verification слой с dry-run режимом, который сохраняет prompt payloads без вызова API.
4. Добавить post-processing и report renderer.
5. Прогнать на `SQL101` и `DB_DESIGN101`, вручную проверить 5–10 выводов и скорректировать thresholds/prompts.
6. Если результат неудовлетворителен по `course_break`, добавить минимальный `skills_graph.json`.

Rollback простой: новые скрипты не меняют raw и normalized входы; можно удалить comparison outputs и вернуться к текущему состоянию.

## Open Questions

- Какая LLM будет использоваться в MVP и какой формат клиента принят в проекте?
- Нужен ли offline/mock режим для учебной демонстрации без API-ключа?
- Должен ли `skills_graph.json` быть обязательным для `course_break` или только повышать confidence?
- Нужно ли сразу хранить raw LLM responses для аудита, или достаточно валидированного JSON?
