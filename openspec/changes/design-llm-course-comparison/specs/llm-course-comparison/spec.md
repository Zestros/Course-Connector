## ADDED Requirements

### Requirement: Система сравнивает только нормализованные курсы

Система SHALL принимать на вход два файла `*.course.normalized.json`, созданные нормализатором, и MUST NOT отправлять в LLM сырые Moodle REST responses целиком.

#### Scenario: Успешная загрузка двух нормализованных курсов

- **WHEN** пользователь запускает сравнение для `normalized/SQL101.course.normalized.json` и `normalized/DB_DESIGN101.course.normalized.json`
- **THEN** система загружает course metadata, units, competencies, skills, assessment tasks, success criteria и evidence из обоих файлов

#### Scenario: Отказ от сырого Moodle dump

- **WHEN** пользователь передаёт `raw/contents.json` вместо нормализованного course graph
- **THEN** система завершает выполнение с понятной ошибкой о необходимости предварительной нормализации

### Requirement: Система готовит компактные кандидаты перед LLM

Система SHALL строить candidate payloads для LLM на основе компетенций, навыков, результатов обучения, заданий, критериев и evidence, а не на основе полного текста курса.

#### Scenario: Candidate pair содержит только релевантные фрагменты

- **WHEN** система находит потенциальную связь между unit из первого курса и unit из второго курса
- **THEN** candidate payload содержит названия unit, релевантные competencies/skills, assessment tasks, criteria, краткие evidence refs и не содержит служебные Moodle-поля

#### Scenario: Слабые кандидаты помечаются для ревью

- **WHEN** deterministic слой находит только слабое пересечение токенов без assessment evidence
- **THEN** candidate получает низкий preliminary score или `review_required`, а LLM не должна принимать его как high-confidence вывод без дополнительных оснований

### Requirement: Система выявляет неподтверждённые компетенции внутри курса

Система SHALL определять `internal_gap`, когда компетенция заявлена, но не имеет достаточного подтверждения через материал, практику, тест или критерии.

#### Scenario: Компетенция подтверждена несколькими типами evidence

- **WHEN** компетенция присутствует в summary, learning material, assignment или quiz, и связана с success criteria
- **THEN** система классифицирует coverage как `strong` или `medium` и не создаёт `internal_gap`

#### Scenario: Компетенция только заявлена

- **WHEN** компетенция присутствует только в заявленном списке компетенций и не имеет подтверждения в task text, quiz text или criteria
- **THEN** система создаёт вывод `internal_gap` с `review_required: true` и ссылками на evidence, где компетенция была заявлена

### Requirement: Система выявляет разрывы между курсами

Система SHALL определять `course_break`, когда последующий курс требует компетенцию или навык, который предыдущий курс не покрывает или покрывает слабо.

#### Scenario: Prerequisite покрыт предыдущим курсом

- **WHEN** последующий курс использует навык, а предыдущий курс содержит совпадающий или связанный prerequisite со статусом coverage `strong` или `medium`
- **THEN** система не создаёт `course_break` и может создать `reinforcement`, если навык развивается дальше

#### Scenario: Prerequisite отсутствует или покрыт слабо

- **WHEN** последующий курс требует prerequisite, которого нет в предыдущем курсе или он имеет coverage `weak`, `declared_only` или `uncertain`
- **THEN** система создаёт вывод `course_break` с confidence, rationale, evidence refs и `review_required: true`

### Requirement: Система различает полезное повторение и дублирование

Система SHALL классифицировать связь между курсами как `reinforcement` или `duplication` с учётом компетенций и проверочных заданий, а не только похожести текста.

#### Scenario: Полезное повторение

- **WHEN** два курса затрагивают связанную компетенцию, но второй курс использует другой уровень применения, другую глубину задания или более сложные критерии
- **THEN** система создаёт вывод `reinforcement` с объяснением различий в assessment evidence

#### Scenario: Вероятное дублирование

- **WHEN** два курса заявляют очень близкую компетенцию и используют похожий тип проверки, похожую задачу и близкие критерии успешности
- **THEN** система создаёт вывод `duplication` с confidence и ссылками на evidence из обоих курсов

### Requirement: LLM работает только как проверяющий слой

Система SHALL использовать LLM для проверки, ранжирования и объяснения candidate payloads, но MUST NOT позволять LLM создавать выводы без ссылок на evidence из входа.

#### Scenario: LLM возвращает валидный JSON

- **WHEN** LLM получает candidate payload
- **THEN** она возвращает JSON с `relation_type`, `confidence`, `rationale`, `evidence_refs`, `review_required` и не добавляет факты, отсутствующие во входе

#### Scenario: LLM возвращает неподтверждённый вывод

- **WHEN** LLM response содержит relation без evidence refs или с несуществующими references
- **THEN** система отклоняет этот вывод или переводит его в `uncertain` с `review_required: true`

### Requirement: Система формирует объяснимый отчёт

Система SHALL формировать machine-readable JSON report и Markdown summary по результатам сравнения двух курсов.

#### Scenario: JSON report содержит проверяемые выводы

- **WHEN** сравнение завершено
- **THEN** JSON report содержит список выводов с relation type, confidence, affected courses/units, competencies/skills, assessment evidence, rationale и review status

#### Scenario: Markdown report пригоден для учебного отчёта

- **WHEN** сравнение завершено
- **THEN** Markdown summary группирует выводы по `reinforcement`, `duplication`, `internal_gap`, `course_break` и кратко объясняет каждый вывод на русском языке
