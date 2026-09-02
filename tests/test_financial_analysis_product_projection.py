"""Tests for the compact Financial Analysis V2 -> product projection adapter, focused on
CORE_FUNDAMENTAL_VALUATION_AND_PEER_CONTEXT_V1's additions: capital_efficiency_context and
history_context must carry real numeric values, not the status-only shape the pre-existing
free_cash_flow_proxy view uses.
"""
from __future__ import annotations

import pytest

import financial_analysis_engine_v2 as engine
import financial_analysis_product_projection as projection

REQUESTED_AT = "2026-09-02T00:00:00+07:00"


def _artifact(rows, tickers=("AAA",), issuer_types=None):
    issuer_types = issuer_types or {ticker: "corporate" for ticker in tickers}
    return engine.build_artifact(tickers=list(tickers), rows=rows, issuer_types=issuer_types,
                                 source_identities={"semantics": "x"}, requested_at=REQUESTED_AT)


def _row(metric, value, period="2026-Q2", *, ticker="AAA", provider="VCI", semantic="STANDALONE_QUARTER", source=None):
    source = source or f"{ticker}_{provider}_{'income' if semantic == 'STANDALONE_QUARTER' else 'balance'}"
    return {
        "ticker": ticker, "canonical_metric": metric, "reported_value": value,
        "native_period_label": period, "period_end": period, "period_semantic_state": semantic,
        "source_status": "provider_reported", "lineage_complete": True, "source_conflicts": [],
        "statement_scope": "consolidated", "normalized_candidate_unit": {"currency": "unknown", "scale": "unknown"},
        "source_lineage": {"provider": provider, "source_file": source, "source_sha256": "sha-1",
                           "fact_id": f"{metric}-{period}-{provider}"},
    }


def _project(financial_context, tickers=("AAA",)):
    return projection.build_product_projection(financial_context=financial_context, product_tickers=list(tickers),
                                                requested_at=REQUESTED_AT)


def test_capital_efficiency_context_carries_a_real_numeric_value_not_status_only():
    rows = [
        _row("net_income", 15, "2026-Q2"),
        _row("shareholders_equity", 100, "2026-Q2", semantic="POINT_IN_TIME_BALANCE_SHEET"),
        _row("shareholders_equity", 80, "2026-Q1", semantic="POINT_IN_TIME_BALANCE_SHEET"),
    ]
    product = _project(_artifact(rows))
    context = product["records"]["AAA"]["capital_efficiency_context"]
    avg_equity = context["same_provider_roe_avg_equity"]
    eop_proxy = context["same_provider_roe_eop_proxy"]
    assert avg_equity["fitness"] == "READY" and avg_equity["value"] == pytest.approx(15 / 90)
    assert eop_proxy["fitness"] == "READY" and eop_proxy["value"] == pytest.approx(0.15)
    assert avg_equity["value"] != eop_proxy["value"]


def test_capital_efficiency_context_blocked_entry_carries_no_value_but_a_reason():
    rows = [_row("net_income", 15, "2026-Q2"),
           _row("shareholders_equity", 100, "2026-Q2", semantic="POINT_IN_TIME_BALANCE_SHEET")]
    product = _project(_artifact(rows))
    entry = product["records"]["AAA"]["capital_efficiency_context"]["same_provider_roe_avg_equity"]
    assert entry["value"] is None
    assert entry["fitness"] == "BLOCKED_BY_EVIDENCE"
    assert "MISSING_SAME_PROVIDER_CONSECUTIVE_PERIOD_BOUNDARY_BALANCES" in entry["reason_codes"]


def test_history_context_survives_into_compact_projection_with_real_percentile():
    periods = ["2024-Q4", "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"]
    margins = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]
    rows = []
    for margin, period in zip(margins, periods):
        rows.append(_row("revenue", 1000, period))
        rows.append(_row("gross_profit", margin * 1000, period))
    product = _project(_artifact(rows))
    entry = product["records"]["AAA"]["history_context"]["gross_margin"]
    assert entry["status"] == "AVAILABLE"
    assert entry["percentile"] == pytest.approx(1.0)
    assert entry["subject_value"] == pytest.approx(0.40)


def test_absent_ticker_carries_no_capital_efficiency_or_history_keys():
    product = _project(_artifact([_row("net_income", 1)]), tickers=("AAA", "ZZZ"))
    absent = product["records"]["ZZZ"]
    assert absent["status"] == "ABSENT"
    assert "capital_efficiency_context" not in absent
    assert "history_context" not in absent


def test_zero_silent_ticker_drops_preserved_with_new_fields_present():
    product = _project(_artifact([_row("net_income", 1)]))
    assert product["coverage"]["zero_silent_ticker_drops"] is True
    assert "capital_efficiency_context" in product["records"]["AAA"]
