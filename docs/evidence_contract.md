# Evidence Contract

Evidence в Course Connector - это основание для методической проверки. Это не оценка студента и не окончательный вывод о качестве курса.

## Зачем нужны evidence refs

Relation candidate должен быть проверяемым. Для этого результат содержит ссылки на исходные фрагменты курсов, заданий или словаря навыков.

Пример:

```json
{
  "chunk_id": "course_b_section_012",
  "source_role": "course_b",
  "source_path": "data/examples/big_course/course_github.md",
  "source_type": "raw_section",
  "locator": {
    "kind": "line_range",
    "line_start": 45,
    "line_end": 62
  }
}
```

## Locator Kinds

`line_range` - диапазон строк в Markdown:

```json
{
  "kind": "line_range",
  "line_start": 45,
  "line_end": 62
}
```

`object_path` - путь внутри YAML:

```json
{
  "kind": "object_path",
  "object_path": "modules[0]"
}
```

`row_index` - строка CSV без заголовка:

```json
{
  "kind": "row_index",
  "row_index": 3
}
```

`coarse_file` - ссылка на файл целиком, если точного места нет.

## Human Review

Автоматический результат не должен перезаписывать решение человека. Ручная проверка добавляет отдельное решение:

```json
{
  "relation_id": "relation_001",
  "review_status": "confirmed",
  "reviewed_by": "methodologist",
  "reviewed_at": "2026-07-01T00:00:00+00:00",
  "review_note": "Course B действительно требует навык, которого нет в Course A."
}
```

Допустимые статусы:

- `confirmed`;
- `rejected`;
- `requires_discussion`.

## Safety Rules

- Не хранить API keys и passwords в evidence.
- Не включать персональные данные студентов.
- Не публиковать отчет без ручной проверки.
- Формулировать выводы осторожно: candidate, probable gap, probable duplication.
- Сохранять только тот контекст, который нужен для проверки вывода.
