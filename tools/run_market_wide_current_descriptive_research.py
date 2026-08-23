"""Build the market-wide current descriptive research artifact.

Thin IO adapter only: reads three already-retained JSON artifacts plus the two already-retained
entity-classification sources (via ``sector_relative_research_context``'s own loaders, unmodified),
verifies identities, and calls the pure core in
``market_wide_current_descriptive_research.py``. No network call, no database write, no new
DNSE acquisition or universe/liquidity qualification.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from market_wide_current_descriptive_research import build_artifact
from sector_relative_research_context import load_provider_descriptive_industry_classes, load_qualified_entity_classes

DEFAULT_UNIVERSE_RESOLUTION = ROOT / "operations-review/current-universe-status-and-session-coverage-resolution-v1-20260823/current_universe_status_and_session_coverage_resolution_artifact.json"
DEFAULT_P3F9B_SNAPSHOT = ROOT / "operations-review/p3f9b-market-wide-exact-session-scaleout-20260821/p3f9b_mva_exact_session_snapshot.json"
DEFAULT_LIQUIDITY_ARTIFACT = ROOT / "operations-review/market-wide-current-liquidity-research-v1-20260823-resumable/market_wide_current_liquidity_research_artifact.json"
DEFAULT_OUTPUT = ROOT / "operations-review/market-wide-current-descriptive-research-v1-20260823/market_wide_current_descriptive_research_artifact.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe-resolution-artifact", default=str(DEFAULT_UNIVERSE_RESOLUTION))
    parser.add_argument("--p3f9b-snapshot", default=str(DEFAULT_P3F9B_SNAPSHOT))
    parser.add_argument("--liquidity-artifact", default=str(DEFAULT_LIQUIDITY_ARTIFACT))
    parser.add_argument("--technical-history-recovery-artifact", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)

    universe_resolution = _load(Path(args.universe_resolution_artifact))
    p3f9b_snapshot = _load(Path(args.p3f9b_snapshot))
    liquidity_artifact = _load(Path(args.liquidity_artifact))
    technical_history_recovery = _load(Path(args.technical_history_recovery_artifact)) if args.technical_history_recovery_artifact else None

    qualified = load_qualified_entity_classes(ROOT)
    provider_descriptive = load_provider_descriptive_industry_classes(ROOT, qualified)
    entity_classifications = {**qualified, **provider_descriptive}

    artifact = build_artifact(
        universe_resolution_artifact=universe_resolution,
        p3f9b_snapshot=p3f9b_snapshot,
        liquidity_artifact=liquidity_artifact,
        entity_classifications=entity_classifications,
        technical_history_recovery_artifact=technical_history_recovery,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(artifact["artifact_identity"])
    print(f"market_breadth = {artifact['market_breadth']}")
    print(f"sector_breadth.sector_count_available = {artifact['sector_breadth']['sector_count_available']} / {artifact['sector_breadth']['sector_count_total']}")
    print(f"cross_sectional_features = {artifact['cross_sectional_features']}")
    print(f"liquidity_features = {artifact['liquidity_features']}")
    print(f"validation.coverage = {artifact['validation']['coverage']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
