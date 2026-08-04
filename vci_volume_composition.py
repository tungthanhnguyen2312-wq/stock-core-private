"""Terminal qualification of VCI volume *market composition*.

Composition asks which trades the exchange counted into a volume figure: continuous
matching, put-through/negotiated, the opening and closing auctions, odd lots. It is a
different question from every dimension already settled for VCI, and none of those answers
it:

* that daily ``v`` equals the intraday accumulator says the provider is self-consistent;
* that the unit is shares says how much, not what kind;
* that the tape reconciles to the share says the arithmetic closes.

All three would hold identically whether the underlying figure were matched-only or
matched-plus-put-through, because every one of them is computed from the same counter. So
this module refuses to derive composition from any of them, and upgrades a dimension only
on an explicit first-party definition or a demonstrated relationship between separately
defined provider fields.

It also carries the terminal state. When no such surface exists, the contract closes as
permanently unresolved *under the currently observable VCI contract* -- not as a claim that
VCI can never publish a definition.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

VERSION = "1.0.0"
PROVIDER = "VCI"

COMPOSITION_DIMENSIONS = (
    "matched_trade_inclusion",
    "negotiated_inclusion",
    "auction_inclusion",
    "odd_lot_inclusion",
)

#: The two auction legs are tracked separately. The opening auction can be demonstrated
#: from a morning snapshot; the closing auction cannot, and rolling them together would
#: let one leg's evidence speak for the other.
AUCTION_SUBDIMENSIONS = ("opening_auction_inclusion", "closing_auction_inclusion")

#: The canonical active market-scope vocabulary. ``partially_observed_but_not_qualified``
#: replaced ``partially_qualified`` on 2026-08-04: the old word was accurate about one
#: dimension and dangerously readable as "qualified enough to size against", which is the
#: one reading the evidence does not support. Nothing about the evidence changed.
MARKET_SCOPE_PARTIAL = "partially_observed_but_not_qualified"
MARKET_SCOPE_UNRESOLVED = "permanently_unresolved"
MARKET_SCOPE_STATES = frozenset({"unknown", MARKET_SCOPE_PARTIAL, MARKET_SCOPE_UNRESOLVED})

#: Recognised only when reading a frozen evidence artifact written before the rename.
#: :func:`assert_canonical_vocabulary` refuses it, so it can never re-enter an active
#: contract. The artifacts themselves are not rewritten.
SUPERSEDED_MARKET_SCOPE_STATES = frozenset({"partially_qualified"})

#: A dimension verdict, as written into the contract.
#:
#: ``unknown``                                 -- nobody has looked, or looking was
#:                                                inconclusive; reopenable by observation.
#: ``unavailable_from_observed_vci_surfaces``  -- every observable VCI surface was examined
#:                                                and none carries the dimension. Terminal
#:                                                for VCI; reopenable only by a new source.
#: ``demonstrated_for_observed_ato_field``     -- the single narrow opening-auction result.
#:                                                Deliberately not spelled ``qualified``:
#:                                                what was demonstrated is that one
#:                                                observed ATO-labelled quantity sits inside
#:                                                the provider accumulator, not that the
#:                                                auction composition of the volume field is
#:                                                known.
DIMENSION_UNKNOWN = "unknown"
DIMENSION_UNAVAILABLE = "unavailable_from_observed_vci_surfaces"
DIMENSION_ATO_DEMONSTRATED = "demonstrated_for_observed_ato_field"
DIMENSION_VERDICTS = frozenset(
    {DIMENSION_UNKNOWN, DIMENSION_UNAVAILABLE, DIMENSION_ATO_DEMONSTRATED}
)

#: The auction roll-up. One leg demonstrated and the other unobserved is *partial
#: observation*, never qualification -- ``qualified`` is not a reachable value.
AUCTION_ROLLUP_PARTIAL = "partially_observed"

#: Settled in commit 9887c1c: the intraday cursor has one-second resolution and the server
#: caps a page at 100 rows, so a second holding >= 100 trades cannot be enumerated. That is
#: structural. No further pagination is authorized, and no test or caller may re-enable it.
FURTHER_PAGINATION_AUTHORIZED = False

#: An endpoint is requested only from :data:`CANDIDATE_SURFACES`, each of which carries a
#: provenance record naming where it was observed. Nothing is composed from a host plus a
#: guessed path.
FURTHER_SPECULATIVE_ENDPOINT_PROBE_AUTHORIZED = False


class CompositionError(ValueError):
    """Fail-closed rejection in the composition contract."""


# ---------------------------------------------------------------------------------
# Part A -- candidate surface inventory
# ---------------------------------------------------------------------------------

#: Every VCI surface reachable from evidence in this environment. ``observed_in`` is the
#: provenance a live probe is gated on; a surface without one cannot be requested.
CANDIDATE_SURFACES: tuple[dict[str, Any], ...] = (
    {
        "surface_id": "vci_daily_gap_chart",
        "endpoint": "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart",
        "method": "POST",
        "observed_in": "vnstock 4.0.4 explorer/vci/quote.py; exercised by vn_stock_pipeline.py",
        "authentication": "none observed; no cookie or token sent",
        "level": "ticker",
        "period": "completed daily bars plus the in-progress session",
        "composition_fields": [],
        "fields": ["t", "o", "h", "l", "c", "v", "accumulatedVolume", "accumulatedValue", "minBatchTruncTime"],
        "rejection_reason": (
            "v and accumulatedVolume are undifferentiated totals. No field names or "
            "separates any trade method."
        ),
    },
    {
        "surface_id": "vci_intraday_ledata",
        "endpoint": "https://trading.vietcap.com.vn/api/market-watch/LEData/getAll",
        "method": "POST",
        "observed_in": "vnstock 4.0.4 explorer/vci/quote.py; paginated in commit 9887c1c",
        "authentication": "none observed",
        "level": "ticker",
        "period": "current session tape only",
        "composition_fields": [],
        "fields": ["id", "symbol", "truncTime", "matchType", "matchVol", "matchPrice",
                    "accumulatedVolume", "accumulatedValue", "type"],
        "rejection_reason": (
            "matchType is b/s -- the aggressor side, not the trade method. `type` is "
            "undocumented. Nothing separates put-through, auction or odd-lot trades, and "
            "the accumulator is a single undifferentiated running total."
        ),
    },
    {
        "surface_id": "vci_price_board",
        "endpoint": "https://trading.vietcap.com.vn/api/price/symbols/getList",
        "method": "POST",
        "observed_in": (
            "vnstock 4.0.4 explorer/vci/trading.py Trading.price_board; already exercised in "
            "production by meta_sync.py:156 and blacklist_sync.py:75"
        ),
        "authentication": "none observed",
        "level": "ticker (bulk list)",
        "period": "live snapshot of the current session",
        "composition_fields": ["__probe_required__"],
        "fields": ["listingInfo", "bidAsk", "matchPrice"],
        "rejection_reason": None,
    },
)

#: Surfaces named in the provider's own constants but which answer a different question.
#: Listed so the inventory is complete and so nobody re-derives them as candidates.
OUT_OF_SCOPE_SURFACES: tuple[dict[str, str], ...] = (
    {"endpoint": "https://iq.vietcap.com.vn/api/iq-insight-service/v1/events", "reason": "corporate events, not volume"},
    {"endpoint": "https://iq.vietcap.com.vn/api/iq-insight-service/v1/market-indices", "reason": "index levels, not per-trade-method volume"},
    {"endpoint": "https://iq.vietcap.com.vn/api/iq-insight-service/v1/company", "reason": "company profile, not volume"},
    {"endpoint": "https://trading.vietcap.com.vn/data-mt/graphql", "reason": "financial statements and listings, not volume composition"},
)


def surface(surface_id: str) -> dict[str, Any]:
    for record in CANDIDATE_SURFACES:
        if record["surface_id"] == surface_id:
            return dict(record)
    raise CompositionError(f"surface_not_in_inventory:{surface_id}")


def assert_probe_permitted(endpoint: str) -> dict[str, Any]:
    """A live probe requires an inventory entry with observed-endpoint provenance.

    This is what stops a plausible URL from being requested. An endpoint absent from the
    inventory has no provenance by construction, so it cannot be reached from here.
    """
    for record in CANDIDATE_SURFACES:
        if record["endpoint"] == endpoint:
            if not str(record.get("observed_in", "")).strip():
                raise CompositionError(f"endpoint_without_observed_provenance:{endpoint}")
            return dict(record)
    raise CompositionError(f"speculative_endpoint_refused:{endpoint}")


# ---------------------------------------------------------------------------------
# Part B -- what counts as a semantic
# ---------------------------------------------------------------------------------

SEMANTIC_STATUS = frozenset(
    {"qualified", "exchange_standard_term", "name_only_not_qualified", "unknown"}
)

#: Labels whose referent is fixed by exchange regulation rather than by the provider.
#: ATO and ATC are HOSE session codes, not VCI coinages, so a field carrying one is not in
#: the same position as an undocumented provider invention. This is a deliberately short
#: list and it is not a licence to read meaning into any suggestive name -- a term earns a
#: place here only if an outside authority defines it and the provider uses it as such.
EXCHANGE_STANDARD_TERMS = frozenset({"ATO", "ATC"})


def classify_field_semantics(
    *,
    field_name: str,
    first_party_definition: str | None,
    definition_kind: str | None = None,
) -> dict[str, Any]:
    """Decide whether a field's meaning is established or merely suggested by its name.

    ``definition_kind`` must be ``explicit`` for a qualification. A contextual or inferred
    reading -- a label sitting near a number, a column heading, a plausible expansion of an
    abbreviation -- is recorded and does not qualify. A field called ``totalVolume`` with no
    definition is exactly as unqualified as one called ``x``.
    """
    if first_party_definition and definition_kind == "explicit":
        return {
            "field": field_name,
            "status": "qualified",
            "definition": first_party_definition,
            "definition_kind": "explicit",
        }
    matched_term = next((t for t in EXCHANGE_STANDARD_TERMS if t in field_name), None)
    if matched_term:
        return {
            "field": field_name,
            "status": "exchange_standard_term",
            "definition": None,
            "definition_kind": "exchange_regulated_session_code",
            "term": matched_term,
            "note": (
                f"{matched_term} is defined by HOSE, not by VCI. That fixes the referent "
                "without the provider defining anything, so it may support a "
                "reconciliation-based qualification but never a qualification on its own."
            ),
        }
    if first_party_definition:
        return {
            "field": field_name,
            "status": "name_only_not_qualified",
            "definition": first_party_definition,
            "definition_kind": definition_kind or "contextual",
            "note": "A contextual or inferred reading is not a first-party definition.",
        }
    return {
        "field": field_name,
        "status": "name_only_not_qualified" if field_name else "unknown",
        "definition": None,
        "definition_kind": None,
        "note": "No first-party definition retained; the name alone establishes nothing.",
    }


def qualify_dimension(
    *,
    dimension: str,
    explicit_definition: Mapping[str, Any] | None = None,
    demonstrated_relationship: Mapping[str, Any] | None = None,
) -> str:
    """Upgrade a composition dimension, or leave it unknown.

    The only two admissible routes are an explicit first-party definition, or separate
    provider fields whose relationship is demonstrated by a bounded reconciliation *and*
    whose labels each carry unambiguous first-party meaning. A reconciliation between
    fields nobody has defined demonstrates arithmetic, not composition.
    """
    if dimension not in COMPOSITION_DIMENSIONS + AUCTION_SUBDIMENSIONS:
        raise CompositionError(f"unknown_composition_dimension:{dimension}")
    if explicit_definition and explicit_definition.get("definition_kind") == "explicit":
        return "qualified"
    if demonstrated_relationship:
        components = demonstrated_relationship.get("component_fields") or []
        if not components:
            raise CompositionError("demonstrated_relationship_requires_component_fields")
        if demonstrated_relationship.get("reconciles") is not True:
            return "unknown"
        statuses = {component.get("status") for component in components}
        if statuses <= {"qualified"}:
            return "qualified"
        # An exchange-regulated label may carry a reconciliation, but only when the
        # referent is pinned by a second, independent field as well. Otherwise an exact
        # match is just arithmetic agreeing with a suggestive name.
        if statuses <= {"qualified", "exchange_standard_term"} and demonstrated_relationship.get(
            "referent_pinned_by_independent_field"
        ):
            return "qualified"
    return "unknown"


# ---------------------------------------------------------------------------------
# Terminal contract
# ---------------------------------------------------------------------------------


def composition_contract(
    *,
    provider_internal_volume_reconciled: bool,
    dimension_verdicts: Mapping[str, str],
    unit: str,
    corporate_action_adjustment: str,
    surfaces_examined: Sequence[Mapping[str, Any]],
    exhausted_dimensions: Mapping[str, str] | None = None,
    resolution: str | None = None,
) -> dict[str, Any]:
    """Assemble the terminal volume contract -- State A or State B.

    ``liquidity_actionable`` is a constant here, not a computed value. There is no
    combination of inputs that turns it on, because sizing against a volume figure requires
    knowing what that figure counts, and market scope is the dimension that says so.

    Callers pass the *route* outcome from :func:`qualify_dimension` -- ``qualified`` or
    ``unknown`` -- or the terminal ``unavailable_from_observed_vci_surfaces``. A successful
    route on the opening-auction leg is narrowed on write to
    ``demonstrated_for_observed_ato_field``: the contract records what was demonstrated
    about one observed field, and there is no spelling of it that reads as a qualified
    volume composition.
    """
    accepted_inputs = {"qualified", DIMENSION_UNKNOWN, DIMENSION_UNAVAILABLE}
    for dimension, verdict in dimension_verdicts.items():
        if dimension not in COMPOSITION_DIMENSIONS + AUCTION_SUBDIMENSIONS:
            raise CompositionError(f"unknown_composition_dimension:{dimension}")
        if verdict not in accepted_inputs:
            raise CompositionError(f"dimension_verdict_invalid:{dimension}={verdict}")
    if dimension_verdicts.get("closing_auction_inclusion") == "qualified":
        # The opening leg was earned from a morning snapshot; the closing leg has no
        # comparable evidence and no route defined here. Refusing it outright keeps the
        # ATO narrowing from being copied onto ATC by a caller in a hurry.
        raise CompositionError("closing_auction_inclusion_has_no_qualification_route")

    # auction_inclusion is a roll-up over its legs and is never asserted directly.
    if "auction_inclusion" in dimension_verdicts:
        raise CompositionError("auction_inclusion_is_derived_from_its_legs_not_asserted")
    legs = {d: dimension_verdicts.get(d, DIMENSION_UNKNOWN) for d in AUCTION_SUBDIMENSIONS}
    demonstrated_legs = sorted(leg for leg, v in legs.items() if v == "qualified")

    contract: dict[str, Any] = {
        "schema_version": VERSION,
        "provider": PROVIDER,
        "provider_internal_volume_reconciled": bool(provider_internal_volume_reconciled),
        "volume_field_identity": "qualified",
        "volume_unit": unit,
        "volume_corporate_action_adjustment": corporate_action_adjustment,
        "liquidity_actionable": False,
        "surfaces_examined": [dict(s) for s in surfaces_examined],
        "further_vci_pagination_authorized": FURTHER_PAGINATION_AUTHORIZED,
        "further_speculative_endpoint_probe_authorized": FURTHER_SPECULATIVE_ENDPOINT_PROBE_AUTHORIZED,
        # The canonical spelling of the same fact. Both keys are emitted because the first
        # is this repository's existing vocabulary and the second is the contract name; they
        # are asserted equal rather than allowed to drift.
        "further_vci_endpoint_probe_authorized": FURTHER_SPECULATIVE_ENDPOINT_PROBE_AUTHORIZED,
    }
    for dimension in COMPOSITION_DIMENSIONS:
        if dimension == "auction_inclusion":
            continue
        contract[dimension] = dimension_verdicts.get(dimension, DIMENSION_UNKNOWN)
    for leg, verdict in legs.items():
        contract[leg] = (
            DIMENSION_ATO_DEMONSTRATED if verdict == "qualified" else verdict
        )

    if demonstrated_legs:
        # A roll-up that does not say which leg it covers is an overclaim waiting to be
        # quoted, so the scope travels with it -- and the roll-up itself never reads
        # "qualified", only "partially observed".
        contract["auction_inclusion"] = AUCTION_ROLLUP_PARTIAL
        contract["general_auction_composition"] = AUCTION_ROLLUP_PARTIAL
        contract["auction_inclusion_scope"] = list(demonstrated_legs)
        contract["auction_inclusion_unresolved_legs"] = sorted(
            leg for leg, verdict in legs.items() if verdict != "qualified"
        )
        # The demonstrated result, stated at the width it was actually demonstrated at.
        contract["opening_auction_labeled_quantity"] = "observed"
        contract["opening_auction_referent"] = "qualified_by_exchange_standard_term"
        contract["opening_auction_included_in_provider_accumulated_volume"] = "demonstrated"
    else:
        contract["auction_inclusion"] = DIMENSION_UNKNOWN
        contract["general_auction_composition"] = DIMENSION_UNKNOWN

    # A dimension can be unknown because nobody looked, or unknown because every observable
    # surface was examined and none carries it. Recording which keeps the second kind from
    # being reopened as though it were the first.
    contract["unresolved_dimension_resolution"] = dict(exhausted_dimensions or {})

    if demonstrated_legs:
        contract["market_scope"] = MARKET_SCOPE_PARTIAL
        contract["overall_market_scope"] = MARKET_SCOPE_PARTIAL
        contract["state"] = "A_composition_partially_observed_not_qualified"
        contract["demonstrated_dimensions"] = list(demonstrated_legs)
        contract["market_composition_resolution"] = (
            resolution or DIMENSION_UNAVAILABLE
        )
    else:
        contract["market_scope"] = MARKET_SCOPE_UNRESOLVED
        contract["overall_market_scope"] = MARKET_SCOPE_UNRESOLVED
        contract["state"] = "B_composition_permanently_unresolved_through_vci"
        contract["market_composition_resolution"] = (
            resolution or DIMENSION_UNAVAILABLE
        )
        contract["permanence_scope"] = (
            "Under the currently observable VCI contract. Not a claim that VCI can never "
            "publish a field definition; a first-party definition would reopen this."
        )
    return contract


#: The evidence artifact this contract was assembled from, and the fact that it is not
#: rewritten. The artifact at ``63ecc48`` uses the superseded ``partially_qualified``
#: spelling; it stays exactly as written, because an evidence record that gets edited when
#: the vocabulary changes is not an evidence record.
SUPERSEDED_ARTIFACT = {
    "path": "operations-review/vci-volume-composition-20260804/composition_summary.json",
    "key": "volume_contract",
    "commit": "63ecc48",
    "vocabulary": "partially_qualified",
    "superseded_by": "market_scope=partially_observed_but_not_qualified",
    "evidence_changed": False,
    "note": (
        "Terminology only. Every dimension verdict, the ATO reconciliation and the surface "
        "inventory are unchanged; what changed is that three dimensions previously recorded "
        "as `unknown` with a sidecar resolution are now written as "
        "`unavailable_from_observed_vci_surfaces` at the top level, and the one demonstrated "
        "leg is no longer spelled `qualified`."
    ),
}


def active_contract() -> dict[str, Any]:
    """The canonical, active VCI volume contract. One definition, assembled once.

    Consumers that need the verdict read this rather than re-deriving it from an evidence
    file, so there is no second place for the vocabulary to drift to.
    """
    contract = composition_contract(
        provider_internal_volume_reconciled=True,
        dimension_verdicts={
            "matched_trade_inclusion": DIMENSION_UNAVAILABLE,
            "negotiated_inclusion": DIMENSION_UNAVAILABLE,
            "odd_lot_inclusion": DIMENSION_UNAVAILABLE,
            "opening_auction_inclusion": "qualified",
            "closing_auction_inclusion": DIMENSION_UNKNOWN,
        },
        unit="shares",
        corporate_action_adjustment=DIMENSION_UNKNOWN,
        surfaces_examined=CANDIDATE_SURFACES,
        exhausted_dimensions={
            "matched_trade_inclusion": DIMENSION_UNAVAILABLE,
            "negotiated_inclusion": DIMENSION_UNAVAILABLE,
            "odd_lot_inclusion": DIMENSION_UNAVAILABLE,
            "closing_auction_inclusion": "not_observable_from_the_retained_morning_snapshot",
        },
    )
    contract["supersedes"] = dict(SUPERSEDED_ARTIFACT)
    return assert_canonical_vocabulary(contract)  # type: ignore[return-value]


LIQUIDITY_CAPABILITIES = (
    "days_to_liquidate",
    "market_impact",
    "position_sizing",
    "liquidity_based_position_sizing",
    "portfolio_sizing",
    "backtesting",
)


def liquidity_eligibility(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Nothing in this contract can open a liquidity capability."""
    return {
        "market_scope": contract.get("market_scope"),
        "unavailable": list(LIQUIDITY_CAPABILITIES),
        "available": [],
        "liquidity_actionable": False,
        "reason": (
            "Sizing against a volume figure requires knowing which trades it counts. "
            "Provider-internal reconciliation does not establish that."
        ),
    }


def assert_fail_closed(contract: Mapping[str, Any]) -> Mapping[str, Any]:
    """Refuse a contract that has leaked an unearned upgrade.

    Accepts both the canonical vocabulary and the superseded ``partially_qualified``
    spelling, so that a frozen evidence artifact written before the 2026-08-04 rename can
    still be checked for safety without being rewritten. Use
    :func:`assert_canonical_vocabulary` for anything that is *active*.
    """
    if contract.get("liquidity_actionable"):
        raise CompositionError("liquidity_actionable_must_stay_false")
    scope = contract.get("market_scope")
    if scope not in MARKET_SCOPE_STATES | SUPERSEDED_MARKET_SCOPE_STATES:
        raise CompositionError(f"market_scope_state_invalid:{scope}")
    partial_evidence = contract.get("demonstrated_dimensions") or contract.get("qualified_dimensions")
    if scope in {MARKET_SCOPE_PARTIAL} | SUPERSEDED_MARKET_SCOPE_STATES and not partial_evidence:
        raise CompositionError("partial_market_scope_without_a_demonstrated_dimension")
    if contract.get("auction_inclusion") in {"qualified", AUCTION_ROLLUP_PARTIAL} and not contract.get(
        "auction_inclusion_scope"
    ):
        raise CompositionError("auction_roll_up_must_name_its_legs")
    if contract.get("further_vci_pagination_authorized"):
        raise CompositionError("further_pagination_is_not_authorized")
    if contract.get("further_speculative_endpoint_probe_authorized"):
        raise CompositionError("speculative_endpoint_probing_is_not_authorized")
    if contract.get("further_vci_endpoint_probe_authorized"):
        raise CompositionError("further_vci_endpoint_probing_is_not_authorized")
    if contract.get("provider") != PROVIDER:
        raise CompositionError("contract_provider_must_be_vci")
    return contract


#: Words that must not appear as an active verdict, and what to say instead. Each was a
#: real spelling in this repository; each reads, to a consumer skimming for a green light,
#: as more than the evidence supports.
BANNED_ACTIVE_VERDICTS: dict[str, str] = {
    "partially_qualified": MARKET_SCOPE_PARTIAL,
    "qualified": "a dimension-specific demonstrated verdict",
}


def assert_canonical_vocabulary(contract: Mapping[str, Any]) -> Mapping[str, Any]:
    """The strict check for an *active* contract: fail-closed **and** canonically worded.

    Separate from :func:`assert_fail_closed` because the two answer different questions.
    A frozen artifact can be safe and still use a word this milestone retired; an active
    contract may not.
    """
    assert_fail_closed(contract)
    scope = contract.get("market_scope")
    if scope in SUPERSEDED_MARKET_SCOPE_STATES:
        raise CompositionError(
            f"superseded_market_scope_vocabulary:{scope}->{BANNED_ACTIVE_VERDICTS[str(scope)]}"
        )
    if contract.get("overall_market_scope") != scope:
        raise CompositionError("overall_market_scope_must_agree_with_market_scope")
    for dimension in COMPOSITION_DIMENSIONS + AUCTION_SUBDIMENSIONS:
        verdict = contract.get(dimension)
        if dimension == "auction_inclusion":
            if verdict not in {DIMENSION_UNKNOWN, AUCTION_ROLLUP_PARTIAL}:
                raise CompositionError(f"auction_roll_up_verdict_invalid:{verdict}")
            continue
        if verdict not in DIMENSION_VERDICTS:
            raise CompositionError(f"non_canonical_dimension_verdict:{dimension}={verdict}")
    if contract.get("general_auction_composition") != contract.get("auction_inclusion"):
        raise CompositionError("general_auction_composition_must_agree_with_the_roll_up")
    if contract.get("opening_auction_inclusion") == DIMENSION_ATO_DEMONSTRATED:
        narrow = {
            "opening_auction_labeled_quantity": "observed",
            "opening_auction_referent": "qualified_by_exchange_standard_term",
            "opening_auction_included_in_provider_accumulated_volume": "demonstrated",
        }
        for key, expected in narrow.items():
            if contract.get(key) != expected:
                raise CompositionError(f"narrow_ato_result_not_stated:{key}")
        if contract.get("closing_auction_inclusion") == DIMENSION_ATO_DEMONSTRATED:
            raise CompositionError("opening_leg_evidence_cannot_cover_the_closing_leg")
    if contract.get("further_vci_endpoint_probe_authorized") is not contract.get(
        "further_speculative_endpoint_probe_authorized"
    ):
        raise CompositionError("probe_authorization_keys_disagree")
    return contract


def assert_no_provider_inheritance(contract: Mapping[str, Any], *, other_provider: str) -> None:
    """A VCI composition verdict says nothing about anyone else's volume field."""
    if str(other_provider).strip().upper() == PROVIDER:
        return
    raise CompositionError(
        f"vci_composition_verdict_does_not_transfer:{str(other_provider).strip().upper()}"
    )


def price_adjustment_does_not_imply_volume_adjustment(
    *, price_basis: str, retained_volume_evidence_determines_adjustment: bool
) -> str:
    """Keep the volume adjustment dimension independent of the price one.

    VCI's prices are demonstrably back-adjusted. Volume is a count of shares that changed
    hands, and a distribution does not retroactively change that count -- but neither does
    the price finding establish anything either way, so the answer comes only from retained
    volume evidence.
    """
    del price_basis  # deliberately unused: it is not an input to this question
    return "qualified" if retained_volume_evidence_determines_adjustment else "unknown"
