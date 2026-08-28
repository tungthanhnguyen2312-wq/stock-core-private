"""Bounded live proof for the repository-owned KBS quarterly retention contract."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atomic_io import atomic_write_json
from canonical_financial_facts import build_facts
import financial_flow_semantics_ttm_bridge as bridge
import kbs_quarterly_financial_retention as kbs
import provider_financial_source_metadata as source
from raw_financial_observations import extract_payload, sha256_file

DEFAULT_OUTPUT = ROOT / "operations-review/kbs-quarterly-financial-lookback-and-semantic-retention-v1-20260828"


def _enriched_observations(request: dict, raw: dict, metadata: list[dict], output: Path) -> tuple[list[dict], str]:
    frame = source.adapter_dataframe_from_raw(request, raw)
    frame.insert(0, "ticker", request["ticker"])
    frame.insert(1, "report_type", "income_statement")
    frame.insert(2, "source", "KBS")
    frame.insert(3, "scraped_at", request.get("retrieved_at"))
    path = output / "adapter_outputs" / f"{request['ticker']}_page{request['params']['page']}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    payload_hash = sha256_file(path)
    observations = extract_payload(frame, ticker=request["ticker"], statement_family="income_statement",
                                   reporting_frequency="quarter", source_file=path.name, source_sha256=payload_hash)["observations"]
    meta_by_period: dict[str, list[dict]] = defaultdict(list)
    for row in metadata:
        meta_by_period[row["reporting_period"]].append(row)
    for values in meta_by_period.values():
        values.sort(key=lambda row: row["period_variant_index"])
    for observation in observations:
        candidates = meta_by_period.get(observation["reporting_period"], [])
        index = int(observation.get("period_variant_index", 0))
        sidecar = candidates[index] if index < len(candidates) else None
        if sidecar is None:
            continue
        observation.update({
            "flow_period_basis": sidecar["flow_period_basis"],
            "flow_period_basis_evidence": sidecar["flow_period_basis_evidence"],
            "period_start": sidecar["period_start"], "period_end": sidecar["period_end"],
            "duration_months": sidecar["duration_months"], "statement_scope": sidecar["statement_scope"],
            "raw_currency": sidecar["currency"] if sidecar["currency"] != "UNKNOWN" else None,
            "raw_scale": sidecar["unit_scale_factor"], "kbs_metadata_identity": sidecar["metadata_identity"],
        })
    return observations, payload_hash


def _enrich_facts(facts: list[dict], metadata: list[dict]) -> list[dict]:
    by_period: dict[str, list[dict]] = defaultdict(list)
    for row in metadata:
        by_period[row["reporting_period"]].append(row)
    for values in by_period.values():
        values.sort(key=lambda row: row["period_variant_index"])
    result = []
    for fact in facts:
        if fact.get("statement_family") != "income_statement":
            continue
        candidates = by_period.get(str(fact.get("reporting_period")), [])
        sidecar = candidates[0] if candidates else None
        if sidecar is not None:
            fact = dict(fact)
            fact.update({"flow_period_basis": sidecar["flow_period_basis"],
                         "flow_period_basis_evidence": sidecar["flow_period_basis_evidence"],
                         "period_start": sidecar["period_start"], "period_end": sidecar["period_end"],
                         "duration_months": sidecar["duration_months"],
                         "statement_scope": sidecar["statement_scope"],
                         "currency": sidecar["currency"].lower() if sidecar["currency"] != "UNKNOWN" else "unknown",
                         "scale": sidecar["unit_scale_factor"], "unit_scale_factor": sidecar["unit_scale_factor"],
                         "normalization_method": sidecar["normalization_method"],
                         "metadata_identity": sidecar["metadata_identity"]})
        result.append(fact)
    return result


def execute(*, output: Path = DEFAULT_OUTPUT, live: bool = True) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    plan = kbs.plan_for_tickers(kbs.PROOF_TICKERS)
    if len(plan) != 10:
        raise ValueError("PROOF_REQUEST_BUDGET_MISMATCH")
    results, all_metadata, all_observations, facts_by_ticker = [], [], [], defaultdict(list)
    network_calls, replayed_retained_raw = 0, 0
    for request in plan:
        retained = sorted((output / "raw").glob(f"{request['ticker']}_page{request['params']['page']}_*.json")) if (output / "raw").exists() else []
        if retained:
            if len(retained) != 1:
                raise ValueError("AMBIGUOUS_RETAINED_RAW_RESPONSE")
            body = retained[0].read_bytes()
            raw = json.loads(body.decode("utf-8"))
            result = {**request, "disposition": "SUCCESS", "http_status": 200,
                      "raw_response_sha256": source._hash_bytes(body), "raw_response_file": str(retained[0].relative_to(output)),
                      "retrieved_at": None, "replayed_retained_raw": True}
            raw_bytes = None
            replayed_retained_raw += 1
        else:
            result = kbs.fetch_raw_once(request) if live else {**request, "disposition": "REPLAY_REQUIRES_RETAINED_RAW"}
            network_calls += int(live)
            raw_bytes = result.pop("raw_response_bytes", None)
            raw = result.pop("raw_response", None)
        if raw_bytes is not None:
            raw_hash = result["raw_response_sha256"]
            path = output / "raw" / f"{request['ticker']}_page{request['params']['page']}_{raw_hash}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw_bytes)
            result["raw_response_file"] = str(path.relative_to(output))
        if result.get("disposition") == "SUCCESS" and isinstance(raw, dict):
            retained_request = {**request, "retrieved_at": result.get("retrieved_at")}
            metadata = kbs.metadata_rows(retained_request, raw, raw_hash=result["raw_response_sha256"])
            observations, payload_hash = _enriched_observations(retained_request, raw, metadata, output)
            result.update({"metadata_row_count": len(metadata), "observation_count": len(observations),
                           "adapter_payload_sha256": payload_hash})
            all_metadata.extend(metadata); all_observations.extend(observations)
        results.append(result)
    variants = kbs.classify_period_variants(all_metadata)
    value_variants = kbs.reconcile_value_variants(all_observations)
    for ticker in kbs.PROOF_TICKERS:
        observations = [row for row in all_observations if row["ticker"] == ticker]
        facts_by_ticker[ticker] = _enrich_facts(build_facts(ticker, observations)["facts"],
                                                 [row for row in all_metadata if row["ticker"] == ticker])
    ttm = bridge.build_artifact(tickers=kbs.PROOF_TICKERS, facts_by_ticker=facts_by_ticker,
                                entity_type_by_ticker={ticker: "corporate" for ticker in kbs.PROOF_TICKERS},
                                requested_at="2026-08-28T00:00:00+07:00")
    report = {"contract_version": kbs.CONTRACT_VERSION,
              "milestone": "KBS_QUARTERLY_FINANCIAL_LOOKBACK_AND_SEMANTIC_RETENTION_V1",
              "request_plan": plan, "network_calls_this_execution": network_calls,
              "replayed_retained_raw_count": replayed_retained_raw,
              "bounded_live_proof_network_calls_total": (network_calls + replayed_retained_raw) if live or replayed_retained_raw else 0,
              "acquisition_dispositions": {name: sum(row.get("disposition") == name for row in results)
                                              for name in ("SUCCESS", "HTTP_ERROR", "NON_JSON_RESPONSE", "TRANSPORT_ERROR")},
              "requests": results, "coverage": kbs.coverage(all_metadata, variants),
              "period_variants": variants, "value_variant_dispositions": value_variants,
              "metadata": all_metadata, "ttm_integration": {"coverage": ttm["coverage"], "records": ttm["records"]},
              "authority_boundary": {"provider_research_only": True, "authoritative_evidence_promoted": False,
                                     "production_database_mutated": False, "dashboard_mutated": False,
                                     "pit_or_valuation_authority_promoted": False}}
    report["artifact_sha256"] = kbs.identity(report)
    report["artifact_identity"] = f"{kbs.CONTRACT_VERSION}:{report['artifact_sha256']}"
    atomic_write_json(output / "artifact.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    report = execute(output=args.output, live=not args.replay)
    print(json.dumps({"coverage": report["coverage"], "ttm": report["ttm_integration"]["coverage"],
                      "network_calls_this_execution": report["network_calls_this_execution"],
                      "bounded_live_proof_network_calls_total": report["bounded_live_proof_network_calls_total"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
