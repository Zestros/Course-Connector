# Course-Connector Skill Batch Analysis Prompt

Analyze one smart batch for course alignment review.

Return only valid JSON. Do not wrap the JSON in Markdown.
Write all natural-language JSON values in {output_language}.
Use only the provided course profiles, skill dictionary subset, course chunks and assessment chunks.
Do not invent evidence references.

Required JSON response format:
{response_schema}

Batch metadata:
{batch_metadata_json}

Course profiles:
{course_profiles_json}

Skill dictionary subset:
{skill_dictionary_subset_json}

Course A chunks:
{course_a_chunks_json}

Course B chunks:
{course_b_chunks_json}

Assessment chunks:
{assessment_chunks_json}

Warnings:
{warnings_json}
