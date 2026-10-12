"""Evidence-bound issuer event context; events are facts, catalysts are linked interpretations."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def load_retained_events(root: Path) -> list[dict[str, Any]]:
    """Adapt the retained official ledger only; duplicate observations stay deduplicated there."""
    path = root / "operations-review/p1f-milestone-20260803/shadow-build-b/data/official-corporate-actions/event_ledger.json"
    ledger = json.loads(path.read_text(encoding="utf-8"))
    events = []
    for item in ledger["entries"]:
        if item.get("qualification_state") != "qualified":
            continue
        lifecycle = item.get("lifecycle_state")
        temporal = "COMPLETED" if lifecycle == "executed" else "STATUS_UNKNOWN"
        fact = {"ticker": item["ticker"], "event_type": "DIVIDEND_CORPORATE_ACTION",
                "source_event_type": item["event_type"], "temporal_state": temporal,
                "observed_date": item.get("announcement_date"), "published_date": item.get("announcement_date"),
                "effective_date": item.get("payment_or_execution_date"), "execution_or_trading_date": item.get("trading_date"),
                "unknown_dates": {"ex_date": item.get("ex_date") is None, "record_date": item.get("record_date") is None},
                "authority_tier": "OFFICIAL_QUALIFIED", "event_fact_classification": "FACT",
                "source_artifact": path.as_posix(), "source_ledger_event_id": item["event_id"],
                "source_document_ids": item["source_document_ids"], "source_content_hashes": item["source_content_hashes"],
                "source_urls": [doc["source_url"] for doc in item["source_documents"]],
                "qualification_reason": item["qualification_reason"], "warnings": item["warnings"],
                "event_history_status": "RETAINED_IMMUTABLE", "supersedes": item.get("supersedes"),
                "superseded_by": item.get("superseded_by")}
        fact["evidence_identity"] = "event_evidence:" + _hash(fact)
        events.append(fact)
    return sorted(events, key=lambda event: (event["ticker"], event["evidence_identity"]))


def build(product: Mapping[str, Any], dossiers: Mapping[str, Mapping[str, Any]],
          tasks: Mapping[str, Mapping[str, Any]], scenarios: Mapping[str, Any], review_pack: Mapping[str, Any],
          *, root: Path) -> dict[str, Any]:
    events = load_retained_events(root)
    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        by_ticker.setdefault(event["ticker"], []).append(event)
    scenario_by_ticker = {row["ticker"]: row for row in scenarios["scenarios"]}
    records = []
    for daily in sorted(product["stock_research"], key=lambda row: row["ticker"]):
        ticker = daily["ticker"]
        facts = by_ticker.get(ticker, [])
        interpretations = []
        for event in facts:
            # Completion is factual; research impact is deliberately withheld without a retained impact contract.
            interpretations.append({"classification": "INFERENCE", "status": "EVENT_WITH_UNKNOWN_RESEARCH_IMPACT",
                                    "event_evidence_identity": event["evidence_identity"], "research_direction": "AMBIGUOUS",
                                    "expected_mechanism": "UNKNOWN", "reason": "NO_RETAINED_EVENT_TO_FUNDAMENTAL_OR_RETURN_IMPACT_CONTRACT",
                                    "scenario_linkage": scenario_by_ticker.get(ticker, {}).get("scenario_content_identity"),
                                    "thesis_hash": dossiers[ticker]["thesis_hash"], "counter_thesis_hash": dossiers[ticker]["counter_thesis_hash"],
                                    "open_verification_question": "Verify whether a later retained issuer disclosure changes the event status or research relevance.",
                                    "invalidation_relevance": "STATUS_REQUIRES_LATER_EVIDENCE"})
        record = {"ticker": ticker, "research_session": daily["ai_ready_brief"]["facts"]["session"],
                  "daily_research_identity": product["artifact_identity"], "dossier_identity": dossiers[ticker]["dossier_identity"],
                  "task_identities": sorted(task["task_identity"] for task in tasks.values() if task["ticker"] == ticker),
                  "event_facts": facts, "catalyst_interpretations": interpretations,
                  "event_context_status": "EVIDENCE_BACKED_EVENT_AVAILABLE" if facts else "NO_EVIDENCE_BACKED_EVENT",
                  "catalyst_research_status": "ELIGIBLE" if facts else "UNAVAILABLE"}
        record["event_context_identity"] = "event_context_record:" + _hash(record)
        records.append(record)
    tax = Counter(event["event_type"] for event in events); authority = Counter(event["authority_tier"] for event in events)
    temporal = Counter(event["temporal_state"] for event in events)
    review_tickers = {row["ticker"] for row in review_pack["owner_review_queue"]}
    artifact = {"schema_version": "1.0.0", "contract_version": "catalyst_event_research_context/v1",
                "research_session": product["daily_market_research"]["session"], "cohort_scope": "EMPIRICAL_ACTIVE_SHADOW_ONLY",
                "source_artifact_identities": {"daily_product": product["artifact_identity"], "scenario": scenarios["artifact_identity"],
                                                 "official_event_ledger": "official_corporate_action_ledger:" + _hash(events)},
                "records": records, "event_facts": events,
                "coverage": {"cohort_records": len(records), "event_covered_records": sum(bool(row["event_facts"]) for row in records),
                             "no_event_evidence_records": sum(not row["event_facts"] for row in records), "event_count": len(events),
                             "taxonomy_counts": dict(tax), "authority_counts": dict(authority), "temporal_state_counts": dict(temporal),
                             "catalyst_research_eligible_count": sum(row["catalyst_research_status"] == "ELIGIBLE" for row in records),
                             "review_pack_event_covered_count": sum(bool(row["event_facts"]) for row in records if row["ticker"] in review_tickers)},
                "authority_boundary": {"event_is_fact_catalyst_is_inference": True, "no_ai_event_creation": True,
                                       "no_price_adjustment_authority": True, "no_recommendation_probability_target_or_return": True,
                                       "historical_pit_backtest": "NOT_PROMOTED"}, "verdict": "CATALYST_EVENT_RESEARCH_CONTEXT_V1_READY"}
    artifact["artifact_sha256"] = _hash(artifact); artifact["artifact_identity"] = "catalyst_event_research_context:" + artifact["artifact_sha256"]
    return artifact


def review_overlay(review_pack: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    records = {row["ticker"]: row for row in context["records"]}
    entries = [{"ticker": row["ticker"], "event_context_identity": records[row["ticker"]]["event_context_identity"],
                "event_context_status": records[row["ticker"]]["event_context_status"],
                "catalyst_research_status": records[row["ticker"]]["catalyst_research_status"],
                "events": records[row["ticker"]]["event_facts"], "interpretations": records[row["ticker"]]["catalyst_interpretations"]}
               for row in review_pack["owner_review_queue"]]
    result = {"schema_version": "1.0.0", "contract_version": "catalyst_event_review_pack_overlay/v1",
              "base_review_pack_identity": review_pack["artifact_identity"], "event_context_identity": context["artifact_identity"], "entries": entries}
    result["artifact_sha256"] = _hash(result); result["artifact_identity"] = "catalyst_event_review_pack_overlay:" + result["artifact_sha256"]
    return result
