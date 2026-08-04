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

MARKET_SCOPE_STATES = frozenset({"unknown", "partially_qualified", "permanently_unresolved"})

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
    """
    for dimension, verdict in dimension_verdicts.items():
        if dimension not in COMPOSITION_DIMENSIONS + AUCTION_SUBDIMENSIONS:
            raise CompositionError(f"unknown_composition_dimension:{dimension}")
        if verdict not in {"qualified", "unknown"}:
            raise CompositionError(f"dimension_verdict_invalid:{dimension}={verdict}")

    # auction_inclusion is a roll-up over its legs and is never asserted directly.
    if "auction_inclusion" in dimension_verdicts:
        raise CompositionError("auction_inclusion_is_derived_from_its_legs_not_asserted")
    legs = {d: dimension_verdicts.get(d, "unknown") for d in AUCTION_SUBDIMENSIONS}
    dimension_verdicts = dict(dimension_verdicts)
    dimension_verdicts["auction_inclusion"] = (
        "qualified" if any(v == "qualified" for v in legs.values()) else "unknown"
    )
    qualified = [d for d, v in dimension_verdicts.items() if v == "qualified"]
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
    }
    for dimension in COMPOSITION_DIMENSIONS + AUCTION_SUBDIMENSIONS:
        contract[dimension] = dimension_verdicts.get(dimension, "unknown")
    if contract["auction_inclusion"] == "qualified":
        # A roll-up that does not say which leg it covers is an overclaim waiting to be
        # quoted, so the scope travels with it.
        contract["auction_inclusion_scope"] = sorted(
            leg for leg, verdict in legs.items() if verdict == "qualified"
        )
        contract["auction_inclusion_unresolved_legs"] = sorted(
            leg for leg, verdict in legs.items() if verdict != "qualified"
        )

    # A dimension can be unknown because nobody looked, or unknown because every observable
    # surface was examined and none carries it. Recording which keeps the second kind from
    # being reopened as though it were the first.
    contract["unresolved_dimension_resolution"] = dict(exhausted_dimensions or {})

    if qualified:
        contract["market_scope"] = "partially_qualified"
        contract["state"] = "A_composition_partially_qualified"
        contract["qualified_dimensions"] = sorted(qualified)
    else:
        contract["market_scope"] = "permanently_unresolved"
        contract["state"] = "B_composition_permanently_unresolved_through_vci"
        contract["market_composition_resolution"] = (
            resolution or "unavailable_from_observed_vci_surfaces"
        )
        contract["permanence_scope"] = (
            "Under the currently observable VCI contract. Not a claim that VCI can never "
            "publish a field definition; a first-party definition would reopen this."
        )
    return contract


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
    """Refuse a contract that has leaked an unearned upgrade."""
    if contract.get("liquidity_actionable"):
        raise CompositionError("liquidity_actionable_must_stay_false")
    if contract.get("market_scope") not in MARKET_SCOPE_STATES:
        raise CompositionError(f"market_scope_state_invalid:{contract.get('market_scope')}")
    if contract.get("market_scope") == "partially_qualified" and not contract.get("qualified_dimensions"):
        raise CompositionError("partially_qualified_without_a_qualified_dimension")
    if contract.get("auction_inclusion") == "qualified" and not contract.get("auction_inclusion_scope"):
        raise CompositionError("qualified_auction_inclusion_must_name_its_legs")
    if contract.get("further_vci_pagination_authorized"):
        raise CompositionError("further_pagination_is_not_authorized")
    if contract.get("further_speculative_endpoint_probe_authorized"):
        raise CompositionError("speculative_endpoint_probing_is_not_authorized")
    if contract.get("provider") != PROVIDER:
        raise CompositionError("contract_provider_must_be_vci")
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
