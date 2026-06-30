# Course-Connector Final Findings Synthesis Prompt

Synthesize already-normalized batch findings into a concise final review.

Return only valid JSON. Do not wrap the JSON in Markdown.
Write all natural-language JSON values in {output_language}.
Do not invent new evidence references.
Only cite evidence_refs already present in the findings input.
Do not return useful_repetition or probable_duplication relations unless evidence_refs include at least one Course A chunk and at least one Course B chunk.

Required JSON response format:
{response_schema}

Course profiles:
{course_profiles_json}

Normalized findings:
{findings_json}

Warnings:
{warnings_json}
