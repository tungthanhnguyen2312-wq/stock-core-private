"""Forward-only, source-scoped current VCI index-constituent snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any


INDEX_CONSTITUENTS_SNAPSHOT_SCHEMA_VERSION = 1
SOURCE_NAME = "VCI"
SOURCE_REFERENCE = "vnstock.api.listing.Listing(source='VCI').symbols_by_group(group=...)"

# Vnstock 4.0.4's VCI index mapping.  Requested aliases remain distinct scopes.
VCI_INDEX_GROUPS = {
    "VNINDEX": "VNINDEX", "VNI": "VNINDEX", "HNX": "HNXIndex", "HNXINDEX": "HNXIndex",
    "UPCOM": "HNXUpcomIndex", "UPCOMINDEX": "HNXUpcomIndex", "VN30": "VN30",
    "VNMID": "VNMIDCAP", "VNSML": "VNSMALLCAP", "VN100": "VN100", "VNALL": "VNALLSHARE",
    "VNSI": "VNSI", "VNIT": "VNIT", "VNIND": "VNIND", "VNCONS": "VNCONS",
    "VNCOND": "VNCOND", "VNHEAL": "VNHEAL", "VNENE": "VNENE", "VNUTI": "VNUTI",
    "VNREAL": "VNREAL", "VNFIN": "VNFIN", "VNMAT": "VNMAT", "VNDIAMOND": "VNDIAMOND",
    "VNFINLEAD": "VNFINLEAD", "VNFINSELECT": "VNFINSELECT", "VNX50": "VNX50",
    "VNXALL": "VNXALL", "HNX30": "HNX30", "HNXFIN": "HNX Financials Index",
    "HNXFINANCIALS": "HNX Financials Index", "HNXCON": "HNX Construction Index",
    "HNXCONSTRUCTION": "HNX Construction Index", "HNXLCAP": "HNX Large Cap Index",
    "HNXLARGECAP": "HNX Large Cap Index", "HNXMAN": "HNX Manufacturing Index",
    "HNXMANUFACTURING": "HNX Manufacturing Index", "HNXMSCAP": "HNX Mid/Small Cap Index",
    "HNXMIDSMALLCAP": "HNX Mid/Small Cap Index", "UPCOMLAR": "UPCOM Large Index",
    "UPCOMMID": "UPCOM Medium Index", "UPCOMSML": "UPCOM Small Index",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def resolve_group(group: str) -> dict[str, str]:
    """Validate a VCI index key while preserving caller-provided alias scope."""
    requested_group = str(group).strip().upper()
    if requested_group not in VCI_INDEX_GROUPS:
        raise ValueError(f"invalid VCI index group: {group}")
    return {
        "requested_group": requested_group,
        "effective_provider_group": VCI_INDEX_GROUPS[requested_group],
    }


def _members_from_payload(payload: Mapping[str, Any]) -> Sequence[Any]:
    if not isinstance(payload, Mapping) or "members" not in payload:
        raise ValueError("index constituents payload is missing members")
    members = payload["members"]
    if not isinstance(members, Sequence) or isinstance(members, (str, bytes)):
        raise ValueError("index constituent members must be a list")
    if not members:
        raise ValueError("empty index constituents payload is not a complete snapshot")
    return members


def normalize_current_payload(
    group: str, payload: Mapping[str, Any], fetched_at: str, *, effective_provider_group: str | None = None
) -> list[dict[str, Any]]:
    """Normalize only VCI-local member symbols; do not infer dates or weights."""
    scope = resolve_group(group)
    if effective_provider_group is not None and effective_provider_group != scope["effective_provider_group"]:
        raise ValueError("effective provider group does not match requested group")
    if not fetched_at:
        raise ValueError("fetched_at is required")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_member in _members_from_payload(payload):
        if not isinstance(raw_member, str):
            raise ValueError("VCI constituent member symbol must be a string")
        symbol = raw_member.strip().upper()
        if not symbol:
            raise ValueError("VCI constituent member symbol must not be blank")
        member_identity = f"vci:symbol:{symbol.casefold()}"
        if member_identity in seen:
            raise ValueError(f"duplicate VCI constituent member identity: {member_identity}")
        seen.add(member_identity)
        normalized.append({
            "symbol": symbol,
            "source_member_identity": member_identity,
            "raw_member": raw_member,
            "provenance": {
                "provider": SOURCE_NAME,
                "source_reference": SOURCE_REFERENCE,
                "requested_group": scope["requested_group"],
                "effective_provider_group": scope["effective_provider_group"],
                "identity_basis": "vci_group_member_symbol",
                "fetch_timestamp_semantics": "collection_provenance_not_effective_or_as_of_date",
                "unavailable_fields": ["effective_date", "history", "weight", "rank", "market_scope", "index_metadata"],
            },
        })
    return normalized


def build_snapshot_manifest(
    group: str, payload: Mapping[str, Any], fetched_at: str, *, effective_provider_group: str | None = None
) -> dict[str, Any]:
    """Build an idempotent source-scoped manifest from one complete response."""
    scope = resolve_group(group)
    if effective_provider_group is not None and effective_provider_group != scope["effective_provider_group"]:
        raise ValueError("effective provider group does not match requested group")
    _members_from_payload(payload)
    if not fetched_at:
        raise ValueError("fetched_at is required")
    raw_payload_json = _canonical_json(payload)
    raw_hash = hashlib.sha256(raw_payload_json.encode("utf-8")).hexdigest()
    identity = _canonical_json([
        INDEX_CONSTITUENTS_SNAPSHOT_SCHEMA_VERSION, SOURCE_NAME, scope["requested_group"],
        scope["effective_provider_group"], SOURCE_REFERENCE, raw_hash,
    ])
    return {
        "snapshot_id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "schema_version": INDEX_CONSTITUENTS_SNAPSHOT_SCHEMA_VERSION,
        "source_name": SOURCE_NAME,
        "requested_group": scope["requested_group"],
        "effective_provider_group": scope["effective_provider_group"],
        "source_reference": SOURCE_REFERENCE,
        "fetched_at": fetched_at,
        "raw_hash": raw_hash,
        "raw_payload_json": raw_payload_json,
        "status": "complete_response",
        "is_complete": 1,
        "provenance": {
            "provider": SOURCE_NAME,
            "source_reference": SOURCE_REFERENCE,
            "requested_group": scope["requested_group"],
            "effective_provider_group": scope["effective_provider_group"],
            "fetch_timestamp_semantics": "collection_provenance_not_effective_or_as_of_date",
            "response_semantics": "current_unpaginated_provider_response",
        },
    }


def init_db(conn: sqlite3.Connection) -> None:
    """Apply additive current-membership tables without backfilling history."""
    conn.execute("""CREATE TABLE IF NOT EXISTS index_constituent_snapshots(
        snapshot_id TEXT PRIMARY KEY,
        schema_version INTEGER NOT NULL,
        source_name TEXT NOT NULL CHECK(source_name = 'VCI'),
        requested_group TEXT NOT NULL,
        effective_provider_group TEXT NOT NULL,
        source_reference TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        raw_hash TEXT NOT NULL,
        raw_payload_json TEXT NOT NULL,
        provenance_json TEXT NOT NULL,
        record_count INTEGER NOT NULL,
        status TEXT NOT NULL,
        is_complete INTEGER NOT NULL CHECK(is_complete IN (0, 1)),
        UNIQUE(source_name, requested_group, effective_provider_group, source_reference, raw_hash))""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_index_constituent_snapshots_scope_time
        ON index_constituent_snapshots(source_name, requested_group, fetched_at DESC)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS index_constituent_records(
        record_id TEXT PRIMARY KEY,
        snapshot_id TEXT NOT NULL REFERENCES index_constituent_snapshots(snapshot_id),
        source_name TEXT NOT NULL CHECK(source_name = 'VCI'),
        requested_group TEXT NOT NULL,
        effective_provider_group TEXT NOT NULL,
        source_member_identity TEXT NOT NULL,
        symbol TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        raw_member_json TEXT NOT NULL,
        provenance_json TEXT NOT NULL,
        UNIQUE(snapshot_id, source_member_identity))""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_index_constituent_records_scope_member
        ON index_constituent_records(source_name, requested_group, source_member_identity)""")
    conn.commit()


def persist_current_snapshot(
    conn: sqlite3.Connection, group: str, payload: Mapping[str, Any], fetched_at: str,
    *, effective_provider_group: str | None = None,
) -> dict[str, Any]:
    """Persist a complete current response; identical scoped payloads are idempotent."""
    records = normalize_current_payload(group, payload, fetched_at, effective_provider_group=effective_provider_group)
    manifest = build_snapshot_manifest(group, payload, fetched_at, effective_provider_group=effective_provider_group)
    try:
        inserted = conn.execute(
            """INSERT INTO index_constituent_snapshots
            (snapshot_id,schema_version,source_name,requested_group,effective_provider_group,source_reference,
             fetched_at,raw_hash,raw_payload_json,provenance_json,record_count,status,is_complete)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(snapshot_id) DO NOTHING""",
            (manifest["snapshot_id"], manifest["schema_version"], manifest["source_name"],
             manifest["requested_group"], manifest["effective_provider_group"], manifest["source_reference"],
             manifest["fetched_at"], manifest["raw_hash"], manifest["raw_payload_json"],
             _canonical_json(manifest["provenance"]), len(records), manifest["status"], manifest["is_complete"]),
        ).rowcount == 1
        if inserted:
            for record in records:
                record_id = hashlib.sha256(_canonical_json([
                    manifest["snapshot_id"], record["source_member_identity"],
                ]).encode("utf-8")).hexdigest()
                conn.execute(
                    """INSERT INTO index_constituent_records
                    (record_id,snapshot_id,source_name,requested_group,effective_provider_group,source_member_identity,
                     symbol,fetched_at,raw_member_json,provenance_json)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (record_id, manifest["snapshot_id"], manifest["source_name"], manifest["requested_group"],
                     manifest["effective_provider_group"], record["source_member_identity"], record["symbol"],
                     manifest["fetched_at"], _canonical_json(record["raw_member"]),
                     _canonical_json(record["provenance"])),
                )
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    return {**manifest, "record_count": len(records), "inserted": inserted}


def payload_from_symbols_series(series: Any) -> dict[str, Any]:
    """Serialize a non-empty VCI `symbol` Series; reject malformed adapter output."""
    if series is None or not hasattr(series, "tolist") or getattr(series, "name", None) != "symbol":
        raise ValueError("VCI index constituent response is malformed")
    members = series.tolist()
    return {"members": members}


def fetch_current_payload(group: str) -> dict[str, Any]:
    """Fetch one VCI current membership list after fail-closed group validation."""
    scope = resolve_group(group)
    from vnstock.api.listing import Listing

    series = Listing(source=SOURCE_NAME, random_agent=False, show_log=False).symbols_by_group(
        group=scope["requested_group"]
    )
    return payload_from_symbols_series(series)


def sync_group(conn: sqlite3.Connection, group: str, *, fetched_at: str | None = None) -> dict[str, Any]:
    """Fetch and persist one source-scoped current VCI membership snapshot."""
    scope = resolve_group(group)
    fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
    return persist_current_snapshot(
        conn, scope["requested_group"], fetch_current_payload(scope["requested_group"]), fetched_at,
        effective_provider_group=scope["effective_provider_group"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Store forward-only VCI current index constituent snapshots.")
    parser.add_argument("--group", action="append", required=True, help="VCI index group; may be repeated.")
    parser.add_argument("--database", default="vn_stock.db")
    args = parser.parse_args()
    with sqlite3.connect(args.database) as conn:
        init_db(conn)
        for group in args.group:
            result = sync_group(conn, group)
            print(
                f"{result['requested_group']} effective={result['effective_provider_group']} "
                f"snapshot={result['snapshot_id']} records={result['record_count']} inserted={result['inserted']}"
            )


if __name__ == "__main__":
    main()
