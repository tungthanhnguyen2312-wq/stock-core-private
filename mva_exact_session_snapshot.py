"""Fail-closed DNSE-only exact-session shadow snapshot for MVA.

This module is deliberately separate from the dashboard runtime database.  It
materializes a bounded, immutable observation envelope which may feed shadow
research only; it never promotes a price basis or writes production data.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping

from dnse_bulk_market_data import fetch_capability_raw
from field_temporal_contract import stable_id
from freshness_history import latest_completed_market_day

VN_TZ = timezone(timedelta(hours=7))
LOOKBACK_SESSIONS = 20
CONTRACT_VERSION = "p3f9_exact_session_mva_snapshot/v1"
REQUIRED_ENVELOPE = {
    "is_actionable_for_execution": False,
    "pit_backtest_eligible": False,
    "liquidity_sizing_authority": "BLOCKED",
    "valuation_scope": "CURRENT_DESCRIPTIVE_ONLY",
}


def canonical_candidates(runtime_root: Path) -> list[str]:
    """Read, but never mutate, the existing canonical-candidate mapping."""
    database = runtime_root / "vn_stock.db"
    connection = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        return [str(row[0]).upper() for row in connection.execute("SELECT ticker FROM metadata ORDER BY ticker")]
    finally:
        connection.close()


def resolved_completed_session(requested_at: datetime) -> str:
    local = requested_at.astimezone(VN_TZ) if requested_at.tzinfo else requested_at.replace(tzinfo=VN_TZ)
    return latest_completed_market_day(local).isoformat()


def _row_date(epoch: Any) -> str | None:
    if isinstance(epoch, bool) or not isinstance(epoch, (int, float)):
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(VN_TZ).date().isoformat()


def _observation_rows(body: Mapping[str, Any], *, requested_session: str, query: Mapping[str, Any], retrieved_at: str) -> tuple[list[dict[str, Any]], str | None]:
    arrays = {key: body.get(key) for key in ("t", "o", "h", "l", "c", "v")}
    if any(not isinstance(value, list) for value in arrays.values()):
        return [], "MALFORMED_RESPONSE"
    sizes = {len(value) for value in arrays.values()}
    if len(sizes) != 1:
        return [], "MALFORMED_RESPONSE"
    rows: list[dict[str, Any]] = []
    for index, epoch in enumerate(arrays["t"]):
        session = _row_date(epoch)
        close = arrays["c"][index]
        volume = arrays["v"][index]
        if session is None or isinstance(close, bool) or not isinstance(close, (int, float)) or isinstance(volume, bool) or not isinstance(volume, (int, float)):
            continue
        rows.append({
            "session": session, "open": arrays["o"][index], "high": arrays["h"][index], "low": arrays["l"][index],
            "close": float(close) * 1000.0, "volume": int(volume), "provider": "DNSE", "dataset": "DNSE_OHLC_1D",
            "field_identity": {"close": "DNSE_OHLC.close", "volume": "DNSE_OHLC.volume"},
            "request": dict(query), "retrieved_at": retrieved_at,
            "price_basis": "CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED",
            "qualification": "CURRENT_MARKET_DESCRIPTIVE_QUALIFIED_ONLY",
        })
    exact = [row for row in rows if row["session"] == requested_session]
    if len(exact) != 1:
        return rows, "EXACT_SESSION_MISSING" if not exact else "EXACT_SESSION_AMBIGUOUS"
    return rows, None


def materialize_snapshot(*, candidates: list[str], requested_at: datetime, api_key: str, api_secret: str,
                         fetcher: Callable[..., dict[str, Any]] = fetch_capability_raw, workers: int = 8,
                         request_limit: int | None = None) -> dict[str, Any]:
    """Fetch each canonical candidate through one generic DNSE path, no fallback."""
    target = resolved_completed_session(requested_at)
    start = datetime.combine(datetime.fromisoformat(target).date() - timedelta(days=45), datetime.min.time(), VN_TZ)
    end = datetime.combine(datetime.fromisoformat(target).date() + timedelta(days=1), datetime.min.time(), VN_TZ) - timedelta(seconds=1)
    query_base = {"resolution": "1D", "from": int(start.timestamp()), "to": int(end.timestamp()), "type": "STOCK"}
    retrieved_at = requested_at.astimezone(VN_TZ).isoformat()

    def one(ticker: str) -> tuple[str, dict[str, Any]]:
        query = {"symbol": ticker, **query_base}
        response = fetcher("ohlc", api_key=api_key, api_secret=api_secret, symbol=None, query=query)
        if not response.get("ok"):
            return ticker, {"status": "FETCH_FAILED", "reason": str(response.get("error_code", "FETCH_FAILED")), "observations": [], "request": query}
        body = response.get("body")
        if not isinstance(body, Mapping):
            return ticker, {"status": "MALFORMED_RESPONSE", "reason": "BODY_NOT_OBJECT", "observations": [], "request": query}
        rows, problem = _observation_rows(body, requested_session=target, query=query, retrieved_at=retrieved_at)
        payload_hash = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        return ticker, {"status": "OBSERVED" if problem is None else problem, "reason": problem, "observations": rows,
                        "payload_hash": payload_hash, "request": query, "provider_endpoint": response.get("endpoint")}

    attempted = candidates if request_limit is None else candidates[:max(0, request_limit)]
    records: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, ticker): ticker for ticker in attempted}
        for future in as_completed(futures):
            ticker, result = future.result()
            records[ticker] = result
    for ticker in candidates:
        records.setdefault(ticker, {"status": "NOT_ATTEMPTED_BOUNDED_PROVIDER_WINDOW", "reason": "EXPLICIT_PARTIAL_MATERIALIZATION", "observations": [], "request": None})
    records = {ticker: records[ticker] for ticker in sorted(records)}
    observed = sum(record["status"] == "OBSERVED" for record in records.values())
    session_counts: dict[str, int] = {}
    for record in records.values():
        for row in record["observations"]:
            if row["session"] <= target:
                session_counts[row["session"]] = session_counts.get(row["session"], 0) + 1
    sessions = sorted(session_counts, reverse=True)[:LOOKBACK_SESSIONS]
    sessions = list(reversed(sessions))
    complete = sum(record["status"] == "OBSERVED" and all(any(row["session"] == session for row in record["observations"]) for session in sessions) for record in records.values()) if len(sessions) == LOOKBACK_SESSIONS else 0
    snapshot: dict[str, Any] = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "artifact_type": "P3F9_MVA_EXACT_SESSION_SNAPSHOT",
        **REQUIRED_ENVELOPE,
        "resolved_completed_session": target, "retained_snapshot_session": target, "requested_at": retrieved_at,
        "canonical_identity": "runtime_metadata_ticker_sorted_v1", "candidate_count": len(candidates),
        "materialization_scope": "FULL_CANONICAL_CANDIDATE_SET" if request_limit is None else "EXPLICIT_PARTIAL_PROVIDER_WINDOW",
        "attempted_candidate_count": len(attempted), "exact_session_observed_count": observed, "empirical_20_session_complete_count": complete,
        "missing_current_session_count": len(candidates) - observed, "sessions": sessions,
        "source": {"provider": "DNSE", "endpoint": "/price/ohlc", "dataset": "DNSE_OHLC_1D", "request_contract": query_base,
                   "no_older_session_substitution": True, "intraday_observations_used": False},
        "records": records,
        "authority_boundary": {"CURRENT_MARKET": "DESCRIPTIVE_QUALIFIED_ONLY", "RAW_AS_TRADED": "NOT_PROMOTED", "HISTORICAL_PIT": "BLOCKED",
                               "runtime_database_mutated": False},
    }
    snapshot["snapshot_sha256"] = stable_id(snapshot)
    snapshot["snapshot_identity"] = f"p3f9_exact_session_snapshot:{snapshot['snapshot_sha256']}"
    return snapshot


def write_snapshot(snapshot: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError("IMMUTABLE_SNAPSHOT_PATH_ALREADY_EXISTS")
    path.write_text(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
