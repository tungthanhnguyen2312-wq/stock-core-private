"""Forward-only KBS current ownership-structure snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any


OWNERSHIP_STRUCTURE_SNAPSHOT_SCHEMA_VERSION = 1
SOURCE_NAME = "KBS"
SOURCE_REFERENCE = "https://kbbuddywts.kbsec.com.vn/iis-server/investment/stockinfo/profile/{ticker}?l=1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _records_from_payload(payload: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    if not isinstance(payload, Mapping) or "records" not in payload:
        raise ValueError("ownership payload is missing records")
    records = payload["records"]
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise ValueError("ownership records must be a list")
    if not records:
        raise ValueError("empty ownership payload is not a complete snapshot")
    if any(not isinstance(record, Mapping) for record in records):
        raise ValueError("ownership records contains a non-record value")
    return records


def normalize_current_payload(ticker: str, payload: Mapping[str, Any], fetched_at: str) -> list[dict[str, Any]]:
    """Retain KBS group labels and raw percentage points without taxonomy mapping."""
    symbol = ticker.upper().strip()
    if not symbol or not fetched_at:
        raise ValueError("ticker and fetched_at are required")
    normalized: list[dict[str, Any]] = []
    seen_identities: set[str] = set()
    for raw in _records_from_payload(payload):
        owner_type = _text(raw.get("owner_type"))
        if owner_type is None:
            raise ValueError("KBS ownership record is missing owner_type")
        source_record_identity = f"kbs:owner_type:{owner_type.casefold()}"
        if source_record_identity in seen_identities:
            raise ValueError(f"duplicate KBS ownership identity: {source_record_identity}")
        seen_identities.add(source_record_identity)
        provenance = {
            "provider": SOURCE_NAME,
            "source_reference": SOURCE_REFERENCE,
            "identity_basis": "owner_type_provider_local",
            "ownership_unit": "percentage_points",
            "update_date_semantics": "current_response_provenance_not_historical_api",
        }
        normalized.append({
            "ticker": symbol,
            "source_name": SOURCE_NAME,
            "source_reference": SOURCE_REFERENCE,
            "source_record_identity": source_record_identity,
            "owner_type": owner_type,
            "ownership_percentage": raw.get("ownership_percentage"),
            "shares_owned": raw.get("shares_owned"),
            "update_date": raw.get("update_date"),
            "fetched_at": fetched_at,
            "raw_record": dict(raw),
            "provenance": provenance,
        })
    return normalized


def build_snapshot_manifest(ticker: str, payload: Mapping[str, Any], fetched_at: str) -> dict[str, Any]:
    """Build an idempotent manifest for one current KBS ownership response."""
    _records_from_payload(payload)
    symbol = ticker.upper().strip()
    if not symbol or not fetched_at:
        raise ValueError("ticker and fetched_at are required")
    raw_payload_json = _canonical_json(payload)
    raw_hash = hashlib.sha256(raw_payload_json.encode("utf-8")).hexdigest()
    identity = _canonical_json([OWNERSHIP_STRUCTURE_SNAPSHOT_SCHEMA_VERSION, symbol, SOURCE_NAME, SOURCE_REFERENCE, raw_hash])
    return {
        "snapshot_id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "schema_version": OWNERSHIP_STRUCTURE_SNAPSHOT_SCHEMA_VERSION,
        "ticker": symbol,
        "source_name": SOURCE_NAME,
        "source_reference": SOURCE_REFERENCE,
        "fetched_at": fetched_at,
        "raw_hash": raw_hash,
        "raw_payload_json": raw_payload_json,
        "status": "complete_response",
        "is_complete": 1,
    }


def init_db(conn: sqlite3.Connection) -> None:
    """Apply additive KBS ownership tables without provider-history backfill."""
    conn.execute("""CREATE TABLE IF NOT EXISTS ownership_structure_snapshots(
        snapshot_id TEXT PRIMARY KEY,
        schema_version INTEGER NOT NULL,
        ticker TEXT NOT NULL,
        source_name TEXT NOT NULL CHECK(source_name = 'KBS'),
        source_reference TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        raw_hash TEXT NOT NULL,
        raw_payload_json TEXT NOT NULL,
        record_count INTEGER NOT NULL,
        status TEXT NOT NULL,
        is_complete INTEGER NOT NULL CHECK(is_complete IN (0, 1)),
        UNIQUE(ticker, source_name, source_reference, raw_hash))""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_ownership_structure_snapshots_scope_time
        ON ownership_structure_snapshots(ticker, fetched_at DESC)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS ownership_structure_records(
        record_id TEXT PRIMARY KEY,
        snapshot_id TEXT NOT NULL REFERENCES ownership_structure_snapshots(snapshot_id),
        ticker TEXT NOT NULL,
        source_name TEXT NOT NULL CHECK(source_name = 'KBS'),
        source_reference TEXT NOT NULL,
        source_record_identity TEXT NOT NULL,
        owner_type TEXT NOT NULL,
        ownership_percentage REAL,
        shares_owned REAL,
        update_date TEXT,
        fetched_at TEXT NOT NULL,
        raw_record_json TEXT NOT NULL,
        provenance_json TEXT NOT NULL,
        UNIQUE(snapshot_id, source_record_identity))""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_ownership_structure_records_scope_identity
        ON ownership_structure_records(ticker, source_record_identity)""")
    conn.commit()


def persist_current_snapshot(conn: sqlite3.Connection, ticker: str, payload: Mapping[str, Any], fetched_at: str) -> dict[str, Any]:
    """Persist one complete current KBS response; identical payloads are idempotent."""
    manifest = build_snapshot_manifest(ticker, payload, fetched_at)
    records = normalize_current_payload(ticker, payload, fetched_at)
    try:
        inserted = conn.execute(
            """INSERT INTO ownership_structure_snapshots
            (snapshot_id,schema_version,ticker,source_name,source_reference,fetched_at,raw_hash,
             raw_payload_json,record_count,status,is_complete)
            VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(snapshot_id) DO NOTHING""",
            (manifest["snapshot_id"], manifest["schema_version"], manifest["ticker"], manifest["source_name"],
             manifest["source_reference"], manifest["fetched_at"], manifest["raw_hash"], manifest["raw_payload_json"],
             len(records), manifest["status"], manifest["is_complete"]),
        ).rowcount == 1
        if inserted:
            for record in records:
                record_id = hashlib.sha256(_canonical_json([manifest["snapshot_id"], record["source_record_identity"]]).encode("utf-8")).hexdigest()
                conn.execute(
                    """INSERT INTO ownership_structure_records
                    (record_id,snapshot_id,ticker,source_name,source_reference,source_record_identity,owner_type,
                     ownership_percentage,shares_owned,update_date,fetched_at,raw_record_json,provenance_json)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (record_id, manifest["snapshot_id"], record["ticker"], record["source_name"],
                     record["source_reference"], record["source_record_identity"], record["owner_type"],
                     record["ownership_percentage"], record["shares_owned"], record["update_date"],
                     record["fetched_at"], _canonical_json(record["raw_record"]), _canonical_json(record["provenance"])),
                )
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    return {**manifest, "record_count": len(records), "inserted": inserted}


def payload_from_ownership_frame(frame: Any, ticker: str) -> dict[str, Any]:
    """Serialize a non-empty KBS ownership DataFrame without group remapping."""
    if len(frame) == 0:
        raise ValueError(f"KBS returned no ownership rows for {ticker}")
    return {"records": json.loads(frame.to_json(orient="records", date_format="iso", force_ascii=False))}


def fetch_current_payload(ticker: str) -> dict[str, Any]:
    """Fetch the current KBS ownership response through Vnstock's public API."""
    from vnstock.api.company import Company

    frame = Company(source=SOURCE_NAME, symbol=ticker, random_agent=False, show_log=False).ownership()
    return payload_from_ownership_frame(frame, ticker)


def sync_ticker(conn: sqlite3.Connection, ticker: str, *, fetched_at: str | None = None) -> dict[str, Any]:
    fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
    return persist_current_snapshot(conn, ticker, fetch_current_payload(ticker), fetched_at)


def main() -> None:
    parser = argparse.ArgumentParser(description="Store forward-only current KBS ownership snapshots.")
    parser.add_argument("--ticker", action="append", required=True, help="Ticker to fetch; may be repeated.")
    parser.add_argument("--database", default="vn_stock.db")
    args = parser.parse_args()
    with sqlite3.connect(args.database) as conn:
        init_db(conn)
        for ticker in args.ticker:
            result = sync_ticker(conn, ticker)
            print(f"{result['ticker']} KBS snapshot={result['snapshot_id']} inserted={result['inserted']}")


if __name__ == "__main__":
    main()
