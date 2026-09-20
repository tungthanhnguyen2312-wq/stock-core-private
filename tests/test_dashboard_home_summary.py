"""Focused tests for dashboard_home_summary/v1.

Includes a real retained-artifact parity check against
C:\\Projects\\StockLookup\\market-dashboard\\data\\screener_master_projection.json (the
real 2026-09-18 session) -- the exact numbers this test pins are the same numbers
independently verified live in market-dashboard's own dashboard-product-summary.js
(summarizeScreenerOverview) during MARKET_DASHBOARD_FULL_SURFACE_CONVERGENCE_AND_HOME_
PERFORMANCE_V1 (380 up / 282 down / 194 flat, 44/197/940/28/284/190 stance counts, 956
tactical coverage, 954 liquidity proxy count).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import dashboard_home_summary as dhs


SESSION = "2026-09-18"
REAL_PROJECTION_PATH = Path(r"C:\Projects\StockLookup\market-dashboard\data\screener_master_projection.json")


def _card(*, price_status="PRICE_AVAILABLE", change_pct_status="AVAILABLE", change_pct=0.0,
          tactical_status="AVAILABLE", entry_state="UPTREND_CONFIRMED", stance="WAIT_FOR_CONFIRMATION",
          liquidity_fitness="LIQUIDITY_RESEARCH_PROXY", execution_status="EXECUTION_CAPACITY_EXACT_BLOCKED",
          sector_status="AVAILABLE", sector_label="Ngân hàng"):
    return {
        "price": {"status": price_status, "change_pct_status": change_pct_status, "change_pct": change_pct},
        "tactical": {"status": tactical_status, "entry_state": entry_state},
        "research": {"stance": stance},
        "liquidity": {"fitness": liquidity_fitness},
        "execution": {"capacity_exact_status": execution_status},
        "sector": {"status": sector_status, "label": sector_label},
    }


def _projection(cards, *, session=SESSION, contract_version=dhs.SOURCE_CONTRACT_VERSION):
    denominator = len(cards)
    payload = {
        "contract_version": contract_version,
        "as_of_session": session,
        "cards": cards,
        "coverage": {"ticker_denominator": denominator, "zero_silent_drops": True},
        "official_scope_coverage": None,
        "artifact_identity": "screener_master_projection/v1:test-identity",
    }
    return payload


def test_build_home_summary_rejects_wrong_source_contract_version():
    payload = _projection({"AAA": _card()}, contract_version="wrong/v1")
    with pytest.raises(dhs.DashboardHomeSummaryError, match="SOURCE_CONTRACT_VERSION_MISMATCH"):
        dhs.build_home_summary(payload, requested_at="2026-09-20T00:00:00+07:00")


def test_build_home_summary_rejects_missing_session():
    payload = _projection({"AAA": _card()}, session="")
    with pytest.raises(dhs.DashboardHomeSummaryError, match="SOURCE_SESSION_MISSING"):
        dhs.build_home_summary(payload, requested_at="2026-09-20T00:00:00+07:00")


def test_build_home_summary_rejects_missing_source_identity():
    payload = _projection({"AAA": _card()})
    payload["artifact_identity"] = None
    with pytest.raises(dhs.DashboardHomeSummaryError, match="SOURCE_ARTIFACT_IDENTITY_MISSING"):
        dhs.build_home_summary(payload, requested_at="2026-09-20T00:00:00+07:00")


def test_build_home_summary_rejects_empty_corpus():
    payload = _projection({})
    with pytest.raises(dhs.DashboardHomeSummaryError, match="SOURCE_EMPTY_CORPUS"):
        dhs.build_home_summary(payload, requested_at="2026-09-20T00:00:00+07:00")


def test_build_home_summary_rejects_denominator_mismatch():
    payload = _projection({"AAA": _card(), "BBB": _card()})
    payload["coverage"]["ticker_denominator"] = 1
    with pytest.raises(dhs.DashboardHomeSummaryError, match="SOURCE_DENOMINATOR_MISMATCH"):
        dhs.build_home_summary(payload, requested_at="2026-09-20T00:00:00+07:00")


def test_build_home_summary_never_creates_ranking_score_or_recommendation():
    payload = _projection({"AAA": _card()})
    summary = dhs.build_home_summary(payload, requested_at="2026-09-20T00:00:00+07:00")
    assert summary["blocked_outputs"]["universal_score"] == "SCORING_PROHIBITED"
    assert summary["blocked_outputs"]["ordinal_rank"] == "RANKING_PROHIBITED"
    assert summary["blocked_outputs"]["probability_of_success"] == "FORECAST_PROHIBITED"
    assert summary["blocked_outputs"]["target_price"] == "NOT_EMITTED"
    assert summary["blocked_outputs"]["market_regime"] == "NOT_COMPUTED"
    assert summary["authority_effect"] == "NONE / PRESENTATION_READ_MODEL_ONLY"


def test_breadth_state_is_pure_deterministic_and_descriptive_only():
    assert dhs.breadth_state(600, 100) == "NGHIENG_TANG"
    assert dhs.breadth_state(100, 600) == "NGHIENG_GIAM"
    assert dhs.breadth_state(300, 280) == "GIANG_CO"
    assert dhs.breadth_state(0, 0) == "UNAVAILABLE"
    # 1.2x lean threshold, exact boundary
    assert dhs.breadth_state(120, 100) == "NGHIENG_TANG"
    assert dhs.breadth_state(119, 100) == "GIANG_CO"


def test_content_identity_excludes_volatile_fields_and_is_deterministic():
    payload = _projection({"AAA": _card()})
    summary = dhs.build_home_summary(payload, requested_at="2026-09-20T00:00:00+07:00")
    identity_a = dhs.content_identity(summary)
    later = dict(summary, requested_at="2026-09-21T00:00:00+07:00",
                 artifact_sha256="stale", artifact_identity="stale")
    identity_b = dhs.content_identity(later)
    assert identity_a == identity_b
    assert identity_a["artifact_identity"] == f"{dhs.CONTRACT_VERSION}:{identity_a['artifact_sha256']}"


def test_session_breadth_and_stance_and_tactical_counts_over_a_small_synthetic_cohort():
    cards = {
        "UP1": _card(change_pct=1.0, entry_state="UPTREND_CONFIRMED", stance="INITIATE_RESEARCH_CANDIDATE"),
        "UP2": _card(change_pct=2.0, entry_state="UPTREND_CONFIRMED", stance="ACCUMULATE_RESEARCH_CANDIDATE"),
        "DOWN1": _card(change_pct=-1.0, entry_state="DOWNTREND", stance="AVOID_NEW_ENTRY"),
        "FLAT1": _card(change_pct=0.0, entry_state="SIDEWAYS_NEUTRAL", stance="WAIT_FOR_CONFIRMATION"),
        "NOPRICE": _card(price_status="PRICE_UNAVAILABLE", change_pct_status="UNAVAILABLE",
                          tactical_status="UNAVAILABLE", entry_state=None, stance=None,
                          liquidity_fitness="LIQUIDITY_RESEARCH_UNAVAILABLE",
                          sector_status="UNKNOWN", sector_label=None),
    }
    payload = _projection(cards)
    summary = dhs.build_home_summary(payload, requested_at="2026-09-20T00:00:00+07:00")
    assert summary["denominator"] == 5
    breadth = summary["session_breadth"]
    assert (breadth["up"], breadth["down"], breadth["flat"]) == (2, 1, 1)
    assert breadth["price_available"] == 4
    assert breadth["state"] == dhs.breadth_state(2, 1)
    assert summary["research_stance"]["counts"]["INITIATE_RESEARCH_CANDIDATE"] == 1
    assert summary["research_stance"]["counts"]["ACCUMULATE_RESEARCH_CANDIDATE"] == 1
    assert summary["research_stance"]["counts"]["AVOID_NEW_ENTRY"] == 1
    assert summary["research_stance"]["counts"]["WAIT_FOR_CONFIRMATION"] == 1
    assert summary["tactical"]["coverage"] == 4
    assert summary["liquidity"]["proxy_count"] == 4
    assert summary["sector"]["labeled"] == 4
    assert summary["sector"]["rows"] == [{"label": "Ngân hàng", "count": 4}]


@pytest.mark.skipif(not REAL_PROJECTION_PATH.is_file(), reason="real retained market-dashboard artifact not present in this checkout")
def test_real_retained_artifact_parity_with_live_verified_home_numbers():
    """Cross-checks against the exact figures independently verified live on
    https://tungthanhnguyen2312-wq.github.io/market-dashboard/dashboard.html during
    MARKET_DASHBOARD_FULL_SURFACE_CONVERGENCE_AND_HOME_PERFORMANCE_V1 (same real
    2026-09-18 session, same artifact) -- this is the numerical-parity proof Phase 7/15
    of DASHBOARD_HOME_SUMMARY_AND_CACHE_BUSTING_V1 requires.
    """
    projection = json.loads(REAL_PROJECTION_PATH.read_text(encoding="utf-8"))
    summary = dhs.build_home_summary(projection, requested_at="2026-09-20T00:00:00+07:00")
    assert summary["as_of_session"] == "2026-09-18"
    assert summary["denominator"] == 1683
    breadth = summary["session_breadth"]
    assert (breadth["up"], breadth["down"], breadth["flat"]) == (380, 282, 194)
    assert breadth["price_available"] == 858
    assert breadth["state"] == "NGHIENG_TANG"
    stance = summary["research_stance"]["counts"]
    assert stance == {
        "ACCUMULATE_RESEARCH_CANDIDATE": 197, "AVOID_NEW_ENTRY": 284,
        "HIGH_RISK_SPECULATION_ONLY": 28, "INITIATE_RESEARCH_CANDIDATE": 44,
        "INSUFFICIENT_EVIDENCE": 190, "WAIT_FOR_CONFIRMATION": 940,
    }
    assert summary["tactical"]["coverage"] == 956
    assert summary["liquidity"]["proxy_count"] == 954
    assert summary["liquidity"]["execution_exact_ready"] == 0
    assert summary["sector"]["rows"][0] == {"label": "Xây dựng và Vật liệu", "count": 351}
    # Size gate (Phase 4): well under the 250KB target, actually under the 100KB "prefer" bar.
    encoded = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    assert len(encoded.encode("utf-8")) < 100_000
    old_size = REAL_PROJECTION_PATH.stat().st_size
    assert old_size > 6_000_000
    reduction = 1 - (len(encoded.encode("utf-8")) / old_size)
    assert reduction > 0.999
