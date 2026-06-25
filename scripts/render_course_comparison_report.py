#!/usr/bin/env python3
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


VERIFIED_SCHEMA = "course-connector.verified-comparison.v0.1"
REPORT_SCHEMA = "course-connector.comparison-report.v0.1"
GROUPS = ["reinforcement", "duplication", "internal_gap", "course_break", "uncertain"]
GROUP_TITLES = {
    "reinforcement": "Полезное повторение",
    "duplication": "Вероятное дублирование",
    "internal_gap": "Неподтверждённые компетенции",
    "course_break": "Разрывы между курсами",
    "uncertain": "Неопределённые выводы",
}


def parse_args():
    parser = argparse.ArgumentParser(description="Render Course Connector comparison reports.")
    parser.add_argument("verified", help="comparison/verified.<course_a>__<course_b>.json")
    parser.add_argument("--out-dir", default="data/comparison/report")
    return parser.parse_args()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_verified(path):
    payload = read_json(path)
    if payload.get("schema_version") != VERIFIED_SCHEMA:
        raise RuntimeError(f"{path} is not a verified comparison file.")
    if not isinstance(payload.get("findings"), list):
        raise RuntimeError(f"{path} has no findings array.")
    return payload


def normalize_relation(relation):
    relation = relation if relation in GROUPS else "uncertain"
    return relation


def group_findings(findings):
    grouped = defaultdict(list)
    for finding in findings:
        grouped[normalize_relation(finding.get("relation_type"))].append(finding)
    for group in GROUPS:
        grouped[group].sort(key=lambda item: item.get("confidence", 0), reverse=True)
    return grouped


def report_from_verified(verified):
    grouped = group_findings(verified["findings"])
    findings = {group: grouped[group] for group in GROUPS}
    return {
        "schema_version": REPORT_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_verified": verified.get("source_candidates"),
        "dry_run": verified.get("dry_run", False),
        "courses": verified["courses"],
        "summary": {group: len(findings[group]) for group in GROUPS},
        "findings": findings,
        "methodology": {
            "ru": (
                "Отчёт построен из deterministic candidates и LLM verification layer. "
                "LLM получает только compact evidence payloads, а выводы без evidence refs "
                "переводятся в uncertain или review_required."
            )
        },
    }


def course_label(course):
    return f"{course.get('course_id')} ({course.get('title')})"


def evidence_line(ref):
    text = ref.get("text") or ""
    if len(text) > 160:
        text = text[:157] + "..."
    parts = [ref.get("course_id", ""), ref.get("unit_id") or "", ref.get("source_type", ""), ref.get("path", "")]
    base = " / ".join(part for part in parts if part)
    return f"{base}: {text}" if text else base


def finding_title(finding):
    courses = finding.get("courses", {})
    left = courses.get("course_a", {})
    right = courses.get("course_b", {})
    left_title = left.get("unit_title") or left.get("course_id")
    right_title = right.get("unit_title") or right.get("course_id")
    if left_title == right_title:
        return str(left_title)
    return f"{left_title} ↔ {right_title}"


def render_markdown(report):
    course_a = report["courses"]["course_a"]
    course_b = report["courses"]["course_b"]
    lines = [
        "# Отчёт Course Connector",
        "",
        f"- Курс A: {course_label(course_a)}",
        f"- Курс B: {course_label(course_b)}",
        f"- Dry-run: {'да' if report.get('dry_run') else 'нет'}",
        "",
        "## Методология",
        "",
        (
            "Система сначала строит deterministic candidates из нормализованных курсов: "
            "компетенции, навыки, результаты обучения, задания, критерии и evidence. "
            "LLM используется только как проверяющий слой над компактными payloads. "
            "Каждый вывод обязан иметь evidence refs; слабые или неподтверждённые выводы "
            "помечаются `review_required`."
        ),
        "",
        "## Сводка",
        "",
    ]
    for group in GROUPS:
        lines.append(f"- {GROUP_TITLES[group]}: {report['summary'][group]}")
    lines.append("")

    for group in GROUPS:
        lines.extend([f"## {GROUP_TITLES[group]}", ""])
        findings = report["findings"][group]
        if not findings:
            lines.extend(["Выводов этого типа не найдено.", ""])
            continue
        for finding in findings:
            lines.append(f"### {finding_title(finding)}")
            lines.append("")
            lines.append(f"- Candidate: `{finding.get('candidate_id')}`")
            lines.append(f"- Confidence: `{finding.get('confidence')}`")
            lines.append(f"- Review required: `{finding.get('review_required')}`")
            lines.append(f"- Объяснение: {finding.get('rationale')}")
            lines.append("- Evidence:")
            evidence = finding.get("evidence_refs", [])
            if evidence:
                for ref in evidence[:5]:
                    lines.append(f"  - {evidence_line(ref)}")
            else:
                lines.append("  - Evidence отсутствует, вывод требует проверки.")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def derive_stem(path):
    name = Path(path).name
    if name.startswith("verified."):
        return name.replace("verified.", "", 1).replace(".json", "")
    return Path(path).stem


def main():
    args = parse_args()
    verified_path = Path(args.verified)
    verified = load_verified(verified_path)
    report = report_from_verified(verified)
    out_dir = Path(args.out_dir)
    stem = derive_stem(verified_path)
    json_path = out_dir / f"report.{stem}.json"
    md_path = out_dir / f"report.{stem}.md"
    write_json(json_path, report)
    write_text(md_path, render_markdown(report))
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
