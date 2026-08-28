"""Write the deterministic FUNDAMENTAL_PLUS_MARKET_OPPORTUNITY_RANKING_V1 artifact."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import fundamental_market_opportunity_ranking as ranking


parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
artifact = ranking.execute()
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(artifact["coverage"], sort_keys=True))
