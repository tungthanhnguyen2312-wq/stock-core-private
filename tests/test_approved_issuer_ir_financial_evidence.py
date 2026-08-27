from __future__ import annotations

from pathlib import Path

import approved_issuer_ir_financial_evidence as subject
from p3f13_official_financial_evidence_scaleout import merge_document_qualified_facts_into_panel


def test_approved_cohort_is_exact_and_abt_is_excluded() -> None:
    assert set(subject.APPROVED_ROUTES) == {"ABS", "ABW", "ACB", "MBB", "MWG", "TCB", "AAA", "AAT", "BID"}
    assert "ABT" not in subject.APPROVED_ROUTES


def test_document_link_never_leaves_approved_host() -> None:
    html = b'<a href="/x.pdf">Bao cao tai chinh</a><a href="https://bad.example/x.pdf">BCTC</a>'
    assert subject.document_links("https://bitagco.com/", html) == ["https://bitagco.com/x.pdf"]


def test_qualified_corporate_fact_requires_all_semantics_and_citation() -> None:
    candidate = {"ticker": "AAA", "canonical_metric": "revenue", "issuer_identity": "AAA", "reporting_period": "2025", "periodicity": "annual", "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1, "audit_or_review_status": "audited", "statement_family": "income_statement", "raw_value_text": "1,000", "document_sha256": "a" * 64, "citation": {"page": 3, "text": "Net revenue 1,000"}}
    result = subject.validate_fact(candidate)
    assert result["qualification_status"] == "QUALIFIED"
    assert result["fact"]["normalized_vnd_value"] == 1000


def test_missing_scale_or_citation_fails_closed_without_inference() -> None:
    result = subject.validate_fact({"ticker": "AAA", "canonical_metric": "revenue", "raw_value_text": "1000"})
    assert result["qualification_status"] == "REJECTED"
    assert "UNIT_SCALE_NOT_EXPLICIT" in result["blockers"]
    assert "CITATION_REQUIRED" in result["blockers"]


def test_bank_taxonomy_rejects_industrial_revenue_and_accepts_bank_earnings() -> None:
    base = {"ticker": "ACB", "issuer_identity": "ACB", "reporting_period": "2025", "periodicity": "annual", "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1, "audit_or_review_status": "audited", "statement_family": "income_statement", "raw_value_text": "1", "document_sha256": "a" * 64, "citation": {"page": 1, "text": "x"}}
    assert "BANK_TAXONOMY_VIOLATION" in subject.validate_fact({**base, "canonical_metric": "revenue"})["blockers"]
    assert subject.validate_fact({**base, "canonical_metric": "net_profit_parent"})["qualification_status"] == "QUALIFIED"


def test_bounded_acquisition_records_only_direct_documents(tmp_path: Path) -> None:
    def fake(url: str):
        if url == subject.APPROVED_ROUTES["AAA"]:
            return 200, {"Content-Type": "text/html"}, b'<a href="report.pdf">Financial statement</a>', url
        if url.endswith("report.pdf"):
            return 200, {"Content-Type": "application/pdf"}, b"%PDF-1.7\nPDF", url
        return 404, {}, b"", url
    artifact = subject.acquire(output_root=tmp_path, fetcher=fake, now=lambda: "2026-08-27T00:00:00Z")
    assert artifact["document_budget"]["actual"] == 1
    assert next(x for x in artifact["route_dispositions"] if x["ticker"] == "AAA")["disposition"] == "OFFICIAL_DOCUMENT_FOUND"
    assert len(artifact["approved_tickers"]) == 9 and artifact["excluded_tickers"] == ["ABT"]
    doc = artifact["documents"][0]
    assert (tmp_path / doc["relative_path"]).read_bytes() == b"%PDF-1.7\nPDF"


def test_document_hash_and_replay_are_deterministic(tmp_path: Path) -> None:
    def fake(url: str): return 404, {}, b"", url
    first = subject.acquire(output_root=tmp_path / "a", fetcher=fake, now=lambda: "2026-08-27T00:00:00Z")
    second = subject.acquire(output_root=tmp_path / "b", fetcher=fake, now=lambda: "2026-08-27T00:00:00Z")
    assert first["artifact_sha256"] == second["artifact_sha256"]


def test_duplicate_document_is_retention_no_op(tmp_path: Path) -> None:
    def fake(url: str):
        if url == subject.APPROVED_ROUTES["AAA"]: return 200, {}, b'<a href="report.pdf">Financial statement</a>', url
        if url.endswith("report.pdf"): return 200, {"Content-Type": "application/pdf"}, b"%PDF-1.7", url
        return 404, {}, b"", url
    subject.acquire(output_root=tmp_path, fetcher=fake, now=lambda: "2026-08-27T00:00:00Z")
    second = subject.acquire(output_root=tmp_path, fetcher=fake, now=lambda: "2026-08-27T00:00:00Z")
    assert second["document_budget"]["actual"] == 0
    assert second["documents"][0]["retention_status"] == "DUPLICATE_DOCUMENT_NO_OP"


def test_route_404_is_explicit_and_no_provider_or_value_activation(tmp_path: Path) -> None:
    artifact = subject.acquire(output_root=tmp_path, fetcher=lambda _: (404, {}, b"", "https://example.invalid"), now=lambda: "2026-08-27T00:00:00Z")
    assert all(x["disposition"] == "OFFICIAL_ROUTE_404" for x in artifact["route_dispositions"])
    assert artifact["authority"] == {"provider_used": False, "canonical_store_mutated": False, "runtime_database_mutated": False, "value_strategy_activated": False, "recommendation_or_ranking_produced": False}


def test_conflicts_remain_explicit_and_never_cross_ticker() -> None:
    base = {"ticker": "AAA", "canonical_metric": "revenue", "reporting_period": "2025", "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1, "value": 1}
    assert subject.classify_conflict(base, {**base, "value": 2}) == "TRUE_CONFLICT"
    assert subject.classify_conflict(base, {**base, "ticker": "AAT"}) == "NOT_COMPARABLE"


def test_existing_p3f13_panel_accepts_only_cited_qualified_facts() -> None:
    panel = {"issuers": []}
    fact = {"issuer_identity": "ACB", "entity_type": "bank", "canonical_metric": "net_profit_parent", "reporting_period": "2025", "statement_scope": "consolidated", "qualification_state": "QUALIFIED", "source_lineage": {"document_sha256": "a" * 64, "citation_id": "c"}}
    merged = merge_document_qualified_facts_into_panel(panel, [fact])
    assert merged["issuers"][0]["issuer_identity"]["entity_type"] == "bank"
    assert merged["qualified_facts_count"] == 1


def test_summary_keeps_aaa_and_bank_boundaries_explicit(tmp_path: Path) -> None:
    artifact = subject.acquire(output_root=tmp_path, fetcher=lambda url: (404, {}, b"", url), now=lambda: "2026-08-27T00:00:00Z")
    report = subject.summarize_existing_artifact(tmp_path / "artifact.json")
    assert report["aaa_effect"].startswith("REMAINS_")
    assert report["bank_validation"]["industrial_ev_metrics_forced"] is False
    assert len(report["inventory"]) == len(artifact["approved_tickers"])
