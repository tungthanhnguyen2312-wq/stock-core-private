"""Resolve current-equity activity status as a dimension independent of session observability.

Builds directly on the retained ``current_market_universe_breadth_foundation_artifact.json``
(membership x session-observability) -- this module does not rebuild or re-derive either of
those two dimensions, only reads them. It adds two more, kept explicitly separate per the
milestone brief: **provider support** (did the DNSE OHLC endpoint recognize the symbol at all
on the target session request) and **listing/activity status** (is the equity itself currently
active, using retained cross-provider evidence, never inferred from a missing bar alone).

EVIDENCE USED (both already retained; no new provider, no new network call)
    1. The raw ``p3f9b_mva_exact_session_snapshot.json`` this project already produced for
       session 2026-08-21 (``mva_exact_session_snapshot.py``). Its ``PROVIDER_REJECTED``
       disposition means the DNSE ``/price/ohlc`` endpoint returned HTTP 400 for that exact
       symbol on that request (see ``tools/run_p3f9b_market_wide_exact_session_scaleout.py``'s
       own report legend). Its ``SESSION_MISSING`` disposition retains the *other* bars returned
       in the same ~45-day request window, which this module reads (never re-fetches) to tell a
       true target-date-only gap from an extended absence of any observed activity.
    2. ``dashboard-runtime/vn_stock.db``'s ``metadata.exchange`` column -- already populated by
       ``meta_sync.py`` from VCI's ``Listing(source="VCI").symbols_by_exchange()``, itself
       already relied on elsewhere in this codebase (``candle_scan.py``, ``live_universe.py``,
       ``stock_analyzer.py``, ``release_session_contract.py``, ``publish_dashboard.py`` all
       already treat its ``"DELISTED"`` value as meaningful). This module consumes a frozen
       snapshot of that column (``vci_exchange_reference_snapshot.py``), never the live database.

THE FINDING THIS MODULE ACTS ON
    Cross-tabulating the two sources over the retained 1,683-candidate cohort: every one of the
    173 ``PROVIDER_REJECTED`` records has ``metadata.exchange == "DELISTED"``, and every
    ``metadata.exchange == "DELISTED"`` record is ``PROVIDER_REJECTED`` -- an exact, symmetric,
    173/173 correspondence between two independently-sourced signals (DNSE's own live session
    endpoint and VCI's separately-synced listing classification). That is materially stronger
    corroboration than the single-source "legacy marker, mechanism unqualified" case
    ``canonical_instrument_reconciliation.py`` already anticipated and deliberately fenced off
    (see its module-level comment at the ``listing_status`` field spec, and
    ``canonical_universe_tiers.py``'s dormant ``listing_status in {"INACTIVE", "DELISTED"}``
    branch in ``_active()``, which has never received a non-``UNKNOWN`` input). This module does
    **not** modify either of those two files or promote ``ACTIVE_UNIVERSE`` -- it surfaces the
    same class of evidence in a new, narrower, explicitly non-authoritative artifact, exactly
    like every recent sibling current-* milestone in ``docs/STATE.md``. Lifting C.1's fail-closed
    gate so this evidence could flow into ``ACTIVE_UNIVERSE`` itself remains a distinct,
    not-yet-made owner decision, not self-promoted here.

NO-TRADE SEMANTICS
    A ``SESSION_MISSING`` record is never classified as inactive or as a proven zero-trade
    session from OHLC absence alone (the milestone's explicit invariant). The only genuine
    zero-trade proof anywhere in this codebase is the bounded, exhaustive ``trades_history``
    pagination precedent for QNS (``dnse_trades_liquidity_basis.py``, 2026-08-23) -- not
    replicated here for this 550-record cohort; see ``no_trade_session_semantics`` below.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Mapping

from field_temporal_contract import stable_id as _p3f9b_stable_id

CONTRACT_VERSION = "current_universe_status_and_session_coverage_resolution/v1"

ACTIVE_LISTED_OBSERVED = "ACTIVE_LISTED_OBSERVED"
ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION = "ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION"
INACTIVE_OR_DELISTED = "INACTIVE_OR_DELISTED"
UNSUPPORTED_OR_INVALID_PROVIDER_SYMBOL = "UNSUPPORTED_OR_INVALID_PROVIDER_SYMBOL"
NOT_APPLICABLE_NON_EQUITY = "NOT_APPLICABLE_NON_EQUITY"
UNKNOWN = "UNKNOWN"
ACTIVITY_STATES = (
    ACTIVE_LISTED_OBSERVED,
    ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION,
    INACTIVE_OR_DELISTED,
    UNSUPPORTED_OR_INVALID_PROVIDER_SYMBOL,
    NOT_APPLICABLE_NON_EQUITY,
    UNKNOWN,
)

SUPPORTED = "SUPPORTED"
REJECTED = "REJECTED"
PROVIDER_SUPPORT_UNKNOWN = "UNKNOWN"
PROVIDER_SUPPORT_STATES = (SUPPORTED, REJECTED, PROVIDER_SUPPORT_UNKNOWN)

_DELISTED = "DELISTED"
_ACTIVE_EXCHANGES = frozenset({"HSX", "HNX", "UPCOM"})
_SUPPORTED_DISPOSITIONS = frozenset({"EXACT_SESSION_RETAINED", "SESSION_MISSING"})


class CurrentUniverseStatusResolutionError(ValueError):
    """A retained input or an invariant of this contract is violated."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _verify_artifact_identity(artifact: Mapping[str, Any], *, hash_key: str, identity_key: str, label: str) -> None:
    payload = {key: value for key, value in artifact.items() if key not in {hash_key, identity_key}}
    expected = _hash(payload)
    if artifact.get(hash_key) != expected:
        raise CurrentUniverseStatusResolutionError(f"{label}_IDENTITY_MISMATCH")


def _verify_p3f9b_identity(snapshot: Mapping[str, Any]) -> None:
    payload = {key: value for key, value in snapshot.items() if key not in {"snapshot_sha256", "snapshot_identity"}}
    if snapshot.get("snapshot_sha256") != _p3f9b_stable_id(payload):
        raise CurrentUniverseStatusResolutionError("P3F9B_SNAPSHOT_IDENTITY_MISMATCH")


def _provider_support(disposition: str | None) -> str:
    if disposition in _SUPPORTED_DISPOSITIONS:
        return SUPPORTED
    if disposition == "PROVIDER_REJECTED":
        return REJECTED
    return PROVIDER_SUPPORT_UNKNOWN


def _nearby_observation_count(p3f9b_record: Mapping[str, Any], *, target_session: str) -> int:
    observations = p3f9b_record.get("observations")
    if not isinstance(observations, list):
        return 0
    return sum(1 for row in observations if isinstance(row, Mapping) and row.get("session") != target_session)


def _tier_analogue(state: str, membership_reason_code: str | None) -> str:
    """A concise cross-reference to canonical_universe_tiers.py's existing vocabulary.

    Never written back to that module or its ledger -- see the module docstring.
    """
    if state == NOT_APPLICABLE_NON_EQUITY:
        detail = (membership_reason_code or "instrument_type_not_equity").lower()
        return f"LISTED_EQUITY_CANDIDATE=EXCLUDED analogue ({detail}) -- matches canonical_universe_tiers.py unchanged"
    if state == INACTIVE_OR_DELISTED:
        return ("ACTIVE_UNIVERSE=EXCLUDED analogue (listing_inactive_or_delisted) -- NOT applied to "
                "canonical_universe_tiers.py; its C.1 fail-closed LEGACY listing_status gate is unmodified")
    return ("ACTIVE_UNIVERSE=UNKNOWN analogue (listing_status_unknown) -- unchanged from "
            "canonical_universe_tiers.py's current fail-closed state")


def _classify(*, membership_state: str, membership_reason_code: str | None, disposition: str | None,
             provider_support: str, vci_exchange: str | None, nearby_observation_count: int | None) -> tuple[str, str]:
    """Deterministic, precedence-ordered, evidence-only classification. Never guesses."""
    if membership_state == "EXCLUDED":
        return NOT_APPLICABLE_NON_EQUITY, "MEMBERSHIP_EXCLUDED_NON_EQUITY_INSTRUMENT_CLASS"

    vci_delisted = vci_exchange == _DELISTED
    if vci_delisted and provider_support == REJECTED:
        return INACTIVE_OR_DELISTED, "CROSS_PROVIDER_DELISTED_CORROBORATED_VCI_EXCHANGE_AND_DNSE_SESSION_REJECTION"
    if vci_delisted:
        return UNKNOWN, "CONTRADICTION_VCI_DELISTED_BUT_DNSE_SESSION_DATA_PRESENT"

    if membership_state == "UNKNOWN":
        if vci_exchange in _ACTIVE_EXCHANGES:
            return UNKNOWN, "CONTRADICTION_ACTIVE_PER_VCI_BUT_ABSENT_FROM_DNSE_REFERENCE"
        if provider_support == REJECTED:
            return UNSUPPORTED_OR_INVALID_PROVIDER_SYMBOL, "NO_DNSE_MEMBERSHIP_NO_VCI_CORROBORATION_SESSION_REJECTED"
        return UNKNOWN, "NO_QUALIFIED_REFERENCE_EVIDENCE"

    if membership_state == "INCLUDED":
        if provider_support == SUPPORTED:
            if disposition == "EXACT_SESSION_RETAINED":
                return ACTIVE_LISTED_OBSERVED, "TARGET_SESSION_BAR_RETAINED"
            if nearby_observation_count and nearby_observation_count > 0:
                return (ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION,
                        "TARGET_SESSION_GAP_WITH_NEARBY_OBSERVED_ACTIVITY")
            return ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION, "NO_OBSERVED_TRADING_ACTIVITY_IN_RETAINED_WINDOW"
        if provider_support == REJECTED:
            return UNKNOWN, "PROVIDER_REJECTED_WITHOUT_CORROBORATING_DELISTING_EVIDENCE"
        return UNKNOWN, "UNCLASSIFIED_SESSION_DISPOSITION"

    return UNKNOWN, "UNCLASSIFIED_MEMBERSHIP_STATE"


def build_artifact(*, breadth_foundation_artifact: Mapping[str, Any], p3f9b_snapshot: Mapping[str, Any],
                   vci_snapshot: Mapping[str, Any]) -> dict[str, Any]:
    _verify_artifact_identity(breadth_foundation_artifact, hash_key="artifact_sha256",
                              identity_key="artifact_identity", label="BREADTH_FOUNDATION_ARTIFACT")
    _verify_p3f9b_identity(p3f9b_snapshot)
    _verify_artifact_identity(vci_snapshot, hash_key="snapshot_sha256", identity_key="snapshot_identity",
                              label="VCI_EXCHANGE_REFERENCE_SNAPSHOT")

    bf_records = breadth_foundation_artifact.get("records")
    pf_records = p3f9b_snapshot.get("records")
    vc_records = vci_snapshot.get("records")
    if not isinstance(bf_records, Mapping) or not isinstance(pf_records, Mapping) or not isinstance(vc_records, Mapping):
        raise CurrentUniverseStatusResolutionError("INPUT_RECORDS_INVALID")
    if not (set(bf_records) == set(pf_records) == set(vc_records)):
        raise CurrentUniverseStatusResolutionError("CANDIDATE_DENOMINATOR_MISMATCH")

    target_session = p3f9b_snapshot.get("resolved_completed_session")
    if not target_session:
        raise CurrentUniverseStatusResolutionError("P3F9B_SNAPSHOT_MISSING_RESOLVED_SESSION")

    records: dict[str, dict[str, Any]] = {}
    for ticker in sorted(bf_records):
        bf = bf_records[ticker]
        pf = pf_records[ticker]
        vc = vc_records[ticker]

        disposition = bf.get("source_session_disposition")
        if disposition != pf.get("disposition"):
            raise CurrentUniverseStatusResolutionError(f"SESSION_DISPOSITION_MISMATCH_BETWEEN_INPUTS:{ticker}")

        membership_state = bf.get("membership_state")
        provider_support = _provider_support(disposition)
        vci_exchange = vc.get("exchange")
        nearby_count = (
            _nearby_observation_count(pf, target_session=target_session)
            if disposition == "SESSION_MISSING" else None
        )

        state, reason = _classify(
            membership_state=membership_state, membership_reason_code=bf.get("membership_reason_code"),
            disposition=disposition, provider_support=provider_support, vci_exchange=vci_exchange,
            nearby_observation_count=nearby_count,
        )

        records[ticker] = {
            "ticker": ticker,
            "membership_state": membership_state,
            "membership_reason_code": bf.get("membership_reason_code"),
            "instrument_class": bf.get("instrument_class"),
            "session_observation_state": bf.get("session_observation_state"),
            "source_session_disposition": disposition,
            "provider_support_state": provider_support,
            "vci_exchange_reference": vci_exchange,
            "nearby_observation_count_in_retained_window": nearby_count,
            "activity_and_session_state": state,
            "activity_and_session_reason_code": reason,
            "canonical_universe_tiers_analogue": _tier_analogue(state, bf.get("membership_reason_code")),
        }

    activity_counts = Counter(record["activity_and_session_state"] for record in records.values())
    provider_support_counts = Counter(record["provider_support_state"] for record in records.values())
    reason_counts = Counter(record["activity_and_session_reason_code"] for record in records.values())
    activity_by_prior_session_state = Counter(
        f"{record['activity_and_session_state']}|{record['session_observation_state']}" for record in records.values()
    )

    active_denominator = activity_counts[ACTIVE_LISTED_OBSERVED] + activity_counts[ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION]
    observed = activity_counts[ACTIVE_LISTED_OBSERVED]
    coverage_ratio = observed / active_denominator if active_denominator else None

    provider_rejected_total = provider_support_counts[REJECTED]
    provider_rejected_resolved_delisted = sum(
        1 for record in records.values()
        if record["provider_support_state"] == REJECTED and record["activity_and_session_state"] == INACTIVE_OR_DELISTED
    )
    provider_rejected_residual = provider_rejected_total - provider_rejected_resolved_delisted

    session_missing_records = [record for record in records.values() if record["source_session_disposition"] == "SESSION_MISSING"]
    session_missing_with_nearby = sum(1 for record in session_missing_records if (record["nearby_observation_count_in_retained_window"] or 0) > 0)
    session_missing_without_nearby = len(session_missing_records) - session_missing_with_nearby

    unknown_membership_resolved = sum(
        1 for record in records.values()
        if record["membership_state"] == "UNKNOWN" and record["activity_and_session_state"] != UNKNOWN
    )
    unknown_membership_total = sum(1 for record in records.values() if record["membership_state"] == "UNKNOWN")

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "input_candidates": {
            "count": len(records),
            "breadth_foundation_artifact_identity": breadth_foundation_artifact.get("artifact_identity"),
            "p3f9b_snapshot_identity": p3f9b_snapshot.get("snapshot_identity"),
            "vci_exchange_reference_snapshot_identity": vci_snapshot.get("snapshot_identity"),
            "resolved_completed_session": target_session,
        },
        "security_master_unknown_resolution": {
            "total_security_master_symbol_not_retained": unknown_membership_total,
            "resolved_via_cross_provider_evidence": unknown_membership_resolved,
            "kept_unknown": unknown_membership_total - unknown_membership_resolved,
            "method": "empirically_deduced",
            "note": (
                "membership_state (DNSE-current-security-master dimension) is left byte-unchanged; "
                "resolution is expressed only in the new activity_and_session_state dimension so the "
                "underlying DNSE-specific fact is never overwritten -- see module docstring."
            ),
        },
        "provider_rejection_resolution": {
            "provider_rejected_total": provider_rejected_total,
            "resolved_to_inactive_or_delisted": provider_rejected_resolved_delisted,
            "residual_unresolved": provider_rejected_residual,
            "resolution_basis": "exact_1_to_1_correspondence_with_vci_exchange_reference_delisted",
        },
        "session_missing_diagnostics": {
            "total": len(session_missing_records),
            "with_nearby_observation_in_retained_window": session_missing_with_nearby,
            "without_any_observation_in_retained_window": session_missing_without_nearby,
            "retained_window": "~45_calendar_days_ending_at_resolved_completed_session_per_mva_exact_session_snapshot_request_contract",
            "note": "Neither sub-population is classified INACTIVE_OR_DELISTED; both remain ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION.",
        },
        "no_trade_session_semantics": {
            "established_for_this_cohort": False,
            "reason": (
                "Retained OHLC-history absence is evidence of no qualified session bar, not proof of zero "
                "executed trades. The only genuine zero-trade proof in this codebase is the bounded, "
                "exhaustive trades_history pagination precedent for QNS "
                "(dnse_trades_liquidity_basis.py, 2026-08-23); replicating it across this 550-record "
                "SESSION_MISSING cohort is out of this milestone's bounded scope."
            ),
        },
        "activity_and_session_status": {
            "counts": {state: activity_counts[state] for state in ACTIVITY_STATES},
            "reason_code_counts": dict(sorted(reason_counts.items())),
            "provider_support_counts": {state: provider_support_counts[state] for state in PROVIDER_SUPPORT_STATES},
            "cross_tab_activity_by_prior_session_observation_state": dict(sorted(activity_by_prior_session_state.items())),
        },
        "current_active_equity_denominator": {
            "count": active_denominator,
            "composition": {
                ACTIVE_LISTED_OBSERVED: activity_counts[ACTIVE_LISTED_OBSERVED],
                ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION: activity_counts[ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION],
            },
            "excludes": {
                INACTIVE_OR_DELISTED: activity_counts[INACTIVE_OR_DELISTED],
                UNSUPPORTED_OR_INVALID_PROVIDER_SYMBOL: activity_counts[UNSUPPORTED_OR_INVALID_PROVIDER_SYMBOL],
                NOT_APPLICABLE_NON_EQUITY: activity_counts[NOT_APPLICABLE_NON_EQUITY],
                UNKNOWN: activity_counts[UNKNOWN],
            },
            "not_authoritative": True,
            "scope": "CURRENT_DESCRIPTIVE_BREADTH_DENOMINATOR_ONLY",
        },
        "observed_session_cohort": {
            "count": observed,
            "current_active_equity_denominator": active_denominator,
            "coverage_ratio": coverage_ratio,
            "coverage_ratio_decimal_places": 6,
            "prior_breadth_foundation_coverage_ratio": breadth_foundation_artifact.get("observed_session_cohort", {}).get("coverage_ratio"),
            "scope": "CURRENT_DESCRIPTIVE_BREADTH_AND_CROSS_SECTIONAL_SCREENING_ONLY",
        },
        "promotion_recommendation": {
            "state": "OWNER_REVIEW_REQUIRED_NOT_AUTHORITATIVE",
            "reason": (
                "INACTIVE_OR_DELISTED is empirically_deduced from cross-provider corroboration (DNSE session "
                "rejection + VCI exchange classification), not documented_verified; canonical_universe_tiers.py's "
                "ACTIVE_UNIVERSE gate and canonical_instrument_reconciliation.py's fail-closed LEGACY "
                "listing_status path are both left unmodified. Promoting either is a distinct future owner gate."
            ),
        },
        "authority_boundary": {
            "active_listing_authority": "NOT_PROMOTED",
            "historical_constituents": "NOT_CONSTRUCTED",
            "PIT": "BLOCKED",
            "RAW_AS_TRADED": "NOT_PROMOTED",
            "adv_adtv_sizing_execution": "NOT_EMITTED",
            "ranking_recommendation_valuation": "NOT_EMITTED",
            "canonical_universe_tiers_modified": False,
            "canonical_instrument_reconciliation_modified": False,
        },
        "records": records,
    }
    artifact_sha256 = _hash(artifact)
    artifact["artifact_sha256"] = artifact_sha256
    artifact["artifact_identity"] = f"current_universe_status_and_session_coverage_resolution:{artifact_sha256}"
    return artifact
