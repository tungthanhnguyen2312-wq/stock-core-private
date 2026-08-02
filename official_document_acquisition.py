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

VERSION = "1.1.0"
MANIFEST = "official_document_acquisition_manifest.json"
EVENTS = "official_price_test_events.jsonl"
TICKERS = frozenset({"HPG", "VNM", "VCB", "SSI", "PAN"})
DOCUMENT_CLASSES = ("audited_annual_financial_statements", "annual_report", "agm_document_or_resolution", "corporate_action_notice", "amendment_or_supersession_notice")
PERIODS = frozenset({"2023", "2024", "2025", "2026"})
CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS, MAX_RESPONSE_BYTES = 5, 15, 20 * 1024 * 1024
REQUEST_HEADERS = {"Accept": "application/pdf,text/html;q=0.9", "User-Agent": "StockLookupOfficialEvidence/1.1"}


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
def _supported(content_type: str, prefix: bytes) -> bool: return (content_type == "application/pdf" and prefix.startswith(b"%PDF")) or (content_type == "text/html" and b"<html" in prefix.lower())


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


def _validate_spec(spec: Mapping[str, Any]) -> tuple[str, str, str, str]:
    ticker, document_class, period = str(spec.get("ticker", "")).upper(), str(spec.get("document_class", "")), str(spec.get("reporting_period", ""))
    if ticker not in TICKERS or document_class not in DOCUMENT_CLASSES or period not in PERIODS: raise ValueError("unsupported_request")
    return ticker, document_class, period, canonical_url(str(spec.get("canonical_url", "")))


def fetch_http(url: str, *, temporary_path: Path, timeout_seconds: int = READ_TIMEOUT_SECONDS,
               connect_timeout_seconds: int = CONNECT_TIMEOUT_SECONDS, max_response_bytes: int = MAX_RESPONSE_BYTES) -> tuple[int, Mapping[str, str], bytes, str]:
    """Stream one response to caller-owned temporary storage; never promote it."""
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=(connect_timeout_seconds, timeout_seconds), allow_redirects=True, stream=True)
    if len(response.history) > 5: raise ValueError("unstable_redirect")
    headers, status = dict(response.headers.items()), response.status_code
    length = response.headers.get("Content-Length")
    if length and int(length) > max_response_bytes: raise ValueError("response_size_limit")
    prefix = bytearray()
    if not 200 <= status < 300:
        for chunk in response.iter_content(chunk_size=1024): prefix.extend(chunk); break
        return status, headers, bytes(prefix), response.url
    if _content_type(headers) not in {"application/pdf", "text/html"}: return status, headers, b"", response.url
    total = 0
    try:
        with temporary_path.open("wb") as out:
            for chunk in response.iter_content(chunk_size=65536):
                total += len(chunk)
                if total > max_response_bytes: raise ValueError("response_size_limit")
                if len(prefix) < 1024: prefix.extend(chunk[:1024-len(prefix)])
                out.write(chunk)
        return status, headers, bytes(prefix), response.url
    except Exception:
        temporary_path.unlink(missing_ok=True); raise


def _failure(exc: Exception) -> str:
    if isinstance(exc, (TimeoutError, requests.Timeout)): return "timeout"
    if isinstance(exc, ValueError) and str(exc) in {"unstable_redirect", "response_size_limit"}: return str(exc)
    if isinstance(exc, requests.SSLError): return "tls_network_error"
    if isinstance(exc, (OSError, requests.RequestException)): return "tls_network_error"
    return "network_error"


def _response_failure(status: int, headers: Mapping[str, str], prefix: bytes, size: int) -> str | None:
    text = prefix.lower()
    if status in {401, 403}: return "robots_or_anti_bot_block" if b"robot" in text or b"captcha" in text else "access_denied"
    if not 200 <= status < 300: return "access_denied" if status in {404, 410} else "network_error"
    if _content_type(headers) not in {"application/pdf", "text/html"}: return "invalid_content_type"
    if not size or not _supported(_content_type(headers), prefix): return "empty_or_truncated_document"
    return None


def _cached(root: Path, records: Iterable[Mapping[str, Any]], ticker: str, url: str) -> Mapping[str, Any] | None:
    for record in reversed(list(records)):
        path = root / str(record.get("relative_path") or "")
        if record.get("ticker") == ticker and record.get("canonical_url") == url and path.is_file() and _sha_file(path) == record.get("sha256"): return record
    return None


def _extraction_state(path: Path) -> str:
    if path.suffix.lower() == ".html": return "ready_for_direct_citations"
    try:
        from pypdf import PdfReader
        return "ready_for_direct_citations" if any((page.extract_text() or "").strip() for page in PdfReader(str(path)).pages) else "needs_ocr"
    except Exception: return "malformed_document"


def acquire(requests_: Iterable[Mapping[str, Any]], destination: Path, *, fetcher: Callable[..., tuple[Any, ...]] = fetch_http,
            timeout_seconds: int = READ_TIMEOUT_SECONDS, max_attempts: int = 2, observed_at: str | None = None,
            sleep: Callable[[float], None] = time.sleep, connect_timeout_seconds: int = CONNECT_TIMEOUT_SECONDS,
            max_response_bytes: int = MAX_RESPONSE_BYTES) -> dict[str, Any]:
    if not 1 <= timeout_seconds <= 30 or not 1 <= max_attempts <= 2 or max_response_bytes < 1024: raise ValueError("bounded_retry_or_timeout_invalid")
    root = Path(destination); root.mkdir(parents=True, exist_ok=True); manifest_path = root / MANIFEST; records = _load(manifest_path)["records"]; outcomes = []
    for spec in requests_:
        try: ticker, document_class, period, url = _validate_spec(spec)
        except ValueError as exc: outcomes.append({"state": str(exc), "ticker": str(spec.get("ticker", "")).upper()}); continue
        cached = _cached(root, records, ticker, url)
        if cached: outcomes.append({"ticker": ticker, "document_id": cached["document_id"], "state": "cached_valid"}); continue
        fd, temp_name = tempfile.mkstemp(prefix=".download-", suffix=".part", dir=root); os.close(fd); temporary = Path(temp_name)
        status, headers, prefix, final_url, failure = 0, {}, b"", url, None
        for attempt in range(max_attempts):
            try:
                response = fetcher(url, temporary_path=temporary, timeout_seconds=timeout_seconds, connect_timeout_seconds=connect_timeout_seconds, max_response_bytes=max_response_bytes) if fetcher is fetch_http else fetcher(url, timeout_seconds=timeout_seconds)
                status, headers, prefix = response[:3]; final_url = response[3] if len(response) > 3 else url
                if fetcher is not fetch_http: temporary.write_bytes(prefix)
                failure = None; break
            except Exception as exc:
                temporary.unlink(missing_ok=True); failure = _failure(exc)
                if attempt + 1 < max_attempts: sleep(0.25 * (2 ** attempt))
        size = temporary.stat().st_size if temporary.exists() else 0
        failure = failure or ("response_size_limit" if size > max_response_bytes else _response_failure(int(status), headers, prefix, size))
        if failure:
            temporary.unlink(missing_ok=True); outcomes.append({"ticker": ticker, "canonical_url": url, "state": failure, "http_status": status or None}); continue
        try: final_url = canonical_url(str(final_url))
        except ValueError:
            temporary.unlink(missing_ok=True); outcomes.append({"ticker": ticker, "canonical_url": url, "state": "unstable_redirect", "http_status": status}); continue
        sha256 = _sha_file(temporary); suffix = ".pdf" if _content_type(headers) == "application/pdf" else ".html"; relative = Path("documents") / ticker / period / _safe(document_class) / f"{sha256}{suffix}"; path = root / relative; path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and _sha_file(path) != sha256:
            temporary.unlink(missing_ok=True); outcomes.append({"ticker": ticker, "canonical_url": url, "state": "hash_conflict", "http_status": status}); continue
        if not path.exists(): os.replace(temporary, path)
        else: temporary.unlink(missing_ok=True)
        document_id, prior = _document_id(ticker, url, sha256), [r for r in records if r.get("ticker") == ticker and r.get("canonical_url") == url]
        record = {"document_id": document_id, "ticker": ticker, "canonical_url": url, "final_url": final_url, "document_class": document_class, "reporting_period": period, "published_at": spec.get("published_at"), "observed_at": spec.get("observed_at") or observed_at or _now(), "source_authority": spec.get("source_authority"), "acquisition_status": "retained", "http_status": status, "content_type": _content_type(headers), "content_length": path.stat().st_size, "sha256": sha256, "relative_path": relative.as_posix(), "supersedes_document_id": spec.get("supersedes_document_id") or (prior[-1].get("document_id") if prior else None), "extraction_status": _extraction_state(path)}
        records.append(record); outcomes.append({"ticker": ticker, "document_id": document_id, "state": "retained", "extraction_status": record["extraction_status"]})
    _write_manifest(manifest_path, records)
    return {"schema_version": VERSION, "manifest": str(manifest_path), "outcomes": outcomes}


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
        records.append({"document_id": document_id, "document_identity": metadata["document_identity"], "ticker": ticker, "canonical_url": url, "final_url": url, "document_class": "corporate_action_notice", "reporting_period": str(metadata["reporting_period"]), "published_at": metadata.get("published_at"), "observed_at": metadata["retrieved_at"], "source_authority": metadata["source_authority"], "acquisition_status": "retained", "http_status": None, "content_type": content_type, "content_length": retained.stat().st_size, "sha256": sha256, "relative_path": relative.as_posix(), "supersedes_document_id": None, "extraction_status": _extraction_state(retained)})
        _write_manifest(root / MANIFEST, records)
    if not any(row.get("canonical_event_id") == event["canonical_event_id"] for row in existing_events):
        _atomic_write(event_path, ("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in [*existing_events, event]) + "\n").encode("utf-8"))
    return {"state": "retained" if not existing else "cached_valid", "document_id": document_id, "canonical_event_id": event["canonical_event_id"], "content_type": content_type}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--file", type=Path, required=True); parser.add_argument("--destination", type=Path, required=True); parser.add_argument("--metadata", type=Path, required=True); parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv); metadata = json.loads(args.metadata.read_text(encoding="utf-8")); print(json.dumps(import_offline_event(args.file, args.destination, metadata, dry_run=args.dry_run), sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
