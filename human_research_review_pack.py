"""Deterministic owner-facing rendering of retained research dossiers and tasks."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from persistent_research_dossier import _change_set

FORBIDDEN = ("BUY", "SELL", "HOLD", "target price", "probability")


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _facts(dossier: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{"type": "FACT", "field": key, "value": value,
             "evidence_path": f"stock_research.<ticker>.ai_ready_brief.facts.{key}", "authority": "SHADOW_ONLY"}
            for key, value in sorted(dossier["deterministic_research_state"]["facts"].items())]


def _inferences(dossier: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{"type": "INFERENCE", "category": item["category"], "value": item["value"],
             "authority": item["authority"], "evidence_path": "stock_research.<ticker>.ai_ready_brief.deterministic_inferences"}
            for item in dossier["deterministic_research_state"]["inferences"]]


def _change(previous: Mapping[str, Any] | None, dossier: Mapping[str, Any]) -> dict[str, Any]:
    if previous is None:
        return {"categories": ["NEW_RESEARCH_STATE"], "baseline": True}
    result = _change_set(previous, dossier)
    return {"categories": result["categories"], "baseline": False}


def build(*, product: Mapping[str, Any], dossiers: Mapping[str, Mapping[str, Any]],
          tasks: Mapping[str, Mapping[str, Any]], prospective: Mapping[str, Any],
          previous_dossiers: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Create a consumer-only structured review pack without changing source state."""
    previous_dossiers = previous_dossiers or {}
    product_records = {record["ticker"]: record for record in product["stock_research"]}
    question_tasks = {task["ticker"]: task for task in tasks.values()
                      if task["task_kind"] == "QUESTION_TO_VERIFY" and task["ticker"] in dossiers}
    queue_tickers = [entry["ticker"] for entry in product["research_attention"][:25]]
    review_entries = []
    for ticker in queue_tickers:
        dossier, record, task = dossiers[ticker], product_records[ticker], question_tasks[ticker]
        review_entries.append({
            "ticker": ticker,
            "dossier_identity": dossier["dossier_identity"],
            "review_reasons": ["PRESERVED_DETERMINISTIC_AI_RESEARCH_QUEUE_MEMBERSHIP"] +
                              record["research_summary"]["attention_descriptors"],
            "attention_descriptors": record["research_summary"]["attention_descriptors"],
            "authority_tiers": dossier["authority_evidence_tiers"],
            "thesis": {"items": dossier["thesis"], "hash": dossier["thesis_hash"],
                       "reference": "stock_briefs.<ticker>.bull_thesis"},
            "counter_thesis": {"items": dossier["counter_thesis"], "hash": dossier["counter_thesis_hash"],
                                "reference": "stock_briefs.<ticker>.counter_thesis"},
            "facts": _facts(dossier),
            "inferences": _inferences(dossier),
            "data_gaps": dossier["data_gaps"],
            "question_to_verify": task["question"],
            "expected_evidence_type": task["expected_evidence_type"],
            "unresolved_task": {"task_identity": task["task_identity"], "status": task["task_status"],
                                "authority_tier": task["authority_tier"], "evidence_paths": task["evidence_paths"]},
            "warnings": dossier["warnings"],
            "dossier_change": _change(previous_dossiers.get(ticker), dossier),
            "prospective_learning": {"snapshot_id": prospective["snapshot_id"],
                                    "outcome_status": prospective["outcome_status"]},
            "owner_annotation": {"review_status": None, "owner_note": None, "follow_up_needed": None,
                                 "evidence_requested": None, "research_priority_override": None,
                                 "system_populated": False},
            "not_a_recommendation": True,
        })
    status_counts: dict[str, int] = {}
    for task in tasks.values():
        status_counts[task["task_status"]] = status_counts.get(task["task_status"], 0) + 1
    deferred_groups: dict[tuple[str | None, str | None], list[Mapping[str, Any]]] = {}
    for task in tasks.values():
        if task["task_status"] == "DEFERRED_NO_CURRENT_EVIDENCE_ROUTE":
            deferred_groups.setdefault((task["deferred_reason"], task["reopen_condition"]), []).append(task)
    deferred_summary = [{"deferred_reason": reason, "reopen_condition": reopen, "affected_task_count": len(group),
                         "affected_ticker_count": len({task["ticker"] for task in group}),
                         "task_identities": [task["task_identity"] for task in sorted(group, key=lambda row: row["ticker"])]}
                        for (reason, reopen), group in sorted(deferred_groups.items())]
    authority_counts: dict[str, int] = {}
    warning_count = 0
    gap_count = 0
    for dossier in dossiers.values():
        tier = dossier["authority_evidence_tiers"]["fundamental_context"]
        authority_counts[tier] = authority_counts.get(tier, 0) + 1
        warning_count += len(dossier["warnings"])
        gap_count += len(dossier["data_gaps"])
    artifact = {
        "schema_version": "1.0.0",
        "contract_version": "human_research_review_pack/v1",
        "run_summary": {"research_session": product["daily_market_research"]["session"],
                        "source_artifact_identities": {"daily_product": product["artifact_identity"],
                                                       "prospective_snapshot": prospective["snapshot_id"],
                                                       "dossier_collection": "dossier_collection:" + _hash({ticker: dossier["dossier_identity"] for ticker, dossier in sorted(dossiers.items())}),
                                                       "task_collection": "task_collection:" + _hash({task_id: task["task_state_identity"] for task_id, task in sorted(tasks.items())})},
                        "eligible_research_cohort": len(dossiers), "owner_review_queue_count": len(review_entries),
                        "task_counts_by_status": status_counts, "evidence_authority_counts": authority_counts,
                        "data_gap_count": gap_count, "warning_count": warning_count,
                        "prospective_attribution_status": prospective["outcome_status"]},
        "owner_annotation_contract": {"fields": ["review_status", "owner_note", "follow_up_needed",
                                                   "evidence_requested", "research_priority_override"],
                                      "system_must_not_populate": True,
                                      "annotations_are_separate_from_immutable_research_state": True},
        "owner_review_queue": review_entries,
        "research_task_summary": {"open_actionable_count": status_counts.get("OPEN", 0),
                                  "resolved_count": sum(count for status, count in status_counts.items() if status.startswith("RESOLVED")),
                                  "superseded_count": status_counts.get("SUPERSEDED_BY_NEW_QUESTION", 0),
                                  "deferred_summary": deferred_summary,
                                  "machine_task_lineage": {task_id: {"ticker": task["ticker"], "status": task["task_status"],
                                                                     "dossier": task["current_dossier_identity"],
                                                                     "evidence_paths": task["evidence_paths"]}
                                                            for task_id, task in sorted(tasks.items())}},
        "authority_boundary": {"deterministic_state_controls_queue_and_status": True,
                               "ai_may_not_change_authority_or_resolve_task": True,
                               "recommendations_targets_probabilities": "NOT_EMITTED"},
        "verdict": "HUMAN_RESEARCH_REVIEW_PACK_V1_READY",
    }
    artifact["artifact_sha256"] = _hash(artifact)
    artifact["artifact_identity"] = "human_research_review_pack:" + artifact["artifact_sha256"]
    return artifact


def markdown(artifact: Mapping[str, Any]) -> str:
    summary = artifact["run_summary"]
    lines = ["# Human Research Review Pack", "", f"Session: {summary['research_session']}",
             f"Review queue: {summary['owner_review_queue_count']}",
             f"Tasks: {summary['task_counts_by_status']}", "", "## Owner review queue"]
    for entry in artifact["owner_review_queue"]:
        lines.extend([f"### {entry['ticker']}",
                      f"- Review reason: {', '.join(entry['review_reasons'])}",
                      "- FACT: " + "; ".join(f"{item['field']}={item['value']}" for item in entry["facts"]),
                      "- INFERENCE: " + "; ".join(f"{item['category']}={item['value']}" for item in entry["inferences"]),
                      "- DATA_GAP: " + "; ".join(item["claim"] for item in entry["data_gaps"]),
                      f"- QUESTION_TO_VERIFY: {entry['question_to_verify']['claim']}",
                      f"- Required evidence: {entry['expected_evidence_type']}",
                      f"- Task: {entry['unresolved_task']['task_identity']} ({entry['unresolved_task']['status']})",
                      "- Owner annotation: UNSET (human-only; not a recommendation)"])
    lines.extend(["", "## Deferred blockers (aggregated)"])
    for group in artifact["research_task_summary"]["deferred_summary"]:
        lines.append(f"- {group['deferred_reason']}: {group['affected_ticker_count']} tickers; reopen with {group['reopen_condition']}.")
    return "\n".join(lines) + "\n"
