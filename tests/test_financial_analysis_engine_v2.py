from __future__ import annotations

from copy import deepcopy

import financial_analysis_engine_v2 as engine
import pytest


def row(metric, value, period="2026-Q2", *, ticker="AAA", provider="KBS", source=None,
        semantic="STANDALONE_QUARTER", scope="consolidated", sha="sha-1"):
    source = source or f"{ticker}_{provider}_{'income' if semantic == 'STANDALONE_QUARTER' else 'balance'}"
    return {
        "ticker": ticker, "canonical_metric": metric, "reported_value": value,
        "native_period_label": period, "period_end": period, "period_semantic_state": semantic,
        "source_status": "provider_reported", "lineage_complete": True, "source_conflicts": [],
        "statement_scope": scope, "normalized_candidate_unit": {"currency": "unknown", "scale": "unknown"},
        "source_lineage": {"provider": provider, "source_file": source, "source_sha256": sha, "fact_id": f"{metric}-{period}-{provider}"},
    }


def context(rows, entity="corporate"):
    return engine.build_ticker_context("AAA", rows, issuer_type=entity, source_identities={"semantics": "x"})


def test_true_consecutive_standalone_qoq_is_ready():
    result = context([row("revenue", 100, "2025-Q4"), row("revenue", 120, "2026-Q1")])
    assert result["features"]["revenue_qoq"]["fitness"] == "READY"
    assert result["features"]["revenue_qoq"]["value"] == pytest.approx(0.2)


def test_period_semantic_normalization_fails_closed_without_inferring_duration():
    assert engine.normalize_period_semantic("STANDALONE_QUARTER") == engine.FLOW_STANDALONE
    assert engine.normalize_period_semantic("quarterly") == engine.UNKNOWN


def test_q3_to_q1_is_not_qoq():
    result = context([row("revenue", 100, "2026-Q1"), row("revenue", 120, "2026-Q3")])
    feature = result["features"]["revenue_qoq"]
    assert feature["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert "MISSING_CONSECUTIVE_STANDALONE_QUARTER_INPUTS" in feature["reason_codes"]


def test_adjacent_scope_mismatch_is_not_qoq():
    rows = [
        row("revenue", 100, "2025-Q4", scope="consolidated"),
        row("revenue", 120, "2026-Q1", scope="standalone"),
    ]
    assert context(rows)["features"]["revenue_qoq"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_same_quarter_yoy_uses_exact_prior_year_quarter():
    result = context([row("revenue", 100, "2025-Q2"), row("revenue", 130, "2026-Q2")])
    feature = result["features"]["revenue_same_quarter_yoy"]
    assert feature["fitness"] == "READY" and feature["value"] == pytest.approx(0.3)


def test_ytd_yoy_rejects_different_cumulative_duration():
    rows = [
        row("revenue", 100, "2025-Q1", semantic="YTD_CUMULATIVE_INTERIM"),
        row("revenue", 130, "2026-Q2", semantic="YTD_CUMULATIVE_INTERIM"),
    ]
    assert context(rows)["features"]["revenue_ytd_yoy"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_unknown_duration_never_forms_growth():
    rows = [row("revenue", 100, "2025-Q2", semantic="UNKNOWN_DURATION"), row("revenue", 130, "2026-Q2", semantic="UNKNOWN_DURATION")]
    assert context(rows)["features"]["revenue_same_quarter_yoy"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_missing_source_sha_cannot_become_ready():
    source = row("revenue", 100, "2025-Q4"); source["source_lineage"]["source_sha256"] = None
    assert context([source, row("revenue", 120, "2026-Q1")])["features"]["revenue_qoq"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_same_provider_ratio_is_ready_even_when_scale_is_unknown():
    result = context([row("revenue", 100), row("net_income", 10)])
    assert result["features"]["net_margin"]["fitness"] == "READY"
    assert result["features"]["net_margin"]["value"] == 0.1


def test_cross_provider_roa_is_proxy_never_ready_or_readiness_source():
    rows = [row("net_income", 10, provider="KBS"), row("total_assets", 100, provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_VCI_balance")]
    result = context(rows)
    feature = result["features"]["mixed_provider_roa_proxy"]
    assert feature["fitness"] == "RESEARCH_PROXY"
    assert "CROSS_PROVIDER_UNRESOLVED_SCALE" in feature["reason_codes"]
    assert result["current_research_ready"] is False


def test_non_positive_growth_base_is_a_semantic_transition_not_a_percentage():
    result = context([row("net_income", -10, "2025-Q2"), row("net_income", 10, "2026-Q2")])
    feature = result["features"]["net_income_same_quarter_yoy"]
    assert feature["value"] is None and feature["semantic_transition"] == "LOSS_TO_PROFIT"
    assert "GROWTH_BASE_NON_POSITIVE" in feature["warnings"]


def test_ocf_sign_and_cross_statement_proxy_are_distinct():
    rows = [row("operating_cash_flow", 8, source="AAA_cash"), row("net_income", 10, source="AAA_income")]
    result = context(rows)
    assert result["features"]["operating_cash_flow_sign"]["fitness"] == "READY"
    assert result["features"]["cfo_to_net_income"]["fitness"] == "RESEARCH_PROXY"


def test_fcf_remains_blocked_without_capex_semantics():
    assert context([])["features"]["fcf"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_ttm_requires_exactly_four_consecutive_standalone_quarters():
    ready = context([row("revenue", value, label) for label, value in (
        ("2025-Q3", 10), ("2025-Q4", 11), ("2026-Q1", 12), ("2026-Q2", 13),
    )])
    blocked = context([row("revenue", value, label) for label, value in (
        ("2025-Q3", 10), ("2026-Q1", 12), ("2026-Q2", 13),
    )])
    assert ready["features"]["revenue_ttm"]["fitness"] == "READY"
    assert ready["features"]["revenue_ttm"]["value"] == 46
    assert blocked["features"]["revenue_ttm"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_balance_sheet_ratios_and_trajectory_are_ready_when_compatible():
    rows = [
        row("shareholders_equity", 40, "2025-Q2", provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_balance"),
        row("total_assets", 100, "2025-Q2", provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_balance"),
        row("cash_and_cash_equivalents", 20, "2025-Q2", provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_balance"),
        row("shareholders_equity", 55, "2026-Q2", provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_balance"),
        row("total_assets", 110, "2026-Q2", provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_balance"),
        row("cash_and_cash_equivalents", 22, "2026-Q2", provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_balance"),
    ]
    result = context(rows)
    assert result["features"]["equity_to_assets"]["fitness"] == "READY"
    assert result["features"]["cash_to_assets"]["fitness"] == "READY"
    assert result["features"]["assets_yoy"]["fitness"] == "READY"


def test_debt_leverage_is_never_manufactured():
    result = context([row("total_interest_bearing_debt", 30, semantic="POINT_IN_TIME_BALANCE_SHEET")])
    assert "DEBT_EVIDENCE_UNAVAILABLE_NO_EXACT_DEBT_LEVERAGE" in result["warnings"]
    assert result["leverage_basis"] == "EQUITY_TO_ASSETS_STRUCTURAL_DIRECTION_ONLY_DEBT_UNAVAILABLE"


def test_non_industrial_and_unknown_are_not_defaulted_to_corporate():
    for issuer_type in ("bank", "securities", "insurance", "finance_company", "unknown", None):
        result = context([row("revenue", 100)], issuer_type)
        assert result["analysis_family"] == engine.LIMITED
        assert result["features"]["net_margin"]["fitness"] == "NOT_APPLICABLE"


def test_conflicting_evidence_does_not_make_a_fake_resilience_winner():
    rows = [row("net_income", 10), row("operating_cash_flow", -5, source="AAA_cash")]
    result = context(rows)
    assert result["states"]["resilience_state"] == "UNAVAILABLE"


def test_artifact_identity_is_deterministic_and_zero_drop():
    rows = [row("revenue", 100), row("net_income", 10)]
    kwargs = {"tickers": ["BBB", "AAA"], "rows": rows, "issuer_types": {"AAA": "corporate", "BBB": "unknown"}, "source_identities": {"semantics": "x"}}
    one = engine.build_artifact(**kwargs, requested_at="one")
    two = engine.build_artifact(**kwargs, requested_at="two")
    assert one["artifact_identity"] == two["artifact_identity"]
    assert one["coverage"]["zero_silent_ticker_drops"] is True
    assert all(record["authority_boundary"]["is_actionable"] is False for record in one["records"].values())


def test_engine_does_not_mutate_retained_rows_or_emit_scores_targets_or_probabilities():
    rows = [row("revenue", 100), row("net_income", 10)]
    before = deepcopy(rows)
    result = context(rows)
    assert rows == before
    assert result["authority_boundary"]["is_actionable"] is False
    assert "score" not in result and "target_price" not in result and "probability" not in result
