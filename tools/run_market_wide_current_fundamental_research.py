"""Materialize the market_wide_current_fundamental_research artifact to disk.

Foreground, offline, deterministic given the already-retained P3-F10/P3-F13 inputs: no network
call, no new evidence acquisition, no source-route discovery. Safe to rerun at any time; the
result only changes if the underlying retained evidence (official facts, provider retention,
approved source registry) changes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_wide_current_fundamental_research import execute  # noqa: E402

DEFAULT_OUT = ROOT / "operations-review" / "market-wide-current-fundamental-research-v1-20260823"
ARTIFACT_FILENAME = "market_wide_current_fundamental_research_artifact.json"


def run(out_dir: Path, *, requested_at: str | None = None) -> Path:
    artifact = execute(requested_at=requested_at)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / ARTIFACT_FILENAME
    target.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(target)
    print(artifact["artifact_identity"])
    print(json.dumps(artifact["coverage"], sort_keys=True))
    return target


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT))
    parser.add_argument("--requested-at", help="Optional fixed timestamp for deterministic offline replay.")
    args = parser.parse_args(argv)
    run(Path(args.out_dir), requested_at=args.requested_at)


if __name__ == "__main__":
    main()
