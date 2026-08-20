"""Deterministic, closed-world issuer-route ownership evidence; discovery never approves."""
from __future__ import annotations
import hashlib, json, urllib.parse
from typing import Any, Mapping

VERSION = "1.0.0"

def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def qualify(record: Mapping[str, Any], registry: Mapping[str, Any]) -> dict[str, Any]:
    url = str(record.get("candidate_locator") or "")
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    source = next((s for s in registry.get("sources", []) if s.get("source_id") == "issuer_ir" and s.get("activation") == "approved"), {})
    allowed = {str(x).lower() for x in source.get("allowed_hosts", [])}
    bound = bool(record.get("issuer_legal_identity") and record.get("profile_locator") and record.get("raw_document_sha256"))
    eligible = bound and host in allowed and record.get("ownership_evidence") == "retained_official_document_locator"
    return {"schema_version": VERSION, "canonical_instrument": record.get("canonical_instrument"), "issuer_legal_identity": record.get("issuer_legal_identity"), "official_profile_locator": record.get("profile_locator"), "candidate_issuer_domain_or_disclosure_locator": url or None, "raw_payload_or_document_identity": record.get("raw_document_sha256"), "discovery_method_version": "retained_manifest_route_ownership/v1", "ownership_qualification_status": "ROUTE_OWNERSHIP_QUALIFIED" if eligible else "OWNERSHIP_EVIDENCE_MISSING", "route_approval_eligible": eligible, "blockers": [] if eligible else ["ISSUER_DOMAIN_OWNERSHIP_EVIDENCE_MISSING"], "ownership_evidence_id": _hash(dict(record))}
