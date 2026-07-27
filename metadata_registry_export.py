"""Read-only adapter: converts `metadata` table rows (written by meta_sync.py) into
vnstock_metadata_snapshot Evidence Platform Registry handoff records -- see
ai-core-private/validation/schemas/vnstock_metadata_snapshot_registry_handoff.schema.json and
operations-review/evidence/subsource-freshness-metadata-refresh-closeout-20260727-125051/
REGISTRY_HANDOFF_NOTES.md for the contract this module implements.

Scope, deliberately bounded: this module only reads `metadata` (mode=ro) and shapes records in
memory. It does not choose or write to any registry storage/service -- none exists yet. It never
writes a file unless the caller passes an explicit output path; there is no default production
output location. It does not modify meta_sync.py, the database schema, or daily_analysis_pipeline.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent

SOURCE = "vnstock_metadata_snapshot"

FRESHNESS_SLA = {
    "domain": "vnstock_metadata_snapshot",
    "cadence_days": 92,
    "grace_days": 35,
    "policy_source": 'stock-core-private/freshness_history.py:RULES["vnstock_metadata_snapshot"]',
}

# Ticker-independent field catalog: provider call, qualification status, timestamp basis, and
# (only where applicable) the financial-statement-derived counterpart this value must never be
# aliased with. Mirrors operations-review/evidence/subsource-freshness-metadata-refresh-closeout-
# 20260727-125051/vnstock_metadata_snapshot_field_catalog.json -- this module does not read that
# file at runtime; it is documented prior art, not a live dependency. Dict order is the
# deterministic field order used in every exported record set.
FIELD_CATALOG: dict[str, dict[str, Any]] = {
    "exchange": {
        "provider": "vnstock:Listing(source=VCI).symbols_by_exchange",
        "qualification_status": "reported",
        "timestamp_basis": "scrape_time_live_value",
    },
    "industry": {
        "provider": "vnstock:Listing(source=VCI).symbols_by_industries",
        "qualification_status": "reported",
        "timestamp_basis": "scrape_time_live_value",
    },
    "foreign_room_pct": {
        "provider": "vnstock:Trading(source=VCI).price_board",
        "qualification_status": "derived",
        "timestamp_basis": "scrape_time_live_value",
    },
    "pe": {
        "provider": "vnstock:Finance(source=KBS).ratio",
        "qualification_status": "reported",
        "timestamp_basis": "scrape_time_approximates_unretained_reporting_period",
    },
    "pb": {
        "provider": "vnstock:Finance(source=KBS).ratio",
        "qualification_status": "reported",
        "timestamp_basis": "scrape_time_approximates_unretained_reporting_period",
    },
    "roe": {
        "provider": "vnstock:Finance(source=KBS).ratio",
        "qualification_status": "reported",
        "timestamp_basis": "scrape_time_approximates_unretained_reporting_period",
        "distinct_from": ["financial_summary.roe_quarter", "financial_summary.roe_fy", "financial_summary.roe_ttm"],
    },
    "market_cap": {
        "provider": "vnstock:Company(source=VCI).overview",
        "qualification_status": "reported",
        "timestamp_basis": "scrape_time_live_value",
    },
    "shares_outstanding": {
        "provider": "vnstock:Company(source=VCI).overview",
        "qualification_status": "reported",
        "timestamp_basis": "scrape_time_live_value",
        "distinct_from": [
            "share_reconciliation.period_end_shares_outstanding",
            "share_reconciliation.weighted_average_basic_shares_outstanding",
        ],
    },
    "free_float_est": {
        "provider": "derived_local:Company(source=VCI).shareholders",
        "qualification_status": "proxy",
        "timestamp_basis": "scrape_time_live_value",
    },
    "dividend_yield": {
        "provider": "vnstock:Finance(source=KBS).ratio",
        "qualification_status": "reported",
        "timestamp_basis": "scrape_time_approximates_unretained_reporting_period",
    },
    "margin_status": {
        "provider": "manual_curation:blacklist.csv",
        "qualification_status": "reported",
        "timestamp_basis": "scrape_time_live_value",
    },
}

FIELDS = tuple(FIELD_CATALOG)


def compute_transform_version(meta_sync_path: Path | None = None) -> str:
    """First 12 hex chars of sha256(meta_sync.py), in the registry schema's transform_version
    format. Reads meta_sync.py's current bytes; never modifies it."""
    path = meta_sync_path or (SCRIPT_DIR / "meta_sync.py")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    return f"meta_sync.py@sha256:{digest}"


def _read_only_connection(db_path: Path) -> sqlite3.Connection:
    if not db_path.is_file():
        raise FileNotFoundError(f"metadata database not found: {db_path}")
    conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.row_factory = sqlite3.Row
    return conn


def read_metadata_rows(db_path: Path, tickers: list[str] | None = None) -> list[sqlite3.Row]:
    """Read-only fetch of `metadata` rows, optionally restricted to an explicit ticker subset
    (dry-run/test use). Always ordered by ticker for deterministic output."""
    conn = _read_only_connection(db_path)
    try:
        if tickers:
            placeholders = ",".join("?" for _ in tickers)
            query = f"SELECT * FROM metadata WHERE ticker IN ({placeholders}) ORDER BY ticker"
            return conn.execute(query, list(tickers)).fetchall()
        return conn.execute("SELECT * FROM metadata ORDER BY ticker").fetchall()
    finally:
        conn.close()


def build_records(row: sqlite3.Row, transform_version: str) -> list[dict[str, Any]]:
    """Convert one `metadata` row into zero or more schema-conforming records (one per field).

    Fail-closed: a ticker with no `updated` timestamp (never synced) yields NO records --
    `observed_at` is a required string in the schema, and fabricating one would misrepresent an
    unsynced ticker as observed. A present-but-null FIELD VALUE still yields a record (`value`:
    null is preserved, never coerced to 0/blank), because the ticker itself was observed; the
    dividend_yield -1 sentinel ("queried, no value") is likewise passed through unchanged, never
    reinterpreted as 0, null, or a real yield.
    """
    observed_at = row["updated"]
    if observed_at is None:
        return []
    records = []
    for field in FIELDS:
        spec = FIELD_CATALOG[field]
        record: dict[str, Any] = {
            "source": SOURCE,
            "provider": spec["provider"],
            "ticker": row["ticker"],
            "field": field,
            "value": row[field],
            "timestamps": {
                "observed_at": observed_at,
                "effective_at": observed_at,
                "provider_timestamp": None,
                "timestamp_basis": spec["timestamp_basis"],
            },
            "raw_hash": {"raw_payload_retained": False, "value": None},
            "transform_version": transform_version,
            "qualification_status": spec["qualification_status"],
            "freshness_sla": FRESHNESS_SLA,
        }
        if "distinct_from" in spec:
            record["distinct_from"] = spec["distinct_from"]
        records.append(record)
    return records


def export_records(
    db_path: Path,
    tickers: list[str] | None = None,
    meta_sync_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Read-only end-to-end: `metadata` rows -> schema-conforming records, in memory only.
    Deterministic: the same DB snapshot and meta_sync.py version always produce the same output,
    in the same (ticker, field-catalog) order."""
    transform_version = compute_transform_version(meta_sync_path)
    rows = read_metadata_rows(db_path, tickers)
    records: list[dict[str, Any]] = []
    for row in rows:
        records.extend(build_records(row, transform_version))
    return records


def write_records(records: list[dict[str, Any]], output_path: Path) -> None:
    """Write records as JSON. Requires an explicit path -- there is no default production
    output location, so an accidental invocation cannot overwrite anything."""
    output_path.write_text(
        json.dumps({"records": records}, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run export of `metadata` rows as vnstock_metadata_snapshot registry "
        "handoff records. Read-only; writes a file only when --output is given explicitly."
    )
    parser.add_argument("--db", required=True, type=Path, help="path to vn_stock.db")
    parser.add_argument("--tickers", nargs="*", default=None, help="ticker subset (default: full table)")
    parser.add_argument("--output", type=Path, default=None, help="explicit output path (omit for dry-run only)")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    records = export_records(args.db, args.tickers)
    if args.output is not None:
        write_records(records, args.output)
        print(f"[metadata_registry_export] wrote {len(records)} records to {args.output}")
    else:
        print(f"[metadata_registry_export] dry-run: {len(records)} records (pass --output to write a file)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
