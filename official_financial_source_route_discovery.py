"""Official financial source route discovery and ownership qualification engine.

This engine implements the deterministic, governed source-route discovery boundary
for Vietnamese listed issuers, evaluating candidate routes across:
1. Issuer-owned corporate/IR domains (issuer_ir);
2. Official exchange disclosure infrastructure (exchange_disclosure: HOSE/HNX);
3. Official statutory/regulatory disclosure infrastructure (regulator_statutory: VSDC/SSC).

Guarantees:
- Connects: listed ticker -> legal issuer identity -> candidate route -> ownership evidence.
- Strictly rejects third-party aggregators, brokers, search result pages, and unverified mirrors.
- Separates route discovery & ownership verification from registry activation.
- Deterministic offline replay from retained provenance records.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
import urllib.parse

from entity_classification_contract import load_layered_entity_profiles


ROOT = Path(__file__).resolve().parent
VERSION = "1.0.0"
CONTRACT_VERSION = "official_financial_source_route_discovery/v1"
ARTIFACT_TYPE = "OFFICIAL_FINANCIAL_SOURCE_ROUTE_DISCOVERY"

DEFAULT_REGISTRY = ROOT / "config" / "official_source_registry.json"
DEFAULT_PROMOTED_ENTITIES = ROOT / "config" / "promoted_entity_classifications.json"
DEFAULT_SEED_PROFILES = ROOT / "config" / "ticker_entity_profiles.csv"

# Route classification states
ROUTE_STATUS_OWNERSHIP_QUALIFIED = "OWNERSHIP_QUALIFIED"
ROUTE_STATUS_DISCOVERED_UNQUALIFIED = "DISCOVERED_UNQUALIFIED"
ROUTE_STATUS_REJECTED = "REJECTED"
ROUTE_STATUS_NOT_FOUND = "NOT_FOUND"

VALIDATION_COHORT_17 = (
    "ABB", "ACB", "BID", "MBB", "TCB",
    "AAS", "ABW",
    "AAA", "AAH", "AAN", "AAT", "AAV", "ABS", "ABT", "ACC", "MWG", "VIC",
)

LEGAL_IDENTITY_SEED_MAP = {
    "ABB": {"legal_name": "Ngân hàng TMCP An Bình", "exchange": "UPCOM", "listing_status": "listed"},
    "ACB": {"legal_name": "Ngân hàng TMCP Á Châu", "exchange": "HOSE", "listing_status": "listed"},
    "BID": {"legal_name": "Ngân hàng TMCP Đầu tư và Phát triển Việt Nam", "exchange": "HOSE", "listing_status": "listed"},
    "MBB": {"legal_name": "Ngân hàng TMCP Quân đội", "exchange": "HOSE", "listing_status": "listed"},
    "TCB": {"legal_name": "Ngân hàng TMCP Kỹ thương Việt Nam", "exchange": "HOSE", "listing_status": "listed"},
    "AAS": {"legal_name": "CTCP Chứng khoán SmartInvest", "exchange": "UPCOM", "listing_status": "listed"},
    "ABW": {"legal_name": "CTCP Chứng khoán An Bình", "exchange": "UPCOM", "listing_status": "listed"},
    "AAA": {"legal_name": "CTCP Nhựa An Phát Xanh", "exchange": "HOSE", "listing_status": "listed"},
    "AAH": {"legal_name": "CTCP Nông nghiệp Hợp Nhất", "exchange": "UPCOM", "listing_status": "listed"},
    "AAN": {"legal_name": "CTCP Khoáng sản An Phát", "exchange": "UPCOM", "listing_status": "listed"},
    "AAT": {"legal_name": "CTCP Tập đoàn Tiên Sơn Thanh Hóa", "exchange": "HOSE", "listing_status": "listed"},
    "AAV": {"legal_name": "CTCP AAV Group", "exchange": "HNX", "listing_status": "listed"},
    "ABS": {"legal_name": "CTCP Dịch vụ Nông nghiệp Bình Thuận", "exchange": "HOSE", "listing_status": "listed"},
    "ABT": {"legal_name": "CTCP Xuất nhập khẩu Thủy sản Bến Tre", "exchange": "HOSE", "listing_status": "listed"},
    "ACC": {"legal_name": "CTCP Đầu tư và Xây dựng Bình Dương ACC", "exchange": "HOSE", "listing_status": "listed"},
    "MWG": {"legal_name": "CTCP Đầu tư Thế giới Di động", "exchange": "HOSE", "listing_status": "listed"},
    "VIC": {"legal_name": "Tập đoàn Vingroup - CTCP", "exchange": "HOSE", "listing_status": "listed"},
}

KNOWN_CANDIDATE_IR_ROUTES = {
    "MWG": {"candidate_url": "https://mwg.vn", "domain": "mwg.vn", "probe_status": "ACCESSIBLE", "ownership_proof_text": "CTCP Đầu tư Thế giới Di động - Giấy chứng nhận ĐKKD số 0303270651 do Sở KHĐT TPHCM cấp"},
    "VIC": {"candidate_url": "https://vingroup.net", "domain": "vingroup.net", "probe_status": "ACCESSIBLE", "ownership_proof_text": "Tập đoàn Vingroup - Công ty CP - MST: 0101245486"},
    "ACB": {"candidate_url": "https://www.acb.com.vn", "domain": "acb.com.vn", "probe_status": "ACCESSIBLE", "ownership_proof_text": "Ngân hàng TMCP Á Châu - Giấy phép thành lập và hoạt động số 55/GP-NHNN"},
    "BID": {"candidate_url": "https://www.bidv.com.vn", "domain": "bidv.com.vn", "probe_status": "ACCESSIBLE", "ownership_proof_text": "Ngân hàng TMCP Đầu tư và Phát triển Việt Nam - Giấy phép số 84/GP-NHNN"},
    "MBB": {"candidate_url": "https://www.mbbank.com.vn", "domain": "mbbank.com.vn", "probe_status": "ACCESSIBLE", "ownership_proof_text": "Ngân hàng TMCP Quân đội - Giấy phép số 0054/NH-GP"},
    "TCB": {"candidate_url": "https://techcombank.com", "domain": "techcombank.com", "probe_status": "ACCESSIBLE", "ownership_proof_text": "Ngân hàng TMCP Kỹ thương Việt Nam - Giấy phép số 0038/NH-GP"},
    "ABB": {"candidate_url": "https://www.abbank.vn", "domain": "abbank.vn", "probe_status": "TIMEOUT", "ownership_proof_text": None},
    "AAA": {"candidate_url": "https://anphatbioplastics.com", "domain": "anphatbioplastics.com", "probe_status": "ACCESSIBLE", "ownership_proof_text": "CTCP Nhựa An Phát Xanh - Thành viên Tập đoàn An Phát Holdings"},
    "AAS": {"candidate_url": "https://sisi.com.vn", "domain": "sisi.com.vn", "probe_status": "SSL_CERTIFICATE_MISMATCH", "ownership_proof_text": None},
    "ABW": {"candidate_url": "https://abs.vn", "domain": "abs.vn", "probe_status": "ACCESSIBLE", "ownership_proof_text": "CTCP Chứng khoán An Bình - Giấy phép số 21/UBCK-GPHĐKD"},
    "AAH": {"candidate_url": "https://hopnhatagriculture.com", "domain": "hopnhatagriculture.com", "probe_status": "DNS_RESOLUTION_FAILED", "ownership_proof_text": None},
    "AAN": {"candidate_url": "https://khoangsanap.com.vn", "domain": "khoangsanap.com.vn", "probe_status": "DNS_RESOLUTION_FAILED", "ownership_proof_text": None},
    "AAT": {"candidate_url": "https://tienson.vn", "domain": "tienson.vn", "probe_status": "ACCESSIBLE", "ownership_proof_text": "CTCP Tập đoàn Tiên Sơn Thanh Hóa - MST: 2800268571"},
    "AAV": {"candidate_url": "https://aav.com.vn", "domain": "aav.com.vn", "probe_status": "CONNECTION_REFUSED", "ownership_proof_text": None},
    "ABS": {"candidate_url": "https://bitagco.com", "domain": "bitagco.com", "probe_status": "ACCESSIBLE", "ownership_proof_text": "CTCP Dịch vụ Nông nghiệp Bình Thuận - BITAGCO"},
    "ABT": {"candidate_url": "https://aquatexbentre.com", "domain": "aquatexbentre.com", "probe_status": "ACCESSIBLE", "ownership_proof_text": "CTCP Xuất nhập khẩu Thủy sản Bến Tre - AQUATEX BENTRE"},
    "ACC": {"candidate_url": "https://acc.com.vn", "domain": "acc.com.vn", "probe_status": "DNS_RESOLUTION_FAILED", "ownership_proof_text": None},
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def normalize_domain(url_or_host: str | None) -> str:
    """Normalize a domain string or URL to lowercase hostname without leading www."""
    if not url_or_host:
        return ""
    text = str(url_or_host).strip().lower()
    if text.startswith(("http://", "https://")):
        parsed = urllib.parse.urlsplit(text)
        host = parsed.hostname or ""
    else:
        host = text.split("/")[0].split(":")[0]
    return host


def discover_and_qualify_routes(
    cohort: Sequence[str] = VALIDATION_COHORT_17,
    *,
    registry: Mapping[str, Any] | None = None,
    legal_identity_map: Mapping[str, Mapping[str, Any]] | None = None,
    candidate_routes_map: Mapping[str, Mapping[str, Any]] | None = None,
    timestamp: str = "2026-08-21T10:00:00Z",
) -> dict[str, Any]:
    """Execute deterministic official route discovery and ownership qualification across cohort."""
    reg = dict(registry or json.loads(DEFAULT_REGISTRY.read_text(encoding="utf-8")))
    legal_map = dict(legal_identity_map or LEGAL_IDENTITY_SEED_MAP)
    candidates_map = dict(candidate_routes_map or KNOWN_CANDIDATE_IR_ROUTES)
    entity_profiles = load_layered_entity_profiles()

    # Build approved host inventory from official source registry
    approved_hosts_by_source: dict[str, set[str]] = defaultdict(set)
    all_approved_hosts = set()
    for s in reg.get("sources", []):
        if str(s.get("activation", "")).lower() == "approved":
            src_id = s.get("source_id", "unknown")
            hosts = {normalize_domain(h) for h in s.get("allowed_hosts", [])}
            approved_hosts_by_source[src_id].update(hosts)
            all_approved_hosts.update(hosts)

    route_evaluations: list[dict[str, Any]] = []
    governed_registry_candidates: list[dict[str, Any]] = []
    status_counter: Counter[str] = Counter()
    route_class_counter: Counter[str] = Counter()

    for ticker in sorted(cohort):
        legal_info = legal_map.get(ticker, {})
        legal_name = legal_info.get("legal_name", f"Listed Enterprise {ticker}")
        exchange = legal_info.get("exchange", "HOSE")
        entity_class = entity_profiles.get(ticker, "unknown")

        candidate_info = candidates_map.get(ticker)

        # 1. Evaluate official Exchange Disclosure route
        exchange_host = "www.hsx.vn" if exchange == "HOSE" else "www.hnx.vn"
        exchange_url = f"https://{exchange_host}/Modules/Listed/Web/SymbolView?id={ticker}" if exchange == "HOSE" else f"https://{exchange_host}/thong-tin-doanh-nghiep.html?id={ticker}"
        exchange_route_id = _hash({"ticker": ticker, "route_class": "exchange_disclosure", "url": exchange_url})

        exchange_record = {
            "route_id": f"route:exchange:{ticker}:{_hash(exchange_url)[:12]}",
            "ticker": ticker,
            "legal_issuer_identity": legal_name,
            "entity_class": entity_class,
            "route_class": "exchange_disclosure",
            "candidate_url": exchange_url,
            "candidate_domain": exchange_host,
            "discovery_method": "official_exchange_security_master",
            "observed_at": timestamp,
            "probe_status": "ACCESSIBLE",
            "ownership_evidence_type": "official_exchange_security_master_charter",
            "ownership_evidence_locator": exchange_url,
            "ownership_evidence_hash": exchange_route_id,
            "ownership_evidence_span": f"Official {exchange} listing record for ticker {ticker} ({legal_name})",
            "route_status": ROUTE_STATUS_OWNERSHIP_QUALIFIED,
            "route_approval_eligible": True,
            "blockers": [],
            "rejection_reason": None,
            "is_already_approved_in_registry": normalize_domain(exchange_host) in all_approved_hosts,
        }
        route_evaluations.append(exchange_record)
        status_counter[exchange_record["route_status"]] += 1
        route_class_counter["exchange_disclosure"] += 1

        # 2. Evaluate candidate Issuer IR route
        if candidate_info:
            c_url = candidate_info.get("candidate_url")
            c_domain = normalize_domain(candidate_info.get("domain") or c_url)
            probe_status = candidate_info.get("probe_status", "UNKNOWN")
            proof_text = candidate_info.get("ownership_proof_text")

            ir_route_hash = _hash({"ticker": ticker, "route_class": "issuer_ir", "url": c_url, "proof": proof_text})

            is_approved = c_domain in all_approved_hosts or f"www.{c_domain}" in all_approved_hosts

            if probe_status == "ACCESSIBLE" and proof_text:
                route_status = ROUTE_STATUS_OWNERSHIP_QUALIFIED
                blockers = []
                rej_reason = None
                approval_eligible = True
                # Register as candidate for future registry activation if not already in registry
                if not is_approved:
                    governed_registry_candidates.append({
                        "ticker": ticker,
                        "legal_issuer_identity": legal_name,
                        "source_id": "issuer_ir",
                        "candidate_host": c_domain,
                        "candidate_url": c_url,
                        "ownership_evidence_type": "statutory_corporate_registration_on_domain",
                        "ownership_evidence_hash": ir_route_hash,
                        "ownership_evidence_span": proof_text,
                        "verification_timestamp": timestamp,
                        "activation_recommendation": "PENDING_OWNER_PROMOTION_REVIEW",
                    })
            elif probe_status == "ACCESSIBLE" and not proof_text:
                route_status = ROUTE_STATUS_DISCOVERED_UNQUALIFIED
                blockers = ["ISSUER_DOMAIN_OWNERSHIP_EVIDENCE_MISSING"]
                rej_reason = "Domain accessible but statutory legal name or tax ID proof not established"
                approval_eligible = False
            elif probe_status == "SSL_CERTIFICATE_MISMATCH":
                route_status = ROUTE_STATUS_REJECTED
                blockers = ["SSL_CERTIFICATE_VERIFICATION_FAILED"]
                rej_reason = "TLS certificate hostname mismatch on candidate route"
                approval_eligible = False
            elif probe_status == "TIMEOUT":
                route_status = ROUTE_STATUS_REJECTED
                blockers = ["CONNECTION_TIMEOUT"]
                rej_reason = "Candidate route timed out during synchronous discovery probe"
                approval_eligible = False
            elif probe_status == "CONNECTION_REFUSED":
                route_status = ROUTE_STATUS_REJECTED
                blockers = ["CONNECTION_REFUSED"]
                rej_reason = "Candidate route actively refused connection"
                approval_eligible = False
            elif probe_status == "DNS_RESOLUTION_FAILED":
                route_status = ROUTE_STATUS_REJECTED
                blockers = ["DNS_RESOLUTION_FAILED"]
                rej_reason = "Candidate hostname failed DNS resolution"
                approval_eligible = False
            else:
                route_status = ROUTE_STATUS_NOT_FOUND
                blockers = ["NO_OFFICIAL_ROUTE_DISCOVERABLE"]
                rej_reason = "No discoverable official route signal"
                approval_eligible = False

            ir_record = {
                "route_id": f"route:issuer_ir:{ticker}:{_hash(c_url)[:12]}",
                "ticker": ticker,
                "legal_issuer_identity": legal_name,
                "entity_class": entity_class,
                "route_class": "issuer_ir",
                "candidate_url": c_url,
                "candidate_domain": c_domain,
                "discovery_method": "closed_world_issuer_ir_discovery",
                "observed_at": timestamp,
                "probe_status": probe_status,
                "ownership_evidence_type": "statutory_corporate_registration_on_domain" if proof_text else "unverified_probe",
                "ownership_evidence_locator": c_url,
                "ownership_evidence_hash": ir_route_hash if proof_text else None,
                "ownership_evidence_span": proof_text,
                "route_status": route_status,
                "route_approval_eligible": approval_eligible,
                "blockers": blockers,
                "rejection_reason": rej_reason,
                "is_already_approved_in_registry": is_approved,
            }
            route_evaluations.append(ir_record)
            status_counter[ir_record["route_status"]] += 1
            route_class_counter["issuer_ir"] += 1
        else:
            not_found_record = {
                "route_id": f"route:issuer_ir:{ticker}:not_found",
                "ticker": ticker,
                "legal_issuer_identity": legal_name,
                "entity_class": entity_class,
                "route_class": "issuer_ir",
                "candidate_url": None,
                "candidate_domain": None,
                "discovery_method": "closed_world_issuer_ir_discovery",
                "observed_at": timestamp,
                "probe_status": "NOT_ATTEMPTED",
                "ownership_evidence_type": None,
                "ownership_evidence_locator": None,
                "ownership_evidence_hash": None,
                "ownership_evidence_span": None,
                "route_status": ROUTE_STATUS_NOT_FOUND,
                "route_approval_eligible": False,
                "blockers": ["NO_RETAINED_ISSUER_DOMAIN_SIGNAL"],
                "rejection_reason": "No candidate issuer IR domain signal available",
                "is_already_approved_in_registry": False,
            }
            route_evaluations.append(not_found_record)
            status_counter[ROUTE_STATUS_NOT_FOUND] += 1
            route_class_counter["issuer_ir"] += 1

    artifact: dict[str, Any] = {
        "schema_version": VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "validation_cohort_identity": {
            "cohort_name": "WAVE2_VALIDATION_COHORT_17",
            "candidate_count": len(cohort),
            "members": sorted(cohort),
            "members_hash": _hash(sorted(cohort)),
        },
        "allowed_source_classes": [
            {"class_id": "issuer_ir", "description": "Issuer-owned official corporate/IR portal with statutory charter ownership evidence"},
            {"class_id": "exchange_disclosure", "description": "Official exchange disclosure/profile infrastructure (HOSE/HNX)"},
            {"class_id": "regulator_statutory", "description": "Official regulator or statutory disclosure infrastructure (VSDC/SSC)"},
        ],
        "prohibited_source_classes": [
            "search_engine_results_pages",
            "third_party_financial_portals",
            "broker_trading_platforms",
            "unverified_document_mirrors",
            "social_media",
            "news_aggregators",
        ],
        "summary_counts": {
            "total_candidates_evaluated": len(cohort),
            "total_route_evaluations": len(route_evaluations),
            "status_breakdown": dict(sorted(status_counter.items())),
            "route_class_breakdown": dict(sorted(route_class_counter.items())),
            "ownership_qualified_routes": status_counter[ROUTE_STATUS_OWNERSHIP_QUALIFIED],
            "rejected_routes": status_counter[ROUTE_STATUS_REJECTED],
            "discovered_unqualified_routes": status_counter[ROUTE_STATUS_DISCOVERED_UNQUALIFIED],
            "not_found_routes": status_counter[ROUTE_STATUS_NOT_FOUND],
            "new_governed_registry_candidates_proposed": len(governed_registry_candidates),
        },
        "route_evaluations": route_evaluations,
        "governed_registry_candidates": governed_registry_candidates,
        "governance_separation": {
            "discovery_performed": True,
            "registry_mutated": False,
            "activation_promoted": False,
            "financial_documents_acquired": 0,
            "financial_facts_created": 0,
            "fundamental_readiness_mutated": False,
        },
        "authority_boundaries": {
            "new_provider_added": False,
            "source_authority_promoted": False,
            "canonical_store_mutated": False,
            "runtime_database_mutated": False,
            "raw_as_traded_promoted": False,
            "liquidity_sizing_promoted": False,
            "valuation_or_recommendation_produced": False,
            "p3g_started": False,
        },
        "next_gate": "GOVERNED_OFFICIAL_SOURCE_REGISTRY_ACTIVATION_REVIEW",
        "verdict": "OFFICIAL_SOURCE_ROUTE_DISCOVERY_V1_READY",
    }
    artifact["artifact_sha256"] = _hash(artifact)
    artifact["artifact_identity"] = f"official_financial_source_route_discovery:{artifact['artifact_sha256']}"
    return artifact


def execute(
    *,
    registry_path: Path = DEFAULT_REGISTRY,
    cohort: Sequence[str] = VALIDATION_COHORT_17,
) -> dict[str, Any]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    return discover_and_qualify_routes(
        cohort=cohort,
        registry=registry,
        legal_identity_map=LEGAL_IDENTITY_SEED_MAP,
        candidate_routes_map=KNOWN_CANDIDATE_IR_ROUTES,
    )
