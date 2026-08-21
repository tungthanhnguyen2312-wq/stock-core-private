"""Deterministic replay for the owner's nine approved issuer-route hosts.

This module records the bounded activation decision and replays only the
already retained prospective-route evidence.  It does not fetch documents or
promote any financial facts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from bounded_official_route_evidence_enrichment import execute_bounded_enrichment
from official_financial_source_route_discovery import normalize_domain
from official_route_ownership_evidence import qualify
from prospective_route_ownership_review import OWNER_REVIEW_READY, build_prospective_owner_review_artifact


ROOT = Path(__file__).resolve().parent
VERSION = "1.0.0"
CONTRACT_VERSION = "official_source_registry_owner_promotion/v1"
ARTIFACT_TYPE = "OFFICIAL_SOURCE_REGISTRY_OWNER_PROMOTION"
DEFAULT_REGISTRY = ROOT / "config" / "official_source_registry.json"

OWNER_APPROVED_HOSTS = {
    "ABS": "bitagco.com",
    "ABW": "abs.vn",
    "ACB": "www.acb.com.vn",
    "MBB": "www.mbbank.com.vn",
    "MWG": "mwg.vn",
    "TCB": "techcombank.com",
    "AAA": "anphatbioplastics.com",
    "AAT": "tiensonaus.com",
    "BID": "bidv.com.vn",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _is_sha256(value: str | None) -> bool:
    return bool(value) and len(str(value)) == 64 and all(char in "0123456789abcdef" for char in str(value).lower())


def _evidence_sources() -> dict[str, tuple[dict[str, Any], str]]:
    prospective = build_prospective_owner_review_artifact()
    enrichment = execute_bounded_enrichment(live_network=False)
    records: dict[str, tuple[dict[str, Any], str]] = {}
    for record in prospective["records"]:
        if record["ticker"] in OWNER_APPROVED_HOSTS:
            records[record["ticker"]] = (record, prospective["artifact_identity"])
    for record in enrichment["records"]:
        if record["ticker"] in OWNER_APPROVED_HOSTS:
            records[record["ticker"]] = (record, enrichment["artifact_identity"])
    return records


def _activated_evidence_record(record: Mapping[str, Any], source_artifact_identity: str) -> dict[str, Any]:
    retained_path = ROOT / str(record["retained_file_path"])
    raw_bytes = retained_path.read_bytes() if retained_path.is_file() else b""
    actual_sha = hashlib.sha256(raw_bytes).hexdigest() if raw_bytes else ""
    expected_sha = str(record.get("retained_sha256") or "")
    integrity_valid = bool(raw_bytes and actual_sha == expected_sha and _is_sha256(expected_sha))
    locator = str(record.get("candidate_locator") or record.get("final_url") or "")
    return {
        "canonical_instrument": record["ticker"],
        "issuer_legal_identity": record["expected_issuer_identity"],
        "source_id": "issuer_ir",
        "route_class": "issuer_ir",
        "candidate_locator": locator,
        "profile_locator": locator,
        "raw_document_sha256": expected_sha if integrity_valid else "",
        "ownership_evidence": "retained_official_document_locator",
        "evidence_type": ",".join(record.get("evidence_types") or []),
        "evidence_provenance": {
            "source_artifact_identity": source_artifact_identity,
            "retained_file_path": record["retained_file_path"],
            "candidate_locator": locator,
            "requested_url": record.get("requested_url"),
            "final_url": record.get("final_url"),
            "redirect_authority_verdict": record.get("redirect_authority_verdict"),
        },
        "evidence_integrity_valid": integrity_valid,
        "retained_file_path": record["retained_file_path"],
        "owner_review_status": record["prospective_owner_review_status"],
    }


def replay_owner_approved_routes(registry_path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    """Replay activated qualification for exactly the nine authorized routes."""
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    issuer_source = next(source for source in registry["sources"] if source["source_id"] == "issuer_ir")
    allowed_hosts = {str(host).lower() for host in issuer_source["allowed_hosts"]}
    sources = _evidence_sources()
    rows: list[dict[str, Any]] = []
    for ticker, approved_host in sorted(OWNER_APPROVED_HOSTS.items()):
        record, source_identity = sources[ticker]
        evidence = _activated_evidence_record(record, source_identity)
        host_matches_authorization = normalize_domain(evidence["candidate_locator"]) == approved_host
        qualifier = qualify(evidence, registry) if host_matches_authorization else None
        qualified = bool(qualifier and qualifier["route_approval_eligible"])
        rows.append({
            "ticker": ticker,
            "owner_approved_host": approved_host,
            "candidate_host": normalize_domain(evidence["candidate_locator"]),
            "host_in_registry": approved_host in allowed_hosts,
            "retained_evidence_sha256": evidence["raw_document_sha256"] or None,
            "retained_evidence_path": evidence["retained_file_path"],
            "evidence_provenance": evidence["evidence_provenance"],
            "owner_review_status": evidence["owner_review_status"],
            "evidence_integrity_valid": evidence["evidence_integrity_valid"],
            "activated_qualification": qualifier,
            "activated_route_status": "OWNERSHIP_QUALIFIED" if qualified else "OWNERSHIP_EVIDENCE_MISSING",
            "route_approval_eligible": qualified,
            "blockers": [] if qualified else ["ACTIVATED_ROUTE_QUALIFICATION_FAILED"],
        })
    return {
        "schema_version": VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "owner_authorization": {
            "authorized_tickers": sorted(OWNER_APPROVED_HOSTS),
            "authorized_hosts": [OWNER_APPROVED_HOSTS[ticker] for ticker in sorted(OWNER_APPROVED_HOSTS)],
            "scope": "source_route_activation_for_downstream_official_document_acquisition_only",
            "excluded_hosts": ["aquatexbentre.com", "tienson.vn"],
        },
        "registry_activation": {
            "issuer_ir_activation": issuer_source["activation"],
            "approved_host_count": len(OWNER_APPROVED_HOSTS),
            "approved_hosts_present": all(host in allowed_hosts for host in OWNER_APPROVED_HOSTS.values()),
            "registry_mutated_by_replay": False,
        },
        "activated_route_replay": rows,
        "summary_counts": {
            "authorized_routes": len(rows),
            "ownership_qualified_routes": sum(row["route_approval_eligible"] for row in rows),
            "ownership_evidence_missing_routes": sum(not row["route_approval_eligible"] for row in rows),
        },
        "governance_separation": {
            "owner_registry_promotion_recorded": True,
            "financial_documents_acquired": 0,
            "financial_facts_created": 0,
            "fundamental_readiness_mutated": False,
            "provider_authority_promoted": False,
            "raw_as_traded_promoted": False,
            "liquidity_sizing_promoted": False,
            "valuation_or_recommendation_produced": False,
        },
        "verdict": "OWNER_APPROVED_SOURCE_ROUTES_ACTIVATED",
    }


def build_artifact(registry_path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    artifact = replay_owner_approved_routes(registry_path)
    artifact["artifact_sha256"] = _hash(artifact)
    artifact["artifact_identity"] = f"official_source_registry_owner_promotion:{artifact['artifact_sha256']}"
    return artifact
