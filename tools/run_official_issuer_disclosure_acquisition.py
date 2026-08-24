"""OFFICIAL_ISSUER_DISCLOSURE_AND_GOVERNANCE_DATA_V1 -- bounded pilot + scale-out runner.

Foreground, single-threaded, one process. Phases:

  1. Fetch and retain the one approved HNX issuer-disclosure RSS feed (a discovery input,
     never evidence -- retained separately from `official_document_store`, exactly as VSDC's
     announcement index page is).
  2. Parse it into a candidate ledger (`hnx_disclosure_feed_parser.parse_disclosure_rss`);
     every item gets a disposition, not only the ones this pilot goes on to fetch.
  3. Acquire a bounded, deterministic (feed-order, capped) subset of candidate detail pages
     through the same governed `admit()` gate and `fetch_http` primitive every other source in
     this repository uses, retaining each into `official_document_store` under its real
     evidence document_type.
  4. Deterministically extract structured fields and typed observations from every retained
     detail page.
  5. Run the audit-opinion classifier over the existing retained
     `audited_annual_financial_statements` / `reviewed_interim_financial_statements` corpus
     (read-only; no new acquisition for that document class in this run).
  6. Project everything -- the new documents and, read-only, the pre-existing
     `governed-official-evidence-v1` corpus -- through `official_issuer_disclosure_registry`
     into one deterministic registry artifact, with coverage and conflict accounting.

Nothing here writes to git, publishes, or mutates production state. Output lands under
`operations-review/<run-id>/`, which is gitignored, exactly like every other evidence pilot in
this repository.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

import audit_opinion_evidence as audit_opinion  # noqa: E402
import hnx_disclosure_feed_parser as feed_parser  # noqa: E402
import insider_and_major_holder_events as events  # noqa: E402
import official_document_store as store  # noqa: E402
import official_issuer_disclosure_registry as disclosure_registry  # noqa: E402
import official_source_registry as registry_module  # noqa: E402
from atomic_io import atomic_write_file, atomic_write_json  # noqa: E402
from official_document_acquisition import fetch_http  # noqa: E402
from official_source_registry import ADMITTED, admit  # noqa: E402

SOURCE_ID = "hnx"
FEED_DOCUMENT_TYPE = "disclosure_rss_feed"
FEED_URL = "https://www.hnx.vn/vi-vn/3/vi_vn/thong-tin-cong-bo-tu-to-chuc-phat-hanh.rss"
MAX_DETAIL_DOCUMENTS = 20
EXISTING_EVIDENCE_MANIFEST = ROOT / "operations-review" / "governed-official-evidence-v1" / "official_document_acquisition_manifest.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_bytes(payload: bytes) -> str:
    import hashlib
    return hashlib.sha256(payload).hexdigest()


class RateLimiter:
    """Single-source minimum-interval pacing, foreground `time.sleep`, no concurrency."""

    def __init__(self, registry: dict[str, Any]):
        self._registry = registry
        self._last: dict[str, float] = {}

    def wait(self, source_id: str) -> float | None:
        interval = 0.0
        for source in self._registry.get("sources") or []:
            if str(source.get("source_id")) == source_id:
                interval = float(source.get("min_request_interval_seconds") or 0.0)
        previous = self._last.get(source_id)
        elapsed = (time.monotonic() - previous) if previous is not None else None
        if elapsed is not None and elapsed < interval:
            time.sleep(interval - elapsed)
            elapsed = interval
        self._last[source_id] = time.monotonic()
        return elapsed


def fetch_feed_bytes(url: str, document_type: str, *, registry: dict[str, Any],
                     limiter: RateLimiter) -> dict[str, Any]:
    """A bounded, `admit()`-gated GET for the one RSS discovery input.

    `official_document_acquisition.fetch_http` is deliberately scoped to PDF/HTML (the only
    two media types `official_document_store` ever promotes), so it silently declines to write
    an `application/rss+xml` body to disk. This mirrors its safety properties -- registry
    admission before the request and before every redirect hop, the registry's own timeouts
    and response-size ceiling -- for the one additional media type this pilot's discovery input
    actually needs, without changing what `fetch_http` accepts for every other caller.
    """
    policy = (registry.get("global_policy") or {})
    max_bytes = int(policy.get("max_response_bytes") or 33554432)
    connect_s, read_s = int(policy.get("connect_timeout_seconds") or 5), int(policy.get("read_timeout_seconds") or 15)
    headers = {"Accept": "application/rss+xml,application/xml,text/xml;q=0.9",
              "User-Agent": policy.get("user_agent") or "StockLookupOfficialEvidence/1.1"}
    current, hops = url, 0
    max_redirects = int(policy.get("max_redirects") or 5)
    elapsed = limiter.wait(SOURCE_ID)
    decision = admit(SOURCE_ID, current, document_type, registry=registry, seconds_since_last_request=elapsed)
    if decision["decision"] != ADMITTED:
        return {"state": "refused_by_source_registry", "reason": decision["reason"], "url": current}
    while hops <= max_redirects:
        try:
            response = requests.get(current, headers=headers, timeout=(connect_s, read_s),
                                    allow_redirects=False, stream=True)
        except requests.RequestException as exc:
            return {"state": "fetch_failed", "reason": type(exc).__name__ + ":" + str(exc), "url": current}
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            response.close()
            if not location:
                return {"state": "unstable_redirect", "url": current}
            target = urllib.parse.urljoin(current, location)
            hop_decision = admit(SOURCE_ID, target, document_type, registry=registry)
            if hop_decision["decision"] != ADMITTED:
                return {"state": "redirect_refused_by_source_registry", "reason": hop_decision["reason"], "url": target}
            current, hops = target, hops + 1
            continue
        if not 200 <= response.status_code < 300:
            status = response.status_code
            response.close()
            return {"state": "http_error", "http_status": status, "url": current}
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > max_bytes:
            response.close()
            return {"state": "response_size_limit", "url": current}
        body = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            body.extend(chunk)
            if len(body) > max_bytes:
                response.close()
                return {"state": "response_size_limit", "url": current}
        if not body:
            return {"state": "empty_response", "http_status": response.status_code, "url": current}
        return {"state": "retained", "http_status": response.status_code, "final_url": current,
               "content_type": response.headers.get("Content-Type"), "body": bytes(body)}
    return {"state": "unstable_redirect", "url": current}


def fetch_admitted(url: str, document_type: str, *, registry: dict[str, Any], limiter: RateLimiter,
                   temp_path: Path) -> dict[str, Any]:
    elapsed = limiter.wait(SOURCE_ID)
    decision = admit(SOURCE_ID, url, document_type, registry=registry, seconds_since_last_request=elapsed)
    if decision["decision"] != ADMITTED:
        return {"state": "refused_by_source_registry", "reason": decision["reason"], "url": url}

    def _admit_hop(target: str) -> bool:
        return admit(SOURCE_ID, target, document_type, registry=registry)["decision"] == ADMITTED

    try:
        status, headers, prefix, final_url = fetch_http(url, temporary_path=temp_path, admit_hop=_admit_hop)
    except Exception as exc:  # noqa: BLE001 - every failure mode is a recorded disposition
        return {"state": "fetch_failed", "reason": type(exc).__name__ + ":" + str(exc), "url": url}
    if not 200 <= status < 300:
        return {"state": "http_error", "http_status": status, "url": url}
    if not temp_path.exists() or temp_path.stat().st_size == 0:
        return {"state": "empty_response", "http_status": status, "url": url}
    return {"state": "retained", "http_status": status, "final_url": final_url,
           "content_type": headers.get("Content-Type") or headers.get("content-type")}


def run(destination: Path, *, max_detail_documents: int = MAX_DETAIL_DOCUMENTS) -> dict[str, Any]:
    registry = registry_module.load_registry()
    destination.mkdir(parents=True, exist_ok=True)
    raw_dir = destination / "raw-feed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    store_root = destination / "store"
    limiter = RateLimiter(registry)
    log: list[dict[str, Any]] = []

    # --- Phase 1+2: the one RSS feed, retained as a discovery input, never as evidence. ---
    feed_outcome = fetch_feed_bytes(FEED_URL, FEED_DOCUMENT_TYPE, registry=registry, limiter=limiter)
    log.append({"phase": "fetch_feed", **{k: v for k, v in feed_outcome.items() if k != "body"}})
    if feed_outcome["state"] != "retained":
        raise SystemExit(f"feed acquisition failed: {feed_outcome}")
    feed_bytes = feed_outcome["body"]
    feed_sha256 = _sha256_bytes(feed_bytes)
    feed_path = raw_dir / f"{feed_sha256}.rss"
    if not feed_path.exists():
        atomic_write_file(feed_path, feed_bytes)
    atomic_write_json(raw_dir / "feed_retention_record.json", {
        "source_id": SOURCE_ID, "document_type": FEED_DOCUMENT_TYPE, "source_url": FEED_URL,
        "final_url": feed_outcome.get("final_url"), "content_sha256": feed_sha256,
        "content_length": len(feed_bytes), "retrieved_at": _now(),
        "relative_path": str(feed_path.relative_to(destination).as_posix()),
    })

    parsed_feed = feed_parser.parse_disclosure_rss(feed_bytes, feed_url=FEED_URL, source_id=SOURCE_ID,
                                                    registry=registry)
    atomic_write_json(destination / "feed_parse_ledger.json", parsed_feed)

    # --- Phase 3+4: bounded, deterministic (feed order) acquisition of candidate detail pages. ---
    candidates = [row for row in parsed_feed["items"] if row.get("state") == "candidate"][:max_detail_documents]
    disclosure_records: list[dict[str, Any]] = []
    insider_observations: list[dict[str, Any]] = []
    major_holder_observations: list[dict[str, Any]] = []
    fetch_failures: list[dict[str, Any]] = []

    for candidate in candidates:
        url, document_type = candidate["canonical_url"], candidate["document_class"]
        detail_temp = raw_dir / ".detail.part"
        outcome = fetch_admitted(url, document_type, registry=registry, limiter=limiter, temp_path=detail_temp)
        log.append({"phase": "fetch_detail", "url": url, **outcome})
        if outcome["state"] != "retained":
            fetch_failures.append({"url": url, **outcome})
            detail_temp.unlink(missing_ok=True)
            continue
        ticker_guess = "MULTI"  # real ticker is read from the document body, not assumed here
        adopted = store.adopt_retained_document(
            store_root, detail_temp, ticker=ticker_guess, document_type=document_type,
            source_url=url, source_authority=registry_module.source_index(registry)[SOURCE_ID]["authority"],
            observed_at=_now(), published_at=candidate.get("pub_date_raw"), execute=True)
        detail_temp.unlink(missing_ok=True)
        manifest_record = dict(adopted["record"])
        payload = store.read_document(store_root, manifest_record["document_id"])
        detail = feed_parser.parse_disclosure_detail(payload, url=url)

        # A document is stored under the coarse type its RSS title implied; if the body's own
        # ticker differs from the placeholder used for the store path, correct the manifest's
        # `ticker` field so downstream projection reads the real, page-observed identity -- the
        # store path key is a filing bucket, not itself evidence.
        if detail.get("ticker"):
            manifest_record["ticker"] = detail["ticker"]

        if document_type == feed_parser.INSIDER_TYPE:
            observation = events.build_insider_transaction_observation(
                document_id=manifest_record["document_id"], content_sha256=manifest_record["content_sha256"],
                source_url=url, published_at=detail.get("published_at_raw"), detail=detail)
            insider_observations.append(observation)
        else:
            observation = events.build_major_holder_observation(
                document_id=manifest_record["document_id"], content_sha256=manifest_record["content_sha256"],
                source_url=url, published_at=detail.get("published_at_raw"), detail=detail)
            major_holder_observations.append(observation)

        record = disclosure_registry.project_disclosure_record(
            manifest_record=manifest_record, source_id=SOURCE_ID, detail=detail,
            observation_state=observation["state"], observation_warnings=observation["warnings"])
        disclosure_records.append(record)

    # --- Phase 5: audit-opinion classification over the pre-existing retained filing corpus. ---
    audit_evaluations: list[dict[str, Any]] = []
    existing_records: list[dict[str, Any]] = []
    if EXISTING_EVIDENCE_MANIFEST.is_file():
        existing_manifest = json.loads(EXISTING_EVIDENCE_MANIFEST.read_text(encoding="utf-8"))
        existing_root = EXISTING_EVIDENCE_MANIFEST.parent
        for rec in existing_manifest.get("records", []):
            existing_records.append(rec)
            if rec.get("document_class") in {"audited_annual_financial_statements",
                                             "reviewed_interim_financial_statements"}:
                doc_path = existing_root / str(rec["relative_path"])
                page_texts: list[str] = []
                if rec.get("extraction_status") == "ready_for_direct_citations" and doc_path.is_file():
                    from pypdf import PdfReader
                    try:
                        page_texts = [(p.extract_text() or "") for p in PdfReader(str(doc_path)).pages]
                    except Exception:  # noqa: BLE001 - a malformed PDF is a recorded state
                        page_texts = []
                audit_evaluations.append(audit_opinion.evaluate_document(
                    document_id=rec["document_id"], content_sha256=rec["sha256"], ticker=rec["ticker"],
                    reporting_period=rec.get("reporting_period", ""), document_type=rec["document_class"],
                    parser_status=rec.get("extraction_status", "not_assessed"), page_texts=page_texts))

    # --- Phase 6: project the pre-existing corpus into the same registry shape (read-only). ---
    host_to_source = {}
    for source in registry.get("sources") or []:
        for host in source.get("allowed_hosts") or []:
            host_to_source[str(host).lower()] = source["source_id"]
    existing_projected: list[dict[str, Any]] = []
    for rec in existing_records:
        url = rec.get("canonical_url") or rec.get("source_url") or ""
        host = registry_module.canonical_host(url) or ""
        source_id = host_to_source.get(host, "issuer_ir")
        normalized = dict(rec)
        normalized.setdefault("document_type", rec.get("document_class"))
        normalized.setdefault("content_sha256", rec.get("sha256"))
        existing_projected.append(disclosure_registry.project_disclosure_record(
            manifest_record=normalized, source_id=source_id, detail=None))

    all_records = disclosure_records + existing_projected
    observation_by_id = {o["document_id"]: o for o in insider_observations + major_holder_observations}
    conflicts = disclosure_registry.detect_conflicts(disclosure_records, observation_by_id)

    coverage = disclosure_registry.coverage_report(
        universe_count=1683, source_visible_issuers=len({r["ticker"] for r in disclosure_records if r.get("ticker")}),
        disclosure_records=all_records, insider_observations=insider_observations,
        major_holder_observations=major_holder_observations, audit_evaluations=audit_evaluations,
        unavailable=len(fetch_failures), source_rejected=sum(1 for r in log if r.get("state") == "refused_by_source_registry"),
        parse_blocked=sum(1 for r in disclosure_records if r.get("parse_status") == "needs_ocr"),
        semantic_blocked=sum(1 for o in insider_observations + major_holder_observations
                             if o["state"] in {events.UNKNOWN, events.UNKNOWN_MAJOR_HOLDER_EVENT}))

    artifact = {
        "schema_version": "1.0.0",
        "run_id": destination.name,
        "generated_at": _now(),
        "feed": {"source_id": SOURCE_ID, "url": FEED_URL, "sha256": feed_sha256,
                "item_count": parsed_feed["item_count"], "candidate_count": parsed_feed["candidate_count"],
                "out_of_scope_count": parsed_feed["out_of_scope_count"]},
        "candidates_attempted": len(candidates), "fetch_failures": fetch_failures,
        "disclosure_records": disclosure_records,
        "existing_corpus_projected_count": len(existing_projected),
        "insider_observations": insider_observations,
        "major_holder_observations": major_holder_observations,
        "audit_opinion_evaluations": audit_evaluations,
        "conflicts": conflicts,
        "coverage": coverage,
        "log": log,
    }
    atomic_write_json(destination / "official_issuer_disclosure_artifact.json", artifact)
    verification = store.verify(store_root)
    atomic_write_json(destination / "store_self_verification.json", verification)
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path,
                        default=ROOT / "operations-review" / "official-issuer-disclosure-and-governance-data-v1-20260824")
    parser.add_argument("--max-detail-documents", type=int, default=MAX_DETAIL_DOCUMENTS)
    args = parser.parse_args(argv)
    artifact = run(args.destination, max_detail_documents=args.max_detail_documents)
    print(json.dumps(artifact["coverage"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
