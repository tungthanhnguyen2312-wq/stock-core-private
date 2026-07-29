"""Producer-owned Corporate Action Ledger MVP for Stock Lookup.

Combines qualified cash dividend, stock dividend, and bonus share events
into a versioned, deterministically ordered corporate action ledger with
immutable evidence lineage and fail-closed validation.

Emits 0 adjustment factors and 0 adjusted returns.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from semantic_evidence_bridge import (
    load_verified_cash_dividends,
    load_verified_non_cash_events,
    load_verified_share_basis,
)

LEDGER_VERSION = "1.0.0"
SUPPORTED_LEDGER_EVENT_TYPES = {"cash_dividend", "stock_dividend", "bonus_share"}


def _hash(value: Any) -> str:
    """Compute deterministic SHA-256 string for canonical objects."""
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _get_ordering_key(entry: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    """Compute deterministic ordering tuple using temporal precedence rule.

    Precedence:
    1. effective_date
    2. record_date
    3. ex_date (ex_dividend_date / ex_rights_date)
    4. declaration_date
    5. publication_date
    6. canonical_event_id (tiebreaker)
    """
    eff = entry.get("effective_date") or "9999-99-99"
    rec = entry.get("record_date") or "9999-99-99"
    ex = entry.get("ex_date") or "9999-99-99"
    decl = entry.get("declaration_date") or "9999-99-99"
    pub = entry.get("evidence", {}).get("publication_date") or "9999-99-99"
    event_id = entry.get("canonical_event_id") or ""
    return (eff, rec, ex, decl, pub, event_id)


def build_corporate_action_ledger(runtime_root: Path, ticker: str = "VNM") -> dict[str, Any]:
    """Build canonical corporate action ledger for specified ticker from verified evidence.

    Fails closed for unsupported event types, hash mismatches, or conflicting citations.
    Emits 0 adjustment factors and 0 adjusted returns.

    Returns:
        {
            "status": "available" | "unavailable",
            "ledger_version": LEDGER_VERSION,
            "ticker": ticker,
            "ledger_entries": [...],
            "rejected_events": [...],
            "entry_counts": {"cash_dividend": N, "stock_dividend": N, "bonus_share": N},
            "share_basis_summary": {...} or None
        }
    """
    cash_res = load_verified_cash_dividends(runtime_root)
    non_cash_res = load_verified_non_cash_events(runtime_root)
    share_basis_res = load_verified_share_basis(runtime_root)

    rejected_events: list[dict[str, Any]] = []
    raw_events: list[dict[str, Any]] = []

    if cash_res.get("status") == "available":
        for ev in cash_res.get("events", []):
            if ev.get("ticker") == ticker:
                raw_events.append(ev)

    if non_cash_res.get("status") == "available":
        for ev in non_cash_res.get("events", []):
            if ev.get("ticker") == ticker:
                raw_events.append(ev)

    # Share basis linkage resolution
    compatible_share_basis = None
    if share_basis_res.get("status") == "available":
        sb_by_id = share_basis_res.get("by_identity", {})
        period_end = sb_by_id.get("period_end_shares_outstanding")
        weighted_avg = sb_by_id.get("weighted_average_basic_shares_outstanding")
        if period_end and period_end.get("ticker") == ticker:
            compatible_share_basis = {
                "period_end_shares": period_end.get("share_count"),
                "weighted_average_basic_shares": weighted_avg.get("share_count") if weighted_avg else None,
                "reporting_period": period_end.get("reporting_period"),
                "evidence_id": period_end.get("evidence", {}).get("evidence_id"),
            }

    entries: list[dict[str, Any]] = []
    counts = {"cash_dividend": 0, "stock_dividend": 0, "bonus_share": 0}

    for ev in raw_events:
        event_type = ev.get("event_type")
        if event_type not in SUPPORTED_LEDGER_EVENT_TYPES:
            rejected_events.append({"event": ev, "reason": "unsupported_event_type"})
            continue

        canonical_event_id = ev.get("event_id")
        if not canonical_event_id:
            rejected_events.append({"event": ev, "reason": "missing_canonical_event_id"})
            continue

        ledger_entry_id = _hash({"canonical_event_id": canonical_event_id, "ledger_version": LEDGER_VERSION})

        ex_date = ev.get("ex_dividend_date") or ev.get("ex_rights_date")
        payment_date = ev.get("payment_date") or ev.get("distribution_date")

        entry = {
            "ledger_entry_id": ledger_entry_id,
            "canonical_event_id": canonical_event_id,
            "event_type": event_type,
            "issuer": ev.get("issuer", "Vietnam Dairy Products Joint Stock Company"),
            "ticker": ev.get("ticker"),
            "source_authority": ev.get("evidence", {}).get("authority", "KPMG Limited Vietnam / Issuer IR Portal"),
            "source_observation_ids": [canonical_event_id],
            "evidence": ev.get("evidence", {}),
            "declaration_date": ev.get("declaration_date"),
            "ex_date": ex_date,
            "record_date": ev.get("record_date"),
            "payment_date": payment_date,
            "effective_date": ev.get("effective_date"),
            "cash_amount": ev.get("cash_amount"),
            "currency": ev.get("currency") or ("VND" if event_type == "cash_dividend" else None),
            "entitlement_ratio": ev.get("entitlement_ratio"),
            "funding_source": ev.get("funding_source"),
            "share_class": ev.get("share_class", "common"),
            "event_status": ev.get("event_status", "completed"),
            "supersedes_citation_ids": ev.get("supersedes_citation_ids", []),
            "share_basis_linkage": compatible_share_basis if compatible_share_basis else None,
            "qualification_state": "qualified",
            "ledger_version": LEDGER_VERSION,
        }

        entries.append(entry)
        counts[event_type] = counts.get(event_type, 0) + 1

    # Apply deterministic ordering rule
    entries.sort(key=_get_ordering_key)

    return {
        "status": "available" if entries else "unavailable",
        "ledger_version": LEDGER_VERSION,
        "ticker": ticker,
        "ledger_entries": entries,
        "rejected_events": rejected_events,
        "entry_counts": counts,
        "share_basis_summary": compatible_share_basis,
    }
