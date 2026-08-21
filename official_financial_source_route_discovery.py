"""Evidence-bound official financial source route discovery.

Static issuer and exchange values are discovery hints only. They cannot establish
route ownership: a qualified route must bind to retained, content-addressed
evidence and pass the existing ownership qualifier where that qualifier applies.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
import urllib.parse

from entity_classification_contract import load_layered_entity_profiles
from official_route_ownership_evidence import qualify as qualify_issuer_route


ROOT = Path(__file__).resolve().parent
VERSION = "2.0.0"
CONTRACT_VERSION = "official_financial_source_route_discovery/v2"
ARTIFACT_TYPE = "OFFICIAL_FINANCIAL_SOURCE_ROUTE_DISCOVERY"
DEFAULT_REGISTRY = ROOT / "config" / "official_source_registry.json"

ROUTE_STATUS_OWNERSHIP_QUALIFIED = "OWNERSHIP_QUALIFIED"
ROUTE_STATUS_DISCOVERED_UNQUALIFIED = "DISCOVERED_UNQUALIFIED"
ROUTE_STATUS_REJECTED = "REJECTED"
ROUTE_STATUS_NOT_FOUND = "NOT_FOUND"
ROUTE_STATUS_EVIDENCE_MISSING = "OWNERSHIP_EVIDENCE_MISSING"

VALIDATION_COHORT_17 = (
    "ABB", "ACB", "BID", "MBB", "TCB",
    "AAS", "ABW",
    "AAA", "AAH", "AAN", "AAT", "AAV", "ABS", "ABT", "ACC", "MWG", "VIC",
)

# Non-authoritative discovery hints only. Retained evidence must bind legal
# identity and ownership to a route before a route may be qualified.
LEGAL_IDENTITY_HINTS = {
    "ABB": {"legal_name": "Ngân hàng TMCP An Bình", "exchange": "UPCOM"},
    "ACB": {"legal_name": "Ngân hàng TMCP Á Châu", "exchange": "HOSE"},
    "BID": {"legal_name": "Ngân hàng TMCP Đầu tư và Phát triển Việt Nam", "exchange": "HOSE"},
    "MBB": {"legal_name": "Ngân hàng TMCP Quân đội", "exchange": "HOSE"},
    "TCB": {"legal_name": "Ngân hàng TMCP Kỹ thương Việt Nam", "exchange": "HOSE"},
    "AAS": {"legal_name": "CTCP Chứng khoán SmartInvest", "exchange": "UPCOM"},
    "ABW": {"legal_name": "CTCP Chứng khoán An Bình", "exchange": "UPCOM"},
    "AAA": {"legal_name": "CTCP Nhựa An Phát Xanh", "exchange": "HOSE"},
    "AAH": {"legal_name": "CTCP Nông nghiệp Hợp Nhất", "exchange": "UPCOM"},
    "AAN": {"legal_name": "CTCP Khoáng sản An Phát", "exchange": "UPCOM"},
    "AAT": {"legal_name": "CTCP Tập đoàn Tiên Sơn Thanh Hóa", "exchange": "HOSE"},
    "AAV": {"legal_name": "CTCP AAV Group", "exchange": "HNX"},
    "ABS": {"legal_name": "CTCP Dịch vụ Nông nghiệp Bình Thuận", "exchange": "HOSE"},
    "ABT": {"legal_name": "CTCP Xuất nhập khẩu Thủy sản Bến Tre", "exchange": "HOSE"},
    "ACC": {"legal_name": "CTCP Đầu tư và Xây dựng Bình Dương ACC", "exchange": "HOSE"},
    "MWG": {"legal_name": "CTCP Đầu tư Thế giới Di động", "exchange": "HOSE"},
    "VIC": {"legal_name": "Tập đoàn Vingroup - CTCP", "exchange": "HOSE"},
}

STATIC_ISSUER_ROUTE_HINTS = {
    "MWG": "https://mwg.vn", "VIC": "https://vingroup.net",
    "ACB": "https://www.acb.com.vn", "BID": "https://www.bidv.com.vn",
    "MBB": "https://www.mbbank.com.vn", "TCB": "https://techcombank.com",
    "ABB": "https://www.abbank.vn", "AAA": "https://anphatbioplastics.com",
    "AAS": "https://sisi.com.vn", "ABW": "https://abs.vn",
    "AAH": "https://hopnhatagriculture.com", "AAN": "https://khoangsanap.com.vn",
    "AAT": "https://tienson.vn", "AAV": "https://aav.com.vn",
    "ABS": "https://bitagco.com", "ABT": "https://aquatexbentre.com",
    "ACC": "https://acc.com.vn",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def normalize_domain(url_or_host: str | None) -> str:
    """Normalize a URL or host to a lowercase hostname."""
    if not url_or_host:
        return ""
    text = str(url_or_host).strip().lower()
    if text.startswith(("http://", "https://")):
        return urllib.parse.urlsplit(text).hostname or ""
    return text.split("/")[0].split(":")[0]


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdefABCDEF" for char in text)


def _records_for(
    retained_ownership_evidence: Sequence[Mapping[str, Any]], ticker: str, route_class: str,
) -> list[Mapping[str, Any]]:
    return [
        row for row in retained_ownership_evidence
        if str(row.get("canonical_instrument", "")).upper() == ticker
        and row.get("route_class") == route_class
    ]


def _binding_fields_present(record: Mapping[str, Any], ticker: str, candidate_url: str | None) -> bool:
    """Require an evidence binding before any qualifier may be asked to approve a route."""
    if str(record.get("canonical_instrument", "")).upper() != ticker:
        return False
    if not record.get("issuer_legal_identity") or not record.get("profile_locator"):
        return False
    if not _is_sha256(record.get("raw_document_sha256")):
        return False
    if not record.get("ownership_evidence") or not record.get("evidence_type"):
        return False
    if not record.get("evidence_provenance"):
        return False
    return bool(candidate_url) and normalize_domain(record.get("candidate_locator")) == normalize_domain(candidate_url)


def _issuer_evaluation(
    ticker: str, legal_hint: Mapping[str, Any], candidate_url: str | None,
    retained_evidence: Sequence[Mapping[str, Any]], registry: Mapping[str, Any],
    entity_class: str, timestamp: str,
) -> dict[str, Any]:
    evidence = next(
        (row for row in _records_for(retained_evidence, ticker, "issuer_ir")
         if _binding_fields_present(row, ticker, candidate_url)),
        None,
    )
    qualifier = qualify_issuer_route(evidence, registry) if evidence else None
    qualified = bool(qualifier and qualifier["route_approval_eligible"])
    return {
        "route_id": f"route:issuer_ir:{ticker}:{_hash(candidate_url)[:12]}",
        "ticker": ticker,
        "legal_issuer_identity": evidence.get("issuer_legal_identity") if evidence else None,
        "legal_identity_hint": legal_hint.get("legal_name"),
        "entity_class": entity_class,
        "route_class": "issuer_ir",
        "candidate_url": candidate_url,
        "candidate_domain": normalize_domain(candidate_url),
        "discovery_method": "static_hint_requires_retained_evidence_binding",
        "observed_at": timestamp,
        "ownership_evidence_type": evidence.get("evidence_type") if evidence else None,
        "ownership_evidence_locator": evidence.get("profile_locator") if evidence else None,
        "retained_content_sha256": evidence.get("raw_document_sha256") if evidence else None,
        "ownership_evidence_provenance": evidence.get("evidence_provenance") if evidence else None,
        "qualifier_result": qualifier,
        "route_status": ROUTE_STATUS_OWNERSHIP_QUALIFIED if qualified else ROUTE_STATUS_EVIDENCE_MISSING,
        "route_approval_eligible": qualified,
        "blockers": [] if qualified else ["NO_RETAINED_ISSUER_DOMAIN_OWNERSHIP_EVIDENCE"],
        "rejection_reason": None if qualified else "Static route hint is not retained ownership evidence",
        "is_already_approved_in_registry": qualified,
    }


def _exchange_evaluation(
    ticker: str, legal_hint: Mapping[str, Any], retained_evidence: Sequence[Mapping[str, Any]],
    registry: Mapping[str, Any], entity_class: str, timestamp: str,
) -> dict[str, Any]:
    """Require a retained per-ticker exchange profile; a hostname or template is never one."""
    evidence = next(
        (row for row in _records_for(retained_evidence, ticker, "exchange_disclosure")
         if _binding_fields_present(row, ticker, row.get("candidate_locator"))),
        None,
    )
    source_id = str(evidence.get("source_id")) if evidence else ""
    source = next((item for item in registry.get("sources", []) if item.get("source_id") == source_id), {})
    allowed_hosts = {normalize_domain(host) for host in source.get("allowed_hosts", [])}
    candidate_host = normalize_domain(evidence.get("candidate_locator")) if evidence else ""
    qualified = bool(
        evidence
        and evidence.get("ownership_evidence") == "retained_ticker_specific_exchange_profile"
        and evidence.get("evidence_type") == "ticker_specific_exchange_profile"
        and source_id in {"hose", "hnx"}
        and candidate_host in allowed_hosts
    )
    return {
        "route_id": f"route:exchange:{ticker}:{_hash(ticker)[:12]}",
        "ticker": ticker,
        "legal_issuer_identity": evidence.get("issuer_legal_identity") if evidence else None,
        "legal_identity_hint": legal_hint.get("legal_name"),
        "entity_class": entity_class,
        "route_class": "exchange_disclosure",
        "candidate_url": evidence.get("candidate_locator") if evidence else None,
        "candidate_domain": candidate_host or None,
        "discovery_method": "retained_ticker_specific_exchange_profile_only",
        "observed_at": timestamp,
        "ownership_evidence_type": evidence.get("evidence_type") if evidence else None,
        "ownership_evidence_locator": evidence.get("profile_locator") if evidence else None,
        "retained_content_sha256": evidence.get("raw_document_sha256") if evidence else None,
        "ownership_evidence_provenance": evidence.get("evidence_provenance") if evidence else None,
        "qualifier_result": None,
        "route_status": ROUTE_STATUS_OWNERSHIP_QUALIFIED if qualified else ROUTE_STATUS_EVIDENCE_MISSING,
        "route_approval_eligible": qualified,
        "blockers": [] if qualified else ["NO_RETAINED_TICKER_SPECIFIC_EXCHANGE_PROFILE_EVIDENCE"],
        "rejection_reason": None if qualified else "Generic exchange hosts and URL templates are not ticker-specific evidence",
        "is_already_approved_in_registry": qualified,
    }


def discover_and_qualify_routes(
    cohort: Sequence[str] = VALIDATION_COHORT_17, *, registry: Mapping[str, Any] | None = None,
    retained_ownership_evidence: Sequence[Mapping[str, Any]] = (),
    legal_identity_hints: Mapping[str, Mapping[str, Any]] | None = None,
    issuer_route_hints: Mapping[str, str] | None = None,
    timestamp: str = "2026-08-21T10:00:00Z",
) -> dict[str, Any]:
    """Evaluate route hints only through retained ownership evidence, entirely offline."""
    reg = dict(registry or json.loads(DEFAULT_REGISTRY.read_text(encoding="utf-8")))
    hints = dict(legal_identity_hints or LEGAL_IDENTITY_HINTS)
    route_hints = dict(issuer_route_hints or STATIC_ISSUER_ROUTE_HINTS)
    entity_profiles = load_layered_entity_profiles()
    evaluations = []
    for ticker in sorted(cohort):
        hint = hints.get(ticker, {})
        entity_class = entity_profiles.get(ticker, "unknown")
        evaluations.append(_exchange_evaluation(ticker, hint, retained_ownership_evidence, reg, entity_class, timestamp))
        evaluations.append(_issuer_evaluation(
            ticker, hint, route_hints.get(ticker), retained_ownership_evidence, reg, entity_class, timestamp,
        ))
    statuses = Counter(row["route_status"] for row in evaluations)
    route_classes = Counter(row["route_class"] for row in evaluations)
    consumed = sorted({row["retained_content_sha256"] for row in evaluations if row["retained_content_sha256"]})
    artifact: dict[str, Any] = {
        "schema_version": VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "validation_cohort_identity": {
            "cohort_name": "WAVE2_VALIDATION_COHORT_17", "candidate_count": len(cohort),
            "members": sorted(cohort), "members_hash": _hash(sorted(cohort)),
        },
        "authority_invariant": "NO_RETAINED_OWNERSHIP_EVIDENCE_MEANS_NO_OWNERSHIP_QUALIFIED_VERDICT",
        "static_hints_are_non_authoritative": True,
        "retained_evidence_content_identities_consumed": consumed,
        "summary_counts": {
            "total_candidates_evaluated": len(cohort), "total_route_evaluations": len(evaluations),
            "status_breakdown": dict(sorted(statuses.items())), "route_class_breakdown": dict(sorted(route_classes.items())),
            "ownership_qualified_routes": statuses[ROUTE_STATUS_OWNERSHIP_QUALIFIED],
            "ownership_evidence_missing_routes": statuses[ROUTE_STATUS_EVIDENCE_MISSING],
        },
        "route_evaluations": evaluations,
        "governed_registry_candidates": [],
        "registry_candidate_disposition": "NO_CANDIDATE_ELIGIBLE_WITHOUT_RETAINED_EVIDENCE",
        "governance_separation": {
            "discovery_performed": True, "registry_mutated": False, "activation_promoted": False,
            "financial_documents_acquired": 0, "financial_facts_created": 0,
            "fundamental_readiness_mutated": False,
        },
        "authority_boundaries": {
            "new_provider_added": False, "source_authority_promoted": False,
            "canonical_store_mutated": False, "runtime_database_mutated": False,
            "raw_as_traded_promoted": False, "liquidity_sizing_promoted": False,
            "valuation_or_recommendation_produced": False, "p3g_started": False,
        },
        "next_gate": "RETAINED_OFFICIAL_PROFILE_OR_ISSUER_DOMAIN_OWNERSHIP_EVIDENCE",
        "verdict": "OFFICIAL_SOURCE_ROUTE_EVIDENCE_BOUNDING_COMPLETE_NO_QUALIFIED_ROUTES",
    }
    artifact["artifact_sha256"] = _hash(artifact)
    artifact["artifact_identity"] = f"official_financial_source_route_discovery:{artifact['artifact_sha256']}"
    return artifact


def build_evidence_binding_correction(
    prior_v1_artifact: Mapping[str, Any], corrected_artifact: Mapping[str, Any], wave2_artifact: Mapping[str, Any],
) -> dict[str, Any]:
    """Record supersession without rewriting the historical V1 artifact."""
    prior_claimed = int(prior_v1_artifact.get("summary_counts", {}).get("ownership_qualified_routes", 0))
    counts = corrected_artifact["summary_counts"]
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": "official_source_route_evidence_binding_correction/v1",
        "authority": "RETAINED_CONTENT_ADDRESSED_EVIDENCE_REQUIRED_FOR_ROUTE_OWNERSHIP",
        "prior_v1": {
            "artifact_identity": prior_v1_artifact.get("artifact_identity"),
            "qualification_status": "IMPLEMENTATION_PRESENT_BUT_QUALIFICATION_INVALIDATED",
            "claimed_ownership_qualified_routes": prior_claimed,
            "invalidation_reason": "STATIC_ASSERTIONS_AND_GENERATED_ROUTE_TEMPLATES_WERE_NOT_RETAINED_OWNERSHIP_EVIDENCE",
        },
        "corrected_discovery": {
            "artifact_identity": corrected_artifact["artifact_identity"],
            "ownership_qualified_routes": counts["ownership_qualified_routes"],
            "ownership_evidence_missing_routes": counts["ownership_evidence_missing_routes"],
            "retained_evidence_content_identities_consumed": corrected_artifact["retained_evidence_content_identities_consumed"],
            "exchange_route_disposition": "ALL_UNQUALIFIED_NO_RETAINED_TICKER_SPECIFIC_PROFILE_EVIDENCE",
            "issuer_route_disposition": "ALL_UNQUALIFIED_NO_RETAINED_DOMAIN_OWNERSHIP_EVIDENCE",
            "registry_candidate_disposition": corrected_artifact["registry_candidate_disposition"],
        },
        "wave2_upstream_blocker": {
            "artifact_identity": wave2_artifact.get("artifact_identity"),
            "route_ownership_status_counts": wave2_artifact.get("source_discovery_summary", {}).get("route_ownership_status_counts", {}),
        },
        "supersession": {
            "historical_v1_preserved": True, "status": "SUPERSEDED_QUALIFICATION_INVALIDATED",
            "corrected_contract_supersedes_only_qualification_claims": True,
        },
        "governance_separation": dict(corrected_artifact["governance_separation"]),
        "verdict": "OFFICIAL_SOURCE_ROUTE_EVIDENCE_BINDING_CORRECTION_V1_COMPLETE",
    }
    payload["artifact_sha256"] = _hash(payload)
    payload["artifact_identity"] = "official_source_route_evidence_binding_correction:" + payload["artifact_sha256"]
    return payload


def execute(
    *, registry_path: Path = DEFAULT_REGISTRY, cohort: Sequence[str] = VALIDATION_COHORT_17,
    retained_ownership_evidence: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    return discover_and_qualify_routes(
        cohort=cohort, registry=registry, retained_ownership_evidence=retained_ownership_evidence,
    )
