from copy import deepcopy
import inspect

import market_wide_fundamental_feature_store as store
import pytest


def row(metric, value, period="2025-Q2", *, provider="KBS", source="AAA_income_statement_quarter.parquet", scope="consolidated", semantic="STANDALONE_QUARTER", ticker="AAA", metadata_missing=None):
    return {"ticker": ticker, "canonical_metric": metric, "statement_scope": scope, "native_period_label": period,
            "period_end": "2025-06-30", "period_semantic_state": semantic, "source_status": "provider_reported",
            "lineage_complete": True, "source_conflicts": [], "reported_value": value, "metadata_missing": metadata_missing or {"unit": True},
            "source_lineage": {"provider": provider, "source_file": source, "source_sha256": "a", "raw_item_id": metric}}


def record(rows, profiles=None):
    return store.build_artifact(semantic_rows=rows, period_semantics_identity="semantics:x", requested_at="t", profiles=profiles or {"AAA": "corporate"})["records"]["AAA"]


def test_same_native_series_yoy_is_proxy_compatible():
    r = record([row("revenue", 120), row("revenue", 100, "2024-Q2")])
    assert r["features"]["revenue_same_period_yoy"]["compatibility_class"] == store.NATIVE


def test_yoy_uses_explicit_same_period_key_when_intervening_quarter_is_missing():
    r = record([
        row("revenue", 130, "2026-Q2"), row("revenue", 100, "2025-Q2"),
        row("revenue", 120, "2025-Q4"),
    ])
    feature = r["features"]["revenue_same_period_yoy"]
    assert feature["value"] == pytest.approx(0.3)
    assert feature["input_periods"] == ["2025-Q2", "2026-Q2"]


def test_incompatible_provider_series_does_not_form_margin():
    r = record([row("revenue", 100), row("net_income", 10, provider="VCI")])
    assert r["features"]["net_margin"]["status"] == store.FEATURE_BLOCKED


def test_incompatible_scope_does_not_form_margin():
    r = record([row("revenue", 100), row("net_income", 10, scope="separate")])
    assert r["features"]["net_margin"]["status"] == store.FEATURE_BLOCKED


def test_incompatible_duration_does_not_form_margin():
    r = record([row("revenue", 100), row("net_income", 10, semantic="UNKNOWN_DURATION")])
    assert r["features"]["net_margin"]["status"] == store.FEATURE_BLOCKED


def test_ttm_requires_four_consecutive_compatible_standalone_quarters():
    r = record([
        row("revenue", 100, "2025-Q3"), row("revenue", 110, "2025-Q4"),
        row("revenue", 120, "2026-Q1"), row("revenue", 130, "2026-Q2"),
    ])
    feature = r["features"]["revenue_ttm_sum"]
    assert feature["value"] == 460
    assert feature["method"] == "TTM_SUM_PROXY"
    assert feature["input_periods"] == ["2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"]


def test_ttm_uses_research_method_only_for_exact_compatible_tier():
    r = record([
        row("revenue", 100, "2025-Q3", metadata_missing={"unit": False}), row("revenue", 110, "2025-Q4", metadata_missing={"unit": False}),
        row("revenue", 120, "2026-Q1", metadata_missing={"unit": False}), row("revenue", 130, "2026-Q2", metadata_missing={"unit": False}),
    ])
    feature = r["features"]["revenue_ttm_sum"]
    assert feature["method"] == "TTM_SUM_RESEARCH"
    assert feature["compatibility_class"] == store.EXACT


def test_ttm_blocks_missing_or_incompatible_quarter_without_imputation():
    missing = record([
        row("revenue", 100, "2025-Q3"), row("revenue", 120, "2026-Q1"),
        row("revenue", 130, "2026-Q2"),
    ])["features"]["revenue_ttm_sum"]
    incompatible = record([
        row("revenue", 100, "2025-Q3"), row("revenue", 110, "2025-Q4", provider="VCI"),
        row("revenue", 120, "2026-Q1"), row("revenue", 130, "2026-Q2"),
    ])["features"]["revenue_ttm_sum"]
    assert missing["status"] == incompatible["status"] == store.FEATURE_BLOCKED
    assert missing["blocker_reason_codes"] == incompatible["blocker_reason_codes"] == ["MISSING_CONSECUTIVE_STANDALONE_QUARTER_INPUTS"]


def test_sign_changing_earnings_is_categorical_not_percentage():
    r = record([row("net_income", 10), row("net_income", -5, "2024-Q2")])
    f = r["features"]["net_income_same_period_yoy"]
    assert f["value"] is None and f["categorical_state"] == "TURNAROUND_TO_PROFIT"


def test_zero_and_missing_remain_distinct():
    zero = record([row("revenue", 0), row("revenue", 10, "2024-Q2")])["features"]["revenue_same_period_yoy"]
    missing = record([row("revenue", None), row("revenue", 10, "2024-Q2")])["features"]["revenue_same_period_yoy"]
    assert "ZERO" not in zero["blocker_reason_codes"] and missing["status"] == store.FEATURE_BLOCKED


def test_net_margin_is_dimensionless_same_native_proxy():
    r = record([row("revenue", 100), row("net_income", 10)])
    assert r["features"]["net_margin"]["value"] == 0.1


def test_gross_margin_is_dimensionless_same_native_proxy():
    r = record([row("revenue", 100), row("gross_profit", 35)])
    assert r["features"]["gross_margin"]["value"] == 0.35


def test_pit_trajectory_uses_balance_only():
    r = record([row("total_assets", 120, semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_balance_sheet_quarter.parquet"), row("total_assets", 100, "2025-Q1", semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_balance_sheet_quarter.parquet")])
    assert r["features"]["total_assets_pit_trajectory"]["compatibility_class"] == store.PIT


def test_debt_never_substitutes_liabilities():
    r = record([row("total_liabilities", 30, semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_balance_sheet_quarter.parquet"), row("shareholders_equity", 70, semantic="POINT_IN_TIME_BALANCE_SHEET", source="AAA_balance_sheet_quarter.parquet")])
    assert r["features"]["debt_to_equity"]["status"] == store.FEATURE_BLOCKED


def test_roa_and_roe_are_explicit_eop_proxy_blocked_without_cross_contract():
    r = record([row("revenue", 100)])
    assert r["features"]["roa_eop_proxy"]["status"] == store.FEATURE_BLOCKED
    assert r["features"]["roe_eop_proxy"]["status"] == store.FEATURE_BLOCKED


def test_negative_cfo_with_profit_is_not_cross_provider_synthesized():
    r = record([row("net_income", 10), row("operating_cash_flow", -5, provider="VCI", source="AAA_cash_flow_quarter.parquet")])
    assert r["features"]["cfo_to_net_income"]["status"] == store.FEATURE_BLOCKED


def test_negative_cfo_with_profit_state_requires_same_native_contract():
    r = record([row("net_income", 10), row("operating_cash_flow", -5)])
    assert r["features"]["cash_earnings_alignment"]["categorical_state"] == "NEGATIVE_CFO_WITH_PROFIT"


def test_financial_entity_gets_generic_corporate_exclusion():
    r = record([row("revenue", 100)], {"AAA": "bank"})
    assert r["entity_applicability"] == "GENERIC_CORPORATE_FEATURE_NOT_APPLICABLE"


def test_identity_is_deterministic_and_request_time_independent():
    rows = [row("revenue", 100)]
    a = store.build_artifact(semantic_rows=rows, period_semantics_identity="x", requested_at="one", profiles={})
    b = store.build_artifact(semantic_rows=rows, period_semantics_identity="x", requested_at="two", profiles={})
    assert a["artifact_identity"] == b["artifact_identity"]


def test_missing_ticker_input_is_local():
    a = store.build_artifact(semantic_rows=[row("revenue", 100), row("revenue", 100, ticker="BBB")], period_semantics_identity="x", requested_at="t", profiles={})
    assert set(a["records"]) == {"AAA", "BBB"}


def test_no_raw_mutation_or_ticker_specific_conditions():
    source = row("revenue", 100); before = deepcopy(source)
    record([source])
    assert source == before and "ticker ==" not in inspect.getsource(store.build_ticker_record)


def test_authority_never_widens_and_compact_context_exists():
    r = record([row("revenue", 100)])
    assert r["authority_boundary"]["authoritative"] is False
    assert "availability" in r["fundamental_feature_context"]


def test_compact_context_does_not_repeat_raw_historical_rows_or_lineage():
    r = record([
        row("revenue", 100, "2025-Q3"), row("revenue", 110, "2025-Q4"),
        row("revenue", 120, "2026-Q1"), row("revenue", 130, "2026-Q2"),
    ])
    detailed = r["features"]["revenue_ttm_sum"]
    compact = r["fundamental_feature_context"]["current_features"]["revenue_ttm_sum"]
    assert compact["input_periods"] == detailed["input_periods"]
    assert "provider_source_lineage" not in compact
    assert "native_field_lineage" not in compact
    assert "calculation_lineage" not in compact
    assert "features" not in r["fundamental_feature_context"]
