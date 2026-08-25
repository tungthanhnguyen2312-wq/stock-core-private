"""Build a current-session official-universe market and sector leadership context artifact.

This is an IO adapter for the pure ``current_market_sector_leadership_context`` contract.  It
reads the three retained inputs supplied on the command line (or the pinned current-review
defaults), performs no acquisition, and writes only the requested diagnostic artifact.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_market_sector_leadership_context import build_artifact, replay


DEFAULT_DESCRIPTIVE = ROOT / "operations-review/market-wide-current-descriptive-research-v1-20260824/market_wide_current_descriptive_research_artifact.json"
DEFAULT_SCREENING = ROOT / "operations-review/current-market-screening-opportunity-comparison-foundation-v1-20260824/current_market_screening_opportunity_comparison_foundation_artifact.json"
DEFAULT_OFFICIAL_UNIVERSE = ROOT / "operations-review/current-official-market-universe-integration-v1-20260824/current_official_market_universe_artifact.json"
DEFAULT_OUTPUT = ROOT / "operations-review/current-market-sector-leadership-context-v1-20260825/current_market_sector_leadership_context_artifact.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-descriptive-artifact", default=str(DEFAULT_DESCRIPTIVE))
    parser.add_argument("--current-screening-artifact", default=str(DEFAULT_SCREENING))
    parser.add_argument("--current-official-universe-artifact", default=str(DEFAULT_OFFICIAL_UNIVERSE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)

    artifact = build_artifact(
        current_descriptive=_load(Path(args.current_descriptive_artifact)),
        current_screening=_load(Path(args.current_screening_artifact)),
        current_official_universe=_load(Path(args.current_official_universe_artifact)),
    )
    replay(artifact)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"])
    print(f"market = {artifact['market']}")
    print(f"groups = {artifact['groups']['available_group_count']} available / {artifact['groups']['group_count']} total")
    print(f"coverage = {artifact['coverage']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
