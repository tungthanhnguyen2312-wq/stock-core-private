"""Forward-only, source-scoped instrument-master snapshots from VCI listings."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any


INSTRUMENT_MASTER_SNAPSHOT_SCHEMA_VERSION = 1
SOURCE_NAME = "VCI"
SOURCE_REFERENCE = "vnstock.api.listing.Listing(source='VCI').symbols_by_exchange()"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _records_from_payload(payload: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    if not isinstance(payload, Mapping) or "records" not in payload:
        raise ValueError("instrument master payload is missing records")
    records = payload["records"]
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise ValueError("instrument master records must be a list")
    if not records:
        raise ValueError("empty instrument master payload is not a complete snapshot")
    if any(not isinstance(record, Mapping) for record in records):
        raise ValueError("instrument master records contains a non-record value")
    return records


def normalize_current_payload(payload: Mapping[str, Any], fetched_at: str) -> list[dict[str, Any]]:
    """Keep VCI listing fields local; no status or issuer identity is inferred."""
    if not fetched_at:
        raise ValueError("fetched_at is required")
    normalized: list[dict[str, Any]] = []
    seen_identities: set[str] = set()
    for raw in _records_from_payload(payload):
        symbol = _text(raw.get("symbol"))
        exchange = _text(raw.get("exchange"))
        instrument_type = _text(raw.get("type"))
        if symbol is None or exchange is None or instrument_type is None:
            raise ValueError("VCI listing record requires symbol, exchange, and type")
        symbol = symbol.upper()
        exchange = exchange.upper()
        instrument_type = instrument_type.upper()
        provider_identity = f"vci:symbol:{symbol.casefold()}"
        if provider_identity in seen_identities:
            raise ValueError(f"duplicate VCI instrument identity: {provider_identity}")
        seen_identities.add(provider_identity)
        normalized.append({
            "symbol": symbol,
            "source_name": SOURCE_NAME,
            "source_reference": SOURCE_REFERENCE,
            "provider_identity": provider_identity,
            "identity_basis": "vci_listing_symbol",
            "exchange": exchange,
            "instrument_type": instrument_type,
            "fetched_at": fetched_at,
            "raw_record": dict(raw),
            "provenance": {
                "provider": SOURCE_NAME,
                "source_reference": SOURCE_REFERENCE,
                "identity_basis": "vci_listing_symbol",
                "field_contract": "vci_symbols_by_exchange_v1",
                "unavailable_fields": [
                    "company_or_organ_identity",
                    "listing_status",
                ],
                "non_equivalences": [
                    "VCI listing symbol is a provider-local instrument identity, not a cross-provider legal-entity key.",
                    "listing endpoint exchange is retained as provider text after trim/uppercase only.",
                ],
            },
        })
    return normalized


def build_snapshot_manifest(payload: Mapping[str, Any], fetched_at: str) -> dict[str, Any]:
    """Build an idempotent manifest for one complete VCI listing response."""
    _records_from_payload(payload)
    if not fetched_at:
        raise ValueError("fetched_at is required")
    raw_payload_json = _canonical_json(payload)
    raw_hash = hashlib.sha256(raw_payload_json.encode("utf-8")).hexdigest()
    identity = _canonical_json([
        INSTRUMENT_MASTER_SNAPSHOT_SCHEMA_VERSION, SOURCE_NAME, SOURCE_REFERENCE, raw_hash,
    ])
    return {
        "snapshot_id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "schema_version": INSTRUMENT_MASTER_SNAPSHOT_SCHEMA_VERSION,
        "source_name": SOURCE_NAME,
        "source_reference": SOURCE_REFERENCE,
        "fetched_at": fetched_at,
        "raw_hash": raw_hash,
        "raw_payload_json": raw_payload_json,
        "status": "complete_response",
        "is_complete": 1,
    }


def init_db(conn: sqlite3.Connection) -> None:
    """Apply additive instrument-master tables without touching existing tables."""
    conn.execute("""CREATE TABLE IF NOT EXISTS instrument_master_snapshots(
        snapshot_id TEXT PRIMARY KEY,
        schema_version INTEGER NOT NULL,
        source_name TEXT NOT NULL CHECK(source_name = 'VCI'),
        source_reference TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        raw_hash TEXT NOT NULL,
        raw_payload_json TEXT NOT NULL,
        record_count INTEGER NOT NULL,
        status TEXT NOT NULL,
        is_complete INTEGER NOT NULL CHECK(is_complete IN (0, 1)),
        UNIQUE(source_name, source_reference, raw_hash))""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_instrument_master_snapshots_scope_time
        ON instrument_master_snapshots(source_name, fetched_at DESC)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS instrument_master_records(
        record_id TEXT PRIMARY KEY,
        snapshot_id TEXT NOT NULL REFERENCES instrument_master_snapshots(snapshot_id),
        symbol TEXT NOT NULL,
        source_name TEXT NOT NULL CHECK(source_name = 'VCI'),
        source_reference TEXT NOT NULL,
        provider_identity TEXT NOT NULL,
        identity_basis TEXT NOT NULL,
        exchange TEXT NOT NULL,
        instrument_type TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        raw_record_json TEXT NOT NULL,
        provenance_json TEXT NOT NULL,
        UNIQUE(snapshot_id, provider_identity))""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_instrument_master_records_scope_identity
        ON instrument_master_records(source_name, provider_identity)""")
    conn.commit()


def persist_current_snapshot(conn: sqlite3.Connection, payload: Mapping[str, Any], fetched_at: str) -> dict[str, Any]:
    """Persist one complete listing response; identical payloads are idempotent."""
    manifest = build_snapshot_manifest(payload, fetched_at)
    records = normalize_current_payload(payload, fetched_at)
    try:
        inserted = conn.execute(
            """INSERT INTO instrument_master_snapshots
            (snapshot_id,schema_version,source_name,source_reference,fetched_at,raw_hash,
             raw_payload_json,record_count,status,is_complete)
            VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(snapshot_id) DO NOTHING""",
            (manifest["snapshot_id"], manifest["schema_version"], manifest["source_name"],
             manifest["source_reference"], manifest["fetched_at"], manifest["raw_hash"],
             manifest["raw_payload_json"], len(records), manifest["status"], manifest["is_complete"]),
        ).rowcount == 1
        if inserted:
            for record in records:
                record_id = hashlib.sha256(_canonical_json([
                    manifest["snapshot_id"], record["provider_identity"],
                ]).encode("utf-8")).hexdigest()
                conn.execute(
                    """INSERT INTO instrument_master_records
                    (record_id,snapshot_id,symbol,source_name,source_reference,provider_identity,identity_basis,
                     exchange,instrument_type,fetched_at,raw_record_json,provenance_json)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (record_id, manifest["snapshot_id"], record["symbol"], record["source_name"],
                     record["source_reference"], record["provider_identity"], record["identity_basis"],
                     record["exchange"], record["instrument_type"], record["fetched_at"],
                     _canonical_json(record["raw_record"]), _canonical_json(record["provenance"])),
                )
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    return {**manifest, "record_count": len(records), "inserted": inserted}


def payload_from_symbols_by_exchange_frame(frame: Any) -> dict[str, Any]:
    """Serialize a non-empty VCI listing DataFrame, preserving source column names."""
    if frame is None or not hasattr(frame, "columns"):
        raise ValueError("VCI listing response is malformed")
    required = {"symbol", "exchange", "type"}
    columns = {str(column) for column in frame.columns}
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"VCI listing response is missing required columns: {missing}")
    if len(frame) == 0:
        raise ValueError("VCI returned no listing rows")
    return {"records": json.loads(frame.to_json(orient="records", date_format="iso", force_ascii=False))}


def fetch_current_payload() -> dict[str, Any]:
    """Fetch the current VCI listing universe through Vnstock's public API."""
    from vnstock.api.listing import Listing

    frame = Listing(source=SOURCE_NAME, random_agent=False, show_log=False).symbols_by_exchange()
    return payload_from_symbols_by_exchange_frame(frame)


def sync_current(conn: sqlite3.Connection, *, fetched_at: str | None = None) -> dict[str, Any]:
    fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
    return persist_current_snapshot(conn, fetch_current_payload(), fetched_at)


def main() -> None:
    parser = argparse.ArgumentParser(description="Store forward-only VCI instrument-master snapshots.")
    parser.add_argument("--database", default="vn_stock.db")
    args = parser.parse_args()
    with sqlite3.connect(args.database) as conn:
        init_db(conn)
        result = sync_current(conn)
        print(f"VCI snapshot={result['snapshot_id']} records={result['record_count']} inserted={result['inserted']}")


if __name__ == "__main__":
    main()
