"""Bounded raw KBS annual metadata retention V1 (8 exact foreground requests)."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import argparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atomic_io import atomic_write_json
import canonical_fact_store as store
import provider_financial_source_metadata as metadata
from canonical_financial_facts import build_facts
import provider_financial_semantic_basis as pfsb

OUT = ROOT / "operations-review" / "annual-provider-financial-metadata-retention-and-flow-semantic-corroboration-v1-20260827"
RUNTIME = ROOT.parent / "dashboard-runtime"

def _replay_saved(results):
    sidecars, observations = [], []
    for result in results:
        if result.get("disposition") != "SUCCESS" or not result.get("raw_response_file"):
            continue
        raw = json.loads((OUT / result["raw_response_file"]).read_text(encoding="utf-8"))
        adapter_dir = OUT / "adapter_outputs"; adapter_dir.mkdir(exist_ok=True)
        adapter_path = adapter_dir / f"{result['ticker']}_{result['statement_family']}_year.parquet"
        built = metadata.materialize_lineage_bound_facts(result, raw, adapter_path)
        sidecars.extend(metadata.metadata_rows(result, raw, raw_hash=result["raw_response_sha256"],
                                              adapter_payload_sha256=built["adapter_payload_sha256"]))
        observations.extend(built["observations"])
        result.update({key: value for key, value in built.items() if key != "observations"})
    return sidecars, observations

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", action="store_true", help="rebuild only from retained raw bytes")
    args = parser.parse_args(argv)
    citations = store.load_official_citations(RUNTIME)
    cohort = sorted({key[0] for key in citations})[:4]
    plan = metadata.plan_for_tickers(cohort)
    if len(plan) > 16:
        raise ValueError("request budget exceeded")
    OUT.mkdir(parents=True, exist_ok=True)
    atomic_write_json(OUT / "request_budget.json", {"maximum_requests": 16, "planned_requests": len(plan), "requests": plan})
    prior_path = OUT / "raw_acquisition_dispositions.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.exists() else []
    # The first bounded probe used an incorrect parameter spelling. It is retained as an explicit
    # non-semantic contract-mismatch disposition; corrected requests consume the remaining budget.
    for item in prior:
        raw_file = item.get("raw_response_file")
        raw = json.loads((OUT / raw_file).read_text(encoding="utf-8")) if raw_file else {}
        empty_raw = not raw.get("Head") and not raw.get("Content")
        if item.get("disposition") == "SUCCESS" and item.get("adapter_row_count") == 0 and empty_raw:
            item["disposition"] = "CONTRACT_MISMATCH_EMPTY"
        elif item.get("disposition") == "CONTRACT_MISMATCH_EMPTY" and not empty_raw:
            item["disposition"] = "SUCCESS"
    if args.replay:
        results = list(prior)
        sidecars, observations = _replay_saved(results)
    else:
        results, sidecars, observations = list(prior), [], []
        for request in plan:
            result = metadata.fetch_raw_once(request)
            raw_bytes = result.pop("raw_response_bytes")
            if raw_bytes is not None:
                raw_path = metadata.raw_response_path(OUT, request, result["raw_response_sha256"])
                raw_path.parent.mkdir(exist_ok=True)
                raw_path.write_bytes(raw_bytes)
                result["raw_response_file"] = str(raw_path.relative_to(OUT))
            if result.get("disposition") == "SUCCESS" and result.get("raw_response"):
                adapter_dir = OUT / "adapter_outputs"; adapter_dir.mkdir(exist_ok=True)
                adapter_path = adapter_dir / f"{request['ticker']}_{request['statement_family']}_year.parquet"
                built = metadata.materialize_lineage_bound_facts(result, result["raw_response"], adapter_path)
                rows = metadata.metadata_rows(result, result["raw_response"], raw_hash=result["raw_response_sha256"],
                                              adapter_payload_sha256=built["adapter_payload_sha256"])
                sidecars.extend(rows); observations.extend(built["observations"])
                result.update({key: value for key, value in built.items() if key != "observations"})
            result.pop("raw_response", None)
            results.append(result)
    joined = metadata.join_metadata_exact(observations, sidecars)
    facts_by_ticker = {}
    for ticker in sorted({row["ticker"] for row in observations}):
        group = [row for row in observations if row["ticker"] == ticker]
        facts_by_ticker[ticker] = build_facts(ticker, group, official_citations=citations)["facts"]
    facts = [fact for values in facts_by_ticker.values() for fact in values]
    reconciliation = metadata.reconcile_annual_flow_facts(facts, sidecars, citations)
    # Existing semantic engine receives only comparisons that pass every sidecar semantic gate.
    # Here none do (currency/unit unavailable), so KBS stays metadata-partial rather than gaining
    # an unsupported absolute shape contract from numerical closeness.
    semantic_registry = pfsb.build_semantic_basis_registry({"shapes": {}})
    atomic_write_json(prior_path, results)
    atomic_write_json(OUT / "provider_financial_source_metadata_sidecar.json", sidecars)
    atomic_write_json(OUT / "metadata_lineage_joins.json", joined)
    atomic_write_json(OUT / "annual_metadata_bound_canonical_facts.json", facts)
    atomic_write_json(OUT / "annual_flow_semantic_reconciliation.json", reconciliation)
    atomic_write_json(OUT / "provider_financial_semantic_basis_registry.json", semantic_registry)
    report = {"milestone": "ANNUAL_PROVIDER_FINANCIAL_METADATA_RETENTION_AND_FLOW_SEMANTIC_CORROBORATION_V1",
              "request_budget": 16, "actual_requests": len(results), "cohort": cohort,
              "dispositions": {name: sum(x.get('disposition') == name for x in results) for name in ('SUCCESS','CONTRACT_MISMATCH_EMPTY','HTTP_ERROR','NON_JSON_RESPONSE','TRANSPORT_ERROR')},
              "raw_response_count": sum(x.get('raw_response_sha256') is not None for x in results),
              "metadata_sidecar_rows": len(sidecars), "annual_observations": len(observations),
              "exact_lineage_joins": sum(x['metadata_joined'] for x in joined),
              "annual_canonical_facts": len(facts), "flow_reconciliation_counts": reconciliation["counts"],
              "flow_reconciliation_residual_zero": reconciliation["residual_zero"],
              "semantic_basis_verdict_counts": semantic_registry["verdict_counts"],
              "authority_boundary": {"provider_absolute_promoted": False, "official_promoted": False, "production_database_mutated": False}}
    atomic_write_json(OUT / "metadata_retention_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))

if __name__ == '__main__': main()
