import json
from pathlib import Path

import pytest

from market_wide_current_corporate_intelligence import build, content_identity, prospective_context

ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = ROOT / "operations-review"


def _artifact():
    descriptive = json.loads((OPERATIONS / "market-wide-current-technical-coverage-scaleout-v1-20260823/market_wide_current_descriptive_research_artifact.json").read_text(encoding="utf-8"))
    fundamental = json.loads((OPERATIONS / "market-wide-current-fundamental-research-v1-20260823/market_wide_current_fundamental_research_artifact.json").read_text(encoding="utf-8"))
    return build(descriptive=descriptive, fundamental=fundamental, session="2026-08-21", root=ROOT)


def test_materializes_full_universe_with_retained_event_lifecycle_boundaries():
    artifact = _artifact()
    assert content_identity(artifact)["artifact_sha256"] == artifact["artifact_sha256"]
    assert artifact["coverage"]["universe_count"] == 1683
    assert artifact["coverage"]["any_intelligence_coverage"] == 3
    hpg, vcb, vnm = (artifact["records"][ticker] for ticker in ("HPG", "VCB", "VNM"))
    assert hpg["intelligence_disposition"] == "CURRENT_INTELLIGENCE_AVAILABLE"
    assert vnm["intelligence_disposition"] == "HISTORICAL_INTELLIGENCE_ONLY"
    event = vcb["events"][0]
    assert event["status"] == "APPROVED" and event["effective_date"] is None and event["record_date"] == "2025-03-13"
    assert event["ex_date"] is None and "Approved/planned issuance is not executed issuance." in event["limitations"]


def test_event_and_catalyst_layers_stay_separate_and_prospective_ids_are_stable():
    artifact = _artifact(); hpg = artifact["records"]["HPG"]
    assert hpg["facts"][0]["fact_id"] and hpg["events"][0]["event_id"]
    assert hpg["catalyst_research"]["observed_catalysts"][0]["direction"] == "DIRECTION_UNCLEAR"
    assert not artifact["records"]["AAA"]["events"]
    first, second = prospective_context(artifact), prospective_context(_artifact())
    assert first["snapshot_id"] == second["snapshot_id"] and first["cohort_count"] == 1683


def test_mismatched_session_fails_closed():
    descriptive = json.loads((OPERATIONS / "market-wide-current-technical-coverage-scaleout-v1-20260823/market_wide_current_descriptive_research_artifact.json").read_text(encoding="utf-8"))
    fundamental = json.loads((OPERATIONS / "market-wide-current-fundamental-research-v1-20260823/market_wide_current_fundamental_research_artifact.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="CORPORATE_INTELLIGENCE_DESCRIPTIVE_SESSION"):
        build(descriptive=descriptive, fundamental=fundamental, session="2026-08-20", root=ROOT)
