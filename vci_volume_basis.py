"""Versioned, fail-closed VCI daily-volume qualification declaration."""
from __future__ import annotations
from typing import Any, Mapping

VERSION = "1.0.0"
VCI_VOLUME_BASIS = "unknown"
VOLUME_UNIT = "unknown"
RAW_FIELD = "v"
RAW_ALIAS_FIELD = "accumulatedVolume"
FORWARD_REQUIRED = ("provider", "raw_volume_field", "raw_volume_alias_field", "volume_basis", "volume_basis_verified", "basis_evidence_id")


def declaration() -> dict[str, Any]:
    return {
        "schema_version": VERSION,
        "provider": "VCI",
        "volume_basis": VCI_VOLUME_BASIS,
        "volume_basis_verified": False,
        "volume_unit": VOLUME_UNIT,
        "raw_payload_fields": {"primary": RAW_FIELD, "same_value_alias": RAW_ALIAS_FIELD},
        "stored_field": "ohlcv.volume",
        "transformation": "pd.to_numeric(raw.volume).fillna(0).astype(int64); no volume scaling or adjustment",
        "conflict_handling": "reject qualification on mismatched raw aliases, source/provider mixing, or competing basis evidence",
        "forward_gate": {"required": list(FORWARD_REQUIRED), "action": "block_liquidity_activation_when_unverified"},
        "limitations": ["The VCI chart response names v/accumulatedVolume but does not declare shares, lots, matched-volume, total-traded-volume, or adjustment semantics."],
    }


def validate_forward(record: Mapping[str, Any]) -> dict[str, Any]:
    if any(key not in record for key in FORWARD_REQUIRED):
        raise ValueError("vci_volume_basis_fields_missing")
    if record["provider"] != "VCI" or record["raw_volume_field"] != RAW_FIELD or record["raw_volume_alias_field"] != RAW_ALIAS_FIELD:
        raise ValueError("vci_volume_source_mapping_conflict")
    if record["volume_basis_verified"] is not True or record["volume_basis"] not in {"raw_shares_traded", "adjusted_volume"}:
        raise ValueError("vci_volume_basis_unqualified")
    return dict(record)