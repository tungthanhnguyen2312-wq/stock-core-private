"""Deterministic, cited facts from locally retained qualified official documents."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

OFFICIAL_EVIDENCE_MANIFEST = "data/official-evidence/manifest.json"
SCHEMA_VERSION = "1.0.0"
_CITED_FACTS = (
    ("HPG", "revenue", 158_332_000_000_000, "2025", 35),
    ("HPG", "total_assets", 257_899_000_000_000, "2025", 35),
    ("HPG", "shareholders_equity", 131_220_000_000_000, "2025", 35),
)

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def load_cited_financial_records(runtime_root: Path, ticker: str) -> dict[str, Any]:
    """Return facts only while their retained qualified document still hash-verifies."""
    manifest_path = runtime_root / OFFICIAL_EVIDENCE_MANIFEST
    if not manifest_path.exists():
        return {"status": "missing", "records": [], "reason": "official_evidence_manifest_missing"}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "malformed", "records": [], "reason": "official_evidence_manifest_malformed"}
    if manifest.get("schema_version") != SCHEMA_VERSION:
        return {"status": "unavailable", "records": [], "reason": "official_evidence_schema_unqualified"}
    symbol, records = str(ticker).upper(), []
    for evidence in manifest.get("records", []):
        if not isinstance(evidence, dict) or evidence.get("ticker") != symbol:
            continue
        document = manifest_path.parent / str(evidence.get("filename") or "")
        if (evidence.get("qualification_state") != "qualified" or not evidence.get("evidence_id") or not document.is_file() or _sha256(document) != evidence.get("sha256")):
            continue
        for fact_ticker, metric, value, period, page in _CITED_FACTS:
            if fact_ticker != symbol or evidence.get("reporting_period") != period:
                continue
            records.append({"canonical_metric": metric, "value": value, "source_field": "annual_report_group_summary_table", "source_statement": "annual_report", "source": "official_evidence", "period_identity": {"fiscal_year": int(period), "fiscal_quarter": None, "period_type": "annual", "period_end": f"{period}-12-31", "report_published_at": evidence.get("publication_date"), "period": period}, "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1, "derivation_status": "reported", "quality_state": "available", "reason": None, "restatement_state": "unknown", "official_evidence": {"evidence_id": evidence["evidence_id"], "source_url": evidence.get("source_url"), "sha256": evidence["sha256"], "page": page, "table": "Revenue, total assets, equity of the Group for 2014-2025", "retrieved_at": evidence.get("retrieved_at")}})
    return {"status": "available" if records else "unavailable", "records": records, "reason": None if records else "no_hash_verified_cited_facts"}
