"""Read-only annual issuer-document facts for the Pillar A research projection.

This is deliberately not a new fact store.  It turns only hash-verified entries from
``financial_identity_citations.jsonl`` into the same ephemeral fact shape used by the
existing qualification policy.  The source document, immutable artifact, page citation,
and extraction metadata remain the authority.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from semantic_evidence_bridge import load_verified_financial_identities


VERSION = "1.0.0"
_METADATA = {
    "operating_cash_flow": ("cash_flow", "Net cash used in operating activities"),
    "net_income": ("income_statement", "Net profit after corporate income tax"),
    "cash_and_equivalents": ("balance_sheet", "Cash and cash equivalents"),
    "total_interest_bearing_debt": ("balance_sheet", "Interest-bearing debt"),
    "shareholders_equity": ("balance_sheet", "Total equity"),
}


def _hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def facts_for_ticker(runtime_root: str, ticker: str) -> list[dict[str, Any]]:
    """Return annual consolidated issuer facts for one ticker, sorted deterministically.

    A malformed or unverified citation produces no fact.  This never reads a provider
    payload and never writes canonical shards, the database, or a generated bundle.
    """
    ticker = str(ticker).upper()
    verified = load_verified_financial_identities(runtime_root).get("by_key") or {}
    result: list[dict[str, Any]] = []
    for (entry_ticker, metric, period), entry in sorted(verified.items()):
        if entry_ticker != ticker or metric not in _METADATA:
            continue
        if entry.get("reporting_frequency") != "annual" or entry.get("statement_scope") != "consolidated":
            continue
        if not (isinstance(period, str) and len(period) == 4 and period.isdigit()):
            continue
        if not entry.get("document_sha256") or not entry.get("citation_id") or not entry.get("evidence_id"):
            continue
        family, raw_item_id = _METADATA[metric]
        fact_identity = {"ticker": ticker, "metric": metric, "period": period,
                         "citation_id": entry["citation_id"], "evidence_id": entry["evidence_id"]}
        fact_id = _hash(fact_identity)
        result.append({
            "ticker": ticker, "canonical_metric": metric, "status": "official_reported",
            "value": entry["value"], "reporting_period": period, "period_type": "annual",
            "period_start": f"{period}-01-01", "period_end": f"{period}-12-31",
            "statement_family": family, "statement_scope": "consolidated",
            "currency": entry["currency"], "scale": "units", "unit_authority": "official_issuer_document",
            "warnings": [], "conflicts": [], "provider": "official_issuer_filing",
            "dialect": "official_document", "raw_item_id": raw_item_id, "source_file": None,
            "source_sha256": entry["document_sha256"],
            "source_observation_ids": [f"official-document-observation:{entry['citation_id']}"],
            "observed_at": entry.get("verified_at"), "fact_id": fact_id,
            "identity_key": f"{ticker}:{metric}:{period}:annual:consolidated",
            "contract_version": VERSION, "mapper_version": VERSION, "resolver_version": VERSION,
            "citation_id": entry["citation_id"], "evidence_id": entry["evidence_id"],
            "document_sha256": entry["document_sha256"], "citation": entry.get("citation"),
            "extraction": entry.get("extraction"), "derived_from": (
                entry.get("extraction") or {}).get("components") if isinstance(entry.get("extraction"), Mapping) else None,
        })
    return result
