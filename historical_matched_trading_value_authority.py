"""Historical daily matched-trading-value authority and ADTV20 contract.

This is a liquidity-input contract, not a sizing engine. It reuses the already
qualified G1 formula ``sum(G1.matchPrice * G1.matchQtty) * 10 * 1000`` VND and
never aliases total, odd-lot, or put-through value to matched value.

``ADTV20_MATCHED_VALUE`` is the average of qualified matched value over the
expected trailing 20 trading sessions of the applicable session calendar. It is
not ``ADV``, not "any 20 qualified rows from a longer corpus", and not a
position-size input. ``ADV20_MATCHED_VOLUME`` is not emitted unless matched
volume is independently qualified, which this module does not claim.

The G1 formula is not rewritten when another composition (for example G1+G4)
fits some conflicts. FHSC matched sometimes includes odd-lot quantity at a
different scale; those rows remain ``CONFLICT``. Generic ADTV20 applicability
is HOSE discriminating exact sessions only.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence

from field_temporal_contract import stable_id
from historical_matched_traded_value_authority import (
    KNOWN_BOARDS,
    MATCHED_VALUE_FORMULA,
    QUALIFIED_BOARD,
)
from market_wide_current_valuation_input_scaleout import official_research_universe_tickers

CONTRACT_VERSION = "historical_matched_trading_value_authority/v1"
ARTIFACT_TYPE = "HISTORICAL_MATCHED_TRADING_VALUE_AUTHORITY"
FEATURE_ADTV20 = "ADTV20_MATCHED_VALUE"
FEATURE_ADV20_VOLUME = "ADV20_MATCHED_VOLUME"
EXPECTED_ADTV_SESSIONS = 20
APPLICABLE_EXCHANGES = frozenset({"HOSE"})

EXACT_RECONCILED = "EXACT_RECONCILED"
COVERAGE_RESTRICTED_RECONCILED = "COVERAGE_RESTRICTED_RECONCILED"
INSUFFICIENT_DISCRIMINATION = "INSUFFICIENT_DISCRIMINATION"
RESTRICTED_SCOPE_EXACT = "RESTRICTED_SCOPE_EXACT"
CONFLICTING = "CONFLICTING"
UNAVAILABLE = "UNAVAILABLE"
NOT_COMPARABLE = "NOT_COMPARABLE"

ADTV20_READY = "ADTV20_READY"
ADTV20_PARTIAL = "ADTV20_PARTIAL"
ADTV20_BLOCKED = "ADTV20_BLOCKED"
ADTV20_NOT_APPLICABLE = "ADTV20_NOT_APPLICABLE"
ADTV20_INSUFFICIENT_HISTORY = "ADTV20_INSUFFICIENT_HISTORY"

MATCHED_VALUE_OBSERVATION_QUALIFIED = "MATCHED_VALUE_OBSERVATION_QUALIFIED_COVERAGE_RESTRICTED"
MATCHED_VALUE_RESTRICTED_SCOPE = "MATCHED_VALUE_RESTRICTED_SCOPE_NON_HOSE_EXACT"
MATCHED_VALUE_NON_DISCRIMINATING = "MATCHED_VALUE_NON_DISCRIMINATING_EXACT_NOT_PROMOTED"
UNAVAILABLE_NO_VALUE_ANCHOR = "UNAVAILABLE_NO_INDEPENDENT_MATCHED_VALUE_ANCHOR"
UNAVAILABLE_MISSING_TRADES = "UNAVAILABLE_MISSING_FROM_RETAINED_TRADES_CORPUS"
TERMINAL_DISPOSITIONS = frozenset({
    MATCHED_VALUE_OBSERVATION_QUALIFIED, MATCHED_VALUE_RESTRICTED_SCOPE,
    MATCHED_VALUE_NON_DISCRIMINATING, UNAVAILABLE_NO_VALUE_ANCHOR, UNAVAILABLE_MISSING_TRADES,
})

CONFLICT_FHSC_INCLUDES_G4_RAW_SHARES = "FHSC_MATCHED_EQUALS_G1_PLUS_G4_RAW_SHARES"
CONFLICT_NO_G4_NO_PT = "NO_G4_NO_PT_STILL_CONFLICT"
CONFLICT_UNEXPLAINED = "UNEXPLAINED_RESIDUAL"

PUT_THROUGH_BOARDS = frozenset({"T1", "T3", "T4", "T6"})
ODD_LOT_BOARDS = frozenset({"G4", "T4", "T6"})
REGULAR_MATCHED_BOARD = "G1"

SOURCE_SEMANTICS = {
    "dnse_trades_history_g1": {
        "identity": "matched_trading_value_vnd",
        "proven_scope": "HOSE discriminating G1-only exact FHSC anchors; HNX/UPCOM exacts are restricted-scope",
        "formula": MATCHED_VALUE_FORMULA,
        "unit": "VND",
        "promotable_generic": False,
        "applicable_exchanges": sorted(APPLICABLE_EXCHANGES),
    },
    "dnse_trades_history_g4": {
        "identity": "odd_lot_matched_component",
        "proven_scope": "board label documented; value/quantity scale not qualified",
        "promotable_generic": False,
    },
    "dnse_trades_history_t_boards": {
        "identity": "put_through_component",
        "proven_scope": "T1/T3 round-lot put-through; T4/T6 odd-lot put-through; not in matched value",
        "promotable_generic": False,
    },
    "dnse_daily_ohlc_v": {
        "identity": "hose_empirical_matched_volume_shares_shadow",
        "proven_scope": "HOSE discriminating DNSE v = FHSC matched volume; not a value field",
        "promotable_generic": False,
    },
    "dnse_daily_ohlc_va": {
        "identity": None,
        "proven_scope": "OBSERVED_ABSENT from DNSE daily OHLC",
        "promotable_generic": False,
    },
    "grossTradeAmount": {
        "identity": "unresolved_board_dependent_cumulative_counter",
        "proven_scope": "not matched-value authority",
        "promotable_generic": False,
    },
}


def _quantity(value: Any) -> Decimal:
    if isinstance(value, bool):
        return Decimal("0")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
    return result if result.is_finite() else Decimal("0")


def classify_session_discrimination(board_composition: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """A session proves composition only when odd-lot and/or put-through quantity is nonzero."""
    odd_lot = Decimal("0")
    put_through = Decimal("0")
    regular = Decimal("0")
    observed = []
    for row in board_composition:
        board = str(row.get("board_id") or "")
        qty = _quantity(row.get("raw_quantity"))
        observed.append(board)
        if board == REGULAR_MATCHED_BOARD:
            regular += qty
        if board in ODD_LOT_BOARDS:
            odd_lot += qty
        if board in PUT_THROUGH_BOARDS:
            put_through += qty
    discriminating = odd_lot > 0 or put_through > 0
    return {
        "status": "DISCRIMINATING" if discriminating else "NON_DISCRIMINATING",
        "regular_matched_g1_raw_quantity": str(regular),
        "odd_lot_raw_quantity": str(odd_lot),
        "put_through_raw_quantity": str(put_through),
        "observed_boards": sorted(set(observed)),
        "missing_boards_not_imputed_zero": sorted(set(KNOWN_BOARDS) - set(observed)),
    }


def session_value_reconciliation(row: Mapping[str, Any], *, exchange: str | None = None) -> str:
    fhsc = row.get("fhsc_reconciliation") or {}
    discrimination = classify_session_discrimination(row.get("board_composition") or [])
    if fhsc.get("status") == "CONFLICT" or row.get("qualification_status") == "CONFLICTING":
        return CONFLICTING
    if row.get("status") == "CONFLICT":
        return CONFLICTING
    if row.get("status") == "NOT_COMPARABLE":
        return NOT_COMPARABLE
    if row.get("qualification_status") != "MATCHED_VALUE_QUALIFIED" or fhsc.get("status") != "EXACT":
        return UNAVAILABLE
    if discrimination["status"] != "DISCRIMINATING":
        return INSUFFICIENT_DISCRIMINATION
    if exchange is not None and exchange not in APPLICABLE_EXCHANGES:
        return RESTRICTED_SCOPE_EXACT
    return EXACT_RECONCILED


def trailing_expected_sessions(
    trading_sessions: Sequence[str] | None, *, expected_sessions: int = EXPECTED_ADTV_SESSIONS,
) -> list[str]:
    """Last ``expected_sessions`` dates of an explicit trading calendar. No weekday fill."""
    ordered = sorted({str(session) for session in (trading_sessions or []) if session})
    if not ordered:
        return []
    return ordered[-expected_sessions:] if len(ordered) >= expected_sessions else ordered


def classify_conflict_cause(row: Mapping[str, Any]) -> dict[str, Any]:
    """Classify an FHSC/G1 conflict. Does not rewrite the G1 formula."""
    composition = row.get("board_composition") or []
    boards = {str(item.get("board_id") or ""): _quantity(item.get("raw_quantity")) for item in composition}
    g1_shares = _quantity(row.get("g1_share_quantity"))
    if g1_shares == 0 and "G1" in boards:
        g1_shares = boards["G1"] * Decimal("10")
    g4_raw = boards.get("G4", Decimal("0"))
    put_through = sum(boards.get(board, Decimal("0")) for board in PUT_THROUGH_BOARDS)
    fhsc_volume = _quantity(row.get("fhsc_matched_volume") or (row.get("fhsc_reconciliation") or {}).get("fhsc_matched_volume"))
    has_g4 = g4_raw > 0
    has_pt = put_through > 0
    if fhsc_volume == g1_shares + g4_raw and has_g4:
        cause = CONFLICT_FHSC_INCLUDES_G4_RAW_SHARES
    elif not has_g4 and not has_pt:
        cause = CONFLICT_NO_G4_NO_PT
    else:
        cause = CONFLICT_UNEXPLAINED
    return {
        "cause": cause,
        "has_g4": has_g4,
        "has_put_through": has_pt,
        "g4_raw_quantity": str(g4_raw),
        "g1_share_quantity": str(g1_shares),
        "fhsc_matched_volume": str(fhsc_volume),
        "volume_delta": str(fhsc_volume - g1_shares),
        "formula_rewritten": False,
    }


def reconcile_expected_session_grid(
    *,
    official_ticker_count: int,
    trading_session_count: int,
    evaluated_pairs: int,
    exact: int,
    conflict: int,
    not_comparable: int,
    unavailable: int,
    structurally_absent: int,
) -> dict[str, Any]:
    """Exact ticker-session denominator. Residual must be zero."""
    expected = official_ticker_count * trading_session_count
    accounted = exact + conflict + not_comparable + unavailable + structurally_absent
    residual = expected - accounted
    evaluated_check = exact + conflict + not_comparable + unavailable
    if residual != 0 or evaluated_check != evaluated_pairs:
        raise ValueError(
            f"SESSION_GRID_RESIDUAL_NONZERO:expected={expected} accounted={accounted} "
            f"residual={residual} evaluated={evaluated_pairs} evaluated_check={evaluated_check}"
        )
    return {
        "expected_ticker_session_pairs": expected,
        "evaluated_pairs": evaluated_pairs,
        "exact": exact,
        "conflict": conflict,
        "not_comparable": not_comparable,
        "unavailable": unavailable,
        "structurally_absent_from_retained_trades": structurally_absent,
        "residual": residual,
        "denominator_reconciles": True,
    }


def _adtv20_row(
    *,
    ticker: str,
    exchange: str | None,
    window: Sequence[str],
    by_session: Mapping[str, Mapping[str, Any]],
    expected_sessions: int,
) -> dict[str, Any]:
    applicable = exchange in APPLICABLE_EXCHANGES if exchange is not None else False
    qualified_sessions: list[str] = []
    conflict_sessions: list[str] = []
    unavailable_sessions: list[str] = []
    non_discriminating_sessions: list[str] = []
    restricted_sessions: list[str] = []
    not_comparable_sessions: list[str] = []
    values: list[Decimal] = []
    for session in window:
        row = by_session.get(session)
        status = row.get("value_reconciliation") if row else UNAVAILABLE
        if row is None:
            unavailable_sessions.append(session)
            continue
        if status == EXACT_RECONCILED:
            qualified_sessions.append(session)
            raw_value = row.get("matched_trading_value_vnd")
            if raw_value is None:
                raw_value = row.get("matched_value_vnd")
            if raw_value is None:
                unavailable_sessions.append(session)
                qualified_sessions.pop()
            else:
                values.append(_quantity(raw_value))
        elif status == CONFLICTING:
            conflict_sessions.append(session)
        elif status == INSUFFICIENT_DISCRIMINATION:
            non_discriminating_sessions.append(session)
        elif status == RESTRICTED_SCOPE_EXACT:
            restricted_sessions.append(session)
        elif status == NOT_COMPARABLE:
            not_comparable_sessions.append(session)
        else:
            unavailable_sessions.append(session)
    qualified_count = len(qualified_sessions)
    window_complete = (
        applicable
        and len(window) == expected_sessions
        and qualified_count == expected_sessions
        and len(values) == expected_sessions
    )
    if not applicable:
        status_name = ADTV20_NOT_APPLICABLE
        reason = "ADTV20_APPLICABLE_ONLY_TO_HOSE_DISCRIMINATING_EXACT_SESSIONS"
    elif not window:
        status_name = ADTV20_BLOCKED
        reason = "EXPECTED_TRADING_SESSION_CALENDAR_REQUIRED"
    elif window_complete:
        status_name = ADTV20_READY
        reason = None
    elif qualified_count > 0:
        status_name = ADTV20_PARTIAL
        reason = "NO_AVERAGE_EMITTED_UNTIL_20_EXPECTED_COMPLETE_QUALIFIED_TRADING_SESSIONS"
    else:
        status_name = ADTV20_BLOCKED
        reason = "NO_AVERAGE_EMITTED_UNTIL_20_EXPECTED_COMPLETE_QUALIFIED_TRADING_SESSIONS"
    average = None
    if window_complete:
        total = sum(values)
        average = int(total / expected_sessions) if total == total.to_integral_value() else format(total / expected_sessions, "f")
    return {
        "feature_id": FEATURE_ADTV20,
        "status": status_name,
        "expected_sessions": expected_sessions,
        "qualified_sessions": qualified_count,
        "conflict_sessions": len(conflict_sessions),
        "unavailable_sessions": len(unavailable_sessions),
        "non_discriminating_sessions": len(non_discriminating_sessions),
        "restricted_scope_sessions": len(restricted_sessions),
        "not_comparable_sessions": len(not_comparable_sessions),
        "observed_sessions": qualified_count,
        "coverage_ratio": (qualified_count / expected_sessions) if expected_sessions else 0,
        "first_session": window[0] if window else None,
        "last_session": window[-1] if window else None,
        "unit": "VND",
        "identity": "matched_trading_value_vnd",
        "adtv20_matched_value_vnd": average,
        "window_sessions": list(window),
        "qualified_window_sessions": qualified_sessions,
        "calendar_day_imputation": False,
        "gap_filled_with_older_session": False,
        "participation_policy_embedded": False,
        "applicable_exchange": exchange,
        "reason": reason,
    }


def adtv20_matched_value(
    rows: Iterable[Mapping[str, Any]],
    *,
    expected_sessions: int = EXPECTED_ADTV_SESSIONS,
    expected_trading_sessions: Sequence[str] | None = None,
    exchange_by_ticker: Mapping[str, str] | None = None,
    tickers: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Average over the expected trailing 20 trading sessions, never any 20 qualified rows.

    Missing, conflicting, non-discriminating, and restricted-scope sessions inside
    that window are not replaced by older qualified observations. Holidays are not
    imputed. A missing observation is not zero.
    """
    window = trailing_expected_sessions(expected_trading_sessions, expected_sessions=expected_sessions)
    exchanges = {str(ticker): str(value) for ticker, value in dict(exchange_by_ticker or {}).items()}
    by_ticker_session: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    seen: set[str] = set()
    for row in rows:
        ticker = str(row.get("ticker") or "")
        session = str(row.get("session") or "")
        if not ticker or not session:
            continue
        seen.add(ticker)
        evaluated = dict(row)
        if "value_reconciliation" not in evaluated:
            evaluated["value_reconciliation"] = session_value_reconciliation(
                evaluated, exchange=exchanges.get(ticker) or evaluated.get("exchange_or_market"),
            )
        if "matched_trading_value_vnd" not in evaluated:
            evaluated["matched_trading_value_vnd"] = evaluated.get("matched_value_vnd")
        by_ticker_session[ticker][session] = evaluated
    universe = list(tickers) if tickers is not None else sorted(seen)
    result: dict[str, Any] = {}
    for ticker in universe:
        result[ticker] = _adtv20_row(
            ticker=ticker,
            exchange=exchanges.get(ticker),
            window=window,
            by_session=by_ticker_session.get(ticker, {}),
            expected_sessions=expected_sessions,
        )
    return result


def adv20_matched_volume_status() -> dict[str, Any]:
    """Volume is not derived from a passing value contract."""
    return {
        "feature_id": FEATURE_ADV20_VOLUME,
        "status": "NOT_EMITTED",
        "ready_count": 0,
        "reason": "MATCHED_TRADING_VOLUME_SHARES_NOT_INDEPENDENTLY_QUALIFIED_AS_GENERIC_FIELD",
    }


def build_historical_matched_trading_value_authority(
    *,
    official_universe: Mapping[str, Any],
    qualified_rows: Sequence[Mapping[str, Any]],
    trades_universe: Sequence[str],
    source_identities: Mapping[str, Any] | None = None,
    trades_source_contract: Mapping[str, Any] | None = None,
    expected_trading_sessions: Sequence[str] | None = None,
    reconciliation_rows: Sequence[Mapping[str, Any]] | None = None,
    session_grid: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """One terminal disposition per official-universe ticker; no sizing policy."""
    tickers = official_research_universe_tickers(official_universe)
    if not tickers:
        raise ValueError("OFFICIAL_RESEARCH_UNIVERSE_EMPTY")
    trades = {str(ticker).upper() for ticker in trades_universe}
    official_records = official_universe.get("records") or {}
    exchange_by_ticker = {
        ticker: str((official_records.get(ticker) or {}).get("exchange_or_market") or "")
        for ticker in tickers
    }
    session_rows = []
    for row in qualified_rows:
        discrimination = classify_session_discrimination(row.get("board_composition") or [])
        exchange = exchange_by_ticker.get(str(row["ticker"])) or None
        status = session_value_reconciliation(row, exchange=exchange)
        session_rows.append({
            "ticker": row["ticker"], "session": row["session"],
            "matched_trading_value_vnd": row.get("matched_value_vnd"),
            "matched_trading_volume_shares": None,
            "g1_share_quantity": row.get("g1_share_quantity"),
            "value_reconciliation": status,
            "discrimination": discrimination,
            "board_composition": row.get("board_composition"),
            "qualification_status": row.get("qualification_status"),
            "fhsc_reconciliation": row.get("fhsc_reconciliation"),
            "exchange_or_market": exchange,
        })
    evaluation_rows = list(session_rows)
    if reconciliation_rows:
        seen = {(item["ticker"], item["session"]) for item in evaluation_rows}
        for row in reconciliation_rows:
            key = (row.get("ticker"), row.get("session"))
            if key in seen:
                continue
            status = session_value_reconciliation(row, exchange=exchange_by_ticker.get(str(row.get("ticker") or "")))
            evaluation_rows.append({
                "ticker": row["ticker"], "session": row["session"],
                "matched_trading_value_vnd": row.get("dnse_matched_value_vnd") or row.get("matched_value_vnd"),
                "matched_trading_volume_shares": None,
                "g1_share_quantity": row.get("g1_share_quantity"),
                "value_reconciliation": status,
                "discrimination": None,
                "board_composition": row.get("board_composition"),
                "qualification_status": row.get("qualification_status") or row.get("status"),
                "fhsc_reconciliation": row.get("fhsc_reconciliation") or {
                    "status": row.get("status"),
                    "fhsc_matched_volume": row.get("fhsc_matched_volume"),
                    "fhsc_matched_value": row.get("fhsc_matched_value"),
                },
                "exchange_or_market": exchange_by_ticker.get(str(row.get("ticker") or "")),
            })
    hose_disc_rows = [item for item in session_rows if item["value_reconciliation"] == EXACT_RECONCILED]
    if not hose_disc_rows:
        cohort_reconciliation = UNAVAILABLE
    elif any(item["value_reconciliation"] == CONFLICTING for item in session_rows):
        cohort_reconciliation = CONFLICTING
    elif all(item["value_reconciliation"] == EXACT_RECONCILED for item in session_rows):
        cohort_reconciliation = COVERAGE_RESTRICTED_RECONCILED
    else:
        cohort_reconciliation = UNAVAILABLE
    records: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        ticker_sessions = [item for item in session_rows if item["ticker"] == ticker]
        hose_disc = [item for item in ticker_sessions if item["value_reconciliation"] == EXACT_RECONCILED]
        restricted = [item for item in ticker_sessions if item["value_reconciliation"] == RESTRICTED_SCOPE_EXACT]
        nondisc = [item for item in ticker_sessions if item["value_reconciliation"] == INSUFFICIENT_DISCRIMINATION]
        if hose_disc:
            disposition = MATCHED_VALUE_OBSERVATION_QUALIFIED
            blockers = ["ADTV20_REQUIRES_20_OF_20_EXPECTED_TRAILING_TRADING_SESSIONS"]
            fitness = "MATCHED_VALUE_OBSERVATION_ONLY"
            stored_sessions = hose_disc
        elif restricted:
            disposition = MATCHED_VALUE_RESTRICTED_SCOPE
            blockers = ["MATCHED_VALUE_EXACT_OUTSIDE_HOSE_APPLICABLE_SCOPE"]
            fitness = "RESTRICTED_SCOPE_NOT_GENERIC"
            stored_sessions = restricted
        elif nondisc:
            disposition = MATCHED_VALUE_NON_DISCRIMINATING
            blockers = ["EXACT_NUMERICAL_MATCH_NOT_DISCRIMINATING"]
            fitness = "NOT_ELIGIBLE"
            stored_sessions = nondisc
        elif ticker in trades:
            disposition = UNAVAILABLE_NO_VALUE_ANCHOR
            blockers = ["NO_INDEPENDENT_EXACT_MATCHED_VALUE_ANCHOR"]
            fitness = "NOT_ELIGIBLE"
            stored_sessions = []
        else:
            disposition = UNAVAILABLE_MISSING_TRADES
            blockers = ["MISSING_FROM_RETAINED_TRADES_CORPUS"]
            fitness = "NOT_ELIGIBLE"
            stored_sessions = []
        records[ticker] = {
            "ticker": ticker,
            "authority_tier": disposition,
            "exchange_or_market": exchange_by_ticker.get(ticker) or None,
            "matched_trading_value_vnd_sessions": stored_sessions,
            "session_count": len(stored_sessions),
            "blockers": blockers,
            "fitness_for_use": fitness,
            "adtv20_matched_value": None,
            "adv20_matched_volume": None,
            "position_sizing": "BLOCKED",
            "participation_policy": "NOT_EMBEDDED",
        }
    window = trailing_expected_sessions(expected_trading_sessions)
    adtv = adtv20_matched_value(
        evaluation_rows,
        expected_trading_sessions=expected_trading_sessions,
        exchange_by_ticker=exchange_by_ticker,
        tickers=tickers,
    )
    for ticker, feature in adtv.items():
        if ticker in records:
            records[ticker]["adtv20_matched_value"] = feature
            if feature["status"] == ADTV20_READY:
                records[ticker]["blockers"] = [
                    blocker for blocker in records[ticker]["blockers"]
                    if blocker != "ADTV20_REQUIRES_20_OF_20_EXPECTED_TRAILING_TRADING_SESSIONS"
                ]
    ready = sum(1 for feature in adtv.values() if feature["status"] == ADTV20_READY)
    partial = sum(1 for feature in adtv.values() if feature["status"] == ADTV20_PARTIAL)
    blocked = sum(1 for feature in adtv.values() if feature["status"] == ADTV20_BLOCKED)
    not_applicable = sum(1 for feature in adtv.values() if feature["status"] == ADTV20_NOT_APPLICABLE)
    recon_counts = Counter(item["value_reconciliation"] for item in session_rows)
    disc_counts = Counter((item.get("discrimination") or {}).get("status") for item in session_rows if item.get("discrimination"))
    tiers = Counter(row["authority_tier"] for row in records.values())
    unexplained = abs(len(records) - len(tickers))
    if unexplained or any(row["authority_tier"] not in TERMINAL_DISPOSITIONS for row in records.values()):
        raise ValueError("MATCHED_VALUE_DISPOSITION_CONTRACT_BROKEN")
    exchange_qualified = Counter(
        row["exchange_or_market"] for row in records.values()
        if row["authority_tier"] == MATCHED_VALUE_OBSERVATION_QUALIFIED
    )
    artifact = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "source_identities": dict(source_identities or {}),
        "source_semantics": SOURCE_SEMANTICS,
        "matched_value_contract": {
            "identity": "matched_trading_value_vnd",
            "formula": MATCHED_VALUE_FORMULA,
            "unit": "VND",
            "qualified_board": QUALIFIED_BOARD,
            "excluded_boards_preserved": ["G4", "T1", "T3", "T4", "T6"],
            "auction_versus_continuous": "NOT_SPLIT_NO_UNIVERSAL_SESSION_CLOCK",
            "gross_trade_amount": "NOT_USED",
            "ohlc_v_not_a_value_field": True,
            "formula_status": "QUALIFIED_EMPIRICAL_SCOPE" if hose_disc_rows else "NOT_QUALIFIED",
            "cohort_reconciliation": cohort_reconciliation,
            "applicable_exchanges": sorted(APPLICABLE_EXCHANGES),
            "g4_not_added_to_resolve_conflicts": True,
        },
        "adtv20_contract": {
            "feature_id": FEATURE_ADTV20,
            "definition": (
                "average of HOSE discriminating exact matched_trading_value_vnd over the "
                "expected trailing 20 trading sessions of the supplied session calendar; "
                "a missing, conflicting, non-discriminating, or restricted session is not "
                "replaced by an older qualified observation"
            ),
            "unit": "VND",
            "calendar_day_imputation": False,
            "coverage_tolerance_17_of_20": False,
            "gap_filled_with_older_session": False,
            "missing_observation_is_zero": False,
            "expected_sessions": EXPECTED_ADTV_SESSIONS,
            "trailing_window": window,
            "applicable_exchanges": sorted(APPLICABLE_EXCHANGES),
            "ready_count": ready,
            "partial_count": partial,
            "blocked_count": blocked,
            "not_applicable_count": not_applicable,
        },
        "adv20_volume_contract": adv20_matched_volume_status(),
        "reconciliation": {
            "eligible_anchor_sessions": len(qualified_rows),
            "complete_qualified_sessions": len(session_rows),
            "hose_discriminating_exact_sessions": len(hose_disc_rows),
            "discriminating_sessions": disc_counts.get("DISCRIMINATING", 0),
            "non_discriminating_sessions": disc_counts.get("NON_DISCRIMINATING", 0),
            "value_reconciliation_counts": dict(sorted(recon_counts.items())),
            "cohort_status": cohort_reconciliation,
        },
        "session_grid": dict(session_grid or {}),
        "trades_source_contract": dict(trades_source_contract or {}),
        "records": records,
        "qualified_session_rows": hose_disc_rows,
        "coverage": {
            "universe_denominator": len(records),
            "trades_universe_denominator": len(trades),
            "denominator_reconciles": unexplained == 0 and sum(tiers.values()) == len(records),
            "unexplained_count": unexplained,
            "authority_tier_distribution": dict(sorted(tiers.items())),
            "adtv20_ready_count": ready,
            "adtv20_partial_count": partial,
            "adtv20_blocked_count": blocked,
            "adtv20_not_applicable_count": not_applicable,
            "adv20_matched_volume_ready_count": 0,
            "qualified_observation_tickers": sum(
                1 for row in records.values() if row["authority_tier"] == MATCHED_VALUE_OBSERVATION_QUALIFIED
            ),
            "qualified_observation_sessions": len(hose_disc_rows),
            "restricted_scope_tickers": sum(
                1 for row in records.values() if row["authority_tier"] == MATCHED_VALUE_RESTRICTED_SCOPE
            ),
            "non_discriminating_exact_tickers": sum(
                1 for row in records.values() if row["authority_tier"] == MATCHED_VALUE_NON_DISCRIMINATING
            ),
            "qualified_observation_tickers_by_exchange": dict(sorted(exchange_qualified.items())),
        },
        "authority_boundary": {
            "qualified_liquidity_inputs": False,
            "position_sizing_is_safe": False,
            "participation_cap": "NOT_EMBEDDED",
            "raw_as_traded": "NOT_PROMOTED",
            "pit": "BLOCKED",
            "backtesting": "BLOCKED",
            "current_common_shares": "UNCHANGED",
            "valuation_value_eligibility": "UNCHANGED",
            "frozen_sessions_not_regenerated": ["2026-08-21", "2026-08-24"],
            "current_session_liquidity_research": "SEPARATE_LANE",
            "adtv20_is_not_safe_position_size": True,
            "adtv20_is_not_participation_cap": True,
            "adtv20_is_not_market_impact": True,
            "adtv20_is_not_slippage": True,
            "adtv20_is_not_executable_capacity": True,
        },
        "verdict": (
            "HISTORICAL_MATCHED_TRADING_VALUE_AUTHORITY_PASS" if ready else
            "MATCHED_VALUE_AUTHORITY_SCOPE_RESTRICTED"
        ),
    }
    if not artifact["coverage"]["denominator_reconciles"]:
        raise ValueError("OFFICIAL_UNIVERSE_DENOMINATOR_DRIFT")
    artifact["artifact_sha256"] = stable_id({key: value for key, value in artifact.items() if key not in {"artifact_sha256", "artifact_identity"}})
    artifact["artifact_identity"] = f"historical_matched_trading_value_authority:{artifact['artifact_sha256']}"
    return artifact


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: value for key, value in dict(artifact).items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"historical_matched_trading_value_authority:{digest}"}
