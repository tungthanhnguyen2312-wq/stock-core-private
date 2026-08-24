"""Read candidate disclosures out of one stored HNX issuer-disclosure RSS feed, and read
structured fields out of one stored HNX disclosure detail page.

WHAT THIS IS
    The HNX sibling of `official_listing_page_parser.py`: a pure function of (bytes, url,
    registry) that turns bytes already retained through the governed acquisition path into the
    *input* `official_document_discovery`-shaped candidates a human would otherwise type by
    hand. It performs no I/O of any kind -- no network, no filesystem, no subprocess -- and
    follows no pagination. Discovery, and then the registry gate at `acquire()`, still decide
    what may actually be requested; this module widens nothing.

WHY TWO PARSERS, NOT ONE
    HNX's RSS titles carry no issuer-code prefix (unlike VSDC's `CODE: subject`), so the ticker
    for an item is not knowable from the feed alone -- only after the linked detail page is
    fetched and its own `Mã chứng khoán:` field is read. `parse_disclosure_rss` therefore only
    orders and coarsely classifies candidates for acquisition; `parse_disclosure_detail` is the
    one place ticker identity and every other structured fact is read, and it is read only from
    the retained detail page's own text, never inferred from the feed.

HOW A DETAIL PAGE'S FACTS ARE READ
    Every field observed on a retained HNX disclosure page lives in one
    `<div class="Box-Noidung">` block as a flat, `<br/>`-separated list of
    `- <Vietnamese label>: <value>` lines -- confirmed on three independently retained pages
    (an insider registration, a related-person execution result, and a major-shareholder-exit
    notice). A related-person notice can repeat the `Tên của người có liên quan tại TCNY` label
    once per named related person; each repeat starts a new sub-record, and the position/holding
    lines that follow belong to that person until the next repeat or the end of the block. A
    label this table does not recognise is never dropped: it is retained verbatim under
    `unparsed_fields`, so an unrecognised disclosure shape is visible rather than silently
    incomplete.
"""

from __future__ import annotations

import hashlib
import html
import re
import urllib.parse
from typing import Any, Mapping

from corporate_action_events import normalize_text, parse_vietnamese_date, parse_vietnamese_number
from official_source_registry import canonical_host, evidence_document_types, source_index

VERSION = "1.0.0"

SAFE_SCHEMES = frozenset({"http", "https"})
UNSTABLE_QUERY_KEYS = frozenset({"session", "sid", "token", "signature", "expires",
                                 "login", "returnurl", "jsessionid", "phpsessid"})

_ITEM = re.compile(r"<item>(.*?)</item>", re.IGNORECASE | re.DOTALL)
_TAGGED = re.compile(r"<(\w+)[^>]*>(.*?)</\1>", re.DOTALL)
_GUID = re.compile(r"<guid[^>]*>(.*?)</guid>", re.IGNORECASE | re.DOTALL)

#: Title cues this pilot acquires. Anything else observed on the feed (AGM documents, charter
#: amendments, foreign-ownership-ratio notices, personnel changes, ...) is real disclosure but
#: is not one of the two fact families this milestone builds a typed extractor for; it is
#: recorded in the parse ledger as `out_of_pilot_scope` rather than mislabelled into one of the
#: two registry types that *are* declared, so `admit()` is never asked to gate a guess.
_INSIDER_CUES = ("đăng ký mua", "đăng ký bán", "đã mua", "đã bán", "người nội bộ",
                 "người có liên quan", "kết quả giao dịch cổ phiếu", "thực hiện quyền mua")
_MAJOR_HOLDER_CUES = ("cổ đông lớn",)

INSIDER_TYPE = "insider_transaction_notice"
MAJOR_HOLDER_TYPE = "major_shareholder_notice"
OUT_OF_SCOPE = "out_of_pilot_scope"

_NOIDUNG = re.compile(r'<div class="Box-Noidung">(.*?)</div>\s*<div class="divLstFileAttach"',
                      re.IGNORECASE | re.DOTALL)
_TIEUDE = re.compile(r'<div class="Box-TieuDe"><label>(.*?)</label></div>', re.IGNORECASE | re.DOTALL)
_THOIGIAN = re.compile(r'<div class="Box-Thoigian">\s*<label>(.*?)</label>', re.IGNORECASE | re.DOTALL)
_ATTACH_HREF = re.compile(r'href="([^"]+)"', re.IGNORECASE)
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_BULLET = re.compile(r"^-\s*(.+?)\s*:\s*(.*)$", re.DOTALL)
_SHARE_AND_RATIO = re.compile(r"([\d.,]+)\s*CP(?:\s*\(t[yỷ]\s*l[eệ]\s*([\d.,]+)\s*%\))?", re.IGNORECASE)

#: Direct page-fact label -> canonical field name. Exact match only, on the label text left of
#: the colon; a label outside this table is retained, never guessed into the nearest entry.
_FIELD_LABELS: dict[str, str] = {
    "Tên cá nhân thực hiện giao dịch": "actor_individual_name",
    "Tên tổ chức thực hiện giao dịch": "actor_entity_name",
    "Chức vụ hiện nay tại TCNY": "actor_position_at_issuer",
    "Mã chứng khoán": "ticker",
    "Số lượng cổ phiếu nắm giữ trước khi thực hiện giao dịch": "shares_held_before_raw",
    "Số lượng cổ phiếu đăng ký mua": "registered_buy_volume_raw",
    "Số lượng cổ phiếu đăng ký bán": "registered_sell_volume_raw",
    "Số lượng cổ phiếu đã mua": "executed_buy_volume_raw",
    "Số lượng cổ phiếu đã bán": "executed_sell_volume_raw",
    "Số lượng cổ phiếu nắm giữ sau khi thực hiện giao dịch": "shares_held_after_raw",
    "Mục đích thực hiện giao dịch": "purpose",
    "Phương thức giao dịch": "method",
    "Ngày dự kiến bắt đầu giao dịch": "registration_start_date_raw",
    "Ngày dự kiến kết thúc giao dịch": "registration_end_date_raw",
    "Ngày bắt đầu giao dịch": "execution_window_start_date_raw",
    "Ngày kết thúc giao dịch": "execution_window_end_date_raw",
    "Lý do không thực hiện giao dịch hết số cổ phiếu đăng ký": "non_execution_reason",
    "Ngày không còn là cổ đông lớn": "ceased_major_holder_date_raw",
    "Ngày trở thành cổ đông lớn": "became_major_holder_date_raw",
    # HNX's own registration-notice template spells this label without the "dịch" diacritic
    # (observed 2026-08-24 on live IDV/VNF/VNT registration-by-entity notices: "...giao dich",
    # not "...giao dịch"), while its execution-result template spells the same label correctly.
    # This is the source page's own inconsistency, not a guess -- both spellings are retained
    # as the one canonical field rather than letting the typo'd variant fall to unparsed_fields.
    "Tên tổ chức thực hiện giao dich": "actor_entity_name",
    "Tên cá nhân thực hiện giao dich": "actor_individual_name",
    "Quan hệ của cá nhân thực hiện giao dịch với NCLQ": "actor_relationship_to_related_person",
}
#: Starts a new related-person sub-record; the three labels below it belong to that person.
_RELATED_PERSON_START = "Tên của người có liên quan tại TCNY"
_RELATED_PERSON_LABELS: dict[str, str] = {
    _RELATED_PERSON_START: "name",
    "Chức vụ hiện nay của NCLQ tại tổ chức niêm yết": "position_at_issuer",
    "Chức vụ hiện nay của NCLQ tại tổ chức thực hiện giao dịch": "position_at_actor",
    "Số lượng cổ phiếu NCLQ đang nắm giữ": "shares_held_raw",
}
#: At least one retained page (VNH, 2026-08-24) omits the `<br/>` between two bullets
#: ("...Đỗ Đức Cường- Mã chứng khoán: VNH"), so `<br/>` alone is not a reliable bullet
#: boundary. Splitting on a lookahead for one of the exact known labels recovers the two
#: bullets without guessing at an unrecognised "- text:" shape -- a value that happens to
#: contain " - word:" never triggers a split, only these exact page-vocabulary strings do.
_ALL_LABELS = sorted({*_FIELD_LABELS, *_RELATED_PERSON_LABELS}, key=len, reverse=True)
_GLUED_BULLET_SPLIT = re.compile(
    r"(?=-\s*(?:" + "|".join(re.escape(label) for label in _ALL_LABELS) + r")\s*:)")


def normalize_candidate_url(raw: str, base_url: str) -> str | None:
    """Resolve, validate and canonicalise one href. Shares `official_listing_page_parser`'s rules."""
    candidate = (raw or "").strip()
    if not candidate:
        return None
    scheme = candidate.split(":", 1)[0].lower() if ":" in candidate.split("/", 1)[0] else ""
    if scheme and scheme not in SAFE_SCHEMES:
        return None
    try:
        resolved = urllib.parse.urlsplit(urllib.parse.urljoin(base_url, candidate))
    except ValueError:
        return None
    if resolved.scheme.lower() not in SAFE_SCHEMES or not resolved.netloc:
        return None
    if "@" in resolved.netloc:
        return None
    try:
        query = urllib.parse.parse_qsl(resolved.query, keep_blank_values=True)
    except ValueError:
        return None
    if any(key.lower() in UNSTABLE_QUERY_KEYS for key, _ in query):
        return None
    # The retained feed's own <link> leaks an internal backend host:port (http://www.hnx.vn:7978/...).
    # The canonical public host has no port and serves the identical path over https (verified
    # 2026-08-24: https://www.hnx.vn/<path> 302-redirects to a real page, never a 404, and the
    # host answers with `Strict-Transport-Security`, i.e. it declares https as authoritative for
    # itself). Stripping the leaked port and forcing https is a same-authority canonicalisation,
    # not a host substitution: the path and the host name are both taken verbatim from the feed's
    # own bytes, only the scheme/port the backend leaked is corrected to what the host itself
    # publishes as canonical.
    netloc = resolved.netloc.lower().split(":", 1)[0]
    return urllib.parse.urlunsplit((
        "https", netloc, resolved.path or "/",
        urllib.parse.urlencode(sorted(query)), ""))


def classify_hnx_disclosure(title: str) -> tuple[str | None, str | None]:
    """Coarse registry-level type from the RSS/detail title, or (None, None) if out of pilot scope."""
    lowered = title.lower()
    for cue in _MAJOR_HOLDER_CUES:
        if cue in lowered:
            return MAJOR_HOLDER_TYPE, cue
    for cue in _INSIDER_CUES:
        if cue in lowered:
            return INSIDER_TYPE, cue
    return None, None


def parse_disclosure_rss(payload: bytes, *, feed_url: str, source_id: str,
                         registry: Mapping[str, Any], encoding: str = "utf-8") -> dict[str, Any]:
    """Turn stored RSS bytes into a ledger of candidate detail-page acquisitions.

    `payload` is bytes already retained by `acquire()` against the `disclosure_rss_feed` index
    type. Nothing here reads a file or a socket. Every `<item>` becomes one row; rows whose
    title matches neither fact family this pilot extracts are kept with `document_class=None`
    so the ledger accounts for every item the feed carried, not only the ones acquired.
    """
    source = source_index(registry).get(str(source_id))
    if source is None:
        raise ValueError("unknown_source_id")
    allowed_hosts = {str(host).lower() for host in source.get("allowed_hosts") or []}
    evidence_types = evidence_document_types(source)
    base = normalize_candidate_url(feed_url, feed_url)
    if base is None:
        raise ValueError("unusable_feed_url")

    document = payload.decode(encoding, errors="replace")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _ITEM.finditer(document):
        body = item.group(1)
        fields = {tag.lower(): html.unescape(inner).strip()
                  for tag, inner in _TAGGED.findall(body)}
        guid_match = _GUID.search(body)
        guid = html.unescape(guid_match.group(1)).strip() if guid_match else None
        raw_link = fields.get("link")
        title = normalize_text(fields.get("title", ""))
        url = normalize_candidate_url(raw_link, base) if raw_link else None
        pub_date = fields.get("pubdate") or None
        row: dict[str, Any] = {
            "guid": guid, "raw_link": raw_link, "canonical_url": url, "title": title,
            "pub_date_raw": pub_date, "page_facts": {"visible_title": title, "pub_date_raw": pub_date},
        }
        if url is None:
            row |= {"state": "rejected", "reason": "unsafe_or_unusable_url"}
        else:
            host = canonical_host(url)
            if host is None or host not in allowed_hosts:
                row |= {"state": "rejected", "reason": "host_outside_approved_source"}
            elif url in seen:
                row |= {"state": "rejected", "reason": "duplicate_candidate_url"}
            else:
                seen.add(url)
                document_class, cue = classify_hnx_disclosure(title)
                if document_class is None:
                    row |= {"state": "out_of_pilot_scope", "document_class": OUT_OF_SCOPE,
                           "inference": {"cue": None, "basis": "title matches neither piloted fact family"}}
                elif document_class not in evidence_types:
                    row |= {"state": "rejected", "reason": "document_type_not_declared_for_source"}
                else:
                    row |= {"state": "candidate", "document_class": document_class,
                           "inference": {"cue": cue, "document_class": document_class,
                                        "basis": "feed title only; the detail page was not fetched"}}
        rows.append(row)

    return {"schema_version": VERSION, "source_id": str(source_id), "feed_url": base,
            "source_authority": source.get("authority"), "items": rows,
            "item_count": len(rows),
            "candidate_count": sum(1 for r in rows if r.get("state") == "candidate"),
            "out_of_scope_count": sum(1 for r in rows if r.get("state") == "out_of_pilot_scope"),
            "rejected_count": sum(1 for r in rows if r.get("state") == "rejected")}


def _split_share_and_ratio(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {"raw": raw, "shares": None, "ownership_pct": None}
    match = _SHARE_AND_RATIO.search(raw)
    if not match:
        return {"raw": raw, "shares": None, "ownership_pct": None}
    shares = parse_vietnamese_number(match.group(1))
    ratio = parse_vietnamese_number(match.group(2)) if match.group(2) else None
    return {"raw": raw, "shares": shares, "ownership_pct": ratio}


def _split_share(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {"raw": raw, "shares": None}
    match = re.search(r"([\d.,]+)\s*CP", raw, re.IGNORECASE)
    return {"raw": raw, "shares": parse_vietnamese_number(match.group(1)) if match else None}


_SHARE_FIELDS = {"shares_held_before_raw", "shares_held_after_raw"}
_PLAIN_SHARE_FIELDS = {"registered_buy_volume_raw", "registered_sell_volume_raw",
                       "executed_buy_volume_raw", "executed_sell_volume_raw"}
_DATE_FIELDS = {"registration_start_date_raw", "registration_end_date_raw",
               "execution_window_start_date_raw", "execution_window_end_date_raw",
               "ceased_major_holder_date_raw", "became_major_holder_date_raw"}


def parse_disclosure_detail(payload: bytes, *, url: str, encoding: str = "utf-8") -> dict[str, Any]:
    """Turn one stored HNX detail page into structured fields, citing every raw bullet line.

    Every recognised field keeps both its parsed value and the exact raw text it was parsed
    from (`_raw` suffix stripped to the bare field name in `fields`, full bullet text kept in
    `citations`), so a downstream reader can always see the sentence a number came from.
    """
    document = payload.decode(encoding, errors="replace")
    title_match = _TIEUDE.search(document)
    time_match = _THOIGIAN.search(document)
    body_match = _NOIDUNG.search(document)
    title = normalize_text(html.unescape(_TAG.sub("", title_match.group(1)))) if title_match else None
    published_raw = normalize_text(html.unescape(_TAG.sub("", time_match.group(1)))) if time_match else None

    fields: dict[str, Any] = {}
    citations: dict[str, str] = {}
    unparsed_fields: list[dict[str, str]] = []
    related_persons: list[dict[str, Any]] = []
    current_person: dict[str, Any] | None = None

    if body_match is not None:
        raw_body = body_match.group(1)
        sub_chunks = (piece for chunk in _BR.split(raw_body) for piece in _GLUED_BULLET_SPLIT.split(chunk))
        for chunk in sub_chunks:
            text = normalize_text(html.unescape(_TAG.sub(" ", chunk))).rstrip(".").strip()
            if not text:
                continue
            bullet = _BULLET.match(text)
            if not bullet:
                unparsed_fields.append({"raw_line": text, "reason": "not_a_label_value_bullet"})
                continue
            label, value = bullet.group(1).strip(), bullet.group(2).strip()
            if label == _RELATED_PERSON_START:
                current_person = {"name": value}
                related_persons.append(current_person)
                citations[f"related_person[{len(related_persons) - 1}].name"] = text
                continue
            if label in _RELATED_PERSON_LABELS and current_person is not None:
                key = _RELATED_PERSON_LABELS[label]
                current_person[key] = value
                citations[f"related_person[{len(related_persons) - 1}].{key}"] = text
                continue
            canonical = _FIELD_LABELS.get(label)
            if canonical is None:
                unparsed_fields.append({"label": label, "value": value, "raw_line": text})
                continue
            fields[canonical] = value
            citations[canonical] = text

    structured: dict[str, Any] = {}
    for key in _SHARE_FIELDS:
        if key in fields:
            structured[key[:-4]] = _split_share_and_ratio(fields[key])
    for key in _PLAIN_SHARE_FIELDS:
        if key in fields:
            structured[key[:-4]] = _split_share(fields[key])
    for key in _DATE_FIELDS:
        if key in fields:
            structured[key[:-4]] = {"raw": fields[key], "iso_date": parse_vietnamese_date(fields[key])}
    for person in related_persons:
        if "shares_held_raw" in person:
            person["shares_held"] = _split_share(person.pop("shares_held_raw"))

    attachment_urls: list[str] = []
    attach_match = re.search(r'<div class="divLstFileAttach">(.*?)</div>\s*</div>', document, re.DOTALL)
    if attach_match:
        base = normalize_candidate_url(url, url) or url
        for href in _ATTACH_HREF.findall(attach_match.group(1)):
            resolved = normalize_candidate_url(html.unescape(href), base)
            if resolved:
                attachment_urls.append(resolved)

    return {
        "schema_version": VERSION,
        "source_url": url,
        "title": title,
        "published_at_raw": published_raw,
        "ticker": fields.get("ticker"),
        "fields": {**fields, **structured},
        "related_persons": related_persons,
        "unparsed_fields": unparsed_fields,
        "attachment_urls": attachment_urls,
        "citations": citations,
        "content_block_found": body_match is not None,
        # A page whose `Box-Noidung` block this parser never even located (a structurally
        # different notice family, e.g. the fund-certificate insider notices observed
        # 2026-08-24) must never read as "complete" merely because it produced zero bullets to
        # disagree with -- `fields=={}` from a missing block and `fields=={}` from a genuinely
        # empty block are different facts, and only the block being found makes emptiness mean
        # anything.
        "extraction_complete": body_match is not None and not unparsed_fields,
    }


def candidate_id(url: str) -> str:
    return hashlib.sha256(str(url).encode()).hexdigest()[:16]
