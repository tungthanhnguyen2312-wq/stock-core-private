"""Deterministic backward pagination over the VCI intraday matched-trade tape.

Observed cursor semantics (measured 2026-08-04, recorded in the pilot report):

* ``truncTime`` is a **backward, strictly exclusive** cursor: the endpoint returns trades
  whose ``truncTime < cursor``, newest first. Measured, not assumed -- across the 71 page
  transitions of run 01, the newest returned trade was strictly older than the requested
  cursor **71 times and equal to it 0 times**.
* That exclusivity is a trap. Paging with ``cursor = oldest_trunc_time`` looks correct and
  produces zero duplicates, which looks like confirmation; in fact the 100-row cap
  truncates the oldest second mid-way and the rest of that second is then skipped forever.
  Run 01 lost 1,704,400 shares that way. The correct cursor is ``oldest_trunc_time + 1``,
  which re-delivers the boundary second whole and is then de-duplicated by trade id.
  **Zero duplicates is evidence of a gap here, not of cleanliness.**
* The page size is capped **server-side at 100 rows** regardless of the requested ``limit``.
* The tape holds **only the current session**. A cursor at the previous session's close
  returns zero rows, so a completed prior session is not reachable through this endpoint.
* ``accumulatedVolume`` on a row is cumulative **including** that row, so the session's
  first trade satisfies ``accumulatedVolume == matchVol`` -- a checkable start boundary.

Because the cursor is inclusive and several trades share one second, consecutive pages
overlap on the boundary second. Overlap is removed by provider trade ``id`` only. Two
genuinely distinct trades can share time, price and quantity, so value-based dedup would
silently delete real volume; :func:`dedupe` refuses to run without an id.

Every function here is pure. Acquisition stays in the runner.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

VERSION = "1.0.0"

#: Measured, not assumed: the endpoint returned 100 rows for a requested limit of 30,000.
OBSERVED_SERVER_ROW_CAP = 100

RECONCILIATION_VERDICTS = frozenset(
    {
        "complete_exact_match",
        "complete_unit_scaled_match",
        "complete_divergence",
        "incomplete_request_cap",
        "incomplete_cursor_failure",
        "incomplete_session_boundary_unknown",
    }
)

STOP_REASONS = frozenset(
    {
        "session_start_boundary_reached",
        "empty_page",
        "cursor_did_not_advance",
        "cursor_repeated",
        "request_cap_reached",
    }
)


class PaginationError(ValueError):
    """Fail-closed rejection inside the paginator."""


# ---------------------------------------------------------------------------------
# Request budget
# ---------------------------------------------------------------------------------


def compute_request_cap(
    *,
    expected_session_quantity: int | None,
    mean_trade_quantity: float | None,
    row_cap: int = OBSERVED_SERVER_ROW_CAP,
    safety_multiplier: float = 1.5,
    fixed_cap_when_unsupported: int = 60,
) -> dict[str, Any]:
    """Derive a conservative request cap **before** the first request.

    When repository evidence supports an estimate the cap is derived from it; otherwise a
    fixed safety cap applies. The cap is an input to the run and is never raised during it.
    """
    if row_cap < 1:
        raise PaginationError("row_cap_invalid")
    if not expected_session_quantity or not mean_trade_quantity or mean_trade_quantity <= 0:
        return {
            "cap": int(fixed_cap_when_unsupported),
            "basis": "fixed_safety_cap_no_supportable_estimate",
            "row_cap": row_cap,
        }
    estimated_trades = expected_session_quantity / mean_trade_quantity
    estimated_pages = estimated_trades / row_cap
    return {
        "cap": int(estimated_pages * safety_multiplier) + 20,
        "basis": "estimated_from_session_quantity_and_observed_mean_trade_size",
        "expected_session_quantity": int(expected_session_quantity),
        "mean_trade_quantity": round(float(mean_trade_quantity), 3),
        "estimated_trades": int(estimated_trades),
        "estimated_pages": int(estimated_pages),
        "safety_multiplier": safety_multiplier,
        "row_cap": row_cap,
    }


# ---------------------------------------------------------------------------------
# Cursor and page mechanics
# ---------------------------------------------------------------------------------


#: The endpoint filters ``truncTime < cursor``. Measured in run 01; see the module docstring.
CURSOR_BOUNDARY = "exclusive"


def oldest_trunc_time(rows: Sequence[Mapping[str, Any]]) -> int:
    """The oldest ``truncTime`` on this page."""
    if not rows:
        raise PaginationError("page_cursor_of_empty_page")
    return min(int(row["vci.raw_trunc_time"]) for row in rows)


def next_cursor(rows: Sequence[Mapping[str, Any]]) -> int:
    """The cursor that continues the scan without a gap.

    Because the filter is ``truncTime < cursor``, asking for ``oldest`` would exclude the
    boundary second entirely -- including the part of it the row cap cut off. Asking for
    ``oldest + 1`` yields ``truncTime <= oldest``, so the boundary second comes back whole
    and the overlap is removed by trade id instead of being wished away.
    """
    return oldest_trunc_time(rows) + 1


def page_hash(raw_body: bytes) -> str:
    return hashlib.sha256(bytes(raw_body)).hexdigest()


def assert_cursor_advances(previous: int | None, candidate: int, *, seen: Iterable[int]) -> None:
    """Enforce strict backward monotonicity and reject a repeated cursor.

    A page whose oldest trade is not older than the cursor that produced it means the
    boundary second holds at least a full page of trades. Requesting again would return
    the same page forever, so this is a stop condition, not something to retry around.
    """
    seen_set = set(seen)
    if previous is not None and candidate >= previous:
        raise PaginationError(f"cursor_did_not_advance:{previous}->{candidate}")
    if candidate in seen_set:
        raise PaginationError(f"cursor_repeated:{candidate}")


def dense_second_escape(rows: Sequence[Mapping[str, Any]]) -> int:
    """Cursor that steps past a second the page cap cannot enumerate.

    When a whole page falls inside one second, ``oldest + 1`` reproduces the same request
    forever. The only cursor the endpoint offers has one-second resolution, so the
    remainder of that second is unreachable and stepping to ``oldest`` skips it.

    This is not a silent skip. The accumulator carried on every row makes the omission
    exactly measurable afterwards (see :func:`enumeration_gaps`), so the scan reports how
    much volume it could not enumerate instead of pretending it enumerated everything.
    """
    return oldest_trunc_time(rows)


def page_is_single_second(rows: Sequence[Mapping[str, Any]]) -> bool:
    times = {int(row["vci.raw_trunc_time"]) for row in rows}
    return len(times) == 1


def enumeration_gaps(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Find, and exactly quantify, trades the scan did not retrieve.

    ``accumulatedVolume`` is cumulative including its own row, so for two consecutive
    retained trades the accumulator delta must equal the newer trade's quantity. Any excess
    is volume that traded between them and was not returned. This measures completeness
    against the provider's own counter rather than against an assumption about the tape.
    """
    ordered = sorted(
        (row for row in rows if row.get("vci.raw_accumulated_volume") is not None),
        key=lambda row: (float(row["vci.raw_accumulated_volume"]), int(row["vci.raw_trunc_time"])),
    )
    gaps: list[dict[str, Any]] = []
    for previous, current in zip(ordered, ordered[1:]):
        delta = float(current["vci.raw_accumulated_volume"]) - float(previous["vci.raw_accumulated_volume"])
        missing = delta - float(current["vci.observed_intraday_trade_quantity"])
        if missing > 0.5:
            gaps.append(
                {
                    "after_trade_id": str(previous["vci.raw_trade_id"]),
                    "before_trade_id": str(current["vci.raw_trade_id"]),
                    "trunc_time_span": [
                        int(previous["vci.raw_trunc_time"]),
                        int(current["vci.raw_trunc_time"]),
                    ],
                    "unenumerated_quantity": int(round(missing)),
                }
            )
    return {
        "gap_count": len(gaps),
        "unenumerated_quantity_total": int(sum(gap["unenumerated_quantity"] for gap in gaps)),
        "gaps": gaps,
    }


def session_start_reached(rows: Sequence[Mapping[str, Any]]) -> bool:
    """True when this page contains the session's first trade.

    The accumulator on a row includes that row, so on the first trade of the session it
    equals the trade's own quantity. That is a provider-side fact about the tape, not an
    assumption about when trading opened.
    """
    for row in rows:
        accumulated = row.get("vci.raw_accumulated_volume")
        if accumulated is None:
            continue
        if abs(float(accumulated) - float(row["vci.observed_intraday_trade_quantity"])) < 0.5:
            return True
    return False


# ---------------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------------

DEDUP_KEY_FIELDS = ("vci.raw_trade_id",)
DEDUP_KEY_DOCUMENTATION = (
    "provider trade id alone. Time, price and quantity are deliberately excluded: two "
    "distinct trades may agree on all three, and collapsing them would delete real volume."
)


def dedup_key(row: Mapping[str, Any]) -> str:
    identity = row.get("vci.raw_trade_id")
    if identity is None or str(identity).strip() == "" or str(identity).startswith("__index_"):
        raise PaginationError("dedup_requires_a_provider_trade_id")
    return str(identity)


def dedupe(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Collapse boundary overlap by trade id, preserving first-seen order."""
    unique: dict[str, Mapping[str, Any]] = {}
    duplicates = 0
    conflicting = 0
    for row in rows:
        key = dedup_key(row)
        if key in unique:
            duplicates += 1
            if unique[key] != row:
                conflicting += 1
            continue
        unique[key] = row
    return {
        "rows": list(unique.values()),
        "raw_rows": len(rows),
        "unique_rows": len(unique),
        "duplicate_boundary_rows": duplicates,
        "conflicting_duplicate_rows": conflicting,
        "dedup_key_fields": list(DEDUP_KEY_FIELDS),
        "dedup_key_documentation": DEDUP_KEY_DOCUMENTATION,
    }


# ---------------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------------


def reconcile_session(
    *,
    rows: Sequence[Mapping[str, Any]],
    daily_volume: int | None,
    stop_reason: str,
    session_start_confirmed: bool,
    covers_full_trading_day: bool,
    value_scale_to_vnd: int = 1_000_000,
) -> dict[str, Any]:
    """Reconcile a paginated tape segment against the daily volume field.

    ``covers_full_trading_day`` is supplied by the caller and never inferred here. A
    segment can be internally complete -- every trade from the session's first to the
    cutoff -- while still not spanning a whole trading day, and the two must not be
    conflated.
    """
    if stop_reason not in STOP_REASONS:
        raise PaginationError(f"stop_reason_unknown:{stop_reason}")
    if not rows:
        return {"verdict": "incomplete_session_boundary_unknown", "reason": "no_rows_retained"}

    ordered = sorted(rows, key=lambda row: (int(row["vci.raw_trunc_time"]), str(row["vci.raw_trade_id"])))
    quantities = [int(row["vci.observed_intraday_trade_quantity"]) for row in ordered]
    quantity_sum = sum(quantities)
    gaps = enumeration_gaps(ordered)

    accumulators = [
        float(row["vci.raw_accumulated_volume"])
        for row in ordered
        if row.get("vci.raw_accumulated_volume") is not None
    ]
    monotonic = all(later >= earlier for earlier, later in zip(accumulators, accumulators[1:]))
    final_accumulator = accumulators[-1] if accumulators else None
    max_accumulator = max(accumulators) if accumulators else None

    # Internal value identity: quantity x price must reproduce the accumulated-value delta
    # under exactly one scale. This checks the tape against itself, not against a source.
    # Pairs that straddle a measured gap are excluded: the delta there legitimately covers
    # trades that were never returned, so counting them as failures would report a defect
    # that is really the already-quantified cursor limit.
    gap_pairs = {(gap["after_trade_id"], gap["before_trade_id"]) for gap in gaps["gaps"]}
    value_checked = value_ok = value_skipped = 0
    with_value = [row for row in ordered if row.get("vci.raw_accumulated_value") is not None]
    for previous, current in zip(with_value, with_value[1:]):
        if (str(previous["vci.raw_trade_id"]), str(current["vci.raw_trade_id"])) in gap_pairs:
            value_skipped += 1
            continue
        delta = current["vci.raw_accumulated_value"] - previous["vci.raw_accumulated_value"]
        turnover = current["vci.observed_intraday_trade_quantity"] * current["vci.raw_match_price"]
        value_checked += 1
        if abs(delta * value_scale_to_vnd - turnover) <= max(1.0, turnover * 1e-6):
            value_ok += 1

    result = {
        "schema_version": VERSION,
        "stop_reason": stop_reason,
        "session_start_boundary_confirmed": bool(session_start_confirmed),
        "covers_full_trading_day": bool(covers_full_trading_day),
        "unique_rows": len(ordered),
        "earliest_trunc_time": int(ordered[0]["vci.raw_trunc_time"]),
        "latest_trunc_time": int(ordered[-1]["vci.raw_trunc_time"]),
        "trade_quantity_sum": quantity_sum,
        "final_accumulated_volume": final_accumulator,
        "max_accumulated_volume": max_accumulator,
        "accumulators_monotonic": monotonic,
        "daily_volume": daily_volume,
        "quantity_sum_minus_final_accumulator": (
            quantity_sum - int(final_accumulator) if final_accumulator is not None else None
        ),
        "daily_volume_minus_quantity_sum": (
            int(daily_volume) - quantity_sum if daily_volume is not None else None
        ),
        "value_identity_pairs_checked": value_checked,
        "value_identity_pairs_matching": value_ok,
        "value_scale_to_vnd": value_scale_to_vnd,
        "enumeration": {k: v for k, v in gaps.items() if k != "gaps"},
        "enumeration_gaps": gaps["gaps"][:50],
        "value_identity_pairs_skipped_at_gaps": value_skipped,
        "enumerated_plus_unenumerated": quantity_sum + gaps["unenumerated_quantity_total"],
        "trades_fully_enumerated": gaps["gap_count"] == 0,
    }

    # Reported separately from the enumeration verdict on purpose. Whether the numbers add
    # up is a different question from whether every trade was retrieved, and only the
    # second one is what "complete" means below.
    if daily_volume is not None:
        closure = quantity_sum + gaps["unenumerated_quantity_total"]
        result["accumulator_closure"] = {
            "enumerated_quantity": quantity_sum,
            "measured_unenumerated_quantity": gaps["unenumerated_quantity_total"],
            "total": closure,
            "daily_volume": int(daily_volume),
            "residual": closure - int(daily_volume),
            "closes_exactly": closure == int(daily_volume),
        }

    incomplete = {
        "request_cap_reached": "incomplete_request_cap",
        "cursor_did_not_advance": "incomplete_cursor_failure",
        "cursor_repeated": "incomplete_cursor_failure",
    }
    if stop_reason in incomplete:
        result["verdict"] = incomplete[stop_reason]
        return result
    if not session_start_confirmed:
        result["verdict"] = "incomplete_session_boundary_unknown"
        return result
    if daily_volume is None:
        result["verdict"] = "incomplete_session_boundary_unknown"
        result["reason"] = "no_daily_volume_to_reconcile_against"
        return result

    # A dense second the one-second cursor could not enumerate leaves the tape provably
    # short, however cleanly the scan otherwise ran. Reporting a match on the enumerated
    # subset would be a match against a quantity nobody asked about.
    if gaps["gap_count"]:
        result["verdict"] = "incomplete_cursor_failure"
        result["reason"] = "dense_seconds_exceed_the_one_second_cursor_resolution"
        return result

    if quantity_sum == int(daily_volume):
        result["verdict"] = "complete_exact_match"
    elif quantity_sum and int(daily_volume) % quantity_sum == 0:
        result["verdict"] = "complete_unit_scaled_match"
        result["implied_scale"] = int(daily_volume) // quantity_sum
    else:
        result["verdict"] = "complete_divergence"
    return result


# ---------------------------------------------------------------------------------
# The volume contract this pilot may write
# ---------------------------------------------------------------------------------

_MARKET_COMPOSITION_DIMENSIONS = (
    "matched_trade_inclusion",
    "negotiated_trade_inclusion",
    "auction_inclusion",
    "odd_lot_inclusion",
    "market_scope",
)


def volume_contract(
    *,
    reconciliation: Mapping[str, Any],
    unit_qualified: bool,
    field_identity_qualified: bool,
) -> dict[str, Any]:
    """Assemble the volume contract.

    A complete exact match qualifies **endpoint reconciliation** and nothing else. Market
    composition asks what the exchange counted, which no amount of internal agreement
    between two fields of the same provider can answer. Those dimensions can only be
    upgraded from direct field semantics, a first-party definition, or a separately
    identified endpoint whose relationship to this one is demonstrable -- none of which
    this pilot has, so they are hard-coded to ``unknown`` here rather than computed.
    """
    verdict = reconciliation.get("verdict")
    if verdict not in RECONCILIATION_VERDICTS:
        raise PaginationError(f"reconciliation_verdict_invalid:{verdict}")
    complete = verdict.startswith("complete_")
    contract = {
        "volume_field_identity": "qualified" if field_identity_qualified else "unknown",
        "volume_unit": "shares" if unit_qualified else "unknown",
        "endpoint_session_completeness": (
            "complete" if complete and reconciliation.get("covers_full_trading_day") else "incomplete"
        ),
        "endpoint_segment_completeness": "complete" if complete else "incomplete",
        "daily_to_intraday_reconciliation": {
            "complete_exact_match": "exact",
            "complete_unit_scaled_match": "scaled",
            "complete_divergence": "divergent",
        }.get(verdict, "unknown"),
        "corporate_action_adjustment": "unknown",
        "liquidity_actionable": False,
    }
    for dimension in _MARKET_COMPOSITION_DIMENSIONS:
        contract[dimension] = "unknown"
    contract["market_scope_upgrade_requires"] = [
        "direct_field_semantics_naming_the_included_trade_types",
        "first_party_source_definition",
        "a_separately_identified_endpoint_with_a_demonstrable_relationship",
    ]
    return contract


def assert_market_scope_not_upgraded(contract: Mapping[str, Any]) -> Mapping[str, Any]:
    """Refuse a contract in which reconciliation has leaked into market composition."""
    for dimension in _MARKET_COMPOSITION_DIMENSIONS:
        if contract.get(dimension) != "unknown":
            raise PaginationError(f"market_composition_dimension_must_stay_unknown:{dimension}")
    if contract.get("liquidity_actionable"):
        raise PaginationError("liquidity_actionable_must_stay_false")
    return contract


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
