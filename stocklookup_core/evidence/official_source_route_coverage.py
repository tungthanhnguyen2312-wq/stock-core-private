"""Non-activating official-source route and evidence-capability ledger.

This is deliberately separate from ``official_source_registry``.  The registry
authorizes document requests only after owner approval; this module records
bounded, source-bound route evidence and can at most emit owner-review
candidates.  It never changes registry activation or creates facts.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
import urllib.parse
import base64
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import requests


VERSION = "1.0.0"
ARTIFACT_TYPE = "official_source_route_evidence_coverage"
SOURCE_FAMILY_ISSUER_IR = "issuer_ir"
SOURCE_FAMILY_EXCHANGE = "exchange_disclosure"
SOURCE_FAMILY_VSDC = "vsdc_notice"

ROUTE_DISCOVERED = "ROUTE_DISCOVERED"
ROUTE_OWNERSHIP_PROVEN = "ROUTE_OWNERSHIP_PROVEN"
ROUTE_TECHNICALLY_REACHABLE = "ROUTE_TECHNICALLY_REACHABLE"
ROUTE_CAPABILITY_CHARACTERIZED = "ROUTE_CAPABILITY_CHARACTERIZED"
ROUTE_READY_FOR_OWNER_PROMOTION = "ROUTE_READY_FOR_OWNER_PROMOTION"
ROUTE_APPROVED = "ROUTE_APPROVED"
LIFECYCLE = (
    ROUTE_DISCOVERED, ROUTE_OWNERSHIP_PROVEN, ROUTE_TECHNICALLY_REACHABLE,
    ROUTE_CAPABILITY_CHARACTERIZED, ROUTE_READY_FOR_OWNER_PROMOTION, ROUTE_APPROVED,
)
_LIFECYCLE_INDEX = {state: index for index, state in enumerate(LIFECYCLE)}

FINANCIAL_EVIDENCE = "financial_evidence"
CORPORATE_ACTION_EVIDENCE = "corporate_action_evidence"
SHARE_LISTING_EVIDENCE = "share_listing_evidence"
EVIDENCE_CATEGORIES = (FINANCIAL_EVIDENCE, CORPORATE_ACTION_EVIDENCE, SHARE_LISTING_EVIDENCE)


class RouteCoverageError(ValueError):
    """A route record or its evidence violates the fail-closed contract."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_locator(url: str) -> str:
    parsed = urllib.parse.urlsplit(str(url))
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise RouteCoverageError("locator_must_be_absolute_http_url")
    query = urllib.parse.urlencode(sorted(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)))
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", query, ""))


def canonical_host(url: str) -> str:
    return urllib.parse.urlsplit(canonical_locator(url)).hostname.lower()


def _same_authority(requested: str, final: str) -> bool:
    first, second = canonical_host(requested), canonical_host(final)
    return first == second or {first, second} == {f"www.{second}", second} or {first, second} == {f"www.{first}", first}


def normalize_identity(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"\bctcp\b", "cong ty co phan", text)
    text = re.sub(r"\bcty\b", "cong ty", text)
    text = re.sub(r"\btnhh\b", "cong ty trach nhiem huu han", text)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._href: str | None = None
        self._parts: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, " ".join(" ".join(self._parts).split())))
            self._href, self._parts = None, []


def _categories(text: str, locator: str) -> list[str]:
    value = normalize_identity(f"{text} {locator}")
    categories: list[str] = []
    if any(token in value for token in ("bao cao tai chinh", "financial statement", "annual report", "bctc", "kiem toan")):
        categories.append(FINANCIAL_EVIDENCE)
    if any(token in value for token in ("co tuc", "dividend", "quyen mua", "rights issue", "ngay dang ky cuoi cung", "record date")):
        categories.append(CORPORATE_ACTION_EVIDENCE)
    # A navigation or policy page merely mentioning ``listing`` is not evidence that this
    # route publishes issuer-specific listing/share-change notices.  Require an event-like
    # discriminator, preserving generic listing-policy links as non-capability evidence.
    if any(token in value for token in ("listing change", "thay doi von", "thay doi co phieu", "issued share", "trading effective")):
        categories.append(SHARE_LISTING_EVIDENCE)
    return categories


def characterize_html(*, locator: str, raw_bytes: bytes) -> dict[str, Any]:
    """Characterize only exact links found in one retained first-party HTML object."""
    text = raw_bytes.decode("utf-8", errors="replace")
    parser = _LinkCollector()
    parser.feed(text)
    locators: list[dict[str, Any]] = []
    for href, label in parser.links:
        try:
            target = canonical_locator(urllib.parse.urljoin(locator, html.unescape(href)))
        except RouteCoverageError:
            continue
        cats = _categories(label, target)
        if cats:
            locators.append({"locator": target, "link_text": label, "evidence_categories": cats})
    deduped = {item["locator"]: item for item in locators}
    locators = [deduped[key] for key in sorted(deduped)]
    demonstrated = sorted({category for item in locators for category in item["evidence_categories"]})
    return {
        "content_type": "text/html",
        "publication_date_visibility": "not_demonstrated_from_single_page",
        "archive_history_capability": "not_demonstrated_from_single_page",
        "exact_document_locator_capability": bool(locators),
        "representative_document_locators": locators,
        "demonstrated_evidence_categories": demonstrated,
    }


def _state_for(*, ownership: bool, reachable: bool, characterized: bool, approved: bool) -> str:
    if approved:
        return ROUTE_APPROVED
    # Capability findings from an ambiguous page remain retained, but cannot advance a
    # route past reachability: lifecycle evidence is conjunctive, never substitutive.
    if ownership and reachable and characterized:
        return ROUTE_READY_FOR_OWNER_PROMOTION
    if reachable:
        return ROUTE_TECHNICALLY_REACHABLE
    if ownership:
        return ROUTE_OWNERSHIP_PROVEN
    return ROUTE_DISCOVERED


def validate_route(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a route without widening its lifecycle or authority."""
    route = dict(record)
    for field in ("instrument_id", "issuer_id", "source_family", "canonical_locator", "qualification_state"):
        if not isinstance(route.get(field), str) or not route[field].strip():
            raise RouteCoverageError(f"missing_required_route_field:{field}")
    route["canonical_locator"] = canonical_locator(route["canonical_locator"])
    route["canonical_domain"] = canonical_host(route["canonical_locator"])
    if route["source_family"] not in {SOURCE_FAMILY_ISSUER_IR, SOURCE_FAMILY_EXCHANGE, SOURCE_FAMILY_VSDC}:
        raise RouteCoverageError("unsupported_source_family")
    if route.get("seed_provenance") not in {"retained_repository_candidate", "retained_official_document", "owner_approved_registry"}:
        raise RouteCoverageError("unguarded_or_guessed_domain_seed")
    provenance = route.get("provenance") if isinstance(route.get("provenance"), Mapping) else {}
    encoded = provenance.get("raw_payload_base64")
    if not isinstance(encoded, str):
        raise RouteCoverageError("retained_raw_payload_missing")
    try:
        retained_bytes = base64.b64decode(encoded.encode("ascii"), validate=True)
    except ValueError as exc:
        raise RouteCoverageError("retained_raw_payload_invalid") from exc
    if provenance.get("response_sha256") != _sha256(retained_bytes):
        raise RouteCoverageError("retained_raw_payload_hash_mismatch")
    ownership = route.get("ownership_evidence")
    ownership_proven = isinstance(ownership, Mapping) and bool(ownership.get("source_sha256")) and bool(ownership.get("evidence_locator"))
    if ownership_proven and ownership.get("source_sha256") != provenance.get("response_sha256"):
        raise RouteCoverageError("ownership_evidence_hash_not_bound_to_retained_payload")
    reachable = route.get("access_state") == "REACHABLE"
    characterization = route.get("capability") if isinstance(route.get("capability"), Mapping) else {}
    characterized = bool(characterization.get("characterized"))
    approved = bool(route.get("owner_approved"))
    expected = _state_for(ownership=ownership_proven, reachable=reachable, characterized=characterized, approved=approved)
    if route["qualification_state"] != expected:
        raise RouteCoverageError(f"lifecycle_state_overclaim:{route['qualification_state']}!=expected:{expected}")
    if approved and not route.get("owner_approval_reference"):
        raise RouteCoverageError("approved_route_missing_owner_reference")
    identity_payload = {key: value for key, value in route.items() if key != "route_id"}
    route_id = f"official-route:{_hash(identity_payload)}"
    if route.get("route_id") not in {None, route_id}:
        raise RouteCoverageError("route_identity_mismatch")
    route["route_id"] = route_id
    return route


def build_artifact(*, baseline: Mapping[str, Any], routes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = [validate_route(route) for route in routes]
    ids = [route["route_id"] for route in normalized]
    if len(ids) != len(set(ids)):
        raise RouteCoverageError("duplicate_route_identity")
    normalized.sort(key=lambda route: route["route_id"])
    # Roadmap coverage is cumulative: a route that reaches a later gate has necessarily
    # cleared every prior gate.  Keep the exclusive terminal-state distribution under an
    # explicit name only for debugging; never present it as lifecycle coverage.
    terminal_counts = Counter(route["qualification_state"] for route in normalized)
    gate_counts = {
        state: sum(1 for route in normalized if _LIFECYCLE_INDEX[route["qualification_state"]] >= _LIFECYCLE_INDEX[state])
        for state in LIFECYCLE
    }
    payload: dict[str, Any] = {
        "schema_version": VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "baseline": dict(baseline),
        "routes": normalized,
        "lifecycle_gate_counts": gate_counts,
        "terminal_state_counts": {state: terminal_counts[state] for state in LIFECYCLE},
        "source_family_counts": dict(sorted(Counter(route["source_family"] for route in normalized).items())),
        "authority": {"owner_promotion_performed": False, "registry_mutated": False, "facts_created": 0},
    }
    digest = _hash(payload)
    return {**payload, "artifact_sha256": digest, "artifact_identity": f"official-source-route-coverage:{digest}"}


def inspect_seed(
    seed: Mapping[str, str], *, fetcher: Callable[[str], tuple[int, Mapping[str, str], bytes, str]]
) -> dict[str, Any]:
    """One bounded GET for an exact repository-supported candidate locator."""
    requested = canonical_locator(str(seed["locator"]))
    fetch_failure: str | None = None
    try:
        status, headers, raw_bytes, final = fetcher(requested)
    except (requests.RequestException, OSError) as exc:
        # A bounded foreground probe failing is evidence about this exact route, not a
        # reason to abandon the remaining independent seeds or invent a replacement URL.
        status, headers, raw_bytes, final = 0, {}, b"", requested
        fetch_failure = type(exc).__name__
    final = canonical_locator(final)
    same_authority = _same_authority(requested, final)
    text = raw_bytes.decode("utf-8", errors="replace")
    expected = str(seed["issuer_id"])
    identity_match = normalize_identity(expected) in normalize_identity(text)
    reachable = 200 <= int(status) < 300 and bool(raw_bytes) and same_authority
    capability = characterize_html(locator=final, raw_bytes=raw_bytes) if reachable else {
        "content_type": str(headers.get("Content-Type") or "unknown"),
        "publication_date_visibility": "not_tested_unreachable",
        "archive_history_capability": "not_tested_unreachable",
        "exact_document_locator_capability": False,
        "representative_document_locators": [],
        "demonstrated_evidence_categories": [],
    }
    characterized = reachable and bool(capability["demonstrated_evidence_categories"])
    ownership = ({"evidence_locator": final, "source_sha256": _sha256(raw_bytes), "evidence_type": "full_legal_identity_in_retained_first_party_html"}
                 if reachable and identity_match else None)
    state = _state_for(ownership=bool(ownership), reachable=reachable, characterized=characterized, approved=False)
    return {
        "instrument_id": seed["ticker"], "issuer_id": expected,
        "source_family": SOURCE_FAMILY_ISSUER_IR, "canonical_locator": final,
        "route_pattern": "issuer_home_or_ir_index_exact_link_v1", "ownership_evidence": ownership,
        "access_state": "REACHABLE" if reachable else "UNREACHABLE_OR_UNSAFE_REDIRECT",
        "rate_limit_or_antibot_state": "NONE_OBSERVED" if reachable else "ACCESS_OR_REDIRECT_BLOCKER",
        "capability": {**capability, "characterized": characterized},
        "content_type": capability["content_type"], "provenance": {"requested_locator": requested, "http_status": int(status) or None, "response_sha256": _sha256(raw_bytes), "response_bytes": len(raw_bytes), "raw_payload_base64": base64.b64encode(raw_bytes).decode("ascii"), "same_authority_redirect": same_authority, "fetch_failure": fetch_failure},
        "qualification_state": state,
        "exact_blocker": None if state == ROUTE_READY_FOR_OWNER_PROMOTION else ("OWNERSHIP_EVIDENCE_MISSING" if reachable and not ownership else "NO_DEMONSTRATED_EVIDENCE_CATEGORY" if reachable else "UNREACHABLE_OR_UNSAFE_REDIRECT"),
        "seed_provenance": "retained_repository_candidate", "owner_approved": False,
    }


def requests_fetcher(url: str) -> tuple[int, Mapping[str, str], bytes, str]:
    response = requests.get(url, timeout=(5, 15), headers={"User-Agent": "StockLookupOfficialEvidence/1.1"}, allow_redirects=True)
    return response.status_code, dict(response.headers), response.content, response.url
