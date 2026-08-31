"""Materialize the retained-input research liquidity and portfolio validation artifact."""
from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research_liquidity_portfolio import build_liquidity_research_context, build_portfolio_research_context

def load(path: Path): return json.loads(path.read_text(encoding="utf-8"))
def main():
    risk = load(ROOT / "operations-review/current-portfolio-risk-research-v1-20260829/artifact.json")
    descriptive = load(ROOT / "operations-review/market-wide-current-technical-coverage-scaleout-v1-20260823/market_wide_current_descriptive_research_artifact.json")
    rows = {ticker: {"current_volume": record.get("liquidity", {}).get("current_ohlc_v"), "board_composition_context": record.get("liquidity", {}).get("status"), "exact_execution_capacity_status": "EXECUTION_CAPACITY_EXACT_BLOCKED"} for ticker, record in descriptive["records"].items()}
    liquidity = build_liquidity_research_context(as_of_session=descriptive["session"], records=rows, source_identity=descriptive.get("artifact_identity"))
    held = risk["joint_matrix_context"]["L60"]["included_tickers"][:3]
    portfolio = {"portfolio_id": "RETAINED_RISK_DEMONSTRATION_NOT_REAL_HOLDINGS", "as_of_session": risk["metadata"]["as_of_session"], "positions": [{"ticker": ticker, "explicit_weight": 1 / len(held)} for ticker in held]}
    portfolio_context = build_portfolio_research_context(portfolio=portfolio, risk_artifact=risk, liquidity_context=liquidity)
    out = ROOT / "operations-review/research-liquidity-and-explicit-portfolio-v1-20260831"; out.mkdir(parents=True, exist_ok=True)
    (out / "artifact.json").write_text(json.dumps({"liquidity_research_context": liquidity, "portfolio_research_context": portfolio_context}, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"liquidity": liquidity["artifact_identity"], "portfolio": portfolio_context["artifact_identity"]}, sort_keys=True))
if __name__ == "__main__": main()
