"""Run sector-aware relative research artifact materialization."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sector_aware_relative_research import build, content_identity

OPS = ROOT / "operations-review"
DEFAULT_OUT = OPS / "sector-aware-relative-research-v1-20260824" / "sector_aware_relative_research_artifact.json"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build sector-aware relative research artifact.")
    parser.add_argument("--descriptive", type=Path, default=OPS / "market-wide-current-technical-coverage-scaleout-v1-20260823/market_wide_current_descriptive_research_artifact.json")
    parser.add_argument("--tactical", type=Path, default=OPS / "watchlist-tactical-entry-decision-v1-20260823/watchlist_tactical_entry_classifier_artifact.json")
    parser.add_argument("--fundamental", type=Path, default=OPS / "market-wide-current-fundamental-research-v1-20260823/market_wide_current_fundamental_research_artifact.json")
    parser.add_argument("--valuation", type=Path, default=OPS / "market-wide-current-valuation-v1-20260824/market_wide_current_valuation_artifact.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    inputs = {
        "descriptive": json.loads(args.descriptive.read_text(encoding="utf-8")),
        "tactical": json.loads(args.tactical.read_text(encoding="utf-8")),
        "fundamental": json.loads(args.fundamental.read_text(encoding="utf-8")),
        "valuation": json.loads(args.valuation.read_text(encoding="utf-8")),
    }
    artifact = build(**inputs)
    assert content_identity(artifact)["artifact_sha256"] == artifact["artifact_sha256"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"])


if __name__ == "__main__":
    main()
