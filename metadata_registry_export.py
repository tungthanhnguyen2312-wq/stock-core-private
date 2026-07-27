"""Read-only adapter: converts `metadata` table rows (written by meta_sync.py) into
vnstock_metadata_snapshot Evidence Platform Registry handoff records -- see
ai-core-private/validation/schemas/vnstock_metadata_snapshot_registry_handoff.schema.json and
operations-review/evidence/subsource-freshness-metadata-refresh-closeout-20260727-125051/
REGISTRY_HANDOFF_NOTES.md for the contract this module implements.

Scope, deliberately bounded: this module only reads `metadata` (mode=ro) and shapes records in
memory. It does not choose or write to any registry storage/service beyond plain immutable files
on local disk. It never writes a file unless the caller passes an explicit output path or the
--registry-snapshot flag; there is no default production trigger. It does not modify meta_sync.py,
the database schema, or daily_analysis_pipeline.py -- this never runs as part of the daily chain.

`--registry-snapshot` writes one immutable JSONL file per invocation into
`registry_snapshots/metadata/` (see docs/metadata_registry_snapshot_contract.md for the naming,
atomicity, and retention contract).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_REGISTRY_SNAPSHOT_DIR = SCRIPT_DIR / "registry_snapshots" / "metadata"

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


def _sorted_for_output(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable sort by (ticker, field-catalog order), independent of the input order, so a
    registry snapshot's content -- and therefore its content-hash filename component -- never
    depends on how records happened to be assembled or which ticker subset was requested."""
    return sorted(records, key=lambda r: (r["ticker"], FIELDS.index(r["field"])))


def _jsonl_body(records: list[dict[str, Any]]) -> bytes:
    ordered = _sorted_for_output(records)
    if not ordered:
        return b""
    lines = (json.dumps(r, ensure_ascii=False, allow_nan=False) for r in ordered)
    return ("\n".join(lines) + "\n").encode("utf-8")


def registry_snapshot_filename(body: bytes, now: datetime) -> str:
    """`vnstock_metadata_snapshot_<UTC-YYYYMMDDTHHMMSSZ>_<content-sha256-12>.jsonl` -- timestamp
    and content hash are both embedded so two snapshots (different content, or the same content
    a second apart) never collide on name."""
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    content_hash = hashlib.sha256(body).hexdigest()[:12]
    return f"vnstock_metadata_snapshot_{stamp}_{content_hash}.jsonl"


def write_registry_snapshot(
    records: list[dict[str, Any]],
    registry_dir: Path,
    now: datetime | None = None,
) -> Path:
    """Atomically write ONE immutable JSONL snapshot into registry_dir: a temp file in the same
    directory, then a rename -- same-volume atomic, and on this project's Windows environment
    `os.rename` raises rather than overwriting if the destination already exists. That covers the
    only way two invocations could otherwise collide (same UTC second and byte-identical
    content); anything already there is left untouched and this raises FileExistsError instead
    of silently succeeding or clobbering.

    Never writes unless explicitly called -- there is no scheduling or pipeline wiring here.
    """
    now = now or datetime.now(timezone.utc)
    body = _jsonl_body(records)
    filename = registry_snapshot_filename(body, now)
    registry_dir.mkdir(parents=True, exist_ok=True)
    final_path = registry_dir / filename
    if final_path.exists():
        raise FileExistsError(f"registry snapshot already exists, refusing to overwrite: {final_path}")
    fd, tmp_name = tempfile.mkstemp(dir=registry_dir, prefix=".tmp-", suffix=".jsonl")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
        os.rename(tmp_name, final_path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return final_path


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run export of `metadata` rows as vnstock_metadata_snapshot registry "
        "handoff records. Read-only; writes a file only when --output or --registry-snapshot "
        "is given explicitly."
    )
    parser.add_argument("--db", required=True, type=Path, help="path to vn_stock.db")
    parser.add_argument("--tickers", nargs="*", default=None, help="ticker subset (default: full table)")
    parser.add_argument("--output", type=Path, default=None, help="explicit output path (omit for dry-run only)")
    parser.add_argument(
        "--registry-snapshot",
        nargs="?",
        const=str(DEFAULT_REGISTRY_SNAPSHOT_DIR),
        default=None,
        metavar="DIR",
        help="write one immutable JSONL registry snapshot into DIR (default when given with no "
        "value: registry_snapshots/metadata/ next to this script). Omit this flag entirely to "
        "skip -- this never runs implicitly.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    records = export_records(args.db, args.tickers)
    if args.output is not None:
        write_records(records, args.output)
        print(f"[metadata_registry_export] wrote {len(records)} records to {args.output}")
    if args.registry_snapshot is not None:
        path = write_registry_snapshot(records, Path(args.registry_snapshot))
        print(f"[metadata_registry_export] wrote immutable registry snapshot: {path}")
    if args.output is None and args.registry_snapshot is None:
        print(f"[metadata_registry_export] dry-run: {len(records)} records "
              "(pass --output or --registry-snapshot to write a file)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
