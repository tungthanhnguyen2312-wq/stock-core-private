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

import indicator_metric_availability as availability

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


# ---------------------------------------------------------------------------
# Investor-facing labels/tooltips + the compact per-ticker bridge
# (DASHBOARD_INVESTOR_FIRST_PRESENTATION_SIMPLIFICATION_V1)
# ---------------------------------------------------------------------------

#: Short Vietnamese investor-facing label per metric_id. Every key in
#: indicator_metric_availability's per-ticker registry has one here so a card slot never
#: needs to fall back to a raw metric_id string.
METRIC_LABELS_VI: dict[str, str] = {
    "revenue_growth_yoy": "Tăng trưởng doanh thu (svck)",
    "net_income_growth_yoy": "Tăng trưởng lợi nhuận (svck)",
    "gross_margin": "Biên lợi nhuận gộp",
    "net_margin": "Biên lợi nhuận ròng",
    "operating_cash_flow_sign": "Dòng tiền hoạt động kinh doanh",
    "roe": "ROE",
    "roa": "ROA",
    "debt_to_equity": "Nợ / Vốn chủ sở hữu",
    "cash_to_assets": "Tiền mặt / Tổng tài sản",
    "cfo_to_net_income": "Dòng tiền / Lợi nhuận",
    "leverage_state": "Đòn bẩy tài chính",
    "cash_quality_state": "Chất lượng dòng tiền",
    "ebitda": "EBITDA",
    "pe_ttm": "P/E",
    "ps_ttm": "P/S",
    "pb": "P/B",
    "ev_sales": "EV/Doanh thu",
    "ev_ebitda": "EV/EBITDA",
    "technical_trend_entry_state": "Xu hướng / trạng thái kỹ thuật",
    "technical_confirmation_trigger": "Điểm xác nhận",
    "technical_invalidation": "Mốc vô hiệu hóa",
    "signal_velocity_state": "Xu hướng tín hiệu",
    "sector_relative_momentum": "Động lượng so với ngành",
    "foreign_flow_state": "Dòng ngoại",
    "flow_price_relationship": "Dòng ngoại & giá",
    "flow_persistence_5session": "Độ bền dòng ngoại (5 phiên)",
    "catalyst_event_context": "Sự kiện doanh nghiệp",
}

#: One short, investor-language sentence per display_state -- generic, never mentioning a
#: blocker code, provider, or pipeline stage (Phase 20 of the milestone brief).
TOOLTIP_VI: dict[str, str] = {
    "AVAILABLE": "Giá trị hiện tại, cập nhật theo phiên gần nhất.",
    "INSUFFICIENT_DATA": "Chưa đủ dữ liệu để tính chỉ số này cho mã hiện tại.",
    "BUILDING_HISTORY": "Cần thêm dữ liệu các phiên tiếp theo mới tính được chỉ số này.",
    "NOT_APPLICABLE": "Chỉ số này không áp dụng cho loại hình doanh nghiệp này.",
    "NOT_TRACKED": "Chỉ báo này chưa được theo dõi cho mã hiện tại.",
    "TEMPORARILY_UNAVAILABLE": "Dữ liệu hiện tại chưa sẵn sàng, sẽ được cập nhật sau.",
}

#: Investor-facing metrics only expose ONE EV/EBITDA slot even though the Producer engine
#: tracks two internal methods (``ev_ebitda``, ``ev_ebitda_calc_ready``) -- this is a pure
#: presentation consolidation (prefer whichever method is more informative), never a new
#: computation. The calc-ready-only method never appears as its own investor-facing card.
_EV_EBITDA_PREFERENCE = ("ev_ebitda", "ev_ebitda_calc_ready")
_STATE_RANK = {"AVAILABLE": 0, "TEMPORARILY_UNAVAILABLE": 1, "BUILDING_HISTORY": 2,
               "INSUFFICIENT_DATA": 3, "NOT_TRACKED": 4, "NOT_APPLICABLE": 5}

#: The curated, investor-facing metric_id order for a ticker detail page (Phase 3 schema).
#: Every id here must already be a key ``indicator_metric_availability.evaluate_ticker``
#: produces (or be handled specially, like ``ev_ebitda`` consolidation below) -- this module
#: never invents a metric Stock Lookup does not implement.
INVESTOR_METRIC_ORDER: tuple[str, ...] = (
    "technical_trend_entry_state", "signal_velocity_state", "technical_invalidation",
    "sector_relative_momentum", "technical_confirmation_trigger",
    "foreign_flow_state", "flow_price_relationship", "flow_persistence_5session",
    "revenue_growth_yoy", "net_income_growth_yoy", "gross_margin", "net_margin",
    "operating_cash_flow_sign", "ebitda", "roe", "roa", "debt_to_equity", "leverage_state",
    "pe_ttm", "pb", "ps_ttm", "ev_sales", "ev_ebitda",
    "catalyst_event_context",
)

_FAMILY_BY_METRIC: dict[str, str] = {
    "technical_trend_entry_state": "PRICE_TECHNICAL", "signal_velocity_state": "PRICE_TECHNICAL",
    "technical_invalidation": "PRICE_TECHNICAL", "sector_relative_momentum": "PRICE_TECHNICAL",
    "technical_confirmation_trigger": "PRICE_TECHNICAL",
    "foreign_flow_state": "FLOW", "flow_price_relationship": "FLOW", "flow_persistence_5session": "FLOW",
    "revenue_growth_yoy": "FUNDAMENTALS", "net_income_growth_yoy": "FUNDAMENTALS", "gross_margin": "FUNDAMENTALS",
    "net_margin": "FUNDAMENTALS", "operating_cash_flow_sign": "FUNDAMENTALS", "roe": "FUNDAMENTALS",
    "roa": "FUNDAMENTALS", "debt_to_equity": "FUNDAMENTALS", "leverage_state": "FUNDAMENTALS",
    "ebitda": "VALUATION", "pe_ttm": "VALUATION", "pb": "VALUATION", "ps_ttm": "VALUATION",
    "ev_sales": "VALUATION", "ev_ebitda": "VALUATION",
    "catalyst_event_context": "CORPORATE_RESEARCH_CONTEXT",
}

#: Published ONCE per artifact (never per ticker): static label/family per investor-facing
#: metric_id. Kept out of every per-ticker record to bound artifact size -- a per-ticker
#: repeat of ~24 metrics' labels/tooltips across ~1,700 tickers would add double-digit
#: megabytes to an already-large published JSON for data that never varies by ticker.
DISPLAY_METRIC_CATALOG: dict[str, dict[str, str]] = {
    metric_id: {"label": METRIC_LABELS_VI.get(metric_id, metric_id), "family": _FAMILY_BY_METRIC[metric_id]}
    for metric_id in INVESTOR_METRIC_ORDER
}


def build_ticker_display_metrics(ticker: str, card: Mapping[str, Any], *,
                                  cohort_tickers: frozenset[str],
                                  technical_coverage_disposition_record: Mapping[str, Any] | None = None,
                                  technical_history_recovery_record: Mapping[str, Any] | None = None,
                                  ) -> dict[str, dict[str, Any]]:
    """The compact, investor-facing ``display_metrics`` block attached to one Workspace card.

    Reuses ``indicator_metric_availability.evaluate_ticker`` (classification) and
    ``to_display_state`` (presentation) exactly as tested -- computes nothing new, recomputes
    no EBITDA/valuation/technical figure. Every id in ``INVESTOR_METRIC_ORDER`` is present in
    the result (never omitted for being unavailable).

    ``technical_coverage_disposition_record``/``technical_history_recovery_record`` (both
    optional) are this one ticker's own real, already session-coherence-checked evidence rows
    (see ``investment_decision_workspace_projection._coherent_technical_evidence()``), passed
    straight through to ``evaluate_ticker()`` for precise ``technical_trend_entry_state``
    blocker classification (INDICATOR_METRIC_AVAILABILITY_RECOVERY_CLASSIFICATION_CORRECTIVE_
    V1). Omitted, classification fails closed exactly as it always has -- no display-state
    vocabulary change either way.

    Deliberately compact: only ``display_state`` and ``value`` vary per ticker. ``label`` and
    ``tooltip`` are static per ``metric_id`` -- read them once from ``DISPLAY_METRIC_CATALOG``/
    ``TOOLTIP_VI`` (keyed by ``display_state``), never repeat them per ticker.
    """
    availability_records = availability.evaluate_ticker(
        ticker, card, cohort_tickers=cohort_tickers,
        technical_coverage_disposition=technical_coverage_disposition_record,
        technical_history_recovery_record=technical_history_recovery_record,
    )
    display_records = {metric_id: to_display_state(record) for metric_id, record in availability_records.items()}

    ev_ebitda_candidates = [display_records[m] for m in _EV_EBITDA_PREFERENCE if m in display_records]
    if ev_ebitda_candidates:
        display_records["ev_ebitda"] = min(ev_ebitda_candidates, key=lambda r: _STATE_RANK.get(r["display_state"], 9))

    return {
        metric_id: {"display_state": display_records[metric_id]["display_state"],
                    "value": display_records[metric_id]["value"]}
        for metric_id in INVESTOR_METRIC_ORDER if metric_id in display_records
    }
