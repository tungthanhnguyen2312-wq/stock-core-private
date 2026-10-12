"""Fail-closed evidence model for historical price basis and corporate-action timing.

This is an evidence ledger, not an OHLC transformer.  It records exactly what a retained
official document says, distinguishes an explicit ex-date from every other date, and keeps
price-stream verdicts scoped to the source/field/windows that earned them.  In particular, no
record date, payment date, or price gap is permitted to manufacture an ex-date or a factor.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Iterable, Mapping

VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"

PRICE_STREAMS = frozenset({
    "RAW_AS_TRADED", "RETROSPECTIVELY_ADJUSTED", "ADJUSTED_ANALYTICAL", "UNKNOWN",
})
EVENT_TYPES = frozenset({
    "cash_dividend", "stock_dividend", "bonus_shares", "rights_issue", "stock_split",
    "reverse_split", "capital_return", "amendment", "cancellation",
})


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def price_source_inventory() -> list[dict[str, Any]]:
    """Configured/governed historical price streams, with no label-based inference."""
    return [
        {
            "source_id": "DNSE_OHLC", "field_scope": "historical closed O/H/L/C",
            "exchange_scope": "provider-returned listed instruments", "range_scope": "bounded qualified windows only",
            "stream": "RETROSPECTIVELY_ADJUSTED", "verdict": "retrospectively_adjusted",
            "evidence": "market_data_source_authority.DNSE_OHLC_PRICE_BASIS",
            "authority": "not_raw_not_point_in_time", "tested_windows": "bounded only",
        },
        {
            "source_id": "VCI", "field_scope": "historical price fields",
            "exchange_scope": "three tested HOSE event windows", "range_scope": "2026 tested windows",
            "stream": "ADJUSTED_ANALYTICAL", "verdict": "adj_provider",
            "evidence": "provider_price_basis_registry active VCI verdict",
            "authority": "provider_scoped_adjusted_only", "tested_windows": "three 2026 windows",
        },
        {
            "source_id": "KBS", "field_scope": "historical price fields",
            "exchange_scope": "three tested HOSE event windows", "range_scope": "2026 tested windows",
            "stream": "ADJUSTED_ANALYTICAL", "verdict": "adj_provider",
            "evidence": "provider_price_basis_registry active KBS verdict",
            "authority": "provider_scoped_adjusted_only", "tested_windows": "three 2026 windows",
        },
        {
            "source_id": "HOSE_OFFICIAL_PILOT", "field_scope": "one published closing-price observation",
            "exchange_scope": "HOSE / HPG", "range_scope": "2024-12-31 only",
            "stream": "RAW_AS_TRADED", "verdict": "raw_candidate",
            "evidence": "market_basis_capability_registry.OFFICIAL_RAW_PRICE_OBSERVATIONS",
            "authority": "single_observation_not_historical_series", "tested_windows": "none",
        },
        {
            "source_id": "VSDC_CORPORATE_ACTION_NOTICE", "field_scope": "corporate-action notice",
            "exchange_scope": "source document only", "range_scope": "document date only",
            "stream": "UNKNOWN", "verdict": "unavailable",
            "evidence": "VSDC notice is entitlement evidence, not an OHLC source",
            "authority": "no_price_stream", "tested_windows": "none",
        },
    ]


def source_document(record: Mapping[str, Any]) -> dict[str, Any]:
    """The provenance shape required for every actually used official document."""
    required = ("document_id", "ticker", "canonical_url", "observed_at", "sha256", "content_type",
                "acquisition_status")
    missing = [key for key in required if not record.get(key)]
    if missing:
        raise ValueError("official_document_provenance_missing:" + ",".join(missing))
    return {
        "source_id": record.get("source_id"),
        "url": record["canonical_url"],
        "retrieved_at": record["observed_at"],
        "document_date": record.get("published_at"),
        "ticker": str(record["ticker"]).upper(),
        "document_id": record["document_id"],
        "event_id": None,
        "raw_payload_sha256": record["sha256"],
        "content_type": record["content_type"],
        "status": record["acquisition_status"],
    }


def event_from_observation(record: Mapping[str, Any], observation: Mapping[str, Any]) -> dict[str, Any]:
    """Convert an existing typed extraction into the PIT schema without enriching facts."""
    event_type = observation.get("event_type")
    if event_type not in EVENT_TYPES:
        raise ValueError("unsupported_or_missing_event_type")
    if str(observation.get("ticker", "")).upper() != str(record.get("ticker", "")).upper():
        raise ValueError("observation_ticker_conflicts_with_retained_document")
    ex_date = observation.get("ex_date")
    event = {
        "ticker": str(record["ticker"]).upper(),
        "event_type": event_type,
        "status": observation.get("lifecycle_state") or "unknown",
        "announcement_date": observation.get("announcement_date"),
        "record_date": observation.get("record_date"),
        "ex_date": ex_date,
        "ex_date_status": "EXPLICIT_OFFICIAL" if ex_date else "MISSING_EXPLICIT_EX_DATE",
        "payment_or_execution_date": observation.get("payment_or_execution_date"),
        "ratio": observation.get("stock_ratio"),
        "cash_amount_per_share": observation.get("cash_amount_per_share"),
        "rights_terms": {"rights_ratio": observation.get("rights_ratio"),
                         "subscription_price": observation.get("subscription_price")},
        "subscription_terms": None,
        "source_documents": [source_document(record)],
        "confidence": "OFFICIAL_DOCUMENT_OBSERVED",
        "lifecycle_state": observation.get("lifecycle_state") or "unknown",
        "amendment_links": {"supersedes": [], "superseded_by": [], "cancelled_by": []},
        "ex_date_absence_reason": observation.get("absent_fields", {}).get("ex_date"),
        "warnings": list(observation.get("warnings") or []),
    }
    event["event_id"] = _hash({
        "ticker": event["ticker"], "event_type": event_type,
        "document_ids": [item["document_id"] for item in event["source_documents"]],
        "facet_index": observation.get("facet_index"),
    })
    event["source_documents"][0]["event_id"] = event["event_id"]
    return event


def shadow_adjustment_ledger(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Record factor prerequisites only; it never changes an OHLC value."""
    rows = []
    for event in events:
        status, reason = "NOT_IMPLEMENTED", "missing_explicit_official_ex_date"
        if event.get("ex_date"):
            # A date alone is still insufficient: cash events require a raw prior close and a
            # correct contractual formula; share events require an explicit ratio/terms.
            reason = "raw_as_traded_event_window_and_event_specific_contract_not_qualified"
        rows.append({
            "event_id": event["event_id"], "ticker": event["ticker"],
            "event_type": event["event_type"], "ex_date": event.get("ex_date"),
            "method": "NOT_IMPLEMENTED", "status": status, "reason": reason,
            "mutates_ohlc": False,
        })
    return rows


def event_windows(events: Iterable[Mapping[str, Any]], snapshots: Iterable[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    """Classify only exact ticker/session snapshot evidence; never infer a price adjustment."""
    rows = []
    snapshot_rows = list(snapshots)
    for event in events:
        if not event.get("ex_date"):
            rows.append({"event_id": event["event_id"], "ticker": event["ticker"],
                         "classification": "INSUFFICIENT", "reason": "explicit_ex_date_missing",
                         "comparisons": []})
            continue
        matched = [row for row in snapshot_rows if row.get("ticker") == event["ticker"]
                   and row.get("trading_session_date") == event["ex_date"]]
        rows.append({"event_id": event["event_id"], "ticker": event["ticker"],
                     "classification": "INSUFFICIENT",
                     "reason": ("no_exact_ticker_session_pre_and_post_event_snapshot_pair" if not matched
                                else "snapshot_pair_does_not_establish_pre_event_and_post_event_evidence"),
                     "comparisons": matched})
    return rows


def build_artifact(events: Iterable[Mapping[str, Any]], *, snapshots: Iterable[Mapping[str, Any]] = (),
                   official_source_results: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    events = sorted((dict(event) for event in events), key=lambda row: row["event_id"])
    windows = event_windows(events, snapshots)
    counts = Counter(event["event_type"] for event in events)
    ex_qualified = sum(event["ex_date_status"] == "EXPLICIT_OFFICIAL" for event in events)
    streams = price_source_inventory()
    artifact = {
        "schema_version": SCHEMA_VERSION, "version": VERSION,
        "official_source_results": list(official_source_results),
        "corporate_action_schema": ["ticker", "event_type", "status", "announcement_date", "record_date", "ex_date", "payment_or_execution_date", "ratio", "cash_amount_per_share", "rights_terms", "subscription_terms", "source_documents", "confidence", "lifecycle_state", "amendment_links"],
        "price_basis_schema": ["source_id", "field_scope", "exchange_scope", "range_scope", "stream", "verdict", "evidence", "authority", "tested_windows"],
        "events": events, "price_sources_tested": streams, "event_windows": windows,
        "shadow_adjustment_ledger": shadow_adjustment_ledger(events),
        "coverage": {
            "universe_count": len({event["ticker"] for event in events}),
            "official_event_tickers": sorted({event["ticker"] for event in events}),
            "total_event_records": len(events), "ex_date_qualified_events": ex_qualified,
            "ex_date_missing_events": len(events) - ex_qualified,
            "amended_events": counts["amendment"], "cancelled_events": counts["cancellation"],
            "event_type_counts": dict(sorted(counts.items())),
            "raw_as_traded_qualified_windows": 0, "prospective_raw_only_windows": 0,
            "retrospective_adjustment_confirmed_windows": 0,
            "insufficient_windows": sum(row["classification"] == "INSUFFICIENT" for row in windows),
            "conflicting_windows": sum(row["classification"] == "CONFLICTING" for row in windows),
        },
        "historical_mutability_result": "NOT_TESTABLE_NO_PRE_EVENT_SNAPSHOT_PAIR",
        "adjustment_ledger_result": "SHADOW_ONLY_NOT_IMPLEMENTED_NO_OHLC_MUTATION",
        "raw_as_traded_authority_result": "NOT_PROMOTED",
        "corporate_action_authority_result": "OFFICIAL_EVENT_EVIDENCE_RETAINED_EX_DATE_UNQUALIFIED",
        "dependency_results": {
            "historical_valuation": "BLOCKED", "return_risk": "BLOCKED", "backtest": "BLOCKED",
        },
        "authority_boundary": "source_field_exchange_class_range_and_tested_window_scoped; no provider-wide claim",
        "still_blocked": ["official_explicit_ex_date_at_useful_scale", "pre_event_price_snapshot_pair", "historical_raw_as_traded_series"],
        "lane_terminal_status": "OUTCOME_D_GATE_3_CLOSED_NO_NEW_RAW_OR_EX_DATE_AUTHORITY",
        "next_real_data_gate": "retain_explicit_official_ex_date_notice_and_pre_event_raw_snapshot_for_the_same_ticker_event_window",
    }
    artifact["artifact_identity"] = "historical_pit_raw_as_traded_evidence:" + _hash(artifact)
    return artifact
