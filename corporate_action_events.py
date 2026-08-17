"""Typed corporate-action event observations extracted from retained official documents.

WHAT THIS IS
    The extraction layer of pillar B. It turns the retained bytes of one official document
    into zero or more **event observations** -- typed, cited, hash-linked claims about a
    corporate action. An observation is not a ledger entry: it is what one document says.
    Reconciling several documents into one event is `official_corporate_action_ledger.py`.

THE LIFECYCLE IS MODELLED EXPLICITLY, BECAUSE A PLAN IS NOT AN EVENT

        proposed -> approved -> announced -> record_date_confirmed -> executed
                       \\-> amended   \\-> cancelled        (and `unknown`)

    `docs/official_corporate_action_ingestion_design.md` is explicit that a board resolution
    states an intention -- a planned ratio and an authorisation to fix dates later -- and is
    not evidence the event happened. So the document class determines the *highest* lifecycle
    state an observation may assert: an AGM resolution can reach `approved` and no further,
    while a listing-change notice reporting a completed share-count change can reach
    `executed`. No extractor may promote beyond its class's ceiling.

FAIL-CLOSED FIELD EXTRACTION
    Every field is optional and every absent field is recorded as absent with a reason,
    never inferred. In particular, **an ex-date is never derived from a record date, a
    payment date or a listing date**, which `docs/DECISIONS.md` already fixes for price-test
    events ("Record date never substitutes for an explicit official ex-date"). An event whose
    ex-date is absent is still a valid, useful ledger entry -- it simply cannot produce a
    price-adjustment factor, and the ledger says so rather than guessing.

OCR DAMAGE IS DETECTED, NOT ABSORBED
    The retained HPG issuer notice is a scan whose extracted text corrupts several figures:
    the post-change share count reads `8.M2.964.520` and tokenises as `2.964.520`. Numbers
    are therefore accepted only when they parse cleanly under Vietnamese grouping **and**
    survive a plausibility check against the field's expected magnitude; anything else is
    dropped with an `ocr_suspect_numeric` warning. The document still contributes the fields
    it does carry cleanly -- here the pre-change count and the change -- which is what makes
    cross-document corroboration worth doing.

VIETNAMESE CONVENTIONS
    Numbers group with `.` and decimalise with `,` (`767.498.665`, `1.234,5`). Dates appear
    as `dd/mm/yyyy`. Both are parsed here rather than by each caller.
"""

from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser
from typing import Any, Iterable, Mapping, Sequence

VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"

EVENT_TYPES = (
    "cash_dividend",
    "stock_dividend",
    "bonus_shares",
    "rights_issue",
    "stock_split",
    "reverse_split",
    "capital_return",
    "cancellation",
    "amendment",
)

LIFECYCLE_STATES = (
    "proposed",
    "approved",
    "announced",
    "record_date_confirmed",
    "executed",
    "amended",
    "cancelled",
    "unknown",
)

_LIFECYCLE_RANK = {state: index for index, state in enumerate(
    ("unknown", "proposed", "approved", "announced", "record_date_confirmed", "executed"))}

#: The highest lifecycle state each document class may assert on its own. A resolution
#: authorises; only an exchange or depository notice of a completed change evidences execution.
DOCUMENT_CLASS_CEILING = {
    "agm_document_or_resolution": "approved",
    "corporate_governance_report": "approved",
    "annual_report": "announced",
    "corporate_action_notice": "announced",
    "ex_right_notice": "record_date_confirmed",
    "last_registration_date_notice": "record_date_confirmed",
    "listing_change_notice": "executed",
    "amendment_or_supersession_notice": "amended",
    "audited_annual_financial_statements": "announced",
    "reviewed_interim_financial_statements": "announced",
}

#: Plausible bounds for a Vietnamese listed issuer's share count. Used only to reject OCR
#: damage, never to adjust a value.
_MIN_SHARES = 1_000_000
_MAX_SHARES = 100_000_000_000

_NUMBER_RE = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?")
_DATE_RE = re.compile(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ENGLISH_GROUPED_INTEGER_RE = re.compile(r"\d{1,3}(?:,\d{3})+")

#: Field cues, Vietnamese first because that is what the official documents are written in.
_CUES = {
    "shares_before": (
        "trước khi thay đổi", "truoc khi thay doi", "before change", "before the change"),
    "shares_after": (
        "sau khi thay đổi", "sau khi thay doi", "after change", "after the change",
        "sau khi thay đổi niêm yết", "chứng khoán sau khi thay đổi niêm yết"),
    "shares_issued": (
        "số lượng chứng khoán thay đổi niêm yết", "số lượng cổ phiếu phát hành",
        "số lượng chứng khoán thay đổi"),
    "ex_date": ("ngày giao dịch không hưởng quyền", "ex-dividend date", "ex-rights date",
                "ngày gdkhq"),
    "record_date": ("record date:", "ngày đăng ký cuối cùng", "record date", "ngày chốt danh sách"),
    "payment_date": ("ngày thanh toán", "ngày chi trả", "payment date"),
    "listing_effective_date": ("ngày thay đổi niêm yết có hiệu lực",),
    "trading_date": ("ngày giao dịch của chứng khoán thay đổi niêm yết",
                     "trading date official:"),
    "cash_amount": ("số tiền", "đồng/cổ phiếu", "vnd/cổ phiếu", "vnd/share"),
    "subscription_price": ("giá phát hành", "giá chào bán", "subscription price"),
    "approval_date": ("approval date",),
}

#: Event-type cues. Matched against normalised lower-case text.
_TYPE_CUES = (
    ("stock_dividend", ("phát hành cổ phiếu để trả cổ tức", "trả cổ tức bằng cổ phiếu",
                        "cổ phiếu phát hành trả cổ tức", "stock dividend",
                        "issuing shares to pay dividend", "share issuance for dividend payment")),
    ("bonus_shares", ("cổ phiếu thưởng", "phát hành cổ phiếu thưởng", "bonus share")),
    ("rights_issue", ("chào bán cho cổ đông hiện hữu", "quyền mua cổ phiếu", "rights issue")),
    ("stock_split", ("chia tách cổ phiếu", "stock split")),
    ("reverse_split", ("gộp cổ phiếu", "reverse split")),
    ("capital_return", ("hoàn vốn", "capital return")),
    ("cancellation", ("hủy bỏ", "huỷ bỏ", "cancellation of")),
    ("amendment", ("điều chỉnh", "đính chính", "amendment to")),
    ("cash_dividend", ("trả cổ tức bằng tiền", "cổ tức bằng tiền mặt", "cash dividend")),
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def normalize_text(raw: str) -> str:
    """Collapse whitespace so cue matching does not depend on the extractor's line breaks."""
    return re.sub(r"\s+", " ", str(raw)).strip()


def parse_vietnamese_number(token: str) -> float | None:
    """`767.498.665` -> 767498665.0, `1.234,5` -> 1234.5. Returns None on anything ambiguous.

    Grouping must be strictly three digits after the first group; `2.96` and `8.M2.964.520`
    therefore fail rather than silently becoming 296 or 2964520.
    """
    text = str(token).strip()
    if not text:
        return None
    if "," in text:
        whole, _, fraction = text.rpartition(",")
        if not fraction.isdigit():
            return None
    else:
        whole, fraction = text, ""
    if "." in whole:
        head, *rest = whole.split(".")
        if not head.isdigit() or not 1 <= len(head) <= 3:
            return None
        if not all(group.isdigit() and len(group) == 3 for group in rest):
            return None
        whole = head + "".join(rest)
    if not whole.isdigit():
        return None
    return float(f"{whole}.{fraction}") if fraction else float(whole)


def parse_vietnamese_date(text: str) -> str | None:
    """First `dd/mm/yyyy` in `text`, as an ISO date. Returns None when absent or invalid."""
    match = _DATE_RE.search(str(text))
    if match is None:
        return None
    day, month, year = (int(group) for group in match.groups())
    if not (1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2200):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _parse_explicit_share_count(token: str) -> int | None:
    """Parse a directly labelled Vietnamese or English grouped integer, never a decimal."""
    value = str(token).strip()
    if _ENGLISH_GROUPED_INTEGER_RE.fullmatch(value):
        parsed = int(value.replace(",", ""))
    else:
        parsed_float = parse_vietnamese_number(value)
        if parsed_float is None or not parsed_float.is_integer():
            return None
        parsed = int(parsed_float)
    return parsed if _MIN_SHARES <= parsed <= _MAX_SHARES else None


def _window(text: str, cue: str, width: int = 160) -> str | None:
    lowered = text.lower()
    index = lowered.find(cue.lower())
    if index < 0:
        return None
    return text[index: index + width]


def _field_window(text: str, field: str, width: int = 160) -> tuple[str, str] | None:
    for cue in _CUES.get(field, ()):
        window = _window(text, cue, width)
        if window is not None:
            return cue, window
    return None


def _share_count_from(window: str) -> tuple[float | None, str | None]:
    """First plausible share count in a window, or (None, reason)."""
    suspect = False
    for token in _NUMBER_RE.findall(window):
        value = parse_vietnamese_number(token)
        if value is None:
            suspect = True
            continue
        if _MIN_SHARES <= value <= _MAX_SHARES and float(value).is_integer():
            return value, None
        suspect = True
    return None, ("ocr_suspect_numeric" if suspect
                  else "no_plausible_share_count_in_field_window")


#: Row labels of the statutory "change in number of voting shares" disclosure form that carry
#: a share **count**. The form is bilingual and its English labels survive OCR intact even
#: where the Vietnamese does not, so the English is what is matched.
_SHARE_ROW_LABELS = (
    "number of voting shares",
    "total number of shares",
)

#: The form prints its own column order. All three headers must be present, in order, before
#: positional extraction is trusted -- otherwise the columns are not known to be Before /
#: Change / After and no positional reading is made.
_COLUMN_HEADERS = ("before", "change", "after")

_ROW_POSITIONS = ("shares_before", "shares_issued", "shares_after")


def _column_order_confirmed(text: str) -> bool:
    lowered = text.lower()
    positions: list[int] = []
    cursor = 0
    for header in _COLUMN_HEADERS:
        index = lowered.find(f"{header} change" if header != "change" else "change", cursor)
        if index < 0:
            return False
        positions.append(index)
        cursor = index + 1
    return positions == sorted(positions)


def extract_share_change_table(text: str) -> dict[str, Any]:
    """Read the Before / Change / After share counts from the statutory disclosure form.

    Positional column reading is only as trustworthy as the evidence that the columns are in
    the order assumed, so two guards apply before any value is accepted:

    1. the form's own English column headers must appear, in order;
    2. a value is accepted only when **two independent labelled rows** of the table agree on
       it. The form states total shares and voting shares as separate rows, which for an
       issuer with no treasury holding are equal, so agreement across them is a real internal
       cross-check rather than the same number read twice.

    The second guard is what makes this safe on a damaged scan. In the retained HPG notice the
    post-change count extracts as `2.964.520` from `8.M2.964.520` -- a value that parses
    cleanly and lies inside any plausible share range, so no bounds check would catch it. It
    is rejected because the two rows disagree on that position and because the row arithmetic
    `before + change = after` fails.
    """
    lowered_all = text.lower()
    is_form = any(label in lowered_all for label in _SHARE_ROW_LABELS)
    if not _column_order_confirmed(text):
        # A document that *is* the share-change form but whose column order cannot be
        # confirmed is refused outright rather than falling back to cue matching. On the
        # retained HPG scan the fallback reads the charter-capital row -- 76,764,658 thousand
        # VND -- as a share count, because "After Change" is a column header shared by every
        # row of the table and the nearest number after it belongs to whichever row the text
        # extractor happened to emit first.
        return {
            "state": "share_change_form_unreadable" if is_form else "not_a_share_change_table",
            "reason": (("the document is a share-change disclosure form, but its extracted "
                        "text does not preserve the Before / Change / After column order, so "
                        "no share count may be read from it positionally or by cue")
                       if is_form else
                       "the Before / Change / After column headers are not present in order"),
        }

    rows: list[list[float | None]] = []
    matched_labels: list[str] = []
    excerpts: list[str] = []
    lowered = text.lower()
    for label in _SHARE_ROW_LABELS:
        index = lowered.find(label)
        if index < 0:
            continue
        window = text[index: index + 220]
        triple: list[float | None] = []
        for token in _NUMBER_RE.findall(window)[:3]:
            value = parse_vietnamese_number(token)
            triple.append(value if value is not None and _MIN_SHARES <= value <= _MAX_SHARES
                          else None)
        while len(triple) < 3:
            triple.append(None)
        rows.append(triple)
        matched_labels.append(label)
        excerpts.append(window[:180])

    if len(rows) < 2:
        return {"state": "not_a_share_change_table",
                "reason": (f"only {len(rows)} labelled share-count row(s) found; two are "
                           "needed to cross-check a positional reading")}

    values: dict[str, int] = {}
    rejected: dict[str, str] = {}
    citations: dict[str, str] = {}
    warnings: list[str] = []
    for position, field in enumerate(_ROW_POSITIONS):
        candidates = [row[position] for row in rows if row[position] is not None]
        if len(candidates) < 2:
            rejected[field] = ("fewer than two labelled rows yielded a parseable value in "
                               "this column; the value is treated as OCR-damaged")
            warnings.append(f"ocr_suspect_numeric:{field}")
            continue
        if len({round(value, 6) for value in candidates}) > 1:
            rejected[field] = ("labelled rows disagree on this column; the value is treated "
                               "as OCR-damaged")
            warnings.append(f"ocr_row_disagreement:{field}")
            continue
        values[field] = int(candidates[0])
        citations[field] = excerpts[0]

    if len(values) == 3:
        expected = values["shares_before"] + values["shares_issued"]
        if expected != values["shares_after"]:
            for field in ("shares_after",):
                rejected[field] = (f"row arithmetic failed: {values['shares_before']} + "
                                   f"{values['shares_issued']} != {values['shares_after']}")
                values.pop(field, None)
                citations.pop(field, None)
            warnings.append("ocr_row_arithmetic_failed")

    return {"state": "extracted", "values": values, "rejected": rejected,
            "citations": citations, "warnings": warnings,
            "cue": " / ".join(matched_labels), "rows": rows}


def detect_event_type(text: str) -> tuple[str | None, str]:
    lowered = normalize_text(text).lower()
    hits = [event_type for event_type, cues in _TYPE_CUES
            if any(cue in lowered for cue in cues)]
    if ("share issuance for raising share capital from owner's equity" in lowered
            and "bonus_shares" not in hits):
        hits.append("bonus_shares")
    if not hits:
        return None, "no event-type cue found in the document text"
    # `stock_dividend` and `cash_dividend` cues can co-occur in a document that recites both;
    # the more specific share-issuing cue wins, and the ambiguity is reported.
    if len(hits) > 1 and "stock_dividend" in hits:
        return "stock_dividend", f"multiple cues ({', '.join(hits)}); share-issuance cue preferred"
    if len(hits) > 1 and "bonus_shares" in hits:
        return "bonus_shares", f"multiple cues ({', '.join(hits)}); share-issuance cue preferred"
    if len(hits) > 1:
        return hits[0], f"multiple cues ({', '.join(hits)}); first in declaration order used"
    return hits[0], f"document text carries the {hits[0]} cue"


def classify_retained_document(document: Mapping[str, Any], payload: bytes) -> dict[str, Any]:
    """Classify one hash-verified acquired record for the existing event extractor.

    Acquisition manifests retain their discovery-time ``document_class`` unchanged.  This
    returns an in-memory typed extraction record only after re-hashing the retained bytes and
    finding an unambiguous document-internal cue; it never edits a manifest or promotes data.

    Two source families are supported, each gated on its own registry identity, never on a
    ticker: VSDC notices (``source_authority`` is the depository's legal name) and issuer-IR
    listing-change recitals (``source_id == "issuer_ir"``). Any other source is refused.
    """
    expected_sha = str(document.get("content_sha256") or document.get("sha256") or "")
    if not _SHA256_RE.fullmatch(expected_sha):
        raise ValueError("retained_document_hash_missing_or_invalid")
    if hashlib.sha256(payload).hexdigest() != expected_sha:
        raise ValueError("retained_document_hash_mismatch")

    document_id = str(document.get("document_id") or "")
    ticker = str(document.get("ticker") or "").upper()
    source_url = str(document.get("source_url") or document.get("canonical_url") or "")
    authority = str(document.get("source_authority") or "")
    source_id = str(document.get("source_id") or "")
    media_type = str(document.get("media_type") or document.get("content_type") or "")
    if not document_id or not ticker or not source_url.startswith(("http://", "https://")):
        raise ValueError("retained_document_identity_incomplete")

    is_vsdc = authority == "Vietnam Securities Depository and Clearing Corporation"
    is_issuer_ir = source_id == "issuer_ir"
    if not is_vsdc and not is_issuer_ir:
        raise ValueError("document_classification_unsupported_or_ambiguous")

    normalized = extract_text(payload, media_type)
    lowered = normalized.lower()

    declared_type = str(document.get("document_type") or "")
    document_type: str
    basis: str
    cue: str
    if is_vsdc:
        # VSDC's current English template includes the corporate-action-processing qualifier
        # between "record date" and "as follows".  Both forms identify the same directly
        # stated record-date notice; do not require an exact presentation string.
        record_notice_cue = "would like to announce the record date"
        certificate_cue = "would like to announce certification of the"
        adjustment_cue = "adjustment of the number of the registered shares"
        listing_transfer_cue = "shares subject to listing change"
        if (record_notice_cue in lowered and "as follows" in lowered
                and "record date:" in lowered):
            document_type = "last_registration_date_notice"
            basis = "document_internal_vsd_record_date_notice_cues"
            cue = record_notice_cue
        elif (certificate_cue in lowered and adjustment_cue in lowered
              and "has additionally registered securities at vsdc from" in lowered):
            # This is deliberately not a listing-change classification: registration at VSDC
            # and later depository acceptance do not themselves say that listed trading changed.
            document_type = "corporate_action_notice"
            basis = "document_internal_vsd_registered_securities_adjustment_certificate_cues"
            cue = certificate_cue
        elif (listing_transfer_cue in lowered and "trading date official:" in lowered
              and "would like to notify all depository members" in lowered):
            # An official trading date is an announced listing/trading lifecycle date, not
            # proof the trade or the corporate action completed. Keep the acquisition ceiling.
            document_type = "corporate_action_notice"
            basis = "document_internal_vsd_listing_change_transfer_notice_cues"
            cue = listing_transfer_cue
        else:
            raise ValueError("document_classification_unsupported_or_ambiguous")
    else:
        # Issuer-IR sites recite an exchange listing-change notice in a standard three-part
        # disclosure: the recital ("... về việc giao dịch chứng khoán thay đổi niêm yết"), a
        # labelled "Tổ chức niêm yết:" (listed organisation) row, and a labelled
        # "Mã chứng khoán:" (securities code) row. All three are the exchange's own template
        # wording, not any one issuer's -- nothing here names a ticker or a company.
        listing_change_cue = "thay đổi niêm yết"
        organization_label = "tổ chức niêm yết:"
        code_label = "mã chứng khoán:"
        if (listing_change_cue in lowered and organization_label in lowered
                and code_label in lowered):
            document_type = "listing_change_notice"
            basis = "document_internal_issuer_listing_change_recital_cues"
            cue = listing_change_cue
        else:
            raise ValueError("document_classification_unsupported_or_ambiguous")
        # The document's own stated code is the identity check here, not the caller's claim:
        # refuse rather than file a listing-change notice under the wrong ticker.
        code_match = re.search(re.escape(code_label) + r"\s*([a-z0-9]{2,10})", lowered)
        stated_ticker = code_match.group(1).upper() if code_match else None
        if stated_ticker and stated_ticker != ticker:
            raise ValueError("document_ticker_conflicts_with_document_text")
    if declared_type and declared_type != document_type:
        raise ValueError("document_type_conflicts_with_document_text")

    index = lowered.index(cue)
    return {
        "document_id": document_id,
        "ticker": ticker,
        "document_type": document_type,
        "source_authority": authority,
        "source_id": document.get("source_id"),
        "source_url": source_url,
        "content_sha256": expected_sha,
        "published_at": document.get("published_at"),
        "observed_at": document.get("observed_at"),
        "media_type": media_type,
        "discovery_provenance": document.get("discovery_provenance"),
        "document_classification": {
            "state": "classified",
            "document_type": document_type,
            "acquisition_document_class": document.get("document_class"),
            "basis": basis,
            "citation": {"cue": cue, "excerpt": normalized[index:index + 180]},
        },
    }


def extract_explicit_stock_dividend_ratio(text: str) -> dict[str, Any]:
    """Return an entitlement ratio only when two explicit VSDC wordings agree."""
    normalized = normalize_text(text)
    rate_matches = re.findall(r"(?:execution|payment) rate\s*:\s*([0-9.,]+)\s*:\s*([0-9.,]+)",
                              normalized, flags=re.I)
    wording_matches = re.findall(
        r"shareholders (?:are )?entitled to\s*([0-9.,]+)\s+new shares?\s+for every\s*"
        r"([0-9.,]+)\s+shares?",
        normalized, flags=re.I)
    if len(rate_matches) != 1 or len(wording_matches) != 1:
        return {"state": "unavailable", "reason": "execution_rate_missing_or_ambiguous"}
    old, new = (parse_vietnamese_number(value) for value in rate_matches[0])
    wording_new, wording_old = (parse_vietnamese_number(value) for value in wording_matches[0])
    if (None in (old, new, wording_old, wording_new) or not old or not new
            or old != wording_old or new != wording_new):
        return {"state": "unavailable", "reason": "execution_rate_wordings_conflict"}
    return {
        "state": "available",
        "stock_ratio": round(float(new) / float(old), 10),
        "ratio_basis": "new_shares_per_existing_share",
        "citations": [
            {"field": "stock_ratio", "cue": "explicit entitlement rate",
             "excerpt": f"Rate: {rate_matches[0][0]}:{rate_matches[0][1]}"},
            {"field": "stock_ratio", "cue": "explicit entitlement wording",
             "excerpt": (f"Shareholders are entitled to {wording_matches[0][0]} new shares "
                         f"for every {wording_matches[0][1]} shares")},
        ],
    }


#: `_CUES["cash_amount"]`'s slash-only forms ("vnd/cổ phiếu") do not match the retained SSI
#: notice's actual wording, "1,000 VND per share". This accepts either separator.
_CASH_AMOUNT_PER_SHARE_RE = re.compile(
    r"([0-9][0-9.,]*)\s*(?:vnd|đồng)\s*(?:/|per)\s*(?:share|cổ phiếu)", re.I)


def _parse_currency_amount(token: str) -> float | None:
    """A VND amount, English comma-grouped (`1,000`) or Vietnamese dot-grouped (`1.500`).

    Unlike `_parse_explicit_share_count`, no share-count magnitude bound applies here -- a
    per-share cash amount and a share count occupy unrelated, non-comparable ranges.
    """
    text = str(token).strip()
    if _ENGLISH_GROUPED_INTEGER_RE.fullmatch(text):
        return float(text.replace(",", ""))
    value = parse_vietnamese_number(text)
    return value if value is not None and value > 0 else None


def extract_explicit_cash_amount_per_share(text: str) -> dict[str, Any]:
    """A cash amount only from an explicit "<amount> VND per share" / "đồng/cổ phiếu" wording.

    Never derived from a payment-rate percentage: a document stating only "10%/share" with no
    directly stated currency amount reports unavailable rather than compute one from the rate.
    """
    normalized = normalize_text(text)
    matches = list(_CASH_AMOUNT_PER_SHARE_RE.finditer(normalized))
    if len(matches) != 1:
        return {"state": "unavailable",
                "reason": "explicit_cash_amount_per_share_missing_or_ambiguous"}
    match = matches[0]
    value = _parse_currency_amount(match.group(1))
    if value is None:
        return {"state": "unavailable",
                "reason": "explicit_cash_amount_per_share_unparseable"}
    return {
        "state": "available",
        "cash_amount_per_share": value,
        "citation": {"field": "cash_amount_per_share",
                     "cue": "explicit currency-per-share wording",
                     "excerpt": normalized[match.start():match.end()]},
    }


def extract_explicit_dividend_event_reference(text: str) -> dict[str, Any]:
    """Build a cross-document key only from one direct dividend reason and one record date.

    The key does not use issuer, ISIN, arithmetic, chronology, or an inferred ratio. It is
    available solely for wording that explicitly identifies a dividend share issuance from the
    2018 and 2021 remaining profits and names its record date.
    """
    normalized = normalize_text(text)
    reason_matches = re.findall(
        r"(?:share issuance for dividend payment|issuing shares to pay dividends)"
        r".*?remaining profit.*?\b2018\b.*?\b2021\b", normalized, flags=re.I)
    date_matches = re.findall(r"record date\s*:\s*(\d{1,2}[/.]\d{1,2}[/.]\d{4})",
                              normalized, flags=re.I)
    if len(reason_matches) != 1 or len(date_matches) != 1:
        return {"state": "unavailable", "reason": "direct_dividend_event_reference_missing_or_ambiguous"}
    record_date = parse_vietnamese_date(date_matches[0])
    if record_date is None:
        return {"state": "unavailable", "reason": "direct_dividend_event_reference_date_unparseable"}
    return {
        "state": "available",
        "direct_event_reference": (
            f"stock_dividend|record_date={record_date}|remaining_profit_2018_2021"),
        "citation": {"field": "direct_event_reference",
                     "cue": "explicit dividend reason and record date",
                     "excerpt": f"{reason_matches[0]}; Record date: {date_matches[0]}"},
    }


def extract_explicit_registered_securities_adjustment(text: str) -> dict[str, Any]:
    """Read only directly labelled VSDC registered-securities certificate facts.

    These are registration facts, not issued-share, listing, or trading facts.  They therefore
    remain separate from the share-transition fields and cannot create a ratio by arithmetic.
    """
    normalized = normalize_text(text)
    patterns = {
        "registered_securities_added": (
            r"quantity of additionally registered securities\s*:\s*"
            r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,3}(?:\.[0-9]{3})+)",
            "Quantity of additionally registered securities"),
        "registered_securities_total": (
            r"total quantity of registered securities\s*:\s*"
            r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,3}(?:\.[0-9]{3})+)",
            "Total quantity of registered securities"),
        "registration_effective_date": (
            r"has additionally registered securities at vsdc from\s*"
            r"(\d{1,2}[/.]\d{1,2}[/.]\d{4})",
            "Has additionally registered securities at VSDC from"),
        "depository_acceptance_date": (
            r"from\s*(\d{1,2}[/.]\d{1,2}[/.]\d{4})\s*,?\s*"
            r"vsdc will receive depository of (?:the )?above additionally registered securit(?:ies|es)",
            "VSDC will receive depository from"),
        "isin": (r"isin\s*:\s*([A-Z0-9]{6,20})", "ISIN"),
    }
    values: dict[str, Any] = {}
    citations: list[dict[str, str]] = []
    absent: dict[str, str] = {}
    for field, (pattern, label) in patterns.items():
        matches = re.findall(pattern, normalized, flags=re.I)
        if len(matches) != 1:
            absent[field] = "direct_label_missing_or_ambiguous"
            continue
        raw = matches[0]
        if field in {"registered_securities_added", "registered_securities_total"}:
            parsed = _parse_explicit_share_count(raw)
        elif field.endswith("_date"):
            parsed = parse_vietnamese_date(raw)
        else:
            parsed = raw.upper()
        if parsed is None:
            absent[field] = "direct_label_value_unparseable_or_out_of_bounds"
            continue
        values[field] = parsed
        citations.append({"field": field, "cue": label, "excerpt": f"{label}: {raw}"})
    return {"values": values, "citations": citations, "absent": absent}


def assess_direct_event_cross_link(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, str]:
    """Allow a cross-document event link only on the same explicit event reference.

    Dates, counts, ratios, issuer names, and ISINs are deliberately not identity keys: any of
    them may be shared by distinct lifecycle notices.  This helper is pure and returns no
    ledger entry; a future extractor may supply ``direct_event_reference`` only where its own
    retained document states one.
    """
    left_ticker = str(left.get("ticker") or "").upper()
    right_ticker = str(right.get("ticker") or "").upper()
    if not left_ticker or not right_ticker or left_ticker != right_ticker:
        return {"state": "not_linked", "reason": "ticker_missing_or_conflicts"}
    left_reference = str(left.get("direct_event_reference") or "").strip()
    right_reference = str(right.get("direct_event_reference") or "").strip()
    if not left_reference or not right_reference:
        return {"state": "not_linked", "reason": "direct_cross_document_event_identifier_absent"}
    if left_reference != right_reference:
        return {"state": "not_linked", "reason": "direct_cross_document_event_identifier_conflicts"}
    return {"state": "linked", "reason": "matching_direct_cross_document_event_identifier"}


def extract_event_observation(document: Mapping[str, Any], text: str) -> dict[str, Any]:
    """One typed, cited observation from one retained document.

    `document` is an `official_document_store` manifest record; `text` is the extracted plain
    text of the retained bytes. Pure: no I/O, no clock.
    """
    normalized = normalize_text(text)
    document_type = str(document.get("document_type") or "")
    ticker = str(document.get("ticker") or "").upper()

    event_type, type_reason = detect_event_type(normalized)
    ceiling = DOCUMENT_CLASS_CEILING.get(document_type, "unknown")

    fields: dict[str, Any] = {}
    citations: list[dict[str, Any]] = []
    warnings: list[str] = []
    absent: dict[str, str] = {}

    table = extract_share_change_table(normalized)
    if table["state"] == "extracted":
        for field, value in table["values"].items():
            fields[field] = value
            citations.append({"field": field, "cue": table["cue"],
                              "excerpt": table["citations"][field]})
        for field, reason in table["rejected"].items():
            absent[field] = reason
        warnings.extend(table["warnings"])
    elif table["state"] == "share_change_form_unreadable":
        for field in ("shares_before", "shares_after", "shares_issued"):
            absent[field] = table["reason"]
        warnings.append("share_change_form_numeric_extraction_refused")
    else:
        for field in ("shares_before", "shares_after", "shares_issued"):
            found = _field_window(normalized, field)
            if found is None:
                absent[field] = table.get("reason") or "no field cue present in the document"
                continue
            cue, window = found
            value, reason = _share_count_from(window)
            if value is None:
                absent[field] = reason or "unparseable"
                if reason == "ocr_suspect_numeric":
                    warnings.append(f"ocr_suspect_numeric:{field}")
                continue
            fields[field] = int(value)
            citations.append({"field": field, "cue": cue, "excerpt": window[:180]})

    registered_adjustment = extract_explicit_registered_securities_adjustment(normalized)
    fields.update(registered_adjustment["values"])
    citations.extend(registered_adjustment["citations"])
    absent.update(registered_adjustment["absent"])

    for field in ("approval_date", "ex_date", "record_date", "payment_date", "listing_effective_date",
                  "trading_date"):
        found = _field_window(normalized, field)
        if found is None:
            absent[field] = "no field cue present in the document"
            continue
        cue, window = found
        parsed = parse_vietnamese_date(window)
        if parsed is None:
            absent[field] = "field cue present but no parseable dd/mm/yyyy date follows it"
            continue
        fields[field] = parsed
        citations.append({"field": field, "cue": cue, "excerpt": window[:180]})

    direct_reference = extract_explicit_dividend_event_reference(normalized)
    if direct_reference["state"] == "available":
        fields["direct_event_reference"] = direct_reference["direct_event_reference"]
        citations.append(direct_reference["citation"])
    else:
        absent["direct_event_reference"] = direct_reference["reason"]

    # Share-count arithmetic has priority. Otherwise an entitlement ratio needs two matching,
    # explicit wordings; no date can open or orient the ratio.
    stock_ratio = None
    ratio_basis = None
    if "shares_issued" in fields and "shares_before" in fields and fields["shares_before"]:
        stock_ratio = round(fields["shares_issued"] / fields["shares_before"], 10)
        ratio_basis = "new_shares_per_existing_share"
        citations.append({"field": "stock_ratio", "cue": "derived",
                          "excerpt": (f"{fields['shares_issued']} / {fields['shares_before']} "
                                      f"= {stock_ratio}")})
    elif "shares_issued" in fields and "shares_after" in fields:
        before = fields["shares_after"] - fields["shares_issued"]
        if before > 0:
            stock_ratio = round(fields["shares_issued"] / before, 10)
            ratio_basis = "new_shares_per_existing_share"
            citations.append({"field": "stock_ratio", "cue": "derived",
                          "excerpt": (f"{fields['shares_issued']} / "
                                      f"({fields['shares_after']} - "
                                      f"{fields['shares_issued']}) = {stock_ratio}")})
    else:
        explicit_ratio = extract_explicit_stock_dividend_ratio(normalized)
        if explicit_ratio["state"] == "available":
            stock_ratio = explicit_ratio["stock_ratio"]
            ratio_basis = explicit_ratio["ratio_basis"]
            citations.extend(explicit_ratio["citations"])
        else:
            absent["stock_ratio"] = explicit_ratio["reason"]

    if "ex_date" not in fields:
        warnings.append("ex_date_absent")
        # Overwrites the generic "cue not found" note deliberately: the reason an ex-date is
        # absent matters less than the rule that nothing else may stand in for it.
        absent["ex_date"] = ("no explicit official ex-date in this document; a record, "
                             "payment, listing or trading date is never substituted for one")

    lifecycle = _lifecycle_for(document_type, fields, ceiling)

    identity = {
        "schema_version": SCHEMA_VERSION,
        "ticker": ticker,
        "event_type": event_type,
        "document_id": document.get("document_id"),
        "content_sha256": document.get("content_sha256"),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "extractor_version": VERSION,
        "observation_id": _fingerprint({**identity, "fields": fields}),
        "ticker": ticker,
        "event_type": event_type,
        "event_type_reason": type_reason,
        "lifecycle_state": lifecycle["state"],
        "lifecycle_reason": lifecycle["reason"],
        "lifecycle_ceiling": ceiling,
        "document_id": document.get("document_id"),
        "document_type": document_type,
        "source_authority": document.get("source_authority"),
        "source_id": document.get("source_id"),
        "source_url": document.get("source_url"),
        "content_sha256": document.get("content_sha256"),
        "discovery_provenance": document.get("discovery_provenance"),
        "document_classification": document.get("document_classification"),
        "published_at": document.get("published_at"),
        "observed_at": document.get("observed_at"),
        "approval_date": fields.get("approval_date"),
        "announcement_date": document.get("published_at"),
        "ex_date": fields.get("ex_date"),
        "record_date": fields.get("record_date"),
        "payment_date": fields.get("payment_date"),
        "listing_effective_date": fields.get("listing_effective_date"),
        "payment_or_execution_date": (fields.get("payment_date")
                                      or fields.get("listing_effective_date")),
        "trading_date": fields.get("trading_date"),
        "direct_event_reference": fields.get("direct_event_reference"),
        "registration_effective_date": fields.get("registration_effective_date"),
        "depository_acceptance_date": fields.get("depository_acceptance_date"),
        "shares_before": fields.get("shares_before"),
        "shares_issued": fields.get("shares_issued"),
        "shares_after": fields.get("shares_after"),
        "registered_securities_added": fields.get("registered_securities_added"),
        "registered_securities_total": fields.get("registered_securities_total"),
        "isin": fields.get("isin"),
        "cash_amount_per_share": fields.get("cash_amount"),
        "stock_ratio": stock_ratio,
        "ratio_basis": ratio_basis,
        "rights_ratio": None,
        "subscription_price": fields.get("subscription_price"),
        "citations": sorted(citations, key=lambda item: str(item["field"])),
        "absent_fields": dict(sorted(absent.items())),
        "warnings": sorted(set(warnings)),
    }


def _lifecycle_for(document_type: str, fields: Mapping[str, Any],
                   ceiling: str) -> dict[str, str]:
    """The lifecycle state this document evidences, capped by its class ceiling."""
    if fields.get("shares_after") or fields.get("listing_effective_date"):
        observed = "executed"
        reason = ("the document reports a completed change in listed or voting share count")
    elif fields.get("record_date"):
        observed = "record_date_confirmed"
        reason = "the document states a confirmed record date"
    elif fields.get("ex_date"):
        observed = "announced"
        reason = "the document states an ex-date but no completed execution"
    else:
        observed = "announced" if document_type.endswith("notice") else "proposed"
        reason = "no execution or entitlement date is stated; the document announces only"

    if _LIFECYCLE_RANK.get(observed, 0) > _LIFECYCLE_RANK.get(ceiling, 0):
        return {"state": ceiling,
                "reason": (f"{reason}, but a {document_type} may not assert beyond "
                           f"{ceiling!r}")}
    return {"state": observed, "reason": reason}


# ==========================================================================
# Multi-event extraction: one retained document, zero or more independent facets.
#
# `extract_event_observation` above returns exactly one observation and stays untouched --
# every existing caller keeps its exact current behaviour. The retained SSI VSDC record-date
# notice is the reason this exists: it states two independent facets, a cash dividend and a
# bonus share issuance, under one shared record date, and the single-event model above can only
# ever report the one its type-cue preference order picks (`detect_event_type`'s own comment
# calls this out: "the more specific share-issuing cue wins, and the ambiguity is reported").
#
# `extract_event_observations` (plural) is the additive entry point: it detects how many
# distinct event-type facets a document actually recites and, for two or more, extracts one
# observation per facet instead of one for the whole document. A document with zero or one
# facet is unaffected -- this delegates to `extract_event_observation` for that case, so it is
# not a second, competing implementation of the single-event path.
# ==========================================================================

#: Must name the same phrase `detect_event_type` treats as an implicit `bonus_shares` cue.
#: Kept as its own literal, rather than a shared constant, so this module's one single-event
#: function stays completely unedited by this addition.
_BONUS_SHARES_IMPLICIT_PHRASE = "share issuance for raising share capital from owner's equity"

#: The date-type fields a facet may either inherit from a shared document preamble or restate
#: itself. Order matches the inline loop in `extract_event_observation`.
_DATE_FIELDS = ("approval_date", "ex_date", "record_date", "payment_date",
                "listing_effective_date", "trading_date")


def detect_event_facets(text: str) -> list[dict[str, Any]]:
    """Every distinct event-type facet a document recites, each anchored to its own section.

    A compound official notice -- the retained SSI VSDC record-date notice among them -- states
    each facet twice: once in a shared "Reason:" summary and again as its own detailed section.
    The **last** occurrence of a type's cue is used as that facet's anchor, because the first is
    a preamble mention shared by every facet, not evidence belonging to one of them.

    Facets are returned in document order. The span from one facet's anchor to the next (or to
    the end of the document) is that facet's own scope; text before the first anchor belongs to
    no single facet and is the shared preamble (see `extract_event_observations`).

    A document with zero or one facet returns a list of that length -- callers use the length to
    decide whether multi-event handling applies at all.
    """
    normalized = normalize_text(text)
    lowered = normalized.lower()
    anchors: dict[str, tuple[int, str]] = {}
    for event_type, cues in _TYPE_CUES:
        for cue in cues:
            position = lowered.rfind(cue)
            if position < 0:
                continue
            best = anchors.get(event_type)
            if best is None or position > best[0]:
                anchors[event_type] = (position, cue)
    position = lowered.rfind(_BONUS_SHARES_IMPLICIT_PHRASE)
    if position >= 0:
        best = anchors.get("bonus_shares")
        if best is None or position > best[0]:
            anchors["bonus_shares"] = (position, _BONUS_SHARES_IMPLICIT_PHRASE)

    ordered = sorted((position, event_type, cue) for event_type, (position, cue) in anchors.items())
    facets: list[dict[str, Any]] = []
    for index, (position, event_type, cue) in enumerate(ordered):
        end = ordered[index + 1][0] if index + 1 < len(ordered) else len(normalized)
        facets.append({"event_type": event_type, "cue": cue,
                       "span_start": position, "span_end": end,
                       "span_text": normalized[position:end]})
    return facets


def _extract_date_fields(text: str) -> tuple[dict[str, str], dict[str, dict[str, str]], dict[str, str]]:
    """The same labelled-date extraction `extract_event_observation` performs inline (fields,
    citations by field, absence reasons by field), factored out so `extract_event_observations`
    can run it once over a shared preamble and again over each facet's own span."""
    fields: dict[str, str] = {}
    citations: dict[str, dict[str, str]] = {}
    absent: dict[str, str] = {}
    for field in _DATE_FIELDS:
        found = _field_window(text, field)
        if found is None:
            absent[field] = "no field cue present in the document"
            continue
        cue, window = found
        parsed = parse_vietnamese_date(window)
        if parsed is None:
            absent[field] = "field cue present but no parseable dd/mm/yyyy date follows it"
            continue
        fields[field] = parsed
        citations[field] = {"field": field, "cue": cue, "excerpt": window[:180]}
    return fields, citations, absent


def _extract_facet_specific_fields(
        span_text: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[str], dict[str, str]]:
    """Share-count, registered-adjustment, direct-reference, and cash-amount fields scoped to
    one facet's own text span -- everything `extract_event_observation` extracts inline other
    than the date fields, which `_extract_date_fields` handles separately because those may also
    be inherited from a shared document preamble (see `extract_event_observations`)."""
    fields: dict[str, Any] = {}
    citations: list[dict[str, Any]] = []
    warnings: list[str] = []
    absent: dict[str, str] = {}

    table = extract_share_change_table(span_text)
    if table["state"] == "extracted":
        for field, value in table["values"].items():
            fields[field] = value
            citations.append({"field": field, "cue": table["cue"],
                              "excerpt": table["citations"][field]})
        for field, reason in table["rejected"].items():
            absent[field] = reason
        warnings.extend(table["warnings"])
    elif table["state"] == "share_change_form_unreadable":
        for field in ("shares_before", "shares_after", "shares_issued"):
            absent[field] = table["reason"]
        warnings.append("share_change_form_numeric_extraction_refused")
    else:
        for field in ("shares_before", "shares_after", "shares_issued"):
            found = _field_window(span_text, field)
            if found is None:
                absent[field] = table.get("reason") or "no field cue present in the document"
                continue
            cue, window = found
            value, reason = _share_count_from(window)
            if value is None:
                absent[field] = reason or "unparseable"
                if reason == "ocr_suspect_numeric":
                    warnings.append(f"ocr_suspect_numeric:{field}")
                continue
            fields[field] = int(value)
            citations.append({"field": field, "cue": cue, "excerpt": window[:180]})

    registered_adjustment = extract_explicit_registered_securities_adjustment(span_text)
    fields.update(registered_adjustment["values"])
    citations.extend(registered_adjustment["citations"])
    absent.update(registered_adjustment["absent"])

    direct_reference = extract_explicit_dividend_event_reference(span_text)
    if direct_reference["state"] == "available":
        fields["direct_event_reference"] = direct_reference["direct_event_reference"]
        citations.append(direct_reference["citation"])
    else:
        absent["direct_event_reference"] = direct_reference["reason"]

    cash_amount = extract_explicit_cash_amount_per_share(span_text)
    if cash_amount["state"] == "available":
        fields["cash_amount"] = cash_amount["cash_amount_per_share"]
        citations.append(cash_amount["citation"])
    else:
        absent["cash_amount"] = cash_amount["reason"]

    return fields, citations, warnings, absent


def extract_event_observations(document: Mapping[str, Any], text: str) -> list[dict[str, Any]]:
    """One typed, cited observation per independent event-type facet in one retained document.

    Almost every retained document states one corporate action and is handled unchanged by
    `extract_event_observation`, which this wraps and returns as a single-item list for. A
    minority -- the retained SSI VSDC notice among them -- recite two or more independent facets
    (a cash dividend and a bonus share issuance) under one shared record date. That is the only
    case this function changes: splitting a compound document into its own typed observations,
    one per facet, each with its own event type and its own facet-scoped fields, plus the
    document's shared provenance (ticker, document/content hash, source, classification) and any
    shared preamble facts -- such as a record date stated once for the whole notice -- carried
    onto every facet. A facet that restates its own value for one of those shared fields speaks
    for itself; the shared preamble value is only a fallback.

    Fields never cross between facets in the other direction: share counts, entitlement ratios,
    and cash amounts are read only from each facet's own text span, never from the document as a
    whole or from another facet's span.

    Nothing here changes what `extract_event_observation` returns for a document with zero or
    one facet -- this function delegates to it entirely in that case, so every existing caller
    and every existing single-event document keeps its exact current behaviour.
    """
    normalized = normalize_text(text)
    facets = detect_event_facets(normalized)
    if len(facets) < 2:
        return [extract_event_observation(document, text)]

    ticker = str(document.get("ticker") or "").upper()
    document_type = str(document.get("document_type") or "")
    ceiling = DOCUMENT_CLASS_CEILING.get(document_type, "unknown")

    preamble = normalized[:facets[0]["span_start"]]
    shared_fields, shared_citations, shared_absent = _extract_date_fields(preamble)

    observations: list[dict[str, Any]] = []
    for index, facet in enumerate(facets):
        facet_fields, facet_citations, facet_warnings, facet_absent = \
            _extract_facet_specific_fields(facet["span_text"])
        facet_dates, facet_date_citations, facet_date_absent = \
            _extract_date_fields(facet["span_text"])

        fields: dict[str, Any] = {**shared_fields, **facet_dates, **facet_fields}
        citations_by_field: dict[str, dict[str, Any]] = {**shared_citations, **facet_date_citations}
        for citation in facet_citations:
            citations_by_field[str(citation["field"])] = citation
        absent: dict[str, str] = {**shared_absent, **facet_date_absent, **facet_absent}
        for field in fields:
            absent.pop(field, None)

        warnings = list(facet_warnings)
        if "ex_date" not in fields:
            warnings.append("ex_date_absent")
            absent["ex_date"] = ("no explicit official ex-date in this document; a record, "
                                 "payment, listing or trading date is never substituted for one")

        stock_ratio = None
        ratio_basis = None
        if "shares_issued" in fields and "shares_before" in fields and fields["shares_before"]:
            stock_ratio = round(fields["shares_issued"] / fields["shares_before"], 10)
            ratio_basis = "new_shares_per_existing_share"
            citations_by_field["stock_ratio"] = {
                "field": "stock_ratio", "cue": "derived",
                "excerpt": (f"{fields['shares_issued']} / {fields['shares_before']} "
                            f"= {stock_ratio}")}
        elif "shares_issued" in fields and "shares_after" in fields:
            before = fields["shares_after"] - fields["shares_issued"]
            if before > 0:
                stock_ratio = round(fields["shares_issued"] / before, 10)
                ratio_basis = "new_shares_per_existing_share"
                citations_by_field["stock_ratio"] = {
                    "field": "stock_ratio", "cue": "derived",
                    "excerpt": (f"{fields['shares_issued']} / "
                                f"({fields['shares_after']} - {fields['shares_issued']}) "
                                f"= {stock_ratio}")}
        else:
            explicit_ratio = extract_explicit_stock_dividend_ratio(facet["span_text"])
            if explicit_ratio["state"] == "available":
                stock_ratio = explicit_ratio["stock_ratio"]
                ratio_basis = explicit_ratio["ratio_basis"]
                for citation in explicit_ratio["citations"]:
                    citations_by_field[str(citation["field"])] = citation
            else:
                absent["stock_ratio"] = explicit_ratio["reason"]

        lifecycle = _lifecycle_for(document_type, fields, ceiling)
        event_type = facet["event_type"]
        identity = {
            "schema_version": SCHEMA_VERSION,
            "ticker": ticker,
            "event_type": event_type,
            "document_id": document.get("document_id"),
            "content_sha256": document.get("content_sha256"),
        }
        observations.append({
            "schema_version": SCHEMA_VERSION,
            "extractor_version": VERSION,
            "observation_id": _fingerprint({**identity, "fields": fields}),
            "ticker": ticker,
            "event_type": event_type,
            "event_type_reason": (f"document text carries the {event_type} cue in its own "
                                  f"section; {len(facets)} independent event-type facets "
                                  "detected in this document"),
            "lifecycle_state": lifecycle["state"],
            "lifecycle_reason": lifecycle["reason"],
            "lifecycle_ceiling": ceiling,
            "document_id": document.get("document_id"),
            "document_type": document_type,
            "source_authority": document.get("source_authority"),
            "source_id": document.get("source_id"),
            "source_url": document.get("source_url"),
            "content_sha256": document.get("content_sha256"),
            "discovery_provenance": document.get("discovery_provenance"),
            "document_classification": document.get("document_classification"),
            "published_at": document.get("published_at"),
            "observed_at": document.get("observed_at"),
            "approval_date": fields.get("approval_date"),
            "announcement_date": document.get("published_at"),
            "ex_date": fields.get("ex_date"),
            "record_date": fields.get("record_date"),
            "payment_date": fields.get("payment_date"),
            "listing_effective_date": fields.get("listing_effective_date"),
            "payment_or_execution_date": (fields.get("payment_date")
                                          or fields.get("listing_effective_date")),
            "trading_date": fields.get("trading_date"),
            "direct_event_reference": fields.get("direct_event_reference"),
            "registration_effective_date": fields.get("registration_effective_date"),
            "depository_acceptance_date": fields.get("depository_acceptance_date"),
            "shares_before": fields.get("shares_before"),
            "shares_issued": fields.get("shares_issued"),
            "shares_after": fields.get("shares_after"),
            "registered_securities_added": fields.get("registered_securities_added"),
            "registered_securities_total": fields.get("registered_securities_total"),
            "isin": fields.get("isin"),
            "cash_amount_per_share": fields.get("cash_amount"),
            "stock_ratio": stock_ratio,
            "ratio_basis": ratio_basis,
            "rights_ratio": None,
            "subscription_price": fields.get("subscription_price"),
            "citations": sorted(citations_by_field.values(), key=lambda item: str(item["field"])),
            "absent_fields": dict(sorted(absent.items())),
            "warnings": sorted(set(warnings)),
            "facet_index": index,
            "facet_count": len(facets),
        })
    return observations


class _VsdNoticeBody(HTMLParser):
    """Capture a VSDC notice body without its navigation or related-news sidebar."""
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.text: list[str] = []
        self._open_tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = dict(attrs).get("class", "") or ""
        if self.depth:
            if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}:
                self.depth += 1
                self._open_tags.append(tag)
        elif tag == "div" and "content-category" in classes.split():
            self.depth = 1
            self._open_tags.append(tag)

    def handle_startendtag(self, _tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        """A self-closing HTML tag does not close the scoped notice body."""

    def handle_endtag(self, tag: str) -> None:
        if self.depth and self._open_tags and self._open_tags[-1] == tag:
            self._open_tags.pop()
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.text.append(data)


def _html_notice_text(raw_html: str) -> str:
    """Prefer a page's named VSDC content body; otherwise retain generic HTML behaviour."""
    parser = _VsdNoticeBody()
    parser.feed(raw_html)
    scoped = normalize_text(" ".join(parser.text))
    if scoped:
        return scoped
    stripped = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw_html, flags=re.S | re.I)
    return normalize_text(re.sub(r"<[^>]+>", " ", stripped))


def extract_text(payload: bytes, media_type: str) -> str:
    """Plain text from retained bytes. HTML is stripped; PDF goes through pypdf."""
    if media_type == "text/html":
        text = payload.decode("utf-8", errors="replace")
        import html as html_module

        return _html_notice_text(html_module.unescape(text))
    if media_type == "application/pdf":
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(payload))
        return normalize_text("\n".join((page.extract_text() or "") for page in reader.pages))
    raise ValueError(f"unsupported media type for extraction: {media_type!r}")
