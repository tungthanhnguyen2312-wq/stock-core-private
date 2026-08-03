"""Bounded, resumable reconciliation of active-universe tickers with no retained payload.

WHAT THIS IS
    The 2026-08-03 retention pass left 131 active-universe tickers with no retained statement
    payload at all. `docs/STATE.md` records that as "a genuine acquisition gap, and the only
    one of these four that needs new data". This module establishes what kind of gap each one
    actually is, without fabricating an observation and without rebuilding the store.

THE DEFECT IT EXISTS TO CORRECT
    `scrape_meta.csv` already records all 131 tickers as `status = empty`, which reads as
    "the source confirmed it has no data". It does not mean that. `bctc_sync.call_api`
    returns `None` -- which `fetch_report` turns into `EMPTY_DATA` -- on **any** exception
    that is neither a rate-limit nor a recognised network error:

        else:
            print(f"   [Lỗi Hệ Thống] {label}: ...")
            return None

    So a schema change, a parse error, an unexpected provider exception and a genuinely empty
    source all land in the same bucket. Every one of the 131 also has `source = NaN`, meaning
    no source ever succeeded, so the recorded state cannot distinguish "this company files
    nothing the provider carries" from "the call broke". Those two have opposite remedies:
    one is closed, the other is a bug or a retry.

    This module re-probes through the same authorized provider path and separates them.

CLASSIFICATIONS

    payload_available          the provider returned rows. The store has a real gap and the
                               authorized sync should be re-run for this ticker.
    source_empty_confirmed     every configured source returned no rows, cleanly, with no
                               exception. The gap is in the source, not in the pipeline.
    provider_error             a non-network exception. This is the class the existing meta
                               silently records as `empty`; the exception type is recorded.
    retrieval_failure          network, timeout or rate-limit, after bounded retries.
    unsupported_entity         the ticker is not a listed equity, so statements are not
                               expected. Resolved offline from the screening snapshot.

WHAT IT NEVER DOES
    It never writes a payload. Retrieval is `bctc_sync.py`'s job and duplicating it here
    would risk writing a second copy of a payload under a different code path. This module
    classifies and reports; acting on `payload_available` is a separate, explicit run of the
    authorized sync. It never fabricates an observation, never rebuilds the observation store,
    and never touches `vn_stock.db` or any published artifact.

BOUNDED AND RESUMABLE
    One ticker at a time, a fixed inter-request delay, at most `max_attempts` attempts per
    source, and a hard `max_tickers` ceiling per run. State is written after every ticker, so
    an interrupted run resumes exactly where it stopped and never re-probes a ticker that
    already reached a terminal classification.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from atomic_io import atomic_write_json

VERSION = "1.0.0"
STATE_RELATIVE = Path("data") / "market-wide-financials" / "missing_payload_reconciliation.json"
REPORT_RELATIVE = Path("data") / "market-wide-financials" / "missing_payload_report.json"

#: Report families, in the order `bctc_sync.py` fetches them.
REPORT_FAMILIES = ("balance_sheet", "income_statement", "cash_flow")

#: Sources, in the order `bctc_sync.py` tries them. Reused rather than redefined so this
#: module cannot drift into probing a path the sync does not use.
SOURCES = ("KBS", "VCI")

PAYLOAD_AVAILABLE = "payload_available"
SOURCE_EMPTY_CONFIRMED = "source_empty_confirmed"
PROVIDER_ERROR = "provider_error"
RETRIEVAL_FAILURE = "retrieval_failure"
UNSUPPORTED_ENTITY = "unsupported_entity"
NOT_PROBED = "not_probed"

#: Classifications that are settled and are never re-probed on a later run.
TERMINAL = frozenset({PAYLOAD_AVAILABLE, SOURCE_EMPTY_CONFIRMED, UNSUPPORTED_ENTITY})

DEFAULT_DELAY_SECONDS = 1.1
DEFAULT_MAX_ATTEMPTS = 2
DEFAULT_MAX_TICKERS = 40

_RATE_MARKERS = ("rate", "429", "quá nhiều", "too many")
_NETWORK_MARKERS = ("timeout", "connection", "disconnected", "reset", "502", "503", "504")
_EMPTY_MARKERS = ("dữ liệu trống", "no data", "empty")


def state_path(runtime_root: Path | str) -> Path:
    return Path(runtime_root) / STATE_RELATIVE


def report_path(runtime_root: Path | str) -> Path:
    return Path(runtime_root) / REPORT_RELATIVE


def load_state(runtime_root: Path | str) -> dict[str, Any]:
    try:
        payload = json.loads(state_path(runtime_root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, Mapping) or payload.get("schema_version") != VERSION:
        return {}
    return dict(payload)


def classify_exception(exc: BaseException) -> tuple[str, str]:
    """Map a provider exception onto (classification, reason).

    Mirrors `bctc_sync.call_api`'s own detection so the same condition is named the same way,
    but keeps `provider_error` distinct from `source_empty_confirmed` instead of collapsing
    both to `None`.
    """
    inner = getattr(getattr(exc, "last_attempt", None), "exception", lambda: None)()
    message = str(inner if inner is not None else exc)
    lowered = message.lower()
    if any(marker in lowered for marker in _EMPTY_MARKERS):
        return SOURCE_EMPTY_CONFIRMED, f"source reported empty: {message[:160]}"
    if any(marker in lowered for marker in _RATE_MARKERS):
        return RETRIEVAL_FAILURE, f"rate limited: {message[:160]}"
    if any(marker in lowered for marker in _NETWORK_MARKERS):
        return RETRIEVAL_FAILURE, f"network error: {message[:160]}"
    return PROVIDER_ERROR, f"{type(inner if inner is not None else exc).__name__}: {message[:160]}"


def _default_fetcher(ticker: str, source: str, family: str, period: str = "quarter") -> Any:
    """The authorized statement path, exactly as `bctc_sync._finance` builds it."""
    from vnstock.api.financial import Finance

    return getattr(Finance(source=source, symbol=ticker), family)(period=period)


def probe_ticker(ticker: str, *, fetcher: Callable[..., Any] = _default_fetcher,
                 max_attempts: int = DEFAULT_MAX_ATTEMPTS,
                 delay_seconds: float = DEFAULT_DELAY_SECONDS,
                 sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Probe every (source, family) pair for one ticker and classify the outcome.

    The ticker-level verdict is the strongest outcome observed: any rows anywhere means
    `payload_available`; otherwise a provider error outranks a retrieval failure, which
    outranks a confirmed empty, because a wrongly-classified `empty` is the failure mode this
    module exists to prevent.
    """
    attempts: list[dict[str, Any]] = []
    for family in REPORT_FAMILIES:
        for source in SOURCES:
            outcome, reason, rows = NOT_PROBED, "", 0
            for attempt in range(1, max_attempts + 1):
                try:
                    frame = fetcher(ticker, source, family)
                except BaseException as exc:  # noqa: BLE001 - classified, never swallowed
                    outcome, reason = classify_exception(exc)
                    if outcome == RETRIEVAL_FAILURE and attempt < max_attempts:
                        sleep(delay_seconds * attempt)
                        continue
                    break
                rows = 0 if frame is None else len(frame)
                if rows:
                    outcome, reason = PAYLOAD_AVAILABLE, f"{rows} rows returned"
                else:
                    outcome, reason = SOURCE_EMPTY_CONFIRMED, "source returned no rows"
                break
            attempts.append({"family": family, "source": source, "outcome": outcome,
                             "reason": reason, "rows": rows})
            sleep(delay_seconds)

    outcomes = {attempt["outcome"] for attempt in attempts}
    for verdict in (PAYLOAD_AVAILABLE, PROVIDER_ERROR, RETRIEVAL_FAILURE,
                    SOURCE_EMPTY_CONFIRMED):
        if verdict in outcomes:
            classification = verdict
            break
    else:
        classification = NOT_PROBED
    return {"ticker": ticker.upper(), "classification": classification, "attempts": attempts}


def plan(runtime_root: Path | str, *, missing_tickers: Iterable[str],
         instrument_of: Mapping[str, str] | None = None) -> dict[str, Any]:
    """What a run would probe, resolving everything that needs no network first."""
    state = load_state(runtime_root)
    recorded = {str(entry["ticker"]): entry for entry in (state.get("tickers") or [])}
    instrument_of = {key.upper(): str(value).upper()
                     for key, value in (instrument_of or {}).items()}

    resolved: list[dict[str, Any]] = []
    pending: list[str] = []
    for ticker in sorted({str(item).upper() for item in missing_tickers}):
        prior = recorded.get(ticker)
        if prior is not None and prior.get("classification") in TERMINAL:
            resolved.append(prior)
            continue
        instrument = instrument_of.get(ticker)
        if instrument and instrument != "STOCK":
            resolved.append({"ticker": ticker, "classification": UNSUPPORTED_ENTITY,
                             "attempts": [],
                             "reason": f"instrument_type={instrument!r} is not a listed equity"})
            continue
        pending.append(ticker)
    return {"resolved": resolved, "pending": pending,
            "already_terminal": len(resolved) - sum(
                1 for entry in resolved if entry["classification"] == UNSUPPORTED_ENTITY)}


def reconcile(runtime_root: Path | str, *, missing_tickers: Iterable[str], generated_at: str,
              instrument_of: Mapping[str, str] | None = None, execute: bool = False,
              max_tickers: int = DEFAULT_MAX_TICKERS,
              fetcher: Callable[..., Any] = _default_fetcher,
              max_attempts: int = DEFAULT_MAX_ATTEMPTS,
              delay_seconds: float = DEFAULT_DELAY_SECONDS,
              sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Probe up to `max_tickers` unresolved tickers, writing state after each one."""
    runtime_root = Path(runtime_root)
    planned = plan(runtime_root, missing_tickers=missing_tickers, instrument_of=instrument_of)
    entries = {entry["ticker"]: entry for entry in planned["resolved"]}
    probed: list[str] = []

    for ticker in planned["pending"][:max(0, int(max_tickers))]:
        if not execute:
            entries[ticker] = {"ticker": ticker, "classification": NOT_PROBED,
                               "attempts": [], "reason": "dry run: no request issued"}
            continue
        result = probe_ticker(ticker, fetcher=fetcher, max_attempts=max_attempts,
                              delay_seconds=delay_seconds, sleep=sleep)
        entries[ticker] = result
        probed.append(ticker)
        # Written after every ticker so an interrupted run resumes exactly here.
        atomic_write_json(state_path(runtime_root), _state_document(entries, generated_at))

    not_reached = planned["pending"][max(0, int(max_tickers)):]
    for ticker in not_reached:
        entries.setdefault(ticker, {"ticker": ticker, "classification": NOT_PROBED,
                                    "attempts": [],
                                    "reason": "beyond this run's max_tickers ceiling"})

    document = _state_document(entries, generated_at)
    report = build_report(document, planned, probed, not_reached)
    if execute:
        atomic_write_json(state_path(runtime_root), document)
        atomic_write_json(report_path(runtime_root), report)
    return {"executed": execute, "state": document, "report": report,
            "probed": probed, "remaining": not_reached}


def _state_document(entries: Mapping[str, Mapping[str, Any]], generated_at: str) -> dict[str, Any]:
    return {
        "schema_version": VERSION,
        "generated_at": generated_at,
        "tickers": [dict(entries[ticker]) for ticker in sorted(entries)],
    }


def build_report(document: Mapping[str, Any], planned: Mapping[str, Any],
                 probed: Iterable[str], remaining: Iterable[str]) -> dict[str, Any]:
    """Deterministic classification report. Counts and named reasons only."""
    counts: dict[str, int] = {}
    by_class: dict[str, list[str]] = {}
    for entry in document.get("tickers") or []:
        classification = str(entry["classification"])
        counts[classification] = counts.get(classification, 0) + 1
        by_class.setdefault(classification, []).append(str(entry["ticker"]))

    error_kinds: dict[str, int] = {}
    for entry in document.get("tickers") or []:
        for attempt in entry.get("attempts") or []:
            if attempt.get("outcome") == PROVIDER_ERROR:
                kind = str(attempt.get("reason", "")).split(":", 1)[0]
                error_kinds[kind] = error_kinds.get(kind, 0) + 1

    return {
        "schema_version": VERSION,
        "reconciliation_version": VERSION,
        "ticker_count": len(document.get("tickers") or []),
        "classification_counts": dict(sorted(counts.items())),
        "tickers_by_classification": {key: sorted(value)
                                      for key, value in sorted(by_class.items())},
        "provider_error_kinds": dict(sorted(error_kinds.items())),
        "probed_this_run": sorted(probed),
        "remaining_unprobed": sorted(remaining),
        "note": ("`scrape_meta.csv` records every one of these tickers as `empty`, which "
                 "conflates a confirmed-empty source with a provider or parse error; see the "
                 "module docstring. No payload is written by this process."),
    }
