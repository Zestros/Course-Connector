"""Smart batch analysis execution."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from course_connector.llm_layer.config import LLMConfig
from course_connector.llm_layer.findings_merge import merge_findings
from course_connector.llm_layer.parsing.json_parser import parse_provider_response
from course_connector.llm_layer.parsing.relation_normalizer import normalize_relations
from course_connector.llm_layer.prompts.batch_renderer import build_final_findings_synthesis_prompt, build_skill_batch_prompt
from course_connector.llm_layer.providers.base import LLMProvider
from course_connector.llm_layer.providers.factory import create_provider


def analyze_batches(
    analysis_payload: dict[str, Any],
    *,
    provider: LLMProvider | None = None,
    config: LLMConfig | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one LLM call per smart batch and return final analysis plus context updates."""
    config = config or LLMConfig.from_input_payload(analysis_payload)
    provider = provider or create_provider(config)
    preprocessing = analysis_payload.get("preprocessing") if isinstance(analysis_payload.get("preprocessing"), dict) else {}
    batches = list(preprocessing.get("skill_batches") or [])
    evidence_roles = _evidence_roles(preprocessing)
    batch_results: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    warnings = list(analysis_payload.get("warnings") or [])

    total_batches = len(batches)
    for index, batch in enumerate(batches, start=1):
        batch_id = str(batch.get("batch_id") or "unknown_batch")
        if batch.get("diagnostic_only"):
            batch_result = {
                "batch_id": batch_id,
                "status": "diagnostic_only",
                "summary": "Diagnostic-only batch was not sent to the LLM relation analyzer.",
                "findings": [],
                "warnings": [],
            }
            batch_results.append(batch_result)
            _emit_progress(
                progress_callback,
                {
                    "event": "batch_complete",
                    "batch_id": batch_id,
                    "batch_type": batch.get("batch_type"),
                    "skill_ids": list(batch.get("skill_ids") or []),
                    "index": index,
                    "total": total_batches,
                    "status": "diagnostic_only",
                    "result": batch_result,
                },
            )
            continue
        _emit_progress(
            progress_callback,
            {
                "event": "batch_start",
                "batch_id": batch_id,
                "batch_type": batch.get("batch_type"),
                "skill_ids": list(batch.get("skill_ids") or []),
                "index": index,
                "total": total_batches,
                "estimated_prompt_tokens": batch.get("estimated_prompt_tokens"),
            },
        )
        prompt = build_skill_batch_prompt(batch, output_language=config.output_language)
        try:
            response = provider.generate(prompt)
            parsed = _parse_batch_response(response.text, batch_id)
        except Exception as exc:
            warning = f"Batch `{batch_id}` failed: {exc}"
            warnings.append(warning)
            batch_result = {"batch_id": batch_id, "status": "provider_error", "warnings": [warning]}
            batch_results.append(batch_result)
            _emit_progress(
                progress_callback,
                {
                    "event": "batch_complete",
                    "batch_id": batch_id,
                    "batch_type": batch.get("batch_type"),
                    "skill_ids": list(batch.get("skill_ids") or []),
                    "index": index,
                    "total": total_batches,
                    "status": "provider_error",
                    "result": batch_result,
                },
            )
            continue
        batch_warnings = [str(warning) for warning in parsed.get("warnings") or []]
        normalized = _normalize_batch_findings(parsed.get("findings") or [], batch_id, batch_warnings)
        normalized = _filter_cross_course_findings(normalized, batch_id, evidence_roles, batch_warnings)
        batch_result = {
            "batch_id": batch_id,
            "status": "completed",
            "summary": parsed.get("summary", ""),
            "findings": normalized,
            "warnings": batch_warnings,
        }
        batch_results.append(batch_result)
        findings.extend(normalized)
        warnings.extend(batch_warnings)
        _emit_progress(
            progress_callback,
            {
                "event": "batch_complete",
                "batch_id": batch_id,
                "batch_type": batch.get("batch_type"),
                "skill_ids": list(batch.get("skill_ids") or []),
                "index": index,
                "total": total_batches,
                "status": "completed",
                "result": batch_result,
            },
        )

    merged = merge_findings(findings)
    summary = _summary(merged, batch_results)
    if preprocessing.get("metrics", {}).get("merge_strategy") == "llm_synthesis" and merged:
        try:
            synthesis_prompt = build_final_findings_synthesis_prompt(
                course_profiles=preprocessing.get("course_profiles", {}),
                findings=merged,
                warnings=warnings,
                output_language=config.output_language,
            )
            synthesis_response = provider.generate(synthesis_prompt)
            synthesis = parse_provider_response(synthesis_response.text)
            synthesis_warnings = [*warnings, *list(synthesis.get("warnings") or [])]
            synthesized_relations = normalize_relations(synthesis.get("relations") or [], synthesis_warnings)
            if synthesized_relations:
                merged = _filter_allowed_evidence_refs(
                    synthesized_relations,
                    merged,
                    evidence_roles,
                    synthesis_warnings,
                )
                summary = str(synthesis.get("summary") or summary)
            warnings = synthesis_warnings
        except Exception as exc:
            warnings.append(f"Final findings synthesis failed: {exc}")
    analysis = {
        "status": _analysis_status(batch_results),
        "summary": summary,
        "relations": merged,
        "warnings": _dedupe(warnings),
        "provider": config.provider,
        "provider_mode": "batch_api",
    }
    context_updates = {
        "batch_results": batch_results,
        "merged_findings": merged,
        "metrics": {
            **dict(preprocessing.get("metrics") or {}),
            "diagnostic_only_batches": len([
                result for result in batch_results if result.get("status") == "diagnostic_only"
            ]),
            "executed_batches": len([
                result for result in batch_results if result.get("status") != "diagnostic_only"
            ]),
            "failed_batches": len([result for result in batch_results if result.get("status") == "provider_error"]),
        },
    }
    return analysis, context_updates


def _emit_progress(
    progress_callback: Callable[[dict[str, Any]], None] | None,
    event: dict[str, Any],
) -> None:
    if progress_callback is not None:
        progress_callback(event)


def _parse_batch_response(text: str, batch_id: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Batch `{batch_id}` response was not valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Batch `{batch_id}` response was not a JSON object.")
    return parsed


def _normalize_batch_findings(
    findings: list[Any],
    batch_id: str,
    warnings: list[str],
) -> list[dict[str, Any]]:
    enriched = []
    for finding in findings:
        if not isinstance(finding, dict):
            enriched.append(finding)
            continue
        item = dict(finding)
        item.setdefault("batch_id", batch_id)
        if not item.get("evidence_refs"):
            warnings.append(f"Batch `{batch_id}` finding without evidence_refs was skipped.")
            continue
        enriched.append(item)
    return normalize_relations(enriched, warnings)


def _filter_cross_course_findings(
    findings: list[dict[str, Any]],
    batch_id: str,
    evidence_roles: dict[str, str],
    warnings: list[str],
) -> list[dict[str, Any]]:
    result = []
    for finding in findings:
        if finding.get("type") not in {"useful_repetition", "probable_duplication"}:
            result.append(finding)
            continue
        roles = {_evidence_role(ref, evidence_roles) for ref in finding.get("evidence_refs", [])}
        if {"course_a", "course_b"} <= roles:
            result.append(finding)
            continue
        warnings.append(
            f"Batch `{batch_id}` {finding.get('type')} finding without Course A and Course B evidence was skipped."
        )
    return result


def _summary(relations: list[dict[str, Any]], batch_results: list[dict[str, Any]]) -> str:
    if not batch_results:
        return "Smart batch analysis did not plan any batches."
    attempted = [result for result in batch_results if result.get("status") != "diagnostic_only"]
    completed = len([result for result in attempted if result.get("status") == "completed"])
    diagnostic_only = len(batch_results) - len(attempted)
    suffix = f" Skipped {diagnostic_only} diagnostic-only batches." if diagnostic_only else ""
    return (
        f"Smart batch analysis completed {completed}/{len(attempted)} LLM batches "
        f"and returned {len(relations)} merged relation candidates."
        f"{suffix}"
    )


def _analysis_status(batch_results: list[dict[str, Any]]) -> str:
    attempted = [result for result in batch_results if result.get("status") != "diagnostic_only"]
    if attempted and all(result.get("status") == "provider_error" for result in attempted):
        return "provider_error"
    return "completed"


def _filter_allowed_evidence_refs(
    synthesized: list[dict[str, Any]],
    source_findings: list[dict[str, Any]],
    evidence_roles: dict[str, str],
    warnings: list[str],
) -> list[dict[str, Any]]:
    allowed = {_ref_key(ref) for finding in source_findings for ref in finding.get("evidence_refs", [])}
    filtered = []
    for relation in synthesized:
        refs = [ref for ref in relation.get("evidence_refs", []) if _ref_key(ref) in allowed]
        if not refs:
            warnings.append("Final synthesis relation without allowed evidence_refs was skipped.")
            continue
        if relation.get("type") in {"useful_repetition", "probable_duplication"}:
            roles = {_evidence_role(ref, evidence_roles) for ref in refs}
            if not {"course_a", "course_b"} <= roles:
                warnings.append("Final synthesis relation without Course A and Course B evidence was skipped.")
                continue
        item = dict(relation)
        item["evidence_refs"] = refs
        filtered.append(item)
    return filtered


def _evidence_roles(preprocessing: dict[str, Any]) -> dict[str, str]:
    roles: dict[str, str] = {}
    evidence_refs = preprocessing.get("evidence_refs")
    chunk_refs = evidence_refs.get("chunks", {}) if isinstance(evidence_refs, dict) else {}
    if isinstance(chunk_refs, dict):
        for chunk_id, ref in chunk_refs.items():
            if isinstance(ref, dict) and ref.get("source_role"):
                roles[str(chunk_id)] = str(ref["source_role"])
    for batch in preprocessing.get("skill_batches") or []:
        for role in ("course_a", "course_b", "assessments"):
            for chunk_id in batch.get(f"{role}_chunk_ids", []) or []:
                roles.setdefault(str(chunk_id), role)
    return roles


def _evidence_role(ref: Any, evidence_roles: dict[str, str]) -> str:
    if isinstance(ref, dict):
        role = ref.get("source_role")
        if role:
            return str(role)
        ref = ref.get("chunk_id") or ref
    key = str(ref)
    if key in evidence_roles:
        return evidence_roles[key]
    if key.startswith("course_a_"):
        return "course_a"
    if key.startswith("course_b_"):
        return "course_b"
    if key.startswith("assessments_"):
        return "assessments"
    return "unknown"


def _ref_key(ref: Any) -> str:
    if isinstance(ref, dict):
        return str(ref.get("chunk_id") or ref)
    return str(ref)


def _dedupe(warnings: list[Any]) -> list[str]:
    result = []
    seen = set()
    for warning in warnings:
        text = str(warning)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
