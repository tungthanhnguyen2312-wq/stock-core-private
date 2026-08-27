"""Run the bounded annual retained replay / acquisition evidence recovery V1."""
from __future__ import annotations
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import annual_provider_financial_recovery as annual
import canonical_fact_store as store
import provider_financial_semantic_basis as pfsb
from atomic_io import atomic_write_file, atomic_write_json

DEFAULT_RUNTIME = ROOT.parent / "dashboard-runtime"
DEFAULT_OUTPUT = ROOT / "operations-review" / "annual-provider-financial-history-retention-repair-and-flow-reconciliation-v1-20260827"

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--acquire", action="store_true")
    parser.add_argument("--request-offset", type=int, default=0)
    parser.add_argument("--request-count", type=int)
    args = parser.parse_args(argv)
    citations = store.load_official_citations(args.runtime_root)
    cited_tickers = sorted({key[0] for key in citations})
    plan = annual.request_plan(cited_tickers)
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out / "request_budget.json", {"maximum_requests": len(plan), "requests": plan,
                                                       "rules": "one request per ticker/provider/family; no retry/failover/delay"})
    replay = annual.replay_annual_payloads(ROOT / "data_bctc", official_citations=citations)
    atomic_write_json(out / "retained_annual_replay.json", replay)
    disposition_path = out / "annual_acquisition_dispositions.json"
    acquisition = json.loads(disposition_path.read_text(encoding="utf-8")) if disposition_path.exists() else []
    if args.acquire:
        selected = plan[args.request_offset: args.request_offset + args.request_count
                        if args.request_count is not None else None]
        if args.request_offset < 0 or args.request_count is not None and args.request_count < 1:
            raise SystemExit("request offset/count must select a non-empty bounded plan")
        prior = acquisition
        prior_keys = {(item["ticker"], item["provider"], item["statement_family"]) for item in prior}
        if any((item["ticker"], item["provider"], item["statement_family"]) in prior_keys for item in selected):
            raise SystemExit("refusing duplicate acquisition request")
        acquired = annual.acquire_annual_once(selected)
        target = out / "acquired_adapter_payloads"
        target.mkdir(exist_ok=True)
        for entry in acquired:
            frame = entry.pop("adapter_payload")
            if frame is not None:
                filename = f"{entry['ticker']}_{entry['statement_family']}_year_{entry['provider']}.parquet"
                path = target / filename
                frame.to_parquet(path, index=False)
                entry["adapter_payload_file"] = str(path.relative_to(out))
                entry["adapter_payload_sha256"] = annual.sha256_file(path)
                entry["raw_response_disposition"] = "adapter_returns_dataframe_only_raw_http_bytes_unavailable"
        acquisition = [*prior, *acquired]
        atomic_write_json(disposition_path, acquisition)
    combined_root = out / "combined_annual_payloads"
    combined_root.mkdir(exist_ok=True)
    for path in annual.annual_payload_paths(ROOT / "data_bctc"):
        shutil.copy2(path, combined_root / path.name)
    for entry in acquisition:
        if entry.get("disposition") == "SUCCESS":
            source = out / entry["adapter_payload_file"]
            name = f"{entry['ticker']}_{entry['statement_family']}_year.parquet"
            # The source-specific acquisition copy is versioned; an existing retained historical
            # payload is never replaced.
            frame = __import__("pandas").read_parquet(source)
            # These four identifiers are acquisition-envelope facts, not provider metadata:
            # the unmodified adapter return remains separately retained above.
            for column, value in (("ticker", entry["ticker"]), ("report_type", entry["statement_family"]),
                                  ("source", entry["provider"]), ("scraped_at", None)):
                if column not in frame.columns:
                    frame.insert(0, column, value)
            frame.to_parquet(combined_root / name, index=False)
    materialized = annual.replay_annual_payloads(combined_root, official_citations=citations)
    reconciliation = annual.reconcile_annual_facts(materialized["facts"], citations)
    annual_facts_by_ticker = {}
    for fact in materialized["facts"]:
        annual_facts_by_ticker.setdefault(fact["ticker"], []).append(fact)
    semantic_reconciliation = pfsb.reconcile_official_anchors(annual_facts_by_ticker)
    semantic_registry = pfsb.build_semantic_basis_registry(semantic_reconciliation)
    atomic_write_json(out / "annual_materialization.json", materialized)
    atomic_write_json(out / "annual_official_reconciliation.json", reconciliation)
    atomic_write_json(out / "annual_provider_semantic_basis_registry.json", semantic_registry)
    report = {"milestone": "ANNUAL_PROVIDER_FINANCIAL_HISTORY_RETENTION_REPAIR_AND_FLOW_RECONCILIATION_V1",
              "retained_replay": {key: replay[key] for key in ("payload_count", "annual_observation_count", "annual_canonical_fact_count", "replay_identity")},
              "request_budget": len(plan), "actual_requests": len(acquisition),
              "acquisition_dispositions": {state: sum(x.get("disposition") == state for x in acquisition) for state in ("SUCCESS", "EMPTY", "ERROR")},
              "materialized": {key: materialized[key] for key in ("payload_count", "annual_observation_count", "annual_canonical_fact_count", "replay_identity")},
              "reconciliation_counts": reconciliation["counts"], "reconciliation_residual_zero": reconciliation["residual_zero"],
              "semantic_basis_verdict_counts": semantic_registry["verdict_counts"],
              "semantic_basis_absolute_qualified": semantic_registry["any_shape_absolute_research_qualified"],
              "authority_boundary": {"provider_absolute_semantics_promoted": False, "official_authority_promoted": False,
                                      "valuation_ready_changed": False, "value_activated": False, "production_database_mutated": False}}
    atomic_write_json(out / "annual_recovery_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
