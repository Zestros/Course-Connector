# Course Connector

Course Connector запускает локальный pipeline для сопоставления учебных материалов и генерации отчетов.

## Локальный запуск

Установите проект в editable-режиме:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

Запустите pipeline на демонстрационных данных. MVP использует локальный mock LLM mode, поэтому для demo не нужны API-ключи и интернет:

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
