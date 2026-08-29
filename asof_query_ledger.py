"""As-of query and revision ledger for Stock Lookup temporal evidence.

This module is the A3 milestone: deterministic knowledge-cutoff query and revision
inspection over already-retained qualified temporal evidence from A1/A2.

It allows downstream research code to answer, without hindsight leakage:

  Given a research cutoff / knowledge time, which retained evidence observation
  or revision was actually knowable and eligible at that time, and how did later
  observations revise or supersede it?

AUTHORITY INVARIANTS (inherited from A1/A2, never relaxed here):
- RAW_AS_TRADED: NOT_PROMOTED
- Historical price PIT: BLOCKED
- Historical full-system backtest: BLOCKED
- Same-close execution eligibility: NOT_ESTABLISHED
- EOD research-session eligibility != same-close execution eligibility

This is infrastructure/semantic capability only.
It does NOT promote any authority by its existence.
A dataset that lacks sufficient retained temporal evidence correctly
produces UNKNOWN/BLOCKED at query time -- that is the correct result.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Iterable, Mapping

from bitemporal_semantic_contract import (
    KnowledgeTimeStatus,
    HistoricalReconstructionScope,
    canonical_json,
)

ASOF_QUERY_CONTRACT_VERSION = "asof_query_ledger/v1"


# ---------------------------------------------------------------------------
# Enum base
# ---------------------------------------------------------------------------

class _ValueEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover
        return self.value


# ---------------------------------------------------------------------------
# Result reason codes -- follow existing A1 KnowledgeTimeStatus vocabulary
# ---------------------------------------------------------------------------

class AsofResultCode(_ValueEnum):
    """Discriminated result from an as-of query."""

    READY = "READY"
    """Exactly one qualifying observation is knowable as of the cutoff."""

    UNKNOWN_TEMPORAL = "UNKNOWN_TEMPORAL"
    """Temporal evidence is present but insufficient (LEGACY_UNKNOWN receipt,
    missing first_observed, timezone-unaware, etc.).  Fail closed."""

    NOT_YET_KNOWABLE = "NOT_YET_KNOWABLE"
    """The observation exists in the current repository but its knowledge
    boundary is strictly after the requested as-of cutoff."""

    NO_QUALIFYING_OBSERVATION = "NO_QUALIFYING_OBSERVATION"
    """No observation matching the requested identity/domain/entity exists
    in the supplied evidence set at all."""

    CONFLICT = "CONFLICT"
    """Multiple observations satisfy the as-of boundary and deterministic
    resolution is not permitted by existing identity semantics."""


class RevisionKnowabilityCode(_ValueEnum):
    KNOWABLE = "KNOWABLE"
    NOT_YET_KNOWABLE = "NOT_YET_KNOWABLE"
    UNKNOWN_TEMPORAL = "UNKNOWN_TEMPORAL"


# ---------------------------------------------------------------------------
# Ledger entry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LedgerEntry:
    """A single observation/revision in the ledger for one logical identity.

    Attributes follow Section 3.2 of the A3 milestone spec.  All fields are
    sourced exclusively from retained A1/A2 temporal evidence; none are
    inferred from filesystem timestamps, HTTP metadata, or current row order.
    """
    observation_identity: str | None
    """SHA-256 or other immutable raw-byte identity from A2 receipt."""

    valid_time_reference: str | None
    """Period-end, reference session, or effective date from A1 valid_time."""

    publication_time: str | None
    """Source publication timestamp (qualified official only; None otherwise)."""

    publication_precision: str | None
    """EXACT_DATETIME / DATE_ONLY / UNKNOWN from A1."""

    first_observed_at: str | None
    """UTC first-observed timestamp from A2 receipt (None for LEGACY_UNKNOWN)."""

    first_observed_status: str
    """RETAINED or LEGACY_UNKNOWN."""

    knowledge_available_research_session: str | None
    """The earliest research session at which this observation was knowable."""

    knowledge_time_status: str
    """KnowledgeTimeStatus value from A1 projection."""

    historical_reconstruction_scope: str
    """HistoricalReconstructionScope value from A1."""

    supersedes_identity: str | None = None
    """Observation identity this entry supersedes, if established by A2."""

    content_provenance: str | None = None
    """Source identity or document reference for lineage."""

    knowability_at_cutoff: RevisionKnowabilityCode = RevisionKnowabilityCode.UNKNOWN_TEMPORAL
    """Whether this specific entry was knowable at the as-of cutoff."""

    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["knowability_at_cutoff"] = self.knowability_at_cutoff.value
        return d


# ---------------------------------------------------------------------------
# As-of query result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AsofQueryResult:
    """Deterministic result of an as-of knowledge-cutoff query."""

    result_code: AsofResultCode
    as_of_research_session: str | None
    selected_observation_identity: str | None
    selected_valid_time: str | None
    selected_knowledge_session: str | None
    excluded_future_observation_identities: tuple[str | None, ...]
    conflict_observation_identities: tuple[str | None, ...]
    ledger: tuple[LedgerEntry, ...]
    authority_boundaries: Mapping[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": ASOF_QUERY_CONTRACT_VERSION,
            "result_code": self.result_code.value,
            "as_of_research_session": self.as_of_research_session,
            "selected_observation_identity": self.selected_observation_identity,
            "selected_valid_time": self.selected_valid_time,
            "selected_knowledge_session": self.selected_knowledge_session,
            "excluded_future_observation_identities": list(self.excluded_future_observation_identities),
            "conflict_observation_identities": list(self.conflict_observation_identities),
            "ledger": [entry.to_dict() for entry in self.ledger],
            "authority_boundaries": dict(self.authority_boundaries),
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_AUTHORITY_INVARIANTS: dict[str, str] = {
    "raw_as_traded": "NOT_PROMOTED",
    "historical_price_pit": "BLOCKED",
    "historical_full_system_backtest": "BLOCKED",
    "same_session_close_execution": "NOT_ESTABLISHED",
    "invariant": "ASOF_QUERY_DOES_NOT_PROMOTE_ANY_AUTHORITY",
}


def _parse_date(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


class _KnowledgeResolutionProxy:
    """Lightweight proxy used for per-entry eligibility checks."""
    __slots__ = ("knowledge_time_status", "knowledge_available_research_session", "historical_reconstruction_scope")

    def __init__(self, *, knowledge_time_status: str, knowledge_available_research_session: str | None,
                 historical_reconstruction_scope: str) -> None:
        self.knowledge_time_status = knowledge_time_status
        self.knowledge_available_research_session = knowledge_available_research_session
        self.historical_reconstruction_scope = historical_reconstruction_scope


def _is_reconstruction_eligible(kr_proxy: _KnowledgeResolutionProxy, as_of: str) -> bool:
    """Return True iff the observation was knowable as of the given session date.

    Fail-closed: KNOWLEDGE_UNKNOWN -> False; HistoricalReconstructionScope.NONE -> False.
    Never backfills or infers from current state.
    """
    if kr_proxy.knowledge_time_status == KnowledgeTimeStatus.KNOWLEDGE_UNKNOWN.value:
        return False
    if kr_proxy.historical_reconstruction_scope == HistoricalReconstructionScope.NONE.value:
        return False
    session = _parse_date(kr_proxy.knowledge_available_research_session)
    as_of_date = _parse_date(as_of)
    if not session or not as_of_date:
        return False
    return as_of_date >= session


def _knowability_code(kr_proxy: _KnowledgeResolutionProxy, as_of: str) -> RevisionKnowabilityCode:
    if kr_proxy.knowledge_time_status == KnowledgeTimeStatus.KNOWLEDGE_UNKNOWN.value:
        return RevisionKnowabilityCode.UNKNOWN_TEMPORAL
    if _is_reconstruction_eligible(kr_proxy, as_of):
        return RevisionKnowabilityCode.KNOWABLE
    return RevisionKnowabilityCode.NOT_YET_KNOWABLE


def _extract_ledger_entry(obs: Mapping[str, Any], as_of: str) -> LedgerEntry:
    """Build one LedgerEntry from a retained observation / A1 projection dict.

    Supports both flat A2 receipt format and nested A1 TemporalEnvelope format.
    """
    kr_raw: Mapping[str, Any] = obs.get("knowledge_resolution") or {}
    obs_time_raw: Mapping[str, Any] = obs.get("observation_time") or {}
    pub_time_raw: Mapping[str, Any] = obs.get("publication_time") or {}
    valid_time_raw: Mapping[str, Any] = obs.get("valid_time") or {}

    # Observation identity (A2 raw bytes SHA-256, or A1 derived)
    obs_identity = (
        obs.get("observation_identity")
        or obs_time_raw.get("observation_identity")
        or obs.get("sha256")
        or obs.get("document_sha256")
    )

    # Valid time reference
    valid_ref = (
        obs.get("valid_time_reference")
        or valid_time_raw.get("reference_session")
        or valid_time_raw.get("period_end")
        or valid_time_raw.get("effective_from")
    )

    # Publication (transport metadata NOT used)
    pub_at = pub_time_raw.get("source_published_at") or obs.get("source_published_at")
    pub_prec = pub_time_raw.get("source_published_at_precision") or obs.get("source_published_at_precision")

    # First observed (from A2 receipt; None for LEGACY_UNKNOWN)
    first_obs = obs_time_raw.get("first_observed_at") or obs.get("first_observed_at")
    first_status = obs_time_raw.get("first_observed_status") or obs.get("first_observed_status") or "LEGACY_UNKNOWN"

    # Knowledge resolution fields from A1 projection
    knowledge_session = kr_raw.get("knowledge_available_research_session") or obs.get("knowledge_available_research_session")
    kt_status = str(kr_raw.get("knowledge_time_status") or obs.get("knowledge_time_status") or KnowledgeTimeStatus.KNOWLEDGE_UNKNOWN.value)
    hr_scope = str(kr_raw.get("historical_reconstruction_scope") or obs.get("historical_reconstruction_scope") or HistoricalReconstructionScope.NONE.value)

    # Supersession and provenance (only from A2 same-logical-identity hash rule)
    supersedes = obs.get("supersedes_identity") or obs.get("supersedes_sha256")
    provenance = (
        obs.get("content_provenance")
        or pub_time_raw.get("source_identity")
        or obs.get("source_identity")
        or obs.get("document_id")
    )

    kr_proxy = _KnowledgeResolutionProxy(
        knowledge_time_status=kt_status,
        knowledge_available_research_session=knowledge_session,
        historical_reconstruction_scope=hr_scope,
    )
    knowability = _knowability_code(kr_proxy, as_of)

    warnings: list[str] = []
    if kt_status == KnowledgeTimeStatus.KNOWLEDGE_UNKNOWN.value:
        warnings.append("TEMPORAL_EVIDENCE_INSUFFICIENT_KNOWLEDGE_UNKNOWN")
    if first_status == "LEGACY_UNKNOWN" and not pub_at:
        warnings.append("NO_TRUSTWORTHY_RECEIPT_AND_NO_QUALIFIED_PUBLICATION")

    return LedgerEntry(
        observation_identity=obs_identity,
        valid_time_reference=valid_ref,
        publication_time=pub_at,
        publication_precision=pub_prec,
        first_observed_at=first_obs,
        first_observed_status=first_status,
        knowledge_available_research_session=knowledge_session,
        knowledge_time_status=kt_status,
        historical_reconstruction_scope=hr_scope,
        supersedes_identity=supersedes,
        content_provenance=provenance,
        knowability_at_cutoff=knowability,
        warnings=tuple(warnings),
    )


def _ledger_sort_key(e: LedgerEntry) -> tuple[str, str]:
    """Deterministic sort: knowledge session asc, then observation identity."""
    session = e.knowledge_available_research_session or "9999-99-99"
    identity = e.observation_identity or ""
    return (session, identity)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def query_as_of(
    observations: Iterable[Mapping[str, Any]],
    as_of_research_session: str,
) -> AsofQueryResult:
    """Deterministic as-of query over a set of retained temporal observations.

    Parameters
    ----------
    observations:
        Iterable of dicts representing retained temporal observations.
        Supports A1 TemporalEnvelope projection format (nested) or flat A2
        receipt envelope format.

    as_of_research_session:
        Knowledge cutoff as a YYYY-MM-DD research session date.
        Only observations knowable on or before this session may be selected.

    Returns
    -------
    AsofQueryResult with result_code one of:
      READY                     - exactly one qualifying observation selected
      UNKNOWN_TEMPORAL          - temporal evidence missing/insufficient
      NOT_YET_KNOWABLE          - all observations exist but are after cutoff
      NO_QUALIFYING_OBSERVATION - no observation present at all
      CONFLICT                  - multiple candidates, resolution not deterministic

    PIT safety invariants:
    - Never selects an observation whose knowledge_available_research_session
      is strictly after as_of_research_session.
    - Fails closed when knowledge_time_status == KNOWLEDGE_UNKNOWN.
    - HTTP Date/Last-Modified/ETag are never used for knowledge determination.
    - Does not promote RAW_AS_TRADED, PIT, backtest, or execution authority.
    - Research-session eligibility does not imply same-close execution eligibility.
    """
    as_of = _parse_date(as_of_research_session)
    if not as_of:
        return AsofQueryResult(
            result_code=AsofResultCode.UNKNOWN_TEMPORAL,
            as_of_research_session=as_of_research_session,
            selected_observation_identity=None,
            selected_valid_time=None,
            selected_knowledge_session=None,
            excluded_future_observation_identities=(),
            conflict_observation_identities=(),
            ledger=(),
            authority_boundaries=_AUTHORITY_INVARIANTS,
            warnings=("AS_OF_RESEARCH_SESSION_NOT_A_VALID_DATE",),
        )

    obs_list = list(observations)
    if not obs_list:
        return AsofQueryResult(
            result_code=AsofResultCode.NO_QUALIFYING_OBSERVATION,
            as_of_research_session=as_of,
            selected_observation_identity=None,
            selected_valid_time=None,
            selected_knowledge_session=None,
            excluded_future_observation_identities=(),
            conflict_observation_identities=(),
            ledger=(),
            authority_boundaries=_AUTHORITY_INVARIANTS,
        )

    # Build ordered ledger
    ledger_entries = sorted(
        [_extract_ledger_entry(obs, as_of) for obs in obs_list],
        key=_ledger_sort_key,
    )

    knowable: list[LedgerEntry] = []
    future: list[LedgerEntry] = []
    unknown_temporal: list[LedgerEntry] = []

    for entry in ledger_entries:
        if entry.knowability_at_cutoff == RevisionKnowabilityCode.KNOWABLE:
            knowable.append(entry)
        elif entry.knowability_at_cutoff == RevisionKnowabilityCode.NOT_YET_KNOWABLE:
            future.append(entry)
        else:
            unknown_temporal.append(entry)

    excluded_future = tuple(e.observation_identity for e in future)

    if not knowable and not unknown_temporal:
        return AsofQueryResult(
            result_code=AsofResultCode.NOT_YET_KNOWABLE,
            as_of_research_session=as_of,
            selected_observation_identity=None,
            selected_valid_time=None,
            selected_knowledge_session=None,
            excluded_future_observation_identities=excluded_future,
            conflict_observation_identities=(),
            ledger=tuple(ledger_entries),
            authority_boundaries=_AUTHORITY_INVARIANTS,
            warnings=("ALL_OBSERVATIONS_NOT_YET_KNOWABLE_AT_CUTOFF",),
        )

    if not knowable:
        # Only UNKNOWN_TEMPORAL entries -- fail closed
        return AsofQueryResult(
            result_code=AsofResultCode.UNKNOWN_TEMPORAL,
            as_of_research_session=as_of,
            selected_observation_identity=None,
            selected_valid_time=None,
            selected_knowledge_session=None,
            excluded_future_observation_identities=excluded_future,
            conflict_observation_identities=(),
            ledger=tuple(ledger_entries),
            authority_boundaries=_AUTHORITY_INVARIANTS,
            warnings=("TEMPORAL_EVIDENCE_INSUFFICIENT_FAIL_CLOSED",),
        )

    if len(knowable) == 1:
        selected = knowable[0]
        return AsofQueryResult(
            result_code=AsofResultCode.READY,
            as_of_research_session=as_of,
            selected_observation_identity=selected.observation_identity,
            selected_valid_time=selected.valid_time_reference,
            selected_knowledge_session=selected.knowledge_available_research_session,
            excluded_future_observation_identities=excluded_future,
            conflict_observation_identities=(),
            ledger=tuple(ledger_entries),
            authority_boundaries=_AUTHORITY_INVARIANTS,
        )

    # Multiple knowable -- try supersession chain resolution
    superseded_ids = {e.supersedes_identity for e in knowable if e.supersedes_identity}
    non_superseded = [e for e in knowable if e.observation_identity not in superseded_ids]

    if len(non_superseded) == 1:
        selected = non_superseded[0]
        return AsofQueryResult(
            result_code=AsofResultCode.READY,
            as_of_research_session=as_of,
            selected_observation_identity=selected.observation_identity,
            selected_valid_time=selected.valid_time_reference,
            selected_knowledge_session=selected.knowledge_available_research_session,
            excluded_future_observation_identities=excluded_future,
            conflict_observation_identities=(),
            ledger=tuple(ledger_entries),
            authority_boundaries=_AUTHORITY_INVARIANTS,
            warnings=("SUPERSESSION_CHAIN_RESOLVED_SINGLE_NON_SUPERSEDED",),
        )

    # Cannot resolve deterministically
    return AsofQueryResult(
        result_code=AsofResultCode.CONFLICT,
        as_of_research_session=as_of,
        selected_observation_identity=None,
        selected_valid_time=None,
        selected_knowledge_session=None,
        excluded_future_observation_identities=excluded_future,
        conflict_observation_identities=tuple(e.observation_identity for e in knowable),
        ledger=tuple(ledger_entries),
        authority_boundaries=_AUTHORITY_INVARIANTS,
        warnings=("MULTIPLE_KNOWABLE_CANDIDATES_DETERMINISTIC_RESOLUTION_NOT_PERMITTED",),
    )


def build_revision_ledger(
    observations: Iterable[Mapping[str, Any]],
    as_of_research_session: str,
) -> tuple[LedgerEntry, ...]:
    """Build the full ordered revision ledger for a set of retained observations.

    All observations are included regardless of knowability at the cutoff.
    Each entry records its own knowability at the requested cutoff.

    The ordering is deterministic: by resolved knowledge session (ascending),
    then by observation identity as tiebreaker.  Observations with UNKNOWN
    knowledge appear last.
    """
    as_of = _parse_date(as_of_research_session) or as_of_research_session
    entries = [_extract_ledger_entry(obs, as_of) for obs in observations]
    entries.sort(key=_ledger_sort_key)
    return tuple(entries)


def deterministic_ledger_hash(ledger: Iterable[LedgerEntry]) -> str:
    """Stable SHA-256 of the canonical serialised ledger for reproducibility."""
    payload = [entry.to_dict() for entry in ledger]
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def canonical_result_identity(result: AsofQueryResult) -> str:
    """Stable identity string for a complete as-of query result."""
    payload = result.to_dict()
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return f"{ASOF_QUERY_CONTRACT_VERSION}:{digest}"
