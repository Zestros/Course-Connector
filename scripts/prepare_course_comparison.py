#!/usr/bin/env python3
import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


NORMALIZED_SCHEMA = "course-connector.normalized.v0.1"
CANDIDATES_SCHEMA = "course-connector.comparison-candidates.v0.1"

RELATION_TYPES = {"reinforcement", "duplication", "internal_gap", "course_break", "uncertain"}
STOP_WORDS = {
    "и", "в", "во", "на", "по", "для", "с", "со", "к", "ко", "от", "до", "из", "без",
    "при", "или", "а", "но", "как", "что", "это", "этот", "эта", "эти", "the", "and",
    "or", "of", "to", "in", "for", "with", "by", "as", "is", "are"
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Prepare compact evidence-based candidates for LLM course comparison."
    )
    parser.add_argument("course_a", help="Upstream/first normalized course JSON.")
    parser.add_argument("course_b", help="Downstream/second normalized course JSON.")
    parser.add_argument("--out-dir", default="data/comparison")
    parser.add_argument("--skills-graph", default=None)
    parser.add_argument("--min-score", type=float, default=0.12)
    parser.add_argument("--max-candidates", type=int, default=80)
    return parser.parse_args()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_text(value):
    value = str(value or "").lower().replace("ё", "е")
    value = re.sub(r"[^\w\s+-]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def tokens(value):
    return {
        token for token in re.split(r"\s+", normalize_text(value))
        if len(token) > 2 and token not in STOP_WORDS
    }


def load_normalized_course(path):
    payload = read_json(path)
    if payload.get("schema_version") != NORMALIZED_SCHEMA:
        raise RuntimeError(
            f"{path} is not a normalized course graph. "
            "Run normalize_moodle_course.py first and pass *.course.normalized.json files."
        )
    if not isinstance(payload.get("units"), list) or not payload.get("course"):
        raise RuntimeError(f"{path} does not look like a normalized course graph.")
    payload["_source_path"] = str(path)
    return payload


def course_ref(course):
    info = course["course"]
    return {
        "course_id": info["id"],
        "title": info.get("title") or info["id"],
        "source_path": course["_source_path"],
    }


def item_texts(unit, field):
    return [item.get("text", "") for item in unit.get(field, [])]


def unit_signal_text(unit):
    parts = [unit.get("title", "")]
    for field in ("competencies", "skills", "learning_outcomes", "assessment_methods", "success_criteria"):
        parts.extend(item_texts(unit, field))
    for task in unit.get("assessment_tasks", []):
        parts.append(task.get("title", ""))
        parts.extend(task.get("declared_methods", []))
        parts.append(task.get("task_text", ""))
        parts.extend(task.get("criteria", []))
    return " ".join(parts)


def compact_item(item):
    return {
        "text": item.get("text", ""),
        "normalized_text": item.get("normalized_text", normalize_text(item.get("text", ""))),
    }


def compact_task(task):
    return {
        "module_id": task.get("module_id"),
        "title": task.get("title"),
        "moodle_type": task.get("moodle_type"),
        "declared_methods": task.get("declared_methods", []),
        "task_text": task.get("task_text", ""),
        "criteria": task.get("criteria", []),
    }


def compact_unit(unit):
    return {
        "unit_id": unit.get("unit_id"),
        "title": unit.get("title"),
        "skills": [compact_item(item) for item in unit.get("skills", [])],
        "competencies": [compact_item(item) for item in unit.get("competencies", [])],
        "learning_outcomes": [compact_item(item) for item in unit.get("learning_outcomes", [])],
        "assessment_methods": [compact_item(item) for item in unit.get("assessment_methods", [])],
        "success_criteria": [compact_item(item) for item in unit.get("success_criteria", [])],
        "assessment_tasks": [compact_task(task) for task in unit.get("assessment_tasks", [])],
        "competency_coverage": [
            {
                "competency": item.get("competency"),
                "status": item.get("status"),
                "support_score": item.get("support_score"),
                "support": item.get("support", {}),
                "review_required": item.get("review_required", False),
            }
            for item in unit.get("competency_coverage", [])
        ],
    }


def make_evidence_ref(course, unit, evidence, text=None, index=0):
    course_id = course["course"]["id"]
    ref_id = f"{course_id}:{unit.get('unit_id')}:{index}"
    return {
        "ref_id": ref_id,
        "course_id": course_id,
        "unit_id": unit.get("unit_id"),
        "source_type": evidence.get("source_type", "unknown"),
        "path": evidence.get("path", ""),
        "heading": evidence.get("heading"),
        "module_id": evidence.get("module_id"),
        "module_type": evidence.get("module_type"),
        "text": text,
    }


def collect_unit_evidence(course, unit, max_refs=12):
    refs = []
    idx = 1
    for field in ("competencies", "skills", "learning_outcomes", "assessment_methods", "success_criteria"):
        for item in unit.get(field, []):
            for evidence in item.get("evidence", []):
                refs.append(make_evidence_ref(course, unit, evidence, text=item.get("text"), index=idx))
                idx += 1
                if len(refs) >= max_refs:
                    return refs
    for task in unit.get("assessment_tasks", []):
        task_text = task.get("task_text") or task.get("title")
        for evidence in task.get("evidence", []):
            refs.append(make_evidence_ref(course, unit, evidence, text=task_text, index=idx))
            idx += 1
            if len(refs) >= max_refs:
                return refs
    return refs


def dedupe_evidence_refs(refs):
    seen = set()
    result = []
    for ref in refs:
        key = (ref["course_id"], ref.get("unit_id"), ref["source_type"], ref["path"], ref.get("heading"), ref.get("module_id"), ref.get("text"))
        if key not in seen:
            seen.add(key)
            ref = dict(ref)
            ref["ref_id"] = f"ev{len(result) + 1:04d}"
            result.append(ref)
    return result


def assessment_profile(unit):
    tasks = unit.get("assessment_tasks", [])
    types = Counter(task.get("moodle_type", "unknown") for task in tasks)
    method_tokens = set()
    for task in tasks:
        for method in task.get("declared_methods", []):
            method_tokens |= tokens(method)
        method_tokens |= tokens(task.get("task_text", ""))
        for criterion in task.get("criteria", []):
            method_tokens |= tokens(criterion)
    return {"types": dict(types), "tokens": method_tokens}


def jaccard(left, right):
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def exact_text_overlap(unit_a, unit_b):
    total = 0
    for field in ("competencies", "skills", "learning_outcomes"):
        left = {item.get("normalized_text") for item in unit_a.get(field, []) if item.get("normalized_text")}
        right = {item.get("normalized_text") for item in unit_b.get(field, []) if item.get("normalized_text")}
        total += len(left & right)
    return total


def unit_similarity(unit_a, unit_b):
    signal_score = jaccard(tokens(unit_signal_text(unit_a)), tokens(unit_signal_text(unit_b)))
    assess_a = assessment_profile(unit_a)
    assess_b = assessment_profile(unit_b)
    assessment_score = jaccard(set(assess_a["types"]), set(assess_b["types"])) * 0.4 + jaccard(assess_a["tokens"], assess_b["tokens"]) * 0.6
    exact_bonus = min(0.25, exact_text_overlap(unit_a, unit_b) * 0.08)
    score = min(1.0, signal_score * 0.65 + assessment_score * 0.25 + exact_bonus)
    return score, signal_score, assessment_score, exact_bonus


def relation_hint(score, assessment_score, exact_bonus):
    if score >= 0.6 and assessment_score >= 0.45:
        return "duplication"
    if score >= 0.18 or exact_bonus > 0:
        return "reinforcement"
    return "uncertain"


def candidate_course_side(course, unit=None):
    side = {"course_id": course["course"]["id"]}
    if unit:
        side["unit_id"] = unit.get("unit_id")
        side["unit_title"] = unit.get("title")
    else:
        side["unit_id"] = None
        side["unit_title"] = None
    return side


def make_candidate(candidate_type, relation, course_a, course_b, unit_a, unit_b, payload, evidence_refs, score, review_required):
    return {
        "candidate_id": "",
        "candidate_type": candidate_type,
        "relation_hint": relation,
        "course_a": candidate_course_side(course_a, unit_a),
        "course_b": candidate_course_side(course_b, unit_b),
        "payload": payload,
        "evidence_refs": dedupe_evidence_refs(evidence_refs),
        "preliminary_score": round(max(0.0, min(1.0, score)), 3),
        "review_required": bool(review_required),
    }


def build_internal_gap_candidates(course):
    candidates = []
    for unit in course.get("units", []):
        for coverage in unit.get("competency_coverage", []):
            status = coverage.get("status")
            support = coverage.get("support", {})
            weak = status not in {"strong", "medium"} or not (support.get("practiced") or support.get("assessed"))
            if not weak:
                continue
            refs = []
            for evidence in coverage.get("evidence", []):
                refs.append(make_evidence_ref(course, unit, evidence, text=coverage.get("competency"), index=len(refs) + 1))
            if not refs:
                refs = collect_unit_evidence(course, unit, max_refs=4)
            payload = {
                "task": "coverage_verification",
                "course": course_ref(course),
                "unit": compact_unit(unit),
                "competency": {
                    "text": coverage.get("competency"),
                    "normalized_text": coverage.get("normalized_text"),
                    "coverage_status": status,
                    "support": support,
                    "support_score": coverage.get("support_score"),
                    "assessment_context": coverage.get("assessment_context", {}),
                },
                "instruction": "Определи, является ли это неподтверждённой компетенцией. Используй только evidence_refs.",
            }
            candidates.append(make_candidate(
                "coverage_verification",
                "internal_gap",
                course,
                course,
                unit,
                unit,
                payload,
                refs,
                1 - float(coverage.get("support_score") or 0),
                True,
            ))
    return candidates


def load_skills_graph(path):
    if not path:
        return None
    graph_path = Path(path)
    if not graph_path.exists():
        raise RuntimeError(f"skills graph not found: {path}")
    raw = read_json(graph_path)
    entries = raw.get("skills", raw if isinstance(raw, list) else [])
    alias_to_entry = {}
    for entry in entries:
        labels = [entry.get("skill_id", ""), entry.get("label", "")] + entry.get("aliases", [])
        for label in labels:
            key = normalize_text(label)
            if key:
                alias_to_entry[key] = entry
    return {"entries": entries, "alias_to_entry": alias_to_entry, "path": str(graph_path)}


def match_graph_entry(text, graph):
    if not graph:
        return None
    normalized = normalize_text(text)
    if normalized in graph["alias_to_entry"]:
        return graph["alias_to_entry"][normalized]
    text_tokens = tokens(text)
    best = None
    best_score = 0
    for alias, entry in graph["alias_to_entry"].items():
        score = jaccard(text_tokens, tokens(alias))
        if score > best_score:
            best = entry
            best_score = score
    return best if best_score >= 0.5 else None


def covered_graph_ids(course, graph):
    covered = set()
    if not graph:
        return covered
    for unit in course.get("units", []):
        strongish = {
            item.get("normalized_text")
            for item in unit.get("competency_coverage", [])
            if item.get("status") in {"strong", "medium"}
        }
        for field in ("skills", "competencies"):
            for item in unit.get(field, []):
                entry = match_graph_entry(item.get("text", ""), graph)
                if entry and (field == "skills" or item.get("normalized_text") in strongish):
                    covered.add(entry.get("skill_id") or normalize_text(entry.get("label", "")))
    return covered


def build_course_break_candidates(course_a, course_b, graph):
    if not graph:
        return []
    covered = covered_graph_ids(course_a, graph)
    candidates = []
    for unit_b in course_b.get("units", []):
        for field in ("skills", "competencies"):
            for item in unit_b.get(field, []):
                entry = match_graph_entry(item.get("text", ""), graph)
                if not entry:
                    continue
                missing = [req for req in entry.get("requires", []) if req not in covered]
                if not missing:
                    continue
                refs = collect_unit_evidence(course_b, unit_b, max_refs=6)
                payload = {
                    "task": "alignment_verification",
                    "comparison_focus": "course_break",
                    "upstream_course": course_ref(course_a),
                    "downstream_course": course_ref(course_b),
                    "downstream_unit": compact_unit(unit_b),
                    "downstream_signal": compact_item(item),
                    "missing_prerequisites": missing,
                    "skills_graph_source": graph["path"],
                    "instruction": "Проверь, является ли это разрывом между курсами. Используй только evidence_refs и missing_prerequisites.",
                }
                candidates.append(make_candidate(
                    "alignment_verification",
                    "course_break",
                    course_a,
                    course_b,
                    None,
                    unit_b,
                    payload,
                    refs,
                    0.75,
                    True,
                ))
    return candidates


def build_alignment_candidates(course_a, course_b, min_score, max_candidates):
    candidates = []
    for unit_a in course_a.get("units", []):
        for unit_b in course_b.get("units", []):
            score, signal_score, assessment_score, exact_bonus = unit_similarity(unit_a, unit_b)
            if score < min_score:
                continue
            relation = relation_hint(score, assessment_score, exact_bonus)
            refs = collect_unit_evidence(course_a, unit_a, max_refs=8) + collect_unit_evidence(course_b, unit_b, max_refs=8)
            payload = {
                "task": "alignment_verification",
                "course_a": course_ref(course_a),
                "course_b": course_ref(course_b),
                "unit_a": compact_unit(unit_a),
                "unit_b": compact_unit(unit_b),
                "deterministic_signals": {
                    "token_overlap_score": round(signal_score, 3),
                    "assessment_similarity_score": round(assessment_score, 3),
                    "exact_text_bonus": round(exact_bonus, 3),
                    "preliminary_relation_hint": relation,
                },
                "instruction": "Классифицируй связь как reinforcement, duplication, course_break, unrelated или uncertain. Используй только evidence_refs.",
            }
            candidates.append(make_candidate(
                "alignment_verification",
                relation,
                course_a,
                course_b,
                unit_a,
                unit_b,
                payload,
                refs,
                score,
                score < 0.65,
            ))
    candidates.sort(key=lambda item: item["preliminary_score"], reverse=True)
    return candidates[:max_candidates]


def assign_candidate_ids(candidates):
    counters = Counter()
    for candidate in candidates:
        relation = candidate["relation_hint"]
        counters[relation] += 1
        candidate["candidate_id"] = f"{relation}-{counters[relation]:04d}"
    return candidates


def candidate_counts(candidates):
    counts = Counter(candidate["relation_hint"] for candidate in candidates)
    return {relation: counts.get(relation, 0) for relation in sorted(RELATION_TYPES)}


def build_output(course_a, course_b, candidates):
    candidates = assign_candidate_ids(candidates)
    return {
        "schema_version": CANDIDATES_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "courses": {
            "course_a": course_ref(course_a),
            "course_b": course_ref(course_b),
        },
        "candidate_counts": candidate_counts(candidates),
        "candidates": candidates,
    }


def main():
    args = parse_args()
    course_a_path = Path(args.course_a)
    course_b_path = Path(args.course_b)
    course_a = load_normalized_course(course_a_path)
    course_b = load_normalized_course(course_b_path)
    graph = load_skills_graph(args.skills_graph)

    candidates = []
    candidates.extend(build_internal_gap_candidates(course_a))
    candidates.extend(build_internal_gap_candidates(course_b))
    candidates.extend(build_alignment_candidates(course_a, course_b, args.min_score, args.max_candidates))
    candidates.extend(build_course_break_candidates(course_a, course_b, graph))

    output = build_output(course_a, course_b, candidates)
    out_dir = Path(args.out_dir)
    output_path = out_dir / f"candidates.{course_a['course']['id']}__{course_b['course']['id']}.json"
    write_json(output_path, output)
    print(
        f"Prepared {len(output['candidates'])} candidates for "
        f"{course_a['course']['id']} -> {course_b['course']['id']} at {output_path}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
