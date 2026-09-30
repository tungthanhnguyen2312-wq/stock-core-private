"""Focused governed correction coverage for HPG consolidated parent earnings."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from financial_statement_template_recognizer import net_income_line_codes_for_scope
from official_financial_pdf_page_evidence import build_artifact
from official_financial_structural_table import reconcile_against_existing_panel
import p3f13_official_financial_evidence_scaleout as p3f13


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "operations-review" / "governed-official-evidence-v1" / "data" / "official-evidence" / "manifest.json"
CITATIONS = ROOT / "operations-review" / "governed-official-evidence-v1" / "data" / "official-evidence" / "financial_identity_citations.jsonl"


def _hpg_facts(panel: dict, metric: str = "net_income") -> dict[str, dict]:
    issuer = next(issuer for issuer in panel["issuers"] if issuer["issuer_identity"]["ticker"] == "HPG")
    return {fact["reporting_period"]: fact for fact in issuer["facts"] if fact["canonical_metric"] == metric}


def test_consolidated_contract_requires_total_line_60_for_net_income():
    assert net_income_line_codes_for_scope("consolidated") == ("60",)
    assert net_income_line_codes_for_scope(None) == ("60",)
    assert net_income_line_codes_for_scope("separate") == ("60",)
    assert net_income_line_codes_for_scope("unconsolidated") == ("60",)


def test_active_hpg_facts_are_corrected_with_coherent_line_61_lineage_and_frozen_history_is_unchanged():
    if not p3f13.DEFAULT_P3F10.is_file() or not CITATIONS.is_file():
        pytest.skip("retained p3f13 evidence is not present in this worktree")
    artifact = p3f13.execute()
    corrections = {record["reporting_period"]: record for record in artifact["canonical_identity_corrections"]}
    totals = _hpg_facts(artifact["refreshed_panel_data"], "net_income")
    attributable = _hpg_facts(artifact["refreshed_panel_data"], "attributable_net_income")
    expected = {
        "2022": (8_444_429_054_516, 8_483_510_554_031, 107, "1f33cabb35a9a4bc7fc6c0eed7c89a80fda8258d61f8d4241669712cc9d94220"),
        "2023": (6_800_388_315_081, 6_835_064_334_356, 89, "d49913fd44b2f7e2fe5accc17d0ab766b363d075e7b15069aed9d00b2c4dc573"),
    }
    for period, (total_value, parent_value, page, citation_id) in expected.items():
        correction, total, parent = corrections[period], totals[period], attributable[period]
        assert (correction["old_value"], correction["correct_value"]) == (total_value, parent_value)
        assert correction["status"] == "HISTORICAL_PROVENANCE"
        assert (total["value"], total["currency"], total["unit_scale"]) == (total_value, "VND", 1)
        assert (parent["value"], parent["source_lineage"]["line_code"]) == (parent_value, "61")
        assert parent["source_lineage"]["source_page"] == page
        assert parent["source_lineage"]["citation_id"] == citation_id
    frozen = CITATIONS.read_text(encoding="utf-8")
    assert '"value": 8444429054516' in frozen and '"value": 6800388315081' in frozen


def test_actual_consolidated_line_60_61_62_accounting_identity_is_exact():
    assert 8_483_510_554_031 + (-39_081_499_515) == 8_444_429_054_516
    assert 6_835_064_334_356 + (-34_676_019_275) == 6_800_388_315_081


def _hpg_structural_candidates() -> list[dict]:
    if hasattr(_hpg_structural_candidates, "value"):
        return _hpg_structural_candidates.value  # type: ignore[attr-defined]
    records = json.loads(MANIFEST.read_text(encoding="utf-8"))["records"]
    candidates = []
    for row in records:
        if row["sha256"].startswith(("44919df68306", "4fb8f8e0f8dd")):
            document = {"document_id": row["document_id"], "ticker": row["ticker"], "sha256": row["sha256"],
                        "official_url": row["source_url"], "retrieved_at": row["observed_at"], "entity_type": "corporate"}
            candidates.extend(build_artifact(document=document, path=ROOT / row["archive_document_path"])["fact_candidates"])
    _hpg_structural_candidates.value = candidates  # type: ignore[attr-defined]
    return candidates


def test_hpg_geometry_reconciliation_is_now_exact_and_duplicate_only():
    if not MANIFEST.is_file() or not p3f13.DEFAULT_P3F10.is_file():
        pytest.skip("retained HPG structural evidence is not present in this worktree")
    records = reconcile_against_existing_panel(_hpg_structural_candidates(), p3f13.execute()["refreshed_panel_data"])
    assert len(records) == 6
    assert {record["classification"] for record in records} == {"EXACT_MATCH"}
    assert all(not record["eligible_for_ingress"] for record in records)


def test_hpg_derived_research_uses_total_net_income():
    if not p3f13.DEFAULT_P3F10.is_file():
        pytest.skip("retained p3f13 evidence is not present in this worktree")
    artifact = p3f13.execute()
    readiness = artifact["refreshed_fundamental_readiness"]
    issuer = next(row for row in readiness["issuer_research_readiness"] if row["issuer_identity"]["ticker"] == "HPG")
    metrics = {(metric["metric_id"], tuple(metric["periods_used"])): metric["value"] for metric in issuer["metrics"]}
    totals = _hpg_facts(artifact["refreshed_panel_data"], "net_income")
    assert totals["2022"]["value"] == 8_444_429_054_516
    assert totals["2023"]["value"] == 6_800_388_315_081
    yoy = (6_800_388_315_081 - 8_444_429_054_516) / abs(8_444_429_054_516)
    assert abs(metrics[("earnings_growth_yoy", ("2022", "2023"))] - yoy) < 1e-9
    assert metrics[("net_margin", ("2022",))] != 0.0599926
    assert metrics[("cash_flow_to_earnings", ("2022",))] != 1.44723539
