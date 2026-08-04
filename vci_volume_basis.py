"""Versioned, fail-closed VCI daily-volume qualification declaration."""
from __future__ import annotations
from typing import Any, Mapping

VERSION = "1.0.0"
VCI_VOLUME_BASIS = "unknown"
VOLUME_UNIT = "unknown"
RAW_FIELD = "v"
RAW_ALIAS_FIELD = "accumulatedVolume"
FORWARD_REQUIRED = ("provider", "raw_volume_field", "raw_volume_alias_field", "volume_basis", "volume_basis_verified", "basis_evidence_id")

#: Settled by the composition closeout: the observed quantity is a count of shares. Recorded
#: separately from ``volume_basis`` because they are different questions -- what the number
#: counts in (shares) versus whether it is corporate-action adjusted (still unknown). Rolling
#: them together is how "the unit is qualified" would have become "the basis is verified".
OBSERVED_VOLUME_UNIT = "shares"

#: The gate this module used to imply, and no longer does.
#:
#: ``forward_gate.action`` read ``block_liquidity_activation_when_unverified`` -- which says,
#: correctly read, that verifying the basis *activates* liquidity. After the composition
#: closeout that is false. Knowing the unit is shares and that the provider's accumulator
#: reconciles leaves the question liquidity actually depends on -- which trades the figure
#: counts -- unanswered. So liquidity activation is refused here unconditionally, and
#: ``validate_forward`` says so in its return value rather than leaving the caller to infer
#: permission from a successful validation.
LIQUIDITY_ACTIVATION_PERMITTED = False
LIQUIDITY_BLOCK_REASON = "complete_market_composition_not_qualified"
LIQUIDITY_REOPEN_CONDITION = "new_authoritative_source_contract"


def declaration() -> dict[str, Any]:
    return {
        "schema_version": VERSION,
        "provider": "VCI",
        "volume_basis": VCI_VOLUME_BASIS,
        "volume_basis_verified": False,
        "volume_unit": VOLUME_UNIT,
        "observed_volume_unit": OBSERVED_VOLUME_UNIT,
        "raw_payload_fields": {"primary": RAW_FIELD, "same_value_alias": RAW_ALIAS_FIELD},
        "stored_field": "ohlcv.volume",
        "transformation": "pd.to_numeric(raw.volume).fillna(0).astype(int64); no volume scaling or adjustment",
        "conflict_handling": "reject qualification on mismatched raw aliases, source/provider mixing, or competing basis evidence",
        "forward_gate": {
            "required": list(FORWARD_REQUIRED),
            "action": "block_liquidity_activation_unconditionally",
            "liquidity_activation_permitted": LIQUIDITY_ACTIVATION_PERMITTED,
            "reason": LIQUIDITY_BLOCK_REASON,
            "reopen_condition": LIQUIDITY_REOPEN_CONDITION,
        },
        "limitations": [
            "The VCI chart response names v/accumulatedVolume but does not declare shares, lots, matched-volume, total-traded-volume, or adjustment semantics.",
            "Market composition is unresolved: no observed VCI surface separates matched from negotiated, odd-lot or closing-auction quantities. Verifying this basis would not change that.",
        ],
    }


def validate_forward(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a forwarded basis record. Success is *not* a liquidity permission.

    The returned record carries ``liquidity_activation_permitted: False`` explicitly, so a
    caller that wants to open liquidity has to override a stated refusal rather than read
    consent into the absence of an exception.
    """
    if any(key not in record for key in FORWARD_REQUIRED):
        raise ValueError("vci_volume_basis_fields_missing")
    if record["provider"] != "VCI" or record["raw_volume_field"] != RAW_FIELD or record["raw_volume_alias_field"] != RAW_ALIAS_FIELD:
        raise ValueError("vci_volume_source_mapping_conflict")
    if record["volume_basis_verified"] is not True or record["volume_basis"] not in {"raw_shares_traded", "adjusted_volume"}:
        raise ValueError("vci_volume_basis_unqualified")
    validated = dict(record)
    validated["liquidity_activation_permitted"] = LIQUIDITY_ACTIVATION_PERMITTED
    validated["liquidity_block_reason"] = LIQUIDITY_BLOCK_REASON
    validated["liquidity_reopen_condition"] = LIQUIDITY_REOPEN_CONDITION
    return validated