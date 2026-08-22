"""Produce the local deterministic evidence-gated research decision packet."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evidence_gated_research_decision_workflow import build


INPUTS = {
    "product": "operations-review/mva-daily-investment-research-20260820/mva_daily_investment_research_artifact.json",
    "eligibility": "operations-review/strategy-research-eligibility-v1-20260820/strategy_research_eligibility_artifact.json",
    "setups": "operations-review/research-setup-classification-v1-20260820/research_setup_classification_artifact.json",
    "scenarios": "operations-review/expectations-scenario-research-v1-20260820/expectations_scenario_research_artifact.json",
    "events": "operations-review/catalyst-event-research-context-v1-20260820/catalyst_event_research_context_artifact.json",
    "downside": "operations-review/downside-uncertainty-research-context-v2-20260820/downside_uncertainty_research_context_artifact.json",
    "market": "operations-review/market-regime-breadth-context-v1-20260820/market_regime_breadth_context_artifact.json",
    "mva_bundle": "operations-review/p3f9b-market-wide-exact-session-scaleout-20260820/p3f7_mva_daily_research_bundle_exact_session.json",
    "official_financial_panel": "operations-review/p3f13-official-financial-evidence-scaleout-20260820/p3f13_official_financial_evidence_scaleout_artifact.json",
    "fundamental_readiness": "operations-review/p3b-fundamental-research-readiness-20260820/p3b_fundamental_research_readiness_artifact.json",
}


def inputs() -> dict[str, dict]:
    return {name: json.loads((ROOT / relative).read_text(encoding="utf-8")) for name, relative in INPUTS.items()}


def run() -> dict:
    return build(**inputs())


if __name__ == "__main__":
    artifact = run()
    output = ROOT / "operations-review/evidence-gated-research-decision-workflow-v1-20260822/evidence_gated_research_decision_workflow_artifact.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"])
