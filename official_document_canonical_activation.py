"""Canonical activation for already-qualified official-document observations.

This deliberately produces additive in-memory records.  It never writes a
runtime database, rewrites a source artifact, or converts official evidence into
provider observations.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

VERSION = "1.0.0"
SOURCE_TYPE = "official_document_observation"
QUALIFICATION_VERSION = "official_document_observation/v1"
REQUIRED = ("raw_label", "raw_value", "period", "scope", "unit", "sign", "page", "document_sha256", "ocr_citation_id", "qualification")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _period_identity(period: str) -> dict[str, Any]:
    text = str(period)
    if text == "FY2024" or text == "fy2024":
        return {"period": "2024", "period_type": "annual", "period_end": "2024-12-31"}
    if text == "as_at_2024-12-31":
        return {"period": "2024", "period_type": "annual", "period_end": "2024-12-31"}
    raise ValueError("official_observation_period_unqualified")


def activate(ticker: str, observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return canonical records only for explicitly qualified official rows."""
    records, rejected = [], []
    for row in observations:
        metric = str(row.get("metric") or row.get("identity") or "")
        missing = [field for field in REQUIRED if not row.get(field)]
        if not metric or missing or not str(row.get("qualification", "")).startswith("qualified_"):
            rejected.append({"metric": metric or None, "reason": "official_observation_unqualified", "fields": missing})
            continue
        if row.get("scope") != "consolidated":
            rejected.append({"metric": metric, "reason": "official_scope_unqualified"})
            continue
        try:
            period_identity = _period_identity(str(row["period"]))
            value = int(str(row["raw_value"]).replace(",", ""))
        except (ValueError, TypeError):
            rejected.append({"metric": metric, "reason": "official_value_or_period_unqualified"})
            continue
        source = {"source_type": SOURCE_TYPE, "document_sha256": row["document_sha256"],
                  "raw_label": row["raw_label"], "raw_value": str(row["raw_value"]),
                  "period": row["period"], "statement_scope": row["scope"], "unit": row["unit"],
                  "sign": row["sign"], "page": int(row["page"]), "page_citation_id": row["ocr_citation_id"],
                  "ocr_provenance": "ocr", "qualification_version": QUALIFICATION_VERSION,
                  "qualification": row["qualification"]}
        record = {"canonical_metric": metric, "value": -value if row["sign"] == "negative" else value,
                  "period_identity": period_identity, "statement_scope": "consolidated", "currency": "VND" if str(row["unit"]).startswith("VND") else None,
                  "unit": row["unit"], "unit_scale": 1, "derivation_status": "reported", "quality_state": "available",
                  "source": SOURCE_TYPE, "source_field": row["raw_label"], "source_statement": "official_document",
                  "official_document_source": source}
        record["record_id"] = _digest({"ticker": ticker.upper(), "metric": metric, "source": source})
        records.append(record)
    return replay({"version": VERSION, "ticker": ticker.upper(), "records": records, "rejected": rejected})


def conflicts(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Report incompatible evidence; never choose or merge one source's value."""
    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for row in records:
        key = (str(row.get("canonical_metric")), str((row.get("period_identity") or {}).get("period")), str(row.get("statement_scope")))
        groups.setdefault(key, []).append(row)
    output=[]
    for key, rows in groups.items():
        if len({row.get("value") for row in rows}) > 1:
            output.append({"identity": key, "state": "incomparable_source_values", "record_ids": sorted(str(row.get("record_id")) for row in rows)})
    return sorted(output, key=lambda row: row["identity"])


def replay(value: Mapping[str, Any]) -> dict[str, Any]:
    records=[]
    for row in value.get("records", []):
        source=row.get("official_document_source") or {}
        if row.get("source") != SOURCE_TYPE or source.get("source_type") != SOURCE_TYPE:
            raise ValueError("official_source_type_invalid")
        expected=_digest({"ticker": value.get("ticker"), "metric": row.get("canonical_metric"), "source": source})
        if row.get("record_id") != expected:
            raise ValueError("official_record_identity_invalid")
        records.append(dict(row))
    return {"version": VERSION, "ticker": str(value.get("ticker", "")).upper(), "records": sorted(records,key=lambda row: row["record_id"]), "rejected": sorted((dict(row) for row in value.get("rejected", [])),key=lambda row:(str(row.get("metric")),str(row.get("reason"))))}
