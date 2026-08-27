"""Governed owner-focus versus broader-watchlist presentation scope.

This module loads a portable config. It grants no investment authority and does
not treat watchlist membership as portfolio holdings.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "owner_research_focus.json"
CONTRACT_VERSION = "owner_research_focus/v1"


class OwnerResearchFocusError(ValueError):
    """Fail-closed owner-focus config error."""


def _tickers(value: Any, *, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise OwnerResearchFocusError("OWNER_FOCUS_CONFIG_INVALID:" + name)
    tickers: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise OwnerResearchFocusError("OWNER_FOCUS_CONFIG_INVALID_TICKER:" + name)
        ticker = item.strip().upper()
        if ticker in seen:
            raise OwnerResearchFocusError("OWNER_FOCUS_CONFIG_DUPLICATE_TICKER:" + ticker)
        seen.add(ticker)
        tickers.append(ticker)
    return tuple(tickers)


def load_owner_research_focus(path: Path | None = None) -> dict[str, Any]:
    """Load and validate the governed owner-focus config."""
    config_path = path or CONFIG_PATH
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("schema_version") != CONTRACT_VERSION:
        raise OwnerResearchFocusError("OWNER_FOCUS_CONFIG_CONTRACT_INVALID")
    owner_focus = _tickers(payload.get("owner_focus_tickers"), name="owner_focus_tickers")
    watchlist = _tickers(payload.get("broader_watchlist"), name="broader_watchlist")
    if payload.get("is_portfolio_holdings") is not False:
        raise OwnerResearchFocusError("OWNER_FOCUS_CONFIG_MUST_NOT_BE_HOLDINGS")
    if payload.get("is_actionable") is not False:
        raise OwnerResearchFocusError("OWNER_FOCUS_CONFIG_MUST_NOT_BE_ACTIONABLE")
    missing_from_watchlist = [ticker for ticker in owner_focus if ticker not in set(watchlist)]
    if missing_from_watchlist:
        raise OwnerResearchFocusError("OWNER_FOCUS_NOT_SUBSET_OF_BROADER_WATCHLIST:" + ",".join(missing_from_watchlist))
    return {
        "schema_version": CONTRACT_VERSION,
        "role": payload.get("role") or "PRESENTATION_ANALYSIS_SCOPE_ONLY",
        "grants_investment_authority": False,
        "is_portfolio_holdings": False,
        "is_actionable": False,
        "review_order": payload.get("review_order") or "OWNER_FOCUS_REVIEW_REQUIRED_BEFORE_MARKET_DISCOVERY",
        "owner_focus_tickers": owner_focus,
        "broader_watchlist": watchlist,
        "notes": list(payload.get("notes") or []),
    }


def owner_focus_tickers(path: Path | None = None) -> tuple[str, ...]:
    return load_owner_research_focus(path)["owner_focus_tickers"]


def broader_watchlist(path: Path | None = None) -> tuple[str, ...]:
    return load_owner_research_focus(path)["broader_watchlist"]
