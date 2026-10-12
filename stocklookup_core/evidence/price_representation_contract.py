"""Explicit, versioned provider-native-to-canonical price representation contracts.

WHY THIS MODULE EXISTS
    DNSE's own API already carries an established thousands-of-VND price convention --
    ``dnse_bid_ask_capability.PRICE_UNIT = "thousands_of_vnd"`` is an active, qualified
    constant (``QUALIFIED_FOR_DISPLAY_ONLY``) for the bid/ask depth endpoint -- but nothing
    generalized that convention to the closed-session OHLC endpoint, and nothing made the
    provider-native-to-canonical-VND mapping an explicit, inspectable, versioned contract
    that every O/H/L/C field goes through identically. That gap is exactly how
    `docs/STATE.md`'s "FHSC/DNSE OHLC Reconciliation Integrity V1" defect happened: a prior
    pipeline (P3F9B) multiplied *close* by 1,000 while leaving *open/high/low* provider-native
    -- a non-uniform, undocumented, per-field scaling this module makes structurally
    impossible by resolving one contract per (source, capability, instrument_class) and
    applying it to every field in the same call (:func:`to_canonical_ohlc`).

    This module intentionally does NOT re-derive or promote the DNSE OHLC unit as
    `documented_verified` or `empirically_deduced` (docs/AI_RULES.md's own evidence tiers).
    It is a third, distinct thing: an explicit, owner-directed representation contract
    (:data:`CONTRACT_BASIS_TIER`), corroborated by same-API precedent (the bid/ask constant
    above) and by an independent official anchor (HOSE's own HPG 2024-12-31 annual report,
    which labels its price field "VND Thousand" -- see
    ``market_basis_capability_registry.OFFICIAL_RAW_PRICE_OBSERVATIONS``), but not claimed as
    independently proven for the OHLC endpoint specifically. See the module docstring of
    ``dnse_provider_native_closed_ohlc.py``, whose own ``FORMAL_PRICE_UNIT =
    "UNRESOLVED"`` this module deliberately leaves untouched.

WHAT IT ADDS ON TOP
    A closed, per-(source, capability_id, instrument_class) contract table
    (:data:`REPRESENTATION_CONTRACTS`) naming the provider-native and canonical units, the
    exact fields the contract applies to, and its corroborating evidence. Lookup
    (:func:`lookup_contract`) is exact-match only -- no nearest-match, no provider-wide
    default, no numeric-magnitude branch anywhere in this module. Two entry points apply it:
    :func:`to_canonical` for one field and :func:`to_canonical_ohlc` for all four O/H/L/C
    fields through one resolved contract, guaranteeing uniformity by construction.

WHAT IT DOES NOT DO
    It never infers a representation from a value's magnitude -- every transform is a table
    lookup keyed by identity, never a comparison against the number being converted. It never
    touches ``provider_price_basis_registry.py``, ``corporate_action_factors.py``, or any
    RAW_AS_TRADED/PIT/adjustment-basis module -- this module has no import of any of them, and
    ``tests/test_price_representation_contract.py`` asserts that statically. It never converts
    a field whose native unit is already VND: DNSE foreign-flow buy/sell/net value fields
    (``dnse_foreign_flow_capability.VALUE_UNIT = "vnd"``, explicitly raw, not thousands) are
    deliberately absent from :data:`REPRESENTATION_CONTRACTS` -- passing them through this
    module's scale factor would silently invent a 1,000x error, which is precisely the
    magnitude-blind mistake an explicit per-capability contract exists to prevent. It never
    changes ``is_actionable``, RAW_AS_TRADED eligibility, or any liquidity/valuation/execution
    gate; every result carries ``authority_effect: "NONE"``.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

CONTRACT_SCHEMA_VERSION = "1.0.0"

PROVIDER_NATIVE_UNIT = "thousands_of_vnd_per_share"
CANONICAL_UNIT = "vnd_per_share"
SCALE_FACTOR = Decimal("1000")

OHLC_FIELDS = ("open", "high", "low", "close")

#: Distinct from docs/AI_RULES.md's `documented_verified` / `empirically_deduced` source-
#: semantics tiers. A representation contract at this tier is an explicit, named,
#: owner-directed definitional mapping -- analogous to "DNSE is the provider direction" being
#: an owner decision recorded in docs/DECISIONS.md, not a Producer-derived empirical finding.
#: It must never be read, logged, or cited as though it were either evidence tier.
CONTRACT_BASIS_TIER = "owner_directed_contractual_assumption"


class RepresentationContractError(ValueError):
    """Fail-closed refusal: no contract exists for the exact identity requested."""


def _contract(
    *, source: str, capability_id: str, instrument_class: str, applies_to_fields: tuple[str, ...],
    corroborating_evidence: tuple[str, ...], explicitly_independent_of: tuple[str, ...],
    established_at: str,
) -> dict[str, Any]:
    return {
        "contract_id": f"{source}:{capability_id}:{instrument_class}:kvnd_to_vnd/v1",
        "contract_schema_version": CONTRACT_SCHEMA_VERSION,
        "source": source,
        "capability_id": capability_id,
        "instrument_class": instrument_class,
        "provider_native_unit": PROVIDER_NATIVE_UNIT,
        "canonical_unit": CANONICAL_UNIT,
        "scale_factor": str(SCALE_FACTOR),
        "applies_to_fields": applies_to_fields,
        "contract_basis_tier": CONTRACT_BASIS_TIER,
        "corroborating_evidence": corroborating_evidence,
        "explicitly_independent_of": explicitly_independent_of,
        "established_at": established_at,
        "authority_effect": "NONE",
    }


_EXPLICITLY_INDEPENDENT_OF = (
    "dnse_provider_native_closed_ohlc.FORMAL_PRICE_UNIT (remains UNRESOLVED)",
    "dnse_provider_native_closed_ohlc.RAW_AS_TRADED (remains NOT_QUALIFIED)",
    "provider_price_basis_registry.py price-basis verdicts (adjustment/raw-as-traded; untouched)",
    "market_data_source_authority.DNSE_OHLC_PRICE_BASIS (ADJUSTED_CONFIRMED_NON_RAW_NON_POINT_IN_TIME; untouched)",
    "PIT backtest eligibility and execution authority (both remain independently blocked)",
)

#: The full contract table. Exact-match lookup only -- see :func:`lookup_contract`. Adding a
#: capability here means adding a new row with its own corroborating evidence, never widening
#: an existing row's ``applies_to_fields`` or ``instrument_class`` by inference.
REPRESENTATION_CONTRACTS: tuple[dict[str, Any], ...] = (
    _contract(
        source="DNSE", capability_id="ohlc_1D", instrument_class="VN_LISTED_EQUITY",
        applies_to_fields=OHLC_FIELDS,
        corroborating_evidence=(
            "dnse_bid_ask_capability.PRICE_UNIT = 'thousands_of_vnd' "
            "(same DNSE API, bid/ask depth endpoint, QUALIFIED_FOR_DISPLAY_ONLY)",
            "dnse_foreign_flow_capability.py docstring: 'the opposite unit convention from "
            "price/depth fields (thousands of VND) observed elsewhere in this same API'",
            "market_basis_capability_registry.OFFICIAL_RAW_PRICE_OBSERVATIONS: HOSE's own "
            "HPG 2024-12-31 annual report labels its closing-price field 'VND Thousand' "
            "(raw_value=26.65, value_vnd_per_share=26650) -- independent official evidence "
            "of the market-wide quoting convention, not a DNSE-specific proof",
        ),
        explicitly_independent_of=_EXPLICITLY_INDEPENDENT_OF,
        established_at="2026-08-21",
    ),
    _contract(
        source="DNSE", capability_id="bid_ask_depth", instrument_class="VN_LISTED_EQUITY",
        applies_to_fields=("bid_price", "ask_price"),
        corroborating_evidence=(
            "ALREADY_ESTABLISHED: dnse_bid_ask_capability.PRICE_UNIT = 'thousands_of_vnd' is "
            "an active qualified constant for this exact endpoint; this contract entry "
            "restates it in this module's uniform, versioned shape rather than re-deriving it.",
        ),
        explicitly_independent_of=_EXPLICITLY_INDEPENDENT_OF,
        established_at="2026-08-21",
    ),
)

#: Fields this repository has already established are natively VND (not thousands) on the
#: same DNSE API, named explicitly so their absence from REPRESENTATION_CONTRACTS above reads
#: as a decision, not an omission. Never looked up for a transform; documentation only.
NATIVE_VND_NO_TRANSFORM_CAPABILITIES: tuple[dict[str, str], ...] = (
    {
        "source": "DNSE", "capability_id": "foreign_trading",
        "fields": "buyTradedAmount, sellTradedAmount, totalBuy*, totalSell* (value fields only)",
        "reason": "dnse_foreign_flow_capability.VALUE_UNIT = 'vnd' (raw, confirmed by magnitude "
                  "plausibility against known daily turnover) -- applying this module's "
                  "1000x scale factor here would introduce a fabricated error, not a fix.",
    },
)


def lookup_contract(source: str, capability_id: str, instrument_class: str) -> dict[str, Any]:
    """Exact-match contract lookup. No nearest-match, no default, no fallback."""
    named_source = str(source).strip().upper()
    for entry in REPRESENTATION_CONTRACTS:
        if (entry["source"] == named_source and entry["capability_id"] == capability_id
                and entry["instrument_class"] == instrument_class):
            return dict(entry)
    raise RepresentationContractError(
        f"no_representation_contract:{named_source}:{capability_id}:{instrument_class}"
    )


def _to_decimal(value: Any, *, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise RepresentationContractError(f"non_numeric_provider_native_value:{field}") from exc


def to_canonical(
    value: Any, *, source: str, capability_id: str, instrument_class: str, field: str,
) -> dict[str, Any]:
    """Convert one provider-native field value to its canonical representation.

    The transform is a single deterministic multiplication by the resolved contract's
    ``scale_factor`` -- never a comparison against ``value`` itself. An unknown identity or a
    field the contract does not name both fail closed rather than guessing.
    """
    contract = lookup_contract(source, capability_id, instrument_class)
    if field not in contract["applies_to_fields"]:
        raise RepresentationContractError(
            f"field_not_covered_by_contract:{field}:{contract['contract_id']}"
        )
    native = _to_decimal(value, field=field)
    canonical = native * Decimal(contract["scale_factor"])
    return {
        "field": field,
        "provider_native_value": str(native),
        "provider_native_unit": contract["provider_native_unit"],
        "canonical_value": str(canonical),
        "canonical_unit": contract["canonical_unit"],
        "contract_id": contract["contract_id"],
        "contract_schema_version": contract["contract_schema_version"],
        "contract_basis_tier": contract["contract_basis_tier"],
        "deterministic": True,
        "authority_effect": "NONE",
    }


def to_canonical_ohlc(
    *, open_: Any, high: Any, low: Any, close: Any, source: str, capability_id: str, instrument_class: str,
) -> dict[str, Any]:
    """Convert all four O/H/L/C fields through exactly one resolved contract.

    Resolving the contract once and mapping it identically over every field is what makes a
    close-only (or otherwise per-field) scaling structurally impossible here -- see the
    module docstring for the P3F9B defect this directly prevents from recurring.
    """
    contract = lookup_contract(source, capability_id, instrument_class)
    missing = [f for f in OHLC_FIELDS if f not in contract["applies_to_fields"]]
    if missing:
        raise RepresentationContractError(
            f"contract_does_not_cover_all_ohlc_fields:{contract['contract_id']}:{missing}"
        )
    values = {"open": open_, "high": high, "low": low, "close": close}
    fields = {
        name: to_canonical(
            raw, source=source, capability_id=capability_id, instrument_class=instrument_class, field=name,
        )
        for name, raw in values.items()
    }
    return {
        "fields": fields,
        "contract_id": contract["contract_id"],
        "contract_schema_version": contract["contract_schema_version"],
        "uniform_transformation": True,
        "authority_effect": "NONE",
    }


def assert_deterministic_replay(
    value: Any, *, source: str, capability_id: str, instrument_class: str, field: str,
) -> dict[str, Any]:
    """Refuse a non-reproducible transform. Two calls with identical input must agree exactly."""
    first = to_canonical(value, source=source, capability_id=capability_id, instrument_class=instrument_class, field=field)
    second = to_canonical(value, source=source, capability_id=capability_id, instrument_class=instrument_class, field=field)
    if first != second:
        raise RepresentationContractError(f"non_deterministic_replay:{field}:{source}:{capability_id}")
    return first


def snapshot() -> dict[str, Any]:
    return {
        "contract_schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_basis_tier": CONTRACT_BASIS_TIER,
        "provider_native_unit": PROVIDER_NATIVE_UNIT,
        "canonical_unit": CANONICAL_UNIT,
        "scale_factor": str(SCALE_FACTOR),
        "contracts": [dict(c) for c in REPRESENTATION_CONTRACTS],
        "native_vnd_no_transform_capabilities": [dict(c) for c in NATIVE_VND_NO_TRANSFORM_CAPABILITIES],
        "authority_effect": "NONE",
    }
