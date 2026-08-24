"""Inventory retained stores and issue the matched-value existing-store verdict; no network I/O."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
sys.path.insert(0, str(ROOT))

from historical_matched_value_existing_store_requalification import build_artifact, inventory_record

RAW_ORIGINAL = WORKSPACE / "operations-review" / "dnse-market-wide-trades-multi-session-v1-20260812"
RAW_REPAIR = WORKSPACE / "operations-review" / "dnse-trades-targeted-repair-live-v1-20260815"
TASK160 = WORKSPACE / "operations-review" / "task-160-canonical-materialization-v1-20260817" / "shadow" / "canonical" / "provider=DNSE" / "dataset=trades_history"
SHADOW21 = WORKSPACE / "operations-review" / "trades-canonical-columnar-shadow-v1-20260813" / "canonical" / "provider=DNSE" / "dataset=trades_history"
DAILY = [
    WORKSPACE / "operations-review" / "dnse-phase2-canonical-20260812" / "canonical_daily_market.parquet",
    WORKSPACE / "operations-review" / "dnse-phase2-canonical-price-basis-20260812" / "canonical_daily_market.parquet",
]
PRIOR = ROOT / "operations-review" / "historical-matched-value-existing-store-requalification-v1-20260824" / "prior-contract-replay" / "historical_matched_traded_value_authority_artifact.json"
DEFAULT_OUTPUT = ROOT / "operations-review" / "historical-matched-value-existing-store-requalification-v1-20260824" / "existing_store_requalification_artifact.json"


def _parquet_columns(path: Path) -> list[str]:
    return pq.ParquetFile(path).schema_arrow.names


def _files(root: Path) -> list[Path]:
    return list(root.rglob("*.parquet"))


def _valid_parquet_files(paths: list[Path]) -> tuple[list[Path], list[Path]]:
    valid, invalid = [], []
    for path in paths:
        try:
            pq.ParquetFile(path).schema_arrow
        except Exception:  # a physical .parquet suffix is not a schema contract
            invalid.append(path)
        else:
            valid.append(path)
    return valid, invalid


def _database(path: Path) -> dict:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    tables = [row[0] for row in connection.execute("select name from sqlite_master where type='table' order by name")]
    ohlcv_columns = [row[1] for row in connection.execute("pragma table_info([ohlcv])")] if "ohlcv" in tables else []
    ohlcv_count = connection.execute("select count(*) from [ohlcv]").fetchone()[0] if "ohlcv" in tables else 0
    connection.close()
    return {"path": str(path), "tables": tables, "ohlcv_row_count": ohlcv_count,
            "ohlcv_columns": ohlcv_columns, "explicit_value_field": False,
            "classification": "OHLCV_ONLY" if ohlcv_columns else "NO_RELEVANT_MARKET_HISTORY"}


def run(output: Path) -> dict:
    original, repair = _files(RAW_ORIGINAL), _files(RAW_REPAIR)
    task160, shadow21_physical = _files(TASK160), _files(SHADOW21)
    shadow21, shadow21_invalid = _valid_parquet_files(shadow21_physical)
    raw_sample = next(path for path in repair if path.name.startswith("HPG__"))
    raw_payload = json.loads(pq.ParquetFile(raw_sample).read_row_group(0, columns=["raw_payload_json"]).column(0)[0].as_py())
    raw_fields = set(raw_payload["trades"][0])
    inventories = [
        inventory_record(dataset="DNSE_RAW_TRADES_ORIGINAL_40_SESSION", file_count=len(original), bytes_count=sum(p.stat().st_size for p in original), columns=raw_fields, source_kind="RAW_PAGE_ENVELOPE", semantic_note="raw Parquet envelope stores these inspected payload trade keys; grossTradeAmount remains unresolved"),
        inventory_record(dataset="DNSE_RAW_TRADES_TARGETED_REPAIR", file_count=len(repair), bytes_count=sum(p.stat().st_size for p in repair), columns=raw_fields, source_kind="RAW_PAGE_ENVELOPE", semantic_note="raw Parquet envelope stores these inspected payload trade keys; grossTradeAmount remains unresolved"),
        inventory_record(dataset="DNSE_CANONICAL_TRADES_40_SESSION", file_count=len(task160), bytes_count=sum(p.stat().st_size for p in task160), columns=_parquet_columns(task160[0]), source_kind="CANONICAL_EXECUTION", semantic_note="price/quantity/board only; no value field"),
        inventory_record(dataset="DNSE_CANONICAL_TRADES_21_SESSION_SHADOW", file_count=len(shadow21_physical), bytes_count=sum(p.stat().st_size for p in shadow21_physical), columns=_parquet_columns(shadow21[0]), source_kind="CANONICAL_EXECUTION", semantic_note=f"{len(shadow21)} valid partitions and {len(shadow21_invalid)} invalid physical .parquet files; valid subset has price/quantity/board only; no value field"),
    ]
    for path in DAILY:
        inventories.append(inventory_record(dataset=path.parent.name, file_count=1, bytes_count=path.stat().st_size, columns=_parquet_columns(path), source_kind="DAILY_CANONICAL", semantic_note="OHLCV only; volume semantic remains UNKNOWN"))
    databases = [_database(path) for path in [ROOT / "vn_stock.db", ROOT / "operations-review" / "p1f-milestone-20260803" / "shadow-build-a" / "vn_stock.db", ROOT / "operations-review" / "p1f-milestone-20260803" / "shadow-build-b" / "vn_stock.db", ROOT / "operations-review" / "p1_current_freshness_20260802T131500+0700" / "shadow_runtime" / "vn_stock.db"]]
    artifact = build_artifact(inventories=inventories, database_inventory=databases, prior=json.loads(PRIOR.read_text(encoding="utf-8")), raw_counter_fields=raw_fields)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--twice", action="store_true")
    args = parser.parse_args(argv)
    first = run(args.output)
    if args.twice and run(args.output)["artifact_identity"] != first["artifact_identity"]:
        return 1
    print(json.dumps({"artifact_identity": first["artifact_identity"], "authority_result": first["authority_result"], "qualified": first["qualified_matched_value"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
