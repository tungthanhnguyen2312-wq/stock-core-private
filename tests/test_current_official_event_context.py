from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from current_official_event_context import build_artifact, replay
from market_wide_current_corporate_intelligence import build as build_ci

ROOT = Path(__file__).resolve().parents[1]; OPS = ROOT / "operations-review"
PATHS = {"official_universe": OPS / "current-official-market-universe-integration-v1-20260824/current_official_market_universe_artifact.json", "hnx": OPS / "hnx-enumerable-universe-kllh-event-and-disclosure-scaleout-v1-20260824/hnx_enumerable_universe_artifact.json", "hose": OPS / "hose-public-xhr-and-periodic-series-recon-v1-20260824-reconciled/hose_public_xhr_artifact.json", "descriptive": OPS / "market-wide-current-technical-coverage-scaleout-v1-20260823/market_wide_current_descriptive_research_artifact.json", "fundamental": OPS / "market-wide-current-fundamental-research-v1-20260823/market_wide_current_fundamental_research_artifact.json"}

@lru_cache(maxsize=1)
def _context():
    inputs = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in PATHS.items()}
    return build_artifact(official_universe=inputs["official_universe"], hnx=inputs["hnx"], hose=inputs["hose"], research_session=inputs["descriptive"]["session"])

def test_current_context_is_deterministic_and_never_infers_ex_dates():
    artifact = _context(); replay(artifact)
    assert artifact["current_official_universe"]["count"] == 1507
    assert artifact["coverage"]["event_context_records"] == len(artifact["all_current_universe_event_records"])
    assert len({event["event_id"] for event in artifact["all_current_universe_event_records"]}) == artifact["coverage"]["event_context_records"]
    assert all(event["event_state"] in {"DATE_INCOMPLETE", "UNKNOWN"} for event in artifact["all_current_universe_event_records"] if event["ex_date"] is None)
    assert all(event["publication_availability"] == "UNKNOWN_NOT_RETAINED" for event in artifact["all_current_universe_event_records"])

def test_ci_adapter_preserves_event_facts_without_promoting_pit():
    context = _context(); descriptive = json.loads(PATHS["descriptive"].read_text(encoding="utf-8")); fundamental = json.loads(PATHS["fundamental"].read_text(encoding="utf-8"))
    ci = build_ci(descriptive=descriptive, fundamental=fundamental, session=descriptive["session"], root=ROOT, official_event_context=context)
    assert ci["coverage"]["any_intelligence_coverage"] > 3
    current = [event for row in ci["records"].values() for event in row["events"] if event.get("source_event_id")]
    assert current and all(event["pit_suitability"] == "LIMITED_PUBLICATION_TIME_UNKNOWN" for event in current)
    assert all(event["ex_date"] != event["record_date"] or event["ex_date"] is None for event in current)
