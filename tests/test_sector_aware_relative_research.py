import json
from pathlib import Path

from export_ai_bundle import attach_sector_aware_relative_research
from sector_aware_relative_research import build, content_identity


ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = ROOT / "operations-review"


def _inputs():
    paths = {
        "descriptive": OPERATIONS / "market-wide-current-descriptive-research-v1-20260823/market_wide_current_descriptive_research_artifact.json",
        "tactical": OPERATIONS / "watchlist-tactical-entry-decision-v1-20260823/watchlist_tactical_entry_classifier_artifact.json",
        "fundamental": OPERATIONS / "market-wide-current-fundamental-research-v1-20260823/market_wide_current_fundamental_research_artifact.json",
        "valuation": OPERATIONS / "market-wide-current-valuation-v1-20260824/market_wide_current_valuation_artifact.json",
    }
    return {name: json.loads(path.read_text(encoding="utf-8")) for name, path in paths.items()}


def test_refined_peer_groups_are_deterministic_and_preserve_boundaries():
    artifact = build(**_inputs())
    assert content_identity(artifact)["artifact_sha256"] == artifact["artifact_sha256"]
    assert artifact["coverage"]["candidate_universe"] == 1683
    assert artifact["coverage"]["valuation_peer_available"] == 0
    assert any(key.startswith("CORPORATE_INDUSTRY:") for key in artifact["peer_groups"])
    assert all(record["is_actionable"] is False for record in artifact["records"].values())
    assert all(record["valuation_peer_context"]["status"] == "VALUATION_PEER_CONTEXT_UNAVAILABLE" for record in artifact["records"].values())


def test_human_use_blocks_cover_retained_watchlist_and_preopen_sets():
    artifact = build(**_inputs())
    blocks = artifact["human_use_research_blocks"]
    assert len(blocks["watchlist"]) == 11
    assert len(blocks["preopen_47"]) == 47
    assert len([key for key in blocks["representative_peer_groups"] if key.startswith("CORPORATE_INDUSTRY:")]) >= 4
    assert all("what_is_unusual" in block and "authority_limitations" in block for block in blocks["watchlist"])


def test_opt_in_bundle_attach_preserves_source_identity_verbatim():
    artifact_path = OPERATIONS / "sector-aware-relative-research-v1-20260824/sector_aware_relative_research_artifact.json"
    bundle = {"AAA": {}}
    attach_sector_aware_relative_research(bundle, True, str(artifact_path))
    attached = bundle["AAA"]["sector_aware_relative_research"]
    assert attached["ticker"] == "AAA"
    assert attached["source_artifact_identity"].startswith("sector_aware_relative_research:")
    assert attached["is_actionable"] is False
