"""Generic, fail-closed document-metadata evidence for financial filings.

This module qualifies only the metadata that is explicitly evidenced by an
already-retained official document and its existing citations.  It neither parses values
from a PDF nor turns provider observations into official facts.  Value-level matching stays
the responsibility of ``canonical_financial_qualification_policy``.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping


VERSION = "1.0.0"
CONTRACT_VERSION = "official_financial_filing_evidence/v1"
REQUIRED_METADATA = ("reporting_period", "periodicity", "statement_scope", "currency", "unit_scale")
METADATA_QUALIFIED = "DOCUMENT_METADATA_QUALIFIED"
METADATA_BLOCKED = "DOCUMENT_METADATA_BLOCKED"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def stable_id(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EvidenceSpan:
    """One explicit, hash-bound source span supporting a metadata property."""
    citation_id: str
    document_sha256: str
    source_page: int | None
    text: str
    citation_kind: str

    def to_dict(self) -> dict[str, Any]:
        return {"citation_id": self.citation_id, "document_sha256": self.document_sha256,
                "source_page": self.source_page, "text": self.text,
                "citation_kind": self.citation_kind}


def _span(value: Mapping[str, Any], document_sha256: str) -> EvidenceSpan | None:
    citation_id = str(value.get("citation_id") or "")
    text = str(value.get("text") or "")
    span_sha = str(value.get("document_sha256") or "")
    page = value.get("source_page")
    if not citation_id or not text or span_sha != document_sha256:
        return None
    if page is not None and (not isinstance(page, int) or page < 1):
        return None
    return EvidenceSpan(citation_id=citation_id, document_sha256=span_sha, source_page=page,
                        text=text, citation_kind=str(value.get("citation_kind") or "source_span"))


def qualify_document_metadata(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic filing envelope; required metadata fails closed individually.

    ``metadata`` must be supplied as ``{property: {value, evidence_span}}``.  The function
    deliberately does not infer values from a filename, provider payload, document class, or
    familiar filing layout.
    """
    document = dict(candidate.get("document") or {})
    document_sha256 = str(document.get("sha256") or "")
    blockers: list[str] = []
    if len(document_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in document_sha256.lower()):
        blockers.append("DOCUMENT_SHA256_MISSING_OR_INVALID")
    if not str(document.get("document_id") or ""):
        blockers.append("DOCUMENT_ID_MISSING")
    if not str(document.get("source_locator") or ""):
        blockers.append("SOURCE_LOCATOR_MISSING")
    if not str(document.get("observed_at") or ""):
        blockers.append("OBSERVED_TIMESTAMP_MISSING")
    if document.get("immutable_bytes_verified") is not True:
        blockers.append("IMMUTABLE_DOCUMENT_BYTES_NOT_VERIFIED")

    claims: dict[str, dict[str, Any]] = {}
    raw_metadata = candidate.get("metadata") or {}
    for name in REQUIRED_METADATA:
        item = raw_metadata.get(name) if isinstance(raw_metadata, Mapping) else None
        evidence = _span(item.get("evidence_span") or {}, document_sha256) if isinstance(item, Mapping) else None
        if not isinstance(item, Mapping) or item.get("value") is None:
            blockers.append(f"{name.upper()}_MISSING")
        elif evidence is None:
            blockers.append(f"{name.upper()}_EXPLICIT_EVIDENCE_MISSING")
        claims[name] = {"value": item.get("value") if isinstance(item, Mapping) else None,
                        "evidence_span": evidence.to_dict() if evidence else None}

    optional: dict[str, dict[str, Any]] = {}
    for name in ("audit_or_review_status", "publication_date"):
        item = raw_metadata.get(name) if isinstance(raw_metadata, Mapping) else None
        evidence = _span(item.get("evidence_span") or {}, document_sha256) if isinstance(item, Mapping) else None
        optional[name] = {"value": item.get("value") if isinstance(item, Mapping) else "NOT_EVIDENCED",
                          "evidence_span": evidence.to_dict() if evidence else None}

    status = METADATA_QUALIFIED if not blockers else METADATA_BLOCKED
    identity = {
        "contract_version": CONTRACT_VERSION,
        "issuer_identity": str(candidate.get("issuer_identity") or "").upper(),
        "document_sha256": document_sha256,
        "document_id": document.get("document_id"),
        "metadata": {name: claims[name]["value"] for name in REQUIRED_METADATA},
        "status": status,
    }
    envelope = {
        "schema_version": VERSION,
        "contract_version": CONTRACT_VERSION,
        "issuer_identity": identity["issuer_identity"],
        "entity_type": str(candidate.get("entity_type") or "unknown"),
        "document": {
            "document_id": document.get("document_id"), "document_sha256": document_sha256,
            "source_locator": document.get("source_locator"), "source_id": document.get("source_id"),
            "source_authority": document.get("source_authority"), "observed_at": document.get("observed_at"),
            "published_at": document.get("published_at"), "relative_path": document.get("relative_path"),
            "immutable_bytes_verified": document.get("immutable_bytes_verified") is True,
        },
        "metadata_claims": claims,
        "optional_metadata_claims": optional,
        "qualification_status": status,
        "blockers": sorted(set(blockers)),
        "provider_observations_created": 0,
        "provider_observation_join_allowed": False,
        "value_level_evidence_required_for_canonical_qualification": True,
    }
    envelope["evidence_envelope_id"] = stable_id(identity)
    return envelope
