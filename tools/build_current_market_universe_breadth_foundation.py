"""Build the retained current-universe membership and session-observability projection."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from current_market_universe_breadth_foundation import build_artifact


DEFAULT_QUALIFICATION = ROOT / "operations-review/market-wide-current-research-universe-qualification-v1-20260823/market_wide_current_research_universe_artifact.json"
DEFAULT_SNAPSHOT = ROOT / "operations-review/p3f9b-market-wide-exact-session-scaleout-20260821/p3f9b_mva_exact_session_snapshot.json"
DEFAULT_OUTPUT = ROOT / "operations-review/current-market-universe-breadth-foundation-v1-20260823/current_market_universe_breadth_foundation_artifact.json"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qualification-artifact", default=str(DEFAULT_QUALIFICATION))
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    qualification = json.loads(Path(args.qualification_artifact).read_text(encoding="utf-8"))
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    artifact = build_artifact(qualification_artifact=qualification, canonical_snapshot=snapshot)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"])


if __name__ == "__main__":
    main()
