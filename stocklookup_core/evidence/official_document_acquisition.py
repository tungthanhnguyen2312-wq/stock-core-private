"""Bounded official-document retention and operator-supplied evidence intake."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import requests

import official_source_registry as registry_module
from official_source_registry import ADMITTED, admit, load_registry
from stocklookup_core.evidence.temporal_retention import capture_raw_receipt, project_retention_to_a1

VERSION = "1.2.0"
MANIFEST = "official_document_acquisition_manifest.json"
EVENTS = "official_price_test_events.jsonl"
# The governed acquirer deliberately retains a finite cohort.  DTP is the one additional
# ticker admitted by HISTORICAL_PIT_RAW_AS_TRADED_AND_CORPORATE_ACTION_EVIDENCE_V1 after it
# appeared as a cash-dividend notice on the single retained VSDC index page; it is not a
# discovery wildcard or a provider-wide expansion.
TICKERS = frozenset({"HPG", "VNM", "VCB", "SSI", "PAN", "PNJ", "FPT", "PVD", "QNS", "POW", "NVL", "GAS", "VRE", "DTP"})
#: Retained for the storage-path vocabulary only. The gate on what may be requested comes
#: from the registry (`declared_document_types`), never from this tuple.
DOCUMENT_CLASSES = ("audited_annual_financial_statements", "reviewed_interim_financial_statements", "annual_report", "corporate_governance_report", "agm_document_or_resolution", "corporate_action_notice", "amendment_or_supersession_notice")
# Annual evidence is retained only for explicitly reviewed reporting periods.  FY2022 is
# required by the targeted multi-period issuer-document pilot; keeping this finite set
# preserves the acquisition boundary while allowing the immediately preceding comparison
# year to be requested.
PERIODS = frozenset({"2022", "2023", "2024", "2025", "2026", "2026-H1", "2026-Q2"})
# The Novaland FY2024 audited consolidated PDF is 23,761,801 bytes.  The bounded
# 32 MiB ceiling admits that known issuer filing without opening unbounded retention.
CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS, MAX_RESPONSE_BYTES = 5, 15, 32 * 1024 * 1024
MAX_REDIRECTS = 5
REQUEST_HEADERS = {"Accept": "application/pdf,text/html;q=0.9", "User-Agent": "StockLookupOfficialEvidence/1.1"}
DISCOVERY_RSS_MEDIA_TYPE = "application/rss+xml"
BOUNDED_ADDITIONAL_TICKER_SCOPE_EXCEEDED = "BOUNDED_ADDITIONAL_TICKER_SCOPE_EXCEEDED"
_TICKER_IDENTITY = re.compile(r"[A-Z][A-Z0-9]{0,9}")


def canonical_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc: raise ValueError("unsupported_url")
    query = urllib.parse.urlencode(sorted(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)))
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", query, ""))


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""): digest.update(chunk)
    return digest.hexdigest()


def _safe(value: str) -> str: return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")
def _now() -> str: return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
def _document_id(ticker: str, url: str, sha256: str) -> str: return hashlib.sha256(f"{ticker}|{url}|{sha256}".encode()).hexdigest()
def _content_type(headers: Mapping[str, str]) -> str: return str(headers.get("Content-Type") or headers.get("content-type") or "").split(";", 1)[0].lower()


def _sniff_media_type(reported_content_type: str, prefix: bytes) -> tuple[str | None, str | None]:
    raw = (reported_content_type or "").split(";", 1)[0].lower().strip()
    if raw == "application/pdf":
        return ("application/pdf", "declared_header") if prefix.startswith(b"%PDF") else (None, None)
    if raw in {"text/html", "application/xhtml+xml"}:
        return ("text/html", "declared_header") if (b"<html" in prefix.lower() or b"<!doctype html" in prefix.lower()) else (None, None)
    # RSS is a registry-declared *discovery input* for HNX, never a corporate-action
    # observation.  It must nevertheless be retained as immutable XML before its exact,
    # first-party item links can be parsed.  Admit it only when the response both declares an
    # XML/RSS media type and carries an RSS root; a generic XML response remains unsupported.
    if raw in {"application/rss+xml", "application/xml", "text/xml"}:
        lowered = prefix.lower()
        return (DISCOVERY_RSS_MEDIA_TYPE, "declared_rss_xml") if b"<rss" in lowered else (None, None)
    if raw in {"application/octet-stream", "binary/octet-stream", ""}:
        if prefix.startswith(b"%PDF"):
            return "application/pdf", "magic_bytes_octet_stream"
        if b"<html" in prefix.lower() or b"<!doctype html" in prefix.lower():
            return "text/html", "html_tag_octet_stream"
    return None, None


def _supported(content_type: str, prefix: bytes) -> bool:
    detected, _ = _sniff_media_type(content_type, prefix)
    return detected is not None


def _load(path: Path) -> dict[str, Any]:
    if not path.exists(): return {"schema_version": VERSION, "records": []}
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise ValueError("manifest_malformed") from exc
    if data.get("schema_version") not in {"1.0.0", VERSION} or not isinstance(data.get("records"), list): raise ValueError("manifest_unsupported")
    data["schema_version"] = VERSION
    return data


def _atomic_write(path: Path, content: bytes) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".retain-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out: out.write(content)
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True); raise


def _write_manifest(path: Path, records: list[dict[str, Any]]) -> None:
    _atomic_write(path, (json.dumps({"schema_version": VERSION, "records": records}, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def declared_document_types(registry: Mapping[str, Any]) -> frozenset[str]:
    """Every document type any source declares.

    The gate on an individual request is `admit()`, which checks the type against *that*
    source. This union only decides whether a request is well-formed enough to ask about, and
    it comes from the registry so the two vocabularies cannot drift: the module's own
    `DOCUMENT_CLASSES` was missing `ex_right_notice`, `listing_change_notice` and
    `last_registration_date_notice`, so the acquirer refused, as malformed, requests for the
    exact notices that carry an ex-date — the field the price-adjustment factor is blocked on.

    Index page types (`index_document_types`) are included: an announcement index must be
    requestable, or links can never be read from a stored artifact and every entry URL stays a
    manual owner hand-off. They are requestable and *not* promotable -- `official_document_store`
    refuses them, so the separation is enforced where evidence is written, not here.
    """
    return frozenset(str(entry) for source in registry.get("sources") or []
                     for field in ("document_types", registry_module.INDEX_DOCUMENT_TYPES_FIELD)
                     for entry in source.get(field) or [])


def _declared_interval(registry: Mapping[str, Any], source_id: str) -> float:
    for source in registry.get("sources") or []:
        if str(source.get("source_id")) == source_id:
            return float(source.get("min_request_interval_seconds") or 0.0)
    return 0.0


def _declared_max_redirects(registry: Mapping[str, Any]) -> int:
    """The redirect bound comes from the registry, which declared one nothing read.

    `global_policy.max_redirects` sat in the reviewed JSON while `fetch_http` compared against
    a hardcoded 5. They agreed, so nothing broke -- but the reviewable value governed nothing,
    which is how the document-type vocabulary drifted too.
    """
    declared = (registry.get("global_policy") or {}).get("max_redirects")
    return int(declared) if isinstance(declared, int) and declared >= 0 else MAX_REDIRECTS


def _validate_spec(spec: Mapping[str, Any], allowed_types: frozenset[str], *,
                   allowed_tickers: frozenset[str] = TICKERS) -> tuple[str, str, str, str, str]:
    ticker, document_class, period = str(spec.get("ticker", "")).upper(), str(spec.get("document_class", "")), str(spec.get("reporting_period", ""))
    source_id = str(spec.get("source_id", ""))
    if not source_id: raise ValueError("missing_source_id")
    if ticker not in allowed_tickers or document_class not in allowed_types or period not in PERIODS: raise ValueError("unsupported_request")
    return ticker, document_class, period, canonical_url(str(spec.get("canonical_url", ""))), source_id


def _bounded_additional_ticker_scope(tickers: Iterable[str] | None) -> frozenset[str]:
    """Validate the explicitly requested, finite extension to ``TICKERS``.

    ``None`` means no extension and preserves the historical default scope.  An
    explicitly supplied empty, duplicate, malformed, default-scope-overlapping,
    or larger-than-three extension fails before any registry or HTTP action.
    """
    if tickers is None:
        return frozenset()
    values = tuple(tickers)
    normalized = tuple(value.strip().upper() if isinstance(value, str) else "" for value in values)
    if (not normalized or len(normalized) > 3 or any(not _TICKER_IDENTITY.fullmatch(value) for value in normalized)
            or len(set(normalized)) != len(normalized) or any(value in TICKERS for value in normalized)):
        raise ValueError(BOUNDED_ADDITIONAL_TICKER_SCOPE_EXCEEDED)
    return frozenset(normalized)


def fetch_http(url: str, *, temporary_path: Path, timeout_seconds: int = READ_TIMEOUT_SECONDS,
               connect_timeout_seconds: int = CONNECT_TIMEOUT_SECONDS, max_response_bytes: int = MAX_RESPONSE_BYTES,
               admit_hop: Callable[[str], bool] | None = None, max_redirects: int = MAX_REDIRECTS,
               before_request: Callable[[], None] | None = None) -> tuple[int, Mapping[str, str], bytes, str]:
    """Stream one response to caller-owned temporary storage; never promote it.

    Redirects are followed one hop at a time, and `admit_hop` decides each hop *before* the
    next request leaves. `allow_redirects=True` delegated that decision to the responding
    host: a 302 off an allowlisted host was followed, retained and recorded, so the allowlist
    governed the URL a spec named rather than the host the bytes came from. An allowlist a
    redirect can step outside of is not one.
    """
    current, seen = url, set()
    for _ in range(max_redirects + 1):
        if before_request is not None:
            before_request()
        response = requests.get(current, headers=REQUEST_HEADERS, timeout=(connect_timeout_seconds, timeout_seconds), allow_redirects=False, stream=True)
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location") or response.headers.get("location")
            response.close()
            if not location: raise ValueError("unstable_redirect")
            target = canonical_url(urllib.parse.urljoin(current, str(location)))
            if target in seen: raise ValueError("unstable_redirect")
            if admit_hop is not None and not admit_hop(target): raise ValueError("redirect_refused_by_source_registry")
            seen.add(current); current = target
            continue
        headers, status = dict(response.headers.items()), response.status_code
        length = response.headers.get("Content-Length")
        if length and int(length) > max_response_bytes: raise ValueError("response_size_limit")
        prefix = bytearray()
        if not 200 <= status < 300:
            for chunk in response.iter_content(chunk_size=1024): prefix.extend(chunk); break
            return status, headers, bytes(prefix), current
        chunks = response.iter_content(chunk_size=65536)
        first_chunk = next(chunks, b"")
        prefix.extend(first_chunk[:1024])
        detected_ct, _ = _sniff_media_type(_content_type(headers), bytes(prefix))
        if detected_ct not in {"application/pdf", "text/html", DISCOVERY_RSS_MEDIA_TYPE}: return status, headers, bytes(prefix), current
        total = len(first_chunk)
        try:
            with temporary_path.open("wb") as out:
                out.write(first_chunk)
                for chunk in chunks:
                    total += len(chunk)
                    if total > max_response_bytes: raise ValueError("response_size_limit")
                    if len(prefix) < 1024: prefix.extend(chunk[:1024-len(prefix)])
                    out.write(chunk)
            return status, headers, bytes(prefix), current
        except Exception:
            temporary_path.unlink(missing_ok=True); raise
    raise ValueError("unstable_redirect")


def _failure(exc: Exception) -> str:
    if str(exc) in {"HTTP_REQUEST_CAP_REACHED", "STORAGE_BUDGET_REACHED"}:
        return str(exc)
    if isinstance(exc, (TimeoutError, requests.Timeout)): return "timeout"
    if isinstance(exc, ValueError) and str(exc) in {"unstable_redirect", "response_size_limit", "redirect_refused_by_source_registry"}: return str(exc)
    if isinstance(exc, requests.exceptions.SSLError): return "tls_network_error"
    if isinstance(exc, (OSError, requests.RequestException)): return "tls_network_error"
    return "network_error"


def _response_failure(status: int, headers: Mapping[str, str], prefix: bytes, size: int) -> str | None:
    text = prefix.lower()
    if status in {401, 403}: return "robots_or_anti_bot_block" if b"robot" in text or b"captcha" in text else "access_denied"
    if not 200 <= status < 300: return "access_denied" if status in {404, 410} else "network_error"
    detected_ct, _ = _sniff_media_type(_content_type(headers), prefix)
    if detected_ct not in {"application/pdf", "text/html", DISCOVERY_RSS_MEDIA_TYPE}: return "invalid_content_type"
    if not size or not _supported(_content_type(headers), prefix): return "empty_or_truncated_document"
    return None


def _cached(root: Path, records: Iterable[Mapping[str, Any]], ticker: str, url: str) -> Mapping[str, Any] | None:
    for record in reversed(list(records)):
        path = root / str(record.get("relative_path") or "")
        if record.get("ticker") == ticker and record.get("canonical_url") == url and path.is_file() and _sha_file(path) == record.get("sha256"): return record
    return None


def _extraction_state(path: Path) -> str:
    if path.suffix.lower() == ".xml": return "ready_for_discovery_parsing"
    if path.suffix.lower() == ".html": return "ready_for_direct_citations"
    try:
        from pypdf import PdfReader
        return "ready_for_direct_citations" if any((page.extract_text() or "").strip() for page in PdfReader(str(path)).pages) else "needs_ocr"
    except Exception: return "malformed_document"


def acquire(requests_: Iterable[Mapping[str, Any]], destination: Path, *, fetcher: Callable[..., tuple[Any, ...]] = fetch_http,
            timeout_seconds: int = READ_TIMEOUT_SECONDS, max_attempts: int = 2, observed_at: str | None = None,
            sleep: Callable[[float], None] = time.sleep, connect_timeout_seconds: int = CONNECT_TIMEOUT_SECONDS,
            max_response_bytes: int = MAX_RESPONSE_BYTES, registry: Mapping[str, Any] | None = None,
            clock: Callable[[], float] = time.monotonic,
            additional_allowed_tickers: Iterable[str] | None = None,
            refresh_index_pages: bool = False) -> dict[str, Any]:
    """Retain official documents, one request at a time, each admitted by the source registry.

    Nothing here reaches the network until `official_source_registry.admit()` has approved that
    exact source, host, document type and request interval. Until this milestone it never did:
    `admit()`'s only caller in the tree was the offline slice runner, so the owner-approved
    registry governed a JSON file and not a single request. A gate nothing calls is a comment.
    """
    if not 1 <= timeout_seconds <= 30 or not 1 <= max_attempts <= 2 or max_response_bytes < 1024: raise ValueError("bounded_retry_or_timeout_invalid")
    registry = registry if registry is not None else load_registry()
    allowed_types = declared_document_types(registry)
    additional_scope = _bounded_additional_ticker_scope(additional_allowed_tickers)
    allowed_tickers = frozenset({*TICKERS, *additional_scope})
    last_request_at: dict[str, float] = {}
    root = Path(destination); root.mkdir(parents=True, exist_ok=True); manifest_path = root / MANIFEST; records = _load(manifest_path)["records"]; outcomes = []
    initial_record_count = len(records)
    for spec in requests_:
        requested_ticker = str(spec.get("ticker", "")).upper()
        if (additional_allowed_tickers is not None and requested_ticker not in TICKERS
                and requested_ticker not in additional_scope):
            outcomes.append({"state": BOUNDED_ADDITIONAL_TICKER_SCOPE_EXCEEDED, "ticker": requested_ticker})
            continue
        try: ticker, document_class, period, url, source_id = _validate_spec(spec, allowed_types, allowed_tickers=allowed_tickers)
        except ValueError as exc: outcomes.append({"state": str(exc), "ticker": str(spec.get("ticker", "")).upper()}); continue
        cached = _cached(root, records, ticker, url)
        if cached and not (refresh_index_pages and document_class == "issuer_ir_index_page"):
            outcomes.append({"ticker": ticker, "document_id": cached["document_id"], "state": "cached_valid"}); continue
        # Honour the source's declared minimum interval before asking, so the rate rule shapes
        # the request rather than merely reporting on one already made.
        previous = last_request_at.get(source_id)
        elapsed = (clock() - previous) if previous is not None else None
        interval = _declared_interval(registry, source_id)
        if elapsed is not None and elapsed < interval: sleep(interval - elapsed); elapsed = interval
        decision = admit(source_id, url, document_class, registry=registry, seconds_since_last_request=elapsed)
        if decision["decision"] != ADMITTED:
            outcomes.append({"ticker": ticker, "canonical_url": url, "source_id": source_id,
                             "state": "refused_by_source_registry", "reason": decision["reason"],
                             "detail": decision["detail"]})
            continue
        last_request_at[source_id] = clock()
        # Every redirect hop is admitted before it is followed, against the same source. The
        # allowlist has to govern the host the bytes come from, not only the host a spec named.
        def _admit_hop(target: str, _source_id: str = source_id, _document_class: str = document_class) -> bool:
            return admit(_source_id, target, _document_class, registry=registry)["decision"] == ADMITTED
        fd, temp_name = tempfile.mkstemp(prefix=".download-", suffix=".part", dir=root); os.close(fd); temporary = Path(temp_name)
        status, headers, prefix, final_url, failure = 0, {}, b"", url, None
        for attempt in range(max_attempts):
            try:
                response = fetcher(url, temporary_path=temporary, timeout_seconds=timeout_seconds, connect_timeout_seconds=connect_timeout_seconds, max_response_bytes=max_response_bytes, admit_hop=_admit_hop, max_redirects=_declared_max_redirects(registry)) if fetcher is fetch_http else fetcher(url, timeout_seconds=timeout_seconds)
                status, headers, prefix = response[:3]; final_url = response[3] if len(response) > 3 else url
                if fetcher is not fetch_http: temporary.write_bytes(prefix)
                failure = None; break
            except Exception as exc:
                temporary.unlink(missing_ok=True); failure = _failure(exc)
                if failure in {"HTTP_REQUEST_CAP_REACHED", "STORAGE_BUDGET_REACHED"}:
                    break
                if attempt + 1 >= max_attempts: break
                # A retry is another request to the same host, so it waits out that source's
                # declared interval. Backing off 0.25s against a declared 10s minimum made the
                # retry path the one way to exceed the rate the registry publishes.
                remaining = interval - (clock() - last_request_at[source_id])
                sleep(max(0.25 * (2 ** attempt), remaining))
                last_request_at[source_id] = clock()
        size = temporary.stat().st_size if temporary.exists() else 0
        failure = failure or ("response_size_limit" if size > max_response_bytes else _response_failure(int(status), headers, prefix, size))
        if failure:
            temporary.unlink(missing_ok=True); outcomes.append({"ticker": ticker, "canonical_url": url, "state": failure, "http_status": status or None}); continue
        try: final_url = canonical_url(str(final_url))
        except ValueError:
            temporary.unlink(missing_ok=True); outcomes.append({"ticker": ticker, "canonical_url": url, "state": "unstable_redirect", "http_status": status}); continue
        # Defence in depth: `fetch_http` admits each hop before following it, but a caller may
        # supply any fetcher. Bytes are never promoted from a host the registry would refuse,
        # whoever fetched them.
        if final_url != url:
            landing = admit(source_id, final_url, document_class, registry=registry)
            if landing["decision"] != ADMITTED:
                temporary.unlink(missing_ok=True)
                outcomes.append({"ticker": ticker, "canonical_url": url, "final_url": final_url, "source_id": source_id,
                                 "state": "redirect_refused_by_source_registry", "reason": landing["reason"],
                                 "detail": landing["detail"], "http_status": status})
                continue
        raw_ct = _content_type(headers)
        detected_ct, detection_rationale = _sniff_media_type(raw_ct, prefix)
        sha256 = _sha_file(temporary)
        suffix = ".pdf" if detected_ct == "application/pdf" else ".xml" if detected_ct == DISCOVERY_RSS_MEDIA_TYPE else ".html"
        relative = Path("documents") / ticker / period / _safe(document_class) / f"{sha256}{suffix}"; path = root / relative; path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and _sha_file(path) != sha256:
            temporary.unlink(missing_ok=True); outcomes.append({"ticker": ticker, "canonical_url": url, "state": "hash_conflict", "http_status": status}); continue
        if not path.exists(): os.replace(temporary, path)
        else: temporary.unlink(missing_ok=True)
        document_id, prior = _document_id(ticker, url, sha256), [r for r in records if r.get("ticker") == ticker and r.get("canonical_url") == url]
        if any(r.get("document_id") == document_id for r in records):
            outcomes.append({"ticker": ticker, "document_id": document_id, "state": "cached_valid",
                             "refreshed_same_bytes": True})
            continue
        received_at = spec.get("observed_at") or observed_at or _now()
        qualified_official = (str(spec.get("qualification_state") or "").upper() == "QUALIFIED"
                              and str(spec.get("source_authority") or "").lower() in {"issuer_ir", "exchange"})
        temporal_retention = capture_raw_receipt(
            data=path.read_bytes(), raw_received_at=received_at, source_identity=source_id,
            provider_or_source=source_id, acquisition_method="GOVERNED_OFFICIAL_DOCUMENT_ACQUISITION_V1",
            source_published_at=spec.get("published_at"),
            publication_authority_tier=("OFFICIAL_ISSUER_IR_OR_EXCHANGE" if qualified_official else "UNVERIFIED"),
            http_headers=headers, content_type=detected_ct or raw_ct,
            warnings=[] if qualified_official else ["OFFICIAL_PUBLICATION_NOT_QUALIFIED"],
        )
        record = {"document_id": document_id, "ticker": ticker, "source_id": source_id,
                  "canonical_url": url, "final_url": final_url, "document_class": document_class,
                  "reporting_period": period, "published_at": spec.get("published_at"),
                  "observed_at": received_at,
                  "source_authority": spec.get("source_authority"),
                  "discovery_provenance": spec.get("discovery_provenance"),
                  "acquisition_status": "retained", "http_status": status,
                  "content_type": detected_ct or raw_ct,
                  "reported_content_type": raw_ct,
                  "media_type_detection_rationale": detection_rationale,
                  "content_length": path.stat().st_size,
                  "sha256": sha256, "relative_path": relative.as_posix(),
                  "supersedes_document_id": spec.get("supersedes_document_id") or (prior[-1].get("document_id") if prior else None),
                  "extraction_status": _extraction_state(path),
                  "temporal_retention": temporal_retention,
                  "a1_temporal_projection": project_retention_to_a1(temporal_retention)}
        records.append(record); outcomes.append({"ticker": ticker, "document_id": document_id, "state": "retained", "extraction_status": record["extraction_status"]})
    if len(records) != initial_record_count or not manifest_path.exists():
        _write_manifest(manifest_path, records)
    return {"schema_version": VERSION, "manifest": str(manifest_path), "outcomes": outcomes}


RETAINED_COPY_METHOD = "RETAINED_LOCAL_COPY_NO_NETWORK"


def adopt_retained_document_copy(source_root: Path, sha256: str, destination: Path, *, reporting_period: str,
                                 adopted_at: str, source_id: str = "issuer_ir",
                                 registry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Bind already retained official bytes to a body-proven period in another landing; no network.

    The document identity (ticker, canonical URL, SHA-256) and the original observation time
    are preserved, so the copy never claims a newer acquisition. Only the reporting-period
    binding, which the caller must have proven from the document body, is new. Calling it
    again for the same document is a manifest-byte no-op.
    """
    source_root, root = Path(source_root), Path(destination)
    # The source manifest is only read; an older schema stays as written.
    try: source_records = json.loads((source_root / MANIFEST).read_text(encoding="utf-8"))["records"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc: raise ValueError("manifest_malformed") from exc
    matches = [r for r in source_records if isinstance(r, dict) and r.get("sha256") == sha256]
    if len(matches) != 1 or matches[0].get("acquisition_status") != "retained":
        raise ValueError("RETAINED_DOCUMENT_NOT_UNIQUE")
    original = matches[0]
    source = source_root / str(original["relative_path"])
    if not source.is_file() or _sha_file(source) != sha256:
        raise ValueError("RETAINED_SOURCE_HASH_MISMATCH")
    registry = registry if registry is not None else load_registry()
    ticker, document_class, url = str(original.get("ticker") or "").upper(), str(original.get("document_class") or ""), canonical_url(str(original["canonical_url"]))
    if ticker not in TICKERS or reporting_period not in PERIODS or document_class not in declared_document_types(registry):
        raise ValueError("unsupported_request")
    for target in {url, canonical_url(str(original.get("final_url") or url))}:
        decision = admit(source_id, target, document_class, registry=registry)
        if decision["decision"] != ADMITTED:
            raise ValueError(f"refused_by_source_registry:{decision['reason']}")
    document_id = _document_id(ticker, url, sha256)
    if original.get("document_id") not in (None, document_id):
        raise ValueError("RETAINED_DOCUMENT_IDENTITY_MISMATCH")
    root.mkdir(parents=True, exist_ok=True)
    records = _load(root / MANIFEST)["records"]
    existing = next((r for r in records if r.get("document_id") == document_id), None)
    if existing is not None:
        if existing.get("reporting_period") != reporting_period or existing.get("sha256") != sha256:
            raise ValueError("RETAINED_COPY_BINDING_CONFLICT")
        return {"ticker": ticker, "document_id": document_id, "state": "cached_valid", "network_requests": 0}
    relative = Path("documents") / ticker / reporting_period / _safe(document_class) / f"{sha256}{source.suffix.lower()}"
    path = root / relative
    if path.exists() and _sha_file(path) != sha256:
        raise ValueError("hash_conflict")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, source.read_bytes())
    record = {key: original.get(key) for key in (
        "canonical_url", "final_url", "document_class", "published_at", "observed_at", "source_authority",
        "http_status", "content_type", "content_length", "sha256", "extraction_status")}
    record.update({"document_id": document_id, "ticker": ticker, "source_id": source_id, "reporting_period": reporting_period,
                   "acquisition_status": "retained", "relative_path": relative.as_posix(), "supersedes_document_id": None,
                   "retained_copy_provenance": {"method": RETAINED_COPY_METHOD, "network_requests": 0, "adopted_at": adopted_at,
                       "source_manifest_reporting_period": original.get("reporting_period"),
                       "source_relative_path": original.get("relative_path")}})
    records.append(record)
    _write_manifest(root / MANIFEST, records)
    return {"ticker": ticker, "document_id": document_id, "state": "retained", "network_requests": 0}


def _offline_content_type(path: Path, prefix: bytes) -> str:
    if path.suffix.lower() == ".pdf" and prefix.startswith(b"%PDF"): return "application/pdf"
    if path.suffix.lower() in {".html", ".htm"} and b"<html" in prefix.lower(): return "text/html"
    raise ValueError("unsupported_or_empty_local_document")


def import_offline_event(source_path: Path, destination: Path, metadata: Mapping[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    """Retain operator-supplied official bytes through the acquisition manifest only."""
    source_path = Path(source_path)
    if not source_path.is_file(): raise ValueError("local_document_missing")
    prefix = source_path.read_bytes()[:1024]
    content_type = _offline_content_type(source_path, prefix)
    required = ("ticker", "exchange", "action_type", "ex_date", "ratio", "ratio_basis", "source_authority", "source_url", "document_identity", "retrieved_at", "reporting_period")
    if any(not metadata.get(field) for field in required): raise ValueError("required_event_metadata_missing")
    ticker, exchange = str(metadata["ticker"]).upper(), str(metadata["exchange"])
    ratio = float(metadata["ratio"])
    if ticker not in TICKERS or exchange != "HOSE" or metadata["action_type"] not in {"stock_dividend", "bonus_share", "stock_split"} or ratio < .10 or metadata["ratio_basis"] != "new_shares_per_existing_share": raise ValueError("event_metadata_unqualified")
    url, sha256 = canonical_url(str(metadata["source_url"])), _sha_file(source_path)
    document_id = _document_id(ticker, url, sha256)
    evidence = {"citation_id": document_id, "document_sha256": sha256, "source_url": url}
    event = {"canonical_event_id": None, "ticker": ticker, "exchange": exchange, "event_type": metadata["action_type"], "ex_date": metadata["ex_date"], "entitlement_ratio": {"ratio_float": ratio}, "ratio_basis": metadata["ratio_basis"], "official_source_id": metadata.get("official_source_id") or url, "retrieved_at": metadata["retrieved_at"], "evidence": evidence, "qualified_for_price_basis_test": True, "qualified_for_share_transition": False, "provider_event_id": metadata.get("provider_event_id")}
    from price_basis_events import official_event_id
    event["canonical_event_id"] = official_event_id(event, ratio)
    root = Path(destination); root.mkdir(parents=True, exist_ok=True); manifest = _load(root / MANIFEST); records = manifest["records"]; existing = next((r for r in records if r.get("document_id") == document_id), None)
    event_path = root / EVENTS
    existing_events = [json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines() if line.strip()] if event_path.exists() else []
    conflicting = next((row for row in existing_events if row.get("canonical_event_id") == event["canonical_event_id"] and row != event), None)
    if conflicting: raise ValueError("offline_event_metadata_conflict")
    if dry_run: return {"state": "dry_run", "document_id": document_id, "canonical_event_id": event["canonical_event_id"], "content_type": content_type}
    if not existing:
        suffix = ".pdf" if content_type == "application/pdf" else ".html"; relative = Path("documents") / ticker / str(metadata["reporting_period"]) / "corporate_action_notice" / f"{sha256}{suffix}"; retained = root / relative; retained.parent.mkdir(parents=True, exist_ok=True)
        if retained.exists() and _sha_file(retained) != sha256: raise ValueError("hash_conflict")
        if not retained.exists(): _atomic_write(retained, source_path.read_bytes())
        temporal_retention = capture_raw_receipt(
            data=retained.read_bytes(), raw_received_at=metadata["retrieved_at"],
            source_identity=metadata.get("official_source_id") or url,
            provider_or_source=metadata.get("official_source_id") or "official_event",
            acquisition_method="OFFLINE_OFFICIAL_CORPORATE_EVENT_IMPORT_V1",
            source_published_at=metadata.get("published_at"),
            publication_authority_tier="UNVERIFIED",
            content_type=content_type,
            warnings=["OFFLINE_EVENT_PUBLICATION_NOT_SEMANTICALLY_QUALIFIED"],
        )
        records.append({"document_id": document_id, "document_identity": metadata["document_identity"], "ticker": ticker, "canonical_url": url, "final_url": url, "document_class": "corporate_action_notice", "reporting_period": str(metadata["reporting_period"]), "published_at": metadata.get("published_at"), "observed_at": metadata["retrieved_at"], "source_authority": metadata["source_authority"], "acquisition_status": "retained", "http_status": None, "content_type": content_type, "content_length": retained.stat().st_size, "sha256": sha256, "relative_path": relative.as_posix(), "supersedes_document_id": None, "extraction_status": _extraction_state(retained), "temporal_retention": temporal_retention, "a1_temporal_projection": project_retention_to_a1(temporal_retention)})
        _write_manifest(root / MANIFEST, records)
    if not any(row.get("canonical_event_id") == event["canonical_event_id"] for row in existing_events):
        _atomic_write(event_path, ("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in [*existing_events, event]) + "\n").encode("utf-8"))
    return {"state": "retained" if not existing else "cached_valid", "document_id": document_id, "canonical_event_id": event["canonical_event_id"], "content_type": content_type}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--file", type=Path, required=True); parser.add_argument("--destination", type=Path, required=True); parser.add_argument("--metadata", type=Path, required=True); parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv); metadata = json.loads(args.metadata.read_text(encoding="utf-8")); print(json.dumps(import_offline_event(args.file, args.destination, metadata, dry_run=args.dry_run), sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
