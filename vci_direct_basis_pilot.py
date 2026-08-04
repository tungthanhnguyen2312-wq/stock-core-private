"""Bounded direct-VCI price/volume basis qualification harness.

Scope discipline (deliberately narrow, do not generalise):

* One provider lane only -- VCI, reached at its observed public web endpoint. This is
  **not** a documented developer API; see ``SOURCE_AUTHORITY``.
* Three tickers, explicit date windows, no symbol discovery, no full-history requests.
* Raw payloads are preserved verbatim and immutably; normalisation is a separate step
  whose every transformation is recorded as data rather than applied silently.
* Nothing here writes to a production database, bundle or dashboard artifact.
* Live acquisition lives in :func:`acquire` alone. Every other function is pure so the
  unit tests can exercise the whole contract from frozen fixtures.

The qualification verdicts this module can emit are provider-namespaced by construction
(``vci.raw_close``, ``vci.observed_daily_volume``). They never qualify a generic field --
see :func:`assert_no_generic_upgrade`.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

VERSION = "1.0.0"

PROVIDER = "VCI"

#: An endpoint observed in the provider's own web application and in the established
#: ``vnstock`` adapter path. It carries no first-party developer-API documentation, no
#: published schema and no semantic declaration, so no verdict derived from it may be
#: promoted to an official-exchange or canonical claim.
SOURCE_AUTHORITY = "observed_public_web_endpoint"

PROVIDER_HOST = "trading.vietcap.com.vn"
DAILY_ENDPOINT = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"
INTRADAY_ENDPOINT = "https://trading.vietcap.com.vn/api/market-watch/LEData/getAll"

ALLOWED_TICKERS = ("HPG", "VNM", "VCB")
ALLOWED_ENDPOINTS = (DAILY_ENDPOINT, INTRADAY_ENDPOINT)

#: Hard ceiling for the whole pilot. Exhausting it stops acquisition; it is never reset.
REQUEST_BUDGET = 8

#: Header names whose values must never reach an evidence artifact.
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

# --- Price-basis vocabulary -------------------------------------------------------

PRICE_BASIS_VERDICTS = frozenset(
    {
        "raw_unadjusted",
        "split_adjusted",
        "dividend_adjusted",
        "split_and_dividend_adjusted",
        "mixed_or_context_dependent",
        "inconclusive",
    }
)

VOLUME_RECONCILIATION_VERDICTS = frozenset(
    {
        "daily_equals_observed_intraday_sum",
        "daily_exceeds_observed_intraday_sum",
        "intraday_sample_incomplete",
        "unit_scaled_match",
        "scope_inconclusive",
    }
)

#: Generic namespaces this milestone must never populate.
FORBIDDEN_GENERIC_FIELDS = frozenset(
    {
        "official_close",
        "official_adjusted_close",
        "official_exchange_volume",
        "canonical_market_volume",
        "adjusted_close",
        "adjustment_factor",
        "price_basis",
        "volume_basis",
        "is_actionable",
        "liquidity_actionable",
    }
)


class VCIPilotError(ValueError):
    """Fail-closed rejection inside the pilot harness."""


# ---------------------------------------------------------------------------------
# Request construction and boundary enforcement
# ---------------------------------------------------------------------------------


def assert_ticker_in_scope(symbol: str) -> str:
    """Reject any symbol outside the three pilot tickers."""
    upper = str(symbol).strip().upper()
    if upper not in ALLOWED_TICKERS:
        raise VCIPilotError(f"ticker_out_of_pilot_scope:{upper}")
    return upper


def assert_endpoint_in_scope(url: str) -> str:
    """Reject any endpoint that is not one of the two observed provider endpoints."""
    if url not in ALLOWED_ENDPOINTS:
        raise VCIPilotError(f"endpoint_out_of_pilot_scope:{url}")
    return url


def assert_redirect_within_boundary(location: str | None) -> None:
    """Reject a redirect that leaves the observed provider host.

    A redirect off ``trading.vietcap.com.vn`` is not the provider answering; following
    it would attribute a third party's bytes to VCI.
    """
    if location is None:
        return
    match = re.match(r"^https?://([^/:?#]+)", str(location).strip(), re.IGNORECASE)
    if match is None:
        # A relative redirect stays on the same host by definition.
        return
    host = match.group(1).lower()
    if host != PROVIDER_HOST:
        raise VCIPilotError(f"redirect_outside_provider_boundary:{host}")


def redact_headers(headers: Mapping[str, Any] | None) -> dict[str, str]:
    """Return headers safe to persist: sensitive values replaced, never dropped silently."""
    if not headers:
        return {}
    return {
        str(name): (REDACTED if str(name).strip().lower() in SENSITIVE_HEADER_NAMES else str(value))
        for name, value in headers.items()
    }


def daily_payload(symbol: str, *, to_epoch: int, count_back: int) -> dict[str, Any]:
    """Non-secret request body for the daily OHLC endpoint."""
    symbol = assert_ticker_in_scope(symbol)
    if not isinstance(to_epoch, int) or to_epoch <= 0:
        raise VCIPilotError("daily_to_epoch_invalid")
    if not isinstance(count_back, int) or not 1 <= count_back <= 400:
        raise VCIPilotError("daily_count_back_out_of_bounds")
    return {"timeFrame": "ONE_DAY", "symbols": [symbol], "to": to_epoch, "countBack": count_back}


def intraday_payload(symbol: str, *, limit: int, trunc_time: int | None = None) -> dict[str, Any]:
    """Non-secret request body for the intraday matched-trade endpoint."""
    symbol = assert_ticker_in_scope(symbol)
    if not isinstance(limit, int) or not 1 <= limit <= 30_000:
        raise VCIPilotError("intraday_limit_out_of_bounds")
    return {"symbol": symbol, "limit": limit, "truncTime": trunc_time}


# ---------------------------------------------------------------------------------
# Response identity
# ---------------------------------------------------------------------------------


def response_sha256(raw_body: bytes) -> str:
    """SHA-256 of the exact bytes the provider returned, before any parsing."""
    if not isinstance(raw_body, (bytes, bytearray)):
        raise VCIPilotError("raw_body_must_be_bytes")
    return hashlib.sha256(bytes(raw_body)).hexdigest()


def schema_fingerprint(obj: Any) -> str:
    """Structure-only fingerprint: key names and value kinds, never values.

    Lets a later observation detect a source-contract change without comparing data.
    """

    def shape(node: Any) -> Any:
        if isinstance(node, Mapping):
            return {str(key): shape(node[key]) for key in sorted(node, key=str)}
        if isinstance(node, (list, tuple)):
            kinds = {json.dumps(shape(item), sort_keys=True) for item in node}
            return ["|".join(sorted(kinds))] if kinds else []
        if isinstance(node, bool):
            return "bool"
        if isinstance(node, (int, float)):
            # JSON draws no line between 54000 and 54000.0, so neither does the
            # fingerprint. Only a changed key or a changed kind is a contract change.
            return "number"
        if node is None:
            return "null"
        return "str"

    canonical = json.dumps(shape(obj), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def artifact_name(kind: str, symbol: str, *, retrieved_at: str, body_sha256: str) -> str:
    """Deterministic artifact name.

    Includes the retrieval instant so a later, differing observation is stored beside the
    earlier one instead of replacing it.
    """
    symbol = assert_ticker_in_scope(symbol)
    if kind not in {"daily", "intraday"}:
        raise VCIPilotError(f"artifact_kind_unknown:{kind}")
    stamp = re.sub(r"[^0-9TZ]", "", str(retrieved_at).upper())
    if not stamp:
        raise VCIPilotError("retrieved_at_unusable_for_artifact_name")
    return f"vci_{kind}_{symbol}_{stamp}_{body_sha256[:16]}.raw.json"


# ---------------------------------------------------------------------------------
# Raw payload parsing -- fail closed, no repair
# ---------------------------------------------------------------------------------

_DAILY_ARRAY_FIELDS = ("t", "o", "h", "l", "c", "v")


def parse_daily_payload(payload: Any, *, symbol: str) -> list[dict[str, Any]]:
    """Parse the raw gap-chart payload into per-session raw rows, or fail closed.

    Returns rows keyed by the provider's own field names under a ``vci.raw_`` namespace.
    No scaling, no rounding, no gap filling, no resampling happens here.
    """
    symbol = assert_ticker_in_scope(symbol)
    if not isinstance(payload, list) or not payload:
        raise VCIPilotError("daily_payload_empty_or_not_a_list")
    if len(payload) != 1:
        raise VCIPilotError(f"daily_payload_symbol_block_count_unexpected:{len(payload)}")
    block = payload[0]
    if not isinstance(block, Mapping):
        raise VCIPilotError("daily_payload_block_not_an_object")

    returned_symbol = str(block.get("symbol", "")).strip().upper()
    if returned_symbol != symbol:
        raise VCIPilotError(f"daily_payload_symbol_mismatch:{returned_symbol or 'missing'}")

    missing = [field for field in _DAILY_ARRAY_FIELDS if not isinstance(block.get(field), list)]
    if missing:
        raise VCIPilotError(f"daily_payload_missing_arrays:{','.join(missing)}")

    lengths = {field: len(block[field]) for field in _DAILY_ARRAY_FIELDS}
    if len(set(lengths.values())) != 1:
        raise VCIPilotError(f"daily_payload_ragged_arrays:{lengths}")
    count = next(iter(lengths.values()))
    if count == 0:
        raise VCIPilotError("daily_payload_zero_sessions")

    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    previous: int | None = None
    for index in range(count):
        try:
            epoch = int(block["t"][index])
        except (TypeError, ValueError) as exc:
            raise VCIPilotError(f"daily_payload_timestamp_unparseable:index={index}") from exc
        if epoch in seen:
            raise VCIPilotError(f"daily_payload_duplicate_session:{epoch}")
        if previous is not None and epoch <= previous:
            raise VCIPilotError(f"daily_payload_timestamps_not_increasing:{epoch}")
        seen.add(epoch)
        previous = epoch

        prices: dict[str, float] = {}
        for field in ("o", "h", "l", "c"):
            value = block[field][index]
            if value is None or (isinstance(value, float) and value != value):
                raise VCIPilotError(f"daily_payload_missing_price:{field}@{epoch}")
            try:
                prices[field] = float(value)
            except (TypeError, ValueError) as exc:
                raise VCIPilotError(f"daily_payload_price_unparseable:{field}@{epoch}") from exc
        if prices["l"] > min(prices["o"], prices["c"]) or prices["h"] < max(prices["o"], prices["c"]):
            raise VCIPilotError(f"daily_payload_ohlc_inconsistent:{epoch}")

        # A missing volume stays missing. It is never coerced to zero, because zero is a
        # meaningful observation (no trading) and None is not.
        raw_volume = block["v"][index]
        if raw_volume is None:
            volume: int | None = None
        else:
            try:
                volume = int(raw_volume)
            except (TypeError, ValueError) as exc:
                raise VCIPilotError(f"daily_payload_volume_unparseable:@{epoch}") from exc
            if volume < 0:
                raise VCIPilotError(f"daily_payload_volume_negative:@{epoch}")

        rows.append(
            {
                "vci.raw_t": epoch,
                "vci.raw_open": prices["o"],
                "vci.raw_high": prices["h"],
                "vci.raw_low": prices["l"],
                "vci.raw_close": prices["c"],
                "vci.raw_volume": volume,
            }
        )
    return rows


def parse_intraday_payload(payload: Any, *, symbol: str) -> list[dict[str, Any]]:
    """Parse the raw matched-trade payload, or fail closed."""
    symbol = assert_ticker_in_scope(symbol)
    if isinstance(payload, Mapping):
        payload = payload.get("data", None)
    if not isinstance(payload, list) or not payload:
        raise VCIPilotError("intraday_payload_empty_or_not_a_list")

    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(payload):
        if not isinstance(item, Mapping):
            raise VCIPilotError(f"intraday_row_not_an_object:index={index}")
        if "symbol" in item and str(item["symbol"]).strip().upper() != symbol:
            raise VCIPilotError(f"intraday_row_symbol_mismatch:index={index}")
        for field in ("truncTime", "matchPrice", "matchVol"):
            if item.get(field) is None:
                raise VCIPilotError(f"intraday_row_missing_field:{field}@index={index}")
        identity = str(item.get("id", f"__index_{index}"))
        if identity in seen_ids:
            raise VCIPilotError(f"intraday_duplicate_trade_id:{identity}")
        seen_ids.add(identity)
        try:
            # The provider sends every numeric as a decimal string ("1700.0"). Parsing
            # through float and demanding integrality keeps a fractional share count -- a
            # thing that cannot exist -- from being silently truncated to an integer.
            quantity_float = float(item["matchVol"])
            price = float(item["matchPrice"])
            trunc_time = int(float(item["truncTime"]))
        except (TypeError, ValueError) as exc:
            raise VCIPilotError(f"intraday_row_unparseable:index={index}") from exc
        if quantity_float != int(quantity_float):
            raise VCIPilotError(f"intraday_trade_quantity_not_integral:index={index}")
        quantity = int(quantity_float)
        if quantity < 0:
            raise VCIPilotError(f"intraday_trade_quantity_negative:index={index}")
        row = {
            "vci.raw_trade_id": identity,
            "vci.raw_trunc_time": trunc_time,
            "vci.raw_match_price": price,
            "vci.observed_intraday_trade_quantity": quantity,
            "vci.raw_match_type": item.get("matchType"),
        }
        for optional, target in (
            ("accumulatedVolume", "vci.raw_accumulated_volume"),
            ("accumulatedValue", "vci.raw_accumulated_value"),
        ):
            if item.get(optional) is not None:
                try:
                    row[target] = float(item[optional])
                except (TypeError, ValueError) as exc:
                    raise VCIPilotError(f"intraday_row_unparseable:{optional}@index={index}") from exc
        rows.append(row)
    return rows


def intraday_accumulator_consistency(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Check the provider's own running accumulators against its own per-trade fields.

    This is an internal-consistency proof, not a cross-source comparison: between two
    consecutive trades the accumulated-volume delta must equal the newer trade's quantity,
    and the accumulated-value delta must equal quantity x price under exactly one scale.
    Establishing that scale is what qualifies the *unit* of the volume field -- a share
    count and a lot count differ by a factor of 100 in the value identity.
    """
    ordered = sorted(rows, key=lambda row: (row["vci.raw_trunc_time"], str(row["vci.raw_trade_id"])))
    usable = [
        row
        for row in ordered
        if "vci.raw_accumulated_volume" in row and "vci.raw_accumulated_value" in row
    ]
    if len(usable) < 2:
        return {"checked_pairs": 0, "verdict": "insufficient_accumulator_coverage"}

    volume_ok = value_ok = pairs = 0
    scales: set[int] = set()
    for previous, current in zip(usable, usable[1:]):
        volume_delta = current["vci.raw_accumulated_volume"] - previous["vci.raw_accumulated_volume"]
        value_delta = current["vci.raw_accumulated_value"] - previous["vci.raw_accumulated_value"]
        quantity = current["vci.observed_intraday_trade_quantity"]
        pairs += 1
        if abs(volume_delta - quantity) < 0.5:
            volume_ok += 1
        turnover_vnd = quantity * current["vci.raw_match_price"]
        for scale in (1, 1_000, 1_000_000):
            if value_delta and abs(value_delta * scale - turnover_vnd) <= max(1.0, turnover_vnd * 1e-6):
                value_ok += 1
                scales.add(scale)
                break

    return {
        "checked_pairs": pairs,
        "accumulated_volume_delta_equals_trade_quantity": volume_ok,
        "accumulated_value_delta_matches_quantity_times_price": value_ok,
        "implied_accumulated_value_scale_to_vnd": sorted(scales),
        "verdict": (
            "accumulators_internally_consistent"
            if pairs and volume_ok == pairs and value_ok == pairs and len(scales) == 1
            else "accumulators_not_fully_consistent"
        ),
    }


# ---------------------------------------------------------------------------------
# Normalisation -- separate from raw, every transformation recorded
# ---------------------------------------------------------------------------------

TRANSFORMATION_CODE_IDENTITY = f"vci_direct_basis_pilot.normalize_daily/{VERSION}"


def normalize_daily(raw_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Derive normalised rows from raw rows, recording each transformation explicitly.

    Only two transformations are applied and both are declared:

    * ``t`` -> session date, by UTC-second interpretation then Asia/Ho_Chi_Minh calendar
      date. The provider stamps daily bars at 00:00:00Z, so this is a labelling step, not
      a timezone shift of an intraday instant.
    * price fields -> VND, by an identity scale. The observed payload already states VND
      (four- to five-digit values). No division, no rounding, no unit guessing.

    The raw values survive untouched next to the normalised ones.
    """
    if not raw_rows:
        raise VCIPilotError("normalize_daily_received_no_rows")

    transformations = [
        {
            "source_field": "vci.raw_t",
            "target_field": "vci.session_date",
            "operation": "epoch_seconds_to_calendar_date",
            "parameters": {"assumed_timezone": "UTC", "provider_stamps_daily_bars_at": "00:00:00Z"},
        },
        {
            "source_field": "vci.raw_open|high|low|close",
            "target_field": "vci.observed_open|high|low|close_vnd",
            "operation": "scale",
            "parameters": {"factor": 1, "rounding": "none"},
            "note": "identity scale; the pilot refuses to guess a unit it cannot observe",
        },
        {
            "source_field": "vci.raw_volume",
            "target_field": "vci.observed_daily_volume",
            "operation": "passthrough",
            "parameters": {"missing_policy": "preserve_null", "zero_fill": False},
        },
    ]

    normalized: list[dict[str, Any]] = []
    for row in raw_rows:
        epoch = int(row["vci.raw_t"])
        session_date = datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")
        normalized.append(
            {
                "vci.session_date": session_date,
                "vci.observed_open_vnd": float(row["vci.raw_open"]),
                "vci.observed_high_vnd": float(row["vci.raw_high"]),
                "vci.observed_low_vnd": float(row["vci.raw_low"]),
                "vci.observed_close_vnd": float(row["vci.raw_close"]),
                "vci.observed_daily_volume": row["vci.raw_volume"],
            }
        )

    dates = [row["vci.session_date"] for row in normalized]
    if len(set(dates)) != len(dates):
        raise VCIPilotError("normalize_daily_duplicate_session_dates")
    if dates != sorted(dates):
        raise VCIPilotError("normalize_daily_sessions_out_of_order")

    return {
        "schema_version": VERSION,
        "transformation_code_identity": TRANSFORMATION_CODE_IDENTITY,
        "transformations": transformations,
        "rows": normalized,
        "returned_date_range": [dates[0], dates[-1]],
        "resampling_applied": False,
        "forward_fill_applied": False,
        "invented_sessions": 0,
    }


# ---------------------------------------------------------------------------------
# HOSE tick lattice
# ---------------------------------------------------------------------------------


def hose_tick_size(price_vnd: float) -> int:
    """HOSE common-stock order price step, in VND.

    Bands as published by the exchange: under 10,000 -> 10; 10,000-49,950 -> 50;
    50,000 and above -> 100. This is an exchange trading rule, not a provider claim.
    """
    if price_vnd <= 0:
        raise VCIPilotError("tick_size_undefined_for_non_positive_price")
    if price_vnd < 10_000:
        return 10
    if price_vnd < 50_000:
        return 50
    return 100


def on_tick_lattice(price_vnd: float, *, tolerance: float = 1e-6) -> bool:
    """True when a price could have been an actual matched order price on HOSE."""
    step = hose_tick_size(price_vnd)
    remainder = abs(price_vnd) % step
    return remainder <= tolerance or abs(step - remainder) <= tolerance


def lattice_profile(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per-session lattice conformance for the four price fields."""
    if not rows:
        raise VCIPilotError("lattice_profile_received_no_rows")
    fields = (
        "vci.observed_open_vnd",
        "vci.observed_high_vnd",
        "vci.observed_low_vnd",
        "vci.observed_close_vnd",
    )
    sessions = []
    for row in rows:
        conforming = all(on_tick_lattice(float(row[field])) for field in fields)
        sessions.append({"session_date": row["vci.session_date"], "all_fields_on_lattice": conforming})
    on_lattice = sum(1 for item in sessions if item["all_fields_on_lattice"])
    return {
        "sessions": sessions,
        "sessions_total": len(sessions),
        "sessions_on_lattice": on_lattice,
        "sessions_off_lattice": len(sessions) - on_lattice,
    }


def lattice_boundary(rows: Sequence[Mapping[str, Any]]) -> str | None:
    """First session date of the maximal fully-on-lattice trailing run.

    ``None`` when every session conforms -- there is then no boundary to locate.
    """
    profile = lattice_profile(rows)["sessions"]
    index = len(profile)
    while index > 0 and profile[index - 1]["all_fields_on_lattice"]:
        index -= 1
    if index == 0 or index == len(profile):
        # Every session conforms, or none of the trailing ones do. Either way the
        # transition is not inside this window.
        return None
    return profile[index]["session_date"]


# ---------------------------------------------------------------------------------
# Price-basis qualification
# ---------------------------------------------------------------------------------


def classify_price_basis(
    *,
    lattice: Mapping[str, Any],
    boundary_date: str | None,
    qualified_events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Qualify the VCI price fields from lattice evidence plus already-qualified events.

    The reasoning is deductive, not a curve fit: a HOSE order can only match at a tick
    multiple, so a series carrying off-lattice prices cannot be the as-quoted series. The
    adjustment *dimension* is then read off which qualified event kinds sit at the
    boundary between the off-lattice prefix and the on-lattice suffix.

    ``qualified_events`` must be repository-qualified event records with ``ex_date``,
    ``kind`` in {``cash``, ``capital``} and an ``evidence_identity``. Event dates are never
    inferred from price behaviour here; they are an input.
    """
    if lattice["sessions_off_lattice"] == 0:
        return {
            "verdict": "inconclusive",
            "reason": "no_off_lattice_session_observed",
            "excludes_raw_unadjusted": False,
            "note": (
                "A fully on-lattice window is consistent with an unadjusted series but does "
                "not establish one; an adjusted series with no intervening event is "
                "indistinguishable from it."
            ),
            "boundary_date": None,
            "matched_events": [],
        }

    # An off-lattice price could not have been a matched order price, so whatever the
    # series is, it is not the as-quoted one. That exclusion holds even when the window
    # is too narrow to say which adjustment dimension produced it.
    if boundary_date is None:
        return {
            "verdict": "inconclusive",
            "reason": "adjustment_boundary_lies_outside_the_observed_window",
            "excludes_raw_unadjusted": True,
            "boundary_date": None,
            "matched_events": [],
        }

    matched = [
        dict(event)
        for event in qualified_events
        if str(event.get("ex_date")) == str(boundary_date)
    ]
    if not matched:
        return {
            "verdict": "mixed_or_context_dependent",
            "reason": "lattice_boundary_matches_no_qualified_event",
            "excludes_raw_unadjusted": True,
            "boundary_date": boundary_date,
            "matched_events": [],
        }
    for event in matched:
        if event.get("kind") not in {"cash", "capital"}:
            raise VCIPilotError(f"qualified_event_kind_unknown:{event.get('kind')}")
        if not str(event.get("evidence_identity", "")).strip():
            raise VCIPilotError("qualified_event_missing_evidence_identity")

    kinds = {event["kind"] for event in matched}
    if kinds == {"cash"}:
        verdict = "dividend_adjusted"
    elif kinds == {"capital"}:
        verdict = "split_adjusted"
    else:
        verdict = "split_and_dividend_adjusted"

    return {
        "verdict": verdict,
        "reason": "off_lattice_prefix_terminates_exactly_at_a_qualified_ex_date",
        "excludes_raw_unadjusted": True,
        "boundary_date": boundary_date,
        "matched_events": matched,
    }


def merge_price_verdicts(per_ticker: Mapping[str, Mapping[str, Any]]) -> str:
    """Combine per-ticker verdicts into one provider-level verdict, conservatively."""
    verdicts = {str(result["verdict"]) for result in per_ticker.values()}
    unknown = verdicts - PRICE_BASIS_VERDICTS
    if unknown:
        raise VCIPilotError(f"price_basis_verdict_not_in_vocabulary:{sorted(unknown)}")
    decisive = verdicts - {"inconclusive"}
    if not decisive:
        return "inconclusive"
    if decisive == {"dividend_adjusted"}:
        return "dividend_adjusted"
    if decisive == {"split_adjusted"}:
        return "split_adjusted"
    if decisive <= {"dividend_adjusted", "split_adjusted", "split_and_dividend_adjusted"}:
        # Distinct tickers demonstrating distinct dimensions is joint evidence about one
        # provider-wide series treatment, not a conflict.
        return "split_and_dividend_adjusted"
    return "mixed_or_context_dependent"


def apply_cross_provider_agreement(
    verdict: Mapping[str, Any], *, agreement: Mapping[str, Any]
) -> dict[str, Any]:
    """Record cross-provider agreement as compatibility evidence only.

    Agreement between two undocumented providers is evidence that they are interchangeable
    for a window, never evidence about what either one *means*. The verdict is returned
    unchanged and the fact of the comparison is attached.
    """
    result = dict(verdict)
    result["cross_provider_comparison"] = dict(agreement)
    result["cross_provider_comparison_upgraded_verdict"] = False
    return result


def apply_event_window_fit(
    verdict: Mapping[str, Any], *, fit: Mapping[str, Any]
) -> dict[str, Any]:
    """Record a numeric event-window fit without letting it establish semantics.

    A reverse-engineered factor can corroborate a verdict that already rests on other
    evidence; on its own it is a curve fit against a series whose contract is unknown.
    """
    result = dict(verdict)
    result["event_window_numeric_fit"] = dict(fit)
    result["event_window_fit_upgraded_verdict"] = False
    return result


# ---------------------------------------------------------------------------------
# Volume-basis qualification
# ---------------------------------------------------------------------------------


def reconcile_volume(
    *,
    daily_volume: int | None,
    intraday_quantities: Sequence[int],
    intraday_page_size: int,
    intraday_rows_returned: int,
    intraday_covers_full_session: bool,
) -> dict[str, Any]:
    """Compare a daily volume against a deterministic sum of observed intraday trades.

    Pagination completeness is checked *first*. An unfinished sample can only produce
    ``intraday_sample_incomplete``; it can never be read as proof that daily volume has a
    wider market scope than matched orders.
    """
    if daily_volume is None:
        return {
            "verdict": "scope_inconclusive",
            "reason": "daily_volume_missing_for_the_compared_session",
            "intraday_sum": None,
            "daily_volume": None,
        }
    intraday_sum = int(sum(int(quantity) for quantity in intraday_quantities))
    sample_complete = bool(intraday_covers_full_session) and intraday_rows_returned < intraday_page_size

    if not sample_complete:
        return {
            "verdict": "intraday_sample_incomplete",
            "reason": "pagination_or_session_coverage_not_exhausted",
            "intraday_sum": intraday_sum,
            "daily_volume": int(daily_volume),
            "difference": int(daily_volume) - intraday_sum,
            "note": (
                "A difference here carries no scope information. Excluding pagination is a "
                "precondition for any matched-versus-negotiated inference."
            ),
        }
    if intraday_sum == int(daily_volume):
        return {
            "verdict": "daily_equals_observed_intraday_sum",
            "intraday_sum": intraday_sum,
            "daily_volume": int(daily_volume),
            "difference": 0,
        }
    if intraday_sum and int(daily_volume) % intraday_sum == 0:
        return {
            "verdict": "unit_scaled_match",
            "intraday_sum": intraday_sum,
            "daily_volume": int(daily_volume),
            "implied_scale": int(daily_volume) // intraday_sum,
        }
    if int(daily_volume) > intraday_sum:
        return {
            "verdict": "daily_exceeds_observed_intraday_sum",
            "intraday_sum": intraday_sum,
            "daily_volume": int(daily_volume),
            "difference": int(daily_volume) - intraday_sum,
            "note": "Consistent with a wider scope, but also with any unobserved trade.",
        }
    return {
        "verdict": "scope_inconclusive",
        "reason": "daily_volume_below_observed_intraday_sum",
        "intraday_sum": intraday_sum,
        "daily_volume": int(daily_volume),
    }


def volume_basis_declaration(
    *,
    field_identity_qualified: bool,
    unit_verdict: str,
    adjustment_verdict: str,
    reconciliation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """The fail-closed provider-namespaced volume declaration.

    Market scope stays ``unknown`` unless a *source-level* statement qualifies it. No
    reconciliation outcome can set it, because every reconciliation outcome is consistent
    with more than one scope.
    """
    if unit_verdict not in {"qualified", "unknown"}:
        raise VCIPilotError(f"volume_unit_verdict_invalid:{unit_verdict}")
    if adjustment_verdict not in {"qualified", "unknown"}:
        raise VCIPilotError(f"volume_adjustment_verdict_invalid:{adjustment_verdict}")
    if reconciliation is not None and reconciliation.get("verdict") not in VOLUME_RECONCILIATION_VERDICTS:
        raise VCIPilotError("volume_reconciliation_verdict_invalid")
    return {
        "field": "vci.observed_daily_volume",
        "volume_field_identity": "qualified" if field_identity_qualified else "unknown",
        "volume_unit": unit_verdict,
        "volume_adjustment_basis": adjustment_verdict,
        "volume_market_scope": "unknown",
        "liquidity_actionable": False,
        "reconciliation": dict(reconciliation) if reconciliation else None,
        "unresolved_dimensions": [
            "matched_order_inclusion",
            "negotiated_put_through_inclusion",
            "auction_inclusion",
            "odd_lot_inclusion",
            "provider_revision_behaviour",
        ],
    }


# ---------------------------------------------------------------------------------
# Downstream eligibility and no-upgrade guards
# ---------------------------------------------------------------------------------

SHADOW_PRICE_CAPABILITIES = (
    "vci_namespaced_historical_returns",
    "vci_namespaced_technical_indicators",
    "controlled_source_comparison",
    "anomaly_detection",
    "isolated_shadow_evaluation",
)

SHADOW_VOLUME_CAPABILITIES = (
    "vci_namespaced_descriptive_volume_history",
    "vci_namespaced_volume_trend",
    "data_quality_comparison",
)

BLOCKED_CAPABILITIES = (
    "production_backtesting",
    "market_impact_models",
    "days_to_liquidate",
    "portfolio_sizing",
    "liquidity_based_position_sizing",
    "ranking",
    "recommendations",
    "price_targets",
    "official_exchange_claims",
    "adjustment_factors_for_another_source",
    "generic_adjusted_return_fields",
    "is_actionable",
    "production_artifact_replacement",
)


def downstream_eligibility(*, price_verdict: str, volume_declaration: Mapping[str, Any]) -> dict[str, Any]:
    """What a verdict unlocks. Production and actionability gates are unconditional."""
    if price_verdict not in PRICE_BASIS_VERDICTS:
        raise VCIPilotError(f"price_basis_verdict_not_in_vocabulary:{price_verdict}")
    price_qualified = price_verdict not in {"inconclusive", "mixed_or_context_dependent"}
    volume_partial = volume_declaration.get("volume_field_identity") == "qualified"
    return {
        "unlocked_shadow_price_capabilities": list(SHADOW_PRICE_CAPABILITIES) if price_qualified else [],
        "unlocked_shadow_volume_capabilities": list(SHADOW_VOLUME_CAPABILITIES) if volume_partial else [],
        "blocked_capabilities": list(BLOCKED_CAPABILITIES),
        "production_gate": "closed",
        "actionability_gate": "closed",
        "liquidity_actionable": False,
        "scope": "vci_namespaced_shadow_only",
    }


def assert_no_generic_upgrade(record: Mapping[str, Any]) -> Mapping[str, Any]:
    """Reject any attempt to write a generic or foreign-provider field from this pilot."""
    for key in record:
        name = str(key)
        if name in FORBIDDEN_GENERIC_FIELDS:
            raise VCIPilotError(f"generic_field_upgrade_forbidden:{name}")
        if "." in name and not name.startswith("vci."):
            raise VCIPilotError(f"foreign_provider_namespace_forbidden:{name}")
    return record


def assert_verdict_scope(verdict_record: Mapping[str, Any]) -> Mapping[str, Any]:
    """A VCI verdict must name VCI and must not claim any other authority."""
    if verdict_record.get("provider") != PROVIDER:
        raise VCIPilotError("verdict_provider_must_be_vci")
    if verdict_record.get("source_authority") != SOURCE_AUTHORITY:
        raise VCIPilotError("verdict_must_declare_observed_public_web_endpoint_authority")
    for foreign in ("TCBS", "KBS", "HOSE", "VNSTOCK_STORED"):
        if verdict_record.get(f"upgrades_{foreign.lower()}"):
            raise VCIPilotError(f"verdict_must_not_upgrade:{foreign}")
    return verdict_record


# ---------------------------------------------------------------------------------
# Observation record
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
    "qualification_verdict",
    "unresolved_semantic_dimensions",
)


def build_observation(**kwargs: Any) -> dict[str, Any]:
    """Assemble one evidence record, refusing to persist an incomplete or unsafe one."""
    missing = [field for field in _OBSERVATION_FIELDS if field not in kwargs]
    if missing:
        raise VCIPilotError(f"observation_fields_missing:{','.join(missing)}")
    record = {field: kwargs[field] for field in _OBSERVATION_FIELDS}
    if record["provider"] != PROVIDER:
        raise VCIPilotError("observation_provider_must_be_vci")
    assert_endpoint_in_scope(str(record["endpoint"]))
    assert_ticker_in_scope(str(record["ticker"]))
    record["request_headers_redacted"] = redact_headers(record["request_headers_redacted"])
    leaked = _find_sensitive_leak(record)
    if leaked:
        raise VCIPilotError(f"observation_contains_sensitive_material:{leaked}")
    record["schema_version"] = VERSION
    return record


def _find_sensitive_leak(node: Any, path: str = "") -> str | None:
    """Depth-first search for an unredacted sensitive key anywhere in a record."""
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


# ---------------------------------------------------------------------------------
# Live acquisition -- the only network-touching function in this module
# ---------------------------------------------------------------------------------


def classify_failure(*, exception: BaseException | None, status: int | None, body: Any) -> str:
    """Name why a bounded attempt did not yield a usable payload."""
    if exception is not None:
        name = type(exception).__name__
        if "Timeout" in name or "ConnectionError" in name:
            return "source_unavailable"
        if isinstance(exception, VCIPilotError):
            message = str(exception)
            if "symbol_mismatch" in message:
                return "symbol_unsupported"
            if "schema" in message or "arrays" in message or "not_a_list" in message:
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
    endpoint: str,
    payload: Mapping[str, Any],
    session: Any,
    headers: Mapping[str, str],
    timeout: tuple[float, float] = (5.0, 20.0),
    max_attempts: int = 2,
) -> dict[str, Any]:
    """Issue one bounded POST and return the raw bytes plus transport facts.

    Redirects are never followed automatically: each hop is inspected against the provider
    boundary first. Nothing is parsed here -- the caller hashes and stores the bytes before
    any interpretation happens.
    """
    assert_endpoint_in_scope(endpoint)
    redirect_count = 0
    retry_count = 0
    last_error: BaseException | None = None
    url = endpoint

    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            retry_count += 1
        try:
            response = session.post(
                url, json=dict(payload), headers=dict(headers), timeout=timeout, allow_redirects=False
            )
        except Exception as exc:  # noqa: BLE001 -- classified, not swallowed
            last_error = exc
            continue

        while response.status_code in (301, 302, 303, 307, 308) and redirect_count < 3:
            location = response.headers.get("Location")
            assert_redirect_within_boundary(location)
            redirect_count += 1
            response = session.post(
                location, json=dict(payload), headers=dict(headers), timeout=timeout, allow_redirects=False
            )

        return {
            "http_status": response.status_code,
            "redirect_count": redirect_count,
            "retry_count": retry_count,
            "raw_body": response.content,
            "response_headers_redacted": redact_headers(dict(response.headers)),
            "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }

    raise VCIPilotError(f"acquisition_failed:{classify_failure(exception=last_error, status=None, body=None)}")
