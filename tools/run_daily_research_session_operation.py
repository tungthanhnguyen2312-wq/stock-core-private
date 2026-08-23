"""One explicit foreground entry point for a retained completed-session operation."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from daily_research_session_operations import _identity, build_operation, load_registry, materialize, resolve_inputs


def _head(root: Path) -> str:
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize one coherent retained completed-session research operation.")
    parser.add_argument("--session", required=True, help="Completed market session YYYY-MM-DD; resolved only through an explicit input registry.")
    parser.add_argument("--input-registry", type=Path, help="Explicit governed session-input registry; never a latest-file search.")
    parser.add_argument("--output-root", type=Path, default=ROOT / "operations-review" / "daily-research-session-operations-v1")
    parser.add_argument("--generation-context", default="RETAINED_FIXED_TIME_REPLAY")
    parser.add_argument("--portfolio-input", type=Path, help="Explicit portfolio JSON; omitted means no portfolio branch.")
    args = parser.parse_args()
    registry = load_registry(ROOT, args.input_registry)
    inputs, _ = resolve_inputs(ROOT, args.session, registry)
    consumer_root = ROOT.parent / "ai-core-private"
    portfolio = json.loads(args.portfolio_input.read_text(encoding="utf-8")) if args.portfolio_input else None
    operation = build_operation(inputs, args.session, producer_head=_head(ROOT), consumer_head=_head(consumer_root), generation_context=args.generation_context, portfolio=portfolio)
    sys.path.insert(0, str(consumer_root))
    from builders.build_ticker_context import current_daily_decision_research_contract
    card = operation["product"]["detailed_research_cards"].get("ABB")
    if not card: raise ValueError("CONSUMER_E2E_REPRESENTATIVE_CARD_MISSING")
    bundled = dict(card); bundled.update({"source_artifact_identity": operation["product"]["artifact_identity"], "source_session": args.session, "market_brief": operation["product"]["market_brief"], "authority_boundary": operation["product"]["authority_boundary"], "is_actionable": False})
    if operation.get("portfolio_risk"): bundled["portfolio_risk"] = operation["portfolio_risk"]
    accepted = current_daily_decision_research_contract({"tickers": {"ABB": {"current_daily_decision_research": bundled}}}, "ABB")
    if not accepted or accepted.get("status") == "malformed": raise ValueError("CONSUMER_E2E_FAIL_CLOSED")
    operation["manifest"]["consumer_e2e"] = {"status": "PASS", "representative_ticker": "ABB", "consumer_contract": "current_daily_decision_research_contract"}
    operation["manifest"]["operation_identity"] = _identity(operation["manifest"])
    output_dir = args.output_root / args.session / operation["manifest"]["operation_identity"].split(":", 1)[1]
    materialize(output_dir, operation)
    print(operation["manifest"]["operation_identity"])
    print(output_dir)


if __name__ == "__main__":
    main()
