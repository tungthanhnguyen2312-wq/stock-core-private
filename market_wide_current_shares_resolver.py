"""Market-wide current effective shares resolver, evidence-derived (P1J.1).

Every value returned carries the lineage that produced it: the store it was read from, the
date it was observed, and — where the value cannot be trusted — the named reason. Nothing is
promoted to `qualified_official` without an official anchor *and* proof that no share-changing
event fell between that anchor and the session being resolved.

The resolver never invents a share count. The three anchors in
`data/official-evidence/share_basis_citations.jsonl` are read as bytes and used as bytes; the
previous revision of this module carried them as literals and two of the three were wrong
(HPG `7,163,748,865` appears in no citation and contradicts the ledger's own `shares_after`;
VCB `5,589,091,222` is the citation's `5,589,091,262` mistyped by 40 shares).

Authority lanes
---------------
``qualified_official``
    An official anchor that states an absolute count at a date — a qualified executed
    corporate action's `shares_after`, promoted through `evidence_promotion.py` — whose date
    precedes the session, corroborated by an independent observation taken on or after it,
    with no later share-changing event recorded. A `period_end_shares_outstanding` citation
    never clears this on its own: it describes a balance-sheet date, and the interval from
    there to the session is exactly what no retained evidence covers. One ticker clears it
    today (HPG, from its own 2026-07-02 listing-change notice).
``provider_reported_current``
    Retained provider observation dated on or after the session being resolved.
``provider_reported_lagged``
    Retained provider observation dated before the session, with no share-changing event
    recorded after it. Carries the lag in days. Absence of a recorded event is not proof that
    none occurred, and `freshness_proof` says so.
``provider_reported_stale``
    A share-changing official event carries an ex-right date after the observation.
``provider_reported_unverifiable_freshness``
    A share-changing or unclassified event exists that cannot be positioned against the
    observation because it carries no ex-right date.
``unknown_observation_date`` / ``unavailable`` / ``unresolved_error``
    No usable observation date; no positive value; and a store that could not be read. The
    last is never folded into either of the first two — a failed read is not an absent value.

Provider field provenance
-------------------------
Source ``Company(source="VCI", symbol=tk).overview()`` via ``meta_sync.py``, raw field
``issue_share``, stored as ``vn_stock.db -> metadata.shares_outstanding``, semantics
``ISSUED_SHARES``, unit ``shares``. Official anchors carry ``share_class`` ``common_outstanding``
instead, so the two concepts are reported separately and never silently mixed.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

RESOLVER_VERSION = "2.0.0"

#: Provider concept for `metadata.shares_outstanding`, proven in P1J workstream A.
PROVIDER_SHARE_CONCEPT = "ISSUED_SHARES"
PROVIDER_SOURCE = "VCI.overview.issue_share"

#: Event codes that change the outstanding share count.
SHARE_CHANGING_EVENT_CODES = frozenset({"ISS"})

#: Event codes that provably do not change the outstanding share count. Anything outside both
#: sets is `unclassified` and is surfaced rather than silently treated as benign.
NON_SHARE_CHANGING_EVENT_CODES = frozenset({
    "DIV", "DDINS", "DDIND", "DDRP", "AGME", "EGME", "MOVE", "SUSP", "OTHE", "AIS",
})

_OFFICIAL_ANCHOR_RELPATH = Path("data") / "official-evidence" / "share_basis_citations.jsonl"

#: A balance-sheet date. Becomes a *current* count only if something proves nothing changed
#: since, which for 1,678 of 1,683 tickers nothing does.
_PERIOD_END_IDENTITY = "period_end_shares_outstanding"

#: An absolute count a qualified executed event states outright, at a stated date. It needs no
#: proof for the interval before it — the issuer's own notice covers that — only for the
#: interval after, which is what the promotion gate below tests.
_EVENT_IDENTITY = "current_shares_outstanding_after_event"

_ANCHOR_IDENTITY_TYPES = frozenset({_PERIOD_END_IDENTITY, _EVENT_IDENTITY})


class ShareStoreUnreadable(RuntimeError):
    """The retained store could not be read. Never reported as an absent observation."""


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    """Read-only connection, matching the operating command's probe.

    A plain `sqlite3.connect` opens read-write and can take a write lock on a database in
    rollback-journal mode; this database is, and a concurrent writer is a real hazard here.
    """
    if not db_path.is_file():
        raise ShareStoreUnreadable(f"{db_path.name} not found under the runtime root")
    connection = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    connection.text_factory = lambda raw: raw.decode("utf-8", "replace")
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def _as_date(raw: Any) -> date | None:
    """Date part of a retained timestamp, or None when it is missing or unparseable."""
    if raw is None or isinstance(raw, bool):
        return None
    text = str(raw).strip()
    if not text:
        return None
    head = text.split()[0].split("T")[0]
    try:
        return datetime.strptime(head, "%Y-%m-%d").date()
    except ValueError:
        return None


def _classify_event_code(code: Any) -> str:
    text = str(code or "").strip().upper()
    if text in SHARE_CHANGING_EVENT_CODES:
        return "share_changing"
    if text in NON_SHARE_CHANGING_EVENT_CODES:
        return "not_share_changing"
    return "unclassified"


def load_official_anchors(runtime_root: Path | str) -> dict[str, dict[str, Any]]:
    """Latest official period-end share anchor per ticker, read from the citation store.

    A malformed line is skipped rather than failing the universe, but an unreadable file is
    raised, because silently resolving the whole market without anchors is the failure this
    module exists to prevent.
    """
    path = Path(runtime_root) / _OFFICIAL_ANCHOR_RELPATH
    if not path.is_file():
        raise ShareStoreUnreadable(f"official share anchors not found at {_OFFICIAL_ANCHOR_RELPATH}")

    anchors: dict[str, dict[str, Any]] = {}
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ShareStoreUnreadable(f"official share anchors unreadable: {exc}") from None

    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        identity = str(record.get("identity_type") or "")
        if identity not in _ANCHOR_IDENTITY_TYPES:
            continue
        ticker = str(record.get("ticker") or "").upper()
        value = record.get("value")
        if not ticker or not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            continue
        candidate = {
            "value": int(value),
            "identity_type": identity,
            "reporting_period": str(record.get("reporting_period") or ""),
            "reporting_frequency": record.get("reporting_frequency"),
            "effective_date": record.get("effective_date"),
            "event_id": record.get("event_id"),
            "event_type": record.get("event_type"),
            "share_class": record.get("share_class"),
            "unit": record.get("unit"),
            "citation_id": record.get("citation_id"),
            "evidence_id": record.get("evidence_id"),
            "source_content_hashes": record.get("source_content_hashes"),
            "corroborated_value": record.get("corroborated_value"),
            "corroborated_source": record.get("corroborated_source"),
            "corroborated_on": record.get("corroborated_on"),
            "verified_at": record.get("verified_at"),
        }
        held = anchors.get(ticker)
        if held is None or _anchor_rank(candidate) > _anchor_rank(held):
            anchors[ticker] = candidate
    return anchors


def _anchor_rank(anchor: Mapping[str, Any]) -> tuple[int, str]:
    """Later evidence wins, and an event-dated count outranks a period-end one at any date.

    A 2024 period-end figure and a 2026 executed event are not two readings of the same thing:
    one describes a balance-sheet date, the other states the count the issuer holds today.
    """
    boundary = _anchor_boundary(anchor)
    return (1 if anchor.get("identity_type") == _EVENT_IDENTITY else 0,
            boundary.isoformat() if boundary else "")


def _anchor_boundary(anchor: Mapping[str, Any]) -> date | None:
    """The date the anchor's count is true as of."""
    stated = _as_date(anchor.get("effective_date"))
    if stated is not None:
        return stated
    period = str(anchor.get("reporting_period") or "")
    if str(anchor.get("reporting_frequency") or "") == "annual" and period.isdigit():
        return date(int(period), 12, 31)
    return None


def _promotion_refusal(anchor: Mapping[str, Any], boundary: date | None,
                       session_on: date | None, observed_on: date | None,
                       provider_value: Any, events: Sequence[Mapping[str, Any]]) -> str | None:
    """Why this anchor is not a current share count, or None when it is one.

    Each refusal names the missing fact rather than the missing feature, because every one of
    them is closed by acquiring a document, not by writing code.
    """
    if anchor.get("identity_type") != _EVENT_IDENTITY:
        return "anchor_is_a_period_end_figure_not_a_dated_current_count"
    if boundary is None:
        return "official_anchor_carries_no_resolvable_effective_date"
    if session_on is None or boundary > session_on:
        return "official_anchor_takes_effect_after_the_session"

    # The interval the anchor does not cover is [effective_date, session]. An independent
    # observation of the same absolute count closes it up to the date it was taken.
    witness = anchor.get("corroborated_value")
    if witness is None:
        return "no_independent_observation_corroborates_the_stated_count"
    if int(witness) != int(anchor["value"]):
        return "independent_observation_contradicts_the_stated_count"
    if provider_value is None or int(float(provider_value)) != int(anchor["value"]):
        return "retained_provider_observation_no_longer_matches_the_corroborated_count"
    if observed_on is None or observed_on < boundary:
        return "corroborating_observation_predates_the_event"

    # A share-changing event after the anchor would move the count again. The retained ledger
    # cannot prove none exists market-wide, but it can prove one does.
    for event in events:
        if event["event_class"] == "not_share_changing":
            continue
        exright = event["exright_date"]
        if exright is not None and exright > boundary:
            return "a_later_share_changing_event_is_recorded_after_the_anchor"
    return None


class _Store:
    """One read of every retained store, shared across a market-wide resolution."""

    def __init__(self, runtime_root: Path | str):
        self.runtime_root = Path(runtime_root)
        self.anchors = load_official_anchors(self.runtime_root)
        self.metadata: dict[str, tuple[float | None, Any]] = {}
        self.events: dict[str, list[dict[str, Any]]] = {}
        self.ledger_coverage: dict[str, str] = {}

        connection = _connect_ro(self.runtime_root / "vn_stock.db")
        try:
            for ticker, shares, updated in connection.execute(
                    "SELECT ticker, shares_outstanding, updated FROM metadata"):
                if ticker:
                    self.metadata[str(ticker).upper()] = (shares, updated)
            for ticker, code, exright, coverage in connection.execute(
                    "SELECT ticker, event_code, exright_date, coverage_status "
                    "FROM corporate_event_records"):
                if not ticker:
                    continue
                key = str(ticker).upper()
                self.events.setdefault(key, []).append({
                    "event_code": str(code or "").strip().upper(),
                    "event_class": _classify_event_code(code),
                    "exright_date": _as_date(exright),
                })
                self.ledger_coverage[key] = str(coverage or "unknown")
        except sqlite3.Error as exc:
            raise ShareStoreUnreadable(f"vn_stock.db unreadable: {exc}") from None
        finally:
            connection.close()

    def universe(self) -> list[str]:
        return sorted(self.metadata)


def _event_verdict(events: Iterable[Mapping[str, Any]], observed_on: date) -> dict[str, Any]:
    """Position the retained events against the observation date.

    Only an ex-right date positions a share-changing event; a record, issue, payment or
    listing date never substitutes for one, so an event missing it makes the observation's
    freshness unverifiable rather than either fresh or stale.
    """
    after: list[str] = []
    undated: list[str] = []
    for event in events:
        if event["event_class"] == "not_share_changing":
            continue
        exright = event["exright_date"]
        if exright is None:
            undated.append(event["event_code"])
        elif exright > observed_on:
            after.append(event["event_code"])
    return {"share_changing_after_observation": sorted(set(after)),
            "undated_share_relevant_events": sorted(set(undated))}


def _result(ticker: str, session_date: str, authority: str, *, value: int | None,
            status: str, reason: str | None = None, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "resolver_version": RESOLVER_VERSION,
        "ticker": ticker,
        "session_date": session_date,
        "value": value,
        "authority": authority,
        "status": status,
    }
    if reason:
        payload["reason"] = reason
    payload.update(extra)
    return payload


def resolve_effective_shares(ticker: str, runtime_root: Path | str, session_date: str,
                             *, store: _Store | None = None) -> dict[str, Any]:
    """Resolve one ticker's effective shares for a stated session.

    `session_date` is required. The previous revision defaulted it to a literal
    `"2026-07-30"`, so every caller that omitted it stamped one session's shares onto
    whatever session was actually being exported.
    """
    t = str(ticker).upper()
    session = str(session_date).strip()
    if not _as_date(session):
        raise ValueError(f"session_date must be an ISO date, got {session_date!r}")

    try:
        store = store if store is not None else _Store(runtime_root)
    except ShareStoreUnreadable as exc:
        return _result(t, session, "unresolved_error", value=None, status="unresolved_error",
                       reason=str(exc), share_concept="unknown_share_concept")

    session_on = _as_date(session)
    anchor = store.anchors.get(t)
    shares, updated = store.metadata.get(t, (None, None))
    observed_on = _as_date(updated)
    events = store.events.get(t, [])
    coverage = store.ledger_coverage.get(t, "absent")

    official: dict[str, Any] | None = None
    if anchor is not None:
        boundary = _anchor_boundary(anchor)
        official = {
            "official_anchor_value": anchor["value"],
            "official_anchor_period": anchor["reporting_period"],
            "official_anchor_share_class": anchor["share_class"],
            "official_anchor_citation_id": anchor["citation_id"],
            "official_anchor_effective_date": boundary.isoformat() if boundary else None,
        }
        # The promotion gate. An anchor is a current share count only when nothing is known to
        # have changed it between the anchor's date and the session, and only an anchor that
        # states an absolute count at a date can carry that weight at all. A period-end figure
        # cannot: it describes 31 December, and the interval from there to the session is
        # exactly what no retained evidence covers.
        refusal = _promotion_refusal(anchor, boundary, session_on, observed_on, shares,
                                     store.events.get(t, []))
        if refusal is None:
            return _result(t, session, "qualified_official", value=anchor["value"],
                           status="qualified", share_concept="current_common_shares_outstanding",
                           unit="shares", source="official_share_basis_citation",
                           lineage=("official executed corporate action stating shares_after, "
                                    "corroborated by an independent observation"),
                           **official)
        official["official_anchor_not_promoted_because"] = refusal
        official["ledger_coverage_status"] = coverage

    extra: dict[str, Any] = dict(official or {})

    if shares is None or isinstance(shares, bool) or float(shares) <= 0:
        return _result(t, session, "unavailable", value=None, status="unavailable",
                       reason="no positive retained provider share observation",
                       share_concept="unknown_share_concept", **extra)

    value = int(float(shares))
    extra.update({
        "share_concept": PROVIDER_SHARE_CONCEPT,
        "unit": "shares",
        "source": PROVIDER_SOURCE,
        "lineage": "retained_provider_metadata_issue_share",
        "observation_date": observed_on.isoformat() if observed_on else None,
    })

    if observed_on is None:
        return _result(t, session, "unknown_observation_date", value=None,
                       status="unknown_observation_date",
                       reason=f"metadata.updated is missing or unparseable ({updated!r})", **extra)

    verdict = _event_verdict(events, observed_on)
    extra["ledger_coverage_status"] = coverage
    extra.update(verdict)

    if verdict["share_changing_after_observation"]:
        return _result(t, session, "provider_reported_stale", value=None,
                       status="provider_reported_stale",
                       reason="invalidated_by_share_changing_event_after_observation", **extra)

    if verdict["undated_share_relevant_events"]:
        return _result(t, session, "provider_reported_unverifiable_freshness", value=None,
                       status="provider_reported_unverifiable_freshness",
                       reason="missing_explicit_official_ex_date_on_share_relevant_event", **extra)

    lag = (session_on - observed_on).days if session_on else None
    if lag is not None and lag > 0:
        return _result(t, session, "provider_reported_lagged", value=value,
                       status="provider_reported", observation_lag_days=lag,
                       freshness_proof=("ledger_covered" if coverage != "absent"
                                        else "absent_no_ledger_coverage"),
                       reason="observation predates the session; no ledger proves the absence "
                              "of a share-changing event in between", **extra)

    return _result(t, session, "provider_reported_current", value=value,
                   status="provider_reported", observation_lag_days=lag,
                   freshness_proof=("ledger_covered" if coverage != "absent"
                                    else "absent_no_ledger_coverage"), **extra)


def resolve_market_wide_shares(runtime_root: Path | str, session_date: str) -> dict[str, Any]:
    """Authority counts across the retained active universe, for a stated session.

    Every count here is measured on the call. The lanes partition the universe exactly, and
    `counts_reconcile` states that as a checked fact rather than leaving the reader to add up.
    """
    session = str(session_date).strip()
    if not _as_date(session):
        raise ValueError(f"session_date must be an ISO date, got {session_date!r}")

    measured_at = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        store = _Store(runtime_root)
    except ShareStoreUnreadable as exc:
        return {
            "resolver_version": RESOLVER_VERSION,
            "session_date": session,
            "measured_at": measured_at,
            "status": "unresolved_error",
            "reason": str(exc),
            "active_universe_count": None,
            "counts": None,
            "tickers": {},
        }

    tickers: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    for t in store.universe():
        result = resolve_effective_shares(t, runtime_root, session, store=store)
        tickers[t] = result
        authority = str(result["authority"])
        counts[authority] = counts.get(authority, 0) + 1

    universe = len(tickers)
    values_present = sum(1 for r in tickers.values() if r["value"] is not None)
    return {
        "resolver_version": RESOLVER_VERSION,
        "session_date": session,
        "measured_at": measured_at,
        "status": "measured",
        "source": "vn_stock.db:metadata + data/official-evidence/share_basis_citations.jsonl",
        "active_universe_count": universe,
        "counts": dict(sorted(counts.items())),
        "usable_share_value_count": values_present,
        "counts_reconcile": sum(counts.values()) == universe,
        "official_anchors_retained": len(store.anchors),
        "ledger_tickers_covered": len(store.events),
        "tickers": tickers,
    }
