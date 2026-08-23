import hashlib
import json

import pytest

from current_universe_status_and_session_coverage_resolution import (
    ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION,
    ACTIVE_LISTED_OBSERVED,
    INACTIVE_OR_DELISTED,
    NOT_APPLICABLE_NON_EQUITY,
    UNKNOWN,
    UNSUPPORTED_OR_INVALID_PROVIDER_SYMBOL,
    CurrentUniverseStatusResolutionError,
    build_artifact,
)
from field_temporal_contract import stable_id as p3f9b_stable_id


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def breadth_foundation(records):
    payload = {
        "records": records,
        "observed_session_cohort": {"coverage_ratio": 0.5},
    }
    digest = _hash(payload)
    return {**payload, "artifact_sha256": digest, "artifact_identity": f"current_market_universe_breadth_foundation:{digest}"}


def p3f9b_snapshot(records, *, resolved_completed_session="2026-08-21"):
    payload = {"records": records, "resolved_completed_session": resolved_completed_session}
    digest = p3f9b_stable_id(payload)
    return {**payload, "snapshot_sha256": digest, "snapshot_identity": f"p3f9_exact_session_snapshot:{digest}"}


def vci_snapshot(records):
    payload = {"records": records}
    digest = _hash(payload)
    return {**payload, "snapshot_sha256": digest, "snapshot_identity": f"vci_exchange_reference_snapshot:{digest}"}


def _bf_record(ticker, *, membership_state="INCLUDED", membership_reason_code="CURRENT_REFERENCE_EQUITY_CANDIDATE",
               instrument_class="EQUITY", session_observation_state="OBSERVED", disposition="EXACT_SESSION_RETAINED"):
    return {
        "ticker": ticker, "membership_state": membership_state, "membership_reason_code": membership_reason_code,
        "instrument_class": instrument_class, "session_observation_state": session_observation_state,
        "source_session_disposition": disposition,
    }


def _pf_record(disposition, observations=None):
    return {"disposition": disposition, "observations": observations if observations is not None else []}


def _vc_record(exchange):
    return {"exchange": exchange}


def _build(tickers_spec):
    """tickers_spec: {ticker: (bf_kwargs_dict, disposition, observations, vci_exchange)}"""
    bf_records, pf_records, vc_records = {}, {}, {}
    for ticker, (bf_kwargs, disposition, observations, exchange) in tickers_spec.items():
        bf_records[ticker] = _bf_record(ticker, disposition=disposition, **bf_kwargs)
        pf_records[ticker] = _pf_record(disposition, observations)
        vc_records[ticker] = _vc_record(exchange)
    return build_artifact(
        breadth_foundation_artifact=breadth_foundation(bf_records),
        p3f9b_snapshot=p3f9b_snapshot(pf_records),
        vci_snapshot=vci_snapshot(vc_records),
    )


def test_active_listed_observed_and_session_missing_with_and_without_nearby_activity():
    artifact = _build({
        "AAA": ({}, "EXACT_SESSION_RETAINED", [{"session": "2026-08-21"}], "HSX"),
        "BBB": ({}, "SESSION_MISSING", [{"session": "2026-08-19"}, {"session": "2026-08-18"}], "HNX"),
        "CCC": ({}, "SESSION_MISSING", [], "UPCOM"),
    })
    records = artifact["records"]
    assert records["AAA"]["activity_and_session_state"] == ACTIVE_LISTED_OBSERVED
    assert records["BBB"]["activity_and_session_state"] == ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION
    assert records["BBB"]["activity_and_session_reason_code"] == "TARGET_SESSION_GAP_WITH_NEARBY_OBSERVED_ACTIVITY"
    assert records["BBB"]["nearby_observation_count_in_retained_window"] == 2
    assert records["CCC"]["activity_and_session_state"] == ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION
    assert records["CCC"]["activity_and_session_reason_code"] == "NO_OBSERVED_TRADING_ACTIVITY_IN_RETAINED_WINDOW"
    assert records["CCC"]["nearby_observation_count_in_retained_window"] == 0
    assert artifact["current_active_equity_denominator"]["count"] == 3
    assert artifact["observed_session_cohort"]["count"] == 1
    assert artifact["observed_session_cohort"]["coverage_ratio"] == pytest.approx(1 / 3)


def test_inactive_or_delisted_via_cross_provider_corroboration_both_membership_states():
    artifact = _build({
        # equity membership confirmed, provider rejects, VCI says delisted
        "OLD": ({"membership_state": "INCLUDED"}, "PROVIDER_REJECTED", [], "DELISTED"),
        # DNSE doesn't even know the symbol, provider rejects, VCI says delisted
        "GONE": ({"membership_state": "UNKNOWN", "membership_reason_code": "SECURITY_MASTER_SYMBOL_NOT_RETAINED",
                  "instrument_class": "UNKNOWN"}, "PROVIDER_REJECTED", [], "DELISTED"),
    })
    records = artifact["records"]
    assert records["OLD"]["activity_and_session_state"] == INACTIVE_OR_DELISTED
    assert records["GONE"]["activity_and_session_state"] == INACTIVE_OR_DELISTED
    assert records["GONE"]["activity_and_session_reason_code"] == "CROSS_PROVIDER_DELISTED_CORROBORATED_VCI_EXCHANGE_AND_DNSE_SESSION_REJECTION"
    assert artifact["provider_rejection_resolution"]["provider_rejected_total"] == 2
    assert artifact["provider_rejection_resolution"]["resolved_to_inactive_or_delisted"] == 2
    assert artifact["provider_rejection_resolution"]["residual_unresolved"] == 0
    assert artifact["security_master_unknown_resolution"]["total_security_master_symbol_not_retained"] == 1
    assert artifact["security_master_unknown_resolution"]["resolved_via_cross_provider_evidence"] == 1
    assert artifact["security_master_unknown_resolution"]["kept_unknown"] == 0
    # confirmed-delisted names must never count toward the active denominator
    assert "OLD" not in {t for t, r in records.items() if r["activity_and_session_state"] in
                         {ACTIVE_LISTED_OBSERVED, ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION}}


def test_contradictions_fail_closed_to_unknown_never_guess():
    artifact = _build({
        # VCI says delisted, but DNSE actually served a session bar -- a real contradiction
        "WEIRD1": ({}, "EXACT_SESSION_RETAINED", [{"session": "2026-08-21"}], "DELISTED"),
        # DNSE has no membership record, but VCI claims an active exchange -- also a contradiction
        "WEIRD2": ({"membership_state": "UNKNOWN", "instrument_class": "UNKNOWN"}, "PROVIDER_REJECTED", [], "HNX"),
    })
    records = artifact["records"]
    assert records["WEIRD1"]["activity_and_session_state"] == UNKNOWN
    assert records["WEIRD1"]["activity_and_session_reason_code"] == "CONTRADICTION_VCI_DELISTED_BUT_DNSE_SESSION_DATA_PRESENT"
    assert records["WEIRD2"]["activity_and_session_state"] == UNKNOWN
    assert records["WEIRD2"]["activity_and_session_reason_code"] == "CONTRADICTION_ACTIVE_PER_VCI_BUT_ABSENT_FROM_DNSE_REFERENCE"


def test_unsupported_or_invalid_provider_symbol_when_no_corroboration_exists():
    artifact = _build({
        "NOPE": ({"membership_state": "UNKNOWN", "instrument_class": "UNKNOWN"}, "PROVIDER_REJECTED", [], None),
    })
    record = artifact["records"]["NOPE"]
    assert record["activity_and_session_state"] == UNSUPPORTED_OR_INVALID_PROVIDER_SYMBOL


def test_non_equity_membership_is_not_applicable_regardless_of_other_evidence():
    artifact = _build({
        "ETF1": ({"membership_state": "EXCLUDED", "membership_reason_code": "INSTRUMENT_CLASS_ETF",
                  "instrument_class": "ETF"}, "EXACT_SESSION_RETAINED", [{"session": "2026-08-21"}], "HSX"),
    })
    record = artifact["records"]["ETF1"]
    assert record["activity_and_session_state"] == NOT_APPLICABLE_NON_EQUITY
    assert "instrument_class_etf" in record["canonical_universe_tiers_analogue"]


def test_full_accounting_reconciles_to_candidate_count():
    artifact = _build({
        "A": ({}, "EXACT_SESSION_RETAINED", [], "HSX"),
        "B": ({}, "SESSION_MISSING", [], "UPCOM"),
        "C": ({"membership_state": "UNKNOWN", "instrument_class": "UNKNOWN"}, "PROVIDER_REJECTED", [], "DELISTED"),
        "D": ({"membership_state": "EXCLUDED", "instrument_class": "ETF"}, "EXACT_SESSION_RETAINED", [], "HSX"),
    })
    counts = artifact["activity_and_session_status"]["counts"]
    assert sum(counts.values()) == 4
    assert artifact["input_candidates"]["count"] == 4


def test_deterministic_identity_across_repeated_builds():
    tickers = {"A": ({}, "EXACT_SESSION_RETAINED", [], "HSX"), "B": ({}, "SESSION_MISSING", [], "UPCOM")}
    first = _build(tickers)
    second = _build(tickers)
    assert first["artifact_identity"] == second["artifact_identity"]
    assert first["artifact_sha256"] == second["artifact_sha256"]


def test_candidate_denominator_mismatch_raises():
    bf = breadth_foundation({"A": _bf_record("A")})
    pf = p3f9b_snapshot({"A": _pf_record("EXACT_SESSION_RETAINED"), "B": _pf_record("EXACT_SESSION_RETAINED")})
    vc = vci_snapshot({"A": _vc_record("HSX"), "B": _vc_record("HSX")})
    with pytest.raises(CurrentUniverseStatusResolutionError):
        build_artifact(breadth_foundation_artifact=bf, p3f9b_snapshot=pf, vci_snapshot=vc)


def test_tampered_input_identity_is_rejected_for_each_source():
    bf = breadth_foundation({"A": _bf_record("A")})
    pf = p3f9b_snapshot({"A": _pf_record("EXACT_SESSION_RETAINED")})
    vc = vci_snapshot({"A": _vc_record("HSX")})

    tampered_bf = dict(bf)
    tampered_bf["records"] = {"A": _bf_record("A", membership_state="EXCLUDED")}
    with pytest.raises(CurrentUniverseStatusResolutionError):
        build_artifact(breadth_foundation_artifact=tampered_bf, p3f9b_snapshot=pf, vci_snapshot=vc)

    tampered_pf = dict(pf)
    tampered_pf["resolved_completed_session"] = "2099-01-01"
    with pytest.raises(CurrentUniverseStatusResolutionError):
        build_artifact(breadth_foundation_artifact=bf, p3f9b_snapshot=tampered_pf, vci_snapshot=vc)

    tampered_vc = dict(vc)
    tampered_vc["records"] = {"A": _vc_record("DELISTED")}
    with pytest.raises(CurrentUniverseStatusResolutionError):
        build_artifact(breadth_foundation_artifact=bf, p3f9b_snapshot=pf, vci_snapshot=tampered_vc)


def test_session_disposition_mismatch_between_breadth_foundation_and_p3f9b_raises():
    bf = breadth_foundation({"A": _bf_record("A", disposition="EXACT_SESSION_RETAINED")})
    pf = p3f9b_snapshot({"A": _pf_record("SESSION_MISSING")})
    vc = vci_snapshot({"A": _vc_record("HSX")})
    with pytest.raises(CurrentUniverseStatusResolutionError):
        build_artifact(breadth_foundation_artifact=bf, p3f9b_snapshot=pf, vci_snapshot=vc)
