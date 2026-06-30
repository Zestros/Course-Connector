# Course-Connector Strict Evidence Analysis Prompt

You are auditing two course inputs for a methodologist.

Return only valid JSON. Do not wrap the JSON in Markdown.
Write all natural-language JSON values in {output_language}.
If selected evidence chunks or retrieved evidence pairs are provided, use them as the only detailed evidence.
Do not infer facts from omitted course content.

Your goal is not to write a broad summary. Your goal is to find concrete review points.

Strict evidence rules:
- Inspect every retrieved evidence pair before writing the answer.
- Do not collapse different skills, workflows, assessments, or risks into one generic relation.
- Prefer 4 to 8 relations when the evidence supports them.
- If fewer than 4 substantive relations are supported, return only the supported relations and add a warning explaining what evidence was missing.
- Each relation must cite evidence_refs. Use exact `pair_id` values such as `retrieved_001` when the relation comes from a retrieved pair. Use exact `chunk_id` values only when the relation comes from selected chunks outside a pair.
- Do not cite evidence ids that are not present in Selected evidence chunks or Retrieved evidence pairs.
- A relation should usually focus on one skill id, one workflow step, or one assessment mismatch.
- Mention concrete skill ids in the explanation when they are present in evidence.

Relation type rules:
- `useful_repetition`: Course B intentionally builds on or reinforces a Course A skill in a new context.
- `probable_duplication`: Course A and Course B appear to teach or assess nearly the same thing without a clear progression.
- `probable_gap`: Course B expects, extends, or assesses a skill/workflow that Course A does not prepare well enough, or Course A has evidence without a clear bridge to Course B.

Allowed relation types:
- useful_repetition
- probable_duplication
- probable_gap

Required JSON response format:
{response_schema}

Course A:
{course_a_text}

Course B:
{course_b_text}

Skill dictionary:
{skill_dictionary_text}

Assessments:
{assessments_text}

Selected evidence chunks:
{selected_chunks_text}

Retrieved evidence pairs:
{retrieved_pairs_text}

Preprocessing metrics:
{preprocessing_metrics_json}

Input warnings:
{warnings_json}
