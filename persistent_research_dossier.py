"""Immutable, evidence-aware research dossiers over the daily research product.

The dossier is a consumer of deterministic research records.  It records state and
change lineage; it neither decides authority nor evaluates a thesis as true or false.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from ai_research_analyst import stock_brief


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _dossier_state(record: Mapping[str, Any], brief: Mapping[str, Any], *, product_id: str,
                   analyst_id: str, queue_member: bool) -> dict[str, Any]:
    """Return the immutable state representation, excluding run-specific change output."""
    summary = record["research_summary"]
    questions = brief["questions_to_verify"]
    gaps = [item for item in brief["counter_thesis"] if item["type"] == "DATA_GAP"]
    state = {
        "schema_version": "1.0.0",
        "contract_version": "persistent_research_dossier/v1",
        "ticker": record["ticker"],
        "research_session": record["ai_ready_brief"]["facts"]["session"],
        "deterministic_research_state": {
            "facts": record["ai_ready_brief"]["facts"],
            "inferences": record["ai_ready_brief"]["deterministic_inferences"],
            "attention_descriptors": summary["attention_descriptors"],
            "fundamental_authority": summary["fundamental_authority"],
            "warnings": record["warnings"],
        },
        "authority_evidence_tiers": {
            "fundamental_context": brief["fundamental_context"]["authority"],
            "valuation_context": brief["valuation_context"]["authority"],
            "technical_context": "SHADOW_ONLY",
            "relative_volume_context": "DERIVED_PROXY",
        },
        "ai_queue_member": queue_member,
        "thesis": brief["bull_thesis"],
        "counter_thesis": brief["counter_thesis"],
        "thesis_hash": _hash(brief["bull_thesis"]),
        "counter_thesis_hash": _hash(brief["counter_thesis"]),
        "open_questions": questions,
        "data_gaps": gaps,
        "warnings": record["warnings"],
        "evidence_paths": {
            "source_artifacts": {"daily_product": product_id, "ai_analyst": analyst_id},
            "record_fields": [
                "stock_research.<ticker>.ai_ready_brief.facts",
                "stock_research.<ticker>.ai_ready_brief.deterministic_inferences",
                "stock_research.<ticker>.warnings",
                "stock_research.<ticker>.research_summary",
                "stock_briefs.<ticker>",
            ],
        },
    }
    state["dossier_identity"] = "persistent_research_dossier:" + _hash(state)
    return state


def _change_set(previous: Mapping[str, Any] | None, current: Mapping[str, Any]) -> dict[str, Any]:
    if previous is None:
        return {"categories": ["NEW_RESEARCH_STATE"], "changed_fields": ["initial_research_state"],
                "human_review_required": False}
    if previous["dossier_identity"] == current["dossier_identity"]:
        return {"categories": ["NO_MATERIAL_CHANGE"], "changed_fields": [], "human_review_required": False}

    checks = (
        ("DETERMINISTIC_EVIDENCE_CHANGED", "deterministic_research_state"),
        ("ATTENTION_STATE_CHANGED", "deterministic_research_state.attention_descriptors"),
        ("AUTHORITY_STATE_CHANGED", "authority_evidence_tiers"),
        ("DATA_GAP_CHANGED", "data_gaps"),
        ("THESIS_TEXT_CHANGED", "thesis_hash"),
        ("COUNTER_THESIS_CHANGED", "counter_thesis_hash"),
        ("OPEN_QUESTIONS_CHANGED", "open_questions"),
    )
    changed: list[str] = []
    for category, field in checks:
        root, *tail = field.split(".")
        old, new = previous[root], current[root]
        for part in tail:
            old, new = old[part], new[part]
        if old != new:
            changed.append(category)
    # Warnings are source-state facts, but are called out separately for human review.
    if previous["warnings"] != current["warnings"] and "DATA_GAP_CHANGED" not in changed:
        changed.append("DATA_GAP_CHANGED")
    if not changed:
        changed.append("DETERMINISTIC_EVIDENCE_CHANGED")
    changed.append("HUMAN_REVIEW_REQUIRED")
    return {"categories": changed, "changed_fields": [x.lower() for x in changed[:-1]],
            "human_review_required": True}


def build(product: Mapping[str, Any], analyst: Mapping[str, Any], *,
          previous_by_ticker: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Build a deterministic daily dossier view; prior states are read-only inputs."""
    previous_by_ticker = previous_by_ticker or {}
    briefs = {brief["ticker"]: brief for brief in analyst["stock_briefs"]}
    queue = {entry["ticker"] for entry in analyst["research_queue"]}
    dossiers: list[dict[str, Any]] = []
    for record in sorted(product["stock_research"], key=lambda row: row["ticker"]):
        ticker = record["ticker"]
        state = _dossier_state(record, briefs.get(ticker, stock_brief(record)),
                               product_id=product["artifact_identity"],
                               analyst_id=analyst["artifact_identity"], queue_member=ticker in queue)
        prior = previous_by_ticker.get(ticker)
        dossiers.append({
            "ticker": ticker,
            "prior_dossier_identity": prior["dossier_identity"] if prior else None,
            "current_dossier_identity": state["dossier_identity"],
            "dossier": state,
            "change_set": _change_set(prior, state),
        })

    follow_up = []
    for item in dossiers:
        state, change = item["dossier"], item["change_set"]
        reasons = []
        if state["ai_queue_member"]:
            reasons.append("PRESERVED_DETERMINISTIC_AI_RESEARCH_QUEUE_MEMBERSHIP")
        if change["human_review_required"]:
            reasons.extend(category for category in change["categories"] if category != "HUMAN_REVIEW_REQUIRED")
        if reasons:
            follow_up.append({
                "ticker": item["ticker"], "review_reasons": reasons,
                "changed_fields": change["changed_fields"],
                "evidence_paths": state["evidence_paths"],
                "not_a_recommendation": True,
            })
    follow_up.sort(key=lambda row: (not row["review_reasons"][0].startswith("PRESERVED"), row["ticker"]))
    category_counts: dict[str, int] = {}
    for item in dossiers:
        for category in item["change_set"]["categories"]:
            category_counts[category] = category_counts.get(category, 0) + 1
    artifact = {
        "schema_version": "1.0.0",
        "contract_version": "persistent_research_dossier/v1",
        "research_session": product["daily_market_research"]["session"],
        "source_artifact_identities": {"daily_product": product["artifact_identity"], "ai_analyst": analyst["artifact_identity"]},
        "dossiers": dossiers,
        "follow_up_queue": follow_up,
        "coverage": {"eligible_records": len(dossiers), "dossiers_dispositioned": len(dossiers),
                     "ai_queue_members": sum(item["dossier"]["ai_queue_member"] for item in dossiers),
                     "follow_up_items": len(follow_up), "change_category_counts": category_counts,
                     "open_question_count": sum(len(item["dossier"]["open_questions"]) for item in dossiers),
                     "data_gap_count": sum(len(item["dossier"]["data_gaps"]) for item in dossiers)},
        "authority_boundary": {
            "ai_cannot_rewrite_historical_dossier": True,
            "ai_cannot_decide_authority_or_thesis_truth": True,
            "recommendations_targets_probabilities": "NOT_EMITTED",
            "historical_pit_backtest": "NOT_PROMOTED",
        },
        "verdict": "PERSISTENT_RESEARCH_DOSSIER_V1_READY",
    }
    artifact["artifact_sha256"] = _hash(artifact)
    artifact["artifact_identity"] = "persistent_research_dossier_run:" + artifact["artifact_sha256"]
    return artifact


def write_immutable(path: Path, value: Mapping[str, Any]) -> None:
    payload = _canon(value) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise ValueError("IMMUTABLE_DOSSIER_CONTENT_CONFLICT")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def load_latest_versions(root: Path) -> dict[str, dict[str, Any]]:
    """Read newest state by session/identity without mutating any retained version."""
    latest: dict[str, dict[str, Any]] = {}
    versions = root / "versions"
    if not versions.exists():
        return latest
    for path in sorted(versions.glob("*/*.json")):
        state = json.loads(path.read_text(encoding="utf-8"))
        ticker = state["ticker"]
        if ticker not in latest or (state["research_session"], state["dossier_identity"]) > (
                latest[ticker]["research_session"], latest[ticker]["dossier_identity"]):
            latest[ticker] = state
    return latest


def write_new_versions(root: Path, artifact: Mapping[str, Any]) -> int:
    written = 0
    for entry in artifact["dossiers"]:
        state = entry["dossier"]
        digest = state["dossier_identity"].split(":", 1)[1]
        path = root / "versions" / state["ticker"] / f"{digest}.json"
        if not path.exists():
            written += 1
        write_immutable(path, state)
    return written


def markdown(artifact: Mapping[str, Any]) -> str:
    coverage = artifact["coverage"]
    lines = ["# Persistent Research Follow-up Queue", "", f"Session: {artifact['research_session']}",
             f"Dossiers: {coverage['dossiers_dispositioned']} / {coverage['eligible_records']}", "",
             "## Human follow-up (not a recommendation)"]
    for item in artifact["follow_up_queue"][:25]:
        lines.append(f"- {item['ticker']}: {', '.join(item['review_reasons'])}")
    return "\n".join(lines) + "\n"
