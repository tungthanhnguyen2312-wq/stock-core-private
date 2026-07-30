"""Bounded, append-only acquisition of explicitly named official documents.

This Producer-only helper never crawls, creates financial observations, or writes
to a runtime root.  Callers supply a small list of canonical URLs and an explicit
destination owned by their pilot.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

VERSION = "1.0.0"
TICKERS = frozenset({"HPG", "VNM", "VCB", "SSI", "PAN"})
DOCUMENT_CLASSES = (
    "audited_annual_financial_statements", "annual_report", "agm_document_or_resolution",
    "corporate_action_notice", "amendment_or_supersession_notice",
)
PERIODS = frozenset({"2024", "2025"})
MANIFEST = "official_document_acquisition_manifest.json"


def canonical_url(url: str) -> str:
    """Normalize only URL identity; never discover or follow a different source."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("unsupported_url")
    query = urllib.parse.urlencode(sorted(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)))
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", query, ""))


def _sha(value: bytes) -> str: return hashlib.sha256(value).hexdigest()
def _document_id(ticker: str, url: str, sha256: str) -> str: return hashlib.sha256(f"{ticker}|{url}|{sha256}".encode()).hexdigest()
def _safe(value: str) -> str: return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")
def _now() -> str: return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load(path: Path) -> dict[str, Any]:
    if not path.exists(): return {"schema_version": VERSION, "records": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("manifest_malformed") from exc
    if data.get("schema_version") != VERSION or not isinstance(data.get("records"), list):
        raise ValueError("manifest_unsupported")
    return data


def _write_manifest(path: Path, records: list[dict[str, Any]]) -> None:
    payload = {"schema_version": VERSION, "records": records}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _validate(spec: Mapping[str, Any]) -> tuple[str, str, str, str]:
    ticker = str(spec.get("ticker", "")).upper()
    document_class = str(spec.get("document_class", ""))
    period = str(spec.get("reporting_period", ""))
    if ticker not in TICKERS or document_class not in DOCUMENT_CLASSES or period not in PERIODS:
        raise ValueError("unsupported_request")
    return ticker, document_class, period, canonical_url(str(spec.get("canonical_url", "")))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def fetch_http(url: str, *, timeout_seconds: int) -> tuple[int, Mapping[str, str], bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": "StockLookupOfficialEvidence/1.0"})
    opener = urllib.request.build_opener(_NoRedirect)
    with opener.open(request, timeout=timeout_seconds) as response:  # nosec B310: explicit caller source
        return int(response.status), dict(response.headers.items()), response.read()


def _extraction_state(path: Path) -> str:
    """Return a handoff state only. Direct citations remain mandatory for retrieval."""
    if path.suffix.lower() != ".pdf": return "unsupported_document"
    try:
        from pypdf import PdfReader
        pages = PdfReader(str(path)).pages
        return "ready_for_direct_citations" if any((page.extract_text() or "").strip() for page in pages) else "needs_ocr"
    except Exception:
        return "malformed_document"


def acquire(
    requests: Iterable[Mapping[str, Any]], destination: Path, *,
    fetcher: Callable[..., tuple[int, Mapping[str, str], bytes]] = fetch_http,
    timeout_seconds: int = 20, max_attempts: int = 2, observed_at: str | None = None,
    local_idempotency_only: bool = False,
) -> dict[str, Any]:
    """Acquire a finite explicit list, version bytes by hash, and append records only."""
    if not 1 <= timeout_seconds <= 30 or not 1 <= max_attempts <= 3: raise ValueError("bounded_retry_or_timeout_invalid")
    root = Path(destination); root.mkdir(parents=True, exist_ok=True); manifest_path = root / MANIFEST
    manifest = _load(manifest_path); records: list[dict[str, Any]] = manifest["records"]
    outcomes: list[dict[str, Any]] = []
    for spec in requests:
        try: ticker, document_class, period, url = _validate(spec)
        except ValueError as exc:
            outcomes.append({"state": str(exc), "ticker": str(spec.get("ticker", "")).upper()}); continue
        prior = [r for r in records if r.get("ticker") == ticker and r.get("canonical_url") == url]
        if local_idempotency_only:
            existing = next((r for r in reversed(prior) if (root / str(r.get("relative_path") or "")).is_file() and _sha((root / str(r["relative_path"])).read_bytes()) == r.get("sha256")), None)
            if existing:
                outcomes.append({"ticker": ticker, "document_id": existing["document_id"], "state": "skipped_idempotent", "local_hash_verified": True})
                continue
        status, headers, body, error = 0, {}, b"", None
        for attempt in range(max_attempts):
            try:
                status, headers, body = fetcher(url, timeout_seconds=timeout_seconds); break
            except (OSError, urllib.error.URLError, TimeoutError) as exc:
                error = type(exc).__name__
        if not body or status < 200 or status >= 300:
            outcomes.append({"ticker": ticker, "canonical_url": url, "state": "inaccessible", "http_status": status or None, "error": error}); continue
        content_type = str(headers.get("Content-Type") or headers.get("content-type") or "").split(";", 1)[0].lower()
        if content_type != "application/pdf" or not body.startswith(b"%PDF"):
            outcomes.append({"ticker": ticker, "canonical_url": url, "state": "malformed", "http_status": status, "content_type": content_type}); continue
        sha256 = _sha(body); existing = next((r for r in prior if r.get("sha256") == sha256), None)
        if existing:
            outcomes.append({"ticker": ticker, "document_id": existing["document_id"], "state": "skipped_idempotent"}); continue
        document_id = _document_id(ticker, url, sha256)
        relative = Path("documents") / ticker / period / _safe(document_class) / f"{sha256}.pdf"
        path = root / relative; path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != body: raise ValueError("immutable_path_conflict")
        if not path.exists(): path.write_bytes(body)
        supersedes = spec.get("supersedes_document_id") or (prior[-1].get("document_id") if prior else None)
        record = {"document_id": document_id, "ticker": ticker, "canonical_url": url, "document_class": document_class,
                  "reporting_period": period, "published_at": spec.get("published_at"), "observed_at": spec.get("observed_at") or observed_at or _now(),
                  "source_authority": spec.get("source_authority"), "acquisition_status": "retained", "http_status": status,
                  "content_type": content_type, "content_length": len(body), "sha256": sha256, "relative_path": relative.as_posix(),
                  "supersedes_document_id": supersedes, "extraction_status": "pending"}
        record["extraction_status"] = _extraction_state(path)
        records.append(record); outcomes.append({"ticker": ticker, "document_id": document_id, "state": "retained", "version": len(prior) + 1, "extraction_status": record["extraction_status"]})
    _write_manifest(manifest_path, records)
    return {"schema_version": VERSION, "manifest": str(manifest_path), "outcomes": outcomes, "coverage_matrix": coverage_matrix(records)}


def coverage_matrix(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for ticker in sorted(TICKERS):
        for document_class in DOCUMENT_CLASSES:
            relevant = [r for r in records if r.get("ticker") == ticker and r.get("document_class") == document_class]
            rows.append({"ticker": ticker, "document_class": document_class, "state": "retained" if relevant else "missing", "document_ids": [r["document_id"] for r in relevant]})
    return rows


def retrieval_handoff(destination: Path) -> list[dict[str, Any]]:
    """Expose retained documents to the cited-retrieval intake; no citation or fact is invented."""
    root = Path(destination); records = _load(root / MANIFEST)["records"]
    return [{"document_id": r["document_id"], "ticker": r["ticker"], "reporting_period": r["reporting_period"], "sha256": r["sha256"],
             "relative_path": r["relative_path"], "state": r["extraction_status"], "citation_status": "direct_citation_metadata_required",
             "canonical_observation_status": "not_created"} for r in records if r.get("acquisition_status") == "retained"]
