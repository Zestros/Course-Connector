# Course Connector

Course Connector запускает локальный pipeline для сопоставления учебных материалов и генерации отчетов.

## Локальный запуск

Установите проект в editable-режиме:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

Запустите pipeline на демонстрационных данных:

```bash
course-connector run \
  --course-a data/examples/course_a.md \
  --course-b data/examples/course_b.yaml \
  --mapping data/examples/mapping.json \
  --source-pack data/examples/source_pack.csv \
  --config data/examples/config.yaml \
  --output-dir outputs/
```

После успешного запуска в `outputs/` будут созданы один Markdown-репорт и один JSON-файл:

- `report.md`
- `summary.json`
