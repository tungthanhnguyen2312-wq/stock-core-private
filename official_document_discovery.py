"""Closed-world discovery for bounded official-document acquisition pilots.

This module never searches, crawls, or follows pagination.  A caller supplies an
explicit finite set of already-qualified listing/detail pages and the direct PDF
links observed on each page.  The result is a deterministic ledger suitable for
passing only validated candidates to :mod:`official_document_acquisition`.
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
from typing import Any, Iterable, Mapping

from official_document_acquisition import PERIODS, TICKERS, canonical_url, declared_document_types
from official_source_registry import all_index_document_types, load_registry

VERSION = "1.0.0"
MAX_LISTING_PAGES = 25
MAX_RETAINED_DOCUMENTS = 10

#: Extensions that are certainly not documents. This is a denylist on purpose.
#:
#: Discovery used to allowlist `.pdf`, which rejected two whole shapes of real evidence: an
#: HTML notice (`vsdc-record-date-notice.html`, the retained HPG `listing_change_notice`), and
#: an **extensionless** URL like `https://vsd.vn/en/ad/177392` -- the form every VSDC notice
#: takes, including the one already retained as official VNM evidence. A URL extension is only
#: a hint; `acquire()` validates the real `Content-Type` and refuses anything that is not
#: `application/pdf` or `text/html`. So the hint's job is to drop stylesheets and images, not
#: to decide what a document is.
NON_DOCUMENT_SUFFIXES = (".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
                         ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".zip", ".xml", ".rss")


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _stable_url(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    unstable = {"session", "sid", "token", "signature", "expires", "login", "returnurl"}
    return not any(key.lower() in unstable for key, _ in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))


def _authority_matches(url: str, authority_host: str) -> bool:
    host = urllib.parse.urlsplit(url).hostname or ""
    allowed = authority_host.lower().strip(".")
    return bool(allowed) and (host.lower() == allowed or host.lower().endswith("." + allowed))


def _known_by_url(records: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    known: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        url = record.get("canonical_url")
        if isinstance(url, str): known.setdefault(canonical_url(url), []).append(record)
    return known


def discover(listing_pages: Iterable[Mapping[str, Any]], manifest_records: Iterable[Mapping[str, Any]],
             registry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Validate explicit direct-link discoveries without network access.

    Each listing requires a ticker, authority host, canonical listing URL and an
    explicit ``links`` collection.  A link must carry its raw on-page identity
    (class, period, publication date); no identity is guessed from a filename.

    The admissible document vocabulary comes from the registry, as it does in `acquire()`.
    It previously came from `official_document_acquisition.DOCUMENT_CLASSES`, which omits
    `ex_right_notice`, `listing_change_notice` and `last_registration_date_notice` -- so
    discovery rejected, as `ambiguous_document_identity`, exactly the three notices that
    carry an ex-date, a listing change and a last registration date. Commit 3b4cc5f fixed
    that drift in the acquirer and left it standing one import away.
    """
    registry = registry if registry is not None else load_registry()
    # An index page is a discovery *input*. Finding one linked from another index page is
    # navigation, not a candidate document, and accepting it would be the first step of the
    # link-following crawl the closed-world contract exists to prevent.
    allowed_types = declared_document_types(registry) - all_index_document_types(registry)
    pages = list(listing_pages)
    if len(pages) > MAX_LISTING_PAGES:
        raise ValueError("pagination_bound_exceeded")
    known = _known_by_url(manifest_records)
    ledger: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page_index, page in enumerate(pages, start=1):
        ticker = str(page.get("ticker", "")).upper()
        authority = str(page.get("authority_host", ""))
        listing_url = str(page.get("canonical_url", ""))
        # The registry source that governs this page, carried onto every candidate found on
        # it. Without it `retain()` builds specs `acquire()` refuses as `missing_source_id`,
        # which is what it did for every candidate once 3b4cc5f made `source_id` mandatory.
        source_id = str(page.get("source_id", ""))
        page_base = {"page_index": page_index, "ticker": ticker, "source_id": source_id, "source_authority": page.get("source_authority"), "listing_url": listing_url}
        if ticker not in TICKERS or not source_id or not _stable_url(listing_url) or not _authority_matches(listing_url, authority):
            ledger.append(page_base | {"state": "rejected", "reason": "listing_identity_or_authority_invalid"})
            continue
        for link in page.get("links", []):
            raw_url = str(link.get("canonical_url", ""))
            try: url = canonical_url(raw_url)
            except ValueError:
                ledger.append(page_base | {"state": "rejected", "reason": "unsupported_url", "candidate_url": raw_url}); continue
            document_class, period = str(link.get("document_class", "")), str(link.get("reporting_period", ""))
            candidate = page_base | {"canonical_url": url, "document_class": document_class, "reporting_period": period, "publication_date": link.get("publication_date"), "observed_at": link.get("observed_at"), "discovery_provenance": {"listing_url": listing_url, "link_text": link.get("link_text", ""), "page_index": page_index}}
            if not _stable_url(url): candidate |= {"state": "rejected", "reason": "unstable_or_session_url"}
            elif not _authority_matches(url, authority): candidate |= {"state": "rejected", "reason": "authority_rejected"}
            elif urllib.parse.urlsplit(url).path.lower().endswith(NON_DOCUMENT_SUFFIXES): candidate |= {"state": "rejected", "reason": "unsupported_mime_hint"}
            elif document_class not in allowed_types or period not in PERIODS or not candidate["publication_date"]: candidate |= {"state": "rejected", "reason": "ambiguous_document_identity"}
            elif url in seen: candidate |= {"state": "unchanged", "reason": "duplicate_canonical_url"}
            elif url in known: candidate |= {"state": "unchanged", "reason": "governed_manifest_url_match", "known_document_ids": sorted(str(x.get("document_id")) for x in known[url])}
            else: candidate |= {"state": "new"}
            seen.add(url)
            ledger.append(candidate)
    accepted = [row for row in ledger if row.get("state") == "new"]
    if len(accepted) > MAX_RETAINED_DOCUMENTS:
        raise ValueError("retention_bound_exceeded")
    return {"schema_version": VERSION, "pages_inspected": len(pages), "ledger": ledger, "ledger_sha256": _sha(ledger), "accepted_requests": [{key: row[key] for key in ("ticker", "source_id", "canonical_url", "document_class", "reporting_period", "publication_date", "source_authority")} for row in accepted]}


def replay(listing_pages: Iterable[Mapping[str, Any]], manifest_records: Iterable[Mapping[str, Any]], expected: Mapping[str, Any],
           registry: Mapping[str, Any] | None = None) -> bool:
    """Confirm the persisted ledger is reproducible from the same inputs."""
    actual = discover(listing_pages, manifest_records, registry)
    return actual["ledger_sha256"] == expected.get("ledger_sha256") and actual["ledger"] == expected.get("ledger")


def retain(discovery: Mapping[str, Any], destination: Any, **kwargs: Any) -> dict[str, Any]:
    """Use the existing append-only contract for validated direct-link rows.

    Existing canonical URLs are deliberately rechecked here: acquisition compares
    bytes and records a new immutable version when an issuer changes a document.
    """
    from official_document_acquisition import acquire
    requests = []
    for row in discovery.get("ledger", []):
        if row.get("state") not in {"new", "unchanged"} or not row.get("canonical_url") or row.get("reason") == "duplicate_canonical_url":
            continue
        requests.append({"ticker": row["ticker"], "source_id": row.get("source_id"), "canonical_url": row["canonical_url"], "document_class": row["document_class"], "reporting_period": row["reporting_period"], "published_at": row["publication_date"], "observed_at": row.get("observed_at"), "source_authority": row.get("source_authority"), "discovery_provenance": row["discovery_provenance"]})
    return acquire(requests, destination, **kwargs) if requests else {"outcomes": []}
