"""Raw-only contracts shared by DNSE intraday history endpoints.

These contracts preserve the proven raw-ingestion boundary: trades history
has a bounded, retained continuation-to-null-terminal probe and may be
collected market-wide; quotes history remains separately readiness-gated.
They provide deterministic identities and fail-closed pagination rules for
the collector without assigning analytical semantics to either payload.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
from typing import Any, Mapping, Sequence

from market_data_contracts import RawObservation
import vn_time

PROVIDER = "DNSE"
ORDER = "DESC"
DEFAULT_LIMIT = 100
CURSOR_INITIAL = "__INITIAL__"
SPECS = {
    "trades_history": {"endpoint": "/price/{symbol}/trades", "records_field": "trades"},
    "quotes_history": {"endpoint": "/price/{symbol}/quotes", "records_field": "quotes"},
}
# First-party runtime evidence retained under operations-review/...
# Defensive handling in ``continuation_token`` remains broader than this fact.
OBSERVED_PROVIDER_TERMINATION = {
    "trades_history": "NULL",
    "quotes_history": "NULL",
}
DEFENSIVE_SUPPORTED_TERMINATION_STATES = ("FIELD_ABSENT", "NULL", "EMPTY_STRING")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def session_window_epoch(session_date: str) -> tuple[int, int]:
    start = datetime.strptime(session_date, "%Y-%m-%d").replace(tzinfo=vn_time.VN_TZ)
    return int(start.timestamp()), int((start + timedelta(days=1) - timedelta(seconds=1)).timestamp())


def request_query(dataset: str, session_date: str, *, limit: int = DEFAULT_LIMIT,
                  order: str = ORDER, cursor: str | None = None,
                  board_id: str | None = None) -> dict[str, Any]:
    if dataset not in SPECS:
        raise ValueError("unsupported_intraday_history_dataset")
    if order not in {"ASC", "DESC"}:
        raise ValueError("unsupported_order")
    start, end = session_window_epoch(session_date)
    query: dict[str, Any] = {"from": start, "to": end, "limit": limit, "order": order}
    if board_id is not None:
        query["boardId"] = board_id
    if cursor is not None:
        query["nextPageToken"] = cursor
    return query


def extract_records(dataset: str, body: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    try:
        field = SPECS[dataset]["records_field"]
    except KeyError as exc:
        raise ValueError("unsupported_intraday_history_dataset") from exc
    records = body.get(field)
    if records is None:
        return []
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise ValueError(f"{field}_field_not_a_list")
    if not all(isinstance(record, Mapping) for record in records):
        raise ValueError(f"{field}_contains_non_object")
    return list(records)


def page_identity(*, dataset: str, symbol: str, session_date: str,
                  query: Mapping[str, Any], cursor: str | None, body: Mapping[str, Any]) -> str:
    value = {"provider": PROVIDER, "dataset": dataset, "symbol": symbol.upper(),
             "session_date": session_date, "query": dict(query),
             "cursor": CURSOR_INITIAL if cursor is None else cursor, "body": dict(body)}
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def record_identity(*, dataset: str, symbol: str, session_date: str,
                    page_id: str, record: Mapping[str, Any]) -> str:
    """Synthetic retention identity, not a claim of a provider natural key."""
    value = {"provider": PROVIDER, "dataset": dataset, "symbol": symbol.upper(),
             "session_date": session_date, "page_identity": page_id, "record": dict(record)}
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def continuation_token(body: Mapping[str, Any], *, seen_tokens: set[str],
                       seen_pages: set[str], page_id: str) -> str | None:
    """Return the next cursor or fail closed on malformed/repeated continuation."""
    if page_id in seen_pages:
        raise ValueError("repeated_page_detected")
    token = body.get("nextPageToken")
    if token is None or token == "":
        return None
    if not isinstance(token, str):
        raise ValueError("malformed_next_page_token")
    if token in seen_tokens:
        raise ValueError("repeated_next_page_token")
    return token


def work_unit_id(dataset: str, symbol: str, session_date: str, board_id: str | None = None) -> str:
    if dataset not in SPECS:
        raise ValueError("unsupported_intraday_history_dataset")
    suffix = "ALL_BOARDS" if board_id is None else f"BOARD_{board_id}"
    return f"{symbol.upper()}__{session_date.replace('-', '')}__{suffix}"


def page_unit_id(work_unit: str, cursor: str | None) -> str:
    marker = CURSOR_INITIAL if cursor is None else hashlib.sha256(cursor.encode("utf-8")).hexdigest()[:16]
    return f"{work_unit}__page_{marker}"


def observation(*, dataset: str, symbol: str, session_date: str, response: Mapping[str, Any],
                cursor: str | None, page_index: int, run_id: str, run_scope_id: str,
                page_unit: str, records: Sequence[Mapping[str, Any]]) -> RawObservation:
    body = dict(response.get("body") or {})
    query = dict(response.get("query_sent") or {})
    request = {"provider": PROVIDER, "dataset": dataset, "endpoint": response.get("endpoint"),
               "symbol": symbol.upper(), "session_date": session_date, "cursor": cursor,
               "page_index": page_index, "query": query}
    return RawObservation(
        provider=PROVIDER, dataset=dataset, instrument=symbol.upper(), retrieved_at=vn_time.vn_now_iso(),
        source_event_time=session_date, request_identity=canonical_json(request),
        raw_payload_hash=hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest(),
        schema_version="1.0.0", raw_payload=body,
        provenance={"endpoint": response.get("endpoint"), "request_parameters": query,
                    "http_status": response.get("http_status"), "page_index": page_index,
                    "page_cursor": cursor, "returned_raw_record_count": len(records),
                    "ingestion_run_id": run_id, "checkpoint_identity": run_scope_id,
                    "checkpoint_unit_id": page_unit, "raw_semantics": "PRESERVED_UNQUALIFIED"},
    )
