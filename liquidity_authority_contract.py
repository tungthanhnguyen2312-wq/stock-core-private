"""Provider-neutral, use-specific liquidity authority contract (AUTHORITY_CLOSURE_LIQUIDITY_FOUNDATION_V1).

WHY THIS EXISTS
    Until 2026-09-28 every historical matched-value claim needed an FHSC secondary anchor, and
    DNSE's per-board counters were usable only as raw provider counters with unknown units
    (``dnse_trades_liquidity_basis``: ``semantic_unit_interpretation = UNKNOWN``). Both exchanges
    publish a dated, per-symbol daily trading history with an explicit matched / put-through /
    odd-lot split (``official_exchange_trading_statistics``). That removes the need for a
    secondary commercial anchor for the tickers whose official series is retained. It also
    gives an independent, first-party test of the DNSE board unit hypothesis.

WHAT THIS MODULE DECIDES
    * The DNSE board-unit contract per (exchange, board). This is a hypothesis
      (``DNSE_BOARD_UNIT_HYPOTHESIS``) that is QUALIFIED only by exact official reconciliation.
      Each board is judged separately; HNX evidence is never used for HOSE, or the reverse.
    * Exact current-session reconciliation of DNSE board counters against the official row.
    * Official trailing ADV/ADTV windows over the governed session calendar. The windows use no
      calendar-day imputation and no zero-fill; a missing row is missing.
    * The seven-dimension liquidity fitness, reusing the vocabulary and the fail-closed guard of
      ``dnse_trades_liquidity_basis``. EXECUTION_CAPACITY, POSITION_SIZING and PIT_BACKTEST can
      never open here.

WHAT IT NEVER DOES
    Emit a position size, participation cap, market-impact estimate or execution instruction.
    Promote PIT or RAW_AS_TRADED. Relabel one exchange's "matched" definition as the other's.
    Turn a correlation into a unit: a board's unit is qualified only by exact, integer,
    same-session equality with an official exchange figure.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

import dnse_trades_liquidity_basis as dimension_basis
import official_exchange_trading_statistics as official
from governed_trading_session_calendar import (
    CALENDAR_SOURCE_KIND,
    CONTRACT_VERSION as CALENDAR_CONTRACT_VERSION,
    GovernedTradingSessionCalendar,
)
from market_wide_historical_matched_liquidity import (
    COVERAGE_RESTRICTED_WINDOW,
    EXACT_WINDOW,
    INSUFFICIENT_WINDOW,
)

CONTRACT_VERSION = "liquidity_authority_contract/v1"
MILESTONE = "AUTHORITY_CLOSURE_LIQUIDITY_FOUNDATION_V1"

# Reused, not re-invented: the seven dimensions and their states.
CURRENT_SESSION_LIQUIDITY_RESEARCH = dimension_basis.CURRENT_SESSION_LIQUIDITY_RESEARCH
HISTORICAL_LIQUIDITY_RESEARCH = dimension_basis.HISTORICAL_LIQUIDITY_RESEARCH
ADV_VOLUME_RESEARCH = dimension_basis.ADV_VOLUME_RESEARCH
ADTV_RESEARCH = dimension_basis.ADTV_RESEARCH
EXECUTION_CAPACITY = dimension_basis.EXECUTION_CAPACITY
POSITION_SIZING = dimension_basis.POSITION_SIZING
PIT_BACKTEST = dimension_basis.PIT_BACKTEST
LIQUIDITY_DIMENSIONS = dimension_basis.LIQUIDITY_DIMENSIONS
ELIGIBLE, PARTIAL, BLOCKED, UNKNOWN, NOT_APPLICABLE = (
    dimension_basis.ELIGIBLE, dimension_basis.PARTIAL, dimension_basis.BLOCKED,
    dimension_basis.UNKNOWN, dimension_basis.NOT_APPLICABLE,
)

# Component vocabulary: the four documented board categories plus the three aggregates the
# exchanges publish (shared with official_exchange_trading_statistics).
MATCHED_ROUND_LOT = official.MATCHED_ROUND_LOT
MATCHED_ODD_LOT = official.MATCHED_ODD_LOT
PUT_THROUGH_ROUND_LOT = official.PUT_THROUGH_ROUND_LOT
PUT_THROUGH_ODD_LOT = official.PUT_THROUGH_ODD_LOT
MATCHED_ALL = official.MATCHED_ALL
PUT_THROUGH_ALL = official.PUT_THROUGH_ALL
TOTAL = official.TOTAL
BASE_COMPONENTS = (MATCHED_ROUND_LOT, MATCHED_ODD_LOT, PUT_THROUGH_ROUND_LOT, PUT_THROUGH_ODD_LOT)
AGGREGATES = {
    MATCHED_ALL: (MATCHED_ROUND_LOT, MATCHED_ODD_LOT),
    PUT_THROUGH_ALL: (PUT_THROUGH_ROUND_LOT, PUT_THROUGH_ODD_LOT),
    TOTAL: BASE_COMPONENTS,
}

#: Which components each exchange's official route publishes separately (used for board
#: reconciliation, so a board is never attributed twice through a derived aggregate).
OFFICIAL_COMPONENTS = {
    official.HOSE: (MATCHED_ROUND_LOT, MATCHED_ODD_LOT, PUT_THROUGH_ROUND_LOT, PUT_THROUGH_ODD_LOT, TOTAL),
    official.HNX: (MATCHED_ALL, PUT_THROUGH_ALL, TOTAL),
    official.UPCOM: (MATCHED_ALL, PUT_THROUGH_ALL, TOTAL),
}
#: Components a trailing window may average: published ones plus HOSE's exact derived sums.
TRAILING_COMPONENTS = {
    official.HOSE: OFFICIAL_COMPONENTS[official.HOSE] + tuple(sorted(official.HOSE_DERIVED_AGGREGATES)),
    official.HNX: OFFICIAL_COMPONENTS[official.HNX],
    official.UPCOM: OFFICIAL_COMPONENTS[official.UPCOM],
}

#: The DNSE trades_latest board encoding under test. ``quantity_unit_shares`` is the number of
#: shares one raw quantity unit represents; ``grossTradeAmount`` is hypothesised to be billion
#: VND for every board. This table is a HYPOTHESIS; ``qualify_board_units`` decides, per
#: exchange, which rows the official evidence actually supports.
DNSE_BOARD_UNIT_HYPOTHESIS: dict[str, dict[str, Any]] = {
    "G1": {"component": MATCHED_ROUND_LOT, "quantity_unit_shares": 10, "phase": "REGULAR_ORDER_MATCHING"},
    "G3": {"component": MATCHED_ROUND_LOT, "quantity_unit_shares": 10, "phase": "POST_CLOSE_ORDER_MATCHING"},
    "G4": {"component": MATCHED_ODD_LOT, "quantity_unit_shares": 1, "phase": "ODD_LOT_ORDER_MATCHING"},
    "T1": {"component": PUT_THROUGH_ROUND_LOT, "quantity_unit_shares": 10, "phase": "PUT_THROUGH"},
    "T3": {"component": PUT_THROUGH_ROUND_LOT, "quantity_unit_shares": 10, "phase": "PUT_THROUGH"},
    "T4": {"component": PUT_THROUGH_ODD_LOT, "quantity_unit_shares": 1, "phase": "PUT_THROUGH"},
    # T6 carries a x10-scaled fractional raw quantity (CTD 2026-09-28: matchQtty 4.1 = 41 shares).
    "T6": {"component": PUT_THROUGH_ODD_LOT, "quantity_unit_shares": 10, "phase": "PUT_THROUGH"},
}
GROSS_TRADE_AMOUNT_VND_PER_UNIT = Decimal(10) ** 9

# Board-unit qualification states (judged separately for volume and value) and thresholds.
UNIT_QUALIFIED = "QUALIFIED_BY_EXACT_OFFICIAL_RECONCILIATION"
UNIT_TRUNCATED = "SCALE_CONFIRMED_CUMULATIVE_QUANTITY_TRUNCATED_LOWER_BOUND_ONLY"
UNIT_INSUFFICIENT = "OBSERVED_EXACT_BELOW_THRESHOLD"
UNIT_UNOBSERVED = "NOT_OBSERVED_ACTIVE_IN_EVIDENCE"
UNIT_CONFLICTED = "CONFLICT_OBSERVED"
MIN_EXACT_TICKERS_FOR_UNIT_QUALIFIED = 3
MIN_EXACT_TICKERS_FOR_UNIT_QUALIFICATION = MIN_EXACT_TICKERS_FOR_UNIT_QUALIFIED
MATCHED_BOARDS = ("G1", "G3", "G4")
PUT_THROUGH_BOARDS = ("T1", "T3", "T4", "T6")

# Reconciliation verdicts.
EXACT = "EXACT"
CONFLICT = "CONFLICT"
#: Value exact; official volume exceeds DNSE by less than one raw ×10 unit per non-zero board.
#: DNSE carries fractional raw quantities on put-through boards (e.g. matchQtty 4.1) while the
#: cumulative ``totalVolumeTraded`` is an integer, so the counter floors them.
VOLUME_TRUNCATED_VALUE_EXACT = "VOLUME_TRUNCATED_VALUE_EXACT"
LOWER_BOUND_CONSISTENT = "LOWER_BOUND_CONSISTENT"
OFFICIAL_ROW_ABSENT = "OFFICIAL_ROW_ABSENT"

# Measurement basis labels for a current-session record.
BASIS_OFFICIAL_RECONCILED = "OFFICIAL_EXCHANGE_RECONCILED_ABSOLUTE_UNITS"
BASIS_UNIT_CONTRACT_APPLIED = "DNSE_UNIT_CONTRACT_APPLIED_NOT_INDIVIDUALLY_RECONCILED"
BASIS_RAW_COUNTERS_ONLY = "PROVIDER_RAW_COUNTERS_ONLY_UNITS_UNQUALIFIED"

KNOWLEDGE_TIME_BASIS = "RETROSPECTIVE_RETRIEVAL_OF_OFFICIAL_POST_SESSION_PUBLICATION"

#: Trailing features. Each is bound to one component identity; MATCHED_ALL is the only
#: order-matching identity both exchanges publish, so it is the cross-exchange comparable one.
TRAILING_FEATURES = (
    ("ADTV20_MATCHED_ALL_VND", MATCHED_ALL, "value", 20),
    ("ADV20_MATCHED_ALL_SHARES", MATCHED_ALL, "volume", 20),
    ("ADTV20_MATCHED_ROUND_LOT_VND", MATCHED_ROUND_LOT, "value", 20),
    ("ADTV20_TOTAL_VND", TOTAL, "value", 20),
    ("ADTV60_MATCHED_ALL_VND", MATCHED_ALL, "value", 60),
    ("ADV60_MATCHED_ALL_SHARES", MATCHED_ALL, "volume", 60),
)
NOT_PUBLISHED_BY_SOURCE = "NOT_PUBLISHED_SEPARATELY_BY_OFFICIAL_SOURCE"
NOT_ACQUIRED_DEPTH = "OFFICIAL_SERIES_DEPTH_NOT_ACQUIRED"
MISSING_OFFICIAL_ROW = "GOVERNED_SESSION_ROW_ABSENT_FROM_OFFICIAL_SERIES"


class LiquidityAuthorityContractError(ValueError):
    """Malformed contract input; never silently coerced."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def content_identity(value: Mapping[str, Any], *, kind: str = "liquidity_authority_closure") -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{kind}:{digest}"}


def _dec(value: Any, *, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise LiquidityAuthorityContractError(f"NUMERIC_FIELD_INVALID:{field}")
    number = Decimal(str(value))
    if not number.is_finite() or number < 0:
        raise LiquidityAuthorityContractError(f"NUMERIC_FIELD_INVALID:{field}")
    return number


def _as_int(value: Decimal) -> int | str:
    return int(value) if value == value.to_integral_value() else format(value, "f")


# ---------------------------------------------------------------------------------
# DNSE trades_latest -> per-board session contributions
# ---------------------------------------------------------------------------------

def dnse_board_contributions(trades_body: Mapping[str, Any], *, symbol: str) -> dict[str, Any]:
    """Resolve each board's latest cumulative tick from one retained trades_latest body.

    ``trades_latest`` returns, per board ever traded, that board's most recent tick carrying
    board-scoped cumulative session counters. A board's latest tick therefore closes the
    session it is dated on (it is the final tick that board ever printed). Floats must have
    been loaded with ``parse_float=Decimal`` for exact VND arithmetic.
    """
    trades = trades_body.get("trades") if isinstance(trades_body, Mapping) else None
    if not isinstance(trades, list):
        return {"state": "TRADES_ARRAY_ABSENT", "boards": {}, "market_id": None}
    # trades_latest keys its latest tick by (market, board): an instrument that changed exchange
    # still carries its old market's boards. The current market is the market of the latest
    # tick; boards of any other market are prior-listing evidence and never enter measures.
    by_market: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    unknown: list[str] = []
    latest: dict[str, str] = {}
    for raw in trades:
        if not isinstance(raw, Mapping):
            continue
        if str(raw.get("symbol") or "").upper() != symbol.upper():
            raise LiquidityAuthorityContractError(f"DNSE_SYMBOL_MISMATCH:{symbol}:{raw.get('symbol')}")
        board = str(raw.get("boardId") or "")
        market = str(raw.get("marketId") or "")
        time_text = str(raw.get("time") or "")
        latest[market] = max(latest.get(market, ""), time_text)
        if board not in DNSE_BOARD_UNIT_HYPOTHESIS:
            unknown.append(board)
            continue
        session = time_text.split(" ", 1)[0] if " " in time_text else None
        quantity = _dec(raw.get("totalVolumeTraded"), field=f"{board}.totalVolumeTraded")
        gross = _dec(raw.get("grossTradeAmount"), field=f"{board}.grossTradeAmount")
        current = by_market[market].get(board)
        if current is None or (session or "", quantity) > (current["session"] or "", current["quantity_raw"]):
            by_market[market][board] = {"board": board, "session": session, "raw_time": time_text,
                                        "quantity_raw": quantity, "gross_trade_amount_raw": gross, "market_id": market}
    if not latest:
        return {"state": "NO_TICKS", "boards": {}, "unknown_boards": [], "market_id": None, "exchange": None, "prior_market_boards": {}}
    newest = max(latest.values())
    current_markets = sorted(market for market, stamp in latest.items() if stamp == newest)
    if len(current_markets) != 1:
        raise LiquidityAuthorityContractError(f"DNSE_CURRENT_MARKET_AMBIGUOUS:{symbol}:{current_markets}")
    market_id = current_markets[0]
    prior = {market: sorted(boards) for market, boards in by_market.items() if market != market_id}
    return {"state": "RESOLVED", "boards": dict(by_market.get(market_id, {})), "unknown_boards": sorted(set(unknown)),
            "market_id": market_id, "exchange": official.exchange_for_dnse_market_id(market_id), "prior_market_boards": prior}


def board_measure(contribution: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the unit HYPOTHESIS to one board contribution (shares, VND)."""
    spec = DNSE_BOARD_UNIT_HYPOTHESIS[contribution["board"]]
    shares = contribution["quantity_raw"] * spec["quantity_unit_shares"]
    value = contribution["gross_trade_amount_raw"] * GROSS_TRADE_AMOUNT_VND_PER_UNIT
    return {"board": contribution["board"], "component": spec["component"], "session": contribution["session"],
            "volume_shares": shares, "value_vnd": value}


def _component_sums(measures: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Decimal]]:
    sums = {name: {"volume_shares": Decimal(0), "value_vnd": Decimal(0)} for name in BASE_COMPONENTS}
    for item in measures:
        sums[item["component"]]["volume_shares"] += item["volume_shares"]
        sums[item["component"]]["value_vnd"] += item["value_vnd"]
    for aggregate, parts in AGGREGATES.items():
        sums[aggregate] = {"volume_shares": sum((sums[p]["volume_shares"] for p in parts), Decimal(0)),
                           "value_vnd": sum((sums[p]["value_vnd"] for p in parts), Decimal(0))}
    return sums


def dnse_session_measures(resolved: Mapping[str, Any], *, session: str) -> dict[str, Any]:
    """Component totals for one session from boards whose latest tick is dated that session.

    A board whose latest tick is dated earlier did not trade on ``session`` (its final tick
    would otherwise be later); it contributes an explicit zero and is listed as not active.
    """
    boards = resolved.get("boards") or {}
    active = [board_measure(item) for item in boards.values() if item.get("session") == session]
    later = sorted(item["board"] for item in boards.values() if (item.get("session") or "") > session)
    if later:
        raise LiquidityAuthorityContractError(f"DNSE_BOARD_DATED_AFTER_TARGET_SESSION:{later}")
    sums = _component_sums(active)
    return {"session": session, "active_boards": sorted(item["board"] for item in active),
            "inactive_boards": sorted(b for b, item in boards.items() if item.get("session") != session),
            "unknown_boards": list(resolved.get("unknown_boards") or []),
            "components": {name: {"volume_shares": _as_int(v["volume_shares"]), "value_vnd": _as_int(v["value_vnd"])} for name, v in sums.items()},
            "_decimal_components": sums, "_active_measures": active}


# ---------------------------------------------------------------------------------
# Reconciliation against an official row
# ---------------------------------------------------------------------------------

def _signed(value: Decimal) -> int | str:
    return _as_int(value) if value >= 0 else "-" + str(_as_int(-value))


def _verdict(volume_delta: Decimal, value_delta: Decimal, *, nonzero_boards: int) -> str:
    if volume_delta == 0 and value_delta == 0:
        return EXACT
    if value_delta == 0 and 0 < volume_delta < 10 * max(nonzero_boards, 1):
        return VOLUME_TRUNCATED_VALUE_EXACT
    return CONFLICT


def _compare(dnse: Mapping[str, Decimal], official_component: Mapping[str, int], *, nonzero_boards: int) -> dict[str, Any]:
    volume_delta = Decimal(official_component["volume_shares"]) - dnse["volume_shares"]
    value_delta = Decimal(official_component["value_vnd"]) - dnse["value_vnd"]
    return {"verdict": _verdict(volume_delta, value_delta, nonzero_boards=nonzero_boards), "official": dict(official_component),
            "dnse": {"volume_shares": _as_int(dnse["volume_shares"]), "value_vnd": _as_int(dnse["value_vnd"])},
            "volume_delta_shares": _signed(volume_delta), "value_delta_vnd": _signed(value_delta)}


def _boards_in(component: str) -> set[str]:
    parts = AGGREGATES.get(component, (component,))
    return {board for board, spec in DNSE_BOARD_UNIT_HYPOTHESIS.items() if spec["component"] in parts}


def _overall(verdicts: Iterable[str]) -> str:
    verdicts = list(verdicts)
    if all(v == EXACT for v in verdicts):
        return EXACT
    if all(v in (EXACT, VOLUME_TRUNCATED_VALUE_EXACT) for v in verdicts):
        return VOLUME_TRUNCATED_VALUE_EXACT
    return CONFLICT


def reconcile_session(dnse_measures: Mapping[str, Any], official_row: Mapping[str, Any] | None, *, exchange: str) -> dict[str, Any]:
    """Compare DNSE session component totals with the official row, component by component.

    ``matched_verdict`` covers the order-matching components only (HOSE MATCHED_ROUND_LOT and
    MATCHED_ODD_LOT; HNX/UPCoM MATCHED_ALL); ``put_through_verdict`` the put-through ones.
    TOTAL is derived from the others and is reported but never attributed to a board.
    """
    session = dnse_measures["session"]
    if official_row is None:
        return {"session": session, "exchange": exchange, "verdict": OFFICIAL_ROW_ABSENT, "components": {}}
    if official_row.get("session") != session:
        raise LiquidityAuthorityContractError("OFFICIAL_ROW_SESSION_MISMATCH")
    if official_row.get("row_integrity") != "COMPONENTS_SUM_TO_TOTAL":
        return {"session": session, "exchange": exchange, "verdict": "OFFICIAL_ROW_INTEGRITY_FAILED", "components": {}}
    sums = dnse_measures["_decimal_components"]
    active = {item["board"]: item for item in dnse_measures["_active_measures"]}
    components = {}
    for name in OFFICIAL_COMPONENTS[exchange]:
        nonzero = sorted(b for b in _boards_in(name) if b in active and (active[b]["volume_shares"] or active[b]["value_vnd"]))
        cell = _compare(sums[name], official_row["components"][name], nonzero_boards=len(nonzero))
        cell["nonzero_dnse_boards"] = nonzero
        components[name] = cell
    matched = [c for n, c in components.items() if n in (MATCHED_ROUND_LOT, MATCHED_ODD_LOT, MATCHED_ALL)]
    put_through = [c for n, c in components.items() if n in (PUT_THROUGH_ROUND_LOT, PUT_THROUGH_ODD_LOT, PUT_THROUGH_ALL)]
    return {"session": session, "exchange": exchange, "verdict": _overall(c["verdict"] for c in components.values()),
            "matched_verdict": _overall(c["verdict"] for c in matched),
            "put_through_verdict": _overall(c["verdict"] for c in put_through), "components": components}


def stale_board_points(resolved: Mapping[str, Any], official_rows: Mapping[str, Mapping[str, Any]], *, exchange: str, target_session: str) -> list[dict[str, Any]]:
    """Historical point checks from boards whose final tick predates the target session.

    Only the board's own final session is knowable; other boards' activity on that date is not.
    Equality with the official component is EXACT (or VOLUME_TRUNCATED_VALUE_EXACT) evidence; the
    official figure exceeding the board is merely LOWER_BOUND_CONSISTENT; the board exceeding
    the official figure is CONFLICT.
    """
    points = []
    for board, item in sorted((resolved.get("boards") or {}).items()):
        session = item.get("session")
        if not session or session >= target_session:
            continue
        measure = board_measure(item)
        if not (measure["volume_shares"] or measure["value_vnd"]):
            continue
        component = measure["component"]
        if exchange != official.HOSE:
            component = MATCHED_ALL if component in AGGREGATES[MATCHED_ALL] else PUT_THROUGH_ALL
        row = official_rows.get(session)
        if row is None or row.get("row_integrity") != "COMPONENTS_SUM_TO_TOTAL":
            points.append({"board": board, "session": session, "component": component, "verdict": OFFICIAL_ROW_ABSENT})
            continue
        published = row["components"][component]
        volume_delta = Decimal(published["volume_shares"]) - measure["volume_shares"]
        value_delta = Decimal(published["value_vnd"]) - measure["value_vnd"]
        verdict = _verdict(volume_delta, value_delta, nonzero_boards=1)
        if verdict == CONFLICT and volume_delta >= 0 and value_delta >= 0:
            verdict = LOWER_BOUND_CONSISTENT
        points.append({"board": board, "session": session, "component": component, "verdict": verdict,
                       "official": dict(published),
                       "dnse": {"volume_shares": _as_int(measure["volume_shares"]), "value_vnd": _as_int(measure["value_vnd"])}})
    return points


def _metric_state(exact_tickers: set[str], truncated: int, conflicts: int) -> str:
    if conflicts:
        return UNIT_CONFLICTED
    if truncated:
        return UNIT_TRUNCATED
    if len(exact_tickers) >= MIN_EXACT_TICKERS_FOR_UNIT_QUALIFIED:
        return UNIT_QUALIFIED
    return UNIT_INSUFFICIENT if exact_tickers else UNIT_UNOBSERVED


def qualify_board_units(evidence: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    """Per (exchange, board) unit qualification, judged separately for volume and value.

    ``evidence`` items: ``{"ticker", "exchange", "kind": "CURRENT_SESSION"|"STALE_BOARD_POINT",
    "reconciliation"|"point"}``. Within a published component (never the derived TOTAL) every
    non-zero board shares that component's outcome for each metric: an exact value is value
    evidence; an exact volume is volume evidence; a volume short by less than one raw unit per
    board with an exact value is truncation evidence; anything else is a conflict. A metric is
    QUALIFIED with exact evidence on at least ``MIN_EXACT_TICKERS_FOR_UNIT_QUALIFIED`` distinct
    tickers of that exchange, and no truncation or conflict.
    """
    exact = {metric: defaultdict(set) for metric in ("volume", "value")}
    truncated: Counter[tuple[str, str]] = Counter()
    conflicts: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)

    def record(exchange: str, ticker: str, session: str, component: str, boards: Iterable[str], verdict: str) -> None:
        for board in boards:
            key = (exchange, board)
            if verdict == EXACT:
                exact["volume"][key].add(ticker)
                exact["value"][key].add(ticker)
            elif verdict == VOLUME_TRUNCATED_VALUE_EXACT:
                exact["value"][key].add(ticker)
                truncated[key] += 1
            elif verdict == CONFLICT:
                conflicts[key].append({"ticker": ticker, "session": session, "component": component})

    for item in evidence:
        exchange, ticker = item["exchange"], item["ticker"]
        if item["kind"] == "CURRENT_SESSION":
            recon = item["reconciliation"]
            for name, cell in (recon.get("components") or {}).items():
                if name != TOTAL:
                    record(exchange, ticker, recon["session"], name, cell.get("nonzero_dnse_boards") or [], cell["verdict"])
        else:
            point = item["point"]
            if point["verdict"] in (EXACT, VOLUME_TRUNCATED_VALUE_EXACT, CONFLICT):
                record(exchange, ticker, point["session"], point["component"], [point["board"]], point["verdict"])
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for exchange in official.EXCHANGES:
        per_board = {}
        for board, spec in DNSE_BOARD_UNIT_HYPOTHESIS.items():
            key = (exchange, board)
            volume_state = _metric_state(exact["volume"][key], truncated[key], len(conflicts[key]))
            value_state = _metric_state(exact["value"][key], 0, len(conflicts[key]))
            state = UNIT_QUALIFIED if volume_state == value_state == UNIT_QUALIFIED else (
                volume_state if volume_state != UNIT_QUALIFIED else value_state)
            per_board[board] = {"state": state, "volume_state": volume_state, "value_state": value_state,
                                "component": spec["component"], "phase": spec["phase"],
                                "quantity_unit_shares": spec["quantity_unit_shares"], "gross_trade_amount_unit": "BILLION_VND",
                                "exact_volume_tickers": sorted(exact["volume"][key]), "exact_value_tickers": sorted(exact["value"][key]),
                                "volume_truncation_observations": truncated[key],
                                "conflicts": conflicts[key][:20], "conflict_count": len(conflicts[key]),
                                "scope": {"exchange": exchange, "generalized_to_other_exchanges": False}}
        result[exchange] = per_board
    return result


def adjudicate_prior_matched_cell(*, exchange: str, official_components: Mapping[str, Mapping[str, int]],
                                  dnse_g1: tuple[int, int], fhsc_matched: tuple[int, int]) -> dict[str, Any]:
    """Adjudicate a retained DNSE-G1 vs FHSC matched cell against the official row.

    Pairs are ``(volume_shares, value_vnd)``. HOSE publishes round-lot order matching alone, which
    is exactly comparable to a G1-only figure. HNX/UPCoM publish only order matching including
    odd lot (and post-close); there a G1-only figure is an ordered lower bound, not comparable.
    """
    if exchange == official.HOSE:
        published = official_components[MATCHED_ROUND_LOT]
        pair = (published["volume_shares"], published["value_vnd"])
        verdict = ("OFFICIAL_EQUALS_BOTH" if dnse_g1 == pair == fhsc_matched else
                   "OFFICIAL_EQUALS_DNSE_G1_ONLY" if dnse_g1 == pair else
                   "OFFICIAL_EQUALS_FHSC_ONLY_DNSE_G1_UNDERCOUNT" if fhsc_matched == pair and dnse_g1[0] < pair[0] else
                   "OFFICIAL_EQUALS_FHSC_ONLY" if fhsc_matched == pair else "OFFICIAL_EQUALS_NEITHER")
        return {"verdict": verdict, "comparability": "EXACT_COMPARABLE_ROUND_LOT_ORDER_MATCHING", "official_component": MATCHED_ROUND_LOT,
                "official": {"volume_shares": pair[0], "value_vnd": pair[1]}}
    published = official_components[MATCHED_ALL]
    pair = (published["volume_shares"], published["value_vnd"])
    ordered = all(dnse_g1[i] <= fhsc_matched[i] <= pair[i] for i in (0, 1)) or all(fhsc_matched[i] <= dnse_g1[i] <= pair[i] for i in (0, 1))
    verdict = ("OFFICIAL_MATCHED_ALL_EQUALS_BOTH" if dnse_g1 == pair == fhsc_matched else
               "FHSC_EQUALS_OFFICIAL_MATCHED_ALL" if fhsc_matched == pair else
               "DNSE_G1_EQUALS_OFFICIAL_MATCHED_ALL" if dnse_g1 == pair else
               "ORDERING_CONSISTENT_NOT_DIRECTLY_COMPARABLE" if ordered else "ORDERING_VIOLATION")
    return {"verdict": verdict, "comparability": "LOWER_BOUND_ONLY_OFFICIAL_INCLUDES_ODD_LOT_AND_POST_CLOSE", "official_component": MATCHED_ALL,
            "official": {"volume_shares": pair[0], "value_vnd": pair[1]},
            "dnse_g1_vs_fhsc": "EQUAL" if dnse_g1 == fhsc_matched else ("DNSE_BELOW_FHSC" if dnse_g1[0] < fhsc_matched[0] else "DNSE_ABOVE_FHSC")}


def matched_measurement_basis(active_boards: Iterable[str], exchange_units: Mapping[str, Mapping[str, Any]],
                              reconciliation: Mapping[str, Any] | None = None) -> str:
    """Basis of the order-matching components for one ticker-session.

    An exact official reconciliation of the matched components beats everything; otherwise
    every active matched board (G1/G3/G4) must be QUALIFIED for this exchange on both metrics.
    With no matched board active the matched components are published zeros of qualified boards.
    """
    if reconciliation is not None and reconciliation.get("matched_verdict") == EXACT:
        return BASIS_OFFICIAL_RECONCILED
    matched = [board for board in active_boards if board in MATCHED_BOARDS]
    if all(exchange_units[board]["state"] == UNIT_QUALIFIED for board in matched):
        return BASIS_UNIT_CONTRACT_APPLIED
    return BASIS_RAW_COUNTERS_ONLY


def put_through_precision(active_boards: Iterable[str], exchange_units: Mapping[str, Mapping[str, Any]],
                          reconciliation: Mapping[str, Any] | None = None) -> str:
    """Precision label for the put-through components (never used by ADV/ADTV MATCHED_ALL)."""
    boards = [board for board in active_boards if board in PUT_THROUGH_BOARDS]
    if not boards:
        return "NO_PUT_THROUGH_ACTIVE"
    verdict = (reconciliation or {}).get("put_through_verdict")
    if verdict == EXACT:
        return "OFFICIAL_RECONCILED_EXACT"
    if verdict == VOLUME_TRUNCATED_VALUE_EXACT:
        return "OFFICIAL_RECONCILED_VALUE_EXACT_VOLUME_TRUNCATED"
    if all(exchange_units[board]["value_state"] == UNIT_QUALIFIED for board in boards):
        exact_volume = all(exchange_units[board]["volume_state"] == UNIT_QUALIFIED for board in boards)
        return "VALUE_QUALIFIED_VOLUME_EXACT" if exact_volume else "VALUE_QUALIFIED_VOLUME_LOWER_BOUND_OR_UNQUALIFIED"
    return "UNQUALIFIED"


# ---------------------------------------------------------------------------------
# Governed session calendar extension from two official exchange publishers
# ---------------------------------------------------------------------------------

def extend_governed_calendar(
    base: GovernedTradingSessionCalendar,
    *,
    hose_sessions: Iterable[str],
    hnx_sessions: Iterable[str],
    evidence_identity: str,
) -> dict[str, Any]:
    """Extend the governed calendar beyond its last session using official evidence.

    A date enters the extension only when BOTH exchanges published a per-session report for it
    (HOSE tradingresult rows and HNX/UPCoM "Thông tin tổng hợp" rows). On the overlap with the
    base calendar the official session set must equal the base set exactly, or the extension
    fails closed. Sessions never come from DNSE partitions or weekday arithmetic.
    """
    hose, hnx = set(hose_sessions), set(hnx_sessions)
    both = hose & hnx
    if not both:
        return {"state": "NO_OFFICIAL_SESSIONS", "calendar": None}
    first_common = max(min(hose), min(hnx))
    base_last = base.sessions[-1]
    base_overlap = {s for s in base.sessions if first_common <= s <= base_last}
    official_overlap = {s for s in both if first_common <= s <= base_last}
    only_one_publisher = sorted(s for s in (hose ^ hnx) if s >= first_common)
    if base_overlap != official_overlap:
        return {"state": "OFFICIAL_CALENDAR_DISAGREES_WITH_GOVERNED_BASE", "calendar": None,
                "base_only": sorted(base_overlap - official_overlap), "official_only": sorted(official_overlap - base_overlap)}
    extension = sorted(s for s in both if s > base_last)
    source = {
        "kind": CALENDAR_SOURCE_KIND,
        "scope": f"Vietnam listed-equity sessions {base.sessions[0]} through {extension[-1] if extension else base_last}",
        "governance": ("Base governed ledger plus an extension in which each session was published as a per-session "
                       "trading report by BOTH HOSE and HNX official public routes; the official set equals the base "
                       "ledger exactly on their overlap. Not derived from DNSE partitions or weekday arithmetic."),
        "base_calendar_identity": base.identity,
        "extension_evidence_identity": evidence_identity,
        "overlap_checked": {"from": first_common, "to": base_last, "sessions": len(base_overlap)},
        "data_availability_is_not_calendar_validity": True,
    }
    calendar = GovernedTradingSessionCalendar.from_mapping({
        "contract_version": CALENDAR_CONTRACT_VERSION, "source": source,
        "sessions": sorted(set(base.sessions) | set(extension)),
    })
    return {"state": "EXTENDED", "calendar": calendar, "extension_sessions": extension,
            "overlap_sessions_checked": len(base_overlap), "single_publisher_dates": only_one_publisher}


# ---------------------------------------------------------------------------------
# Official trailing windows
# ---------------------------------------------------------------------------------

def official_trailing_feature(
    *,
    ticker: str,
    exchange: str,
    feature_id: str,
    component: str,
    metric: str,
    size: int,
    target_session: str,
    calendar: GovernedTradingSessionCalendar,
    rows_by_session: Mapping[str, Mapping[str, Any]],
    series_exhausted: bool,
    oldest_retained_session: str | None,
) -> dict[str, Any]:
    """Exact trailing mean of one official component over the governed window.

    EXACT_WINDOW only when every governed window session has an official row whose components
    close to the published total. A zero row is a published zero; an absent row is never zero.
    """
    unit = "VND" if metric == "value" else "shares"
    base = {"feature_id": feature_id, "ticker": ticker, "exchange": exchange, "component": component,
            "metric": metric, "unit": unit, "expected_sessions": size, "target_session": target_session,
            "method": "official_exchange_published_component_trailing_mean/v1", "calendar_day_imputation": False,
            "zero_fill": False, "knowledge_time_basis": KNOWLEDGE_TIME_BASIS, "value": None}
    if component not in TRAILING_COMPONENTS[exchange]:
        return {**base, "status": NOT_APPLICABLE, "blockers": [NOT_PUBLISHED_BY_SOURCE]}
    window = calendar.resolve_window(target_session, size)
    if window["state"] != "RESOLVED":
        return {**base, "status": INSUFFICIENT_WINDOW, "blockers": [window["state"]], "window_identity": window["calendar_identity"]}
    sessions = window["sessions"]
    field = "value_vnd" if metric == "value" else "volume_shares"
    values, missing, integrity_failed, depth_missing, before_listing = [], [], [], [], []
    for session in sessions:
        row = rows_by_session.get(session)
        if row is None:
            if oldest_retained_session is not None and session < oldest_retained_session:
                (before_listing if series_exhausted else depth_missing).append(session)
            else:
                missing.append(session)
        elif row.get("row_integrity") != "COMPONENTS_SUM_TO_TOTAL":
            integrity_failed.append(session)
        else:
            values.append(Decimal(row["components"][component][field]))
    common = {**base, "window_sessions": sessions, "window_identity": window["calendar_identity"],
              "qualified_sessions": len(values), "missing_sessions": sorted(missing + integrity_failed + depth_missing + before_listing)}
    if len(values) == size:
        mean = sum(values, Decimal(0)) / Decimal(size)
        return {**common, "status": EXACT_WINDOW, "value": format(mean.quantize(Decimal("0.01")), "f"), "blockers": []}
    blockers = ([MISSING_OFFICIAL_ROW] if missing else []) + (["OFFICIAL_ROW_INTEGRITY_FAILED"] if integrity_failed else []) \
        + ([NOT_ACQUIRED_DEPTH] if depth_missing else []) + (["SERIES_STARTS_INSIDE_WINDOW"] if before_listing else [])
    if depth_missing or before_listing:
        return {**common, "status": INSUFFICIENT_WINDOW, "blockers": blockers}
    return {**common, "status": COVERAGE_RESTRICTED_WINDOW, "blockers": blockers + ["NO_EXACT_AVERAGE_EMITTED_FOR_COVERAGE_RESTRICTED_WINDOW"]}


# ---------------------------------------------------------------------------------
# Seven-dimension fitness
# ---------------------------------------------------------------------------------

def _cell(state: str, reason: str, cites: Sequence[str], **extra: Any) -> dict[str, Any]:
    if state not in dimension_basis.DIMENSION_STATES:
        raise LiquidityAuthorityContractError(f"UNREGISTERED_DIMENSION_STATE:{state}")
    if not cites:
        raise LiquidityAuthorityContractError(f"UNCITED_DIMENSION_VERDICT:{reason}")
    return {"state": state, "reason": reason, "cites": list(cites), **extra}


BLOCKED_EXECUTION_REASON = ("no governed participation-rate policy, market-impact model, order-book depth, "
                            "price-limit or intraday liquidity profile exists; ADTV knowledge time is retrospective")
BLOCKED_SIZING_REASON = ("sizing needs qualified liquidity plus portfolio capital, risk budget, participation rate, "
                         "max days-to-liquidate, order size and an execution-capacity model; EXECUTION_CAPACITY is blocked")
BLOCKED_PIT_REASON = ("official series were retrieved retrospectively (no as-known-at publication or revision "
                      "evidence); RAW_AS_TRADED/PIT price basis and historical universe remain unpromoted")


def dimension_fitness(
    *,
    current_basis: str | None,
    current_active: bool,
    official_series_acquired: bool,
    features: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """The seven-dimension table for one ticker; authority-sensitive dimensions never open."""
    if current_active and current_basis in (BASIS_OFFICIAL_RECONCILED, BASIS_UNIT_CONTRACT_APPLIED):
        current = _cell(ELIGIBLE, "current-session component shares/VND under an officially qualified DNSE board-unit contract",
                        ["liquidity_authority_contract.qualify_board_units", "official_exchange_trading_statistics"], measurement_basis=current_basis)
    elif current_active:
        current = _cell(ELIGIBLE, "current-session board counters are descriptive only; at least one active board unit is not qualified for this exchange",
                        ["dnse_trades_liquidity_basis.board_latest_snapshot"], measurement_basis=BASIS_RAW_COUNTERS_ONLY)
    else:
        current = _cell(BLOCKED, "no DNSE board observed active for the target session", ["dnse_trades_liquidity_basis.board_latest_snapshot"])
    adtv = features.get("ADTV20_MATCHED_ALL_VND") or {}
    adv = features.get("ADV20_MATCHED_ALL_SHARES") or {}
    if not official_series_acquired:
        historical = _cell(BLOCKED, "no official exchange per-session series retained for this ticker", ["official_exchange_trading_statistics"])
        adtv_cell = _cell(BLOCKED, "no official matched-value series retained; no secondary anchor exists", ["official_exchange_trading_statistics"])
        adv_cell = _cell(BLOCKED, "no official matched-volume series retained", ["official_exchange_trading_statistics"])
    else:
        exact_hist = adtv.get("status") == EXACT_WINDOW
        historical = _cell(ELIGIBLE if exact_hist else PARTIAL,
                           "official per-session matched/put-through/odd-lot series retained; research use only, retrospective knowledge time"
                           if exact_hist else "official series retained but the governed 20-session window is not complete",
                           ["official_exchange_trading_statistics", "liquidity_authority_contract.official_trailing_feature"])
        adtv_cell = _cell(ELIGIBLE if exact_hist else (PARTIAL if adtv.get("status") == COVERAGE_RESTRICTED_WINDOW else BLOCKED),
                          "ADTV20 of official MATCHED_ALL value (order matching incl. odd lot; put-through excluded) over the exact governed window"
                          if exact_hist else f"ADTV20 window status {adtv.get('status')}",
                          ["liquidity_authority_contract.official_trailing_feature"], feature="ADTV20_MATCHED_ALL_VND")
        adv_cell = _cell(PARTIAL if adv.get("status") == EXACT_WINDOW else BLOCKED,
                         "official as-traded matched shares; share counts are not corporate-action normalized and no ex-date authority "
                         "can rule out a share-count event inside the window" if adv.get("status") == EXACT_WINDOW
                         else f"ADV20 window status {adv.get('status')}",
                         ["liquidity_authority_contract.official_trailing_feature", "docs/STATE.md Invariant 1"], feature="ADV20_MATCHED_ALL_SHARES")
    contract = {
        CURRENT_SESSION_LIQUIDITY_RESEARCH: current,
        HISTORICAL_LIQUIDITY_RESEARCH: historical,
        ADV_VOLUME_RESEARCH: adv_cell,
        ADTV_RESEARCH: adtv_cell,
        EXECUTION_CAPACITY: _cell(BLOCKED, BLOCKED_EXECUTION_REASON, ["docs/STATE.md Invariant 2", "market_volume_capability_matrix.days_to_liquidate"]),
        POSITION_SIZING: _cell(BLOCKED, BLOCKED_SIZING_REASON, ["docs/STATE.md Invariant 2", "liquidity_authority_contract.sizing_readiness_envelope"]),
        PIT_BACKTEST: _cell(BLOCKED, BLOCKED_PIT_REASON, ["docs/STATE.md Invariant 1", "market_data_source_authority.DNSE_OHLC_PRICE_BASIS"]),
    }
    dimension_basis.assert_fail_closed(contract)
    return contract


def sizing_readiness_envelope(*, qualified_liquidity_tickers: int) -> dict[str, Any]:
    """What POSITION_SIZING / EXECUTION_CAPACITY would still need after liquidity qualification."""
    inputs = [
        ("qualified_liquidity_input", "PRESENT_RESEARCH_SCOPED" if qualified_liquidity_tickers else "ABSENT",
         "liquidity_authority_contract ADTV20_MATCHED_ALL_VND (official, retrospective knowledge time)"),
        ("portfolio_capital_and_holdings", "PRESENT_PRIVATE_OWNER_SCOPED", "private_portfolio_context / portfolio_aware_decision (private, not in Git)"),
        ("risk_budget", "PRESENT_POLICY_DEFAULT", "private_portfolio_context portfolio_policy/v1 risk_budget_per_investment_decision_to_nav"),
        ("max_single_position_and_sector_weight", "PRESENT_POLICY_DEFAULT", "private_portfolio_context portfolio_policy/v1"),
        ("volatility_and_risk_inputs", "PRESENT_RESEARCH_SCOPED", "current_portfolio_risk_envelope (research; VaR/CVaR/position_sizing blocked)"),
        ("participation_rate_policy", "ABSENT", "no governed max participation of ADTV exists"),
        ("max_days_to_liquidate_policy", "ABSENT", "market_volume_capability_matrix.days_to_liquidate is UNAVAILABLE_BY_CONTRACT"),
        ("market_impact_model", "ABSENT", "market_volume_capability_matrix.market_impact_estimation is UNAVAILABLE_BY_CONTRACT"),
        ("order_size", "ABSENT", "user-supplied per decision; never inferred"),
        ("intraday_liquidity_profile_and_price_limits", "ABSENT", "no auction/continuous decomposition or price-band model"),
        ("minimum_liquidity_window", "DEFINED", "20 governed sessions (ADTV20), 60 where official depth retained"),
        ("point_in_time_liquidity_knowledge", "ABSENT", BLOCKED_PIT_REASON),
    ]
    return {"inputs": [{"input": name, "status": status, "source": source} for name, status, source in inputs],
            "POSITION_SIZING": BLOCKED, "EXECUTION_CAPACITY": BLOCKED,
            "position_sizing_is_safe": False, "execution_input_eligible": False,
            "note": "Readiness only; no size, participation cap, impact estimate or execution instruction is emitted."}
