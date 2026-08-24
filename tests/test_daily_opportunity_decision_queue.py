import json
from pathlib import Path

import pytest

from daily_opportunity_decision_queue import LANES, build, prospective_context, replay

ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = ROOT / "operations-review"


def _row(**overrides):
    row = {
        "ticker": "AAA", "official_current_universe_status": "OFFICIAL_CURRENT_EXCHANGE_SECURITY",
        "eligible_strategies": ["EVENT_DRIVEN"], "lane_priority": {"EVENT_DRIVEN": "PRIORITY_NOW"},
        "tactical_state": "DOWNTREND", "entry_action": "AVOID", "scenario_status": "SCENARIO_READY",
        "fundamental_context_status": "PROVIDER_RESEARCH", "event_context_status": "AVAILABLE",
        "liquidity_context_status": "ELIGIBLE", "data_quality_status": "SUFFICIENT",
        "priority_tier": "PRIORITY_NOW", "priority_reasons": ["EVENT_DRIVEN=PRIORITY_NOW"], "blocking_reasons": [],
        "invalidation_or_context_warnings": [], "source_input_identities": {"tactical": "t:1"},
        "is_actionable": False, "position_sizing_status": "NOT_EVALUATED", "is_full_position_ready": False,
    }
    row.update(overrides); row["content_identity"] = "current_opportunity_record:" + row["ticker"]
    return row


def _opportunity(records):
    artifact = {"contract_version": "current_opportunity_prioritization/v1", "research_session": "2099-01-05",
                "artifact_identity": "current_opportunity_prioritization:fixture",
                "coverage": {"current_official_universe": len(records)}, "records": records}
    return artifact


def _triage(review_tickers):
    return {"artifact_identity": "full_universe_entry_candidate_triage:fixture",
            "cohort_definitions": {"TACTICAL_HIGH_PRIORITY_REVIEW": "fixture policy text"},
            "high_priority_review_eligible_records": [{"ticker": ticker} for ticker in review_tickers]}


def test_priority_now_is_not_entry_ready_by_construction():
    """A PRIORITY_NOW record whose entry_action is AVOID must surface as research-priority
    but explicitly not entry-relevant -- the exact scenario the milestone exists to catch."""
    records = {"AAA": _row(ticker="AAA")}
    queue = build(opportunity=_opportunity(records), triage=_triage([]))
    replay(queue)
    row = queue["records"]["AAA"]
    assert row["research_priority_tier"] == "PRIORITY_NOW"
    assert row["entry_action"] == "AVOID"
    assert row["entry_relevant"] is False
    assert queue["entry_relevant_summary"]["PRIORITY_NOW_TOTAL"] == 1
    assert queue["entry_relevant_summary"]["PRIORITY_NOW_ENTRY_RELEVANT"] == 0
    assert queue["entry_relevant_summary"]["PRIORITY_NOW_NOT_ENTRY_RELEVANT"] == 1


def test_lane_queue_orders_by_tier_then_ticker_not_a_score():
    records = {
        "ZZZ": _row(ticker="ZZZ", eligible_strategies=["BREAKOUT"], lane_priority={"BREAKOUT": "PRIORITY_NOW"}, tactical_state="BREAKOUT_READY", entry_action="BUY_ON_CONFIRMATION"),
        "AAA": _row(ticker="AAA", eligible_strategies=["BREAKOUT"], lane_priority={"BREAKOUT": "PRIORITY_NOW"}, tactical_state="BREAKOUT_READY", entry_action="BUY_ON_CONFIRMATION"),
        "MMM": _row(ticker="MMM", eligible_strategies=["BREAKOUT"], lane_priority={"BREAKOUT": "SETUP_WATCH"}, tactical_state="BREAKOUT_READY", entry_action="BUY_ON_CONFIRMATION"),
    }
    queue = build(opportunity=_opportunity(records), triage=_triage([]))
    tickers = [row["ticker"] for row in queue["lane_queues"]["BREAKOUT"]["tickers"]]
    assert tickers == ["AAA", "ZZZ", "MMM"]  # PRIORITY_NOW tier first (ticker-ascending), then SETUP_WATCH
    assert queue["lane_queues"]["BREAKOUT"]["ordering"] == "LANE_TIER_THEN_TICKER_ASCENDING_NOT_A_SCORE"


def test_multi_strategy_preserved_across_lane_queues():
    records = {"MSX": _row(ticker="MSX", eligible_strategies=["TREND_MOMENTUM", "EVENT_DRIVEN"],
                            lane_priority={"TREND_MOMENTUM": "PRIORITY_NOW", "EVENT_DRIVEN": "PRIORITY_NOW"},
                            tactical_state="UPTREND_CONFIRMED", entry_action="WAIT")}
    queue = build(opportunity=_opportunity(records), triage=_triage([]))
    assert queue["multi_strategy"]["tickers"] == ["MSX"]
    assert any(row["ticker"] == "MSX" for row in queue["lane_queues"]["TREND_MOMENTUM"]["tickers"])
    assert any(row["ticker"] == "MSX" for row in queue["lane_queues"]["EVENT_DRIVEN"]["tickers"])


def test_value_lane_never_populated_by_shadow_valuation():
    records = {"AAA": _row(ticker="AAA", eligible_strategies=[], lane_priority={}, priority_tier="MONITOR", entry_action="WAIT")}
    queue = build(opportunity=_opportunity(records), triage=_triage([]))
    assert queue["lane_queues"]["VALUE"]["count"] == 0
    assert queue["lane_queues"]["VALUE"]["tickers"] == []


def test_legacy_comparison_flags_newly_surfaced_and_downgraded_with_deterministic_reasons():
    records = {
        "NEW1": _row(ticker="NEW1", eligible_strategies=["EVENT_DRIVEN"], lane_priority={"EVENT_DRIVEN": "PRIORITY_NOW"}, tactical_state="SIDEWAYS_NEUTRAL", entry_action="WAIT", scenario_status="SCENARIO_READY"),
        "GONE": _row(ticker="GONE", eligible_strategies=["BASE_ACCUMULATION"], lane_priority={"BASE_ACCUMULATION": "SETUP_WATCH"}, priority_tier="SETUP_WATCH", tactical_state="BASE_BUILDING", entry_action="ACCUMULATE_IN_BASE", scenario_status="SCENARIO_PARTIAL"),
        "STILL": _row(ticker="STILL", eligible_strategies=["BREAKOUT"], lane_priority={"BREAKOUT": "PRIORITY_NOW"}, tactical_state="BREAKOUT_READY", entry_action="BUY_ON_CONFIRMATION"),
    }
    queue = build(opportunity=_opportunity(records), triage=_triage(["GONE", "STILL"]))
    comparison = queue["legacy_comparison"]
    assert comparison["legacy_high_priority_count"] == 2
    assert comparison["agreement"] == ["STILL"]
    newly = {row["ticker"]: row["reason_categories"] for row in comparison["newly_surfaced"]}
    downgraded = {row["ticker"]: row["reason_categories"] for row in comparison["downgraded"]}
    assert set(newly) == {"NEW1"}
    assert "NEW_STRATEGY_LANE_CONTEXT" in newly["NEW1"] and "CURRENT_EVENT_ELIGIBILITY" in newly["NEW1"] and "ENTRY_NOT_READY" in newly["NEW1"]
    assert set(downgraded) == {"GONE"}
    assert "SCENARIO_COMPLETENESS" in downgraded["GONE"]
    assert set(comparison["reason_category_vocabulary"]) >= {"NEW_STRATEGY_LANE_CONTEXT", "CURRENT_EVENT_ELIGIBILITY", "TACTICAL_STATE_DIFFERENCE", "SCENARIO_COMPLETENESS", "DATA_QUALITY", "ENTRY_NOT_READY", "MULTI_STRATEGY_CONTEXT"}


def test_primary_review_candidates_reuses_existing_triage_policy_verbatim():
    records = {"AAA": _row(ticker="AAA")}
    queue = build(opportunity=_opportunity(records), triage=_triage(["AAA"]))
    review = queue["primary_review_candidates"]
    assert review["policy_kind"] == "EXISTING_EVIDENCE_GATED_ELIGIBILITY_NOT_A_FIXED_CAP"
    assert review["tickers"] == ["AAA"] and review["count"] == 1
    assert review["policy_definition"] == "fixture policy text"


def test_build_is_deterministic():
    records = {"AAA": _row(ticker="AAA")}
    first = build(opportunity=_opportunity(records), triage=_triage([]))
    second = build(opportunity=_opportunity(records), triage=_triage([]))
    assert first["artifact_identity"] == second["artifact_identity"]


def test_no_forbidden_authority_fields_anywhere_in_records():
    records = {"AAA": _row(ticker="AAA")}
    queue = build(opportunity=_opportunity(records), triage=_triage([]))
    replay(queue)  # replay() itself fails closed on global_score/target_price/probability keys
    blob = json.dumps(queue)
    # Quoted on both sides so this checks for an actual JSON key/value, not a
    # substring of the long compound authority_boundary flag names below.
    for forbidden in ('"global_score"', '"target_price"', '"expected_return"', '"position_size"'):
        assert forbidden not in blob


def test_denominator_mismatch_fails_closed():
    opportunity = _opportunity({"AAA": _row(ticker="AAA")})
    opportunity["coverage"]["current_official_universe"] = 2
    with pytest.raises(ValueError, match="OPPORTUNITY_COVERAGE_DENOMINATOR_MISMATCH"):
        build(opportunity=opportunity, triage=_triage([]))


def test_prospective_context_freezes_full_universe_not_only_shortlist():
    records = {"AAA": _row(ticker="AAA"), "BBB": _row(ticker="BBB", priority_tier="MONITOR", eligible_strategies=[], lane_priority={}, entry_action="WAIT")}
    opportunity = _opportunity(records)
    queue = build(opportunity=opportunity, triage=_triage(["AAA"]))
    snapshot = prospective_context(opportunity, queue)
    assert snapshot["cohort_count"] == 2  # full universe, not just the 1-ticker review shortlist
    assert snapshot["future_outcomes"] == "PENDING_FUTURE_OBSERVATION"
    rows = {row["ticker"]: row for row in snapshot["frozen_records"]}
    assert rows["AAA"]["is_primary_review_candidate"] is True
    assert rows["BBB"]["is_primary_review_candidate"] is False
    assert "outcome" not in json.dumps(rows["AAA"]).lower().replace("future_outcomes", "").replace("pending_future_observation", "")


def test_prospective_context_is_deterministic_and_lineage_checked():
    records = {"AAA": _row(ticker="AAA")}
    opportunity = _opportunity(records)
    queue = build(opportunity=opportunity, triage=_triage([]))
    first = prospective_context(opportunity, queue); second = prospective_context(opportunity, queue)
    assert first["snapshot_id"] == second["snapshot_id"]
    other_opportunity = _opportunity(records); other_opportunity["artifact_identity"] = "current_opportunity_prioritization:different"
    with pytest.raises(ValueError, match="OPPORTUNITY_DECISION_QUEUE_LINEAGE_MISMATCH"):
        prospective_context(other_opportunity, queue)


def test_all_seven_lanes_present_even_when_empty():
    records = {"AAA": _row(ticker="AAA", eligible_strategies=[], lane_priority={}, priority_tier="MONITOR", entry_action="WAIT")}
    queue = build(opportunity=_opportunity(records), triage=_triage([]))
    assert set(queue["lane_queues"]) == set(LANES)
    for lane in LANES:
        assert queue["lane_queues"][lane]["count"] == 0


def test_real_retained_universe_matches_milestone_ground_truth():
    """Integration proof against the actual retained 1,507-record artifact (not a fixture)."""
    opportunity = json.loads((OPERATIONS / "current-opportunity-prioritization-v1-20260824/current_opportunity_prioritization_artifact.json").read_text(encoding="utf-8"))
    triage = json.loads((OPERATIONS / "full-universe-entry-candidate-triage-20260824/full_universe_entry_candidate_triage_20260824.json").read_text(encoding="utf-8"))
    queue = build(opportunity=opportunity, triage=triage)
    replay(queue)
    summary = queue["entry_relevant_summary"]
    assert summary["PRIORITY_NOW_TOTAL"] == 190
    assert summary["PRIORITY_NOW_ENTRY_RELEVANT"] == 67
    assert summary["PRIORITY_NOW_NOT_ENTRY_RELEVANT"] == 123
    assert summary["SETUP_WATCH_ENTRY_RELEVANT"] == 23
    comparison = queue["legacy_comparison"]
    assert comparison["legacy_high_priority_count"] == 47
    assert comparison["agreement_count"] == 30
    assert len(comparison["newly_surfaced"]) == 160
    assert len(comparison["downgraded"]) == 17
    assert all(row["reason_categories"] for row in comparison["newly_surfaced"] + comparison["downgraded"])
    assert queue["lane_queues"]["VALUE"]["count"] == 0
    assert queue["multi_strategy"]["count"] == 33
    assert queue["primary_review_candidates"]["count"] == 47
    assert queue["primary_review_candidates"]["tickers"] == sorted(queue["primary_review_candidates"]["tickers"])
    snapshot = prospective_context(opportunity, queue)
    assert snapshot["cohort_count"] == 1507
    assert sum(row["is_primary_review_candidate"] for row in snapshot["frozen_records"]) == 47
