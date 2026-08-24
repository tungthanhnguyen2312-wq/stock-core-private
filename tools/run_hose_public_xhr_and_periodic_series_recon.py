"""Retain one bounded, first-party public HOSE SPA evidence snapshot."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hose_public_xhr_and_periodic_series_recon import build, replay

# The initial local capture remains immutable; this reconciled destination is the
# authoritative producer output after the HNX-overlap denominator correction.
OUT = ROOT / "operations-review" / "hose-public-xhr-and-periodic-series-recon-v1-20260824-reconciled" / "hose_public_xhr_artifact.json"
UNIVERSE = ROOT / "operations-review" / "current-market-universe-breadth-foundation-v1-20260823" / "current_market_universe_breadth_foundation_artifact.json"
HNX_UNIVERSE = ROOT / "operations-review" / "hnx-enumerable-universe-kllh-event-and-disclosure-scaleout-v1-20260824" / "hnx_enumerable_universe_artifact.json"


if __name__ == "__main__":
    artifact = build(destination=OUT.parent, stocklookup_universe=UNIVERSE, hnx_universe=HNX_UNIVERSE)
    replay(artifact, destination=OUT.parent)
    data = json.dumps(artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if OUT.exists() and OUT.read_text(encoding="utf-8") != data:
        raise ValueError("IMMUTABLE_CONTENT_CONFLICT")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(data, encoding="utf-8")
    print(artifact["artifact_identity"])
