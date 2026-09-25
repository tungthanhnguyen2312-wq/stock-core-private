"""Authoritative 20-observation reference window (TACTICAL_REFERENCE_WINDOW_CORRECTIVE_V1).

One pure computation boundary for the close-based reference values that the tactical lens names
``ma_20`` and ``momentum_20d``. ``mva_daily_research_bundle.market_features()`` (and therefore
``market_wide_current_descriptive_research`` -> ``watchlist_tactical_entry_classifier``) and
``tactical_momentum_context`` both call these functions, so the two contracts cannot compute
the same concept two different ways again.

Contract (unchanged intent, now enforced):

* Window: the latest ``REFERENCE_WINDOW_OBSERVATIONS`` (20) retained observations, ordered by
  session, whose session is not after the feature session. Observations are never imputed and
  an unusable row inside the window is never skipped to reach an older one. For a sparse
  ticker, the window can span more than 20 calendar sessions when the provider omitted
  zero-trade days. This matches the convention already used by ``tactical_momentum_context``,
  the structural MA20 slope, and ``market_wide_historical_research_context``.
* ``ma_20`` = arithmetic mean of the window's 20 closes.
* ``momentum_20d`` = ``close[last] / close[first] - 1`` over the same window: close(T0) versus
  the close 19 observations earlier, which is 19 return intervals.
* The window fails closed with a blocker when:
  * fewer than 20 observations exist through the feature session;
  * a close is missing, non-finite or non-positive;
  * a volume is missing;
  * a session is duplicated;
  * price-basis / transformation identities are mixed.
  It never falls back to a longer or shorter history.

Before this corrective, ``market_features()`` received the whole retained history (~250
observations) from the descriptive research and silently computed a whole-history mean/return
under the 20-session names (recorded as a known characteristic in DECISIONS 2026-08-31).
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Mapping, Sequence

REFERENCE_WINDOW_OBSERVATIONS = 20
WINDOW_CONVENTION = "LATEST_20_QUALIFIED_RETAINED_OBSERVATIONS_THROUGH_FEATURE_SESSION"
MOMENTUM_CONVENTION = "CLOSE_LAST_OVER_CLOSE_FIRST_OF_WINDOW_MINUS_ONE_19_INTERVALS"

BLOCKER_INCOMPLETE_WINDOW = "COMPLETE_20_SESSION_WINDOW_REQUIRED"
BLOCKER_DUPLICATE_SESSION = "REFERENCE_WINDOW_DUPLICATE_SESSION"
BLOCKER_MIXED_PRICE_BASIS = "REFERENCE_WINDOW_PRICE_BASIS_INCOMPATIBLE"

AVAILABLE = "AVAILABLE"
MISSING = "MISSING"


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _session_of(row: Mapping[str, Any]) -> str | None:
    value = row.get("date", row.get("session"))
    return str(value) if value is not None else None


def select_reference_window(
    rows: Sequence[Mapping[str, Any]], *, as_of_session: str | None = None,
    length: int = REFERENCE_WINDOW_OBSERVATIONS,
) -> dict[str, Any]:
    """Select the authoritative trailing window from retained observations.

    ``rows`` carry ``date`` (or ``session``), ``close``, ``volume`` and optionally
    ``price_basis`` / ``transformation_identity``. Rows dated after ``as_of_session`` are
    excluded (no future contamination). Returns the ordered window rows or an explicit
    fail-closed status; never a partial window.
    """
    dated = [row for row in rows if isinstance(row, Mapping) and _session_of(row) is not None]
    if as_of_session is not None:
        dated = [row for row in dated if _session_of(row) <= as_of_session]
    ordered = sorted(dated, key=_session_of)
    last_session = _session_of(ordered[-1]) if ordered else None
    window = ordered[-length:]

    def _missing(blocker: str) -> dict[str, Any]:
        return {"status": MISSING, "blockers": [blocker], "rows": [], "first_session": None,
                "last_session": last_session, "observations": len(window), "convention": WINDOW_CONVENTION}

    if len(window) < length:
        return _missing(BLOCKER_INCOMPLETE_WINDOW)
    sessions = [_session_of(row) for row in window]
    if len(set(sessions)) != len(sessions):
        return _missing(BLOCKER_DUPLICATE_SESSION)
    closes = [_finite(row.get("close")) for row in window]
    if any(value is None or value <= 0 for value in closes) or any(_finite(row.get("volume")) is None for row in window):
        return _missing(BLOCKER_INCOMPLETE_WINDOW)
    if len({(row.get("price_basis"), row.get("transformation_identity")) for row in window}) != 1:
        return _missing(BLOCKER_MIXED_PRICE_BASIS)
    return {"status": AVAILABLE, "blockers": [], "rows": list(window), "first_session": sessions[0],
            "last_session": sessions[-1], "observations": length, "convention": WINDOW_CONVENTION}


def trailing_mean(values: Sequence[float]) -> float:
    """The one arithmetic-mean definition used for every close moving average here."""
    return statistics.mean(values)


def reference_ma20(window_closes: Sequence[float]) -> float:
    if len(window_closes) != REFERENCE_WINDOW_OBSERVATIONS:
        raise ValueError("REFERENCE_WINDOW_LENGTH_INVALID")
    return trailing_mean(window_closes)


def reference_momentum_20d(window_closes: Sequence[float]) -> float:
    if len(window_closes) != REFERENCE_WINDOW_OBSERVATIONS:
        raise ValueError("REFERENCE_WINDOW_LENGTH_INVALID")
    return (window_closes[-1] / window_closes[0]) - 1


def reference_values(rows: Sequence[Mapping[str, Any]], *, as_of_session: str | None = None) -> dict[str, Any]:
    """Window metadata plus the authoritative ``ma_20`` / ``momentum_20d`` (or fail-closed)."""
    window = select_reference_window(rows, as_of_session=as_of_session)
    result = {key: window[key] for key in ("status", "blockers", "first_session", "last_session", "observations", "convention")}
    result["momentum_convention"] = MOMENTUM_CONVENTION
    if window["status"] != AVAILABLE:
        result.update({"ma_20": None, "momentum_20d": None})
        return result
    closes = [float(row["close"]) for row in window["rows"]]
    result.update({"ma_20": reference_ma20(closes), "momentum_20d": reference_momentum_20d(closes)})
    return result
