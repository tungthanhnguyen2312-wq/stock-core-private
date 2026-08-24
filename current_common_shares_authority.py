"""Market-wide current common-share authority and fitness-for-use.

Contract: current_common_shares_authority/v1

Question answered for ticker T and completed session S: what common-share
count is known to be valid through S, with what semantic identity, evidence,
temporal coverage, and authority tier?

This is not a valuation engine and not a source promotion. It inventories
already-retained share observations, keeps their identities separate, applies
the P3-F2/P3-F4 coverage-through-session gate, and emits one terminal
disposition per official-universe ticker.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Mapping, Sequence

from current_share_authority import COMMON_OUTSTANDING, build_current_share_timeline
from current_share_basis_capability_reconciliation import derive_common_shares_from_components
from field_temporal_contract import stable_id
from market_wide_current_shares_resolver import (
    NON_SHARE_CHANGING_EVENT_CODES,
    PROVIDER_SHARE_CONCEPT,
    PROVIDER_SOURCE,
    SHARE_CHANGING_EVENT_CODES,
)
from market_wide_current_valuation_input_scaleout import official_research_universe_tickers

CONTRACT_VERSION = "current_common_shares_authority/v1"
ARTIFACT_TYPE = "CURRENT_COMMON_SHARES_AUTHORITY"

QUALIFIED_CURRENT_COMMON_SHARES = "QUALIFIED_CURRENT_COMMON_SHARES"
QUALIFIED_OFFICIAL_ANCHOR_NOT_CURRENT = "QUALIFIED_OFFICIAL_ANCHOR_NOT_CURRENT"
PROVIDER_REPORTED_CURRENT_RESEARCH = "PROVIDER_REPORTED_CURRENT_RESEARCH"
PROVIDER_REPORTED_LAGGED = "PROVIDER_REPORTED_LAGGED"
UNVERIFIABLE_FRESHNESS = "UNVERIFIABLE_FRESHNESS"
SEMANTIC_IDENTITY_UNRESOLVED = "SEMANTIC_IDENTITY_UNRESOLVED"
CORPORATE_ACTION_RECONCILIATION_REQUIRED = "CORPORATE_ACTION_RECONCILIATION_REQUIRED"
UNAVAILABLE = "UNAVAILABLE"

TERMINAL_DISPOSITIONS = frozenset({
    QUALIFIED_CURRENT_COMMON_SHARES, QUALIFIED_OFFICIAL_ANCHOR_NOT_CURRENT,
    PROVIDER_REPORTED_CURRENT_RESEARCH, PROVIDER_REPORTED_LAGGED,
    UNVERIFIABLE_FRESHNESS, SEMANTIC_IDENTITY_UNRESOLVED,
    CORPORATE_ACTION_RECONCILIATION_REQUIRED, UNAVAILABLE,
})

FITNESS_AUTHORITATIVE = "AUTHORITATIVE_CURRENT_MARKET_CAP"
FITNESS_RESEARCH = "RESEARCH_USABLE_NOT_AUTHORITATIVE"
FITNESS_NOT_ELIGIBLE = "NOT_ELIGIBLE"

SHARE_CHANGING_OFFICIAL_TYPES = frozenset({"STOCK_DIVIDEND", "BONUS", "RIGHTS"})
NON_SHARE_CHANGING_OFFICIAL_TYPES = frozenset({"CASH_DIVIDEND", "AGM"})
WEIGHTED_AVERAGE_IDENTITIES = frozenset({
    "weighted_average_basic_shares", "weighted_average_basic_shares_outstanding",
    "weighted_average_diluted_shares_outstanding", "diluted_shares",
})
PERIOD_END_IDENTITIES = frozenset({"period_end_shares", "period_end_shares_outstanding"})
ISSUED_IDENTITIES = frozenset({"issued_shares", "ISSUED_SHARES", PROVIDER_SHARE_CONCEPT})

SOURCE_AND_SEMANTIC_QUALIFICATION = {
    "vci_overview_issue_share": {
        "native_field": "issue_share",
        "canonical_identity": "issued_shares",
        "proven": True,
        "promotable_to_current_common_shares": False,
        "authority": "NOT_PROMOTED",
        "evidence": "P3-F5/P3-F6/resolver: ISSUED_SHARES, no treasury treatment, no effective interval",
    },
    "kbs_public_outstanding_shares": {
        "native_field": "outstanding_shares",
        "canonical_identity": "provider_reported_outstanding_shares",
        "proven": False,
        "promotable_to_current_common_shares": False,
        "authority": "UNAVAILABLE",
        "evidence": "2026-08-24 pilot HTTP 400 for HPG/VCB/SSI/VNM/FPT/PAN; no schema or effective interval",
    },
    "hose_public_outstanding_volume": {
        "native_field": "outStanding",
        "canonical_identity": "exchange_outstanding_volume",
        "proven": True,
        "promotable_to_current_common_shares": False,
        "authority": "NOT_ACCOUNTING_COMMON_SHARES_OUTSTANDING",
        "evidence": "hose_public_xhr_and_periodic_series_recon: exchange-labelled outstanding volume",
    },
    "hose_listing_volume": {
        "native_field": "listingVolume",
        "canonical_identity": "listed_shares",
        "proven": True,
        "promotable_to_current_common_shares": False,
        "authority": "LISTING_REGISTRATION_VOLUME",
        "evidence": "HOSE listing registration, not outstanding/common",
    },
    "hnx_kllh": {
        "native_field": "KLLH (Cổ phiếu)",
        "canonical_identity": "exchange_reported_circulating_shares",
        "proven": True,
        "promotable_to_current_common_shares": False,
        "authority": "CURRENT_EXCHANGE_PROFILE_ONLY",
        "evidence": "HNX circulating field; treasury/accounting scope unavailable; distinct from KLNY",
    },
    "hnx_klny": {
        "native_field": "KLNY (Cổ phiếu)",
        "canonical_identity": "listed_shares",
        "proven": True,
        "promotable_to_current_common_shares": False,
        "authority": "HNX_LISTED_QUANTITY",
        "evidence": "MBS KLLH 1,000,933,410 < KLNY 1,000,963,451",
    },
    "hnx_kldkgd": {
        "native_field": "KLĐKGD (Cổ phiếu)",
        "canonical_identity": "registered_for_trading_shares",
        "proven": True,
        "promotable_to_current_common_shares": False,
        "authority": "UPCOM_REGISTERED_TRADING_QUANTITY",
        "evidence": "Never aliased to KLNY",
    },
    "official_executed_current_common_after_event": {
        "native_field": "current_shares_outstanding_after_event",
        "canonical_identity": COMMON_OUTSTANDING,
        "proven": True,
        "promotable_to_current_common_shares": True,
        "authority": "APPROVED_EXISTING_WHEN_COVERAGE_INCLUDES_SESSION",
        "evidence": "HPG 8,442,964,520 effective 2026-07-02; coverage_through 2026-07-30 only",
    },
    "official_period_end_shares": {
        "native_field": "period_end_shares_outstanding",
        "canonical_identity": "period_end_shares",
        "proven": True,
        "promotable_to_current_common_shares": False,
        "authority": "HISTORICAL_BALANCE_SHEET_ONLY",
        "evidence": "VCB/VNM FY2024 period-end are not current counts",
    },
    "weighted_average_basic_or_diluted": {
        "native_field": "weighted_average_basic_shares_outstanding",
        "canonical_identity": "weighted_average_basic_shares",
        "proven": True,
        "promotable_to_current_common_shares": False,
        "authority": "EARNINGS_DENOMINATOR_ONLY",
        "evidence": "EPS/accounting denominator; never current market-cap shares",
    },
    "dnse_ohlc": {
        "native_field": None,
        "canonical_identity": None,
        "proven": True,
        "promotable_to_current_common_shares": False,
        "authority": "NO_SHARE_FIELD_IN_EXISTING_CONTRACT",
        "evidence": "current_share_authority.SOURCE_AUTHORITY_INVENTORY",
    },
}

TEMPORAL_SHARE_CONTRACT = {
    "anchor_semantics": (
        "An official current-common identity is an executed resulting count with an "
        "explicit effective date. A period-end figure is an opening/historical identity, "
        "never current by itself. Provider issue_share is ISSUED_SHARES with an observation "
        "date, not an effective interval."
    ),
    "event_reconciliation": (
        "Subsequent qualified executed share-changing events (stock dividend, bonus, "
        "rights, split, consolidation, executed ESOP, treasury cancellation) with a "
        "directly stated resulting count update the chain. The same events without "
        "resulting shares terminate coverage. Planned/approved issuance is not execution. "
        "Ex-dates and execution dates are never inferred."
    ),
    "coverage_through_session": (
        "coverage_through is the latest explicit corroboration/valid_through date. "
        "current = valid_from <= session <= coverage_through and no unresolved "
        "share-changing action in that interval. Forward-fill is prohibited."
    ),
    "synthetic_forward_fill": "PROHIBITED",
    "issued_minus_treasury": "PROHIBITED_UNLESS_BOTH_COMPONENTS_EXPLICIT",
    "weighted_average_as_current": "PROHIBITED",
}


def _date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    head = text.split()[0].split("T")[0]
    try:
        return datetime.strptime(head, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def coverage_includes_session(valid_from: str | None, valid_through: str | None, session: str) -> bool:
    start, end, target = _date(valid_from), _date(valid_through), _date(session)
    return bool(start and end and target and start <= target <= end)


def classify_event_share_effect(event: Mapping[str, Any]) -> str:
    official_type = str(event.get("event_type") or "").strip().upper()
    if official_type in SHARE_CHANGING_OFFICIAL_TYPES:
        return "share_changing"
    if official_type in NON_SHARE_CHANGING_OFFICIAL_TYPES:
        return "not_share_changing"
    code = str(event.get("event_code") or "").strip().upper()
    if code in SHARE_CHANGING_EVENT_CODES:
        return "share_changing"
    if code in NON_SHARE_CHANGING_EVENT_CODES:
        return "not_share_changing"
    return "unclassified"


def _event_execution_date(event: Mapping[str, Any]) -> str | None:
    return _date(event.get("execution_date") or event.get("effective_date") or event.get("exright_date"))


def _event_known_on(event: Mapping[str, Any]) -> str | None:
    dates = [_date(event.get(name)) for name in ("execution_date", "effective_date", "ex_date", "record_date", "published_at", "exright_date")]
    present = [item for item in dates if item]
    return min(present) if present else None


def reconcile_subsequent_events(
    events: Sequence[Mapping[str, Any]], *, after_date: str | None, session: str,
) -> dict[str, Any]:
    """Position share-changing events after an anchor/observation without inferring dates."""
    considered: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    after = _date(after_date)
    target = _date(session)
    if target is None:
        raise ValueError("session must be an ISO date")
    for event in events:
        effect = classify_event_share_effect(event)
        if effect == "not_share_changing":
            continue
        execution = _event_execution_date(event)
        known_on = _event_known_on(event)
        planned = str(event.get("event_state") or "").upper() == "UPCOMING" or (
            execution is None and known_on is not None and known_on > target
        )
        row = {
            "event_id": event.get("event_id") or event.get("event_code"),
            "event_type": event.get("event_type") or event.get("event_code"),
            "share_effect": effect,
            "execution_date": execution,
            "known_on": known_on,
            "resulting_shares": event.get("resulting_shares") or event.get("shares_after"),
            "planned": planned,
            "lifecycle": event.get("lifecycle"),
        }
        if planned:
            row["disposition"] = "PLANNED_NOT_EXECUTION"
            considered.append(row)
            continue
        if effect == "unclassified":
            warnings.append("UNCLASSIFIED_OFFICIAL_EVENT_NOT_TREATED_AS_SHARE_CHANGE_WITHOUT_TYPE_PROOF")
            row["disposition"] = "UNCLASSIFIED_NOT_PROVEN_SHARE_CHANGING"
            considered.append(row)
            continue
        in_gap = False
        if execution is not None:
            in_gap = (after is None or execution > after) and execution <= target
        elif known_on is None:
            in_gap = True
        else:
            in_gap = (after is None or known_on > after) and known_on <= target
        if not in_gap:
            continue
        considered.append(row)
        resulting = row["resulting_shares"]
        resulting_valid = isinstance(resulting, int) and not isinstance(resulting, bool) and resulting > 0
        if execution is None:
            blockers.append("CORPORATE_ACTION_TIMING_UNRESOLVED_NO_EX_DATE_INFERRED")
            row["disposition"] = "EXECUTION_UNRESOLVED"
        elif not resulting_valid:
            blockers.append("CORPORATE_ACTION_INVALIDATES_CURRENT_SHARE_COVERAGE")
            row["disposition"] = "EXECUTED_WITHOUT_RESULTING_SHARES"
        else:
            row["disposition"] = "EXECUTED_WITH_RESULTING_SHARES"
            blockers.append("CORPORATE_ACTION_REQUIRES_CHAIN_RECONCILIATION")
    unique_blockers = sorted(set(blockers))
    unique_warnings = sorted(set(warnings))
    return {"considered": considered, "blockers": unique_blockers, "warnings": unique_warnings}


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if float(value) <= 0 or float(value) != int(value):
        return None
    return int(value)


def _identity_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(record)
    payload.pop("content_identity", None)
    return payload


def _terminal(
    *,
    ticker: str,
    session: str,
    authority_tier: str,
    native_identity: str | None,
    canonical_identity: str | None,
    value: int | None,
    source_evidence_identity: str | None,
    observed_at: str | None,
    published_at: str | None,
    effective_at: str | None,
    anchor_date: str | None,
    coverage_through: str | None,
    coverage_through_session: bool,
    subsequent: Sequence[Mapping[str, Any]],
    blockers: Sequence[str],
    warnings: Sequence[str],
    lineage: Mapping[str, Any],
    observed_identities: Sequence[str],
) -> dict[str, Any]:
    if authority_tier == QUALIFIED_CURRENT_COMMON_SHARES:
        fitness = FITNESS_AUTHORITATIVE
    elif authority_tier in {QUALIFIED_OFFICIAL_ANCHOR_NOT_CURRENT, PROVIDER_REPORTED_CURRENT_RESEARCH, PROVIDER_REPORTED_LAGGED}:
        fitness = FITNESS_RESEARCH
    else:
        fitness = FITNESS_NOT_ELIGIBLE
        value = None
    record = {
        "ticker": ticker,
        "as_of_session": session,
        "native_share_identity": native_identity,
        "canonical_share_identity": canonical_identity,
        "value": value,
        "source_evidence_identity": source_evidence_identity,
        "observed_at": observed_at,
        "published_at": published_at,
        "effective_at": effective_at,
        "anchor_date": anchor_date,
        "subsequent_qualified_share_changing_events": list(subsequent),
        "coverage_through": coverage_through,
        "coverage_through_session": coverage_through_session,
        "authority_tier": authority_tier,
        "fitness_for_use": fitness,
        "blockers": list(blockers),
        "warnings": list(warnings),
        "observed_identities": list(observed_identities),
        "lineage": dict(lineage),
    }
    record["content_identity"] = stable_id(_identity_payload(record))
    return record


def resolve_ticker_share_authority(
    ticker: str,
    *,
    session: str,
    resolver_row: Mapping[str, Any] | None = None,
    official_common: Mapping[str, Any] | None = None,
    official_period_end: Mapping[str, Any] | None = None,
    official_events: Sequence[Mapping[str, Any]] = (),
    weighted_average: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Emit exactly one terminal disposition for one ticker."""
    t = str(ticker).strip().upper()
    target = _date(session)
    if target is None:
        raise ValueError("session must be an ISO date")
    identities: list[str] = []
    warnings: list[str] = []
    if official_common:
        identities.append(str(official_common.get("identity") or COMMON_OUTSTANDING))
    if official_period_end:
        identities.append(str(official_period_end.get("identity") or "period_end_shares"))
    if weighted_average:
        identities.append(str(weighted_average.get("identity") or "weighted_average_basic_shares"))
        warnings.append("WEIGHTED_AVERAGE_SHARES_ARE_NOT_CURRENT_COMMON_SHARES")
    resolver_row = dict(resolver_row or {})
    if resolver_row.get("share_concept"):
        identities.append(str(resolver_row["share_concept"]))
    if derive_common_shares_from_components(None, None)["status"] == "UNAVAILABLE":
        warnings.append("ISSUED_MINUS_TREASURY_NOT_INFERRED")

    common_value = _positive_int((official_common or {}).get("value"))
    common_from = _date((official_common or {}).get("effective_date") or (official_common or {}).get("effective_on"))
    common_through = _date((official_common or {}).get("coverage_through"))
    if official_common and common_value and common_from:
        candidates = [{
            "canonical_ticker": t,
            "identity": COMMON_OUTSTANDING,
            "value": common_value,
            "effective_date": common_from,
            "coverage_through": common_through,
            "qualification_state": official_common.get("qualification_state") or "QUALIFIED",
            "source_authority": official_common.get("source") or "official_corporate_action_result",
            "evidence_ids": [official_common.get("citation_id")] if official_common.get("citation_id") else [],
            "payload_identity": official_common.get("citation_id"),
        }]
        actions = []
        subsequent = reconcile_subsequent_events(official_events, after_date=common_from, session=target)
        for item in subsequent["considered"]:
            if item.get("planned"):
                continue
            if item.get("share_effect") != "share_changing":
                continue
            actions.append({
                "potential_share_change": True,
                "effective_date": item.get("execution_date"),
                "record_date": item.get("known_on"),
                "lifecycle": (
                    "completed_with_resulting_common_shares"
                    if item.get("disposition") == "EXECUTED_WITH_RESULTING_SHARES" else "announced"
                ),
            })
        timeline = build_current_share_timeline(
            {"canonical_ticker": t}, candidates, valuation_date=target, corporate_actions=actions,
        )
        through_session = coverage_includes_session(common_from, common_through, target)
        if timeline.get("status") == "SHARE_READY" and through_session:
            return _terminal(
                ticker=t, session=target, authority_tier=QUALIFIED_CURRENT_COMMON_SHARES,
                native_identity="current_shares_outstanding_after_event",
                canonical_identity=COMMON_OUTSTANDING, value=timeline["value"],
                source_evidence_identity=str((official_common or {}).get("citation_id") or "official_common_share_anchor"),
                observed_at=_date((official_common or {}).get("corroborated_on") or (official_common or {}).get("observed_at")),
                published_at=_date((official_common or {}).get("published_at")),
                effective_at=common_from, anchor_date=common_from,
                coverage_through=common_through, coverage_through_session=True,
                subsequent=subsequent["considered"], blockers=[], warnings=warnings,
                lineage={"official_common": dict(official_common), "timeline_status": timeline.get("status")},
                observed_identities=sorted(set(identities)),
            )
        blockers = list(timeline.get("reason_codes") or [])
        if not through_session:
            blockers.append("CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN_THROUGH_PRICE_SESSION")
        blockers.extend(subsequent["blockers"])
        warnings.extend(subsequent["warnings"])
        return _terminal(
            ticker=t, session=target, authority_tier=QUALIFIED_OFFICIAL_ANCHOR_NOT_CURRENT,
            native_identity="current_shares_outstanding_after_event",
            canonical_identity=COMMON_OUTSTANDING, value=common_value,
            source_evidence_identity=str((official_common or {}).get("citation_id") or "official_common_share_anchor"),
            observed_at=_date((official_common or {}).get("corroborated_on") or (official_common or {}).get("observed_at")),
            published_at=_date((official_common or {}).get("published_at")),
            effective_at=common_from, anchor_date=common_from,
            coverage_through=common_through, coverage_through_session=False,
            subsequent=subsequent["considered"], blockers=sorted(set(blockers)),
            warnings=sorted(set(warnings)),
            lineage={"official_common": dict(official_common), "timeline_status": timeline.get("status")},
            observed_identities=sorted(set(identities)),
        )

    if official_period_end:
        warnings.append("PERIOD_END_SHARES_ARE_NOT_CURRENT_COMMON_SHARES")
    if weighted_average:
        identities.append(str(weighted_average.get("identity") or "weighted_average_basic_shares"))

    authority = str(resolver_row.get("authority") or "unavailable")
    observed_at = _date(resolver_row.get("observation_date") or resolver_row.get("observed_at"))
    provider_value = _positive_int(resolver_row.get("value") if authority not in {
        "provider_reported_stale", "provider_reported_unverifiable_freshness", "unavailable",
        "unknown_observation_date", "unresolved_error",
    } else resolver_row.get("provider_value"))
    if provider_value is None and authority in {"provider_reported_lagged", "provider_reported_current"}:
        provider_value = _positive_int(resolver_row.get("value"))
    subsequent = reconcile_subsequent_events(official_events, after_date=observed_at, session=target)
    event_blockers = list(subsequent["blockers"])
    warnings.extend(subsequent["warnings"])
    if authority == "qualified_official":
        official_value = _positive_int(resolver_row.get("value") or resolver_row.get("official_anchor_value"))
        official_from = _date(resolver_row.get("official_anchor_effective_date"))
        return _terminal(
            ticker=t, session=target, authority_tier=QUALIFIED_OFFICIAL_ANCHOR_NOT_CURRENT,
            native_identity="current_shares_outstanding_after_event",
            canonical_identity=COMMON_OUTSTANDING, value=official_value,
            source_evidence_identity=str(resolver_row.get("official_anchor_citation_id") or resolver_row.get("source") or "official_share_basis_citation"),
            observed_at=observed_at, published_at=None, effective_at=official_from, anchor_date=official_from,
            coverage_through=None, coverage_through_session=False, subsequent=subsequent["considered"],
            blockers=sorted(set(["CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN_THROUGH_PRICE_SESSION"] + event_blockers)),
            warnings=sorted(set(warnings + ["OFFICIAL_ANCHOR_IS_NOT_CURRENT_WITHOUT_COVERAGE_THROUGH_SESSION"])),
            lineage={"resolver": dict(resolver_row)},
            observed_identities=sorted(set(identities)),
        )
    if authority == "provider_reported_unverifiable_freshness" or (
        resolver_row.get("undated_share_relevant_events") and not subsequent["considered"]
    ):
        return _terminal(
            ticker=t, session=target, authority_tier=UNVERIFIABLE_FRESHNESS,
            native_identity=PROVIDER_SOURCE, canonical_identity=PROVIDER_SHARE_CONCEPT, value=None,
            source_evidence_identity=PROVIDER_SOURCE, observed_at=observed_at, published_at=None,
            effective_at=None, anchor_date=observed_at, coverage_through=None,
            coverage_through_session=False, subsequent=subsequent["considered"],
            blockers=sorted(set(["STALE_SHARE_FAIL_CLOSED_CORPORATE_ACTION_OR_UNVERIFIABLE_FRESHNESS",
                                 str(resolver_row.get("reason") or "missing_explicit_official_ex_date_on_share_relevant_event")] + event_blockers)),
            warnings=sorted(set(warnings)),
            lineage={"resolver": dict(resolver_row), "period_end": dict(official_period_end or {})},
            observed_identities=sorted(set(identities)),
        )
    if authority == "provider_reported_stale" or event_blockers:
        return _terminal(
            ticker=t, session=target, authority_tier=CORPORATE_ACTION_RECONCILIATION_REQUIRED,
            native_identity=PROVIDER_SOURCE, canonical_identity=PROVIDER_SHARE_CONCEPT, value=None,
            source_evidence_identity=PROVIDER_SOURCE, observed_at=observed_at, published_at=None,
            effective_at=None, anchor_date=observed_at, coverage_through=None,
            coverage_through_session=False, subsequent=subsequent["considered"],
            blockers=sorted(set(["STALE_SHARE_FAIL_CLOSED_CORPORATE_ACTION_OR_UNVERIFIABLE_FRESHNESS"] + event_blockers + (
                [str(resolver_row["reason"])] if resolver_row.get("reason") else []
            ))),
            warnings=sorted(set(warnings)),
            lineage={"resolver": dict(resolver_row)},
            observed_identities=sorted(set(identities)),
        )
    if authority == "provider_reported_current" and provider_value is not None:
        return _terminal(
            ticker=t, session=target, authority_tier=PROVIDER_REPORTED_CURRENT_RESEARCH,
            native_identity=PROVIDER_SOURCE, canonical_identity=PROVIDER_SHARE_CONCEPT, value=provider_value,
            source_evidence_identity=PROVIDER_SOURCE, observed_at=observed_at, published_at=None,
            effective_at=None, anchor_date=observed_at, coverage_through=observed_at,
            coverage_through_session=bool(observed_at and observed_at >= target),
            subsequent=subsequent["considered"],
            blockers=["CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN_THROUGH_PRICE_SESSION"],
            warnings=sorted(set(warnings + ["ISSUED_SHARES_ARE_NOT_COMMON_SHARES_OUTSTANDING"])),
            lineage={"resolver": dict(resolver_row)},
            observed_identities=sorted(set(identities)),
        )
    if authority == "provider_reported_lagged" and provider_value is not None:
        return _terminal(
            ticker=t, session=target, authority_tier=PROVIDER_REPORTED_LAGGED,
            native_identity=PROVIDER_SOURCE, canonical_identity=PROVIDER_SHARE_CONCEPT, value=provider_value,
            source_evidence_identity=PROVIDER_SOURCE, observed_at=observed_at, published_at=None,
            effective_at=None, anchor_date=observed_at, coverage_through=observed_at,
            coverage_through_session=False, subsequent=subsequent["considered"],
            blockers=["CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN_THROUGH_PRICE_SESSION"],
            warnings=sorted(set(warnings + [
                "ISSUED_SHARES_ARE_NOT_COMMON_SHARES_OUTSTANDING",
                str(resolver_row.get("reason") or "observation predates the session"),
            ])),
            lineage={"resolver": dict(resolver_row), "observation_lag_days": resolver_row.get("observation_lag_days")},
            observed_identities=sorted(set(identities)),
        )
    if official_period_end and _positive_int(official_period_end.get("value")):
        return _terminal(
            ticker=t, session=target, authority_tier=SEMANTIC_IDENTITY_UNRESOLVED,
            native_identity="period_end_shares_outstanding", canonical_identity="period_end_shares",
            value=None, source_evidence_identity=str(official_period_end.get("citation_id") or "period_end"),
            observed_at=_date(official_period_end.get("effective_on")), published_at=None,
            effective_at=_date(official_period_end.get("effective_on")),
            anchor_date=_date(official_period_end.get("effective_on")), coverage_through=None,
            coverage_through_session=False, subsequent=subsequent["considered"],
            blockers=["SHARE_IDENTITY_NOT_CURRENT_COMMON_OUTSTANDING", "PERIOD_END_SHARES_ARE_NOT_CURRENT"],
            warnings=sorted(set(warnings)),
            lineage={"period_end": dict(official_period_end), "resolver": dict(resolver_row)},
            observed_identities=sorted(set(identities)),
        )
    return _terminal(
        ticker=t, session=target, authority_tier=UNAVAILABLE,
        native_identity=None, canonical_identity=None, value=None,
        source_evidence_identity=None, observed_at=observed_at, published_at=None,
        effective_at=None, anchor_date=None, coverage_through=None,
        coverage_through_session=False, subsequent=subsequent["considered"],
        blockers=["NO_TICKER_LEVEL_CURRENT_SHARE_BASIS_EVIDENCE_RETAINED"],
        warnings=sorted(set(warnings)),
        lineage={"resolver": dict(resolver_row)},
        observed_identities=sorted(set(identities)),
    )


def build_current_common_shares_authority(
    *,
    session: str,
    official_universe: Mapping[str, Any],
    share_resolution: Mapping[str, Any],
    official_common_anchors: Mapping[str, Mapping[str, Any]] | None = None,
    official_period_end_anchors: Mapping[str, Mapping[str, Any]] | None = None,
    official_events_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    source_identities: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Scale the temporal share contract across the official research universe."""
    tickers = official_research_universe_tickers(official_universe)
    if not tickers:
        raise ValueError("OFFICIAL_RESEARCH_UNIVERSE_EMPTY")
    resolved = (share_resolution or {}).get("tickers") or {}
    common_anchors = official_common_anchors or {}
    period_end = official_period_end_anchors or {}
    events = official_events_by_ticker or {}
    records: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        records[ticker] = resolve_ticker_share_authority(
            ticker, session=session, resolver_row=resolved.get(ticker),
            official_common=common_anchors.get(ticker), official_period_end=period_end.get(ticker),
            official_events=list(events.get(ticker) or []),
        )
    tiers = Counter(row["authority_tier"] for row in records.values())
    blockers = Counter(reason for row in records.values() for reason in row["blockers"])
    if set(records) != set(tickers) or any(row["authority_tier"] not in TERMINAL_DISPOSITIONS for row in records.values()):
        raise ValueError("SHARE_AUTHORITY_DISPOSITION_CONTRACT_BROKEN")
    unexplained = abs(len(records) - len(tickers))
    verdict = (
        "CURRENT_COMMON_SHARES_AUTHORITY_SCALEOUT_PASS"
        if tiers.get(QUALIFIED_CURRENT_COMMON_SHARES, 0) and not unexplained
        else "CURRENT_COMMON_SHARES_AUTHORITY_CEILING_ESTABLISHED"
    )
    artifact = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "as_of_session": _date(session),
        "universe_denominator": len(records),
        "source_identities": dict(source_identities or {}),
        "source_and_semantic_qualification": SOURCE_AND_SEMANTIC_QUALIFICATION,
        "temporal_share_contract": TEMPORAL_SHARE_CONTRACT,
        "records": records,
        "coverage": {
            "universe_denominator": len(records),
            "denominator_reconciles": unexplained == 0 and sum(tiers.values()) == len(records),
            "unexplained_count": unexplained,
            "authority_tier_distribution": dict(sorted(tiers.items())),
            "fitness_distribution": dict(sorted(Counter(row["fitness_for_use"] for row in records.values()).items())),
            "major_blocker_reasons": dict(sorted(blockers.items())),
            "qualified_current_common_shares": tiers.get(QUALIFIED_CURRENT_COMMON_SHARES, 0),
            "generic_authority_source_promoted": False,
        },
        "authority_boundary": {
            "historical_raw_as_traded": "NOT_PROMOTED",
            "pit": "BLOCKED",
            "backtesting": "BLOCKED",
            "sizing": "BLOCKED",
            "target_price": False,
            "dcf": False,
            "issued_shares_not_common_outstanding": True,
            "weighted_average_not_current": True,
            "period_end_not_current": True,
            "listed_not_outstanding": True,
            "official_not_automatically_current": True,
            "provider_not_automatically_authoritative": True,
            "valuation_formulas_unchanged": True,
            "frozen_sessions_not_regenerated": ["2026-08-21", "2026-08-24"],
        },
        "verdict": verdict,
    }
    if not artifact["coverage"]["denominator_reconciles"]:
        raise ValueError("OFFICIAL_UNIVERSE_DENOMINATOR_DRIFT")
    artifact["artifact_sha256"] = stable_id({key: value for key, value in artifact.items() if key not in {"artifact_sha256", "artifact_identity"}})
    artifact["artifact_identity"] = f"current_common_shares_authority:{artifact['artifact_sha256']}"
    return artifact


def authoritative_share_states(artifact: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Adapter consumed by the existing current-valuation engine."""
    states: dict[str, dict[str, Any]] = {}
    for ticker, row in (artifact.get("records") or {}).items():
        states[ticker] = {
            "status": "SHARE_READY" if row.get("authority_tier") == QUALIFIED_CURRENT_COMMON_SHARES else "SHARE_BLOCKED",
            "identity": row.get("canonical_share_identity"),
            "value": row.get("value") if row.get("authority_tier") == QUALIFIED_CURRENT_COMMON_SHARES else None,
            "authority_tier": row.get("authority_tier"),
            "fitness_for_use": row.get("fitness_for_use"),
        }
    return states
