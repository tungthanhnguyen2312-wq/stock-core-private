"""Append-only owner feedback overlay for immutable human research review packs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

WORKFLOW_STATES = {"UNREVIEWED", "REVIEWED", "NEEDS_FOLLOW_UP", "NEEDS_EVIDENCE", "DEFERRED_BY_OWNER", "NO_FURTHER_REVIEW"}
PRIORITY_OVERRIDES = {None, "HIGH", "NORMAL", "LOW"}


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def create_event(*, ticker: str, review_pack_identity: str, dossier_identity: str, research_session: str,
                 linked_task_identities: Iterable[str], created_at: str, review_status: str,
                 owner_note: str | None = None, follow_up_needed: bool | None = None,
                 evidence_requested: str | None = None, research_priority_override: str | None = None,
                 prior_annotation_identity: str | None = None) -> dict[str, Any]:
    """Construct a provenance-bound owner event; this creates no system research state."""
    if review_status not in WORKFLOW_STATES:
        raise ValueError("OWNER_WORKFLOW_STATUS_INVALID")
    if research_priority_override not in PRIORITY_OVERRIDES:
        raise ValueError("OWNER_PRIORITY_OVERRIDE_INVALID")
    event = {
        "schema_version": "1.0.0", "contract_version": "owner_research_journal/v1",
        "event_type": "OWNER_RESEARCH_ANNOTATION", "ticker": ticker,
        "target_review_pack_identity": review_pack_identity, "target_dossier_identity": dossier_identity,
        "linked_research_task_identities": sorted(linked_task_identities), "research_session": research_session,
        "created_at": created_at, "prior_annotation_identity": prior_annotation_identity,
        "owner_fields": {"review_status": review_status, "owner_note": owner_note,
                         "follow_up_needed": follow_up_needed, "evidence_requested": evidence_requested,
                         "research_priority_override": research_priority_override},
        "owner_feedback_is_not_evidence": True, "owner_feedback_may_not_change_task_status": True,
    }
    event["annotation_identity"] = "owner_research_annotation:" + _hash(event)
    return event


def write_immutable_event(path: Path, event: Mapping[str, Any]) -> None:
    payload = _canon(event) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise ValueError("IMMUTABLE_OWNER_ANNOTATION_CONTENT_CONFLICT")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def append_event(root: Path, event: Mapping[str, Any]) -> Path:
    """Append by stable identity, making resubmission idempotent rather than duplicate."""
    digest = event["annotation_identity"].split(":", 1)[1]
    path = root / f"{digest}.json"
    write_immutable_event(path, event)
    return path


def load_events(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(root.glob("*.json"))]


def _latest_events(events: Iterable[Mapping[str, Any]], pack_identity: str) -> dict[str, Mapping[str, Any]]:
    latest: dict[str, Mapping[str, Any]] = {}
    seen: set[str] = set()
    for event in sorted((event for event in events if event["target_review_pack_identity"] == pack_identity),
                        key=lambda item: (item["created_at"], item["annotation_identity"])):
        if event["annotation_identity"] in seen:
            continue
        seen.add(event["annotation_identity"])
        ticker = event["ticker"]
        prior = event["prior_annotation_identity"]
        if prior is not None and ticker in latest and prior != latest[ticker]["annotation_identity"]:
            raise ValueError("OWNER_ANNOTATION_PRIOR_LINEAGE_CONFLICT")
        if prior is not None and ticker not in latest:
            raise ValueError("OWNER_ANNOTATION_PRIOR_LINEAGE_MISSING")
        latest[ticker] = event
    return latest


def build(review_pack: Mapping[str, Any], events: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Project owner state separately from the system review pack; no source is modified."""
    pack_identity = review_pack["artifact_identity"]
    latest = _latest_events(events, pack_identity)
    entries = []
    for system_rank, review in enumerate(review_pack["owner_review_queue"], start=1):
        event = latest.get(review["ticker"])
        fields = event["owner_fields"] if event else {"review_status": "UNREVIEWED", "owner_note": None,
                                                        "follow_up_needed": None, "evidence_requested": None,
                                                        "research_priority_override": None}
        entries.append({
            "ticker": review["ticker"], "system_queue_rank": system_rank,
            "system_research": {"review_pack_identity": pack_identity, "dossier_identity": review["dossier_identity"],
                                "task_identity": review["unresolved_task"]["task_identity"],
                                "task_status": review["unresolved_task"]["status"],
                                "authority_tiers": review["authority_tiers"], "evidence_paths": review["unresolved_task"]["evidence_paths"],
                                "thesis_hash": review["thesis"]["hash"], "counter_thesis_hash": review["counter_thesis"]["hash"]},
            "owner_feedback": {"latest_annotation_identity": event["annotation_identity"] if event else None,
                               "prior_annotation_identity": event["prior_annotation_identity"] if event else None,
                               **fields},
            "owner_feedback_boundary": "WORKFLOW_ONLY_NOT_FACT_EVIDENCE_TASK_RESOLUTION_OR_RECOMMENDATION",
        })
    order = {"HIGH": 0, None: 1, "NORMAL": 2, "LOW": 3}
    owner_order = sorted(entries, key=lambda item: (order[item["owner_feedback"]["research_priority_override"]], item["system_queue_rank"]))
    status_counts: dict[str, int] = {}
    for entry in entries:
        status = entry["owner_feedback"]["review_status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    artifact = {
        "schema_version": "1.0.0", "contract_version": "owner_research_journal/v1",
        "target_review_pack_identity": pack_identity, "research_session": review_pack["run_summary"]["research_session"],
        "owner_overlay": owner_order,
        "summary": {"review_candidates": len(entries), "workflow_status_counts": status_counts,
                    "reviewed_count": sum(count for status, count in status_counts.items() if status != "UNREVIEWED"),
                    "unreviewed_count": status_counts.get("UNREVIEWED", 0),
                    "follow_up_count": sum(entry["owner_feedback"]["follow_up_needed"] is True for entry in entries),
                    "evidence_request_count": sum(bool(entry["owner_feedback"]["evidence_requested"]) for entry in entries),
                    "priority_override_count": sum(entry["owner_feedback"]["research_priority_override"] is not None for entry in entries)},
        "future_learning_contract": {"compare_separately": ["system_attention_at_t", "ai_queue_membership_at_t",
                                                                "owner_review_status_at_t", "owner_priority_override_at_t", "later_observed_outcome"],
                                     "performance_scoring": "NOT_IMPLEMENTED"},
        "authority_boundary": {"system_review_pack_immutable": True, "owner_feedback_is_not_evidence": True,
                               "owner_feedback_cannot_change_task_status_or_authority": True,
                               "recommendations_targets_probabilities": "NOT_EMITTED"},
        "verdict": "OWNER_RESEARCH_JOURNAL_V1_READY",
    }
    artifact["artifact_sha256"] = _hash(artifact)
    artifact["artifact_identity"] = "owner_research_journal:" + artifact["artifact_sha256"]
    return artifact


def markdown(artifact: Mapping[str, Any]) -> str:
    summary = artifact["summary"]
    lines = ["# Owner Research Journal", "", "## Owner workflow (separate from system research)",
             f"Reviewed: {summary['reviewed_count']}; unreviewed: {summary['unreviewed_count']}; "
             f"follow-up: {summary['follow_up_count']}; evidence requests: {summary['evidence_request_count']}", ""]
    for entry in artifact["owner_overlay"]:
        owner, system = entry["owner_feedback"], entry["system_research"]
        lines.append(f"- {entry['ticker']} — OWNER: {owner['review_status']} / priority={owner['research_priority_override'] or 'SYSTEM_ORDER'}; "
                     f"SYSTEM: task={system['task_status']} dossier={system['dossier_identity']}")
    return "\n".join(lines) + "\n"
