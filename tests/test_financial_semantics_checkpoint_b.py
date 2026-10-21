"""Checkpoint B: HPG period identity, financial freshness, and share effective date."""
from __future__ import annotations

import stocklookup_core.financial.financial_flow_semantics_ttm_bridge as bridge
import stocklookup_core.valuation.current_valuation_denominator_integrity as integrity
from stocklookup_core.decision.opportunity_axis_freshness import classify_axis_freshness
from stocklookup_core.evidence.temporal_freshness import separate_financial_clock
from stocklookup_core.valuation.current_research_valuation_context import _metric_freshness


def _hpg(label: str, value: int, metric: str = "net_income") -> dict:
    return {
        "ticker": "HPG", "canonical_metric": metric, "provider": "KBS",
        "statement_family": "income_statement", "reporting_period": label,
        "value": value, "status": "provider_reported", "statement_scope": "consolidated",
        "currency": "VND", "scale": "units", "source_sha256": "hpg-kbs", "fact_id": label,
    }


def test_hpg_kbs_raw_labels_stay_and_only_the_reconciled_signature_normalizes():
    parts = {
        "2025-Q3": 1_000, "2025-Q4": 2_000, "2025-Q4_1": 3_000,
        "2026-Q1": 15_514_931_571_606 - 6_000,
    }
    original = [_hpg(label, value) for label, value in parts.items()]
    saved = [dict(row) for row in original]
    qualified = bridge.qualify_proven_kbs_income_period(original)
    assert original == saved
    by_raw = {row["reporting_period"]: row for row in qualified}
    assert by_raw["2026-Q1"]["reporting_period"] == "2026-Q1"
    assert by_raw["2026-Q1"]["qualified_normalized_period"] == "2025-Q4"
    assert by_raw["2025-Q4_1"]["qualified_normalized_period"] == "2025-Q1"
    assert by_raw["2025-Q3"]["qualified_normalized_period"] == "2025-Q2"
    assert by_raw["2025-Q4"]["qualified_normalized_period"] == "2025-Q3"
    quarters, blockers = bridge.standalone_quarters(original)
    assert SAME_NOT_IN(blockers)
    assert [row["qualified_normalized_period"] for row in quarters] == ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"]
    assert [row["reporting_period"] for row in quarters] == ["2025-Q4_1", "2025-Q3", "2025-Q4", "2026-Q1"]
    record = bridge.build_ticker_record(ticker="HPG", entity_type="corporate", facts=original)
    ttm = record["ttm"]["net_income"]
    assert ttm["value"] == 15_514_931_571_606
    assert ttm["source_periods"] == ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"]
    assert ttm["source_raw_periods"] == ["2025-Q4_1", "2025-Q3", "2025-Q4", "2026-Q1"]


def SAME_NOT_IN(blockers):
    return bridge.SAME_FISCAL_PERIOD_COUNTED_TWICE not in blockers and bridge.KBS_PERIOD_ALIGNMENT_UNRECONCILED not in blockers


def test_unproven_ticker_and_unreconciled_hpg_do_not_shift_or_build_ttm():
    parts = {"2025-Q3": 1, "2025-Q4": 1, "2025-Q4_1": 1, "2026-Q1": 1}
    other = [{**_hpg(label, value), "ticker": "FPT"} for label, value in parts.items()]
    untouched = bridge.qualify_proven_kbs_income_period(other)
    assert all("qualified_normalized_period" not in row for row in untouched)
    drifted = [_hpg(label, value) for label, value in parts.items()]
    closed = bridge.qualify_proven_kbs_income_period(drifted)
    assert all(row["qualified_normalized_period"] is None for row in closed)
    assert all(row["ttm_blocker"] == bridge.KBS_PERIOD_ALIGNMENT_UNRECONCILED for row in closed)
    record = bridge.build_ticker_record(ticker="HPG", entity_type="corporate", facts=drifted)
    assert record["ttm"] == {}
    vci = {**_hpg("2025-Q4", 10), "provider": "VCI", "qualified_normalized_period": None}
    hpg = {**_hpg("2026-Q1", 10), "qualified_normalized_period": "2025-Q4"}
    refused = bridge.refuse_duplicate_fiscal_period([hpg, vci])
    assert refused["blocker"] == bridge.SAME_FISCAL_PERIOD_COUNTED_TWICE
    assert refused["value"] is None


def test_fy2024_is_not_current_just_because_the_price_session_is():
    clock = separate_financial_clock(
        financial_period="2024-FY", financial_period_end="2026-10-20", price_as_of="2026-10-20",
        knowledge_available_at="2025-03-28", decision_session="2026-10-20",
        maximum_completed_quarter_lag=4,
    )
    assert clock["freshness_status"] == "STALE_BUT_RESEARCH_USABLE"
    assert clock["financial_period_end"] == "2024-12-31"
    assert clock["price_as_of"] == "2026-10-20"
    assert clock["knowledge_available_at"] == "2025-03-28"
    assert clock["research_usable"] is True
    assert clock["rewritten_as_current"] is False
    metric = _metric_freshness(["2024-FY"], decision_session="2026-10-20",
                               reporting_basis={"period_end": "2026-10-20", "price_as_of": "2026-10-20",
                                                "knowledge_available_at": "2025-03-28"})
    assert metric["financial_freshness"] == "STALE_BUT_RESEARCH_USABLE"
    assert metric["price_session_not_used_as_financial_period_end"] is True
    recent = separate_financial_clock(
        financial_period="2026-Q2", financial_period_end=None, price_as_of="2026-10-20",
        knowledge_available_at="2026-08-28", decision_session="2026-10-20",
        maximum_completed_quarter_lag=4,
    )
    assert recent["freshness_status"] == "CURRENT"
    joined = classify_axis_freshness(
        axis="fundamental", decision_session="2026-10-20", source_session="2026-10-20",
        source_period="2024-FY",
    )
    assert joined["freshness_status"] == "STALE_BUT_RESEARCH_USABLE"
    assert joined["price_session_does_not_set_financial_freshness"] is True


def test_share_basis_fail_closed_for_plan_missing_ex_date_and_market_cap_price():
    planned = integrity.qualify_share_basis_for_price_session({
        "lifecycle": "ANNOUNCED", "shares": 85_000_000, "price_session": "2026-10-20",
        "execution_evidence_qualified": False,
    })
    assert planned["shares"] is None
    assert planned["planned_shares_converted_to_executed"] is False
    assert planned["share_continuity"] == "BLOCKED"
    missing_ex = integrity.qualify_share_basis_for_price_session({
        "lifecycle": "EXECUTED", "shares": 1_000, "price_session": "2026-10-20",
        "execution_evidence_qualified": True, "share_continuity_evidence": True,
        "effective_date": "2026-07-02", "effective_date_qualified": True,
    })
    assert missing_ex["share_continuity"] == "BLOCKED"
    assert "MISSING_EXPLICIT_OFFICIAL_EX_DATE" in missing_ex["reason_codes"]
    inferred = integrity.qualify_share_basis_for_price_session({
        "lifecycle": "SHARES_OUTSTANDING_EFFECTIVE", "market_cap": 178_146_551_372_000,
        "price": 21_100, "price_session": "2026-10-20",
    })
    assert inferred["shares"] is None
    assert inferred["market_cap_over_price_used_as_shares"] is False
    assert "SHARE_AUTHORITY_NOT_INFERRED_FROM_MARKET_CAP_OVER_PRICE" in inferred["reason_codes"]
    restated = integrity.qualify_share_basis_for_price_session({
        "lifecycle": "SHARES_OUTSTANDING_EFFECTIVE", "shares": 100, "price": 20_000,
        "price_basis": "ADJUSTED_RETROSPECTIVE", "price_session": "2026-10-20",
        "execution_evidence_qualified": True, "share_continuity_evidence": True,
        "ex_date": "2026-07-02", "ex_date_qualified": True,
        "effective_date": "2026-07-15", "effective_date_qualified": True,
    })
    assert restated["original_price"] is None
    assert "RESTATED_PRICE_IS_NOT_ORIGINAL_PRICE" in restated["reason_codes"]
    early = integrity.qualify_share_basis_for_price_session({
        "lifecycle": "REGISTERED", "shares": 100, "price_session": "2026-10-20",
        "execution_evidence_qualified": True, "share_continuity_evidence": True,
        "ex_date": "2026-11-01", "ex_date_qualified": True,
        "effective_date": "2026-11-02", "effective_date_qualified": True,
    })
    assert early["shares"] is None
    assert "EFFECTIVE_DATE_AFTER_PRICE_SESSION" in early["reason_codes"]
    effective = integrity.qualify_share_basis_for_price_session({
        "lifecycle": "SHARES_OUTSTANDING_EFFECTIVE", "shares": 100, "price": 20_000,
        "price_basis": "RAW_AS_TRADED", "price_session": "2026-10-20",
        "execution_evidence_qualified": True, "share_continuity_evidence": True,
        "ex_date": "2026-07-02", "ex_date_qualified": True,
        "effective_date": "2026-07-15", "effective_date_qualified": True,
    })
    assert effective["shares"] == 100
    assert effective["share_continuity"] == "QUALIFIED"
    assert effective["ex_date_inferred"] is False
