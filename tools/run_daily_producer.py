"""Foreground command for one governed completed-session Producer run."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from daily_producer_pipeline import DailyProducerError, run_daily_producer


def _head(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one exact, completed-session Stock Lookup Producer delivery.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--session", help="Exact governed completed market session (YYYY-MM-DD).")
    mode.add_argument("--latest-completed-session", action="store_true", help="Resolve only from the explicit governed completed-session ledger; never from wall clock.")
    parser.add_argument("--input-registry", type=Path, help="Explicit governed registry path.")
    parser.add_argument("--output-root", type=Path, default=ROOT / "operations-review" / "daily-producer-runs-v1")
    parser.add_argument("--operation-output-root", type=Path, default=ROOT / "operations-review" / "daily-research-session-operations-v1")
    parser.add_argument("--portfolio-input", type=Path, help="Explicit portfolio JSON only; a watchlist is never holdings.")
    parser.add_argument("--macro-artifact", type=Path, help="Explicit macro artifact only; omitted remains unavailable.")
    args = parser.parse_args()
    portfolio = json.loads(args.portfolio_input.read_text(encoding="utf-8")) if args.portfolio_input else None
    macro = json.loads(args.macro_artifact.read_text(encoding="utf-8")) if args.macro_artifact else None
    try:
        result = run_daily_producer(ROOT, session=args.session, latest_completed_session=args.latest_completed_session, producer_head=_head(ROOT), consumer_head=_head(ROOT.parent / "ai-core-private"), registry_path=args.input_registry, output_root=args.output_root, operation_output_root=args.operation_output_root, portfolio=portfolio, macro=macro)
    except DailyProducerError as exc:
        print("STATUS: REFUSE_COMPLETED_SESSION_RUN")
        print(f"REASON: {exc}")
        raise SystemExit(2)
    manifest = result["manifest"]
    print(f"SESSION: {result['session']}")
    print(f"STATUS: {result['status']}")
    print(f"OPERATION_ID: {result['operation']['manifest']['operation_identity']}")
    print(f"MARKET_COVERAGE: {manifest['coverage_summary']['technical']}")
    print(f"WARNINGS: {len(manifest['warnings'])}")
    print(f"AI_PRIMARY_BUNDLE: {result['run_dir'] / 'ai_research_session_bundle.json'}")
    print(f"AI_FULL_UNIVERSE_LOOKUP_ONLY: {result['run_dir'] / 'ai_research_full_universe.ndjson'}")
    print("DO_NOT_USE_AS_PRIMARY: ai_research_full_universe.ndjson")
    print(f"DASHBOARD_PROJECTION: {result['run_dir'] / 'dashboard' / 'current_decision_cockpit_projection.json'}")
    print(f"BLOCKED_DIMENSIONS: {','.join(manifest['blocked_dimensions'])}")


if __name__ == "__main__":
    main()
