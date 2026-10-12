"""Deterministic, fail-closed monetary-basis contract for absolute-value comparisons.

Two absolute monetary quantities (a current-research market capitalization and a TTM
financial sum, say) may only be divided or compared once both sides prove the same
currency and the same unit scale. This module holds that comparison in one place so it
is expressed once, not re-implemented ad hoc at each consumer.

It never infers a currency or a scale from magnitude, provider name, ticker, or
convention -- only from a `basis_source` citation the caller already holds. A basis is
`QUALIFIED` only when that citation is independent, official evidence (e.g. an audited
share-count note); `RESEARCH_CONTRACT_QUALIFIED` for a weaker but still real retained
code/schema proof (never promoted to official evidence); otherwise `UNKNOWN`. `UNKNOWN`
never becomes compatible with anything, including another `UNKNOWN` -- two unresolved
bases are not "the same unresolved basis", they are two absent proofs.

`known()` is the single place that recognizes every stringified spelling of "no value"
this repository's own code has been seen to produce, including `str(None) == "None"`,
which is the accidental-stringification defect this contract exists to close off.
"""
from __future__ import annotations

from typing import Any, Mapping

CONTRACT_VERSION = "monetary_basis_contract/v1"

QUALIFIED = "QUALIFIED"
RESEARCH_CONTRACT_QUALIFIED = "RESEARCH_CONTRACT_QUALIFIED"
UNKNOWN = "UNKNOWN"
BASIS_STATUSES = frozenset({QUALIFIED, RESEARCH_CONTRACT_QUALIFIED, UNKNOWN})

INCOMPATIBLE_REASON = "TTM_MARKET_CAP_MONETARY_BASIS_INCOMPATIBLE"

#: A base, unscaled representation of a currency (KBS/official-citation convention calls
#: this "units"; it means multiplier_to_vnd == 1, not "no scale is retained").
BASE_UNIT_SCALE_LABEL = "units"

#: Every stringified spelling of "no value" seen in this repository's retained data,
#: including the accidental `str(None)` result -- never a known currency or scale.
_UNKNOWN_TOKENS = frozenset({
    "", "unknown", "UNKNOWN", "Unknown", "None", "none", "NONE",
    "null", "NULL", "Null", "n/a", "N/A", "na", "NA", "not_applicable", "NOT_APPLICABLE",
})


def known(value: Any) -> bool:
    """True only for a real, non-sentinel unit component.

    Never treats a stringified absence -- ``str(None) == "None"``, ``"unknown"``,
    ``""``, ... -- as known, however it was produced upstream.
    """
    if value is None:
        return False
    if isinstance(value, str) and value.strip() in _UNKNOWN_TOKENS:
        return False
    return True


def unit_component(value: Any) -> Any:
    """A known component passes through unchanged; any sentinel or non-value becomes None."""
    return value if known(value) else None


def agree(values: set[Any]) -> Any:
    """The single known component every member of `values` shares, or None otherwise.

    Requires unanimous, known agreement: a lone unresolved member (a missing field, or
    any sentinel spelling of "no value") makes the result None just as surely as an
    outright disagreement does -- a value this function has not seen cannot be assumed
    to have agreed. `values` may already contain a mix of real components and
    sentinels (as raw facts do); sentinels never count toward, or masquerade as, an
    agreed value (this is where the `str(None) == "None"` defect used to leak in: two
    missing components would stringify to the same fake "None" and appear to agree).
    """
    resolved = {unit_component(value) for value in values}
    if len(resolved) != 1:
        return None
    only = next(iter(resolved))
    return only if known(only) else None


def build_basis(*, currency: Any, scale: Any, basis_source: str,
                basis_status: str | None = None,
                multiplier_to_vnd: float | int | None = None,
                normalized_unit: str | None = None) -> dict[str, Any]:
    """One `monetary_basis_contract/v1` envelope describing a quantity's representation.

    `currency`/`scale` are the native, as-retained components -- never mutated, only
    reported. `basis_status` is never inferred from magnitude: it is `UNKNOWN` the
    moment either native component is unproven, `QUALIFIED` only when the caller
    explicitly claims independent official evidence, and otherwise defaults to
    `RESEARCH_CONTRACT_QUALIFIED` once both native components are known.
    """
    native_currency, native_scale = unit_component(currency), unit_component(scale)
    if native_currency is None or native_scale is None:
        status = UNKNOWN
    elif basis_status in (QUALIFIED, RESEARCH_CONTRACT_QUALIFIED):
        status = basis_status
    else:
        status = RESEARCH_CONTRACT_QUALIFIED
    multiplier = multiplier_to_vnd if known(multiplier_to_vnd) else None
    normalized = unit_component(normalized_unit)
    if status == UNKNOWN:
        # A comparison-usability claim (a multiplier, a normalized target unit) is never
        # reported once either native component is unproven -- but a native component
        # that *is* independently known (say, currency, while scale is not) is kept for
        # lineage: it explains exactly which half of the basis is missing, rather than
        # erasing real information the moment the pair as a whole can't be used.
        multiplier = normalized = None
    return {
        "contract_version": CONTRACT_VERSION,
        "currency": native_currency,
        "native_scale": native_scale,
        "multiplier_to_vnd": multiplier,
        "normalized_unit": normalized,
        "basis_source": basis_source,
        "basis_status": status,
    }


def normalize_value(value: Any, basis: Mapping[str, Any] | None) -> Any:
    """`value` rescaled to the basis's canonical unit when a multiplier is proven.

    A numeric value with no known multiplier passes through unchanged -- dividing two
    values that share one unproven native scale is still valid (the unknown factor
    cancels), which is why `compatible()` accepts a same-native-scale match without
    ever requiring `multiplier_to_vnd` on either side.
    """
    multiplier = (basis or {}).get("multiplier_to_vnd")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and known(multiplier):
        return value * multiplier
    return value


def compatible(basis_a: Mapping[str, Any] | None, basis_b: Mapping[str, Any] | None) -> tuple[bool, str | None]:
    """Two bases are comparable only once both are proven and agree on currency and scale.

    Agreement is reached either natively (same currency, same native scale -- the usual
    case, valid even without an absolute multiplier) or, when native scales differ, via
    a shared `normalized_unit` that both sides reach through a known `multiplier_to_vnd`
    (so the caller can rescale each value with `normalize_value` before comparing).
    """
    a, b = basis_a or {}, basis_b or {}
    if a.get("basis_status") in (None, UNKNOWN) or b.get("basis_status") in (None, UNKNOWN):
        return False, INCOMPATIBLE_REASON
    same_currency = known(a.get("currency")) and known(b.get("currency")) and a.get("currency") == b.get("currency")
    if not same_currency:
        return False, INCOMPATIBLE_REASON
    same_native_scale = known(a.get("native_scale")) and known(b.get("native_scale")) and a.get("native_scale") == b.get("native_scale")
    same_normalized = (
        known(a.get("normalized_unit")) and known(b.get("normalized_unit"))
        and a.get("normalized_unit") == b.get("normalized_unit")
        and known(a.get("multiplier_to_vnd")) and known(b.get("multiplier_to_vnd"))
    )
    if same_native_scale or same_normalized:
        return True, None
    return False, INCOMPATIBLE_REASON
