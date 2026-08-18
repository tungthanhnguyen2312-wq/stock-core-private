"""Canonical, fail-closed semantics for market volume and value fields.

This is a capability boundary, not a calculation layer.  It records the exact
meaning that retained source evidence supports and refuses a consumer whose
requested semantic type, unit, or downstream use does not match.  In
particular, a numeric value never substitutes for a numeric volume merely
because both are often described as "turnover" in user-facing screens.

The contract deliberately leaves execution composition questions to P0-B.2.
Known dimensions are retained, while every unestablished dimension is spelled
``unknown`` rather than filled from a provider label or another field.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


VERSION = "1.1.0"

# DNSE's retained daily-OHLC representation establishes ``v`` as the general
# volume field.  No equally identified daily traded-value field is present in
# that source contract, so consumers have an explicit negative fact to test
# rather than attempting to substitute price * volume or a foreign-flow value.
DNSE_DAILY_TRADED_VALUE_FIELD = "UNKNOWN/NOT_CONFIRMED"


class SemanticContractError(ValueError):
    """A field cannot satisfy the requested semantic or downstream use."""


class SemanticType(str, Enum):
    TRADED_VOLUME_SHARES = "TRADED_VOLUME_SHARES"
    TRADED_VALUE_VND = "TRADED_VALUE_VND"
    RELATIVE_VOLUME = "RELATIVE_VOLUME"
    FOREIGN_BUY_VALUE_VND = "FOREIGN_BUY_VALUE_VND"
    FOREIGN_SELL_VALUE_VND = "FOREIGN_SELL_VALUE_VND"
    FOREIGN_NET_VALUE_VND = "FOREIGN_NET_VALUE_VND"
    FOREIGN_BUY_VOLUME_SHARES = "FOREIGN_BUY_VOLUME_SHARES"
    FOREIGN_SELL_VOLUME_SHARES = "FOREIGN_SELL_VOLUME_SHARES"
    FOREIGN_NET_VOLUME_SHARES = "FOREIGN_NET_VOLUME_SHARES"
    FOREIGN_ROOM_OR_HEADROOM = "FOREIGN_ROOM_OR_HEADROOM"
    DERIVED_PRICE_TIMES_VOLUME_VND = "DERIVED_PRICE_TIMES_VOLUME_VND"
    UNKNOWN_UNQUALIFIED = "UNKNOWN_UNQUALIFIED"


class Unit(str, Enum):
    SHARES = "shares"
    VND = "VND"
    MILLION_VND = "million_VND"
    RATIO = "ratio"
    UNKNOWN = "unknown"


class QualificationState(str, Enum):
    QUALIFIED = "qualified"
    PARTIALLY_QUALIFIED = "partially_qualified"
    UNQUALIFIED = "unqualified"
    UNKNOWN = "unknown"


class ScopeState(str, Enum):
    INCLUDED = "included"
    EXCLUDED = "excluded"
    UNKNOWN = "unknown"
    PARTIALLY_OBSERVED = "partially_observed"


class DownstreamUse(str, Enum):
    DISPLAY = "display"
    PROVIDER_SCOPED_ANALYTICS = "provider_scoped_analytics"
    OBSERVED_VALUE_STATISTICS = "observed_value_statistics"
    FOREIGN_VALUE_FLOW_ANALYTICS = "foreign_value_flow_analytics"
    MARKET_WIDE_TURNOVER = "market_wide_turnover"
    MARKET_LIQUIDITY = "market_liquidity"
    EXECUTION_SIZING = "execution_sizing"
    GENERIC_FOREIGN_FLOW = "generic_foreign_flow"


@dataclass(frozen=True)
class ScopeMetadata:
    """Execution and identity scope, independently recorded for each field."""

    session: ScopeState = ScopeState.UNKNOWN
    board: ScopeState = ScopeState.UNKNOWN
    put_through: ScopeState = ScopeState.UNKNOWN
    odd_lot: ScopeState = ScopeState.UNKNOWN
    auction: ScopeState = ScopeState.UNKNOWN
    opening_auction: ScopeState = ScopeState.UNKNOWN
    closing_auction: ScopeState = ScopeState.UNKNOWN
    continuous_session: ScopeState = ScopeState.UNKNOWN

    def record(self) -> dict[str, str]:
        return {
            "session_scope": self.session.value,
            "board_scope": self.board.value,
            "put_through_inclusion": self.put_through.value,
            "odd_lot_inclusion": self.odd_lot.value,
            "auction_inclusion": self.auction.value,
            "ato_inclusion": self.opening_auction.value,
            "atc_inclusion": self.closing_auction.value,
            "continuous_session_inclusion": self.continuous_session.value,
        }


@dataclass(frozen=True)
class FieldContract:
    """Machine-readable semantic identity for exactly one field or derived quantity."""

    key: str
    provider: str
    field_identity: str
    unit: Unit
    semantic_type: SemanticType
    qualification: QualificationState
    scope: ScopeMetadata
    pit_as_of_identity: Mapping[str, Any]
    eligible_uses: frozenset[DownstreamUse]
    prohibited_uses: frozenset[DownstreamUse]
    volume_corporate_action_adjustment: ScopeState = ScopeState.UNKNOWN
    evidence: str = ""

    def record(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "provider": self.provider,
            "field_identity": self.field_identity,
            "unit": self.unit.value,
            "semantic_type": self.semantic_type.value,
            "qualification_state": self.qualification.value,
            **self.scope.record(),
            "volume_corporate_action_adjustment": self.volume_corporate_action_adjustment.value,
            "pit_as_of_identity": dict(sorted(self.pit_as_of_identity.items())),
            "downstream_eligible_uses": sorted(use.value for use in self.eligible_uses),
            "prohibited_uses": sorted(use.value for use in self.prohibited_uses),
            "evidence": self.evidence,
        }


_LIQUIDITY_AND_TURNOVER_USES = frozenset(
    {DownstreamUse.MARKET_WIDE_TURNOVER, DownstreamUse.MARKET_LIQUIDITY, DownstreamUse.EXECUTION_SIZING}
)


def _contract(
    key: str,
    provider: str,
    field_identity: str,
    unit: Unit,
    semantic_type: SemanticType,
    qualification: QualificationState,
    *,
    scope: ScopeMetadata = ScopeMetadata(),
    pit_as_of_identity: Mapping[str, Any] | None = None,
    eligible_uses: frozenset[DownstreamUse] = frozenset(),
    prohibited_uses: frozenset[DownstreamUse] = frozenset(),
    volume_corporate_action_adjustment: ScopeState = ScopeState.UNKNOWN,
    evidence: str,
) -> FieldContract:
    return FieldContract(
        key=key,
        provider=provider,
        field_identity=field_identity,
        unit=unit,
        semantic_type=semantic_type,
        qualification=qualification,
        scope=scope,
        pit_as_of_identity=pit_as_of_identity or {},
        eligible_uses=eligible_uses,
        prohibited_uses=prohibited_uses,
        volume_corporate_action_adjustment=volume_corporate_action_adjustment,
        evidence=evidence,
    )


# These are projections of existing, retained source contracts.  This module does
# not re-qualify a provider and does not turn a bounded empirical finding into a
# provider-wide or exchange-wide claim.
FIELD_CONTRACTS: dict[str, FieldContract] = {
    "dnse.daily.ohlc.v": _contract(
        "dnse.daily.ohlc.v", "DNSE", "daily OHLC v", Unit.SHARES,
        SemanticType.TRADED_VOLUME_SHARES, QualificationState.PARTIALLY_QUALIFIED,
        # The source shape establishes the field and share-volume semantics,
        # not its execution composition.  Every execution dimension therefore
        # remains unknown until a separately bounded reconciliation proves it.
        scope=ScopeMetadata(),
        pit_as_of_identity={
            "endpoint": "/price/ohlc",
            "resolution": "1D",
            "session_identity": "provider_daily_bar",
            "total_session": "unknown",
        },
        eligible_uses=frozenset({DownstreamUse.DISPLAY, DownstreamUse.PROVIDER_SCOPED_ANALYTICS}),
        prohibited_uses=_LIQUIDITY_AND_TURNOVER_USES,
        evidence=(
            "dnse_market_data.MARKET_DATA_ENDPOINTS['ohlc'] plus retained DNSE OHLC "
            "schema/tests: daily array field v; execution scope not qualified"
        ),
    ),
    "vci.daily.v": _contract(
        "vci.daily.v", "VCI", "daily v / accumulatedVolume", Unit.SHARES,
        SemanticType.TRADED_VOLUME_SHARES, QualificationState.PARTIALLY_QUALIFIED,
        scope=ScopeMetadata(auction=ScopeState.PARTIALLY_OBSERVED),
        pit_as_of_identity={"as_of": "unknown", "session_identity": "provider_daily_row"},
        eligible_uses=frozenset({DownstreamUse.DISPLAY, DownstreamUse.PROVIDER_SCOPED_ANALYTICS}),
        prohibited_uses=_LIQUIDITY_AND_TURNOVER_USES,
        evidence="vci_volume_composition.active_contract: shares; composition unresolved",
    ),
    "kbs.daily.v": _contract(
        "kbs.daily.v", "KBS", "daily v / price-board volume_accumulated", Unit.SHARES,
        SemanticType.TRADED_VOLUME_SHARES, QualificationState.PARTIALLY_QUALIFIED,
        scope=ScopeMetadata(
            session=ScopeState.PARTIALLY_OBSERVED,
            put_through=ScopeState.EXCLUDED,
            odd_lot=ScopeState.UNKNOWN,
            auction=ScopeState.INCLUDED,
            continuous_session=ScopeState.INCLUDED,
        ),
        pit_as_of_identity={"as_of": "unknown", "tested_session": "2026-08-07"},
        eligible_uses=frozenset({DownstreamUse.DISPLAY, DownstreamUse.PROVIDER_SCOPED_ANALYTICS}),
        prohibited_uses=_LIQUIDITY_AND_TURNOVER_USES,
        evidence="kbs_trade_scope_qualification.active_contract: one tested session, three tickers",
    ),
    "kbs.daily.va": _contract(
        "kbs.daily.va", "KBS", "observed daily va", Unit.VND,
        SemanticType.TRADED_VALUE_VND, QualificationState.PARTIALLY_QUALIFIED,
        pit_as_of_identity={"as_of": "unknown", "coverage": "row_and_window_specific"},
        eligible_uses=frozenset({DownstreamUse.DISPLAY, DownstreamUse.OBSERVED_VALUE_STATISTICS}),
        prohibited_uses=_LIQUIDITY_AND_TURNOVER_USES,
        evidence="kbs_trading_value_coverage: observed VND only; coverage is fail-closed",
    ),
    "vci.intraday.accumulatedValue": _contract(
        "vci.intraday.accumulatedValue", "VCI", "intraday accumulatedValue", Unit.MILLION_VND,
        SemanticType.TRADED_VALUE_VND, QualificationState.PARTIALLY_QUALIFIED,
        pit_as_of_identity={"as_of": "unknown", "session_identity": "intraday_accumulator"},
        eligible_uses=frozenset({DownstreamUse.DISPLAY}),
        prohibited_uses=_LIQUIDITY_AND_TURNOVER_USES,
        evidence="vci_volume_basis: accumulatedValue is millions of VND; composition unresolved",
    ),
    "dnse.foreign_buy_value": _contract(
        "dnse.foreign_buy_value", "DNSE", "totalBuyTradedAmount", Unit.VND,
        SemanticType.FOREIGN_BUY_VALUE_VND, QualificationState.PARTIALLY_QUALIFIED,
        scope=ScopeMetadata(session=ScopeState.INCLUDED),
        pit_as_of_identity={"as_of": "qualified_per_observation", "session_identity": "tradingSessionId"},
        eligible_uses=frozenset({DownstreamUse.DISPLAY, DownstreamUse.FOREIGN_VALUE_FLOW_ANALYTICS}),
        prohibited_uses=_LIQUIDITY_AND_TURNOVER_USES | frozenset({DownstreamUse.GENERIC_FOREIGN_FLOW}),
        evidence="dnse_foreign_flow_capability: raw VND session cumulative foreign value",
    ),
    "dnse.foreign_sell_value": _contract(
        "dnse.foreign_sell_value", "DNSE", "totalSellTradedAmount", Unit.VND,
        SemanticType.FOREIGN_SELL_VALUE_VND, QualificationState.PARTIALLY_QUALIFIED,
        scope=ScopeMetadata(session=ScopeState.INCLUDED),
        pit_as_of_identity={"as_of": "qualified_per_observation", "session_identity": "tradingSessionId"},
        eligible_uses=frozenset({DownstreamUse.DISPLAY, DownstreamUse.FOREIGN_VALUE_FLOW_ANALYTICS}),
        prohibited_uses=_LIQUIDITY_AND_TURNOVER_USES | frozenset({DownstreamUse.GENERIC_FOREIGN_FLOW}),
        evidence="dnse_foreign_flow_capability: raw VND session cumulative foreign value",
    ),
    "dnse.foreign_net_value": _contract(
        "dnse.foreign_net_value", "DNSE", "totalBuyTradedAmount - totalSellTradedAmount", Unit.VND,
        SemanticType.FOREIGN_NET_VALUE_VND, QualificationState.PARTIALLY_QUALIFIED,
        scope=ScopeMetadata(session=ScopeState.INCLUDED),
        pit_as_of_identity={"as_of": "qualified_per_observation", "session_identity": "tradingSessionId"},
        eligible_uses=frozenset({DownstreamUse.DISPLAY, DownstreamUse.FOREIGN_VALUE_FLOW_ANALYTICS}),
        prohibited_uses=_LIQUIDITY_AND_TURNOVER_USES | frozenset({DownstreamUse.GENERIC_FOREIGN_FLOW}),
        evidence="dnse_foreign_flow_capability.derive_net: same-record VND difference",
    ),
    "dnse.foreign_buy_volume": _contract(
        "dnse.foreign_buy_volume", "DNSE", "totalBuyVolume", Unit.SHARES,
        SemanticType.FOREIGN_BUY_VOLUME_SHARES, QualificationState.UNQUALIFIED,
        scope=ScopeMetadata(session=ScopeState.INCLUDED),
        pit_as_of_identity={"as_of": "qualified_per_observation", "session_identity": "tradingSessionId"},
        eligible_uses=frozenset({DownstreamUse.DISPLAY}),
        prohibited_uses=_LIQUIDITY_AND_TURNOVER_USES | frozenset({DownstreamUse.GENERIC_FOREIGN_FLOW}),
        evidence="dnse_foreign_flow_capability: shares magnitude is not independently qualified",
    ),
    "dnse.foreign_sell_volume": _contract(
        "dnse.foreign_sell_volume", "DNSE", "totalSellVolume", Unit.SHARES,
        SemanticType.FOREIGN_SELL_VOLUME_SHARES, QualificationState.UNQUALIFIED,
        scope=ScopeMetadata(session=ScopeState.INCLUDED),
        pit_as_of_identity={"as_of": "qualified_per_observation", "session_identity": "tradingSessionId"},
        eligible_uses=frozenset({DownstreamUse.DISPLAY}),
        prohibited_uses=_LIQUIDITY_AND_TURNOVER_USES | frozenset({DownstreamUse.GENERIC_FOREIGN_FLOW}),
        evidence="dnse_foreign_flow_capability: shares magnitude is not independently qualified",
    ),
    "dnse.foreign_net_volume": _contract(
        "dnse.foreign_net_volume", "DNSE", "totalBuyVolume - totalSellVolume", Unit.SHARES,
        SemanticType.FOREIGN_NET_VOLUME_SHARES, QualificationState.UNQUALIFIED,
        scope=ScopeMetadata(session=ScopeState.INCLUDED),
        pit_as_of_identity={"as_of": "qualified_per_observation", "session_identity": "tradingSessionId"},
        eligible_uses=frozenset({DownstreamUse.DISPLAY}),
        prohibited_uses=_LIQUIDITY_AND_TURNOVER_USES | frozenset({DownstreamUse.GENERIC_FOREIGN_FLOW}),
        evidence="dnse_foreign_flow_capability: shares magnitude is not independently qualified",
    ),
    "legacy.rel_vol": _contract(
        "legacy.rel_vol", "LEGACY_DERIVED", "volume / average_volume20", Unit.RATIO,
        SemanticType.RELATIVE_VOLUME, QualificationState.PARTIALLY_QUALIFIED,
        pit_as_of_identity={"as_of": "inherits_input_rows"},
        eligible_uses=frozenset({DownstreamUse.DISPLAY, DownstreamUse.PROVIDER_SCOPED_ANALYTICS}),
        prohibited_uses=_LIQUIDITY_AND_TURNOVER_USES,
        evidence="candlestick_patterns.rel_vol_calc: within-series ratio, not market liquidity",
    ),
    "legacy.gtgd20_ty": _contract(
        "legacy.gtgd20_ty", "LEGACY_DERIVED", "rolling mean(close * volume) / 1e9", Unit.VND,
        SemanticType.DERIVED_PRICE_TIMES_VOLUME_VND, QualificationState.UNQUALIFIED,
        pit_as_of_identity={"as_of": "inherits_input_rows"},
        eligible_uses=frozenset({DownstreamUse.DISPLAY, DownstreamUse.PROVIDER_SCOPED_ANALYTICS}),
        prohibited_uses=_LIQUIDITY_AND_TURNOVER_USES,
        evidence="kbs_trading_value_coverage.NON_VA_DERIVED_QUANTITIES: not observed va or official turnover",
    ),
    "dnse.foreign_room_headroom": _contract(
        "dnse.foreign_room_headroom", "DNSE", "foreignerBuyPossibleQuantity / foreignerOrderLimitQuantity",
        Unit.UNKNOWN, SemanticType.FOREIGN_ROOM_OR_HEADROOM, QualificationState.UNQUALIFIED,
        pit_as_of_identity={"as_of": "observation_timestamp_only"},
        eligible_uses=frozenset({DownstreamUse.DISPLAY}),
        prohibited_uses=frozenset({DownstreamUse.FOREIGN_VALUE_FLOW_ANALYTICS, DownstreamUse.GENERIC_FOREIGN_FLOW})
        | _LIQUIDITY_AND_TURNOVER_USES,
        evidence="dnse_foreign_flow_capability: relationship/meaning remains unqualified",
    ),
}


def field_contract(key: str) -> FieldContract:
    """Return one registered contract; an unregistered field is never assumed usable."""
    try:
        return FIELD_CONTRACTS[key]
    except KeyError as exc:
        raise SemanticContractError(f"unregistered_volume_value_field:{key}") from exc


def require(
    key: str,
    *,
    semantic_type: SemanticType,
    unit: Unit,
    downstream_use: DownstreamUse,
) -> FieldContract:
    """Validate one consumer request with exact semantic, unit, and use matching."""
    contract = field_contract(key)
    if contract.semantic_type is not semantic_type:
        raise SemanticContractError(
            f"semantic_type_mismatch:{key}:{contract.semantic_type.value}!={semantic_type.value}"
        )
    if contract.unit is not unit:
        raise SemanticContractError(f"unit_mismatch:{key}:{contract.unit.value}!={unit.value}")
    if downstream_use not in contract.eligible_uses:
        raise SemanticContractError(f"downstream_use_not_eligible:{key}:{downstream_use.value}")
    if downstream_use in contract.prohibited_uses:
        raise SemanticContractError(f"downstream_use_prohibited:{key}:{downstream_use.value}")
    return contract


def contract_snapshot() -> dict[str, Any]:
    """Stable JSON-ready projection for consumers and deterministic tests."""
    return {
        "schema_version": VERSION,
        "fields": {key: FIELD_CONTRACTS[key].record() for key in sorted(FIELD_CONTRACTS)},
    }


def assert_fail_closed(snapshot: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    """Reject an attempted snapshot that broadens an unqualified field's uses."""
    snap = snapshot if snapshot is not None else contract_snapshot()
    fields = snap.get("fields")
    if not isinstance(fields, Mapping):
        raise SemanticContractError("contract_fields_missing")
    for key, record in fields.items():
        if record.get("semantic_type") == SemanticType.FOREIGN_ROOM_OR_HEADROOM.value:
            uses = set(record.get("downstream_eligible_uses") or [])
            if DownstreamUse.FOREIGN_VALUE_FLOW_ANALYTICS.value in uses:
                raise SemanticContractError(f"room_headroom_cannot_become_flow:{key}")
        if record.get("semantic_type") == SemanticType.DERIVED_PRICE_TIMES_VOLUME_VND.value:
            if record.get("qualification_state") == QualificationState.QUALIFIED.value:
                raise SemanticContractError(f"derived_price_times_volume_cannot_become_traded_value:{key}")
    dnse_daily = fields.get("dnse.daily.ohlc.v")
    if dnse_daily is not None:
        if dnse_daily.get("semantic_type") != SemanticType.TRADED_VOLUME_SHARES.value:
            raise SemanticContractError("dnse_daily_ohlc_v_must_remain_traded_volume_shares")
        if dnse_daily.get("unit") != Unit.SHARES.value:
            raise SemanticContractError("dnse_daily_ohlc_v_must_remain_shares")
        forbidden = {use.value for use in _LIQUIDITY_AND_TURNOVER_USES}
        eligible = set(dnse_daily.get("downstream_eligible_uses") or [])
        if eligible & forbidden:
            raise SemanticContractError("dnse_daily_ohlc_v_cannot_be_execution_eligible")
        for dimension in (
            "session_scope", "board_scope", "put_through_inclusion", "odd_lot_inclusion",
            "auction_inclusion", "ato_inclusion", "atc_inclusion", "continuous_session_inclusion",
        ):
            if dnse_daily.get(dimension) != ScopeState.UNKNOWN.value:
                raise SemanticContractError(f"dnse_daily_ohlc_v_scope_must_remain_unknown:{dimension}")
    if DNSE_DAILY_TRADED_VALUE_FIELD != "UNKNOWN/NOT_CONFIRMED":
        raise SemanticContractError("dnse_daily_traded_value_must_not_be_invented")
    return snap
