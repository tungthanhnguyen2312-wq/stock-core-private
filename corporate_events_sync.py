"""VCI-only forward observation of corporate events; never a complete snapshot."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any


CORPORATE_EVENTS_SCHEMA_VERSION = 1
QUALIFIED_PROVIDER = "VCI"
QUALIFIED_VNSTOCK_VERSION = "4.0.4"
VCI_EVENTS_ENDPOINT = "vnstock.api.company.Company(source='VCI').events()"
COVERAGE_STATUS = "partial_unqualified_50_row_cap"


class CorporateEventsContractError(ValueError):
    """Raised when a provider response cannot be represented safely."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _provider(value: str) -> str:
    provider = _text(value)
    if provider != QUALIFIED_PROVIDER:
        raise CorporateEventsContractError(f"unsupported corporate events provider: {value}")
    return provider


def _ticker(value: str) -> str:
    ticker = (_text(value) or "").upper()
    if not ticker:
        raise CorporateEventsContractError("ticker is required")
    return ticker


def _raw_hash(payload: Mapping[str, Any]) -> tuple[str, str]:
    raw_json = _canonical_json(payload)
    return raw_json, hashlib.sha256(raw_json.encode("utf-8")).hexdigest()


def normalize_event(ticker: str, provider: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one VCI event without deriving dates, status, ordering, or amounts."""
    source = _provider(provider)
    expected_ticker = _ticker(ticker)
    if not isinstance(payload, Mapping) or not payload:
        raise CorporateEventsContractError("corporate event payload must be a non-empty object")
    provider_event_id = _text(payload.get("id"))
    if not provider_event_id:
        raise CorporateEventsContractError("corporate event payload is missing provider event id")
    payload_ticker = (_text(payload.get("ticker")) or "").upper()
    if payload_ticker != expected_ticker:
        raise CorporateEventsContractError(
            f"corporate event ticker mismatch: expected {expected_ticker}, got {payload_ticker or 'missing'}"
        )
    return {
        "provider": source,
        "provider_event_id": provider_event_id,
        "ticker": expected_ticker,
        "event_code": _text(payload.get("event_code")),
        "category": _text(payload.get("category")),
        "event_name_vi": _text(payload.get("event_name_vi")),
        "event_name_en": _text(payload.get("event_name_en")),
        "event_title_vi": _text(payload.get("event_title_vi")),
        "event_title_en": _text(payload.get("event_title_en")),
        "display_date1": payload.get("display_date1"),
        "display_date2": payload.get("display_date2"),
        "public_date": payload.get("public_date"),
        "record_date": payload.get("record_date"),
        "exright_date": payload.get("exright_date"),
        "issue_date": payload.get("issue_date"),
        "start_date": payload.get("start_date"),
        "end_date": payload.get("end_date"),
        "payout_date": payload.get("payout_date"),
        "listing_date": payload.get("listing_date"),
        "exercise_ratio": payload.get("exercise_ratio"),
        "value_per_share": payload.get("value_per_share"),
    }


def init_db(conn: sqlite3.Connection) -> None:
    """Apply only additive forward-observation tables to an existing database."""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""CREATE TABLE IF NOT EXISTS corporate_event_records(
        record_id TEXT PRIMARY KEY,
        schema_version INTEGER NOT NULL,
        provider TEXT NOT NULL,
        provider_event_id TEXT NOT NULL,
        ticker TEXT NOT NULL,
        event_code TEXT,
        category TEXT,
        event_name_vi TEXT,
        event_name_en TEXT,
        event_title_vi TEXT,
        event_title_en TEXT,
        display_date1 TEXT,
        display_date2 TEXT,
        public_date TEXT,
        record_date TEXT,
        exright_date TEXT,
        issue_date TEXT,
        start_date TEXT,
        end_date TEXT,
        payout_date TEXT,
        listing_date TEXT,
        exercise_ratio REAL,
        value_per_share REAL,
        first_observed_at TEXT NOT NULL,
        last_observed_at TEXT NOT NULL,
        revision_status TEXT NOT NULL,
        coverage_status TEXT NOT NULL,
        UNIQUE(provider, provider_event_id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS corporate_event_observations(
        observation_id TEXT PRIMARY KEY,
        record_id TEXT NOT NULL REFERENCES corporate_event_records(record_id),
        provider TEXT NOT NULL,
        provider_event_id TEXT NOT NULL,
        ticker TEXT NOT NULL,
        raw_payload_json TEXT NOT NULL,
        raw_payload_hash TEXT NOT NULL,
        retrieved_at TEXT NOT NULL,
        vnstock_version TEXT NOT NULL,
        endpoint TEXT NOT NULL,
        parameters_json TEXT NOT NULL,
        coverage_status TEXT NOT NULL,
        revision_status TEXT NOT NULL,
        UNIQUE(provider, provider_event_id, raw_payload_hash))""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_corporate_event_observations_record_time
        ON corporate_event_observations(record_id, retrieved_at)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS corporate_event_ingestion_runs(
        run_id TEXT PRIMARY KEY,
        schema_version INTEGER NOT NULL,
        provider TEXT NOT NULL,
        ticker TEXT NOT NULL,
        retrieved_at TEXT NOT NULL,
        vnstock_version TEXT NOT NULL,
        endpoint TEXT NOT NULL,
        parameters_json TEXT NOT NULL,
        coverage_status TEXT NOT NULL,
        response_count INTEGER NOT NULL,
        accepted_count INTEGER NOT NULL,
        status TEXT NOT NULL,
        error_text TEXT)""")
    conn.commit()


def _run_id(provider: str, ticker: str, retrieved_at: str, parameters_json: str) -> str:
    return hashlib.sha256(_canonical_json([CORPORATE_EVENTS_SCHEMA_VERSION, provider, ticker, retrieved_at, parameters_json]).encode("utf-8")).hexdigest()


def ingest_events(
    conn: sqlite3.Connection,
    ticker: str,
    provider: str,
    payloads: Sequence[Mapping[str, Any]],
    retrieved_at: str,
    *,
    vnstock_version: str = QUALIFIED_VNSTOCK_VERSION,
    endpoint: str = VCI_EVENTS_ENDPOINT,
    parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist one bounded VCI response; identical evidence is idempotent.

    A response is always recorded as incomplete because the qualified public
    API has a 50-row cap and no qualified total, ordering, or pagination.
    """
    source = _provider(provider)
    symbol = _ticker(ticker)
    if not retrieved_at:
        raise CorporateEventsContractError("retrieved_at is required")
    if vnstock_version != QUALIFIED_VNSTOCK_VERSION:
        raise CorporateEventsContractError(f"unqualified vnstock version: {vnstock_version}")
    if not isinstance(payloads, Sequence) or isinstance(payloads, (str, bytes, bytearray)):
        raise CorporateEventsContractError("corporate events payload must be a sequence")
    parameters_json = _canonical_json(dict(parameters or {}))
    run_id = _run_id(source, symbol, retrieved_at, parameters_json)
    init_db(conn)
    accepted: list[dict[str, Any]] = []
    try:
        for payload in payloads:
            accepted.append(normalize_event(symbol, source, payload))
        seen: set[str] = set()
        for event in accepted:
            if event["provider_event_id"] in seen:
                raise CorporateEventsContractError(f"duplicate provider event id in response: {event['provider_event_id']}")
            seen.add(event["provider_event_id"])
        status = "source_empty" if not accepted else "observed_incomplete"
        conn.execute(
            """INSERT INTO corporate_event_ingestion_runs
            (run_id,schema_version,provider,ticker,retrieved_at,vnstock_version,endpoint,parameters_json,
             coverage_status,response_count,accepted_count,status,error_text)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(run_id) DO NOTHING""",
            (run_id, CORPORATE_EVENTS_SCHEMA_VERSION, source, symbol, retrieved_at, vnstock_version, endpoint,
             parameters_json, COVERAGE_STATUS, len(payloads), len(accepted), status, None),
        )
        inserted_observations = 0
        revisions = 0
        for event, payload in zip(accepted, payloads):
            raw_json, payload_hash = _raw_hash(payload)
            record_id = hashlib.sha256(_canonical_json([source, event["provider_event_id"]]).encode("utf-8")).hexdigest()
            existing = conn.execute(
                "SELECT record_id,ticker FROM corporate_event_records WHERE provider=? AND provider_event_id=?",
                (source, event["provider_event_id"]),
            ).fetchone()
            if existing and existing[1] != symbol:
                raise CorporateEventsContractError("provider event identity conflicts with an existing ticker")
            prior = conn.execute("SELECT 1 FROM corporate_event_observations WHERE record_id=? LIMIT 1", (record_id,)).fetchone()
            revision_status = "revised_or_unknown" if prior else "observed"
            if not existing:
                conn.execute(
                    """INSERT INTO corporate_event_records
                    (record_id,schema_version,provider,provider_event_id,ticker,event_code,category,event_name_vi,event_name_en,
                     event_title_vi,event_title_en,display_date1,display_date2,public_date,record_date,exright_date,issue_date,
                     start_date,end_date,payout_date,listing_date,exercise_ratio,value_per_share,first_observed_at,last_observed_at,
                     revision_status,coverage_status)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (record_id, CORPORATE_EVENTS_SCHEMA_VERSION, source, event["provider_event_id"], symbol,
                     event["event_code"], event["category"], event["event_name_vi"], event["event_name_en"],
                     event["event_title_vi"], event["event_title_en"], event["display_date1"], event["display_date2"],
                     event["public_date"], event["record_date"], event["exright_date"], event["issue_date"], event["start_date"],
                     event["end_date"], event["payout_date"], event["listing_date"], event["exercise_ratio"], event["value_per_share"],
                     retrieved_at, retrieved_at, revision_status, COVERAGE_STATUS),
                )
            observation_id = hashlib.sha256(_canonical_json([source, event["provider_event_id"], payload_hash]).encode("utf-8")).hexdigest()
            inserted = conn.execute(
                """INSERT INTO corporate_event_observations
                (observation_id,record_id,provider,provider_event_id,ticker,raw_payload_json,raw_payload_hash,retrieved_at,
                 vnstock_version,endpoint,parameters_json,coverage_status,revision_status)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(provider,provider_event_id,raw_payload_hash) DO NOTHING""",
                (observation_id, record_id, source, event["provider_event_id"], symbol, raw_json, payload_hash, retrieved_at,
                 vnstock_version, endpoint, parameters_json, COVERAGE_STATUS, revision_status),
            ).rowcount == 1
            if inserted:
                inserted_observations += 1
                if prior:
                    revisions += 1
                    conn.execute(
                        """UPDATE corporate_event_records SET last_observed_at=?, revision_status=?
                        WHERE record_id=?""", (retrieved_at, "revised_or_unknown", record_id))
        conn.commit()
    except (sqlite3.Error, CorporateEventsContractError):
        conn.rollback()
        raise
    return {"run_id": run_id, "provider": source, "ticker": symbol, "response_count": len(payloads),
            "accepted_count": len(accepted), "inserted_observations": inserted_observations,
            "revisions": revisions, "status": status, "coverage_status": COVERAGE_STATUS}


def payloads_from_vci_frame(frame: Any) -> list[dict[str, Any]]:
    """Serialize the public VCI result without inventing pagination or status."""
    return json.loads(frame.to_json(orient="records", date_format="iso", force_ascii=False))


def fetch_vci_events(ticker: str) -> tuple[list[dict[str, Any]], str]:
    """Explicit live fetch entry point; no alternate provider is available."""
    version = importlib.metadata.version("vnstock")
    if version != QUALIFIED_VNSTOCK_VERSION:
        raise CorporateEventsContractError(f"unqualified vnstock version: {version}")
    from vnstock.api.company import Company

    frame = Company(source=QUALIFIED_PROVIDER, symbol=_ticker(ticker), random_agent=False, show_log=False).events()
    return payloads_from_vci_frame(frame), version


def sync_ticker(conn: sqlite3.Connection, ticker: str, *, retrieved_at: str | None = None) -> dict[str, Any]:
    payloads, version = fetch_vci_events(ticker)
    return ingest_events(conn, ticker, QUALIFIED_PROVIDER, payloads, retrieved_at or datetime.now(timezone.utc).isoformat(), vnstock_version=version)


def main() -> None:
    parser = argparse.ArgumentParser(description="Store VCI corporate-event observations; never a complete snapshot.")
    parser.add_argument("--ticker", action="append", required=True, help="Ticker to fetch from VCI; may be repeated.")
    parser.add_argument("--database", default="vn_stock.db")
    args = parser.parse_args()
    with sqlite3.connect(args.database) as conn:
        for ticker in args.ticker:
            result = sync_ticker(conn, ticker)
            print(f"{result['ticker']} {result['provider']} observations={result['inserted_observations']} coverage={result['coverage_status']}")


if __name__ == "__main__":
    main()
