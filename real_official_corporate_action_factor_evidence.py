"""Bounded selection and fail-closed bridge for real HNX corporate-action evidence.

The HNX rights-event index is evidence for its explicit ex-date only.  This module
preserves that fact and its source identity without treating a calendar row as a
ledger observation: ratio, executed lifecycle, and publication evidence remain
required before the existing factor-chain pipeline can be invoked.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

VERSION = "1.0.0"
SHARE_AFFECTING_EVENT_TYPES = ("STOCK_DIVIDEND", "BONUS", "RIGHTS")
_TYPE_RANK = {"STOCK_DIVIDEND": 0, "BONUS": 1, "RIGHTS": 2}


def index_gap_classification(event: Mapping[str, Any]) -> tuple[str, list[str]]:
    """Classify an HNX index event without assigning facts the index lacks."""
    if not event.get("ex_date"):
        return "MISSING_EXPLICIT_EX_DATE", ["missing_explicit_official_ex_date"]
    return "OTHER_EVIDENCE_GAP", [
        "explicit_official_ex_date_present",
        "missing_documentary_stock_ratio_or_share_counts",
        "missing_documentary_executed_lifecycle_evidence",
        "missing_documentary_publication_cutoff",
    ]


def bridge_index_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Return a source-bound ex-date bridge, deliberately not a ledger observation."""
    classification, reasons = index_gap_classification(event)
    return {
        "bridge_contract": "hnx_rights_event_index_ex_date_bridge/v1",
        "bridge_scope": "EXPLICIT_EX_DATE_ONLY_NOT_LEDGER_OBSERVATION",
        "ticker": event.get("ticker"),
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type"),
        "ex_date": event.get("ex_date"),
        "record_date": event.get("record_date"),
        "execution_date": event.get("execution_date"),
        "source_contract": event.get("source"),
        "source_identity": event.get("source_identity"),
        "source_record_identity": event.get("source_record_identity"),
        "source_url": event.get("source_url"),
        "source_document_identities": {
            "index_source_record_identity": event.get("source_record_identity"),
            "retained_detail_document_ids": [],
        },
        "official_ex_date_status": "EXPLICIT_OFFICIAL" if event.get("ex_date") else "MISSING_EXPLICIT_OFFICIAL",
        "ratio_share_evidence_status": "MISSING_OFFICIAL_DOCUMENTARY_EVIDENCE",
        "execution_status": "NOT_EXECUTED_NO_DOCUMENTARY_EVIDENCE",
        "knowledge_cutoff_status": "MISSING_DOCUMENTARY_PUBLICATION_CUTOFF",
        "ledger_qualification": "NOT_EVALUATED_NOT_LEDGER_OBSERVATION",
        "factor_status": "NOT_QUALIFIED",
        "factor_chain_classification": classification,
        "pit_raw_input_status": "NOT_REQUESTED_NO_REAL_FACTOR_CHAIN_QUALIFIED",
        "pit_series_status": "NOT_EVALUATED_NO_REAL_FACTOR_CHAIN_QUALIFIED",
        "classification": classification,
        "reason_codes": reasons,
        "exact_blocker_codes": reasons,
        "ledger_observation_emitted": False,
    }


def select_candidates(events: Iterable[Mapping[str, Any]], *, reference_tickers: Iterable[str],
                      cutoff_date: str, limit: int = 3,
                      listing_by_ticker: Mapping[str, Mapping[str, Any]] | None = None,
                      admitted_route_tickers: Iterable[str] = ()) -> dict[str, Any]:
    """Select at most ``limit`` current, past, ex-date-bearing share events.

    The retained index supplies the event facts.  When a retained official listing
    collection is supplied, HOSE membership is a selection preference only; it is
    never treated as a listing-status or PIT-universe assertion.  The optional
    admitted-route set is likewise a request-admission preference, not evidence.
    A future execution/payment date is never read as evidence of execution.
    """
    if not 1 <= limit <= 3:
        raise ValueError("candidate_limit_must_be_between_1_and_3")
    universe = {str(ticker).upper() for ticker in reference_tickers}
    listings = {str(ticker).upper(): value for ticker, value in (listing_by_ticker or {}).items()}
    admitted_routes = {str(ticker).upper() for ticker in admitted_route_tickers}
    eligible: list[Mapping[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for event in events:
        ticker = str(event.get("ticker") or "").upper()
        event_type = str(event.get("event_type") or "")
        ex_date = event.get("ex_date")
        if event_type not in SHARE_AFFECTING_EVENT_TYPES:
            continue
        if ticker not in universe:
            excluded.append({"ticker": ticker, "event_id": event.get("event_id"), "reason": "not_in_reference_collection"})
        elif not ex_date:
            excluded.append({"ticker": ticker, "event_id": event.get("event_id"), "reason": "missing_explicit_ex_date"})
        # The retained index's event_state is a snapshot-time label.  It can read
        # UPCOMING in its August capture even when the explicit ex-date is before
        # this bounded September audit.  The real source fact relevant to this
        # completed-event cohort is therefore the explicit date itself; this does
        # not turn an index execution_date into execution evidence.
        elif str(ex_date) > cutoff_date:
            excluded.append({"ticker": ticker, "event_id": event.get("event_id"), "reason": "ex_date_after_cutoff"})
        elif event.get("execution_date") and str(event["execution_date"]) > cutoff_date:
            excluded.append({"ticker": ticker, "event_id": event.get("event_id"), "reason": "future_execution_date_not_treated_as_executed"})
        else:
            eligible.append(event)
    def rank(row: Mapping[str, Any]) -> tuple[Any, ...]:
        ticker = str(row.get("ticker") or "").upper()
        listing = listings.get(ticker, {})
        hose = str(listing.get("exchange_or_market") or "").upper() == "HOSE"
        has_route = ticker in admitted_routes
        in_snapshot_horizon = "2026-08-24" <= str(row.get("ex_date")) <= "2026-09-24"
        return (
            0 if hose else 1,
            "".join(chr(255 - ord(char)) for char in str(row.get("ex_date"))),
            0 if has_route else 1,
            0 if in_snapshot_horizon else 1,
            ticker, str(row.get("event_id")),
        )
    ranked = sorted(eligible, key=rank)
    candidates = [bridge_index_event(event) for event in ranked[:limit]]
    return {
        "selection_contract": "real_official_corporate_action_factor_evidence_candidate_selection/v1",
        "cutoff_date": cutoff_date,
        "candidate_limit": limit,
        "reference_collection_ticker_count": len(universe),
        "eligible_event_count": len(eligible),
        "selected_count": len(candidates),
        "selection_order": "supported_share_affecting__hose_listed__newest_ex_date__admitted_route__prospective_snapshot_horizon__ticker__event_id",
        "candidates": candidates,
        "excluded_completed_event_reasons": excluded,
    }
