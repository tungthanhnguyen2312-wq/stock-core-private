"""Deterministic, presentation-safe events adapted from qualified research deltas."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from qualified_research_delta import compare

SCHEMA_VERSION = "1.0.0"


def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _event(ticker: str, family: str, previous: Any, current: Any, provenance: list[str], source: Any, destination: Any) -> dict[str, Any]:
    identity = {"ticker": ticker, "family": family, "previous": previous, "current": current,
                "provenance": sorted(provenance), "source_snapshot": source, "destination_snapshot": destination}
    return {"event_id": "qrc-" + sha256(_stable(identity).encode()).hexdigest(), "ticker": ticker,
            "family": family, "importance": "research_state_change", "previous": previous,
            "current": current, "provenance_references": sorted(provenance), "historical_only": True,
            "is_actionable": False}


def build(previous: Mapping[str, Any] | None, current: Mapping[str, Any] | None) -> dict[str, Any]:
    """Adapt only canonical semantic deltas; identical/invalid inputs yield first-class NO_CHANGE."""
    delta = compare(previous, current)
    ticker = str(delta.get("ticker") or "").upper()
    events: list[dict[str, Any]] = []
    if delta["comparison_status"] in {"comparable", "partially_comparable"}:
        eligibility = delta["eligibility_change"]
        if eligibility["status"] != "unchanged":
            events.append(_event(ticker, "capability_transition", eligibility["previous"], eligibility["current"],
                                 ["identity.eligibility"], delta["previous_snapshot"], delta["current_snapshot"]))
        for change in delta["quality_changes"]:
            if change["status"] != "unchanged":
                events.append(_event(ticker, "fundamental_analytic_transition", change["previous_status"], change["current_status"],
                                     ["quality." + str(change["dimension"])], delta["previous_snapshot"], delta["current_snapshot"]))
        if delta["historical_conclusion"]["changed"]:
            events.append(_event(ticker, "historical_conclusion_transition", delta["historical_conclusion"]["previous"].get("status"), delta["historical_conclusion"]["current"].get("status"),
                                 ["historical_conclusion.status"], delta["previous_snapshot"], delta["current_snapshot"]))
    events.sort(key=lambda item: item["event_id"])
    return {"schema_version": SCHEMA_VERSION, "ticker": ticker, "source_snapshot": delta["previous_snapshot"],
            "destination_snapshot": delta["current_snapshot"], "comparison_status": delta["comparison_status"],
            "events": events, "status": "events_available" if events else "NO_CHANGE",
            "historical_only": True, "is_actionable": False}
