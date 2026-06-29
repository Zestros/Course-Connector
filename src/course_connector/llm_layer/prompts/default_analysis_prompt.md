# Course-Connector MVP Analysis Prompt

Analyze two course inputs and identify candidate relations for human review.

Return only valid JSON. Do not wrap the JSON in Markdown.
Write all natural-language JSON values in {output_language}.
If selected evidence chunks or retrieved evidence pairs are provided, use them as the only detailed evidence.
Do not infer facts from omitted course content.

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
