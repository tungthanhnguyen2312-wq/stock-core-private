from __future__ import annotations

import financial_analysis_engine_v2 as engine
import financial_flow_semantics_ttm_bridge as bridge
import market_wide_financial_analysis_v2_scaleout as scaleout
import structured_financial_period_semantics as sem_semantics
from market_wide_financial_analysis_v2_scaleout import GENERIC, build_qualified_flow_artifact, build_scaleout


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


def _semantic_row(metric, value, label, *, ticker="AAA", cumulative_state="unknown"):
    """A real structured_financial_period_semantics.project_fact() output -- the actual shape
    every real build_qualified_flow_artifact caller passes, with its renamed/nested field names
    (reported_value, source_status, source_lineage.provider, normalized_candidate_unit.*)."""
    raw = {"ticker": ticker, "canonical_metric": metric, "provider": "KBS", "statement_family": "income_statement",
           "statement_scope": "consolidated", "reporting_period": label, "period_type": "quarterly",
           "source_sha256": "x" * 64, "source_file": "income", "fact_id": f"{metric}-{label}",
           "source_observation_ids": ["o-1"], "status": "provider_reported",
           "qualification_state": "provider_reported", "value": value, "currency": "VND", "scale": "ONE",
           "observed_at": "2026-01-01T00:00:00+07:00", "conflicts": [], "warnings": [],
           "cumulative_state": cumulative_state}
    return sem_semantics.project_fact(raw)


def test_build_qualified_flow_artifact_groups_semantic_rows_by_ticker():
    """FINANCIAL_TEMPORAL_SEMANTIC_NORMALIZATION_AND_ANALYTICAL_PANEL_V1: the bridge was
    previously built and tested but never invoked by any real `build_scaleout` caller, because
    each caller would have had to hand-derive `facts_by_ticker`/`entity_type_by_ticker` itself.
    This proves the new one-call helper reproduces that same qualification end to end using the
    REAL structured_financial_period_semantics row shape -- an earlier version of this helper
    passed such rows to the bridge unadapted, which silently qualified nothing (every bridge
    field read resolved to None) and caused a real production regression, only caught by the
    end-to-end `current_research_ready_count` regression lock, not by a unit test in isolation."""
    rows = [_semantic_row(metric, value, label)
            for label in ("2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2")
            for metric, value in (("revenue", 100), ("profit_before_tax", 10), ("net_income", 8))]
    # A second ticker with no rows at all must not crash or appear with a spurious record.
    qualified = build_qualified_flow_artifact(
        semantic_rows=rows, feature_records={"AAA": _store(), "BBB": _store(ticker="BBB")}, requested_at="t",
    )
    assert qualified["records"]["AAA"]["ttm"]["revenue"]["value"] == 400
    assert "BBB" in qualified["records"]
    artifact = build_scaleout(semantic_rows=[_row("revenue", 999)], feature_records={"AAA": _store()},
                              feature_store_artifact={"artifact_identity": "store:1"}, period_semantics_identity="sem:1",
                              requested_at="t", qualified_flow_artifact=qualified)
    assert artifact["records"]["AAA"]["features"]["revenue_ttm"]["value"] == 400
    assert artifact["scaleout"]["qualified_flow_replaced_raw_flow_rows"] is True


def test_build_qualified_flow_artifact_ignores_rows_with_no_ticker():
    rows = [{"canonical_metric": "revenue", "value": 1}]  # malformed/missing ticker
    qualified = build_qualified_flow_artifact(semantic_rows=rows, feature_records={"AAA": _store()}, requested_at="t")
    assert qualified["records"]["AAA"]["ttm"] == {}


def test_bridge_fact_adapter_recovers_the_fields_the_bridge_actually_reads():
    """Regression guard for the exact bug this milestone found: feeding a reshaped
    structured_financial_period_semantics row to the bridge unadapted makes every field the
    bridge reads resolve to None."""
    row = _semantic_row("revenue", 100.0, "2026-Q1", cumulative_state="period_only")
    adapted = scaleout._bridge_fact(row)
    assert adapted["value"] == 100.0
    assert adapted["status"] == "provider_reported"
    assert adapted["provider"] == "KBS"
    assert adapted["currency"] == "VND"
    assert adapted["scale"] == "ONE"
    assert adapted["reporting_period"] == "2026-Q1"
    assert adapted["cumulative_state"] == "period_only"
    assert bridge._usable(adapted) is True
