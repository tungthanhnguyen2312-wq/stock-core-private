"""Focused tests for CANONICAL_RECURRING_DECISION_CONTEXT_MATERIALIZATION_V1.

Covers the two new recurring axis materializers in canonical_current_product_projections.py:
``materialize_current_fundamental_feature_store_context`` (rebuilt fresh every run from the
pinned, versioned ``financial_v2_current_input_authority`` semantics chain -- never the module's
own frozen DEFAULT_SEMANTICS, never the detached one-off snapshot) and
``materialize_current_tactical_behavior_context`` (rebuilt from exact-session registry/retained
inputs only, fail-closed on any mandatory gap or session mismatch, never a historical fallback).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import canonical_current_product_projections as ccpp
import market_wide_fundamental_feature_store as feature_store_module
import tactical_behavior_context as compact_module
from test_tactical_behavior_context import (
    SESSION as TACTICAL_SESSION,
    _descriptive_source, _leadership_source, _p3f9b_snapshot,
)
import current_market_screening_opportunity_comparison_foundation as screening_module
import market_wide_current_descriptive_research as descriptive_module
import tactical_confirmation_invalidation_boundaries as boundaries_module
import tactical_setup_tags as tags_module
import technical_structure_context as structure_module
import watchlist_tactical_entry_classifier as tactical_module

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Fundamental feature store: real evidence, pinned authority, non-session-bound
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real_feature_store_result():
    return ccpp.materialize_current_fundamental_feature_store_context(
        root=ROOT, requested_at="2026-09-12T00:00:00+07:00",
    )


def test_fundamental_feature_store_materializes_from_current_pinned_authority(real_feature_store_result):
    result = real_feature_store_result
    assert result["status"] == "MATERIALIZED"
    artifact = result["artifact"]
    assert artifact["contract_version"] == "market_wide_fundamental_feature_store/v1"
    coverage = artifact["coverage"]
    assert coverage["ticker_denominator"] > 0
    assert coverage["zero_silent_ticker_drops"] is True
    assert coverage["tickers_with_ready_feature"] > 0
    # Never the module's own frozen 2026-08-31 constant, never the pinned 2026-08-31 Feature
    # Store snapshot Financial V2 separately verifies for its own internal entity-type join.
    assert result["financial_input_authority"]["semantics_dir"] != "market-wide-structured-financial-period-semantics-v1-20260831"
    assert result["source_semantics_identity"] != feature_store_module.DEFAULT_SEMANTICS
    assert artifact["artifact_identity"] != result["financial_input_authority"]["expected_feature_store_identity"]
    assert artifact["authority_effect"] == "NONE / OPERATIONAL_PROVIDER_RESEARCH_ONLY"


def test_fundamental_feature_store_wallclock_excluded_from_identity(real_feature_store_result):
    other = ccpp.materialize_current_fundamental_feature_store_context(
        root=ROOT, requested_at="2099-01-01T00:00:00+07:00",
    )
    assert other["status"] == "MATERIALIZED"
    assert other["artifact"]["artifact_identity"] == real_feature_store_result["artifact"]["artifact_identity"]


def test_fundamental_feature_store_deterministic_across_repeated_builds(real_feature_store_result):
    again = ccpp.materialize_current_fundamental_feature_store_context(
        root=ROOT, requested_at="2026-09-12T00:00:00+07:00",
    )
    assert again["artifact"]["artifact_identity"] == real_feature_store_result["artifact"]["artifact_identity"]
    assert again["artifact"]["coverage"] == real_feature_store_result["artifact"]["coverage"]


def test_fundamental_feature_store_records_are_non_authoritative(real_feature_store_result):
    records = real_feature_store_result["artifact"]["records"]
    sample = next(iter(records.values()))
    assert sample["authority_boundary"] == {"authoritative": False, "pit": False, "actionable": False}
    for feature in sample["features"].values():
        assert feature["authoritative_financial_eligible"] is False
        assert feature["is_actionable"] is False


def test_fundamental_feature_store_missing_authority_returns_unavailable_never_raises(tmp_path):
    result = ccpp.materialize_current_fundamental_feature_store_context(
        root=tmp_path, requested_at="2026-09-12T00:00:00+07:00",
    )
    assert result["status"] == "UNAVAILABLE"
    assert result["reason_code"] == "FUNDAMENTAL_FEATURE_SEMANTICS_SOURCE_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Tactical behavior: exact-session only, fail-closed, bounded optional degradation
# ---------------------------------------------------------------------------

def _tactical_fixture():
    """Build a genuinely valid, self-consistent tactical/technical/setup chain via the REAL
    upstream modules (mirrors test_tactical_behavior_context.py's own proven fixture)."""
    p3f9b = _p3f9b_snapshot()
    descriptive_draft = _descriptive_source()
    descriptive_draft["input_lineage"]["p3f9b_snapshot_identity"] = p3f9b["snapshot_identity"]
    descriptive = {**descriptive_draft, **descriptive_module.content_identity(descriptive_draft)}
    screening = screening_module.build_artifact(descriptive)
    technical_structure = structure_module.build_artifact(
        current_descriptive=descriptive, p3f9b_snapshot=p3f9b, requested_at="2026-08-31T00:00:00+00:00",
    )
    tactical_records = {ticker: {"entry_state": "BREAKOUT_READY", "rule_id": "R_FIXTURE"} for ticker in descriptive["records"]}
    tactical_source = {
        "schema_version": "1.0.0", "contract_version": "watchlist_tactical_entry_classifier/v1", "session": TACTICAL_SESSION,
        "source_artifacts": {"descriptive": descriptive["artifact_identity"]}, "records": tactical_records,
    }
    tactical = {**tactical_source, **tactical_module.content_identity(tactical_source)}
    leadership = _leadership_source()
    setup_tags = tags_module.build_artifact(
        technical_structure=technical_structure, current_descriptive=descriptive, current_screening=screening,
        current_leadership=leadership, tactical=tactical, requested_at="2026-08-31T00:00:00+00:00",
    )
    boundaries = boundaries_module.build_artifact(
        tactical=tactical, current_descriptive=descriptive, technical_structure=technical_structure,
        requested_at="2026-08-31T00:00:00+00:00",
    )
    return {
        "tactical": tactical, "technical_structure": technical_structure, "tactical_setup_tags": setup_tags,
        "tactical_boundaries": boundaries, "leadership": leadership,
    }


def _registry_and_supplementary(fixture):
    registry_inputs = {"tactical": fixture["tactical"]}
    supplementary = {
        "technical_structure": fixture["technical_structure"],
        "tactical_setup_tags": fixture["tactical_setup_tags"],
        "tactical_boundaries": fixture["tactical_boundaries"],
        "leadership": fixture["leadership"],
    }
    return registry_inputs, supplementary


def test_tactical_behavior_materializes_with_all_inputs_present():
    fixture = _tactical_fixture()
    registry_inputs, supplementary = _registry_and_supplementary(fixture)
    result = ccpp.materialize_current_tactical_behavior_context(
        session=TACTICAL_SESSION, registry_inputs=registry_inputs, supplementary=supplementary,
        requested_at="2026-08-31T00:00:00+00:00",
    )
    assert result["status"] == "MATERIALIZED"
    artifact = result["artifact"]
    assert artifact["contract_version"] == "tactical_behavior_context/v1"
    assert artifact["session"] == TACTICAL_SESSION
    for ticker, record in artifact["records"].items():
        assert record["primary_entry_state"] == fixture["tactical"]["records"][ticker]["entry_state"]
    assert artifact["blocked_outputs"]["opportunity_score"] == "SCORING_PROHIBITED"


def test_tactical_behavior_optional_boundaries_and_leadership_absent_still_materializes():
    fixture = _tactical_fixture()
    registry_inputs, supplementary = _registry_and_supplementary(fixture)
    supplementary["tactical_boundaries"] = None
    supplementary["leadership"] = None
    result = ccpp.materialize_current_tactical_behavior_context(
        session=TACTICAL_SESSION, registry_inputs=registry_inputs, supplementary=supplementary,
        requested_at="2026-08-31T00:00:00+00:00",
    )
    assert result["status"] == "MATERIALIZED"
    artifact = result["artifact"]
    for record in artifact["records"].values():
        assert record["data_coverage"]["leadership_context_available"] is False
        assert record["data_coverage"]["boundary_available"] is False
        assert record["confirmation_boundary"]["reason"] == "BOUNDARY_ARTIFACT_NOT_SUPPLIED"


@pytest.mark.parametrize("missing_key", ["technical_structure", "tactical_setup_tags"])
def test_tactical_behavior_mandatory_input_missing_returns_unavailable(missing_key):
    fixture = _tactical_fixture()
    registry_inputs, supplementary = _registry_and_supplementary(fixture)
    supplementary[missing_key] = None
    result = ccpp.materialize_current_tactical_behavior_context(
        session=TACTICAL_SESSION, registry_inputs=registry_inputs, supplementary=supplementary,
        requested_at="2026-08-31T00:00:00+00:00",
    )
    assert result["status"] == "UNAVAILABLE"
    assert result["reason_code"] == "TACTICAL_BEHAVIOR_MANDATORY_INPUT_MISSING"


def test_tactical_behavior_registry_tactical_missing_returns_unavailable():
    fixture = _tactical_fixture()
    _, supplementary = _registry_and_supplementary(fixture)
    result = ccpp.materialize_current_tactical_behavior_context(
        session=TACTICAL_SESSION, registry_inputs={}, supplementary=supplementary,
        requested_at="2026-08-31T00:00:00+00:00",
    )
    assert result["status"] == "UNAVAILABLE"
    assert result["reason_code"] == "TACTICAL_BEHAVIOR_MANDATORY_INPUT_MISSING"


def test_tactical_behavior_session_mismatch_fails_closed_no_fallback():
    fixture = _tactical_fixture()
    registry_inputs, supplementary = _registry_and_supplementary(fixture)
    result = ccpp.materialize_current_tactical_behavior_context(
        session="2026-09-11",  # the Daily-requested session differs from the fixture's own
        registry_inputs=registry_inputs, supplementary=supplementary,
        requested_at="2026-08-31T00:00:00+00:00",
    )
    assert result["status"] == "UNAVAILABLE"
    assert result["reason_code"] == "TACTICAL_SESSION_MISMATCH"
    assert result["detail"] == {"expected": "2026-09-11", "observed": TACTICAL_SESSION}


def test_tactical_behavior_ticker_set_mismatch_returns_unavailable_not_raised():
    fixture = _tactical_fixture()
    registry_inputs, supplementary = _registry_and_supplementary(fixture)
    corrupted_structure = dict(fixture["technical_structure"])
    corrupted_records = dict(corrupted_structure["records"])
    corrupted_records.pop(next(iter(corrupted_records)))
    corrupted_structure["records"] = corrupted_records
    supplementary["technical_structure"] = corrupted_structure
    result = ccpp.materialize_current_tactical_behavior_context(
        session=TACTICAL_SESSION, registry_inputs=registry_inputs, supplementary=supplementary,
        requested_at="2026-08-31T00:00:00+00:00",
    )
    assert result["status"] == "UNAVAILABLE"
    assert result["reason_code"] in (
        "TECHNICAL_STRUCTURE_IDENTITY_MISMATCH", "TICKER_SET_MISMATCH_ACROSS_SOURCES",
    )


def test_tactical_behavior_repeated_build_is_deterministic():
    fixture = _tactical_fixture()
    registry_inputs, supplementary = _registry_and_supplementary(fixture)
    first = ccpp.materialize_current_tactical_behavior_context(
        session=TACTICAL_SESSION, registry_inputs=registry_inputs, supplementary=supplementary,
        requested_at="2026-08-31T00:00:00+00:00",
    )
    second = ccpp.materialize_current_tactical_behavior_context(
        session=TACTICAL_SESSION, registry_inputs=registry_inputs, supplementary=supplementary,
        requested_at="2026-08-31T00:00:00+00:00",
    )
    assert first["artifact"]["artifact_identity"] == second["artifact"]["artifact_identity"]


def test_tactical_behavior_no_historical_dated_path_referenced_in_orchestration_source():
    """Static guard: no glob/mtime/hardcoded-dated fallback in the orchestration module."""
    source = (ROOT / "canonical_current_product_projections.py").read_text(encoding="utf-8")
    for forbidden in ("glob(", "rglob(", "getmtime", "-20260831", "-20260828"):
        assert forbidden not in source, f"forbidden pattern found: {forbidden}"
