from __future__ import annotations

import inspect

from official_financial_filing_evidence import METADATA_BLOCKED, METADATA_QUALIFIED, qualify_document_metadata


SHA = "a" * 64


def _span(property_name: str, text: str = "explicit source text"):
    return {"citation_id": f"citation-{property_name}", "document_sha256": SHA,
            "source_page": 1, "text": text, "citation_kind": "test"}


def _candidate(scope="consolidated", periodicity="annual"):
    return {"issuer_identity": "TEST", "entity_type": "corporate",
            "document": {"document_id": "doc", "sha256": SHA, "source_locator": "https://approved.example/report.pdf", "observed_at": "2026-08-20T00:00:00Z", "immutable_bytes_verified": True},
            "metadata": {name: {"value": value, "evidence_span": _span(name)} for name, value in {
                "reporting_period": "2024", "periodicity": periodicity, "statement_scope": scope,
                "currency": "VND", "unit_scale": 1}.items()}}


def test_explicit_scope_currency_scale_and_hash_bound_lineage_qualify_deterministically():
    first, second = qualify_document_metadata(_candidate()), qualify_document_metadata(_candidate())
    assert first["qualification_status"] == METADATA_QUALIFIED
    assert first["evidence_envelope_id"] == second["evidence_envelope_id"]
    assert first["metadata_claims"]["currency"]["evidence_span"]["document_sha256"] == SHA
    assert first["provider_observations_created"] == 0
    assert first["value_level_evidence_required_for_canonical_qualification"] is True
    assert first["optional_metadata_claims"]["audit_or_review_status"] == {"value": "NOT_EVIDENCED", "evidence_span": None}


def test_scope_and_periodicity_preserve_distinct_identities_and_missing_metadata_fails_closed():
    separate = qualify_document_metadata(_candidate(scope="separate", periodicity="quarterly"))
    assert separate["metadata_claims"]["statement_scope"]["value"] == "separate"
    assert separate["metadata_claims"]["periodicity"]["value"] == "quarterly"
    missing = _candidate(); missing["metadata"].pop("unit_scale")
    blocked = qualify_document_metadata(missing)
    assert blocked["qualification_status"] == METADATA_BLOCKED
    assert "UNIT_SCALE_MISSING" in blocked["blockers"]


def test_unverified_document_bytes_fail_closed():
    candidate = _candidate()
    candidate["document"].pop("immutable_bytes_verified")
    blocked = qualify_document_metadata(candidate)
    assert blocked["qualification_status"] == METADATA_BLOCKED
    assert "IMMUTABLE_DOCUMENT_BYTES_NOT_VERIFIED" in blocked["blockers"]


def test_production_contract_has_no_ticker_specific_branch():
    assert "if ticker ==" not in inspect.getsource(qualify_document_metadata)
