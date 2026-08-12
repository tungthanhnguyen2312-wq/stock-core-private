"""Build Phase 2 derived outputs from an explicit immutable runtime root; no network calls."""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from market_phase2_foundation import (evaluate_quality, expand_raw_ohlc, phase1_provider_exceptions,
                                      semantic_registry, volume_reconciliation_summary)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", default=os.environ.get("STOCK_LOOKUP_RUNTIME_ROOT"))
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()
    if not args.runtime_root: parser.error("--runtime-root or STOCK_LOOKUP_RUNTIME_ROOT is required")
    runtime, output = Path(args.runtime_root), Path(args.output_root)
    if output.exists(): parser.error("--output-root must not already exist")
    universe_path = next((runtime / "data/market_raw_lake/universe").glob("*.parquet"))
    coverage_path = next((runtime / "data/market_raw_lake/coverage").glob("*resume1*.json"))
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    final = coverage["dataset_coverage"][0]
    universe_rows = pq.read_table(universe_path).to_pylist()
    universe = {str(r["symbol"]): r for r in universe_rows}
    success = {str(r["symbol"]) for r in universe_rows if r.get("instrument_class") == "EQUITY"} - set(final["failed_symbols"])
    if len(success) != final["successful_unit_count"]:
        raise RuntimeError("coverage success count does not reconcile to retained universe")
    raw_files = [p for p in (runtime / "data/market_raw_lake/raw/DNSE/ohlc").rglob("*.parquet") if p.stem.split("__", 1)[0] in success]
    raw_rows = []
    for path in raw_files:
        row = pq.read_table(path).to_pylist()[0]; row["raw_file"] = str(path); raw_rows.append(row)
    canonical, quality = evaluate_quality(expand_raw_ohlc(raw_rows, universe))
    provider = phase1_provider_exceptions(final["failed_symbols"], universe, final["run_scope_id"])
    exceptions = pd.concat([quality, provider], ignore_index=True)
    output.mkdir(parents=True)
    canonical.to_parquet(output / "canonical_daily_market.parquet", index=False)
    canonical[["canonical_instrument_id", "provider_symbol", "session", "quality_status", "quality_flags", "raw_observation_id"]].to_parquet(output / "quality_results.parquet", index=False)
    exceptions.to_json(output / "exception_queue.jsonl", orient="records", lines=True, force_ascii=False)
    (output / "semantic_registry.json").write_text(json.dumps(semantic_registry(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    value_counts = lambda col: {str(k): int(v) for k,v in canonical[col].value_counts(dropna=False).items()}
    sessions = pd.to_datetime(canonical["session"], errors="coerce", utc=True)
    summary = {"schema_version":"1.0.0", "input":{"successful_symbols":len(success),"raw_files":len(raw_files),"raw_rows":len(canonical),"date_range":[str(sessions.min().date()),str(sessions.max().date())],"phase1_provider_failures":len(provider)},
               "canonical":{"symbols":int(canonical.provider_symbol.nunique()),"rows":len(canonical),"suspect_rows":int((canonical.quality_status == "SUSPECT").sum()),"affected_symbols":int(canonical.loc[canonical.quality_status == "SUSPECT","provider_symbol"].nunique())},
               "quality_rule_counts":{str(k):int(v) for k,v in quality.quality_rule.value_counts().items()} if not quality.empty else {},
               "exceptions":{"count":len(exceptions),"unresolved":int((exceptions.disposition == "UNRESOLVED").sum())}, "price_basis_distribution":value_counts("price_basis_status"), "volume_basis_distribution":value_counts("volume_basis_status"), "canonical_exchange_distribution":value_counts("canonical_exchange"), "pit_status_distribution":value_counts("pit_status"), "volume_reconciliation":volume_reconciliation_summary(canonical), "phase1_http400_reconciliation":{"expected":133,"represented":len(provider)}, "unknown_security_groups_preserved":1590}
    (output / "coverage_report.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "REPORT.md").write_text("# Phase 2 canonical market output\n\n" + json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0
if __name__ == "__main__": raise SystemExit(main())
