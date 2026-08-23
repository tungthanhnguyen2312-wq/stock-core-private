"""Current descriptive breadth projection from retained universe and session evidence."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Mapping


CONTRACT_VERSION = "current_market_universe_breadth_foundation/v1"
EQUITY = "EQUITY"
MEMBERSHIP_STATES = ("INCLUDED", "EXCLUDED", "UNKNOWN")
OBSERVATION_STATES = ("OBSERVED", "SESSION_MISSING", "INCOMPLETE", "PROVIDER_REJECTED")
BREADTH_STATES = ("ELIGIBLE", "NOT_READY", "NOT_APPLICABLE")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _identity_payload(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in artifact.items() if key not in {"artifact_sha256", "artifact_identity"}}


def _verify_identity(artifact: Mapping[str, Any], *, label: str) -> None:
    expected = hashlib.sha256(_canonical_json(_identity_payload(artifact)).encode()).hexdigest()
    if artifact.get("artifact_sha256") != expected:
        raise ValueError(f"{label}_IDENTITY_MISMATCH")


def _observation_state(record: Mapping[str, Any]) -> tuple[str, str]:
    disposition = record.get("disposition")
    if disposition == "EXACT_SESSION_RETAINED":
        return "OBSERVED", "EXACT_SESSION_RETAINED"
    if disposition == "SESSION_MISSING":
        return "SESSION_MISSING", "SESSION_MISSING"
    if disposition == "PROVIDER_REJECTED":
        return "PROVIDER_REJECTED", "PROVIDER_REJECTED"
    return "INCOMPLETE", f"UNCLASSIFIED_SESSION_DISPOSITION_{disposition or 'MISSING'}"


def _counts_with_zeros(counter: Counter[str], states: tuple[str, ...]) -> dict[str, int]:
    return {state: counter[state] for state in states}


def build_artifact(*, qualification_artifact: Mapping[str, Any], canonical_snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Separate current equity-candidate membership from session observability.

    ``INCLUDED`` here is deliberately only the retained current DNSE security-master
    equity-candidate scope. It does not assert an active-listing or authoritative
    market-membership claim, because DNSE's instruments response lacks listing status.
    """
    _verify_identity(qualification_artifact, label="QUALIFICATION_ARTIFACT")
    qualification_records = qualification_artifact.get("records")
    snapshot_records = canonical_snapshot.get("records")
    if not isinstance(qualification_records, Mapping) or not isinstance(snapshot_records, Mapping):
        raise ValueError("INPUT_RECORDS_INVALID")
    if set(qualification_records) != set(snapshot_records):
        raise ValueError("CANDIDATE_DENOMINATOR_MISMATCH")

    records: dict[str, dict[str, Any]] = {}
    for ticker in sorted(snapshot_records):
        qualification = qualification_records[ticker]
        session = snapshot_records[ticker]
        instrument_class = qualification.get("instrument_class", "UNKNOWN")
        if instrument_class == EQUITY:
            membership_state = "INCLUDED"
            membership_reason = "CURRENT_REFERENCE_EQUITY_CANDIDATE"
        elif instrument_class in {None, "UNKNOWN", "UNKNOWN_SECURITY_GROUP"}:
            membership_state = "UNKNOWN"
            membership_reason = "SECURITY_MASTER_SYMBOL_NOT_RETAINED"
        else:
            membership_state = "EXCLUDED"
            membership_reason = f"INSTRUMENT_CLASS_{instrument_class}"

        observation_state, observation_reason = _observation_state(session)
        if membership_state == "INCLUDED" and observation_state == "OBSERVED":
            breadth_state = "ELIGIBLE"
            breadth_reason = "OBSERVED_CURRENT_SESSION_EQUITY_CANDIDATE"
        elif membership_state == "INCLUDED":
            breadth_state = "NOT_READY"
            breadth_reason = f"SESSION_{observation_state}"
        elif membership_state == "UNKNOWN":
            breadth_state = "NOT_READY"
            breadth_reason = "MEMBERSHIP_UNKNOWN"
        else:
            breadth_state = "NOT_APPLICABLE"
            breadth_reason = membership_reason

        records[ticker] = {
            "ticker": ticker,
            "instrument_class": instrument_class,
            "instrument_class_basis": qualification.get("instrument_class_basis"),
            "exchange": qualification.get("exchange"),
            "listing_context": qualification.get("listing_context"),
            "membership_state": membership_state,
            "membership_reason_code": membership_reason,
            "session_observation_state": observation_state,
            "session_observation_reason_code": observation_reason,
            "source_session_disposition": session.get("disposition"),
            "breadth_screening_state": breadth_state,
            "breadth_screening_reason_code": breadth_reason,
        }

    membership_counts = Counter(record["membership_state"] for record in records.values())
    class_counts = Counter(record["instrument_class"] for record in records.values())
    observation_counts = Counter(record["session_observation_state"] for record in records.values())
    breadth_counts = Counter(record["breadth_screening_state"] for record in records.values())
    membership_session_counts = Counter(
        f"{record['membership_state']}|{record['session_observation_state']}" for record in records.values()
    )
    denominator = membership_counts["INCLUDED"]
    observed = sum(
        1 for record in records.values()
        if record["membership_state"] == "INCLUDED" and record["session_observation_state"] == "OBSERVED"
    )
    if denominator == 0:
        raise ValueError("NO_CURRENT_EQUITY_CANDIDATE_DENOMINATOR")

    artifact = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "input_candidates": {
            "count": len(records),
            "snapshot_identity": canonical_snapshot.get("snapshot_identity"),
            "qualification_artifact_identity": qualification_artifact.get("artifact_identity"),
        },
        "current_universe_membership": {
            "included_equity_candidate_count": denominator,
            "excluded_non_equity_count": membership_counts["EXCLUDED"],
            "unknown_membership_count": membership_counts["UNKNOWN"],
            "scope": "CURRENT_DNSE_SECURITY_MASTER_EQUITY_CANDIDATE_ONLY",
            "listing_status": "UNKNOWN_NOT_PROVIDED_BY_DNSE_INSTRUMENTS",
            "not_authoritative": True,
        },
        "instrument_classes": dict(sorted(class_counts.items())),
        "session_observability": {
            "counts": _counts_with_zeros(observation_counts, OBSERVATION_STATES),
            "scope": "RETAINED_P3F9B_COMPLETED_SESSION_2026_08_21",
        },
        "observed_session_cohort": {
            "count": observed,
            "membership_denominator": denominator,
            "coverage_ratio": observed / denominator,
            "coverage_ratio_decimal_places": 6,
            "scope": "CURRENT_DESCRIPTIVE_BREADTH_AND_CROSS_SECTIONAL_SCREENING_ONLY",
        },
        "breadth_screening": {
            "state": "PARTIAL_ELIGIBLE_WITH_EXPLICIT_COVERAGE",
            "counts": _counts_with_zeros(breadth_counts, BREADTH_STATES),
            "authority": "CURRENT_DESCRIPTIVE_ONLY",
            "coverage_required_in_every_consumer": True,
        },
        "exclusion_and_availability_ledger": {
            "membership": _counts_with_zeros(membership_counts, MEMBERSHIP_STATES),
            "session_observability": _counts_with_zeros(observation_counts, OBSERVATION_STATES),
            "membership_by_session_observability": dict(sorted(membership_session_counts.items())),
            "breadth_screening": _counts_with_zeros(breadth_counts, BREADTH_STATES),
        },
        "promotion_recommendation": {
            "state": "OWNER_REVIEW_REQUIRED_NOT_AUTHORITATIVE",
            "reason": "CURRENT_LISTING_STATUS_NOT_PROVIDED_AND_SESSION_COVERAGE_PARTIAL",
        },
        "authority_boundary": {
            "historical_constituents": "NOT_CONSTRUCTED",
            "PIT": "BLOCKED",
            "RAW_AS_TRADED": "NOT_PROMOTED",
            "adv_adtv_sizing_execution": "NOT_EMITTED",
            "ranking_recommendation_valuation": "NOT_EMITTED",
        },
        "records": records,
    }
    artifact_sha256 = hashlib.sha256(_canonical_json(artifact).encode()).hexdigest()
    artifact["artifact_sha256"] = artifact_sha256
    artifact["artifact_identity"] = f"current_market_universe_breadth_foundation:{artifact_sha256}"
    return artifact
