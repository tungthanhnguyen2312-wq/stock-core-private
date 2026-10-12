"""DNSE bid/ask depth: canonical normalization and capability qualification.

Evidence base: the 2026-08-10 bounded qualification pilots (general source
qualification, `operations-review/dnse_market_data_source_qualification_20260810.md`,
plus the follow-on point-in-time probe,
`operations-review/dnse-bid-ask-foreign-flow-qualification-20260810/probe_results.json`).
This module performs no network I/O; it normalizes an already-fetched raw
`GET /price/{symbol}/quotes[/latest]` response and carries the qualification
verdict that evidence established. It does not re-derive that verdict per
call, and it does not inherit DNSE's OHLC price-basis/volume-basis verdict --
both remain independently NOT qualified (see market_data_source_authority.py
and dnse_market_data_source_qualification_20260810.md); depth's own price and
quantity semantics are qualified here on their own evidence, per this
milestone's explicit instruction not to assume inheritance.

WHAT WAS DEMONSTRATED, AND WHAT WAS NOT
    Point-in-time (2026-08-10 pit probe): a `quotes` history query scoped to
    the fully-closed 2026-08-07 session returned genuinely 2026-08-07-dated,
    differently-priced book content -- not today's book relabelled. A
    same-day early-session (ASC) vs. recent (DESC) pair returned distinct
    timestamps at opposite ends of the window. This is real evidence, not an
    assumption: DEMONSTRATED.

    Price unit: every depth price observed sits on the same thousands-of-VND
    scale as OHLC/trades (cross-checked exactly against vn_stock.db in the
    general pass) -- but that check was for OHLC/trade prices, not depth
    prices specifically, so this is empirical consistency, not independent
    proof for this endpoint. UNQUALIFIED, conservatively.

    Quantity unit: plausible as shares by magnitude (a single resting level
    of tens of thousands "lots" would imply hundreds of thousands to
    millions of shares at one price, which is implausible next to the
    tens-of-millions-share *daily total*) -- but plausibility is not proof.
    Per this milestone's explicit instruction, quantity semantics are NOT
    inherited from the OHLC volume finding and stay UNQUALIFIED here too.
    Liquidity/sizing analytics are therefore refused regardless of how
    complete the depth data looks.

    Put-through contamination: `quotes_latest` with `boardId=T1` (2026-08-10
    pit probe) returned zero rows (`{"quotes": []}`) for HPG, while G1/G4
    returned real multi-level books at the same instant. This is consistent
    with (not proof of) the general-qualification hypothesis that T-boards
    carry put-through/negotiated trades, which are bilaterally negotiated
    and therefore never enter an order book at all -- if so, G-board depth
    is structurally free of that contamination, not through any DNSE-side
    filtering. Reported as a lead, not a verdict.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

VERSION = "1.0.0"
PROVIDER = "DNSE"
SOURCE_CONTRACT_VERSION = "dnse_bid_ask/2026-08-10"

# Part A formal results -- exactly the milestone's vocabulary, nothing added.
DISPLAY_ONLY = "QUALIFIED_FOR_DISPLAY_ONLY"
LIQUIDITY_ANALYTICS = "QUALIFIED_FOR_LIQUIDITY_ANALYTICS"
SEMANTICS_UNQUALIFIED = "AVAILABLE_BUT_SEMANTICS_UNQUALIFIED"
UNAVAILABLE = "UNAVAILABLE"
FORMAL_RESULTS = frozenset({DISPLAY_ONLY, LIQUIDITY_ANALYTICS, SEMANTICS_UNQUALIFIED, UNAVAILABLE})

# The active, evidence-grounded verdict. A caller may not upgrade this locally --
# reaching QUALIFIED_FOR_LIQUIDITY_ANALYTICS requires a proven quantity unit,
# which requires new evidence, which requires editing this constant alongside it.
ACTIVE_QUALIFICATION_STATUS = DISPLAY_ONLY
PRICE_UNIT = "thousands_of_vnd"
QUANTITY_UNIT_QUALIFIED = False
POINT_IN_TIME_QUALIFIED = True

WARNINGS = (
    "dnse_provider_scoped_depth",
    "price_unit_thousands_of_vnd_empirically_derived_not_documented_for_depth_specifically",
    "quantity_unit_not_independently_proven_do_not_use_for_sizing_or_liquidity_analytics",
    "market_composition_and_put_through_contamination_unresolved",
    "not_an_official_exchange_depth_contract",
)

# Part A's 17 semantic dimensions, classified from retained evidence only.
# "QUALIFIED" here means directly observed/demonstrated in this pilot's bounded
# evidence -- it is a narrower bar than official documentation, per this
# project's evidence-qualification convention, and is not a claim that DNSE
# has published anything.
DIMENSION_QUALIFICATION: dict[str, dict[str, str]] = {
    "instrument_identity": {
        "status": "QUALIFIED",
        "note": "`symbol` present on every record; cross-checked against `secdef`/`instruments`.",
    },
    "exchange_board_identity": {
        "status": "QUALIFIED",
        "note": "`marketId` + `boardId` present on every record (STO/UPX observed; G1/G4/T1 boards tested).",
    },
    "observation_timestamp": {
        "status": "QUALIFIED",
        "note": "Millisecond-precision `time` field on every record.",
    },
    "timezone": {
        "status": "UNQUALIFIED",
        "note": "`time` carries no explicit offset; values are consistent with Asia/Ho_Chi_Minh "
                "by convention (matches VN market hours) but DNSE documents no timezone.",
    },
    "trading_session_date": {
        "status": "QUALIFIED",
        "note": "Derived from `time`'s date portion; confirmed correct against a historical "
                "(2026-08-07) query in the point-in-time test, not merely assumed.",
    },
    "bid_levels": {
        "status": "QUALIFIED",
        "note": "Array of {price, quantity} under `bid`; 1-10 levels observed across samples.",
    },
    "ask_levels": {
        "status": "QUALIFIED",
        "note": "Array of {price, quantity} under `offer` (DNSE's own field name; normalized here to ask_levels).",
    },
    "price_unit": {
        "status": "UNQUALIFIED",
        "note": "Empirically thousands-of-VND by scale-consistency with OHLC/trades "
                "(exact-matched against vn_stock.db); not independently documented for depth.",
    },
    "quantity_unit": {
        "status": "UNQUALIFIED",
        "note": "Plausible shares by magnitude reasoning; not proven. Liquidity use refused "
                "on this basis alone, per explicit milestone instruction.",
    },
    "depth_level_ordering": {
        "status": "QUALIFIED",
        "note": "Bid levels descending by price, ask levels ascending, in every sample observed.",
    },
    "snapshot_vs_event": {
        "status": "UNQUALIFIED",
        "note": "History queries returned several near-identical consecutive records a few "
                "seconds apart -- consistent with periodic snapshot polling rather than "
                "pure on-change events, but not confirmed either way.",
    },
    "historical_point_in_time": {
        "status": "QUALIFIED",
        "note": "2026-08-10 pit probe: a query scoped to the closed 2026-08-07 session "
                "returned genuinely 2026-08-07-dated, differently-priced book content.",
    },
    "pagination_window": {
        "status": "UNQUALIFIED",
        "note": "A same-day window is required (wider windows were rejected in the general "
                "pass); the exact maximum range was not determined. nextPageToken is "
                "populated (more rows exist) but was not paged through.",
    },
    "freshness_delay": {
        "status": "QUALIFIED",
        "note": "The recent_90min pit sample returned quotes only a few seconds old at "
                "request time -- real-time or near-real-time, not end-of-day-only.",
    },
    "empty_book_semantics": {
        "status": "QUALIFIED",
        "note": "HPG boardId=T1 quotes_latest returned `{\"quotes\": []}`, HTTP 200 -- "
                "directly observed, not inferred.",
    },
    "auction_session_behavior": {
        "status": "UNQUALIFIED",
        "note": "Not directly tested in this bounded pilot.",
    },
    "put_through_contamination_risk": {
        "status": "UNQUALIFIED",
        "note": "T1-board depth returned zero rows while G1/G4 returned real books at the "
                "same instant -- a lead consistent with the put-through hypothesis, not proof.",
    },
}


class DnseBidAskError(ValueError):
    """Fail-closed rejection while normalizing a DNSE quotes response."""


def _level(raw: Mapping[str, Any], *, level_index: int) -> dict[str, Any]:
    price = raw.get("price")
    quantity = raw.get("quantity")
    if isinstance(price, bool) or not isinstance(price, (int, float)) or price <= 0:
        raise DnseBidAskError("invalid_level_price")
    if isinstance(quantity, bool) or not isinstance(quantity, (int, float)) or quantity < 0:
        raise DnseBidAskError("invalid_level_quantity")
    return {"level": level_index, "price": price, "quantity": quantity}


def _levels(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise DnseBidAskError("levels_field_not_a_list")
    return [_level(item, level_index=index + 1) for index, item in enumerate(raw)]


def normalize_snapshot(
    raw_quote: Mapping[str, Any],
    *,
    source_endpoint: str,
    query_window: Mapping[str, Any] | None = None,
    probe_observed_at: str | None = None,
) -> dict[str, Any]:
    """One canonical bid/ask depth snapshot from one raw DNSE quote record.

    Fails closed on malformed input (missing identity fields, malformed
    levels, or a crossed/inverted book) rather than silently producing a
    partial or wrong-shaped record. Never derives a field DNSE did not
    supply.
    """
    ticker = raw_quote.get("symbol")
    board_id = raw_quote.get("boardId")
    session_time = raw_quote.get("time")
    if not isinstance(ticker, str) or not ticker:
        raise DnseBidAskError("missing_or_invalid_ticker")
    if not isinstance(board_id, str) or not board_id:
        raise DnseBidAskError("missing_or_invalid_board_id")
    if not isinstance(session_time, str) or not session_time:
        raise DnseBidAskError("missing_or_invalid_observation_timestamp")

    bid_levels = _levels(raw_quote.get("bid"))
    ask_levels = _levels(raw_quote.get("offer"))
    if bid_levels and ask_levels:
        best_bid = max(level["price"] for level in bid_levels)
        best_ask = min(level["price"] for level in ask_levels)
        if best_bid >= best_ask:
            raise DnseBidAskError("bid_ask_inverted_or_crossed")

    session_date = session_time.split(" ", 1)[0]
    freshness = None
    if probe_observed_at:
        freshness = {"probe_observed_at": probe_observed_at, "source_time": session_time}

    return {
        "ticker": ticker,
        "exchange": raw_quote.get("marketId"),
        "board_id": board_id,
        "session_date": session_date,
        "observed_at": session_time,
        "source": PROVIDER,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "bid_levels": bid_levels,
        "ask_levels": ask_levels,
        "depth_level_count": max(len(bid_levels), len(ask_levels)),
        "price_unit": PRICE_UNIT,
        "freshness": freshness,
        "provenance": {
            "source_endpoint": source_endpoint,
            "isin": raw_quote.get("isin"),
            "query_window": dict(query_window) if query_window else None,
        },
        "qualification_status": ACTIVE_QUALIFICATION_STATUS,
        "warnings": list(WARNINGS),
    }


def normalize_response(
    payload: Mapping[str, Any],
    *,
    source_endpoint: str,
    query_window: Mapping[str, Any] | None = None,
    probe_observed_at: str | None = None,
) -> list[dict[str, Any]]:
    """Normalize every quote record in a raw `quotes`/`quotes/latest` response.

    An empty or absent `quotes` list is a valid, honestly-represented empty
    book -- it returns an empty list, not an error.
    """
    quotes = payload.get("quotes")
    if quotes is None:
        return []
    if isinstance(quotes, (str, bytes)) or not isinstance(quotes, Sequence):
        raise DnseBidAskError("quotes_field_not_a_list")
    return [
        normalize_snapshot(
            item, source_endpoint=source_endpoint, query_window=query_window,
            probe_observed_at=probe_observed_at,
        )
        for item in quotes
    ]


def assert_point_in_time_consistency(
    *, requested_session_date: str, observations: Sequence[Mapping[str, Any]]
) -> None:
    """Fail closed if any observation's session_date does not match what was
    requested -- guards a historical query against silently returning (or
    being fed) today's current state instead of the requested past state."""
    for observation in observations:
        if observation.get("session_date") != requested_session_date:
            raise DnseBidAskError(
                f"point_in_time_mismatch:{observation.get('session_date')!r}"
                f"!={requested_session_date!r}"
            )


def serialize(record: Mapping[str, Any]) -> str:
    """Deterministic JSON serialization -- same input always produces the
    same bytes, so a caller can hash/compare/replay a retained observation."""
    return json.dumps(record, sort_keys=True, default=str)


def active_capability_contract() -> dict[str, Any]:
    """The canonical, active DNSE bid/ask capability verdict, assembled once
    from the 2026-08-10 bounded pilots' evidence. Consumers read this rather
    than re-deriving a verdict from raw evidence files."""
    return {
        "schema_version": VERSION,
        "provider": PROVIDER,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "formal_result": ACTIVE_QUALIFICATION_STATUS,
        "price_unit": PRICE_UNIT,
        "quantity_unit_qualified": QUANTITY_UNIT_QUALIFIED,
        "point_in_time_qualified": POINT_IN_TIME_QUALIFIED,
        "dimensions": {k: dict(v) for k, v in DIMENSION_QUALIFICATION.items()},
        "warnings": list(WARNINGS),
        "evidence": (
            "operations-review/dnse-bid-ask-foreign-flow-qualification-20260810/"
            "probe_results.json"
        ),
    }


def assert_fail_closed(status: str) -> None:
    """Refuse an out-of-vocabulary or unearned qualification status."""
    if status not in FORMAL_RESULTS:
        raise DnseBidAskError(f"formal_result_invalid:{status}")
    if status == LIQUIDITY_ANALYTICS and not QUANTITY_UNIT_QUALIFIED:
        raise DnseBidAskError("liquidity_analytics_requires_a_qualified_quantity_unit")
