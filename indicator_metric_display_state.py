"""Product display-state projection: ``indicator_metric_display_state/v1``.

A pure whitelist/reshape layer over ``indicator_metric_availability.py`` records
(mirrors ``velocity_flow_price_presentation_projection.py``'s established pattern: this
module computes nothing new). It exists so the Dashboard never has to infer availability
from an arbitrary null or an internal reason code: every metric always renders, in one of
exactly six frontend-facing states, in Vietnamese product language.

Never expose (see the milestone's Phase 14/23 requirement): ``blocker_class``,
``recoverability``, ``recovery_action_code``, ``source_identity``, Python/module names,
provider names, pipeline/contract names, or any raw internal reason code. A capability that
exists but currently has no value for this ticker MUST still render a state -- it must never
disappear from the presentation model (Phase 16).
"""
from __future__ import annotations

from typing import Any, Mapping

CONTRACT_VERSION = "indicator_metric_display_state/v1"

DISPLAY_STATES = (
    "AVAILABLE",
    "INSUFFICIENT_DATA",
    "BUILDING_HISTORY",
    "NOT_APPLICABLE",
    "NOT_TRACKED",
    "TEMPORARILY_UNAVAILABLE",
)

#: Product-language text per Phase 15 of the milestone brief. Deliberately the only
#: strings this module ever emits as ``display_text`` -- no interpolation of any
#: upstream value, reason code, or identity into this text.
DISPLAY_TEXT_VI: dict[str, str] = {
    "AVAILABLE": None,  # the actual value/state is shown instead of a placeholder
    "INSUFFICIENT_DATA": "Chưa đủ dữ liệu",
    "BUILDING_HISTORY": "Đang tích lũy chuỗi phiên",
    "NOT_APPLICABLE": "Không áp dụng",
    "NOT_TRACKED": "Chưa theo dõi",
    "TEMPORARILY_UNAVAILABLE": "Tạm chưa có dữ liệu",
}

#: Internal availability_state -> frontend display_state. Identical vocabulary today
#: (see indicator_metric_availability.py's module docstring) but kept as an explicit
#: table, not an identity assumption, so the two contracts can diverge safely later.
_AVAILABILITY_TO_DISPLAY: dict[str, str] = {
    "READY": "AVAILABLE",
    "INSUFFICIENT_DATA": "INSUFFICIENT_DATA",
    "BUILDING_HISTORY": "BUILDING_HISTORY",
    "NOT_APPLICABLE": "NOT_APPLICABLE",
    "NOT_TRACKED": "NOT_TRACKED",
    "TEMPORARILY_UNAVAILABLE": "TEMPORARILY_UNAVAILABLE",
}


def to_display_state(record: Mapping[str, Any]) -> dict[str, Any]:
    """One availability record -> one presentation-safe display record.

    Fails closed: an ``availability_state`` this module does not recognize is never
    silently promoted to ``AVAILABLE`` -- it renders as ``INSUFFICIENT_DATA`` (the same
    stance ``indicator_metric_availability._status_to_state`` takes for an unmapped
    Producer status), never a blank/omitted card.
    """
    availability_state = record.get("availability_state")
    display_state = _AVAILABILITY_TO_DISPLAY.get(availability_state, "INSUFFICIENT_DATA")
    display_text = DISPLAY_TEXT_VI[display_state]
    value = record.get("value") if display_state == "AVAILABLE" else None
    return {
        "contract_version": CONTRACT_VERSION,
        "metric_id": record.get("metric_id"),
        "family": record.get("family"),
        "display_state": display_state,
        "display_text": display_text,
        "value": value,
        "value_present": bool(record.get("value_present")) and display_state == "AVAILABLE",
        "as_of_session": record.get("as_of_session"),
    }


def project_ticker(availability_records: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Every metric on one ticker -> its display record, keyed by ``metric_id``.

    Every key present in ``availability_records`` produces an entry here -- a metric
    with a capability but no current value still renders (never omitted), satisfying
    Phase 16's "EBITDA must not disappear" requirement generically for every metric.
    """
    return {metric_id: to_display_state(record) for metric_id, record in availability_records.items()}


def project_workspace(evaluation: Mapping[str, Any]) -> dict[str, Any]:
    """The full ``indicator_metric_availability.evaluate_workspace_artifact`` output ->
    its presentation projection, one entry per ticker plus one market-wide entry."""
    tickers = evaluation.get("tickers") or {}
    return {
        "contract_version": CONTRACT_VERSION,
        "as_of_session": evaluation.get("as_of_session"),
        "tickers": {ticker: project_ticker(records) for ticker, records in tickers.items()},
        "market_wide": project_ticker(evaluation.get("market_wide") or {}),
    }
