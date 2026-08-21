"""Focused tests for byte-derived prospective route ownership review V1."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from official_route_ownership_evidence import qualify
from prospective_route_ownership_review import (
    BRANDING_ONLY,
    FULL_LEGAL_ENTITY_NAME,
    IDENTITY_CONFLICT,
    INSUFFICIENT_IDENTITY_EVIDENCE,
    OWNER_REVIEW_READY,
    STATUTORY_REGISTRATION_IDENTIFIER,
    STRUCTURED_LEGAL_NAME,
    build_prospective_owner_review_artifact,
    generate_registry_candidates,
    review_retained_object,
)
from retained_official_route_ownership_evidence import OFFLINE_RETAINED_EVIDENCE_CATALOG


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config" / "official_source_registry.json"


def _record(ticker: str) -> dict:
    return next(record for record in build_prospective_owner_review_artifact()["records"] if record["ticker"] == ticker)


def test_identity_evidence_is_byte_derived_not_catalog_legal_assertion(monkeypatch) -> None:
    before = _record("ABS")
    monkeypatch.setitem(OFFLINE_RETAINED_EVIDENCE_CATALOG["ABS"], "legal_name", "Injected wrong name")
    after = review_retained_object("ABS")
    raw = (ROOT / after["retained_file_path"]).read_text(encoding="utf-8")
    assert before["normalized_extracted_issuer_identity"] == after["normalized_extracted_issuer_identity"]
    assert any(item["span"] in raw for item in after["extracted_identity_evidence"])
    assert after["prospective_owner_review_status"] == OWNER_REVIEW_READY


def test_absent_statutory_identifier_is_not_emitted_as_retained_evidence() -> None:
    for ticker in ("AAT", "ABW", "ACB", "BID", "MBB", "MWG", "TCB"):
        record = _record(ticker)
        assert record["statutory_identifiers_present"] == []
        assert STATUTORY_REGISTRATION_IDENTIFIER not in record["evidence_types"]


def test_strong_full_legal_name_is_typed_honestly() -> None:
    record = _record("ABW")
    assert record["prospective_owner_review_status"] == OWNER_REVIEW_READY
    assert FULL_LEGAL_ENTITY_NAME in record["evidence_types"]
    assert STATUTORY_REGISTRATION_IDENTIFIER not in record["evidence_types"]


def test_branding_only_evidence_cannot_satisfy_identity_contract() -> None:
    record = _record("AAA")
    assert record["prospective_owner_review_status"] == INSUFFICIENT_IDENTITY_EVIDENCE
    assert record["evidence_types"] == [BRANDING_ONLY]


def test_aat_different_entity_fails_closed() -> None:
    record = _record("AAT")
    assert record["prospective_owner_review_status"] == IDENTITY_CONFLICT
    assert record["identity_match_verdict"] == "CONFLICT"
    assert "Tiên Sơn" in record["normalized_extracted_issuer_identity"] or "tien son" in record["normalized_extracted_issuer_identity"]


def test_content_bound_to_one_host_cannot_approve_another() -> None:
    record = review_retained_object("MWG", candidate_locator="https://other.example/ir")
    assert record["domain_binding_verdict"] == "INVALID"
    assert record["prospective_owner_review_status"] != OWNER_REVIEW_READY


def test_static_catalog_identity_alone_cannot_produce_owner_review_ready() -> None:
    assert OFFLINE_RETAINED_EVIDENCE_CATALOG["ABT"]["legal_name"]
    assert _record("ABT")["prospective_owner_review_status"] == INSUFFICIENT_IDENTITY_EVIDENCE


def test_prospective_review_remains_byte_derived_after_owner_activation() -> None:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    allowed = next(source for source in registry["sources"] if source["source_id"] == "issuer_ir")["allowed_hosts"]
    assert "bitagco.com" in allowed
    assert _record("ABS")["prospective_owner_review_status"] == OWNER_REVIEW_READY


def test_activated_route_qualification_accepts_explicitly_approved_host() -> None:
    record = _record("ABS")
    evidence = {
        "canonical_instrument": "ABS",
        "issuer_legal_identity": record["expected_issuer_identity"],
        "profile_locator": record["candidate_locator"],
        "candidate_locator": record["candidate_locator"],
        "raw_document_sha256": record["retained_sha256"],
        "ownership_evidence": "retained_official_document_locator",
    }
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert qualify(evidence, registry)["route_approval_eligible"]


def test_registry_candidates_are_only_genuine_owner_review_ready_records() -> None:
    artifact = build_prospective_owner_review_artifact()
    candidates = generate_registry_candidates(artifact["records"])
    ready = {record["ticker"] for record in artifact["records"] if record["prospective_owner_review_status"] == OWNER_REVIEW_READY}
    assert {candidate["ticker"] for candidate in candidates} == ready
    assert all(candidate["activation_recommendation"] == "PENDING_OWNER_PROMOTION_REVIEW" for candidate in candidates)


def test_registry_remains_unchanged_and_replay_is_deterministic() -> None:
    before = hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest()
    first = build_prospective_owner_review_artifact()
    second = build_prospective_owner_review_artifact()
    assert first == second
    assert first["artifact_identity"] == second["artifact_identity"]
    assert hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest() == before


def test_structured_legal_name_is_retained_for_tcb() -> None:
    record = _record("TCB")
    assert record["prospective_owner_review_status"] == OWNER_REVIEW_READY
    assert STRUCTURED_LEGAL_NAME in record["evidence_types"]
