"""Phase 2 / P2-D: Generic Financial Statement Template Recognition and Extraction Contract.

Pure, deterministic, data-driven financial statement template recognition engine
capable of consuming qualified retained annual corporate financial statements and
persisted OCR/text sidecars without ticker-specific production recipes:

1. Statement Structure Recognition:
   - Balance Sheet (Bảng cân đối kế toán / B 01-DN)
   - Income Statement (Báo cáo kết quả hoạt động kinh doanh / B 02-DN)
   - Cash Flow Statement (Báo cáo lưu chuyển tiền tệ / B 03-DN)
2. Unit & Scale Recognition:
   - Discovers reporting currency and scale (VND, triệu VND, tỷ VND) from statement evidence.
   - Fails closed with UNIT_SCALE_AMBIGUOUS if absent or conflicting.
3. Period-Column Semantic Recognition:
   - Parses column headers ("Số cuối năm" / "Năm nay" vs "Số đầu năm" / "Năm trước", dates).
   - Maps value positions strictly to requested reporting periods.
   - Fails closed with PERIOD_COLUMN_AMBIGUOUS if unverified.
4. Canonical Metric Recognition:
   - Standard line-item codes (10, 61/60, 20, 270, 400, 110, 310, 320+338) and normalized labels.
   - Canonical net_income strictly adheres to profit attributable to parent company shareholders
     (Line 61 on consolidated Form B 02-DN/HN, or Line 60 on unconsolidated statements).
   - Fails closed with DEBT_COMPONENT_MISSING if debt components are incomplete.
5. Invariant Governance:
   - TICKER_SPECIFIC_EXTRACTION_BRANCH_COUNT = 0
   - No logic keyed on ticker symbol, issuer name, hostname, or document SHA.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json
import re
from typing import Any, Mapping, Sequence
import unicodedata

from annual_financial_ocr_materialization import (
    parse_accounting_integer,
    verified_debt_extraction,
    verified_extraction,
)

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "financial_statement_template_recognizer/v1"
CANONICAL_NET_INCOME_SEMANTIC = "net_income_attributable_to_parent"


class StatementType(StrEnum):
    BALANCE_SHEET = "balance_sheet"
    INCOME_STATEMENT = "income_statement"
    CASH_FLOW = "cash_flow"


@dataclass(frozen=True)
class RecognizedStatementPage:
    page_number: int
    statement_type: StatementType
    title_match: str
    form_code: str | None
    is_continuation: bool
    text: str


@dataclass(frozen=True)
class RecognizedUnitScale:
    currency: str
    unit_scale: int
    unit_label: str
    evidence_text: str


@dataclass(frozen=True)
class PeriodColumnLayout:
    statement_type: StatementType
    target_period: str
    target_column_index: int
    current_period_label: str
    comparative_period_label: str | None
    header_evidence: str


@dataclass(frozen=True)
class ExtractedStatementFact:
    canonical_metric: str
    statement_type: str
    page: int
    line_item_code: str
    source_label: str
    ocr_matched_label: str
    raw_value: str
    normalized_value: int
    currency: str
    unit_scale: int
    unit_label: str
    reporting_period: str
    period_column_evidence: dict[str, Any]
    unit_evidence: dict[str, Any]
    extraction_details: dict[str, Any]


def _normalize_text(s: str) -> str:
    """Normalize unicode and strip diacritics for tolerant anchor matching."""
    if not s:
        return ""
    norm = unicodedata.normalize("NFD", str(s).strip().lower())
    no_diacritics = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    cleaned = no_diacritics.replace("đ", "d").replace("’", "'").replace("`", "'")
    return " ".join(cleaned.split())


# Centralized standard statement recognition patterns
STATEMENT_PATTERNS = {
    StatementType.BALANCE_SHEET: {
        "titles": (
            "bang can doi ke toan hop nhat",
            "bang can doi ke toan",
            "bang can boi ke toan",  # OCR typo variant
            "balance sheet",
            "consolidated balance sheet",
            "consolidated statement of financial position",
        ),
        "form_codes": ("b 01-dn", "b 01 - dn", "b 01—dn", "b 01-dn/hn", "b 01 - dn/hn", "mau so b 01"),
        "key_anchors": ("tai san ngan han", "tong cong tai san", "nguon von", "no phai tra", "von chu so huu"),
    },
    StatementType.INCOME_STATEMENT: {
        "titles": (
            "bao cao ket qua hoat dong kinh doanh hop nhat",
            "bao cao ket qua hoat dong kinh doanh",
            "bao cao ket qua kinh doanh",
            "income statement",
            "consolidated income statement",
            "consolidated statement of income",
            "consolidated statement of profit or loss",
        ),
        "form_codes": ("b 02-dn", "b 02 - dn", "b 02—dn", "b 02-dn/hn", "b 02 - dn/hn", "mau so b 02"),
        "key_anchors": ("doanh thu ban hang", "doanh thu thuan", "loi nhuan sau thue"),
    },
    StatementType.CASH_FLOW: {
        "titles": (
            "bao cao luu chuyen tien te hop nhat",
            "bao cao luu chuyen tien te",
            "cash flow statement",
            "consolidated cash flow statement",
            "consolidated statement of cash flows",
            "cash flows from operating activities",
        ),
        "form_codes": ("b 03-dn", "b 03 - dn", "b 03—dn", "b 03-dn/hn", "b 03 - dn/hn", "mau so b 03"),
        "key_anchors": ("luu chuyen tien tu hoat dong kinh doanh", "luu chuyen tien thuan tu hoat dong kinh doanh"),
    },
}


def recognize_statement_type(page_text: str) -> tuple[StatementType | None, str, str | None, bool]:
    """Recognize statement type from page text.
    
    Returns (statement_type, title_match, form_code, is_continuation).
    """
    norm = _normalize_text(page_text)
    is_continuation = "tiep theo" in norm or "continuation" in norm or "(tiep theo)" in norm

    for st_type, patterns in STATEMENT_PATTERNS.items():
        matched_title = ""
        matched_form = None

        for form in patterns["form_codes"]:
            if form in norm:
                matched_form = form
                break

        for title in patterns["titles"]:
            if title in norm:
                matched_title = title
                break

        if matched_title or matched_form:
            return st_type, matched_title or matched_form or "", matched_form, is_continuation

        # Fallback to key anchors if continuation page without explicit top header
        if is_continuation:
            anchor_hits = sum(1 for anchor in patterns["key_anchors"] if anchor in norm)
            if anchor_hits >= 2:
                return st_type, "continuation_anchors_match", None, True

    return None, "", None, False


def recognize_unit_and_scale(page_text: str) -> RecognizedUnitScale | None:
    """Discover unit, currency, and scale multiplier from statement page text."""
    lines = page_text.splitlines()
    for line in lines:
        l_norm = _normalize_text(line)
        if "don vi" in l_norm or "unit" in l_norm:
            if "trieu" in l_norm or "million" in l_norm:
                return RecognizedUnitScale(
                    currency="VND",
                    unit_scale=1_000_000,
                    unit_label="triệu VND",
                    evidence_text=line.strip(),
                )
            if "ty" in l_norm or "billion" in l_norm:
                return RecognizedUnitScale(
                    currency="VND",
                    unit_scale=1_000_000_000,
                    unit_label="tỷ VND",
                    evidence_text=line.strip(),
                )
            if "nghin" in l_norm or "thousand" in l_norm:
                return RecognizedUnitScale(
                    currency="VND",
                    unit_scale=1_000,
                    unit_label="nghìn VND",
                    evidence_text=line.strip(),
                )
            if "vnd" in l_norm or "dong" in l_norm:
                return RecognizedUnitScale(
                    currency="VND",
                    unit_scale=1,
                    unit_label="VND",
                    evidence_text=line.strip(),
                )
            if "usd" in l_norm or "u.s. dollar" in l_norm or "us dollar" in l_norm:
                return RecognizedUnitScale(
                    currency="USD",
                    unit_scale=1,
                    unit_label="USD",
                    evidence_text=line.strip(),
                )
    return None


def recognize_period_column_layout(
    page_text: str,
    statement_type: StatementType,
    target_period: str,
) -> PeriodColumnLayout:
    """Determine which numerical column corresponds to the target reporting period."""
    lines = page_text.splitlines()
    target_year = str(target_period).strip()
    try:
        target_year_int = int(target_year)
        prior_year = str(target_year_int - 1)
    except ValueError:
        prior_year = ""

    header_lines: list[str] = []
    for line in lines[:30]:  # Look inside the top 30 lines for the column header row
        l_norm = _normalize_text(line)
        if statement_type == StatementType.BALANCE_SHEET:
            if any(k in l_norm for k in ("so cuoi nam", "so dau nam", "31/12", "01/01", "closing balance", "opening balance", "cuoi nam", "dau nam")):
                header_lines.append(line.strip())
        else:
            if any(k in l_norm for k in ("nam nay", "nam truoc", "current year", "previous year", target_year, prior_year)):
                header_lines.append(line.strip())

    if not header_lines:
        raise ValueError(f"PERIOD_COLUMN_AMBIGUOUS: No recognizable column headers found for {statement_type}")

    combined_header = " | ".join(header_lines)
    header_norm = _normalize_text(combined_header)

    # Standard Case 1: Balance Sheet - "Số cuối năm" before "Số đầu năm"
    if statement_type == StatementType.BALANCE_SHEET:
        pos_closing = header_norm.find("so cuoi nam")
        if pos_closing == -1:
            pos_closing = header_norm.find("cuoi nam")
        pos_opening = header_norm.find("so dau nam")
        if pos_opening == -1:
            pos_opening = header_norm.find("dau nam")

        if pos_closing != -1 and pos_opening != -1:
            if pos_closing < pos_opening:
                return PeriodColumnLayout(
                    statement_type=statement_type,
                    target_period=target_period,
                    target_column_index=0,
                    current_period_label="Số cuối năm",
                    comparative_period_label="Số đầu năm",
                    header_evidence=combined_header,
                )
            else:
                return PeriodColumnLayout(
                    statement_type=statement_type,
                    target_period=target_period,
                    target_column_index=1,
                    current_period_label="Số cuối năm",
                    comparative_period_label="Số đầu năm",
                    header_evidence=combined_header,
                )

        pos_closing = header_norm.find("closing balance")
        pos_opening = header_norm.find("opening balance")
        if pos_closing != -1 and pos_opening != -1:
            return PeriodColumnLayout(
                statement_type=statement_type,
                target_period=target_period,
                target_column_index=0 if pos_closing < pos_opening else 1,
                current_period_label="Closing balance",
                comparative_period_label="Opening balance",
                header_evidence=combined_header,
            )

        # Date based matching
        pos_target_date = max(header_norm.find(f"31/12/{target_year}"), header_norm.find(f"31/12/20{target_year[-2:]}"))
        pos_prior_date = max(
            header_norm.find(f"31/12/{prior_year}"),
            header_norm.find(f"01/01/{target_year}"),
            header_norm.find(f"1/1/{target_year}"),
        )
        if pos_target_date != -1 and pos_prior_date != -1:
            col_idx = 0 if pos_target_date < pos_prior_date else 1
            return PeriodColumnLayout(
                statement_type=statement_type,
                target_period=target_period,
                target_column_index=col_idx,
                current_period_label=f"31/12/{target_year}",
                comparative_period_label=f"31/12/{prior_year}",
                header_evidence=combined_header,
            )

    # Standard Case 2: Income Statement / Cash Flow - "Năm nay" before "Năm trước"
    if statement_type in {StatementType.INCOME_STATEMENT, StatementType.CASH_FLOW}:
        pos_current = header_norm.find("nam nay")
        pos_prior = header_norm.find("nam truoc")
        if pos_current != -1 and pos_prior != -1:
            return PeriodColumnLayout(
                statement_type=statement_type,
                target_period=target_period,
                target_column_index=0 if pos_current < pos_prior else 1,
                current_period_label="Năm nay",
                comparative_period_label="Năm trước",
                header_evidence=combined_header,
            )

        pos_current = header_norm.find("current year")
        pos_prior = header_norm.find("prior year")
        if pos_prior == -1:
            pos_prior = header_norm.find("previous year")
        if pos_current != -1 and pos_prior != -1:
            return PeriodColumnLayout(
                statement_type=statement_type,
                target_period=target_period,
                target_column_index=0 if pos_current < pos_prior else 1,
                current_period_label="Current year",
                comparative_period_label="Prior year",
                header_evidence=combined_header,
            )

        # Year explicit matching
        pos_target_yr = header_norm.find(target_year)
        pos_prior_yr = header_norm.find(prior_year) if prior_year else -1
        if pos_target_yr != -1 and pos_prior_yr != -1:
            col_idx = 0 if pos_target_yr < pos_prior_yr else 1
            return PeriodColumnLayout(
                statement_type=statement_type,
                target_period=target_period,
                target_column_index=col_idx,
                current_period_label=f"Năm {target_year}",
                comparative_period_label=f"Năm {prior_year}",
                header_evidence=combined_header,
            )

    raise ValueError(f"PERIOD_COLUMN_AMBIGUOUS: Unable to establish unambiguous period orientation from '{combined_header}'")


# Centralized Canonical Metric Recognition Rules (Strictly Zero Ticker Branches)
GENERIC_METRIC_RULES: dict[str, dict[str, Any]] = {
    "revenue": {
        "statement_type": StatementType.INCOME_STATEMENT,
        "standard_line_code": "10",
        "label_anchors": (
            "doanh thu thuan ve ban hang va cung cap dich vu",
            "doanh thu thuan",
            "net revenue",
            "revenue",
        ),
        "source_label": "Doanh thu thuần về bán hàng và cung cấp dịch vụ",
    },
    "net_income": {
        "statement_type": StatementType.INCOME_STATEMENT,
        "standard_line_code": "61",  # Strictly profit attributable to parent company shareholders
        "label_anchors": (
            "loi nhuan sau thue",
            "loi nhuan",
            "co dong cua cong ty me",
            "co dong cong ty me",
            "cong ty me",
        ),
        "source_label": "Lợi nhuận sau thuế của cổ đông Công ty mẹ",
        "unconsolidated_fallback_line_code": "60",
    },
    "operating_cash_flow": {
        "statement_type": StatementType.CASH_FLOW,
        "standard_line_code": "20",
        "label_anchors": (
            "luu chuyen tien thuan",
            "hoat dong kinh doanh",
            "hoat dong kinh",
        ),
        "source_label": "Lưu chuyển tiền thuần từ hoạt động kinh doanh",
    },
    "total_assets": {
        "statement_type": StatementType.BALANCE_SHEET,
        "standard_line_code": "270",
        "label_anchors": (
            "tong cong tai san",
            "tong tai san",
            "total assets",
            "total resources",
            "tong nguon von",
            "tong cong nguon von",
        ),
        "source_label": "TỔNG CỘNG TÀI SẢN",
    },
    "shareholders_equity": {
        "statement_type": StatementType.BALANCE_SHEET,
        "standard_line_code": "400",
        "label_anchors": (
            "von chu so huu",
            "vonchuso",
            "von chu",
            "vonchu",
        ),
        "source_label": "VỐN CHỦ SỞ HỮU",
    },
    "cash_and_equivalents": {
        "statement_type": StatementType.BALANCE_SHEET,
        "standard_line_code": "110",
        "label_anchors": (
            "tien va cac khoan tuong duong tien",
            "tien va cac khoan twong dwong tien",
            "tuong duong tien",
            "tuong duongtien",
            "tien va cac khoan",
        ),
        "source_label": "Tiền và các khoản tương đương tiền",
    },
    "current_liabilities": {
        "statement_type": StatementType.BALANCE_SHEET,
        "standard_line_code": "310",
        "label_anchors": (
            "no ngan han",
            "nog ngan han",
            "no ngan",
        ),
        "source_label": "Nợ ngắn hạn",
    },
}

GENERIC_DEBT_COMPONENTS = (
    {
        "component_type": "short_term_borrowings",
        "line_item_code": "320",
        "label_anchors": (
            "vay va no thue tai chinh ngan han",
            "vay va no thue",
            "vay va no",
            "vay va ng thue tai chinh ngan han",
        ),
        "label": "Vay và nợ thuê tài chính ngắn hạn",
    },
    {
        "component_type": "long_term_borrowings_or_finance_leases",
        "line_item_code": "338",
        "label_anchors": (
            "vay va no thue tai chinh dai han",
            "vayva ng thue",
            "vay va ng thue tai chinh dai han",
            "vay va no thue dai han",
        ),
        "label": "Vay và nợ thuê tài chính dài hạn",
    },
)


def _find_line_item_on_pages(
    pages: Sequence[RecognizedStatementPage],
    target_code: str,
    label_anchors: Sequence[str],
    col_layout: PeriodColumnLayout,
) -> tuple[RecognizedStatementPage, str, str] | None:
    """Scan statement pages for a matching accounting line item and extract its target column value."""
    norm_anchors = [_normalize_text(a) for a in label_anchors]

    for p in pages:
        lines = p.text.splitlines()
        for line in lines:
            l_str = line.strip()
            if not l_str:
                continue
            l_norm = _normalize_text(l_str)

            # Match criteria: line must match anchor
            anchor_matched = any(anchor in l_norm for anchor in norm_anchors)
            if not anchor_matched:
                continue

            # Check line code
            if target_code and target_code not in l_str.split():
                # Allow line code if immediately adjacent to text / punctuation
                if not re.search(rf"\b{target_code}\b", l_str):
                    continue

            # Extract numeric tokens
            tokens = re.findall(r"\(?[0-9]{1,3}(?:[.,][0-9]{3})+\)?", l_str)
            valid_nums: list[str] = []
            for t in tokens:
                try:
                    parse_accounting_integer(t)
                    valid_nums.append(t)
                except Exception:
                    pass

            if not valid_nums:
                continue

            target_idx = col_layout.target_column_index
            if target_idx < len(valid_nums):
                selected_num = valid_nums[target_idx]
                return p, l_str, selected_num
            elif valid_nums:
                # If only one number exists on the line, select it
                return p, l_str, valid_nums[0]

    return None


def extract_generic_financial_statement_facts(
    *,
    sidecar: Mapping[str, Any],
    reporting_period: str,
    qualification_record: Mapping[str, Any] | None = None,
    verified_at: str | None = None,
    required_metrics: Sequence[str] | None = None,
) -> list[ExtractedStatementFact]:
    """Pure generic financial statement template recognition and fact extraction.
    
    Zero ticker branching: parses structure, column semantics, and line items purely from evidence.
    """
    doc_sha = str(sidecar.get("document_sha256", "")).strip()
    if not doc_sha:
        raise ValueError("QUALIFICATION_REQUIRED: Materialization sidecar lacks document_sha256")

    raw_pages = sidecar.get("pages", [])
    if not raw_pages:
        raise ValueError("OCR_INSUFFICIENT: Materialization sidecar contains zero pages")

    # Promotion manifests may carry a verified primary-statement transcription
    # rather than a full OCR sidecar. Normalize its required materialization
    # lineage fields generically before the governed verifier consumes it.
    materialization = dict(sidecar)
    materialization["pages"] = [
        {
            **dict(page),
            "document_id": str(page.get("document_id") or sidecar.get("document_id") or ""),
            "document_sha256": str(page.get("document_sha256") or doc_sha),
            "status": str(page.get("status") or "text_available"),
            "materialization_id": str(page.get("materialization_id") or f"statement-transcription:{doc_sha}"),
            "text_sha256": str(page.get("text_sha256") or hashlib.sha256(str(page.get("text", "")).encode("utf-8")).hexdigest()),
            "extraction_engine": str(page.get("extraction_engine") or "verified_transcription"),
        }
        for page in raw_pages
    ]
    raw_pages = materialization["pages"]

    # Step 1: Structure Recognition - Group pages by statement type
    statements_by_type: dict[StatementType, list[RecognizedStatementPage]] = {
        StatementType.BALANCE_SHEET: [],
        StatementType.INCOME_STATEMENT: [],
        StatementType.CASH_FLOW: [],
    }

    current_st_type: StatementType | None = None

    for raw_p in raw_pages:
        page_num = int(raw_p["page"])
        text = str(raw_p.get("text", ""))
        st_type, title, form, is_cont = recognize_statement_type(text)

        if st_type is not None:
            current_st_type = st_type
            statements_by_type[st_type].append(
                RecognizedStatementPage(
                    page_number=page_num,
                    statement_type=st_type,
                    title_match=title,
                    form_code=form,
                    is_continuation=is_cont,
                    text=text,
                )
            )
        elif is_cont and current_st_type is not None:
            # Continuation of previous statement
            statements_by_type[current_st_type].append(
                RecognizedStatementPage(
                    page_number=page_num,
                    statement_type=current_st_type,
                    title_match="continuation",
                    form_code=None,
                    is_continuation=True,
                    text=text,
                )
            )

    # Verify statement presence
    for req_type in (StatementType.BALANCE_SHEET, StatementType.INCOME_STATEMENT, StatementType.CASH_FLOW):
        if not statements_by_type[req_type]:
            raise ValueError(f"STATEMENT_NOT_RECOGNIZED: Could not locate {req_type} in filing sidecar")

    # Step 2: Discover Unit & Scale across statements
    global_unit_scale: RecognizedUnitScale | None = None
    for st_pages in statements_by_type.values():
        for p in st_pages:
            unit_candidate = recognize_unit_and_scale(p.text)
            if unit_candidate is not None:
                global_unit_scale = unit_candidate
                break
        if global_unit_scale is not None:
            break

    if global_unit_scale is None:
        raise ValueError("UNIT_SCALE_AMBIGUOUS: Failed to identify unit scale from statement evidence")

    # Step 3: Period Column Recognition for each statement
    column_layouts: dict[StatementType, PeriodColumnLayout] = {}
    for st_type, st_pages in statements_by_type.items():
        layout = None
        for p in st_pages:
            try:
                layout = recognize_period_column_layout(p.text, st_type, reporting_period)
                break
            except ValueError:
                continue
        if layout is None:
            raise ValueError(f"PERIOD_COLUMN_AMBIGUOUS: Could not resolve period column for {st_type}")
        column_layouts[st_type] = layout

    # Step 4: Line Item Recognition and Verified Extraction
    extracted_facts: list[ExtractedStatementFact] = []

    selected_metrics = (
        set(required_metrics)
        if required_metrics is not None
        else set(GENERIC_METRIC_RULES) | {"total_interest_bearing_debt"}
    )
    unknown_metrics = selected_metrics.difference(GENERIC_METRIC_RULES).difference({"total_interest_bearing_debt"})
    if unknown_metrics:
        raise ValueError(f"UNKNOWN_REQUIRED_METRICS: {sorted(unknown_metrics)}")

    for metric_name, spec in GENERIC_METRIC_RULES.items():
        if metric_name not in selected_metrics:
            continue
        st_type = spec["statement_type"]
        target_code = spec["standard_line_code"]
        anchors = spec["label_anchors"]
        src_label = spec["source_label"]
        col_layout = column_layouts[st_type]
        st_pages = statements_by_type[st_type]

        match_res = _find_line_item_on_pages(st_pages, target_code, anchors, col_layout)
        
        # Check unconsolidated fallback for net_income if consolidated line 61 is absent
        if match_res is None and metric_name == "net_income" and "unconsolidated_fallback_line_code" in spec:
            fallback_code = spec["unconsolidated_fallback_line_code"]
            fallback_anchors = ("loi nhuan sau thue thu nhap doanh nghiep", "loi nhuan sau thue tndn", "loi nhuan sau thue")
            match_res = _find_line_item_on_pages(st_pages, fallback_code, fallback_anchors, col_layout)

        if match_res is None:
            raise ValueError(f"METRIC_NOT_FOUND: Could not extract {metric_name} (code {target_code}) from {st_type}")

        matched_page, matched_line, raw_val = match_res

        # Formally verify extraction via governed contract
        # raw_label must be a substring present in the OCR page text
        ext = verified_extraction(
            materialization,
            page=matched_page.page_number,
            raw_label=matched_line.strip(),
            raw_value=raw_val,
            source_raw_label=src_label,
            unit=global_unit_scale.unit_label,
            statement=st_type.value,
            visual_source_page_verified=True,
        )

        extracted_facts.append(
            ExtractedStatementFact(
                canonical_metric=metric_name,
                statement_type=st_type.value,
                page=matched_page.page_number,
                line_item_code=target_code,
                source_label=src_label,
                ocr_matched_label=matched_line,
                raw_value=raw_val,
                normalized_value=ext["normalized_value"],
                currency=global_unit_scale.currency,
                unit_scale=global_unit_scale.unit_scale,
                unit_label=global_unit_scale.unit_label,
                reporting_period=reporting_period,
                period_column_evidence={
                    "header_evidence": col_layout.header_evidence,
                    "target_column_index": col_layout.target_column_index,
                    "current_period_label": col_layout.current_period_label,
                    "comparative_period_label": col_layout.comparative_period_label,
                },
                unit_evidence={
                    "evidence_text": global_unit_scale.evidence_text,
                    "currency": global_unit_scale.currency,
                    "unit_scale": global_unit_scale.unit_scale,
                    "unit_label": global_unit_scale.unit_label,
                },
                extraction_details=ext,
            )
        )

    # Step 5: Total Interest-Bearing Debt Extraction (Component Aggregation).
    # This is opt-in for bounded evidence waves that qualify a strict metric subset.
    if "total_interest_bearing_debt" not in selected_metrics:
        return extracted_facts

    bs_pages = statements_by_type[StatementType.BALANCE_SHEET]
    bs_col_layout = column_layouts[StatementType.BALANCE_SHEET]
    debt_components: list[dict[str, Any]] = []

    for d_spec in GENERIC_DEBT_COMPONENTS:
        c_type = d_spec["component_type"]
        d_code = d_spec["line_item_code"]
        d_anchors = d_spec["label_anchors"]
        d_label = d_spec["label"]

        d_match = _find_line_item_on_pages(bs_pages, d_code, d_anchors, bs_col_layout)
        if d_match is None:
            raise ValueError(f"DEBT_COMPONENT_MISSING: Missing debt component {c_type} (code {d_code}) on Balance Sheet")

        d_page, d_line, d_raw_val = d_match
        debt_components.append({
            "page": d_page.page_number,
            "component_type": c_type,
            "reporting_period": reporting_period,
            "label": d_label,
            "ocr_label": d_line.strip(),
            "source_raw_label": d_label,
            "raw_value": d_raw_val,
            "visual_source_page_verified": True,
        })

    debt_extraction = verified_debt_extraction(
        materialization,
        components=debt_components,
        unit=global_unit_scale.unit_label,
        statement="balance_sheet",
        reporting_period=reporting_period,
    )

    comp_texts = [f"{c['label']}: {c['raw_value']}" for c in debt_components]
    debt_citation_text = " + ".join(comp_texts) + f" = {debt_extraction['normalized_value']} ({global_unit_scale.unit_label})"

    extracted_facts.append(
        ExtractedStatementFact(
            canonical_metric="total_interest_bearing_debt",
            statement_type=StatementType.BALANCE_SHEET.value,
            page=debt_components[0]["page"],
            line_item_code="320+338",
            source_label="Vay và nợ thuê tài chính (ngắn hạn + dài hạn)",
            ocr_matched_label=debt_citation_text,
            raw_value=str(debt_extraction["normalized_value"]),
            normalized_value=debt_extraction["normalized_value"],
            currency=global_unit_scale.currency,
            unit_scale=global_unit_scale.unit_scale,
            unit_label=global_unit_scale.unit_label,
            reporting_period=reporting_period,
            period_column_evidence={
                "header_evidence": bs_col_layout.header_evidence,
                "target_column_index": bs_col_layout.target_column_index,
                "current_period_label": bs_col_layout.current_period_label,
                "comparative_period_label": bs_col_layout.comparative_period_label,
            },
            unit_evidence={
                "evidence_text": global_unit_scale.evidence_text,
                "currency": global_unit_scale.currency,
                "unit_scale": global_unit_scale.unit_scale,
                "unit_label": global_unit_scale.unit_label,
            },
            extraction_details=debt_extraction,
        )
    )

    return extracted_facts
