"""Current-state relative valuation: qualified DNSE current-session price times
official-evidence current common shares outstanding, against already-qualified
historical (annual) canonical financial denominators.

WHAT THIS IS, IN ONE LINE
    market_cap = current_price(DNSE, as_of_session) x current_shares_outstanding
    (share_transition_bridge, official evidence only); every multiple derives from
    that one market_cap plus already-qualified canonical financial facts.

WHY THIS IS NOT "historical_relative_valuation_snapshot.md" AND NOT relative_valuation.py's
OWN price/period alignment check
    relative_valuation.evaluate_relative_valuation() requires
    ``current_price["financial_period"] == financial[metric]["period_identity"]["period"]``
    for every multiple -- a deliberate guard against silently mixing a price from one
    period with fundamentals from another. That guard is correct for a *historical*
    point-in-time valuation (price and fundamentals both dated to the same period-end),
    which is the only thing that contract computes today. This module computes a
    different, complementary thing on purpose: a *current* market price against the
    *latest genuinely qualified historical* financial period -- by construction the two
    periods differ. Every result this module produces is therefore explicitly labelled
    ``as_of_semantics = "current_market_price_on_qualified_historical_fundamentals"``,
    never called "TTM", "forward", or "current earnings valuation", and is never fed
    back into relative_valuation.py or presented as one of its methods. This is a
    smaller, sibling module reusing the same formula shapes and vocabulary field names
    (mirroring the "current_state_X.py adapter beside the PIT-labelled original"
    pattern already established by dnse_current_state_price_analytics.py and
    dnse_current_state_market_risk.py), not a modification of relative_valuation.py.

WHY ONE SHARE COUNT, NOT relative_valuation.py's period-end/weighted-average SPLIT
    The historical snapshot needs two distinct share identities (weighted-average
    basic for P/E's EPS-style numerator, period-end for P/B's balance-sheet-date
    numerator) because it relates one *completed* reporting period's price to that
    *same* period's flow/stock figures. A "weighted-average share count for the
    still-open current period" is not a coherent concept -- there is no completed
    period to weight across. This module therefore uses exactly one current share
    count (current common shares outstanding, right now) for every metric's market
    cap, which is also the standard real-world convention for a current trailing
    multiple (today's market cap over a trailing/most-recent-qualified financial
    figure). This is a deliberate simplification relative to relative_valuation.py,
    not an oversight.

CURRENT PRICE -- REUSED, NEVER RECOMPUTED, NEVER FETCHED
    Reads dnse_current_state_price_analytics.build_current_state_price_analytics_from_evidence_store()
    (the same, already-qualified, closed capability that also feeds
    tickers[ticker].current_state_price_analytics) and uses its own
    ``as_of_session``/``price_basis``/``coverage``/``eligibility`` verbatim. No network
    call, no new evidence, no formula recomputed. Ticker eligibility is the exact same
    evidence-bounded gate (``dnse_ohlc_price_basis_capability.current_state_eligibility``)
    -- currently HPG, VCB -- reused, not re-derived.

    PRICE UNIT: DNSE's raw OHLC close values are empirically thousands-of-VND, the
    same scale already established and named ``PRICE_UNIT = "thousands_of_vnd"`` in
    ``dnse_bid_ask_capability.py`` (cross-checked there against vn_stock.db). Verified
    again directly for this module: vn_stock.db's HPG close on 2026-08-07 is
    22000.0 VND; the retained DNSE evidence's close for the same session is 22 --
    an exact x1000 match. ``dnse_current_state_price_analytics.py`` never needed this
    conversion (its own outputs -- returns, volatility, drawdown, RSI, SMA -- are all
    scale-invariant ratios); this module is the first DNSE current-state consumer that
    needs an absolute VND price, so the conversion is applied here, once, explicitly.

CURRENT SHARES -- share_transition_bridge.py, OFFICIAL EVIDENCE ONLY, NEVER VENDOR METADATA
    Deliberately does NOT use market_wide_current_shares_resolver.py, even though that
    module's own "qualified_official" lane currently reports HPG as qualified for a
    session as late as 2026-08-07. That lane's coverage bar is: an official anchor,
    corroborated by an independent (vendor) observation *on or after the anchor*, with
    no later share-changing event *on record* -- which extrapolates a corroboration
    dated 2026-07-30 forward to any later session indefinitely, never requiring the
    corroboration itself to reach the session being resolved. That is exactly the
    "infer continued validity beyond proven event/coverage dates" pattern this
    milestone was explicitly told not to do. share_transition_bridge.resolve_share_transition
    is stricter and is the one this milestone was explicitly told to reuse: it requires
    an explicit ``coverage_through`` that must itself reach ``target_date`` (the DNSE
    price's own ``as_of_session``) before ``current_shares.qualified`` is ever True.

    ``resolve_share_transition`` has no existing caller in this repository (grep-verified
    -- only its own test module calls it); this module is its first production wiring,
    via two small adapters:
      - ``opening``: the ticker's earliest annual ``period_end_shares_outstanding``
        citation from ``data/official-evidence/share_basis_citations.jsonl``, loaded
        through ``semantic_evidence_bridge.load_verified_share_basis`` -- the existing,
        hash-verifying, manifest-cross-checked loader, completely unmodified.
      - ``events``: citations with ``identity_type == "current_shares_outstanding_after_event"``
        in the same file, read directly (see "A REAL, PRE-EXISTING GAP" below for why),
        each translated into ``resolve_share_transition``'s event shape.

    ``coverage_through`` is derived honestly, never invented: the latest
    ``corroborated_on`` date carried by any of the ticker's promoted event citations
    (an independent vendor snapshot re-checking the official anchor still held), or the
    opening identity's own effective date when no event/corroboration exists at all.
    This milestone performs no new corroboration check of its own (no network call).

A REAL, PRE-EXISTING GAP DISCOVERED (NOT CAUSED, NOT FIXED, BY THIS MILESTONE)
    ``semantic_evidence_bridge.load_verified_share_basis``'s ``_SUPPORTED_SHARE_IDENTITIES``
    is exactly ``{period_end_shares_outstanding, weighted_average_basic_shares_outstanding,
    weighted_average_diluted_shares_outstanding}`` -- it does not include
    ``current_shares_outstanding_after_event`` at all, so that loader was never able to
    serve this module's ``events`` side regardless of any other gap. Separately and more
    fundamentally: HPG's own ``period_end_shares_outstanding`` (and
    ``weighted_average_basic_shares_outstanding``) citation's ``evidence_id``
    (``a7c3711d1b02c131a87fef4a0f5bd4d5fbd780bbb0c07665111a358a2ddcd2a8``, the flat
    top-level ``data/official-evidence/hpg-consolidated-fy2024-audited.pdf``) is absent
    from ``data/official-evidence/manifest.json``'s 11 records entirely (verified
    directly, both by reading the manifest and by running
    ``load_verified_share_basis`` against the real runtime root: every HPG/VNM/VCB
    share-basis citation rejects with ``evidence_missing_or_hash_mismatch``). This
    module discovered this by reusing the loader honestly, not by inventing a check;
    it does not repair the manifest (an evidence-registry write, `evidence_promotion.py`'s
    exclusive domain, out of this milestone's scope) and does not work around it with a
    weaker bespoke re-verification of the opening identity -- the opening leg fails
    closed through the exact same loader every other qualified-share-basis consumer in
    this repository already depends on (``_relative_valuation_period_end_share_count``,
    ``_relative_valuation_weighted_average_share_count``, ``_net_net_share_count``,
    ``corporate_action_ledger.py``), so this is a shared, pre-existing gap, not a new
    one this module introduces or hides.

FINANCIAL DENOMINATORS -- REUSED VERBATIM, NEVER RE-QUALIFIED HERE
    This module takes an already-built ``financial`` mapping (the exact
    ``export_ai_bundle._financial_input(financial_canonical.get(ticker))`` shape already
    fed to ``evaluate_relative_valuation``/``evaluate_intrinsic_valuation``) as an input,
    and reuses ``relative_valuation._qualified``/``relative_valuation._number`` verbatim
    to validate each denominator -- the exact same qualification predicate the existing
    historical contract trusts, not a re-derived one. It never re-derives, re-fetches, or
    promotes a financial fact.

TEMPORAL LABELLING
    Every method carries ``as_of_semantics = AS_OF_SEMANTICS`` (never "TTM", "forward",
    or "current earnings valuation" -- none of those are independently qualified here),
    ``historical_only = False`` (the price is current), ``market_dependent = True``, and
    ``is_actionable = False`` always -- matching the newer DNSE current-state family's
    own convention (current_state_market_risk, qualified_market_observations: always
    False regardless of qualification, a descriptive-fact signal, not a data-quality
    flag) rather than relative_valuation.py's data-quality-flag usage of the same field
    name, because a valuation multiple is exactly the kind of number most likely to be
    misread as an actionable signal.

NAMING -- DELIBERATELY NOT "current_valuation"
    ``tickers[ticker].ticker_capability_matrix.market_actionable.current_valuation`` is
    an already-existing, unrelated, market-wide GENERIC capability-status slot (from
    ``market_basis_capability_registry.py``, requiring generic ``qualified_raw_price``
    and ``valuation_identity`` capabilities across the whole universe) -- it is not this
    module and this module does not change it (it correctly stays "blocked" as a
    generic, market-wide claim, independent of this evidence-bounded HPG lane). This
    module's own bundle key is ``current_state_relative_valuation``, matching the
    existing ``current_state_market_risk``/``current_state_price_analytics`` naming
    family exactly, to avoid exactly this collision.

NO NETWORK I/O, NO PRODUCTION WRITE
    Pure functions of their arguments plus read-only JSONL/loader calls under
    ``runtime_root``. Never writes to ``vn_stock.db`` or any evidence file.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import dnse_ohlc_price_basis_capability as price_basis_capability
from dnse_current_state_price_analytics import (
    STATUS_QUALIFIED as DNSE_PRICE_STATUS_QUALIFIED,
    build_current_state_price_analytics_from_evidence_store,
)
from relative_valuation import _number as _rv_number, _qualified as _rv_qualified
from semantic_evidence_bridge import load_verified_share_basis
from share_transition_bridge import resolve_share_transition

VERSION = "1.0.0"
PROVIDER = "DNSE"

# Empirically established thousands-of-VND scale; see module docstring. Same string
# already used by dnse_bid_ask_capability.PRICE_UNIT for the same empirical reason.
PRICE_UNIT = "thousands_of_vnd"
PRICE_UNIT_TO_VND = 1000

AS_OF_SEMANTICS = "current_market_price_on_qualified_historical_fundamentals"
FORMULA_VERSION = "current_state_relative_valuation_v1_current_price_x_official_current_shares"

METHODS = ("market_cap", "pe", "pb", "ps", "enterprise_value", "ev_sales", "ev_ebitda")
_DENOMINATOR_METRIC = {"pe": "net_income", "pb": "shareholders_equity", "ps": "revenue",
                        "ev_sales": "revenue", "ev_ebitda": "ebitda"}
_EV_METHODS = ("enterprise_value", "ev_sales", "ev_ebitda")
_SHARE_BASIS_RELATIVE = Path("data") / "official-evidence" / "share_basis_citations.jsonl"
_EVENT_IDENTITY_TYPE = "current_shares_outstanding_after_event"

STATUS_QUALIFIED = "QUALIFIED_FOR_CURRENT_STATE_RELATIVE_VALUATION"
STATUS_NOT_QUALIFIED = "NOT_QUALIFIED_FOR_CURRENT_STATE_RELATIVE_VALUATION"


# --------------------------------------------------------------------- current price

def resolve_current_price(
    ticker: str, *, runtime_root: Path | str, reference_session_date: str | None = None,
) -> dict[str, Any]:
    """The qualified DNSE current-state price, reused verbatim from the already-closed
    price-analytics capability. Never fetches, never recomputes eligibility/coverage."""
    report = build_current_state_price_analytics_from_evidence_store(
        ticker, runtime_root=runtime_root, reference_session_date=reference_session_date,
        include_technical_indicators=False,
    )
    coverage = report.get("coverage") or {}
    observations = report.get("observations") or []
    qualified = (
        report.get("status") == DNSE_PRICE_STATUS_QUALIFIED
        and coverage.get("status") == "complete"
        and bool(observations)
    )
    base = {
        "qualified": qualified,
        "as_of_session": report.get("as_of_session"),
        "status": report.get("status"),
        "coverage": coverage,
        "eligibility": report.get("eligibility"),
        "price_basis": report.get("price_basis"),
        "price_basis_contract_version": report.get("price_basis_contract_version"),
        "source": PROVIDER,
        "analysis_time_semantics": report.get("analysis_time_semantics"),
        "pit_backtest_eligible": report.get("pit_backtest_eligible"),
        "provenance": report.get("provenance"),
        "warnings": list(report.get("warnings") or []),
        "raw_close": None,
        "price_unit": PRICE_UNIT,
        "value_vnd": None,
    }
    if not qualified:
        return base
    latest = observations[-1]
    base["raw_close"] = latest["close"]
    base["value_vnd"] = latest["close"] * PRICE_UNIT_TO_VND
    return base


# --------------------------------------------------------------------- current shares

def _load_share_basis_event_rows(runtime_root: Path | str, ticker: str) -> list[dict[str, Any]]:
    """Raw ``current_shares_outstanding_after_event`` rows for ``ticker`` from
    ``share_basis_citations.jsonl``, read directly. ``load_verified_share_basis``
    cannot serve this identity type -- see module docstring, "A REAL, PRE-EXISTING
    GAP". Malformed lines are skipped, never fabricated or repaired."""
    path = Path(runtime_root) / _SHARE_BASIS_RELATIVE
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (isinstance(row, dict) and row.get("ticker") == ticker
                and row.get("identity_type") == _EVENT_IDENTITY_TYPE):
            rows.append(row)
    return rows


def _map_event_row_to_bridge_event(row: Mapping[str, Any]) -> dict[str, Any] | None:
    """Translate one promoted ``current_shares_outstanding_after_event`` citation into
    ``share_transition_bridge.resolve_share_transition``'s event shape.

    This is descriptive relabelling of an already-qualified fact (evidence_promotion.py
    already required the underlying corporate action to be executed/qualified before
    admitting this citation type -- see official_corporate_action_ledger.py), never new
    evidence. ``lifecycle`` is set to "completed" unconditionally because this identity
    type, by construction, only ever exists for an event whose resulting share count was
    already promoted as a completed fact -- there is no "proposed"/"announced" variant
    of this identity type to confuse it with. ``opening_shares`` is left unstated
    (``None``): this citation does not itself state the pre-event count, and
    ``resolve_share_transition`` correctly treats an unstated ``opening_shares`` as "no
    conflict asserted", never as silent agreement.
    """
    required = ("event_id", "effective_date", "event_type", "value", "citation_id",
                "source_content_hashes", "share_class", "unit", "ticker")
    if not all(key in row for key in required):
        return None
    value = row.get("value")
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return None
    hashes = row.get("source_content_hashes")
    source_hash = hashes[0] if isinstance(hashes, list) and hashes and isinstance(hashes[0], str) else None
    if not source_hash or not isinstance(row.get("citation_id"), str) or not row["citation_id"]:
        return None
    resulting_identity_type = (
        "common_outstanding_shares"
        if row.get("share_class") == "common_outstanding" and row.get("unit") == "shares"
        else None
    )
    return {
        "event_id": row["event_id"],
        "effective_date": row["effective_date"],
        "action_type": row["event_type"],
        "lifecycle": "completed",
        "opening_shares": None,
        "resulting_shares": value,
        "resulting_identity_type": resulting_identity_type,
        "unit": row.get("unit"),
        "identity_scope": "issuer",
        "ratio": None,
        "qualification": "qualified",
        "source_hash": source_hash,
        "citation_id": row["citation_id"],
    }


def _resolve_opening_identity(
    runtime_root: Path | str, ticker: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """The earliest annual ``period_end_shares_outstanding`` citation for ``ticker``,
    shaped for ``resolve_share_transition``'s ``opening`` parameter -- via
    ``load_verified_share_basis``, the existing, hash-verifying, manifest-cross-checked
    loader, completely unmodified. Returns ``(None, verified)`` (never fabricates an
    opening) when nothing verifies; the caller inspects ``verified["rejected"]`` for the
    specific reason."""
    verified = load_verified_share_basis(runtime_root)
    candidates = [entry for key, entry in verified.get("by_identity", {}).items()
                  if key[0] == ticker and key[1] == "period_end_shares_outstanding"
                  and entry.get("reporting_frequency") == "annual"]
    if not candidates:
        return None, verified
    entry = min(candidates, key=lambda e: str(e["reporting_period"]))
    period = str(entry["reporting_period"])
    opening = {
        "value": int(entry["value"]),
        # Annual reporting_period "YYYY" -> fiscal year-end date, the same convention
        # already established by historical_relative_valuation_snapshot.md and
        # hpg_fy2024_ebitda_qualification.md for this exact citation family.
        "effective_date": f"{period}-12-31",
        "unit": entry.get("unit") or "shares",
        "share_class": entry.get("share_class") or "common_outstanding",
        "identity_scope": "issuer",
        "qualification": "qualified",
        "source_hash": entry.get("evidence_id"),
        "citation_id": entry.get("citation_id"),
    }
    return opening, verified


def _explain_opening_unavailable(verified_share_basis: Mapping[str, Any], ticker: str) -> dict[str, Any]:
    for rejection in verified_share_basis.get("rejected", []):
        key = rejection.get("key")
        if isinstance(key, (list, tuple)) and len(key) == 3 and key[0] == ticker and key[1] == "period_end_shares_outstanding":
            return {
                "reason": "official_evidence_share_basis_unverifiable",
                "detail": rejection.get("reason"),
                "note": ("semantic_evidence_bridge.load_verified_share_basis could not "
                         "hash-verify this ticker's period-end share-count citation "
                         "against data/official-evidence/manifest.json -- a pre-existing "
                         "evidence-registration gap this module discovered but does not "
                         "fix (see module docstring, 'A REAL, PRE-EXISTING GAP')."),
            }
    return {"reason": "no_period_end_share_basis_citation_retained_for_ticker", "detail": None, "note": None}


def _resolve_coverage_through(event_rows: Sequence[Mapping[str, Any]], opening_effective_date: str) -> str:
    """The latest date this repository has explicit, retained evidence that no further
    share-changing event occurred for this ticker -- never inferred forward from an
    event's own effective_date, and never from today's wall clock (no new corroboration
    check is performed here). Falls back to the opening identity's own effective date
    (no forward coverage claim at all) when no event citation carries a
    ``corroborated_on`` date."""
    candidates = [opening_effective_date]
    for row in event_rows:
        corroborated_on = row.get("corroborated_on")
        if isinstance(corroborated_on, str) and corroborated_on:
            candidates.append(corroborated_on)
    return max(candidates)


def resolve_current_shares(
    runtime_root: Path | str, ticker: str, target_date: str,
) -> dict[str, Any]:
    """Current common shares outstanding for ``ticker`` as of ``target_date``, via
    ``share_transition_bridge.resolve_share_transition`` fed only by official evidence.
    Never uses vendor/metadata shares_outstanding, and never infers coverage beyond a
    proven date. See module docstring for the full rationale."""
    opening, verified_share_basis = _resolve_opening_identity(runtime_root, ticker)
    opening_diagnostic = None if opening is not None else _explain_opening_unavailable(verified_share_basis, ticker)
    raw_event_rows = _load_share_basis_event_rows(runtime_root, ticker)
    mapped_events = [event for event in (_map_event_row_to_bridge_event(row) for row in raw_event_rows)
                      if event is not None]
    effective_opening = opening if opening is not None else {}
    coverage_through = _resolve_coverage_through(
        raw_event_rows, (opening or {}).get("effective_date") or "0001-01-01",
    )
    bridge_result = resolve_share_transition(
        effective_opening, mapped_events, target_date=target_date, coverage_through=coverage_through,
    )
    return {
        "bridge_result": bridge_result,
        "opening_identity": opening,
        "opening_identity_diagnostic": opening_diagnostic,
        "coverage_through": coverage_through,
        "raw_event_citation_count": len(raw_event_rows),
        "mapped_event_count": len(mapped_events),
        "target_date": target_date,
    }


# --------------------------------------------------------------------- metric envelope

def _base_method(name: str, state: str = "unavailable", **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "method": name,
        "method_version": FORMULA_VERSION,
        "state": state,
        "as_of_semantics": AS_OF_SEMANTICS,
        "historical_only": False,
        "market_dependent": True,
        "is_actionable": False,
        "observed_value": None,
        "numerator_identity": None,
        "denominator_identity": None,
        "financial_period": None,
        "statement_scope": None,
        "price_as_of_session": None,
        "share_effective_date": None,
        "share_coverage_status": None,
        "source": None,
        "provenance": {},
        "missing_inputs": [],
        "warnings": [],
        "limitations": [
            "No target price, recommendation, or cheap/expensive conclusion is produced by this contract.",
            "This multiple mixes a current market price with an older qualified financial "
            "period; it is not a TTM, forward, or current-earnings valuation.",
        ],
        "qualification_status": "unavailable",
    }
    result.update(extra)
    return result


def _missing_inputs_for(price_ok: bool, shares_ok: bool) -> list[str]:
    missing = []
    if not price_ok:
        missing.append("qualified_current_price")
    if not shares_ok:
        missing.append("qualified_current_shares_outstanding_for_session")
    return missing


def evaluate_current_state_relative_valuation(
    ticker: str,
    *,
    runtime_root: Path | str,
    financial: Mapping[str, Any],
    entity_type: str = "unknown",
    reference_session_date: str | None = None,
    historical_relative_valuation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate the current-state relative valuation lane for ``ticker``.

    Always returns a dict; never raises for an ineligible/unqualified ticker (an
    expected, common outcome carried in ``status``, not an error). ``historical_relative_valuation``
    is the ticker's own ``relative_valuation`` bundle section (relative_valuation.py's
    output), passed straight through to ``evaluate_historical_comparability`` -- never
    recomputed here. Omit it (or pass ``None``) to always get ``incomparable``.
    """
    normalized_ticker = str(ticker).strip().upper()
    eligibility = price_basis_capability.current_state_eligibility(normalized_ticker)
    envelope: dict[str, Any] = {
        "schema_version": VERSION,
        "ticker": normalized_ticker,
        "source": PROVIDER,
        "as_of_semantics": AS_OF_SEMANTICS,
        "formula_version": FORMULA_VERSION,
        "is_actionable": False,
        "eligibility": eligibility,
        "current_price": None,
        "current_shares": None,
        "methods": {name: _base_method(name) for name in METHODS},
        "historical_comparison": {"status": "not_attempted", "reasons": ["current_valuation_not_qualified"], "comparisons": {}},
        "warnings": list(price_basis_capability.WARNINGS),
        "limitations": [],
    }
    if not eligibility["eligible_for_current_state_price_analytics"]:
        envelope["status"] = STATUS_NOT_QUALIFIED
        envelope["historical_comparison"] = evaluate_historical_comparability(
            envelope["methods"], historical_relative_valuation,
        )
        return envelope

    price = resolve_current_price(normalized_ticker, runtime_root=runtime_root, reference_session_date=reference_session_date)
    envelope["current_price"] = price
    price_ok = price["qualified"]

    shares_result: dict[str, Any] | None = None
    shares_ok = False
    shares_value: int | None = None
    if price_ok:
        shares_result = resolve_current_shares(runtime_root, normalized_ticker, price["as_of_session"])
        envelope["current_shares"] = shares_result
        bridge_current = shares_result["bridge_result"]["current_shares"]
        shares_ok = bool(bridge_current.get("qualified"))
        shares_value = bridge_current.get("value") if shares_ok else None

    market_cap_value = (
        price["value_vnd"] * shares_value
        if price_ok and shares_ok and isinstance(shares_value, int)
        else None
    )
    price_session = price.get("as_of_session")
    share_effective_date = None
    if shares_result is not None:
        bridge = shares_result["bridge_result"]
        if shares_ok:
            # Qualified current means the bridge proved coverage exactly through
            # target_date, so that is the effective date of the value being used.
            share_effective_date = bridge.get("target_date")
        else:
            # Not qualified as current: surface the latest historical identity's own
            # effective date for lineage/context only -- never used as a current value.
            latest_identity = bridge.get("latest_qualified_identity") or {}
            share_effective_date = latest_identity.get("effective_date")
    share_coverage_status = shares_result["bridge_result"]["status"] if shares_result else None

    methods: dict[str, dict[str, Any]] = {}
    ev_inapplicable = entity_type in {"bank", "securities"}

    # market_cap
    if market_cap_value is not None:
        methods["market_cap"] = _base_method(
            "market_cap", "available", observed_value=market_cap_value,
            numerator_identity="current_price_x_official_current_shares_outstanding",
            price_as_of_session=price_session, share_effective_date=share_effective_date,
            share_coverage_status=share_coverage_status, source=PROVIDER,
            qualification_status="qualified",
            provenance={"current_price": price, "current_shares": shares_result},
        )
    else:
        methods["market_cap"] = _base_method(
            "market_cap", "unavailable", missing_inputs=_missing_inputs_for(price_ok, shares_ok),
            price_as_of_session=price_session, share_effective_date=share_effective_date,
            share_coverage_status=share_coverage_status,
            provenance={"current_price": price, "current_shares": shares_result},
        )

    for name in ("pe", "pb", "ps"):
        metric = _DENOMINATOR_METRIC[name]
        denominator, missing = _rv_qualified(financial.get(metric), metric)
        period = (financial.get(metric) or {}).get("period_identity")
        scope = (financial.get(metric) or {}).get("statement_scope")
        if market_cap_value is None or denominator is None or denominator <= 0:
            state = "incomparable" if (denominator is not None and denominator < 0) else "unavailable"
            combined = _missing_inputs_for(price_ok, shares_ok) + missing
            if denominator is not None and denominator == 0:
                combined = combined + ["positive_denominator_required"]
            methods[name] = _base_method(
                name, state, missing_inputs=combined, denominator_identity=metric,
                financial_period=period, statement_scope=scope,
                price_as_of_session=price_session, share_effective_date=share_effective_date,
                share_coverage_status=share_coverage_status,
                warnings=["negative_or_zero_denominator_not_normalized"] if state == "incomparable" else [],
            )
            continue
        methods[name] = _base_method(
            name, "available", observed_value=market_cap_value / denominator,
            numerator_identity="current_market_cap", denominator_identity=metric,
            financial_period=period, statement_scope=scope,
            price_as_of_session=price_session, share_effective_date=share_effective_date,
            share_coverage_status=share_coverage_status, source=PROVIDER,
            qualification_status="qualified",
            provenance={"current_price": price, "current_shares": shares_result, "financial": dict(financial[metric])},
        )

    debt, debt_missing = _rv_qualified(financial.get("total_debt"), "total_debt")
    cash, cash_missing = _rv_qualified(financial.get("cash_and_equivalents"), "cash_and_equivalents")
    ev_value = (
        market_cap_value + debt - cash
        if market_cap_value is not None and debt is not None and cash is not None
        else None
    )
    for name in _EV_METHODS:
        if ev_inapplicable:
            methods[name] = _base_method(
                name, "inapplicable",
                warnings=["enterprise_value_method_not_qualified_for_non_corporate_financial_archetype"],
            )
            continue
        if name == "enterprise_value":
            if ev_value is not None:
                methods[name] = _base_method(
                    name, "available", observed_value=ev_value,
                    numerator_identity="current_market_cap_plus_total_debt_minus_cash",
                    price_as_of_session=price_session, share_effective_date=share_effective_date,
                    share_coverage_status=share_coverage_status, source=PROVIDER,
                    qualification_status="qualified",
                    provenance={"current_price": price, "current_shares": shares_result,
                                "debt": financial.get("total_debt"), "cash": financial.get("cash_and_equivalents")},
                )
            else:
                methods[name] = _base_method(
                    name, "unavailable",
                    missing_inputs=_missing_inputs_for(price_ok, shares_ok) + debt_missing + cash_missing,
                    price_as_of_session=price_session, share_effective_date=share_effective_date,
                    share_coverage_status=share_coverage_status,
                    warnings=["enterprise_value_semantics_or_inputs_unqualified"],
                )
            continue
        metric = _DENOMINATOR_METRIC[name]
        denominator, missing = _rv_qualified(financial.get(metric), metric)
        if ev_value is None or denominator is None or denominator <= 0:
            state = "incomparable" if (denominator is not None and denominator < 0) else "unavailable"
            methods[name] = _base_method(
                name, state,
                missing_inputs=_missing_inputs_for(price_ok, shares_ok) + debt_missing + cash_missing + missing,
                denominator_identity=metric,
                price_as_of_session=price_session, share_effective_date=share_effective_date,
                share_coverage_status=share_coverage_status,
                warnings=["enterprise_value_semantics_or_inputs_unqualified"],
            )
            continue
        methods[name] = _base_method(
            name, "available", observed_value=ev_value / denominator,
            numerator_identity="current_enterprise_value", denominator_identity=metric,
            financial_period=financial[metric].get("period_identity"), statement_scope=financial[metric].get("statement_scope"),
            price_as_of_session=price_session, share_effective_date=share_effective_date,
            share_coverage_status=share_coverage_status, source=PROVIDER,
            qualification_status="qualified",
            provenance={"current_price": price, "current_shares": shares_result,
                        "debt": financial.get("total_debt"), "cash": financial.get("cash_and_equivalents"),
                        "financial": dict(financial[metric])},
        )

    envelope["methods"] = methods
    envelope["status"] = STATUS_QUALIFIED if any(m["state"] == "available" for m in methods.values()) else STATUS_NOT_QUALIFIED
    envelope["historical_comparison"] = evaluate_historical_comparability(methods, historical_relative_valuation)
    return envelope


# --------------------------------------------------------------------- historical comparison

def evaluate_historical_comparability(
    current_methods: Mapping[str, Mapping[str, Any]],
    historical_relative_valuation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Deterministic current-vs-historical valuation comparison.

    Reads the Producer's own, separately-maintained ``relative_valuation`` bundle
    section for this ticker (the one existing historical valuation checkpoint
    contract -- relative_valuation.py, historical_relative_valuation_snapshot.md) and
    never recomputes or re-derives a historical multiple. A method is ``comparable``
    only when both sides are ``state == "available"``, share the same
    ``denominator_identity`` and ``statement_scope``, and the historical side is
    explicitly marked ``historical_only``. Otherwise ``incomparable`` with reasons.
    Never emits a "cheap"/"expensive"/target-price/expected-return conclusion --
    only a raw, labelled multiple delta.
    """
    historical_methods = (historical_relative_valuation or {}).get("methods") or {}
    comparisons: dict[str, Any] = {}
    for name in ("pe", "pb", "ps", "ev_sales", "ev_ebitda"):
        current = current_methods.get(name) or {}
        historical = historical_methods.get(name) or {}
        if current.get("state") != "available":
            comparisons[name] = {"status": "incomparable", "reasons": ["current_metric_unavailable"]}
            continue
        if historical.get("state") != "available":
            comparisons[name] = {
                "status": "incomparable",
                "reasons": ["historical_checkpoint_unavailable", f"historical_state:{historical.get('state')}"],
            }
            continue
        mismatches = []
        if current.get("denominator_identity") != historical.get("denominator_identity"):
            mismatches.append("denominator_identity_mismatch")
        if current.get("statement_scope") != historical.get("statement_scope"):
            mismatches.append("statement_scope_mismatch")
        if historical.get("historical_only") is not True:
            mismatches.append("historical_checkpoint_not_marked_historical_only")
        if mismatches:
            comparisons[name] = {"status": "incomparable", "reasons": mismatches}
            continue
        current_value = _rv_number(current.get("observed_value"))
        historical_value = _rv_number(historical.get("observed_multiple"))
        if current_value is None or historical_value is None or historical_value == 0:
            comparisons[name] = {"status": "incomparable", "reasons": ["non_numeric_or_zero_multiple"]}
            continue
        comparisons[name] = {
            "status": "comparable",
            "current_value": current_value,
            "current_price_as_of_session": current.get("price_as_of_session"),
            "historical_value": historical_value,
            "historical_price_as_of_date": historical.get("price_as_of_date"),
            "multiple_change_pct": (current_value / historical_value) - 1.0,
            "reasons": [],
            "interpretation_limits": [
                "A multiple change is a descriptive delta only; it is not a cheap/expensive, "
                "buy/sell, target-price, or expected-return conclusion.",
            ],
        }
    any_comparable = any(c.get("status") == "comparable" for c in comparisons.values())
    status = "comparable" if any_comparable else "incomparable"
    reasons: list[str] = []
    if status == "incomparable":
        reasons = sorted({reason for comparison in comparisons.values() for reason in comparison.get("reasons", [])})
        if not reasons:
            reasons = ["no_qualified_historical_checkpoint_available"]
    return {"status": status, "reasons": reasons, "comparisons": comparisons}
