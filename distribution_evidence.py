"""Generic, source-qualified distribution_evidence contract (Phase 5D).

Transforms corporate_action_ledger.build_corporate_action_ledger()'s already-qualified,
already-hash-verified events into a ticker-agnostic cash/non-cash distribution contract.
No ticker-specific branches: every ticker is processed through the same generic path,
using only citations already present under data/official-evidence/. Never fetches
evidence, never derives yield/payout ratio/CAGR/total return/adjusted returns, and
always reports is_actionable=False.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import semantic_evidence_bridge as bridge
from corporate_action_ledger import build_corporate_action_ledger

DISTRIBUTION_EVIDENCE_SCHEMA_VERSION = "1.0.0"

_CASH_EVENT_TYPE = "cash_dividend"
_NON_CASH_EVENT_TYPES = frozenset({"stock_dividend", "bonus_share"})
_NON_CASH_DISTRIBUTION_TYPES = {"stock_dividend": "stock_dividend", "bonus_share": "bonus_share"}

_STANDING_LIMITATIONS: tuple[str, ...] = (
    "No dividend yield, payout ratio, CAGR, total return, or adjusted return is derived by "
    "this contract.",
    "is_actionable is always false; this contract carries source-qualified evidence only, "
    "never an investment signal.",
)


def _period_of(entry: Mapping[str, Any]) -> str | None:
    """Calendar-year period key for one ledger entry, first available of record/declaration/
    effective/payment date. Used only to count distinct annual periods -- never to derive a
    fiscal-year attribution, yield, or return."""
    for field in ("record_date", "declaration_date", "effective_date", "payment_date"):
        value = entry.get(field)
        if isinstance(value, str) and len(value) >= 4 and value[:4].isdigit():
            return value[:4]
    return None


def _rejection_ticker(rejection: Mapping[str, Any]) -> str | None:
    key = rejection.get("key")
    if isinstance(key, (tuple, list)) and key:
        return key[0]
    citation = rejection.get("citation")
    if isinstance(citation, Mapping):
        return citation.get("ticker")
    return None


def _cash_distribution_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "event_id": entry.get("canonical_event_id"),
        "distribution_type": "cash_distribution",
        "ticker": entry.get("ticker"),
        "issuer": entry.get("issuer"),
        "declaration_date": entry.get("declaration_date"),
        "record_date": entry.get("record_date"),
        "ex_date": entry.get("ex_date"),
        "payment_date": entry.get("payment_date"),
        "effective_date": entry.get("effective_date"),
        "amount": entry.get("cash_amount"),
        "currency": entry.get("currency"),
        "unit": "per_share",
        "per_share_basis": entry.get("share_class"),
        "event_status": entry.get("event_status"),
        "source_authority": entry.get("source_authority"),
        "evidence": entry.get("evidence"),
        "qualification_state": entry.get("qualification_state"),
        "ledger_entry_id": entry.get("ledger_entry_id"),
    }


def _non_cash_distribution_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "event_id": entry.get("canonical_event_id"),
        "distribution_type": _NON_CASH_DISTRIBUTION_TYPES.get(entry.get("event_type"), "unknown"),
        "ticker": entry.get("ticker"),
        "issuer": entry.get("issuer"),
        "declaration_date": entry.get("declaration_date"),
        "record_date": entry.get("record_date"),
        "ex_date": entry.get("ex_date"),
        "distribution_date": entry.get("payment_date"),
        "effective_date": entry.get("effective_date"),
        "entitlement_ratio": entry.get("entitlement_ratio"),
        "funding_source": entry.get("funding_source"),
        "share_class": entry.get("share_class"),
        "event_status": entry.get("event_status"),
        "source_authority": entry.get("source_authority"),
        "evidence": entry.get("evidence"),
        "qualification_state": entry.get("qualification_state"),
        "ledger_entry_id": entry.get("ledger_entry_id"),
    }


def build_distribution_evidence_for_ticker(runtime_root: Path, ticker: str) -> dict[str, Any]:
    """Build the distribution_evidence contract for one ticker from already-retained,
    already-qualified corporate-action evidence only. Generic across tickers: identical
    code path regardless of which ticker is passed, no per-ticker branching.

    coverage_status is one of "missing" (no retained ledger data for this ticker),
    "partial" (only non-cash events qualified), "conflict" (a ticker-scoped citation
    was rejected -- hash mismatch, conflicting citations, malformed citation, unsupported
    event type/currency, or invalid ratio), or "available" (>=1 qualified cash_distribution).
    history_status reflects whether qualified cash events span >=2 distinct annual periods
    ("multi_period_available"); a single qualified period is not sufficient to claim
    recurring income. is_actionable is always False.
    """
    ledger_result = build_corporate_action_ledger(runtime_root, ticker=ticker)
    cash_result = bridge.load_verified_cash_dividends(runtime_root)
    non_cash_result = bridge.load_verified_non_cash_events(runtime_root)

    ticker_rejections: list[Mapping[str, Any]] = [
        rejection
        for rejection in (*cash_result.get("rejected", []), *non_cash_result.get("rejected", []))
        if _rejection_ticker(rejection) == ticker
    ]
    # Ledger-level rejections are already ticker-scoped (raw_events is pre-filtered by ticker).
    ticker_rejections.extend(ledger_result.get("rejected_events", []))

    entries = ledger_result.get("ledger_entries", [])
    cash_entries = [e for e in entries if e.get("event_type") == _CASH_EVENT_TYPE]
    non_cash_entries = [e for e in entries if e.get("event_type") in _NON_CASH_EVENT_TYPES]
    other_entries = [
        e for e in entries
        if e.get("event_type") != _CASH_EVENT_TYPE and e.get("event_type") not in _NON_CASH_EVENT_TYPES
    ]

    cash_distributions = [_cash_distribution_entry(e) for e in cash_entries]
    non_cash_distributions = [_non_cash_distribution_entry(e) for e in (*non_cash_entries, *other_entries)]

    covered_periods = sorted({period for period in (_period_of(e) for e in cash_entries) if period is not None})

    if ticker_rejections:
        coverage_status = "conflict"
        blocking_reasons = sorted({str(r.get("reason", "unknown_rejection_reason")) for r in ticker_rejections})
    elif not entries:
        coverage_status = "missing"
        blocking_reasons = []
    elif not cash_distributions:
        coverage_status = "partial"
        blocking_reasons = []
    else:
        coverage_status = "available"
        blocking_reasons = []

    if not cash_distributions:
        history_status = "no_qualified_events"
    elif len(covered_periods) < 2:
        history_status = "single_period_only"
    else:
        history_status = "multi_period_available"

    limitations = list(_STANDING_LIMITATIONS)
    if history_status != "multi_period_available":
        limitations.append(
            "Retained cash-distribution history covers fewer than two distinct qualified "
            "annual periods; recurring income is not claimed by this contract.",
        )
    if non_cash_distributions:
        limitations.append(
            "Stock dividends and bonus shares are share-count events, not cash income; they "
            "are kept in non_cash_distributions and must not be treated as yield.",
        )

    return {
        "schema_version": DISTRIBUTION_EVIDENCE_SCHEMA_VERSION,
        "ticker": ticker,
        "coverage_status": coverage_status,
        "cash_distributions": cash_distributions,
        "non_cash_distributions": non_cash_distributions,
        "latest_cash_distribution": cash_distributions[-1] if cash_distributions else None,
        "qualified_cash_event_count": len(cash_distributions),
        "covered_periods": covered_periods,
        "history_status": history_status,
        "blocking_reasons": blocking_reasons,
        "limitations": limitations,
        "provenance": {
            "source": "corporate_action_ledger.build_corporate_action_ledger",
            "ledger_version": ledger_result.get("ledger_version"),
            "ledger_status": ledger_result.get("status"),
            "cash_dividend_citations_path": bridge.CASH_DIVIDEND_RELATIVE.as_posix(),
            "non_cash_event_citations_path": bridge.NON_CASH_EVENT_RELATIVE.as_posix(),
            "cash_source_status": cash_result.get("status"),
            "non_cash_source_status": non_cash_result.get("status"),
        },
        "is_actionable": False,
    }
