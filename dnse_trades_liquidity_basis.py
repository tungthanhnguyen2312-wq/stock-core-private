"""DNSE trades/liquidity basis qualification (``DNSE_TRADES_AND_LIQUIDITY_BASIS_QUALIFICATION_V1``).

WHAT THIS MODULE IS
    A reusable, read-only capability for turning DNSE's per-board trade-tick endpoints
    (``trades_latest``, ``trades_history`` -- both already registered in
    ``dnse_market_data.MARKET_DATA_ENDPOINTS`` under the ``trades`` family) into canonical trade
    records, per-session per-board volume/value snapshots, a cross-check against the existing
    ``C5 = 10 x G1`` shadow candidate, and a fitness-for-use liquidity-research contract. It never
    re-derives board-label semantics (``market_phase2_foundation.DNSE_BOARD_SEMANTICS``) or the
    matched/odd-lot/put-through category split
    (``market_price_volume_basis_authority.assert_lot_and_route_not_conflated``); it only consumes
    them.

WHAT THIS MODULE IS NOT
    Not a bulk historical ingestion pipeline, not a replacement for the orphaned
    ``dnse_trades_canonical_shadow.py`` (commit ``2b7b38772e16c434c8adf5288cbc46ef0f7f4c02``,
    ``SOURCE_GENERATOR_NOT_IN_CURRENT_MAIN_ANCESTRY`` -- that commit is used only as
    implementation archaeology; nothing here imports or replays it), not a liquidity/sizing
    authority, and not a value calculator: every derived-value path fails closed until an explicit,
    external lot-multiplier decision is supplied, which no caller in this milestone provides.

KEY EMPIRICAL FINDING THIS MODULE ENCODES (bounded live probe, 2026-08-21/2026-08-23)
    ``trades_latest`` (no query params) returns, per board that has ever traded, that board's own
    most recent tick -- and that tick's ``totalVolumeTraded``/``grossTradeAmount``/``avgPrice`` are
    already board-scoped *cumulative session* counters, not just that one tick's own size. Reading
    the single latest tick per board is therefore sufficient to recover a board's full-session
    volume; no summation across ticks is required. Across five fresh tickers spanning four sectors
    (HPG steel, VCB banking, SSI securities, FPT technology, QNS food/beverage) on the same session
    (2026-08-21), ``10 x G1.totalVolumeTraded`` equals that session's DNSE daily OHLC ``v`` exactly
    -- independent, live, cross-sector confirmation of the existing shadow ``C5`` candidate
    (``dnse_volume_composition_reconciliation.C5_CANDIDATE``), which remains an
    ``EMPIRICAL_CANDIDATE`` with ``semantic_unit_interpretation=UNKNOWN``: this module does not
    promote it to authority.

    ``trades_history`` pagination toward a *complete* session reconstruction is activity-dependent,
    not uniformly available: a low-activity name (QNS) fully exhausts in 4 pages (387 rows,
    09:16-14:59, matching HOSE's session bounds); a high-activity name during its closing-auction
    burst (HPG, 2026-08-19) advances the clock by only ~0.08 seconds across 300 DESC-ordered rows
    (3 pages) -- full reconstruction there would require an unbounded number of calls and is
    reported ``PARTIAL_BOUNDED_SCAN``, never silently treated as complete.

    ``grossTradeAmount`` is only *arithmetically* self-consistent as
    ``avgPrice_kvnd x totalVolumeTraded_raw / 100_000`` across every observed board -- it is not
    board-agnostic true VND value: applying the same G1 x10 hypothesis implies it lands on true
    cumulative value in *billion VND* for G1 specifically, but would overstate a directly-reported
    (non-x10) board's value by the same factor of 10. This is recorded as an open, unresolved
    finding, never silently resolved in either direction.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from dnse_volume_composition_reconciliation import (
    C5_CANDIDATE,
    CANONICAL_TRADES_LINEAGE_STATUS,
    CANONICAL_TRADES_SOURCE_COMMIT,
    ResidualClass,
    ScaledG1Candidate,
    classify_c5_residual,
)
from market_phase2_foundation import DNSE_BOARD_SEMANTICS
from market_price_volume_basis_authority import assert_lot_and_route_not_conflated

CONTRACT_VERSION = "dnse_trades_liquidity_basis/v1"
SCHEMA_VERSION = "1.0.0"
MILESTONE = "DNSE_TRADES_AND_LIQUIDITY_BASIS_QUALIFICATION_V1"

#: This module's own live-probe evidence lineage -- always distinct from, and never confused
#: with, the orphaned canonical-Trades generator's lineage status.
LIVE_ADAPTER_LINEAGE_STATUS = "LIVE_BOUNDED_ADAPTER_PROBE_2026_08_23"

KNOWN_BOARD_CODES = frozenset(DNSE_BOARD_SEMANTICS)

# ---------------------------------------------------------------------------------
# Liquidity-research dimension taxonomy (fixed by the milestone; never inferred per-row)
# ---------------------------------------------------------------------------------

CURRENT_SESSION_LIQUIDITY_RESEARCH = "CURRENT_SESSION_LIQUIDITY_RESEARCH"
HISTORICAL_LIQUIDITY_RESEARCH = "HISTORICAL_LIQUIDITY_RESEARCH"
ADV_VOLUME_RESEARCH = "ADV_VOLUME_RESEARCH"
ADTV_RESEARCH = "ADTV_RESEARCH"
POSITION_SIZING = "POSITION_SIZING"
EXECUTION_CAPACITY = "EXECUTION_CAPACITY"
PIT_BACKTEST = "PIT_BACKTEST"

LIQUIDITY_DIMENSIONS = (
    CURRENT_SESSION_LIQUIDITY_RESEARCH, HISTORICAL_LIQUIDITY_RESEARCH, ADV_VOLUME_RESEARCH,
    ADTV_RESEARCH, POSITION_SIZING, EXECUTION_CAPACITY, PIT_BACKTEST,
)

ELIGIBLE = "ELIGIBLE"
PARTIAL = "PARTIAL"
BLOCKED = "BLOCKED"
UNKNOWN = "UNKNOWN"
NOT_APPLICABLE = "NOT_APPLICABLE"
DIMENSION_STATES = (ELIGIBLE, PARTIAL, BLOCKED, UNKNOWN, NOT_APPLICABLE)

_AUTHORITY_SENSITIVE_DIMENSIONS = frozenset({POSITION_SIZING, EXECUTION_CAPACITY, PIT_BACKTEST})

# Board-level completeness states for one (ticker, session) trades_history scan.
COMPLETE = "COMPLETE"
PARTIAL_BOUNDED_SCAN = "PARTIAL_BOUNDED_SCAN"
NOT_OBSERVED_WITHIN_BOUNDED_SCAN = "NOT_OBSERVED_WITHIN_BOUNDED_SCAN"
CONFIRMED_NO_ACTIVITY = "CONFIRMED_NO_ACTIVITY"

# trades_latest-derived board activity states.
OBSERVED_ACTIVE_THIS_SESSION = "OBSERVED_ACTIVE_THIS_SESSION"
OBSERVED_INACTIVE_STALE = "OBSERVED_INACTIVE_STALE"
NOT_OBSERVED = "NOT_OBSERVED"


class TradesLiquidityBasisError(ValueError):
    """A caller violated this module's own fail-closed shape -- never silently coerced."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = _sha256(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"dnse_trades_liquidity_basis:{digest}"}


def serialize(value: Mapping[str, Any]) -> str:
    return _canonical_json(value)


def _fitness(state: str, *, reason: str, cites: Sequence[str]) -> dict[str, Any]:
    if state not in DIMENSION_STATES:
        raise TradesLiquidityBasisError(f"unregistered_dimension_state:{state}")
    if not cites:
        raise TradesLiquidityBasisError(f"dimension_verdict_requires_citation:{reason}")
    return {"state": state, "reason": reason, "cites": list(cites)}


# ---------------------------------------------------------------------------------
# Section 1: raw response -> canonical trade-tick records
# ---------------------------------------------------------------------------------

_REQUIRED_NUMERIC_FIELDS = ("matchPrice", "matchQtty", "avgPrice", "totalVolumeTraded", "grossTradeAmount")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def canonicalize_trade_tick(raw: Mapping[str, Any], *, symbol: str, endpoint: str) -> dict[str, Any]:
    """Map one raw DNSE trade-tick object into an immutable canonical record.

    Fails closed (``parse_status != "PARSED"``) on a missing/mistyped required field or an
    unrecognized ``boardId`` -- this never invents a board semantic or coerces a bad value.
    ``side`` is carried through verbatim and is never assigned directional meaning here (matching
    ``docs/DATA_FIRST_DOCTRINE.md`` and the orphaned canonicalizer's own stated discipline).
    """
    raw_sha256 = _sha256(raw)
    board_id = raw.get("boardId")
    if board_id not in KNOWN_BOARD_CODES:
        return {"parse_status": "UNRECOGNIZED_BOARD_ID", "raw_board_id": board_id, "raw_sha256": raw_sha256}
    for field_name in _REQUIRED_NUMERIC_FIELDS:
        if not _is_number(raw.get(field_name)):
            return {"parse_status": "REQUIRED_FIELD_MISSING_OR_INVALID", "field": field_name, "raw_sha256": raw_sha256}
    raw_time = raw.get("time")
    if not isinstance(raw_time, str) or " " not in raw_time:
        return {"parse_status": "TIME_FIELD_MISSING_OR_INVALID", "raw_sha256": raw_sha256}
    session_date = raw_time.split(" ", 1)[0]
    try:
        datetime.strptime(session_date, "%Y-%m-%d")
    except ValueError:
        return {"parse_status": "TIME_FIELD_MISSING_OR_INVALID", "raw_sha256": raw_sha256}
    return {
        "parse_status": "PARSED",
        "schema_version": "dnse_trade_tick/v1",
        "provider": "DNSE",
        "endpoint": endpoint,
        "symbol": symbol.upper(),
        "board_id": board_id,
        "board_semantic": DNSE_BOARD_SEMANTICS[board_id],
        "session_date": session_date,
        "raw_time": raw_time,
        "match_price_kvnd": float(raw["matchPrice"]),
        "match_quantity_raw": float(raw["matchQtty"]),
        "avg_price_kvnd": float(raw["avgPrice"]),
        "cumulative_volume_raw": float(raw["totalVolumeTraded"]),
        "cumulative_gross_trade_amount_raw": float(raw["grossTradeAmount"]),
        "side_raw": raw.get("side"),
        "market_id_raw": raw.get("marketId"),
        "isin_raw": raw.get("isin"),
        "raw_sha256": raw_sha256,
    }


def parse_trades_response(raw_body: Mapping[str, Any], *, symbol: str, endpoint: str) -> dict[str, Any]:
    """Parse one ``trades_latest``/``trades_history`` HTTP body into canonical records.

    Never raises on a malformed body; returns a structured failure instead so a bounded probe run
    always finishes and reports.
    """
    raw_sha256 = _sha256(raw_body)
    trades = raw_body.get("trades") if isinstance(raw_body, Mapping) else None
    if not isinstance(trades, list):
        return {"parse_status": "TRADES_ARRAY_ABSENT_OR_INVALID", "raw_sha256": raw_sha256}
    records = [canonicalize_trade_tick(row, symbol=symbol, endpoint=endpoint) for row in trades if isinstance(row, Mapping)]
    return {
        "parse_status": "PARSED",
        "symbol": symbol.upper(),
        "endpoint": endpoint,
        "records": records,
        "parsed_count": sum(1 for r in records if r["parse_status"] == "PARSED"),
        "rejected_count": sum(1 for r in records if r["parse_status"] != "PARSED"),
        "next_page_token_present": bool(raw_body.get("nextPageToken")),
        "raw_sha256": raw_sha256,
    }


# ---------------------------------------------------------------------------------
# Section 2: per-board session snapshot (trades_latest leg -- complete by construction)
# ---------------------------------------------------------------------------------

def board_latest_snapshot(records: Iterable[Mapping[str, Any]], *, target_session_date: str | None = None) -> dict[str, Any]:
    """Resolve one representative record per known board code from a set of parsed records.

    Ties within a board are broken by the highest ``cumulative_volume_raw`` (the most-advanced
    running counter, i.e. the true latest observation for that board). If ``target_session_date``
    is omitted, it is resolved as the maximum ``session_date`` observed across all input records
    -- the natural "most recently active session" reading, never an assumed wall-clock "today".
    """
    parsed = [r for r in records if r.get("parse_status") == "PARSED"]
    by_board: dict[str, dict[str, Any]] = {}
    for record in parsed:
        board_id = record["board_id"]
        current = by_board.get(board_id)
        if current is None or record["cumulative_volume_raw"] > current["cumulative_volume_raw"]:
            by_board[board_id] = record

    resolved_target = target_session_date or (
        max((r["session_date"] for r in parsed), default=None)
    )

    boards: dict[str, dict[str, Any]] = {}
    for board_id in sorted(KNOWN_BOARD_CODES):
        record = by_board.get(board_id)
        if record is None:
            boards[board_id] = {"activity_state": NOT_OBSERVED, "board_semantic": DNSE_BOARD_SEMANTICS[board_id]}
            continue
        if resolved_target is not None and record["session_date"] == resolved_target:
            boards[board_id] = {**record, "activity_state": OBSERVED_ACTIVE_THIS_SESSION}
        else:
            boards[board_id] = {**record, "activity_state": OBSERVED_INACTIVE_STALE, "last_active_session_date": record["session_date"]}

    return {"target_session_date": resolved_target, "boards": boards}


def board_category_totals(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Sum ``cumulative_volume_raw`` per matched/odd-lot/put-through category.

    Only ``OBSERVED_ACTIVE_THIS_SESSION`` boards contribute a nonzero volume; a category with an
    ``OBSERVED_INACTIVE_STALE`` or ``NOT_OBSERVED`` member records that member explicitly in
    ``boards_not_counted`` rather than silently folding it into a bare zero.
    """
    categories = assert_lot_and_route_not_conflated()
    boards = snapshot["boards"]
    result: dict[str, Any] = {}
    for category, codes in categories.items():
        active_total = 0.0
        not_counted: list[dict[str, str]] = []
        for code in codes:
            entry = boards.get(code, {})
            if entry.get("activity_state") == OBSERVED_ACTIVE_THIS_SESSION:
                active_total += entry["cumulative_volume_raw"]
            else:
                not_counted.append({"board_id": code, "activity_state": entry.get("activity_state", NOT_OBSERVED)})
        result[category] = {
            "boards": list(codes),
            "active_volume_raw_total": active_total,
            "boards_not_counted": not_counted,
        }
    return result


# ---------------------------------------------------------------------------------
# Section 3: bounded trades_history pagination-scan completeness (historical leg)
# ---------------------------------------------------------------------------------

def scan_completeness(
    *, boards_seen: Sequence[str], target_boards: Sequence[str] = tuple(sorted(KNOWN_BOARD_CODES)),
    pages_fetched: int, page_cap: int, exhausted: bool,
) -> dict[str, Any]:
    """Classify one bounded ``trades_history`` DESC pagination scan.

    ``exhausted`` means the server returned an empty/absent ``nextPageToken`` before ``page_cap``
    was reached -- the only condition under which a board's absence may be read as
    ``CONFIRMED_NO_ACTIVITY`` rather than merely unscanned.
    """
    missing = [code for code in target_boards if code not in boards_seen]
    return {
        "pages_fetched": pages_fetched,
        "page_cap": page_cap,
        "pagination_exhausted": exhausted,
        "boards_seen": sorted(boards_seen),
        "boards_confirmed_absent": sorted(missing) if exhausted else [],
        "boards_unscanned": [] if exhausted else sorted(missing),
        "state": COMPLETE if exhausted else PARTIAL_BOUNDED_SCAN,
        "lower_bound_only": not exhausted,
    }


# ---------------------------------------------------------------------------------
# Section 4: G1 x10 cross-check against OHLC daily v (reuses the existing C5 engine)
# ---------------------------------------------------------------------------------

def g1_scale_cross_check(
    snapshot: Mapping[str, Any], *, ohlc_v: float | None, candidate: ScaledG1Candidate = C5_CANDIDATE,
) -> dict[str, Any]:
    """Test the existing shadow ``C5`` candidate (``10 x G1``) against a fresh live observation.

    Never promotes the candidate: the output ``scale_status``/``semantic_unit_interpretation`` are
    read straight from the cited candidate object, unchanged.
    """
    g1 = snapshot["boards"].get("G1", {})
    if ohlc_v is None or g1.get("activity_state") != OBSERVED_ACTIVE_THIS_SESSION:
        return {"verdict": "UNAVAILABLE", "reason": "missing_g1_active_observation_or_ohlc_v"}
    g1_quantity = g1["cumulative_volume_raw"]
    computed = candidate.compute(g1_quantity)
    delta = float(ohlc_v) - computed
    return {
        "verdict": classify_c5_residual(delta).value,
        "ohlc_v": ohlc_v,
        "g1_cumulative_volume_raw": g1_quantity,
        "candidate": candidate.record(),
        "candidate_value": computed,
        "delta": delta,
        "exact_match": delta == 0.0,
        "lineage_status": LIVE_ADAPTER_LINEAGE_STATUS,
        "contrast_with_orphaned_generator": {
            "orphaned_source_commit": CANONICAL_TRADES_SOURCE_COMMIT,
            "orphaned_lineage_status": CANONICAL_TRADES_LINEAGE_STATUS,
        },
    }


# ---------------------------------------------------------------------------------
# Section 5: traded value -- direct candidate, and a value-derivation gate that fails closed
# ---------------------------------------------------------------------------------

def gross_trade_amount_uniform_formula_check(record: Mapping[str, Any], *, relative_tolerance: float = 0.01) -> dict[str, Any]:
    """Recompute ``avgPrice x totalVolumeTraded / 100_000`` and compare to the reported
    ``grossTradeAmount``. This checks arithmetic self-consistency only -- it makes no claim about
    what unit or true VND magnitude the field represents for any given board."""
    if record.get("parse_status") != "PARSED":
        return {"verdict": "UNAVAILABLE"}
    expected = record["avg_price_kvnd"] * record["cumulative_volume_raw"] / 100_000.0
    reported = record["cumulative_gross_trade_amount_raw"]
    if expected == 0:
        consistent = reported == 0
    else:
        consistent = abs(reported - expected) / abs(expected) <= relative_tolerance
    return {
        "verdict": "CONSISTENT_WITH_UNIFORM_FORMULA" if consistent else "INCONSISTENT",
        "expected_from_uniform_formula": expected,
        "reported_gross_trade_amount": reported,
    }


def traded_value_candidate(record: Mapping[str, Any]) -> dict[str, Any]:
    """The DIRECT-supplied traded-value candidate for one board's session snapshot.

    Never authoritative. For a non-G1 board this repeats the module docstring's open finding:
    applying the same G1 x10 hypothesis to a board whose quantity is NOT independently hypothesized
    to need x10 would overstate true value by the same factor of 10 -- so the candidate is returned
    for every board, but flagged, never resolved, outside G1.
    """
    if record.get("parse_status") != "PARSED":
        return {"method": "DNSE_DIRECT_GROSS_TRADE_AMOUNT_FIELD", "state": "UNAVAILABLE"}
    board_id = record["board_id"]
    return {
        "method": "DNSE_DIRECT_GROSS_TRADE_AMOUNT_FIELD",
        "board_id": board_id,
        "value_candidate_raw": record["cumulative_gross_trade_amount_raw"],
        "authoritative": False,
        "semantic_unit_interpretation": "UNKNOWN",
        "cross_board_scale_ambiguity_open": board_id != "G1",
        "evidence": "dnse_trades_liquidity_basis.gross_trade_amount_uniform_formula_check",
    }


def derived_value_price_times_shares(record: Mapping[str, Any], *, lot_multiplier: float | None = None) -> dict[str, Any]:
    """A derived ``PRICE_TIMES_EXECUTED_SHARES`` value -- structurally blocked unless a caller
    supplies an explicit ``lot_multiplier``. Nothing in this milestone supplies one: the lot/scale
    ambiguity documented in this module's docstring remains open, so this always reports
    ``BLOCKED`` in current usage, by design (milestone section 7)."""
    if record.get("parse_status") != "PARSED":
        return {"method": "PRICE_TIMES_EXECUTED_SHARES", "state": "UNAVAILABLE"}
    if lot_multiplier is None:
        return {
            "method": "PRICE_TIMES_EXECUTED_SHARES", "state": "BLOCKED",
            "reason": "lot_multiplier_ambiguity_unresolved",
        }
    true_shares = record["cumulative_volume_raw"] * lot_multiplier
    true_price_vnd = record["match_price_kvnd"] * 1000.0
    return {
        "method": "PRICE_TIMES_EXECUTED_SHARES", "state": "COMPUTED",
        "lot_multiplier_used": lot_multiplier, "true_shares": true_shares,
        "value_vnd": true_price_vnd * true_shares,
        "authoritative": False,
    }


# ---------------------------------------------------------------------------------
# Section 6: liquidity-research fitness contract
# ---------------------------------------------------------------------------------

def session_liquidity_research_contract(
    *, current_session_boards_active: bool, historical_scan_state: str | None,
) -> dict[str, dict[str, Any]]:
    """The 7-dimension liquidity-research eligibility table (milestone section 12).

    One successful current-session aggregate never promotes historical ADV/ADTV or sizing --
    each dimension below is independently derived and independently cited.
    """
    current_state = ELIGIBLE if current_session_boards_active else BLOCKED
    historical_state = {
        COMPLETE: PARTIAL, PARTIAL_BOUNDED_SCAN: BLOCKED, None: UNKNOWN,
    }.get(historical_scan_state, UNKNOWN)

    return {
        CURRENT_SESSION_LIQUIDITY_RESEARCH: _fitness(
            current_state,
            reason=(
                "trades_latest gives a complete, non-paginated per-board cumulative volume/value "
                "reading for the most recently active session; this is a research-descriptive "
                "capability only, not a promoted liquidity/turnover authority"
                if current_session_boards_active else
                "no board observed active for the resolved target session"
            ),
            cites=["dnse_trades_liquidity_basis.board_latest_snapshot"],
        ),
        HISTORICAL_LIQUIDITY_RESEARCH: _fitness(
            historical_state,
            reason=(
                "a fully-exhausted bounded trades_history scan yields a genuine per-board session "
                "total for that one session only (demonstrated on a low-activity name); it is not "
                "a general historical-liquidity authority and does not extend to sessions not "
                "individually scanned"
                if historical_state == PARTIAL else
                "trades_history pagination toward full-session completeness is activity-dependent; "
                "a high-activity session's closing-auction burst makes bounded pagination reach "
                "only a small time slice, so the scan is left-truncated and unusable for a "
                "historical liquidity claim"
                if historical_state == BLOCKED else
                "no bounded historical scan was supplied for this evaluation"
            ),
            cites=["dnse_trades_liquidity_basis.scan_completeness"],
        ),
        ADV_VOLUME_RESEARCH: _fitness(
            BLOCKED,
            reason=(
                "average daily volume requires multiple complete sessions; bounded trades_history "
                "pagination is proven activity-dependent (complete for a low-activity name, "
                "left-truncated for a high-activity name's auction burst) and cannot be relied on "
                "across an arbitrary multi-session window within a finite call budget"
            ),
            cites=["dnse_trades_liquidity_basis.scan_completeness", "docs/STATE.md P0-B"],
        ),
        ADTV_RESEARCH: _fitness(
            BLOCKED,
            reason=(
                "average daily traded VALUE inherits the same multi-session completeness blocker "
                "as ADV, plus the open grossTradeAmount board-dependent scale ambiguity documented "
                "in this module"
            ),
            cites=["dnse_trades_liquidity_basis.gross_trade_amount_uniform_formula_check", "docs/STATE.md P0-B"],
        ),
        POSITION_SIZING: _fitness(
            BLOCKED,
            reason="no historical completeness, no resolved lot-multiplier, no qualified PIT price basis",
            cites=["dnse_trades_liquidity_basis.derived_value_price_times_shares", "docs/STATE.md Invariant 2"],
        ),
        EXECUTION_CAPACITY: _fitness(
            BLOCKED,
            reason="a prerequisite of POSITION_SIZING; inherits the same block",
            cites=["docs/STATE.md Invariant 2"],
        ),
        PIT_BACKTEST: _fitness(
            BLOCKED,
            reason="DNSE OHLC price basis remains ADJUSTED_CONFIRMED_NON_RAW_NON_POINT_IN_TIME regardless of this milestone's volume findings",
            cites=["market_data_source_authority.DNSE_OHLC_PRICE_BASIS"],
        ),
    }


def assert_fail_closed(contract: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Mapping[str, Any]]:
    """The one hard safety net over the liquidity-research contract."""
    missing = set(LIQUIDITY_DIMENSIONS) - set(contract)
    if missing:
        raise TradesLiquidityBasisError(f"contract_missing_dimensions:{sorted(missing)}")
    for dimension in _AUTHORITY_SENSITIVE_DIMENSIONS:
        cell = contract[dimension]
        if cell["state"] in (ELIGIBLE, PARTIAL):
            raise TradesLiquidityBasisError(f"authority_sensitive_dimension_must_not_be_open:{dimension}:{cell['state']}")
        if not cell.get("cites"):
            raise TradesLiquidityBasisError(f"uncited_dimension_verdict:{dimension}")
    return contract
