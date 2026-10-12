"""Bridges qualified ``official_corporate_action_ledger`` entries into the factor-chain
mapping shape consumed by ``price_basis_feature_fitness.price_series_context()``.

WHY THIS MODULE EXISTS
    ``official_corporate_action_ledger.py`` derives a per-event ``adjustment_factor`` with its
    own vocabulary (``qualification_state``, ``lifecycle_state``/``execution_status``,
    ``adjustment_factor_status``). ``price_basis_feature_fitness.price_series_context()``
    separately accepts a caller-supplied ``factor_chain`` mapping with a *different* required
    vocabulary (``status == "QUALIFIED"``, ``official_execution_status == "EXECUTED"``,
    ``ex_date_status == "EXPLICIT_OFFICIAL"``, ``knowledge_cutoff``). Nothing before this module
    converted one into the other; every caller either omitted ``factor_chain`` (leaving it
    ``NOT_PROVIDED``) or would have had to hand-write the translation per call site. This module
    is that one, single, deterministic translation -- it derives no new fact, computes no new
    factor, and invents no missing evidence. It only relabels an already-produced ledger verdict
    into the shape the fitness contract expects, or reports exactly why it cannot.

FAIL-CLOSED CLASSIFICATION
    Every ledger entry is classified into exactly one of six buckets before a factor-chain shape
    is built:

    FACTOR_CHAIN_QUALIFIED    -- executed, explicit official ex-date, ready factor, explicit
                                  knowledge/publication cutoff all present together.
    MISSING_EXPLICIT_EX_DATE  -- executed and otherwise ready, but no ``ex_date`` on the ledger
                                  entry. A ``record_date`` is never read as a substitute.
    NOT_EXECUTED              -- lifecycle/execution status has not reached ``executed``
                                  (``proposed``/``approved``/``announced``/``record_date_confirmed``).
                                  A planned/announced issuance is never treated as executed.
    CONFLICTING               -- the ledger recorded a document conflict or a violated
                                  cross-document share-count identity.
    FACTOR_NOT_APPLICABLE     -- the event type does not mechanically rescale the share count
                                  (e.g. ``cash_dividend``); the ledger itself marks the factor
                                  ``not_applicable`` for exactly this reason.
    OTHER_EVIDENCE_GAP        -- executed, conflict-free, explicit ex-date, but still missing
                                  something else required for QUALIFIED -- most commonly a
                                  missing ``stock_ratio`` on the ledger entry, or a missing
                                  caller-supplied knowledge/publication cutoff.

    Only ``FACTOR_CHAIN_QUALIFIED`` produces a factor-chain identity and a non-null
    ``adjustment_factor``. Every other bucket returns ``status: "NOT_QUALIFIED"`` with the exact
    reason codes that block it, which ``price_series_context()`` then correctly renders as
    ``UNQUALIFIED`` and downstream ``evaluate_feature_fitness()`` correctly renders as
    ``POINT_IN_TIME_SEMANTICS_UNQUALIFIED`` for ``PIT_BACKTEST``.

KNOWLEDGE/PUBLICATION CUTOFF IS NEVER DERIVED HERE
    ``official_corporate_action_ledger`` entries do not retain a publication or first-observed
    timestamp (only dates that describe the corporate event itself: ex-date, record date,
    payment/execution date). A knowledge/publication cutoff must therefore be supplied
    explicitly by the caller from retained temporal evidence -- typically
    ``bitemporal_semantic_contract.project_official_evidence_temporal_metadata()`` applied to
    the qualifying event's original source document/observation record. This module never
    defaults a missing cutoff to "now", never reads a filesystem modification time, and never
    upgrades a bucket to ``FACTOR_CHAIN_QUALIFIED`` without one.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Mapping, Sequence

CONTRACT_VERSION = "qualified_corporate_action_factor_chain/v1"
SCHEMA_VERSION = "1.0.0"

STATUS_QUALIFIED = "QUALIFIED"
STATUS_NOT_QUALIFIED = "NOT_QUALIFIED"

EXECUTED = "EXECUTED"
EX_DATE_EXPLICIT_OFFICIAL = "EXPLICIT_OFFICIAL"
EX_DATE_MISSING = "MISSING"

CLASSIFICATION_FACTOR_CHAIN_QUALIFIED = "FACTOR_CHAIN_QUALIFIED"
CLASSIFICATION_MISSING_EXPLICIT_EX_DATE = "MISSING_EXPLICIT_EX_DATE"
CLASSIFICATION_NOT_EXECUTED = "NOT_EXECUTED"
CLASSIFICATION_CONFLICTING = "CONFLICTING"
CLASSIFICATION_FACTOR_NOT_APPLICABLE = "FACTOR_NOT_APPLICABLE"
CLASSIFICATION_OTHER_EVIDENCE_GAP = "OTHER_EVIDENCE_GAP"
CLASSIFICATIONS = frozenset({
    CLASSIFICATION_FACTOR_CHAIN_QUALIFIED,
    CLASSIFICATION_MISSING_EXPLICIT_EX_DATE,
    CLASSIFICATION_NOT_EXECUTED,
    CLASSIFICATION_CONFLICTING,
    CLASSIFICATION_FACTOR_NOT_APPLICABLE,
    CLASSIFICATION_OTHER_EVIDENCE_GAP,
})

REASON_MISSING_EXPLICIT_EX_DATE = "missing_explicit_official_ex_date"
REASON_NOT_EXECUTED = "lifecycle_not_executed"
REASON_CONFLICTING_DOCUMENTS = "documents_conflict"
REASON_CONFLICTING_SHARE_IDENTITY = "share_count_identity_violated"
REASON_FACTOR_NOT_APPLICABLE = "event_type_not_dilutive_or_concentrating"
REASON_MISSING_KNOWLEDGE_CUTOFF = "missing_knowledge_publication_cutoff"
REASON_RECORD_DATE_NOT_EX_DATE = "record_date_does_not_establish_ex_date"

_EXECUTED_LIFECYCLE = "executed"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def classify_ledger_entry(entry: Mapping[str, Any]) -> tuple[str, list[str]]:
    """Deterministically classify one ``official_corporate_action_ledger`` entry.

    Uses only fields the ledger itself already computed. Never infers ex-date from record
    date, never infers execution from a planned/announced lifecycle, and never widens a
    ``not_applicable``/``not_ready`` ledger verdict into a qualified one.
    """
    if str(entry.get("qualification_state") or "") == "conflicted":
        reasons = [REASON_CONFLICTING_DOCUMENTS if entry.get("conflicts") else REASON_CONFLICTING_SHARE_IDENTITY]
        return CLASSIFICATION_CONFLICTING, reasons

    factor_status = str(entry.get("adjustment_factor_status") or "")
    if factor_status == "not_applicable":
        return CLASSIFICATION_FACTOR_NOT_APPLICABLE, [REASON_FACTOR_NOT_APPLICABLE]

    execution_status = str(entry.get("execution_status") or entry.get("lifecycle_state") or "").lower()
    if execution_status != _EXECUTED_LIFECYCLE:
        return CLASSIFICATION_NOT_EXECUTED, [f"{REASON_NOT_EXECUTED}:{execution_status or 'unknown'}"]

    if not entry.get("ex_date"):
        reasons = [REASON_MISSING_EXPLICIT_EX_DATE]
        if entry.get("record_date"):
            reasons.append(REASON_RECORD_DATE_NOT_EX_DATE)
        return CLASSIFICATION_MISSING_EXPLICIT_EX_DATE, reasons

    if factor_status != "ready" or entry.get("adjustment_factor") is None:
        blocked_by = list(entry.get("adjustment_factor_blocked_by") or [])
        return CLASSIFICATION_OTHER_EVIDENCE_GAP, blocked_by or ["adjustment_factor_not_ready"]

    return CLASSIFICATION_FACTOR_CHAIN_QUALIFIED, []


def build_factor_chain_entry(
    entry: Mapping[str, Any],
    *,
    knowledge_cutoff: str | None = None,
    knowledge_evidence_reason_codes: Sequence[str] = (),
) -> dict[str, Any]:
    """Build the ``factor_chain`` mapping shape ``price_series_context()`` expects.

    ``knowledge_cutoff`` must already be resolved by the caller from retained
    publication/first-observed evidence for the qualifying event's source document(s) (see
    module docstring). Its absence blocks ``FACTOR_CHAIN_QUALIFIED`` even when every other
    requirement is met -- this mirrors ``price_basis_feature_fitness``'s own PIT gate, which
    requires a knowable-by-decision-cutoff factor, not merely a computed one.
    """
    classification, class_reasons = classify_ledger_entry(entry)
    reason_codes: set[str] = set(class_reasons)
    is_qualified = classification == CLASSIFICATION_FACTOR_CHAIN_QUALIFIED
    if is_qualified and not knowledge_cutoff:
        is_qualified = False
        classification = CLASSIFICATION_OTHER_EVIDENCE_GAP
        reason_codes.add(REASON_MISSING_KNOWLEDGE_CUTOFF)
    reason_codes.update(str(reason) for reason in knowledge_evidence_reason_codes if str(reason).strip())

    ex_date = entry.get("ex_date")
    event_id = entry.get("event_id")
    identity: str | None = None
    if is_qualified:
        identity_payload = {
            "contract_version": CONTRACT_VERSION,
            "event_id": event_id,
            "ticker": entry.get("ticker"),
            "event_type": entry.get("event_type"),
            "ex_date": ex_date,
            "adjustment_factor": entry.get("adjustment_factor"),
            "knowledge_cutoff": str(knowledge_cutoff),
            "source_content_hashes": entry.get("source_content_hashes"),
        }
        identity = "qualified_corporate_action_factor_chain:" + _identity(identity_payload)

    execution_status = str(entry.get("execution_status") or entry.get("lifecycle_state") or "").lower()

    return {
        "contract_version": CONTRACT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "identity": identity,
        "factor_chain_identity": identity,
        "status": STATUS_QUALIFIED if is_qualified else STATUS_NOT_QUALIFIED,
        "classification": classification,
        "official_execution_status": EXECUTED if execution_status == _EXECUTED_LIFECYCLE else execution_status.upper() or "UNKNOWN",
        "ex_date_status": EX_DATE_EXPLICIT_OFFICIAL if ex_date else EX_DATE_MISSING,
        "ex_date": ex_date,
        "record_date": entry.get("record_date"),
        "knowledge_cutoff": str(knowledge_cutoff) if (is_qualified and knowledge_cutoff) else None,
        "event_types": [str(entry.get("event_type"))] if entry.get("event_type") else [],
        "adjustment_factor": entry.get("adjustment_factor") if is_qualified else None,
        "adjustment_authority": entry.get("adjustment_authority"),
        "authority_state": entry.get("authority_state"),
        "source_event_id": event_id,
        "source_ledger_entry_identity": event_id,
        "source_document_ids": list(entry.get("source_document_ids") or []),
        "source_content_hashes": list(entry.get("source_content_hashes") or []),
        "reason_codes": sorted(reason_codes) if reason_codes else [],
    }


def build_factor_chain_cohort(
    ledger: Mapping[str, Any],
    *,
    knowledge_cutoff_resolver: Callable[[Mapping[str, Any]], tuple[str | None, Sequence[str]]] | None = None,
) -> dict[str, Any]:
    """Classify every entry in an ``official_corporate_action_ledger`` result.

    Evidence chooses the cohort: this walks every retained ledger entry and reports its
    classification and (where qualifying) its factor-chain shape. It never pre-selects tickers.
    ``knowledge_cutoff_resolver``, when supplied, is called once per ledger entry and must
    return ``(knowledge_cutoff, reason_codes)`` derived from retained temporal evidence for that
    entry's source documents; when omitted, no entry can reach ``FACTOR_CHAIN_QUALIFIED``.
    """
    entries = list(ledger.get("entries") or [])
    counts: dict[str, int] = {classification: 0 for classification in sorted(CLASSIFICATIONS)}
    events: list[dict[str, Any]] = []
    for entry in entries:
        cutoff, cutoff_reasons = (None, ())
        if knowledge_cutoff_resolver is not None:
            cutoff, cutoff_reasons = knowledge_cutoff_resolver(entry)
        chain = build_factor_chain_entry(entry, knowledge_cutoff=cutoff, knowledge_evidence_reason_codes=cutoff_reasons)
        counts[chain["classification"]] = counts.get(chain["classification"], 0) + 1
        events.append({
            "event_id": entry.get("event_id"),
            "ticker": entry.get("ticker"),
            "event_type": entry.get("event_type"),
            "classification": chain["classification"],
            "factor_chain": chain,
        })
    return {
        "contract_version": CONTRACT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "cohort_size": len(entries),
        "classification_counts": counts,
        "qualified_count": counts.get(CLASSIFICATION_FACTOR_CHAIN_QUALIFIED, 0),
        "events": events,
    }


def contract_summary() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "classifications": sorted(CLASSIFICATIONS),
        "record_date_inferred_as_ex_date": False,
        "planned_issuance_treated_as_executed": False,
        "authority_effect": "NONE",
    }
