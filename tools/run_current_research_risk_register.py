"""Build the retained, descriptive current research risk register."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from current_research_risk_register import build_artifact, replay

DEFAULTS = {
    "current_official_universe": ROOT / "operations-review/current-official-market-universe-integration-v1-20260824/current_official_market_universe_artifact.json",
    "historical_context": ROOT / "operations-review/market-wide-historical-research-context-v1-20260824/market_wide_historical_research_context_artifact.json",
    "leadership_context": ROOT / "operations-review/current-market-sector-leadership-context-v1-20260825/current_market_sector_leadership_context_artifact.json",
    "financial_context": ROOT / "operations-review/current-financial-momentum-context-v1/current_financial_momentum_context_artifact.json",
    "corporate_event_context": ROOT / "operations-review/current-corporate-event-context-v1/current_corporate_event_context_artifact.json",
    "valuation_context": ROOT / "operations-review/market-wide-current-valuation-research-scaleout-v1/market_wide_current_valuation_artifact.json",
}
DEFAULT_OUTPUT = ROOT / "operations-review/current-research-risk-register-v1/current_research_risk_register_artifact.json"

def _load(path: Path) -> dict:
    return json.loads(path.read_bytes().decode("utf-8"))

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name, path in DEFAULTS.items():
        parser.add_argument("--" + name.replace("_", "-"), default=str(path))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    artifact = build_artifact(**{name: _load(Path(getattr(args, name))) for name in DEFAULTS})
    replay(artifact)
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"])
    print(json.dumps(artifact["coverage"], sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
