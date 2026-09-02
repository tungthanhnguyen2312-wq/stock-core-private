"""Publish read-only validation artifacts for QUALIFIED_FREE_CASH_FLOW_RESEARCH_PROXY_V1.

This is intentionally a post-processor over a Financial V2 replay artifact.  It
never acquires provider data, rebuilds either persisted financial store, or emits
raw financial values.  The only runtime access is the standard read-only state
reader used to record the provenance of the replay.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atomic_io import atomic_write_file, atomic_write_json  # noqa: E402
import canonical_fact_store as canonical_store  # noqa: E402
import financial_analysis_engine_v2 as engine  # noqa: E402
import raw_financial_store  # noqa: E402
from financial_analysis_product_projection import build_product_projection  # noqa: E402


MILESTONE = "QUALIFIED_FREE_CASH_FLOW_RESEARCH_PROXY_V1"
PROXY = "free_cash_flow_proxy"
DIRECTION = "free_cash_flow_proxy_direction"
DIRECTION_STATE = "free_cash_flow_proxy_direction_state"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("REPLAY_INPUT_NOT_OBJECT")
    return value


def _feature_store_tickers(path: Path) -> list[str]:
    tickers: list[str] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            ticker = str(item.get("ticker") or "").strip().upper()
            if not ticker or ticker in tickers:
                raise ValueError("FEATURE_STORE_TICKER_INVALID_OR_DUPLICATE")
            tickers.append(ticker)
    return sorted(tickers)


def _identity_ok(artifact: Mapping[str, Any]) -> bool:
    expected = engine.content_identity(artifact)
    return artifact.get("artifact_sha256") == expected["artifact_sha256"]


def build(*, replay: Mapping[str, Any], baseline: Mapping[str, Any], tickers: list[str], runtime_root: Path,
          requested_at: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    if replay.get("contract_version") != engine.CONTRACT_VERSION or not _identity_ok(replay):
        raise ValueError("FINANCIAL_V2_REPLAY_IDENTITY_INVALID")
    if baseline.get("contract_version") != engine.CONTRACT_VERSION or not _identity_ok(baseline):
        raise ValueError("FINANCIAL_V2_BASELINE_IDENTITY_INVALID")
    records = replay.get("records")
    baseline_records = baseline.get("records")
    if not isinstance(records, Mapping) or not isinstance(baseline_records, Mapping):
        raise ValueError("FINANCIAL_V2_RECORDS_INVALID")
    if set(records) != set(tickers) or len(records) != len(tickers):
        raise ValueError("REPLAY_TICKER_DENOMINATOR_MISMATCH")

    product = build_product_projection(financial_context=replay, product_tickers=tickers, requested_at=requested_at)
    statuses = Counter()
    methods = Counter()
    direction_statuses = Counter()
    direction_states = Counter()
    for record in records.values():
        features = record.get("features") or {}
        proxy = features.get(PROXY) or {}
        direction = features.get(DIRECTION) or {}
        statuses[str(proxy.get("fitness"))] += 1
        methods[str(proxy.get("method"))] += 1
        direction_statuses[str(direction.get("fitness"))] += 1
        direction_states[str((record.get("states") or {}).get(DIRECTION_STATE))] += 1

    ready_changed = sorted(ticker for ticker in tickers
                           if bool((records[ticker] or {}).get("current_research_ready"))
                           != bool((baseline_records.get(ticker) or {}).get("current_research_ready")))
    compact_proxy_value_exposed = any("value" in ((record.get(PROXY) or {}))
                                      for record in (product.get("records") or {}).values()
                                      if record.get("status") == "AVAILABLE")
    coverage = {
        "milestone": MILESTONE,
        "replay_artifact_identity": replay.get("artifact_identity"),
        "ticker_denominator": len(tickers),
        "ticker_record_count": len(records),
        "zero_silent_ticker_drops": len(tickers) == len(records),
        "free_cash_flow_proxy_status": dict(sorted(statuses.items())),
        "free_cash_flow_proxy_method": dict(sorted(methods.items())),
        "free_cash_flow_proxy_direction_status": dict(sorted(direction_statuses.items())),
        "free_cash_flow_proxy_direction_state": dict(sorted(direction_states.items())),
        "current_research_ready_count": (replay.get("coverage") or {}).get("current_research_ready_count"),
        "baseline_current_research_ready_count": (baseline.get("coverage") or {}).get("current_research_ready_count"),
    }
    validation = {
        "milestone": MILESTONE,
        "requested_at": requested_at,
        "source_provenance": {
            "runtime_root": str(runtime_root),
            "raw_store_state": raw_financial_store.inspect_state(runtime_root),
            "canonical_store_schema_version": (canonical_store._load_state(runtime_root) or {}).get("schema_version"),
            "canonical_ticker_count": len((canonical_store._load_state(runtime_root) or {}).get("tickers") or []),
            "financial_v2_source_identities": replay.get("source_identities"),
            "baseline_artifact_identity": baseline.get("artifact_identity"),
        },
        "checks": {
            "financial_v2_identity_valid": True,
            "baseline_identity_valid": True,
            "zero_silent_ticker_drops": coverage["zero_silent_ticker_drops"],
            "current_research_ready_unchanged": not ready_changed,
            "current_research_ready_changed_ticker_count": len(ready_changed),
            "proxy_outside_readiness_tuple": not ready_changed,
            "compact_proxy_value_not_exposed": not compact_proxy_value_exposed,
            "proxy_is_research_only": all((record.get("authority_boundary") or {}).get("is_actionable") is False
                                            for record in records.values()),
            "no_provider_or_store_write_performed": True,
        },
        "boundaries": {
            "canonical_metrics_only": ["operating_cash_flow", "capital_expenditure"],
            "same_representation_gate": "provider_source_scope_currency_scale_exact_period_standalone_quarter",
            "capex_sign_rule": "provider_native_signed_capex_is_retained_without_normalization",
            "excluded": ["YTD_CUMULATIVE_INTERIM", "UNKNOWN_DURATION", "provider_or_scope_mix", "conflicted_or_partial_inputs"],
            "not_authoritative_free_cash_flow": True,
            "not_valuation_or_decision_input": True,
        },
    }
    report = "\n".join([
        f"# {MILESTONE}", "",
        "Read-only persisted Financial V2 replay; no provider, runtime-store, database, UI, or decision-path writes.", "",
        "## Coverage", "",
        f"- Financial V2 denominator: {coverage['ticker_denominator']}",
        f"- Zero silent drops: {coverage['zero_silent_ticker_drops']}",
        f"- READY free-cash-flow research proxies: {coverage['free_cash_flow_proxy_status'].get('READY', 0)}",
        f"- READY same-quarter direction calculations: {coverage['free_cash_flow_proxy_direction_status'].get('READY', 0)}",
        f"- Current-research-ready count unchanged: {validation['checks']['current_research_ready_unchanged']}", "",
        "## Boundary", "",
        "The feature is `free_cash_flow_proxy`, computed only as operating cash flow plus the provider-native signed capital-expenditure fact in one compatible standalone-quarter representation. It is not authoritative free cash flow and is not a valuation, readiness, or decision input.", "",
        "See `coverage.json`, `validation_artifact.json`, and `financial_analysis_product_projection.json` for machine-readable evidence. No raw financial values are published in these validation artifacts.", "",
    ])
    return coverage, validation, product, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-artifact", type=Path, required=True)
    parser.add_argument("--baseline-engine-artifact", type=Path, required=True)
    parser.add_argument("--feature-store-records", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--requested-at", default="2026-09-02T00:00:00+07:00")
    args = parser.parse_args()
    coverage, validation, product, report = build(
        replay=_read_json(args.engine_artifact), baseline=_read_json(args.baseline_engine_artifact),
        tickers=_feature_store_tickers(args.feature_store_records), runtime_root=args.runtime_root,
        requested_at=args.requested_at,
    )
    atomic_write_json(args.output_dir / "coverage.json", coverage)
    atomic_write_json(args.output_dir / "validation_artifact.json", validation)
    atomic_write_json(args.output_dir / "financial_analysis_product_projection.json", product)
    atomic_write_file(args.output_dir / "REPORT.md", report)
    print(json.dumps({"coverage": coverage, "checks": validation["checks"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
