"""Materialize the watchlist_tactical_entry_classifier artifact to disk.

Foreground, offline, deterministic given three already-retained inputs: no network call, no new
technical/screening/fundamental evidence acquisition. Safe to rerun at any time; the result only
changes if one of the three retained source artifacts changes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from watchlist_tactical_entry_classifier import build_artifact  # noqa: E402

DEFAULT_DESCRIPTIVE = ROOT / "operations-review/market-wide-current-technical-coverage-scaleout-v1-20260823/market_wide_current_descriptive_research_artifact.json"
DEFAULT_SCREENING = ROOT / "operations-review/current-market-screening-opportunity-comparison-foundation-v1-20260823/current_market_screening_opportunity_comparison_foundation_artifact.json"
DEFAULT_FUNDAMENTAL = ROOT / "operations-review/market-wide-current-fundamental-research-v1-20260823/market_wide_current_fundamental_research_artifact.json"
DEFAULT_OUT = ROOT / "operations-review" / "watchlist-tactical-entry-decision-v1-20260823"
ARTIFACT_FILENAME = "watchlist_tactical_entry_classifier_artifact.json"


def run(*, descriptive_path: Path, screening_path: Path, fundamental_path: Path, out_dir: Path,
        requested_at: str) -> Path:
    descriptive = json.loads(descriptive_path.read_text(encoding="utf-8"))
    screening = json.loads(screening_path.read_text(encoding="utf-8"))
    fundamental = json.loads(fundamental_path.read_text(encoding="utf-8"))
    artifact = build_artifact(
        descriptive_source=descriptive, screening_source=screening, fundamental_source=fundamental,
        requested_at=requested_at,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / ARTIFACT_FILENAME
    target.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(target)
    print(artifact["artifact_identity"])
    print(json.dumps(artifact["coverage"], sort_keys=True))
    print(json.dumps(artifact["market_state"], sort_keys=True))
    return target


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptive-path", default=str(DEFAULT_DESCRIPTIVE))
    parser.add_argument("--screening-path", default=str(DEFAULT_SCREENING))
    parser.add_argument("--fundamental-path", default=str(DEFAULT_FUNDAMENTAL))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT))
    parser.add_argument("--requested-at", default=None, help="Defaults to current UTC time if omitted.")
    args = parser.parse_args(argv)
    requested_at = args.requested_at
    if requested_at is None:
        from datetime import datetime, timezone
        requested_at = datetime.now(timezone.utc).isoformat()
    run(
        descriptive_path=Path(args.descriptive_path), screening_path=Path(args.screening_path),
        fundamental_path=Path(args.fundamental_path), out_dir=Path(args.out_dir), requested_at=requested_at,
    )


if __name__ == "__main__":
    main()
