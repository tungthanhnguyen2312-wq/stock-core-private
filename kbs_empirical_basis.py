"""Bounded empirical qualification of the KBS daily price and volume fields.

WHY THIS LANE REOPENED
    Phase 1C examined the KBS daily chart endpoint and found no ``adjustment_status``, no
    unit declaration and no trade-method metadata anywhere in the payload, the adapter or
    the provider's surfaces. That finding stands and is not revisited here. What is revised
    is the conclusion drawn from it -- that the fields were therefore unusable. Absence of
    documentation is a fact about the provider's publishing, not about the numbers.

    The fields already have identities the payload makes plain: ``t`` time, ``o/h/l/c`` the
    session's open, high, low and close, ``v`` a volume, ``va`` a traded amount. What is
    missing is their *basis* -- adjusted or as-traded, shares or lots, VND or thousands,
    matched-only or matched-plus-negotiated. This module tests what can be tested and
    leaves the rest closed.

THE THREE DIMENSIONS THAT MUST NOT MERGE
    ``field_identity``  -- what the number is a number *of*. Known from the payload.
    ``basis``           -- what economic transformation stands behind it. Tested here.
    ``market_scope``    -- which trades the exchange counted into it. Not testable from
                           any KBS surface reachable in this environment, and therefore
                           left ``unknown`` with liquidity fail-closed.

    Every function below belongs to exactly one of them, and none of them upgrades another.
    In particular: qualifying the volume *unit* says how much, never what kind, and price
    adjustment says nothing at all about volume adjustment.

SCOPE DISCIPLINE
    One provider, three tickers, explicit small windows, at most six live requests. Raw
    bytes are preserved verbatim; normalisation is a separate step whose every
    transformation is recorded as data. Nothing here writes a production database, bundle
    or dashboard artifact, and no verdict this module can emit raises ``is_actionable``.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import evidence_qualification_tiers as tiers

# The HOSE order-price step. An exchange trading rule, not a provider claim, and the same
# rule the VCI lane used -- reused rather than restated so the two lanes cannot drift into
# disagreeing about what the exchange permits. Importing a pure arithmetic function is not
# a VCI probe and touches no VCI surface.
from vci_direct_basis_pilot import hose_tick_size, on_tick_lattice  # noqa: F401

VERSION = "1.0.0"

PROVIDER = "KBS"

#: An endpoint observed in the provider's own web trading application and exercised by the
#: established ``vnstock`` adapter path this repository already runs as its OHLCV failover.
#: It carries no first-party developer documentation, no published schema and no semantic
#: declaration, so no verdict derived from it may be promoted to an official-exchange claim.
SOURCE_AUTHORITY = "observed_public_web_endpoint"

PROVIDER_HOST = "kbbuddywts.kbsec.com.vn"
IIS_BASE_URL = "https://kbbuddywts.kbsec.com.vn/iis-server/investment"
DAILY_ENDPOINT_TEMPLATE = IIS_BASE_URL + "/stocks/{symbol}/data_day"
DAILY_RESPONSE_KEY = "data_day"

ALLOWED_TICKERS = ("HPG", "VNM", "VCB")

#: Hard ceiling for the whole milestone. Exhausting it stops acquisition; it is never reset.
REQUEST_BUDGET = 6

#: The window a single request may span. Small windows only -- no broad history.
MAX_WINDOW_DAYS = 45

SENSITIVE_HEADER_NAMES = frozenset(
    {
        "cookie",
        "set-cookie",
        "authorization",
        "proxy-authorization",
        "x-api-key",
        "api-key",
        "x-auth-token",
        "token",
    }
)

REDACTED = "[REDACTED]"


class KBSBasisError(ValueError):
    """Fail-closed rejection inside the KBS empirical-basis harness."""


# ---------------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------------

PRICE_BASIS_VERDICTS = frozenset(
    {
        "raw_as_traded_empirically_supported",
        "empirically_event_adjusted",
        "cash_distribution_adjusted_observed",
        "share_event_adjusted_observed",
        "mixed_or_context_dependent",
        "inconclusive",
        "conflicted",
    }
)

HISTORICAL_MUTABILITY_VERDICTS = frozenset(
    {"retrospectively_rewritten", "not_observed", "unknown"}
)

VOLUME_UNIT_VERDICTS = frozenset({"shares", "board_lots", "scaled_units", "inconclusive"})

TRADING_VALUE_UNIT_VERDICTS = frozenset(
    {"VND", "thousand_VND", "million_VND", "scaled_units", "inconclusive"}
)

VOLUME_ADJUSTMENT_VERDICTS = frozenset(
    {
        "unadjusted_volume_empirically_supported",
        "share_event_adjusted_volume_observed",
        "retrospectively_rewritten_unknown_method",
        "not_observed",
        "unknown",
    }
)

#: Market composition, kept as an independent axis with its own evidence requirements.
MARKET_SCOPE_DIMENSIONS = (
    "continuous_matching_inclusion",
    "opening_auction_inclusion",
    "closing_auction_inclusion",
    "negotiated_trade_inclusion",
    "odd_lot_inclusion",
    "total_exchange_volume_equivalence",
)

#: Generic namespaces this milestone must never populate. A KBS finding is a KBS finding.
FORBIDDEN_GENERIC_FIELDS = frozenset(
    {
        "official_close",
        "official_adjusted_close",
        "official_exchange_volume",
        "official_exchange_price",
        "canonical_market_volume",
        "adjusted_close",
        "adjustment_factor",
        "price_basis",
        "volume_basis",
        "is_actionable",
        "liquidity_actionable",
        "total_shareholder_return",
    }
)


# ---------------------------------------------------------------------------------
# Boundary enforcement
# ---------------------------------------------------------------------------------


def assert_ticker_in_scope(symbol: str) -> str:
    upper = str(symbol).strip().upper()
    if upper not in ALLOWED_TICKERS:
        raise KBSBasisError(f"ticker_out_of_milestone_scope:{upper}")
    return upper


def daily_endpoint(symbol: str) -> str:
    """The one endpoint this milestone may request, for one in-scope ticker."""
    return DAILY_ENDPOINT_TEMPLATE.format(symbol=assert_ticker_in_scope(symbol))


def assert_endpoint_in_scope(url: str) -> str:
    for symbol in ALLOWED_TICKERS:
        if url == DAILY_ENDPOINT_TEMPLATE.format(symbol=symbol):
            return url
    raise KBSBasisError(f"endpoint_out_of_milestone_scope:{url}")


def assert_redirect_within_boundary(location: str | None) -> None:
    """A redirect off the provider host is not the provider answering."""
    if location is None:
        return
    match = re.match(r"^https?://([^/:?#]+)", str(location).strip(), re.IGNORECASE)
    if match is None:
        return
    host = match.group(1).lower()
    if host != PROVIDER_HOST:
        raise KBSBasisError(f"redirect_outside_provider_boundary:{host}")


def redact_headers(headers: Mapping[str, Any] | None) -> dict[str, str]:
    if not headers:
        return {}
    return {
        str(name): (REDACTED if str(name).strip().lower() in SENSITIVE_HEADER_NAMES else str(value))
        for name, value in headers.items()
    }


def daily_params(*, start: str, end: str) -> dict[str, str]:
    """The adapter's own query contract: ``sdate``/``edate`` as ``DD-MM-YYYY``.

    The window is bounded here rather than at the call site so a broad-history request is
    impossible to express, not merely discouraged.
    """
    first = datetime.strptime(start, "%Y-%m-%d").date()
    last = datetime.strptime(end, "%Y-%m-%d").date()
    if last < first:
        raise KBSBasisError("daily_window_end_before_start")
    span = (last - first).days
    if span > MAX_WINDOW_DAYS:
        raise KBSBasisError(f"daily_window_too_wide:{span}d>{MAX_WINDOW_DAYS}d")
    return {"sdate": first.strftime("%d-%m-%Y"), "edate": last.strftime("%d-%m-%Y")}


# ---------------------------------------------------------------------------------
# Response identity
# ---------------------------------------------------------------------------------


def response_sha256(raw_body: bytes) -> str:
    if not isinstance(raw_body, (bytes, bytearray)):
        raise KBSBasisError("raw_body_must_be_bytes")
    return hashlib.sha256(bytes(raw_body)).hexdigest()


def schema_fingerprint(obj: Any) -> str:
    """Structure-only fingerprint: key names and value kinds, never values."""

    def shape(node: Any) -> Any:
        if isinstance(node, Mapping):
            return {str(key): shape(node[key]) for key in sorted(node, key=str)}
        if isinstance(node, (list, tuple)):
            kinds = {json.dumps(shape(item), sort_keys=True) for item in node}
            return ["|".join(sorted(kinds))] if kinds else []
        if isinstance(node, bool):
            return "bool"
        if isinstance(node, (int, float)):
            return "number"
        if node is None:
            return "null"
        return "str"

    canonical = json.dumps(shape(obj), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def artifact_name(symbol: str, *, retrieved_at: str, body_sha256: str) -> str:
    """Deterministic artifact name carrying the retrieval instant.

    A later, differing observation of the same window is stored *beside* the earlier one
    rather than replacing it -- which is the only reason a historical-rewrite test is
    possible at all.
    """
    symbol = assert_ticker_in_scope(symbol)
    stamp = re.sub(r"[^0-9TZ]", "", str(retrieved_at).upper())
    if not stamp:
        raise KBSBasisError("retrieved_at_unusable_for_artifact_name")
    return f"kbs_daily_{symbol}_{stamp}_{body_sha256[:16]}.raw.json"


# ---------------------------------------------------------------------------------
# Raw payload parsing -- fail closed, no repair
# ---------------------------------------------------------------------------------

#: The provider's own field names, and what each one is a number of. Identity only: none of
#: these entries claims a basis, a unit or a market scope.
RAW_FIELD_IDENTITY: dict[str, str] = {
    "t": "session timestamp label",
    "o": "session open price",
    "h": "session high price",
    "l": "session low price",
    "c": "session close price",
    "v": "session volume count",
    "va": "session traded amount",
}

_PRICE_FIELDS = ("o", "h", "l", "c")
_DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def _session_date(label: Any) -> str:
    """Read the calendar date off the provider's ``t`` label.

    Observed in two shapes across retrievals -- ``2026-07-20`` and ``2026-07-30 07:00`` --
    so only the leading date is taken. The trailing clock component is *not* interpreted as
    an instant: these are daily bars, and reading ``07:00`` as a session time would be
    inventing a semantic the provider never stated.
    """
    match = _DATE_PREFIX.match(str(label).strip())
    if match is None:
        raise KBSBasisError(f"session_label_unparseable:{label!r}")
    return match.group(1)


def unwrap_daily_payload(payload: Any) -> list[Any]:
    """Accept either the enveloped response or a retained bare array of rows."""
    if isinstance(payload, Mapping):
        rows = payload.get(DAILY_RESPONSE_KEY)
        if rows is None:
            raise KBSBasisError(f"daily_payload_missing_key:{DAILY_RESPONSE_KEY}")
        payload = rows
    if not isinstance(payload, list):
        raise KBSBasisError("daily_payload_not_a_list")
    return payload


def parse_daily_payload(payload: Any, *, symbol: str) -> list[dict[str, Any]]:
    """Parse the raw daily payload into per-session raw rows, or fail closed.

    Rows are keyed under a ``kbs.raw_`` namespace using the provider's own field names. No
    scaling, no rounding, no gap filling, no resampling and no repair happens here -- in
    particular the ``/1000`` the ``vnstock`` adapter applies to prices is *not* applied,
    because this module qualifies the provider's numbers and not the adapter's.
    """
    symbol = assert_ticker_in_scope(symbol)
    rows_in = unwrap_daily_payload(payload)
    if not rows_in:
        raise KBSBasisError("daily_payload_zero_sessions")

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(rows_in):
        if not isinstance(item, Mapping):
            raise KBSBasisError(f"daily_row_not_an_object:index={index}")
        missing = [field for field in ("t",) + _PRICE_FIELDS if field not in item]
        if missing:
            raise KBSBasisError(f"daily_row_missing_fields:{','.join(missing)}@index={index}")
        session = _session_date(item["t"])
        if session in seen:
            raise KBSBasisError(f"daily_payload_duplicate_session:{session}")
        seen.add(session)

        prices: dict[str, float] = {}
        for field in _PRICE_FIELDS:
            value = item[field]
            if value is None or (isinstance(value, float) and value != value):
                raise KBSBasisError(f"daily_row_missing_price:{field}@{session}")
            try:
                prices[field] = float(value)
            except (TypeError, ValueError) as exc:
                raise KBSBasisError(f"daily_row_price_unparseable:{field}@{session}") from exc
        if prices["l"] > min(prices["o"], prices["c"]) or prices["h"] < max(prices["o"], prices["c"]):
            raise KBSBasisError(f"daily_row_ohlc_inconsistent:{session}")

        # A missing v or va stays missing. Zero is a meaningful observation -- a session
        # with no trading -- and None is not, so the two are never merged.
        row: dict[str, Any] = {
            "kbs.raw_t": str(item["t"]),
            "kbs.session_date": session,
            "kbs.raw_o": prices["o"],
            "kbs.raw_h": prices["h"],
            "kbs.raw_l": prices["l"],
            "kbs.raw_c": prices["c"],
            "kbs.raw_v": _optional_number(item.get("v"), field="v", session=session),
            "kbs.raw_va": _optional_number(item.get("va"), field="va", session=session),
        }
        rows.append(row)
    rows.sort(key=lambda row: row["kbs.session_date"])
    return rows


def _optional_number(value: Any, *, field: str, session: str) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise KBSBasisError(f"daily_row_{field}_unparseable:@{session}") from exc
    if number != number:  # NaN
        return None
    if number < 0:
        raise KBSBasisError(f"daily_row_{field}_negative:@{session}")
    return number


# ---------------------------------------------------------------------------------
# Normalisation -- separate from raw, every transformation recorded
# ---------------------------------------------------------------------------------

TRANSFORMATION_CODE_IDENTITY = f"kbs_empirical_basis.normalize_daily/{VERSION}"

#: What the production adapter does to the same payload, recorded so the repository's own
#: normalisation is never mistaken for a provider semantic. ``vnstock`` divides prices by
#: 1000 for stock assets, rounds to two decimals, casts volume to int64 and -- in the
#: installed 4.0.4 -- drops ``va`` entirely unless ``get_all=True``, in which case it
#: survives under its own raw name rather than as ``value``.
ADAPTER_TRANSFORMATIONS: tuple[dict[str, Any], ...] = (
    {
        "stage": "vnstock.explorer.kbs.quote.Quote.history",
        "source_field": "o|h|l|c",
        "target_field": "open|high|low|close",
        "operation": "divide_then_round",
        "parameters": {"divisor": 1000, "decimals": 2, "applies_to_asset_types": "stock, ETF"},
        "provider_declared": False,
    },
    {
        "stage": "vnstock.explorer.kbs.quote.Quote.history",
        "source_field": "v",
        "target_field": "volume",
        "operation": "cast",
        "parameters": {"dtype": "int64"},
        "provider_declared": False,
    },
    {
        "stage": "vnstock.explorer.kbs.quote.Quote.history",
        "source_field": "va",
        "target_field": None,
        "operation": "drop",
        "parameters": {"retained_when": "get_all=True", "retained_as": "va"},
        "provider_declared": False,
    },
    {
        "stage": "vn_stock_pipeline.normalize",
        "source_field": "open|high|low|close",
        "target_field": "ohlcv.open|high|low|close",
        "operation": "scale",
        "parameters": {"factor": 1000, "source_scales": {"KBS": 1000}},
        "provider_declared": False,
        "note": "Undoes the adapter's division, returning VND. The round trip is lossy at "
        "the second decimal; it is recorded because it is a repository transformation.",
    },
)


def normalize_daily(raw_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Derive normalised rows from raw rows, recording each transformation explicitly.

    Two transformations are applied and both are declared: the ``t`` label becomes a
    session date, and price fields pass through at identity scale. The payload states VND
    in four- to five-digit integers, so there is nothing to convert -- and this module does
    not guess a unit it cannot observe.
    """
    if not raw_rows:
        raise KBSBasisError("normalize_daily_received_no_rows")

    transformations = [
        {
            "source_field": "kbs.raw_t",
            "target_field": "kbs.session_date",
            "operation": "leading_calendar_date_of_label",
            "parameters": {"observed_label_shapes": ["YYYY-MM-DD", "YYYY-MM-DD HH:MM"]},
            "note": "The clock component is discarded, not interpreted. These are daily bars.",
        },
        {
            "source_field": "kbs.raw_o|h|l|c",
            "target_field": "kbs.observed_open|high|low|close_vnd",
            "operation": "scale",
            "parameters": {"factor": 1, "rounding": "none"},
            "note": "identity scale; the harness refuses to guess a unit it cannot observe",
        },
        {
            "source_field": "kbs.raw_v",
            "target_field": "kbs.observed_daily_volume",
            "operation": "passthrough",
            "parameters": {"missing_policy": "preserve_null", "zero_fill": False},
        },
        {
            "source_field": "kbs.raw_va",
            "target_field": "kbs.observed_daily_trading_value",
            "operation": "passthrough",
            "parameters": {"missing_policy": "preserve_null", "zero_fill": False},
        },
    ]

    normalized = [
        {
            "kbs.session_date": row["kbs.session_date"],
            "kbs.observed_open_vnd": float(row["kbs.raw_o"]),
            "kbs.observed_high_vnd": float(row["kbs.raw_h"]),
            "kbs.observed_low_vnd": float(row["kbs.raw_l"]),
            "kbs.observed_close_vnd": float(row["kbs.raw_c"]),
            "kbs.observed_daily_volume": row["kbs.raw_v"],
            "kbs.observed_daily_trading_value": row["kbs.raw_va"],
        }
        for row in raw_rows
    ]

    dates = [row["kbs.session_date"] for row in normalized]
    if len(set(dates)) != len(dates):
        raise KBSBasisError("normalize_daily_duplicate_session_dates")
    if dates != sorted(dates):
        raise KBSBasisError("normalize_daily_sessions_out_of_order")

    return {
        "schema_version": VERSION,
        "transformation_code_identity": TRANSFORMATION_CODE_IDENTITY,
        "transformations": transformations,
        "adapter_transformations": [dict(t) for t in ADAPTER_TRANSFORMATIONS],
        "rows": normalized,
        "returned_date_range": [dates[0], dates[-1]],
        "resampling_applied": False,
        "forward_fill_applied": False,
        "invented_sessions": 0,
    }


# ---------------------------------------------------------------------------------
# Price basis -- the quotation lattice
# ---------------------------------------------------------------------------------

_LATTICE_FIELDS = (
    "kbs.observed_open_vnd",
    "kbs.observed_high_vnd",
    "kbs.observed_low_vnd",
    "kbs.observed_close_vnd",
)


def lattice_profile(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per-session HOSE tick-lattice conformance for the four price fields.

    A HOSE order can only match at a tick multiple, so a session carrying an off-lattice
    price was not quoted as displayed. That is an exclusion, and a strong one: it does not
    depend on knowing anything the provider declines to publish.
    """
    if not rows:
        raise KBSBasisError("lattice_profile_received_no_rows")
    sessions = []
    for row in rows:
        offenders = [
            field for field in _LATTICE_FIELDS if not on_tick_lattice(float(row[field]))
        ]
        sessions.append(
            {
                "session_date": row["kbs.session_date"],
                "all_fields_on_lattice": not offenders,
                "off_lattice_fields": offenders,
            }
        )
    on_lattice = sum(1 for item in sessions if item["all_fields_on_lattice"])
    return {
        "sessions": sessions,
        "sessions_total": len(sessions),
        "sessions_on_lattice": on_lattice,
        "sessions_off_lattice": len(sessions) - on_lattice,
    }


def lattice_boundary(rows: Sequence[Mapping[str, Any]]) -> str | None:
    """First session of the maximal fully-on-lattice trailing run, or ``None``.

    ``None`` when every session conforms or none of the trailing ones do -- either way the
    transition is not inside this window, and a boundary that is not observed is not
    reported.
    """
    profile = lattice_profile(rows)["sessions"]
    index = len(profile)
    while index > 0 and profile[index - 1]["all_fields_on_lattice"]:
        index -= 1
    if index == 0 or index == len(profile):
        return None
    return profile[index]["session_date"]


def trading_value_presence_profile(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Whether ``va`` is present, against whether the session is on the tick lattice.

    A second signal from a different field, and an independent one: nothing in the lattice
    test looks at ``va``, and nothing about ``va``'s presence looks at price values. When
    the two agree session for session, the two most obvious alternative explanations for
    the lattice result -- coincidental rounding, and an unrecorded event -- have to explain
    a field's *absence* as well, which neither does.

    It also disposes of the retention hypothesis: if ``va`` were simply dropped for older
    data, its presence would track the calendar. Comparing windows tells you whether it
    tracks the calendar or the boundary.
    """
    if not rows:
        raise KBSBasisError("trading_value_presence_profile_received_no_rows")
    sessions = []
    for row in rows:
        sessions.append(
            {
                "session_date": row["kbs.session_date"],
                "trading_value_present": row.get("kbs.observed_daily_trading_value") is not None,
                "all_price_fields_on_lattice": all(
                    on_tick_lattice(float(row[field])) for field in _LATTICE_FIELDS
                ),
            }
        )
    agree = sum(
        1
        for item in sessions
        if item["trading_value_present"] == item["all_price_fields_on_lattice"]
    )
    return {
        "sessions": sessions,
        "sessions_total": len(sessions),
        "sessions_with_trading_value": sum(1 for item in sessions if item["trading_value_present"]),
        "sessions_where_presence_agrees_with_lattice": agree,
        "presence_tracks_lattice_exactly": agree == len(sessions),
        "note": (
            "Correlation only. It says the provider treats these sessions differently; it "
            "does not say why, and it is not a provider statement about either field."
        ),
    }


# ---------------------------------------------------------------------------------
# Price basis -- classification
# ---------------------------------------------------------------------------------

EVENT_KIND_CASH = "cash_distribution"
EVENT_KIND_SHARE = "share_related_event"
EVENT_KINDS = frozenset({EVENT_KIND_CASH, EVENT_KIND_SHARE})


def assert_qualified_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """An event is an *input*, never inferred from price behaviour.

    It must name its retained evidence identity, so a reader can go back to the record that
    put the date in the repository rather than to the price series that was supposed to be
    explained by it.
    """
    if event.get("kind") not in EVENT_KINDS:
        raise KBSBasisError(f"qualified_event_kind_unknown:{event.get('kind')}")
    if not str(event.get("ex_date", "")).strip():
        raise KBSBasisError("qualified_event_missing_ex_date")
    if not str(event.get("evidence_identity", "")).strip():
        raise KBSBasisError("qualified_event_missing_evidence_identity")
    return dict(event)


def classify_price_basis(
    *,
    lattice: Mapping[str, Any],
    boundary_date: str | None,
    qualified_events: Sequence[Mapping[str, Any]],
    window_contains_event: bool,
) -> dict[str, Any]:
    """Qualify KBS ``o/h/l/c`` for one window from lattice evidence plus qualified events.

    Three outcomes matter and they are deliberately asymmetric:

    * Every session on the lattice **through a qualified ex-date** is affirmative evidence
      for an as-traded series: an adjusted series would have had to move the pre-event
      prices, and a moved price lands off the lattice except by coincidence. This is the
      only route to ``raw_as_traded_empirically_supported``, and it still needs the
      historical-rewrite test before eligibility follows -- see :func:`price_basis_contract`.
    * An off-lattice prefix terminating exactly at a qualified ex-date is evidence of an
      event adjustment, and the *dimension* is read off the event kinds at that boundary.
    * A fully on-lattice window with no event in it says nothing. An unadjusted series and
      an adjusted series with nothing to adjust for are the same series.
    """
    for event in qualified_events:
        assert_qualified_event(event)

    if lattice["sessions_off_lattice"] == 0:
        if not window_contains_event:
            return {
                "verdict": "inconclusive",
                "reason": "no_qualified_event_inside_a_fully_on_lattice_window",
                "excludes_raw_as_traded": False,
                "supports_raw_as_traded": False,
                "boundary_date": None,
                "matched_events": [],
                "note": (
                    "A control window cannot distinguish an unadjusted series from an "
                    "adjusted one with no event to adjust for."
                ),
            }
        return {
            "verdict": "raw_as_traded_empirically_supported",
            "reason": "every_session_on_lattice_across_a_qualified_ex_date",
            "excludes_raw_as_traded": False,
            "supports_raw_as_traded": True,
            "boundary_date": None,
            "matched_events": [dict(event) for event in qualified_events],
            "note": (
                "Pre-event sessions were not moved. Compatible with an as-traded series; "
                "it does not by itself establish that the whole history is immutable."
            ),
        }

    if boundary_date is None:
        return {
            "verdict": "inconclusive",
            "reason": "adjustment_boundary_lies_outside_the_observed_window",
            "excludes_raw_as_traded": True,
            "supports_raw_as_traded": False,
            "boundary_date": None,
            "matched_events": [],
        }

    matched = [
        dict(event) for event in qualified_events if str(event.get("ex_date")) == str(boundary_date)
    ]
    if not matched:
        return {
            "verdict": "mixed_or_context_dependent",
            "reason": "lattice_boundary_matches_no_qualified_event",
            "excludes_raw_as_traded": True,
            "supports_raw_as_traded": False,
            "boundary_date": boundary_date,
            "matched_events": [],
        }

    kinds = {event["kind"] for event in matched}
    if kinds == {EVENT_KIND_CASH}:
        verdict = "cash_distribution_adjusted_observed"
    elif kinds == {EVENT_KIND_SHARE}:
        verdict = "share_event_adjusted_observed"
    else:
        verdict = "empirically_event_adjusted"
    return {
        "verdict": verdict,
        "reason": "off_lattice_prefix_terminates_exactly_at_a_qualified_ex_date",
        "excludes_raw_as_traded": True,
        "supports_raw_as_traded": False,
        "boundary_date": boundary_date,
        "matched_events": matched,
    }


def merge_price_verdicts(per_window: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Combine per-window verdicts into one provider-level verdict, conservatively.

    Windows that exclude an as-traded series and windows that support one are a genuine
    contradiction about the same provider, so the result is ``conflicted`` -- never a
    majority vote and never the most recent window.
    """
    verdicts = {str(result["verdict"]) for result in per_window.values()}
    unknown = verdicts - PRICE_BASIS_VERDICTS
    if unknown:
        raise KBSBasisError(f"price_basis_verdict_not_in_vocabulary:{sorted(unknown)}")

    excludes = any(result.get("excludes_raw_as_traded") for result in per_window.values())
    supports = any(result.get("supports_raw_as_traded") for result in per_window.values())
    dimensions = sorted(
        {
            event["kind"]
            for result in per_window.values()
            for event in result.get("matched_events", [])
            if result.get("excludes_raw_as_traded")
        }
    )

    if excludes and supports:
        return {
            "verdict": "conflicted",
            "observed_adjustment_dimensions": dimensions,
            "reason": "one_window_excludes_an_as_traded_series_and_another_supports_one",
            "note": "Recency does not resolve this; a justified supersession would.",
        }
    if supports:
        return {
            "verdict": "raw_as_traded_empirically_supported",
            "observed_adjustment_dimensions": [],
            "reason": "every_decisive_window_kept_pre_event_prices_on_the_lattice",
        }
    decisive = verdicts - {"inconclusive"}
    if not decisive:
        return {"verdict": "inconclusive", "observed_adjustment_dimensions": [], "reason": "no_decisive_window"}
    if decisive == {"cash_distribution_adjusted_observed"}:
        return {"verdict": "cash_distribution_adjusted_observed", "observed_adjustment_dimensions": dimensions,
                "reason": "only_cash_distribution_boundaries_were_decisive"}
    if decisive == {"share_event_adjusted_observed"}:
        return {"verdict": "share_event_adjusted_observed", "observed_adjustment_dimensions": dimensions,
                "reason": "only_share_event_boundaries_were_decisive"}
    if decisive <= {
        "cash_distribution_adjusted_observed",
        "share_event_adjusted_observed",
        "empirically_event_adjusted",
    }:
        # Distinct windows demonstrating distinct dimensions is joint evidence about one
        # provider-wide treatment, not a conflict.
        return {"verdict": "empirically_event_adjusted", "observed_adjustment_dimensions": dimensions,
                "reason": "distinct_windows_demonstrated_distinct_adjustment_dimensions"}
    return {"verdict": "mixed_or_context_dependent", "observed_adjustment_dimensions": dimensions,
            "reason": "decisive_windows_did_not_agree_on_a_single_treatment"}


# ---------------------------------------------------------------------------------
# Historical mutability
# ---------------------------------------------------------------------------------


def historical_rewrite_test(
    *,
    prior_rows: Sequence[Mapping[str, Any]],
    current_rows: Sequence[Mapping[str, Any]],
    prior_observed_at: str,
    current_observed_at: str,
    prior_artifact: str,
) -> dict[str, Any]:
    """Compare the same historical sessions across two retrieval instants.

    This is the strongest evidence available to the milestone, because it does not require
    interpreting a value at all -- it asks only whether the provider returned a different
    number for a date that had already closed. ``not_observed`` on a window with no event
    in it is a control result, not an immutability proof: see :func:`price_basis_contract`.
    """
    prior = {row["kbs.session_date"]: row for row in prior_rows}
    current = {row["kbs.session_date"]: row for row in current_rows}
    shared = sorted(set(prior) & set(current))
    if not shared:
        return {
            "verdict": "unknown",
            "reason": "no_overlapping_sessions_between_the_two_observations",
            "sessions_compared": 0,
        }

    detail = []
    for session in shared:
        before, after = prior[session], current[session]
        changed_close = float(before["kbs.observed_close_vnd"]) != float(after["kbs.observed_close_vnd"])
        changed_volume = before["kbs.observed_daily_volume"] != after["kbs.observed_daily_volume"]
        changed_value = before.get("kbs.observed_daily_trading_value") != after.get(
            "kbs.observed_daily_trading_value"
        )
        if changed_close or changed_volume or changed_value:
            detail.append(
                {
                    "session_date": session,
                    "prior_close_vnd": before["kbs.observed_close_vnd"],
                    "current_close_vnd": after["kbs.observed_close_vnd"],
                    "prior_volume": before["kbs.observed_daily_volume"],
                    "current_volume": after["kbs.observed_daily_volume"],
                    "prior_trading_value": before.get("kbs.observed_daily_trading_value"),
                    "current_trading_value": after.get("kbs.observed_daily_trading_value"),
                    "close_changed": changed_close,
                    "volume_changed": changed_volume,
                    "trading_value_changed": changed_value,
                }
            )
    return {
        "verdict": "retrospectively_rewritten" if detail else "not_observed",
        "sessions_compared": len(shared),
        "sessions_with_changed_close": sum(1 for item in detail if item["close_changed"]),
        "sessions_with_changed_volume": sum(1 for item in detail if item["volume_changed"]),
        "sessions_with_changed_trading_value": sum(1 for item in detail if item["trading_value_changed"]),
        "changed_detail": detail,
        "prior_observation": prior_artifact,
        "prior_observed_at": prior_observed_at,
        "current_observed_at": current_observed_at,
    }


# ---------------------------------------------------------------------------------
# Volume and trading value -- the unit relationship
# ---------------------------------------------------------------------------------

#: The bounded candidate space. Both axes are powers of ten because every plausible
#: alternative -- shares against board lots, VND against thousands or millions -- is one.
VOLUME_SCALES = (1, 10, 100, 1_000)
TRADING_VALUE_SCALES = (1, 1_000, 1_000_000, 1_000_000_000)

#: A session VWAP must lie inside that session's own range if OHLC and value describe the
#: same trades. The tolerance absorbs the provider's rounding, nothing more; it is far
#: tighter than the factor-of-ten gaps between competing candidates, so it cannot let two
#: candidates pass together.
VWAP_TOLERANCE_VND = 1.0


def implied_average_price(
    *, raw_v: float, raw_va: float, volume_scale: int, trading_value_scale: int
) -> float | None:
    """``scaled_va / scaled_v`` for one candidate pair, or ``None`` when undefined."""
    denominator = raw_v * volume_scale
    if denominator <= 0:
        return None
    return (raw_va * trading_value_scale) / denominator


def row_is_eligible(row: Mapping[str, Any]) -> bool:
    """Whether a row can say anything about units at all.

    A missing ``v`` or ``va`` is not a zero and a zero is not a missing value; neither
    carries unit information, and both are set aside rather than counted as failures. This
    matters more for KBS than it would elsewhere, because the provider omits ``va``
    entirely on a large fraction of sessions -- see :func:`trading_value_presence_profile`.
    """
    raw_v = row.get("kbs.observed_daily_volume")
    raw_va = row.get("kbs.observed_daily_trading_value")
    return not (raw_v is None or raw_va is None or raw_v == 0 or raw_va == 0)


def candidates_fitting_row(row: Mapping[str, Any]) -> list[tuple[int, int]]:
    """Every candidate scale pair that puts this row's implied average price in its range.

    The empty result is the interesting one. A row that *no* candidate explains is not
    evidence against any particular scale -- it rejects all sixteen equally -- so it says
    something about the row, not about the units. :func:`select_unit_scales` partitions on
    exactly that distinction instead of letting such a row veto the whole test.
    """
    if not row_is_eligible(row):
        return []
    low = float(row["kbs.observed_low_vnd"])
    high = float(row["kbs.observed_high_vnd"])
    fitting: list[tuple[int, int]] = []
    for volume_scale in VOLUME_SCALES:
        for trading_value_scale in TRADING_VALUE_SCALES:
            implied = implied_average_price(
                raw_v=float(row["kbs.observed_daily_volume"]),
                raw_va=float(row["kbs.observed_daily_trading_value"]),
                volume_scale=volume_scale,
                trading_value_scale=trading_value_scale,
            )
            if implied is not None and implied > 0 and (
                low - VWAP_TOLERANCE_VND <= implied <= high + VWAP_TOLERANCE_VND
            ):
                fitting.append((volume_scale, trading_value_scale))
    return fitting


def evaluate_scale_pair(
    rows: Sequence[Mapping[str, Any]], *, volume_scale: int, trading_value_scale: int
) -> dict[str, Any]:
    """Score one candidate scale pair across every eligible row.

    Rows with a missing or zero ``v`` or ``va`` are *set aside*, not counted as failures.
    A session that did not trade carries no information about units, and letting it count
    would let an untraded day argue for a scale.
    """
    inside = outside = skipped = 0
    residuals: list[float] = []
    failures: list[dict[str, Any]] = []
    for row in rows:
        raw_v = row.get("kbs.observed_daily_volume")
        raw_va = row.get("kbs.observed_daily_trading_value")
        if raw_v is None or raw_va is None or raw_v == 0 or raw_va == 0:
            skipped += 1
            continue
        implied = implied_average_price(
            raw_v=float(raw_v),
            raw_va=float(raw_va),
            volume_scale=volume_scale,
            trading_value_scale=trading_value_scale,
        )
        if implied is None or implied <= 0:
            skipped += 1
            continue
        low = float(row["kbs.observed_low_vnd"])
        high = float(row["kbs.observed_high_vnd"])
        if low - VWAP_TOLERANCE_VND <= implied <= high + VWAP_TOLERANCE_VND:
            inside += 1
            midpoint = (low + high) / 2.0
            residuals.append(abs(implied - midpoint))
        else:
            outside += 1
            failures.append(
                {
                    "session_date": row["kbs.session_date"],
                    "implied_average_price": round(implied, 4),
                    "low": low,
                    "high": high,
                }
            )
    evaluated = inside + outside
    return {
        "volume_scale": volume_scale,
        "trading_value_scale": trading_value_scale,
        "rows_evaluated": evaluated,
        "rows_inside_range": inside,
        "rows_outside_range": outside,
        "rows_skipped_missing_or_zero": skipped,
        "all_rows_inside_range": bool(evaluated) and outside == 0,
        "mean_absolute_residual_to_range_midpoint": (
            round(sum(residuals) / len(residuals), 4) if residuals else None
        ),
        "example_failures": failures[:3],
    }


#: A candidate is only *selectable* with this much evidence behind it. One row cannot pick
#: a scale, and neither can one ticker: a coincidence that survives twenty sessions across
#: three price levels is not a coincidence.
MIN_ROWS_FOR_UNIT_SELECTION = 20
MIN_TICKERS_FOR_UNIT_SELECTION = 2

#: The VWAP identity ``va*va_scale / (v*v_scale)`` depends only on the *quotient* of the
#: two scales. Two candidate pairs sharing a quotient are mathematically indistinguishable
#: by that test no matter how many rows it sees -- (1, 1) and (1000, 1000) predict the
#: identical implied price for every session ever. Pretending otherwise would be the single
#: easiest way for this milestone to overclaim, so the quotient is named as its own concept
#: and the absolute anchor is earned separately, from separately identified evidence.
def scale_quotient(volume_scale: int, trading_value_scale: int) -> float:
    """Value units per one raw ``v`` unit -- everything the VWAP test can constrain."""
    return trading_value_scale / volume_scale


def scale_quotient_class(
    candidates: Sequence[tuple[int, int]]
) -> dict[float, list[tuple[int, int]]]:
    """Group candidate pairs by the quotient the VWAP test actually measures."""
    classes: dict[float, list[tuple[int, int]]] = {}
    for volume_scale, trading_value_scale in candidates:
        classes.setdefault(scale_quotient(volume_scale, trading_value_scale), []).append(
            (volume_scale, trading_value_scale)
        )
    return classes


#: How much of a retained issued-share count a single session's implied volume may reach
#: before the reading is rejected as impossible. Deliberately loose: the tie this breaks is
#: a factor of a thousand, so the bound does its work with room to spare and never needs the
#: share count to be precise.
SHARE_COUNT_SLACK_MULTIPLE = 2.0


def resolve_scale_degeneracy(
    *,
    members: Sequence[tuple[int, int]],
    per_ticker_rows: Mapping[str, Sequence[Mapping[str, Any]]],
    share_count_bounds: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Break a quotient tie with an absolute magnitude bound, or refuse to break it.

    The bound is an order-of-magnitude falsifier, not a measurement: it asks whether a
    candidate implies a session trading several times a company's entire issued capital.
    That is why an *unqualified* share count is admissible input here and would not be
    admissible in a valuation -- the argument survives the figure being wrong by any factor
    short of the one it is rejecting. The looseness is recorded with the result so nobody
    later reads it as a qualified share-count dependency.

    Without a bound, nothing is chosen. The quotient is still reported, because the
    quotient is what was genuinely earned.
    """
    if len(members) == 1:
        return {
            "resolved": True,
            "selected": {"volume_scale": members[0][0], "trading_value_scale": members[0][1]},
            "route": "no_degeneracy",
            "members": [list(member) for member in members],
        }
    if not share_count_bounds:
        return {
            "resolved": False,
            "route": "no_absolute_anchor_supplied",
            "members": [list(member) for member in members],
            "reason": "vwap_identity_constrains_only_the_scale_quotient",
        }

    rejections: list[dict[str, Any]] = []
    surviving: list[tuple[int, int]] = []
    for volume_scale, trading_value_scale in members:
        impossible = None
        for ticker, rows in per_ticker_rows.items():
            bound = share_count_bounds.get(ticker)
            if not bound:
                continue
            ceiling = float(bound["shares_outstanding"]) * SHARE_COUNT_SLACK_MULTIPLE
            for row in rows:
                raw_v = row.get("kbs.observed_daily_volume")
                if raw_v is None:
                    continue
                implied_shares = float(raw_v) * volume_scale
                if implied_shares > ceiling:
                    impossible = {
                        "ticker": ticker,
                        "session_date": row["kbs.session_date"],
                        "implied_shares_traded": implied_shares,
                        "retained_shares_outstanding": float(bound["shares_outstanding"]),
                        "ceiling_applied": ceiling,
                        "slack_multiple": SHARE_COUNT_SLACK_MULTIPLE,
                        "bound_evidence_identity": bound.get("evidence_identity"),
                        "bound_qualification": bound.get("qualification", tiers.OBSERVED_ONLY),
                    }
                    break
            if impossible:
                break
        if impossible:
            rejections.append(
                {
                    "volume_scale": volume_scale,
                    "trading_value_scale": trading_value_scale,
                    "rejected_because": "implied_session_volume_exceeds_retained_issued_capital",
                    "detail": impossible,
                }
            )
        else:
            surviving.append((volume_scale, trading_value_scale))

    if len(surviving) != 1:
        return {
            "resolved": False,
            "route": "absolute_anchor_did_not_isolate_one_member",
            "members": [list(member) for member in members],
            "survivors": [list(member) for member in surviving],
            "rejections": rejections,
        }
    return {
        "resolved": True,
        "selected": {"volume_scale": surviving[0][0], "trading_value_scale": surviving[0][1]},
        "route": "absolute_magnitude_bound_against_retained_issued_share_count",
        "members": [list(member) for member in members],
        "rejections": rejections,
        "anchor_is_a_falsifier_not_a_measurement": True,
    }


#: How much unexplained residue a selection tolerates. A row no candidate fits is a real
#: contradiction and is always retained in full, but it does not choose between candidates,
#: so a handful of them cannot veto a relationship that thirty-odd rows demonstrate. Past
#: this share the residue stops being residue and the whole relationship is in doubt.
UNEXPLAINED_ROW_FRACTION_CEILING = 0.10


def select_unit_scales(
    per_ticker_rows: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    share_count_bounds: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Choose the one defensible ``(v, va)`` scale pair, or refuse to choose.

    The test partitions eligible rows first, because two very different things look alike
    in a naive pass/fail count:

    * a row that *some* candidate explains discriminates between candidates, and the winner
      must be inside range on every one of them;
    * a row that *no* candidate explains discriminates between nothing -- it rejects all
      sixteen identically. Treating it as a failure would let one malformed payload or one
      out-of-scope session veto a relationship the rest of the sample demonstrates, and
      treating it as a pass would be forcing a scale. It is recorded verbatim as a
      contradiction, excluded from discrimination, and capped by
      :data:`UNEXPLAINED_ROW_FRACTION_CEILING`.

    Selection then requires all of: enough discriminating rows, enough tickers, the winner
    inside range on every discriminating row, the winner holding for each ticker
    independently, and every competitor decisively rejected. Two survivors means neither is
    selected -- an ambiguous unit is an unknown unit.
    """
    all_rows = [row for rows in per_ticker_rows.values() for row in rows]
    tickers = sorted(per_ticker_rows)

    eligible = [row for row in all_rows if row_is_eligible(row)]
    fits = {id(row): candidates_fitting_row(row) for row in eligible}
    unexplained = [row for row in eligible if not fits[id(row)]]
    discriminating = [row for row in eligible if fits[id(row)]]
    unexplained_detail = [
        {
            "session_date": row["kbs.session_date"],
            "low": row["kbs.observed_low_vnd"],
            "high": row["kbs.observed_high_vnd"],
            "volume": row["kbs.observed_daily_volume"],
            "trading_value": row["kbs.observed_daily_trading_value"],
            "implied_average_price_at_unit_scale": round(
                float(row["kbs.observed_daily_trading_value"])
                / float(row["kbs.observed_daily_volume"]),
                4,
            ),
            "rejects_every_candidate": True,
        }
        for row in unexplained
    ]

    candidates = [
        {
            **evaluate_scale_pair(discriminating, volume_scale=v_scale, trading_value_scale=va_scale),
            "tickers": tickers,
        }
        for v_scale in VOLUME_SCALES
        for va_scale in TRADING_VALUE_SCALES
    ]
    survivors = [candidate for candidate in candidates if candidate["all_rows_inside_range"]]

    base = {
        "schema_version": VERSION,
        "candidates": candidates,
        "rows_eligible": len(eligible),
        "rows_evaluated": len(discriminating),
        "rows_unexplained_by_every_candidate": len(unexplained),
        "unexplained_rows": unexplained_detail,
        "unexplained_row_fraction": (
            round(len(unexplained) / len(eligible), 4) if eligible else None
        ),
        "unexplained_row_fraction_ceiling": UNEXPLAINED_ROW_FRACTION_CEILING,
        "tickers_evaluated": tickers,
        "surviving_candidates": [
            {"volume_scale": c["volume_scale"], "trading_value_scale": c["trading_value_scale"]}
            for c in survivors
        ],
        "rejected_candidates": [
            {
                "volume_scale": c["volume_scale"],
                "trading_value_scale": c["trading_value_scale"],
                "rows_outside_range": c["rows_outside_range"],
            }
            for c in candidates
            if not c["all_rows_inside_range"]
        ],
        "unexplained_row_alternative_explanations": [
            "va includes a trading component the OHLC range does not represent",
            "v and va have different market scopes",
            "partial, revised or stale payload value",
            "malformed payload",
        ],
    }

    if eligible and len(unexplained) / len(eligible) > UNEXPLAINED_ROW_FRACTION_CEILING:
        return {
            **base,
            "volume_unit": "inconclusive",
            "trading_value_unit": "inconclusive",
            "qualification": tiers.CONFLICTED,
            "reason": "too_many_rows_are_explained_by_no_candidate_scale",
        }
    if len(discriminating) < MIN_ROWS_FOR_UNIT_SELECTION or len(tickers) < MIN_TICKERS_FOR_UNIT_SELECTION:
        return {
            **base,
            "volume_unit": "inconclusive",
            "trading_value_unit": "inconclusive",
            "qualification": tiers.UNKNOWN,
            "reason": "insufficient_sample_for_unit_selection",
        }
    if not survivors:
        return {
            **base,
            "volume_unit": "inconclusive",
            "trading_value_unit": "inconclusive",
            "qualification": tiers.CONFLICTED,
            "reason": "no_candidate_scale_holds_across_the_discriminating_rows",
        }

    # Survivors that share a quotient are not competitors -- the VWAP test cannot tell them
    # apart even in principle. Survivors with *different* quotients are genuine competitors
    # and mean the test failed to discriminate.
    quotient_classes = scale_quotient_class(
        [(c["volume_scale"], c["trading_value_scale"]) for c in survivors]
    )
    base["surviving_scale_quotients"] = sorted(quotient_classes)
    base["surviving_quotient_classes"] = {
        str(quotient): [list(member) for member in members]
        for quotient, members in sorted(quotient_classes.items())
    }
    if len(quotient_classes) > 1:
        return {
            **base,
            "volume_unit": "inconclusive",
            "trading_value_unit": "inconclusive",
            "qualification": tiers.UNKNOWN,
            "reason": "competing_scale_quotients_both_survived",
        }

    quotient, members = next(iter(quotient_classes.items()))
    degeneracy = resolve_scale_degeneracy(
        members=members,
        per_ticker_rows=per_ticker_rows,
        share_count_bounds=share_count_bounds,
    )
    base["scale_quotient"] = quotient
    base["scale_quotient_meaning"] = (
        "value units per one raw v unit; this is what the VWAP identity constrains and "
        "the only part of the result the price-range test earns on its own"
    )
    base["degeneracy_resolution"] = degeneracy
    if not degeneracy["resolved"]:
        return {
            **base,
            # The quotient is real and is reported. The unit names are not, because naming
            # them would assert an absolute scale that nothing here established.
            "volume_unit": "scaled_units",
            "trading_value_unit": "scaled_units",
            "qualification": tiers.OBSERVED_ONLY,
            "reason": "scale_quotient_established_but_absolute_scale_undetermined",
        }

    winner = next(
        candidate
        for candidate in survivors
        if candidate["volume_scale"] == degeneracy["selected"]["volume_scale"]
        and candidate["trading_value_scale"] == degeneracy["selected"]["trading_value_scale"]
    )
    per_ticker_winner = {
        ticker: evaluate_scale_pair(
            [row for row in rows if row_is_eligible(row) and fits[id(row)]],
            volume_scale=winner["volume_scale"],
            trading_value_scale=winner["trading_value_scale"],
        )
        for ticker, rows in per_ticker_rows.items()
    }
    supporting = {
        ticker: item for ticker, item in per_ticker_winner.items() if item["rows_evaluated"]
    }
    if not all(item["all_rows_inside_range"] for item in supporting.values()):
        return {
            **base,
            "volume_unit": "inconclusive",
            "trading_value_unit": "inconclusive",
            "qualification": tiers.CONFLICTED,
            "reason": "winning_candidate_does_not_hold_for_every_ticker_independently",
            "per_ticker_support": {ticker: dict(item) for ticker, item in per_ticker_winner.items()},
        }
    if len(supporting) < MIN_TICKERS_FOR_UNIT_SELECTION:
        return {
            **base,
            "volume_unit": "inconclusive",
            "trading_value_unit": "inconclusive",
            "qualification": tiers.UNKNOWN,
            "reason": "insufficient_sample_for_unit_selection",
            "per_ticker_support": {ticker: dict(item) for ticker, item in per_ticker_winner.items()},
        }

    return {
        **base,
        "selected": {
            "volume_scale": winner["volume_scale"],
            "trading_value_scale": winner["trading_value_scale"],
        },
        "per_ticker_support": {ticker: dict(item) for ticker, item in per_ticker_winner.items()},
        "volume_unit": _volume_unit_for(winner["volume_scale"]),
        "trading_value_unit": _trading_value_unit_for(winner["trading_value_scale"]),
        "qualification": tiers.EMPIRICALLY_DEDUCED,
        "reason": "one_candidate_held_across_every_ticker_and_every_competitor_was_rejected",
        "mean_absolute_residual_to_range_midpoint": winner["mean_absolute_residual_to_range_midpoint"],
        "residual_contradictions_retained": len(unexplained),
    }


def _volume_unit_for(volume_scale: int) -> str:
    """A scale of 1 means ``v`` already counts what ``va`` was paid for: shares."""
    return {1: "shares", 100: "board_lots"}.get(volume_scale, "scaled_units")


def _trading_value_unit_for(trading_value_scale: int) -> str:
    return {1: "VND", 1_000: "thousand_VND", 1_000_000: "million_VND"}.get(
        trading_value_scale, "scaled_units"
    )


def assert_unit_does_not_qualify_scope(unit_result: Mapping[str, Any]) -> None:
    """A unit verdict must never be written as if it settled market composition.

    The two questions are ``how much`` and ``what kind``. A share count that reconciles
    against a traded amount reconciles identically whether the underlying figure counts
    matched orders only or matched plus negotiated blocks.
    """
    for key in ("volume_market_scope", "market_scope", "negotiated_trade_inclusion"):
        if unit_result.get(key) not in (None, "unknown"):
            raise KBSBasisError(f"unit_verdict_must_not_set_market_scope:{key}")


# ---------------------------------------------------------------------------------
# Volume adjustment -- independent of the price finding
# ---------------------------------------------------------------------------------


def price_volume_restatement_divergence(
    *,
    rows: Sequence[Mapping[str, Any]],
    reference_volumes: Mapping[str, Any],
    reference_identity: str,
) -> dict[str, Any]:
    """Do the price and volume fields get restated together, or independently?

    Compares a KBS window against an independently retained volume series for the same
    sessions. When the price fields sit off the quotation lattice -- so they were restated
    -- and the volumes are nonetheless identical to a series recorded before the event,
    the two fields were demonstrably restated on different schedules.

    That is a fact about *these* sessions and this event kind. It is recorded as its own
    observation rather than folded into the volume-adjustment verdict, because a cash
    distribution has no share count to restate; what a *share* event does to volume is a
    different question and this cannot answer it.
    """
    matched = [row for row in rows if row["kbs.session_date"] in reference_volumes]
    if not matched:
        return {"sessions_compared": 0, "verdict": "no_overlapping_sessions"}
    off_lattice = [
        row
        for row in matched
        if not all(on_tick_lattice(float(row[field])) for field in _LATTICE_FIELDS)
    ]
    volume_agreements = [
        row
        for row in matched
        if row.get("kbs.observed_daily_volume") is not None
        and float(row["kbs.observed_daily_volume"])
        == float(reference_volumes[row["kbs.session_date"]])
    ]
    diverged = bool(off_lattice) and len(volume_agreements) == len(matched)
    return {
        "sessions_compared": len(matched),
        "sessions_with_restated_prices": len(off_lattice),
        "sessions_with_volume_equal_to_reference": len(volume_agreements),
        "reference_identity": reference_identity,
        "verdict": (
            "price_restated_while_volume_unchanged"
            if diverged
            else "no_independent_restatement_demonstrated"
        ),
        "note": (
            "Demonstrates that the two fields are restated on different schedules. It does "
            "not establish what a share-related event does to volume, and it is not an "
            "input to the volume-adjustment verdict."
        ),
    }


def volume_adjustment_verdict(
    *,
    rewrite_test: Mapping[str, Any] | None,
    share_event_window_tested: bool,
    price_basis_verdict: str,
) -> dict[str, Any]:
    """Qualify whether historical ``v`` is rewritten, using volume evidence only.

    ``price_basis_verdict`` is accepted precisely so the refusal can be explicit: a price
    adjustment is a restatement of what a share was worth, and a volume is a count of
    shares that changed hands. Neither implies the other in either direction.
    """
    del price_basis_verdict  # deliberately unused; it is not an input to this question
    if rewrite_test is None:
        return {
            "verdict": "unknown",
            "reason": "no_retained_as_of_pair_covering_a_share_event_window",
            "derived_from_price_adjustment": False,
        }
    if rewrite_test.get("sessions_with_changed_volume"):
        return {
            "verdict": "retrospectively_rewritten_unknown_method",
            "reason": "the_same_historical_sessions_returned_different_volumes",
            "sessions_with_changed_volume": rewrite_test["sessions_with_changed_volume"],
            "derived_from_price_adjustment": False,
            "note": "Rewritten is not the same as event-adjusted. Without a share-event "
            "window in the comparison, the cause is unidentified.",
        }
    if not share_event_window_tested:
        return {
            "verdict": "not_observed",
            "reason": "no_volume_change_observed_but_no_share_event_spanned_the_comparison",
            "sessions_compared": rewrite_test.get("sessions_compared", 0),
            "derived_from_price_adjustment": False,
            "note": "A control window cannot demonstrate that a share event would leave "
            "volume alone.",
        }
    return {
        "verdict": "unadjusted_volume_empirically_supported",
        "reason": "volumes_unchanged_across_a_comparison_spanning_a_qualified_share_event",
        "sessions_compared": rewrite_test.get("sessions_compared", 0),
        "derived_from_price_adjustment": False,
    }


# ---------------------------------------------------------------------------------
# Market scope -- an independent axis that stays shut
# ---------------------------------------------------------------------------------

#: The only routes that may upgrade a composition dimension. Each is a *reproducible
#: independent observation*, not an interpretation of the same undifferentiated counter.
ADMISSIBLE_SCOPE_EVIDENCE = frozenset(
    {
        "retained_official_exchange_total_matching_ticker_and_date",
        "separately_labelled_provider_fields_with_demonstrated_relationship",
        "complete_intraday_reconciliation_with_clear_field_semantics",
        "reproducible_independent_observation",
    }
)

#: Deliberately inadmissible on its own. A financial portal or a news report can point at a
#: date worth examining and cannot say what the exchange counted.
SECONDARY_CORROBORATION = "secondary_media_or_financial_website"

#: Confounders that must each be eliminated before a discrepancy means anything about
#: composition. Any one of them produces the same shaped gap as a missing trade class.
SCOPE_CONFOUNDERS = (
    "unit_mismatch",
    "partial_day_data",
    "delayed_update",
    "pagination_limit",
    "revised_figures",
    "ticker_or_date_mismatch",
)

MIN_INDEPENDENT_OBSERVATIONS_FOR_SCOPE = 2


def qualify_market_scope_dimension(
    *,
    dimension: str,
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Upgrade one composition dimension, or leave it ``unknown``.

    Requires at least two admissible independent observations, each with every confounder
    explicitly eliminated. Secondary corroboration is counted and never qualifies: one
    large negotiated-trade day looking small against a media total is a reason to look, not
    a finding.
    """
    if dimension not in MARKET_SCOPE_DIMENSIONS:
        raise KBSBasisError(f"unknown_market_scope_dimension:{dimension}")
    admissible = []
    secondary = 0
    for observation in observations:
        kind = str(observation.get("evidence_kind", ""))
        if kind == SECONDARY_CORROBORATION:
            secondary += 1
            continue
        if kind not in ADMISSIBLE_SCOPE_EVIDENCE:
            continue
        eliminated = set(observation.get("confounders_eliminated") or ())
        if set(SCOPE_CONFOUNDERS) - eliminated:
            continue
        admissible.append(dict(observation))
    if len(admissible) >= MIN_INDEPENDENT_OBSERVATIONS_FOR_SCOPE:
        return {
            "dimension": dimension,
            "verdict": "qualified",
            "qualification": tiers.EMPIRICALLY_DEDUCED,
            "independent_observations": len(admissible),
            "secondary_corroboration_count": secondary,
            "secondary_corroboration_upgraded_verdict": False,
        }
    return {
        "dimension": dimension,
        "verdict": "unknown",
        "qualification": tiers.UNKNOWN,
        "independent_observations": len(admissible),
        "secondary_corroboration_count": secondary,
        "secondary_corroboration_upgraded_verdict": False,
        "reason": "insufficient_admissible_independent_observations",
    }


def market_scope_contract(
    dimension_observations: Mapping[str, Sequence[Mapping[str, Any]]] | None = None
) -> dict[str, Any]:
    """The KBS market-scope contract. Every dimension starts and stays ``unknown`` here.

    ``liquidity_actionable`` is a constant, not a computed value: sizing against a volume
    figure requires knowing which trades it counts, and no route in this milestone answers
    that for KBS.
    """
    observations = dimension_observations or {}
    dimensions = {
        dimension: qualify_market_scope_dimension(
            dimension=dimension, observations=observations.get(dimension, ())
        )
        for dimension in MARKET_SCOPE_DIMENSIONS
    }
    return {
        "schema_version": VERSION,
        "provider": PROVIDER,
        "source_authority": SOURCE_AUTHORITY,
        "dimensions": dimensions,
        "volume_market_scope": (
            "unknown"
            if any(item["verdict"] == "unknown" for item in dimensions.values())
            else "qualified"
        ),
        "liquidity_actionable": False,
        "reason": "no_admissible_independent_observation_of_kbs_market_composition_exists",
        "reopen_condition": "retained_official_exchange_totals_or_separately_labelled_provider_fields",
    }


# ---------------------------------------------------------------------------------
# The assembled contract
# ---------------------------------------------------------------------------------

STARTING_CONTRACT: dict[str, Any] = {
    "provider": PROVIDER,
    "time_field_identity": "qualified",
    "open_field_identity": "qualified",
    "high_field_identity": "qualified",
    "low_field_identity": "qualified",
    "close_field_identity": "qualified",
    "volume_field_identity": "qualified",
    "trading_value_field_identity": "qualified",
    "price_basis": "unknown",
    "historical_mutability": "unknown",
    "volume_unit": "unknown",
    "volume_adjustment_basis": "unknown",
    "volume_market_scope": "unknown",
    "trading_value_unit": "unknown",
    "liquidity_actionable": False,
}


def price_basis_contract(
    *,
    merged: Mapping[str, Any],
    historical_mutability: str,
    tested_windows: Sequence[str],
    empirical_record: Mapping[str, Any],
) -> dict[str, Any]:
    """Assemble the KBS price-basis contract, with eligibility computed, never asserted.

    ``raw_as_traded_eligible`` needs two independent things and gets neither for free: a
    window that supports an as-traded series, *and* the absence of an observed retrospective
    rewrite. A rewritten series is ineligible whatever the lattice says, because the value
    for a past date is not the value that date will report tomorrow.
    """
    if merged["verdict"] not in PRICE_BASIS_VERDICTS:
        raise KBSBasisError(f"price_basis_verdict_not_in_vocabulary:{merged['verdict']}")
    if historical_mutability not in HISTORICAL_MUTABILITY_VERDICTS:
        raise KBSBasisError(f"historical_mutability_invalid:{historical_mutability}")

    record = tiers.assert_empirically_deduced(empirical_record)
    tiers.assert_single_window_insufficient(record)

    supports_raw = merged["verdict"] == "raw_as_traded_empirically_supported"
    rewritten = historical_mutability == "retrospectively_rewritten"
    qualification = (
        tiers.CONFLICTED
        if merged["verdict"] == "conflicted"
        else tiers.UNKNOWN
        if merged["verdict"] == "inconclusive"
        else tiers.EMPIRICALLY_DEDUCED
    )
    return {
        "schema_version": VERSION,
        "provider": PROVIDER,
        "source_authority": SOURCE_AUTHORITY,
        "documented_semantics": "absent",
        "field_identity": "qualified",
        "price_basis": merged["verdict"],
        "price_basis_qualification": qualification,
        "historical_mutability": historical_mutability,
        "observed_adjustment_dimensions": list(merged.get("observed_adjustment_dimensions", [])),
        "provider_methodology": "unknown",
        "coverage_generalization": tiers.COVERAGE_LIMITED,
        "tested_windows": list(tested_windows),
        "raw_as_traded_eligible": bool(supports_raw and not rewritten),
        "official_exchange_price": False,
        "empirical_record": record,
    }


def assert_contract_fail_closed(contract: Mapping[str, Any]) -> Mapping[str, Any]:
    """Refuse a contract that has opened something the evidence does not open."""
    if contract.get("liquidity_actionable"):
        raise KBSBasisError("liquidity_actionable_must_stay_false")
    if contract.get("official_exchange_price"):
        raise KBSBasisError("official_exchange_price_must_stay_false")
    if contract.get("provider") != PROVIDER:
        raise KBSBasisError("contract_provider_must_be_kbs")
    if contract.get("coverage_generalization") not in tiers.COVERAGE_STATES:
        raise KBSBasisError(f"coverage_generalization_invalid:{contract.get('coverage_generalization')}")
    qualification = str(contract.get("price_basis_qualification", tiers.UNKNOWN))
    if tiers.may_claim_official_semantics(qualification):
        raise KBSBasisError("kbs_has_no_documented_semantics_to_claim")
    if contract.get("raw_as_traded_eligible") and contract.get("historical_mutability") == "retrospectively_rewritten":
        raise KBSBasisError("rewritten_series_cannot_be_raw_as_traded_eligible")
    if contract.get("provider_methodology") not in (None, "unknown"):
        raise KBSBasisError("provider_methodology_is_not_established_by_this_milestone")
    return contract


def apply_cross_provider_agreement(
    contract: Mapping[str, Any], *, agreement: Mapping[str, Any]
) -> dict[str, Any]:
    """Record agreement with another provider as compatibility evidence only.

    Two undocumented providers returning the same numbers are interchangeable for that
    window. Neither one thereby acquires an authority the other never had.
    """
    result = tiers.apply_corroboration(
        {**contract, "qualification": contract.get("price_basis_qualification", tiers.UNKNOWN)},
        corroboration={**dict(agreement), "authority_effect": "none"},
    )
    result["price_basis_qualification"] = contract.get("price_basis_qualification", tiers.UNKNOWN)
    result["cross_provider_comparison_upgraded_verdict"] = False
    result.pop("qualification", None)
    return result


def assert_no_generic_upgrade(record: Mapping[str, Any]) -> Mapping[str, Any]:
    """Reject any attempt to write a generic or foreign-provider field from this lane."""
    for key in record:
        name = str(key)
        if name in FORBIDDEN_GENERIC_FIELDS:
            raise KBSBasisError(f"generic_field_upgrade_forbidden:{name}")
        if "." in name and not name.startswith("kbs."):
            raise KBSBasisError(f"foreign_provider_namespace_forbidden:{name}")
    return record


def assert_no_provider_inheritance(other_provider: str) -> None:
    """A KBS verdict says nothing about anyone else's fields."""
    if str(other_provider).strip().upper() == PROVIDER:
        return
    raise KBSBasisError(
        f"kbs_verdict_does_not_transfer:{str(other_provider).strip().upper()}"
    )


# ---------------------------------------------------------------------------------
# Evidence manifest and deterministic replay
# ---------------------------------------------------------------------------------

_OBSERVATION_FIELDS = (
    "provider",
    "source_authority",
    "endpoint",
    "method",
    "request_parameters",
    "request_headers_redacted",
    "retrieved_at",
    "http_status",
    "redirect_count",
    "retry_count",
    "raw_response_sha256",
    "response_schema_fingerprint",
    "ticker",
    "interval",
    "requested_date_range",
    "returned_date_range",
    "raw_field_names",
    "normalized_field_names",
    "transformations",
    "transformation_code_identity",
    "window_role",
    "unresolved_semantic_dimensions",
)


def build_observation(**kwargs: Any) -> dict[str, Any]:
    """Assemble one evidence record, refusing to persist an incomplete or unsafe one."""
    missing = [field for field in _OBSERVATION_FIELDS if field not in kwargs]
    if missing:
        raise KBSBasisError(f"observation_fields_missing:{','.join(missing)}")
    record = {field: kwargs[field] for field in _OBSERVATION_FIELDS}
    if record["provider"] != PROVIDER:
        raise KBSBasisError("observation_provider_must_be_kbs")
    assert_endpoint_in_scope(str(record["endpoint"]))
    assert_ticker_in_scope(str(record["ticker"]))
    record["request_headers_redacted"] = redact_headers(record["request_headers_redacted"])
    leaked = _find_sensitive_leak(record)
    if leaked:
        raise KBSBasisError(f"observation_contains_sensitive_material:{leaked}")
    record["schema_version"] = VERSION
    return record


def _find_sensitive_leak(node: Any, path: str = "") -> str | None:
    if isinstance(node, Mapping):
        for key, value in node.items():
            name = str(key)
            here = f"{path}.{name}" if path else name
            if name.strip().lower() in SENSITIVE_HEADER_NAMES and value != REDACTED:
                return here
            found = _find_sensitive_leak(value, here)
            if found:
                return found
    elif isinstance(node, (list, tuple)):
        for index, item in enumerate(node):
            found = _find_sensitive_leak(item, f"{path}[{index}]")
            if found:
                return found
    return None


def evidence_manifest(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The manifest a later reader replays the whole qualification from."""
    entries = [
        {
            "artifact": observation["artifact"],
            "sha256": observation["raw_response_sha256"],
            "ticker": observation["ticker"],
            "window_role": observation["window_role"],
            "requested_date_range": observation["requested_date_range"],
            "retrieved_at": observation["retrieved_at"],
            "response_schema_fingerprint": observation["response_schema_fingerprint"],
        }
        for observation in observations
    ]
    entries.sort(key=lambda entry: (entry["ticker"], entry["retrieved_at"], entry["sha256"]))
    payload = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": VERSION,
        "provider": PROVIDER,
        "source_authority": SOURCE_AUTHORITY,
        "transformation_code_identity": TRANSFORMATION_CODE_IDENTITY,
        "artifacts": entries,
        "artifact_count": len(entries),
        "manifest_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


def replay(manifest: Mapping[str, Any], *, load_bytes: Any) -> dict[str, Any]:
    """Re-derive every raw row from the manifest, verifying each artifact's hash first.

    Deterministic by construction: it touches no clock, no network and no database, and a
    byte that does not match its recorded hash stops the replay rather than being parsed.
    """
    if manifest.get("provider") != PROVIDER:
        raise KBSBasisError("manifest_provider_must_be_kbs")
    per_artifact: dict[str, list[dict[str, Any]]] = {}
    for entry in manifest["artifacts"]:
        raw = load_bytes(entry["artifact"])
        digest = response_sha256(raw)
        if digest != entry["sha256"]:
            raise KBSBasisError(f"replay_artifact_hash_mismatch:{entry['artifact']}")
        payload = json.loads(raw.decode("utf-8"))
        per_artifact[entry["artifact"]] = parse_daily_payload(payload, symbol=entry["ticker"])
    fingerprint_payload = json.dumps(
        {name: rows for name, rows in sorted(per_artifact.items())},
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "schema_version": VERSION,
        "artifacts_replayed": len(per_artifact),
        "rows_by_artifact": per_artifact,
        "replay_fingerprint": hashlib.sha256(fingerprint_payload.encode("utf-8")).hexdigest(),
    }


# ---------------------------------------------------------------------------------
# Live acquisition -- the only network-touching function in this module
# ---------------------------------------------------------------------------------


def classify_failure(*, exception: BaseException | None, status: int | None, body: Any) -> str:
    if exception is not None:
        name = type(exception).__name__
        if "Timeout" in name or "ConnectionError" in name:
            return "source_unavailable"
        if isinstance(exception, KBSBasisError):
            message = str(exception)
            if "not_a_list" in message or "missing_key" in message:
                return "schema_changed"
            if "zero_sessions" in message:
                return "empty_valid_response"
            return "malformed_response"
        return "request_contract_defect"
    if status in (401, 403):
        return "access_blocked"
    if status == 429:
        return "rate_limited"
    if status is not None and status >= 400:
        return "source_unavailable"
    if not body:
        return "empty_valid_response"
    return "unclassified"


def acquire(
    *,
    symbol: str,
    start: str,
    end: str,
    session: Any,
    headers: Mapping[str, str],
    timeout: tuple[float, float] = (5.0, 20.0),
    max_attempts: int = 2,
) -> dict[str, Any]:
    """Issue one bounded GET and return the raw bytes plus transport facts.

    Redirects are inspected against the provider boundary before being followed, and
    nothing is parsed here -- the caller hashes and stores the bytes before any
    interpretation happens. ``max_attempts`` matches the adapter's own retry behaviour and
    is not a place to add retries of our own.
    """
    url = assert_endpoint_in_scope(daily_endpoint(symbol))
    params = daily_params(start=start, end=end)
    redirect_count = 0
    retry_count = 0
    last_error: BaseException | None = None

    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            retry_count += 1
        try:
            response = session.get(
                url, params=dict(params), headers=dict(headers), timeout=timeout, allow_redirects=False
            )
        except Exception as exc:  # noqa: BLE001 -- classified, not swallowed
            last_error = exc
            continue

        while response.status_code in (301, 302, 303, 307, 308) and redirect_count < 3:
            location = response.headers.get("Location")
            assert_redirect_within_boundary(location)
            redirect_count += 1
            response = session.get(
                location, headers=dict(headers), timeout=timeout, allow_redirects=False
            )

        return {
            "url": url,
            "request_parameters": dict(params),
            "http_status": response.status_code,
            "redirect_count": redirect_count,
            "retry_count": retry_count,
            "raw_body": response.content,
            "response_headers_redacted": redact_headers(dict(response.headers)),
            "retrieved_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
        }

    raise KBSBasisError(
        f"acquisition_failed:{classify_failure(exception=last_error, status=None, body=None)}"
    )
