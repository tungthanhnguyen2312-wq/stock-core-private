"""Retained-manifest and generic discovery contracts for the owner-focus OCR batch."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import owner_focus_image_only_corporate_ocr_batch as batch
from owner_focus_image_only_corporate_ocr_batch import BATCH_TICKERS, CORE_METRICS, DISCOVERY_CONFIG, build_batch_manifest


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


def test_discovery_scans_to_cap_when_one_required_family_is_absent(monkeypatch, tmp_path):
    result, calls = _discover(monkeypatch, tmp_path, {2: "Balance sheet", 6: "Income statement"})
    assert calls == list(range(1, DISCOVERY_CONFIG["max_front_pages"] + 1))
    assert not batch._discovery_complete(result["statement_pages"])


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
