"""Materialize current valuation + opportunity integration from retained artifacts. No network."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from current_valuation_opportunity_integration import build_artifacts  # noqa: E402

OUT = ROOT / "operations-review" / "current-valuation-and-opportunity-integration-v1-20260831"
DECISION_SESSION = "2026-08-28"
SEARCH_ROOTS = [
    ROOT,
    ROOT.parents[1] / "stock-core-private",
    ROOT.parents[1] / "worktrees" / "stock-core-tactical-behavioral-engine-v2-20260831",
    ROOT.parents[1] / "worktrees" / "stock-core-research-liquidity-explicit-portfolio-v1-20260831",
    ROOT.parents[1] / "worktrees" / "stock-core-market-wide-fundamental-feature-store-v1-20260831",
]


def resolve(*relative: str) -> Path:
    for root in SEARCH_ROOTS:
        for item in relative:
            path = Path(item)
            candidate = path if path.is_absolute() else root / item
            if candidate.exists():
                return candidate
    raise FileNotFoundError("RETAINED_ARTIFACT_NOT_FOUND:" + "|".join(relative))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_feature_store(directory: Path) -> dict:
    summary = load_json(directory / "market_wide_fundamental_feature_store_artifact.json")
    payload = directory / ((summary.get("records_payload") or {}).get("path") or "market_wide_fundamental_feature_store_records.jsonl.gz")
    records = {}
    with gzip.open(payload, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                records[row["ticker"]] = row
    summary["records"] = records
    return summary


def representative_cases(opportunity: dict, decision: dict) -> list[dict]:
    rows = []
    for ticker, record in opportunity["records"].items():
        decision_row = decision["records"][ticker]
        rows.append({
            "ticker": ticker,
            "entry_state": record["tactical"].get("primary_entry_state"),
            "research_stance": decision_row["research_stance"],
            "fundamental_state": record["fundamental"].get("state"),
            "fundamental_readiness": record["fundamental"].get("readiness"),
            "relative_valuation": (record["valuation"].get("peer_relative_context") or {}).get("relative_research_state"),
            "entity": record["valuation"].get("entity_class") or record["fundamental"].get("entity_type"),
            "liquidity": record["liquidity"].get("readiness"),
            "execution": record["liquidity"].get("exact_execution_capacity_status"),
            "pe_status": (record["valuation"].get("applicable_methods") or {}).get("P/E_TTM", {}).get("status"),
            "usable_axes": record["usable_major_axes"],
            "freshness": (record.get("data_authority") or {}).get("per_axis_freshness"),
        })

    def pick(predicate, label):
        match = next((row for row in rows if predicate(row)), None)
        return {"label": label, "ticker": None if match is None else match["ticker"], "record": match}

    return [
        pick(lambda row: row["fundamental_state"] == "PROFITABLE" and row["relative_valuation"] == "ATTRACTIVE_RELATIVE_RESEARCH"
             and row["entry_state"] in {"BREAKOUT_READY", "UPTREND_CONFIRMED", "EARLY_REVERSAL_CANDIDATE", "BASE_BUILDING"},
             "profitable_attractive_constructive_tactical"),
        pick(lambda row: row["relative_valuation"] == "EXPENSIVE_RELATIVE_RESEARCH"
             and row["entry_state"] in {"BREAKOUT_READY", "UPTREND_CONFIRMED", "EARLY_REVERSAL_CANDIDATE"},
             "expensive_strong_tactical"),
        pick(lambda row: row["fundamental_state"] == "LOSS_MAKING", "loss_making_turnaround"),
        pick(lambda row: row["fundamental_state"] == "PROFITABLE" and row["entry_state"] in {"DOWNTREND", "BREAKDOWN_RISK", "DISTRIBUTION_RISK"},
             "good_fundamental_weak_tactical"),
        pick(lambda row: row["entry_state"] == "EARLY_REVERSAL_CANDIDATE", "early_reversal_candidate"),
        pick(lambda row: row["relative_valuation"] in {None, "UNAVAILABLE", "PE_NOT_MEANINGFUL"} and row["usable_axes"]
             and "valuation" not in (row["usable_axes"] or []),
             "valuation_unavailable_otherwise_usable"),
        pick(lambda row: row["entity"] in {"bank", "securities", "insurance", "finance_company"}, "specialized_financial_entity"),
        pick(lambda row: row["liquidity"] == "LIQUIDITY_RESEARCH_PROXY" and row["execution"] == "EXECUTION_CAPACITY_EXACT_BLOCKED",
             "liquidity_proxy_exact_execution_blocked"),
        pick(lambda row: row["freshness"] and any(status == "STALE_BUT_RESEARCH_USABLE" for status in (row["freshness"] or {}).values())
             and any(status == "CURRENT" for status in (row["freshness"] or {}).values()),
             "stale_one_axis_current_other_axes"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of-session", default=DECISION_SESSION)
    parser.add_argument("--requested-at", default="2026-08-31T00:00:00+07:00")
    parser.add_argument("--output-dir", type=Path, default=OUT)
    parser.add_argument("--financial-analysis-context", type=Path)
    parser.add_argument("--financial-analysis-product-context", type=Path)
    args = parser.parse_args()

    feature_store = load_feature_store(resolve(
        "operations-review/market-wide-fundamental-feature-store-v1-20260831",
    ))
    tactical = load_json(resolve(
        "operations-review/tactical-behavioral-engine-v2-20260831/tactical_behavior_context_artifact.json",
    ))
    watchlist = load_json(resolve(
        "operations-review/watchlist-tactical-entry-decision-v1-20260828/watchlist_tactical_entry_classifier_artifact.json",
    ))
    valuation = load_json(resolve(
        "operations-review/market-wide-current-valuation-v1-20260828-session20260828/market_wide_current_valuation_artifact.json",
    ))
    liquidity = load_json(resolve(
        "operations-review/market-wide-current-liquidity-research-v1-20260828/market_wide_current_liquidity_research_artifact.json",
    ))
    events = load_json(resolve(
        "operations-review/current-corporate-event-context-v1/current_corporate_event_context_artifact.json",
    ))
    thesis = load_json(resolve(
        "operations-review/thesis-catalyst-downside-and-dual-invalidation-v1-20260828/artifact.json",
    ))
    leadership = load_json(resolve(
        "operations-review/current-market-sector-leadership-context-v1-20260828/current_market_sector_leadership_context_artifact.json",
    ))
    portfolio = None
    try:
        portfolio = load_json(resolve(
            "operations-review/current-portfolio-risk-research-v1-20260829/artifact.json",
            "operations-review/research-liquidity-and-explicit-portfolio-v1-20260831/artifact.json",
        ))
        if "portfolio_research_context" in portfolio:
            portfolio = portfolio["portfolio_research_context"]
    except FileNotFoundError:
        portfolio = None

    financial_analysis_context = load_json(args.financial_analysis_context) if args.financial_analysis_context else None
    financial_analysis_product_context = load_json(args.financial_analysis_product_context) if args.financial_analysis_product_context else None
    artifacts = build_artifacts(
        as_of_session=args.as_of_session, feature_store=feature_store, tactical_behavior=tactical,
        watchlist=watchlist, valuation=valuation, liquidity=liquidity, events=events, thesis_cases=thesis,
        leadership=leadership, portfolio=portfolio, financial_analysis_context=financial_analysis_context,
        financial_analysis_product_context=financial_analysis_product_context, requested_at=args.requested_at,
    )
    opportunity, decision = artifacts["opportunity_context"], artifacts["security_decision_context"]
    cases = representative_cases(opportunity, decision)
    earnings = Counter(record["valuation"].get("earnings_state") for record in opportunity["records"].values())
    pe_status = Counter((record["valuation"].get("applicable_methods") or {}).get("P/E_TTM", {}).get("status")
                         for record in opportunity["records"].values())
    qualified_ttm = Counter()
    ttm_basis_blockers = Counter()
    for record in opportunity["records"].values():
        for method_id in ("P/E_TTM", "P/S_TTM"):
            method = (record["valuation"].get("applicable_methods") or {}).get(method_id) or {}
            qualified_ttm[f"{method_id}:{method.get('ttm_input_source')}"] += 1
            for blocker in method.get("blocker_reason_codes") or []:
                if blocker in {"TTM_MARKET_CAP_MONETARY_BASIS_INCOMPATIBLE", "MARKET_CAP_RESEARCH_INPUT_UNAVAILABLE", "SHARE_BASIS_UNAVAILABLE"}:
                    ttm_basis_blockers[f"{method_id}:{blocker}"] += 1
    entity_methods = {}
    for record in opportunity["records"].values():
        entity = record["valuation"].get("entity_class") or "unknown"
        for method_id, method in (record["valuation"].get("applicable_methods") or {}).items():
            entity_methods.setdefault(entity, {}).setdefault(method_id, Counter())[method.get("applicability")] += 1
    specialized = {
        entity: {method_id: dict(counts) for method_id, counts in methods.items()}
        for entity, methods in entity_methods.items() if entity in {"bank", "securities", "insurance", "finance_company"}
    }
    blockers = Counter()
    for record in opportunity["records"].values():
        for item in (record.get("data_authority") or {}).get("blockers") or []:
            blockers[f"{item.get('axis')}:{item.get('readiness')}"] += 1

    validation = {
        "milestone": "CURRENT_VALUATION_AND_OPPORTUNITY_INTEGRATION_V1",
        "as_of_session": args.as_of_session,
        "ticker_denominator": opportunity["coverage"]["ticker_denominator"],
        "opportunity_context_coverage": opportunity["coverage"]["opportunity_context_coverage"],
        "security_decision_context_coverage": decision["coverage"]["security_decision_context_coverage"],
        "usable_axis_distribution": opportunity["coverage"]["axis_research_usable"],
        "usable_major_axis_count_distribution": opportunity["coverage"]["usable_major_axis_count_distribution"],
        "tickers_with_ge_3_usable_major_axes": opportunity["coverage"]["tickers_with_ge_3_usable_major_axes"],
        "tickers_with_ge_5_usable_major_axes": opportunity["coverage"]["tickers_with_ge_5_usable_major_axes"],
        "partial_by_evidence": opportunity["coverage"]["partial_by_evidence"],
        "valuation_method_coverage": opportunity["coverage"]["valuation_method_status"],
        "peer_relative_valuation_coverage": {
            "ready_method_instances": opportunity["coverage"]["peer_relative_valuation_ready_method_instances"],
            "tickers": opportunity["coverage"]["tickers_with_peer_relative_valuation"],
        },
        "fundamental_relative_coverage": opportunity["coverage"]["tickers_with_fundamental_relative"],
        "tactical_axis_coverage": opportunity["coverage"]["axis_research_usable"]["tactical"],
        "market_sector_axis_coverage": opportunity["coverage"]["axis_research_usable"]["market_sector"],
        "catalyst_axis_coverage": opportunity["coverage"]["axis_research_usable"]["catalyst"],
        "liquidity_axis_coverage": opportunity["coverage"]["axis_research_usable"]["liquidity"],
        "freshness_session_distribution": opportunity["coverage"]["freshness_status_by_axis"],
        "research_stance_distribution": decision["coverage"]["research_stance_distribution"],
        "negative_earnings_treatment": {
            "earnings_state": {str(key): count for key, count in earnings.items()},
            "pe_ttm_status": {str(key): count for key, count in pe_status.items()},
        },
        "qualified_ttm_valuation": {
            "ttm_input_source": dict(sorted(qualified_ttm.items())),
            "basis_and_input_blockers": dict(sorted(ttm_basis_blockers.items())),
            "pbt_context_only": True,
        },
        "specialized_financial_applicability": specialized,
        "main_blockers": {str(key): count for key, count in blockers.most_common(20)},
        "representative_real_cases": cases,
        "deterministic_identities": {
            "opportunity_context": opportunity["artifact_identity"],
            "security_decision_context": decision["artifact_identity"],
            "source_artifacts": opportunity["source_artifacts"],
        },
        "zero_silent_ticker_drops": opportunity["coverage"]["zero_silent_ticker_drops"]
            and decision["coverage"]["zero_silent_ticker_drops"],
        "authority_effect": "NONE / RESEARCH_ONLY",
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "opportunity_context_artifact.json").write_text(
        json.dumps(opportunity, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "security_decision_context_artifact.json").write_text(
        json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "validation_artifact.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "opportunity_identity": opportunity["artifact_identity"],
        "decision_identity": decision["artifact_identity"],
        "ticker_denominator": validation["ticker_denominator"],
        "research_stance_distribution": validation["research_stance_distribution"],
        "usable_axis_distribution": validation["usable_axis_distribution"],
        "tickers_with_ge_3_usable_major_axes": validation["tickers_with_ge_3_usable_major_axes"],
        "tickers_with_ge_5_usable_major_axes": validation["tickers_with_ge_5_usable_major_axes"],
        "representative_tickers": {item["label"]: item["ticker"] for item in cases},
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
