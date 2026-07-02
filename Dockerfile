FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY configs ./configs
COPY data ./data
COPY tests ./tests
COPY Makefile module.yaml ./

RUN pip install --no-cache-dir -e ".[dev]"

CMD ["course-connector", "run", "--course-a", "data/examples/big_course/course_git.md", "--course-b", "data/examples/big_course/course_github.md", "--skill-dictionary", "data/examples/big_course/skill_dictionary.yaml", "--assessments", "data/examples/big_course/assessments.md", "--config", "data/examples/big_course/config.yaml", "--output-dir", "outputs/demo"]
