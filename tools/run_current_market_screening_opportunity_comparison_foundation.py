"""Materialize the deterministic current screening/comparison consumer artifact."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from current_market_screening_opportunity_comparison_foundation import build_artifact


SOURCE = ROOT / "operations-review/market-wide-current-technical-coverage-scaleout-v1-20260823/market_wide_current_descriptive_research_artifact.json"
OUT = ROOT / "operations-review/current-market-screening-opportunity-comparison-foundation-v1-20260823/current_market_screening_opportunity_comparison_foundation_artifact.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(SOURCE))
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args(argv)
    source = json.loads(Path(args.source).read_text(encoding="utf-8"))
    artifact = build_artifact(source)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
