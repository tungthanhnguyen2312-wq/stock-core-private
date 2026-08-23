"""Frozen, content-hashed snapshot of the retained VCI exchange-classification reference.

``dashboard-runtime/vn_stock.db``'s ``metadata.exchange`` column is populated by
``meta_sync.py:sync_exchange_industry()`` from ``vnstock.api.listing.Listing(source="VCI")
.symbols_by_exchange()`` -- a source already integrated and relied on elsewhere in this
codebase (``instrument_master_sync.py``, ``candle_scan.py``, ``live_universe.py``,
``stock_analyzer.py``, ``release_session_contract.py``), not a new provider. Its documented
domain is exactly four values (see ``meta_sync.py`` schema comment and
``stock_analyzer.EXCHANGE_DOMAIN``): ``HSX``, ``HNX``, ``UPCOM``, ``DELISTED``.

This module only freezes that already-retained column into an immutable, hashed,
provenance-bearing artifact -- no network call, no new provider, no inference. Whether the
``DELISTED`` value is fit to promote as ``canonical_universe_tiers.ACTIVE_UNIVERSE`` authority
is explicitly not decided here; see ``current_universe_status_and_session_coverage_resolution.py``,
which consumes this snapshot as one of several evidence inputs and stays owner-review-required.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "vci_exchange_reference_snapshot/v1"
SOURCE_REFERENCE = "dashboard-runtime/vn_stock.db:metadata.exchange (meta_sync.sync_exchange_industry <- vnstock.api.listing.Listing(source='VCI').symbols_by_exchange)"
KNOWN_EXCHANGE_VALUES = frozenset({"HSX", "HNX", "UPCOM", "DELISTED"})


class VciExchangeReferenceSnapshotError(ValueError):
    """A retained ``metadata`` row or the assembled snapshot violates this contract."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_snapshot(*, rows: Sequence[Mapping[str, Any]], retrieved_at: str,
                   source_reference: str = SOURCE_REFERENCE) -> dict[str, Any]:
    """One immutable snapshot of ``ticker -> exchange`` straight off the retained table.

    ``rows`` is already-loaded data (e.g. from a read-only ``SELECT ticker, exchange, updated
    FROM metadata``) -- this function never opens a database connection itself, matching this
    project's pure-core/thin-adapter convention.
    """
    if not _text(retrieved_at):
        raise VciExchangeReferenceSnapshotError("retrieved_at_required")
    records: dict[str, dict[str, Any]] = {}
    unrecognized_values: set[str] = set()
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise VciExchangeReferenceSnapshotError("metadata_row_not_a_mapping")
        ticker = _text(raw.get("ticker"))
        if ticker is None:
            raise VciExchangeReferenceSnapshotError("metadata_row_missing_ticker")
        ticker = ticker.upper()
        if ticker in records:
            raise VciExchangeReferenceSnapshotError(f"duplicate_ticker_in_metadata_snapshot:{ticker}")
        exchange = _text(raw.get("exchange"))
        if exchange is not None and exchange.upper() not in KNOWN_EXCHANGE_VALUES:
            unrecognized_values.add(exchange)
        records[ticker] = {
            "ticker": ticker,
            "exchange": exchange.upper() if exchange is not None else None,
            "recognized_exchange_value": exchange is None or exchange.upper() in KNOWN_EXCHANGE_VALUES,
            "updated": _text(raw.get("updated")),
        }

    by_exchange = Counter(record["exchange"] if record["exchange"] is not None else "MISSING" for record in records.values())
    snapshot = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "source_reference": source_reference,
        "retrieved_at": retrieved_at,
        "known_exchange_values": sorted(KNOWN_EXCHANGE_VALUES),
        "row_count": len(records),
        "by_exchange": dict(sorted(by_exchange.items())),
        "unrecognized_exchange_values": sorted(unrecognized_values),
        "records": records,
    }
    snapshot_sha256 = hashlib.sha256(_canonical_json(snapshot).encode()).hexdigest()
    snapshot["snapshot_sha256"] = snapshot_sha256
    snapshot["snapshot_identity"] = f"vci_exchange_reference_snapshot:{snapshot_sha256}"
    return snapshot


def verify_identity(snapshot: Mapping[str, Any]) -> None:
    payload = {key: value for key, value in snapshot.items() if key not in {"snapshot_sha256", "snapshot_identity"}}
    expected = hashlib.sha256(_canonical_json(payload).encode()).hexdigest()
    if snapshot.get("snapshot_sha256") != expected:
        raise VciExchangeReferenceSnapshotError("SNAPSHOT_IDENTITY_MISMATCH")
