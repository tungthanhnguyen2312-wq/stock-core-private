"""Materialize the optional current candidate-set risk research artifact offline."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_portfolio_risk_research import build_artifact

DEFAULT_SHADOW = ROOT / "operations-review/shadow-action-readiness-v1-20260828/artifact.json"
DEFAULT_CASES = ROOT / "operations-review/thesis-catalyst-downside-and-dual-invalidation-v1-20260828/artifact.json"
DEFAULT_SNAPSHOT = ROOT / "operations-review/p3f9b-market-wide-exact-session-scaleout-20260825/p3f9b_mva_exact_session_snapshot.json"
DEFAULT_SECTOR = ROOT / "operations-review/current-market-sector-leadership-context-v1-20260825/current_market_sector_leadership_context_artifact.json"
DEFAULT_OUTPUT = ROOT / "operations-review/current-portfolio-risk-research-v1-20260829/artifact.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run(output: Path = DEFAULT_OUTPUT) -> dict:
    artifact = build_artifact(shadow_readiness=_load(DEFAULT_SHADOW), research_cases=_load(DEFAULT_CASES),
                              price_snapshot=_load(DEFAULT_SNAPSHOT), sector_context=_load(DEFAULT_SECTOR))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    artifact = run(Path(args.output))
    print(artifact["artifact_identity"])
    print(f"as_of_session = {artifact['metadata']['as_of_session']}")
    print(f"cohort = {artifact['cohort_summary']['primary_cohort_count']}")
    print(f"pairwise_total_pair_count = {artifact['validation']['pairwise_total_pair_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
