"""Retained-manifest and generic discovery contracts for the owner-focus OCR batch."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import inspect

import owner_focus_image_only_corporate_ocr_batch as batch
from owner_focus_image_only_corporate_ocr_batch import BATCH_TICKERS, CORE_METRICS, DISCOVERY_CONFIG, DISCOVERY_FALLBACK_CONFIG, build_batch_manifest


ROOT = Path(__file__).resolve().parents[1]


def _inputs():
    inventory = json.loads((ROOT / "operations-review" / "retained-official-financial-pdf-extraction-scaleout-v1-20260827" / "artifact.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "operations-review" / "governed-official-evidence-v1" / "official_document_acquisition_manifest.json").read_text(encoding="utf-8"))
    owner = {"records": [{"ticker": ticker, "entity_type": "corporate", "primary_blocker": "CURRENT_PRIMARY_CORE_METRIC_NOT_OFFICIAL_QUALIFIED"} for ticker in BATCH_TICKERS]}
    return inventory, manifest, owner


def test_exact_target_manifest_is_deterministic_and_complete():
    inventory, official, owner = _inputs()
    first = build_batch_manifest(inventory=inventory, official_manifest=official, owner_focus_artifact=owner)
    second = build_batch_manifest(inventory=inventory, official_manifest=official, owner_focus_artifact=owner)
    assert first == second
    assert [(row["ticker"], row["reporting_period"]) for row in first["documents"]] == [
        ("PNJ", "2024"), ("PNJ", "2025"), ("PVD", "2022"), ("PVD", "2023"), ("PVD", "2024"), ("NVL", "2024"), ("POW", "2024"),
    ]
    assert first["eligible_document_count"] == 7
    assert all(row["terminal_manifest_disposition"] == "ELIGIBLE" for row in first["documents"])
    assert first["residual_checks"] == {"manifest_records": 7, "terminal_records": 7, "residual": 0, "residual_zero": True, "target_tickers_exact": True, "fpt_not_new_target": True}


def test_batch_contract_excludes_fpt_sector_boundaries_and_acquisition_fixtures():
    inventory, official, owner = _inputs()
    artifact = build_batch_manifest(inventory=inventory, official_manifest=official, owner_focus_artifact=owner)
    tickers = {row["ticker"] for row in artifact["documents"]}
    assert tickers == set(BATCH_TICKERS)
    assert not tickers & {"FPT", "SSI", "EVF", "HPG", "PAN", "VNM", "AAA", "ABS"}
    assert artifact["regression_only_tickers"] == ["FPT"]
    assert set(CORE_METRICS) >= {"revenue", "net_income", "total_interest_bearing_debt", "operating_cash_flow"}
    assert DISCOVERY_CONFIG["purpose"] == "STATEMENT_ROUTING_ONLY_NOT_FACT_EXTRACTION"


class _Pixmap:
    def __init__(self, number):
        self.number = number

    def tobytes(self, _format):
        return str(self.number).encode("ascii")


class _Page:
    def __init__(self, number):
        self.number = number

    def get_pixmap(self, **_kwargs):
        return _Pixmap(self.number)


class _Document:
    def __getitem__(self, index):
        return _Page(index + 1)

    def close(self):
        pass


def _discover(monkeypatch, tmp_path, routes, page_count=20):
    source = tmp_path / "retained.pdf"
    source.write_bytes(b"fixture")
    calls = []

    def fake_run(_args, *, input, **_kwargs):
        number = int(input.decode("ascii"))
        calls.append(number)
        return SimpleNamespace(stdout=routes.get(number, "unreadable decorative page").encode("utf-8"))

    monkeypatch.setattr(batch, "sha256_file", lambda _path: "fixture-sha")
    monkeypatch.setattr(batch.fitz, "open", lambda _path: _Document())
    monkeypatch.setattr(batch.subprocess, "run", fake_run)
    result = batch.discover_statement_pages({"retained_path": source.name, "document_sha256": "fixture-sha", "page_count": page_count}, evidence_root=tmp_path)
    return result, calls


def test_discovery_stops_after_all_three_statement_families_are_independently_identified(monkeypatch, tmp_path):
    result, calls = _discover(monkeypatch, tmp_path, {2: "Balance sheet", 4: "Income statement", 6: "Cash flow", 9: "Balance sheet"})
    assert calls == [1, 2, 3, 4, 5, 6]
    assert [page["page_number"] for page in result["statement_pages"]] == [2, 4, 6]
    assert batch._discovery_complete(result["statement_pages"])


def test_discovery_preserves_order_and_does_not_stop_on_weak_or_missing_family(monkeypatch, tmp_path):
    result, calls = _discover(monkeypatch, tmp_path, {2: "Balance sheet", 3: "Balance sheet", 5: "Income statement", 8: "cash flow"}, page_count=8)
    assert calls == list(range(1, 9))
    assert [page["page_number"] for page in result["statement_pages"]] == [2, 3, 5, 8]
    assert result["statement_pages"][1]["statement_families"] == ["balance_sheet"]


def test_discovery_scans_to_cap_without_fallback_when_cheap_path_has_a_valid_candidate(monkeypatch, tmp_path):
    result, calls = _discover(monkeypatch, tmp_path, {2: "Balance sheet", 6: "Income statement"})
    assert calls == list(range(1, DISCOVERY_CONFIG["max_front_pages"] + 1))
    assert result["fallback_used"] is False
    assert not batch._discovery_complete(result["statement_pages"])


def test_primary_failure_uses_strict_high_resolution_fallback_and_recovers(monkeypatch, tmp_path):
    # The fake output distinguishes the second bounded pass by invocation count.
    source = tmp_path / "retained.pdf"; source.write_bytes(b"fixture")
    calls = []
    def fake_run(_args, *, input, **_kwargs):
        page = int(input.decode("ascii")); calls.append(page)
        if len(calls) <= 8:
            return SimpleNamespace(stdout=b"unreadable")
        fallback = {2: "ISSUED UNDER CIRCULAR FORM B 01-DN/HN CONSOLIDATED BALANCE SHEET", 4: "ISSUED UNDER CIRCULAR FORM B 02-DN/HN CONSOLIDATED INCOME STATEMENT", 6: "ISSUED UNDER CIRCULAR FORM B 03-DN/HN CONSOLIDATED CASH FLOW STATEMENT"}
        return SimpleNamespace(stdout=fallback.get(page, "notes to financial statements").encode())
    monkeypatch.setattr(batch, "sha256_file", lambda _path: "fixture-sha")
    monkeypatch.setattr(batch.fitz, "open", lambda _path: _Document())
    monkeypatch.setattr(batch.subprocess, "run", fake_run)
    result = batch.discover_statement_pages({"retained_path": source.name, "document_sha256": "fixture-sha", "page_count": 8}, evidence_root=tmp_path)
    assert result["fallback_used"] is True
    assert [row["page_number"] for row in result["statement_pages"]] == [2, 4, 6]
    assert [row["page_count"] for row in result["routing_passes"]] == [8, 6]


def test_empty_primary_still_blocks_after_one_finite_fallback(monkeypatch, tmp_path):
    result, calls = _discover(monkeypatch, tmp_path, {})
    assert result["fallback_used"] is True
    assert calls == list(range(1, DISCOVERY_CONFIG["max_front_pages"] + 1)) * 2
    assert result["statement_pages"] == []


def test_fallback_does_not_run_when_cheap_path_succeeds(monkeypatch, tmp_path):
    result, calls = _discover(monkeypatch, tmp_path, {2: "Balance sheet", 4: "Income statement", 6: "Cash flow"})
    assert result["fallback_used"] is False
    assert len(result["routing_passes"]) == 1 and calls == [1, 2, 3, 4, 5, 6]


def test_routing_identity_is_deterministic(monkeypatch, tmp_path):
    first, _ = _discover(monkeypatch, tmp_path, {2: "Balance sheet", 4: "Income statement", 6: "Cash flow"})
    second, _ = _discover(monkeypatch, tmp_path, {2: "Balance sheet", 4: "Income statement", 6: "Cash flow"})
    assert first["discovery_id"] == second["discovery_id"]


def test_strict_fallback_recognizes_english_and_vietnamese_circular_200_forms():
    assert batch._statement_families_from_text("ISSUED UNDER CIRCULAR FORM B 01-DN/HN CONSOLIDATED BALANCE SHEET", requires_circular_issuance_attestation=True) == ["balance_sheet"]
    assert batch._statement_families_from_text("BAN HANH THEO THONG TU MAU SO B 02-DN/HN BAO CAO KET QUA HOAT DONG KINH DOANH", requires_circular_issuance_attestation=True) == ["income_statement"]


def test_strict_fallback_rejects_notes_and_front_matter_mentions():
    assert batch._statement_families_from_text("TABLE OF CONTENTS FORM B 01-DN/HN CONSOLIDATED BALANCE SHEET INCOME STATEMENT CASH FLOW", requires_circular_issuance_attestation=True) == []
    assert batch._statement_families_from_text("FORM B 09-DN/HN NOTES TO THE FINANCIAL STATEMENTS balance sheet income statement", requires_circular_issuance_attestation=True) == []


def test_no_fuzzy_heading_broadening_or_ticker_specific_fallback_logic():
    source = inspect.getsource(batch._statement_families_from_text) + inspect.getsource(batch._scan_discovery_pass)
    assert "SequenceMatcher" not in source and "edit_distance" not in source and "ticker ==" not in source
    assert "PVD" not in source and "POW" not in source


def test_fallback_budget_is_finite_and_empty_ocr_fails_closed():
    assert DISCOVERY_CONFIG["max_front_pages"] == DISCOVERY_FALLBACK_CONFIG["max_front_pages"] == 20
    assert DISCOVERY_CONFIG["dpi"] == 50 and DISCOVERY_FALLBACK_CONFIG["dpi"] == 100
    assert DISCOVERY_FALLBACK_CONFIG["requires_circular_issuance_attestation"] is True
    assert batch._statement_families_from_text("", requires_circular_issuance_attestation=True) == []


def test_reconciliation_result_shape_translates_to_an_eligible_ingress_key():
    eligible = batch._eligible_ingress_keys([{
        "ticker": "PNJ", "canonical_metric": "revenue", "reporting_period": "2025", "statement_scope": "consolidated",
        "new_value": 34_976_042_929_392, "eligible_for_ingress": True,
    }, {
        "ticker": "PNJ", "canonical_metric": "cash_and_equivalents", "reporting_period": "2025", "statement_scope": "consolidated",
        "new_value": 1, "eligible_for_ingress": False,
    }])
    assert eligible == {("PNJ", "revenue", "2025", "consolidated", 34_976_042_929_392)}


def test_prior_image_ocr_replay_requires_exact_document_and_issuer_linkage(tmp_path):
    run = tmp_path / "fpt-image-table-tsv-ocr-evidence-run"; run.mkdir()
    (run / "artifact.json").write_text(json.dumps({
        "contract_version": "image_table_tsv_ocr_evidence_run/v1",
        "document": {"ticker": "FPT", "sha256": "doc-sha"},
        "ingress": {"panel_facts": [
            {"issuer_identity": "FPT", "canonical_metric": "revenue", "source_lineage": {"document_sha256": "doc-sha"}},
            {"issuer_identity": "FPT", "canonical_metric": "net_income", "source_lineage": {"document_sha256": "wrong"}},
        ]},
    }), encoding="utf-8")
    assert [fact["canonical_metric"] for fact in batch._prior_qualified_image_ocr_ingress(evidence_root=tmp_path / "governed-official-evidence-v1")] == ["revenue"]
