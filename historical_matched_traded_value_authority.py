"""Narrow, evidence-bound historical DNSE matched-traded-value qualification.

This contract deliberately qualifies only the observed ``G1`` component of a
complete DNSE ``trades_history`` session when it has an independent retained
FHSC matched-volume and matched-value anchor.  It does not turn the remaining
boards, a grossTradeAmount counter, or an OHLC price-times-volume calculation
into traded value.  It therefore creates no ADV, liquidity, execution, or
position-sizing authority.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping


CONTRACT_VERSION = "historical_matched_traded_value_authority/v1"
PRICE_NATIVE_UNIT = "thousands_of_vnd_per_share_empirically_qualified_for_g1_scope"
G1_QUANTITY_MULTIPLIER = Decimal("10")
PRICE_TO_VND_MULTIPLIER = Decimal("1000")
MATCHED_VALUE_FORMULA = "sum(G1.matchPrice * G1.matchQtty) * 10 * 1000"
QUALIFIED_BOARD = "G1"
KNOWN_BOARDS = ("G1", "G4", "T1", "T3", "T4", "T6")
MINIMUM_ANCHOR_TICKERS = 2
MINIMUM_ANCHOR_SESSIONS = 2


class QualificationError(ValueError):
    """Raised when a proposed qualified observation lacks a required gate."""


def _decimal(value: Any, *, field: str) -> Decimal:
    if isinstance(value, bool):
        raise QualificationError(f"non_numeric:{field}")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise QualificationError(f"non_numeric:{field}") from exc
    if not result.is_finite() or result < 0:
        raise QualificationError(f"invalid_nonnegative_numeric:{field}")
    return result


def _integer_or_decimal(value: Decimal) -> int | str:
    return int(value) if value == value.to_integral_value() else format(value, "f")


def page_chain_status(pages: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Verify an explicit, terminal page chain without assuming session phases."""
    ordered = sorted(pages, key=lambda page: int(page["page_index"]))
    if not ordered:
        return {"status": "INCOMPLETE", "reason": "NO_RETAINED_PAGES"}
    indices = [int(page["page_index"]) for page in ordered]
    if indices[0] != 1:
        return {"status": "INCOMPLETE", "reason": "PAGE_CHAIN_DOES_NOT_START_AT_FIRST_PAGE", "page_indices": indices}
    if indices != list(range(indices[0], indices[0] + len(indices))):
        return {"status": "INCOMPLETE", "reason": "NON_CONTIGUOUS_PAGE_INDICES", "page_indices": indices}
    for previous, current in zip(ordered, ordered[1:]):
        if previous.get("next_page_token") != current.get("page_cursor"):
            return {"status": "INCOMPLETE", "reason": "PAGINATION_CURSOR_CHAIN_BROKEN", "page_indices": indices}
    if ordered[-1].get("next_page_token"):
        return {"status": "INCOMPLETE", "reason": "TERMINAL_PAGE_TOKEN_PRESENT", "page_indices": indices}
    return {"status": "COMPLETE", "page_count": len(ordered), "page_indices": indices}


def summarize_complete_trade_session(
    *, ticker: str, session: str, pages: Iterable[Mapping[str, Any]], raw_payload_hashes: Iterable[str],
) -> dict[str, Any]:
    """Preserve actual board composition and calculate only the G1 candidate.

    ``pages`` is a normalized, retained-page representation: each page has
    ``page_index``, ``page_cursor``, ``next_page_token`` and a ``trades`` list.
    Every field needed by the qualified formula is validated before arithmetic.
    """
    page_list = list(pages)
    chain = page_chain_status(page_list)
    if chain["status"] != "COMPLETE":
        return {
            "ticker": ticker, "session": session, "session_completeness": chain,
            "qualification_status": "INCOMPLETE_SESSION", "matched_value_vnd": None,
        }
    board_quantity: dict[str, Decimal] = defaultdict(Decimal)
    board_native_value: dict[str, Decimal] = defaultdict(Decimal)
    observed_boards: set[str] = set()
    timestamps: list[str] = []
    record_count = 0
    for page in page_list:
        trades = page.get("trades")
        if not isinstance(trades, list):
            raise QualificationError("invalid_trades_array")
        for trade in trades:
            if not isinstance(trade, Mapping):
                raise QualificationError("invalid_trade_record")
            board = trade.get("boardId")
            if not isinstance(board, str) or not board:
                raise QualificationError("missing_board_id")
            price = _decimal(trade.get("matchPrice"), field="matchPrice")
            quantity = _decimal(trade.get("matchQtty"), field="matchQtty")
            timestamp = trade.get("time")
            if not isinstance(timestamp, str) or not timestamp.startswith(session):
                raise QualificationError("timestamp_outside_or_missing_session")
            observed_boards.add(board)
            board_quantity[board] += quantity
            board_native_value[board] += price * quantity
            timestamps.append(timestamp)
            record_count += 1
    if QUALIFIED_BOARD not in observed_boards:
        return {
            "ticker": ticker, "session": session, "session_completeness": chain,
            "qualification_status": "NO_G1_MATCHED_BOARD_OBSERVATION", "matched_value_vnd": None,
            "observed_boards": sorted(observed_boards), "record_count": record_count,
        }
    g1_raw_quantity = board_quantity[QUALIFIED_BOARD]
    matched_value = board_native_value[QUALIFIED_BOARD] * G1_QUANTITY_MULTIPLIER * PRICE_TO_VND_MULTIPLIER
    composition = [
        {
            "board_id": board,
            "raw_quantity": _integer_or_decimal(board_quantity[board]),
            "native_price_times_quantity": _integer_or_decimal(board_native_value[board]),
            "included_in_matched_value": board == QUALIFIED_BOARD,
            "disposition": "QUALIFIED_MATCHED_COMPONENT" if board == QUALIFIED_BOARD else "RETAINED_NOT_QUALIFIED_FOR_MATCHED_VALUE",
        }
        for board in sorted(observed_boards)
    ]
    return {
        "ticker": ticker,
        "session": session,
        "session_completeness": chain,
        "qualification_status": "CANDIDATE_PENDING_FHSC_ANCHOR",
        "record_count": record_count,
        "first_trade_timestamp": min(timestamps),
        "last_trade_timestamp": max(timestamps),
        "observed_boards": sorted(observed_boards),
        "board_composition": composition,
        "g1_raw_quantity": _integer_or_decimal(g1_raw_quantity),
        "g1_share_quantity": _integer_or_decimal(g1_raw_quantity * G1_QUANTITY_MULTIPLIER),
        "matched_value_vnd": _integer_or_decimal(matched_value),
        "raw_payload_hashes": sorted(set(raw_payload_hashes)),
    }


def reconcile_fhsc_anchor(candidate: Mapping[str, Any], anchor: Mapping[str, Any]) -> dict[str, Any]:
    """Require independent exact G1 quantity and matched-value reconciliation."""
    if candidate.get("qualification_status") != "CANDIDATE_PENDING_FHSC_ANCHOR":
        return {"status": "NOT_COMPARABLE", "reason": candidate.get("qualification_status")}
    if not anchor.get("fhsc_identity_retained_exact"):
        return {"status": "NOT_COMPARABLE", "reason": "FHSC_INTERNAL_IDENTITY_NOT_EXACT"}
    expected_volume = _decimal(anchor.get("fhsc_matched_volume"), field="fhsc_matched_volume")
    expected_value = _decimal(anchor.get("fhsc_matched_value"), field="fhsc_matched_value")
    g1_volume = _decimal(candidate.get("g1_share_quantity"), field="g1_share_quantity")
    value = _decimal(candidate.get("matched_value_vnd"), field="matched_value_vnd")
    volume_status = "EXACT" if g1_volume == expected_volume else "CONFLICT"
    value_status = "EXACT" if value == expected_value else "CONFLICT"
    return {
        "status": "EXACT" if volume_status == value_status == "EXACT" else "CONFLICT",
        "g1_to_fhsc_matched_volume": volume_status,
        "g1_to_fhsc_matched_value": value_status,
        "fhsc_matched_volume": _integer_or_decimal(expected_volume),
        "fhsc_matched_value": _integer_or_decimal(expected_value),
    }


def qualify_anchor_rows(rows: Iterable[tuple[Mapping[str, Any], Mapping[str, Any]]]) -> dict[str, Any]:
    """Apply the exact, all-row gate and never average conflicting observations."""
    reconciliations: list[dict[str, Any]] = []
    for candidate, anchor in sorted(rows, key=lambda pair: (str(pair[0].get("ticker")), str(pair[0].get("session")))):
        reconciliation = reconcile_fhsc_anchor(candidate, anchor)
        row = dict(candidate)
        row["fhsc_reconciliation"] = reconciliation
        row["qualification_status"] = "EXACT_PENDING_COHORT_BREADTH" if reconciliation["status"] == "EXACT" else "CONFLICTING"
        reconciliations.append(row)
    counts = Counter(row["fhsc_reconciliation"]["status"] for row in reconciliations)
    exact = [row for row in reconciliations if row["fhsc_reconciliation"]["status"] == "EXACT"]
    breadth_ok = (
        len({row["ticker"] for row in exact}) >= MINIMUM_ANCHOR_TICKERS
        and len({row["session"] for row in exact}) >= MINIMUM_ANCHOR_SESSIONS
    )
    formula_status = "QUALIFIED_EMPIRICAL_SCOPE" if exact and not counts.get("CONFLICT") and breadth_ok else "NOT_QUALIFIED"
    for row in exact:
        row["qualification_status"] = "MATCHED_VALUE_QUALIFIED" if formula_status == "QUALIFIED_EMPIRICAL_SCOPE" else "EXACT_BUT_INSUFFICIENT_ANCHOR_BREADTH"
    qualified = [row for row in reconciliations if row["qualification_status"] == "MATCHED_VALUE_QUALIFIED"]
    return {
        "rows": reconciliations,
        "qualified_rows": qualified,
        "reconciliation_counts": dict(sorted(counts.items())),
        "formula_status": formula_status,
        "formula": MATCHED_VALUE_FORMULA,
        "price_native_unit": PRICE_NATIVE_UNIT,
        "quantity_contract": "G1_raw_quantity_times_10_equals_FHSC_matched_volume_exactly",
        "authority_boundary": "MATCHED_VALUE_OBSERVATION_ONLY__NO_ADV20_LIQUIDITY_SIZING_EXECUTION_OR_PIT_AUTHORITY",
    }


def adv20_status(rows: Iterable[Mapping[str, Any]], *, expected_sessions: int = 20) -> dict[str, Any]:
    """Report calendar-denominator insufficiency without calculating an average."""
    by_ticker: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("qualification_status") == "MATCHED_VALUE_QUALIFIED":
            by_ticker[str(row["ticker"])].append(row)
    return {
        ticker: {
            "status": "ADV20_INSUFFICIENT_HISTORY",
            "qualified_complete_sessions": len(values),
            "expected_complete_sessions": expected_sessions,
            "adv20_vnd": None,
            "reason": "NO_AVERAGE_EMITTED_UNTIL_20_EXPECTED_COMPLETE_SESSIONS",
        }
        for ticker, values in sorted(by_ticker.items())
    }
