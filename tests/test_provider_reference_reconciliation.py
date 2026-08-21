"""Focused provider-reference reconciliation regressions."""
from __future__ import annotations

from provider_reference_reconciliation import (
    BASIS_UNRESOLVED,
    CLOSED_SESSION_OBSERVATION,
    EXACT_MATCH,
    FHSC_CAPABILITY_PROFILES,
    FINALIZATION_MISMATCH,
    FINALIZATION_STATUS_UNKNOWN,
    MISSING_SOURCE_OBSERVATION,
    NOT_COMPARABLE,
    SEMANTICS_RESOLVED,
    SESSION_MISMATCH,
    SHADOW_REFERENCE_PROVIDER,
    TIMESTAMP_SEMANTICS_UNRESOLVED,
    UNIT_MISMATCH,
    UNKNOWN_SEMANTICS,
    VALUE_MISMATCH,
    build_offline_artifact,
    provider_reference_observation,
    reconcile_observations,
)


def _observation(provider: str, value: float = 10.0, **changes: object) -> dict:
    values: dict[str, object] = {
        "provider": provider,
        "provider_interface": "test_interface",
        "endpoint_capability": "stock_history_1d",
        "instrument": "HPG",
        "exchange": "HOSE",
        "session": "2026-08-20",
        "event_time": "2026-08-20T08:00:00+07:00",
        "retrieval_time": "2026-08-20T17:20:00+07:00",
        "field": "close",
        "raw_value": value,
        "normalized_value": value,
        "unit": "VND_PER_SHARE",
        "basis": "ADJUSTED_RETROSPECTIVE",
        "semantic_status": SEMANTICS_RESOLVED,
        "finalization_status": CLOSED_SESSION_OBSERVATION,
        "source_payload_identity": f"{provider.lower()}:payload",
        "source_payload_sha256": "a" * 64,
        "missing_disposition": "OBSERVED",
        "provenance": {"test": True},
        "source_role": SHADOW_REFERENCE_PROVIDER,
    }
    values.update(changes)
    return provider_reference_observation(**values)


def test_exact_match_and_value_mismatch() -> None:
    assert reconcile_observations([_observation("DNSE"), _observation("FHSC")])["verdict"] == EXACT_MATCH
    assert reconcile_observations([_observation("DNSE"), _observation("FHSC", 11.0)])["verdict"] == VALUE_MISMATCH


def test_missing_source_is_not_a_value_mismatch() -> None:
    result = reconcile_observations([_observation("DNSE")])
    assert result["verdict"] == MISSING_SOURCE_OBSERVATION
    assert result["missing_providers"] == ["FHSC"]


def test_basis_and_unit_mismatch_fail_closed() -> None:
    basis = reconcile_observations([_observation("DNSE"), _observation("FHSC", semantic_status=BASIS_UNRESOLVED)])
    unit = reconcile_observations([_observation("DNSE"), _observation("FHSC", unit="THOUSAND_VND_PER_SHARE")])
    assert basis["verdict"] == BASIS_UNRESOLVED
    assert unit["verdict"] == UNIT_MISMATCH


def test_session_and_finalization_mismatch_fail_closed() -> None:
    session = reconcile_observations([_observation("DNSE"), _observation("FHSC", session="2026-08-19")])
    current = reconcile_observations([_observation("DNSE"), _observation("FHSC", finalization_status=FINALIZATION_STATUS_UNKNOWN)])
    assert session["verdict"] == SESSION_MISMATCH
    assert current["verdict"] == FINALIZATION_MISMATCH


def test_timestamp_and_unknown_semantics_fail_closed() -> None:
    timestamp = reconcile_observations([_observation("DNSE"), _observation("FHSC", retrieval_time=None)])
    semantics = reconcile_observations([_observation("DNSE"), _observation("FHSC", semantic_status=UNKNOWN_SEMANTICS)])
    assert timestamp["verdict"] == TIMESTAMP_SEMANTICS_UNRESOLVED
    assert semantics["verdict"] == UNKNOWN_SEMANTICS


def test_fhsc_volume_decomposition_remains_explicit_and_non_inherited() -> None:
    profiles = {profile["capability"]: profile for profile in FHSC_CAPABILITY_PROFILES}
    for capability in ("stock_trading", "stock_trading_history"):
        fields = profiles[capability]["fields"]
        assert {"matched_volume", "put_through_volume", "total_volume"} <= set(fields)
        assert profiles[capability]["volume_semantics"]["matched_plus_put_through_equals_total"] == "OBSERVED_CONNECTOR_BEHAVIOR_NOT_AUTHORITY"
    result = reconcile_observations([
        _observation("DNSE", field="total_volume", unit="SHARES", semantic_status=BASIS_UNRESOLVED),
        _observation("FHSC", field="total_volume", unit="SHARES", semantic_status=BASIS_UNRESOLVED),
    ])
    assert result["verdict"] == BASIS_UNRESOLVED


def test_fhsc_financial_fields_are_reference_only() -> None:
    profile = next(profile for profile in FHSC_CAPABILITY_PROFILES if profile["capability"] == "financial_statement")
    assert profile["financial_authority"] == "PROVIDER_REFERENCE_DESCRIPTIVE_ONLY"
    assert profile["canonical_fact_mapping"].startswith("PROHIBITED")


def test_provider_majority_never_creates_authority() -> None:
    result = reconcile_observations([
        _observation("DNSE", 10.0), _observation("FHSC", 11.0),
        _observation("VCI", 11.0), _observation("KBS", 11.0),
    ])
    assert result["verdict"] == VALUE_MISMATCH
    assert result["authority_effect"] == "NONE"
    assert result["selected_provider"] is None
    assert result["authoritative_value"] is None


def test_source_order_does_not_change_identity_or_result() -> None:
    rows = [_observation("DNSE"), _observation("FHSC")]
    assert reconcile_observations(rows) == reconcile_observations(reversed(rows))


def test_duplicate_provider_observations_are_not_silently_selected() -> None:
    result = reconcile_observations([_observation("DNSE"), _observation("DNSE", 11.0), _observation("FHSC")])
    assert result["verdict"] == NOT_COMPARABLE
    assert result["reason"] == "multiple_observations_for_comparison_provider"


def test_offline_replay_is_deterministic_and_authority_neutral() -> None:
    first = build_offline_artifact()
    second = build_offline_artifact()
    assert first == second
    # The offline artifact is deterministic for a fixed local credential state;
    # it must not assume an operator-approved secret file stays unconfigured.
    assert first["fhsc_credential_state"]["secrets_file_consulted"] is True
    assert first["real_probe"]["network_requests"] == 0
    assert len(first["dnse_retained_observations"]) == 3
    assert all(row["verdict"] == MISSING_SOURCE_OBSERVATION for row in first["reconciliation_rows"])
    assert first["authority_boundaries"] == {
        "fhsc_promoted": False, "dnse_replaced": False, "legacy_provider_retired": False,
        "raw_as_traded_promoted": False, "liquidity_sizing_promoted": False,
        "provider_fundamentals_promoted": False, "canonical_facts_created": 0,
        "valuation_or_recommendation_authority_created": False, "runtime_or_database_mutated": False,
    }
