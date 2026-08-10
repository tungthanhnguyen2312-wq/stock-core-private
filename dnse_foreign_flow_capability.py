"""DNSE foreign-investor flow: canonical normalization and capability qualification.

Evidence base: the same two 2026-08-10 bounded pilots as `dnse_bid_ask_capability.py`
(general source qualification plus the point-in-time follow-on probe). No
network I/O here; this module normalizes an already-fetched raw
`GET /price/{symbol}/foreign-trading` response.

WHAT WAS DEMONSTRATED, AND WHAT WAS NOT
    Point-in-time (pit probe): a foreign-trading query scoped to the closed
    2026-08-07 session returned genuinely 2026-08-07-timestamped records with
    a distinct `tradingSessionId` ("99") from today's ("40"), and
    ticker-specific `total*` figures consistent with that day's activity --
    not today's cumulative totals relabelled. DEMONSTRATED.

    Value currency/unit: `buyTradedAmount`/`sellTradedAmount`/`totalBuy*`/
    `totalSell*` are **raw VND, not thousands** -- confirmed by magnitude
    plausibility (HPG's 2026-08-07 `totalBuyTradedAmount` of ~47.9 billion
    VND is a plausible one-day foreign-buy value against an estimated
    ~300-1000 billion VND daily turnover at that price/volume level;
    interpreting it as thousands-of-VND would imply ~47.9 trillion VND,
    which is not plausible). This is the opposite unit convention from
    price/depth fields (thousands of VND) observed elsewhere in this same
    API -- a genuine inconsistency worth flagging explicitly, not an error
    in this module.

    Volume unit: `buyVolume`/`sellVolume`/`totalBuyVolume`/`totalSellVolume`
    are consistent with shares by magnitude (millions-of-shares cumulative
    totals sit well below the tens-of-millions-of-shares daily totals
    already exactly cross-checked against vn_stock.db for the same tickers).

    Cumulative-session vs. per-event: both coexist in the same record
    (`buyVolume` = one event's delta; `totalBuyVolume` = the day's running
    total) and are clearly distinguishable by field name and magnitude --
    QUALIFIED as a distinction, independent of whether either scope's exact
    trade-type composition is known.

    Foreign room: `foreignerBuyPossibleQuantity` and `foreignerOrderLimitQuantity`
    are present and ticker-scoped (identical across boardId values for the
    same ticker at the same instant, confirming they are not board-specific),
    but their exact relationship (which is the cap, which is the remainder,
    whether either nets against current foreign holdings) is not documented
    and was not independently proven. Per this milestone's explicit
    instruction, no ownership or free-float percentage is derived from them.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

VERSION = "1.0.0"
PROVIDER = "DNSE"
SOURCE_CONTRACT_VERSION = "dnse_foreign_flow/2026-08-10"

# Part B formal results -- exactly the milestone's vocabulary.
QUALIFIED_EOD_FLOW = "QUALIFIED_EOD_FLOW"
QUALIFIED_INTRADAY_CUMULATIVE_FLOW = "QUALIFIED_INTRADAY_CUMULATIVE_FLOW"
QUALIFIED_ROOM_ONLY = "QUALIFIED_ROOM_ONLY"
PARTIALLY_QUALIFIED = "PARTIALLY_QUALIFIED"
SEMANTICS_UNQUALIFIED = "AVAILABLE_BUT_SEMANTICS_UNQUALIFIED"
FORMAL_RESULTS = frozenset({
    QUALIFIED_EOD_FLOW, QUALIFIED_INTRADAY_CUMULATIVE_FLOW, QUALIFIED_ROOM_ONLY,
    PARTIALLY_QUALIFIED, SEMANTICS_UNQUALIFIED,
})

# The active, evidence-grounded verdict. Flow (buy/sell volume+value, both
# per-event and cumulative) is well-evidenced; room field *meaning* is not --
# so the honest single verdict is PARTIALLY_QUALIFIED, carried alongside the
# two sub-verdicts a caller actually needs to make a decision from.
ACTIVE_QUALIFICATION_STATUS = PARTIALLY_QUALIFIED
FLOW_QUALIFICATION_STATUS = QUALIFIED_INTRADAY_CUMULATIVE_FLOW
ROOM_QUALIFICATION_STATUS = SEMANTICS_UNQUALIFIED
VALUE_UNIT = "vnd"  # raw VND -- NOT thousands, unlike price/depth fields. See module docstring.
VOLUME_UNIT = "shares"
POINT_IN_TIME_QUALIFIED = True

WARNINGS = (
    "dnse_provider_scoped_foreign_flow",
    "trade_type_composition_matched_vs_negotiated_undocumented",
    "foreign_room_field_relationship_and_meaning_unqualified",
    "value_unit_is_raw_vnd_not_thousands_unlike_price_and_depth_fields",
    "not_an_official_exchange_foreign_flow_contract",
)

# Part B's 10 semantic dimensions, classified from retained evidence only.
DIMENSION_QUALIFICATION: dict[str, dict[str, str]] = {
    "value_currency_unit": {
        "status": "QUALIFIED",
        "note": "Raw VND, confirmed by magnitude plausibility against estimated daily "
                "turnover -- NOT the thousands-of-VND convention used by price/depth fields.",
    },
    "volume_unit": {
        "status": "UNQUALIFIED",
        "note": "Plausible shares by magnitude (consistent with the exactly-cross-checked "
                "OHLC daily volume for the same tickers); not independently documented.",
    },
    "matched_vs_negotiated_inclusion": {
        "status": "UNQUALIFIED",
        "note": "No field or documentation distinguishes trade-type composition of the "
                "flow figures; not tested this pilot.",
    },
    "intraday_vs_eod": {
        "status": "QUALIFIED",
        "note": "Confirmed intraday: consecutive records ~1 minute apart within a single "
                "session, not a single end-of-day summary row.",
    },
    "cumulative_vs_per_event": {
        "status": "QUALIFIED",
        "note": "Both scopes coexist per record (`buyVolume` = event delta, "
                "`totalBuyVolume` = day running total), clearly distinguishable by name "
                "and magnitude.",
    },
    "foreign_room_unit": {
        "status": "UNQUALIFIED",
        "note": "`foreignerBuyPossibleQuantity`/`foreignerOrderLimitQuantity` present, "
                "ticker-scoped (not board-specific -- confirmed identical across boards "
                "for one ticker/instant), but unit/meaning not documented.",
    },
    "foreign_ownership_limit_meaning": {
        "status": "UNQUALIFIED",
        "note": "Which field is the cap and which is the remainder (or whether either nets "
                "against current holdings) is not established; no percentage is derived.",
    },
    "timestamp_date_authority": {
        "status": "QUALIFIED",
        "note": "Millisecond `time` field; session-date derivation confirmed correct "
                "against a historical (2026-08-07) query in the point-in-time test.",
    },
    "revision_behavior": {
        "status": "UNQUALIFIED",
        "note": "Not tested -- whether a past session's totals can change after the fact "
                "(late-reported foreign trades) was out of this pilot's bounded scope.",
    },
    "history_window_pagination": {
        "status": "UNQUALIFIED",
        "note": "Same-day window required (wider windows rejected in the general pass); "
                "`nextPageToken` populated but not paged through; exact max range unknown.",
    },
}


class DnseForeignFlowError(ValueError):
    """Fail-closed rejection while normalizing a DNSE foreign-trading response."""


def _amount(value: Any, field: str) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise DnseForeignFlowError(f"invalid_{field}")
    return value


def normalize_record(
    raw: Mapping[str, Any],
    *,
    source_endpoint: str,
    query_window: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """One canonical foreign-flow observation from one raw DNSE record.

    Uses the cumulative session-total fields (`total*`) as the primary
    buy/sell figures -- the canonical contract's fields describe a
    session/date's flow, and `total*` is what actually answers that; the
    per-event delta is retained separately under `provenance.event_scoped`
    rather than silently discarded.
    """
    ticker = raw.get("symbol")
    session_time = raw.get("time")
    if not isinstance(ticker, str) or not ticker:
        raise DnseForeignFlowError("missing_or_invalid_ticker")
    if not isinstance(session_time, str) or not session_time:
        raise DnseForeignFlowError("missing_or_invalid_observation_timestamp")

    buy_volume = _amount(raw.get("totalBuyVolume"), "totalBuyVolume")
    sell_volume = _amount(raw.get("totalSellVolume"), "totalSellVolume")
    buy_value = _amount(raw.get("totalBuyTradedAmount"), "totalBuyTradedAmount")
    sell_value = _amount(raw.get("totalSellTradedAmount"), "totalSellTradedAmount")
    event_buy_volume = _amount(raw.get("buyVolume"), "buyVolume")
    event_sell_volume = _amount(raw.get("sellVolume"), "sellVolume")
    event_buy_value = _amount(raw.get("buyTradedAmount"), "buyTradedAmount")
    event_sell_value = _amount(raw.get("sellTradedAmount"), "sellTradedAmount")

    room_possible = _amount(raw.get("foreignerBuyPossibleQuantity"), "foreignerBuyPossibleQuantity")
    room_limit = _amount(raw.get("foreignerOrderLimitQuantity"), "foreignerOrderLimitQuantity")
    foreign_room = None
    if room_possible is not None or room_limit is not None:
        foreign_room = {
            "buy_possible_quantity": room_possible,
            "order_limit_quantity": room_limit,
            "unit": VOLUME_UNIT,
            "relationship_qualified": False,
        }

    return {
        "ticker": ticker,
        "session_date": session_time.split(" ", 1)[0],
        "observed_at": session_time,
        "foreign_buy_volume": buy_volume,
        "foreign_sell_volume": sell_volume,
        "foreign_net_volume": derive_net(buy_volume, sell_volume),
        "foreign_buy_value": buy_value,
        "foreign_sell_value": sell_value,
        "foreign_net_value": derive_net(buy_value, sell_value),
        "foreign_room": foreign_room,
        "source": PROVIDER,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "volume_unit": VOLUME_UNIT,
        "value_unit": VALUE_UNIT,
        "provenance": {
            "source_endpoint": source_endpoint,
            "board_id": raw.get("boardId"),
            "exchange": raw.get("marketId"),
            "trading_session_id": raw.get("tradingSessionId"),
            "query_window": dict(query_window) if query_window else None,
            "event_scoped": {
                "buy_volume": event_buy_volume,
                "sell_volume": event_sell_volume,
                "buy_value": event_buy_value,
                "sell_value": event_sell_value,
            },
        },
        "qualification_status": ACTIVE_QUALIFICATION_STATUS,
        "warnings": list(WARNINGS),
    }


def normalize_response(
    payload: Mapping[str, Any],
    *,
    source_endpoint: str,
    query_window: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    records = payload.get("foreigners")
    if records is None:
        return []
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise DnseForeignFlowError("foreigners_field_not_a_list")
    return [
        normalize_record(item, source_endpoint=source_endpoint, query_window=query_window)
        for item in records
    ]


def derive_net(buy: int | float | None, sell: int | float | None) -> int | float | None:
    """net = buy - sell, and only when both sides are present.

    Both inputs must come from the same normalized record (guaranteeing same
    date/session/scope/unit by construction) -- this function never accepts
    or reconciles two different records' figures.
    """
    if buy is None or sell is None:
        return None
    return buy - sell


def assert_same_scope(a: Mapping[str, Any], b: Mapping[str, Any]) -> None:
    """Fail closed if two records are combined across an incompatible scope
    (different ticker or different session date). Guards any future caller
    that tries to net two separately-fetched records instead of one."""
    if a.get("ticker") != b.get("ticker"):
        raise DnseForeignFlowError("scope_mismatch_ticker")
    if a.get("session_date") != b.get("session_date"):
        raise DnseForeignFlowError("scope_mismatch_session_date")


def assert_point_in_time_consistency(
    *, requested_session_date: str, observations: Sequence[Mapping[str, Any]]
) -> None:
    """Fail closed if any observation's session_date does not match what was
    requested -- see dnse_bid_ask_capability.assert_point_in_time_consistency
    for the identical rationale."""
    for observation in observations:
        if observation.get("session_date") != requested_session_date:
            raise DnseForeignFlowError(
                f"point_in_time_mismatch:{observation.get('session_date')!r}"
                f"!={requested_session_date!r}"
            )


def serialize(record: Mapping[str, Any]) -> str:
    """Deterministic JSON serialization -- same input always produces the same bytes."""
    return json.dumps(record, sort_keys=True, default=str)


def active_capability_contract() -> dict[str, Any]:
    """The canonical, active DNSE foreign-flow capability verdict, assembled
    once from the 2026-08-10 bounded pilots' evidence."""
    return {
        "schema_version": VERSION,
        "provider": PROVIDER,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "formal_result": ACTIVE_QUALIFICATION_STATUS,
        "flow_qualification_status": FLOW_QUALIFICATION_STATUS,
        "room_qualification_status": ROOM_QUALIFICATION_STATUS,
        "value_unit": VALUE_UNIT,
        "volume_unit": VOLUME_UNIT,
        "point_in_time_qualified": POINT_IN_TIME_QUALIFIED,
        "dimensions": {k: dict(v) for k, v in DIMENSION_QUALIFICATION.items()},
        "warnings": list(WARNINGS),
        "evidence": (
            "operations-review/dnse-bid-ask-foreign-flow-qualification-20260810/"
            "probe_results.json"
        ),
    }


def assert_fail_closed(status: str) -> None:
    """Refuse an out-of-vocabulary qualification status."""
    if status not in FORMAL_RESULTS:
        raise DnseForeignFlowError(f"formal_result_invalid:{status}")
