"""Phase 2 / P2-C2: Persisted Official Document Qualification Boundary.

Pure, deterministic, ticker-agnostic document qualification engine that establishes
formal financial-statement authority from retained official evidence:
1. Verifies that the retained document exists and matches its recorded SHA-256 digest.
2. Evaluates source admission against official_source_registry.admit().
3. Validates document class, fiscal period, audit status, periodicity, and statement scope.
4. Binds deterministic qualification identity, evidence identity, and immutable provenance.
5. Persists qualification artifacts independently of execution runners.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from stocklookup_core.evidence.field_identity import stable_id
from stocklookup_core.evidence.official_source_registry import ADMITTED, admit, load_registry

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "official_document_qualification/v1"
QUALIFICATION_SUCCESS_STATUS = "QUALIFIED_RETAINED_FINANCIAL_STATEMENT"
QUALIFICATION_FAILURE_STATUS = "DISQUALIFIED_RETAINED_DOCUMENT"


def retained_assurance_is_bound(status, evidence, *, document_sha256):
    """Reuse this owner's existing assurance identity check for retained fields."""
    from official_financial_assurance_evidence import assurance_proof_is_bound
    return assurance_proof_is_bound(status, evidence, document_sha256=document_sha256)

SUPPORTED_DOCUMENT_CLASSES = frozenset({
    "audited_annual_financial_statements",
    "reviewed_interim_financial_statements",
    "annual_report",
})

KNOWN_AUDITORS = frozenset({
    "Deloitte Vietnam",
    "PwC Vietnam",
    "EY Vietnam",
    "KPMG Vietnam",
    "A&C Auditing",
    "AASCS",
    "VACO",
    "AFC Vietnam",
    "UHY Vietnam",
})


@dataclass(frozen=True)
class DocumentQualificationRecord:
    """Immutable, persisted document qualification record."""
    qualification_id: str
    evidence_id: str
    document_id: str
    document_sha256: str
    ticker: str
    issuer_identity: str
    entity_type: str
    document_class: str
    reporting_period: str
    periodicity: str
    audit_status: str
    auditor: str | None
    statement_scope: str
    source_id: str
    source_host: str
    source_url: str
    published_at: str | None
    observed_at: str
    verified_at: str
    qualification_status: str
    qualification_reasons: tuple[str, ...]
    contract_version: str = CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "qualification_id": self.qualification_id,
            "evidence_id": self.evidence_id,
            "document_id": self.document_id,
            "document_sha256": self.document_sha256,
            "ticker": self.ticker,
            "issuer_identity": self.issuer_identity,
            "entity_type": self.entity_type,
            "document_class": self.document_class,
            "reporting_period": self.reporting_period,
            "periodicity": self.periodicity,
            "audit_status": self.audit_status,
            "auditor": self.auditor,
            "statement_scope": self.statement_scope,
            "source_id": self.source_id,
            "source_host": self.source_host,
            "source_url": self.source_url,
            "published_at": self.published_at,
            "observed_at": self.observed_at,
            "verified_at": self.verified_at,
            "qualification_status": self.qualification_status,
            "qualification_reasons": list(self.qualification_reasons),
            "contract_version": self.contract_version,
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_evidence_id(*, ticker: str, document_sha256: str, document_id: str) -> str:
    """Compute deterministic evidence ID matching evidence_promotion contract."""
    payload = json.dumps(
        {"document_id": document_id, "document_sha256": document_sha256, "ticker": ticker.upper()},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def qualify_retained_document(
    record: Mapping[str, Any],
    *,
    evidence_root: Path,
    registry: Mapping[str, Any] | None = None,
    issuer_identity: str | None = None,
    entity_type: str = "corporate",
    auditor: str | None = None,
    verified_at: str | None = None,
) -> DocumentQualificationRecord:
    """Qualify a retained official document against strict governance criteria."""
    now_iso = verified_at or datetime.now(timezone.utc).isoformat()
    ticker = str(record.get("ticker", "")).upper().strip()
    doc_id = str(record.get("document_id", "")).strip()
    doc_sha = str(record.get("sha256", "")).strip()
    doc_class = str(record.get("document_class", "")).strip()
    period = str(record.get("reporting_period", "")).strip()
    url = str(record.get("canonical_url", "")).strip()
    source_id = str(record.get("source_id", "issuer_ir")).strip()
    published_at = record.get("published_at")
    observed_at = str(record.get("observed_at", now_iso))
    rel_path = record.get("relative_path")

    reasons: list[str] = []
    is_qualified = True

    # 1. Physical Retained Document Integrity
    if not rel_path:
        is_qualified = False
        reasons.append("MISSING_RELATIVE_PATH")
        doc_path = None
    else:
        doc_path = Path(evidence_root) / str(rel_path)
        if not doc_path.is_file():
            is_qualified = False
            reasons.append("RETAINED_DOCUMENT_FILE_NOT_FOUND")
        else:
            live_hash = _sha256_file(doc_path)
            if live_hash != doc_sha:
                is_qualified = False
                reasons.append("CONTENT_SHA256_MISMATCH")

    # 2. Source Registry Admission
    reg = registry if registry is not None else load_registry()
    adm = admit(source_id, url, doc_class, registry=reg)
    if adm["decision"] != ADMITTED:
        is_qualified = False
        reasons.append(f"SOURCE_ADMISSION_REFUSED:{adm['reason']}")

    # 3. Document Class & Periodicity Criteria
    if doc_class not in SUPPORTED_DOCUMENT_CLASSES:
        is_qualified = False
        reasons.append("UNSUPPORTED_DOCUMENT_CLASS")

    is_annual = (doc_class == "audited_annual_financial_statements" or doc_class == "annual_report")
    periodicity = "annual" if is_annual else "interim"

    # 4. A discovered class is a hint, never proof of assurance or scope.
    audit_status, scope = "unknown", "unknown"
    try:
        import io
        from pypdf import PdfReader
        from financial_evidence_currency_refresh import _metadata_from_pages
        from official_financial_assurance_evidence import resolve_native_document_assurance, assurance_proof_is_bound
        from stocklookup_core.evidence.financial_metadata_envelope import METADATA_QUALIFIED
        reader = PdfReader(io.BytesIO(doc_path.read_bytes())) if doc_path is not None else None
        pages = {index+1:reader.pages[index].extract_text() or "" for index in range(min(8,len(reader.pages)))} if reader else {}
        metadata = _metadata_from_pages(pages,{**record,"immutable_bytes_verified":is_qualified})
        claims = metadata.get("metadata_claims") or {}
        assurance = resolve_native_document_assurance(doc_sha,pages)
        actual_scope = (claims.get("statement_scope") or {}).get("value")
        actual_period = (claims.get("reporting_period") or {}).get("value")
        actual_status = assurance.get("audit_or_review_status")
        expected_status = "audited" if doc_class=="audited_annual_financial_statements" else "reviewed"
        import re
        if (metadata.get("qualification_status") != METADATA_QUALIFIED or actual_period != period
                or actual_scope != "consolidated" or actual_status != expected_status
                or not assurance_proof_is_bound(actual_status,assurance,document_sha256=doc_sha)
                or not re.search(r"\b"+re.escape(ticker)+r"\b","\n".join(pages.values()),re.IGNORECASE)):
            raise ValueError("DOCUMENT_LITERAL_QUALIFICATION_NOT_BOUND")
        audit_status,scope = actual_status,actual_scope
    except Exception:
        is_qualified = False
        reasons.append("DOCUMENT_METADATA_OR_ASSURANCE_PROOF_UNAVAILABLE")

    if is_qualified:
        reasons.append("OFFICIAL_HOST_ADMITTED")
        reasons.append("DOCUMENT_INTEGRITY_VERIFIED")
        reasons.append("LITERAL_DOCUMENT_PERIOD_SCOPE_ASSURANCE_VERIFIED")
        status = QUALIFICATION_SUCCESS_STATUS
    else:
        status = QUALIFICATION_FAILURE_STATUS

    ev_id = compute_evidence_id(ticker=ticker, document_sha256=doc_sha, document_id=doc_id)
    
    # Deterministic qualification ID
    qual_id_dict = {
        "ticker": ticker,
        "document_sha256": doc_sha,
        "reporting_period": period,
        "audit_status": audit_status,
        "scope": scope,
        "status": status,
    }
    qual_id = stable_id(qual_id_dict)

    from urllib.parse import urlsplit
    host = urlsplit(url).netloc.lower()

    return DocumentQualificationRecord(
        qualification_id=qual_id,
        evidence_id=ev_id,
        document_id=doc_id,
        document_sha256=doc_sha,
        ticker=ticker,
        issuer_identity=issuer_identity or ticker,
        entity_type=entity_type,
        document_class=doc_class,
        reporting_period=period,
        periodicity=periodicity,
        audit_status=audit_status,
        auditor=auditor,
        statement_scope=scope,
        source_id=source_id,
        source_host=host,
        source_url=url,
        published_at=published_at,
        observed_at=observed_at,
        verified_at=now_iso,
        qualification_status=status,
        qualification_reasons=tuple(sorted(set(reasons))),
    )


def persist_document_qualification(
    record: DocumentQualificationRecord,
    destination_path: Path,
) -> Path:
    """Atomically write qualification record to destination JSON file."""
    dest = Path(destination_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "record": record.to_dict(),
    }
    content = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    dest.write_text(content, encoding="utf-8")
    return dest


def load_document_qualification(path: Path) -> dict[str, Any]:
    """Load persisted qualification record from JSON file."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Qualification file not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("record", data)


def admit_retained_financial_fact(row: Mapping[str, Any], *, evidence_root: Path | None = None,
        registry: Mapping[str, Any] | None = None, cutoff: str | None = None,
        intended_use: str = "CURRENT_RESEARCH_FACTUAL_AUTHORITY") -> dict[str, Any]:
    """Read-only source replay around the pure filing admission rule.

    The source record comes from the retained manifest, never from an overlay's
    caller-selected source flags. Historical rows without metadata remain unproved.
    """
    from official_financial_filing_evidence import admit_official_financial_fact
    from financial_evidence_currency_contract import DEFAULT_LANDING_ROOT
    from runtime_paths import runtime_root
    kwargs = {"cutoff": cutoff, "intended_use": intended_use}
    if not isinstance(row.get("document_metadata"), Mapping):
        return admit_official_financial_fact(row, **kwargs)
    base = (Path(evidence_root) if evidence_root is not None else runtime_root(DEFAULT_LANDING_ROOT)).resolve()
    subdir = Path(str(row.get("evidence_subdir") or "."))
    landing = (base / subdir).resolve()
    if not landing.is_relative_to(base):
        return admit_official_financial_fact(row, **kwargs)
    try:
        manifest = json.loads((landing / "official_document_acquisition_manifest.json").read_text(encoding="utf8"))
        matches = [record for record in manifest.get("records", []) if record.get("sha256") == row.get("document_sha256")]
        if len(matches) != 1:
            return admit_official_financial_fact(row, **kwargs)
        record = matches[0]
        path = (landing / str(record.get("relative_path") or "")).resolve()
        if not path.is_relative_to(landing) or not path.is_file():
            return admit_official_financial_fact(row, **kwargs)
        payload = path.read_bytes()
        source_registry = registry if registry is not None else load_registry()
    except (OSError, ValueError, TypeError, AttributeError):
        return admit_official_financial_fact(row, **kwargs)
    pages = None
    if payload.startswith(b"%PDF"):
        try:
            from pypdf import PdfReader
            import io
            reader = PdfReader(io.BytesIO(payload))
            metadata = row["document_metadata"]
            required = {((claim or {}).get("evidence_span") or {}).get("source_page")
                        for claim in (metadata.get("metadata_claims") or {}).values()}
            proof = row.get("assurance_evidence") or {}
            required.update((proof.get("native_text_evidence") or {}).get("page_numbers") or [])
            required.update((proof.get("page_number"), (proof.get("opinion_evidence") or {}).get("page_number"),
                             (row.get("source_span") or {}).get("source_page")))
            required.discard(None)
            if len(required) <= 8 and all(isinstance(number, int) and 1 <= number <= len(reader.pages) for number in required):
                pages = {number: reader.pages[number-1].extract_text() or "" for number in sorted(required)}
        except Exception:  # An unavailable/malformed retained parser leaves proof UNKNOWN.
            pass
    return admit_official_financial_fact(row, source_record=record, retained_bytes=payload,
                                       registry=source_registry, document_pages=pages, **kwargs)


def _publish_official_artifacts(payloads: Mapping[Path, str], *, commit_path: Path, writer=None) -> None:
    """Facts are the final commit point; restore companions on a promotion failure.

    Callers must complete common admission and serialization first. This helper
    cannot authorize publication. It preserves existing bytes on a failed batch.
    """
    from stocklookup_core.acquisition.artifact_io import atomic_write_file
    commit = Path(commit_path).resolve()
    prepared = {Path(path).resolve(): text.encode("utf8") for path, text in payloads.items()}
    if commit not in prepared or any(path.parent != commit.parent for path in prepared):
        raise ValueError("OFFICIAL_PUBLICATION_PATH_OUTSIDE_ARTIFACT_ROOT")
    originals = {path: path.read_bytes() if path.exists() else None for path in prepared}
    promote = writer or atomic_write_file
    order = sorted((path for path in prepared if path != commit), key=str) + [commit]
    try:
        for path in order:
            promote(path, prepared[path])
    except Exception as error:
        failed = []
        for path, content in originals.items():
            try:
                if content is not None:
                    if not path.exists() or path.read_bytes() != content:
                        atomic_write_file(path, content)
                elif path.exists():
                    path.unlink()
            except OSError:
                failed.append(str(path))
        if failed:
            raise RuntimeError("OFFICIAL_ARTIFACT_ROLLBACK_INCOMPLETE:" + ",".join(failed)) from error
        raise
