"""Compare two isolated retained-session rebuilds; output counts and identities only."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

FIELDS = (
    "research_action_posture", "decision_identity", "evidence_currency",
    "fundamental_state", "financial_composite_context", "valuation_methods",
    "valuation_context_summary", "evidence_axes", "source_identities",
)
METHODS = ("P/B", "P/E", "P/S", "EV/EBITDA")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(baseline: Path, after: Path, producer: Path) -> dict:
    before_output, after_output = baseline / "outputs", after / "outputs"
    before = _load(before_output / "integrated_investment_decision_product.json")
    current = _load(after_output / "integrated_investment_decision_product.json")
    before_records, after_records = before["records"], current["records"]
    tickers = sorted(set(before_records) | set(after_records))
    changes = {field: [] for field in FIELDS}
    for ticker in tickers:
        old, new = before_records.get(ticker, {}), after_records.get(ticker, {})
        for field in FIELDS:
            if old.get(field) != new.get(field):
                changes[field].append(ticker)
    before_run = _load(before_output / "assembly_result.json")
    after_run = _load(after_output / "assembly_result.json")
    feature_candidates = list((producer / "operations-review/daily-research-session-operations-v1/2026-09-28").glob(
        "*/market_wide_fundamental_feature_store_artifact.json"))
    if len(feature_candidates) != 1:
        raise ValueError(f"EXPECTED_ONE_PINNED_FEATURE_STORE:{len(feature_candidates)}")
    feature = _load(feature_candidates[0])
    semantics = _load(producer / "operations-review/market-wide-structured-financial-period-semantics-v1-20260905"
                      / "structured_financial_period_semantics_artifact.json")
    raw_valuation = _load(producer / "operations-review/market-wide-current-valuation-v1-20260928-session20260928"
                          / "market_wide_current_valuation_artifact.json")
    official = [v["financial_input"] for v in raw_valuation["records"].values()
                if v["financial_input"].get("authority") == "OFFICIAL_QUALIFIED"]
    methods = raw_valuation["coverage"]["metric_research_usable_counts"]
    bytes_equal = {}
    for filename in ("integrated_investment_decision_product.json", "financial_analysis_product.json",
                     "operational_fundamental_context_integration.json", "current_research_entity_applicability.json"):
        bytes_equal[filename] = _sha(before_output / filename) == _sha(after_output / filename)
    inputs_equal = (before_run["staged_session_inputs"] == after_run["staged_session_inputs"])
    network_zero = all(run["provider_calls"] == 0 and run["retired_provider_imports"] == 0
                       and run["vnstock_worker_processes"] == 0 and not run["write_guard"]["violations"]
                       for run in (before_run, after_run))

    def _coverage(records):
        return {
            "financial_v2_governed_records": len(_load(before_output / "financial_analysis_product.json")["records"]),
            "financial_v2_compact_coverage": _load(before_output / "financial_analysis_product.json")["coverage"]["compact_coverage"],
            "feature_store_governed_tickers": feature["coverage"]["ticker_denominator"],
            "tickers_with_ready_feature": feature["coverage"]["tickers_with_ready_feature"],
            "ready_research_proxy_feature_count": feature["coverage"]["feature_status_distribution"]["READY_RESEARCH_PROXY"],
            "kbs_retained_facts": semantics["coverage"]["provider_distribution"]["KBS"],
            "vci_retained_facts": semantics["coverage"]["provider_distribution"]["VCI"],
            "official_qualified_valuation_input_tickers": len(official),
            "official_qualified_valuation_metric_inputs": sum(v.get("metric_count", 0) for v in official),
            "current_method_research_usable": {name: methods[name] for name in METHODS},
            "fundamental_state_distribution": dict(Counter(v.get("fundamental_state") for v in records.values())),
            "research_action_posture_distribution": dict(Counter(v.get("research_action_posture") for v in records.values())),
        }

    result = {
        "contract_version": "zero_active_vnstock_retained_acceptance/v1",
        "session": "2026-09-28", "governed_denominator": len(tickers),
        "baseline_integrated_identity": before["artifact_identity"],
        "after_integrated_identity": current["artifact_identity"],
        "per_ticker_changes": {key: value for key, value in changes.items() if value},
        "byte_equal_products": bytes_equal,
        "staged_inputs_identical": inputs_equal,
        "no_provider_import_network_or_worker": network_zero,
        "before_coverage": _coverage(before_records), "after_coverage": _coverage(after_records),
    }
    result["verdict"] = "PASS" if (len(tickers) == 1683 and not result["per_ticker_changes"]
                                   and all(bytes_equal.values()) and inputs_equal and network_zero) else "FAIL"
    body = dict(result)
    result["content_identity"] = "zero_active_vnstock_retained_acceptance/v1:" + hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--after-root", type=Path, required=True)
    parser.add_argument("--producer-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.baseline_root, args.after_root, args.producer_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": result["verdict"], "content_identity": result["content_identity"],
                      "denominator": result["governed_denominator"]}, sort_keys=True))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
