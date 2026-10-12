"""Pure, offline analyses for PROSPECTIVE_RAW_PIT_AUTHORITY_V1 (no I/O, no clock reads, no provider calls).

* ``classify_bar_pair``      -- same ticker/session observed at two known times: identical, an
  adjustment-like consistent-ratio revision, or an inconsistent (non-proportional) revision.
* ``three_way_basis``        -- DNSE as known at T0, DNSE re-fetched at T1, and an official series:
  which of T0/T1 the official series matches. A series equal to T0 and different from a
  consistently re-based T1 is UNADJUSTED across that event; equal to T1 is ADJUSTED.
* ``event_authority_table``  -- what the retained official event evidence does and does not carry.
* ``reconstruct_daily_ohlc_from_trades`` -- Trades-derived OHLC candidate that FAILS CLOSED unless
  session completeness is proven (page-capped trade pages cannot prove it).

Every verdict is scoped to the tested provider/route/field/window and is never generalised.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping, Sequence

IDENTICAL = "IDENTICAL"
CONSISTENT_RATIO = "CONSISTENT_RATIO"
INCONSISTENT = "INCONSISTENT"
PRICE_EPSILON = 1e-6
#: Maximum spread between per-field ratios for a revision to count as one adjustment-like factor.
RATIO_SPREAD_TOLERANCE = 0.006

HOSE_EQ_T0_ONLY = "OFFICIAL_EQUALS_T0_NOT_T1"
HOSE_EQ_T1_ONLY = "OFFICIAL_EQUALS_T1_NOT_T0"
OFFICIAL_EQ_BOTH = "OFFICIAL_EQUALS_BOTH"
OFFICIAL_EQ_NEITHER = "OFFICIAL_EQUALS_NEITHER"

DNSE_TRADES_PAGE_CAP = 100  # observed retained page size; a page at the cap cannot prove completeness


def _bar(value: Sequence[float]) -> tuple[float, ...]:
    if len(value) < 4:
        raise ValueError("bar_requires_open_high_low_close")
    return tuple(float(x) for x in value[:4])


def bars_equal(a: Sequence[float], b: Sequence[float]) -> bool:
    return all(abs(x - y) < PRICE_EPSILON for x, y in zip(_bar(a), _bar(b)))


def classify_bar_pair(t0: Sequence[float], t1: Sequence[float]) -> str:
    """O/H/L/C tuples in one unit, same ticker/session, T0 retained before T1."""
    b0, b1 = _bar(t0), _bar(t1)
    if bars_equal(b0, b1):
        return IDENTICAL
    ratios = [y / x for x, y in zip(b0, b1) if x]
    if len(ratios) == 4 and max(ratios) - min(ratios) < RATIO_SPREAD_TOLERANCE:
        return CONSISTENT_RATIO
    return INCONSISTENT


def three_way_basis(official: Sequence[float], t0: Sequence[float], t1: Sequence[float]) -> str:
    e0, e1 = bars_equal(official, t0), bars_equal(official, t1)
    if e0 and e1:
        return OFFICIAL_EQ_BOTH
    if e0:
        return HOSE_EQ_T0_ONLY
    if e1:
        return HOSE_EQ_T1_ONLY
    return OFFICIAL_EQ_NEITHER


def event_window_ratio(pre_ex_official: float, pre_ex_rebased: float) -> float:
    """Observed re-basing factor between a re-fetched series and the unadjusted official series."""
    if pre_ex_official <= 0:
        raise ValueError("official_price_required")
    return pre_ex_rebased / pre_ex_official


def event_authority_table(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Coverage of the retained official event index by field; never infers a missing field."""
    rows = list(events)
    by_type: dict[str, dict[str, Any]] = {}
    for event in rows:
        cell = by_type.setdefault(event["event_type"], Counter())
        cell["events"] += 1
        cell["explicit_ex_date"] += bool(event.get("ex_date"))
        cell["record_date"] += bool(event.get("record_date"))
        cell["execution_or_payment_date"] += bool(event.get("execution_date"))
        cell["published_at"] += bool(event.get("published_at"))
        cell["ratio_or_cash_terms"] += any(event.get(k) is not None for k in ("stock_ratio", "cash_amount_per_share", "rights_ratio"))
        cell["price_share_affecting"] += event.get("materiality_status") == "PRICE_SHARE_AFFECTING"
    return {
        "events": len(rows),
        "by_event_type": {k: dict(sorted(v.items())) for k, v in sorted(by_type.items())},
        "explicit_ex_date": sum(bool(e.get("ex_date")) for e in rows),
        "ratio_or_cash_terms": sum(any(e.get(k) is not None for k in ("stock_ratio", "cash_amount_per_share", "rights_ratio")) for e in rows),
        "publication_time_retained": sum(bool(e.get("published_at")) for e in rows),
        "sources": dict(sorted(Counter(e.get("source") for e in rows).items())),
        "ex_date_inferred_from_record_date": 0,
        "planned_issuance_treated_as_executed": 0,
    }


def reconstruct_daily_ohlc_from_trades(trades: Sequence[Mapping[str, Any]], *, session: str,
                                       completeness_proof: Mapping[str, Any] | None,
                                       included_boards: Sequence[str] = ("G1",)) -> dict[str, Any]:
    """DERIVED_RAW_AS_TRADED_CANDIDATE for ordinary-lot matched trading (board G1 by default).

    Fails closed unless ``completeness_proof`` shows the session's trade pages are complete
    (``{"pages_complete": True, "http_failures": 0, "page_count": n}``) and no page is at the cap.
    The result is derived, never official, and grants no execution or backtest authority.
    """
    proof = completeness_proof or {}
    if not proof.get("pages_complete") or proof.get("http_failures"):
        return {"state": "FAIL_CLOSED", "reason_codes": ["SESSION_COMPLETENESS_NOT_PROVEN"], "ohlc": None}
    if any(int(size) >= DNSE_TRADES_PAGE_CAP for size in proof.get("page_sizes", [])) and not proof.get("cap_page_exhausted_proof"):
        return {"state": "FAIL_CLOSED", "reason_codes": ["PAGE_AT_CAP_TRUNCATION_NOT_EXCLUDED"], "ohlc": None}
    ticks = sorted((t for t in trades if t.get("boardId") in included_boards and t.get("time", "").startswith(session)),
                   key=lambda t: (t["time"], t.get("source_record_index", 0)))
    if not ticks:
        return {"state": "FAIL_CLOSED", "reason_codes": ["NO_INCLUDED_BOARD_TRADES"], "ohlc": None}
    prices = [float(t["matchPrice"]) for t in ticks]
    return {"state": "DERIVED_RAW_AS_TRADED_CANDIDATE", "reason_codes": [],
            "ohlc": {"open": prices[0], "high": max(prices), "low": min(prices), "close": prices[-1]},
            "trade_count": len(ticks), "included_boards": list(included_boards),
            "authority": "DERIVED_NOT_OFFICIAL",
            "unresolved_semantics": ["auction_and_post_close_inclusion_unverified", "odd_lot_and_put_through_excluded_by_board"]}
