#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


CANDIDATES_SCHEMA = "course-connector.comparison-candidates.v0.1"
VERIFIED_SCHEMA = "course-connector.verified-comparison.v0.1"
PROMPT_VERSION = "course-comparison-prompts.v0.1"
RELATION_TYPES = {"reinforcement", "duplication", "internal_gap", "course_break", "uncertain", "unrelated"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Verify course comparison candidates with an evidence-only LLM prompt."
    )
    parser.add_argument("candidates", help="comparison/candidates.<course_a>__<course_b>.json")
    parser.add_argument("--out-dir", default="data/comparison/llm")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--provider", choices=["openai", "gemini", "lmstudio"], default=os.environ.get("LLM_PROVIDER", "openai"))
    parser.add_argument("--model", default=None)
    parser.add_argument("--temperature", type=float, default=0.0)
    return parser.parse_args()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_env(path=".env"):
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def input_hash(payload):
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def load_candidates(path):
    payload = read_json(path)
    if payload.get("schema_version") != CANDIDATES_SCHEMA:
        raise RuntimeError(f"{path} is not a course comparison candidates file.")
    if not isinstance(payload.get("candidates"), list):
        raise RuntimeError(f"{path} has no candidates array.")
    return payload


def prompt_for_candidate(candidate):
    if candidate["candidate_type"] == "coverage_verification":
        task = "Проверь, является ли заявленная компетенция неподтверждённой внутри курса."
        allowed = ["internal_gap", "uncertain"]
    else:
        task = "Сравни две учебные единицы и классифицируй связь между ними."
        allowed = ["reinforcement", "duplication", "course_break", "uncertain", "unrelated"]

    system = (
        "Ты проверяющий слой Course Connector. Используй только факты из candidate_payload "
        "и evidence_refs. Не добавляй внешние знания. Если evidence недостаточно, верни uncertain. "
        "Ответ должен быть только валидным JSON."
    )
    user = {
        "task": task,
        "allowed_relation_types": allowed,
        "required_json_shape": {
            "relation_type": "one of allowed_relation_types",
            "confidence": "number from 0 to 1",
            "rationale": "short Russian explanation grounded in evidence",
            "evidence_refs": ["ref_id values used"],
            "review_required": "boolean"
        },
        "candidate_id": candidate["candidate_id"],
        "relation_hint": candidate["relation_hint"],
        "preliminary_score": candidate["preliminary_score"],
        "candidate_payload": compact_prompt_payload(candidate["payload"]),
        "evidence_refs": compact_evidence_refs(candidate["evidence_refs"]),
    }
    return {
        "prompt_version": PROMPT_VERSION,
        "system": system,
        "user": user,
    }


def truncate_text(text, limit=420):
    text = str(text or "").strip()
    return text if len(text) <= limit else text[:limit - 3] + "..."


def compact_items(items, limit=5):
    return [truncate_text(item.get("text") or item.get("competency") or "") for item in items[:limit]]


def compact_tasks(tasks, limit=2):
    result = []
    for task in tasks[:limit]:
        result.append({
            "title": truncate_text(task.get("title"), 120),
            "moodle_type": task.get("moodle_type"),
            "declared_methods": [truncate_text(item, 120) for item in task.get("declared_methods", [])[:3]],
            "task_text": truncate_text(task.get("task_text"), 320),
            "criteria": [truncate_text(item, 140) for item in task.get("criteria", [])[:4]],
        })
    return result


def compact_unit_for_prompt(unit):
    if not isinstance(unit, dict):
        return unit
    return {
        "unit_id": unit.get("unit_id"),
        "title": unit.get("title"),
        "competencies": compact_items(unit.get("competencies", []), 4),
        "skills": compact_items(unit.get("skills", []), 5),
        "learning_outcomes": compact_items(unit.get("learning_outcomes", []), 2),
        "assessment_methods": compact_items(unit.get("assessment_methods", []), 3),
        "success_criteria": compact_items(unit.get("success_criteria", []), 4),
        "assessment_tasks": compact_tasks(unit.get("assessment_tasks", []), 2),
        "coverage": [
            {
                "competency": truncate_text(item.get("competency"), 160),
                "status": item.get("status"),
                "support_score": item.get("support_score"),
                "support": item.get("support", {}),
            }
            for item in unit.get("competency_coverage", [])[:4]
        ],
    }


def compact_prompt_payload(payload):
    compact = {}
    for key, value in payload.items():
        if key in {"unit", "unit_a", "unit_b", "downstream_unit"}:
            compact[key] = compact_unit_for_prompt(value)
        elif key in {"course", "course_a", "course_b", "upstream_course", "downstream_course"}:
            compact[key] = value
        elif key == "downstream_signal":
            compact[key] = {
                "text": truncate_text(value.get("text"), 160),
                "normalized_text": truncate_text(value.get("normalized_text"), 160),
            }
        elif key == "competency":
            compact[key] = {
                "text": truncate_text(value.get("text"), 180),
                "coverage_status": value.get("coverage_status"),
                "support": value.get("support", {}),
                "support_score": value.get("support_score"),
            }
        elif key == "instruction":
            compact[key] = value
        elif key in {"task", "comparison_focus", "deterministic_signals", "missing_prerequisites"}:
            compact[key] = value
    return compact


def compact_evidence_refs(refs, limit=8):
    selected = []
    buckets = {}
    for ref in refs:
        buckets.setdefault(ref.get("course_id", "unknown"), []).append(ref)
    while len(selected) < limit and any(buckets.values()):
        for key in sorted(buckets):
            if buckets[key] and len(selected) < limit:
                selected.append(buckets[key].pop(0))

    result = []
    for ref in selected:
        result.append({
            "ref_id": ref.get("ref_id"),
            "course_id": ref.get("course_id"),
            "unit_id": ref.get("unit_id"),
            "source_type": ref.get("source_type"),
            "heading": ref.get("heading"),
            "text": truncate_text(ref.get("text"), 220),
        })
    return result


def dry_run_response(candidate):
    relation = candidate.get("relation_hint", "uncertain")
    if relation not in {"reinforcement", "duplication", "internal_gap", "course_break"}:
        relation = "uncertain"
    confidence = min(0.84, max(0.35, float(candidate.get("preliminary_score") or 0.0)))
    if candidate["relation_hint"] == "internal_gap":
        confidence = max(confidence, 0.7)
    if candidate["relation_hint"] == "course_break":
        confidence = max(confidence, 0.7)
    evidence_ids = [ref["ref_id"] for ref in candidate.get("evidence_refs", [])[:6]]
    return {
        "relation_type": relation,
        "confidence": round(confidence, 3),
        "rationale": "Dry-run вывод: требуется LLM-проверка, но candidate содержит evidence для ручного анализа.",
        "evidence_refs": evidence_ids,
        "review_required": True,
    }


def call_openai_responses(prompt, model, temperature):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Use --dry-run for offline verification.")

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    url = f"{base_url}/responses"
    body = {
        "model": model,
        "temperature": temperature,
        "input": [
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": json.dumps(prompt["user"], ensure_ascii=False)}
        ],
        "text": {"format": {"type": "json_object"}}
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "course-connector/0.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API error {error.code}: {detail}") from error

    payload = json.loads(raw)
    text = extract_response_text(payload)
    return json.loads(text), payload


def call_gemini_generate_content(prompt, model, temperature):
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it to .env or use --dry-run.")

    base_url = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    model_name = model.removeprefix("models/")
    url = f"{base_url}/models/{model_name}:generateContent?key={api_key}"
    body = {
        "systemInstruction": {
            "parts": [{"text": prompt["system"]}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": json.dumps(prompt["user"], ensure_ascii=False)}]
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json"
        }
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "course-connector/0.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini API error {error.code}: {detail}") from error

    payload = json.loads(raw)
    text = extract_gemini_text(payload)
    return json.loads(text), payload


def call_lmstudio_responses(prompt, model, temperature):
    base_url = os.environ.get("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
    url = f"{base_url}/responses"
    body = {
        "model": model,
        "temperature": temperature,
        "input": [
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": json.dumps(prompt["user"], ensure_ascii=False)}
        ]
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "course-connector/0.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LM Studio API error {error.code}: {detail}") from error

    payload = json.loads(raw)
    text = extract_response_text(payload)
    return json.loads(extract_json_object(text)), payload


def extract_response_text(payload):
    if "output_text" in payload:
        return payload["output_text"]
    parts = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and "text" in content:
                parts.append(content["text"])
    if not parts:
        raise RuntimeError("Could not extract JSON text from LLM response.")
    return "\n".join(parts)


def extract_json_object(text):
    text = str(text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise RuntimeError(f"Could not find JSON object in model text: {text[:200]}")
    return text[start:end + 1]


def extract_gemini_text(payload):
    parts = []
    for candidate in payload.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            if "text" in part:
                parts.append(part["text"])
    if not parts:
        raise RuntimeError("Could not extract JSON text from Gemini response.")
    return "\n".join(parts)


def default_model(provider):
    if provider == "lmstudio":
        return os.environ.get("LMSTUDIO_MODEL", "qwen3-14b-mlx")
    if provider == "gemini":
        return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    return os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")


def call_provider(prompt, provider, model, temperature):
    if provider == "lmstudio":
        return call_lmstudio_responses(prompt, model, temperature)
    if provider == "gemini":
        return call_gemini_generate_content(prompt, model, temperature)
    return call_openai_responses(prompt, model, temperature)


def validate_llm_result(result, candidate):
    relation = result.get("relation_type", "uncertain")
    if relation == "unrelated":
        relation = "uncertain"
    if relation not in RELATION_TYPES:
        relation = "uncertain"

    try:
        confidence = float(result.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    valid_ref_ids = {ref["ref_id"] for ref in candidate.get("evidence_refs", [])}
    used_refs = [ref for ref in result.get("evidence_refs", []) if ref in valid_ref_ids]
    if not used_refs:
        relation = "uncertain"
        confidence = min(confidence, 0.5)

    review_required = bool(result.get("review_required", False))
    if confidence < 0.85 or relation == "uncertain":
        review_required = True

    return {
        "relation_type": relation,
        "confidence": round(confidence, 3),
        "rationale": str(result.get("rationale") or "Нет объяснения от LLM."),
        "evidence_refs": used_refs,
        "review_required": review_required,
    }


def refs_by_id(candidate):
    return {ref["ref_id"]: ref for ref in candidate.get("evidence_refs", [])}


def payload_summary(candidate):
    payload = candidate.get("payload", {})
    summary = {
        "task": payload.get("task"),
        "relation_hint": candidate.get("relation_hint"),
        "preliminary_score": candidate.get("preliminary_score"),
    }
    for key in ("unit", "unit_a", "unit_b", "downstream_unit"):
        if key in payload:
            value = payload[key]
            summary[key] = {
                "unit_id": value.get("unit_id"),
                "title": value.get("title"),
            }
    return summary


def make_finding(candidate, checked, model, raw_response=None, dry_run=False):
    ref_lookup = refs_by_id(candidate)
    evidence = [ref_lookup[ref_id] for ref_id in checked["evidence_refs"] if ref_id in ref_lookup]
    return {
        "candidate_id": candidate["candidate_id"],
        "candidate_type": candidate["candidate_type"],
        "relation_type": checked["relation_type"],
        "confidence": checked["confidence"],
        "rationale": checked["rationale"],
        "evidence_refs": evidence,
        "review_required": checked["review_required"],
        "llm_model": None if dry_run else model,
        "prompt_version": PROMPT_VERSION,
        "input_hash": input_hash(candidate),
        "courses": {
            "course_a": candidate["course_a"],
            "course_b": candidate["course_b"],
        },
        "payload_summary": payload_summary(candidate),
        "raw_response": raw_response,
        "dry_run": dry_run,
    }


def derive_output_stem(candidates_path):
    name = Path(candidates_path).name
    if name.startswith("candidates."):
        return name.replace("candidates.", "", 1).replace(".json", "")
    return Path(candidates_path).stem


def main():
    load_env()
    args = parse_args()
    model = args.model or default_model(args.provider)
    candidates_path = Path(args.candidates)
    candidates_payload = load_candidates(candidates_path)
    candidates = candidates_payload["candidates"]
    if args.limit:
        candidates = candidates[:args.limit]

    out_dir = Path(args.out_dir)
    stem = derive_output_stem(candidates_path)
    prompt_rows = []
    findings = []

    for candidate in candidates:
        prompt = prompt_for_candidate(candidate)
        row = {
            "candidate_id": candidate["candidate_id"],
            "prompt_version": PROMPT_VERSION,
            "input_hash": input_hash(candidate),
            "prompt": prompt,
        }
        prompt_rows.append(row)

        if args.dry_run:
            llm_result = dry_run_response(candidate)
            raw_response = None
        else:
            llm_result, raw_response = call_provider(prompt, args.provider, model, args.temperature)
        checked = validate_llm_result(llm_result, candidate)
        findings.append(make_finding(candidate, checked, model, raw_response=raw_response, dry_run=args.dry_run))

    verified = {
        "schema_version": VERIFIED_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_candidates": str(candidates_path),
        "courses": candidates_payload["courses"],
        "prompt_version": PROMPT_VERSION,
        "llm_provider": None if args.dry_run else args.provider,
        "llm_model": None if args.dry_run else model,
        "dry_run": args.dry_run,
        "findings": findings,
    }

    write_jsonl(out_dir / f"prompts.{stem}.jsonl", prompt_rows)
    write_json(out_dir / f"verified.{stem}.json", verified)

    canonical_verified = candidates_path.parent / f"verified.{stem}.json"
    if args.limit is None:
        write_json(canonical_verified, verified)
        print(f"Verified {len(findings)} candidates. Wrote {canonical_verified}")
    else:
        print(f"Verified {len(findings)} candidates. Wrote {out_dir / f'verified.{stem}.json'}")
    if args.dry_run:
        print(f"Dry-run prompts saved to {out_dir / f'prompts.{stem}.jsonl'}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
