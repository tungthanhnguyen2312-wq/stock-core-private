"""Deterministic, cited facts from locally retained qualified official documents."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from semantic_evidence_bridge import load_verified_financial_identities


def _canonical_record(identity: dict[str, Any]) -> dict[str, Any]:
    """Project an already verified financial identity without changing its lineage."""
    period = str(identity["reporting_period"])
    extraction = identity.get("extraction")
    source_statement = (extraction or {}).get("statement") if isinstance(extraction, dict) else None
    return {
        "canonical_metric": identity["metric"],
        "value": identity["value"],
        "source_field": identity["metric"],
        "source_statement": source_statement or "official_financial_identity",
        "source": "official_evidence",
        "period_identity": {
            "fiscal_year": int(period), "fiscal_quarter": None, "period_type": "annual",
            "period_end": f"{period}-12-31", "report_published_at": None, "period": period,
        },
        "statement_scope": identity["statement_scope"],
        "currency": identity["currency"],
        "unit_scale": identity["unit_scale"],
        "derivation_status": "reported",
        "quality_state": "available",
        "reason": None,
        "restatement_state": "unknown",
        "official_evidence": {
            "evidence_id": identity["evidence_id"],
            "citation_id": identity["citation_id"],
            "citation": identity.get("citation"),
            "sha256": identity["document_sha256"],
            "document_sha256": identity["document_sha256"],
            "qualification_version": identity["qualification_version"],
            "verified_at": identity.get("verified_at"),
            "extraction": extraction,
        },
    }


def _is_annual_period(identity: dict[str, Any]) -> bool:
    period = str(identity.get("reporting_period") or "")
    return identity.get("reporting_frequency") == "annual" and len(period) == 4 and period.isdigit()

def load_cited_financial_records(runtime_root: Path, ticker: str) -> dict[str, Any]:
    """Return canonical records only from hash-verified financial identities.

    Manifest/document resolution and citation validation stay in
    :mod:`semantic_evidence_bridge`; this adapter only preserves those verified
    identity and provenance fields in the canonical-record shape.
    """
    symbol = str(ticker).upper()
    verified = load_verified_financial_identities(Path(runtime_root))
    records = [_canonical_record(identity) for key, identity in verified["by_key"].items()
               if key[0] == symbol and _is_annual_period(identity)]
    records.sort(key=lambda record: (record["canonical_metric"], record["period_identity"]["period"],
                                     record["official_evidence"]["citation_id"]))
    return {
        "status": "available" if records else verified["status"],
        "records": records,
        "reason": None if records else "no_hash_verified_cited_financial_identities",
        "rejected": verified["rejected"],
    }
