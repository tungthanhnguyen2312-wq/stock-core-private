"""Focused tests for bounded official route evidence enrichment V1."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bounded_official_route_evidence_enrichment import (
    BRANDING_ONLY,
    CONTRACT_VERSION,
    ENRICHMENT_EVIDENCE_DIR,
    FIXED_ROUTE_PLANS,
    FULL_LEGAL_ENTITY_NAME,
    IDENTITY_CONFLICT,
    INSUFFICIENT_IDENTITY_EVIDENCE,
    OFFLINE_ENRICHED_EVIDENCE_CATALOG,
    OWNER_REVIEW_READY,
    REQUEST_BUDGET,
    TARGET_TICKERS,
    execute_bounded_enrichment,
    normalize_legal_identity,
    review_retained_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config" / "official_source_registry.json"


def _artifact() -> dict:
    return execute_bounded_enrichment(live_network=False)


def _record(ticker: str) -> dict:
    artifact = _artifact()
    return next(rec for rec in artifact["records"] if rec["ticker"] == ticker)


def test_hard_request_budget_enforcement_and_limits() -> None:
    artifact = _artifact()
    budget_info = artifact["hard_request_budget"]
    assert budget_info["budget_respected"] is True
    assert budget_info["total_requests"] <= budget_info["first_party_ceiling"]
    assert budget_info["official_cross_registry_fallback_requests"] == 0

    actual_requests = budget_info["actual_network_requests"]
    assert actual_requests["AAA"] == 1  # 1 / 1
    assert actual_requests["BID"] == 1  # stopped after request 1 because sufficient
    assert actual_requests["AAT"] == 1  # stopped after request 1 because sufficient
    assert actual_requests["ABT"] == 2  # attempted 2 before stopping


def test_retain_on_acquisition_sha256_verification() -> None:
    for ticker, entries in OFFLINE_ENRICHED_EVIDENCE_CATALOG.items():
        for entry in entries:
            file_path = ROOT / entry["relative_path"]
            assert file_path.is_file(), f"Retained file missing: {file_path}"
            raw_bytes = file_path.read_bytes()
            actual_sha = hashlib.sha256(raw_bytes).hexdigest()
            assert actual_sha == entry["sha256"], f"SHA mismatch for {entry['relative_path']}"
            assert len(raw_bytes) == entry["bytes_length"]


def test_no_second_request_after_sufficient_evidence() -> None:
    # BID and AAT achieve OWNER_REVIEW_READY on request 1, so request 2 must not be executed
    artifact = _artifact()
    actual = artifact["hard_request_budget"]["actual_network_requests"]
    assert actual["BID"] == 1
    assert len(FIXED_ROUTE_PLANS["BID"]) == 2

    assert actual["AAT"] == 1
    assert len(FIXED_ROUTE_PLANS["AAT"]) == 2


def test_aaa_legal_form_normalization_and_owner_review_ready() -> None:
    rec = _record("AAA")
    assert rec["prospective_owner_review_status"] == OWNER_REVIEW_READY
    assert rec["identity_match_verdict"] == "MATCH"
    assert rec["candidate_host"] == "anphatbioplastics.com"
    assert FULL_LEGAL_ENTITY_NAME in rec["evidence_types"]
    assert normalize_legal_identity("Công ty CP Nhựa An Phát Xanh") == rec["normalized_expected_issuer_identity"]


def test_bid_redirect_provenance_and_full_legal_identity() -> None:
    rec = _record("BID")
    assert rec["prospective_owner_review_status"] == OWNER_REVIEW_READY
    assert rec["identity_match_verdict"] == "MATCH"
    assert rec["candidate_host"] == "bidv.com.vn"
    assert rec["final_url"] == "https://bidv.com.vn/vn/quan-he-nha-dau-tu"
    assert rec["redirect_chain"] == ["https://bidv.com.vn/vn/quan-he-nha-dau-tu"]
    assert "Ngân hàng TMCP Đầu tư và Phát triển Việt Nam" in rec["observed_identity"]


def test_aat_historical_conflict_preserved_and_new_route_ready() -> None:
    rec = _record("AAT")
    assert rec["candidate_host"] == "tiensonaus.com"
    assert rec["prospective_owner_review_status"] == OWNER_REVIEW_READY
    assert rec["identity_match_verdict"] == "MATCH"

    artifact = _artifact()
    historical = artifact["historical_evidence_preservation"]["AAT_tienson_vn"]
    assert historical["locator"] == "https://tienson.vn"
    assert historical["status"] == "REJECTED_IDENTITY_CONFLICT"
    assert historical["preserved_unmodified"] is True
    assert (ROOT / historical["retained_path"]).is_file()


def test_abt_unsupported_abbreviation_fails_closed() -> None:
    rec = _record("ABT")
    assert rec["prospective_owner_review_status"] == INSUFFICIENT_IDENTITY_EVIDENCE
    assert rec["identity_match_verdict"] == "INSUFFICIENT"
    assert "ABBREVIATION_ONLY_XNK_REQUIRES_FULL_LEGAL_EXPANSION_CONTRACT" in rec["reason_codes"]
    assert "ENGLISH_LEGAL_IDENTITY_REQUIRES_ALIAS_CONTRACT" in rec["reason_codes"]


def test_byte_derived_evidence_only_no_static_hints_as_proof(monkeypatch) -> None:
    rec = _record("AAA")
    raw_text = (ROOT / rec["retained_file_path"]).read_text(encoding="utf-8")
    for evidence in rec["extracted_identity_evidence"]:
        assert evidence["span"] in raw_text


def test_registry_remains_unchanged_and_replay_deterministic() -> None:
    before = hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest()
    first = _artifact()
    second = _artifact()
    assert first == second
    assert first["artifact_identity"] == second["artifact_identity"]
    assert hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest() == before


def test_registry_candidates_proposed_count() -> None:
    artifact = _artifact()
    candidates = artifact["governed_registry_candidates_proposed"]
    ready_tickers = {rec["ticker"] for rec in artifact["records"] if rec["prospective_owner_review_status"] == OWNER_REVIEW_READY}
    candidate_tickers = {cand["ticker"] for cand in candidates}
    assert candidate_tickers == ready_tickers == {"AAA", "BID", "AAT"}
    assert all(c["activation_recommendation"] == "PENDING_OWNER_PROMOTION_REVIEW" for c in candidates)
