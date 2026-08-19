"""Phase 2 / P2-F1: Generic Financial Disclosure & Sector Statement Recognizer.

Pure, deterministic, data-driven recognition and extraction engine for sector-specific
financial statements and accompanying notes/disclosures (bank, securities, corporate,
insurance, and finance_company).

Core Architecture:
1. Entity-Class Pre-Gating:
   Resolves issuer entity class via authoritative Layered Resolver
   (entity_classification_contract.resolve_layered_entity_classification).
   Fails closed on UNKNOWN, AMBIGUOUS, CONFLICT, or UNPROVEN historical PIT.
2. Statement & Disclosure Structure Recognition:
   - Primary statement types (Balance Sheet, Income Statement, Cash Flow)
   - Statutory form codes (B 01-DN, B 01-NH/B 02-TCTD, B 01-CTCK, B 01-BH)
   - Note & Disclosure sections (B 09-DN, B 05-NH/B 05-TCTD, B 09-CTCK, B 09-BH)
3. Note Headings & Cross-References Recognition:
   - Deterministic note heading patterns ("Thuyết minh số X", "Note X", "X. Tiêu đề")
   - Cross-reference mapping between primary statement lines and note indices.
4. Unit, Scale & Period-Column Discovery:
   - Form-wide reporting currency and scale factor (VND, triệu VND, tỷ VND).
   - Period-column layout parsing ("Số cuối năm" / "Năm nay" vs "Số đầu năm" / "Năm trước").
5. Provenance & Citation Lineage:
   - Immutable output facts bound to document SHA-256, page number, and SHA-256 citation ID.
6. Invariant Governance:
   - TICKER_SPECIFIC_SECTOR_EXTRACTION_BRANCH_COUNT = 0
   - No branching on ticker symbol, issuer name, hostname, document SHA, or fixed page numbers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
import hashlib
import json
import re
from typing import Any, Mapping, Sequence
import unicodedata

from annual_financial_ocr_materialization import parse_accounting_integer
from entity_classification_contract import (
    ClassificationStatus,
    EntityClass,
    resolve_layered_entity_classification,
)
from sector_financial_taxonomy import (
    ALL_SECTOR_METRICS,
    MetricApplicabilityState,
    MetricDefinition,
    REAL_DATA_PROOF_CORPUS,
    REAL_DATA_VALIDATED_SECTORS,
    SCHEMA_ONLY_SECTORS,
    SECTOR_INAPPLICABLE_CORPORATE_METRICS,
    SECTOR_PRIMARY_STATEMENT_FORMS,
    StatementFormFamily,
    evaluate_metric_sector_applicability,
)

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "financial_disclosure_recognizer/v1"
TICKER_SPECIFIC_SECTOR_EXTRACTION_BRANCH_COUNT = 0


class DisclosureSectionType(StrEnum):
    PRIMARY_STATEMENT = "primary_statement"
    NOTES_AND_DISCLOSURES = "notes_and_disclosures"
    AUDIT_REPORT = "audit_report"
    DIRECTORS_REPORT = "directors_report"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RecognizedDisclosurePage:
    page_number: int
    section_type: DisclosureSectionType
    statement_type: str | None
    form_code: str | None
    title_match: str
    detected_note_numbers: tuple[str, ...]
    is_continuation: bool
    text: str


@dataclass(frozen=True)
class RecognizedNoteHeading:
    note_number: str
    note_title: str
    page_number: int
    matched_heading_text: str


@dataclass(frozen=True)
class ExtractedSectorFact:
    """One immutable sector financial fact extracted with complete provenance."""
    issuer_identity: str
    entity_class: str
    document_sha256: str
    qualification_id: str
    reporting_period: str
    statement_scope: str
    statement_or_note_section: str
    source_page: int
    note_number: str | None
    raw_label: str
    raw_value: str
    normalized_metric: str
    value: int | float | None
    currency: str
    unit_scale: int
    citation_id: str
    evidence_id: str
    extraction_status: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "issuer_identity": self.issuer_identity,
            "entity_class": self.entity_class,
            "document_sha256": self.document_sha256,
            "qualification_id": self.qualification_id,
            "reporting_period": self.reporting_period,
            "statement_scope": self.statement_scope,
            "statement_or_note_section": self.statement_or_note_section,
            "source_page": self.source_page,
            "note_number": self.note_number,
            "raw_label": self.raw_label,
            "raw_value": self.raw_value,
            "normalized_metric": self.normalized_metric,
            "value": self.value,
            "currency": self.currency,
            "unit_scale": self.unit_scale,
            "citation_id": self.citation_id,
            "evidence_id": self.evidence_id,
            "extraction_status": self.extraction_status,
            "reason_codes": list(self.reason_codes),
        }


def _normalize_text(s: str) -> str:
    """Normalize unicode and strip combining marks for tolerant anchor lookup."""
    if not s:
        return ""
    norm = unicodedata.normalize("NFD", str(s).strip().lower())
    no_diacritics = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    cleaned = no_diacritics.replace("đ", "d").replace("’", "'").replace("`", "'")
    return " ".join(cleaned.split())


def compute_sector_citation_id(
    *,
    ticker: str,
    metric: str,
    reporting_period: str,
    document_sha256: str,
    source_page: int,
    raw_value: str,
    note_number: str | None = None,
) -> str:
    """Compute deterministic SHA-256 citation ID bound to document, page, and note."""
    note_part = f"|{note_number}" if note_number else ""
    payload = f"sector_citation|{ticker.upper()}|{metric}|{reporting_period}|{document_sha256}|{source_page}|{raw_value}{note_part}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# Generic Note Section Header Patterns
_NOTE_SECTION_HEADER_PATTERNS: tuple[str, ...] = (
    "ban thuyet minh bao cao tai chinh",
    "thuyet minh bao cao tai chinh",
    "thuyet minh bao cao tai chinh hop nhat",
    "ban thuyet minh bao cao tai chinh hop nhat",
    "notes to the consolidated financial statements",
    "notes to the financial statements",
    "notes to the separate financial statements",
)

# Generic Note Number & Heading Regexes
_NOTE_HEADING_REGEXES: tuple[re.Pattern, ...] = (
    # "Thuyết minh số 15: Vốn chủ sở hữu" or "Thuyết minh 15. Vay và nợ"
    re.compile(r"^(?:thuyet\s+minh|ghi\s+chu|note)\s*(?:so|no\.?)?\s*(\d+(?:\.\d+)?)\s*[:\.\-—–]\s*(.+)$", re.IGNORECASE),
    # "15. Vốn chủ sở hữu" / "21. Short-term borrowings" (starts with number and period)
    re.compile(r"^(\d+(?:\.\d+)?)\s*[\.\-—–]\s*([a-zA-ZÀ-ỹ\s,_\(\)\/]+)$", re.IGNORECASE),
    # "VI.15. Vốn chủ sở hữu" (roman numeral section prefix)
    re.compile(r"^[ivxLCDM]+\s*[\.\-—–]\s*(\d+(?:\.\d+)?)\s*[\.\-—–]\s*(.+)$", re.IGNORECASE),
)

# Note Cross-Reference Column Header Patterns
_NOTE_COLUMN_PATTERNS: tuple[str, ...] = (
    "thuyet minh",
    "tm",
    "thuyet_minh",
    "note",
    "notes",
)


def recognize_disclosure_page(
    page_text: str,
    page_number: int,
    entity_class: EntityClass = EntityClass.UNKNOWN,
) -> RecognizedDisclosurePage:
    """Recognize statement type or note/disclosure section from page text."""
    norm_text = _normalize_text(page_text)
    
    # 1. Check for Note Section headers
    for pat in _NOTE_SECTION_HEADER_PATTERNS:
        if pat in norm_text:
            # Detect note numbers on this page
            note_nums = extract_note_numbers_from_text(page_text)
            form_code = detect_form_code(norm_text, entity_class)
            return RecognizedDisclosurePage(
                page_number=page_number,
                section_type=DisclosureSectionType.NOTES_AND_DISCLOSURES,
                statement_type="notes",
                form_code=form_code,
                title_match=pat,
                detected_note_numbers=tuple(note_nums),
                is_continuation=False,
                text=page_text,
            )

    # 2. Check for Primary Statement types
    # Balance Sheet
    bs_patterns = (
        "bang can doi ke toan",
        "bao cao tinh hinh tai chinh",
        "statement of financial position",
        "balance sheet",
    )
    for pat in bs_patterns:
        if pat in norm_text:
            form_code = detect_form_code(norm_text, entity_class)
            is_cont = ("tiep theo" in norm_text or "continued" in norm_text)
            return RecognizedDisclosurePage(
                page_number=page_number,
                section_type=DisclosureSectionType.PRIMARY_STATEMENT,
                statement_type="balance_sheet",
                form_code=form_code,
                title_match=pat,
                detected_note_numbers=(),
                is_continuation=is_cont,
                text=page_text,
            )

    # Income Statement
    is_patterns = (
        "bao cao ket qua hoat dong kinh doanh",
        "bao cao ket qua kinh doanh",
        "income statement",
        "statement of income",
        "statement of profit or loss",
    )
    for pat in is_patterns:
        if pat in norm_text:
            form_code = detect_form_code(norm_text, entity_class)
            is_cont = ("tiep theo" in norm_text or "continued" in norm_text)
            return RecognizedDisclosurePage(
                page_number=page_number,
                section_type=DisclosureSectionType.PRIMARY_STATEMENT,
                statement_type="income_statement",
                form_code=form_code,
                title_match=pat,
                detected_note_numbers=(),
                is_continuation=is_cont,
                text=page_text,
            )

    # Cash Flow
    cf_patterns = (
        "bao cao luu chuyen tien te",
        "cash flow statement",
        "statement of cash flows",
    )
    for pat in cf_patterns:
        if pat in norm_text:
            form_code = detect_form_code(norm_text, entity_class)
            is_cont = ("tiep theo" in norm_text or "continued" in norm_text)
            return RecognizedDisclosurePage(
                page_number=page_number,
                section_type=DisclosureSectionType.PRIMARY_STATEMENT,
                statement_type="cash_flow",
                form_code=form_code,
                title_match=pat,
                detected_note_numbers=(),
                is_continuation=is_cont,
                text=page_text,
            )

    # Check if page is continuation of notes
    note_nums = extract_note_numbers_from_text(page_text)
    if note_nums:
        form_code = detect_form_code(norm_text, entity_class)
        return RecognizedDisclosurePage(
            page_number=page_number,
            section_type=DisclosureSectionType.NOTES_AND_DISCLOSURES,
            statement_type="notes",
            form_code=form_code,
            title_match="note_continuation",
            detected_note_numbers=tuple(note_nums),
            is_continuation=True,
            text=page_text,
        )

    return RecognizedDisclosurePage(
        page_number=page_number,
        section_type=DisclosureSectionType.UNKNOWN,
        statement_type=None,
        form_code=None,
        title_match="none",
        detected_note_numbers=(),
        is_continuation=False,
        text=page_text,
    )


def detect_form_code(norm_text: str, entity_class: EntityClass) -> str | None:
    """Detect standard Vietnamese accounting form code from page text."""
    # Look for known statutory forms across all classes
    forms_to_check = [
        # Bank forms
        ("b 01-nh/hn", "B 01-NH/HN"), ("b 01-nh", "B 01-NH"),
        ("b 02/tctd-hn", "B 02/TCTD-HN"), ("b 02/tctd", "B 02/TCTD"),
        ("b 02-nh/hn", "B 02-NH/HN"), ("b 02-nh", "B 02-NH"),
        ("b 03/tctd-hn", "B 03/TCTD-HN"), ("b 03/tctd", "B 03/TCTD"),
        ("b 03-nh/hn", "B 03-NH/HN"), ("b 03-nh", "B 03-NH"),
        ("b 04/tctd-hn", "B 04/TCTD-HN"), ("b 04/tctd", "B 04/TCTD"),
        ("b 05-nh/hn", "B 05-NH/HN"), ("b 05-nh", "B 05-NH"),
        ("b 05/tctd-hn", "B 05/TCTD-HN"), ("b 05/tctd", "B 05/TCTD"),
        # Securities forms
        ("b01-ctck/hn", "B01-CTCK/HN"), ("b 01-ctck/hn", "B 01-CTCK/HN"),
        ("b01-ctck", "B01-CTCK"), ("b 01-ctck", "B 01-CTCK"),
        ("b 01-ck", "B 01-CK"), ("b 01-ctc/hn", "B 01-CTC/HN"),
        ("b02-ctck/hn", "B02-CTCK/HN"), ("b 02-ctck/hn", "B 02-CTCK/HN"),
        ("b02-ctck", "B02-CTCK"), ("b 02-ctck", "B 02-CTCK"),
        ("b 02-ck", "B 02-CK"), ("b 02-ctc/hn", "B 02-CTC/HN"),
        ("b03-ctck/hn", "B03-CTCK/HN"), ("b 03-ctck/hn", "B 03-CTCK/HN"),
        ("b 03-ck", "B 03-CK"), ("b 09-ctck", "B 09-CTCK"),
        # Insurance forms
        ("b 01-bh/hn", "B 01-BH/HN"), ("b 01-bh", "B 01-BH"),
        ("b 02-bh/hn", "B 02-BH/HN"), ("b 02-bh", "B 02-BH"),
        ("b 03-bh/hn", "B 03-BH/HN"), ("b 03-bh", "B 03-BH"),
        ("b 09-bh/hn", "B 09-BH/HN"), ("b 09-bh", "B 09-BH"),
        # Corporate forms
        ("b 01-dn/hn", "B 01-DN/HN"), ("b 01-dn", "B 01-DN"),
        ("b 02-dn/hn", "B 02-DN/HN"), ("b 02-dn", "B 02-DN"),
        ("b 03-dn/hn", "B 03-DN/HN"), ("b 03-dn", "B 03-DN"),
        ("b 09-dn/hn", "B 09-DN/HN"), ("b 09-dn", "B 09-DN"),
        ("b 09a-dn", "B 09a-DN"),
    ]
    for key, display in forms_to_check:
        if key in norm_text:
            return display
    return None


def extract_note_numbers_from_text(page_text: str) -> list[str]:
    """Extract list of detected note numbers from page lines."""
    found: list[str] = []
    lines = page_text.splitlines()
    for raw_line in lines:
        line_clean = raw_line.strip()
        norm_line = _normalize_text(line_clean)
        for pattern in _NOTE_HEADING_REGEXES:
            m = pattern.match(norm_line)
            if m:
                note_num = m.group(1).strip()
                if note_num not in found:
                    found.append(note_num)
                break
    return found


def extract_note_headings(
    pages: Sequence[Mapping[str, Any]],
) -> list[RecognizedNoteHeading]:
    """Scan all pages to extract recognized note headings and their page numbers."""
    headings: list[RecognizedNoteHeading] = []
    for p in pages:
        p_num = int(p.get("page") or 0)
        p_text = str(p.get("text") or "")
        lines = p_text.splitlines()
        for line in lines:
            line_clean = line.strip()
            norm_line = _normalize_text(line_clean)
            for pattern in _NOTE_HEADING_REGEXES:
                m = pattern.match(norm_line)
                if m:
                    note_num = m.group(1).strip()
                    title_raw = m.group(2).strip() if len(m.groups()) > 1 else ""
                    headings.append(
                        RecognizedNoteHeading(
                            note_number=note_num,
                            note_title=title_raw,
                            page_number=p_num,
                            matched_heading_text=line_clean,
                        )
                    )
                    break
    return headings


def recognize_unit_scale_from_evidence(
    text: str,
) -> tuple[str, int, str]:
    """Recognize reporting currency and scale factor (currency, unit_scale, unit_label)."""
    norm = _normalize_text(text)
    
    # Check scale
    if "ty vnd" in norm or "ty dong" in norm or "billion vnd" in norm:
        return "VND", 1_000_000_000, "tỷ VND"
    elif "trieu vnd" in norm or "trieu dong" in norm or "million vnd" in norm:
        return "VND", 1_000_000, "triệu VND"
    elif "dong" in norm or "vnd" in norm or "currency: vnd" in norm:
        return "VND", 1, "VND"
    elif "usd" in norm or "currency: usd" in norm:
        return "USD", 1, "USD"
    
    # Default to VND scale 1 if standard Vietnamese statement
    return "VND", 1, "VND"


def extract_sector_facts_from_sidecar(
    *,
    ticker: str,
    qualification: Mapping[str, Any],
    sidecar: Mapping[str, Any],
    reporting_period: str = "2024",
    statement_scope: str = "consolidated",
    verified_at: str | None = None,
) -> list[ExtractedSectorFact]:
    """Extract verified sector financial facts and disclosure citations from sidecar.

    Gated by authoritative Layered Entity Classification.
    Fails closed if entity class is UNKNOWN, AMBIGUOUS, or CONFLICT.
    """
    clean_sym = str(ticker).upper().strip()
    
    # 1. Authoritative Entity Class Gating
    layered_res = resolve_layered_entity_classification(clean_sym)
    if not layered_res.is_positive_authority or layered_res.resolved_entity_class == EntityClass.UNKNOWN:
        # Fails closed
        return [
            ExtractedSectorFact(
                issuer_identity=clean_sym,
                entity_class=layered_res.resolved_entity_class.value,
                document_sha256=str(qualification.get("sha256") or ""),
                qualification_id=str(qualification.get("document_id") or ""),
                reporting_period=reporting_period,
                statement_scope=statement_scope,
                statement_or_note_section="gating",
                source_page=0,
                note_number=None,
                raw_label="entity_class_gate",
                raw_value="",
                normalized_metric="entity_class_gate",
                value=None,
                currency="VND",
                unit_scale=1,
                citation_id=compute_sector_citation_id(
                    ticker=clean_sym,
                    metric="entity_class_gate",
                    reporting_period=reporting_period,
                    document_sha256=str(qualification.get("sha256") or ""),
                    source_page=0,
                    raw_value="",
                ),
                evidence_id="",
                extraction_status="ENTITY_CLASS_UNRESOLVED",
                reason_codes=(f"Entity class unresolved ({layered_res.resolved_entity_class.value}); extraction failed closed",),
            )
        ]

    e_class = layered_res.resolved_entity_class

    # 2. Check Schema-Only Sector Gate
    if e_class.value in SCHEMA_ONLY_SECTORS:
        return [
            ExtractedSectorFact(
                issuer_identity=clean_sym,
                entity_class=e_class.value,
                document_sha256=str(qualification.get("sha256") or ""),
                qualification_id=str(qualification.get("document_id") or ""),
                reporting_period=reporting_period,
                statement_scope=statement_scope,
                statement_or_note_section="gating",
                source_page=0,
                note_number=None,
                raw_label="sector_proof_gate",
                raw_value="",
                normalized_metric="sector_proof_gate",
                value=None,
                currency="VND",
                unit_scale=1,
                citation_id=compute_sector_citation_id(
                    ticker=clean_sym,
                    metric="sector_proof_gate",
                    reporting_period=reporting_period,
                    document_sha256=str(qualification.get("sha256") or ""),
                    source_page=0,
                    raw_value="",
                ),
                evidence_id="",
                extraction_status="SCHEMA_SUPPORTED_BUT_NOT_REAL_DATA_VALIDATED",
                reason_codes=(f"Sector {e_class.value} is schema-supported only; real proof filing not authorized",),
            )
        ]

    doc_sha = str(qualification.get("sha256") or sidecar.get("document_sha256") or "")
    doc_id = str(qualification.get("document_id") or sidecar.get("document_id") or "")
    evidence_id = hashlib.sha256(f"{clean_sym}|{doc_sha}|{doc_id}".encode("utf-8")).hexdigest()

    pages = list(sidecar.get("pages") or [])
    note_headings = extract_note_headings(pages)
    note_map = {h.note_number: h for h in note_headings}

    sector_vocab = ALL_SECTOR_METRICS.get(e_class, {})
    extracted_facts: list[ExtractedSectorFact] = []

    EXPENSE_METRICS = {
        "interest_expense", "operating_expenses", "provision_for_credit_losses",
        "fvtpl_loss", "borrowing_costs", "cost_of_goods_sold", "selling_expense",
        "general_admin_expense", "financial_expenses", "claim_expenses",
    }

    # Map across all pages in the sidecar
    for p in pages:
        p_num = int(p.get("page") or 0)
        p_text = str(p.get("text") or "")
        curr, scale, scale_label = recognize_unit_scale_from_evidence(p_text)
        rec_page = recognize_disclosure_page(p_text, p_num, e_class)

        lines = p_text.splitlines()
        for line in lines:
            line_clean = line.strip()
            if not line_clean:
                continue
            norm_line = _normalize_text(line_clean)

            # Find best (most specific/longest) matching metric for this line
            best_metric_key = None
            best_m_def = None
            best_match_len = 0

            for metric_key, m_def in sector_vocab.items():
                # If page is a recognized primary statement, enforce statement family alignment
                if rec_page.section_type == DisclosureSectionType.PRIMARY_STATEMENT and rec_page.statement_type:
                    if m_def.statement_family != rec_page.statement_type:
                        continue
                elif rec_page.section_type == DisclosureSectionType.NOTES_AND_DISCLOSURES:
                    if m_def.statement_family not in {"notes_and_disclosures", "balance_sheet", "income_statement"}:
                        continue

                # Disambiguate provision expenses from "before provision" operating profit
                if metric_key == "provision_for_credit_losses" and ("truoc chi phi" in norm_line or "before provision" in norm_line):
                    continue

                for alias_vi in m_def.raw_label_aliases_vi:
                    norm_alias = _normalize_text(alias_vi)
                    if norm_alias and norm_alias in norm_line:
                        if len(norm_alias) > best_match_len:
                            best_match_len = len(norm_alias)
                            best_metric_key = metric_key
                            best_m_def = m_def

                for alias_en in m_def.raw_label_aliases_en:
                    norm_alias = _normalize_text(alias_en)
                    if norm_alias and norm_alias in norm_line:
                        if len(norm_alias) > best_match_len:
                            best_match_len = len(norm_alias)
                            best_metric_key = metric_key
                            best_m_def = m_def

            if best_metric_key and best_m_def:
                # Extract accounting value from line
                val_int, raw_val_str = _extract_number_from_line(line_clean)
                if val_int is not None:
                    # Extract cross-reference note number if present in line
                    line_note_num = _extract_line_note_cross_ref(line_clean)

                    citation_id = compute_sector_citation_id(
                        ticker=clean_sym,
                        metric=best_metric_key,
                        reporting_period=reporting_period,
                        document_sha256=doc_sha,
                        source_page=p_num,
                        raw_value=raw_val_str,
                        note_number=line_note_num,
                    )

                    # Canonical magnitude rule: expenses reported in parentheses on statement are positive magnitudes
                    if best_metric_key in EXPENSE_METRICS:
                        scaled_value = abs(val_int) * scale * best_m_def.sign_multiplier
                    else:
                        scaled_value = val_int * scale * best_m_def.sign_multiplier

                    fact = ExtractedSectorFact(
                        issuer_identity=clean_sym,
                        entity_class=e_class.value,
                        document_sha256=doc_sha,
                        qualification_id=doc_id,
                        reporting_period=reporting_period,
                        statement_scope=statement_scope,
                        statement_or_note_section=best_m_def.statement_family,
                        source_page=p_num,
                        note_number=line_note_num,
                        raw_label=line_clean,
                        raw_value=raw_val_str,
                        normalized_metric=best_metric_key,
                        value=scaled_value,
                        currency=curr,
                        unit_scale=scale,
                        citation_id=citation_id,
                        evidence_id=evidence_id,
                        extraction_status="QUALIFIED",
                        reason_codes=("EXACT_SEMANTIC_MATCH",),
                    )

                    # Avoid duplicates for same metric on same page
                    if not any(f.normalized_metric == best_metric_key and f.source_page == p_num for f in extracted_facts):
                        extracted_facts.append(fact)

    return extracted_facts


def _extract_number_from_line(line: str) -> tuple[int | None, str]:
    """Extract the primary accounting integer and raw string from line tokens."""
    # Split line and look for numeric accounting tokens (e.g. 46,599,438,522,989 or (1,458,465,074,277))
    # Tokens may have spaces between thousands if OCR split them, e.g. "45,501 ,969,699, 137"
    cleaned = re.sub(r"\s*([,\.])\s*", r"\1", line)
    tokens = cleaned.split()

    # Scan from right to left (most financial figures appear at the end of the line)
    for tok in reversed(tokens):
        # Remove trailing punctuation or OCR garbage
        tok_clean = tok.strip(";|[]{}'\"")
        if not tok_clean:
            continue
        try:
            val_int, norm_str = parse_accounting_integer(tok_clean)
            if val_int is not None and abs(val_int) > 0:
                return val_int, tok_clean
        except (ValueError, TypeError):
            continue

    return None, ""


def _extract_line_note_cross_ref(line: str) -> str | None:
    """Extract note cross-reference number if explicitly columned in the line."""
    # Examples: "311 | 1. Short-term borrowings ... | 21 | 45,501,969,699,137" -> Note 21
    # or "Revenue from brokerage services 22 1,667,430,605,344"
    parts = [p.strip() for p in line.split("|") if p.strip()]
    if len(parts) >= 3:
        for part in parts[1:-1]:
            if re.match(r"^\d+(?:\.\d+)?$", part):
                return part
    # Look for standalone small integer token before the large monetary numbers
    tokens = line.split()
    for i, tok in enumerate(tokens[:-1]):
        if re.match(r"^\d{1,2}(?:\.\d+)?$", tok) and i > 0 and len(tokens[i+1]) > 5:
            return tok
    return None
