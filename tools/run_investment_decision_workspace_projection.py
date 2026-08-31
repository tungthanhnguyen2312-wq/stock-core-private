"""Materialize investment_decision_workspace_projection/v1 from retained artifacts. No network."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from investment_decision_workspace_projection import build_artifacts  # noqa: E402

OUT = ROOT / "operations-review" / "investment-decision-workspace-v1-20260831"
DECISION_SESSION = "2026-08-28"
SEARCH_ROOTS = [
    ROOT,
    ROOT / "operations-review" / "current-valuation-and-opportunity-integration-v1-20260831",
    ROOT / "operations-review" / "workspace-inputs-v1",
    ROOT / "operations-review" / "research-liquidity-and-explicit-portfolio-v1-20260831",
    ROOT / "operations-review" / "current-market-sector-leadership-context-v1-20260828",
    ROOT.parents[1] / "stock-core-private",
]


def resolve(*relative: str) -> Path | None:
    for root in SEARCH_ROOTS:
        for item in relative:
            path = Path(item)
            candidate = path if path.is_absolute() else root / item
            if candidate.exists():
                return candidate
    return None


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def representative_cases(cards: dict) -> list[dict]:
    rows = []
    for ticker, card in cards.items():
        rows.append({
            "ticker": ticker, "research_stance": card["research_stance"], "entry_state": card["entry_state"],
            "fundamental_state": card["fundamental"].get("state"),
            "relative_valuation": card["valuation"].get("relative_research_state"),
            "guard_applied": card["valuation"].get("market_cap_semantic_guard_applied"),
            "entity_class": card["valuation"].get("entity_class"),
            "liquidity": card["liquidity"].get("readiness"),
            "execution": card["liquidity"].get("exact_execution_capacity_status"),
            "usable_axes": [axis for axis, freshness in card["lineage"]["per_axis_freshness"].items() if freshness in {"CURRENT", "STALE_BUT_RESEARCH_USABLE"}],
            "freshness": card["lineage"]["per_axis_freshness"],
            "portfolio_status": card["portfolio"].get("status"),
        })

    def pick(predicate, label):
        match = next((row for row in rows if predicate(row)), None)
        return {"label": label, "ticker": None if match is None else match["ticker"], "record": match}

    return [
        pick(lambda r: r["fundamental_state"] == "PROFITABLE" and r["relative_valuation"] == "ATTRACTIVE_RELATIVE_RESEARCH"
             and r["entry_state"] in {"BREAKOUT_READY", "UPTREND_CONFIRMED", "EARLY_REVERSAL_CANDIDATE", "BASE_BUILDING"}, "initiate_breakout_ready"),
        pick(lambda r: r["relative_valuation"] == "EXPENSIVE_RELATIVE_RESEARCH" and r["entry_state"] in {"BREAKOUT_READY", "UPTREND_CONFIRMED"}, "expensive_strong_tactical"),
        pick(lambda r: r["fundamental_state"] == "LOSS_MAKING", "loss_making"),
        pick(lambda r: r["entry_state"] == "EARLY_REVERSAL_CANDIDATE", "early_reversal_speculative"),
        pick(lambda r: r["relative_valuation"] in {None, "UNAVAILABLE"} and "fundamental" in r["usable_axes"], "valuation_unavailable_otherwise_usable"),
        pick(lambda r: r["entity_class"] in {"bank", "securities", "insurance", "finance_company"}, "specialized_financial_entity"),
        pick(lambda r: r["liquidity"] == "LIQUIDITY_RESEARCH_PROXY" and r["execution"] == "EXECUTION_CAPACITY_EXACT_BLOCKED", "liquidity_proxy_exact_blocked"),
        pick(lambda r: len({v for v in r["freshness"].values() if v}) > 1, "mixed_session_evidence"),
        pick(lambda r: r["portfolio_status"] == "NOT_EVALUATED", "no_portfolio"),
        pick(lambda r: r["guard_applied"], "market_cap_guard_applied"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--opportunity-context", type=Path, default=None)
    parser.add_argument("--decision-context", type=Path, default=None)
    parser.add_argument("--leadership", type=Path, default=None)
    parser.add_argument("--portfolio-research", type=Path, default=None)
    parser.add_argument("--prospective-lifecycle", type=Path, default=None)
    parser.add_argument("--requested-at", default="2026-08-31T00:00:00+07:00")
    parser.add_argument("--output-dir", type=Path, default=OUT)
    args = parser.parse_args()

    opportunity_path = args.opportunity_context or resolve("opportunity_context_artifact.json")
    decision_path = args.decision_context or resolve("security_decision_context_artifact.json")
    if opportunity_path is None or decision_path is None:
        raise FileNotFoundError("RETAINED_OPPORTUNITY_OR_DECISION_ARTIFACT_NOT_FOUND")
    opportunity = load_json(opportunity_path)
    decision = load_json(decision_path)

    leadership = None
    leadership_path = args.leadership or resolve(
        "operations-review/current-market-sector-leadership-context-v1-20260828/current_market_sector_leadership_context_artifact.json",
        "current_market_sector_leadership_context_artifact.json",
    )
    if leadership_path is not None:
        leadership = load_json(leadership_path)

    portfolio_research = None
    portfolio_path = args.portfolio_research or resolve("research-liquidity-and-explicit-portfolio-v1-20260831/artifact.json")
    if portfolio_path is not None:
        payload = load_json(portfolio_path)
        portfolio_research = payload.get("portfolio_research_context") if "portfolio_research_context" in payload else payload

    prospective_lifecycle = None
    if args.prospective_lifecycle is not None and args.prospective_lifecycle.exists():
        prospective_lifecycle = load_json(args.prospective_lifecycle)

    artifact = build_artifacts(
        opportunity_artifact=opportunity, decision_artifact=decision, leadership=leadership,
        portfolio_research=portfolio_research, prospective_lifecycle=prospective_lifecycle,
        requested_at=args.requested_at,
    )

    cases = representative_cases(artifact["cards"])
    validation = {
        "milestone": "INVESTMENT_DECISION_WORKSPACE_V1",
        "as_of_session": artifact["as_of_session"],
        "ticker_denominator": artifact["coverage"]["ticker_denominator"],
        "workspace_coverage": artifact["coverage"]["workspace_coverage"],
        "zero_silent_ticker_drops": artifact["coverage"]["zero_silent_ticker_drops"],
        "research_stance_distribution": artifact["coverage"]["research_stance_distribution"],
        "entry_state_distribution": artifact["coverage"]["entry_state_distribution"],
        "valuation_relative_state_distribution": artifact["coverage"]["valuation_relative_state_distribution"],
        "market_cap_semantic_guard_applied_count": artifact["coverage"]["market_cap_semantic_guard_applied_count"],
        "portfolio_evaluated_count": artifact["coverage"]["portfolio_evaluated_count"],
        "prospective_cases_available_count": artifact["coverage"]["prospective_cases_available_count"],
        "stale_axis_present_count": artifact["coverage"]["stale_axis_present_count"],
        "source_artifacts": artifact["source_artifacts"],
        "artifact_identity": artifact["artifact_identity"],
        "representative_real_cases": cases,
        "inputs_used": {
            "opportunity_context": str(opportunity_path), "security_decision_context": str(decision_path),
            "leadership": str(leadership_path) if leadership_path else None,
            "portfolio_research": str(portfolio_path) if portfolio_path else None,
        },
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "investment_decision_workspace_artifact.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "validation_artifact.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "artifact_identity": artifact["artifact_identity"],
        "ticker_denominator": validation["ticker_denominator"],
        "research_stance_distribution": validation["research_stance_distribution"],
        "market_cap_semantic_guard_applied_count": validation["market_cap_semantic_guard_applied_count"],
        "representative_tickers": {item["label"]: item["ticker"] for item in cases},
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
