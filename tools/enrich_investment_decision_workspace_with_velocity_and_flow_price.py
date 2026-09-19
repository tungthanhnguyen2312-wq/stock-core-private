"""Additively attach Signal Velocity V1.2 / Flow-Price Divergence V1 presentation fields to an
already-materialized investment_decision_workspace_projection/v1 artifact, then re-stamp its
content identity.

Why this exists: this session's full canonical_current_product_projections pipeline requires
reconstructing every registry/supplementary input that produced the real 2026-09-18 workspace
artifact. That artifact already exists, already-retained, at its normal Daily Research Session
Operation path. This tool performs the exact same per-ticker join
canonical_current_product_projections.materialize_current_investment_decision_workspace now
performs for a fresh run (via investment_decision_workspace_projection.build_ticker_card's two
new optional fields), applied to the existing cards instead of rebuilding them from scratch. No
new analytical computation happens here -- see velocity_flow_price_presentation_projection.py.

No network. No live DNSE acquisition. Every input is already-retained.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT))

import velocity_flow_price_presentation_projection as velocity_flow_price  # noqa: E402
from investment_decision_workspace_projection import content_identity  # noqa: E402
from owner_research_focus import load_owner_research_focus  # noqa: E402


def enrich(*, workspace: dict[str, Any], signal_velocity_artifact: dict[str, Any] | None,
           flow_price_artifact: dict[str, Any] | None, flow_cohort_tickers: frozenset[str]) -> dict[str, Any]:
    if workspace.get("contract_version") != "investment_decision_workspace_projection/v1":
        raise ValueError("WORKSPACE_CONTRACT_UNSUPPORTED")
    as_of_session = workspace.get("as_of_session")
    cards = workspace.get("cards") or {}
    for ticker, card in cards.items():
        card["signal_velocity"] = velocity_flow_price.signal_velocity_view(
            ticker=ticker, artifact=signal_velocity_artifact, as_of_session=as_of_session,
        )
        card["flow_price"] = velocity_flow_price.flow_price_view(
            ticker=ticker, artifact=flow_price_artifact, cohort_tickers=flow_cohort_tickers,
        )
    source_artifacts = dict(workspace.get("source_artifacts") or {})
    source_artifacts["signal_velocity"] = (signal_velocity_artifact or {}).get("artifact_identity")
    source_artifacts["flow_price_divergence_shadow"] = (flow_price_artifact or {}).get("artifact_identity")
    workspace["source_artifacts"] = source_artifacts
    workspace.update(content_identity(workspace))
    return workspace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--signal-velocity", required=True, type=Path)
    parser.add_argument("--flow-price", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    workspace = json.loads(args.workspace.read_text(encoding="utf-8"))
    signal_velocity_artifact = json.loads(args.signal_velocity.read_text(encoding="utf-8"))
    flow_price_artifact = json.loads(args.flow_price.read_text(encoding="utf-8"))
    cohort = velocity_flow_price.cohort_tickers_from_owner_focus(load_owner_research_focus())

    enriched = enrich(
        workspace=workspace, signal_velocity_artifact=signal_velocity_artifact,
        flow_price_artifact=flow_price_artifact, flow_cohort_tickers=cohort,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(enriched, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    velocity_states = {}
    flow_relationships = {}
    for card in enriched["cards"].values():
        velocity_states[card["signal_velocity"]["overall_transition_state"]] = velocity_states.get(card["signal_velocity"]["overall_transition_state"], 0) + 1
        flow_relationships[card["flow_price"]["relationship"]] = flow_relationships.get(card["flow_price"]["relationship"], 0) + 1
    print(json.dumps({
        "artifact_identity": enriched["artifact_identity"],
        "ticker_count": len(enriched["cards"]),
        "signal_velocity_distribution": velocity_states,
        "flow_price_relationship_distribution": flow_relationships,
        "flow_cohort_size": len(cohort),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
