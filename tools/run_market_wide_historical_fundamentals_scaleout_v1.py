"""Replay retained provider financial history over the current research universe."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
import market_wide_historical_fundamentals_scaleout as scaleout
def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--requested-at", default="2026-08-28T00:00:00+07:00")
    args = parser.parse_args(); artifact = scaleout.execute(requested_at=args.requested_at)
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps(artifact["coverage"], ensure_ascii=False, sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())
