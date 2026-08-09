"""Provider-scoped descriptive/technical price and volume observations, wired to the
capability registry instead of sitting disconnected from the research product.

WHY THIS MODULE EXISTS
    ``risk_liquidity.py`` already computes realized volatility, downside volatility and
    maximum drawdown from the retained OHLCV series -- but only inside a branch gated on
    the *generic* ``price_adjustment == "qualified"`` flag, which is always false (the
    generic price basis is unknown market-wide). Every production ticker's retained OHLCV
    is, in fact, 100% VCI-sourced (verified against ``dashboard-runtime/vn_stock.db`` for
    all 11 live tickers), and VCI's own price series carries a real, evidenced,
    provider-scoped verdict (``empirically_event_adjusted``, ``empirically_deduced`` tier --
    see ``provider_price_basis_registry.py``). That is exactly the evidence
    ``vci_direct_basis_pilot.SHADOW_PRICE_CAPABILITIES`` already names as sufficient for
    ``vci_namespaced_historical_returns`` / ``vci_namespaced_technical_indicators``. The
    capability was proven safe and was simply never connected to anything a reader sees.

    This module is that connection. It does not touch ``risk_liquidity.py``'s existing
    output shape (no regression risk to the generic-gated ``market_risk`` section any other
    consumer already depends on) -- it adds a new, separately named, additive section.

WHAT IT REFUSES TO DO
    Compute anything when the retained window mixes providers (fail closed on ambiguous
    provenance, never silently blend two unqualified-relative-to-each-other bases -- see
    ``price_basis_qualification_contract.md`` section on mixed-basis calculations).
    Compute anything from fewer than :data:`MIN_SESSIONS` rows (a scale or a trend from a
    handful of sessions is noise wearing a number). Claim ``is_actionable`` or
    ``liquidity_actionable`` under any input -- both are hardcoded ``False`` here, never
    computed, so no combination of inputs can turn them on. Let a return or technical
    result go out without the ``provider_series_return`` label the capability registry
    requires for that capability.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import kbs_empirical_basis as kbs_basis
import market_basis_capability_registry as registry
import provider_price_basis_registry as price_registry

VERSION = "1.0.0"
SCHEMA_VERSION = VERSION

#: Below this many sessions, a return/volatility/drawdown descriptor is noise, not a
#: finding. Reuses the same order-of-magnitude threshold kbs_empirical_basis applies before
#: trusting a scale selection (``MIN_ROWS_FOR_UNIT_SELECTION``) -- this repository's
#: standing convention for "enough rows to say something", not a number invented here.
MIN_SESSIONS = 20

SUPPORTED_PROVIDERS = frozenset({"KBS", "VCI"})

PROHIBITED_CLAIMS: tuple[str, ...] = (
    "current_valuation",
    "target_price",
    "buy_hold_sell",
    "ranking",
    "current_market_liquidity",
    "position_sizing",
    "market_impact",
    "days_to_liquidate",
    "official_exchange_price",
    "total_shareholder_return",
    "raw_as_traded_price",
    "expected_return",
    "portfolio_allocation",
)


def _unavailable(ticker: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": str(ticker).upper(),
        "status": "unavailable",
        "reason": reason,
        "provider": None,
        "is_actionable": False,
        "liquidity_actionable": False,
        "descriptive_price": None,
        "descriptive_volume": None,
        "return_descriptors": None,
        "prohibited_claims": list(PROHIBITED_CLAIMS),
        **extra,
    }


def _capability_field(provider: str, capability_name: str, *, label: str | None = None) -> dict[str, Any]:
    """Evaluate one capability through the registry and reduce it to what a caller needs.

    ``existing_gates_passed=True`` here means exactly what it means in every matrix this
    delegates to: the caller (this module) has already checked its own freshness/provenance
    precondition -- a single-provider window of at least :data:`MIN_SESSIONS` sessions --
    before asking. The registry still decides whether the capability is open at all.
    """
    kwargs: dict[str, Any] = {"existing_gates_passed": True}
    if label is not None:
        kwargs["label"] = label
    record = registry.evaluate(provider, capability_name, **kwargs)
    return {
        "capability": capability_name,
        "capability_class": record.get("capability_class"),
        "availability": record.get("availability"),
        "available": bool(record.get("available")),
        "required_warnings": list(record.get("required_warnings") or []),
        "ladder_level": registry.ladder_level(record),
        "ladder_level_name": registry.LADDER_LEVELS[registry.ladder_level(record)],
    }


def _provenance_ok(provenance: Mapping[str, Any] | None) -> tuple[str | None, str | None]:
    """The retained window's provider, or the reason it cannot be used.

    Returns ``(provider, None)`` when usable, or ``(None, reason)`` when not. A missing
    provenance object, a non-pure (multi-source) window, or a provider this module has no
    capability registry entry for all fail closed the same way: no guess, no default.
    """
    if not isinstance(provenance, Mapping):
        return None, "ohlcv_provider_provenance_absent"
    if not provenance.get("pure"):
        return None, "ohlcv_window_mixes_more_than_one_provider"
    provider = str(provenance.get("provider") or "").strip().upper()
    if provider not in SUPPORTED_PROVIDERS:
        return None, f"provider_not_in_capability_registry:{provider or 'unknown'}"
    return provider, None


def _closes_and_volumes(rows: Sequence[Mapping[str, Any]]) -> tuple[list[float], list[float], list[str]]:
    closes: list[float] = []
    volumes: list[float] = []
    dates: list[str] = []
    for row in rows:
        close = row.get("close")
        if close in (None, 0):
            continue
        closes.append(float(close))
        volumes.append(float(row.get("volume") or 0))
        dates.append(str(row.get("date")))
    return closes, volumes, dates


def _descriptive_price(rows: Sequence[Mapping[str, Any]], closes: Sequence[float], dates: Sequence[str]) -> dict[str, Any]:
    highs = [float(r["high"]) for r in rows if r.get("high") is not None]
    lows = [float(r["low"]) for r in rows if r.get("low") is not None]
    mean_close = sum(closes) / len(closes)
    return {
        "session_count": len(closes),
        "as_of_date": dates[-1] if dates else None,
        "first_date": dates[0] if dates else None,
        "latest_close": closes[-1],
        "period_high": max(highs) if highs else max(closes),
        "period_low": min(lows) if lows else min(closes),
        "mean_close": mean_close,
        "unit": "provider_reported_price_unit",
    }


def _descriptive_volume(volumes: Sequence[float]) -> dict[str, Any]:
    mean_volume = sum(volumes) / len(volumes) if volumes else None
    latest = volumes[-1] if volumes else None
    relative = (latest / mean_volume) if (mean_volume not in (None, 0) and latest is not None) else None
    return {
        "session_count": len(volumes),
        "latest_volume": latest,
        "mean_volume": mean_volume,
        "relative_volume": relative,
        "unit": "provider_reported_volume_units",
    }


def _return_descriptors(closes: Sequence[float]) -> dict[str, Any]:
    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1]]
    if not rets:
        return {"window_return": None, "realized_volatility": None, "maximum_drawdown": None, "sessions_used": 0}
    window_return = closes[-1] / closes[0] - 1 if closes[0] else None
    mean = sum(rets) / len(rets)
    volatility = math.sqrt(sum((r - mean) ** 2 for r in rets) / len(rets))
    peak = closes[0]
    drawdown = 0.0
    for c in closes:
        peak = max(peak, c)
        drawdown = min(drawdown, c / peak - 1.0) if peak else drawdown
    return {
        "window_return": window_return,
        "realized_volatility": volatility,
        "maximum_drawdown": drawdown,
        "sessions_used": len(rets),
        "return_basis": "simple_consecutive_returns_over_the_retained_provider_series",
    }


#: Which registry capability name gates each field this module produces, per provider.
#: KBS already has one unified matrix that covers both; VCI splits across its price matrix
#: (in this registry) and its existing volume matrix.
_CAPABILITY_NAMES = {
    "KBS": {
        "descriptive_price": "kbs_descriptive_price_statistics",
        "descriptive_volume": "kbs_descriptive_volume_statistics",
        "return_descriptors": "kbs_provider_series_return",
    },
    "VCI": {
        "descriptive_price": "vci_namespaced_price_display",
        "descriptive_volume": "provider_volume_history_display",
        "return_descriptors": "vci_namespaced_historical_returns",
    },
}


def evaluate(ticker: str, entry: Mapping[str, Any] | None) -> dict[str, Any]:
    """Build the ``qualified_market_observations`` section for one ticker.

    Pure: takes exactly what is already in the bundle entry (``ohlcv_recent`` and
    ``ohlcv_provider_provenance``) and returns a new dict. No I/O, no network, no
    recomputation of anything another module already qualified -- provider price-basis and
    volume-scope facts are read from ``market_basis_capability_registry``, never re-derived.
    """
    ticker = str(ticker).upper()
    entry = entry if isinstance(entry, Mapping) else {}
    provider, reason = _provenance_ok(entry.get("ohlcv_provider_provenance"))
    if provider is None:
        return _unavailable(ticker, reason or "provenance_unresolved")

    rows = entry.get("ohlcv_recent")
    if not isinstance(rows, list) or not rows:
        return _unavailable(ticker, "ohlcv_recent_absent", provider=provider)

    closes, volumes, dates = _closes_and_volumes(rows)
    if len(closes) < MIN_SESSIONS:
        return _unavailable(
            ticker, "insufficient_session_history",
            provider=provider, sessions_available=len(closes), sessions_required=MIN_SESSIONS,
        )

    names = _CAPABILITY_NAMES[provider]
    price_cap = _capability_field(provider, names["descriptive_price"])
    volume_cap = _capability_field(provider, names["descriptive_volume"])
    return_cap = _capability_field(
        provider, names["return_descriptors"], label=registry.PROVIDER_SERIES_RETURN_LABEL
    )

    price_registry_verdict = _price_basis_summary(provider)

    descriptive_price = None
    if price_cap["available"]:
        descriptive_price = {**_descriptive_price(rows, closes, dates), "capability": price_cap}
    descriptive_volume = None
    if volume_cap["available"]:
        descriptive_volume = {**_descriptive_volume(volumes), "capability": volume_cap}
    return_descriptors = None
    if return_cap["available"]:
        return_descriptors = {
            **_return_descriptors(closes),
            "required_label": registry.PROVIDER_SERIES_RETURN_LABEL,
            "capability": return_cap,
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": ticker,
        "status": "available",
        "provider": provider,
        "namespace": "provider_scoped",
        "descriptive_only": True,
        "price_basis": price_registry_verdict,
        "descriptive_price": descriptive_price,
        "descriptive_volume": descriptive_volume,
        "return_descriptors": return_descriptors,
        "is_actionable": False,
        "liquidity_actionable": False,
        "market_dependent": False,
        "prohibited_claims": list(PROHIBITED_CLAIMS),
        "warnings": sorted(
            set(
                (price_cap.get("required_warnings") or [])
                + (volume_cap.get("required_warnings") or [])
                + (return_cap.get("required_warnings") or [])
            )
        ),
    }


def _price_basis_summary(provider: str) -> dict[str, Any]:
    verdict = price_registry.active_verdict(provider)
    summary = {
        "price_basis": verdict.get("price_basis"),
        "price_basis_qualification": verdict.get("price_basis_qualification", "empirically_deduced"),
        "raw_as_traded_eligible": verdict.get("raw_as_traded_eligible"),
        "historical_mutability": verdict.get("historical_mutability"),
    }
    if provider == "KBS":
        summary["volume_market_scope"] = kbs_basis.market_scope_contract()["volume_market_scope"]
    return summary
