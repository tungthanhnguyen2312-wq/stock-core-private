"""Producer-owned Point-in-Time Benchmark Return and Session Alignment MVP for Stock Lookup.

Qualifies VN-Index benchmark observations, builds point-in-time benchmark simple returns,
and performs exact-date session alignment between VNM adjusted returns and benchmark returns.

Emits 0 beta, 0 correlation, and 0 backtest outputs.
"""

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from point_in_time_adjusted_returns import build_point_in_time_adjusted_returns
from semantic_evidence_bridge import DB_RELATIVE

BENCHMARK_CONTRACT_VERSION = "1.0.0"
ALIGNMENT_CONTRACT_VERSION = "1.0.0"
QUALIFIED_BENCHMARK_SYMBOL = "VNINDEX"
QUALIFIED_BENCHMARK_NAME = "VN-Index"
QUALIFIED_BENCHMARK_ADMINISTRATOR = "Ho Chi Minh Stock Exchange (HOSE)"
BENCHMARK_RELATIVE_PATH = Path("data") / "official-evidence" / "benchmark_citations.jsonl"


def _hash(value: Any) -> str:
    """Compute deterministic SHA-256 string for canonical benchmark and alignment objects."""
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _load_benchmark_citations(runtime_root: Path) -> list[dict[str, Any]]:
    """Load benchmark citations from official evidence file if present."""
    path = runtime_root / BENCHMARK_RELATIVE_PATH
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows
    except (json.JSONDecodeError, OSError):
        return []


def _query_raw_benchmark_ohlcv(db_path: Path, symbol: str = "VNINDEX") -> list[dict[str, Any]]:
    """Query raw daily benchmark OHLCV index rows from db_path."""
    if not db_path.is_file():
        return []
    try:
        connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        # Check if ohlcv or index_ohlcv contains benchmark symbol
        cursor = connection.execute(
            "SELECT ticker as symbol, date as trading_date, open, high, low, close as raw_index_level, volume, source FROM ohlcv WHERE ticker=? ORDER BY date ASC",
            (symbol,),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        connection.close()
        return rows
    except sqlite3.Error:
        return []


def build_point_in_time_benchmark_returns(
    runtime_root: Path,
    symbol: str = QUALIFIED_BENCHMARK_SYMBOL,
    knowledge_cutoff: str | None = None,
) -> dict[str, Any]:
    """Build point-in-time benchmark simple return series under an explicit knowledge_cutoff.

    Returns:
        {
            "status": "available" | "unavailable",
            "benchmark_contract_version": BENCHMARK_CONTRACT_VERSION,
            "symbol": symbol,
            "benchmark_name": QUALIFIED_BENCHMARK_NAME,
            "administrator": QUALIFIED_BENCHMARK_ADMINISTRATOR,
            "knowledge_cutoff": knowledge_cutoff,
            "benchmark_series": [...],
            "benchmark_row_count": N,
            "valid_return_count": V,
            "unavailable_return_count": U
        }
    """
    if symbol != QUALIFIED_BENCHMARK_SYMBOL and symbol != "VN-Index":
        return {
            "status": "unavailable",
            "benchmark_contract_version": BENCHMARK_CONTRACT_VERSION,
            "symbol": symbol,
            "benchmark_name": symbol,
            "administrator": "unknown",
            "knowledge_cutoff": knowledge_cutoff,
            "benchmark_series": [],
            "benchmark_row_count": 0,
            "valid_return_count": 0,
            "unavailable_return_count": 0,
            "reason": "unqualified_benchmark_symbol",
        }

    db_path = runtime_root / DB_RELATIVE
    raw_rows = _query_raw_benchmark_ohlcv(db_path, symbol="VNINDEX")
    citations = _load_benchmark_citations(runtime_root)
    cit_by_date = {c["trading_date"]: c for c in citations if isinstance(c, dict) and "trading_date" in c}

    # Filter raw rows by knowledge_cutoff if provided
    eligible_rows = [
        r for r in raw_rows
        if knowledge_cutoff is None or r["trading_date"] <= knowledge_cutoff
    ]

    if not eligible_rows:
        return {
            "status": "unavailable",
            "benchmark_contract_version": BENCHMARK_CONTRACT_VERSION,
            "symbol": QUALIFIED_BENCHMARK_SYMBOL,
            "benchmark_name": QUALIFIED_BENCHMARK_NAME,
            "administrator": QUALIFIED_BENCHMARK_ADMINISTRATOR,
            "knowledge_cutoff": knowledge_cutoff,
            "benchmark_series": [],
            "benchmark_row_count": 0,
            "valid_return_count": 0,
            "unavailable_return_count": 0,
            "reason": "empty_benchmark_series",
        }

    benchmark_series: list[dict[str, Any]] = []
    valid_count = 0
    unavailable_count = 0

    for idx, curr in enumerate(eligible_rows):
        t_date = curr["trading_date"]
        curr_level = float(curr["raw_index_level"])
        cit = cit_by_date.get(t_date)
        obs_id = cit.get("citation_id") if cit else _hash({"symbol": QUALIFIED_BENCHMARK_SYMBOL, "trading_date": t_date, "raw_index_level": curr_level})

        if idx == 0:
            # First row has no previous session
            row_id = _hash({
                "symbol": QUALIFIED_BENCHMARK_SYMBOL,
                "trading_date": t_date,
                "previous_trading_date": None,
                "raw_index_level": curr_level,
                "knowledge_cutoff": knowledge_cutoff,
                "version": BENCHMARK_CONTRACT_VERSION,
            })

            bmk_row = {
                "benchmark_row_id": row_id,
                "symbol": QUALIFIED_BENCHMARK_SYMBOL,
                "benchmark_name": QUALIFIED_BENCHMARK_NAME,
                "administrator": QUALIFIED_BENCHMARK_ADMINISTRATOR,
                "trading_date": t_date,
                "previous_trading_date": None,
                "current_index_level": curr_level,
                "previous_index_level": None,
                "benchmark_return_type": "simple_benchmark_return",
                "return_value": None,
                "currency": "VND",
                "knowledge_cutoff": knowledge_cutoff,
                "benchmark_observation_id": obs_id,
                "benchmark_contract_version": BENCHMARK_CONTRACT_VERSION,
                "qualification_state": "qualified",
                "unavailable_reason": "no_previous_eligible_session",
            }
            benchmark_series.append(bmk_row)
            unavailable_count += 1
            continue

        prev = eligible_rows[idx - 1]
        prev_t_date = prev["trading_date"]
        prev_level = float(prev["raw_index_level"])

        if prev_level <= 0 or curr_level <= 0:
            row_id = _hash({
                "symbol": QUALIFIED_BENCHMARK_SYMBOL,
                "trading_date": t_date,
                "previous_trading_date": prev_t_date,
                "raw_index_level": curr_level,
                "knowledge_cutoff": knowledge_cutoff,
                "version": BENCHMARK_CONTRACT_VERSION,
            })

            bmk_row = {
                "benchmark_row_id": row_id,
                "symbol": QUALIFIED_BENCHMARK_SYMBOL,
                "benchmark_name": QUALIFIED_BENCHMARK_NAME,
                "administrator": QUALIFIED_BENCHMARK_ADMINISTRATOR,
                "trading_date": t_date,
                "previous_trading_date": prev_t_date,
                "current_index_level": curr_level,
                "previous_index_level": prev_level,
                "benchmark_return_type": "simple_benchmark_return",
                "return_value": None,
                "currency": "VND",
                "knowledge_cutoff": knowledge_cutoff,
                "benchmark_observation_id": obs_id,
                "benchmark_contract_version": BENCHMARK_CONTRACT_VERSION,
                "qualification_state": "qualified",
                "unavailable_reason": "invalid_or_non_positive_index_level",
            }
            benchmark_series.append(bmk_row)
            unavailable_count += 1
            continue

        ret_val = (curr_level / prev_level) - 1.0
        row_id = _hash({
            "symbol": QUALIFIED_BENCHMARK_SYMBOL,
            "trading_date": t_date,
            "previous_trading_date": prev_t_date,
            "raw_index_level": curr_level,
            "knowledge_cutoff": knowledge_cutoff,
            "version": BENCHMARK_CONTRACT_VERSION,
        })

        bmk_row = {
            "benchmark_row_id": row_id,
            "symbol": QUALIFIED_BENCHMARK_SYMBOL,
            "benchmark_name": QUALIFIED_BENCHMARK_NAME,
            "administrator": QUALIFIED_BENCHMARK_ADMINISTRATOR,
            "trading_date": t_date,
            "previous_trading_date": prev_t_date,
            "current_index_level": curr_level,
            "previous_index_level": prev_level,
            "benchmark_return_type": "simple_benchmark_return",
            "return_value": ret_val,
            "currency": "VND",
            "knowledge_cutoff": knowledge_cutoff,
            "benchmark_observation_id": obs_id,
            "benchmark_contract_version": BENCHMARK_CONTRACT_VERSION,
            "qualification_state": "qualified",
            "unavailable_reason": None,
        }
        benchmark_series.append(bmk_row)
        valid_count += 1

    return {
        "status": "available",
        "benchmark_contract_version": BENCHMARK_CONTRACT_VERSION,
        "symbol": QUALIFIED_BENCHMARK_SYMBOL,
        "benchmark_name": QUALIFIED_BENCHMARK_NAME,
        "administrator": QUALIFIED_BENCHMARK_ADMINISTRATOR,
        "knowledge_cutoff": knowledge_cutoff,
        "benchmark_series": benchmark_series,
        "benchmark_row_count": len(benchmark_series),
        "valid_return_count": valid_count,
        "unavailable_return_count": unavailable_count,
    }


def align_vnm_and_benchmark_returns(
    runtime_root: Path,
    ticker: str = "VNM",
    benchmark_symbol: str = QUALIFIED_BENCHMARK_SYMBOL,
    knowledge_cutoff: str | None = None,
    anchor_date: str | None = None,
) -> dict[str, Any]:
    """Perform exact-date session alignment between VNM PIT adjusted returns and Benchmark PIT returns.

    Returns:
        {
            "status": "available" | "unavailable",
            "alignment_contract_version": ALIGNMENT_CONTRACT_VERSION,
            "ticker": ticker,
            "benchmark_symbol": benchmark_symbol,
            "knowledge_cutoff": knowledge_cutoff,
            "anchor_date": anchor_date,
            "aligned_pairs": [...],
            "vnm_return_row_count": N,
            "benchmark_return_row_count": M,
            "aligned_pair_count": P,
            "unmatched_vnm_dates_count": U1,
            "unmatched_benchmark_dates_count": U2
        }
    """
    vnm_res = build_point_in_time_adjusted_returns(
        runtime_root=runtime_root,
        ticker=ticker,
        knowledge_cutoff=knowledge_cutoff,
        anchor_date=anchor_date,
    )

    bmk_res = build_point_in_time_benchmark_returns(
        runtime_root=runtime_root,
        symbol=benchmark_symbol,
        knowledge_cutoff=knowledge_cutoff,
    )

    if vnm_res.get("status") != "available" or bmk_res.get("status") != "available":
        return {
            "status": "unavailable",
            "alignment_contract_version": ALIGNMENT_CONTRACT_VERSION,
            "ticker": ticker,
            "benchmark_symbol": benchmark_symbol,
            "knowledge_cutoff": knowledge_cutoff,
            "anchor_date": anchor_date,
            "aligned_pairs": [],
            "vnm_return_row_count": vnm_res.get("total_row_count", 0),
            "benchmark_return_row_count": bmk_res.get("benchmark_row_count", 0),
            "aligned_pair_count": 0,
            "unmatched_vnm_dates_count": 0,
            "unmatched_benchmark_dates_count": 0,
            "reason": "source_series_unavailable",
        }

    vnm_series = vnm_res.get("return_series", [])
    bmk_series = bmk_res.get("benchmark_series", [])

    bmk_by_date = {b["trading_date"]: b for b in bmk_series}
    vnm_dates = {v["trading_date"] for v in vnm_series}
    bmk_dates = set(bmk_by_date.keys())

    aligned_pairs: list[dict[str, Any]] = []
    unmatched_vnm = 0
    unmatched_bmk = len(bmk_dates - vnm_dates)

    for vnm_row in vnm_series:
        t_date = vnm_row["trading_date"]
        bmk_row = bmk_by_date.get(t_date)

        if not bmk_row:
            unmatched_vnm += 1
            continue

        vnm_ret = vnm_row.get("return_value")
        bmk_ret = bmk_row.get("return_value")

        if vnm_ret is None or bmk_ret is None:
            # Pair emitted with null returns if either row has no valid prior return
            pair_id = _hash({
                "vnm_return_row_id": vnm_row["return_row_id"],
                "benchmark_return_row_id": bmk_row["benchmark_row_id"],
                "trading_date": t_date,
                "knowledge_cutoff": knowledge_cutoff,
                "version": ALIGNMENT_CONTRACT_VERSION,
            })
            pair_obj = {
                "pair_id": pair_id,
                "trading_date": t_date,
                "vnm_return_row_id": vnm_row["return_row_id"],
                "benchmark_return_row_id": bmk_row["benchmark_row_id"],
                "vnm_return_value": vnm_ret,
                "benchmark_return_value": bmk_ret,
                "currency": "VND",
                "knowledge_cutoff": knowledge_cutoff,
                "anchor_date": vnm_res.get("anchor_date"),
                "vnm_lineage": {
                    "applied_factor_ids": vnm_row.get("applied_factor_ids", []),
                    "applied_event_ids": vnm_row.get("applied_event_ids", []),
                    "source_observation_ids": vnm_row.get("source_observation_ids", []),
                },
                "benchmark_lineage": {
                    "benchmark_observation_id": bmk_row.get("benchmark_observation_id"),
                },
                "alignment_contract_version": ALIGNMENT_CONTRACT_VERSION,
                "qualification_state": "qualified",
                "unavailable_reason": vnm_row.get("unavailable_reason") or bmk_row.get("unavailable_reason") or "null_return_value",
            }
            aligned_pairs.append(pair_obj)
            continue

        pair_id = _hash({
            "vnm_return_row_id": vnm_row["return_row_id"],
            "benchmark_return_row_id": bmk_row["benchmark_row_id"],
            "trading_date": t_date,
            "knowledge_cutoff": knowledge_cutoff,
            "version": ALIGNMENT_CONTRACT_VERSION,
        })

        pair_obj = {
            "pair_id": pair_id,
            "trading_date": t_date,
            "vnm_return_row_id": vnm_row["return_row_id"],
            "benchmark_return_row_id": bmk_row["benchmark_row_id"],
            "vnm_return_value": vnm_ret,
            "benchmark_return_value": bmk_ret,
            "currency": "VND",
            "knowledge_cutoff": knowledge_cutoff,
            "anchor_date": vnm_res.get("anchor_date"),
            "vnm_lineage": {
                "applied_factor_ids": vnm_row.get("applied_factor_ids", []),
                "applied_event_ids": vnm_row.get("applied_event_ids", []),
                "source_observation_ids": vnm_row.get("source_observation_ids", []),
            },
            "benchmark_lineage": {
                "benchmark_observation_id": bmk_row.get("benchmark_observation_id"),
            },
            "alignment_contract_version": ALIGNMENT_CONTRACT_VERSION,
            "qualification_state": "qualified",
            "unavailable_reason": None,
        }
        aligned_pairs.append(pair_obj)

    return {
        "status": "available",
        "alignment_contract_version": ALIGNMENT_CONTRACT_VERSION,
        "ticker": ticker,
        "benchmark_symbol": benchmark_symbol,
        "knowledge_cutoff": knowledge_cutoff,
        "anchor_date": vnm_res.get("anchor_date"),
        "aligned_pairs": aligned_pairs,
        "vnm_return_row_count": len(vnm_series),
        "benchmark_return_row_count": len(bmk_series),
        "aligned_pair_count": len(aligned_pairs),
        "unmatched_vnm_dates_count": unmatched_vnm,
        "unmatched_benchmark_dates_count": unmatched_bmk,
    }
