"""Acceptance for the historical temporal research panel.

Fixtures describe situations. Issuer symbols are cohort members, not branches.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import historical_temporal_research_panel as panel


def _observation(**overrides):
    base = {
        "session": "2026-09-04",
        "ticker": "HPG",
        "tactical_state": "BASE_BUILDING",
        "source_identity": "opportunity:test",
        "semantic_tier": panel.RECONSTRUCTED_RESEARCH,
        "market": {"market_regime": "MARKET_BREADTH_MIXED", "breadth": {"advancing": 10, "declining": 20}},
    }
    base.update(overrides)
    return base


def test_rebuild_is_deterministic_and_ordered():
    observations = [
        _observation(session="2026-09-08", ticker="SSI"),
        _observation(session="2026-09-04", ticker="HPG"),
        _observation(session="2026-09-04", ticker="AAA", tactical_state="BREAKOUT_READY"),
    ]
    first = panel.build_panel(observations)
    second = panel.build_panel(list(reversed(observations)))
    assert first["panel_identity"] == second["panel_identity"]
    assert [row["ticker"] for row in first["rows"]] == ["AAA", "HPG", "SSI"]
    assert first["authority_promoted"] is False
    assert first["raw_as_traded_promoted"] is False
    assert first["pit_backtest_authority"] is False
    assert first["storage_choice"] == panel.STORAGE_CHOICE
    changed = panel.build_panel([_observation(market={"market_regime": "OTHER", "breadth": {"advancing": 10, "declining": 20}})])
    assert changed["panel_identity"] != panel.build_panel([_observation()])["panel_identity"]


def test_unqualified_pit_request_stays_unknown_and_not_raw():
    row = panel.build_row(_observation(semantic_tier=panel.PIT_AUTHORITATIVE, qualification={"raw_as_traded": True}))
    assert row["semantic_tier"] == panel.UNKNOWN
    assert row["tier_reason"] == "PIT_QUALIFICATION_ABSENT"
    assert row["raw_as_traded"] is False
    assert row["authority_promoted"] is False


def test_adjusted_history_cannot_become_pit_or_raw():
    row = panel.build_row(_observation(
        semantic_tier=panel.PIT_AUTHORITATIVE,
        qualification={
            "qualification_id": "q1",
            "knowledge_date": "2026-09-01",
            "event_date": "2026-08-01",
            "adjusted_retrospective": True,
            "raw_as_traded": True,
        },
    ))
    assert row["semantic_tier"] == panel.RECONSTRUCTED_RESEARCH
    assert row["tier_reason"] == "RETROSPECTIVE_ADJUSTMENT_NOT_PIT"
    assert row["raw_as_traded"] is False


def test_separated_pit_qualification_is_preserved():
    row = panel.build_row(_observation(
        semantic_tier=panel.PIT_AUTHORITATIVE,
        qualification={
            "qualification_id": "q1",
            "knowledge_date": "2026-09-04",
            "event_date": "2026-08-15",
        },
    ))
    assert row["semantic_tier"] == panel.PIT_AUTHORITATIVE
    assert row["tier_reason"] == "PIT_QUALIFICATION_PRESENT"
    assert row["fields"]["source_knowledge_date"]["status"] == "MISSING"
    assert row["raw_as_traded"] is False


def test_equal_clock_without_intent_does_not_collapse_knowledge_into_event():
    classified = panel.classify_tier(panel.PIT_AUTHORITATIVE, {
        "qualification_id": "q1",
        "knowledge_date": "2026-09-04",
        "event_date": "2026-09-04",
    })
    assert classified["tier"] == panel.UNKNOWN
    assert classified["reason"] == "KNOWLEDGE_AND_EVENT_TIME_NOT_SEPARATED"


def test_corporate_action_closes_only_the_affected_calculation():
    row = panel.build_row(_observation(corporate_action_boundary={
        "affected_fields": ["returns", "valuation"],
        "reason": "SHARE_ISSUANCE_BOUNDARY",
        "drop_ticker": True,
    }))
    assert row["ticker"] == "HPG"
    assert row["fields"]["returns"]["status"] == "INCOMPARABLE"
    assert row["fields"]["valuation"]["status"] == "INCOMPARABLE"
    assert row["fields"]["ohlcv"]["status"] == "MISSING"
    assert row["fields"]["tactical_state"]["status"] == "PRESENT"
    assert row["fields"]["market_regime"]["value"] == "MARKET_BREADTH_MIXED"
    assert any(item["status"] == "DROP_REFUSED" for item in row["calculation_closures"])


def test_outcome_requires_an_implemented_horizon_and_a_population():
    absent = panel.build_row(_observation())
    assert absent["fields"]["outcome"]["status"] == "NOT_OBSERVED"
    refused = panel.build_row(_observation(outcome={"horizon_sessions": 60, "observed_qualified": True, "forward_return": 0.1, "population": "PROSPECTIVE_GENUINE"}))
    assert refused["fields"]["outcome"]["status"] == "HORIZON_NOT_IMPLEMENTED"
    assert refused["fields"]["outcome"]["value"] is None
    unclassified = panel.build_row(_observation(outcome={"horizon_sessions": 5, "observed_qualified": True, "forward_return": 0.1}))
    assert unclassified["fields"]["outcome"]["status"] == "POPULATION_UNCLASSIFIED"
    observed = panel.build_row(_observation(outcome={
        "horizon_sessions": 5, "observed_qualified": True, "forward_return": 0.02,
        "population": "PROSPECTIVE_GENUINE", "tier": panel.RECONSTRUCTED_RESEARCH,
    }))
    assert observed["fields"]["outcome"]["status"] == "OBSERVED"
    assert observed["fields"]["outcome"]["value"]["population"] == "PROSPECTIVE_GENUINE"


def test_missing_focus_name_is_explicit_and_not_invented():
    built = panel.build_panel([_observation(ticker="QNS", tactical_state="BREAKOUT_READY")], focus_tickers=("QNS", "NVL", "PNJ"))
    assert built["focus_coverage"]["QNS"]["row_count"] == 1
    assert built["focus_coverage"]["NVL"]["status"] == "NO_RETAINED_COHORT_EVIDENCE"
    assert built["focus_coverage"]["PNJ"]["row_count"] == 0
    assert all(row["ticker"] != "NVL" for row in built["rows"])


def test_indexer_reads_only_the_small_files_and_does_not_mutate_them(tmp_path: Path):
    session = tmp_path / "2026-09-04"
    session.mkdir()
    enrichment = session / "enrichment"
    enrichment.mkdir()
    giant = enrichment / "integrated_investment_decision_product.json"
    giant.write_text('{"do_not_open": true}', encoding="utf-8")
    handoff = {
        "session": "2026-09-04",
        "breadth": {"advancing": 1, "declining": 2, "unchanged": 3, "breadth_descriptor": "MARKET_BREADTH_MIXED", "momentum_descriptor": "MIXED"},
        "prospective_decision_snapshot": {"identity": "prospective_decision_snapshot:abc"},
        "warnings": ["retained"],
    }
    opportunity = {
        "opportunity_prioritization_identity": "opportunity:abc",
        "cohort_tickers_by_state": {"EARLY_REVERSAL_CANDIDATE": ["pow", "POW", "HPG"], "BASE_BUILDING": ["PAN"]},
    }
    handoff_path = session / panel.HANDOFF_NAME
    opportunity_path = session / panel.OPPORTUNITY_NAME
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
    opportunity_path.write_text(json.dumps(opportunity), encoding="utf-8")
    before = hashlib.sha256(opportunity_path.read_bytes()).hexdigest()
    built = panel.index_retained_root(tmp_path, focus_tickers=("HPG", "PAN", "POW", "NVL"))
    after = hashlib.sha256(opportunity_path.read_bytes()).hexdigest()
    assert before == after
    assert built["row_count"] == 3
    assert built["session_index"][0]["duplicate_names_collapsed"] == 1
    assert built["rows"][0]["fields"]["decision_identity"]["value"] == "prospective_decision_snapshot:abc"
    assert built["focus_coverage"]["NVL"]["status"] == "NO_RETAINED_COHORT_EVIDENCE"
    assert built["tier_counts"][panel.RECONSTRUCTED_RESEARCH] == 3
    assert giant.read_text(encoding="utf-8").startswith("{")


def test_malformed_session_does_not_discard_a_valid_sibling(tmp_path: Path):
    bad = tmp_path / "2026-09-03"
    good = tmp_path / "2026-09-04"
    bad.mkdir()
    good.mkdir()
    (bad / panel.OPPORTUNITY_NAME).write_text("{", encoding="utf-8")
    (good / panel.OPPORTUNITY_NAME).write_text(json.dumps({
        "opportunity_prioritization_identity": "opportunity:good",
        "cohort_tickers_by_state": {"BREAKOUT_READY": ["QNS"]},
    }), encoding="utf-8")
    (good / panel.HANDOFF_NAME).write_text(json.dumps({
        "breadth": {"breadth_descriptor": "MARKET_BREADTH_POSITIVE", "advancing": 4, "declining": 1, "unchanged": 0},
    }), encoding="utf-8")
    built = panel.index_retained_root(tmp_path)
    statuses = {item["session"]: item["session_status"] for item in built["session_index"]}
    assert statuses["2026-09-03"] == "MALFORMED"
    assert statuses["2026-09-04"] == "INDEXED"
    assert [row["ticker"] for row in built["rows"]] == ["QNS"]
    assert built["rows"][0]["fields"]["market_regime"]["value"] == "MARKET_BREADTH_POSITIVE"


def test_unreadable_handoff_keeps_the_cohort_row(tmp_path: Path):
    session = tmp_path / "2026-09-04"
    session.mkdir()
    (session / panel.HANDOFF_NAME).write_text("{", encoding="utf-8")
    (session / panel.OPPORTUNITY_NAME).write_text(json.dumps({
        "opportunity_prioritization_identity": "opportunity:kept",
        "cohort_tickers_by_state": {"BASE_BUILDING": ["FPT"]},
    }), encoding="utf-8")
    built = panel.index_retained_root(tmp_path)
    assert built["session_index"][0]["session_status"] == "INDEXED_HANDOFF_UNREADABLE"
    assert [row["ticker"] for row in built["rows"]] == ["FPT"]
    assert built["rows"][0]["fields"]["market_regime"]["status"] == "MISSING"


def test_knowledge_date_is_not_copied_from_event_date():
    row = panel.build_row(_observation(event_date="2026-08-01"))
    assert row["fields"]["event_date"]["value"] == "2026-08-01"
    assert row["fields"]["source_knowledge_date"]["status"] == "MISSING"
    assert row["fields"]["source_knowledge_date"]["value"] is None
