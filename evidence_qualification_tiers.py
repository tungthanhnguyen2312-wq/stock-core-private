"""The canonical ladder for *how well* a claim is evidenced, separate from *what* it claims.

WHY THIS MODULE EXISTS
    Until this milestone the repository had two states for a source semantic: qualified, or
    unknown. That binary is what closed the KBS lane in Phase 1C. The reasoning there was
    sound as far as it went -- the provider publishes no adjustment, unit or composition
    metadata, so nothing about KBS is *documented*. The step that did not follow is the one
    that was taken next: that undocumented therefore means unusable, and the fields should
    be treated as absent.

    A field can have a known identity, a reproducibly demonstrated behaviour, and still no
    first-party definition. That is a real and common state, and collapsing it into
    ``unknown`` throws away work that was actually done. So the ladder has a rung for it.

WHAT THE MIDDLE RUNG COSTS
    :data:`EMPIRICALLY_DEDUCED` is not a cheaper spelling of qualified. A verdict at that
    tier must carry its whole apparatus -- method, scope, artifacts, the alternatives that
    were considered and the falsification that was attempted -- and
    :func:`assert_empirically_deduced` refuses one that does not. That is deliberate: the
    tier is only safe to have in the vocabulary if claiming it is more work than claiming
    ``unknown``, not less.

WHAT IT NEVER BUYS
    An empirical deduction never becomes a documented one, however many windows agree. It
    cannot support an official-exchange claim, and cross-source agreement cannot raise it --
    two undocumented sources agreeing are compatible, not authoritative. Those are enforced
    by :func:`may_claim_official_semantics` and :func:`apply_corroboration`.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

VERSION = "1.0.0"

# ---------------------------------------------------------------------------------
# The ladder
# ---------------------------------------------------------------------------------

#: The provider, or an authoritative first-party source, explicitly defines the field or
#: the methodology. Only this tier speaks for the source.
DOCUMENTED_VERIFIED = "documented_verified"

#: A reproducible and falsifiable test supports a *narrowly scoped* conclusion. The scope
#: is part of the verdict, not a footnote on it.
EMPIRICALLY_DEDUCED = "empirically_deduced"

#: The field exists and its immediate identity is known -- this number is the closing
#: price -- but its economic basis is unresolved.
OBSERVED_ONLY = "observed_only"

#: Available evidence is insufficient.
UNKNOWN = "unknown"

#: Two active evidence paths disagree and no justified supersession resolves them.
CONFLICTED = "conflicted"

#: A prior verdict was demonstrated false.
INVALIDATED = "invalidated"

TIERS: tuple[str, ...] = (
    DOCUMENTED_VERIFIED,
    EMPIRICALLY_DEDUCED,
    OBSERVED_ONLY,
    UNKNOWN,
    CONFLICTED,
    INVALIDATED,
)

#: Strength ordering, used only to answer "does this tier support that claim". It is not a
#: conflict resolver -- see :func:`resolve_active`.
_STRENGTH: dict[str, int] = {
    DOCUMENTED_VERIFIED: 4,
    EMPIRICALLY_DEDUCED: 3,
    OBSERVED_ONLY: 2,
    UNKNOWN: 1,
    CONFLICTED: 0,
    INVALIDATED: 0,
}


class QualificationError(ValueError):
    """Fail-closed rejection in the qualification ladder."""


def assert_tier(tier: str) -> str:
    if tier not in _STRENGTH:
        raise QualificationError(f"unknown_qualification_tier:{tier}")
    return tier


def outranks(tier: str, other: str) -> bool:
    """Whether ``tier`` is strictly stronger evidence than ``other``."""
    return _STRENGTH[assert_tier(tier)] > _STRENGTH[assert_tier(other)]


def may_claim_official_semantics(tier: str) -> bool:
    """Only a first-party definition may be presented as the source's own meaning.

    An empirical deduction describes what a series *does*. An official claim asserts what
    the source *says it is*, and no amount of observation produces that.
    """
    return assert_tier(tier) == DOCUMENTED_VERIFIED


# ---------------------------------------------------------------------------------
# What an empirically deduced verdict must carry
# ---------------------------------------------------------------------------------

#: Every field an ``empirically_deduced`` verdict must retain. Absent any one of them, the
#: verdict cannot be reproduced or attacked by a later reader, which is precisely what
#: separates this tier from a hunch.
EMPIRICAL_RECORD_FIELDS: tuple[str, ...] = (
    "test_method",
    "tested_fields",
    "tested_tickers",
    "tested_date_windows",
    "event_evidence",
    "raw_artifact_hashes",
    "transformation_version",
    "alternative_explanations_considered",
    "falsification_attempts",
    "confidence",
    "scope_limitations",
    "retrieval_timestamps",
    "historical_mutability",
)

#: Fields that must be non-empty, not merely present. A verdict that considered no
#: alternative explanation and attempted no falsification is an observation, not a
#: deduction, and the empty list is the tell.
_MUST_BE_NON_EMPTY: frozenset[str] = frozenset(
    {
        "test_method",
        "tested_fields",
        "tested_tickers",
        "tested_date_windows",
        "raw_artifact_hashes",
        "transformation_version",
        "alternative_explanations_considered",
        "falsification_attempts",
        "confidence",
        "scope_limitations",
        "retrieval_timestamps",
    }
)

CONFIDENCE_LEVELS = frozenset({"low", "moderate", "high"})

#: The only admissible coverage statement for an empirical verdict. A deduction from three
#: windows says nothing about the fourth, so there is no vocabulary here for "applies
#: generally" -- the value would have no evidence behind it.
COVERAGE_LIMITED = "limited_to_tested_windows"
COVERAGE_NOT_AUTHORIZED = "not_authorized"
COVERAGE_STATES = frozenset({COVERAGE_LIMITED, COVERAGE_NOT_AUTHORIZED})


def assert_empirically_deduced(record: Mapping[str, Any]) -> dict[str, Any]:
    """Refuse an ``empirically_deduced`` verdict that cannot be reproduced or falsified.

    The check is deliberately unforgiving about emptiness. A caller that has genuinely
    considered no alternative explanation should be recording ``observed_only``.
    """
    missing = [field for field in EMPIRICAL_RECORD_FIELDS if field not in record]
    if missing:
        raise QualificationError(f"empirical_record_fields_missing:{','.join(sorted(missing))}")
    empty = [
        field
        for field in _MUST_BE_NON_EMPTY
        if not record[field] and record[field] != 0
    ]
    if empty:
        raise QualificationError(f"empirical_record_fields_empty:{','.join(sorted(empty))}")
    if record["confidence"] not in CONFIDENCE_LEVELS:
        raise QualificationError(f"empirical_confidence_invalid:{record['confidence']}")
    coverage = record.get("coverage_generalization", COVERAGE_LIMITED)
    if coverage not in COVERAGE_STATES:
        raise QualificationError(f"empirical_coverage_generalization_invalid:{coverage}")
    windows = record["tested_date_windows"]
    if not isinstance(windows, Sequence) or isinstance(windows, (str, bytes)):
        raise QualificationError("tested_date_windows_must_be_a_sequence")
    result = dict(record)
    result["qualification"] = EMPIRICALLY_DEDUCED
    result["coverage_generalization"] = coverage
    result["qualification_schema_version"] = VERSION
    return result


def assert_scope_not_exceeded(
    record: Mapping[str, Any], *, claimed_windows: Iterable[str]
) -> None:
    """Refuse a claim about a window the deduction never tested.

    This is the guard that makes ``limited_to_tested_windows`` mean something. Without it
    the phrase is a disclaimer; with it, quoting the verdict outside its evidence raises.
    """
    tested = {str(window) for window in record.get("tested_date_windows", [])}
    overreach = sorted({str(window) for window in claimed_windows} - tested)
    if overreach:
        raise QualificationError(f"claim_exceeds_tested_windows:{','.join(overreach)}")


def assert_single_window_insufficient(record: Mapping[str, Any]) -> None:
    """One event window cannot establish a provider-wide methodology.

    A single boundary is consistent with a general rule and with a one-off correction, and
    nothing inside that window distinguishes them. So a verdict resting on one window may
    describe that window and may not describe the provider.
    """
    windows = list(record.get("tested_date_windows", []))
    if len(windows) <= 1 and record.get("provider_methodology") not in (None, "", UNKNOWN):
        raise QualificationError(
            "single_window_cannot_establish_provider_methodology:"
            f"{record.get('provider_methodology')}"
        )


# ---------------------------------------------------------------------------------
# Corroboration and conflict
# ---------------------------------------------------------------------------------


def apply_corroboration(
    record: Mapping[str, Any], *, corroboration: Mapping[str, Any]
) -> dict[str, Any]:
    """Attach corroborating evidence without letting it change the tier.

    Cross-source agreement, a media report, a fitted factor: each is worth recording and
    none is an authority. The tier is copied through unchanged and the fact that it was
    *not* raised is written down, so a later reader cannot mistake the attachment for a
    promotion.
    """
    result = dict(record)
    attached = list(result.get("corroboration", []))
    attached.append(dict(corroboration))
    result["corroboration"] = attached
    result["corroboration_upgraded_qualification"] = False
    result["qualification"] = assert_tier(str(record.get("qualification", UNKNOWN)))
    return result


def resolve_active(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Collapse candidate verdicts about one proposition into one active verdict.

    Superseded and invalidated records are set aside. Two live records that disagree are
    reported as ``conflicted``: recency is not evidence, and neither is tier strength when
    both paths are live -- a stronger tier disagreeing with a weaker one is still a
    disagreement somebody has to adjudicate with a justified supersession.
    """
    live = [
        dict(record)
        for record in records
        if record.get("status") not in {"superseded", "invalidated"}
        and record.get("qualification") != INVALIDATED
    ]
    if not live:
        return {"verdict": None, "qualification": UNKNOWN, "status": "no_live_evidence"}
    verdicts = {str(record.get("verdict")) for record in live}
    if len(verdicts) > 1:
        return {
            "verdict": None,
            "qualification": CONFLICTED,
            "status": "active",
            "conflicting_values": sorted(verdicts),
            "reason": "two_live_evidence_paths_disagree",
            "note": "Recency does not resolve a conflict, and neither does tier strength "
            "alone; a justified supersession does.",
        }
    winner = max(live, key=lambda record: _STRENGTH[assert_tier(str(record.get("qualification", UNKNOWN)))])
    return dict(winner)


def supersede(
    *, prior: Mapping[str, Any], superseding: Mapping[str, Any], justification: str
) -> dict[str, Any]:
    """Record a justified supersession, keeping the prior evidence chain intact.

    A supersession names *which proposition* was too broad. The prior record is retained
    with the narrower claim it was right about, because deleting it would delete the
    evidence that produced the correction.
    """
    if not str(justification).strip():
        raise QualificationError("supersession_requires_a_justification")
    if not str(prior.get("retained_correct_for", "")).strip():
        raise QualificationError("supersession_must_state_what_the_prior_verdict_got_right")
    retained = dict(prior)
    retained["status"] = "superseded"
    return {
        "schema_version": VERSION,
        "superseded": retained,
        "superseding": dict(superseding),
        "justification": justification,
        "resolved_by": "justified_supersession",
        "resolved_by_recency": False,
    }
