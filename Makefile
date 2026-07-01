PYTHON ?= python3
VENV ?= .venv
OUTPUT_DIR ?= outputs/demo
DEMO_COURSE_A ?= data/examples/big_course/course_git.md
DEMO_COURSE_B ?= data/examples/big_course/course_github.md
DEMO_SKILL_DICTIONARY ?= data/examples/big_course/skill_dictionary.yaml
DEMO_ASSESSMENTS ?= data/examples/big_course/assessments.md
DEMO_CONFIG ?= data/examples/big_course/config.yaml

-include .env

PIP := $(VENV)/bin/python -m pip
PYTEST := $(VENV)/bin/pytest
COURSE_CONNECTOR := $(VENV)/bin/course-connector
DOCKER_COMPOSE ?= docker compose
OPENAI_MODEL ?= gpt-5.4-mini
OPENAI_API_BASE_URL ?= https://api.openai.com/v1

.PHONY: install test demo run-cli docker-build docker-up docker-demo docker-api

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
	$(VENV)/bin/python -c "import json, pathlib; result=json.loads(pathlib.Path('$(OUTPUT_DIR)/result.json').read_text(encoding='utf-8')); relations=result.get('relations', []); found={relation.get('type') for relation in relations}; assert result.get('status') == 'completed', result.get('status'); assert relations, 'Demo produced no relations'; assert result.get('inputs', {}).get('course_a', {}).get('source_path') == '$(DEMO_COURSE_A)'; assert result.get('inputs', {}).get('course_b', {}).get('source_path') == '$(DEMO_COURSE_B)'; print('Demo verified:', ', '.join(sorted(found)))"

run-cli:
	$(COURSE_CONNECTOR) --help

docker-build:
	docker build -t course-connector:local .

docker-up: docker-demo

docker-demo:
	$(DOCKER_COMPOSE) run --rm --build course-connector-demo

docker-api:
	@test -n "$(OPENAI_API_KEY)" || (echo "OPENAI_API_KEY is required. Run: make docker-api OPENAI_API_KEY=sk-..."; exit 2)
	OPENAI_API_KEY="$(OPENAI_API_KEY)" OPENAI_MODEL="$(OPENAI_MODEL)" OPENAI_API_BASE_URL="$(OPENAI_API_BASE_URL)" $(DOCKER_COMPOSE) run --rm --build course-connector-api
