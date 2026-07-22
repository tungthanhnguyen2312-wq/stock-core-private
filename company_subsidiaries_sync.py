"""Forward-only current snapshots for source-scoped company relationships.

The providers do not expose historical relationship snapshots.  This module
therefore stores only responses fetched locally; it never backfills or infers
relationship changes from a missing record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any


COMPANY_SUBSIDIARY_SNAPSHOT_SCHEMA_VERSION = 1
SUPPORTED_SOURCES = frozenset({"VCI", "KBS"})
SOURCE_REFERENCES = {
    "VCI": "https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/{ticker}/relationship",
    "KBS": "https://kbbuddywts.kbsec.com.vn/iis-server/investment/stockinfo/profile/{ticker}?l=1",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _payload_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _source_name(source_name: str) -> str:
    source = source_name.upper()
    if source not in SUPPORTED_SOURCES:
        raise ValueError(f"unsupported company relationship source: {source_name}")
    return source


def _text(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _first(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record:
            return record[key]
    return None


def _record_identity(source: str, name: str | None, provider_id: str | None) -> tuple[str, str]:
    if source == "VCI" and provider_id:
        return f"vci:sub_organ_code:{provider_id}", "sub_organ_code"
    if name:
        # KBS has no organization ID in this endpoint.  This is deliberately a
        # provider-local fallback, never a cross-provider identity.
        return f"{source.lower()}:name:{name.casefold()}", "provider_name"
    raise ValueError(f"{source} relationship record has no provider identity or name")


def normalize_current_payload(
    ticker: str,
    source_name: str,
    payload: Mapping[str, Any],
    fetched_at: str,
    *,
    source_reference: str | None = None,
) -> list[dict[str, Any]]:
    """Preserve provider semantics while making source-scoped rows persistable.

    VCI payloads have separate ``subsidiaries`` and ``affiliates`` arrays.  KBS
    payloads have one ``records`` array whose ``type`` is retained verbatim.
    Ownership units intentionally remain provider-specific.
    """
    source = _source_name(source_name)
    symbol = ticker.upper().strip()
    if not symbol or not fetched_at:
        raise ValueError("ticker and fetched_at are required")
    reference = source_reference or SOURCE_REFERENCES[source]
    if not isinstance(payload, Mapping):
        raise ValueError("company relationship payload must be a mapping")
    rows: list[tuple[Mapping[str, Any], str | None]] = []
    if source == "VCI":
        for relation_key, relationship_type in (("subsidiaries", "subsidiary"), ("affiliates", "affiliate")):
            if relation_key not in payload:
                raise ValueError(f"VCI payload is missing {relation_key}")
            values = payload[relation_key]
            if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
                raise ValueError(f"VCI {relation_key} must be a list")
            if any(not isinstance(row, Mapping) for row in values):
                raise ValueError(f"VCI {relation_key} contains a non-record value")
            rows.extend((row, relationship_type) for row in values)
    else:
        if "records" not in payload:
            raise ValueError("KBS payload is missing records")
        values = payload["records"]
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise ValueError("KBS records must be a list")
        if any(not isinstance(row, Mapping) for row in values):
            raise ValueError("KBS records contains a non-record value")
        rows.extend((row, _text(row.get("type"))) for row in values)
    # An empty response cannot be distinguished from a provider error/partial
    # response by this endpoint contract.  Do not record it as complete.
    if not rows:
        raise ValueError("empty company relationship payload is not a complete snapshot")

    normalized: list[dict[str, Any]] = []
    seen_identities: set[str] = set()
    for raw, relationship_type in rows:
        if source == "VCI":
            name = _text(_first(raw, "organ_name", "right_organ_name_vi", "rightOrganNameVi"))
            provider_id = _text(_first(raw, "sub_organ_code", "right_organ_code", "rightOrganCode"))
            ownership_percent = _first(raw, "ownership_percent", "owned_percentage", "ownedPercentage")
            ownership_unit = "fraction"
            charter_capital = None
            currency = None
            provider_update_date = None
        else:
            name = _text(raw.get("name"))
            provider_id = None
            ownership_percent = raw.get("ownership_percent")
            ownership_unit = "percent"
            charter_capital = raw.get("charter_capital")
            currency = _text(raw.get("currency"))
            provider_update_date = _text(raw.get("update_date"))
        source_record_identity, identity_basis = _record_identity(source, name, provider_id)
        if source_record_identity in seen_identities:
            raise ValueError(f"duplicate {source} source record identity: {source_record_identity}")
        seen_identities.add(source_record_identity)
        provenance = {
            "provider": source,
            "source_reference": reference,
            "identity_basis": identity_basis,
            "raw_relationship_type": relationship_type,
            "ownership_unit": ownership_unit,
        }
        normalized.append({
            "ticker": symbol,
            "source_name": source,
            "source_reference": reference,
            "source_record_identity": source_record_identity,
            "provider_record_id": provider_id,
            "organization_name": name,
            "relationship_type": relationship_type,
            "ownership_percent": ownership_percent,
            "ownership_unit": ownership_unit,
            "charter_capital": charter_capital,
            "currency": currency,
            "provider_update_date": provider_update_date,
            "fetched_at": fetched_at,
            "raw_record": dict(raw),
            "provenance": provenance,
        })
    return normalized


def build_snapshot_manifest(
    ticker: str,
    source_name: str,
    payload: Mapping[str, Any],
    fetched_at: str,
    *,
    source_reference: str | None = None,
) -> dict[str, Any]:
    """Build an idempotent, forward-only manifest for one provider response."""
    source = _source_name(source_name)
    symbol = ticker.upper().strip()
    reference = source_reference or SOURCE_REFERENCES[source]
    raw_hash = _payload_hash(payload)
    identity = _canonical_json([COMPANY_SUBSIDIARY_SNAPSHOT_SCHEMA_VERSION, symbol, source, reference, raw_hash])
    return {
        "snapshot_id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "schema_version": COMPANY_SUBSIDIARY_SNAPSHOT_SCHEMA_VERSION,
        "ticker": symbol,
        "source_name": source,
        "source_reference": reference,
        "fetched_at": fetched_at,
        "raw_hash": raw_hash,
        "raw_payload_json": _canonical_json(payload),
        "status": "complete_response",
        "is_complete": 1,
    }


def init_db(conn: sqlite3.Connection) -> None:
    """Additive migration; never backfills relationship history."""
    conn.execute("""CREATE TABLE IF NOT EXISTS company_subsidiary_snapshots(
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
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_company_subsidiary_snapshots_scope_time
        ON company_subsidiary_snapshots(ticker, source_name, fetched_at DESC)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS company_subsidiary_records(
        record_id TEXT PRIMARY KEY,
        snapshot_id TEXT NOT NULL REFERENCES company_subsidiary_snapshots(snapshot_id),
        ticker TEXT NOT NULL,
        source_name TEXT NOT NULL,
        source_reference TEXT NOT NULL,
        source_record_identity TEXT NOT NULL,
        provider_record_id TEXT,
        organization_name TEXT,
        relationship_type TEXT,
        ownership_percent REAL,
        ownership_unit TEXT NOT NULL,
        charter_capital REAL,
        currency TEXT,
        provider_update_date TEXT,
        fetched_at TEXT NOT NULL,
        raw_record_json TEXT NOT NULL,
        provenance_json TEXT NOT NULL,
        UNIQUE(snapshot_id, source_record_identity))""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_company_subsidiary_records_scope_identity
        ON company_subsidiary_records(ticker, source_name, source_record_identity)""")
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
    """Persist one source response; an identical payload does not create a new snapshot."""
    manifest = build_snapshot_manifest(ticker, source_name, payload, fetched_at, source_reference=source_reference)
    records = normalize_current_payload(ticker, source_name, payload, fetched_at, source_reference=manifest["source_reference"])
    try:
        cursor = conn.execute(
            """INSERT INTO company_subsidiary_snapshots
            (snapshot_id,schema_version,ticker,source_name,source_reference,fetched_at,raw_hash,
             raw_payload_json,record_count,status,is_complete)
            VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(snapshot_id) DO NOTHING""",
            (manifest["snapshot_id"], manifest["schema_version"], manifest["ticker"], manifest["source_name"],
             manifest["source_reference"], manifest["fetched_at"], manifest["raw_hash"], manifest["raw_payload_json"],
             len(records), manifest["status"], manifest["is_complete"]),
        )
        inserted = cursor.rowcount == 1
        if inserted:
            for record in records:
                record_identity = _canonical_json([manifest["snapshot_id"], record["source_record_identity"]])
                record_id = hashlib.sha256(record_identity.encode("utf-8")).hexdigest()
                conn.execute(
                    """INSERT INTO company_subsidiary_records
                    (record_id,snapshot_id,ticker,source_name,source_reference,source_record_identity,
                     provider_record_id,organization_name,relationship_type,ownership_percent,ownership_unit,
                     charter_capital,currency,provider_update_date,fetched_at,raw_record_json,provenance_json)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (record_id, manifest["snapshot_id"], record["ticker"], record["source_name"],
                     record["source_reference"], record["source_record_identity"], record["provider_record_id"],
                     record["organization_name"], record["relationship_type"], record["ownership_percent"],
                     record["ownership_unit"], record["charter_capital"], record["currency"],
                     record["provider_update_date"], record["fetched_at"], _canonical_json(record["raw_record"]),
                     _canonical_json(record["provenance"])),
                )
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    return {**manifest, "record_count": len(records), "inserted": inserted}


def fetch_current_payload(ticker: str, source_name: str) -> dict[str, Any]:
    """Fetch only the current provider response through Vnstock's public API."""
    source = _source_name(source_name)
    from vnstock.api.company import Company

    company = Company(source=source, symbol=ticker, random_agent=False, show_log=False)
    if source == "VCI":
        return {
            "subsidiaries": company.subsidiaries(filter_by="subsidiary").to_dict(orient="records"),
            "affiliates": company.subsidiaries(filter_by="affiliate").to_dict(orient="records"),
        }
    return {"records": company.subsidiaries().to_dict(orient="records")}


def sync_ticker(conn: sqlite3.Connection, ticker: str, source_name: str, *, fetched_at: str | None = None) -> dict[str, Any]:
    fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
    return persist_current_snapshot(conn, ticker, source_name, fetch_current_payload(ticker, source_name), fetched_at)


def main() -> None:
    parser = argparse.ArgumentParser(description="Store forward-only company subsidiary snapshots.")
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
