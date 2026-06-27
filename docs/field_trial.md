# Field Trial

The field trial checks whether Course Connector helps a teacher, methodologist, or program lead discuss course alignment using concrete evidence.

## Goal

Run Course Connector on two related courses and verify that the report makes repetitions, duplications, and gaps visible enough for human review.

## Participants

- One methodologist or program lead.
- Two teachers responsible for the compared courses.
- One developer or operator who can run the CLI and collect feedback.

## Materials

- Course A description.
- Course B description.
- Shared skill dictionary.
- Assessment descriptions or assessment CSV.
- Config file.
- Generated `report.md`.
- Generated `result.json`.

## Preparation

Each course should be described with at least:

- title;
- short description or topics;
- learning outcomes;
- skills or skill references;
- assessment evidence.

The skill dictionary should use stable IDs. The same skill IDs should appear in course modules, learning outcomes, or assessment rows whenever possible.

## Procedure

1. Prepare the input files in the agreed format.
2. Run Course Connector locally.
3. Open `report.md`.
4. Review each relation candidate.
5. Mark each candidate as:
   - confirmed;
   - rejected;
   - requires discussion.
6. Record which source fragments support or weaken the candidate.
7. Decide whether the courses need changes.

## Simulation Trial

Before a real field trial, run the demonstration scenario:

```bash
course-connector run \
  --course-a data/examples/course_a/course.yaml \
  --course-b data/examples/course_b/course.yaml \
  --skill-dictionary data/examples/skill_dictionary.yaml \
  --assessments data/examples/assessments.csv \
  --config data/examples/config.yaml \
  --output-dir outputs/demo
```

Expected simulation result:

- at least one `useful_repetition` candidate;
- at least one `probable_duplication` candidate;
- at least one `probable_gap` candidate;
- a Markdown report;
- a JSON result;
- source file references.

## Metrics

Quantitative:

- number of relation candidates;
- number of confirmed candidates;
- number of rejected candidates;
- number of candidates requiring discussion;
- number of useful repetitions;
- number of probable duplications;
- number of probable gaps;
- time from prepared files to report.

Qualitative:

- whether the report is understandable;
- whether the evidence is inspectable;
- whether the relation labels are too strong or appropriately cautious;
- whether the report leads to a concrete course discussion.

## Acceptance Criteria

The module is ready for limited field use when:

- the local run completes without external LMS dependencies;
- the report contains at least three relation types in the simulation;
- each candidate can be traced back to input files or evidence references;
- reviewers can confirm, reject, or discuss candidates without rewriting the whole report.
