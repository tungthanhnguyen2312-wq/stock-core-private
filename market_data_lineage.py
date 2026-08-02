"""Immutable lineage records for newly ingested OHLCV observations."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import sqlite3
from collections.abc import Mapping
from typing import Any

LINEAGE_SCHEMA_VERSION = "1.0.0"
ADAPTER_SCHEMA_VERSION = "vn_stock_pipeline.ohlcv_lineage/v1"


def installed_provider_version(package: str = "vnstock") -> str:
    """Return the installed package version; do not substitute a guessed value."""
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError as exc:
        raise ValueError("provider_version_unavailable") from exc


def init_ohlcv_lineage_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ohlcv_lineage(
            ticker TEXT NOT NULL, trading_session_date TEXT NOT NULL,
            provider TEXT NOT NULL, provider_version TEXT NOT NULL,
            adapter_schema_version TEXT NOT NULL, endpoint TEXT NOT NULL,
            canonical_field TEXT NOT NULL, retrieved_at TEXT NOT NULL,
            source_record_hash TEXT NOT NULL, unit_scale INTEGER NOT NULL,
            PRIMARY KEY(ticker, trading_session_date))"""
    )


def _canonical_hash(record: Mapping[str, Any]) -> str:
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_ohlcv_lineage_records(frame: Any, *, source: str, endpoint: str,
                                retrieved_at: str, provider_version: str | None = None) -> list[dict[str, Any]]:
    """Build row-bound source-record hashes after canonical scaling.

    The hash is a retained source-record hash, not a claim that an unavailable
    upstream raw payload has been retained.
    """
    required = {"ticker", "date", "open", "high", "low", "close", "volume", "source"}
    if not required.issubset(set(frame.columns)):
        raise ValueError("ohlcv_lineage_input_schema_invalid")
    version = provider_version or installed_provider_version()
    if not version:
        raise ValueError("provider_version_unavailable")
    unit_scale = frame.attrs.get("unit_scale")
    if not isinstance(unit_scale, int) or unit_scale < 1:
        raise ValueError("unit_scale_unavailable")
    records: list[dict[str, Any]] = []
    for row in frame.sort_values(["ticker", "date"]).to_dict("records"):
        source_record = {key: row[key] for key in sorted(required)}
        records.append({
            "ticker": str(row["ticker"]), "trading_session_date": str(row["date"]),
            "provider": source, "provider_version": version,
            "adapter_schema_version": ADAPTER_SCHEMA_VERSION, "endpoint": endpoint,
            "canonical_field": "ohlcv.close", "retrieved_at": retrieved_at,
            "source_record_hash": _canonical_hash(source_record), "unit_scale": unit_scale,
        })
    return records


def upsert_ohlcv_lineage(conn: sqlite3.Connection, records: list[Mapping[str, Any]]) -> None:
    if not records:
        return
    init_ohlcv_lineage_schema(conn)
    fields = ("ticker", "trading_session_date", "provider", "provider_version", "adapter_schema_version",
              "endpoint", "canonical_field", "retrieved_at", "source_record_hash", "unit_scale")
    conn.executemany(
        """INSERT INTO ohlcv_lineage VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(ticker, trading_session_date) DO UPDATE SET
          provider=excluded.provider, provider_version=excluded.provider_version,
          adapter_schema_version=excluded.adapter_schema_version, endpoint=excluded.endpoint,
          canonical_field=excluded.canonical_field, retrieved_at=excluded.retrieved_at,
          source_record_hash=excluded.source_record_hash, unit_scale=excluded.unit_scale""",
        [tuple(record[field] for field in fields) for record in records],
    )
