"""Byte-derived, non-activating owner review for prospective issuer routes.

This contract intentionally precedes registry admission.  It can determine
whether a retained first-party page is suitable for an owner's review, but it
cannot approve a host or qualify an activated financial-document route.
"""
from __future__ import annotations

from collections import Counter
from html import unescape
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping
import unicodedata
from urllib.parse import urlsplit

from official_financial_source_route_discovery import LEGAL_IDENTITY_HINTS, STATIC_ISSUER_ROUTE_HINTS, normalize_domain
from retained_official_route_ownership_evidence import EVIDENCE_STORE_DIR, OFFLINE_RETAINED_EVIDENCE_CATALOG


ROOT = Path(__file__).resolve().parent
VERSION = "1.0.0"
CONTRACT_VERSION = "prospective_route_ownership_review/v1"
ARTIFACT_TYPE = "PROSPECTIVE_ROUTE_OWNERSHIP_REVIEW"
ACQUISITION_ARTIFACT = (
    ROOT / "operations-review" / "retained-official-route-ownership-evidence-20260821"
    / "retained_official_route_ownership_evidence_artifact.json"
)

OWNER_REVIEW_READY = "OWNER_REVIEW_READY"
INSUFFICIENT_IDENTITY_EVIDENCE = "INSUFFICIENT_IDENTITY_EVIDENCE"
IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
TECHNICAL_EVIDENCE_INVALID = "TECHNICAL_EVIDENCE_INVALID"

FULL_LEGAL_ENTITY_NAME = "FULL_LEGAL_ENTITY_NAME_IN_FIRST_PARTY_PAGE"
STRUCTURED_LEGAL_NAME = "STRUCTURED_LEGAL_NAME"
COPYRIGHT_LEGAL_ENTITY = "COPYRIGHT_LEGAL_ENTITY"
STATUTORY_REGISTRATION_IDENTIFIER = "STATUTORY_REGISTRATION_IDENTIFIER"
BRANDING_ONLY = "BRANDING_ONLY"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def normalize_legal_identity(value: str | None) -> str:
    """Versioned, conservative normalization for Vietnamese legal entity names."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char)).casefold()
    text = re.sub(r"\bcong\s+ty\s+cp\b", "cong ty co phan", text)
    text = re.sub(r"\bctcp\b", "cong ty co phan", text)
    text = re.sub(r"\bngan\s+hang\s+tmcp\b", "ngan hang thuong mai co phan", text)
    text = re.sub(r"\btmcp\b", "thuong mai co phan", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _identity_variants(expected_identity: str) -> tuple[str, ...]:
    variants = {
        expected_identity,
        re.sub(r"\bCTCP\b", "Công ty cổ phần", expected_identity, flags=re.I),
        re.sub(r"\bCTCP\b", "Công ty CP", expected_identity, flags=re.I),
        re.sub(r"\bTMCP\b", "Thương mại cổ phần", expected_identity, flags=re.I),
    }
    variants.add(re.sub(r"Ngân hàng\s+TMCP", "Ngân hàng Thương mại cổ phần", expected_identity, flags=re.I))
    return tuple(sorted(variants, key=len, reverse=True))


class _FirstPartyTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._tag_stack: list[str] = []
        self.title_fragments: list[str] = []
        self.text_fragments: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._tag_stack.append(tag.lower())

    def handle_endtag(self, tag: str) -> None:
        if self._tag_stack and self._tag_stack[-1] == tag.lower():
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        compact = re.sub(r"\s+", " ", data).strip()
        if not compact or any(tag in {"script", "style"} for tag in self._tag_stack):
            return
        if "title" in self._tag_stack:
            self.title_fragments.append(compact)
        self.text_fragments.append(compact)


def _structured_legal_names(text: str) -> list[str]:
    pattern = re.compile(
        r"(?:\\?[\"'])legalName(?:\\?[\"'])\s*:\s*\\?[\"'](?P<value>(?:\\.|[^\"\\])*)",
        re.I,
    )
    return [unescape(match.group("value")).replace(r"\"", '"').strip() for match in pattern.finditer(text)]


def _first_matching_span(text: str, expected_identity: str) -> str | None:
    for variant in _identity_variants(expected_identity):
        match = re.search(re.escape(variant), text, re.I)
        if match:
            return match.group(0)
    return None


def _identity_evidence(raw_text: str, expected_identity: str) -> tuple[list[dict[str, str]], str | None]:
    parser = _FirstPartyTextParser()
    parser.feed(raw_text)
    evidence: list[dict[str, str]] = []

    for name in _structured_legal_names(raw_text):
        if normalize_legal_identity(name) == normalize_legal_identity(expected_identity):
            evidence.append({"evidence_type": STRUCTURED_LEGAL_NAME, "span": name, "source": "structured_legalName"})

    for title in parser.title_fragments:
        span = _first_matching_span(title, expected_identity)
        if span:
            evidence.append({"evidence_type": FULL_LEGAL_ENTITY_NAME, "span": span, "source": "html_title"})

    for fragment in parser.text_fragments:
        span = _first_matching_span(fragment, expected_identity)
        if not span:
            continue
        prefix = fragment[: max(0, fragment.casefold().find(span.casefold()))].casefold()
        evidence_type = COPYRIGHT_LEGAL_ENTITY if "copyright" in prefix or "bản quyền" in prefix else FULL_LEGAL_ENTITY_NAME
        evidence.append({"evidence_type": evidence_type, "span": span, "source": "html_text"})

    unique = {(item["evidence_type"], item["span"], item["source"]): item for item in evidence}
    result = [unique[key] for key in sorted(unique)]
    observed = result[0]["span"] if result else None
    return result, observed


def _conflicting_identity(raw_text: str) -> str | None:
    parser = _FirstPartyTextParser()
    parser.feed(raw_text)
    for title in parser.title_fragments:
        if re.search(r"\b(Công ty|Ngân hàng)\b", title, re.I):
            return title
    for name in _structured_legal_names(raw_text):
        if re.search(r"\b(Công ty|Ngân hàng)\b", name, re.I):
            return name
    return None


def _branding_evidence(raw_text: str, expected_host: str) -> list[dict[str, str]]:
    parser = _FirstPartyTextParser()
    parser.feed(raw_text)
    evidence = []
    for title in parser.title_fragments:
        if title:
            evidence.append({"evidence_type": BRANDING_ONLY, "span": title, "source": "html_title"})
            break
    if not evidence and expected_host in raw_text.lower():
        evidence.append({"evidence_type": BRANDING_ONLY, "span": expected_host, "source": "retained_html_locator"})
    return evidence


def _prior_artifact_records() -> dict[str, Mapping[str, Any]]:
    artifact = json.loads(ACQUISITION_ARTIFACT.read_text(encoding="utf-8"))
    return {
        str(record["canonical_instrument"]): record
        for record in artifact["retained_evidence_summary"]["retained_evidence_objects"]
    }


def review_retained_object(
    ticker: str,
    *,
    candidate_locator: str | None = None,
    evidence_dir: Path = EVIDENCE_STORE_DIR,
    prior_records: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Review one retained object without consulting the approved-host registry."""
    catalog = OFFLINE_RETAINED_EVIDENCE_CATALOG[ticker]
    prior = (prior_records or _prior_artifact_records())[ticker]
    expected_identity = str(LEGAL_IDENTITY_HINTS[ticker]["legal_name"])
    expected_locator = str(candidate_locator or STATIC_ISSUER_ROUTE_HINTS[ticker])
    expected_host = normalize_domain(expected_locator)
    retained_path = evidence_dir / f"{ticker}_issuer_ir_{catalog['sha256'][:12]}.html"
    reason_codes: list[str] = []

    if not retained_path.is_file():
        return {
            "ticker": ticker,
            "candidate_host": expected_host,
            "retained_file_path": str(retained_path.relative_to(ROOT)),
            "prospective_owner_review_status": TECHNICAL_EVIDENCE_INVALID,
            "reason_codes": ["RETAINED_OBJECT_MISSING"],
        }

    raw_bytes = retained_path.read_bytes()
    raw_sha = hashlib.sha256(raw_bytes).hexdigest()
    locator_host = normalize_domain(str(prior.get("candidate_locator") or ""))
    provenance_host = normalize_domain(str(prior.get("evidence_provenance", {}).get("url") or ""))
    bytes_valid = raw_sha == str(catalog["sha256"]) == str(prior.get("raw_document_sha256"))
    domain_valid = bool(expected_host and locator_host == expected_host and provenance_host == expected_host)
    if not bytes_valid:
        reason_codes.append("RETAINED_SHA256_MISMATCH")
    if not domain_valid:
        reason_codes.append("LOCATOR_OR_PROVENANCE_DOMAIN_MISMATCH")

    raw_text = raw_bytes.decode("utf-8", errors="replace")
    identity_evidence, observed_identity = _identity_evidence(raw_text, expected_identity)
    statutory_identifiers = []
    prior_claim = str(prior.get("extracted_identity_fields", {}).get("statutory_registration_span") or "")
    prior_identifiers = re.findall(r"\b\d{4,}(?:/[A-Za-zÀ-ỹĐđ-]+)?\b|\b\d{2,}/[A-Za-zÀ-ỹĐđ-]+", prior_claim)
    for identifier in prior_identifiers:
        if identifier in raw_text:
            statutory_identifiers.append(identifier)
            identity_evidence.append({
                "evidence_type": STATUTORY_REGISTRATION_IDENTIFIER,
                "span": identifier,
                "source": "retained_html",
            })
    if not statutory_identifiers:
        reason_codes.append("NO_RETAINED_STATUTORY_IDENTIFIER")

    identity_match = bool(observed_identity and normalize_legal_identity(observed_identity) == normalize_legal_identity(expected_identity))
    conflict = _conflicting_identity(raw_text)
    if not bytes_valid or not domain_valid:
        status = TECHNICAL_EVIDENCE_INVALID
    elif identity_match:
        status = OWNER_REVIEW_READY
        reason_codes.append("BYTE_DERIVED_LEGAL_IDENTITY_MATCH")
    elif conflict:
        status = IDENTITY_CONFLICT
        reason_codes.append("RETAINED_LEGAL_IDENTITY_CONFLICTS_WITH_EXPECTED_ISSUER")
        observed_identity = conflict
        identity_evidence = _branding_evidence(raw_text, expected_host)
    else:
        status = INSUFFICIENT_IDENTITY_EVIDENCE
        reason_codes.append("NO_BYTE_DERIVED_FULL_LEGAL_IDENTITY_MATCH")
        identity_evidence = _branding_evidence(raw_text, expected_host)

    evidence_types = sorted({item["evidence_type"] for item in identity_evidence})
    content_identity = _hash({
        "ticker": ticker,
        "candidate_host": expected_host,
        "retained_sha256": raw_sha,
        "identity_evidence": identity_evidence,
        "status": status,
    })
    return {
        "ticker": ticker,
        "candidate_host": expected_host,
        "candidate_locator": expected_locator,
        "retained_file_path": str(retained_path.relative_to(ROOT)),
        "retained_sha256": raw_sha,
        "retained_locator": prior.get("candidate_locator"),
        "retained_provenance": prior.get("evidence_provenance"),
        "retained_bytes_valid": bytes_valid,
        "expected_issuer_identity": expected_identity,
        "normalized_expected_issuer_identity": normalize_legal_identity(expected_identity),
        "extracted_identity_evidence": identity_evidence,
        "evidence_types": evidence_types,
        "normalized_extracted_issuer_identity": normalize_legal_identity(observed_identity),
        "identity_match_verdict": "MATCH" if identity_match else "CONFLICT" if status == IDENTITY_CONFLICT else "INSUFFICIENT",
        "domain_binding_verdict": "BOUND" if domain_valid else "INVALID",
        "statutory_identifiers_present": statutory_identifiers,
        "prospective_owner_review_status": status,
        "reason_codes": reason_codes,
        "deterministic_content_identity": f"prospective_route_ownership_record:{content_identity}",
    }


def generate_registry_candidates(records: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Create non-activating candidates only from independently ready records."""
    candidates = []
    for record in records:
        if record.get("prospective_owner_review_status") != OWNER_REVIEW_READY:
            continue
        candidates.append({
            "ticker": record["ticker"],
            "source_id": "issuer_ir",
            "candidate_host": record["candidate_host"],
            "candidate_url": record["candidate_locator"],
            "legal_issuer_identity": record["expected_issuer_identity"],
            "ownership_evidence_types": record["evidence_types"],
            "ownership_evidence_sha256": record["retained_sha256"],
            "retained_evidence_path": record["retained_file_path"],
            "prospective_review_identity": record["deterministic_content_identity"],
            "activation_recommendation": "PENDING_OWNER_PROMOTION_REVIEW",
        })
    return candidates


def build_prospective_owner_review_artifact() -> dict[str, Any]:
    prior_artifact = json.loads(ACQUISITION_ARTIFACT.read_text(encoding="utf-8"))
    prior_records = _prior_artifact_records()
    records = [review_retained_object(ticker, prior_records=prior_records) for ticker in sorted(prior_records)]
    statuses = Counter(record["prospective_owner_review_status"] for record in records)
    candidates = generate_registry_candidates(records)
    statutory_claims = [
        {
            "ticker": record["ticker"],
            "historical_claim_status": "SUPERSEDED_NOT_PRESENT_IN_RETAINED_BYTES",
            "statutory_identifiers_present": record["statutory_identifiers_present"],
        }
        for record in records
    ]
    artifact: dict[str, Any] = {
        "schema_version": VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "authority": {
            "prospective_review_is_non_activating": True,
            "activated_route_qualification_still_requires_approved_host": True,
            "registry_mutated": False,
            "owner_promotion_performed": False,
        },
        "identity_normalization_version": "v1_unicode_case_whitespace_punctuation_controlled_legal_form_expansion",
        "historical_acquisition_artifact": {
            "artifact_identity": prior_artifact["artifact_identity"],
            "preserved": True,
            "injected_statutory_span_claims": statutory_claims,
        },
        "records": records,
        "summary_counts": {
            "retained_objects_reviewed": len(records),
            "owner_review_ready": statuses[OWNER_REVIEW_READY],
            "insufficient_identity_evidence": statuses[INSUFFICIENT_IDENTITY_EVIDENCE],
            "identity_conflict": statuses[IDENTITY_CONFLICT],
            "technical_evidence_invalid": statuses[TECHNICAL_EVIDENCE_INVALID],
        },
        "governed_registry_candidates_proposed": candidates,
        "next_gate": "EXPLICIT_OWNER_REGISTRY_PROMOTION_REVIEW",
        "authority_boundaries": {
            "network_requests": 0,
            "registry_mutated": False,
            "activation_promoted": False,
            "financial_documents_acquired": 0,
            "financial_facts_created": 0,
            "fundamental_readiness_mutated": False,
        },
        "verdict": "PROSPECTIVE_ROUTE_OWNERSHIP_REVIEW_COMPLETE",
    }
    artifact["artifact_sha256"] = _hash(artifact)
    artifact["artifact_identity"] = f"prospective_route_ownership_review:{artifact['artifact_sha256']}"
    return artifact


def execute() -> dict[str, Any]:
    return build_prospective_owner_review_artifact()
