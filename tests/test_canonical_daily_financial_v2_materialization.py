"""Tests for canonical_daily_financial_v2_materialization.py (CANONICAL_DAILY_FINANCIAL_V2_
AND_CURRENT_RESEARCH_ENRICHMENT_V1): canonical daily Financial V2 engine + compact product +
peer context + evaluated valuation, over the Daily Product's own ticker denominator.

The engine build reads ~68k retained semantic facts across ~1,492 tickers (~20s); it is built
ONCE per test session via a module-scoped fixture and reused read-only by every test below.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import canonical_daily_financial_v2_materialization as materialization
import financial_v2_current_input_authority as auth

ROOT = Path(__file__).resolve().parents[1]
REQUESTED_AT = "2026-09-02T15:00:00+07:00"


@pytest.fixture(scope="module")
def authority():
    return auth.resolve(ROOT)


@pytest.fixture(scope="module")
def engine_artifact(authority):
    return materialization.build_engine_artifact(root=ROOT, requested_at=REQUESTED_AT, authority=authority)


# --- 1. canonical current Financial V2 resolver + correct engine/product contract ---

def test_engine_artifact_reproduces_regression_locked_figures(engine_artifact):
    """Real retained-evidence smoke test: reproduces the CORE_FUNDAMENTAL_VALUATION_AND_
    PEER_CONTEXT_V1 regression lock exactly (1,492 denominator, 1,380 current_research_ready)."""
    assert engine_artifact["contract_version"] == "financial_analysis_context/v2"
    assert engine_artifact["coverage"]["ticker_denominator"] == 1492
    assert engine_artifact["coverage"]["current_research_ready_count"] == 1380


def test_engine_artifact_identity_independent_of_requested_at(authority):
    """Same underlying evidence must reproduce a byte-identical engine identity regardless of
    which decision session/time requested it -- financial evidence is periodic, not daily."""
    a = materialization.build_engine_artifact(root=ROOT, requested_at="2026-08-25T15:00:00+07:00", authority=authority)
    b = materialization.build_engine_artifact(root=ROOT, requested_at="2026-08-28T15:00:00+07:00", authority=authority)
    assert a["artifact_identity"] == b["artifact_identity"]


# --- 2. full Daily denominator projection with explicit ABSENT records; zero silent drops ---

def test_compact_product_projects_over_full_daily_denominator_with_zero_silent_drops(engine_artifact):
    engine_tickers = sorted(engine_artifact["records"])
    daily_denominator = engine_tickers + ["ZZZNOTREAL1", "ZZZNOTREAL2"]
    product = materialization.build_compact_product(
        engine_artifact=engine_artifact, product_tickers=daily_denominator, requested_at=REQUESTED_AT,
    )
    assert set(product["records"]) == set(daily_denominator)
    assert product["coverage"]["zero_silent_ticker_drops"] is True
    assert product["records"]["ZZZNOTREAL1"]["status"] == "ABSENT"
    assert product["coverage"]["absent_coverage"] == 2
    assert product["coverage"]["compact_coverage"] == len(engine_tickers)


def test_compact_product_is_the_flat_shape_evaluate_fundamental_direction_reads(engine_artifact):
    """Real ticker: the compact record must expose the exact flat keys
    integrated_investment_decision_product.evaluate_fundamental_direction() reads directly."""
    product = materialization.build_compact_product(
        engine_artifact=engine_artifact, product_tickers=["HPG"], requested_at=REQUESTED_AT,
    )
    assert product["contract_version"] == "financial_analysis_product_integration/v1"
    record = product["records"]["HPG"]
    assert record["contract_version"] == "financial_analysis_compact/v1"
    assert record["status"] == "AVAILABLE"
    for key in ("profitability_state", "margin_state", "growth_state", "earnings_turnaround_state",
                "cash_conversion_state", "balance_sheet_state", "leverage_state",
                "working_capital_trajectory_state", "gross_margin_trajectory_state"):
        assert key in record


# --- 3. fundamental peer-method compatibility (sector/industry, entity-class fallback) ---

def test_peer_context_covers_the_full_engine_cohort(engine_artifact, authority):
    peer_context = materialization.build_peer_context(engine_artifact=engine_artifact, authority=authority)
    assert set(peer_context) == set(engine_artifact["records"])
    # At least one already-READY-capable metric resolves a real sector cohort for a real name.
    hpg_peers = peer_context["HPG"]
    assert "gross_margin" in hpg_peers


def test_peer_context_degrades_to_entity_class_fallback_without_industry_snapshot(engine_artifact, authority, tmp_path):
    """Missing/absent industry snapshot must never block peer context -- only narrow the
    cohort to the entity-class fallback (current_research_valuation_context's own contract)."""
    broken = auth.FinancialV2InputAuthority(
        authority_version=authority.authority_version,
        semantics_dir=authority.semantics_dir, feature_store_dir=authority.feature_store_dir,
        classification_dir=authority.classification_dir,
        semantics_artifact_path=authority.semantics_artifact_path,
        semantics_facts_path=authority.semantics_facts_path,
        feature_store_artifact_path=authority.feature_store_artifact_path,
        feature_store_records_path=authority.feature_store_records_path,
        classification_diagnostics_path=authority.classification_diagnostics_path,
        industry_snapshot_path=tmp_path / "does_not_exist.json",
        expected_semantics_identity=authority.expected_semantics_identity,
        expected_feature_store_identity=authority.expected_feature_store_identity,
        expected_classification_diagnostics_identity=authority.expected_classification_diagnostics_identity,
    )
    peer_context = materialization.build_peer_context(engine_artifact=engine_artifact, authority=broken)
    assert set(peer_context) == set(engine_artifact["records"])


# --- 4. valuation proxy vs exact distinction (evaluated shape, not the raw price/EPS artifact) ---

def test_evaluated_valuation_artifact_is_the_shape_the_decision_engine_needs(engine_artifact):
    raw_valuation = {
        "artifact_identity": "market_wide_current_valuation/v1:fake",
        "records": {"HPG": {"share_basis_input": {}, "metrics": {}}},
    }
    valuation = materialization.build_evaluated_valuation_artifact(
        engine_artifact=engine_artifact, raw_valuation_artifact=raw_valuation,
        product_tickers=["HPG"], requested_at=REQUESTED_AT,
    )
    assert valuation["contract_version"] == "current_research_valuation_context/v1"
    row = valuation["records"]["HPG"]
    assert "methods" in row
    assert "peer_relative_context" not in row  # attach_peer_relative attaches peer_relative/relative_research_state, not this key
    assert "peer_relative" in row
    assert "relative_research_state" in row


def test_evaluated_valuation_handles_missing_raw_valuation_without_raising(engine_artifact):
    valuation = materialization.build_evaluated_valuation_artifact(
        engine_artifact=engine_artifact, raw_valuation_artifact=None,
        product_tickers=["HPG"], requested_at=REQUESTED_AT,
    )
    assert valuation["records"]["HPG"]["methods"]["P/E"]["status"] in ("INPUT_BLOCKED", "NOT_APPLICABLE")


# --- 5. financial period != decision session semantics; session-delivery identity ---

def test_session_artifact_binds_decision_session_distinct_from_financial_evidence_identity(engine_artifact):
    session_artifact = materialization.build_session_artifact(
        root=ROOT, decision_session="2026-08-25", product_tickers=["HPG", "VCB"],
        requested_at=REQUESTED_AT, engine_artifact=engine_artifact,
    )
    assert session_artifact["decision_session"] == "2026-08-25"
    assert session_artifact["financial_v2_engine_identity"] == engine_artifact["artifact_identity"]
    assert session_artifact["financial_evidence_as_of_period"] is not None
    assert session_artifact["temporal_semantics"]["financial_evidence_is_periodic"] is True


def test_financial_evidence_identity_stable_but_wrapper_identity_differs_across_sessions(engine_artifact):
    """Section 20: financial evidence can legitimately be identical across sessions while the
    decision-session-bound wrapper's own identity still changes."""
    first = materialization.build_session_artifact(
        root=ROOT, decision_session="2026-08-25", product_tickers=["HPG", "VCB"],
        requested_at="2026-08-25T15:00:00+07:00", engine_artifact=engine_artifact,
    )
    second = materialization.build_session_artifact(
        root=ROOT, decision_session="2026-08-28", product_tickers=["HPG", "VCB"],
        requested_at="2026-08-28T15:00:00+07:00", engine_artifact=engine_artifact,
    )
    assert first["financial_v2_engine_identity"] == second["financial_v2_engine_identity"]
    assert first["financial_content_identity"] == second["financial_content_identity"]
    assert first["artifact_identity"] != second["artifact_identity"]


def test_session_artifact_zero_silent_drops_over_superset_denominator(engine_artifact):
    daily_denominator = sorted(engine_artifact["records"]) + ["ZZZNOTREAL1"]
    session_artifact = materialization.build_session_artifact(
        root=ROOT, decision_session="2026-09-02", product_tickers=daily_denominator,
        requested_at=REQUESTED_AT, engine_artifact=engine_artifact,
    )
    assert session_artifact["coverage"]["decision_denominator"] == len(daily_denominator)
    assert session_artifact["coverage"]["zero_silent_ticker_drops"] is True
    assert session_artifact["coverage"]["financial_product_absent"] == 1


# --- 6. no ticker hardcoding ---

def test_no_ticker_hardcoded_in_materialization_module():
    source = (ROOT / "canonical_daily_financial_v2_materialization.py").read_text(encoding="utf-8")
    for ticker in ("HPG", "VCB", "SSI", "PNJ", "FPT", "PVD", "QNS"):
        assert f'"{ticker}"' not in source
        assert f"'{ticker}'" not in source
