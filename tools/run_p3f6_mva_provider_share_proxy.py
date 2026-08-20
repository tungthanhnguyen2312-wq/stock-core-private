"""Generate the deterministic P3-F6 MVA provider-share proxy artifact.

The runner is read-only with respect to the runtime database.  It materializes
only the requested review artifact under the repository's operations review.
"""
from __future__ import annotations

import argparse
from collections import Counter
import inspect
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from field_temporal_contract import stable_id
import market_wide_current_shares_resolver as shares_resolver
import mva_provider_share_proxy as proxy
from runtime_paths import runtime_root as resolve_runtime_root

VERSION = "1.0.0"
ARTIFACT_TYPE = "P3F6_MVA_PROVIDER_SHARE_PROXY_SHADOW_VALUATION"
P3E_PATH = ROOT / "operations-review" / "p3e-fundamental-coverage-closeout-20260820" / "p3e_fundamental_coverage_closeout_artifact.json"
P3F3_PATH = ROOT / "operations-review" / "p3f3-operational-valuation-input-scaleout-20260820" / "p3f3_operational_valuation_input_scaleout_artifact.json"
P3F5_PATH = ROOT / "operations-review" / "p3f5-current-share-promotion-review-20260820" / "p3f5_current_share_promotion_review_artifact.json"
DEFAULT_OUTPUT_DIR = ROOT / "operations-review" / "p3f6-mva-provider-share-proxy-20260820"


def _metadata(runtime_root: Path) -> dict[str, dict[str, Any]]:
    database = runtime_root / "vn_stock.db"
    connection = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        rows = connection.execute("SELECT ticker, shares_outstanding, updated FROM metadata ORDER BY ticker").fetchall()
    finally:
        connection.close()
    result: dict[str, dict[str, Any]] = {}
    for ticker, value, updated in rows:
        integer = int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 and float(value).is_integer() else None
        result[str(ticker).upper()] = {"canonical_ticker": str(ticker).upper(), "value": integer,
                                       "observation_date": str(updated)[:10] if updated else None,
                                       "retrieved_at": str(updated) if updated else None,
                                       "semantic_identity": proxy.SEMANTIC_IDENTITY,
                                       "provider_source": proxy.PROVIDER_SOURCE,
                                       "provider_field_lineage": proxy.PROVIDER_FIELD_LINEAGE}
    return result


def _ticker_branch_audit() -> dict[str, Any]:
    source = inspect.getsource(proxy) + inspect.getsource(sys.modules[__name__])
    candidates = ("HPG", "VCB", "SSI", "GAS", "VNM")
    violations = [ticker for ticker in candidates if f'== "{ticker}"' in source or f"== '{ticker}'" in source]
    return {"production_modules": ["mva_provider_share_proxy.py", "tools/run_p3f6_mva_provider_share_proxy.py"],
            "tested_ticker_literals": list(candidates), "branch_violations": violations,
            "status": "PASS" if not violations else "FAIL"}


def build_p3f6_artifact(runtime_root: Path) -> dict[str, Any]:
    p3e = json.loads(P3E_PATH.read_text(encoding="utf-8"))
    p3f3 = json.loads(P3F3_PATH.read_text(encoding="utf-8"))
    p3f5 = json.loads(P3F5_PATH.read_text(encoding="utf-8"))
    valuation_date = p3f3["valuation_session"]["valuation_session"]
    envelope = dict(proxy.REQUIRED_ENVELOPE)
    metadata = _metadata(runtime_root)
    safety_scan = shares_resolver.resolve_market_wide_shares(runtime_root, valuation_date)

    broad_proxy_rows = []
    for ticker in sorted(metadata):
        instrument = {"canonical_ticker": ticker}
        broad_proxy_rows.append(proxy.qualify_provider_issued_shares_proxy(
            instrument, metadata[ticker], valuation_date=valuation_date,
            safety_state=safety_scan["tickers"].get(ticker), envelope=envelope,
        ))

    issuers = sorted(p3e["refreshed_panel_data"]["issuers"], key=lambda item: item["issuer_identity"]["ticker"])
    prices = {row["canonical_instrument"]["canonical_ticker"]: row for row in p3f3["current_price_authority_matrix"]}
    valuation_rows = []
    for issuer in issuers:
        ticker = issuer["issuer_identity"]["ticker"]
        instrument = {"canonical_ticker": ticker, "provider_symbols": {"DNSE": ticker}}
        share_proxy = proxy.qualify_provider_issued_shares_proxy(
            instrument, metadata.get(ticker), valuation_date=valuation_date,
            safety_state=safety_scan["tickers"].get(ticker), envelope=envelope,
        )
        price = prices.get(ticker, {"status": "PRICE_BLOCKED", "reason_codes": ["P3F3_PRICE_MISSING"]})
        valuation_rows.append(proxy.evaluate_mva_proxy_issuer(issuer, price=price, proxy=share_proxy, envelope=envelope))

    proxy_statuses = Counter(row["status"] for row in broad_proxy_rows)
    cohort_proxy_statuses = Counter(row["provider_share_proxy"]["status"] for row in valuation_rows)
    ready_market_caps = [row for row in valuation_rows if row[proxy.PROXY_METRIC_IDENTITY]["status"] == "PROXY_MARKET_CAP_READY"]
    methods = ("P/E", "P/B", "P/S", "EV/Sales", "EV/EBITDA")
    metric_counts = {name: sum(row["methods"][name]["status"] == "MVA_PROXY_READY" for row in valuation_rows) for name in methods}
    authoritative = p3f3["authority_coverage_before_after"]["post_scaleout_p3f3"]
    authoritative_valuation = p3f3["valuation_coverage_before_after"]["post_scaleout_p3f3"]
    source_text = inspect.getsource(proxy)
    artifact: dict[str, Any] = {
        "schema_version": VERSION,
        "policy_version": proxy.POLICY_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "verdict": "P3F6_MVA_PROVIDER_PROXY_ACTIVATION_COMPLETE",
        **envelope,
        "source_artifacts": {"p3e": p3e.get("artifact_identity"), "p3f3": p3f3.get("artifact_identity"), "p3f5": p3f5.get("artifact_identity")},
        "allowed_use_boundary": {"owner_approval": "MVA_PROVIDER_ISSUED_SHARE_PROXY_USE", "proxy_namespace": proxy.PROXY_NAMESPACE,
                                 "semantic_identity": proxy.SEMANTIC_IDENTITY, "source_authority": proxy.SOURCE_AUTHORITY,
                                 "official_share_authority": False, "common_outstanding_equivalence": False,
                                 "permitted": "current_descriptive_MVA_shadow_only"},
        "source_authority_summary": {"VCI.overview.issue_share": "NOT_PROMOTED", "authoritative_p3f2_share_resolver": "UNCHANGED_FAIL_CLOSED"},
        "authoritative_coverage_unchanged": {"share_ready": authoritative.get("SHARE_READY"), "both_ready": authoritative.get("BOTH_READY"),
                                                "valuation_method_counts": {name: authoritative_valuation.get({"P/E": "pe_count", "P/B": "pb_count", "P/S": "ps_count", "EV/Sales": "ev_sales_count", "EV/EBITDA": "ev_ebitda_count"}[name]) for name in methods}},
        "provider_proxy_coverage": {"valuation_date": valuation_date, "available_metadata_universe": len(metadata),
                                      "status_counts": dict(sorted(proxy_statuses.items())), "proxy_share_eligible": sum(row["mva_proxy_eligible"] for row in broad_proxy_rows),
                                      "corporate_action_blocks": sum(row["status"] == "PROXY_CORPORATE_ACTION_BLOCKED" for row in broad_proxy_rows),
                                      "source_completeness": "retained_metadata_rows_only; not_canonical_universe_authority"},
        "freshness_distribution": dict(sorted(Counter(row["freshness_state"] for row in broad_proxy_rows).items())),
        "corporate_action_blocks": [{"ticker": row["canonical_instrument"]["canonical_ticker"], "status": row["status"], "blockers": row["blockers"]}
                                    for row in broad_proxy_rows if row["status"] == "PROXY_CORPORATE_ACTION_BLOCKED"],
        "mva_proxy_valuation_coverage": {"cohort_size": len(valuation_rows), "proxy_share_eligible": sum(row["provider_share_proxy"]["mva_proxy_eligible"] for row in valuation_rows),
                                           "proxy_both_ready": len(ready_market_caps), "proxy_market_cap_coverage": len(ready_market_caps),
                                           "proxy_method_counts": metric_counts, "proxy_share_status_counts": dict(sorted(cohort_proxy_statuses.items()))},
        "proxy_valuation_rows": valuation_rows,
        "representative_proxy_outputs": [row for row in valuation_rows if row[proxy.PROXY_METRIC_IDENTITY]["status"] == "PROXY_MARKET_CAP_READY"][:2],
        "sector_applicability": {"corporate": ["P/E", "P/B", "P/S", "EV/Sales", "EV/EBITDA_when_exact_EBITDA"], "bank": ["P/E", "P/B"], "securities": ["P/E", "P/B"]},
        "data_quality_warnings": ["ISSUED_SHARES_NOT_COMMON_OUTSTANDING", "NOT_PROMOTED_SOURCE_AUTHORITY", "STALE_PROVIDER_OBSERVATIONS_VISIBLE_ONLY_AS_DEGRADED_MVA_PROXY", "NO_EFFECTIVE_DATE_PROOF", "RAW_AS_TRADED_NOT_PROMOTED", "LIQUIDITY_SIZING_BLOCKED"],
        "blocked_capabilities": ["BUY_SELL_HOLD", "TARGET_PRICE", "EXPECTED_RETURN", "PEER_OR_INVESTMENT_RANKING", "POSITION_SIZE", "LIQUIDITY_CAPACITY", "PORTFOLIO_ACTION", "HISTORICAL_VALUATION", "PIT_BACKTEST", "SCENARIO_PROBABILITY"],
        "ticker_specific_branch_audit": _ticker_branch_audit(),
        "formula_reuse": {"formula_owner": "p3f_current_market_valuation._evaluate_issuer", "formula_version": proxy.p3f.CONTRACT_VERSION, "mathematics_forked": False,
                          "source_contains_no_formula_reimplementation": "market_cap /" not in source_text},
        "boundaries": {"source_promotion": False, "authoritative_resolver_changed": False, "runtime_database_mutated": False, "p3g": "RESERVED_NOT_STARTED"},
    }
    artifact["artifact_sha256"] = stable_id(artifact)
    artifact["artifact_identity"] = f"p3f6_mva_provider_share_proxy:{artifact['artifact_sha256']}"
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)
    artifact = build_p3f6_artifact(resolve_runtime_root(args.runtime_root))
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True)
    (output / "p3f6_mva_provider_share_proxy_artifact.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Artifact identity: {artifact['artifact_identity']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
