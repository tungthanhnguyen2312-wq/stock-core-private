"""Fail-closed historical regular-board matched-liquidity contract.

This module consumes canonical Trades evidence and its materialization coverage
manifest.  It deliberately keeps a retained trade print, a qualified matched
share measurement, and a qualified matched-VND measurement separate.  A caller
must supply explicit unit semantics; numerical magnitude is never a substitute.

The module is a data contract, not a liquidity score, sizing, execution, or
price-basis authority.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence


CONTRACT_VERSION = "market_wide_historical_matched_liquidity/v1"
REGULAR_BOARD = "G1"
REGULAR_BOARD_SEMANTIC = "MATCHED_ROUND_LOT"

COMPLETE = "COMPLETE"
KNOWN_INCOMPLETE = "KNOWN_INCOMPLETE"
KNOWN_FAILED = "KNOWN_FAILED"
NOT_ACQUIRED = "NOT_ACQUIRED"
NO_TRADES_CONFIRMED = "NO_TRADES_CONFIRMED"
SEMANTICS_UNQUALIFIED = "SEMANTICS_UNQUALIFIED"

QUALIFIED_MATCHED_VOLUME = "QUALIFIED_MATCHED_VOLUME"
QUALIFIED_MATCHED_VALUE = "QUALIFIED_MATCHED_VALUE"
COVERAGE_RESTRICTED = "COVERAGE_RESTRICTED"

EXACT_WINDOW = "EXACT_WINDOW"
COVERAGE_RESTRICTED_WINDOW = "COVERAGE_RESTRICTED_WINDOW"
INSUFFICIENT_WINDOW = "INSUFFICIENT_WINDOW"
SEMANTICS_UNQUALIFIED_WINDOW = "SEMANTICS_UNQUALIFIED"

FEATURES = (
    ("ADV20_MATCHED_SHARES", "volume", 20, "shares"),
    ("ADV60_MATCHED_SHARES", "volume", 60, "shares"),
    ("ADTV20_MATCHED_VND", "value", 20, "VND"),
    ("ADTV60_MATCHED_VND", "value", 60, "VND"),
)

_SUCCESS_STATES = {
    "ORIGINAL_SUCCESS",
    "ORIGINAL_SUCCESS_EMPTY",
    "REPAIR_RECOVERED_SUCCESS",
    "REPAIR_RECOVERED_SUCCESS_EMPTY",
}
_EMPTY_STATES = {"ORIGINAL_SUCCESS_EMPTY", "REPAIR_RECOVERED_SUCCESS_EMPTY"}


class MatchedLiquidityContractError(ValueError):
    """Raised for a malformed contract input rather than silently coercing it."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def _identity(prefix: str, value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{prefix}:{digest}"}


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    return _identity("market_wide_historical_matched_liquidity", value)


def _decimal(value: Any, *, field: str) -> Decimal:
    if isinstance(value, bool):
        raise MatchedLiquidityContractError(f"NUMERIC_FIELD_INVALID:{field}")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MatchedLiquidityContractError(f"NUMERIC_FIELD_INVALID:{field}") from exc
    if not parsed.is_finite() or parsed < 0:
        raise MatchedLiquidityContractError(f"NUMERIC_FIELD_INVALID:{field}")
    return parsed


def _number(value: Decimal) -> int | str:
    return int(value) if value == value.to_integral_value() else format(value, "f")


def unit_coverage_from_manifest(units: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """Normalize one explicit materialization state per ticker/session.

    Empty selected raw pages are genuine confirmed no-trade evidence.  An absent
    unit is intentionally not filled in; consumers classify it as NOT_ACQUIRED.
    """
    normalized: dict[tuple[str, str], dict[str, Any]] = {}
    for item in units:
        ticker = str(item.get("instrument") or "").upper()
        session = str(item.get("session") or "")
        status = str(item.get("logical_status") or "")
        if not ticker or not session or not status:
            raise MatchedLiquidityContractError("CANONICAL_UNIT_IDENTITY_MISSING")
        key = (ticker, session)
        if key in normalized:
            raise MatchedLiquidityContractError(f"DUPLICATE_CANONICAL_UNIT:{ticker}:{session}")
        if status == "REMAINING_FAILED":
            completeness, blockers = KNOWN_FAILED, ["KNOWN_TASK160_FAILURE"]
        elif status in _EMPTY_STATES:
            completeness, blockers = NO_TRADES_CONFIRMED, []
        elif status in _SUCCESS_STATES:
            completeness, blockers = COMPLETE, []
        else:
            completeness, blockers = KNOWN_INCOMPLETE, [f"CANONICAL_UNIT_STATUS:{status}"]
        normalized[key] = {
            "ticker": ticker,
            "session": session,
            "logical_status": status,
            "session_completeness": completeness,
            "selected_raw_record_count": item.get("selected_raw_record_count"),
            "source_page_identity": item.get("selected_observation_id"),
            "source_page_payload_hash": item.get("selected_raw_payload_hash"),
            "blockers": blockers,
        }
    return normalized


def aggregate_regular_board_trades(
    *,
    ticker: str,
    session: str,
    trades: Iterable[Mapping[str, Any]],
    session_completeness: str,
    unit_semantics: Mapping[str, Any],
    source_lineage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate a complete canonical Trade cohort without guessing its units.

    ``quantity_shares_qualified`` and ``price_vnd_per_share_qualified`` must
    be separately asserted by a source contract.  The multiplier values are
    ignored unless their corresponding qualification flag is true.
    """
    ticker = str(ticker).upper()
    if session_completeness in {KNOWN_FAILED, KNOWN_INCOMPLETE, NOT_ACQUIRED}:
        return {
            "ticker": ticker, "session": session, "regular_board": REGULAR_BOARD,
            "regular_board_semantic": REGULAR_BOARD_SEMANTIC,
            "session_completeness": session_completeness,
            "matched_volume_state": session_completeness,
            "matched_value_state": session_completeness,
            "regular_board_matched_volume_shares": None,
            "regular_board_matched_value_vnd": None,
            "record_count": 0, "duplicate_records_discarded": 0,
            "input_content_identities": [], "source_lineage": dict(source_lineage or {}),
            "blockers": [session_completeness],
        }

    all_rows = [dict(row) for row in trades]
    unique: dict[str, Mapping[str, Any]] = {}
    duplicate_count = 0
    for row in all_rows:
        identity = str(row.get("raw_record_identity") or hashlib.sha256(_canonical(row).encode("utf-8")).hexdigest())
        if identity in unique:
            duplicate_count += 1
            continue
        unique[identity] = row
    regular = [row for row in unique.values() if str(row.get("board_id") or "") == REGULAR_BOARD]
    content_ids = sorted({str(row.get("source_page_payload_hash") or "") for row in unique.values() if row.get("source_page_payload_hash")})
    other_board_counts = Counter(str(row.get("board_id") or "UNKNOWN") for row in unique.values() if str(row.get("board_id") or "") != REGULAR_BOARD)

    if not regular:
        return {
            "ticker": ticker, "session": session, "regular_board": REGULAR_BOARD,
            "regular_board_semantic": REGULAR_BOARD_SEMANTIC,
            "session_completeness": NO_TRADES_CONFIRMED,
            "matched_volume_state": NO_TRADES_CONFIRMED,
            "matched_value_state": NO_TRADES_CONFIRMED,
            "regular_board_matched_volume_shares": 0,
            "regular_board_matched_value_vnd": 0,
            "record_count": 0, "duplicate_records_discarded": duplicate_count,
            "input_content_identities": content_ids, "source_lineage": dict(source_lineage or {}),
            "other_board_record_count": dict(sorted(other_board_counts.items())), "blockers": [],
        }

    quantity_raw = sum((_decimal(row.get("quantity"), field="quantity") for row in regular), Decimal("0"))
    quantity_qualified = bool(unit_semantics.get("quantity_shares_qualified"))
    price_qualified = bool(unit_semantics.get("price_vnd_per_share_qualified"))
    quantity_multiplier = _decimal(unit_semantics.get("quantity_multiplier", 1), field="quantity_multiplier") if quantity_qualified else None
    price_multiplier = _decimal(unit_semantics.get("price_multiplier", 1), field="price_multiplier") if price_qualified else None
    matched_volume = quantity_raw * quantity_multiplier if quantity_multiplier is not None else None
    matched_value = None
    if matched_volume is not None and price_multiplier is not None:
        matched_value = sum(
            (_decimal(row.get("price"), field="price") * price_multiplier * _decimal(row.get("quantity"), field="quantity") * quantity_multiplier for row in regular),
            Decimal("0"),
        )
    blockers = []
    if not quantity_qualified:
        blockers.append("QUANTITY_UNIT_UNQUALIFIED")
    if not price_qualified:
        blockers.append("PRICE_UNIT_UNQUALIFIED")
    return {
        "ticker": ticker, "session": session, "regular_board": REGULAR_BOARD,
        "regular_board_semantic": REGULAR_BOARD_SEMANTIC,
        "session_completeness": COMPLETE,
        "matched_volume_state": QUALIFIED_MATCHED_VOLUME if matched_volume is not None else SEMANTICS_UNQUALIFIED,
        "matched_value_state": QUALIFIED_MATCHED_VALUE if matched_value is not None else SEMANTICS_UNQUALIFIED,
        "regular_board_matched_quantity_raw": _number(quantity_raw),
        "regular_board_matched_volume_shares": _number(matched_volume) if matched_volume is not None else None,
        "regular_board_matched_value_vnd": _number(matched_value) if matched_value is not None else None,
        "record_count": len(regular), "duplicate_records_discarded": duplicate_count,
        "input_content_identities": content_ids, "source_lineage": dict(source_lineage or {}),
        "other_board_record_count": dict(sorted(other_board_counts.items())), "blockers": blockers,
        "calculation_identity": "canonical_trade_price_vnd_x_canonical_matched_quantity_shares/v1" if matched_value is not None else None,
    }


def daily_cells_from_retained_evidence(
    *,
    unit_coverage: Mapping[tuple[str, str], Mapping[str, Any]],
    reconciliation_rows: Iterable[Mapping[str, Any]],
    qualified_value_rows: Iterable[Mapping[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Reuse the existing canonical-Trades/FHSC reconciled daily value lane.

    The legacy evidence validates value only for exact rows.  It does *not*
    promote a general shares volume field, even where ``g1_share_quantity`` is
    retained.  This preserves the existing authority boundary.
    """
    recon = {(str(row.get("ticker") or "").upper(), str(row.get("session") or "")): dict(row) for row in reconciliation_rows}
    values = {(str(row.get("ticker") or "").upper(), str(row.get("session") or "")): dict(row) for row in qualified_value_rows}
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    for key, unit in sorted(unit_coverage.items()):
        ticker, session = key
        completeness = unit["session_completeness"]
        common = {
            "ticker": ticker, "session": session, "regular_board": REGULAR_BOARD,
            "regular_board_semantic": REGULAR_BOARD_SEMANTIC,
            "session_completeness": completeness,
            "source_lineage": {
                "canonical_unit_logical_status": unit.get("logical_status"),
                "source_page_identity": unit.get("source_page_identity"),
                "source_page_payload_hash": unit.get("source_page_payload_hash"),
            },
            "regular_board_matched_volume_shares": None,
            "regular_board_matched_value_vnd": None,
            "regular_board_matched_quantity_raw": None,
            "calculation_identity": None,
        }
        if completeness == KNOWN_FAILED:
            cells[key] = {**common, "matched_volume_state": KNOWN_FAILED, "matched_value_state": KNOWN_FAILED,
                          "blockers": ["KNOWN_TASK160_FAILURE"]}
            continue
        if completeness == NO_TRADES_CONFIRMED:
            cells[key] = {**common, "matched_volume_state": NO_TRADES_CONFIRMED,
                          "matched_value_state": NO_TRADES_CONFIRMED,
                          "regular_board_matched_volume_shares": 0,
                          "regular_board_matched_value_vnd": 0, "blockers": []}
            continue
        row, exact = recon.get(key), values.get(key)
        recon_status = str((row or {}).get("status") or "")
        raw_quantity = (row or {}).get("g1_share_quantity")
        if recon_status == "EXACT" and exact is not None:
            cells[key] = {**common, "matched_volume_state": SEMANTICS_UNQUALIFIED,
                          "matched_value_state": QUALIFIED_MATCHED_VALUE,
                          "regular_board_matched_value_vnd": exact.get("matched_value_vnd"),
                          "regular_board_matched_quantity_raw": exact.get("g1_share_quantity", raw_quantity),
                          "calculation_identity": "sum(G1.matchPrice_x_10_x_G1.matchQtty)_x_10_x_1000/v1",
                          "blockers": ["MATCHED_VOLUME_SHARES_NOT_INDEPENDENTLY_QUALIFIED_AS_GENERIC_FIELD"]}
        elif recon_status == "CONFLICT":
            cells[key] = {**common, "matched_volume_state": SEMANTICS_UNQUALIFIED,
                          "matched_value_state": SEMANTICS_UNQUALIFIED,
                          "regular_board_matched_quantity_raw": raw_quantity,
                          "blockers": ["FHSC_MATCHED_VALUE_RECONCILIATION_CONFLICT"]}
        elif recon_status == "NOT_COMPARABLE":
            cells[key] = {**common, "matched_volume_state": SEMANTICS_UNQUALIFIED,
                          "matched_value_state": SEMANTICS_UNQUALIFIED,
                          "regular_board_matched_quantity_raw": raw_quantity,
                          "blockers": ["BOARD_OR_VALUE_SEMANTICS_UNQUALIFIED"]}
        else:
            cells[key] = {**common, "matched_volume_state": SEMANTICS_UNQUALIFIED,
                          "matched_value_state": SEMANTICS_UNQUALIFIED,
                          "regular_board_matched_quantity_raw": raw_quantity,
                          "blockers": ["NO_INDEPENDENT_MATCHED_VALUE_ANCHOR"]}
    return cells


def resolve_trailing_window(*, calendar: Sequence[str], target_session: str, size: int) -> dict[str, Any]:
    """Resolve an injected governed trading-session calendar without weekday fill."""
    ordered = sorted({str(item) for item in calendar if item})
    if target_session not in ordered:
        return {"state": "TARGET_SESSION_NOT_IN_GOVERNED_CALENDAR", "target_session": target_session,
                "expected_sessions": size, "sessions": [], "calendar_identity": _identity("trading_session_calendar", {"sessions": ordered})["artifact_identity"]}
    eligible = [session for session in ordered if session <= target_session]
    return {"state": "RESOLVED" if len(eligible) >= size else "INSUFFICIENT_CALENDAR_HISTORY",
            "target_session": target_session, "expected_sessions": size,
            "sessions": eligible[-size:],
            "calendar_identity": _identity("trading_session_calendar", {"sessions": ordered})["artifact_identity"]}


def calculate_trailing_feature(
    *,
    ticker: str,
    feature_id: str,
    metric: str,
    unit: str,
    target_session: str,
    calendar: Sequence[str],
    size: int,
    daily_cells: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    """Calculate an exact trailing statistic only over an exact trading window."""
    window = resolve_trailing_window(calendar=calendar, target_session=target_session, size=size)
    key_name = "regular_board_matched_volume_shares" if metric == "volume" else "regular_board_matched_value_vnd"
    state_name = "matched_volume_state" if metric == "volume" else "matched_value_state"
    qualified_state = QUALIFIED_MATCHED_VOLUME if metric == "volume" else QUALIFIED_MATCHED_VALUE
    if window["state"] != "RESOLVED":
        return {
            "feature_id": feature_id, "ticker": ticker, "target_session": target_session,
            "status": INSUFFICIENT_WINDOW, "value": None, "unit": unit,
            "method": "trading_session_window_canonical_regular_board_matched/v1",
            "expected_sessions": size, "qualified_sessions": 0, "missing_sessions": size,
            "coverage_ratio": 0.0, "window_identity": window["calendar_identity"],
            "window_sessions": window["sessions"], "blockers": [window["state"]],
        }
    qualified, missing, semantic, failed, values = [], [], [], [], []
    for session in window["sessions"]:
        daily = daily_cells.get((ticker, session))
        if daily is None:
            missing.append(session)
            continue
        state = daily.get(state_name)
        if state == qualified_state:
            value = daily.get(key_name)
            if value is None:
                semantic.append(session)
            else:
                qualified.append(session)
                values.append(_decimal(value, field=key_name))
        elif state == NO_TRADES_CONFIRMED:
            qualified.append(session)
            values.append(Decimal("0"))
        elif state == KNOWN_FAILED:
            failed.append(session)
        elif state in {NOT_ACQUIRED, KNOWN_INCOMPLETE}:
            missing.append(session)
        else:
            semantic.append(session)
    exact = len(qualified) == size and not missing and not semantic and not failed
    if exact:
        value = sum(values) / Decimal(size)
        status, blockers = EXACT_WINDOW, []
    elif semantic:
        value, status, blockers = None, SEMANTICS_UNQUALIFIED_WINDOW, ["SEMANTICS_UNQUALIFIED_IN_WINDOW"]
    elif len(qualified) > 0:
        value, status, blockers = None, COVERAGE_RESTRICTED_WINDOW, ["NO_EXACT_AVERAGE_EMITTED_FOR_COVERAGE_RESTRICTED_WINDOW"]
    else:
        value, status, blockers = None, INSUFFICIENT_WINDOW, ["NO_QUALIFIED_SESSIONS_IN_WINDOW"]
    blockers += (["KNOWN_FAILED_SESSION_IN_WINDOW"] if failed else [])
    blockers += (["MISSING_OR_NOT_ACQUIRED_SESSION_IN_WINDOW"] if missing else [])
    return {
        "feature_id": feature_id, "ticker": ticker, "target_session": target_session,
        "status": status, "value": _number(value) if value is not None else None, "unit": unit,
        "method": "trading_session_window_canonical_regular_board_matched/v1",
        "expected_sessions": size, "qualified_sessions": len(qualified),
        "missing_sessions": len(missing) + len(failed) + len(semantic),
        "coverage_ratio": len(qualified) / size, "window_identity": window["calendar_identity"],
        "window_sessions": window["sessions"], "qualified_window_sessions": qualified,
        "missing_window_sessions": sorted(set(missing + failed + semantic)),
        "blockers": blockers, "calendar_day_imputation": False,
    }


def build_ticker_liquidity_context(
    *, ticker: str, target_session: str, calendar: Sequence[str], daily_cells: Mapping[tuple[str, str], Mapping[str, Any]]
) -> dict[str, Any]:
    """The smallest additive Current-Research context; never emits a size."""
    features = {
        feature_id: calculate_trailing_feature(ticker=ticker, feature_id=feature_id, metric=metric, unit=unit,
                                               target_session=target_session, calendar=calendar, size=size,
                                               daily_cells=daily_cells)
        for feature_id, metric, size, unit in FEATURES
    }
    exact_any = any(record["status"] == EXACT_WINDOW for record in features.values())
    restricted_any = any(record["status"] == COVERAGE_RESTRICTED_WINDOW for record in features.values())
    semantic_any = any(record["status"] == SEMANTICS_UNQUALIFIED_WINDOW for record in features.values())
    current = daily_cells.get((ticker, target_session))
    if exact_any:
        # An exact historical window supports research context only.  This
        # foundation deliberately creates no execution-input authority.
        state, research, execution = "EXACT_MATCHED_LIQUIDITY_RESEARCH_AVAILABLE", True, False
    elif restricted_any:
        state, research, execution = "RESEARCH_PROXY_ONLY", True, False
    elif semantic_any:
        state, research, execution = "SEMANTICS_BLOCKED", False, False
    elif current is None:
        state, research, execution = "INCOMPLETE_TRADES_HISTORY", False, False
    else:
        state, research, execution = "INSUFFICIENT_HISTORY", False, False
    blockers = sorted({blocker for feature in features.values() for blocker in feature["blockers"]})
    return {
        "ticker": ticker, "target_session": target_session, "liquidity_state": state,
        "current_regular_board_matched_value_vnd": (current or {}).get("regular_board_matched_value_vnd"),
        "features": features, "research_liquidity_eligible": research,
        "execution_liquidity_input_eligible": execution,
        "position_sizing_eligible": False, "fitness": "CURRENT_RESEARCH_MATCHED_LIQUIDITY" if research else "BLOCKED_BY_EVIDENCE",
        "blockers": blockers,
        "lineage": {"daily_cell": (current or {}).get("source_lineage"), "calendar_sessions": len(set(calendar))},
    }


def coverage_distribution(cells: Mapping[tuple[str, str], Mapping[str, Any]]) -> dict[str, Any]:
    """Compact, deterministic coverage summary without duplicating retained Trades."""
    volume = Counter(str(row.get("matched_volume_state")) for row in cells.values())
    value = Counter(str(row.get("matched_value_state")) for row in cells.values())
    completeness = Counter(str(row.get("session_completeness")) for row in cells.values())
    blockers = Counter(blocker for row in cells.values() for blocker in (row.get("blockers") or []))
    return {
        "ticker_session_pairs": len(cells),
        "matched_volume_state_distribution": dict(sorted(volume.items())),
        "matched_value_state_distribution": dict(sorted(value.items())),
        "session_completeness_distribution": dict(sorted(completeness.items())),
        "blocker_distribution": dict(sorted(blockers.items())),
    }


def build_artifact(
    *,
    target_session: str,
    universe: Mapping[str, Mapping[str, Any]],
    calendar: Sequence[str],
    daily_cells: Mapping[tuple[str, str], Mapping[str, Any]],
    source_identities: Mapping[str, Any],
) -> dict[str, Any]:
    records = {
        ticker: build_ticker_liquidity_context(ticker=ticker, target_session=target_session, calendar=calendar, daily_cells=daily_cells)
        for ticker in sorted(universe)
    }
    states = Counter(record["liquidity_state"] for record in records.values())
    feature_counts = {
        feature_id: dict(sorted(Counter(record["features"][feature_id]["status"] for record in records.values()).items()))
        for feature_id, _, _, _ in FEATURES
    }
    payload: dict[str, Any] = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "target_session": target_session,
        "calendar": {"sessions": sorted({str(item) for item in calendar}), "calendar_day_imputation": False},
        "source_identities": dict(source_identities), "records": records,
        "coverage": {"universe_denominator": len(records), "liquidity_state_distribution": dict(sorted(states.items())),
                     "feature_status_distribution": feature_counts, "daily": coverage_distribution(daily_cells)},
        "authority_boundary": {
            "canonical_trades_primary": True, "daily_provider_v_or_va_promoted": False,
            "raw_as_traded_promoted": False, "pit_promoted": False,
            "position_sizing_eligible": False, "participation_cap_embedded": False,
            "execution_or_slippage_model": "NOT_EMITTED",
        },
    }
    return {**payload, **content_identity(payload)}
