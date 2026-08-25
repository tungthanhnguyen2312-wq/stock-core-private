"""Build the retained, descriptive current research scenario framework."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from current_research_risk_register import build_artifact as build_risk_register
from current_research_scenario_context import build_artifact, replay

DEFAULTS = {
    "current_official_universe": ROOT / "operations-review/current-official-market-universe-integration-v1-20260824/current_official_market_universe_artifact.json",
    "tactical": ROOT / "operations-review/watchlist-tactical-entry-decision-v1-20260823/watchlist_tactical_entry_classifier_artifact.json",
    "opportunity": ROOT / "operations-review/current-opportunity-prioritization-v1-20260824/current_opportunity_prioritization_artifact.json",
    "historical_context": ROOT / "operations-review/market-wide-historical-research-context-v1-20260824/market_wide_historical_research_context_artifact.json",
    "leadership_context": ROOT / "operations-review/current-market-sector-leadership-context-v1-20260825/current_market_sector_leadership_context_artifact.json",
    "financial_context": ROOT / "operations-review/current-financial-momentum-context-v1/current_financial_momentum_context_artifact.json",
    "corporate_event_context": ROOT / "operations-review/current-corporate-event-context-v1/current_corporate_event_context_artifact.json",
    "valuation_context": ROOT / "operations-review/market-wide-current-valuation-research-scaleout-v1/market_wide_current_valuation_artifact.json",
}
DEFAULT_OUTPUT = ROOT / "operations-review/current-research-scenario-framework-v1/current_research_scenario_context_artifact.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_bytes().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name, path in DEFAULTS.items():
        parser.add_argument("--" + name.replace("_", "-"), default=str(path))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    loaded = {name: _load(Path(getattr(args, name))) for name in DEFAULTS}
    risk_register = build_risk_register(
        current_official_universe=loaded["current_official_universe"],
        historical_context=loaded["historical_context"],
        leadership_context=loaded["leadership_context"],
        financial_context=loaded["financial_context"],
        corporate_event_context=loaded["corporate_event_context"],
        valuation_context=loaded["valuation_context"],
    )
    artifact = build_artifact(risk_register=risk_register, **loaded)
    replay(artifact)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"])
    print(json.dumps(artifact["coverage"], sort_keys=True))
    print(json.dumps({
        name: {"ticker": row["ticker"], "present": row["present"]}
        for name, row in artifact["validation"]["representative_cases"].items()
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
