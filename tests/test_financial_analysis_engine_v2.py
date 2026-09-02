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


def test_ocf_sign_and_same_provider_cross_statement_ratio_are_distinct():
    rows = [row("operating_cash_flow", 8, source="AAA_cash"), row("net_income", 10, source="AAA_income")]
    result = context(rows)
    assert result["features"]["operating_cash_flow_sign"]["fitness"] == "READY"
    assert result["features"]["cfo_to_net_income"]["fitness"] == "READY"


def test_same_provider_eop_capital_efficiency_is_ready_and_explicitly_a_proxy():
    rows = [
        row("net_income", 10, provider="VCI", source="AAA_vci_income"),
        row("revenue", 50, provider="VCI", source="AAA_vci_income"),
        row("total_assets", 100, provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_vci_balance"),
        row("shareholders_equity", 40, provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_vci_balance"),
    ]
    result = context(rows)
    assert result["features"]["same_provider_roa_eop_proxy"]["value"] == pytest.approx(0.1)
    assert result["features"]["same_provider_roe_eop_proxy"]["value"] == pytest.approx(0.25)
    assert result["features"]["same_provider_asset_turnover_eop_proxy"]["value"] == pytest.approx(0.5)
    assert "END_OF_PERIOD_BALANCE_PROXY_NOT_AVERAGE_BALANCE_RETURN" in result["features"]["same_provider_roa_eop_proxy"]["warnings"]


def test_cfo_to_net_income_keeps_negative_ratio_and_blocks_zero_denominator():
    negative = context([row("operating_cash_flow", 8, provider="VCI", source="AAA_vci_cash"),
                        row("net_income", -10, provider="VCI", source="AAA_vci_income")])
    assert negative["features"]["cfo_to_net_income"]["value"] == pytest.approx(-0.8)
    assert "NEGATIVE_NET_INCOME_RATIO_RETAINED_AS_REPORTED" in negative["features"]["cfo_to_net_income"]["warnings"]
    zero = context([row("operating_cash_flow", 8, provider="VCI", source="AAA_vci_cash"),
                    row("net_income", 0, provider="VCI", source="AAA_vci_income")])
    assert "ZERO_NET_INCOME_DENOMINATOR" in zero["features"]["cfo_to_net_income"]["reason_codes"]


def test_unknown_duration_same_provider_flows_never_activate_capital_efficiency_or_cash_conversion():
    rows = [
        row("net_income", 10, provider="VCI", semantic="UNKNOWN_DURATION", source="AAA_vci_income"),
        row("revenue", 50, provider="VCI", semantic="UNKNOWN_DURATION", source="AAA_vci_income"),
        row("operating_cash_flow", 8, provider="VCI", semantic="UNKNOWN_DURATION", source="AAA_vci_cash"),
        row("total_assets", 100, provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_vci_balance"),
    ]
    result = context(rows)
    assert result["features"]["same_provider_roa_eop_proxy"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert result["features"]["same_provider_asset_turnover_eop_proxy"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert result["features"]["cfo_to_net_income"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert result["features"]["revenue_qoq"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert result["features"]["revenue_ttm"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_free_cash_flow_proxy_is_blocked_without_qualified_capex():
    feature = context([])["features"]["free_cash_flow_proxy"]
    assert feature["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert "MISSING_SAME_PROVIDER_TICKER_PERIOD_SCOPE_REPRESENTATION" in feature["reason_codes"]


def test_free_cash_flow_proxy_uses_only_existing_canonical_ocf_and_capex_routes():
    import canonical_financial_facts as canonical

    routes = {
        metric: {candidate.raw_item_id for candidate in canonical.METRIC_REGISTRY[metric]["candidates"]}
        for metric in ("operating_cash_flow", "capital_expenditure")
    }
    assert routes == {
        "operating_cash_flow": {"operating_cash_flow", "net_cash_inflows_outflows_from_operating_activities"},
        "capital_expenditure": {
            "payment_for_fixed_assets_constructions_and_other_long_term_assets",
            "purchases_of_fixed_assets_and_other_long_term_assets",
        },
    }


def test_free_cash_flow_proxy_adds_signed_capex_without_normalization():
    result = context([row("operating_cash_flow", 100, source="AAA_cash"),
                      row("capital_expenditure", -40, source="AAA_cash")])
    feature = result["features"]["free_cash_flow_proxy"]
    assert feature["fitness"] == "READY"
    assert feature["value"] == 60
    assert feature["method"] == "same_provider_same_period_operating_cash_flow_plus_signed_capex/v1"
    assert "CAPEX_PROVIDER_SIGN_RETAINED_NO_NORMALIZATION" in feature["warnings"]
    assert result["current_research_ready"] is False


def test_free_cash_flow_proxy_preserves_positive_and_zero_capex_signs():
    positive = context([row("operating_cash_flow", 100, source="AAA_cash"),
                        row("capital_expenditure", 40, source="AAA_cash")])
    zero = context([row("operating_cash_flow", 100, source="AAA_cash"),
                    row("capital_expenditure", 0, source="AAA_cash")])
    assert positive["features"]["free_cash_flow_proxy"]["value"] == 140
    assert zero["features"]["free_cash_flow_proxy"]["value"] == 100


def test_free_cash_flow_proxy_requires_same_source_provider_scope_period_and_standalone_semantics():
    cases = [
        [row("operating_cash_flow", 100, provider="KBS", source="AAA_cash"),
         row("capital_expenditure", -40, provider="VCI", source="AAA_cash")],
        [row("operating_cash_flow", 100, source="AAA_cash_one"),
         row("capital_expenditure", -40, source="AAA_cash_two")],
        [row("operating_cash_flow", 100, source="AAA_cash", scope="consolidated"),
         row("capital_expenditure", -40, source="AAA_cash", scope="standalone")],
        [row("operating_cash_flow", 100, "2026-Q1", source="AAA_cash"),
         row("capital_expenditure", -40, "2026-Q2", source="AAA_cash")],
        [row("operating_cash_flow", 100, source="AAA_cash", semantic="YTD_CUMULATIVE_INTERIM"),
         row("capital_expenditure", -40, source="AAA_cash", semantic="YTD_CUMULATIVE_INTERIM")],
        [row("operating_cash_flow", 100, provider="VCI", source="AAA_cash", semantic="UNKNOWN_DURATION"),
         row("capital_expenditure", -40, provider="VCI", source="AAA_cash", semantic="UNKNOWN_DURATION")],
    ]
    for rows in cases:
        assert context(rows)["features"]["free_cash_flow_proxy"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_free_cash_flow_proxy_direction_is_same_quarter_yoy_level_delta_only():
    ready = context([
        row("operating_cash_flow", 100, "2025-Q2", source="AAA_cash"),
        row("capital_expenditure", -30, "2025-Q2", source="AAA_cash"),
        row("operating_cash_flow", 160, "2026-Q2", source="AAA_cash"),
        row("capital_expenditure", -40, "2026-Q2", source="AAA_cash"),
    ])
    assert ready["features"]["free_cash_flow_proxy_direction"]["value"] == 50
    assert ready["states"]["free_cash_flow_proxy_direction_state"] == "IMPROVING"
    wrong_quarter = context([
        row("operating_cash_flow", 100, "2025-Q4", source="AAA_cash"),
        row("capital_expenditure", -30, "2025-Q4", source="AAA_cash"),
        row("operating_cash_flow", 160, "2026-Q1", source="AAA_cash"),
        row("capital_expenditure", -40, "2026-Q1", source="AAA_cash"),
    ])
    assert wrong_quarter["features"]["free_cash_flow_proxy_direction"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert wrong_quarter["states"]["free_cash_flow_proxy_direction_state"] == "UNAVAILABLE"


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


def test_ttm_currency_scale_stay_unknown_when_the_lowercase_unknown_sentinel_is_retained():
    # `row()`'s default `normalized_candidate_unit` is the retained lowercase-"unknown"
    # sentinel a real unresolved fact carries -- must surface as None, not the string.
    result = context([row("revenue", value, label) for label, value in (
        ("2025-Q3", 10), ("2025-Q4", 11), ("2026-Q1", 12), ("2026-Q2", 13),
    )])
    assert result["features"]["revenue_ttm"]["currency"] is None
    assert result["features"]["revenue_ttm"]["scale"] is None


def test_ttm_currency_scale_str_none_cannot_become_a_known_basis():
    # A missing `normalized_candidate_unit` (Python None on `.get("currency")`, not the
    # string "unknown") must not stringify to the fake shared value "None" and read
    # back as a known, agreed-upon currency.
    rows = []
    for label, value in (("2025-Q3", 10), ("2025-Q4", 11), ("2026-Q1", 12), ("2026-Q2", 13)):
        one = row("revenue", value, label)
        del one["normalized_candidate_unit"]
        rows.append(one)
    result = context(rows)
    feature = result["features"]["revenue_ttm"]
    assert feature["fitness"] == "READY"
    assert feature["currency"] is None
    assert feature["currency"] != "None"
    assert feature["scale"] is None
    assert feature["scale"] != "None"


def test_ttm_currency_scale_surface_a_real_known_agreed_basis():
    rows = [row("revenue", value, label) for label, value in (
        ("2025-Q3", 10), ("2025-Q4", 11), ("2026-Q1", 12), ("2026-Q2", 13),
    )]
    for one in rows:
        one["normalized_candidate_unit"] = {"currency": "VND", "scale": "units"}
    result = context(rows)
    feature = result["features"]["revenue_ttm"]
    assert feature["currency"] == "VND"
    assert feature["scale"] == "units"


def test_ttm_currency_disagreement_across_quarters_never_silently_sums():
    # A currency-mismatched quarter cannot even join the same series: `_source_key`
    # buckets by (ticker, provider, source_file, statement_scope, currency, scale), so
    # a lone VND quarter among three USD ones leaves no single bucket with four
    # consecutive quarters -- the TTM sum blocks outright rather than ever combining
    # incompatible bases (belt-and-suspenders on top of `agree()`'s own unanimity rule,
    # covered directly in test_monetary_basis_contract.py).
    rows = [row("revenue", value, label) for label, value in (
        ("2025-Q3", 10), ("2025-Q4", 11), ("2026-Q1", 12), ("2026-Q2", 13),
    )]
    rows[0]["normalized_candidate_unit"] = {"currency": "VND", "scale": "units"}
    for one in rows[1:]:
        one["normalized_candidate_unit"] = {"currency": "USD", "scale": "units"}
    result = context(rows)
    feature = result["features"]["revenue_ttm"]
    assert feature["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert "MISSING_CONSECUTIVE_STANDALONE_QUARTER_INPUTS" in feature["reason_codes"]
    assert feature["currency"] is None


def test_pbt_ttm_margins_and_ttm_cash_conversion_use_four_compatible_quarters():
    rows = []
    for label in ("2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"):
        rows.extend([row("revenue", 100, label), row("profit_before_tax", 10, label), row("net_income", 8, label),
                     row("operating_cash_flow", 12, label, source="AAA_cash")])
    result = context(rows)
    assert result["features"]["profit_before_tax_ttm"]["value"] == 40
    assert result["features"]["ttm_pbt_margin"]["value"] == pytest.approx(.1)
    assert result["features"]["ttm_net_margin"]["value"] == pytest.approx(.08)
    assert result["features"]["cfo_to_net_income_ttm"]["value"] == pytest.approx(1.5)
    assert result["states"]["cash_conversion_state"] == "HEALTHY"


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


def _wc_row(metric, value, period, **kwargs):
    return row(metric, value, period, provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", **kwargs)


def test_positive_net_working_capital_and_current_ratio_are_ready():
    rows = [_wc_row("current_assets", 700, "2026-Q2"), _wc_row("current_liabilities", 350, "2026-Q2")]
    result = context(rows)
    nwc = result["features"]["net_working_capital"]
    ratio = result["features"]["current_ratio"]
    assert nwc["fitness"] == "READY" and nwc["value"] == 350
    assert ratio["fitness"] == "READY" and ratio["value"] == pytest.approx(2.0)
    assert result["states"]["working_capital_state"] == "POSITIVE_NET_WORKING_CAPITAL"
    assert result["current_research_ready"] is True


def test_negative_net_working_capital_state():
    rows = [_wc_row("current_assets", 100, "2026-Q2"), _wc_row("current_liabilities", 250, "2026-Q2")]
    result = context(rows)
    assert result["features"]["net_working_capital"]["value"] == -150
    assert result["states"]["working_capital_state"] == "NEGATIVE_NET_WORKING_CAPITAL"


def test_zero_net_working_capital_state():
    rows = [_wc_row("current_assets", 200, "2026-Q2"), _wc_row("current_liabilities", 200, "2026-Q2")]
    result = context(rows)
    assert result["features"]["net_working_capital"]["value"] == 0
    assert result["states"]["working_capital_state"] == "ZERO_NET_WORKING_CAPITAL"


def test_missing_current_liabilities_blocks_rather_than_substitutes_zero():
    result = context([_wc_row("current_assets", 700, "2026-Q2")])
    nwc = result["features"]["net_working_capital"]
    assert nwc["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert nwc["value"] is None
    assert result["states"]["working_capital_state"] == "WORKING_CAPITAL_UNAVAILABLE"
    assert result["features"]["current_ratio"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_scope_mismatch_blocks_the_pair_not_a_false_positive():
    rows = [_wc_row("current_assets", 700, "2026-Q2", scope="consolidated"),
            _wc_row("current_liabilities", 350, "2026-Q2", scope="standalone")]
    result = context(rows)
    assert result["features"]["current_ratio"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert result["features"]["net_working_capital"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_current_ratio_zero_denominator_is_blocked_not_infinite():
    rows = [_wc_row("current_assets", 700, "2026-Q2"), _wc_row("current_liabilities", 0, "2026-Q2")]
    result = context(rows)
    ratio = result["features"]["current_ratio"]
    assert ratio["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert ratio["value"] is None
    assert "ZERO_DENOMINATOR" in ratio["reason_codes"]
    # Net working capital is a subtraction, not a ratio: a zero denominator on the ratio
    # side must not block the independently well-defined difference.
    assert result["features"]["net_working_capital"]["fitness"] == "READY"


def test_working_capital_and_current_ratio_trajectory_improving():
    rows = [_wc_row("current_assets", 500, "2025-Q2"), _wc_row("current_liabilities", 400, "2025-Q2"),
            _wc_row("current_assets", 700, "2026-Q2"), _wc_row("current_liabilities", 350, "2026-Q2")]
    result = context(rows)
    # NWC: 100 -> 350 (improving). Current ratio: 1.25 -> 2.0 (improving).
    assert result["features"]["net_working_capital_direction"]["fitness"] == "READY"
    assert result["states"]["working_capital_trajectory_state"] == "WORKING_CAPITAL_IMPROVING"
    assert result["states"]["current_ratio_trajectory_state"] == "CURRENT_RATIO_IMPROVING"


def test_working_capital_trajectory_worsening_even_when_crossing_zero():
    # NWC goes from +50 to -100: a real deterioration that a percentage-of-prior formula
    # cannot express safely (the prior value is not the right denominator for a sign flip).
    rows = [_wc_row("current_assets", 450, "2025-Q2"), _wc_row("current_liabilities", 400, "2025-Q2"),
            _wc_row("current_assets", 300, "2026-Q2"), _wc_row("current_liabilities", 400, "2026-Q2")]
    result = context(rows)
    assert result["features"]["net_working_capital_direction"]["value"] == -150
    assert result["states"]["working_capital_trajectory_state"] == "WORKING_CAPITAL_WORSENING"


def test_trajectory_blocked_without_a_compatible_prior_year_pair():
    rows = [_wc_row("current_assets", 700, "2026-Q2"), _wc_row("current_liabilities", 350, "2026-Q2")]
    result = context(rows)
    assert result["features"]["net_working_capital_direction"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert result["features"]["current_ratio_direction"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert result["states"]["working_capital_trajectory_state"] == "UNAVAILABLE"
    assert result["states"]["current_ratio_trajectory_state"] == "UNAVAILABLE"


def test_no_arbitrary_current_ratio_healthy_threshold_in_state_vocabulary():
    rows = [_wc_row("current_assets", 100, "2026-Q2"), _wc_row("current_liabilities", 400, "2026-Q2")]
    result = context(rows)
    # A ratio well under any textbook "healthy" cutoff is still READY -- direction only,
    # never a weak/healthy verdict baked into the engine.
    assert result["features"]["current_ratio"]["fitness"] == "READY"
    assert result["features"]["current_ratio"]["value"] == pytest.approx(0.25)
    for state in result["states"].values():
        assert state not in {"WEAK", "HEALTHY_LIQUIDITY", "UNHEALTHY"}


def test_debt_and_working_capital_both_worsening_is_thesis_context_not_a_score():
    rows = [
        row("total_interest_bearing_debt", 100, "2025-Q2", provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_bs"),
        row("shareholders_equity", 500, "2025-Q2", provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_bs"),
        row("total_interest_bearing_debt", 300, "2026-Q2", provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_bs"),
        row("shareholders_equity", 500, "2026-Q2", provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_bs"),
        _wc_row("current_assets", 450, "2025-Q2", source="AAA_bs"), _wc_row("current_liabilities", 400, "2025-Q2", source="AAA_bs"),
        _wc_row("current_assets", 300, "2026-Q2", source="AAA_bs"), _wc_row("current_liabilities", 400, "2026-Q2", source="AAA_bs"),
    ]
    result = context(rows)
    assert result["states"]["leverage_state"] == "WORSENING"
    assert result["states"]["working_capital_trajectory_state"] == "WORKING_CAPITAL_WORSENING"
    assert any("leverage worsening alongside working capital worsening" in item for item in result["negative_evidence"])
    assert "score" not in result and "recommendation" not in result and "target_price" not in result


def test_limited_family_working_capital_features_are_not_applicable():
    result = context([_wc_row("current_assets", 700, "2026-Q2"), _wc_row("current_liabilities", 350, "2026-Q2")], entity="bank")
    assert result["features"]["current_ratio"]["fitness"] == "NOT_APPLICABLE"
    assert result["features"]["net_working_capital"]["fitness"] == "NOT_APPLICABLE"
    assert result["states"]["working_capital_state"] == "WORKING_CAPITAL_UNAVAILABLE"
    assert result["states"]["working_capital_trajectory_state"] == "UNAVAILABLE"


def test_current_liabilities_is_never_substituted_for_debt():
    # Only current_liabilities is retained -- no total_interest_bearing_debt row at all.
    # debt_to_equity must stay blocked, never silently pick up current_liabilities instead.
    rows = [_wc_row("current_assets", 700, "2026-Q2"), _wc_row("current_liabilities", 350, "2026-Q2"),
            row("shareholders_equity", 500, "2026-Q2", provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET")]
    result = context(rows)
    assert result["features"]["debt_to_equity"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert result["features"]["current_ratio"]["fitness"] == "READY"  # unaffected by debt's absence


def test_finance_lease_metrics_are_not_folded_into_total_interest_bearing_debt():
    import canonical_financial_facts as canonical
    definition = canonical.METRIC_REGISTRY["total_interest_bearing_debt"]
    assert set(definition["derived_from"]) == {"short_term_interest_bearing_debt", "long_term_interest_bearing_debt"}
    assert "short_term_finance_lease_liabilities" not in definition["derived_from"]
    assert "long_term_finance_lease_liabilities" not in definition["derived_from"]


def test_gross_margin_ready_same_provider_same_period():
    result = context([row("gross_profit", 400), row("revenue", 1000)])
    feature = result["features"]["gross_margin"]
    assert feature["fitness"] == "READY" and feature["value"] == pytest.approx(0.4)


def test_negative_gross_profit_produces_negative_margin_not_unavailable():
    # Negative gross profit is a valid input; `_ratio` never special-cases the
    # numerator's sign, only a zero denominator.
    result = context([row("gross_profit", -50), row("revenue", 1000)])
    feature = result["features"]["gross_margin"]
    assert feature["fitness"] == "READY" and feature["value"] == pytest.approx(-0.05)


def test_gross_margin_cross_provider_is_blocked():
    rows = [row("gross_profit", 400, provider="KBS"), row("revenue", 1000, provider="VCI", source="AAA_VCI_income")]
    assert context(rows)["features"]["gross_margin"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_gross_margin_period_mismatch_is_blocked():
    rows = [row("gross_profit", 400, "2026-Q1"), row("revenue", 1000, "2026-Q2")]
    assert context(rows)["features"]["gross_margin"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_gross_margin_scope_mismatch_is_blocked():
    rows = [row("gross_profit", 400, scope="consolidated"), row("revenue", 1000, scope="standalone")]
    assert context(rows)["features"]["gross_margin"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_gross_margin_zero_revenue_is_blocked():
    result = context([row("gross_profit", 400), row("revenue", 0)])
    feature = result["features"]["gross_margin"]
    assert feature["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert "ZERO_DENOMINATOR" in feature["reason_codes"]


def test_gross_margin_missing_revenue_is_blocked():
    assert context([row("gross_profit", 400)])["features"]["gross_margin"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_gross_margin_missing_gross_profit_is_blocked():
    assert context([row("revenue", 1000)])["features"]["gross_margin"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_gross_margin_conflict_blocks_ready():
    conflicted = row("gross_profit", 400)
    conflicted["source_conflicts"] = [{"kind": "restated_period_column_disagrees"}]
    result = context([conflicted, row("revenue", 1000)])
    assert result["features"]["gross_margin"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_unknown_duration_gross_profit_never_activates_margin():
    # Stands in for a VCI-sourced income statement: even if a ticker also retains a
    # compatible-looking revenue row, an UNKNOWN_DURATION gross_profit (VCI's real
    # period-semantics classification per structured_financial_period_semantics.py)
    # must never form a READY gross margin.
    rows = [row("gross_profit", 400, provider="VCI", semantic="UNKNOWN_DURATION", source="AAA_vci_income"),
            row("revenue", 1000, provider="VCI", semantic="UNKNOWN_DURATION", source="AAA_vci_income")]
    assert context(rows)["features"]["gross_margin"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_gross_margin_direction_same_quarter_prior_year():
    rows = [row("gross_profit", 300, "2025-Q2"), row("revenue", 1000, "2025-Q2"),
            row("gross_profit", 400, "2026-Q2"), row("revenue", 1000, "2026-Q2")]
    result = context(rows)
    feature = result["features"]["gross_margin_direction"]
    # 0.4 - 0.3 = 0.1: margin improved year over year on the same quarter.
    assert feature["fitness"] == "READY" and feature["value"] == pytest.approx(0.1)
    assert result["states"]["gross_margin_trajectory_state"] == "GROSS_MARGIN_IMPROVING"


def test_gross_margin_direction_worsening():
    rows = [row("gross_profit", 400, "2025-Q2"), row("revenue", 1000, "2025-Q2"),
            row("gross_profit", 300, "2026-Q2"), row("revenue", 1000, "2026-Q2")]
    result = context(rows)
    assert result["states"]["gross_margin_trajectory_state"] == "GROSS_MARGIN_WORSENING"


def test_gross_margin_direction_wrong_quarter_comparison_is_blocked():
    # Adjacent quarters (Q4 then Q1), not a same-quarter/prior-year pair -- must not be
    # silently accepted as a QoQ substitute for the required YoY comparison.
    rows = [row("gross_profit", 400, "2025-Q4"), row("revenue", 1000, "2025-Q4"),
            row("gross_profit", 420, "2026-Q1"), row("revenue", 1000, "2026-Q1")]
    result = context(rows)
    assert result["features"]["gross_margin_direction"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert result["states"]["gross_margin_trajectory_state"] == "UNAVAILABLE"


def test_gross_margin_direction_insufficient_history_is_blocked():
    result = context([row("gross_profit", 400, "2026-Q2"), row("revenue", 1000, "2026-Q2")])
    assert result["features"]["gross_margin_direction"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert result["states"]["gross_margin_trajectory_state"] == "UNAVAILABLE"


def test_limited_family_gross_margin_is_not_applicable():
    result = context([row("gross_profit", 400), row("revenue", 1000)], entity="bank")
    assert result["features"]["gross_margin"]["fitness"] == "NOT_APPLICABLE"
    assert result["features"]["gross_margin_direction"]["fitness"] == "NOT_APPLICABLE"
    assert result["states"]["gross_margin_trajectory_state"] == "UNAVAILABLE"


def test_gross_margin_alone_contributes_to_current_research_ready():
    # No other readiness feature is retained -- net_margin/pbt_margin/balance-sheet
    # ratios are all blocked -- so this isolates gross_margin's own contribution.
    result = context([row("gross_profit", 400), row("revenue", 1000)])
    assert result["features"]["net_margin"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert result["features"]["gross_margin"]["fitness"] == "READY"
    assert result["current_research_ready"] is True


# --- Average-balance ROE/ROA: exact-vs-EOP-proxy separation ---------------------------

def test_avg_equity_roe_ready_and_distinct_from_eop_proxy():
    rows = [
        row("net_income", 15, "2026-Q2", provider="VCI", source="AAA_vci_income"),
        row("shareholders_equity", 100, "2026-Q2", provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_vci_balance"),
        row("shareholders_equity", 80, "2026-Q1", provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_vci_balance"),
    ]
    result = context(rows)
    avg_equity = result["features"]["same_provider_roe_avg_equity"]
    eop_proxy = result["features"]["same_provider_roe_eop_proxy"]
    assert avg_equity["fitness"] == "READY" and avg_equity["value"] == pytest.approx(15 / 90)
    assert eop_proxy["fitness"] == "READY" and eop_proxy["value"] == pytest.approx(0.15)
    assert avg_equity["value"] != eop_proxy["value"]
    assert avg_equity["method"] != eop_proxy["method"]
    assert "AVERAGE_OF_PERIOD_BOUNDARY_BALANCES_NOT_MULTI_POINT_AVERAGE" in avg_equity["warnings"]


def test_avg_equity_roe_blocks_without_prior_quarter_boundary_while_eop_proxy_stays_ready():
    # Only the ending balance is retained -- the EOP proxy is still exactly what it was
    # before this milestone; the new average-balance feature must not silently fall back
    # to it, and must not be labelled READY off a single balance point.
    rows = [
        row("net_income", 15, "2026-Q2", provider="VCI", source="AAA_vci_income"),
        row("shareholders_equity", 100, "2026-Q2", provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_vci_balance"),
    ]
    result = context(rows)
    avg_equity = result["features"]["same_provider_roe_avg_equity"]
    assert avg_equity["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert "MISSING_SAME_PROVIDER_CONSECUTIVE_PERIOD_BOUNDARY_BALANCES" in avg_equity["reason_codes"]
    assert result["features"]["same_provider_roe_eop_proxy"]["fitness"] == "READY"
    assert result["features"]["same_provider_roe_eop_proxy"]["value"] == pytest.approx(0.15)


def test_avg_assets_roa_ready_and_distinct_from_eop_proxy():
    rows = [
        row("net_income", 20, "2026-Q2", provider="VCI", source="AAA_vci_income"),
        row("total_assets", 200, "2026-Q2", provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_vci_balance"),
        row("total_assets", 150, "2026-Q1", provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_vci_balance"),
    ]
    result = context(rows)
    avg_assets = result["features"]["same_provider_roa_avg_assets"]
    eop_proxy = result["features"]["same_provider_roa_eop_proxy"]
    assert avg_assets["fitness"] == "READY" and avg_assets["value"] == pytest.approx(20 / 175)
    assert eop_proxy["fitness"] == "READY" and eop_proxy["value"] == pytest.approx(0.1)
    assert avg_assets["value"] != eop_proxy["value"]


def test_avg_balance_return_blocks_on_zero_average_independent_of_eop_proxy():
    # Equity swings from -50 to +50: the average of the two boundary balances is exactly
    # zero even though neither individual balance is, and the EOP proxy (ending balance
    # only) is unaffected by that cancellation.
    rows = [
        row("net_income", 5, "2026-Q2", provider="VCI", source="AAA_vci_income"),
        row("shareholders_equity", 50, "2026-Q2", provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_vci_balance"),
        row("shareholders_equity", -50, "2026-Q1", provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_vci_balance"),
    ]
    result = context(rows)
    assert result["features"]["same_provider_roe_avg_equity"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert "ZERO_DENOMINATOR" in result["features"]["same_provider_roe_avg_equity"]["reason_codes"]
    assert result["features"]["same_provider_roe_eop_proxy"]["fitness"] == "READY"
    assert result["features"]["same_provider_roe_eop_proxy"]["value"] == pytest.approx(0.1)


def test_limited_family_avg_balance_roe_roa_are_not_applicable():
    result = context([row("net_income", 15), row("shareholders_equity", 100, semantic="POINT_IN_TIME_BALANCE_SHEET"),
                      row("total_assets", 200, semantic="POINT_IN_TIME_BALANCE_SHEET")], entity="bank")
    assert result["features"]["same_provider_roe_avg_equity"]["fitness"] == "NOT_APPLICABLE"
    assert result["features"]["same_provider_roa_avg_assets"]["fitness"] == "NOT_APPLICABLE"


# --- Own-history retrospective percentile/range context -------------------------------

def _margin_rows(margins, periods, *, provider="VCI"):
    rows = []
    for margin, period in zip(margins, periods):
        rows.append(row("revenue", 1000, period, provider=provider, source="AAA_vci_income"))
        rows.append(row("gross_profit", margin * 1000, period, provider=provider, source="AAA_vci_income"))
    return rows


def test_history_context_available_with_at_least_six_retained_periods():
    periods = ["2024-Q4", "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"]
    margins = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]
    result = context(_margin_rows(margins, periods))
    entry = result["history_context"]["gross_margin"]
    assert entry["status"] == "AVAILABLE"
    assert entry["sample_count"] == 6
    assert entry["subject_value"] == pytest.approx(0.40)
    assert entry["percentile"] == pytest.approx(1.0)
    assert entry["descriptive_bucket"] == "UPPER_QUARTILE"
    assert entry["range_min"] == pytest.approx(0.10)
    assert entry["range_max"] == pytest.approx(0.35)
    assert entry["as_of_period"] == "2026-Q2"
    assert entry["authority"] == "CURRENT_RESEARCH_RETROSPECTIVE_ONLY_NOT_PIT_HISTORICAL_CLAIM"


def test_history_context_partial_with_three_to_five_retained_periods():
    periods = ["2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"]
    margins = [0.10, 0.15, 0.20, 0.25]
    result = context(_margin_rows(margins, periods))
    entry = result["history_context"]["gross_margin"]
    assert entry["status"] == "PARTIAL"
    assert entry["sample_count"] == 3
    assert entry["percentile"] == pytest.approx(1.0)


def test_history_context_insufficient_below_three_retained_periods():
    periods = ["2026-Q1", "2026-Q2"]
    margins = [0.10, 0.25]
    result = context(_margin_rows(margins, periods))
    entry = result["history_context"]["gross_margin"]
    assert entry["status"] == "INSUFFICIENT_HISTORY"
    assert entry["sample_count"] == 1
    assert entry.get("percentile") is None


def test_history_context_percentile_is_tie_aware():
    periods = ["2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"]
    margins = [0.20, 0.20, 0.30, 0.20]  # current (latest) repeats two prior observations
    result = context(_margin_rows(margins, periods))
    entry = result["history_context"]["gross_margin"]
    assert entry["status"] == "PARTIAL" and entry["sample_count"] == 3
    assert entry["percentile"] == pytest.approx((0 + 0.5 * 2) / 3)
    assert entry["descriptive_bucket"] == "LOWER_MIDDLE"


def test_history_context_unavailable_when_subject_feature_is_blocked():
    result = context([row("revenue", 1000)])  # no gross_profit at all -> gross_margin BLOCKED
    assert result["features"]["gross_margin"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    entry = result["history_context"]["gross_margin"]
    assert entry["status"] == "UNAVAILABLE" and entry["reason"] == "SUBJECT_VALUE_UNAVAILABLE"


def test_history_context_blocks_rather_than_compares_across_a_different_source_key():
    # The subject value is the single latest-period observation from provider A; provider
    # B independently retains a longer but strictly older series under a different source
    # key. The longer series must never stand in as "history" for a value it never produced.
    rows = [
        row("revenue", 1000, "2026-Q2", provider="KBS", source="AAA_kbs_income"),
        row("gross_profit", 500, "2026-Q2", provider="KBS", source="AAA_kbs_income"),
        *_margin_rows([0.10, 0.15, 0.20, 0.25], ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"], provider="VCI"),
    ]
    result = context(rows)
    assert result["features"]["gross_margin"]["value"] == pytest.approx(0.5)
    entry = result["history_context"]["gross_margin"]
    assert entry["status"] == "UNAVAILABLE"
    assert entry["reason"] == "SUBJECT_PERIOD_NOT_IN_RETAINED_HISTORY_SERIES"


def test_limited_family_history_context_is_not_applicable():
    result = context([row("gross_profit", 400), row("revenue", 1000)], entity="securities")
    for feature_id in engine.HISTORY_CONTEXT_FEATURES:
        assert result["history_context"][feature_id]["status"] == "NOT_APPLICABLE"


def test_history_context_coverage_is_reported_in_artifact():
    periods = ["2024-Q4", "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"]
    margins = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]
    rows = _margin_rows(margins, periods)
    artifact = engine.build_artifact(tickers=["AAA"], rows=rows, issuer_types={"AAA": "corporate"},
                                     source_identities={"semantics": "x"}, requested_at="2026-09-02T00:00:00+07:00")
    coverage = artifact["coverage"]["history_context_coverage"]
    assert coverage["gross_margin"] == {"AVAILABLE": 1}
    assert set(coverage) == set(engine.HISTORY_CONTEXT_FEATURES)
