# Course-Connector MVP Analysis Prompt

Analyze two course inputs and identify candidate relations for human review.

Return only valid JSON. Do not wrap the JSON in Markdown.
Write all natural-language JSON values in {output_language}.

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

Input warnings:
{warnings_json}
