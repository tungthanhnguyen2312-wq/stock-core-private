"""Forward-only, source-scoped current company-profile snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any


COMPANY_PROFILE_SNAPSHOT_SCHEMA_VERSION = 1
SUPPORTED_SOURCES = frozenset({"VCI", "KBS"})
SOURCE_REFERENCES = {
    "VCI": "https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/details?ticker={ticker}",
    "KBS": "https://kbbuddywts.kbsec.com.vn/iis-server/investment/stockinfo/profile/{ticker}?l=1",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _source_name(source_name: str) -> str:
    source = source_name.upper()
    if source not in SUPPORTED_SOURCES:
        raise ValueError(f"unsupported company profile source: {source_name}")
    return source


def _text(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _required_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping) or "record" not in payload:
        raise ValueError("company profile payload is missing record")
    record = payload["record"]
    if not isinstance(record, Mapping) or not record:
        raise ValueError("empty company profile payload is not a complete snapshot")
    return record


def normalize_current_payload(
    ticker: str,
    source_name: str,
    payload: Mapping[str, Any],
    fetched_at: str,
    *,
    source_reference: str | None = None,
) -> dict[str, Any]:
    """Return a provider-local profile record without cross-source mappings."""
    source = _source_name(source_name)
    symbol = ticker.upper().strip()
    if not symbol or not fetched_at:
        raise ValueError("ticker and fetched_at are required")
    raw_record = _required_payload(payload)
    reference = source_reference or SOURCE_REFERENCES[source]
    if source == "VCI":
        provider_identity = _text(raw_record.get("organ_code")) or symbol
        identity_basis = "organ_code" if _text(raw_record.get("organ_code")) else "symbol_fallback"
        qualified_fields = {
            "symbol": _text(raw_record.get("symbol")),
            "organ_code": _text(raw_record.get("organ_code")),
            "organ_name": _text(raw_record.get("organ_name")),
            "organ_short_name": _text(raw_record.get("organ_short_name")),
            "sector": _text(raw_record.get("sector")),
            "company_profile": _text(raw_record.get("company_profile")),
            "listing_date": raw_record.get("listing_date"),
            "issue_share": raw_record.get("issue_share"),
        }
    else:
        provider_identity = _text(raw_record.get("tax_id")) or symbol
        identity_basis = "tax_id" if _text(raw_record.get("tax_id")) else "symbol_fallback"
        qualified_fields = {
            "symbol": _text(raw_record.get("symbol")),
            "business_model": _text(raw_record.get("business_model")),
            "charter_capital": raw_record.get("charter_capital"),
            "listing_date": raw_record.get("listing_date"),
            "exchange": _text(raw_record.get("exchange")),
            "outstanding_shares": raw_record.get("outstanding_shares"),
            "website": _text(raw_record.get("website")),
            "address": _text(raw_record.get("address")),
            "tax_id": _text(raw_record.get("tax_id")),
            "as_of_date": raw_record.get("as_of_date"),
        }
    provenance = {
        "provider": source,
        "source_reference": reference,
        "identity_basis": identity_basis,
        "field_contract": "source_specific_company_profile_v1",
        "non_equivalences": [
            "VCI.issue_share is not merged with KBS.outstanding_shares",
            "VCI.sector is not merged with KBS.business_model",
            "KBS.charter_capital and KBS.address retain provider semantics",
        ],
    }
    return {
        "ticker": symbol,
        "source_name": source,
        "source_reference": reference,
        "provider_identity": provider_identity,
        "identity_basis": identity_basis,
        "fetched_at": fetched_at,
        "qualified_fields": qualified_fields,
        "raw_record": dict(raw_record),
        "provenance": provenance,
    }


def build_snapshot_manifest(
    ticker: str,
    source_name: str,
    payload: Mapping[str, Any],
    fetched_at: str,
    *,
    source_reference: str | None = None,
) -> dict[str, Any]:
    """Build a local snapshot identity from one raw provider response."""
    _required_payload(payload)
    source = _source_name(source_name)
    symbol = ticker.upper().strip()
    reference = source_reference or SOURCE_REFERENCES[source]
    raw_payload_json = _canonical_json(payload)
    raw_hash = hashlib.sha256(raw_payload_json.encode("utf-8")).hexdigest()
    identity = _canonical_json([COMPANY_PROFILE_SNAPSHOT_SCHEMA_VERSION, symbol, source, reference, raw_hash])
    return {
        "snapshot_id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "schema_version": COMPANY_PROFILE_SNAPSHOT_SCHEMA_VERSION,
        "ticker": symbol,
        "source_name": source,
        "source_reference": reference,
        "fetched_at": fetched_at,
        "raw_hash": raw_hash,
        "raw_payload_json": raw_payload_json,
        "record_count": 1,
        "status": "complete_response",
        "is_complete": 1,
    }


def init_db(conn: sqlite3.Connection) -> None:
    """Apply the additive profile-snapshot schema; never backfill history."""
    conn.execute("""CREATE TABLE IF NOT EXISTS company_profile_snapshots(
        snapshot_id TEXT PRIMARY KEY,
        schema_version INTEGER NOT NULL,
        ticker TEXT NOT NULL,
        source_name TEXT NOT NULL,
        source_reference TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        raw_hash TEXT NOT NULL,
        raw_payload_json TEXT NOT NULL,
        record_count INTEGER NOT NULL,
        status TEXT NOT NULL,
        is_complete INTEGER NOT NULL CHECK(is_complete IN (0, 1)),
        UNIQUE(ticker, source_name, source_reference, raw_hash))""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_company_profile_snapshots_scope_time
        ON company_profile_snapshots(ticker, source_name, fetched_at DESC)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS company_profile_records(
        record_id TEXT PRIMARY KEY,
        snapshot_id TEXT NOT NULL REFERENCES company_profile_snapshots(snapshot_id),
        ticker TEXT NOT NULL,
        source_name TEXT NOT NULL,
        source_reference TEXT NOT NULL,
        provider_identity TEXT NOT NULL,
        identity_basis TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        qualified_fields_json TEXT NOT NULL,
        raw_record_json TEXT NOT NULL,
        provenance_json TEXT NOT NULL,
        UNIQUE(snapshot_id, provider_identity))""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_company_profile_records_scope_identity
        ON company_profile_records(ticker, source_name, provider_identity)""")
    conn.commit()


def persist_current_snapshot(
    conn: sqlite3.Connection,
    ticker: str,
    source_name: str,
    payload: Mapping[str, Any],
    fetched_at: str,
    *,
    source_reference: str | None = None,
) -> dict[str, Any]:
    """Persist one profile response; same payload is idempotent by raw hash."""
    manifest = build_snapshot_manifest(ticker, source_name, payload, fetched_at, source_reference=source_reference)
    record = normalize_current_payload(ticker, source_name, payload, fetched_at, source_reference=manifest["source_reference"])
    try:
        inserted = conn.execute(
            """INSERT INTO company_profile_snapshots
            (snapshot_id,schema_version,ticker,source_name,source_reference,fetched_at,raw_hash,
             raw_payload_json,record_count,status,is_complete)
            VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(snapshot_id) DO NOTHING""",
            (manifest["snapshot_id"], manifest["schema_version"], manifest["ticker"], manifest["source_name"],
             manifest["source_reference"], manifest["fetched_at"], manifest["raw_hash"], manifest["raw_payload_json"],
             manifest["record_count"], manifest["status"], manifest["is_complete"]),
        ).rowcount == 1
        if inserted:
            record_id = hashlib.sha256(_canonical_json([manifest["snapshot_id"], record["provider_identity"]]).encode("utf-8")).hexdigest()
            conn.execute(
                """INSERT INTO company_profile_records
                (record_id,snapshot_id,ticker,source_name,source_reference,provider_identity,identity_basis,
                 fetched_at,qualified_fields_json,raw_record_json,provenance_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (record_id, manifest["snapshot_id"], record["ticker"], record["source_name"],
                 record["source_reference"], record["provider_identity"], record["identity_basis"],
                 record["fetched_at"], _canonical_json(record["qualified_fields"]),
                 _canonical_json(record["raw_record"]), _canonical_json(record["provenance"])),
            )
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    return {**manifest, "inserted": inserted}


def fetch_current_payload(ticker: str, source_name: str) -> dict[str, Any]:
    """Fetch exactly one current Vnstock overview row through its public API."""
    source = _source_name(source_name)
    from vnstock.api.company import Company

    frame = Company(source=source, symbol=ticker, random_agent=False, show_log=False).overview()
    return payload_from_overview_frame(frame, source, ticker)


def payload_from_overview_frame(frame: Any, source_name: str, ticker: str) -> dict[str, Any]:
    """Serialize exactly one provider profile row; reject duplicates deterministically."""
    source = _source_name(source_name)
    if len(frame) != 1:
        raise ValueError(f"{source} returned {len(frame)} company profile rows for {ticker}")
    records = json.loads(frame.to_json(orient="records", date_format="iso", force_ascii=False))
    return {"record": records[0]}


def sync_ticker(conn: sqlite3.Connection, ticker: str, source_name: str, *, fetched_at: str | None = None) -> dict[str, Any]:
    fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
    return persist_current_snapshot(conn, ticker, source_name, fetch_current_payload(ticker, source_name), fetched_at)


def main() -> None:
    parser = argparse.ArgumentParser(description="Store forward-only company profile snapshots.")
    parser.add_argument("--ticker", action="append", required=True, help="Ticker to fetch; may be repeated.")
    parser.add_argument("--source", choices=sorted(SUPPORTED_SOURCES), required=True)
    parser.add_argument("--database", default="vn_stock.db")
    args = parser.parse_args()
    with sqlite3.connect(args.database) as conn:
        init_db(conn)
        for ticker in args.ticker:
            result = sync_ticker(conn, ticker, args.source)
            print(f"{result['ticker']} {result['source_name']} snapshot={result['snapshot_id']} inserted={result['inserted']}")


if __name__ == "__main__":
    main()
