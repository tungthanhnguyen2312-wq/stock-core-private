"""Generic, fail-closed current-common-share authority boundary.

This module is deliberately narrower than a valuation engine.  It turns
evidence candidates into an effective-dated *timeline*, and only exposes a
market-cap eligible value when the candidate itself explicitly covers the
valuation date.  It never forward-fills a historical observation.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

CONTRACT_VERSION = "current_share_authority/v1"
COMMON_OUTSTANDING = "common_shares_outstanding"
SHARE_IDENTITIES = frozenset({
    "issued_shares", "listed_shares", COMMON_OUTSTANDING, "treasury_shares",
    "period_end_shares", "weighted_average_basic_shares", "diluted_shares",
})

# This is an inventory of already governed paths, not a source registry and not
# an authority promotion.  A candidate remains unusable until it satisfies the
# exact identity and temporal requirements below.
SOURCE_AUTHORITY_INVENTORY = {
    "official_retained_evidence": {
        "authority_state": "APPROVED_EXISTING",
        "share_identities": ["period_end_shares", "weighted_average_basic_shares", COMMON_OUTSTANDING],
        "market_cap_allowed_only_when": "explicit_common_outstanding_with_coverage_through_valuation_date",
        "lineage": "manifest_hash_verified_citation_or_qualified_event",
    },
    "official_corporate_action_result": {
        "authority_state": "APPROVED_EXISTING",
        "share_identities": [COMMON_OUTSTANDING],
        "market_cap_allowed_only_when": "executed_resulting_count_and_explicit_coverage",
        "lineage": "qualified_event_with_resulting_shares",
    },
    "provider_metadata_issue_share": {
        "authority_state": "NOT_PROMOTED",
        "share_identities": ["issued_shares"],
        "market_cap_allowed_only_when": "never_without_owner_source_promotion",
        "lineage": "VCI.overview.issue_share_retained_metadata",
    },
    "dnse_current_market_ohlc": {
        "authority_state": "NO_SHARE_FIELD_IN_EXISTING_CONTRACT",
        "share_identities": [],
        "market_cap_allowed_only_when": "not_applicable",
        "lineage": "DNSE_/price/ohlc",
    },
}


def _date(value: Any) -> str | None:
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (TypeError, ValueError):
        return None


def _ticker(instrument: Mapping[str, Any]) -> str:
    return str(instrument.get("canonical_ticker") or "").strip().upper()


def _action_blockers(actions: Sequence[Mapping[str, Any]], valuation_date: str) -> list[str]:
    """Name unresolved share-changing actions without inferring an effective date.

    A record/publication date may establish that uncertainty was known before
    the valuation date; it is never substituted for execution or an ex-date.
    An undated potential share change remains fail-closed because its position
    cannot be proven.
    """
    blockers: set[str] = set()
    for action in actions:
        if not action.get("potential_share_change"):
            continue
        lifecycle = str(action.get("lifecycle") or "")
        effective = _date(action.get("effective_date"))
        known_on = next((_date(action.get(name)) for name in ("disclosed_on", "record_date", "published_at")
                         if _date(action.get(name)) is not None), None)
        if effective is None:
            blockers.add("CORPORATE_ACTION_TIMING_UNRESOLVED_NO_EX_DATE_INFERRED")
        elif effective <= valuation_date and lifecycle != "completed_with_resulting_common_shares":
            blockers.add("CORPORATE_ACTION_INVALIDATES_CURRENT_SHARE_COVERAGE")
        elif known_on is not None and known_on <= valuation_date and lifecycle != "completed_with_resulting_common_shares":
            blockers.add("CORPORATE_ACTION_CURRENT_SHARE_STATE_UNRESOLVED")
    return sorted(blockers)


def build_current_share_timeline(
    instrument: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]], *,
    valuation_date: str, corporate_actions: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Return an evidence-driven timeline and one fail-closed eligibility decision."""
    target = _date(valuation_date)
    if target is None:
        raise ValueError("valuation_date must be an ISO date")
    ticker = _ticker(instrument)
    applicable = [dict(row) for row in candidates
                  if str(row.get("canonical_ticker") or ticker).strip().upper() == ticker]
    observed_identities = sorted({str(row.get("identity") or "unknown") for row in applicable})
    timeline: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    for row in applicable:
        identity = str(row.get("identity") or "unknown")
        valid_from, valid_through = _date(row.get("effective_date")), _date(row.get("coverage_through"))
        count = row.get("value")
        explicitly_common = identity == COMMON_OUTSTANDING
        qualified = row.get("qualification_state") == "QUALIFIED"
        count_valid = isinstance(count, int) and not isinstance(count, bool) and count > 0
        usable = explicitly_common and qualified and count_valid and valid_from is not None and valid_through is not None
        reasons: list[str] = []
        if not explicitly_common:
            reasons.append("SHARE_IDENTITY_NOT_CURRENT_COMMON_OUTSTANDING")
        if not qualified:
            reasons.append("CANDIDATE_NOT_QUALIFIED")
        if not count_valid:
            reasons.append("SHARE_COUNT_INVALID_OR_ABSENT")
        if valid_from is None or valid_through is None:
            reasons.append("EFFECTIVE_COVERAGE_NOT_EXPLICIT")
        entry = {
            "instrument": ticker, "share_identity": identity, "share_count": count if count_valid else None,
            "valid_from": valid_from, "valid_through": valid_through,
            "source_authority": row.get("source_authority"), "evidence_ids": row.get("evidence_ids", []),
            "corporate_action_ids": row.get("corporate_action_ids", []),
            "qualification_state": "QUALIFIED" if usable else "BLOCKED",
            "valuation_use": "current_market_capitalization_only" if usable else "not_eligible",
            "warnings": reasons, "blockers": [], "payload_identity": row.get("payload_identity"),
        }
        timeline.append(entry)
        if usable and valid_from <= target <= valid_through:
            eligible.append({**entry, "_source": row})

    action_blockers = _action_blockers(corporate_actions, target)
    if action_blockers:
        return {"contract_version": CONTRACT_VERSION, "timeline": timeline, "status": "SHARE_BLOCKED",
                "qualification_state": "BLOCKED", "identity": None, "value": None,
                "observed_identities": observed_identities, "reason_codes": action_blockers,
                "allowed_use": "current_market_capitalization_only"}
    if not eligible:
        return {"contract_version": CONTRACT_VERSION, "timeline": timeline, "status": "SHARE_BLOCKED",
                "qualification_state": "STALE_OR_MISSING", "identity": None, "value": None,
                "observed_identities": observed_identities,
                "reason_codes": ["CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN"],
                "allowed_use": "current_market_capitalization_only"}
    values = {entry["share_count"] for entry in eligible}
    if len(values) != 1:
        return {"contract_version": CONTRACT_VERSION, "timeline": timeline, "status": "SHARE_BLOCKED",
                "qualification_state": "CONFLICT", "identity": None, "value": None,
                "observed_identities": observed_identities,
                "reason_codes": ["EQUALLY_QUALIFIED_CURRENT_SHARE_VALUES_CONFLICT"],
                "allowed_use": "current_market_capitalization_only"}
    chosen = sorted(eligible, key=lambda item: (item["valid_through"], str(item.get("payload_identity") or "")))[-1]
    return {"contract_version": CONTRACT_VERSION, "timeline": timeline, "status": "SHARE_READY",
            "qualification_state": "QUALIFIED", "identity": COMMON_OUTSTANDING,
            "value": chosen["share_count"], "effective_date": chosen["valid_from"],
            "coverage_through": chosen["valid_through"], "lineage": chosen["_source"],
            "observed_identities": observed_identities, "reason_codes": [],
            "allowed_use": "current_market_capitalization_only"}
