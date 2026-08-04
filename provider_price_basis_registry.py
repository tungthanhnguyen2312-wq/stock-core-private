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
    }
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


def unexamined_providers_note() -> str:
    return (
        "Only VCI has an established price-basis verdict. Every other provider still "
        "passes on its citation's adjustment_status alone, which is the same conflation "
        "this module was created to fix -- it is simply not yet evidenced for them. "
        "Qualifying or disqualifying another provider needs its own bounded pilot."
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
