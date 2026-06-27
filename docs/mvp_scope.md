# MVP Scope

Course Connector MVP compares two course descriptions through skills, learning outcomes, and assessment evidence. It is a teacher-side and integration-layer module: it prepares candidates for methodological review, but it does not change courses and does not make a final expert decision.

## Included

- Load course A from Markdown, YAML, or YML.
- Load course B from Markdown, YAML, or YML.
- Load one shared skill dictionary from YAML, YML, or JSON.
- Load assessment evidence from Markdown, YAML, YML, or CSV.
- Load optional YAML configuration.
- Prepare lightweight preprocessing context when enabled.
- Build chunks for course material, skill dictionary entries, and assessment rows.
- Retrieve candidate evidence pairs with keyword retrieval, or with local embeddings when the optional dependency and model are available.
- Run an LLM provider in mock or OpenRouter mode.
- Normalize relation candidates into the supported MVP relation types:
  - `useful_repetition`
  - `probable_duplication`
  - `probable_gap`
- Write a Markdown report.
- Write a machine-readable JSON result.
- Preserve source paths and evidence references when available.

## Excluded

- Automatic course editing.
- Full Moodle import/export support.
- Continuous LMS synchronization.
- Web UI.
- Multi-user approval workflows.
- Full CASE implementation.
- Persistent database.
- Automatic publication to Redmine, OpenProject, Nextcloud, Evidence Locker, or Skill-matrix.

## Acceptance Path

The MVP is acceptable when a user can run the local CLI on two demonstration courses, get `report.md` and `result.json`, see at least the three MVP relation types, and inspect source references for the generated candidates.

Recommended local checks:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
course-connector run \
  --course-a data/examples/course_a/course.yaml \
  --course-b data/examples/course_b/course.yaml \
  --skill-dictionary data/examples/skill_dictionary.yaml \
  --assessments data/examples/assessments.csv \
  --config data/examples/config.yaml \
  --output-dir outputs/demo
```

If project automation files are present, the same scenario should be available through `make demo`.
