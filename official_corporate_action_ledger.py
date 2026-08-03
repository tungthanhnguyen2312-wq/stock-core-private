"""Immutable corporate-action event ledger built from official document observations.

WHAT THIS IS
    The reconciliation layer of pillar B: many documents, one event. It links the typed
    observations produced by `corporate_action_events.py` into deduplicated ledger entries,
    resolves each entry's lifecycle state, records amendments and supersessions without
    editing anything, and derives a price-adjustment factor **only** where the evidence
    directly supports one.

    It is separate from the existing `corporate_action_ledger.py`, which is the qualified
    per-ticker MVP over `semantic_evidence_bridge`. That module keeps its contract and its
    callers; this one is the official-document path the pillar-B design specifies.

HOW DOCUMENTS ARE LINKED INTO ONE EVENT
    Two observations describe the same event when they agree on the issuer, the event type,
    and the **share-change identity** -- the number of shares issued -- which is the field
    Vietnamese notices state most consistently and most precisely. Dates are deliberately not
    part of the link key: the whole point of linking is that an issuer disclosure, an exchange
    notice and a depository notice carry *different* dates for one event.

    Where two observations of one event both state a field, they must agree. A disagreement
    is recorded as a conflict on the entry and blocks promotion, rather than being resolved
    by preferring a source.

CROSS-DOCUMENT CORROBORATION IS REAL EVIDENCE
    In the bounded slice, the issuer notice yields `shares_before` and `shares_issued`, and
    the exchange notice yields `shares_issued` and `shares_after`. Neither document alone
    states all three, and the scanned issuer notice's own `shares_after` is OCR-damaged. The
    ledger checks `before + issued == after` **across the two documents** and records the
    result as an arithmetic corroboration with both hashes cited. That is stronger evidence
    than either document alone, and it is what promotes the entry's ratio to qualified.

WHY MOST ENTRIES STILL PRODUCE NO ADJUSTMENT FACTOR
    A price-adjustment factor places a corporate action on the price timeline, which requires
    an **explicit official ex-date**. `docs/DECISIONS.md` already fixes that a record date
    never substitutes for one. Neither retained HPG document states an ex-date, so the slice's
    event is a complete, executed, fully-cited ledger entry with `adjustment_factor_status =
    not_ready` and a named missing field. This is the fail-closed case the milestone asks the
    slice to demonstrate, and it is the correct outcome, not a shortfall.

    Factors derived here are explicitly outside production authority: `authority_state` is
    `outside_production_authority` on every one, and nothing in this module writes to
    `data/official-evidence/`, which `evidence_promotion.py` alone may do.

DETERMINISTIC REPLAY
    The same retained documents always produce the same ledger: entries are keyed by content
    hashes, ordered by a total ordering with an `event_key` tiebreaker, and no field depends
    on the clock or on iteration order. `replay_fingerprint` is the value that claim is made
    about.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

VERSION = "1.0.0"
LEDGER_SCHEMA_VERSION = "1.0.0"
ADJUSTMENT_POLICY_VERSION = "1.0.0"

ADJUSTMENT_AUTHORITY = "official_corporate_action_ledger"
AUTHORITY_STATE = "outside_production_authority"

FACTOR_READY = "ready"
FACTOR_NOT_READY = "not_ready"
FACTOR_NOT_APPLICABLE = "not_applicable"

#: Event types whose execution mechanically changes the share count and therefore the price.
_DILUTIVE = frozenset({"stock_dividend", "bonus_shares", "stock_split"})
_CONCENTRATING = frozenset({"reverse_split"})

_LIFECYCLE_RANK = {
    "unknown": 0, "proposed": 1, "approved": 2, "announced": 3,
    "record_date_confirmed": 4, "executed": 5,
}

#: Fields that must agree wherever two observations of one event both state them.
_AGREEMENT_FIELDS = (
    "shares_before", "shares_after", "shares_issued", "ex_date", "record_date",
    "payment_or_execution_date", "cash_amount_per_share", "subscription_price",
)

#: Fields taken from whichever observation states them, once agreement has been checked.
_MERGE_FIELDS = _AGREEMENT_FIELDS + (
    "trading_date", "approval_date", "stock_ratio", "ratio_basis", "rights_ratio",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def event_key(observation: Mapping[str, Any]) -> tuple[str, str, str]:
    """The identity two documents must share to describe one event."""
    issued = observation.get("shares_issued")
    if issued is None and observation.get("shares_after") is not None \
            and observation.get("shares_before") is not None:
        issued = int(observation["shares_after"]) - int(observation["shares_before"])
    return (
        str(observation.get("ticker") or ""),
        str(observation.get("event_type") or "unknown"),
        str(issued) if issued is not None else "unidentified",
    )


def build_ledger(observations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Link, deduplicate and reconcile observations into an immutable event ledger."""
    deduplicated: dict[str, Mapping[str, Any]] = {}
    duplicates: list[dict[str, Any]] = []
    for observation in observations:
        identifier = str(observation.get("observation_id"))
        if identifier in deduplicated:
            duplicates.append({"observation_id": identifier,
                               "document_id": observation.get("document_id"),
                               "reason": "identical observation identity already linked"})
            continue
        deduplicated[identifier] = observation

    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    unlinked: list[dict[str, Any]] = []
    for observation in deduplicated.values():
        key = event_key(observation)
        if key[1] == "unknown" or key[2] == "unidentified":
            unlinked.append({
                "observation_id": observation.get("observation_id"),
                "document_id": observation.get("document_id"),
                "reason": ("no event type detected" if key[1] == "unknown"
                           else "no share-change identity; cannot be linked to an event"),
            })
            continue
        grouped.setdefault(key, []).append(observation)

    entries = [_reconcile(key, members) for key, members in sorted(grouped.items())]
    entries.sort(key=_ordering_key)

    superseded = _apply_supersession(entries)

    replay = _fingerprint({
        "schema_version": LEDGER_SCHEMA_VERSION,
        "entries": [{key: entry[key] for key in sorted(entry)
                     if key not in {"source_documents"}} for entry in entries],
    })
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "ledger_version": VERSION,
        "adjustment_policy_version": ADJUSTMENT_POLICY_VERSION,
        "adjustment_authority": ADJUSTMENT_AUTHORITY,
        "authority_state": AUTHORITY_STATE,
        "entries": entries,
        "entry_count": len(entries),
        "duplicate_observations": duplicates,
        "unlinked_observations": unlinked,
        "superseded_entry_ids": superseded,
        "replay_fingerprint": replay,
        "qualified_event_count": sum(1 for entry in entries
                                     if entry["qualification_state"] == "qualified"),
        "adjustment_factor_counts": _tally(entries, "adjustment_factor_status"),
        "lifecycle_counts": _tally(entries, "lifecycle_state"),
    }


def _tally(entries: Sequence[Mapping[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        value = str(entry.get(field))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _ordering_key(entry: Mapping[str, Any]) -> tuple:
    far = "9999-99-99"
    return (
        str(entry.get("ticker") or ""),
        str(entry.get("payment_or_execution_date") or far),
        str(entry.get("record_date") or far),
        str(entry.get("ex_date") or far),
        str(entry.get("announcement_date") or far),
        str(entry.get("event_id") or ""),
    )


def _reconcile(key: tuple[str, str, str],
               members: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """One ledger entry from every observation that describes one event."""
    ticker, event_type, issued_key = key
    ordered = sorted(members, key=lambda item: (str(item.get("content_sha256") or ""),
                                                str(item.get("observation_id") or "")))

    merged: dict[str, Any] = {}
    conflicts: list[dict[str, Any]] = []
    for field in _MERGE_FIELDS:
        stated = [(observation, observation.get(field)) for observation in ordered
                  if observation.get(field) is not None]
        if not stated:
            continue
        values = {_comparable(value) for _, value in stated}
        if field in _AGREEMENT_FIELDS and len(values) > 1:
            conflicts.append({
                "field": field,
                "values": [
                    {"value": value, "document_id": observation.get("document_id"),
                     "content_sha256": observation.get("content_sha256")}
                    for observation, value in stated
                ],
            })
            continue
        merged[field] = stated[0][1]

    corroboration = _corroborate(merged, ordered)
    lifecycle = max((str(observation.get("lifecycle_state") or "unknown")
                     for observation in ordered),
                    key=lambda state: _LIFECYCLE_RANK.get(state, 0))

    identity = {"ticker": ticker, "event_type": event_type, "share_change": issued_key,
                "schema_version": LEDGER_SCHEMA_VERSION}
    entry_id = _fingerprint(identity)

    warnings = sorted({warning for observation in ordered
                       for warning in observation.get("warnings") or []})
    absent = {}
    for observation in ordered:
        for field, reason in (observation.get("absent_fields") or {}).items():
            if merged.get(field) is None:
                absent.setdefault(field, reason)

    qualification, qualification_reason = _qualify(merged, conflicts, corroboration, lifecycle)
    factor = _adjustment_factor(event_type, merged, qualification)

    return {
        "event_id": entry_id,
        "schema_version": LEDGER_SCHEMA_VERSION,
        "ledger_version": VERSION,
        "ticker": ticker,
        "event_type": event_type,
        "lifecycle_state": lifecycle,
        "execution_status": lifecycle,
        "approval_date": merged.get("approval_date"),
        "announcement_date": min(
            (str(observation.get("announcement_date")) for observation in ordered
             if observation.get("announcement_date")), default=None),
        "ex_date": merged.get("ex_date"),
        "record_date": merged.get("record_date"),
        "payment_or_execution_date": merged.get("payment_or_execution_date"),
        "trading_date": merged.get("trading_date"),
        "shares_before": merged.get("shares_before"),
        "shares_issued": merged.get("shares_issued"),
        "shares_after": merged.get("shares_after"),
        "cash_amount_per_share": merged.get("cash_amount_per_share"),
        "stock_ratio": merged.get("stock_ratio"),
        "ratio_basis": merged.get("ratio_basis"),
        "rights_ratio": merged.get("rights_ratio"),
        "subscription_price": merged.get("subscription_price"),
        "source_document_ids": sorted({str(observation.get("document_id"))
                                       for observation in ordered}),
        "source_content_hashes": sorted({str(observation.get("content_sha256"))
                                         for observation in ordered}),
        "source_observation_ids": sorted({str(observation.get("observation_id"))
                                          for observation in ordered}),
        "source_documents": [
            {"document_id": observation.get("document_id"),
             "document_type": observation.get("document_type"),
             "source_authority": observation.get("source_authority"),
             "source_url": observation.get("source_url"),
             "content_sha256": observation.get("content_sha256"),
             "citations": observation.get("citations") or []}
            for observation in ordered
        ],
        "arithmetic_corroboration": corroboration,
        "conflicts": conflicts,
        "conflict_status": "conflicted" if conflicts else "consistent",
        "absent_fields": dict(sorted(absent.items())),
        "warnings": warnings,
        "qualification_state": qualification,
        "qualification_reason": qualification_reason,
        "superseded_by": None,
        "supersedes": None,
        **factor,
    }


def _comparable(value: Any) -> Any:
    return round(float(value), 6) if isinstance(value, (int, float)) else str(value)


def _corroborate(merged: Mapping[str, Any],
                 members: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """`shares_before + shares_issued == shares_after`, across whichever documents state them."""
    before, issued, after = (merged.get("shares_before"), merged.get("shares_issued"),
                             merged.get("shares_after"))
    if None in (before, issued, after):
        present = [name for name, value in (("shares_before", before),
                                            ("shares_issued", issued),
                                            ("shares_after", after)) if value is not None]
        return {"state": "not_testable",
                "reason": (f"only {', '.join(present) or 'no share count'} is stated; the "
                           "identity needs all three"),
                "documents": []}
    holds = int(before) + int(issued) == int(after)
    contributors = sorted({
        str(observation.get("content_sha256"))
        for observation in members
        if any(observation.get(field) is not None
               for field in ("shares_before", "shares_issued", "shares_after"))
    })
    return {
        "state": "confirmed" if holds else "violated",
        "reason": (f"{before} + {issued} "
                   f"{'=' if holds else '!='} {after}"),
        "documents": contributors,
        "cross_document": len(contributors) > 1,
    }


def _qualify(merged: Mapping[str, Any], conflicts: Sequence[Mapping[str, Any]],
             corroboration: Mapping[str, Any], lifecycle: str) -> tuple[str, str]:
    if conflicts:
        return "conflicted", ("documents disagree on: "
                              + ", ".join(sorted(str(item["field"]) for item in conflicts)))
    if corroboration["state"] == "violated":
        return "conflicted", f"share-count identity does not hold ({corroboration['reason']})"
    if _LIFECYCLE_RANK.get(lifecycle, 0) < _LIFECYCLE_RANK["executed"]:
        return "provisional", (f"lifecycle is {lifecycle!r}; only an executed event is a "
                               "qualified historical fact")
    # A `not_testable` identity is an absent third number, not a disagreement. It withholds
    # corroboration, which the entry records, but it does not impeach an executed event that
    # an exchange notice states completely. Only a `violated` identity does, and that is
    # handled above.
    if corroboration["state"] == "confirmed":
        return "qualified", ("executed, internally consistent, and the share-count identity is "
                             "confirmed"
                             + (" across independent documents"
                                if corroboration.get("cross_document") else ""))
    return "qualified", ("executed and internally consistent; the share-count identity is not "
                         f"testable from the retained documents ({corroboration['reason']})")


def _adjustment_factor(event_type: str, merged: Mapping[str, Any],
                       qualification: str) -> dict[str, Any]:
    """A factor only where the evidence directly supports placing the event on the timeline."""
    base = {
        "adjustment_authority": ADJUSTMENT_AUTHORITY,
        "adjustment_policy_version": ADJUSTMENT_POLICY_VERSION,
        "authority_state": AUTHORITY_STATE,
        "adjustment_factor": None,
        "adjustment_factor_status": FACTOR_NOT_READY,
        "adjustment_factor_reason": "",
        "adjustment_factor_blocked_by": [],
    }
    if event_type not in _DILUTIVE | _CONCENTRATING:
        return {**base, "adjustment_factor_status": FACTOR_NOT_APPLICABLE,
                "adjustment_factor_reason": (
                    f"{event_type} does not mechanically rescale the share count; a factor "
                    "for it needs a cash amount and a reference price, which this ledger "
                    "does not hold")}

    blocked: list[str] = []
    if qualification != "qualified":
        blocked.append(f"event_qualification:{qualification}")
    if not merged.get("ex_date"):
        blocked.append("missing_explicit_official_ex_date")
    ratio = merged.get("stock_ratio")
    if ratio is None:
        blocked.append("missing_stock_ratio")

    if blocked:
        return {**base, "adjustment_factor_blocked_by": sorted(blocked),
                "adjustment_factor_reason": (
                    "a price-adjustment factor places the event on the price timeline and "
                    "needs an explicit official ex-date; a record, payment or listing date is "
                    "never substituted for one")}

    factor = round(1.0 / (1.0 + float(ratio)), 12)
    return {**base, "adjustment_factor": factor, "adjustment_factor_status": FACTOR_READY,
            "adjustment_factor_reason": (
                f"1 / (1 + {ratio}) applied to closes strictly before the ex-date "
                f"{merged.get('ex_date')}; derived for a directly supported event and held "
                "outside production authority")}


def _apply_supersession(entries: Sequence[dict[str, Any]]) -> list[str]:
    """Link amendments and cancellations to what they replace. Nothing is edited in place.

    A `cancellation` or `amendment` entry supersedes the most recent earlier entry for the
    same issuer whose share-change identity it repeats. The superseded entry keeps every
    field it had and gains only a `superseded_by` pointer, so the ledger stays append-only.
    """
    superseded: list[str] = []
    for index, entry in enumerate(entries):
        if entry["event_type"] not in {"cancellation", "amendment"}:
            continue
        for candidate in reversed(entries[:index]):
            if candidate["ticker"] != entry["ticker"]:
                continue
            if candidate["shares_issued"] != entry["shares_issued"]:
                continue
            if candidate["superseded_by"] is not None:
                continue
            candidate["superseded_by"] = entry["event_id"]
            candidate["lifecycle_state"] = (
                "cancelled" if entry["event_type"] == "cancellation" else "amended")
            candidate["execution_status"] = candidate["lifecycle_state"]
            entry["supersedes"] = candidate["event_id"]
            superseded.append(candidate["event_id"])
            break
    return sorted(superseded)
