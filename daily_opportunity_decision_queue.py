"""Presentation/consumption layer over current_opportunity_prioritization/v1.

Computes no new eligibility, tier, or lane -- it groups, orders, and bounds the
already-computed per-ticker records for daily human/product consumption. Lane
ordering is tier (reusing current_opportunity_prioritization.TIERS) then ticker
ascending; this is an evidence-availability ordering, never a magnitude score.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Mapping

from current_opportunity_prioritization import TIERS
from field_temporal_contract import stable_id

CONTRACT_VERSION = "daily_opportunity_decision_queue/v1"
LANES = ("TREND_MOMENTUM", "BREAKOUT", "EARLY_REVERSAL", "BASE_ACCUMULATION", "FUNDAMENTAL_IMPROVEMENT", "EVENT_DRIVEN", "VALUE")
ENTRY_RELEVANT_ACTIONS = frozenset({"BUY_ON_CONFIRMATION", "EARLY_ENTRY", "ACCUMULATE_IN_BASE"})
# The only three (lane, tactical entry_state) pairs the pre-existing triage
# high-priority-review cohort ever considered; verified 1:1 (zero mismatches
# across the full 1,507-record universe) before this module was written.
LEGACY_REVIEWED_LANES = frozenset({"EARLY_REVERSAL", "BASE_ACCUMULATION", "BREAKOUT"})
LEGACY_REVIEWED_TACTICAL_STATES = frozenset({"EARLY_REVERSAL_CANDIDATE", "BASE_BUILDING", "BREAKOUT_READY"})
REASON_CATEGORY_VOCABULARY = ("NEW_STRATEGY_LANE_CONTEXT", "CURRENT_EVENT_ELIGIBILITY", "TACTICAL_STATE_DIFFERENCE", "SCENARIO_COMPLETENESS", "DATA_QUALITY", "ENTRY_NOT_READY", "MULTI_STRATEGY_CONTEXT")


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact)); payload.pop("artifact_sha256", None); payload.pop("artifact_identity", None)
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": "daily_opportunity_decision_queue:" + digest}


def _entry_relevant(entry_action: str | None) -> bool:
    return entry_action in ENTRY_RELEVANT_ACTIONS


def _queue_record(ticker: str, row: Mapping[str, Any]) -> dict[str, Any]:
    record = {
        "ticker": ticker,
        "research_priority_tier": row["priority_tier"],
        "eligible_strategies": list(row["eligible_strategies"]),
        "lane_specific_priority": dict(row["lane_priority"]),
        "tactical_state": row["tactical_state"],
        "entry_action": row["entry_action"],
        "entry_relevant": _entry_relevant(row["entry_action"]),
        "scenario_status": row["scenario_status"],
        "event_context_status": row["event_context_status"],
        "fundamental_context_status": row["fundamental_context_status"],
        "data_quality_status": row["data_quality_status"],
        "priority_reasons": list(row["priority_reasons"]),
        "blocking_reasons": list(row["blocking_reasons"]),
        "invalidation_or_context_warnings": list(row["invalidation_or_context_warnings"]),
        "opportunity_record_content_identity": row["content_identity"],
        "source_input_identities": dict(row["source_input_identities"]),
        "authority_note": "research_priority_tier is a research-lane priority signal; it is not entry timing (see entry_action/entry_relevant), not is_full_position_ready, and not position_sizing_status.",
        "is_actionable": False,
    }
    record["content_identity"] = "daily_opportunity_decision_record:" + stable_id(record)
    return record


def _lane_queue(lane: str, records: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    members = [record for record in records.values() if lane in record["lane_specific_priority"]]
    ordered = sorted(members, key=lambda record: (TIERS.index(record["lane_specific_priority"][lane]), record["ticker"]))
    rows = [{"ticker": record["ticker"], "lane_priority": record["lane_specific_priority"][lane], "research_priority_tier": record["research_priority_tier"], "entry_relevant": record["entry_relevant"]} for record in ordered]
    counts = Counter(row["lane_priority"] for row in rows)
    return {"lane": lane, "ordering": "LANE_TIER_THEN_TICKER_ASCENDING_NOT_A_SCORE", "tier_counts": {tier: counts.get(tier, 0) for tier in TIERS if tier != "EXCLUDED"}, "count": len(rows), "tickers": rows}


def _reason_categories_newly_surfaced(record: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if any(lane not in LEGACY_REVIEWED_LANES for lane in record["eligible_strategies"]):
        reasons.append("NEW_STRATEGY_LANE_CONTEXT")
    if "EVENT_DRIVEN" in record["eligible_strategies"]:
        reasons.append("CURRENT_EVENT_ELIGIBILITY")
    if record["tactical_state"] in LEGACY_REVIEWED_TACTICAL_STATES:
        reasons.append("TACTICAL_STATE_DIFFERENCE")
    if record["scenario_status"] == "SCENARIO_READY":
        reasons.append("SCENARIO_COMPLETENESS")
    if len(record["eligible_strategies"]) > 1:
        reasons.append("MULTI_STRATEGY_CONTEXT")
    if not record["entry_relevant"]:
        reasons.append("ENTRY_NOT_READY")
    return reasons or ["DATA_QUALITY"]


def _reason_categories_downgraded(record: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if record["research_priority_tier"] == "DATA_LIMITED" or record["data_quality_status"] in {"INSUFFICIENT", None}:
        reasons.append("DATA_QUALITY")
    if record["scenario_status"] in {"SCENARIO_PARTIAL", "SCENARIO_INSUFFICIENT_DATA"}:
        reasons.append("SCENARIO_COMPLETENESS")
    if record["tactical_state"] not in LEGACY_REVIEWED_TACTICAL_STATES:
        reasons.append("TACTICAL_STATE_DIFFERENCE")
    if not record["entry_relevant"]:
        reasons.append("ENTRY_NOT_READY")
    if len(record["eligible_strategies"]) > 1:
        reasons.append("MULTI_STRATEGY_CONTEXT")
    return reasons or ["DATA_QUALITY"]


def legacy_comparison(records: Mapping[str, dict[str, Any]], triage: Mapping[str, Any]) -> dict[str, Any]:
    legacy = set(triage.get("high_priority_review_eligible_records") and [row["ticker"] for row in triage["high_priority_review_eligible_records"]] or [])
    now = {ticker for ticker, record in records.items() if record["research_priority_tier"] == "PRIORITY_NOW"}
    now_entry_relevant = {ticker for ticker in now if records[ticker]["entry_relevant"]}
    newly_surfaced = sorted(now - legacy); downgraded = sorted(legacy - now)
    return {
        "legacy_high_priority_count": len(legacy),
        "new_research_priority_now_count": len(now),
        "new_entry_relevant_priority_now_count": len(now_entry_relevant),
        "agreement": sorted(legacy & now),
        "agreement_count": len(legacy & now),
        "newly_surfaced": [{"ticker": ticker, "reason_categories": _reason_categories_newly_surfaced(records[ticker])} for ticker in newly_surfaced],
        "downgraded": [{"ticker": ticker, "reason_categories": _reason_categories_downgraded(records[ticker])} for ticker in downgraded],
        "reason_category_vocabulary": list(REASON_CATEGORY_VOCABULARY),
        "compatibility": "READ_ONLY_TICKER_COMPARISON_NO_FROZEN_TRIAGE_OUTPUT_MUTATION",
        "source_artifact_identity": triage.get("artifact_identity"),
    }


def build(*, opportunity: Mapping[str, Any], triage: Mapping[str, Any]) -> dict[str, Any]:
    if opportunity.get("coverage", {}).get("current_official_universe") != len(opportunity.get("records", {})):
        raise ValueError("OPPORTUNITY_COVERAGE_DENOMINATOR_MISMATCH")
    records = {ticker: _queue_record(ticker, row) for ticker, row in sorted(opportunity["records"].items())}
    lane_queues = {lane: _lane_queue(lane, records) for lane in LANES}
    priority_now = sorted(ticker for ticker, record in records.items() if record["research_priority_tier"] == "PRIORITY_NOW")
    setup_watch = sorted(ticker for ticker, record in records.items() if record["research_priority_tier"] == "SETUP_WATCH")
    priority_now_entry_relevant = [ticker for ticker in priority_now if records[ticker]["entry_relevant"]]
    setup_watch_entry_relevant = [ticker for ticker in setup_watch if records[ticker]["entry_relevant"]]
    review_rows = triage.get("high_priority_review_eligible_records") or []
    primary_review_candidates = {
        "source": "full_universe_entry_candidate_triage.TACTICAL_HIGH_PRIORITY_REVIEW",
        "policy_kind": "EXISTING_EVIDENCE_GATED_ELIGIBILITY_NOT_A_FIXED_CAP",
        "policy_definition": (triage.get("cohort_definitions") or {}).get("TACTICAL_HIGH_PRIORITY_REVIEW"),
        "triage_artifact_identity": triage.get("artifact_identity"),
        "tickers": sorted(row["ticker"] for row in review_rows if isinstance(row, Mapping)),
        "count": len(review_rows),
    }
    comparison = legacy_comparison(records, triage)
    multi_strategy = sorted(ticker for ticker, record in records.items() if len(record["eligible_strategies"]) > 1)
    artifact = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "research_session": opportunity.get("research_session"),
        "source_artifact_identities": {"opportunity": opportunity.get("artifact_identity"), "triage": triage.get("artifact_identity")},
        "records": records,
        "lane_queues": lane_queues,
        "entry_relevant_summary": {
            "PRIORITY_NOW_TOTAL": len(priority_now),
            "PRIORITY_NOW_ENTRY_RELEVANT": len(priority_now_entry_relevant),
            "PRIORITY_NOW_NOT_ENTRY_RELEVANT": len(priority_now) - len(priority_now_entry_relevant),
            "SETUP_WATCH_TOTAL": len(setup_watch),
            "SETUP_WATCH_ENTRY_RELEVANT": len(setup_watch_entry_relevant),
        },
        "full_priority_now": priority_now,
        "primary_review_candidates": primary_review_candidates,
        "legacy_comparison": comparison,
        "multi_strategy": {"count": len(multi_strategy), "tickers": multi_strategy},
        "authority_boundary": {
            "research_priority_is_not_trade_readiness": True,
            "priority_now_is_not_buy_now": True,
            "priority_now_is_not_full_position_ready": True,
            "priority_now_is_not_sizing_ready": True,
            "no_global_score": True,
            "no_position_size_liquidity_capacity_leverage_execution_target_price_expected_return_probability_or_recommendation": True,
            "value_strategy_strictly_blocked_no_shadow_valuation_substitute": True,
        },
        "is_actionable": False,
    }
    artifact.update(content_identity(artifact))
    return artifact


def replay(artifact: Mapping[str, Any]) -> None:
    if content_identity(artifact)["artifact_sha256"] != artifact.get("artifact_sha256"):
        raise ValueError("IDENTITY_MISMATCH")
    if any("global_score" in record or "target_price" in record or "probability" in record for record in artifact.get("records", {}).values()):
        raise ValueError("FORBIDDEN_AUTHORITY_FIELD_PRESENT")


def prospective_context(opportunity: Mapping[str, Any], decision_queue: Mapping[str, Any]) -> dict[str, Any]:
    """Additive identity freeze sealed beside (never inside/replacing) the current-decision snapshot.

    Mirrors market_wide_current_corporate_intelligence.prospective_context and
    polymorphic_current_strategy_classification.prospective_context: one small
    per-ticker row set, no outcome, sealed for later strictly-future attribution.
    """
    if decision_queue.get("source_artifact_identities", {}).get("opportunity") != opportunity.get("artifact_identity"):
        raise ValueError("OPPORTUNITY_DECISION_QUEUE_LINEAGE_MISMATCH")
    review_tickers = set(decision_queue["primary_review_candidates"]["tickers"])
    rows = []
    for ticker, row in sorted(opportunity["records"].items()):
        queue_record = decision_queue["records"][ticker]
        rows.append({
            "ticker": ticker,
            "official_universe_identity": row["official_current_universe_status"],
            "research_priority_tier": row["priority_tier"],
            "eligible_strategies": list(row["eligible_strategies"]),
            "lane_specific_priority": dict(row["lane_priority"]),
            "tactical_state": row["tactical_state"],
            "entry_action": row["entry_action"],
            "entry_relevant": queue_record["entry_relevant"],
            "scenario_status": row["scenario_status"],
            "event_context_status": row["event_context_status"],
            "fundamental_context_status": row["fundamental_context_status"],
            "data_quality_status": row["data_quality_status"],
            "is_primary_review_candidate": ticker in review_tickers,
            "opportunity_record_content_identity": row["content_identity"],
            "decision_queue_record_content_identity": queue_record["content_identity"],
        })
    payload = {
        "schema_version": "1.0.0",
        "contract_version": "prospective_research_learning/opportunity_decision_context/v1",
        "research_session": opportunity.get("research_session"),
        "source_artifact_identities": {"opportunity": opportunity.get("artifact_identity"), "decision_queue": decision_queue.get("artifact_identity")},
        "frozen_records": rows,
        "cohort_count": len(rows),
        "future_outcomes": "PENDING_FUTURE_OBSERVATION",
        "authority_boundary": "IDENTITY_FREEZE_ONLY_NOT_OUTCOME_OR_RANKING_OR_RECOMMENDATION_OR_SIZING",
    }
    payload["snapshot_id"] = "prospective_research_snapshot:" + stable_id(payload)
    return payload
