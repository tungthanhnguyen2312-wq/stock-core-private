from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from market_wide_implied_growth_reverse_valuation_research import build_artifact


def _load(path: Path | None) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path else {}


parser = argparse.ArgumentParser(description="Build retained-only implied-growth/reverse-valuation research artifact.")
parser.add_argument("--current-valuation-artifact", type=Path, required=True)
parser.add_argument("--valuation-proxy-artifact", type=Path, required=True)
parser.add_argument("--fundamental-artifact", type=Path)
parser.add_argument("--intrinsic-artifact", type=Path)
parser.add_argument("--as-of")
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
artifact = build_artifact(
    current_valuation=_load(args.current_valuation_artifact), valuation_proxy=_load(args.valuation_proxy_artifact),
    fundamental=_load(args.fundamental_artifact), intrinsic=_load(args.intrinsic_artifact), as_of=args.as_of,
)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"denominator": artifact["universe_denominator"], "coverage": artifact["coverage"]}, ensure_ascii=False))
