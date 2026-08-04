"""Active, per-provider price-basis verdicts, and the supersession history behind them.

This module exists because the repository briefly held two contradictory active claims
about the same 1.9 million rows. Resolving that needs three things kept apart, which the
previous vocabulary ran together:

1. **The repository applied no adjustment of its own.** True of every VCI row, and it says
   nothing about the numbers.
2. **The provider returned already-adjusted values.** A fact about the source.
3. **The series is raw as-traded.** Only true when (1) *and* the negation of (2) hold.

`raw_as_quoted_no_adjustment_applied` named (1) and was read as (3). Every consumer that
gates on it is really asking (3), so the gate now lives here and answers (3) directly.

Nothing in this module authorises a downstream capability. A verdict is a description of a
series, and every production and actionability gate stays where it was.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

VERSION = "1.0.0"

# --- Vocabulary -------------------------------------------------------------------

HISTORICAL_MUTABILITY = frozenset({"immutable", "retrospectively_rewritten", "unknown"})

PRICE_BASIS = frozenset(
    {
        "raw_as_traded",
        "empirically_event_adjusted",
        "documented_adjusted",
        "conflicted",
        "unknown",
    }
)

ADJUSTMENT_DIMENSIONS = frozenset({"cash_distribution", "share_related_event"})

#: The legacy label. Retained so stored artifacts remain readable, never emitted as a new
#: verdict, and never sufficient on its own to establish a raw as-traded series.
LEGACY_NO_LOCAL_ADJUSTMENT_LABEL = "raw_as_quoted_no_adjustment_applied"


class PriceBasisConflict(ValueError):
    """Raised when active verdicts disagree, or a verdict is read past its supersession."""


# --- Active verdicts ---------------------------------------------------------------

_ACTIVE: dict[str, dict[str, Any]] = {
    "VCI": {
        "provider": "VCI",
        "status": "active",
        "source_field_identity": "observed",
        "historical_mutability": "retrospectively_rewritten",
        "price_basis": "empirically_event_adjusted",
        "observed_adjustment_dimensions": ["cash_distribution", "share_related_event"],
        "provider_methodology": "unknown",
        "unobserved_event_types": "unknown",
        "coverage_generalization": "not_authorized",
        "raw_as_traded_eligible": False,
        "official_exchange_price": False,
        "evidence": [
            "operations-review/vci-direct-basis-pilot-20260804/pilot_summary.json",
            "operations-review/vci-direct-basis-pilot-20260804/VCI_DIRECT_BASIS_PILOT.md",
        ],
        "established_at": "2026-08-04",
        "limitations": [
            "Three qualified events across three tickers, all in 2026. Older history, "
            "rights issues and par-value changes are untested.",
            "No first-party methodology exists, so which events the provider adjusts for "
            "-- and which it silently does not -- is unknown.",
        ],
    },
    "KBS": {
        "provider": "KBS",
        "status": "active",
        "source_field_identity": "observed",
        # Three distinct questions, kept apart because conflating them is how a control
        # result gets read as an immutability proof.
        #
        # 1. Event-time rewriting -- do historical rows change when a corporate action
        #    becomes effective? NOT TESTABLE from any retained pair. The earliest KBS
        #    payload for every tested window is 2026-08-04 and every qualified ex-right date
        #    in those windows precedes it, so both snapshots sit on the same side of the
        #    event. This is terminal for the retained evidence: a later request produces
        #    another post-event snapshot, and elapsed time is not the missing ingredient.
        #    Only a snapshot retained *before* a future event can answer it -- see
        #    kbs_mutability_protocol.
        # 2. Post-event snapshot stability -- observed over 2026-08-01..2026-08-04, 9
        #    sessions, no change. A real finding, and not evidence about (1).
        # 3. Volume corporate-action adjustment -- see volume_adjustment_basis below.
        "historical_mutability": "not_observed",
        "event_time_rewriting": "not_testable_from_retained_pairs",
        "event_time_rewriting_route": "prospective_pre_event_snapshot_required",
        "post_event_snapshot_stability": "observed_for_tested_retrieval_interval",
        "post_event_stability_interval": ["2026-08-01", "2026-08-04"],
        "price_basis": "empirically_event_adjusted",
        "price_basis_qualification": "empirically_deduced",
        "observed_adjustment_dimensions": ["cash_distribution", "share_related_event"],
        "provider_methodology": "unknown",
        "unobserved_event_types": "unknown",
        "coverage_generalization": "limited_to_tested_windows",
        "raw_as_traded_eligible": False,
        "official_exchange_price": False,
        "volume_unit": "shares",
        "trading_value_unit": "VND",
        "volume_unit_qualification": "empirically_deduced",
        "trading_value_unit_qualification": "empirically_deduced",
        # The price-range test earns the *quotient* of the two scales and nothing more --
        # (1,1) and (1000,1000) are indistinguishable by it in principle. The absolute
        # scale is earned separately, by two independent routes:
        #   primary  -- KBS returns integers exactly equal to a locally stored VCI series
        #               on 34 sessions across all three tickers, and VCI's volume unit was
        #               established from its own per-trade tape, not from a plausibility
        #               bound. Equality is impossible under a thousand-fold difference.
        #               Transfers magnitude only; VCI's market scope is NOT inherited.
        #   corroborating -- (1000,1000) implies HPG trading 27,485,500,000 shares on
        #               2026-05-18 against a retained 8,442,964,520 issued. Rejected with a
        #               1.63x margin.
        # Neither route can reach documented_verified, and the share count remains
        # inadmissible for valuation -- see unit_anchor_admissible_for_valuation.
        "unit_scale_ratio": 1.0,
        "absolute_scale": "resolved",
        "absolute_scale_anchor": "numeric_identity_with_an_independently_unit_qualified_series",
        "absolute_scale_corroborating_anchor": "issued_share_count_plausibility_falsifier",
        "unit_anchor_admissible_for_valuation": False,
        "volume_adjustment_basis": "not_observed",
        "volume_adjustment_route": "prospective_pre_event_snapshot_spanning_a_share_event",
        "volume_market_scope": "unknown",
        "liquidity_actionable": False,
        "evidence": [
            "operations-review/kbs-empirical-basis-20260804/basis_summary.json",
            "operations-review/kbs-empirical-basis-20260804/evidence_manifest.json",
            "operations-review/kbs-empirical-basis-20260804/KBS_EMPIRICAL_BASIS.md",
            "operations-review/kbs-empirical-closeout-20260804/KBS_EMPIRICAL_CLOSEOUT.md",
        ],
        "established_at": "2026-08-04",
        "limitations": [
            "Three qualified events across three tickers, all HOSE, all in 2026. Older "
            "history, rights issues, par-value changes and other exchanges are untested.",
            "No first-party methodology exists, so which events the provider adjusts for "
            "-- and which it silently does not -- is unknown.",
            "The unit result fixes the ratio of the two scales from the price range; the "
            "absolute scale rests on numeric identity with a VCI series whose own unit "
            "verdict is itself only empirically deduced, corroborated by an unqualified "
            "issued-share count used solely as an order-of-magnitude falsifier.",
            "Two of thirty-eight eligible rows are explained by no candidate scale and are "
            "retained as contradictions rather than resolved.",
            "Event-time historical rewriting is untestable from any retained evidence and "
            "cannot be made testable by re-requesting an already-post-event window.",
        ],
    },
}

# --- Supersession history ----------------------------------------------------------

_SUPERSEDED: tuple[dict[str, Any], ...] = (
    {
        "verdict_id": "phase3a_vci_price_basis",
        "provider": "VCI",
        "status": "superseded",
        "asserted_value": LEGACY_NO_LOCAL_ADJUSTMENT_LABEL,
        "asserted_in": [
            "operations-review/phase3a-qualified-vci-price-benchmark.json (manifest.price_basis)",
            "qualified_price_storage_benchmark.py (module constant BASIS)",
        ],
        "asserted_scope": "1,923,111 exported VCI rows, 1,686 tickers, 2014-06-25..2026-07-28",
        "asserted_at": "phase 3A",
        "root_cause": "unsupported_assumption_conflating_no_local_adjustment_with_provider_raw",
        "root_cause_detail": (
            "The value was a hard-coded module constant stamped onto every exported row and "
            "into the manifest. It was never derived from a payload, never gated on evidence "
            "and never verified. What it truthfully recorded is that the export applies no "
            "adjustment of its own; it was then read as a statement about the provider."
        ),
        "superseded_by": "provider_price_basis_registry:VCI@1.0.0",
        "superseded_at": "2026-08-04",
        "superseding_evidence": [
            "Returned prices sit off the HOSE tick lattice, so they were never matched order prices.",
            "The off-lattice prefix terminates exactly at a qualified ex-date for VCB "
            "(2026-07-23 cash), HPG (2026-05-25 share issue) and VNM (2026-06-26 cash).",
            "A pre-ex-date database snapshot shows 13/13 VCB closes rewritten afterwards, "
            "while a no-event control re-request returned byte-identical bytes.",
        ],
        "retained_for": "provenance; the artifact and its history are not deleted",
    },
    {
        "verdict_id": "phase1c_kbs_fields_unusable",
        "provider": "KBS",
        "status": "superseded",
        # Note what is *not* superseded. Phase 1C's factual findings were all correct and
        # are re-affirmed by this milestone: the payload carries no adjustment flag, no unit
        # declaration and no trade-method metadata, and none exists in the adapter either.
        "asserted_value": "fields_unusable_because_no_documented_semantics_were_found",
        "retained_correct_for": (
            "No documented semantic metadata exists for the KBS OHLCV fields. Re-confirmed "
            "on 2026-08-04 against six freshly retrieved payloads: the response carries "
            "t/o/h/l/c/v/va and nothing else."
        ),
        "asserted_in": [
            "operations-review/phase_1c_kbs_ohlcv_semantics_20260801T081200Z.md "
            "(KBS_PRICE_BASIS: ABSENT, KBS_VOLUME_BASIS: ABSENT, "
            "PROVIDER_QUALIFICATION_BRANCH_CLOSED: YES)"
        ],
        "asserted_scope": "the KBS daily OHLCV lane in its entirety",
        "asserted_at": "phase 1C, 2026-08-01",
        "root_cause": "absence_of_documentation_treated_as_absence_of_usable_data",
        "root_cause_detail": (
            "The report established that the provider publishes no semantics and then "
            "concluded that every consumer must fail closed. Those are different claims. "
            "A field can have a known identity and a reproducibly demonstrated behaviour "
            "and still no first-party definition, and a chart of the series was never a "
            "claim about adjustment or market composition in the first place."
        ),
        "superseded_by": "provider_price_basis_registry:KBS@1.0.0",
        "superseded_at": "2026-08-04",
        "superseding_evidence": [
            "Pre-event prices sit off the HOSE tick lattice, so they were never matched "
            "order prices; the off-lattice prefix terminates exactly at a qualified "
            "ex-right date for HPG (2026-05-25 share issue), VCB (2026-07-23 cash) and "
            "VNM (2026-06-26 cash).",
            "The provider omits `va` over exactly the off-lattice runs and emits it over "
            "exactly the on-lattice ones, in all six windows -- an independent second "
            "signal that tracks the boundary rather than the calendar.",
            "36 of 38 eligible rows across three tickers place va/v inside the session "
            "range at one scale quotient, and every competing quotient is rejected.",
            "Two no-event control windows produced no boundary, which is what falsifies the "
            "event attribution if it is wrong.",
        ],
        "narrowed_to": (
            "documented_semantics=absent; field_identity=qualified; "
            "empirical_semantics=partially_available; descriptive_capability=available; "
            "technical_capability=provider_scoped_available; liquidity_capability=unavailable"
        ),
        "retained_for": "provenance; the report and its findings are not deleted or edited",
    },
)


def active_verdict(provider: str) -> dict[str, Any]:
    """The one active verdict for a provider, or an explicit *absence* of one.

    A provider with no entry gets ``raw_as_traded_eligible: None`` -- unknown, not False.
    The distinction matters: this registry blocks what has been *shown* to be ineligible,
    and silently reclassifying every unexamined provider as ineligible would be a policy
    change wearing the costume of a bug fix. Providers other than VCI were not examined by
    the pilot that created this module and are deliberately left where they were; see
    :func:`unexamined_providers_note`.
    """
    record = _ACTIVE.get(str(provider).strip().upper())
    if record is None:
        return {
            "provider": str(provider).strip().upper(),
            "status": "no_established_verdict",
            "price_basis": "unknown",
            "historical_mutability": "unknown",
            "raw_as_traded_eligible": None,
            "official_exchange_price": False,
            "coverage_generalization": "not_authorized",
        }
    return dict(record)


EXAMINED_PROVIDERS = ("VCI", "KBS")


def unexamined_providers_note() -> str:
    return (
        "VCI and KBS have established price-basis verdicts, each from its own bounded "
        "lane and neither inherited from the other. Every other provider still passes on "
        "its citation's adjustment_status alone, which is the same conflation this module "
        "was created to fix -- it is simply not yet evidenced for them. Qualifying or "
        "disqualifying another provider needs its own bounded lane."
    )


def blocks_raw_as_traded(provider: str) -> bool:
    """True only when a provider has been *shown* not to serve a raw as-traded series."""
    return active_verdict(provider).get("raw_as_traded_eligible") is False


def superseded_verdicts(provider: str | None = None) -> list[dict[str, Any]]:
    """Superseded verdicts, retained with provenance. Never returned as active."""
    wanted = str(provider).strip().upper() if provider else None
    return [dict(r) for r in _SUPERSEDED if wanted is None or r["provider"] == wanted]


def is_superseded(verdict_id: str) -> bool:
    return any(record["verdict_id"] == verdict_id for record in _SUPERSEDED)


def raw_as_traded_eligible(provider: str) -> bool:
    """Whether a stored series from this provider may be treated as raw as-traded.

    Returns False only for a provider shown ineligible. An unexamined provider is not
    blocked here -- see :func:`active_verdict` and :func:`unexamined_providers_note`.
    """
    return not blocks_raw_as_traded(provider)


def ineligibility_reason(provider: str) -> str | None:
    """Why a provider is not raw-as-traded eligible, for a rejection record."""
    verdict = active_verdict(provider)
    if not blocks_raw_as_traded(provider):
        return None
    if verdict.get("historical_mutability") == "retrospectively_rewritten":
        return "provider_series_retrospectively_rewritten"
    # Not the same as unqualified. A series shown to be event-adjusted has a *qualified*
    # basis; it is simply not the as-traded one. Reporting that as "unqualified" is what
    # made an undocumented provider read as an unusable one.
    if verdict.get("price_basis") in {
        "empirically_event_adjusted",
        "cash_distribution_adjusted_observed",
        "share_event_adjusted_observed",
        "documented_adjusted",
    }:
        return "provider_series_empirically_event_adjusted_not_as_traded"
    return "provider_price_basis_unqualified"


def assert_not_conflated(
    *, local_adjustment_applied: bool, provider: str, claimed_basis: str
) -> None:
    """Refuse the inference "we adjusted nothing, therefore the series is raw".

    ``local_adjustment_applied`` is a fact about this repository. It is accepted as an
    argument precisely so the refusal can be explicit: no value of it makes a series raw
    when the provider is not eligible.
    """
    if claimed_basis != "raw_as_traded":
        return
    if blocks_raw_as_traded(provider):
        raise PriceBasisConflict(
            "no_local_adjustment_does_not_establish_provider_raw:"
            f"{provider}:{ineligibility_reason(provider)}:"
            f"local_adjustment_applied={local_adjustment_applied}"
        )


def resolve_active(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Collapse candidate verdicts for one provider into a single active verdict.

    Superseded records are ignored. Two *active* records that disagree do not get a winner
    chosen for them -- recency is not evidence -- so the result is ``conflicted`` and every
    downstream gate stays shut.
    """
    live = [dict(r) for r in records if r.get("status") != "superseded"]
    if not live:
        return {"price_basis": "unknown", "status": "active", "raw_as_traded_eligible": False}
    bases = {str(r.get("price_basis")) for r in live}
    if len(bases) > 1:
        return {
            "price_basis": "conflicted",
            "status": "active",
            "raw_as_traded_eligible": False,
            "official_exchange_price": False,
            "conflicting_values": sorted(bases),
            "reason": "two_active_verdicts_disagree_and_recency_is_not_evidence",
        }
    return live[0]


def assert_single_active_verdict(records: Iterable[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Fail closed rather than let two contradictory active verdicts coexist."""
    resolved = resolve_active(records)
    if resolved.get("price_basis") == "conflicted":
        raise PriceBasisConflict(f"conflicting_active_price_basis:{resolved['conflicting_values']}")
    return resolved
