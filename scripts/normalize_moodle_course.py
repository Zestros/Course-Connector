#!/usr/bin/env python3
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


HEADING_ALIASES = {
    "Навыки": "skills",
    "Компетенции": "competencies",
    "Тип проверки": "assessment_methods",
    "Ожидаемый результат обучения": "learning_outcomes",
    "Критерии успешного выполнения": "success_criteria",
    "Содержание проверки": "check_content",
}

ASSESSMENT_TYPE_BY_MODNAME = {
    "assign": "assignment",
    "quiz": "quiz",
    "page": "learning_material",
    "forum": "discussion",
}


class StructuredHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sections = defaultdict(list)
        self.intro = []
        self._current_heading = None
        self._current_tag = None
        self._text_parts = []
        self._list_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"h1", "h2", "h3", "h4", "p", "li"}:
            self._flush_text()
            self._current_tag = tag
            self._text_parts = []
        if tag in {"ul", "ol"}:
            self._list_depth += 1

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"h1", "h2", "h3", "h4", "p", "li"}:
            self._flush_text()
            self._current_tag = None
        if tag in {"ul", "ol"}:
            self._list_depth = max(0, self._list_depth - 1)

    def handle_data(self, data):
        if self._current_tag:
            self._text_parts.append(data)

    def _flush_text(self):
        if not self._current_tag or not self._text_parts:
            return

        text = clean_text(" ".join(self._text_parts))
        self._text_parts = []
        if not text:
            return

        if self._current_tag in {"h1", "h2", "h3", "h4"}:
            if text in HEADING_ALIASES:
                self._current_heading = text
            else:
                self.intro.append(text)
            return

        if self._current_heading:
            self.sections[self._current_heading].append(text)
        else:
            self.intro.append(text)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Normalize exported Moodle raw course trees into compact course graphs."
    )
    parser.add_argument("courses", nargs="+", help="Course directories with index.json, e.g. SQL101 DB_DESIGN101.")
    parser.add_argument("--out-dir", default="data/normalized")
    parser.add_argument("--include-section-zero", action="store_true")
    return parser.parse_args()


def clean_text(value):
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return value


def normalize_text(value):
    value = clean_text(value).lower()
    value = value.replace("ё", "е")
    value = re.sub(r"[^\w\s+-]+", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_html_sections(html):
    parser = StructuredHTMLParser()
    parser.feed(html or "")
    parser.close()
    return {
        "intro": unique_texts(parser.intro),
        "sections": {HEADING_ALIASES[key]: unique_texts(values) for key, values in parser.sections.items()},
    }


def unique_texts(values):
    seen = set()
    result = []
    for value in values:
        text = clean_text(value)
        key = normalize_text(text)
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def make_evidence(course_dir, source_type, source_path, heading=None, module_id=None, module_type=None):
    evidence = {
        "source_type": source_type,
        "path": str(source_path.relative_to(course_dir)),
    }
    if heading:
        evidence["heading"] = heading
    if module_id is not None:
        evidence["module_id"] = module_id
    if module_type:
        evidence["module_type"] = module_type
    return evidence


def add_items(bucket, field, texts, evidence):
    for text in texts:
        key = normalize_text(text)
        if not key:
            continue
        item = bucket[field].setdefault(key, {
            "text": text,
            "normalized_text": key,
            "evidence": [],
        })
        item["evidence"].append(evidence)


def finalize_items(items_by_key):
    result = []
    for item in items_by_key.values():
        item["evidence"] = dedupe_evidence(item["evidence"])
        result.append(item)
    return sorted(result, key=lambda item: item["normalized_text"])


def dedupe_evidence(evidence_items):
    seen = set()
    result = []
    for evidence in evidence_items:
        key = tuple(sorted(evidence.items()))
        if key not in seen:
            seen.add(key)
            result.append(evidence)
    return result


def normalize_module_role(modname):
    return ASSESSMENT_TYPE_BY_MODNAME.get(modname, modname or "unknown")


def load_module_html(course_dir, module_entry):
    chunks = []
    for content in module_entry.get("contents", []):
        content_type = content.get("content_type", "")
        downloaded = content.get("downloaded")
        if downloaded and "html" in content_type:
            path = course_dir / downloaded
            if path.exists():
                chunks.append((path, path.read_text(encoding="utf-8", errors="replace")))
    return chunks


def extract_module(course_dir, module_entry):
    module_path = course_dir / module_entry["path"] / "module.raw.json"
    raw = read_json(module_path)
    modname = raw.get("modname")
    module = {
        "module_id": raw.get("id"),
        "instance_id": raw.get("instance"),
        "title": raw.get("name"),
        "moodle_modname": modname,
        "role": normalize_module_role(modname),
        "source_path": str(module_path.relative_to(course_dir)),
        "url": raw.get("url"),
        "extracted": {
            "intro": [],
            "skills": [],
            "competencies": [],
            "assessment_methods": [],
            "learning_outcomes": [],
            "success_criteria": [],
            "check_content": [],
        },
        "assessment": {
            "moodle_type": normalize_module_role(modname),
            "declared_methods": [],
            "is_assessment": modname in {"assign", "quiz"},
        },
    }

    html_sources = []
    description = raw.get("description")
    if description:
        html_sources.append((module_path, description, "module_description"))
    for path, html in load_module_html(course_dir, module_entry):
        html_sources.append((path, html, "downloaded_content"))

    for source_path, html, _source_type in html_sources:
        parsed = parse_html_sections(html)
        module["extracted"]["intro"].extend(parsed["intro"])
        for field, values in parsed["sections"].items():
            module["extracted"][field].extend(values)

    for field, values in module["extracted"].items():
        module["extracted"][field] = unique_texts(values)

    module["assessment"]["declared_methods"] = module["extracted"]["assessment_methods"]
    return module


def normalize_course(course_dir, include_section_zero=False):
    index_path = course_dir / "index.json"
    index = read_json(index_path)
    raw_course = read_json(course_dir / index["raw"]["course"])
    course_info = index["course"]
    normalized = {
        "schema_version": "course-connector.normalized.v0.1",
        "normalized_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": {
            "type": "moodle_raw_course_tree",
            "course_dir": str(course_dir),
            "index": str(index_path.relative_to(course_dir)),
            "raw_course": index["raw"]["course"],
            "raw_contents": index["raw"]["contents"],
        },
        "course": {
            "id": str(course_info.get("shortname") or course_info.get("id")),
            "moodle_id": course_info.get("id"),
            "shortname": course_info.get("shortname"),
            "title": course_info.get("fullname"),
            "summary": clean_text(strip_html(first_course(raw_course).get("summary", ""))),
        },
        "units": [],
        "course_signals": {
            "skills": [],
            "competencies": [],
            "assessment_methods": [],
            "assessment_types": {},
        },
    }

    course_buckets = {
        "skills": {},
        "competencies": {},
        "assessment_methods": {},
    }
    assessment_type_counter = Counter()

    for section_entry in index["sections"]:
        section_number = section_entry.get("section")
        if section_number == 0 and not include_section_zero:
            continue

        section_path = course_dir / section_entry["path"] / "section.raw.json"
        section_raw = read_json(section_path)
        unit_id = f"{normalized['course']['id']}:s{str(section_number).zfill(2)}"
        unit = {
            "unit_id": unit_id,
            "section_number": section_number,
            "title": section_entry.get("name"),
            "source_path": str(section_path.relative_to(course_dir)),
            "skills": [],
            "competencies": [],
            "assessment_methods": [],
            "learning_outcomes": [],
            "success_criteria": [],
            "assessment_tasks": [],
            "modules": [],
            "competency_coverage": [],
        }
        buckets = {
            "skills": {},
            "competencies": {},
            "assessment_methods": {},
            "learning_outcomes": {},
            "success_criteria": {},
            "check_content": {},
        }

        section_summary = section_raw.get("summary", "")
        if section_summary:
            parsed = parse_html_sections(section_summary)
            for field, values in parsed["sections"].items():
                evidence = make_evidence(
                    course_dir,
                    "section_summary",
                    section_path,
                    heading=display_heading(field),
                )
                add_items(buckets, field, values, evidence)
                if field in course_buckets:
                    add_items(course_buckets, field, values, evidence)

        for module_entry in section_entry.get("modules", []):
            module = extract_module(course_dir, module_entry)
            unit["modules"].append(module)
            assessment_type_counter[module["assessment"]["moodle_type"]] += 1

            module_source = course_dir / module["source_path"]
            for field in buckets:
                values = module["extracted"].get(field, [])
                if not values:
                    continue
                evidence = make_evidence(
                    course_dir,
                    module_evidence_type(module),
                    module_source,
                    heading=display_heading(field),
                    module_id=module["module_id"],
                    module_type=module["moodle_modname"],
                )
                add_items(buckets, field, values, evidence)
                if field in course_buckets:
                    add_items(course_buckets, field, values, evidence)

            if module["assessment"]["is_assessment"]:
                task_texts = module["extracted"]["check_content"] or module["extracted"]["intro"]
                unit["assessment_tasks"].append({
                    "module_id": module["module_id"],
                    "title": module["title"],
                    "moodle_type": module["assessment"]["moodle_type"],
                    "declared_methods": module["assessment"]["declared_methods"],
                    "task_text": " ".join(task_texts),
                    "criteria": module["extracted"]["success_criteria"],
                    "evidence": [
                        make_evidence(
                            course_dir,
                            module_evidence_type(module),
                            module_source,
                            module_id=module["module_id"],
                            module_type=module["moodle_modname"],
                        )
                    ],
                })

        for field in ("skills", "competencies", "assessment_methods", "learning_outcomes", "success_criteria"):
            unit[field] = finalize_items(buckets[field])
        unit["competency_coverage"] = build_competency_coverage(unit, buckets)
        normalized["units"].append(unit)

    for field in ("skills", "competencies", "assessment_methods"):
        normalized["course_signals"][field] = finalize_items(course_buckets[field])
    normalized["course_signals"]["assessment_types"] = dict(sorted(assessment_type_counter.items()))
    return normalized


def first_course(raw_course):
    courses = raw_course.get("courses", [])
    return courses[0] if courses else {}


def strip_html(html):
    parsed = parse_html_sections(html)
    return " ".join(parsed["intro"] + [item for values in parsed["sections"].values() for item in values])


def display_heading(field):
    for heading, alias in HEADING_ALIASES.items():
        if alias == field:
            return heading
    return field


def module_evidence_type(module):
    role = module["role"]
    if role == "learning_material":
        return "learning_material"
    if role == "assignment":
        return "practice_assignment"
    if role == "quiz":
        return "assessment_quiz"
    return role


def build_competency_coverage(unit, buckets):
    coverage = []
    task_text = " ".join(task["task_text"] for task in unit["assessment_tasks"])
    criteria_text = " ".join(item["text"] for item in finalize_items(buckets["success_criteria"]))
    for competency in finalize_items(buckets["competencies"]):
        roles = evidence_roles(competency["evidence"])
        role_set = set(roles)
        support = {
            "declared": "declared" in role_set,
            "taught": "taught" in role_set,
            "practiced": "practiced" in role_set,
            "assessed": "assessed" in role_set,
            "criteria": bool(criteria_text),
        }
        support_score = (
            0.15 * support["declared"]
            + 0.25 * support["taught"]
            + 0.25 * support["practiced"]
            + 0.25 * support["assessed"]
            + 0.10 * support["criteria"]
        )
        status = coverage_status(support, support_score)
        coverage.append({
            "competency": competency["text"],
            "normalized_text": competency["normalized_text"],
            "status": status,
            "support_score": round(support_score, 2),
            "support": support,
            "review_required": status in {"declared_only", "weak", "uncertain"},
            "evidence": competency["evidence"],
            "assessment_context": {
                "assessment_task_count": len(unit["assessment_tasks"]),
                "has_task_text": bool(clean_text(task_text)),
                "has_success_criteria": bool(clean_text(criteria_text)),
            },
        })
    return coverage


def evidence_roles(evidence_items):
    roles = []
    for evidence in evidence_items:
        source_type = evidence.get("source_type")
        if source_type == "section_summary":
            roles.append("declared")
        elif source_type == "learning_material":
            roles.append("taught")
        elif source_type == "practice_assignment":
            roles.append("practiced")
        elif source_type == "assessment_quiz":
            roles.append("assessed")
    return roles


def coverage_status(support, support_score):
    if support["taught"] and (support["practiced"] or support["assessed"]) and support["criteria"]:
        return "strong"
    if support["taught"] and (support["practiced"] or support["assessed"]):
        return "medium"
    if support_score > 0.3:
        return "weak"
    if support["declared"]:
        return "declared_only"
    return "uncertain"


def main():
    args = parse_args()
    out_dir = Path(args.out_dir)
    outputs = []
    for course_arg in args.courses:
        course_dir = Path(course_arg)
        if not (course_dir / "index.json").exists():
            raise RuntimeError(f"Course directory must contain index.json: {course_dir}")
        normalized = normalize_course(course_dir, include_section_zero=args.include_section_zero)
        output_path = out_dir / f"{normalized['course']['id']}.course.normalized.json"
        write_json(output_path, normalized)
        outputs.append({
            "course_id": normalized["course"]["id"],
            "path": str(output_path),
            "units": len(normalized["units"]),
            "competencies": len(normalized["course_signals"]["competencies"]),
            "skills": len(normalized["course_signals"]["skills"]),
        })

    write_json(out_dir / "index.json", {
        "schema_version": "course-connector.normalized-index.v0.1",
        "normalized_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "courses": outputs,
    })
    for output in outputs:
        print(
            f"Normalized {output['course_id']}: "
            f"{output['units']} units, {output['competencies']} competencies, {output['skills']} skills"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
