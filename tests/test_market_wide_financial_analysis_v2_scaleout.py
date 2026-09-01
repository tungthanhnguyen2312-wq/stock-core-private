from __future__ import annotations

import financial_analysis_engine_v2 as engine
import financial_flow_semantics_ttm_bridge as bridge
from market_wide_financial_analysis_v2_scaleout import GENERIC, build_scaleout


def _row(metric, value, period="2026-Q2", *, ticker="AAA", semantic="STANDALONE_QUARTER"):
    return {"ticker": ticker, "canonical_metric": metric, "reported_value": value, "native_period_label": period,
            "period_end": period, "period_semantic_state": semantic, "source_status": "provider_reported",
            "lineage_complete": True, "source_conflicts": [], "statement_scope": "consolidated",
            "normalized_candidate_unit": {"currency": "VND", "scale": "ONE"},
            "source_lineage": {"provider": "KBS", "source_file": f"{ticker}-income", "source_sha256": "x", "fact_id": f"{ticker}-{metric}-{period}"}}


def _store(ticker="AAA", *, entity="corporate", applicability="GENERIC_RESEARCH_PRIMITIVES_ALLOWED"):
    return {"ticker": ticker, "entity_type": entity, "entity_applicability": applicability, "features": {
        "profit_state": {"status": "READY_RESEARCH_PROXY", "value": 10, "categorical_state": "PROFITABLE", "input_periods": ["2026-Q2"], "provider_source_lineage": [], "scope": ["consolidated"], "duration_semantics": ["STANDALONE_QUARTER"]},
        "net_margin": {"status": "READY_RESEARCH_PROXY", "value": .1, "categorical_state": None, "input_periods": ["2026-Q2"], "provider_source_lineage": [], "scope": ["consolidated"], "duration_semantics": ["STANDALONE_QUARTER"]},
    }}


def test_stronger_period_semantic_ready_feature_wins_over_store_proxy():
    artifact = build_scaleout(semantic_rows=[_row("revenue", 100), _row("net_income", 10)], feature_records={"AAA": _store()}, feature_store_artifact={"artifact_identity": "store:1"}, period_semantics_identity="sem:1", requested_at="t")
    feature = artifact["records"]["AAA"]["features"]["net_margin"]
    assert feature["fitness"] == "READY"
    assert feature["source_tier"] == "PERIOD_SEMANTIC_FACTS"


def test_store_proxy_can_expose_generic_context_but_never_make_ready():
    artifact = build_scaleout(semantic_rows=[], feature_records={"AAA": _store(entity=None)}, feature_store_artifact={"artifact_identity": "store:1"}, period_semantics_identity="sem:1", requested_at="t")
    record = artifact["records"]["AAA"]
    assert record["analysis_family"] == GENERIC
    assert record["features"]["net_income_sign"]["fitness"] == "RESEARCH_PROXY"
    assert record["current_research_ready"] is False
    assert record["states"]["profitability_state"] == "PROFITABLE"


def test_proxy_roa_does_not_change_v2_capital_efficiency_or_readiness():
    store = _store(); store["features"]["roa_eop_proxy"] = {"status": "READY_RESEARCH_PROXY", "value": .2, "categorical_state": None, "input_periods": ["2026-Q2"], "provider_source_lineage": [], "scope": ["consolidated"], "duration_semantics": ["POINT_IN_TIME_BALANCE_SHEET"]}
    artifact = build_scaleout(semantic_rows=[], feature_records={"AAA": store}, feature_store_artifact={"artifact_identity": "store:1"}, period_semantics_identity="sem:1", requested_at="t")
    record = artifact["records"]["AAA"]
    assert record["features"]["mixed_provider_roa_proxy"]["fitness"] == "RESEARCH_PROXY"
    assert record["states"]["capital_efficiency_state"] == "UNAVAILABLE"
    assert record["current_research_ready"] is False


def test_original_engine_qoq_guard_is_unchanged():
    artifact = build_scaleout(semantic_rows=[_row("revenue", 100, "2026-Q1"), _row("revenue", 120, "2026-Q3")], feature_records={"AAA": _store()}, feature_store_artifact={"artifact_identity": "store:1"}, period_semantics_identity="sem:1", requested_at="t")
    assert artifact["records"]["AAA"]["features"]["revenue_qoq"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert artifact["coverage"]["zero_silent_ticker_drops"] is True
    assert artifact["contract_version"] == engine.CONTRACT_VERSION


def test_qualified_flow_artifact_is_the_only_flow_input_and_carries_coverage():
    facts = [{"ticker": "AAA", "canonical_metric": metric, "provider": "KBS", "statement_family": "income_statement",
              "reporting_period": label, "value": value, "status": "provider_reported", "statement_scope": "consolidated",
              "currency": "VND", "scale": "ONE", "source_sha256": "x", "source_file": "income", "fact_id": f"{metric}-{label}"}
             for label in ("2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2")
             for metric, value in (("revenue", 100), ("profit_before_tax", 10), ("net_income", 8))]
    qualified = bridge.build_artifact(tickers=["AAA"], facts_by_ticker={"AAA": facts}, entity_type_by_ticker={"AAA": "corporate"}, requested_at="t")
    artifact = build_scaleout(semantic_rows=[_row("revenue", 999)], feature_records={"AAA": _store()},
                              feature_store_artifact={"artifact_identity": "store:1"}, period_semantics_identity="sem:1",
                              requested_at="t", qualified_flow_artifact=qualified)
    assert artifact["records"]["AAA"]["features"]["revenue_ttm"]["value"] == 400
    assert artifact["records"]["AAA"]["features"]["profit_before_tax_ttm"]["value"] == 40
    assert artifact["coverage"]["qualified_flow_before_after"]["after"]["revenue"]["ttm_ticker_count"] == 1
    assert artifact["records"]["AAA"]["states"]["earnings_turnaround_state"] == "UNAVAILABLE"
