FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY configs ./configs
COPY data ./data
COPY tests ./tests
COPY Makefile module.yaml ./

RUN pip install --no-cache-dir -e ".[dev]"

CMD ["course-connector", "run", "--course-a", "data/examples/course_a/course.yaml", "--course-b", "data/examples/course_b/course.yaml", "--skill-dictionary", "data/examples/skill_dictionary.yaml", "--assessments", "data/examples/assessments.csv", "--config", "data/examples/config.yaml", "--output-dir", "outputs/demo"]
