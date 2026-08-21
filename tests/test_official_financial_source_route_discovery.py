"""Focused evidence-binding tests for official route discovery correction."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from official_financial_source_route_discovery import (
    ROUTE_STATUS_EVIDENCE_MISSING,
    ROUTE_STATUS_OWNERSHIP_QUALIFIED,
    VALIDATION_COHORT_17,
    build_evidence_binding_correction,
    discover_and_qualify_routes,
    execute,
)
from tools.run_official_source_route_evidence_binding_correction import PRIOR_V1, WAVE2, run


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = {
    "sources": [
        {"source_id": "issuer_ir", "activation": "approved", "allowed_hosts": ["issuer.example"]},
        {"source_id": "hose", "activation": "approved", "allowed_hosts": ["www.hsx.vn"]},
        {"source_id": "hnx", "activation": "approved", "allowed_hosts": ["www.hnx.vn"]},
    ]
}


def _issuer_evidence(**overrides: object) -> dict:
    record = {
        "canonical_instrument": "AAA",
        "route_class": "issuer_ir",
        "issuer_legal_identity": "Issuer AAA",
        "profile_locator": "https://issuer.example/investor-relations",
        "candidate_locator": "https://issuer.example/investor-relations",
        "raw_document_sha256": "a" * 64,
        "ownership_evidence": "retained_official_document_locator",
        "evidence_type": "retained_issuer_profile",
        "evidence_provenance": {"retained_manifest": "fixture-content-addressed"},
    }
    record.update(overrides)
    return record


def _run(evidence=(), *, ticker="AAA", issuer_url="https://issuer.example/investor-relations") -> dict:
    return discover_and_qualify_routes(
        cohort=[ticker], registry=REGISTRY, retained_ownership_evidence=evidence,
        legal_identity_hints={ticker: {"legal_name": f"Hint {ticker}", "exchange": "HOSE"}},
        issuer_route_hints={ticker: issuer_url},
    )


def _row(artifact: dict, route_class: str) -> dict:
    return next(row for row in artifact["route_evaluations"] if row["route_class"] == route_class)


def test_nonempty_hard_coded_proof_string_cannot_qualify() -> None:
    artifact = _run()
    assert _row(artifact, "issuer_ir")["route_status"] == ROUTE_STATUS_EVIDENCE_MISSING
    assert artifact["retained_evidence_content_identities_consumed"] == []


def test_fake_issuer_mapping_and_zzz_regression_fail_closed() -> None:
    artifact = _run(ticker="ZZZ", issuer_url="https://unverified.example")
    assert {row["route_status"] for row in artifact["route_evaluations"]} == {ROUTE_STATUS_EVIDENCE_MISSING}
    assert not any(row["route_approval_eligible"] for row in artifact["route_evaluations"])


def test_generic_exchange_host_is_not_ticker_specific_evidence() -> None:
    generic_exchange = {
        "canonical_instrument": "AAA", "route_class": "exchange_disclosure",
        "issuer_legal_identity": "Issuer AAA", "profile_locator": "https://www.hsx.vn",
        "candidate_locator": "https://www.hsx.vn", "raw_document_sha256": "b" * 64,
        "ownership_evidence": "generic_exchange_host", "evidence_type": "generic_exchange_host",
        "evidence_provenance": {"retained_manifest": "generic-host-only"}, "source_id": "hose",
    }
    assert _row(_run([generic_exchange]), "exchange_disclosure")["route_status"] == ROUTE_STATUS_EVIDENCE_MISSING


def test_hashing_an_assertion_is_not_retained_evidence_binding() -> None:
    assertion_hash = hashlib.sha256(b"static proof string").hexdigest()
    evidence = _issuer_evidence(raw_document_sha256=assertion_hash, ownership_evidence="static_proof_string")
    assert _row(_run([evidence]), "issuer_ir")["route_status"] == ROUTE_STATUS_EVIDENCE_MISSING


def test_correct_retained_evidence_uses_existing_issuer_qualifier() -> None:
    artifact = _run([_issuer_evidence()])
    issuer = _row(artifact, "issuer_ir")
    assert issuer["route_status"] == ROUTE_STATUS_OWNERSHIP_QUALIFIED
    assert issuer["qualifier_result"]["ownership_qualification_status"] == "ROUTE_OWNERSHIP_QUALIFIED"
    assert issuer["retained_content_sha256"] == "a" * 64


def test_missing_or_misaligned_retained_evidence_fails_closed() -> None:
    evidence = _issuer_evidence(candidate_locator="https://other.example/profile")
    assert _row(_run([evidence]), "issuer_ir")["route_status"] == ROUTE_STATUS_EVIDENCE_MISSING


def test_real_17_issuer_replay_has_no_qualified_routes_or_registry_mutation() -> None:
    artifact = execute()
    counts = artifact["summary_counts"]
    assert artifact["validation_cohort_identity"]["members"] == sorted(VALIDATION_COHORT_17)
    assert counts["ownership_qualified_routes"] == 0
    assert counts["ownership_evidence_missing_routes"] == 34
    assert artifact["governed_registry_candidates"] == []
    assert artifact["governance_separation"]["registry_mutated"] is False
    assert artifact["governance_separation"]["activation_promoted"] is False


def test_historical_v1_is_preserved_and_correction_supersedes_claims() -> None:
    original_bytes = PRIOR_V1.read_bytes()
    corrected, correction = run()
    assert PRIOR_V1.read_bytes() == original_bytes
    assert correction["prior_v1"]["claimed_ownership_qualified_routes"] == 28
    assert correction["prior_v1"]["qualification_status"] == "IMPLEMENTATION_PRESENT_BUT_QUALIFICATION_INVALIDATED"
    assert correction["corrected_discovery"]["ownership_qualified_routes"] == 0
    assert correction["supersession"]["historical_v1_preserved"] is True
    assert correction["corrected_discovery"]["artifact_identity"] == corrected["artifact_identity"]


def test_deterministic_replay_and_content_identity() -> None:
    first_corrected, first_correction = run()
    second_corrected, second_correction = run()
    assert first_corrected == second_corrected
    assert first_correction == second_correction
    assert first_correction["wave2_upstream_blocker"]["artifact_identity"] == json.loads(WAVE2.read_text(encoding="utf-8"))["artifact_identity"]


def test_correction_builder_records_no_side_effects() -> None:
    prior = json.loads(PRIOR_V1.read_text(encoding="utf-8"))
    corrected = execute()
    wave2 = json.loads(WAVE2.read_text(encoding="utf-8"))
    correction = build_evidence_binding_correction(prior, corrected, wave2)
    assert correction["governance_separation"] == corrected["governance_separation"]
    assert correction["corrected_discovery"]["retained_evidence_content_identities_consumed"] == []
