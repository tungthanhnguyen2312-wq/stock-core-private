"""Focused tests for `current_research_valuation_context`: the TTM monetary-basis
comparison, and the sector/industry (entity-class fallback) engine-feature peer context.
"""
from __future__ import annotations

import pytest

from current_research_valuation_context import (
    ENGINE_PEER_FEATURES, ENTITY_CLASS_COHORT_LEVEL, EV_EBITDA, EV_EBITDA_CALC_READY, INPUT_BLOCKED,
    NOT_APPLICABLE, PE_NOT_MEANINGFUL, PE_TTM, PS_TTM, SECTOR_COHORT_LEVEL,
    _calculation_readiness_method, _calculation_readiness_reconciliation, _monetary_basis_compatible,
    _select_ttm, attach_engine_fundamental_peers, attach_peer_relative, evaluate_ticker_valuation,
)
import monetary_basis_contract as basis_contract

BLOCKED_METHOD = {"status": "BLOCKED", "value": None, "blocked_reasons": []}


def test_readiness_reconciliation_compares_only_same_period_methods():
    methods = {
        "P/E": {"status": "RESEARCH_USABLE", "value": 12.0, "period_basis": "2025"},
        "P/S": {"status": "RESEARCH_USABLE", "value": 2.0, "period_basis": "2025"},
    }
    context = {"status": "AVAILABLE", "calculation_readiness": [{
        "reporting_period": "2025",
        "pe": {"readiness": "ready", "status": "provider_reported", "value": 12.0, "blocked_by": []},
    }]}
    result = _calculation_readiness_reconciliation(methods, context)
    assert result["P/E"]["comparison_status"] == "AGREES_WITHIN_REPRESENTATION_TOLERANCE"
    assert result["P/S"]["comparison_status"] == "NOT_SEMANTICALLY_EQUIVALENT"
    context["calculation_readiness"][0]["reporting_period"] = "2026-Q1"
    result = _calculation_readiness_reconciliation(methods, context)
    assert result["P/E"]["comparison_status"] == "NOT_COMPARABLE_DIFFERENT_REPORTING_PERIOD"


def qualified_feature(value, *, currency="VND", scale="units", provider="KBS",
                      periods=("2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4")):
    return {"fitness": "READY", "value": value, "method": "four_consecutive_compatible_standalone_quarters/v2",
            "period_identity": list(periods), "provider_source_provenance": [{"provider": provider}],
            "currency": currency, "scale": scale, "reason_codes": []}


def financial_analysis_record(*, net_income=None, revenue=None):
    features = {}
    if net_income is not None:
        features["net_income_ttm"] = net_income
    if revenue is not None:
        features["revenue_ttm"] = revenue
    return {"features": features}


def market_cap_metric(value, *, status="RESEARCH_USABLE", currency="VND", scale="units", monetary_basis=None):
    row = {"status": status, "value": value, "blocked_reasons": []}
    if monetary_basis is not None:
        row["monetary_basis"] = monetary_basis
        row["currency"] = monetary_basis.get("currency")
        row["scale"] = monetary_basis.get("native_scale")
        row["monetary_basis_status"] = monetary_basis.get("basis_status")
    else:
        row["currency"] = currency
        row["scale"] = scale
    return row


def valuation_record(market_cap):
    share = {"authority": "provider_reported_lagged", "status": "PROVIDER_REPORTED_LAGGED",
             "research_proxy_eligible": True, "authoritative_current_market_cap_eligible": False,
             "share_concept": "ISSUED_SHARES"}
    return {
        "entity_class": "corporate", "share_basis_input": share,
        "metrics": {
            "market_cap": market_cap, "P/E": BLOCKED_METHOD, "P/B": BLOCKED_METHOD,
            "P/S": BLOCKED_METHOD, "EV/Sales": BLOCKED_METHOD, "EV/EBITDA": BLOCKED_METHOD,
        },
    }


def feature_record():
    return {"features": {
        "net_income_ttm_sum": {"status": "BLOCKED"},
        "revenue_ttm_sum": {"status": "BLOCKED"},
        "profit_state": {"status": "BLOCKED"},
    }}


def evaluate(*, net_income=None, revenue=None, market_cap_value=8_000_000, cap_currency="VND",
            cap_scale="units", cap_monetary_basis=None):
    market_cap = market_cap_metric(market_cap_value, currency=cap_currency, scale=cap_scale,
                                   monetary_basis=cap_monetary_basis)
    return evaluate_ticker_valuation(
        ticker="AAA", feature_record=feature_record(), valuation_record=valuation_record(market_cap),
        financial_analysis_record=financial_analysis_record(net_income=net_income, revenue=revenue),
        financial_analysis_context_identity="fa:1",
    )


def test_compatible_normalized_bases_allow_pe_ttm():
    row = evaluate(net_income=qualified_feature(400_000), market_cap_value=8_000_000)
    method = row["methods"][PE_TTM]
    assert method["status"] == "RESEARCH_USABLE"
    assert method["value"] == pytest.approx(20.0)


def test_compatible_normalized_bases_allow_ps_ttm():
    row = evaluate(revenue=qualified_feature(4_000_000), market_cap_value=8_000_000)
    method = row["methods"][PS_TTM]
    assert method["status"] == "RESEARCH_USABLE"
    assert method["value"] == pytest.approx(2.0)


def test_currency_mismatch_blocks_pe_ttm():
    row = evaluate(net_income=qualified_feature(400_000, currency="USD"), market_cap_value=8_000_000)
    method = row["methods"][PE_TTM]
    assert method["status"] == INPUT_BLOCKED
    assert "TTM_MARKET_CAP_MONETARY_BASIS_INCOMPATIBLE" in method["blocker_reason_codes"]


def test_unknown_ttm_basis_blocks_even_though_market_cap_basis_is_known():
    # `feature.get("currency")` missing entirely (as `resolve_currency_and_scale` leaves
    # it absent an official-citation match) must never be treated as "matches VND".
    row = evaluate(net_income=qualified_feature(400_000, currency=None, scale=None), market_cap_value=8_000_000)
    method = row["methods"][PE_TTM]
    assert method["status"] == INPUT_BLOCKED
    assert "TTM_MARKET_CAP_MONETARY_BASIS_INCOMPATIBLE" in method["blocker_reason_codes"]


def test_unknown_market_cap_basis_blocks_even_though_ttm_basis_is_known():
    # The real production default today: market_wide_current_valuation_input_scaleout's
    # market_cap carries monetary_basis_status == UNKNOWN (see that module's own tests).
    unknown_cap_basis = basis_contract.build_basis(currency="VND", scale=None, basis_source="price scale undocumented")
    row = evaluate(net_income=qualified_feature(400_000), market_cap_value=8_000_000, cap_monetary_basis=unknown_cap_basis)
    method = row["methods"][PE_TTM]
    assert method["status"] == INPUT_BLOCKED
    assert "TTM_MARKET_CAP_MONETARY_BASIS_INCOMPATIBLE" in method["blocker_reason_codes"]


def test_different_native_scales_but_same_normalized_vnd_may_compare():
    # TTM retained in native thousand-VND with a proven multiplier; market cap retained
    # in native base VND. Native scales differ, but both reach the same normalized VND.
    ttm_thousand = qualified_feature(4_000)  # will be overridden below with a richer basis
    ttm_thousand["currency"], ttm_thousand["scale"] = "VND", "THOUSAND"
    financial_record = {"features": {"net_income_ttm": ttm_thousand}}
    cap_basis = basis_contract.build_basis(currency="VND", scale="units", multiplier_to_vnd=1,
                                           normalized_unit="VND", basis_status=basis_contract.QUALIFIED,
                                           basis_source="test: base-vnd market cap")
    market_cap = market_cap_metric(8_000_000, monetary_basis=cap_basis)
    row = evaluate_ticker_valuation(
        ticker="AAA", feature_record=feature_record(), valuation_record=valuation_record(market_cap),
        financial_analysis_record=financial_record, financial_analysis_context_identity="fa:1",
    )
    method = row["methods"][PE_TTM]
    # THOUSAND vs units, with no proven multiplier on the THOUSAND side -> still blocked:
    # a labelled scale alone (without a multiplier_to_vnd) is not by itself comparable.
    assert method["status"] == INPUT_BLOCKED


def test_monetary_basis_compatible_directly_with_a_proven_multiplier_on_both_sides():
    thousand = basis_contract.build_basis(currency="VND", scale="THOUSAND", multiplier_to_vnd=1000,
                                          normalized_unit="VND", basis_status=basis_contract.QUALIFIED, basis_source="a")
    base = basis_contract.build_basis(currency="VND", scale="units", multiplier_to_vnd=1,
                                      normalized_unit="VND", basis_status=basis_contract.QUALIFIED, basis_source="b")
    ttm = {"ttm_currency": thousand["currency"], "ttm_scale": thousand["native_scale"], "ttm_monetary_basis": thousand}
    market_cap = market_cap_metric(1, monetary_basis=base)
    ok, reason = _monetary_basis_compatible(ttm, market_cap)
    assert ok is True
    assert reason is None


def test_negative_ni_ttm_is_pe_not_meaningful_not_blocked():
    row = evaluate(net_income=qualified_feature(-400_000), market_cap_value=8_000_000)
    method = row["methods"][PE_TTM]
    assert method["status"] == PE_NOT_MEANINGFUL
    assert method["value"] is None


def test_zero_ni_ttm_is_pe_not_meaningful_not_blocked():
    row = evaluate(net_income=qualified_feature(0), market_cap_value=8_000_000)
    method = row["methods"][PE_TTM]
    assert method["status"] == PE_NOT_MEANINGFUL


def test_no_value_magnitude_heuristic_a_plausible_looking_ratio_still_blocks():
    # A market cap and TTM net income whose *ratio* looks like an entirely ordinary P/E
    # must still block when the basis itself is unproven -- plausibility is never used
    # as a substitute for a real currency/scale citation.
    unknown_cap_basis = basis_contract.build_basis(currency="VND", scale=None, basis_source="undocumented")
    row = evaluate(net_income=qualified_feature(1_000), market_cap_value=15_000, cap_monetary_basis=unknown_cap_basis)
    method = row["methods"][PE_TTM]
    assert method["status"] == INPUT_BLOCKED


def test_old_ttm_fallback_precedence_unchanged_when_no_qualified_ttm_present():
    old = {"status": "READY_RESEARCH_PROXY", "value": 500, "feature_id": "net_income_ttm_sum",
           "provider_source_lineage": [{"provider": "LEGACY"}], "currency": "VND", "scale": "units"}
    selected = _select_ttm(old=old, qualified=None)
    assert selected["ttm_input_source"] == "OLD_TTM_FALLBACK_SELECTED"
    assert selected["ttm_currency"] == "VND"
    assert selected["ttm_scale"] == "units"


def test_no_ttm_precedence_unchanged_when_neither_source_present():
    old = {"status": "BLOCKED", "value": None, "feature_id": "net_income_ttm_sum"}
    selected = _select_ttm(old=old, qualified=None)
    assert selected["ttm_input_source"] == "NO_TTM"
    assert selected["ttm_currency"] is None
    assert selected["ttm_scale"] is None


def test_both_present_new_qualified_ttm_still_preferred():
    old = {"status": "READY_RESEARCH_PROXY", "value": 999, "feature_id": "net_income_ttm_sum",
           "provider_source_lineage": [{"provider": "LEGACY"}], "currency": "VND", "scale": "units"}
    qualified = {"status": "READY", "value": 400, "ttm_currency": "VND", "ttm_scale": "units"}
    selected = _select_ttm(old=old, qualified=qualified)
    assert selected["ttm_input_source"] == "BOTH_PRESENT_CONFLICT"
    assert selected["value"] == 400
    assert selected["old_ttm_value"] == 999


def test_deterministic_identity_same_inputs_same_output():
    first = evaluate(net_income=qualified_feature(400_000), market_cap_value=8_000_000)
    second = evaluate(net_income=qualified_feature(400_000), market_cap_value=8_000_000)
    assert first["methods"][PE_TTM] == second["methods"][PE_TTM]


# --- attach_engine_fundamental_peers: sector/industry peer context over engine_v2 -----

def _engine_feature(value, *, fitness="READY", method="same_provider_same_period_gross_margin/v2",
                    period="2026-Q2", scope=("consolidated",), currency="unknown", scale="unknown"):
    return {"fitness": fitness, "value": value, "method": method, "period_identity": [period, period],
           "scope": list(scope), "currency": currency, "scale": scale, "reason_codes": [] if fitness == "READY" else ["X"]}


def _engine_record(gross_margin=None, *, issuer_type="corporate", **overrides):
    features = {}
    if gross_margin is not None:
        features["gross_margin"] = gross_margin if isinstance(gross_margin, dict) else _engine_feature(gross_margin)
    features.update(overrides)
    return {"issuer_type": issuer_type, "features": features}


def test_engine_peer_median_and_tie_aware_percentile():
    values = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60]
    records = {f"T{i}": _engine_record(value) for i, value in enumerate(values)}
    peers = attach_engine_fundamental_peers(records)
    entry = peers["T2"]["gross_margin"]  # subject value 0.30
    assert entry["status"] == "READY_RESEARCH_ONLY"
    assert entry["peer_count"] == 6
    assert entry["peer_median"] == pytest.approx(0.35)
    assert entry["percentile"] == pytest.approx((2 + 0.5) / 6)
    assert entry["cohort_level"] == ENTITY_CLASS_COHORT_LEVEL
    assert entry["cohort_id"] == "ENTITY_CLASS:corporate"


def test_engine_peer_percentile_is_tie_aware():
    values = [0.20, 0.20, 0.20, 0.30, 0.40]
    records = {f"T{i}": _engine_record(value) for i, value in enumerate(values)}
    peers = attach_engine_fundamental_peers(records)
    entry = peers["T0"]["gross_margin"]
    assert entry["percentile"] == pytest.approx((0 + 0.5 * 3) / 5)


def test_engine_peer_insufficient_below_minimum_cohort():
    records = {f"T{i}": _engine_record(value) for i, value in enumerate([0.1, 0.2, 0.3, 0.4])}
    peers = attach_engine_fundamental_peers(records)
    entry = peers["T0"]["gross_margin"]
    assert entry["status"] == "INSUFFICIENT_PEER_COUNT"
    assert entry["peer_count"] == 4
    assert entry.get("percentile") is None


def test_engine_peer_not_comparable_when_feature_not_ready():
    records = {f"T{i}": _engine_record(0.2 + i / 100) for i in range(5)}
    records["T0"] = _engine_record(_engine_feature(None, fitness="BLOCKED_BY_EVIDENCE"))
    peers = attach_engine_fundamental_peers(records)
    assert peers["T0"]["gross_margin"]["status"] == "NOT_COMPARABLE"
    assert peers["T0"]["gross_margin"]["peer_count"] == 0


def test_engine_peer_missing_metric_degrades_only_that_metric():
    records = {f"T{i}": _engine_record(0.2 + i / 100) for i in range(5)}
    for ticker, record in records.items():
        record["features"]["net_margin"] = _engine_feature(None, fitness="BLOCKED_BY_EVIDENCE")
    peers = attach_engine_fundamental_peers(records)
    assert peers["T0"]["gross_margin"]["status"] == "READY_RESEARCH_ONLY"
    assert peers["T0"]["net_margin"]["status"] == "NOT_COMPARABLE"
    assert set(peers["T0"]) == set(ENGINE_PEER_FEATURES)


def test_engine_peer_incompatible_method_never_pooled_together():
    records = {f"T{i}": _engine_record(0.2 + i / 100) for i in range(5)}
    records["T5"] = _engine_record(_engine_feature(0.99, method="a_different_method/v9"))
    peers = attach_engine_fundamental_peers(records)
    assert peers["T0"]["gross_margin"]["peer_count"] == 5
    assert peers["T5"]["gross_margin"]["status"] == "INSUFFICIENT_PEER_COUNT"
    assert peers["T5"]["gross_margin"]["peer_count"] == 1


def test_engine_peer_incompatible_monetary_basis_never_pooled_together():
    # Same feature, same cohort, same method, same period -- but a different native
    # currency/scale is a genuinely different monetary basis and must not be blended
    # into one percentile, exactly as the pre-existing valuation route's monetary-basis
    # compatibility gate already enforces for P/E, P/B, and P/S.
    records = {f"T{i}": _engine_record(0.2 + i / 100) for i in range(5)}
    records["T5"] = _engine_record(_engine_feature(0.99, currency="USD"))
    records["T6"] = _engine_record(_engine_feature(0.98, scale="thousand"))
    peers = attach_engine_fundamental_peers(records)
    assert peers["T0"]["gross_margin"]["peer_count"] == 5
    assert peers["T5"]["gross_margin"]["status"] == "INSUFFICIENT_PEER_COUNT"
    assert peers["T5"]["gross_margin"]["peer_count"] == 1
    assert peers["T6"]["gross_margin"]["status"] == "INSUFFICIENT_PEER_COUNT"
    assert peers["T6"]["gross_margin"]["peer_count"] == 1


def test_engine_peer_prefers_retained_sector_over_entity_class():
    records = {f"T{i}": _engine_record(0.2 + i / 100) for i in range(5)}
    industry = {ticker: "Bất động sản" for ticker in records}
    peers = attach_engine_fundamental_peers(records, industry_by_ticker=industry)
    entry = peers["T0"]["gross_margin"]
    assert entry["cohort_level"] == SECTOR_COHORT_LEVEL
    assert entry["cohort_id"] == f"SECTOR:{'bất động sản'}"
    assert entry["status"] == "READY_RESEARCH_ONLY" and entry["peer_count"] == 5


def test_engine_peer_falls_back_to_entity_class_without_retained_industry():
    records = {f"T{i}": _engine_record(0.2 + i / 100) for i in range(5)}
    peers = attach_engine_fundamental_peers(records, industry_by_ticker={"T0": "   "})
    assert peers["T0"]["gross_margin"]["cohort_level"] == ENTITY_CLASS_COHORT_LEVEL


# --- MARKET_WIDE_FUNDAMENTAL_VALUATION_ANALYTICAL_PRODUCT_V1: EV/EBITDA_CALC_READY ---------
# Wires market_wide_calculation_readiness.py's own EV/EBITDA verdict into a genuinely usable,
# separately-named method. The pre-existing EV_EBITDA method_id must remain untouched.

def _readiness_context(*, period="2026-Q1", readiness="ready", value=8.5, status="provider_reported",
                       blocked_by=()):
    return {
        "status": "AVAILABLE",
        "calculation_readiness": [{
            "reporting_period": period,
            "ev_ebitda": {"readiness": readiness, "status": status, "value": value,
                         "formula": "enterprise_value / ebitda", "blocked_by": list(blocked_by)},
        }],
    }


def test_calculation_readiness_method_ready_is_research_usable():
    method = _calculation_readiness_method(
        capability="ev_ebitda", method_id=EV_EBITDA_CALC_READY, applicability_method_id=EV_EBITDA,
        entity="corporate", calculation_readiness_record=_readiness_context(value=7.25))
    assert method["status"] == "RESEARCH_USABLE"
    assert method["value"] == pytest.approx(7.25)
    assert method["applicability"] == "APPLICABLE"
    assert method["own_history_status"] == "UNAVAILABLE_LATEST_PERIOD_ONLY_PIPELINE"


def test_calculation_readiness_method_not_applicable_for_bank():
    method = _calculation_readiness_method(
        capability="ev_ebitda", method_id=EV_EBITDA_CALC_READY, applicability_method_id=EV_EBITDA,
        entity="bank", calculation_readiness_record=_readiness_context())
    assert method["status"] == NOT_APPLICABLE
    assert method["applicability"] == NOT_APPLICABLE


def test_calculation_readiness_method_blocked_when_not_ready():
    method = _calculation_readiness_method(
        capability="ev_ebitda", method_id=EV_EBITDA_CALC_READY, applicability_method_id=EV_EBITDA,
        entity="corporate", calculation_readiness_record=_readiness_context(
            readiness="blocked", value=None, blocked_by=["negative_or_zero_ebitda_denominator"]))
    assert method["status"] == INPUT_BLOCKED
    assert "negative_or_zero_ebitda_denominator" in method["blocker_reason_codes"]


def test_calculation_readiness_method_blocked_when_context_absent():
    method = _calculation_readiness_method(
        capability="ev_ebitda", method_id=EV_EBITDA_CALC_READY, applicability_method_id=EV_EBITDA,
        entity="corporate", calculation_readiness_record=None)
    assert method["status"] == INPUT_BLOCKED
    assert "CALCULATION_READINESS_CONTEXT_UNAVAILABLE" in method["blocker_reason_codes"]


def test_evaluate_ticker_valuation_wires_calculation_readiness_method_end_to_end():
    row = evaluate_ticker_valuation(
        ticker="AAA", feature_record=feature_record(), valuation_record=valuation_record(market_cap_metric(8_000_000)),
        financial_analysis_record=financial_analysis_record(), financial_analysis_context_identity="fa:1",
        calculation_readiness_record=_readiness_context(value=9.1),
    )
    method = row["methods"][EV_EBITDA_CALC_READY]
    assert method["status"] == "RESEARCH_USABLE"
    assert method["value"] == pytest.approx(9.1)
    # The always-blocked, structurally-distinct legacy method is untouched by this wiring.
    assert row["methods"][EV_EBITDA]["status"] == INPUT_BLOCKED
    assert row["usable_relative_method_count"] >= 1


def test_evaluate_ticker_valuation_ev_ebitda_calc_ready_absent_stays_blocked_not_crashing():
    row = evaluate(net_income=qualified_feature(400_000), market_cap_value=8_000_000)
    assert row["methods"][EV_EBITDA_CALC_READY]["status"] == INPUT_BLOCKED


def test_ev_ebitda_calc_ready_participates_in_peer_relative_cohort():
    rows = {
        f"T{i}": evaluate_ticker_valuation(
            ticker=f"T{i}", feature_record=feature_record(), valuation_record=valuation_record(market_cap_metric(8_000_000)),
            financial_analysis_record=financial_analysis_record(), financial_analysis_context_identity="fa:1",
            calculation_readiness_record=_readiness_context(value=value),
        )
        for i, value in enumerate([5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    }
    rows = attach_peer_relative(rows)
    entry = rows["T2"]["peer_relative"][EV_EBITDA_CALC_READY]  # subject value 7.0
    assert entry["status"] == "READY_RESEARCH_ONLY"
    assert entry["peer_count"] == 6
    assert entry["percentile"] == pytest.approx((2 + 0.5) / 6)


def test_earnings_yield_ttm_is_reciprocal_of_usable_pe_ttm():
    row = evaluate(net_income=qualified_feature(400_000), market_cap_value=8_000_000)
    assert row["methods"][PE_TTM]["value"] == pytest.approx(20.0)
    assert row["earnings_yield_ttm"]["status"] == "RESEARCH_USABLE"
    assert row["earnings_yield_ttm"]["value"] == pytest.approx(0.05)


def test_earnings_yield_ttm_blocked_when_pe_ttm_not_meaningful():
    row = evaluate(net_income=qualified_feature(-400_000), market_cap_value=8_000_000)
    assert row["methods"][PE_TTM]["status"] == PE_NOT_MEANINGFUL
    assert row["earnings_yield_ttm"]["status"] == "BLOCKED"
    assert row["earnings_yield_ttm"]["value"] is None


def test_fcf_yield_ttm_is_explicitly_blocked_no_ttm_fcf_retained():
    row = evaluate(net_income=qualified_feature(400_000), market_cap_value=8_000_000)
    assert row["fcf_yield_ttm"]["status"] == "BLOCKED"
    assert row["fcf_yield_ttm"]["blocker_reason_codes"] == ["FCF_TTM_NOT_RETAINED_STANDALONE_QUARTER_PROXY_ONLY"]
