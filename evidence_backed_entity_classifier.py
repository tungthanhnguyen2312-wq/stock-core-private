"""Phase 2 / P2-E: Evidence-Backed Entity Classifier Engine.

Pure, deterministic, evidence-backed classifier resolving entity classes across:
- Corporate (ordinary commercial, manufacturing, service enterprises)
- Bank (commercial banks licensed under Law on Credit Institutions)
- Securities (licensed brokers/dealers under Law on Securities)
- Insurance (licensed insurers under Law on Insurance Business)
- Finance Company (specialized credit institutions under Law on Credit Institutions)
- Unknown (insufficient evidence / fail-closed)

Evidence hierarchy & multi-source fusion:
1. Documented Regulatory & Accounting Statement Filings (Form codes & exclusive line markers)
2. Official Security Master & Legal Charter Descriptors
3. Curated Seed Authority Baseline (config/ticker_entity_profiles.csv)
4. Strict Conflict & Ambiguity Detection (ClassificationStatus.CONFLICT / AMBIGUOUS)
5. Pure fail-closed: in the absence of positive evidence, emits UNKNOWN. Zero ticker branches.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Mapping, Sequence
import unicodedata

from entity_classification_contract import (
    CONTRACT_VERSION,
    ConfidenceSemantics,
    EntityClass,
    EntityClassificationRecord,
    EvidenceTier,
    ClassificationStatus,
    compute_classification_evidence_id,
)
from financial_entity_applicability import (
    CREDIT_INSTITUTION_INCOME_MARKERS,
    INSURANCE_INCOME_MARKERS,
    SECURITIES_INCOME_MARKERS,
    classify_income_statement,
    load_entity_profiles,
)
from statement_taxonomy_classifier import (
    CORPORATE_MARKERS,
    CREDIT_INSTITUTION_EXCLUSIVE_MARKERS,
    SECURITIES_MARKERS,
    classify_statement_taxonomy,
)

TICKER_SPECIFIC_EXTRACTION_BRANCH_COUNT = 0


def _normalize_text(s: str) -> str:
    """Normalize unicode and strip combining marks for tolerant anchor lookup."""
    if not s:
        return ""
    norm = unicodedata.normalize("NFD", str(s).strip().lower())
    no_diacritics = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    cleaned = no_diacritics.replace("đ", "d").replace("’", "'").replace("`", "'")
    return " ".join(cleaned.split())


# Legal Charter Descriptor Patterns
CHARTER_PATTERNS: dict[EntityClass, tuple[str, ...]] = {
    EntityClass.SECURITIES: (
        "cong ty co phan chung khoan",
        "ctcp chung khoan",
        "cong ty chung khoan",
        "securities joint stock company",
        "securities corporation",
        "securities inc",
        "securities jsc",
        "chung khoan",
    ),
    EntityClass.INSURANCE: (
        "tong cong ty bao hiem",
        "tap doan bao hiem",
        "cong ty co phan bao hiem",
        "ctcp bao hiem",
        "tong cong ty co phan bao hiem",
        "bao hiem",
        "tai bao hiem",
        "bao viet",
        "bao minh",
        "insurance corporation",
        "insurance joint stock company",
        "life insurance",
        "non-life insurance",
        "reinsurance",
    ),
    EntityClass.FINANCE_COMPANY: (
        "cong ty tai chinh",
        "ctcp tai chinh",
        "cong ty co phan tai chinh",
        "finance company",
        "financial services jsc",
    ),
    EntityClass.BANK: (
        "ngan hang thuong mai co phan",
        "ngan hang tmcp",
        "ngan hang thuong mai",
        "commercial bank",
        "commercial joint stock bank",
    ),
}

# Accounting Statement Form Codes
FORM_CODE_PATTERNS: dict[EntityClass, tuple[str, ...]] = {
    EntityClass.CORPORATE: (
        "b 01-dn", "b 01 - dn", "b 01-dn/hn", "b 01 - dn/hn", "b 01—dn",
        "b 02-dn", "b 02 - dn", "b 02-dn/hn", "b 02 - dn/hn", "b 02—dn",
        "b 03-dn", "b 03 - dn", "b 03-dn/hn", "b 03 - dn/hn", "b 03—dn",
        "mau so b 01-dn", "mau so b 02-dn", "mau so b 03-dn",
        "thong tu 200/2014/tt-btc", "thong tu 202/2014/tt-btc",
        "tt 200/2014/tt-btc", "tt 202/2014/tt-btc",
    ),
    EntityClass.BANK: (
        "b 01-nh", "b 01 - nh", "b 01-nh/hn", "b 01 - nh/hn",
        "b 02-nh", "b 02 - nh", "b 02-nh/hn", "b 02 - nh/hn",
        "b 03-nh", "b 03 - nh", "b 03-nh/hn", "b 03 - nh/hn",
        "mau so b 01-nh", "mau so b 02-nh", "mau so b 03-nh",
        "thong tu 49/2014/tt-nhnn", "quyet dinh 16/2007/qd-nhnn",
    ),
    EntityClass.SECURITIES: (
        "b 01-ck", "b 01 - ck", "b 01-ck/hn", "b 01 - ck/hn",
        "b 02-ck", "b 02 - ck", "b 02-ck/hn", "b 02 - ck/hn",
        "b 03-ck", "b 03 - ck", "b 03-ck/hn", "b 03 - ck/hn",
        "mau so b 01-ck", "mau so b 02-ck", "mau so b 03-ck",
        "thong tu 210/2014/tt-btc", "thong tu 334/2016/tt-btc",
    ),
    EntityClass.INSURANCE: (
        "b 01-bh", "b 01 - bh", "b 01-bh/hn", "b 01 - bh/hn",
        "b 01-dnbh", "b 01 - dnbh", "b 01-dnbh/hn", "b 01 - dnbh/hn",
        "b 02-bh", "b 02 - bh", "b 02-bh/hn", "b 02 - bh/hn",
        "b 03-bh", "b 03 - bh", "b 03-bh/hn", "b 03 - bh/hn",
        "thong tu 232/2012/tt-btc", "thong tu 125/2018/tt-btc",
    ),
}


GENERAL_CORPORATE_PATTERNS = (
    "cong ty co phan",
    "ctcp",
    "tong cong ty",
    "tap doan",
    "cong ty tnhh",
)


def evaluate_legal_charter_evidence(legal_name: str | None) -> tuple[EntityClass | None, str, list[str]]:
    """Evaluate legal name / registered issuer identity charter descriptors.
    
    Returns (matched_class, reason, matched_keywords).
    """
    if not legal_name:
        return None, "no_legal_name_provided", []

    norm_name = _normalize_text(legal_name)
    hits: dict[EntityClass, list[str]] = {}

    for e_class, patterns in CHARTER_PATTERNS.items():
        matched = [p for p in patterns if p in norm_name]
        if matched:
            hits[e_class] = matched

    if hits:
        if len(hits) > 1:
            # Disambiguate specialized vs parent (e.g. securities/insurance subsidiary of bank)
            if EntityClass.SECURITIES in hits and EntityClass.BANK in hits:
                return EntityClass.SECURITIES, "charter_matches_securities_descriptor", hits[EntityClass.SECURITIES]
            if EntityClass.INSURANCE in hits and EntityClass.BANK in hits:
                return EntityClass.INSURANCE, "charter_matches_insurance_descriptor", hits[EntityClass.INSURANCE]
            if EntityClass.FINANCE_COMPANY in hits and EntityClass.BANK in hits:
                return EntityClass.FINANCE_COMPANY, "charter_matches_finance_company_descriptor", hits[EntityClass.FINANCE_COMPANY]
            return None, f"conflicting_charter_descriptors:{[k.value for k in hits.keys()]}", [k for l in hits.values() for k in l]

        matched_class = list(hits.keys())[0]
        return matched_class, f"charter_matches_{matched_class.value}_descriptor", hits[matched_class]

    # Check for general commercial enterprise prefixes (Corporate)
    matched_corp = [p for p in GENERAL_CORPORATE_PATTERNS if p in norm_name]
    if matched_corp:
        return EntityClass.CORPORATE, "general_commercial_enterprise_charter_without_specialized_financial_license", matched_corp

    return None, "no_recognized_enterprise_charter_descriptors", []


def evaluate_statement_form_evidence(statement_texts: Sequence[str]) -> tuple[EntityClass | None, str, list[str]]:
    """Evaluate official financial statement form codes and Circular headers across statement text.
    
    Returns (matched_class, reason, matched_form_codes).
    """
    if not statement_texts:
        return None, "no_statement_texts_provided", []

    combined_norm = " ".join(_normalize_text(t) for t in statement_texts)
    hits: dict[EntityClass, list[str]] = {}

    for e_class, patterns in FORM_CODE_PATTERNS.items():
        matched = [p for p in patterns if p in combined_norm]
        if matched:
            hits[e_class] = matched

    if not hits:
        return None, "no_standard_form_codes_matched", []

    if len(hits) > 1:
        return None, f"conflicting_form_codes:{list(hits.keys())}", [k for l in hits.values() for k in l]

    matched_class = list(hits.keys())[0]
    return matched_class, f"statement_form_code_matches_{matched_class.value}", hits[matched_class]


def evaluate_line_item_marker_evidence(
    balance_sheet_item_ids: Sequence[str] | None = None,
    income_statement_item_ids: Sequence[str] | None = None,
) -> tuple[EntityClass | None, str, dict[str, Any]]:
    """Evaluate exclusive line-item financial markers across balance sheet and income statement.
    
    Returns (matched_class, reason, supporting_details).
    """
    bs_items = balance_sheet_item_ids or []
    is_items = income_statement_item_ids or []

    bs_tax = classify_statement_taxonomy(bs_items) if bs_items else None
    is_tax = classify_income_statement(is_items) if is_items else None

    # Map statement taxonomies to entity class candidates
    candidates: set[EntityClass] = set()
    details: dict[str, Any] = {"bs_taxonomy": bs_tax, "is_taxonomy": is_tax}

    if bs_tax:
        bs_name = bs_tax.get("taxonomy")
        if bs_name == "corporate_vas":
            candidates.add(EntityClass.CORPORATE)
        elif bs_name == "credit_institution":
            candidates.add(EntityClass.BANK)
        elif bs_name == "securities_company":
            candidates.add(EntityClass.SECURITIES)

    if is_tax:
        is_family = is_tax.get("template_family")
        if is_family == "credit_institution":
            candidates.add(EntityClass.BANK)
        elif is_family == "securities_company":
            candidates.add(EntityClass.SECURITIES)
        elif is_family == "insurance":
            candidates.add(EntityClass.INSURANCE)

    if not candidates:
        return None, "no_exclusive_line_item_markers_matched", details

    if len(candidates) > 1:
        return None, f"conflicting_line_item_evidence:{[c.value for c in candidates]}", details

    matched_class = list(candidates)[0]
    return matched_class, f"line_item_markers_positively_evidence_{matched_class.value}", details


def classify_entity(
    *,
    issuer_identity: str,
    ticker: str,
    legal_name: str | None = None,
    statement_texts: Sequence[str] | None = None,
    balance_sheet_item_ids: Sequence[str] | None = None,
    income_statement_item_ids: Sequence[str] | None = None,
    curated_seed_profile: str | None = None,
    source_id: str = "canonical_instrument_reconciliation",
    source_record_id: str | None = None,
    effective_from: str | None = None,
    knowledge_available_at: str | None = None,
    verified_at: str | None = None,
) -> EntityClassificationRecord:
    """Classify an issuer entity under multi-evidence positive authority.
    
    Zero ticker branching: uses strictly legal charter descriptors, form codes,
    line-item marker sets, and curated seed profiles with deterministic conflict handling.
    """
    v_time = verified_at or datetime.now(timezone.utc).isoformat()
    clean_ticker = str(ticker).upper().strip()
    clean_identity = str(issuer_identity or f"issuer:{clean_ticker}").strip()

    # Step 1: Evaluate Legal Charter Descriptors
    charter_class, charter_reason, charter_markers = evaluate_legal_charter_evidence(legal_name)

    # Step 2: Evaluate Statement Form Codes
    form_class, form_reason, form_codes = evaluate_statement_form_evidence(statement_texts or [])

    # Step 3: Evaluate Line Item Markers
    marker_class, marker_reason, marker_details = evaluate_line_item_marker_evidence(
        balance_sheet_item_ids=balance_sheet_item_ids,
        income_statement_item_ids=income_statement_item_ids,
    )

    # Step 4: Evaluate Curated Seed Authority
    seed_class: EntityClass | None = None
    if curated_seed_profile:
        s_norm = curated_seed_profile.strip().lower()
        if s_norm in {e.value for e in EntityClass if e != EntityClass.UNKNOWN}:
            seed_class = EntityClass(s_norm)

    # Step 5: Multi-Evidence Fusion & Conflict Resolution
    evidence_classes = [
        (c, EvidenceTier.EXCHANGE_SECURITY_MASTER, charter_reason)
        for c in [charter_class] if c is not None
    ] + [
        (c, EvidenceTier.DOCUMENTED_VERIFIED, form_reason)
        for c in [form_class] if c is not None
    ] + [
        (c, EvidenceTier.FINANCIAL_STATEMENT_TEMPLATE, marker_reason)
        for c in [marker_class] if c is not None
    ]

    distinct_classes = {item[0] for item in evidence_classes}

    # Case A: Conflict across primary evidence
    if len(distinct_classes) > 1:
        competing_details = {
            "charter_evidence": {"class": charter_class.value if charter_class else None, "reason": charter_reason, "markers": charter_markers},
            "form_evidence": {"class": form_class.value if form_class else None, "reason": form_reason, "codes": form_codes},
            "marker_evidence": {"class": marker_class.value if marker_class else None, "reason": marker_reason, "details": marker_details},
            "seed_evidence": seed_class.value if seed_class else None,
        }
        ev_id = compute_classification_evidence_id(
            issuer_identity=clean_identity,
            ticker=clean_ticker,
            entity_class=EntityClass.UNKNOWN.value,
            classification_status=ClassificationStatus.CONFLICT.value,
            source_id=source_id,
            evidence_payload=competing_details,
        )
        return EntityClassificationRecord(
            issuer_identity=clean_identity,
            ticker=clean_ticker,
            legal_name=legal_name,
            entity_class=EntityClass.UNKNOWN,
            classification_status=ClassificationStatus.CONFLICT,
            confidence_semantics=ConfidenceSemantics.CONTRADICTORY_EVIDENCE,
            evidence_tier=EvidenceTier.DOCUMENTED_VERIFIED,
            classification_evidence_id=ev_id,
            source_id=source_id,
            source_record_id=source_record_id,
            effective_from=effective_from,
            knowledge_available_at=knowledge_available_at,
            verified_at=v_time,
            classification_reason=f"CONFLICT: Contradictory evidence across sources ({[c.value for c in distinct_classes]})",
            supporting_evidence=competing_details,
        )

    # Case B: Primary evidence established a single positive class
    if len(distinct_classes) == 1:
        positive_class = list(distinct_classes)[0]
        primary_tier = evidence_classes[0][1]
        reasons = [item[2] for item in evidence_classes]
        
        # Check conflict with seed authority if present
        if seed_class is not None and seed_class != positive_class:
            competing_details = {
                "primary_evidence_class": positive_class.value,
                "seed_authority_class": seed_class.value,
                "reasons": reasons,
            }
            ev_id = compute_classification_evidence_id(
                issuer_identity=clean_identity,
                ticker=clean_ticker,
                entity_class=EntityClass.UNKNOWN.value,
                classification_status=ClassificationStatus.CONFLICT.value,
                source_id=source_id,
                evidence_payload=competing_details,
            )
            return EntityClassificationRecord(
                issuer_identity=clean_identity,
                ticker=clean_ticker,
                legal_name=legal_name,
                entity_class=EntityClass.UNKNOWN,
                classification_status=ClassificationStatus.CONFLICT,
                confidence_semantics=ConfidenceSemantics.CONTRADICTORY_EVIDENCE,
                evidence_tier=primary_tier,
                classification_evidence_id=ev_id,
                source_id=source_id,
                source_record_id=source_record_id,
                effective_from=effective_from,
                knowledge_available_at=knowledge_available_at,
                verified_at=v_time,
                classification_reason=f"CONFLICT: Primary evidence ({positive_class.value}) conflicts with seed authority ({seed_class.value})",
                supporting_evidence=competing_details,
            )

        supporting = {
            "charter_markers": charter_markers,
            "form_codes": form_codes,
            "marker_details": marker_details,
            "seed_profile": seed_class.value if seed_class else None,
        }
        ev_id = compute_classification_evidence_id(
            issuer_identity=clean_identity,
            ticker=clean_ticker,
            entity_class=positive_class.value,
            classification_status=ClassificationStatus.QUALIFIED.value,
            source_id=source_id,
            evidence_payload=supporting,
        )
        return EntityClassificationRecord(
            issuer_identity=clean_identity,
            ticker=clean_ticker,
            legal_name=legal_name,
            entity_class=positive_class,
            classification_status=ClassificationStatus.QUALIFIED,
            confidence_semantics=ConfidenceSemantics.DETERMINISTIC_PROOF,
            evidence_tier=primary_tier,
            classification_evidence_id=ev_id,
            source_id=source_id,
            source_record_id=source_record_id,
            effective_from=effective_from,
            knowledge_available_at=knowledge_available_at,
            verified_at=v_time,
            classification_reason="; ".join(reasons),
            supporting_evidence=supporting,
        )

    # Case C: Seed Authority only (no other positive evidence)
    if seed_class is not None:
        supporting = {"seed_profile": seed_class.value}
        ev_id = compute_classification_evidence_id(
            issuer_identity=clean_identity,
            ticker=clean_ticker,
            entity_class=seed_class.value,
            classification_status=ClassificationStatus.QUALIFIED.value,
            source_id="config/ticker_entity_profiles.csv",
            evidence_payload=supporting,
        )
        return EntityClassificationRecord(
            issuer_identity=clean_identity,
            ticker=clean_ticker,
            legal_name=legal_name,
            entity_class=seed_class,
            classification_status=ClassificationStatus.QUALIFIED,
            confidence_semantics=ConfidenceSemantics.DETERMINISTIC_PROOF,
            evidence_tier=EvidenceTier.CURATED_SEED_AUTHORITY,
            classification_evidence_id=ev_id,
            source_id="config/ticker_entity_profiles.csv",
            source_record_id=clean_ticker,
            effective_from=effective_from,
            knowledge_available_at=knowledge_available_at,
            verified_at=v_time,
            classification_reason="seed_profile_from_config_ticker_entity_profiles",
            supporting_evidence=supporting,
        )

    # Case D: General Enterprise Name Descriptor (CTCP / Cong ty co phan without specialized financial charter)
    # When legal name clearly shows an ordinary enterprise, e.g. "CTCP May 32", "Công ty Cổ phần Sữa Việt Nam"
    if legal_name:
        norm_n = _normalize_text(legal_name)
        if any(prefix in norm_n for prefix in ("cong ty co phan", "ctcp", "tong cong ty", "tap doan", "cong ty tnhh")):
            supporting = {"general_enterprise_name": legal_name}
            ev_id = compute_classification_evidence_id(
                issuer_identity=clean_identity,
                ticker=clean_ticker,
                entity_class=EntityClass.CORPORATE.value,
                classification_status=ClassificationStatus.QUALIFIED.value,
                source_id=source_id,
                evidence_payload=supporting,
            )
            return EntityClassificationRecord(
                issuer_identity=clean_identity,
                ticker=clean_ticker,
                legal_name=legal_name,
                entity_class=EntityClass.CORPORATE,
                classification_status=ClassificationStatus.QUALIFIED,
                confidence_semantics=ConfidenceSemantics.DETERMINISTIC_PROOF,
                evidence_tier=EvidenceTier.EXCHANGE_SECURITY_MASTER,
                classification_evidence_id=ev_id,
                source_id=source_id,
                source_record_id=source_record_id,
                effective_from=effective_from,
                knowledge_available_at=knowledge_available_at,
                verified_at=v_time,
                classification_reason="general_commercial_enterprise_charter_without_specialized_financial_license",
                supporting_evidence=supporting,
            )

    # Case E: Fail-Closed UNKNOWN
    supporting = {
        "charter_evaluation": charter_reason,
        "form_evaluation": form_reason,
        "marker_evaluation": marker_reason,
    }
    ev_id = compute_classification_evidence_id(
        issuer_identity=clean_identity,
        ticker=clean_ticker,
        entity_class=EntityClass.UNKNOWN.value,
        classification_status=ClassificationStatus.UNKNOWN.value,
        source_id=source_id,
        evidence_payload=supporting,
    )
    return EntityClassificationRecord(
        issuer_identity=clean_identity,
        ticker=clean_ticker,
        legal_name=legal_name,
        entity_class=EntityClass.UNKNOWN,
        classification_status=ClassificationStatus.UNKNOWN,
        confidence_semantics=ConfidenceSemantics.UNPROVEN_ABSENCE,
        evidence_tier=EvidenceTier.EXCHANGE_SECURITY_MASTER,
        classification_evidence_id=ev_id,
        source_id=source_id,
        source_record_id=source_record_id,
        effective_from=effective_from,
        knowledge_available_at=knowledge_available_at,
        verified_at=v_time,
        classification_reason="UNKNOWN: Insufficient positive legal charter, form code, or line-item evidence",
        supporting_evidence=supporting,
    )
