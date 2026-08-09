"""One queryable capability registry across providers, composing existing matrices.

WHY THIS MODULE EXISTS
    KBS already has a unified price+volume capability matrix (``kbs_capability_matrix.py``).
    VCI's volume side has an equally rigorous one (``market_volume_capability_matrix.py``),
    built from ``vci_volume_composition.py``. VCI's *price* side never had more than a flat
    eligibility list (``vci_direct_basis_pilot.SHADOW_PRICE_CAPABILITIES`` /
    ``BLOCKED_CAPABILITIES``) -- computable, but not named, classed or gated the way every
    other capability in this repository is. A caller who wanted "what can I compute from
    provider X's price series" had to know which of three modules to read, in two different
    vocabularies, one of which (the pilot's own ``PRICE_BASIS_VERDICTS``) predates the more
    conservative, supersession-aware verdict now held in ``provider_price_basis_registry.py``.

    This module resolves that by delegating, not re-deriving. For everything the existing
    matrices already cover (KBS whole, VCI volume) it is a thin pass-through -- same records,
    same objects, no re-classification. For the one real gap, VCI price, it wraps the
    already-established facts in ``provider_price_basis_registry.py`` in the exact shape the
    other two matrices use. No evidence is re-examined and no verdict is re-litigated.

WHAT IT ADDS ON TOP
    A capability ladder (Level 0-5, see ``LADDER_LEVELS``) that classifies every capability
    record -- from every underlying matrix -- by how far it sits from a generic actionable
    market basis. And a gap table (:func:`generic_unlock_gap_table`) naming, for each blocked
    *generic* capability, exactly what evidence is missing and what the next bounded action
    is. Both are read-only annotations over records the other matrices already produced;
    neither opens anything, and neither is itself a source of evidence.

WHAT IT DOES NOT DO
    It does not change ``is_actionable`` or ``liquidity_actionable`` anywhere -- those stay
    exactly what the underlying matrix already said. It does not let a provider verdict
    upgrade a generic field, and it does not let one provider's verdict speak for another's
    (:func:`assert_no_cross_provider_inheritance`). It does not compute anything from OHLCV
    data; see ``qualified_market_observations.py`` for that.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import kbs_capability_matrix as kbs
import market_volume_capability_matrix as vci_volume
import provider_price_basis_registry as price_registry
import vci_direct_basis_pilot as vci_pilot

VERSION = "1.1.0"

PROVIDERS = ("KBS", "VCI")


class RegistryError(ValueError):
    """Fail-closed refusal in the cross-provider capability registry."""


# ---------------------------------------------------------------------------------
# VCI price capabilities -- the one gap this module fills
# ---------------------------------------------------------------------------------
#
# Named directly from vci_direct_basis_pilot.SHADOW_PRICE_CAPABILITIES (the descriptive /
# technical side, unchanged) plus three point-in-time-truth capabilities named to mirror
# KBS's own CLASS_HISTORICAL_TRUTH set exactly, so the two providers are queried the same
# way. Gating uses provider_price_basis_registry -- the canonical, supersession-aware
# verdict -- never vci_direct_basis_pilot.PRICE_BASIS_VERDICTS, which is the pilot's own
# older internal vocabulary and predates the registry's conservative relabelling.

VCI_CLASS_DESCRIPTIVE = kbs.CLASS_DESCRIPTIVE
VCI_CLASS_CONDITIONAL = kbs.CLASS_CONDITIONAL
VCI_CLASS_HISTORICAL_TRUTH = kbs.CLASS_HISTORICAL_TRUTH

#: The label a VCI provider-series return or technical-continuity result must wear. Reuses
#: KBS's exact constant and forbidden-label set: the concept ("this is the provider's
#: series, not a market truth") is provider-agnostic and the two must not drift apart.
PROVIDER_SERIES_RETURN_LABEL = kbs.PROVIDER_SERIES_RETURN_LABEL
FORBIDDEN_RETURN_LABELS = kbs.FORBIDDEN_RETURN_LABELS

#: KBS's own required-warnings wording, with the one KBS-specific entry
#: (``provider_scoped_kbs_series``) swapped for VCI's. The other six say nothing about
#: which provider they belong to and are reused verbatim rather than restated.
VCI_REQUIRED_WARNINGS: tuple[str, ...] = tuple(
    "provider_scoped_vci_series" if w == "provider_scoped_kbs_series" else w
    for w in kbs.REQUIRED_WARNINGS
)
VCI_REQUIRED_PROVENANCE_FIELDS = kbs.REQUIRED_PROVENANCE_FIELDS

_VCI_PRICE_QUALIFIED_NOTE = (
    "VCI's active price verdict ({basis!r}) is a real, evidenced value -- not unknown or "
    "conflicted -- so a statement about the VCI series itself (its own shape, its own "
    "return, its own technical indicators) is supportable. It is not raw as-traded and "
    "must never be presented as one."
)


def _vci_price_verdict() -> Mapping[str, Any]:
    return price_registry.active_verdict("VCI")


def _vci_price_qualified() -> bool:
    """Whether VCI's price series has any real (non-unknown, non-conflicted) verdict.

    Mirrors ``vci_direct_basis_pilot.downstream_eligibility``'s own
    ``price_verdict not in {"inconclusive", "mixed_or_context_dependent"}`` test, restated
    against the canonical registry's vocabulary instead of the pilot's superseded one.
    """
    basis = str(_vci_price_verdict().get("price_basis", "unknown"))
    return basis not in {"unknown", "conflicted"}


def _vci_descriptive(name: str, note: str) -> dict[str, Any]:
    qualified = _vci_price_qualified()
    return {
        "capability": name,
        "capability_class": VCI_CLASS_DESCRIPTIVE,
        "availability": kbs.AVAILABLE_UNDER_EXISTING_GATES if qualified else kbs.UNAVAILABLE_BY_CONTRACT,
        "required_warnings": list(VCI_REQUIRED_WARNINGS) if qualified else [],
        "required_provenance_fields": list(VCI_REQUIRED_PROVENANCE_FIELDS) if qualified else [],
        "namespace": "provider_scoped",
        "reason": None if qualified else "vci_price_basis_has_no_established_verdict",
        "note": note,
    }


def _vci_conditional(name: str, note: str) -> dict[str, Any]:
    qualified = _vci_price_qualified()
    return {
        "capability": name,
        "capability_class": VCI_CLASS_CONDITIONAL,
        "availability": kbs.AVAILABLE_WITH_REQUIRED_LABEL if qualified else kbs.UNAVAILABLE_BY_CONTRACT,
        "required_label": PROVIDER_SERIES_RETURN_LABEL,
        "forbidden_labels": sorted(FORBIDDEN_RETURN_LABELS),
        "required_warnings": list(VCI_REQUIRED_WARNINGS) if qualified else [],
        "required_provenance_fields": list(VCI_REQUIRED_PROVENANCE_FIELDS) if qualified else [],
        "namespace": "provider_scoped",
        "reason": None if qualified else "vci_price_basis_has_no_established_verdict",
        "note": note,
    }


def _vci_historical_truth(name: str, note: str) -> dict[str, Any]:
    reason = price_registry.ineligibility_reason("VCI") or "vci_not_raw_as_traded_eligible"
    return {
        "capability": name,
        "capability_class": VCI_CLASS_HISTORICAL_TRUTH,
        "availability": kbs.UNAVAILABLE_BY_CONTRACT,
        "reason": reason,
        "reopen_condition": "documented_first_party_methodology_or_a_point_in_time_immutable_source",
        "required_warnings": [],
        "required_provenance_fields": [],
        "note": note,
    }


def _build_vci_price_matrix() -> dict[str, dict[str, Any]]:
    verdict = _vci_price_verdict()
    basis = str(verdict.get("price_basis", "unknown"))
    qualified_note = _VCI_PRICE_QUALIFIED_NOTE.format(basis=basis)
    return {
        # -- descriptive / technical, from vci_direct_basis_pilot.SHADOW_PRICE_CAPABILITIES
        "vci_namespaced_price_display": _vci_descriptive(
            "vci_namespaced_price_display",
            "Showing the retained VCI daily series as this repository normalised it. " + qualified_note,
        ),
        "vci_controlled_source_comparison": _vci_descriptive(
            "vci_controlled_source_comparison",
            "Comparing VCI against another provider to detect divergence. Agreement is "
            "compatibility evidence and never raises either provider's authority.",
        ),
        "vci_anomaly_detection": _vci_descriptive(
            "vci_anomaly_detection", "Outliers within the same provider series."
        ),
        "vci_isolated_shadow_evaluation": _vci_descriptive(
            "vci_isolated_shadow_evaluation",
            "Research-scope evaluation confined to the VCI-namespaced shadow lane.",
        ),
        "vci_namespaced_technical_indicators": _vci_conditional(
            "vci_namespaced_technical_indicators",
            "An already-adjusted series is continuous across an ex-date, which is what "
            "makes it usable for indicator continuity. " + qualified_note,
        ),
        "vci_namespaced_historical_returns": _vci_conditional(
            "vci_namespaced_historical_returns",
            "The series is event-adjusted, so a return computed over it is neither an "
            "as-traded return nor a total shareholder return -- it is this provider's "
            "series return, and it must say so. " + qualified_note,
        ),
        # -- point-in-time truth, unavailable by contract -- mirrors KBS's own three
        "vci_point_in_time_valuation": _vci_historical_truth(
            "vci_point_in_time_valuation",
            "The value the series reports for a past date is not necessarily the value "
            "that was quoted on that date (historical_mutability="
            f"{verdict.get('historical_mutability')!r}), so it cannot support a claim "
            "about what was knowable then.",
        ),
        "vci_official_exchange_price_claim": _vci_historical_truth(
            "vci_official_exchange_price_claim",
            "An observed web endpoint with no published schema is not the exchange.",
        ),
        "vci_official_total_return_claim": _vci_historical_truth(
            "vci_official_total_return_claim",
            "Total return requires a known distribution treatment. The method is undocumented.",
        ),
    }


#: Prohibitions that apply to *every* provider and every capability, not just one. Carried
#: from vci_direct_basis_pilot.BLOCKED_CAPABILITIES rather than re-typed, filtered to the
#: entries that are not already a named capability in a per-provider matrix (ranking,
#: recommendations, sizing and price targets are outcomes, not provider-scoped
#: computations, and never become available regardless of any basis finding).
UNIVERSAL_PROHIBITED_CAPABILITIES: tuple[str, ...] = tuple(
    sorted(
        set(vci_pilot.BLOCKED_CAPABILITIES)
        - {
            "days_to_liquidate",
            "market_impact_models",
            "liquidity_based_position_sizing",
        }
    )
)


# ---------------------------------------------------------------------------------
# Cross-provider dispatch
# ---------------------------------------------------------------------------------

_VCI_PRICE_MATRIX_CACHE: dict[str, dict[str, Any]] | None = None


def _vci_price_matrix() -> dict[str, dict[str, Any]]:
    global _VCI_PRICE_MATRIX_CACHE
    if _VCI_PRICE_MATRIX_CACHE is None:
        _VCI_PRICE_MATRIX_CACHE = _build_vci_price_matrix()
    return _VCI_PRICE_MATRIX_CACHE


def _normalize_provider(provider: str) -> str:
    named = str(provider).strip().upper()
    if named not in PROVIDERS:
        raise RegistryError(f"unregistered_provider:{named}")
    return named


def capability(provider: str, name: str) -> dict[str, Any]:
    """Look up one capability for one provider. Delegates; never re-derives.

    KBS capabilities (price and volume together) come from ``kbs_capability_matrix``
    unchanged. VCI volume capabilities come from ``market_volume_capability_matrix``
    unchanged. VCI price capabilities come from the small matrix built in this module from
    already-established facts. An unregistered name is refused, never defaulted open.
    """
    named = _normalize_provider(provider)
    if named == "KBS":
        try:
            return kbs.capability(name)
        except kbs.KBSCapabilityError as exc:
            raise RegistryError(f"unregistered_kbs_capability:{name}") from exc
    price_matrix = _vci_price_matrix()
    if name in price_matrix:
        return dict(price_matrix[name])
    try:
        return vci_volume.capability(name)
    except vci_volume.CapabilityError as exc:
        raise RegistryError(f"unregistered_vci_capability:{name}") from exc


def evaluate(provider: str, name: str, **kwargs: Any) -> dict[str, Any]:
    """Decide one capability for one provider, delegating to the owning matrix's own
    ``evaluate`` so its exact gating logic (labels, existing-gates, provider scope) applies.
    """
    named = _normalize_provider(provider)
    if named == "KBS":
        try:
            return kbs.evaluate(name, provider="KBS", **kwargs)
        except kbs.KBSCapabilityError as exc:
            raise RegistryError(f"kbs_evaluate_refused:{exc}") from exc
    price_matrix = _vci_price_matrix()
    if name in price_matrix:
        record = dict(price_matrix[name])
        existing_gates_passed = bool(kwargs.get("existing_gates_passed", False))
        label = kwargs.get("label")
        if record["availability"] == kbs.UNAVAILABLE_BY_CONTRACT:
            return {**record, "provider": "VCI", "available": False, "liquidity_actionable": False}
        if record["availability"] == kbs.AVAILABLE_WITH_REQUIRED_LABEL:
            if label in FORBIDDEN_RETURN_LABELS:
                raise RegistryError(f"forbidden_return_label:{label}")
            if label != record["required_label"]:
                return {
                    **record, "provider": "VCI", "available": False,
                    "reason": f"required_label_missing:{record['required_label']}",
                    "liquidity_actionable": False,
                }
        return {
            **record, "provider": "VCI", "available": existing_gates_passed,
            "blocked_by": None if existing_gates_passed else "existing_freshness_or_provenance_gate",
            "liquidity_actionable": False,
        }
    return vci_volume.evaluate(name, provider="VCI", **{k: v for k, v in kwargs.items() if k != "label"})


def assert_no_cross_provider_inheritance(provider_a: str, provider_b: str) -> None:
    """A verdict about one provider's price or volume series says nothing about another's.

    Delegates to each existing matrix's own ``provider_scope`` guard rather than
    re-deriving the check. For each of the two distinct providers named, and for each
    matrix that is not that provider's own, verifies the matrix does not claim its contract
    applies there -- which would mean a verdict had leaked across providers. Each matrix's
    own ``provider_scope`` is definitionally correct for its own provider, so this never
    raises on legitimate input; it exists to catch a regression, not to permit anything.
    """
    a, b = _normalize_provider(provider_a), _normalize_provider(provider_b)
    if a == b:
        return
    for foreign in (a, b):
        if foreign != "KBS" and kbs.provider_scope(foreign)["contract_applies"]:
            raise RegistryError(f"kbs_verdict_must_not_apply_to:{foreign}")
        if foreign != "VCI" and vci_volume.provider_scope(foreign)["contract_applies"]:
            raise RegistryError(f"vci_verdict_must_not_apply_to:{foreign}")


# ---------------------------------------------------------------------------------
# The capability ladder (brief: Level 0-5)
# ---------------------------------------------------------------------------------
#
# This is a readability layer, not a new gate. Every capability's actual availability was
# already decided by the matrix that owns it; the ladder only explains, for a report or a
# doc, how far a capability's *class* sits from a generic actionable market basis. A
# capability can be "at" a ladder level while still individually unavailable (e.g. every
# Level 4 liquidity capability in this repository today is unavailable_by_contract -- the
# level names what it would take, not that it has been granted).

LEVEL_GENERIC_UNKNOWN = 0
LEVEL_PROVIDER_DESCRIPTIVE = 1
LEVEL_PROVIDER_ADJUSTED_ANALYTICS = 2
LEVEL_QUALIFIED_VOLUME_DESCRIPTIVE = 3
LEVEL_MARKET_SCOPE_QUALIFIED_LIQUIDITY = 4
LEVEL_GENERIC_RAW_AUTHORITATIVE = 5

LADDER_LEVELS: Mapping[int, str] = {
    LEVEL_GENERIC_UNKNOWN: "generic_basis_unknown_no_market_derived_capability",
    LEVEL_PROVIDER_DESCRIPTIVE: "provider_scoped_descriptive_basis",
    LEVEL_PROVIDER_ADJUSTED_ANALYTICS: "provider_scoped_adjusted_price_analytics",
    LEVEL_QUALIFIED_VOLUME_DESCRIPTIVE: "qualified_volume_unit_descriptive_analytics",
    LEVEL_MARKET_SCOPE_QUALIFIED_LIQUIDITY: "market_scope_qualified_liquidity",
    LEVEL_GENERIC_RAW_AUTHORITATIVE: "generic_raw_as_traded_authoritative_market_basis",
}

_LIQUIDITY_CLASSES = frozenset(
    {kbs.CLASS_LIQUIDITY, kbs.CLASS_EXECUTION, vci_volume.CLASS_LIQUIDITY, vci_volume.CLASS_EXECUTION}
)
_HISTORICAL_TRUTH_CLASSES = frozenset({kbs.CLASS_HISTORICAL_TRUTH, VCI_CLASS_HISTORICAL_TRUTH})
_ADJUSTED_ANALYTICS_CLASSES = frozenset({kbs.CLASS_TECHNICAL, kbs.CLASS_CONDITIONAL})


def ladder_level(record: Mapping[str, Any]) -> int:
    """Which rung a capability record's *class* occupies on the brief's Level 0-5 ladder.

    Ties on capability name, not on current availability -- a liquidity capability is
    Level 4 whether or not it is presently open, because the level describes what the
    capability would need in order to be safe, not whether it has it.

    Class strings alone cannot separate "descriptive price" from "descriptive volume":
    ``kbs_capability_matrix.CLASS_DESCRIPTIVE`` and
    ``market_volume_capability_matrix.CLASS_DESCRIPTIVE`` are both the literal string
    ``"descriptive_provider_scoped"`` (KBS's one matrix covers both price and volume; VCI's
    volume matrix is volume-only). So volume is detected from the capability's *name*
    -- every volume capability in this repository, in both matrices, names itself with
    ``volume`` or ``trading_value`` -- not from its class.
    """
    klass = record.get("capability_class")
    name = str(record.get("capability", ""))
    if klass in _HISTORICAL_TRUTH_CLASSES:
        return LEVEL_GENERIC_RAW_AUTHORITATIVE
    if klass in _LIQUIDITY_CLASSES:
        return LEVEL_MARKET_SCOPE_QUALIFIED_LIQUIDITY
    if klass in _ADJUSTED_ANALYTICS_CLASSES:
        return LEVEL_PROVIDER_ADJUSTED_ANALYTICS
    is_volume_named = "volume" in name or "trading_value" in name
    if klass == vci_volume.CLASS_ANALYTICAL or is_volume_named:
        return LEVEL_QUALIFIED_VOLUME_DESCRIPTIVE
    if klass == kbs.CLASS_DESCRIPTIVE:  # identical string to VCI_CLASS_DESCRIPTIVE; covers both
        return LEVEL_PROVIDER_DESCRIPTIVE
    return LEVEL_GENERIC_UNKNOWN


# ---------------------------------------------------------------------------------
# Snapshot -- the whole registry, for the closeout artifact and for diffing
# ---------------------------------------------------------------------------------


def matrix_snapshot() -> dict[str, Any]:
    kbs_snap = kbs.matrix_snapshot()
    vci_volume_snap = vci_volume.matrix_snapshot()
    vci_price = _vci_price_matrix()
    capabilities: dict[str, dict[str, Any]] = {}
    for cap_name, record in kbs_snap["capabilities"].items():
        tagged = dict(record)
        tagged["provider"] = "KBS"
        tagged["ladder_level"] = ladder_level(record)
        tagged["ladder_level_name"] = LADDER_LEVELS[ladder_level(record)]
        capabilities[f"KBS:{cap_name}"] = tagged
    for cap_name, record in vci_volume_snap["capabilities"].items():
        tagged = dict(record)
        tagged["provider"] = "VCI"
        tagged["ladder_level"] = ladder_level(record)
        tagged["ladder_level_name"] = LADDER_LEVELS[ladder_level(record)]
        capabilities[f"VCI:{cap_name}"] = tagged
    for cap_name, record in vci_price.items():
        tagged = dict(record)
        tagged["provider"] = "VCI"
        tagged["ladder_level"] = ladder_level(record)
        tagged["ladder_level_name"] = LADDER_LEVELS[ladder_level(record)]
        capabilities[f"VCI:{cap_name}"] = tagged
    available = sorted(k for k, v in capabilities.items() if v["availability"] in kbs.OPEN_AVAILABILITIES)
    unavailable = sorted(k for k, v in capabilities.items() if v["availability"] == kbs.UNAVAILABLE_BY_CONTRACT)
    return {
        "schema_version": VERSION,
        "providers": list(PROVIDERS),
        "capabilities": dict(sorted(capabilities.items())),
        "available_count": len(available),
        "unavailable_count": len(unavailable),
        "available_capabilities": available,
        "unavailable_capabilities": unavailable,
        "universal_prohibited_capabilities": list(UNIVERSAL_PROHIBITED_CAPABILITIES),
        "ladder_levels": dict(LADDER_LEVELS),
        "kbs_source_snapshot_version": kbs_snap["schema_version"],
        "vci_volume_source_snapshot_version": vci_volume_snap["schema_version"],
        "vci_price_verdict": dict(_vci_price_verdict()),
        "liquidity_actionable": False,
        "is_actionable_effect": "none",
    }


def assert_registry_fail_closed() -> Mapping[str, Any]:
    """Refuse a registry snapshot that has opened something no underlying matrix opened."""
    kbs.assert_matrix_fail_closed()
    vci_volume.assert_matrix_fail_closed()
    snap = matrix_snapshot()
    for key, record in snap["capabilities"].items():
        if ladder_level(record) >= LEVEL_MARKET_SCOPE_QUALIFIED_LIQUIDITY and record["availability"] != kbs.UNAVAILABLE_BY_CONTRACT:
            raise RegistryError(f"level_4_or_5_capability_is_open:{key}")
    if snap["liquidity_actionable"]:
        raise RegistryError("registry_liquidity_actionable_must_stay_false")
    return snap


# ---------------------------------------------------------------------------------
# Stage D -- the generic-unlock gap table
# ---------------------------------------------------------------------------------
#
# Every row cites evidence already established elsewhere in this repository. Nothing here
# is a new finding; this is the "what's missing, named precisely" table the milestone asks
# for, built entirely from facts already on record in provider_price_basis_registry.py,
# vci_volume_composition.py, official_authority_candidates.py and docs/STATE.md.

GENERIC_UNLOCK_GAP_TABLE: tuple[dict[str, str], ...] = (
    {
        "capability": "raw_as_traded_price",
        "already_proven": (
            "VCI and KBS both carry an active, evidenced price-basis verdict "
            "(empirically_event_adjusted, empirically_deduced tier) -- not unknown. "
            "2026-08-09: every installed vnstock explorer (vci, kbs, msn, fmarket, misc) "
            "was checked directly for an adjust/raw parameter or vocabulary -- zero matches "
            "for 'adjust' anywhere in any quote/trading module; the only recognized "
            "adjustment_status value anywhere in this repository "
            "(semantic_evidence_bridge._SUPPORTED_ADJUSTMENT_STATUSES) is the legacy, "
            "already-superseded raw_as_quoted_no_adjustment_applied label."
        ),
        "missing_evidence": "OFFICIAL_DAILY_TICKER_SESSION_STATISTICS_ROUTE_NONCONFORMING_SUMMARY_ONLY",
        "required_authority": (
            "A daily official exchange raw-tick/settlement-price route, or a documented "
            "first-party provider adjustment methodology. The retained HOSE annual report "
            "has one HPG 2024-12-31 official closing-price observation, but it does not "
            "supply ticker/session history or an event-window route."
        ),
        "next_bounded_action": (
            "Pillar B: qualify one deterministic official HOSE daily ticker/session "
            "trading-statistics route whose retained bytes name the price and volume "
            "categories. The bounded official daily-summary route was retained and is "
            "nonconforming: it has no ticker closing-price field and only aggregate "
            "order-matching/put-through volume. The precise present blocker is "
            "OFFICIAL_DAILY_TICKER_SESSION_STATISTICS_ROUTE_NONCONFORMING_SUMMARY_ONLY."
        ),
    },
    {
        "capability": "generic_adjusted_price",
        "already_proven": (
            "Two independent provider-scoped adjusted series are qualified "
            "(kbs.empirically_event_adjusted, vci.empirically_event_adjusted), each from "
            "its own bounded lane."
        ),
        "missing_evidence": "GENERIC_PROVIDER_PROMOTION_NOT_AUTHORIZED",
        "required_authority": (
            "No rule in this repository promotes a provider-scoped verdict to a generic "
            "one, and none should without a documented methodology or an independent "
            "official ledger -- two undocumented sources agreeing is compatibility, not "
            "authority (evidence_qualification_tiers.may_claim_official_semantics)."
        ),
        "next_bounded_action": "Same as raw_as_traded_price: Pillar B B6.",
    },
    {
        "capability": "current_market_cap",
        "already_proven": (
            "EV balance-sheet components ready for 1,338 tickers (P1E); current effective "
            "shares qualified_official for exactly 1 of 1,683 tickers (HPG, B1.1)."
        ),
        "missing_evidence": "POINT_IN_TIME_SHARE_BASIS_INCOMPLETE + generic price basis (above)",
        "required_authority": (
            "Corporate-action ledger coverage per ticker (currently 250 rows across 5 of "
            "1,683 tickers, partial_unqualified_50_row_cap) plus a generic price basis."
        ),
        "next_bounded_action": (
            "Pillar B B2-B6 acquisition scale-out. Concrete next input: an official VSDC "
            "ex-date notice for SSI (already-retained ISS event has no ex-date; VCB was "
            "acquired 2026-08-08 the same way)."
        ),
    },
    {
        "capability": "historical_point_in_time_valuation",
        "already_proven": (
            "P2a's HPG/VNM FY2024 multiples were computed, then correctly reopened as "
            "BLOCKED (2026-08-04) once the cited close was shown off the HOSE tick lattice."
        ),
        "missing_evidence": "OFFICIAL_DAILY_PRICE_COVERAGE_AND_EVENT_LINEAGE_INCOMPLETE, at the specific cited date",
        "required_authority": "Same as raw_as_traded_price and generic_adjusted_price, applied point-in-time.",
        "next_bounded_action": "Same as raw_as_traded_price: Pillar B B6.",
    },
    {
        "capability": "average_daily_volume_and_tradability",
        "already_proven": (
            "Volume unit qualified as shares for both providers; VCI's provider-internal "
            "accumulator reconciles exactly; one opening-auction-labelled quantity "
            "demonstrated inside VCI's accumulator (demonstrated_for_observed_ato_field). "
            "2026-08-09, KBS only: three tickers (HPG/VNM/VCB), one session (2026-08-07), "
            "exact zero-residual reconciliation of the full intraday trade tape against the "
            "price board's volume_accumulated (the field already numerically identical to "
            "the already-qualified daily v) proves continuous-matching and auction-cleared "
            "trades are included, and separately-reported put_through_qty is excluded -- "
            "see kbs_trade_scope_qualification.py. VCI's own composition is unchanged."
        ),
        "missing_evidence": (
            "KBS: odd_lot_inclusion only (TRADE_TYPE_COVERAGE: PARTIAL). VCI: "
            "TRADE_TYPE_COVERAGE_UNQUALIFIED, unchanged, not re-probed this pass."
        ),
        "required_authority": (
            "For KBS's remaining gap: an odd-lot-distinguishing surface (none reachable in "
            "the installed free-tier library) or more independent sessions to strengthen "
            "the single-session finding. For VCI: a source that states what its volume "
            "figure counts at all -- all 96 examined VCI fields and every reachable KBS "
            "surface this repository can reach for free were exhausted for VCI specifically "
            "(see docs/DECISIONS.md 2026-08-04 'Ninety-six fields, and none of them says "
            "put-through')."
        ),
        "next_bounded_action": (
            "Not next: odd-lot and cross-session generalization are narrower, lower-value "
            "gaps than what already-qualified KBS composition unlocks (see "
            "ACTIONABLE_LIQUIDITY_UNLOCK). Obtain the HOSE trading-statistics locator "
            "(official_authority_candidates.HOSE_TRADING_STATISTICS) -- owner-supplied URL, "
            "not composed -- only if VCI's own composition specifically becomes the binding "
            "constraint later."
        ),
    },
    {
        "capability": "liquidity_adjusted_position_sizing",
        "already_proven": "Same volume-unit evidence as average_daily_volume_and_tradability.",
        "missing_evidence": (
            "Odd-lot inclusion (KBS) / full composition (VCI), plus a downstream "
            "authority-selection rule and holdings/cash/risk-budget contract this milestone "
            "does not build (see ACTIONABLE_LIQUIDITY_UNLOCK)."
        ),
        "required_authority": "Same as average_daily_volume_and_tradability.",
        "next_bounded_action": "Not next on its own; downstream of the ADV route above.",
    },
    {
        "capability": "production_execution_backtest",
        "already_proven": (
            "KBS shadow-backtest eligibility is defined (8 conditions in "
            "SHADOW_BACKTEST_CONDITIONS) but ELIGIBILITY_DEFINED_NOT_IMPLEMENTED; no "
            "provider's price or volume series authorizes execution semantics."
        ),
        "missing_evidence": "TRADE_TYPE_COVERAGE_UNQUALIFIED + point-in-time signal infrastructure absent",
        "required_authority": (
            "Trade-scope qualification (above) plus point-in-time signal storage and "
            "execution-lag/cost modelling (docs/risk_liquidity_backtesting_contract.md)."
        ),
        "next_bounded_action": "Not next; downstream of the ADV route and a separate signal-storage milestone.",
    },
)


def generic_unlock_gap_table() -> list[dict[str, str]]:
    return [dict(row) for row in GENERIC_UNLOCK_GAP_TABLE]


# ---------------------------------------------------------------------------------
# GENERIC_MARKET_BASIS_UNLOCK milestone (2026-08-09) -- price-branch findings
# ---------------------------------------------------------------------------------
#
# The price branch of that milestone inspected every installed vnstock provider explorer
# (vci, kbs, msn, fmarket, misc) and every approved official source's declared document
# types for a raw/as-traded price namespace or authority. It found none. These constants are
# the precise, code-level record of that negative result -- not a re-statement of the
# already-qualified adjusted verdicts above, which are unchanged.

EXPLICIT_RAW_ADJUSTED_NAMESPACE = "PILOT_PARTIAL"
RAW_AS_TRADED_PRICE_AUTHORITY = "PARTIAL"

#: Every installed vnstock explorer checked, and what was found. Not a claim about anything
#: unobserved -- see docs/DECISIONS.md 2026-08-09 for the exact commands run.
RAW_PRICE_NAMESPACE_INSPECTION: dict[str, Any] = {
    "installed_explorers_checked": ("vci", "kbs", "msn", "fmarket", "misc"),
    "adjust_vocabulary_matches": 0,
    "raw_vocabulary_matches_relevant_to_price": 0,
    "recognized_adjustment_status_values_repository_wide": (
        "raw_as_quoted_no_adjustment_applied",  # legacy, already-superseded label; see
        # provider_price_basis_registry.LEGACY_NO_LOCAL_ADJUSTMENT_LABEL
    ),
    "official_sources_checked": ("hose", "hnx", "vsdc", "issuer_ir"),
    "official_sources_with_price_bearing_document_types": (
        "hose:official_exchange_annual_trading_statistics",
        "hose:official_exchange_daily_trading_summary",
    ),
    "registered_future_candidates_with_a_locator": (),
    "conclusion": (
        "No installed provider adapter distinguishes raw from adjusted. A bounded official "
        "HOSE annual-statistics artifact supplies one explicitly dated closing-price "
        "observation. A retained two-session HOSE daily Trading Summary surface has date, "
        "aggregate market matched/put-through totals, and selective top-five ticker volumes, "
        "but no ticker closing-price/last-price field and no ticker-level trade-type totals. "
        "It is not a deterministic ticker/session statistics route. The annual artifact "
        "therefore remains a partial official raw namespace, not a generic price authority."
    ),
}

#: Bounded qualification result for HOSE's retained ``TỔNG HỢP THÔNG TIN GIAO DỊCH``
#: (Trading Summary) PDFs.  This is deliberately a terminal *schema* result, not a network
#: error: the source is first-party, stable and date-labelled, but cannot identify a ticker's
#: daily close.  The only prices called "Closing value" are index values.  HPG appears in the
#: top-volume tables for both sampled sessions; VNM's retained summary is still not a VNM
#: equity price observation (its VNM occurrence is a covered-warrant identifier).  Neither
#: sample contains ``Giá đóng cửa`` / Close for a named equity.  Aggregate matched and
#: put-through totals must not be projected onto any ticker.
OFFICIAL_DAILY_TICKER_SESSION_ROUTE_MILESTONE = "TERMINAL_BLOCKER"
OFFICIAL_DAILY_TICKER_SESSION_STATISTICS_ROUTE = "BLOCKED_NONCONFORMING_SUMMARY_ONLY"
OFFICIAL_DAILY_TICKER_SESSION_ROUTE_BLOCKER = (
    "OFFICIAL_DAILY_TICKER_SESSION_STATISTICS_ROUTE_NONCONFORMING_SUMMARY_ONLY"
)
OFFICIAL_DAILY_ROUTE_QUALIFICATION: dict[str, Any] = {
    "source_id": "HOSE",
    "authority": "Ho Chi Minh City Stock Exchange",
    "document_type": "official_exchange_daily_trading_summary",
    "route_state": OFFICIAL_DAILY_TICKER_SESSION_STATISTICS_ROUTE,
    "blocker": OFFICIAL_DAILY_TICKER_SESSION_ROUTE_BLOCKER,
    "stable_artifact_route": "retained_staticfile_pdf_by_published_session",
    "sampled_sessions": (
        {
            "trading_session_date": "2026-02-06",
            "document_id": "a01f738c42cf2c5c3881c282e93b9b8613973dc197cbebcee66c855d20e83d3f",
            "sha256": "b664b2eb670b82737fd3bce3116d598a0680ecf80561037e6576d3b0906b0b10",
        },
        {
            "trading_session_date": "2026-02-13",
            "document_id": "4b7a3a354d432cb2a679f1b04a6c6defbb3875238f8d679f94ad1a469f3d4875",
            "sha256": "ec3eb209d131e93f33fb0f202974dcaba6cd0dfd7952ddd2eee97a51fb395ddb",
        },
    ),
    "identity_fields": {
        "exchange": "HOSE publication heading",
        "session_date": "Ngày / Date",
        "ticker": "Top-five tables only; not a requested-ticker endpoint",
        "price": "absent for individual equities; 'Closing value' is an index field",
    },
    "volume_fields": {
        "market_total": ("Khớp lệnh / Order matching", "Thỏa thuận / Put-through", "Tổng / Total"),
        "ticker_total": "top-five volume only",
        "ticker_trade_type_breakdown": "absent",
    },
    "qualification_result": "reproducible_first_party_document_but_not_ticker_session_price_or_volume_schema",
    "daily_raw_price_observations_added": 0,
    "historical_or_event_window_route": "not_demonstrated",
    "hpg_2024_12_31_crosscheck": "existing_annual_report_only; no_daily_summary_close_field",
}

# The sole official raw observation retained by the bounded milestone.  It is deliberately
# a record, not a provider value, and it must be queried by both security and session.  The
# document says "Closing Price (31/12/2024) (VND Thousand)" for HPG and therefore identifies
# a published session-close observation and its scale.  It does not promise a continuously
# discoverable history or contain an event-window series, hence the PARTIAL authority verdict.
OFFICIAL_RAW_PRICE_OBSERVATIONS: tuple[dict[str, Any], ...] = (
    {
        "source_id": "HOSE",
        "authority": "Ho Chi Minh City Stock Exchange",
        "ticker": "HPG",
        "trading_session_date": "2024-12-31",
        "field": "Closing Price (31/12/2024) (VND Thousand)",
        "raw_value": 26.65,
        "price_unit": "VND_thousand_per_share",
        "value_vnd_per_share": 26650,
        "namespace": "official_raw_as_traded_pilot",
        "semantics": "officially_published_session_closing_price",
        "retrospective_rewrite_status": "not_observed_for_single_retained_session",
        "document_id": "42dbebe913beeebac997a7d1d3106bb2be1b0a27759c7ca872e65d683a206a17",
        "sha256": "0ae9f3095d3d021b063c3ffe27d698b58dae825c89e00e457ab92d83dbb03427",
        "source_location": "PDF printed pages 88-89 / PDF page 45",
        "retrieved_at": "2026-08-09T05:00:00Z",
        "evidence_path": (
            "operations-review/official-exchange-raw-price-volume-pilot-20260809/"
            "official_document_acquisition_manifest.json"
        ),
    },
)


def official_raw_price_observation(ticker: str, trading_session_date: str) -> dict[str, Any]:
    """Return the one exact-match official raw observation, or fail closed.

    This function intentionally has no nearest-date lookup and no adjusted-provider fallback.
    An official raw observation is useful only at the exact session it identifies.
    """
    matches = [dict(record) for record in OFFICIAL_RAW_PRICE_OBSERVATIONS
               if record["ticker"] == str(ticker).upper()
               and record["trading_session_date"] == str(trading_session_date)]
    if len(matches) != 1:
        raise RegistryError(
            f"official_raw_price_observation_unavailable:{str(ticker).upper()}:{trading_session_date}"
        )
    return matches[0]


def reconcile_raw_and_provider_adjusted(*, ticker: str, trading_session_date: str,
                                        provider_adjusted_value_vnd_per_share: float,
                                        provider: str) -> dict[str, Any]:
    """Preserve, rather than merge, a retained official raw and provider-adjusted value.

    A non-equal pair is expected evidence of distinct namespaces; equality would not make the
    namespaces interchangeable.  A non-VCI/KBS source and non-positive observations fail
    closed so callers cannot manufacture an apparent reconciliation.
    """
    raw = official_raw_price_observation(ticker, trading_session_date)
    named_provider = _normalize_provider(provider)
    adjusted = float(provider_adjusted_value_vnd_per_share)
    if adjusted <= 0:
        raise RegistryError("provider_adjusted_price_must_be_positive")
    return {
        "ticker": raw["ticker"],
        "trading_session_date": raw["trading_session_date"],
        "status": "partial_distinct_namespaces",
        "official_raw": raw,
        "provider_adjusted": {
            "provider": named_provider,
            "namespace": "provider_adjusted",
            "value_vnd_per_share": adjusted,
            "price_basis": price_registry.active_verdict(named_provider)["price_basis"],
        },
        "relationship": "values_must_not_be_merged_or_used_as_fallbacks",
        "ratio_provider_adjusted_to_official_raw": adjusted / raw["value_vnd_per_share"],
    }


# ---------------------------------------------------------------------------------
# Deterministic, capability-specific authority-selection rule
# ---------------------------------------------------------------------------------
#
# "If more than one qualified source/path exists, pick the strongest one, deterministically,
# per capability -- never merge or silently fall back." Four tiers, evaluated in order; the
# first tier with a real answer wins and the tier is always reported alongside the result.

AUTHORITY_TIER_OFFICIAL_RAW = 1
AUTHORITY_TIER_PROVIDER_RAW = 2
AUTHORITY_TIER_PROVIDER_ADJUSTED_DESCRIPTIVE = 3
AUTHORITY_TIER_BLOCKED = 4

AUTHORITY_TIER_NAMES: Mapping[int, str] = {
    AUTHORITY_TIER_OFFICIAL_RAW: "official_raw_as_traded_source",
    AUTHORITY_TIER_PROVIDER_RAW: "qualified_provider_raw_namespace",
    AUTHORITY_TIER_PROVIDER_ADJUSTED_DESCRIPTIVE: "qualified_provider_adjusted_namespace_descriptive_only",
    AUTHORITY_TIER_BLOCKED: "blocked",
}

#: Capabilities for which Tier 3 (provider-adjusted, descriptive-only) is ever an admissible
#: answer. Anything not listed here has no Tier 3 route and falls straight to Tier 4 --
#: valuation, sizing, ranking and execution are never descriptive-only capabilities.
_TIER_3_ELIGIBLE_CAPABILITY_KINDS = frozenset(
    {
        "descriptive_price", "descriptive_volume", "technical_indicator",
        "provider_series_return", "volume_composition_disclosure",
    }
)


def select_price_authority(capability_kind: str, *, provider: str | None = None,
                           ticker: str | None = None,
                           trading_session_date: str | None = None) -> dict[str, Any]:
    """The one place this repository decides which namespace answers a price/volume
    capability. Deterministic and capability-specific: the same ``capability_kind`` always
    resolves to the same tier given the same evidence state, and a capability ineligible for
    Tier 3 (valuation, sizing, ranking, execution) can never land there no matter which
    provider is asked.

    Never merges: when Tier 3 applies, the result names exactly one provider (the one
    passed in, defaulting to none selected) rather than picking "whichever is available".
    """
    # Tier 1: a narrowly-scoped official raw observation is available only by exact identity.
    # It cannot satisfy a generic capability, and it never permits adjusted fallback.
    if capability_kind in {"raw_eod_observation", "point_in_time_price"}:
        if ticker is None or trading_session_date is None:
            return {
                "capability_kind": capability_kind,
                "tier": AUTHORITY_TIER_BLOCKED,
                "tier_name": AUTHORITY_TIER_NAMES[AUTHORITY_TIER_BLOCKED],
                "provider": None,
                "reason": "official_raw_price_requires_exact_ticker_and_trading_session_date",
            }
        try:
            raw = official_raw_price_observation(ticker, trading_session_date)
        except RegistryError:
            return {
                "capability_kind": capability_kind,
                "tier": AUTHORITY_TIER_BLOCKED,
                "tier_name": AUTHORITY_TIER_NAMES[AUTHORITY_TIER_BLOCKED],
                "provider": None,
                "reason": "official_raw_price_observation_not_retained_for_exact_identity",
            }
        return {
            "capability_kind": capability_kind,
            "tier": AUTHORITY_TIER_OFFICIAL_RAW,
            "tier_name": AUTHORITY_TIER_NAMES[AUTHORITY_TIER_OFFICIAL_RAW],
            "provider": None,
            "source_id": raw["source_id"],
            "namespace": raw["namespace"],
            "observation": raw,
            "descriptive_only": False,
            "reason": "exact_retained_official_raw_observation",
        }
    # Tier 2: neither provider has ever been qualified as raw -- both are
    # raw_as_traded_eligible == False in provider_price_basis_registry.py.
    if capability_kind not in _TIER_3_ELIGIBLE_CAPABILITY_KINDS:
        return {
            "capability_kind": capability_kind,
            "tier": AUTHORITY_TIER_BLOCKED,
            "tier_name": AUTHORITY_TIER_NAMES[AUTHORITY_TIER_BLOCKED],
            "provider": None,
            "reason": "capability_kind_has_no_tier_3_route_and_no_tier_1_or_2_source_exists",
        }
    if provider is None:
        return {
            "capability_kind": capability_kind,
            "tier": AUTHORITY_TIER_BLOCKED,
            "tier_name": AUTHORITY_TIER_NAMES[AUTHORITY_TIER_BLOCKED],
            "provider": None,
            "reason": "no_provider_named_and_no_implicit_best_available_provider_selection_exists",
        }
    named = _normalize_provider(provider)
    return {
        "capability_kind": capability_kind,
        "tier": AUTHORITY_TIER_PROVIDER_ADJUSTED_DESCRIPTIVE,
        "tier_name": AUTHORITY_TIER_NAMES[AUTHORITY_TIER_PROVIDER_ADJUSTED_DESCRIPTIVE],
        "provider": named,
        "reason": "only_admissible_route_today_is_the_named_providers_own_qualified_adjusted_series",
        "namespace": "provider_scoped",
        "descriptive_only": True,
    }


def assert_no_fallback_merging(results: Sequence[Mapping[str, Any]]) -> None:
    """Refuse a caller that collapsed more than one provider's answer for the same
    capability into one value -- the one shape this rule exists to prevent."""
    by_capability: dict[str, set[str]] = {}
    for result in results:
        providers = by_capability.setdefault(str(result.get("capability_kind")), set())
        if result.get("provider"):
            providers.add(str(result["provider"]))
    for capability_kind, providers in by_capability.items():
        if len(providers) > 1:
            raise RegistryError(
                f"fallback_merging_forbidden:{capability_kind}:{sorted(providers)}"
            )
