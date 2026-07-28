"""Fail-closed contract for Price Basis, Corporate Action Adjustments, and Volume Semantics.

Establishes deterministic, fail-closed metadata standards for price series, volume series,
and derived technical/financial metrics. Prevents silent mixing of raw and adjusted price series,
independently qualifies volume treatment, and exposes explicit provenance and uncertainty flags.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Iterable, Mapping, Sequence


class PriceBasis(str, Enum):
    RAW = "raw"
    ADJUSTED = "adjusted"
    UNKNOWN = "unknown"


class VolumeBasis(str, Enum):
    RAW_SHARES_TRADED = "raw_shares_traded"
    ADJUSTED_VOLUME = "adjusted_volume"
    UNKNOWN = "unknown"


class PriceBasisMismatchError(ValueError):
    """Raised when raw and adjusted price series are mixed without an explicit conversion contract."""


def qualify_price_basis(
    basis: str | PriceBasis | None,
    *,
    verified: bool = False,
    adjustment_source: str | None = None,
    effective_date: str | None = None,
    provenance_notes: Sequence[str] = (),
) -> dict[str, Any]:
    """Qualify a price basis string into a deterministic, fail-closed contract envelope."""
    raw_str = str(basis).strip().lower() if basis is not None else "unknown"

    if raw_str in (PriceBasis.RAW.value, PriceBasis.ADJUSTED.value) and verified:
        selected_basis = raw_str
        is_verified = True
        is_actionable = True
        limitations = list(provenance_notes)
    else:
        selected_basis = PriceBasis.UNKNOWN.value
        is_verified = False
        is_actionable = False
        limitations = list(provenance_notes) + [
            "Price basis is unverified or unknown; corporate actions may affect price and return calculations."
        ]

    return {
        "price_basis": selected_basis,
        "price_basis_verified": is_verified,
        "is_actionable": is_actionable,
        "adjustment_source": adjustment_source if is_verified else None,
        "effective_date": effective_date if is_verified else None,
        "limitations": limitations,
    }


def qualify_volume_basis(
    basis: str | VolumeBasis | None = VolumeBasis.RAW_SHARES_TRADED.value,
    *,
    verified: bool = True,
    provenance_notes: Sequence[str] = (),
) -> dict[str, Any]:
    """Qualify historical volume basis independently from price basis.

    Corporate actions (splits/dividends) do not automatically adjust volume when price is adjusted.
    """
    raw_str = str(basis).strip().lower() if basis is not None else "unknown"

    if raw_str in (VolumeBasis.RAW_SHARES_TRADED.value, VolumeBasis.ADJUSTED_VOLUME.value) and verified:
        selected_basis = raw_str
        is_verified = True
    else:
        selected_basis = VolumeBasis.UNKNOWN.value
        is_verified = False

    return {
        "volume_basis": selected_basis,
        "volume_basis_verified": is_verified,
        "price_volume_basis_decoupled": True,
        "limitations": list(provenance_notes) + [
            "Volume basis is evaluated independently from price basis."
        ],
    }


def validate_basis_compatibility(
    basis_a: str | Mapping[str, Any],
    basis_b: str | Mapping[str, Any],
    *,
    strict: bool = True,
) -> dict[str, Any]:
    """Validate that two price series or metrics use compatible price bases before combining.

    Raises PriceBasisMismatchError in strict mode if 'raw' and 'adjusted' series are mixed.
    """
    val_a = basis_a.get("price_basis") if isinstance(basis_a, Mapping) else str(basis_a)
    val_b = basis_b.get("price_basis") if isinstance(basis_b, Mapping) else str(basis_b)

    str_a = str(val_a).strip().lower()
    str_b = str(val_b).strip().lower()

    if str_a == PriceBasis.UNKNOWN.value or str_b == PriceBasis.UNKNOWN.value:
        return {
            "is_compatible": False,
            "reason": "unverified_or_unknown_basis",
            "basis_a": str_a,
            "basis_b": str_b,
        }

    if str_a != str_b:
        msg = f"Cannot combine mixed price bases: series A is {str_a!r}, series B is {str_b!r}."
        if strict:
            raise PriceBasisMismatchError(msg)
        return {
            "is_compatible": False,
            "reason": "mixed_raw_and_adjusted_basis",
            "basis_a": str_a,
            "basis_b": str_b,
        }

    return {
        "is_compatible": True,
        "reason": "compatible_basis",
        "basis_a": str_a,
        "basis_b": str_b,
    }


def derive_metric_basis(
    price_contract: Mapping[str, Any],
    volume_contract: Mapping[str, Any] | None = None,
    metric_name: str = "derived_metric",
) -> dict[str, Any]:
    """Propagate price and volume basis metadata down to derived indicators and valuation metrics."""
    price_basis = price_contract.get("price_basis", PriceBasis.UNKNOWN.value)
    price_verified = price_contract.get("price_basis_verified", False)
    vol_basis = volume_contract.get("volume_basis", VolumeBasis.RAW_SHARES_TRADED.value) if volume_contract else None

    is_actionable = price_verified and (price_basis != PriceBasis.UNKNOWN.value)

    return {
        "metric_name": metric_name,
        "price_basis": price_basis,
        "price_basis_verified": price_verified,
        "volume_basis": vol_basis,
        "is_actionable": is_actionable,
        "qualification_status": "qualified" if is_actionable else "unverified_or_unknown_basis",
        "warnings": [] if is_actionable else [
            f"Metric {metric_name!r} is derived from an unverified or unknown price basis."
        ],
    }
