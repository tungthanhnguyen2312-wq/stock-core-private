"""Regression guards for the V2 compact product / AI integration boundary."""
from __future__ import annotations

import json

import pytest

import financial_analysis_engine_v2 as engine
from financial_analysis_product_projection import (
    FinancialAnalysisProductProjectionError, build_product_projection, context_for_ticker,
)
from security_decision_context import _financial_analysis_annotation
from ai_research_session_delivery import build_delivery
from export_ai_bundle import attach_financial_analysis_v2_product_context


def _row(metric, value, *, provider="KBS", semantic="STANDALONE_QUARTER"):
    return {
        "ticker": "AAA", "canonical_metric": metric, "reported_value": value, "native_period_label": "2026-Q2",
        "period_end": "2026-Q2", "period_semantic_state": semantic, "source_status": "provider_reported",
        "lineage_complete": True, "source_conflicts": [], "statement_scope": "consolidated",
        "normalized_candidate_unit": {"currency": "VND", "scale": "ONE"},
        "source_lineage": {"provider": provider, "source_file": f"{provider}-{metric}", "source_sha256": "x", "fact_id": metric},
    }


def _engine():
    return engine.build_artifact(tickers=["AAA"], rows=[_row("revenue", 100), _row("net_income", 10)],
                                 issuer_types={"AAA": "corporate"}, source_identities={"retained": "x"}, requested_at="t")


def _product():
    return build_product_projection(financial_context=_engine(), product_tickers=["BBB", "AAA"], requested_at="t")


def test_compact_projection_preserves_proxy_and_explicit_absence_without_raw_records():
    product = _product()
    aaa, bbb = product["records"]["AAA"], product["records"]["BBB"]
    assert product["coverage"] == {"ticker_denominator": 2, "compact_coverage": 1, "absent_coverage": 1, "zero_silent_ticker_drops": True}
    assert aaa["contract_version"] == "financial_analysis_compact/v1"
    assert aaa["feature_fitness"]["mixed_provider_roa_proxy"]["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert "features" not in aaa and "reported_value" not in json.dumps(aaa)
    assert bbb["status"] == "ABSENT" and bbb["reason"] == "FA_V2_CONTEXT_ABSENT"
    assert all(record["is_actionable"] is False for record in product["records"].values())


def test_raw_engine_is_rejected_and_proxy_never_becomes_supporting_evidence():
    with pytest.raises(FinancialAnalysisProductProjectionError, match="RAW_FINANCIAL_ENGINE_RECORD_REJECTED"):
        context_for_ticker(_engine(), "AAA")
    compact = _product()["records"]["AAA"]
    compact["cash_conversion_state"] = "HEALTHY"
    annotation = _financial_analysis_annotation(compact)
    assert "FA_V2_CASH_CONVERSION_HEALTHY" not in annotation["supporting"]
    assert "FA_V2_CASH_CONVERSION_PROXY_NOT_READY" in annotation["missing_dimensions"]


def test_export_opt_in_is_off_without_io_and_on_requires_valid_explicit_context(tmp_path):
    entries = {"AAA": {}}
    assert attach_financial_analysis_v2_product_context(entries, False, str(tmp_path / "does-not-exist.json")) is None
    path = tmp_path / "context.json"
    path.write_text(json.dumps(_product()), encoding="utf-8")
    attached = attach_financial_analysis_v2_product_context(entries, True, str(path))
    assert attached and entries["AAA"]["financial_analysis"]["status"] == "AVAILABLE"
    with pytest.raises(ValueError, match="PATH_REQUIRED"):
        attach_financial_analysis_v2_product_context({}, True, None)


def test_compact_projection_exposes_working_capital_states_not_raw_amounts():
    current_assets = _row("current_assets", 700, provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET")
    current_liabilities = _row("current_liabilities", 350, provider="VCI", semantic="POINT_IN_TIME_BALANCE_SHEET")
    # Both balance-sheet lines come from the same retained payload/source file in production;
    # `_row()` defaults each metric to a distinct file, so align them for a same-representation pair.
    current_liabilities["source_lineage"]["source_file"] = current_assets["source_lineage"]["source_file"]
    rows = [_row("revenue", 100), _row("net_income", 10), current_assets, current_liabilities]
    context = engine.build_artifact(tickers=["AAA"], rows=rows, issuer_types={"AAA": "corporate"},
                                    source_identities={"retained": "x"}, requested_at="t")
    product = build_product_projection(financial_context=context, product_tickers=["AAA"], requested_at="t")
    compact = product["records"]["AAA"]
    assert compact["working_capital_state"] == "POSITIVE_NET_WORKING_CAPITAL"
    assert compact["feature_fitness"]["current_ratio"]["fitness"] == "READY"
    # The compact contract exposes qualitative state/fitness only, never the raw statement figures.
    assert "700" not in json.dumps(compact) and "350" not in json.dumps(compact)


def test_delivery_attaches_compact_after_slim_and_retains_absent_ndjson_context():
    product = _product()
    operation = {"product": {"artifact_identity": "p", "authority_boundary": {}, "market_brief": {}, "macro_context": {},
        "research_cohorts": {}, "high_priority_full_universe_review_set": {}, "watchlist": {}, "aggregate_validation": {"entry_relevant_90_count": 0},
        "detailed_research_cards": {"AAA": {"ticker": "AAA"}}, "risk_data_gap_panel": {}, "what_to_verify_next": [], "source_artifact_identities": {}},
        "manifest": {"market_session": "2026-08-28", "operation_identity": "o", "producer_head": "h", "consumer_head": "c", "input_artifacts": {}, "outputs": {}, "warnings": [], "session_coherence": {}, "coverage_summary": {}},
        "peer": {}, "scenario": {}, "strategy": {}}
    inputs = {"descriptive": {"records": {"AAA": {}, "BBB": {}}}, "tactical": {}, "fundamental": {}, "valuation": {},
              "market_flow_positioning": {}, "corporate_intelligence": {}, "financial_analysis_product_context": product}
    delivery = build_delivery(operation, inputs)
    rows = {row["ticker"]: row for row in map(json.loads, delivery["full_universe"].decode().splitlines())}
    assert rows["AAA"]["financial_analysis"]["status"] == "AVAILABLE"
    assert rows["AAA"]["financial_analysis"]["deterministic_positive_evidence"] == ["AAA: profitable retained net income"]
    assert rows["BBB"]["financial_analysis"]["status"] == "ABSENT"
    assert "lineage" not in rows["AAA"]["financial_analysis"]
