"""Materialize research liquidity + explicit-portfolio research context from retained inputs.

Default (no flags): reproduces the original retained-risk demonstration artifact, unchanged.
--portfolio-input <path.json>: evaluate a REAL explicit_portfolio_input JSON (portfolio_id,
as_of_session, positions[], optional risk_limits/cash) exported from the Dashboard Portfolio
Editor, instead of the synthetic top-3-by-weight demonstration portfolio. No network; no
covariance/volatility/correlation is computed here -- this script only joins the caller's
holdings against already-computed current_portfolio_risk_research/v1 and liquidity evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research_liquidity_portfolio import build_liquidity_research_context, build_portfolio_research_context  # noqa: E402

DEFAULT_RISK = ROOT / "operations-review/current-portfolio-risk-research-v1-20260829/artifact.json"
DEFAULT_DESCRIPTIVE = ROOT / "operations-review/market-wide-current-technical-coverage-scaleout-v1-20260823/market_wide_current_descriptive_research_artifact.json"
DEFAULT_OUT = ROOT / "operations-review/research-liquidity-and-explicit-portfolio-v1-20260831"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_liquidity(descriptive: dict) -> dict:
    rows = {
        ticker: {
            "current_volume": record.get("liquidity", {}).get("current_ohlc_v"),
            "board_composition_context": record.get("liquidity", {}).get("status"),
            "exact_execution_capacity_status": "EXECUTION_CAPACITY_EXACT_BLOCKED",
        }
        for ticker, record in descriptive["records"].items()
    }
    return build_liquidity_research_context(
        as_of_session=descriptive["session"], records=rows, source_identity=descriptive.get("artifact_identity"),
    )


def demonstration_portfolio(risk: dict) -> dict:
    held = risk["joint_matrix_context"]["L60"]["included_tickers"][:3]
    return {
        "portfolio_id": "RETAINED_RISK_DEMONSTRATION_NOT_REAL_HOLDINGS",
        "as_of_session": risk["metadata"]["as_of_session"],
        "positions": [{"ticker": ticker, "explicit_weight": 1 / len(held)} for ticker in held],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portfolio-input", type=Path, default=None,
                        help="Explicit portfolio JSON (portfolio_id, as_of_session, positions[], optional risk_limits/cash).")
    parser.add_argument("--risk-artifact", type=Path, default=DEFAULT_RISK)
    parser.add_argument("--descriptive-artifact", type=Path, default=DEFAULT_DESCRIPTIVE)
    parser.add_argument("--output", type=Path, default=None, help="Explicit output file path.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    risk = load(args.risk_artifact)
    descriptive = load(args.descriptive_artifact)
    liquidity = build_liquidity(descriptive)

    if args.portfolio_input is not None:
        portfolio = load(args.portfolio_input)
    else:
        portfolio = demonstration_portfolio(risk)

    portfolio_context = build_portfolio_research_context(portfolio=portfolio, risk_artifact=risk, liquidity_context=liquidity)
    payload = {"liquidity_research_context": liquidity, "portfolio_research_context": portfolio_context}

    if args.output is not None:
        output_path = args.output
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        suffix = "" if args.portfolio_input is None else f"-{portfolio_context['portfolio_id']}"
        output_path = args.output_dir / f"artifact{suffix}.json"

    output_path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "liquidity": liquidity["artifact_identity"], "portfolio": portfolio_context["artifact_identity"],
        "portfolio_id": portfolio_context["portfolio_id"], "output": str(output_path),
        "sector_concentration": portfolio_context["sector_concentration"],
        "user_limit_breaches": portfolio_context["user_limit_breaches"],
        "selected_joint_risk_horizon": portfolio_context["selected_joint_risk_horizon"],
        "joint_risk_status": portfolio_context["joint_risk_status"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
