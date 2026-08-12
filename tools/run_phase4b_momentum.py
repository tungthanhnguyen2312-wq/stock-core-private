"""Run the retained-data Phase 4B Momentum screen; it performs no provider calls."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from momentum_screening_v1 import evaluate_momentum, load_phase3_historical, write_momentum_artifacts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase3-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--as-of")
    parser.add_argument("--top-n", type=int, default=25)
    args = parser.parse_args()
    run = evaluate_momentum(load_phase3_historical(args.phase3_root), as_of=args.as_of)
    paths = write_momentum_artifacts(run, args.output_root, top_n=args.top_n)
    print(run.report)
    print({key: str(value) for key, value in paths.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
