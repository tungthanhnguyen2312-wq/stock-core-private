"""Private, local-only owner research-exclusion preferences (PERSONAL_DECISION_INPUT_TRUTH_V1).

Generic mechanism for the owner to permanently keep a ticker out of active investment research
(e.g. a delisted historical holding they never want resurfaced) without touching its historical
accounting ledger. Lives entirely under the same private root as the owner workbook (default
``%USERPROFILE%/.stocklookup/portfolio``, see ``private_portfolio_context.default_portfolio_root``)
as ``research_exclusions.json``. This module's own code is tracked in Git like any other module;
the exclusion *values* it reads are owner data and are never written to the repository,
operations-review, the Dashboard, or a public artifact.

A missing exclusions file is the honest default: no owner exclusions set, never an error.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from private_portfolio_context import default_portfolio_root

CONTRACT_VERSION = "owner_research_exclusion/v1"


class OwnerResearchExclusionError(ValueError):
    """The owner's local exclusions file cannot be interpreted without an explicit disposition."""


def _ticker(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text if re.fullmatch(r"[A-Z0-9.\-]{1,16}", text) else None


def default_exclusions_path(portfolio_root: Path | None = None) -> Path:
    root = (portfolio_root or default_portfolio_root()).expanduser().resolve()
    return root / "research_exclusions.json"


def load_research_exclusions(portfolio_root: Path | None = None) -> dict[str, Any]:
    """Read-only. A missing or empty file returns ``status: "NOT_PROVIDED"`` with an empty list --
    never raises, so every caller downstream can unconditionally merge this in."""
    path = default_exclusions_path(portfolio_root)
    if not path.is_file():
        return {
            "schema_version": "owner_research_exclusion_v1", "contract_version": CONTRACT_VERSION,
            "status": "NOT_PROVIDED", "path": str(path), "excluded_tickers": [],
        }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OwnerResearchExclusionError("OWNER_RESEARCH_EXCLUSIONS_FILE_UNREADABLE") from exc
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw.get("excluded_tickers") or []:
        if isinstance(item, str):
            ticker, reason, excluded_since = item, None, None
        elif isinstance(item, Mapping):
            ticker, reason, excluded_since = item.get("ticker"), item.get("reason"), item.get("excluded_since")
        else:
            continue
        ticker = _ticker(ticker)
        if ticker is None or ticker in seen:
            continue
        seen.add(ticker)
        entries.append({"ticker": ticker, "reason": reason, "excluded_since": excluded_since})
    entries.sort(key=lambda entry: entry["ticker"])
    return {
        "schema_version": "owner_research_exclusion_v1", "contract_version": CONTRACT_VERSION,
        "status": "PROVIDED" if entries else "NOT_PROVIDED", "path": str(path), "excluded_tickers": entries,
    }


def excluded_ticker_set(exclusions: Mapping[str, Any]) -> frozenset[str]:
    return frozenset(entry["ticker"] for entry in exclusions.get("excluded_tickers") or [])


def write_research_exclusions(entries: list[Any], *, portfolio_root: Path | None = None) -> Path:
    """Materialize the owner's full exclusion list (replaces the file's contents). Local-only:
    never called by Daily, the Dashboard, or any AI-handoff path."""
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in entries:
        if isinstance(item, str):
            ticker, reason, excluded_since = item, None, None
        elif isinstance(item, Mapping):
            ticker, reason, excluded_since = item.get("ticker"), item.get("reason"), item.get("excluded_since")
        else:
            raise OwnerResearchExclusionError("EXCLUSION_ENTRY_INVALID")
        ticker = _ticker(ticker)
        if ticker is None:
            raise OwnerResearchExclusionError("EXCLUSION_TICKER_INVALID")
        if ticker in seen:
            continue
        seen.add(ticker)
        normalized.append({"ticker": ticker, "reason": reason, "excluded_since": excluded_since})
    normalized.sort(key=lambda entry: entry["ticker"])
    path = default_exclusions_path(portfolio_root)
    body = {"schema_version": "owner_research_exclusion_v1", "contract_version": CONTRACT_VERSION, "excluded_tickers": normalized}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    import os
    os.replace(temporary, path)
    return path


def add_research_exclusion(ticker: str, *, reason: str | None = None, excluded_since: str | None = None, portfolio_root: Path | None = None) -> dict[str, Any]:
    current = load_research_exclusions(portfolio_root)
    entries = {entry["ticker"]: entry for entry in current.get("excluded_tickers") or []}
    normalized_ticker = _ticker(ticker)
    if normalized_ticker is None:
        raise OwnerResearchExclusionError("EXCLUSION_TICKER_INVALID")
    entries[normalized_ticker] = {"ticker": normalized_ticker, "reason": reason, "excluded_since": excluded_since}
    write_research_exclusions(list(entries.values()), portfolio_root=portfolio_root)
    return load_research_exclusions(portfolio_root)


def remove_research_exclusion(ticker: str, *, portfolio_root: Path | None = None) -> dict[str, Any]:
    current = load_research_exclusions(portfolio_root)
    normalized_ticker = _ticker(ticker)
    entries = [entry for entry in current.get("excluded_tickers") or [] if entry["ticker"] != normalized_ticker]
    write_research_exclusions(entries, portfolio_root=portfolio_root)
    return load_research_exclusions(portfolio_root)
