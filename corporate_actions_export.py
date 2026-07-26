"""Additive Consumer section derived from existing bounded corporate-event records."""
from __future__ import annotations

from typing import Any, Mapping

from corporate_actions import canonicalize_corporate_actions


def build_corporate_actions_section(events: Mapping[str, Any]) -> dict[str, Any]:
    if events.get("status") == "missing":
        return {"status": "missing", "reason": events.get("reason"), "sources": []}
    if events.get("status") != "partial":
        return {"status": "malformed", "reason": "corporate_events_not_usable", "sources": []}
    sources = []
    for source in events.get("sources", []):
        raw_records = source.get("records") if isinstance(source, Mapping) else None
        coverage = source.get("coverage_status") if isinstance(source, Mapping) else None
        if not isinstance(raw_records, list):
            return {"status": "malformed", "reason": "corporate_event_records_malformed", "sources": []}
        records = []
        for record in raw_records:
            if not isinstance(record, Mapping) or not isinstance(record.get("fields"), Mapping):
                return {"status": "malformed", "reason": "corporate_event_record_malformed", "sources": []}
            records.append({**record["fields"], "provider_event_id": record.get("provider_event_id")})
        provenance_by_id = {record.get("provider_event_id"): record.get("provenance") for record in raw_records if isinstance(record, Mapping)}
        mapped = canonicalize_corporate_actions(records, coverage_status=coverage, provenance={"source_name": source.get("source_name"), "event_source": "corporate_events", "coverage_status": coverage})
        for canonical in mapped["records"]:
            original = provenance_by_id.get(canonical["provider_event_id"])
            if isinstance(original, Mapping):
                canonical["provenance"] = {**original, "event_source": "corporate_events"}
        sources.append({"source_name": source.get("source_name"), "coverage_status": coverage, **mapped})
    statuses = [source["status"] for source in sources]
    return {"status": "partial" if "partial" in statuses else "unavailable", "coverage_status": events.get("coverage_status"),
            "reason": "derived_from_partial_corporate_events", "sources": sources,
            "warnings": ["No complete history, lifecycle state, adjustment ratio, or adjusted-price claim is inferred."]}
