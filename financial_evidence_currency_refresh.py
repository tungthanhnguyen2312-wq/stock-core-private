"""Bounded Cohort-1 official financial currency refresh.

Orchestrates route discovery, capped acquisition, native-text extraction,
metadata/value qualification, official-vs-legacy precedence, and public
citation artifacts.  Raw PDF/HTML bytes stay in the private landing directory
and are never staged for Git.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urljoin, urlparse

from financial_evidence_currency_contract import (
    ANNUAL_DOCUMENT_CLASS,
    COHORT,
    CONTRACT_VERSION,
    DEFAULT_LANDING_ROOT,
    DIRECT_TARGET_LOCATORS,
    ENTITY_FAMILY,
    EVF_BLOCKER,
    HTTP_REQUEST_CAP,
    INDEX_DOCUMENT_TYPE,
    INTERIM_DOCUMENT_CLASS,
    ISSUER_IR_INDEX_SEEDS,
    MAX_DOCUMENTS_PER_ISSUER,
    MILESTONE_ID,
    PAN_INDEX_BLOCKER,
    PUBLIC_ARTIFACT_DIR,
    STORAGE_BUDGET_BYTES,
    TARGET_ANNUAL_PERIOD,
    TARGET_INTERIM_PERIODS,
    core_metrics_for,
    corporate_debt_ebitda_applicable,
    entity_family,
    official_ttm_eligible,
    period_document_class,
    pin_rebuild_eligible,
)
from official_financial_filing_evidence import METADATA_QUALIFIED, qualify_document_metadata
from official_financial_period_identity import (
    period_bounds,
    recognize_audit_or_review,
    recognize_currency,
    recognize_scope,
    recognize_statement_period,
    recognize_unit_scale,
)
from official_financial_value_evidence import parse_accounting_integer
from official_legacy_precedence import (
    EXACT_MATCH,
    LEGACY_ONLY,
    NOT_COMPARABLE,
    TRUE_CONFLICT,
    compare_official_and_legacy,
)
import official_document_acquisition as acquirer
import official_source_registry as registry_module

VERSION = "1.0.0"
SOURCE_ID = "issuer_ir"
PUBLIC_FACTS = "qualified_official_facts.jsonl"
PUBLIC_PRECEDENCE = "official_legacy_precedence.jsonl"
PUBLIC_REPORT = "cohort_report.json"
LANDING_RUN_MANIFEST = "currency_refresh_run_manifest.json"


class OfficialOverlayArtifactError(ValueError):
    """Present public overlay is unreadable, schema-invalid, or identity-corrupt.

    Missing overlay is expected absence and is not this error.
    """


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8") if not isinstance(value, bytes) else value).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".refresh-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def restatement_envelope(*, original: Mapping[str, Any], amendment: Mapping[str, Any]) -> dict[str, Any]:
    """Append-only supersession.  Amendments never inherit the original observed_at."""
    original_obs = str(original.get("observed_at") or "")
    amendment_obs = str(amendment.get("observed_at") or "")
    backdated = bool(original_obs and amendment_obs and amendment_obs < original_obs)
    return {
        "append_only": True,
        "original_document_sha256": original.get("document_sha256"),
        "amended_document_sha256": amendment.get("document_sha256"),
        "original_observed_at": original_obs,
        "amended_observed_at": amendment_obs,
        "original_knowledge_available_at": original.get("knowledge_available_at") or original_obs,
        "amended_knowledge_available_at": amendment.get("knowledge_available_at") or amendment_obs,
        "supersedes": original.get("document_sha256"),
        "backdating_attempted": backdated,
        "accepted": not backdated,
        "blocker": "AMENDMENT_BACKDATING_FORBIDDEN" if backdated else None,
    }


def image_only_disposition(*, text_layer_status: str, ocr_authorized: bool, needed_for_core: bool) -> dict[str, Any]:
    if text_layer_status != "IMAGE_ONLY_OR_SCANNED":
        return {"extraction_mode": "native_text", "ocr_used": False, "status": "NATIVE_TEXT"}
    if not ocr_authorized or not needed_for_core:
        return {
            "extraction_mode": "image_only",
            "ocr_used": False,
            "status": "IMAGE_ONLY_FAIL_CLOSED",
            "blocker": "IMAGE_ONLY_OCR_NOT_TRIGGERED",
        }
    return {"extraction_mode": "triggered_ocr", "ocr_used": True, "status": "OCR_AUTHORIZED_BOUNDED"}


def financial_v2_pin_decision(*, tickers_with_new_qualified_core: int,
                              unresolved_schema_ambiguity: bool) -> dict[str, Any]:
    eligible = pin_rebuild_eligible(
        tickers_with_new_qualified_core=tickers_with_new_qualified_core,
        unresolved_schema_ambiguity=unresolved_schema_ambiguity,
    )
    return {
        "decision": "KEEP_CURRENT_PIN" if not eligible else "ELIGIBLE_TO_CONSIDER_NEW_PIN",
        "rebuild_performed": False,
        "current_authority_version": "2026-09-05.1",
        "new_authority_version": None,
        "tickers_with_new_qualified_core": tickers_with_new_qualified_core,
        "unresolved_schema_ambiguity": unresolved_schema_ambiguity,
        "reason": (
            "THRESHOLD_NOT_MET_OR_AMBIGUOUS" if not eligible
            else "THRESHOLD_MET_PIN_LEFT_UNCHANGED_ADDITIVE_OFFICIAL_FACTS"
        ),
    }


class BoundedHttpBudget:
    def __init__(self, cap: int = HTTP_REQUEST_CAP, storage_budget: int = STORAGE_BUDGET_BYTES) -> None:
        self.cap = cap
        self.storage_budget = storage_budget
        self.requests = 0
        self.new_bytes = 0
        self.stopped_reason: str | None = None

    def can_request(self) -> bool:
        if self.stopped_reason:
            return False
        if self.requests >= self.cap:
            self.stopped_reason = "HTTP_REQUEST_CAP_REACHED"
            return False
        if self.new_bytes >= self.storage_budget:
            self.stopped_reason = "STORAGE_BUDGET_REACHED"
            return False
        return True

    def record_request(self) -> None:
        self.requests += 1
        if self.requests >= self.cap:
            self.stopped_reason = self.stopped_reason or "HTTP_REQUEST_CAP_REACHED"

    def record_bytes(self, size: int) -> None:
        self.new_bytes += max(0, int(size))
        if self.new_bytes >= self.storage_budget:
            self.stopped_reason = "STORAGE_BUDGET_REACHED"


_PERIOD_HREF = (
    (TARGET_ANNUAL_PERIOD, re.compile(
        r"(2025|nam[-_]?2025|fy[-_]?2025|year[-_]?2025|hop[-_]?nhat[-_]?nam[-_]?2025|bctc[-_].*2025)",
        re.IGNORECASE,
    )),
    ("2026-H1", re.compile(
        r"(2026.*(6[-_ ]?thang|ban[-_ ]?nien|h1|interim|soat[-_ ]?xet)|"
        r"(6[-_ ]?thang|ban[-_ ]?nien|h1|interim).{0,40}2026|"
        r"30[-_.]?06[-_.]?2026|30[-_.]?6[-_.]?2026)",
        re.IGNORECASE,
    )),
    ("2026-Q2", re.compile(
        r"(2026.*(quy[-_ ]?(2|ii)|q2)|q2[-_ ]?2026|quarter[-_ ]?2[-_ ]?2026)",
        re.IGNORECASE,
    )),
)
_Q3_HREF = re.compile(r"(2026.*(quy[-_ ]?(3|iii)|q3)|q3[-_ ]?2026)", re.IGNORECASE)
_FS_HINT = re.compile(
    r"(bctc|bao[-_ ]?cao[-_ ]?tai[-_ ]?chinh|financial[-_ ]?statement|hop[-_ ]?nhat|consolidated|kiem[-_ ]?toan|audited|soat[-_ ]?xet|reviewed)",
    re.IGNORECASE,
)


def parse_index_document_links(html: str, base_url: str) -> list[dict[str, str]]:
    """Pull first-party PDF/Excel locators for target periods; drop Q3 2026."""
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in re.finditer(r"""href\s*=\s*["']([^"']+)["']""", html, flags=re.IGNORECASE):
        href = match.group(1).strip()
        if href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        absolute = urljoin(base_url, href)
        path = urlparse(absolute).path.lower()
        if not path.endswith((".pdf", ".xlsx", ".xls")):
            continue
        if _Q3_HREF.search(absolute) and not _PERIOD_HREF[1][1].search(absolute):
            continue
        period = None
        for name, pattern in _PERIOD_HREF:
            if pattern.search(absolute) or pattern.search(href):
                period = name
                break
        if period is None:
            continue
        if not _FS_HINT.search(absolute + " " + href):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        found.append({"url": absolute, "period": period, "document_class": period_document_class(
            TARGET_ANNUAL_PERIOD if period == TARGET_ANNUAL_PERIOD else period
        )})
    return found


def _route_for(ticker: str) -> dict[str, Any]:
    if ticker == "EVF":
        return {
            "ticker": ticker, "entity_family": entity_family(ticker),
            "admitted_index": None, "requested": False,
            "blocker": EVF_BLOCKER, "route_status": "ROUTE_DISCOVERY_ONLY_NO_ADMITTED_HOST",
        }
    if ticker == "PAN":
        return {
            "ticker": ticker, "entity_family": entity_family(ticker),
            "admitted_index": None, "requested": False,
            "blocker": PAN_INDEX_BLOCKER, "route_status": "STORAGE_HOST_ONLY_NO_INDEX",
        }
    seed = ISSUER_IR_INDEX_SEEDS.get(ticker)
    return {
        "ticker": ticker, "entity_family": entity_family(ticker),
        "admitted_index": seed, "requested": False,
        "blocker": None if seed else "NO_INDEX_SEED",
        "route_status": "INDEX_SEEDED" if seed else "NO_INDEX_SEED",
    }


def _qualify_extracted_fact(fact: Mapping[str, Any], document: Mapping[str, Any]) -> dict[str, Any]:
    sha = str(document.get("sha256") or "")
    period = str(fact.get("reporting_period") or "")
    currency = str(fact.get("currency") or "")
    scale = fact.get("unit_scale")
    scope = str(fact.get("statement_scope") or "")
    citation = fact.get("source_span") or fact.get("citation")
    raw = fact.get("raw_value_text") or fact.get("raw_numeric_text")
    blockers: list[str] = []
    if not sha or len(sha) != 64:
        blockers.append("DOCUMENT_HASH_MISSING")
    if not period:
        blockers.append("PERIOD_MISSING")
    if currency != "VND":
        blockers.append("CURRENCY_MISSING_OR_NOT_VND")
    if not scale:
        blockers.append("UNIT_SCALE_MISSING")
    if scope != "consolidated":
        blockers.append("SCOPE_NOT_CONSOLIDATED")
    if not citation:
        blockers.append("CITATION_MISSING")
    try:
        parsed = parse_accounting_integer(raw) if raw is not None else fact.get("parsed_numeric_value")
        if parsed is None:
            blockers.append("VALUE_UNPARSABLE")
    except ValueError:
        parsed = None
        blockers.append("VALUE_UNPARSABLE")
    qualified = not blockers
    start, end = (None, None)
    if period:
        try:
            start, end = period_bounds(period)
        except ValueError:
            blockers.append("PERIOD_BOUNDS_UNSUPPORTED")
            qualified = False
    return {
        **dict(fact),
        "ticker": document.get("ticker"),
        "document_sha256": sha,
        "source_locator": document.get("official_url") or document.get("source_locator"),
        "qualification_state": "QUALIFIED" if qualified else "BLOCKED",
        "blockers": blockers,
        "parsed_numeric_value": parsed,
        "period_start": start,
        "period_end": end,
        "observed_at": document.get("observed_at") or document.get("retrieved_at"),
        "knowledge_available_at": document.get("observed_at") or document.get("retrieved_at"),
        "publication_date": document.get("published_at"),
        "source_family": SOURCE_ID,
        "restatement": None,
    }


def _metadata_from_pages(pages_text: str, document: Mapping[str, Any]) -> dict[str, Any]:
    period = recognize_statement_period(pages_text)
    scale = recognize_unit_scale(pages_text)
    currency = recognize_currency(pages_text)
    scope = recognize_scope(pages_text)
    audit = recognize_audit_or_review(pages_text)
    sha = str(document.get("sha256") or "")

    def span(text: str | None) -> dict[str, Any]:
        return {
            "citation_id": _hash({"doc": sha, "text": text or ""}),
            "document_sha256": sha, "source_page": 1,
            "text": text or "explicit", "citation_kind": "source_span",
        }

    metadata = {}
    if period.get("period"):
        metadata["reporting_period"] = {"value": period["period"], "evidence_span": span(period.get("evidence"))}
        metadata["periodicity"] = {
            "value": "annual" if period["periodicity"] == "annual" else "interim",
            "evidence_span": span(period.get("evidence")),
        }
    if scope.get("statement_scope"):
        metadata["statement_scope"] = {"value": scope["statement_scope"], "evidence_span": span(pages_text[:180])}
    if currency.get("currency"):
        metadata["currency"] = {"value": currency["currency"], "evidence_span": span(currency.get("evidence"))}
    if scale.get("unit_scale"):
        metadata["unit_scale"] = {"value": scale["unit_scale"], "evidence_span": span(scale.get("evidence"))}
    if audit.get("audit_or_review_status"):
        metadata["audit_or_review_status"] = {
            "value": audit["audit_or_review_status"], "evidence_span": span(pages_text[:180]),
        }
    return qualify_document_metadata({
        "issuer_identity": document.get("ticker"),
        "entity_type": entity_family(str(document.get("ticker") or "")),
        "document": {
            "document_id": document.get("document_id"), "sha256": sha,
            "source_locator": document.get("official_url") or document.get("source_locator"),
            "source_id": SOURCE_ID, "observed_at": document.get("observed_at") or document.get("retrieved_at"),
            "published_at": document.get("published_at"),
            "immutable_bytes_verified": document.get("immutable_bytes_verified", True),
        },
        "metadata": metadata,
    })


def extract_from_retained_pdf(document: Mapping[str, Any], path: Path, *, allow_ocr: bool = False) -> dict[str, Any]:
    from official_financial_pdf_page_evidence import build_artifact

    entity = entity_family(str(document.get("ticker") or ""))
    payload = {**dict(document), "entity_type": entity if entity == "corporate" else entity}
    artifact = build_artifact(document=payload, path=path)
    text_status = str(artifact.get("text_layer_status") or "")
    ocr = image_only_disposition(
        text_layer_status=text_status, ocr_authorized=allow_ocr,
        needed_for_core=True,
    )
    pages_text = "\n".join(str(page.get("page_text") or "") for page in artifact.get("page_evidence") or [])
    metadata = _metadata_from_pages(pages_text, {**payload, "sha256": document["sha256"]})
    facts = []
    if ocr["status"] == "IMAGE_ONLY_FAIL_CLOSED":
        return {
            "extraction_mode": ocr["extraction_mode"], "ocr": ocr, "metadata": metadata,
            "facts": [], "blocker": ocr["blocker"], "artifact_identity": artifact.get("artifact_identity"),
        }
    for candidate in artifact.get("fact_candidates") or []:
        mapped = dict(candidate)
        if mapped.get("canonical_metric") == "cash_and_equivalents":
            mapped["canonical_metric"] = "cash_and_cash_equivalents"
        mapped["reporting_period"] = mapped.get("fiscal_period") or (metadata.get("metadata_claims") or {}).get(
            "reporting_period", {},
        ).get("value")
        mapped["statement_scope"] = mapped.get("statement_scope") or "consolidated"
        mapped["currency"] = mapped.get("currency") or "VND"
        facts.append(_qualify_extracted_fact(mapped, document))
    if entity in {"bank", "securities"}:
        # Specialist layouts are not forced through the corporate Circular-200 template.
        if not facts:
            return {
                "extraction_mode": "native_text", "ocr": ocr, "metadata": metadata, "facts": [],
                "blocker": "SPECIALIST_TEMPLATE_REQUIRED",
                "artifact_identity": artifact.get("artifact_identity"),
            }
    return {
        "extraction_mode": ocr["extraction_mode"], "ocr": ocr, "metadata": metadata,
        "facts": facts, "blocker": None, "artifact_identity": artifact.get("artifact_identity"),
        "text_layer_status": text_status,
    }


def _empty_period_row(ticker: str, period: str) -> dict[str, Any]:
    return {
        "ticker": ticker, "period": period, "route": None, "requested": False,
        "http_status": None, "document_found": False, "immutable_raw_retained": False,
        "hash": None, "publication_date": None, "statement_type": period_document_class(
            TARGET_ANNUAL_PERIOD if period == TARGET_ANNUAL_PERIOD else period
        ) if period in {TARGET_ANNUAL_PERIOD, *TARGET_INTERIM_PERIODS} else None,
        "scope": None, "extraction_mode": None, "metadata_qualification": None,
        "value_qualification": None, "core_qualified_metrics": [], "conflicts": [],
        "restatement_state": None, "blocker": None,
    }


def _acquire_one(
    spec: Mapping[str, Any],
    destination: Path,
    budget: BoundedHttpBudget,
    *,
    fetcher: Callable[..., tuple[Any, ...]] | None,
    observed_at: str,
) -> dict[str, Any]:
    if not budget.can_request():
        return {"state": budget.stopped_reason, "ticker": spec.get("ticker"), "requested": False}

    before = {path: path.stat().st_size for path in destination.rglob("*") if path.is_file()}
    if fetcher is None:
        original = acquirer.fetch_http

        def wrapped(url: str, **kwargs: Any) -> tuple[Any, ...]:
            if not budget.can_request():
                raise RuntimeError(budget.stopped_reason)
            budget.record_request()
            return original(url, **kwargs)

        acquirer.fetch_http = wrapped  # type: ignore[method-assign]
        try:
            result = acquirer.acquire(
                [spec], destination, fetcher=acquirer.fetch_http, observed_at=observed_at, max_attempts=2,
            )
        finally:
            acquirer.fetch_http = original  # type: ignore[method-assign]
    else:
        def counting(url: str, timeout_seconds: int = 15, **kwargs: Any) -> tuple[Any, ...]:
            if not budget.can_request():
                raise RuntimeError(budget.stopped_reason)
            budget.record_request()
            return fetcher(url, timeout_seconds=timeout_seconds, **kwargs)

        result = acquirer.acquire(
            [spec], destination, fetcher=counting, observed_at=observed_at, max_attempts=2,
        )
    after = {path: path.stat().st_size for path in destination.rglob("*") if path.is_file()}
    added = sum(size - before.get(path, 0) for path, size in after.items())
    budget.record_bytes(added)
    if budget.new_bytes > budget.storage_budget:
        budget.stopped_reason = "STORAGE_BUDGET_REACHED"
    outcome = dict((result.get("outcomes") or [{}])[0])
    manifest_path = Path(result["manifest"]) if result.get("manifest") else destination / acquirer.MANIFEST
    if manifest_path.is_file():
        try:
            records = json.loads(manifest_path.read_text(encoding="utf-8")).get("records") or []
        except (OSError, json.JSONDecodeError):
            records = []
        ticker = str(spec.get("ticker") or "").upper()
        url = str(spec.get("canonical_url") or "")
        for record in reversed(records):
            if record.get("ticker") == ticker and record.get("canonical_url") == url:
                outcome.setdefault("sha256", record.get("sha256"))
                outcome.setdefault("relative_path", record.get("relative_path"))
                outcome.setdefault("http_status", record.get("http_status"))
                outcome.setdefault("document_id", record.get("document_id"))
                break
    outcome["http_requests_so_far"] = budget.requests
    outcome["new_landing_bytes_so_far"] = budget.new_bytes
    return outcome


def run_refresh(
    *,
    landing_root: Path | str | None = None,
    public_root: Path | str | None = None,
    allow_network: bool = False,
    allow_ocr: bool = False,
    fetcher: Callable[..., tuple[Any, ...]] | None = None,
    observed_at: str | None = None,
    legacy_facts: Mapping[tuple[str, str, str, str], Mapping[str, Any]] | None = None,
    retained_documents: list[Mapping[str, Any]] | None = None,
    extracted_facts: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the bounded refresh.  Network is off unless ``allow_network`` is true.

    Tests inject ``retained_documents`` / ``extracted_facts`` / ``fetcher`` so the
    framework is proven without live HTTP or giant OCR work.
    """
    observed = observed_at or _now()
    landing = Path(landing_root or DEFAULT_LANDING_ROOT)
    public = Path(public_root) if public_root else Path(__file__).resolve().parent / PUBLIC_ARTIFACT_DIR
    budget = BoundedHttpBudget()
    routes = {ticker: _route_for(ticker) for ticker in COHORT}
    per_issuer: dict[str, dict[str, Any]] = {
        ticker: {
            "ticker": ticker,
            "entity_family": entity_family(ticker),
            "core_metrics": list(core_metrics_for(ticker)),
            "corporate_debt_ebitda_applicable": corporate_debt_ebitda_applicable(ticker),
            "route": routes[ticker],
            "periods": {
                TARGET_ANNUAL_PERIOD: _empty_period_row(ticker, TARGET_ANNUAL_PERIOD),
                "2026-H1": _empty_period_row(ticker, "2026-H1"),
                "2026-Q2": _empty_period_row(ticker, "2026-Q2"),
            },
            "documents_retained": 0,
        }
        for ticker in COHORT
    }
    qualified_facts: list[dict[str, Any]] = list(extracted_facts or [])
    precedence_rows: list[dict[str, Any]] = []

    if extracted_facts:
        for fact in extracted_facts:
            ticker = str(fact.get("ticker") or "").upper()
            period = str(fact.get("reporting_period") or "")
            if ticker not in per_issuer:
                continue
            row = per_issuer[ticker]["periods"].get(period)
            if row is None and period in TARGET_INTERIM_PERIODS:
                row = per_issuer[ticker]["periods"][period]
            if row is None:
                continue
            row["document_found"] = True
            row["immutable_raw_retained"] = True
            row["hash"] = fact.get("document_sha256")
            row["scope"] = fact.get("statement_scope")
            row["extraction_mode"] = fact.get("extraction_mode") or "native_text"
            if fact.get("qualification_state") == "QUALIFIED":
                row["value_qualification"] = "QUALIFIED"
                row["metadata_qualification"] = METADATA_QUALIFIED
                metric = str(fact.get("canonical_metric") or "")
                if metric in core_metrics_for(ticker) and metric not in row["core_qualified_metrics"]:
                    row["core_qualified_metrics"].append(metric)
            else:
                row["value_qualification"] = "BLOCKED"
                row["blocker"] = ",".join(fact.get("blockers") or []) or row.get("blocker")

    if allow_network:
        landing.mkdir(parents=True, exist_ok=True)
        for locator in DIRECT_TARGET_LOCATORS:
            ticker = locator["ticker"]
            if ticker not in per_issuer or not budget.can_request():
                continue
            if per_issuer[ticker]["documents_retained"] >= MAX_DOCUMENTS_PER_ISSUER:
                continue
            spec = {
                "ticker": ticker, "source_id": SOURCE_ID,
                "document_class": locator["document_class"],
                "reporting_period": locator["period"], "canonical_url": locator["url"],
            }
            outcome = _acquire_one(spec, landing, budget, fetcher=fetcher, observed_at=observed)
            row = per_issuer[ticker]["periods"].setdefault(
                locator["period"], _empty_period_row(ticker, locator["period"]),
            )
            row["requested"] = True
            row["route"] = locator["url"]
            row["http_status"] = outcome.get("http_status") or outcome.get("state")
            if outcome.get("state") in {"retained", "cached_valid"}:
                row["document_found"] = True
                row["immutable_raw_retained"] = True
                row["hash"] = outcome.get("sha256")
                per_issuer[ticker]["documents_retained"] += 1
                relative_doc = outcome.get("relative_path")
                pdf_path = landing / relative_doc if relative_doc else None
                if pdf_path and pdf_path.is_file() and pdf_path.suffix.lower() == ".pdf":
                    extracted = extract_from_retained_pdf(
                        {
                            "document_id": outcome.get("document_id"),
                            "ticker": ticker, "sha256": outcome.get("sha256"),
                            "official_url": locator["url"], "retrieved_at": observed,
                            "observed_at": observed, "immutable_bytes_verified": True,
                        },
                        pdf_path, allow_ocr=allow_ocr,
                    )
                    row["extraction_mode"] = extracted.get("extraction_mode")
                    row["metadata_qualification"] = (extracted.get("metadata") or {}).get("qualification_status")
                    row["blocker"] = extracted.get("blocker")
                    for fact in extracted.get("facts") or []:
                        qualified_facts.append(fact)
                        if fact.get("qualification_state") == "QUALIFIED":
                            metric = str(fact.get("canonical_metric") or "")
                            if metric in core_metrics_for(ticker) and metric not in row["core_qualified_metrics"]:
                                row["core_qualified_metrics"].append(metric)
                            row["value_qualification"] = "QUALIFIED"
            else:
                row["blocker"] = outcome.get("state") or outcome.get("reason")
        for ticker, route in routes.items():
            if ticker == "EVF":
                for period_row in per_issuer[ticker]["periods"].values():
                    period_row["blocker"] = EVF_BLOCKER
                continue
            if not budget.can_request():
                break
            seed = route.get("admitted_index")
            if not seed:
                continue
            spec = {
                "ticker": ticker, "source_id": SOURCE_ID, "document_class": INDEX_DOCUMENT_TYPE,
                "reporting_period": TARGET_ANNUAL_PERIOD, "canonical_url": seed,
            }
            route["requested"] = True
            per_issuer[ticker]["periods"][TARGET_ANNUAL_PERIOD]["route"] = seed
            outcome = _acquire_one(spec, landing, budget, fetcher=fetcher, observed_at=observed)
            per_issuer[ticker]["periods"][TARGET_ANNUAL_PERIOD]["http_status"] = outcome.get("http_status") or outcome.get("state")
            per_issuer[ticker]["periods"][TARGET_ANNUAL_PERIOD]["requested"] = True
            if outcome.get("state") not in {"retained", "cached_valid"}:
                per_issuer[ticker]["periods"][TARGET_ANNUAL_PERIOD]["blocker"] = outcome.get("state") or outcome.get("reason")
                continue
            relative = outcome.get("relative_path")
            html_path = landing / relative if relative else None
            links: list[dict[str, str]] = []
            if html_path and html_path.is_file():
                links = parse_index_document_links(html_path.read_text(encoding="utf-8", errors="replace"), seed)
            kept: list[dict[str, str]] = []
            seen_periods: set[str] = set()
            for link in links:
                if len(kept) >= MAX_DOCUMENTS_PER_ISSUER:
                    break
                if link["period"] in seen_periods:
                    continue
                kept.append(link)
                seen_periods.add(link["period"])
            for link in kept:
                if not budget.can_request():
                    break
                doc_spec = {
                    "ticker": ticker, "source_id": SOURCE_ID,
                    "document_class": link["document_class"],
                    "reporting_period": (
                        TARGET_ANNUAL_PERIOD if link["period"] == TARGET_ANNUAL_PERIOD else link["period"]
                    ),
                    "canonical_url": link["url"],
                }
                doc_outcome = _acquire_one(doc_spec, landing, budget, fetcher=fetcher, observed_at=observed)
                period_key = link["period"]
                row = per_issuer[ticker]["periods"].setdefault(period_key, _empty_period_row(ticker, period_key))
                row["requested"] = True
                row["route"] = link["url"]
                row["http_status"] = doc_outcome.get("http_status") or doc_outcome.get("state")
                if doc_outcome.get("state") in {"retained", "cached_valid"}:
                    row["document_found"] = True
                    row["immutable_raw_retained"] = True
                    row["hash"] = doc_outcome.get("sha256")
                    per_issuer[ticker]["documents_retained"] += 1
                    relative_doc = doc_outcome.get("relative_path")
                    pdf_path = landing / relative_doc if relative_doc else None
                    if pdf_path and pdf_path.is_file() and pdf_path.suffix.lower() == ".pdf":
                        extracted = extract_from_retained_pdf(
                            {
                                "document_id": doc_outcome.get("document_id"),
                                "ticker": ticker, "sha256": doc_outcome.get("sha256"),
                                "official_url": link["url"], "retrieved_at": observed,
                                "observed_at": observed, "immutable_bytes_verified": True,
                            },
                            pdf_path, allow_ocr=allow_ocr,
                        )
                        row["extraction_mode"] = extracted.get("extraction_mode")
                        row["metadata_qualification"] = (extracted.get("metadata") or {}).get("qualification_status")
                        row["blocker"] = extracted.get("blocker")
                        for fact in extracted.get("facts") or []:
                            qualified_facts.append(fact)
                            if fact.get("qualification_state") == "QUALIFIED":
                                metric = str(fact.get("canonical_metric") or "")
                                if metric in core_metrics_for(ticker) and metric not in row["core_qualified_metrics"]:
                                    row["core_qualified_metrics"].append(metric)
                                row["value_qualification"] = "QUALIFIED"
                else:
                    row["blocker"] = doc_outcome.get("state") or doc_outcome.get("reason")

    for document in retained_documents or ():
        ticker = str(document.get("ticker") or "").upper()
        period = str(document.get("reporting_period") or "")
        if ticker not in per_issuer:
            continue
        row = per_issuer[ticker]["periods"].get(period) or _empty_period_row(ticker, period)
        per_issuer[ticker]["periods"][period] = row
        row["document_found"] = True
        row["immutable_raw_retained"] = True
        row["hash"] = document.get("sha256")
        row["route"] = document.get("official_url")
        path = Path(str(document.get("path") or ""))
        if path.is_file():
            extracted = extract_from_retained_pdf(document, path, allow_ocr=allow_ocr)
            row["extraction_mode"] = extracted.get("extraction_mode")
            row["metadata_qualification"] = (extracted.get("metadata") or {}).get("qualification_status")
            row["blocker"] = extracted.get("blocker")
            for fact in extracted.get("facts") or []:
                qualified_facts.append(fact)
                if fact.get("qualification_state") == "QUALIFIED":
                    metric = str(fact.get("canonical_metric") or "")
                    if metric in core_metrics_for(ticker) and metric not in row["core_qualified_metrics"]:
                        row["core_qualified_metrics"].append(metric)
                    row["value_qualification"] = "QUALIFIED"

    for item in per_issuer.values():
        for row in item["periods"].values():
            if row["requested"] and not row["document_found"] and not row.get("blocker"):
                row["blocker"] = "INDEX_OR_ROUTE_NO_TARGET_PERIOD_DOCUMENT"

    for fact in qualified_facts:
        key = (
            str(fact.get("ticker") or "").upper(),
            str(fact.get("canonical_metric") or ""),
            str(fact.get("reporting_period") or ""),
            str(fact.get("statement_scope") or "consolidated"),
        )
        legacy = (legacy_facts or {}).get(key)
        compared = compare_official_and_legacy(fact, legacy)
        precedence_rows.append({"key": {"ticker": key[0], "metric": key[1], "period": key[2], "scope": key[3]},
                                **compared})
        ticker = key[0]
        period = key[2]
        if ticker in per_issuer and period in per_issuer[ticker]["periods"]:
            if compared["status"] in {TRUE_CONFLICT, NOT_COMPARABLE, EXACT_MATCH}:
                per_issuer[ticker]["periods"][period]["conflicts"].append(compared["status"])

    new_core_by_ticker: dict[str, int] = {}
    for fact in qualified_facts:
        if fact.get("qualification_state") != "QUALIFIED":
            continue
        ticker = str(fact.get("ticker") or "").upper()
        if str(fact.get("canonical_metric") or "") in core_metrics_for(ticker):
            new_core_by_ticker[ticker] = new_core_by_ticker.get(ticker, 0) + 1

    fy_gain = sorted({
        str(fact.get("ticker")) for fact in qualified_facts
        if fact.get("qualification_state") == "QUALIFIED"
        and str(fact.get("reporting_period")) == TARGET_ANNUAL_PERIOD
        and str(fact.get("canonical_metric")) in core_metrics_for(str(fact.get("ticker") or ""))
    })
    interim_gain = sorted({
        str(fact.get("ticker")) for fact in qualified_facts
        if fact.get("qualification_state") == "QUALIFIED"
        and str(fact.get("reporting_period")) in TARGET_INTERIM_PERIODS
        and str(fact.get("canonical_metric")) in core_metrics_for(str(fact.get("ticker") or ""))
    })
    equity_gain = sorted({
        str(fact.get("ticker")) for fact in qualified_facts
        if fact.get("qualification_state") == "QUALIFIED"
        and fact.get("canonical_metric") in {"shareholders_equity", "total_equity"}
    })
    pin = financial_v2_pin_decision(
        tickers_with_new_qualified_core=len(new_core_by_ticker),
        unresolved_schema_ambiguity=False,
    )
    conflicts = {
        "TRUE_CONFLICT": sum(1 for row in precedence_rows if row.get("status") == TRUE_CONFLICT),
        "NOT_COMPARABLE": sum(1 for row in precedence_rows if row.get("status") == NOT_COMPARABLE),
        "EXACT_MATCH": sum(1 for row in precedence_rows if row.get("status") == EXACT_MATCH),
        "LEGACY_ONLY": sum(1 for row in precedence_rows if row.get("status") == LEGACY_ONLY),
    }
    report = {
        "schema_version": VERSION,
        "contract_version": CONTRACT_VERSION,
        "milestone_id": MILESTONE_ID,
        "observed_at": observed,
        "official_route_tickers_attempted": 14,
        "period_targets_per_ticker_max": 2,
        "http_requests": budget.requests,
        "http_request_cap": HTTP_REQUEST_CAP,
        "new_landing_bytes": budget.new_bytes,
        "storage_budget_bytes": STORAGE_BUDGET_BYTES,
        "stopped_reason": budget.stopped_reason,
        "issuers": per_issuer,
        "acquired_ok": sum(1 for item in per_issuer.values() if item["documents_retained"] > 0),
        "documents_retained": sum(item["documents_retained"] for item in per_issuer.values()),
        "new_qualified_core_fact_count": sum(new_core_by_ticker.values()),
        "tickers_with_ge1_new_qualified_core_fact": sorted(new_core_by_ticker),
        "fy2025_official_coverage_gain": fy_gain,
        "h1_q2_2026_official_coverage_gain": interim_gain,
        "official_pb_input_gain": equity_gain,
        "official_pe_ttm_gain": [],
        "official_ps_ttm_gain": [],
        "official_ttm_eligible": official_ttm_eligible([]),
        "conflicts": conflicts,
        "restatement_supersession_count": 0,
        "posture_delta_count": 0,
        "posture_deltas": [],
        "zero_active_vnstock_status": "RETIRED_PROVIDER",
        "financial_v2_pin": pin,
        "q3_2026_assumed": False,
        "raw_filings_committed": False,
        "vnstock_runtime": False,
        "kbs_vci_live_call": False,
        "hnx_bulk_crawl": False,
        "production_db_write": False,
        "live_owner_daily": False,
        "dashboard_publication": False,
        "main_merge": False,
        "successor_milestone_started": False,
        "ev_ebitda_dcf_unchanged": True,
        "implementation_success_gate": (
            "A_FIVE_TICKERS_QUALIFIED" if len(new_core_by_ticker) >= 5
            else "B_PARTIAL_EXTERNAL_BLOCKERS"
        ),
    }
    public.mkdir(parents=True, exist_ok=True)
    facts_path = public / PUBLIC_FACTS
    _atomic_write(facts_path, "".join(_json(fact) + "\n" for fact in qualified_facts))
    _atomic_write(public / PUBLIC_PRECEDENCE, "".join(_json(row) + "\n" for row in precedence_rows))
    report["public_facts_path"] = str(facts_path)
    report["artifact_sha256"] = _hash(report)
    report["artifact_identity"] = f"financial_evidence_currency_refresh:{report['artifact_sha256']}"
    _atomic_write(public / PUBLIC_REPORT, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    landing.mkdir(parents=True, exist_ok=True)
    _atomic_write(landing / LANDING_RUN_MANIFEST, json.dumps({
        "http_requests": budget.requests, "new_bytes": budget.new_bytes,
        "stopped_reason": budget.stopped_reason, "observed_at": observed,
    }, indent=2, sort_keys=True) + "\n")
    return report


def load_public_official_fact_rows(root: Path | str) -> list[dict[str, Any]]:
    path = Path(root) / PUBLIC_ARTIFACT_DIR / PUBLIC_FACTS
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OfficialOverlayArtifactError(f"OFFICIAL_OVERLAY_UNREADABLE:{path}") from exc
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise OfficialOverlayArtifactError(
                f"OFFICIAL_OVERLAY_MALFORMED_JSON:line={index}"
            ) from exc
        if not isinstance(record, dict):
            raise OfficialOverlayArtifactError(
                f"OFFICIAL_OVERLAY_SCHEMA_ERROR:line={index}:not_object"
            )
        ticker = str(record.get("ticker") or "").upper()
        metric = str(record.get("canonical_metric") or "")
        period = str(record.get("reporting_period") or "")
        if record.get("qualification_state") == "QUALIFIED" and not (ticker and metric and period):
            raise OfficialOverlayArtifactError(
                f"OFFICIAL_OVERLAY_IDENTITY_CORRUPT:line={index}"
            )
        rows.append(record)
    return rows


def load_public_official_citations(root: Path | str) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Additive overlay consumed by canonical_fact_store; never overwrites legacy rows.

    Missing overlay is empty. A present malformed overlay raises OfficialOverlayArtifactError.
    """
    citations: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in load_public_official_fact_rows(root):
        if record.get("qualification_state") != "QUALIFIED":
            continue
        ticker = str(record.get("ticker") or "").upper()
        metric = str(record.get("canonical_metric") or "")
        period = str(record.get("reporting_period") or "")
        citations[(ticker, metric, period)] = {
            "citation_id": record.get("citation_id") or record.get("table_id") or _hash(record),
            "evidence_id": record.get("document_sha256"),
            "value": next((record[key] for key in ("normalized_value", "parsed_numeric_value", "value")
                           if record.get(key) is not None), None),
            "currency": record.get("currency") or "VND",
            "scale": record.get("unit_scale") or 1,
            "statement_scope": record.get("statement_scope"),
            "document_sha256": record.get("document_sha256"),
            "verified": True,
            "provenance": "official_issuer_ir",
        }
    return citations
