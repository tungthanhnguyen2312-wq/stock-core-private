"""Valuation-axis research freshness policy, separated from temporal measurement."""
from __future__ import annotations
from typing import Any, Mapping
from stocklookup_core.evidence.temporal_freshness import classify_freshness, CURRENT, STALE_BUT_RESEARCH_USABLE

VALUATION_CONTRACT = {"older_usable": True, "period_based": False}


def classify_valuation_freshness(*, decision_session: str, source_session: str | None,
                               source_artifact_identity: str | None = None) -> dict[str, Any]:
    return classify_freshness(axis="valuation", contract=VALUATION_CONTRACT,
                             decision_session=decision_session, source_session=source_session,
                             source_artifact_identity=source_artifact_identity)


def axis_is_research_usable(envelope: Mapping[str, Any]) -> bool:
    return envelope.get("freshness_status") in {CURRENT, STALE_BUT_RESEARCH_USABLE}

