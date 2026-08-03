"""Derive promotable share-basis citations from the official corporate-action ledger (B1.1).

WHAT THIS IS FOR
    The ledger already produces qualified, hash-bound, executed events. One of them states
    HPG's share count outright: `shares_after = 8,442,964,520` as of 2026-07-02. Nothing read
    it. `market_wide_current_shares_resolver` looked for official anchors in
    `share_basis_citations.jsonl`, which held only FY2024 period-end figures, so the count the
    issuer had already published sat one directory away while the resolver reported HPG as
    `provider_reported_lagged`.

    This module is the reader that closes that gap. It selects the ledger entries that may
    become evidence and hands them to `evidence_promotion.promote()`, which remains the sole
    writer. Nothing here writes anything.

WHAT QUALIFIES, AND WHAT DOES NOT
    An entry is promotable only when all of these hold:

      * `qualification_state == "qualified"` — the ledger's own verdict, unchanged;
      * `lifecycle_state == "executed"` — a proposed or approved event has not happened;
      * `shares_after` is a positive integer the document states outright, not a difference
        this module computes;
      * an execution date exists (`payment_or_execution_date`, else `trading_date`);
      * the entry is neither superseded nor cancelled nor amended away;
      * at least one source content hash, so the value is traceable to retained bytes.

    An **ex-right date is not required**, and that is deliberate. An ex-date places an action
    on the price timeline, which is what a price-adjustment factor needs and why HPG's factor
    is correctly `not_ready`. A share count needs proof the event executed. Requiring an
    ex-date for both is what kept a published share count out of the evidence store.

WHAT THIS DOES NOT DECIDE
    Whether the resulting anchor makes a ticker's *current* shares qualified for a given
    session. That is the resolver's promotion gate: an anchor dated before the session still
    has to survive the question of what happened between the anchor and the session.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

VERSION = "1.0.0"

LEDGER_RELATIVE = Path("data") / "official-corporate-actions" / "event_ledger.json"

#: Event types that change the outstanding share count and therefore establish a new one.
SHARE_ESTABLISHING_EVENT_TYPES = frozenset({
    "stock_dividend", "bonus_issue", "rights_issue", "share_split", "share_consolidation",
    "esop_issue", "private_placement", "treasury_share_cancellation",
})

#: Lifecycle and revision states that disqualify an entry outright.
_WITHDRAWN_STATES = frozenset({"cancelled", "amended", "superseded", "withdrawn"})


class LedgerUnavailable(RuntimeError):
    """The retained ledger is missing or unreadable. Never reported as "no events"."""


def load_ledger(runtime_root: Path | str) -> dict[str, Any]:
    path = Path(runtime_root) / LEDGER_RELATIVE
    if not path.is_file():
        raise LedgerUnavailable(f"official event ledger not found at {LEDGER_RELATIVE}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LedgerUnavailable(f"official event ledger unreadable: {exc}") from None
    if not isinstance(payload, Mapping) or not isinstance(payload.get("entries"), list):
        raise LedgerUnavailable("official event ledger carries no entry list")
    return dict(payload)


def _execution_date(entry: Mapping[str, Any]) -> str | None:
    for field in ("payment_or_execution_date", "trading_date"):
        value = entry.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()[:10]
    return None


def entry_verdict(entry: Mapping[str, Any], superseded_ids: Iterable[str] = ()) -> dict[str, Any]:
    """Whether one ledger entry may establish a share count, with a named reason either way."""
    event_id = str(entry.get("event_id") or "")
    ticker = str(entry.get("ticker") or "").upper()
    base = {"event_id": event_id, "ticker": ticker,
            "event_type": str(entry.get("event_type") or "")}

    if event_id in set(superseded_ids) or entry.get("superseded_by"):
        return {**base, "promotable": False, "reason": "entry_superseded"}
    for field in ("lifecycle_state", "execution_status", "amendment_state", "revision_status"):
        if str(entry.get(field) or "").lower() in _WITHDRAWN_STATES:
            return {**base, "promotable": False, "reason": f"{field}_withdrawn_or_amended"}
    if str(entry.get("qualification_state") or "") != "qualified":
        return {**base, "promotable": False, "reason": "ledger_verdict_not_qualified"}
    if str(entry.get("lifecycle_state") or "") != "executed":
        return {**base, "promotable": False, "reason": "event_not_executed"}
    if base["event_type"] not in SHARE_ESTABLISHING_EVENT_TYPES:
        return {**base, "promotable": False, "reason": "event_type_does_not_change_share_count"}

    shares_after = entry.get("shares_after")
    if not isinstance(shares_after, (int, float)) or isinstance(shares_after, bool) or shares_after <= 0:
        return {**base, "promotable": False, "reason": "no_stated_shares_after"}

    effective_date = _execution_date(entry)
    if effective_date is None:
        return {**base, "promotable": False, "reason": "no_stated_execution_date"}

    hashes = [str(h) for h in (entry.get("source_content_hashes") or []) if h]
    if not hashes:
        return {**base, "promotable": False, "reason": "no_source_content_hash"}

    return {**base, "promotable": True, "reason": "qualified_executed_event_states_shares_after",
            "shares_after": int(shares_after), "effective_date": effective_date,
            "source_content_hashes": sorted(hashes),
            "evidence_id": (entry.get("source_document_ids") or [None])[0]}


def promotable_citations(runtime_root: Path | str, *, tickers: Iterable[str] | None = None,
                         corroboration: Mapping[str, Mapping[str, Any]] | None = None
                         ) -> dict[str, Any]:
    """Every citation the retained ledger supports, plus why each rejected entry was rejected.

    `corroboration` optionally carries an independent observation per ticker
    (`{"value": int, "source": str, "observed_on": str}`). It is recorded on the citation, not
    used to decide promotability: an official document stating its own result does not need a
    provider to agree before it may be retained as evidence. Disagreement is recorded and the
    entry is refused, because two sources contradicting each other is not evidence of either.
    """
    from evidence_promotion import build_share_basis_event_citation

    ledger = load_ledger(runtime_root)
    superseded = set(ledger.get("superseded_entry_ids") or [])
    wanted = {str(t).upper() for t in tickers} if tickers is not None else None
    corroboration = corroboration or {}

    citations: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for entry in ledger.get("entries") or []:
        verdict = entry_verdict(entry, superseded)
        if wanted is not None and verdict["ticker"] not in wanted:
            continue
        if not verdict["promotable"]:
            rejected.append(verdict)
            continue

        witness = corroboration.get(verdict["ticker"]) or {}
        witness_value = witness.get("value")
        if witness_value is not None and int(witness_value) != verdict["shares_after"]:
            rejected.append({**verdict, "promotable": False,
                             "reason": "independent_observation_contradicts_stated_shares_after",
                             "observed_value": int(witness_value)})
            continue

        citations.append(build_share_basis_event_citation(
            ticker=verdict["ticker"], shares_after=verdict["shares_after"],
            effective_date=verdict["effective_date"], event_id=verdict["event_id"],
            event_type=verdict["event_type"], evidence_id=str(verdict["evidence_id"] or ""),
            source_content_hashes=verdict["source_content_hashes"],
            corroborated_value=(int(witness_value) if witness_value is not None else None),
            corroborated_source=witness.get("source"),
            corroborated_on=witness.get("observed_on"),
            citation=f"{verdict['event_type']} executed {verdict['effective_date']}, "
                     f"shares_after stated by the issuer's own notice",
            verified_at=ledger.get("replay_fingerprint")))

    return {
        "version": VERSION,
        "ledger_replay_fingerprint": ledger.get("replay_fingerprint"),
        "ledger_entry_count": ledger.get("entry_count"),
        "citations": citations,
        "rejected": rejected,
    }
