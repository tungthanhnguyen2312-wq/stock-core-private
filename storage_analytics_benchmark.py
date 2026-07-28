"""Bounded read-only SQLite/Pandas versus DuckDB/Parquet benchmark for Phase 3D."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import statistics
import time
import tracemalloc
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from shadow_analytics_pilot import TICKERS, _evidence_records, _financial_records, require_duckdb, semantic_fingerprint


class BenchmarkError(RuntimeError):
    pass


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.to_json(orient="records", date_format="iso", double_precision=15))


def _duck_rows(connection, sql: str) -> list[dict[str, Any]]:
    cursor = connection.execute(sql)
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _sample(query: Callable[[], list[dict[str, Any]]]) -> dict[str, Any]:
    tracemalloc.start()
    started = time.perf_counter_ns()
    rows = query()
    elapsed = time.perf_counter_ns() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    payload = json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    return {"rows": rows, "fingerprint": semantic_fingerprint(rows), "elapsed_ms": elapsed / 1_000_000, "peak_python_bytes": peak, "output_bytes": len(payload)}


def _measure_pair(name: str, sqlite_query: Callable[[], list[dict[str, Any]]], duck_query: Callable[[], list[dict[str, Any]]]) -> dict[str, Any]:
    """One warm-up and exactly two measured executions per backend/query."""
    warm_sqlite, warm_duck = _sample(sqlite_query), _sample(duck_query)
    if warm_sqlite["fingerprint"] != warm_duck["fingerprint"]:
        raise BenchmarkError(f"{name} semantic parity failed during warm-up")
    sqlite_runs, duck_runs = [], []
    for _ in range(2):
        left, right = _sample(sqlite_query), _sample(duck_query)
        if left["fingerprint"] != right["fingerprint"] or left["fingerprint"] != warm_sqlite["fingerprint"]:
            raise BenchmarkError(f"{name} semantic parity/determinism failed")
        sqlite_runs.append(left); duck_runs.append(right)
    def summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
        return {"runs": len(runs), "median_elapsed_ms": statistics.median(row["elapsed_ms"] for row in runs),
                "peak_python_bytes": max(row["peak_python_bytes"] for row in runs), "output_bytes": runs[0]["output_bytes"],
                "rows": len(runs[0]["rows"]), "semantic_fingerprint": runs[0]["fingerprint"]}
    return {"parity": "pass", "sqlite_pandas": summary(sqlite_runs), "duckdb_parquet": summary(duck_runs)}


def run_benchmark(*, runtime_root: Path, lake_root: Path, output_path: Path) -> dict[str, Any]:
    runtime_root, lake_root = runtime_root.resolve(), lake_root.resolve()
    db = runtime_root / "vn_stock.db"
    if not db.is_file() or not (lake_root / "ohlcv").is_dir():
        raise BenchmarkError("required read-only authority or Phase 3A lake is missing")
    before = {name: _hash(runtime_root / name) for name in ("vn_stock.db", "financial_snapshot.parquet")}
    sqlite_connection = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    duckdb = require_duckdb(); duck = duckdb.connect(":memory:")
    marks = ",".join("?" for _ in TICKERS)
    try:
        latest_date = sqlite_connection.execute(f"SELECT MAX(date) FROM ohlcv WHERE ticker IN ({marks})", TICKERS).fetchone()[0]
        cutoff = "2024-12-31"
        financial, _ = _financial_records(runtime_root, TICKERS)
        evidence = _evidence_records(runtime_root, TICKERS)
        financial_frame, evidence_frame = pd.DataFrame(financial), pd.DataFrame(evidence)
        ohlcv_glob = (lake_root / "ohlcv" / "ticker=*" / "data.parquet").as_posix()
        financial_glob = (lake_root / "financial_metrics" / "ticker=*" / "data.parquet").as_posix()
        evidence_glob = (lake_root / "evidence_identities" / "ticker=*" / "data.parquet").as_posix()

        def sql_frame(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
            return _rows(pd.read_sql_query(query, sqlite_connection, params=params))
        queries: dict[str, tuple[Callable[[], list[dict[str, Any]]], Callable[[], list[dict[str, Any]]]]] = {
            "single_ticker_ohlcv_history": (
                lambda: sql_frame("SELECT ticker,date,open,high,low,close,volume,source FROM ohlcv WHERE ticker=? ORDER BY date", ("HPG",)),
                lambda: _duck_rows(duck, f"SELECT ticker,date,open,high,low,close,volume,source FROM read_parquet('{ohlcv_glob}') WHERE ticker='HPG' ORDER BY date")),
            "three_ticker_latest_date_slice": (
                lambda: sql_frame(f"SELECT ticker,date,close,volume,source FROM ohlcv WHERE ticker IN ({marks}) AND date=? ORDER BY ticker", TICKERS + (latest_date,)),
                lambda: _duck_rows(duck, f"SELECT ticker,date,close,volume,source FROM read_parquet('{ohlcv_glob}') WHERE date='{latest_date}' ORDER BY ticker")),
            "historical_price_lookup": (
                lambda: sql_frame(f"SELECT a.ticker,a.date,a.close,a.source FROM ohlcv a WHERE a.ticker IN ({marks}) AND a.date<=? AND a.date=(SELECT MAX(b.date) FROM ohlcv b WHERE b.ticker=a.ticker AND b.date<=?) ORDER BY a.ticker", TICKERS + (cutoff, cutoff)),
                lambda: _duck_rows(duck, f"SELECT ticker,date,close,source FROM read_parquet('{ohlcv_glob}') WHERE date<='{cutoff}' QUALIFY row_number() OVER (PARTITION BY ticker ORDER BY date DESC)=1 ORDER BY ticker")),
            "financial_evidence_lineage_join": (
                lambda: _rows(financial_frame.merge(evidence_frame, on=["ticker", "citation_id"], suffixes=("_financial", "_evidence"))[["ticker", "canonical_metric", "value_financial", "period_financial", "statement_scope", "citation_id", "document_hash", "evidence_id_financial"]].sort_values(["ticker", "canonical_metric", "citation_id"])),
                lambda: _duck_rows(duck, f"SELECT f.ticker,f.canonical_metric,f.value AS value_financial,f.period AS period_financial,f.statement_scope,f.citation_id,e.document_hash,f.evidence_id AS evidence_id_financial FROM read_parquet('{financial_glob}') f JOIN read_parquet('{evidence_glob}') e USING(ticker,citation_id) ORDER BY f.ticker,f.canonical_metric,f.citation_id")),
            "representative_analytical_scan": (
                lambda: sql_frame(f"SELECT ticker,COUNT(*) AS rows,MIN(date) AS first_date,MAX(date) AS last_date,AVG(close) AS avg_close,MAX(high) AS max_high FROM ohlcv WHERE ticker IN ({marks}) GROUP BY ticker ORDER BY ticker", TICKERS),
                lambda: _duck_rows(duck, f"SELECT ticker,COUNT(*) AS rows,MIN(date) AS first_date,MAX(date) AS last_date,AVG(close) AS avg_close,MAX(high) AS max_high FROM read_parquet('{ohlcv_glob}') GROUP BY ticker ORDER BY ticker")),
        }
        results = {name: _measure_pair(name, *pair) for name, pair in queries.items()}
    finally:
        duck.close(); sqlite_connection.close()
    after = {name: _hash(runtime_root / name) for name in before}
    if before != after:
        raise BenchmarkError("production authority changed during benchmark")
    report = {"status": "pass", "scope": list(TICKERS), "warmups_per_backend_query": 1, "measured_runs_per_backend_query": 2,
              "measurement": "elapsed wall time and Python allocation peak; native engine allocations are not estimated", "results": results,
              "production_unchanged": True, "authority": "SQLite/JSONL remains read-only authority"}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run bounded Phase 3D storage benchmark")
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--lake-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run_benchmark(runtime_root=args.runtime_root, lake_root=args.lake_root, output_path=args.output)
    except BenchmarkError as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)})); return 2
    print(json.dumps({"status": report["status"], "output": str(args.output)})); return 0

if __name__ == "__main__":
    raise SystemExit(main())
