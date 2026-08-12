"""Restartable raw-only DNSE foreign-trading collection contract.

This module deliberately retains full provider pages without normalizing or
combining their values.  Existing foreign-flow VALUE authority is a separate
downstream contract and is never read or widened here.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import market_raw_lake as lake
from market_data_contracts import RawObservation
import vn_time

PROVIDER = "DNSE"
DATASET = "foreign_trading"
CAPABILITY = "foreign_trading"
SCHEMA_VERSION = "1.0.0"
ORDER = "DESC"
DEFAULT_LIMIT = 100
DEFAULT_MAX_PAGES_PER_WORK = 1000
APPLICABLE_INSTRUMENT_CLASS = "EQUITY"
CURSOR_INITIAL = "__INITIAL__"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def session_window_epoch(session_date: str) -> tuple[int, int]:
    start = datetime.strptime(session_date, "%Y-%m-%d").replace(tzinfo=vn_time.VN_TZ)
    end = start + timedelta(days=1) - timedelta(seconds=1)
    return int(start.timestamp()), int(end.timestamp())


def load_applicable_symbols(snapshot_path: Path) -> list[str]:
    import pandas as pd

    frame = pd.read_parquet(snapshot_path)
    required = {"symbol", "instrument_class"}
    if not required.issubset(frame.columns):
        raise ValueError("universe snapshot missing symbol/instrument_class")
    eligible = frame[frame["instrument_class"].eq(APPLICABLE_INSTRUMENT_CLASS)]
    symbols = sorted(set(eligible["symbol"].astype(str).str.upper()))
    if not symbols:
        raise ValueError("universe snapshot has no directly evidenced EQUITY symbols")
    return symbols


def work_unit_id(symbol: str, session_date: str) -> str:
    return f"{symbol.upper()}__{session_date.replace('-', '')}"


def page_unit_id(work_unit: str, cursor: str | None) -> str:
    marker = CURSOR_INITIAL if cursor is None else hashlib.sha256(cursor.encode("utf-8")).hexdigest()[:16]
    return f"{work_unit}__page_{marker}"


def compute_run_scope_id(*, symbols: Sequence[str], session_date: str, limit: int = DEFAULT_LIMIT,
                         order: str = ORDER, board_scope: str = "UNSPECIFIED") -> str:
    identity = canonical_json({"provider": PROVIDER, "dataset": DATASET,
                               "symbols": sorted(set(symbols)), "session_date": session_date,
                               "limit": limit, "order": order, "board_scope": board_scope})
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def request_query(symbol: str, session_date: str, *, limit: int = DEFAULT_LIMIT,
                  order: str = ORDER, cursor: str | None = None, board_id: str | None = None) -> dict[str, Any]:
    from_ts, to_ts = session_window_epoch(session_date)
    query: dict[str, Any] = {"from": from_ts, "to": to_ts, "limit": limit, "order": order}
    if board_id is not None:
        query["boardId"] = board_id
    if cursor is not None:
        query["nextPageToken"] = cursor
    return query


def extract_records(body: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    records = body.get("foreigners")
    if records is None:
        return []
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise ValueError("foreigners_field_not_a_list")
    if not all(isinstance(record, Mapping) for record in records):
        raise ValueError("foreigners_contains_non_object")
    return list(records)


def board_ids(records: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted({str(record["boardId"]) for record in records if record.get("boardId") is not None})


def observation(*, symbol: str, session_date: str, response: Mapping[str, Any], cursor: str | None,
                page_index: int, run_id: str, run_scope_id: str, page_unit: str,
                records: Sequence[Mapping[str, Any]]) -> RawObservation:
    body = dict(response.get("body") or {})
    request_identity = {"provider": PROVIDER, "dataset": DATASET, "endpoint": response.get("endpoint"),
                        "symbol": symbol, "session_date": session_date, "page_index": page_index,
                        "cursor": cursor, "query": response.get("query_sent") or {}}
    return RawObservation(
        provider=PROVIDER, dataset=DATASET, instrument=symbol, retrieved_at=vn_time.vn_now_iso(),
        source_event_time=session_date,
        request_identity=canonical_json(request_identity),
        raw_payload_hash=hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest(),
        schema_version=SCHEMA_VERSION, raw_payload=body,
        provenance={"endpoint": response.get("endpoint"), "request_parameters": response.get("query_sent") or {},
                    "http_status": response.get("http_status"), "elapsed_ms": response.get("elapsed_ms"),
                    "provider_interface_version": response.get("provider_interface_version"),
                    "page_index": page_index, "page_cursor": cursor, "returned_raw_record_count": len(records),
                    "returned_board_ids": board_ids(records), "ingestion_run_id": run_id,
                    "checkpoint_identity": run_scope_id, "checkpoint_unit_id": page_unit,
                    "raw_semantics": "PRESERVED_UNQUALIFIED"},
    )


def pagination_state(checkpoint: Mapping[str, Any], work_unit: str) -> dict[str, Any]:
    states = checkpoint.get("foreign_pagination", {})
    state = states.get(work_unit, {}) if isinstance(states, Mapping) else {}
    return dict(state) if isinstance(state, Mapping) else {}


def with_pagination_state(checkpoint: Mapping[str, Any], work_unit: str,
                          state: Mapping[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(dict(checkpoint))
    updated.setdefault("foreign_pagination", {})[work_unit] = dict(state)
    return updated


def page_fingerprint(body: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
