"""Focused governed correction coverage for HPG consolidated parent earnings."""
from __future__ import annotations

import json
from pathlib import Path

from financial_statement_template_recognizer import net_income_line_codes_for_scope
from official_financial_pdf_page_evidence import build_artifact
from official_financial_structural_table import reconcile_against_existing_panel
import p3f13_official_financial_evidence_scaleout as p3f13


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "operations-review" / "governed-official-evidence-v1" / "data" / "official-evidence" / "manifest.json"
CITATIONS = ROOT / "operations-review" / "governed-official-evidence-v1" / "data" / "official-evidence" / "financial_identity_citations.jsonl"


def _hpg_facts(panel: dict) -> dict[str, dict]:
    issuer = next(issuer for issuer in panel["issuers"] if issuer["issuer_identity"]["ticker"] == "HPG")
    return {fact["reporting_period"]: fact for fact in issuer["facts"] if fact["canonical_metric"] == "net_income"}


def test_consolidated_contract_requires_parent_line_61_and_keeps_narrow_separate_fallback():
    assert net_income_line_codes_for_scope("consolidated") == ("61",)
    assert net_income_line_codes_for_scope(None) == ("61",)
    assert net_income_line_codes_for_scope("separate") == ("61", "60")
    assert net_income_line_codes_for_scope("unconsolidated") == ("61", "60")


def test_active_hpg_facts_are_corrected_with_coherent_line_61_lineage_and_frozen_history_is_unchanged():
    artifact = p3f13.execute()
    corrections = {record["reporting_period"]: record for record in artifact["canonical_identity_corrections"]}
    facts = _hpg_facts(artifact["refreshed_panel_data"])
    expected = {
        "2022": (8_444_429_054_516, 8_483_510_554_031, 107, "1f33cabb35a9a4bc7fc6c0eed7c89a80fda8258d61f8d4241669712cc9d94220"),
        "2023": (6_800_388_315_081, 6_835_064_334_356, 89, "d49913fd44b2f7e2fe5accc17d0ab766b363d075e7b15069aed9d00b2c4dc573"),
    }
    for period, (old_value, corrected_value, page, citation_id) in expected.items():
        correction, fact = corrections[period], facts[period]
        assert (correction["old_value"], correction["correct_value"]) == (old_value, corrected_value)
        assert (fact["value"], fact["currency"], fact["unit_scale"]) == (corrected_value, "VND", 1)
        assert (fact["source_lineage"]["source_page"], fact["source_lineage"]["line_code"], fact["source_lineage"]["citation_id"]) == (page, "61", citation_id)
        assert fact["source_lineage"]["raw_row_label"] == "Shareholders of the parent company"
        assert fact["source_lineage"]["canonical_identity_correction"]["superseded_citation_id"] == correction["superseded_citation_id"]
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
    records = reconcile_against_existing_panel(_hpg_structural_candidates(), p3f13.execute()["refreshed_panel_data"])
    assert len(records) == 6
    assert {record["classification"] for record in records} == {"EXACT_MATCH"}
    assert all(not record["eligible_for_ingress"] for record in records)


def test_hpg_derived_research_uses_corrected_parent_earnings():
    readiness = p3f13.execute()["refreshed_fundamental_readiness"]
    issuer = next(row for row in readiness["issuer_research_readiness"] if row["issuer_identity"]["ticker"] == "HPG")
    metrics = {(metric["metric_id"], tuple(metric["periods_used"])): metric["value"] for metric in issuer["metrics"]}
    assert metrics[("earnings_growth_yoy", ("2022", "2023"))] == -0.1943118
    assert metrics[("net_margin", ("2022",))] == 0.0599926
    assert metrics[("net_margin", ("2023",))] == 0.0574602
    assert metrics[("cash_flow_to_earnings", ("2022",))] == 1.44723539
    assert metrics[("cash_flow_to_earnings", ("2023",))] == 1.26451345
