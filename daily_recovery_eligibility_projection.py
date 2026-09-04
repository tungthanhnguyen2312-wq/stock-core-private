"""Pre-resolution recovery-eligibility projection for Daily's secondary-provider gap recovery.

WHY THIS MODULE EXISTS
    2026-09-04 DAILY_ACTIVITY_AWARE_ADAPTIVE_GAP_RECOVERY_V1: live evidence
    (operations-review/dnse-same-day-finalization-observation-20260904/ and
    operations-review/same-session-gap-semantics-and-fallback-value-qualification-v1-20260904/)
    found that of the 725 raw DNSE non-exact candidates for 2026-09-04, 177 were already
    corroborated inactive/delisted or membership-unresolved by this project's own existing
    current-universe evidence -- yet the resolver spent secondary-provider (KBS/VCI) requests on
    all 725 anyway, because ``multi_source_exact_session_resolver``'s recovery-candidate selection
    (``all_dnse_missing_tickers``) filters only on DNSE's own disposition, never on membership or
    activity status.

    This module projects that existing, already-qualified evidence -- ``current_market_universe_
    breadth_foundation`` (DNSE security-master instrument-class membership) layered with
    ``current_universe_status_and_session_coverage_resolution`` (frozen VCI-exchange delisting
    cross-check) -- onto a single session's Pass-1 DNSE-only snapshot, to answer one question:
    *which of DNSE's own gaps are even worth spending a secondary-provider request on?*

NOT CIRCULAR
    Both underlying contracts take a session snapshot as an input, which could look circular if
    fed the FINAL, multi-source-*resolved* snapshot (the thing the exact-session coverage gate
    itself validates -- STATE.md's own prior note on why this was left unwired). This module
    always feeds them Pass 1's own DNSE-only snapshot instead, which already exists, unmodified,
    before Pass 2-4 recovery ever starts. No resolved/recovered data is required or consulted.

NOT A NEW LISTING-AUTHORITY CONCEPT
    Every classification here is read verbatim from the two existing contracts named above ("
    activity_and_session_state" and its five documented values). This module does not invent a
    new state, threshold, or listing rule -- it only decides which of the *existing* states make a
    ticker worth a secondary-provider request, and preserves full reason-code provenance for why.

FAIL-OPEN, NEVER A HARD DEPENDENCY
    Every static, already-retained input (the qualification artifact, the VCI exchange
    reference snapshot) is optional. When any of it is absent, malformed, or does not cover the
    exact candidate set this session presents, this module returns ``available=False`` and every
    candidate is reported ``recovery_eligible=True`` -- i.e. no filtering at all, byte-identical to
    this project's pre-existing behavior. A missing side-artifact must never block Daily.

AUTHORITY BOUNDARY
    This is a Current-Research-only, non-authoritative projection, exactly like the two contracts
    it reuses: it never promotes ACTIVE_UNIVERSE, never asserts listing/PIT/historical authority,
    and never mutates either underlying contract or the runtime database.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import current_market_universe_breadth_foundation as _breadth_foundation
import current_universe_status_and_session_coverage_resolution as _status_resolution

CONTRACT_VERSION = "daily_recovery_eligibility_projection/v1"

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_QUALIFICATION_ARTIFACT_PATH = (
    REPO_ROOT / "operations-review" / "market-wide-current-research-universe-qualification-v1-20260823"
    / "market_wide_current_research_universe_artifact.json"
)
DEFAULT_VCI_EXCHANGE_SNAPSHOT_PATH = (
    REPO_ROOT / "operations-review" / "vci-exchange-reference-snapshot-v1-20260823"
    / "vci_exchange_reference_snapshot_artifact.json"
)

# activity_and_session_state values (current_universe_status_and_session_coverage_resolution)
# that make a still-gapped ticker worth a secondary-provider request.
_RECOVERY_ELIGIBLE_STATES = frozenset({
    _status_resolution.ACTIVE_LISTED_OBSERVED,
    _status_resolution.ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION,
})
_INELIGIBLE_REASON_BY_STATE = {
    _status_resolution.INACTIVE_OR_DELISTED: "RECOVERY_INELIGIBLE_INACTIVE_OR_DELISTED",
    _status_resolution.NOT_APPLICABLE_NON_EQUITY: "RECOVERY_INELIGIBLE_NON_EQUITY",
    _status_resolution.UNSUPPORTED_OR_INVALID_PROVIDER_SYMBOL: "RECOVERY_INELIGIBLE_UNSUPPORTED_PROVIDER_SYMBOL",
    _status_resolution.UNKNOWN: "RECOVERY_INELIGIBLE_MEMBERSHIP_UNKNOWN",
}


def _load_json(path: Path) -> Mapping[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _degraded(reason: str, *, candidates: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "available": False,
        "degraded_reason": reason,
        "per_ticker": {
            ticker: {"recovery_eligible": True, "reason_code": "RECOVERY_ELIGIBILITY_PROJECTION_UNAVAILABLE"}
            for ticker in candidates
        },
        "counts": {"total": len(candidates), "recovery_eligible": len(candidates), "recovery_ineligible": 0},
        "authority_boundary": {
            "not_authoritative": True, "active_listing_authority": "NOT_PROMOTED",
            "PIT": "BLOCKED", "new_listing_concept_introduced": False,
        },
    }


def project_recovery_eligibility(
    dnse_snapshot: Mapping[str, Any],
    *,
    qualification_artifact_path: Path = DEFAULT_QUALIFICATION_ARTIFACT_PATH,
    vci_exchange_snapshot_path: Path = DEFAULT_VCI_EXCHANGE_SNAPSHOT_PATH,
) -> dict[str, Any]:
    """Project existing current-universe/activity evidence onto ``dnse_snapshot`` (Pass 1's own
    DNSE-only output -- never a post-recovery snapshot).

    Returns a dict with ``available`` (bool). When ``True``, ``per_ticker[ticker]`` carries
    ``recovery_eligible``/``reason_code``/``activity_and_session_state`` for every candidate in
    ``dnse_snapshot``. When ``False`` (either input file absent/malformed, or its candidate set
    does not exactly match this session's), every candidate defaults ``recovery_eligible=True`` --
    fail-open, never fail-closed, since this is a cost-saving optimization, not a correctness gate.
    """
    candidates = dnse_snapshot.get("records")
    if not isinstance(candidates, Mapping) or not candidates:
        return _degraded("DNSE_SNAPSHOT_RECORDS_MISSING", candidates=candidates or {})

    qualification = _load_json(qualification_artifact_path)
    vci_snapshot = _load_json(vci_exchange_snapshot_path)
    if qualification is None:
        return _degraded("QUALIFICATION_ARTIFACT_UNAVAILABLE", candidates=candidates)
    if vci_snapshot is None:
        return _degraded("VCI_EXCHANGE_SNAPSHOT_UNAVAILABLE", candidates=candidates)

    try:
        breadth = _breadth_foundation.build_artifact(
            qualification_artifact=qualification, canonical_snapshot=dnse_snapshot,
        )
        status = _status_resolution.build_artifact(
            breadth_foundation_artifact=breadth, p3f9b_snapshot=dnse_snapshot, vci_snapshot=vci_snapshot,
        )
    except (ValueError, KeyError) as exc:
        # Candidate-set mismatch, a stale/rotated static artifact, or an identity check failure --
        # any of these means the retained side-evidence no longer matches this session's universe.
        # Degrade to "no filter" rather than block Daily on a diagnostic optimization.
        return _degraded(f"ELIGIBILITY_PROJECTION_INPUT_REJECTED:{type(exc).__name__}:{exc}", candidates=candidates)

    per_ticker: dict[str, dict[str, Any]] = {}
    eligible_count = 0
    for ticker, record in status["records"].items():
        state = record["activity_and_session_state"]
        eligible = state in _RECOVERY_ELIGIBLE_STATES
        eligible_count += eligible
        per_ticker[ticker] = {
            "recovery_eligible": eligible,
            "reason_code": (
                "RECOVERY_ELIGIBLE_CURRENT_ACTIVE_EQUITY" if eligible
                else _INELIGIBLE_REASON_BY_STATE.get(state, f"RECOVERY_INELIGIBLE_UNCLASSIFIED_{state}")
            ),
            "activity_and_session_state": state,
        }

    return {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "available": True,
        "source_evidence_identities": {
            "breadth_foundation": breadth.get("artifact_identity"),
            "status_resolution": status.get("artifact_identity"),
            "qualification_artifact_path": str(qualification_artifact_path),
            "vci_exchange_snapshot_path": str(vci_exchange_snapshot_path),
            "dnse_snapshot_identity": dnse_snapshot.get("snapshot_identity"),
        },
        "per_ticker": per_ticker,
        "counts": {
            "total": len(per_ticker),
            "recovery_eligible": eligible_count,
            "recovery_ineligible": len(per_ticker) - eligible_count,
        },
        "authority_boundary": {
            "not_authoritative": True, "active_listing_authority": "NOT_PROMOTED",
            "PIT": "BLOCKED", "new_listing_concept_introduced": False,
        },
    }


def recovery_eligible_ticker_set(projection: Mapping[str, Any]) -> set[str] | None:
    """``None`` means "no filter" (projection unavailable) -- callers must treat that as
    "every candidate remains recovery-eligible", never as an empty set."""
    if not projection.get("available"):
        return None
    return {
        ticker for ticker, row in projection["per_ticker"].items() if row["recovery_eligible"]
    }
