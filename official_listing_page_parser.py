"""Read candidate links out of one stored official announcement index page.

WHAT THIS IS
    The smallest first-party parser that removes the "an owner hand-supplies every URL"
    dependency. It takes bytes already retained through the governed acquisition path and the
    admitted URL those bytes came from, and returns the *input* to
    `official_document_discovery.discover()` -- the same `listing_pages` mapping a human would
    otherwise have typed. Discovery, and then the registry gate at `acquire()`, still decide
    what may be requested. This module widens nothing.

WHAT IT IS NOT
    It performs no I/O of any kind: no network, no filesystem, no subprocess. It follows no
    pagination, executes no JavaScript, drives no browser, and reads no PDF. It is a pure
    function of (bytes, base URL, registry) so that "the parser made a request" is not a thing
    that can happen, rather than a thing that is asserted not to happen.

WHY A REGEX PARSER AND NOT AN HTML LIBRARY
    The tree has no HTML parser dependency and this needs one page shape, not a DOM. VSDC
    announcement indexes and the "Issuer's news" blocks on notice pages share one structure,
    observed in two independently retained artifacts:

        <ul class="list-news">
          <li>
            <h3><a href="/en/ad/197038">VNM: Residual Payment of 2025 cash dividend</a></h3>
            <div class="time-news">Date update 17/06/2026 - 17:20:44</div>
          </li>

    Anchors outside that structure are still read, but without a date; nothing is invented to
    fill the gap.

HOW AN ISSUER IS IDENTIFIED
    By the `CODE:` prefix the source itself writes, matched whole -- never by asking whether
    "VNM" appears somewhere in a title. Substring matching would accept the bond code
    `VNM12501` and the phrase "compared with VNM"; it would also silently match a different
    issuer's notice that happens to mention Vinamilk. The prefix is a direct page fact; the
    document class inferred from the subject line is explicitly not, and the two are returned
    under separate keys so a reader can never mistake one for the other.
"""

from __future__ import annotations

import html
import re
import urllib.parse
from typing import Any, Iterable, Mapping

from official_source_registry import canonical_host, evidence_document_types, source_index

VERSION = "1.0.0"

#: Only these schemes may appear in a candidate. Everything else -- `javascript:`, `data:`,
#: `file:`, `mailto:` -- is rejected by name rather than by failing to parse later.
SAFE_SCHEMES = frozenset({"http", "https"})

#: Query keys that make a URL non-reproducible. A candidate carrying one is not a stable
#: identity for a document, so it is rejected rather than normalised.
UNSTABLE_QUERY_KEYS = frozenset({"session", "sid", "token", "signature", "expires",
                                 "login", "returnurl", "jsessionid", "phpsessid"})

_ANCHOR = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_HREF = re.compile(r"""href\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_LIST_ITEM = re.compile(r"<li\b[^>]*>(.*?)</li>", re.IGNORECASE | re.DOTALL)
_TIME_NEWS = re.compile(r'class\s*=\s*["\'][^"\']*\btime-news\b[^"\']*["\'][^>]*>(.*?)<',
                        re.IGNORECASE | re.DOTALL)
#: `dd/mm/yyyy`, the only date form these pages print.
_VISIBLE_DATE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
#: `VNM: ...`, `NAB12504: ...` -- the source's own issuer/instrument code prefix.
_CODE_PREFIX = re.compile(r"^\s*([A-Z][A-Z0-9]{2,11})\s*:\s*(.+)$", re.DOTALL)

#: Subject-line cues, most specific first. Every value is an *inference* about what the linked
#: document may contain, never a fact read off the index page.
_CLASS_CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # The VSDC class that actually carries an absolute registered share quantity. Observed as
    # "CTR: Adjustment of the number of registered shares" on the acquired index page and as
    # "VCB: Certification of the 10th adjustment of the number of the registered shares" in the
    # retained VCB artifact. A record-date notice does not carry a share count -- the retained
    # VNM notice `/en/ad/177392` states issuer, ISIN, par value, record date and payment rate
    # and no total -- so this cue is the one that matters for a share-count question.
    ("listing_change_notice", ("adjustment of the number of registered shares",
                               "adjustment of the number of the registered shares",
                               "number of registered shares", "registered shares",
                               "listing change", "change of listing", "additional listing",
                               "change in listing", "delisting", "listing of additional",
                               "thay doi niem yet", "niem yet bo sung")),
    ("ex_right_notice", ("ex-right", "ex right", "ex-dividend", "ex dividend",
                         "ngay giao dich khong huong quyen")),
    ("last_registration_date_notice", ("record date", "last registration", "registration date",
                                       "ngay dang ky cuoi cung")),
    ("amendment_or_supersession_notice", ("correcting information", "correction", "amendment",
                                          "cancellation of", "dinh chinh")),
    ("agm_document_or_resolution", ("general meeting", "agm", "egm", "dai hoi dong co dong")),
    ("corporate_action_notice", ("stock dividend", "bonus share", "share issuance",
                                 "issuance for raising", "cash dividend", "dividend",
                                 "share capital", "co tuc")),
)

#: Cues that a candidate may bear on an absolute share count or an executed capital change.
#: Used only to order a human's review queue; it asserts nothing about the document.
_SHARE_RELEVANCE_CUES = ("registered shares", "listing", "issuance", "stock dividend", "bonus",
                         "share capital", "raising share capital", "additional", "delisting",
                         "split")


def _text(fragment: str) -> str:
    return " ".join(html.unescape(_TAG.sub(" ", fragment)).split())


def _href(attrs: str) -> str | None:
    found = _HREF.search(attrs)
    if not found:
        return None
    return html.unescape(next(g for g in found.groups() if g is not None)).strip()


def normalize_candidate_url(raw: str, base_url: str) -> str | None:
    """Resolve, validate and canonicalise one href, or return None if it is not usable.

    The explicit rules, in order:

    * resolve relative to the admitted listing-page URL, so `/en/ad/197038` becomes absolute;
    * reject any scheme outside `SAFE_SCHEMES`, checked *before* resolution as well, so a
      `javascript:` href cannot be laundered into a path by `urljoin`;
    * reject embedded credentials (`user:pass@host`) outright -- a URL that carries a secret is
      not a public document identity, and normalising it would retain the secret;
    * drop the fragment always: `#section-2` names a position in a document, never a document;
    * keep the query, but sort its pairs, so two orderings of the same request are one identity;
    * reject a query carrying a session-shaped key, since it cannot be reproduced later.
    """
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
    return urllib.parse.urlunsplit((
        resolved.scheme.lower(), resolved.netloc.lower(), resolved.path or "/",
        urllib.parse.urlencode(sorted(query)), ""))


def _visible_date(fragment: str) -> str | None:
    """`dd/mm/yyyy` as printed, returned ISO. Absent means absent -- never today's date."""
    stamp = _TIME_NEWS.search(fragment) or None
    found = _VISIBLE_DATE.search(_text(stamp.group(1)) if stamp else _text(fragment))
    if not found:
        return None
    day, month, year = found.groups()
    if not (1 <= int(month) <= 12 and 1 <= int(day) <= 31):
        return None
    return f"{year}-{month}-{day}"


def infer_document_class(subject: str,
                         declared: Iterable[str] | None = None) -> tuple[str, str | None]:
    """Guess what the linked document is, from the subject line only.

    Returns the class and the cue that produced it, so the guess is auditable and a reader can
    see it is a guess. Nothing downstream treats this as evidence: `discover()` revalidates the
    class against the registry, and the notice itself is what would have to be acquired and
    parsed before any fact is claimed.

    The guess is confined to what *this source* declares. VSDC does not declare
    `listing_change_notice`, so inferring one for a VSDC candidate would mint a candidate the
    gate then refuses with `document_type_not_declared_for_source` -- correct, fail-closed, and
    useless, because every registered-share notice would land in that hole. Cues for classes
    the source does not publish fall through to the next cue, and finally to the source's own
    general notice type.
    """
    allowed = {str(entry) for entry in declared} if declared is not None else None
    lowered = subject.lower()
    fallback = "corporate_action_notice"
    if allowed is not None and fallback not in allowed:
        fallback = sorted(allowed)[0] if allowed else fallback
    for suggested, cues in _CLASS_CUES:
        for cue in cues:
            if cue not in lowered:
                continue
            # The cue survives even when the class does not. What the subject line is *about*
            # is a reading of the page; which registry class the source happens to publish it
            # under is a fact about the source. Dropping the cue with the class would have
            # silently downgraded every VSDC registered-share notice -- the one class that
            # carries an absolute share count -- to an uncued guess.
            if allowed is None or suggested in allowed:
                return suggested, cue
            return fallback, cue
    return fallback, None


def _share_relevance(subject: str) -> list[str]:
    lowered = subject.lower()
    return sorted({cue for cue in _SHARE_RELEVANCE_CUES if cue in lowered})


def parse_index_page(payload: bytes, *, listing_url: str, source_id: str, ticker: str,
                     registry: Mapping[str, Any], encoding: str = "utf-8") -> dict[str, Any]:
    """Turn stored index-page bytes into one `official_document_discovery` listing page.

    `payload` is bytes already retained by `acquire()`. Nothing here reads a file or a socket.
    """
    source = source_index(registry).get(str(source_id))
    if source is None:
        raise ValueError("unknown_source_id")
    allowed_hosts = {str(host).lower() for host in source.get("allowed_hosts") or []}
    evidence_types = evidence_document_types(source)
    base = normalize_candidate_url(listing_url, listing_url)
    if base is None:
        raise ValueError("unusable_listing_url")

    document = payload.decode(encoding, errors="replace")
    wanted = str(ticker).upper()

    # Anchors inside `<li>` blocks carry a visible date; the rest are read without one.
    dated: dict[str, str] = {}
    for item in _LIST_ITEM.finditer(document):
        stamp = _visible_date(item.group(1))
        if not stamp:
            continue
        for anchor in _ANCHOR.finditer(item.group(1)):
            href = _href(anchor.group(1))
            resolved = normalize_candidate_url(href, base) if href else None
            if resolved:
                dated.setdefault(resolved, stamp)

    links: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for anchor in _ANCHOR.finditer(document):
        raw_href = _href(anchor.group(1))
        title = _text(anchor.group(2))
        if not raw_href:
            continue
        url = normalize_candidate_url(raw_href, base)
        if url is None:
            rejected.append({"raw_href": raw_href, "link_text": title,
                             "reason": "unsafe_or_unusable_url"})
            continue
        host = canonical_host(url)
        if host is None or host not in allowed_hosts:
            rejected.append({"candidate_url": url, "link_text": title,
                             "reason": "host_outside_approved_source"})
            continue
        if not title:
            rejected.append({"candidate_url": url, "reason": "no_visible_title"})
            continue
        coded = _CODE_PREFIX.match(title)
        if not coded:
            rejected.append({"candidate_url": url, "link_text": title,
                             "reason": "no_issuer_code_prefix"})
            continue
        code, subject = coded.group(1).upper(), " ".join(coded.group(2).split())
        if code != wanted:
            rejected.append({"candidate_url": url, "link_text": title, "issuer_code": code,
                             "reason": "different_issuer"})
            continue
        if url in seen:
            rejected.append({"candidate_url": url, "link_text": title,
                             "reason": "duplicate_candidate_url"})
            continue
        seen.add(url)
        document_class, cue = infer_document_class(subject, evidence_types)
        publication_date = dated.get(url)
        links.append({
            "canonical_url": url,
            "link_text": title,
            "document_class": document_class,
            "reporting_period": (publication_date or "")[:4] or None,
            "publication_date": publication_date,
            # Direct page facts, read verbatim off the index page.
            "page_facts": {"issuer_code": code, "subject": subject,
                           "visible_date": publication_date, "visible_title": title},
            # Inference about the linked document. Not a fact, and labelled as such.
            "inference": {"document_class": document_class, "cue": cue,
                          "share_relevance_cues": _share_relevance(subject),
                          "basis": "index-page subject line only; the document was not fetched"},
        })

    links.sort(key=lambda row: (row["publication_date"] or "", row["canonical_url"]),
               reverse=True)
    return {
        "schema_version": VERSION,
        "ticker": wanted,
        "source_id": str(source_id),
        "authority_host": canonical_host(base),
        "canonical_url": base,
        "source_authority": source.get("authority"),
        "links": links,
        "rejected_links": rejected,
    }


def listing_pages(parsed: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The `discover()` argument, so callers never hand-build the seam."""
    return [{key: parsed[key] for key in ("ticker", "source_id", "authority_host",
                                          "canonical_url", "source_authority", "links")}]


def candidate_id(ticker: str, url: str) -> str:
    """Deterministic, content-free candidate identity: same page, same ids, every run."""
    import hashlib
    return hashlib.sha256(f"{str(ticker).upper()}|{url}".encode()).hexdigest()[:16]


def review_queue(parsed: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Candidates ordered for a human: share-count relevance first, then most recent."""
    rows = []
    for link in parsed.get("links") or []:
        cues = link["inference"]["share_relevance_cues"]
        rows.append({
            "candidate_id": candidate_id(parsed.get("ticker", ""), link["canonical_url"]),
            "canonical_url": link["canonical_url"],
            "visible_title": link["page_facts"]["visible_title"],
            "visible_date": link["page_facts"]["visible_date"],
            "issuer_code": link["page_facts"]["issuer_code"],
            "inferred_document_class": link["inference"]["document_class"],
            "share_relevance_cues": cues,
            "confidence": "high" if cues and link["inference"]["cue"] else
                          ("medium" if link["inference"]["cue"] else "low"),
        })
    rows.sort(key=lambda row: (not row["share_relevance_cues"],
                               row["visible_date"] is None,
                               "" if row["visible_date"] is None else _descending(row["visible_date"]),
                               row["candidate_id"]))
    for order, row in enumerate(rows, start=1):
        row["review_order"] = order
    return rows


def _descending(stamp: str) -> str:
    """Sort key that puts the most recent date first without reversing the whole tuple."""
    return "".join(chr(ord("9") - int(ch)) if ch.isdigit() else ch for ch in stamp)


def parsed_summary(parsed: Mapping[str, Any]) -> dict[str, Any]:
    reasons: dict[str, int] = {}
    for row in parsed.get("rejected_links") or []:
        reasons[row["reason"]] = reasons.get(row["reason"], 0) + 1
    return {"ticker": parsed.get("ticker"), "listing_url": parsed.get("canonical_url"),
            "candidates": len(parsed.get("links") or []),
            "rejected": sum(reasons.values()), "rejected_by_reason": dict(sorted(reasons.items()))}
