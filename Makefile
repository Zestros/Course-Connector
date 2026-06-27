PYTHON ?= python3
VENV ?= .venv
OUTPUT_DIR ?= outputs/demo
DEMO_COURSE_A ?= data/examples/course_a/course.yaml
DEMO_COURSE_B ?= data/examples/course_b/course.yaml
DEMO_SKILL_DICTIONARY ?= data/examples/skill_dictionary.yaml
DEMO_ASSESSMENTS ?= data/examples/assessments.csv
DEMO_CONFIG ?= data/examples/config.yaml

-include .env

PIP := $(VENV)/bin/python -m pip
PYTEST := $(VENV)/bin/pytest
COURSE_CONNECTOR := $(VENV)/bin/course-connector

.PHONY: install test demo run-cli docker-build docker-up

install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"

test:
	$(PYTEST) -q

demo:
	mkdir -p $(OUTPUT_DIR)
	$(COURSE_CONNECTOR) run \
		--course-a $(DEMO_COURSE_A) \
		--course-b $(DEMO_COURSE_B) \
		--skill-dictionary $(DEMO_SKILL_DICTIONARY) \
		--assessments $(DEMO_ASSESSMENTS) \
		--config $(DEMO_CONFIG) \
		--output-dir $(OUTPUT_DIR)
	$(VENV)/bin/python -c "import json, pathlib; result=json.loads(pathlib.Path('$(OUTPUT_DIR)/result.json').read_text(encoding='utf-8')); expected={'useful_repetition','probable_duplication','probable_gap'}; found={relation.get('type') for relation in result.get('relations', [])}; missing=expected-found; assert result.get('status') == 'completed', result.get('status'); assert not missing, f'Missing demo relation types: {sorted(missing)}'; print('Demo verified:', ', '.join(sorted(found)))"

run-cli:
	$(COURSE_CONNECTOR) --help

docker-build:
	docker build -t course-connector:local .

docker-up:
	docker compose up --build course-connector-demo
