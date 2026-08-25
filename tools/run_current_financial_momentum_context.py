"""Build the current financial-momentum research context from retained artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_financial_momentum_context import build_artifact, replay


DEFAULT_OFFICIAL_UNIVERSE = ROOT / "operations-review/current-official-market-universe-integration-v1-20260824/current_official_market_universe_artifact.json"
DEFAULT_FUNDAMENTAL = ROOT / "operations-review/market-wide-current-fundamental-research-v1-20260823/market_wide_current_fundamental_research_artifact.json"
DEFAULT_DESCRIPTIVE = ROOT / "operations-review/market-wide-current-descriptive-research-v1-20260824/market_wide_current_descriptive_research_artifact.json"
DEFAULT_OUTPUT = ROOT / "operations-review/current-financial-momentum-context-v1/current_financial_momentum_context_artifact.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-official-universe-artifact", default=str(DEFAULT_OFFICIAL_UNIVERSE))
    parser.add_argument("--current-fundamental-artifact", default=str(DEFAULT_FUNDAMENTAL))
    parser.add_argument("--current-descriptive-artifact", default=str(DEFAULT_DESCRIPTIVE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)

    descriptive_path = Path(args.current_descriptive_artifact)
    artifact = build_artifact(
        current_official_universe=_load(Path(args.current_official_universe_artifact)),
        current_fundamental=_load(Path(args.current_fundamental_artifact)),
        current_descriptive=_load(descriptive_path) if descriptive_path.is_file() else None,
    )
    replay(artifact)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"])
    print(json.dumps(artifact["coverage"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
