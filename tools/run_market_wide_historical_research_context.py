"""Build the market-wide historical research-context artifact from retained data.

Thin IO adapter only: reads already-retained JSON artifacts, verifies identities,
and calls the pure core in ``market_wide_historical_research_context.py``.
No network call, no database write, no new DNSE acquisition, and no mutation of
the governed 2026-08-24 session or 2026-08-21 prospective freeze.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from market_wide_historical_research_context import build_artifact

DEFAULT_UNIVERSE_RESOLUTION = ROOT / (
    "operations-review/current-universe-status-and-session-coverage-resolution-v1-20260824/"
    "current_universe_status_and_session_coverage_resolution_artifact.json"
)
DEFAULT_P3F9B_SNAPSHOT = ROOT / (
    "operations-review/p3f9b-market-wide-exact-session-scaleout-20260824/"
    "p3f9b_mva_exact_session_snapshot.json"
)
DEFAULT_RECOVERY = ROOT / (
    "operations-review/market-wide-current-technical-coverage-scaleout-v1-20260824/"
    "market_wide_current_technical_coverage_recovery_artifact.json"
)
DEFAULT_STRATEGY = ROOT / (
    "operations-review/daily-research-session-operations-v1/2026-08-24/"
    "4c6ee6fcfc170824ac4c7ca1fb495cf7774aaebaf7d48975bd681d7e34ab80aa/"
    "strategy_classification_artifact.json"
)
DEFAULT_OUTPUT = ROOT / (
    "operations-review/market-wide-historical-research-context-v1-20260824/"
    "market_wide_historical_research_context_artifact.json"
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe-resolution-artifact", default=str(DEFAULT_UNIVERSE_RESOLUTION))
    parser.add_argument("--p3f9b-snapshot", default=str(DEFAULT_P3F9B_SNAPSHOT))
    parser.add_argument("--technical-history-recovery-artifact", default=str(DEFAULT_RECOVERY))
    parser.add_argument("--strategy-artifact", default=str(DEFAULT_STRATEGY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)

    universe_resolution = _load(Path(args.universe_resolution_artifact))
    p3f9b_snapshot = _load(Path(args.p3f9b_snapshot))
    recovery = _load(Path(args.technical_history_recovery_artifact)) if args.technical_history_recovery_artifact else None
    strategy = _load(Path(args.strategy_artifact)) if args.strategy_artifact else None

    artifact = build_artifact(
        universe_resolution_artifact=universe_resolution,
        p3f9b_snapshot=p3f9b_snapshot,
        technical_history_recovery_artifact=recovery,
        strategy_artifact=strategy,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    coverage = artifact["coverage"]
    print(artifact["artifact_identity"])
    print(f"session = {artifact['session']}")
    print(f"context_status_counts = {coverage['context_status_counts']}")
    print(f"structural_state_counts = {coverage['structural_state_counts']}")
    print(f"observation_count_buckets = {coverage['observation_count_buckets']}")
    print(f"fifty_two_week_available_count = {coverage['fifty_two_week_available_count']}")
    print(f"current_session_context_count = {coverage['current_session_context_count']}")
    print(f"RAW_AS_TRADED = {artifact['authority_boundary']['RAW_AS_TRADED']}")
    print(f"PIT = {artifact['authority_boundary']['PIT']}")
    examples = artifact["pilot_diagnostics"]["current_strategy_lane_examples"]["lanes"]
    for lane, rows in examples.items():
        print(f"example {lane} = {[row['ticker'] for row in rows]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
