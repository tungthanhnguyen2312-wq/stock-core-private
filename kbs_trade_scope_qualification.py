"""KBS trade-scope (market-composition) qualification, from two surfaces never examined by
the P0-Z lane: the price board (``stock/iss``) and the intraday trade tape
(``trade/history/{symbol}``).

WHY THIS LANE OPENED
    ``kbs_empirical_basis.market_scope_contract()`` correctly reported all six market-scope
    dimensions ``unknown`` -- but that lane examined exactly one endpoint, the daily chart
    (``data_day``), which genuinely carries no scope-distinguishing field. Two different,
    already-installed KBS endpoints on the same approved host were never examined: the price
    board, which separately reports ``put_through_qty``/``put_through_value``, and the
    intraday tape, whose per-row ``side`` field is empty on exactly the rows a call auction
    produces. Finding them is not re-deriving the P0-Z finding; it is testing surfaces P0-Z
    never reached.

WHAT WAS FOUND, PRECISELY, AND NO FURTHER
    For three tickers (HPG, VNM, VCB), one session (2026-08-07), the intraday tape's full
    trading day (09:15-14:45, matching HOSE's own session bounds) sums -- continuous
    buy/sell trades plus the handful of side-less, auction-cleared trades -- to *exactly*
    the price board's ``volume_accumulated`` (the field already established elsewhere in
    this repository to be numerically identical to the already-qualified daily ``v``).
    ``put_through_qty`` plays no part in that sum in any of the three reconciliations: zero
    residual, three times, is what "excluded" means here.

WHAT THIS DOES NOT ESTABLISH
    Which of the two side-less prints is the opening auction and which is the closing
    auction: that split is ``vnstock``'s own time-window heuristic
    (``core.utils.transform.process_match_types``, matching a raw empty-side row against a
    9:13-9:17 / 14:43-14:47 clock window), not a first-party KBS field. This module never
    relies on it -- it qualifies one combined ``auction_inclusion`` dimension, never split
    into ATO/ATC, exactly because the split is inferred and the inclusion fact is not.
    ``odd_lot_inclusion`` stays unknown: no reachable free-tier endpoint distinguishes it,
    and the installed library's own module docstring names dedicated odd-lot/put-through
    detail endpoints as Sponsor-only -- not probed, per this project's standing refusal to
    reach for an endpoint that is not already installed and reachable.
    A ``PMQ``/``PMP`` ("previous match") field pair was checked as a possible second
    independent corroboration of the put-through print specifically (mirroring how VCI's ATO
    finding needed a second field). It agreed exactly for HPG, only on price for VNM, and not
    at all for VCB -- consistent with it being a live "most recent trade at snapshot time"
    field rather than a stable reference to the put-through print, and it is not relied on
    anywhere below.

    One session is one window. ``coverage_generalization`` stays
    ``limited_to_tested_windows`` and ``provider_methodology`` stays ``unknown`` throughout,
    exactly as ``kbs_empirical_basis.py`` already requires for every empirical verdict in
    this repository.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import evidence_qualification_tiers as tiers

VERSION = "1.0.0"
PROVIDER = "KBS"

#: Same source authority as kbs_empirical_basis.py -- an observed public web endpoint with
#: no first-party developer documentation, reused rather than restated.
SOURCE_AUTHORITY = "observed_public_web_endpoint"

TESTED_TICKERS = ("HPG", "VNM", "VCB")
TESTED_SESSION = "2026-08-07"

DIMENSION_CONTINUOUS = "continuous_matching_inclusion"
DIMENSION_AUCTION = "auction_inclusion"
DIMENSION_NEGOTIATED = "negotiated_trade_inclusion"
DIMENSION_ODD_LOT = "odd_lot_inclusion"
DIMENSIONS = (DIMENSION_CONTINUOUS, DIMENSION_AUCTION, DIMENSION_NEGOTIATED, DIMENSION_ODD_LOT)

#: A dimension's finding, kept distinct from evidence *strength* (which lives in
#: ``qualification``, the tiers.py ladder). "excluded" is not "unknown" -- it is a positive,
#: evidenced finding that the category is demonstrably absent from the reconciled field.
INCLUDED = "included"
EXCLUDED = "excluded"
UNKNOWN = "unknown"
INCLUSION_STATES = frozenset({INCLUDED, EXCLUDED, UNKNOWN})

MIN_INDEPENDENT_OBSERVATIONS = 2


class TradeScopeError(ValueError):
    """Fail-closed rejection in the KBS trade-scope qualification."""


# ---------------------------------------------------------------------------------
# Pure parsing -- raw provider bytes in, normalized rows out, no I/O
# ---------------------------------------------------------------------------------


def parse_price_board(raw: Any, *, ticker: str) -> dict[str, Any]:
    """One ticker's row from the price-board response. Refuses a missing ticker."""
    rows = raw.get("data") if isinstance(raw, Mapping) else raw
    if not isinstance(rows, list):
        raise TradeScopeError("price_board_payload_not_a_list")
    by_symbol = {str(r.get("SB")): r for r in rows if isinstance(r, Mapping)}
    row = by_symbol.get(ticker)
    if row is None:
        raise TradeScopeError(f"price_board_missing_ticker:{ticker}")
    required = ("TT", "PTQ", "PTV", "TD")
    missing = [f for f in required if f not in row]
    if missing:
        raise TradeScopeError(f"price_board_row_missing_fields:{','.join(missing)}")
    return {
        "ticker": ticker,
        "trading_date": str(row["TD"]),
        "volume_accumulated": int(row["TT"]),
        "put_through_qty": int(row["PTQ"]),
        "put_through_value": int(row["PTV"]),
    }


def parse_intraday_tape(raw: Any, *, ticker: str) -> list[dict[str, Any]]:
    """Raw intraday rows -> normalized rows. A blank ``LC`` (side) is preserved as ``None``,
    never coerced to a guessed side -- that emptiness is the auction signal this module
    reads, not noise to clean up.
    """
    rows = raw.get("data") if isinstance(raw, Mapping) else raw
    if not isinstance(rows, list):
        raise TradeScopeError("intraday_payload_not_a_list")
    out: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise TradeScopeError(f"intraday_row_not_an_object:index={index}")
        if str(row.get("SB")) != ticker:
            raise TradeScopeError(f"intraday_row_ticker_mismatch:index={index}")
        missing = [f for f in ("t", "FV", "AVO") if f not in row]
        if missing:
            raise TradeScopeError(f"intraday_row_missing_fields:{','.join(missing)}@index={index}")
        side = str(row.get("LC") or "").strip()
        out.append(
            {
                "timestamp": str(row["t"]),
                "volume": int(row["FV"]),
                "accumulated_volume": int(row["AVO"]),
                "side": side or None,
            }
        )
    return out


# ---------------------------------------------------------------------------------
# The decisive per-ticker reconciliation
# ---------------------------------------------------------------------------------


def reconcile_session(*, tape: Sequence[Mapping[str, Any]], board: Mapping[str, Any]) -> dict[str, Any]:
    """Whether the tape's full-day sum accounts for ``volume_accumulated`` exactly, and
    whether ``put_through_qty`` played any part in it.

    ``side is None`` rows are the auction-cleared trades -- structurally so: a call auction
    clears multiple orders at one price with no single aggressor, which is why continuous
    (order-driven) trades carry a side and auction trades do not. This module relies only on
    that structural fact, not on which specific auction (opening or closing) a given row is.
    """
    continuous_rows = [r for r in tape if r["side"] is not None]
    auction_rows = [r for r in tape if r["side"] is None]
    continuous_volume = sum(r["volume"] for r in continuous_rows)
    auction_volume = sum(r["volume"] for r in auction_rows)
    tape_total = continuous_volume + auction_volume
    accumulated = board["volume_accumulated"]
    put_through = board["put_through_qty"]
    exact = tape_total == accumulated
    return {
        "ticker": board["ticker"],
        "trading_date": board["trading_date"],
        "tape_rows": len(tape),
        "continuous_trade_count": len(continuous_rows),
        "auction_trade_count": len(auction_rows),
        "continuous_volume": continuous_volume,
        "auction_volume": auction_volume,
        "tape_total": tape_total,
        "volume_accumulated": accumulated,
        "put_through_qty": put_through,
        "residual": accumulated - tape_total,
        "tape_matches_accumulated_exactly": exact,
        # Decisive only when the tape already accounts for 100% of the accumulated figure
        # with no room left over: put-through cannot be "excluded" from a reconciliation
        # that still has an unexplained gap it could be hiding inside.
        "put_through_demonstrated_excluded": exact and put_through > 0,
    }


def assert_full_session_coverage(tape: Sequence[Mapping[str, Any]], *, expected_open: str = "09:1", expected_close: str = "14:4") -> None:
    """Refuse a tape that looks truncated rather than a full trading day.

    Coarse on purpose: this checks the tape *spans* the session, not that every minute is
    present. A paginated or partial pull is the one failure mode this guards against --
    the reconciliation above is meaningless against a truncated tape.
    """
    if not tape:
        raise TradeScopeError("empty_tape_cannot_demonstrate_session_coverage")
    times = sorted(r["timestamp"] for r in tape)
    if not times[0].split(" ")[-1].startswith(expected_open):
        raise TradeScopeError(f"tape_does_not_start_near_session_open:{times[0]}")
    if not times[-1].split(" ")[-1].startswith(expected_close):
        raise TradeScopeError(f"tape_does_not_end_near_session_close:{times[-1]}")


# ---------------------------------------------------------------------------------
# Dimension qualification -- reuses evidence_qualification_tiers, not a parallel ladder
# ---------------------------------------------------------------------------------


def qualify_dimensions(reconciliations: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Roll bounded per-ticker reconciliations up into the four dimension verdicts.

    Requires at least :data:`MIN_INDEPENDENT_OBSERVATIONS` exact, independent-ticker
    reconciliations before any dimension leaves ``unknown`` -- the same threshold
    ``kbs_empirical_basis.MIN_INDEPENDENT_OBSERVATIONS_FOR_SCOPE`` already applies to scope
    dimensions, reused here rather than restated.
    """
    exact = [r for r in reconciliations if r["tape_matches_accumulated_exactly"]]
    tickers = {r["ticker"] for r in exact}
    sufficient = len(exact) >= MIN_INDEPENDENT_OBSERVATIONS and len(tickers) >= MIN_INDEPENDENT_OBSERVATIONS

    if not sufficient:
        return {
            dimension: {
                "dimension": dimension,
                "inclusion_state": UNKNOWN,
                "qualification": tiers.UNKNOWN,
                "independent_observations": len(exact),
                "reason": "insufficient_exact_reconciliations",
            }
            for dimension in DIMENSIONS
        }

    all_have_continuous = all(r["continuous_volume"] > 0 for r in exact)
    all_have_auction = all(r["auction_volume"] > 0 for r in exact)
    all_exclude_put_through = all(r["put_through_demonstrated_excluded"] for r in exact)
    any_put_through_present = any(r["put_through_qty"] > 0 for r in exact)

    def _record(dimension: str, state: str, note: str) -> dict[str, Any]:
        return {
            "dimension": dimension,
            "inclusion_state": state,
            "qualification": tiers.EMPIRICALLY_DEDUCED if state != UNKNOWN else tiers.UNKNOWN,
            "independent_observations": len(exact),
            "observed_tickers": sorted(tickers),
            "note": note,
        }

    return {
        DIMENSION_CONTINUOUS: _record(
            DIMENSION_CONTINUOUS,
            INCLUDED if all_have_continuous else UNKNOWN,
            "Every reconciled session has nonzero side-labelled (buy/sell) volume, "
            "included in the exact reconciliation.",
        ),
        DIMENSION_AUCTION: _record(
            DIMENSION_AUCTION,
            INCLUDED if all_have_auction else UNKNOWN,
            "Every reconciled session has nonzero side-less volume, included in the exact "
            "reconciliation. Opening vs. closing auction is not distinguished here -- see "
            "module docstring.",
        ),
        DIMENSION_NEGOTIATED: _record(
            DIMENSION_NEGOTIATED,
            EXCLUDED if (all_exclude_put_through and any_put_through_present) else UNKNOWN,
            "put_through_qty is separately, nonzero-ly reported and plays no part in any "
            "exact reconciliation: three tickers, zero residual, put-through excluded from "
            "volume_accumulated (the field already established numerically identical to "
            "the already-qualified daily v).",
        ),
        DIMENSION_ODD_LOT: _record(
            DIMENSION_ODD_LOT,
            UNKNOWN,
            "No reachable free-tier KBS surface distinguishes odd-lot trades; the "
            "dedicated endpoint is Sponsor-tier and not probed.",
        ),
    }


# ---------------------------------------------------------------------------------
# The contract
# ---------------------------------------------------------------------------------


def trade_scope_contract(
    reconciliations: Sequence[Mapping[str, Any]], *, raw_artifact_hashes: Sequence[str] = ()
) -> dict[str, Any]:
    dimensions = qualify_dimensions(reconciliations)
    states = {d["inclusion_state"] for d in dimensions.values()}
    # Any dimension resolved (included or excluded) is real progress over the all-unknown
    # starting state, even though odd_lot stays unknown and nothing here is a full
    # composition qualification -- "unresolved" is reserved for the case nothing moved.
    overall = "unresolved" if states <= {UNKNOWN} else "partial_composition_qualified"

    empirical_record = tiers.assert_empirically_deduced(
        {
            "test_method": "complete_intraday_tape_reconciliation_against_price_board_accumulator",
            "tested_fields": ["volume_accumulated (TT)", "put_through_qty (PTQ)", "intraday side (LC)"],
            "tested_tickers": sorted({r["ticker"] for r in reconciliations}),
            "tested_date_windows": sorted({r["trading_date"] for r in reconciliations}),
            "event_evidence": [],
            "raw_artifact_hashes": list(raw_artifact_hashes),
            "transformation_version": VERSION,
            "alternative_explanations_considered": [
                "tape_pagination_truncation_hiding_a_residual",
                "put_through_qty_double_counted_inside_accumulated_volume_by_coincidence",
                "empty_side_rows_being_a_data_defect_rather_than_auction_clearing",
            ],
            "falsification_attempts": [
                "checked_tape_spans_full_session_09:15_to_14:45_not_a_partial_page",
                "checked_residual_is_exactly_zero_not_approximately_zero",
            ],
            "confidence": "moderate",
            "scope_limitations": [
                "one_session_only_2026-08-07",
                "opening_vs_closing_auction_split_relies_on_a_third_party_time_window_heuristic_not_used_here",
                "odd_lot_inclusion_untested",
            ],
            "retrieval_timestamps": ["2026-08-09"],
            "historical_mutability": "not_observed",
        }
    )

    return {
        "schema_version": VERSION,
        "provider": PROVIDER,
        "source_authority": SOURCE_AUTHORITY,
        "dimensions": dimensions,
        "overall_composition_state": overall,
        "liquidity_actionable": False,
        "reopen_condition": "additional_independent_trading_sessions_or_a_first_party_kbs_api_specification",
        "empirical_record": empirical_record,
    }


def assert_contract_fail_closed(contract: Mapping[str, Any]) -> Mapping[str, Any]:
    if contract.get("liquidity_actionable"):
        raise TradeScopeError("liquidity_actionable_must_stay_false")
    if contract.get("provider") != PROVIDER:
        raise TradeScopeError("contract_provider_must_be_kbs")
    for dimension, record in contract["dimensions"].items():
        if dimension not in DIMENSIONS:
            raise TradeScopeError(f"unknown_dimension_in_contract:{dimension}")
        if record["inclusion_state"] not in INCLUSION_STATES:
            raise TradeScopeError(f"invalid_inclusion_state:{dimension}={record['inclusion_state']}")
        if record["inclusion_state"] != UNKNOWN and record["qualification"] != tiers.EMPIRICALLY_DEDUCED:
            raise TradeScopeError(f"resolved_dimension_must_carry_empirically_deduced_tier:{dimension}")
    if contract["dimensions"][DIMENSION_ODD_LOT]["inclusion_state"] != UNKNOWN:
        raise TradeScopeError("odd_lot_inclusion_was_not_tested_and_must_stay_unknown")
    return contract


# ---------------------------------------------------------------------------------
# The frozen result -- computed once from retained evidence, not re-read at import time
# ---------------------------------------------------------------------------------
#
# active_contract() must not depend on operations-review/ still being present on disk at
# call time: that directory is an evidence archive, not a runtime input, and this module is
# reachable from kbs_capability_matrix.py, which many things import. Following
# vci_volume_composition.active_contract()'s own precedent (literal dimension_verdicts, not
# a file read), the reconciliation *results* -- verified against the retained raw artifacts
# below and reproducible from them by anyone who runs verify_against_retained_evidence() --
# are frozen here as data. The raw bytes stay retained, hashed, and re-verifiable; the
# module just does not require them to exist to answer a query.

EVIDENCE_DIR = Path(__file__).resolve().parent / "operations-review" / "kbs-trade-scope-qualification-20260809" / "raw"

#: Retrieved and reconciled 2026-08-09, one session (2026-08-07), from the raw artifacts
#: hashed in FROZEN_ARTIFACT_HASHES below. Reproduce with verify_against_retained_evidence().
FROZEN_RECONCILIATIONS: tuple[dict[str, Any], ...] = (
    {
        "ticker": "HPG", "trading_date": "07/08/2026", "tape_rows": 2751,
        "continuous_trade_count": 2749, "auction_trade_count": 2,
        "continuous_volume": 11630500, "auction_volume": 1387600, "tape_total": 13018100,
        "volume_accumulated": 13018100, "put_through_qty": 200000, "residual": 0,
        "tape_matches_accumulated_exactly": True, "put_through_demonstrated_excluded": True,
    },
    {
        "ticker": "VNM", "trading_date": "07/08/2026", "tape_rows": 4132,
        "continuous_trade_count": 4130, "auction_trade_count": 2,
        "continuous_volume": 12888200, "auction_volume": 351300, "tape_total": 13239500,
        "volume_accumulated": 13239500, "put_through_qty": 500000, "residual": 0,
        "tape_matches_accumulated_exactly": True, "put_through_demonstrated_excluded": True,
    },
    {
        "ticker": "VCB", "trading_date": "07/08/2026", "tape_rows": 2684,
        "continuous_trade_count": 2682, "auction_trade_count": 2,
        "continuous_volume": 6330800, "auction_volume": 191400, "tape_total": 6522200,
        "volume_accumulated": 6522200, "put_through_qty": 857000, "residual": 0,
        "tape_matches_accumulated_exactly": True, "put_through_demonstrated_excluded": True,
    },
)

#: SHA-256 of the four raw retained artifacts (price board batch + one intraday tape per
#: ticker), sorted. Matches operations-review/kbs-trade-scope-qualification-20260809/raw/.
FROZEN_ARTIFACT_HASHES: tuple[str, ...] = (
    "19e86c1c0eb76aca24eb73684af1177119cd59c213df0fb89266272bdf3d6475",
    "4ca608084c184bcd49b5acc8c675f382bb818a4370e5b9b79629eea7876a29a7",
    "92dbaa28f5eaa2786feccccba7e9a698613f1477e3caa8b8c5980397b7ccaaa9",
    "e7d03dd471469620966110a74b7a620bbdbb3a238dd3f32f36ff64e98ef4b337",
)


def active_contract() -> dict[str, Any]:
    """The canonical, active KBS trade-scope contract, assembled from the frozen,
    retained-evidence-verified reconciliation results. Consumers read this rather than
    re-deriving it or depending on the evidence archive at call time."""
    return assert_contract_fail_closed(
        trade_scope_contract(FROZEN_RECONCILIATIONS, raw_artifact_hashes=FROZEN_ARTIFACT_HASHES)
    )


# ---------------------------------------------------------------------------------
# Verification -- reproduces FROZEN_RECONCILIATIONS from the retained raw artifacts
# ---------------------------------------------------------------------------------


def _file_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_retained_reconciliations(
    evidence_dir: Path = EVIDENCE_DIR,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Rebuild the per-ticker reconciliations from the retained raw artifacts on disk, and
    the SHA-256 of every artifact read.

    Pure with respect to the network: reads only files already written by the bounded
    evidence-acquisition pass. Raises if a ticker's artifact is missing rather than
    silently reconciling a partial set. Used by tests and
    :func:`verify_against_retained_evidence` to prove :data:`FROZEN_RECONCILIATIONS` was
    not hand-edited; never called from :func:`active_contract`.
    """
    board_path = evidence_dir / "price_board_HPG_VNM_VCB.raw.json"
    if not board_path.exists():
        raise TradeScopeError(f"retained_price_board_evidence_missing:{board_path}")
    hashes = [_file_sha256(board_path)]
    with board_path.open(encoding="utf-8") as handle:
        board_raw = json.load(handle)

    reconciliations = []
    for ticker in TESTED_TICKERS:
        tape_path = evidence_dir / f"intraday_{ticker}.raw.json"
        if not tape_path.exists():
            raise TradeScopeError(f"retained_intraday_evidence_missing:{ticker}:{tape_path}")
        hashes.append(_file_sha256(tape_path))
        with tape_path.open(encoding="utf-8") as handle:
            tape_raw = json.load(handle)
        board = parse_price_board(board_raw, ticker=ticker)
        tape = parse_intraday_tape(tape_raw, ticker=ticker)
        assert_full_session_coverage(tape)
        reconciliations.append(reconcile_session(tape=tape, board=board))
    return reconciliations, sorted(hashes)


def verify_against_retained_evidence(evidence_dir: Path = EVIDENCE_DIR) -> bool:
    """Recompute reconciliations from the retained raw artifacts and check they match
    :data:`FROZEN_RECONCILIATIONS` and :data:`FROZEN_ARTIFACT_HASHES` exactly. Raises
    ``TradeScopeError`` if the evidence directory is missing; returns ``False`` (never
    silently ``True``) on any mismatch."""
    reconciliations, hashes = load_retained_reconciliations(evidence_dir)
    return (
        list(reconciliations) == list(FROZEN_RECONCILIATIONS)
        and tuple(hashes) == FROZEN_ARTIFACT_HASHES
    )
