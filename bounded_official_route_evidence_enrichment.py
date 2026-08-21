"""Bounded official route evidence enrichment engine V1.

This engine executes a strictly bounded, synchronous acquisition pass over the
four non-ready Wave-2 issuers (AAA, BID, AAT, ABT), enforcing:
1. Hard request budgets (AAA: 1, BID: 2, AAT: 2, ABT: 2; total <= 7 first-party requests);
2. Retain-on-acquisition: exact response bytes are immediately written to disk with SHA-256;
3. Early stop: no subsequent request is made once sufficient evidence is acquired;
4. Byte-derived extraction: evaluate legal identity strictly against retained bytes;
5. Preservation of historical truth: AAT's historical tienson.vn conflict is preserved
   alongside the new independent candidate route;
6. Separation of discovery from activation: candidate routes are marked
   PENDING_OWNER_PROMOTION_REVIEW with zero source registry mutations.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import ssl
from typing import Any, Mapping, Sequence
import urllib.error
import urllib.parse
import urllib.request
import certifi

from official_financial_source_route_discovery import (
    LEGAL_IDENTITY_HINTS,
    normalize_domain,
)
from prospective_route_ownership_review import (
    BRANDING_ONLY,
    COPYRIGHT_LEGAL_ENTITY,
    FULL_LEGAL_ENTITY_NAME,
    IDENTITY_CONFLICT,
    INSUFFICIENT_IDENTITY_EVIDENCE,
    OWNER_REVIEW_READY,
    STATUTORY_REGISTRATION_IDENTIFIER,
    STRUCTURED_LEGAL_NAME,
    TECHNICAL_EVIDENCE_INVALID,
    _conflicting_identity,
    _branding_evidence,
    _identity_evidence,
    _structured_legal_names,
    normalize_legal_identity,
)

ROOT = Path(__file__).resolve().parent
VERSION = "1.0.0"
CONTRACT_VERSION = "bounded_official_route_evidence_enrichment/v1"
ARTIFACT_TYPE = "BOUNDED_OFFICIAL_ROUTE_EVIDENCE_ENRICHMENT"
REDIRECT_AUTHORITY_CONTRACT_VERSION = "redirect_domain_authority/v1"

SAFE_SAME_AUTHORITY_REDIRECT = "SAFE_SAME_AUTHORITY_REDIRECT"
NO_REDIRECT_SAME_HOST = "NO_REDIRECT_SAME_HOST"
CROSS_DOMAIN_REDIRECT_REQUIRES_EVIDENCE = "CROSS_DOMAIN_REDIRECT_REQUIRES_EVIDENCE"
REDIRECT_LINEAGE_INVALID = "REDIRECT_LINEAGE_INVALID"
ROUTE_AUTHORITY_EVIDENCE_REQUIRED = "ROUTE_AUTHORITY_EVIDENCE_REQUIRED"

OPERATIONS_REVIEW_DIR = (
    ROOT / "operations-review" / "bounded-official-route-evidence-enrichment-v1-20260821"
)
ENRICHMENT_EVIDENCE_DIR = OPERATIONS_REVIEW_DIR / "evidence"
DEFAULT_REGISTRY_PATH = ROOT / "config" / "official_source_registry.json"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StockLookup/1.0"

# Scope and hard request limits
TARGET_TICKERS: tuple[str, ...] = ("AAA", "BID", "AAT", "ABT")

REQUEST_BUDGET: dict[str, int] = {
    "AAA": 1,
    "BID": 2,
    "AAT": 2,
    "ABT": 2,
}

# Fixed candidate URL plans in priority order
FIXED_ROUTE_PLANS: dict[str, list[str]] = {
    "AAA": [
        "https://anphatbioplastics.com/ve-chung-toi/",
    ],
    "BID": [
        "https://www.bidv.com.vn/vn/quan-he-nha-dau-tu",
        "https://www.bidv.com.vn/vn/ve-bidv",
    ],
    "AAT": [
        "https://tiensonaus.com/gioi-thieu/",
        "https://tiensonaus.com/",
    ],
    "ABT": [
        "https://aquatexbentre.com/cong/",
        "https://aquatexbentre.com/investors-copy/",
    ],
}

# Baseline statuses from prospective route ownership review V1
BASELINE_STATUSES: dict[str, dict[str, Any]] = {
    "AAA": {
        "status": INSUFFICIENT_IDENTITY_EVIDENCE,
        "candidate_locator": "https://anphatbioplastics.com",
        "evidence_types": [BRANDING_ONLY],
        "reason_codes": [
            "NO_RETAINED_STATUTORY_IDENTIFIER",
            "NO_BYTE_DERIVED_FULL_LEGAL_IDENTITY_MATCH",
        ],
    },
    "BID": {
        "status": INSUFFICIENT_IDENTITY_EVIDENCE,
        "candidate_locator": "https://www.bidv.com.vn",
        "evidence_types": [BRANDING_ONLY],
        "reason_codes": [
            "NO_RETAINED_STATUTORY_IDENTIFIER",
            "NO_BYTE_DERIVED_FULL_LEGAL_IDENTITY_MATCH",
        ],
    },
    "AAT": {
        "status": IDENTITY_CONFLICT,
        "candidate_locator": "https://tienson.vn",
        "evidence_types": [BRANDING_ONLY],
        "reason_codes": [
            "NO_RETAINED_STATUTORY_IDENTIFIER",
            "RETAINED_LEGAL_IDENTITY_CONFLICTS_WITH_EXPECTED_ISSUER",
        ],
    },
    "ABT": {
        "status": INSUFFICIENT_IDENTITY_EVIDENCE,
        "candidate_locator": "https://aquatexbentre.com",
        "evidence_types": [BRANDING_ONLY],
        "reason_codes": [
            "NO_RETAINED_STATUTORY_IDENTIFIER",
            "NO_BYTE_DERIVED_FULL_LEGAL_IDENTITY_MATCH",
        ],
    },
}

# Offline catalog for deterministic replay without network
OFFLINE_ENRICHED_EVIDENCE_CATALOG: dict[str, list[dict[str, Any]]] = {
    "AAA": [
        {
            "requested_url": "https://anphatbioplastics.com/ve-chung-toi/",
            "final_url": "https://anphatbioplastics.com/ve-chung-toi/",
            "relative_path": "operations-review/bounded-official-route-evidence-enrichment-v1-20260821/evidence/AAA_issuer_ir_82562472198e.html",
            "sha256": "82562472198e55f65eae2b61d79d8a2831decb9704e96b6306d56f3b4a9abb75",
            "mime_type": "text/html; charset=UTF-8",
            "bytes_length": 183185,
            "http_status": 200,
            "redirect_chain": [],
        },
    ],
    "BID": [
        {
            "requested_url": "https://www.bidv.com.vn/vn/quan-he-nha-dau-tu",
            "final_url": "https://bidv.com.vn/vn/quan-he-nha-dau-tu",
            "relative_path": "operations-review/bounded-official-route-evidence-enrichment-v1-20260821/evidence/BID_issuer_ir_db7c65a90092.html",
            "sha256": "db7c65a9009248ca7b67dd47929ebd91ca1ba4158471c3a03881037d56b63cca",
            "mime_type": "text/html; charset=UTF-8",
            "bytes_length": 395053,
            "http_status": 200,
            "redirect_chain": ["https://bidv.com.vn/vn/quan-he-nha-dau-tu"],
        },
    ],
    "AAT": [
        {
            "requested_url": "https://tiensonaus.com/gioi-thieu/",
            "final_url": "https://tiensonaus.com/gioi-thieu/",
            "relative_path": "operations-review/bounded-official-route-evidence-enrichment-v1-20260821/evidence/AAT_issuer_ir_44f038434d5f.html",
            "sha256": "44f038434d5f3f68e70e79c4b2d7d6f26ee87f7e7438992e63303280db42bc97",
            "mime_type": "text/html; charset=UTF-8",
            "bytes_length": 75956,
            "http_status": 200,
            "redirect_chain": [],
        },
    ],
    "ABT": [
        {
            "requested_url": "https://aquatexbentre.com/cong/",
            "final_url": "https://aquatexbentre.com/cong/",
            "relative_path": "operations-review/bounded-official-route-evidence-enrichment-v1-20260821/evidence/ABT_issuer_ir_871db402f981.html",
            "sha256": "871db402f9814dc2d5fc64d9e0bd5cdd48fa020959d3af684daa070b7f8e505a",
            "mime_type": "text/html; charset=UTF-8",
            "bytes_length": 303339,
            "http_status": 200,
            "redirect_chain": [],
        },
        {
            "requested_url": "https://aquatexbentre.com/investors-copy/",
            "final_url": "https://aquatexbentre.com/investors-copy/",
            "relative_path": "operations-review/bounded-official-route-evidence-enrichment-v1-20260821/evidence/ABT_issuer_ir_709bdcb2a9f3.html",
            "sha256": "709bdcb2a9f3dbd34fde46d2a6eb4491eba841373907ac985a4eb3188d593498",
            "mime_type": "text/html; charset=UTF-8",
            "bytes_length": 337162,
            "http_status": 200,
            "redirect_chain": [],
        },
    ],
}


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def validate_redirect_domain_authority(
    requested_url: str,
    final_url: str,
    redirect_chain: Sequence[str],
) -> dict[str, Any]:
    """Validate request-to-final authority without collapsing arbitrary subdomains.

    V1 recognizes one narrowly defined canonicalization only: an exact leading
    ``www.`` toggle on the same remaining hostname.  It preserves both hosts
    in lineage and never treats other subdomains as equivalent.
    """
    requested_host = normalize_domain(requested_url)
    final_host = normalize_domain(final_url)
    chain = [str(item) for item in redirect_chain]
    chain_final_host = normalize_domain(chain[-1]) if chain else ""

    if not requested_host or not final_host:
        return {
            "requested_host": requested_host,
            "final_host": final_host,
            "redirect_chain": chain,
            "redirect_authority_verdict": REDIRECT_LINEAGE_INVALID,
            "safe_same_authority": False,
            "reason_code": "REQUESTED_OR_FINAL_HOST_MISSING",
        }
    if chain and chain_final_host != final_host:
        return {
            "requested_host": requested_host,
            "final_host": final_host,
            "redirect_chain": chain,
            "redirect_authority_verdict": REDIRECT_LINEAGE_INVALID,
            "safe_same_authority": False,
            "reason_code": "REDIRECT_CHAIN_DOES_NOT_TERMINATE_AT_FINAL_HOST",
        }
    if requested_host != final_host and not chain:
        return {
            "requested_host": requested_host,
            "final_host": final_host,
            "redirect_chain": chain,
            "redirect_authority_verdict": REDIRECT_LINEAGE_INVALID,
            "safe_same_authority": False,
            "reason_code": "CROSS_HOST_FINAL_URL_REQUIRES_RETAINED_REDIRECT_CHAIN",
        }

    def exact_www_pair(left: str, right: str) -> bool:
        return left == f"www.{right}" or right == f"www.{left}"

    lineage_hosts = [requested_host] + [normalize_domain(item) for item in chain]
    if chain and any(
        left != right and not exact_www_pair(left, right)
        for left, right in zip(lineage_hosts, lineage_hosts[1:])
    ):
        return {
            "requested_host": requested_host,
            "final_host": final_host,
            "redirect_chain": chain,
            "redirect_authority_verdict": CROSS_DOMAIN_REDIRECT_REQUIRES_EVIDENCE,
            "safe_same_authority": False,
            "reason_code": "REDIRECT_CHAIN_CONTAINS_NON_WWW_AUTHORITY_CHANGE",
        }
    if requested_host == final_host:
        return {
            "requested_host": requested_host,
            "final_host": final_host,
            "redirect_chain": chain,
            "redirect_authority_verdict": NO_REDIRECT_SAME_HOST,
            "safe_same_authority": True,
            "reason_code": "REQUESTED_AND_FINAL_HOST_MATCH",
        }

    if exact_www_pair(requested_host, final_host):
        return {
            "requested_host": requested_host,
            "final_host": final_host,
            "redirect_chain": chain,
            "redirect_authority_verdict": SAFE_SAME_AUTHORITY_REDIRECT,
            "safe_same_authority": True,
            "reason_code": "EXACT_WWW_CANONICALIZATION_WITH_RETAINED_REDIRECT_LINEAGE",
        }
    return {
        "requested_host": requested_host,
        "final_host": final_host,
        "redirect_chain": chain,
        "redirect_authority_verdict": CROSS_DOMAIN_REDIRECT_REQUIRES_EVIDENCE,
        "safe_same_authority": False,
        "reason_code": "REQUESTED_AND_FINAL_HOSTS_ARE_NOT_EXACT_WWW_EQUIVALENTS",
    }


def synchronous_fetch_and_retain(
    ticker: str,
    url: str,
    evidence_dir: Path = ENRICHMENT_EVIDENCE_DIR,
    timestamp: str = "2026-08-21T18:45:00Z",
) -> dict[str, Any]:
    """Execute a single synchronous foreground HTTP GET and retain bytes immediately."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    ctx = ssl.create_default_context(cafile=certifi.where())
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            http_status = resp.status
            final_url = resp.geturl()
            content_type = resp.headers.get("Content-Type", "text/html; charset=UTF-8")
            raw_bytes = resp.read()
    except urllib.error.HTTPError as e:
        return {
            "ticker": ticker,
            "requested_url": url,
            "final_url": url,
            "http_status": e.code,
            "content_type": None,
            "content_bytes_length": 0,
            "raw_sha256": None,
            "retained_file_path": None,
            "retrieval_timestamp": timestamp,
            "redirect_chain": [],
            "technical_error": f"HTTP Error {e.code}: {e.reason}",
            "success": False,
        }
    except Exception as e:
        return {
            "ticker": ticker,
            "requested_url": url,
            "final_url": url,
            "http_status": None,
            "content_type": None,
            "content_bytes_length": 0,
            "raw_sha256": None,
            "retained_file_path": None,
            "retrieval_timestamp": timestamp,
            "redirect_chain": [],
            "technical_error": f"{type(e).__name__}: {e}",
            "success": False,
        }

    raw_sha = hashlib.sha256(raw_bytes).hexdigest()
    file_name = f"{ticker}_issuer_ir_{raw_sha[:12]}.html"
    file_path = evidence_dir / file_name
    file_path.write_bytes(raw_bytes)

    redirect_chain = [final_url] if final_url != url else []

    return {
        "ticker": ticker,
        "requested_url": url,
        "final_url": final_url,
        "http_status": http_status,
        "content_type": content_type,
        "content_bytes_length": len(raw_bytes),
        "raw_sha256": raw_sha,
        "retained_file_path": str(file_path.relative_to(ROOT)).replace("\\", "/"),
        "retrieval_timestamp": timestamp,
        "redirect_chain": redirect_chain,
        "technical_error": None,
        "success": True,
    }


def review_retained_bytes(
    ticker: str,
    requested_url: str,
    final_url: str,
    raw_bytes: bytes,
    raw_sha: str,
    retained_file_path: str,
    redirect_chain: list[str],
    timestamp: str = "2026-08-21T18:45:00Z",
) -> dict[str, Any]:
    """Perform byte-derived prospective review over locally retained file bytes."""
    expected_identity = str(LEGAL_IDENTITY_HINTS[ticker]["legal_name"])
    norm_expected = normalize_legal_identity(expected_identity)
    redirect_authority = validate_redirect_domain_authority(
        requested_url,
        final_url,
        redirect_chain,
    )
    requested_host = redirect_authority["requested_host"]
    final_host = redirect_authority["final_host"]
    candidate_host = final_host
    raw_text = raw_bytes.decode("utf-8", errors="replace")

    identity_evidence, observed_identity = _identity_evidence(raw_text, expected_identity)
    conflict = _conflicting_identity(raw_text)

    reason_codes: list[str] = []
    identity_match = bool(
        observed_identity
        and normalize_legal_identity(observed_identity) == norm_expected
    )

    if not redirect_authority["safe_same_authority"]:
        status = ROUTE_AUTHORITY_EVIDENCE_REQUIRED
        reason_codes.extend([
            redirect_authority["redirect_authority_verdict"],
            redirect_authority["reason_code"],
        ])
    elif identity_match:
        status = OWNER_REVIEW_READY
        reason_codes.append("BYTE_DERIVED_LEGAL_IDENTITY_MATCH")
    elif conflict:
        status = IDENTITY_CONFLICT
        reason_codes.append("RETAINED_LEGAL_IDENTITY_CONFLICTS_WITH_EXPECTED_ISSUER")
        observed_identity = conflict
        identity_evidence = _branding_evidence(raw_text, candidate_host)
    else:
        status = INSUFFICIENT_IDENTITY_EVIDENCE
        reason_codes.append("NO_BYTE_DERIVED_FULL_LEGAL_IDENTITY_MATCH")
        # Check for known unsupported abbreviation/language in ABT
        if "XNK" in raw_text:
            reason_codes.append("ABBREVIATION_ONLY_XNK_REQUIRES_FULL_LEGAL_EXPANSION_CONTRACT")
        if "IMPORT AND EXPORT JOINT STOCK COMPANY" in raw_text:
            reason_codes.append("ENGLISH_LEGAL_IDENTITY_REQUIRES_ALIAS_CONTRACT")
        identity_evidence = _branding_evidence(raw_text, candidate_host)

    evidence_types = sorted({item["evidence_type"] for item in identity_evidence})
    domain_bound = bool(redirect_authority["safe_same_authority"])

    content_identity = _hash({
        "ticker": ticker,
        "candidate_host": candidate_host,
        "requested_url": requested_url,
        "final_url": final_url,
        "retained_sha256": raw_sha,
        "identity_evidence": identity_evidence,
        "redirect_authority_verdict": redirect_authority["redirect_authority_verdict"],
        "status": status,
    })

    return {
        "ticker": ticker,
        "candidate_host": candidate_host,
        "candidate_locator": final_url,
        "requested_url": requested_url,
        "requested_host": requested_host,
        "final_url": final_url,
        "final_host": final_host,
        "redirect_chain": list(redirect_chain),
        "redirect_authority_contract_version": REDIRECT_AUTHORITY_CONTRACT_VERSION,
        "redirect_authority_verdict": redirect_authority["redirect_authority_verdict"],
        "retained_file_path": retained_file_path.replace("\\", "/"),
        "retained_sha256": raw_sha,
        "content_bytes_length": len(raw_bytes),
        "retrieval_timestamp": timestamp,
        "retained_bytes_valid": True,
        "expected_issuer_identity": expected_identity,
        "normalized_expected_issuer_identity": norm_expected,
        "extracted_identity_evidence": identity_evidence,
        "evidence_types": evidence_types,
        "observed_identity": observed_identity,
        "normalized_extracted_issuer_identity": normalize_legal_identity(observed_identity),
        "identity_match_verdict": (
            "MATCH"
            if identity_match
            else "CONFLICT"
            if status == IDENTITY_CONFLICT
            else "INSUFFICIENT"
        ),
        "domain_binding_verdict": "BOUND" if domain_bound else "INVALID",
        "prospective_owner_review_status": status,
        "reason_codes": reason_codes,
        "deterministic_content_identity": f"prospective_route_ownership_record:{content_identity}",
    }


def execute_bounded_enrichment(
    *,
    live_network: bool = False,
    evidence_dir: Path = ENRICHMENT_EVIDENCE_DIR,
    timestamp: str = "2026-08-21T18:45:00Z",
) -> dict[str, Any]:
    """Execute the bounded route evidence enrichment with hard request budgets."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    per_ticker_acquisitions: list[dict[str, Any]] = []
    final_records: list[dict[str, Any]] = []
    request_counts: dict[str, int] = {t: 0 for t in TARGET_TICKERS}

    for ticker in TARGET_TICKERS:
        budget = REQUEST_BUDGET[ticker]
        url_plan = FIXED_ROUTE_PLANS[ticker]
        ticker_acquisitions: list[dict[str, Any]] = []
        best_review_record: dict[str, Any] | None = None

        for url in url_plan:
            if request_counts[ticker] >= budget:
                break

            if live_network:
                acq = synchronous_fetch_and_retain(
                    ticker,
                    url,
                    evidence_dir=evidence_dir,
                    timestamp=timestamp,
                )
                request_counts[ticker] += 1
            else:
                # Replay from offline catalog
                catalog_matches = [
                    item for item in OFFLINE_ENRICHED_EVIDENCE_CATALOG.get(ticker, [])
                    if item["requested_url"] == url
                ]
                if not catalog_matches:
                    break
                cat = catalog_matches[0]
                file_path = ROOT / cat["relative_path"]
                if not file_path.is_file():
                    break
                raw_bytes = file_path.read_bytes()
                actual_sha = hashlib.sha256(raw_bytes).hexdigest()
                request_counts[ticker] += 1
                acq = {
                    "ticker": ticker,
                    "requested_url": cat["requested_url"],
                    "final_url": cat["final_url"],
                    "http_status": cat["http_status"],
                    "content_type": cat["mime_type"],
                    "content_bytes_length": len(raw_bytes),
                    "raw_sha256": actual_sha,
                    "retained_file_path": cat["relative_path"],
                    "retrieval_timestamp": timestamp,
                    "redirect_chain": cat.get("redirect_chain", []),
                    "technical_error": None,
                    "success": actual_sha == cat["sha256"],
                }

            ticker_acquisitions.append(acq)

            if not acq["success"] or not acq["retained_file_path"]:
                continue

            file_path = ROOT / acq["retained_file_path"]
            raw_bytes = file_path.read_bytes()
            review = review_retained_bytes(
                ticker=ticker,
                requested_url=acq["requested_url"],
                final_url=acq["final_url"],
                raw_bytes=raw_bytes,
                raw_sha=acq["raw_sha256"],
                retained_file_path=acq["retained_file_path"],
                redirect_chain=acq.get("redirect_chain", []),
                timestamp=timestamp,
            )
            best_review_record = review

            # Stop immediately if sufficient evidence acquired
            if review["prospective_owner_review_status"] == OWNER_REVIEW_READY:
                break

        per_ticker_acquisitions.extend(ticker_acquisitions)
        if best_review_record:
            final_records.append(best_review_record)

    # Candidate generation for new OWNER_REVIEW_READY routes only
    candidates: list[dict[str, Any]] = []
    for rec in final_records:
        if rec["prospective_owner_review_status"] != OWNER_REVIEW_READY:
            continue
        candidates.append({
            "ticker": rec["ticker"],
            "source_id": "issuer_ir",
            "candidate_host": rec["candidate_host"],
            "candidate_url": rec["candidate_locator"],
            "legal_issuer_identity": rec["expected_issuer_identity"],
            "ownership_evidence_types": rec["evidence_types"],
            "ownership_evidence_sha256": rec["retained_sha256"],
            "retained_evidence_path": rec["retained_file_path"],
            "prospective_review_identity": rec["deterministic_content_identity"],
            "activation_recommendation": "PENDING_OWNER_PROMOTION_REVIEW",
        })

    # Summary counts
    statuses = Counter(rec["prospective_owner_review_status"] for rec in final_records)
    total_network_requests = sum(request_counts.values())

    artifact: dict[str, Any] = {
        "schema_version": VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "milestone": "BOUNDED_OFFICIAL_ROUTE_EVIDENCE_ENRICHMENT_V1",
        "redirect_domain_authority_contract_version": REDIRECT_AUTHORITY_CONTRACT_VERSION,
        "authority": {
            "prospective_review_is_non_activating": True,
            "activated_route_qualification_still_requires_approved_host": True,
            "registry_mutated": False,
            "owner_promotion_performed": False,
        },
        "identity_normalization_version": "v1_unicode_case_whitespace_punctuation_controlled_legal_form_expansion",
        "hard_request_budget": {
            "per_ticker_budget": REQUEST_BUDGET,
            "actual_network_requests": request_counts,
            "first_party_ceiling": 7,
            "total_first_party_requests": total_network_requests,
            "official_cross_registry_fallback_requests": 0,
            "total_requests": total_network_requests,
            "budget_respected": bool(
                all(request_counts[t] <= REQUEST_BUDGET[t] for t in TARGET_TICKERS)
                and total_network_requests <= 7
            ),
        },
        "target_cohort": list(TARGET_TICKERS),
        "baseline_statuses": BASELINE_STATUSES,
        "acquisition_attempts": per_ticker_acquisitions,
        "records": final_records,
        "historical_evidence_preservation": {
            "AAT_tienson_vn": {
                "locator": "https://tienson.vn",
                "status": "REJECTED_IDENTITY_CONFLICT",
                "preserved_unmodified": True,
                "retained_path": "operations-review/retained-official-route-ownership-evidence-20260821/evidence/AAT_issuer_ir_0b4379eac689.html",
            },
        },
        "summary_counts": {
            "target_issuers_evaluated": len(TARGET_TICKERS),
            "owner_review_ready": statuses[OWNER_REVIEW_READY],
            "insufficient_identity_evidence": statuses[INSUFFICIENT_IDENTITY_EVIDENCE],
            "identity_conflict": statuses[IDENTITY_CONFLICT],
            "technical_evidence_invalid": statuses[TECHNICAL_EVIDENCE_INVALID],
            "route_authority_evidence_required": statuses[ROUTE_AUTHORITY_EVIDENCE_REQUIRED],
            "new_registry_candidates_proposed": len(candidates),
        },
        "governed_registry_candidates_proposed": candidates,
        "next_gate": "GOVERNED_OFFICIAL_SOURCE_REGISTRY_ACTIVATION_REVIEW",
        "authority_boundaries": {
            "network_requests": total_network_requests,
            "registry_mutated": False,
            "activation_promoted": False,
            "financial_documents_acquired": 0,
            "financial_facts_created": 0,
            "fundamental_readiness_mutated": False,
        },
        "verdict": "BOUNDED_OFFICIAL_ROUTE_EVIDENCE_ENRICHMENT_COMPLETE",
    }
    artifact["artifact_sha256"] = _hash(artifact)
    artifact["artifact_identity"] = (
        f"bounded_official_route_evidence_enrichment:{artifact['artifact_sha256']}"
    )
    return artifact


def execute() -> dict[str, Any]:
    return execute_bounded_enrichment(live_network=False)
