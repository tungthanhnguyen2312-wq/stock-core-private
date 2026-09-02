"""Compact per-ticker market-structure-breakout product projection (TACTICAL_MARKET_STRUCTURE_AND_BREAKOUT_V3).

Consumes ``technical_structure_context`` v2 to emit a compact, serialisable per-ticker record
suitable for downstream consumption by ``INTEGRATED_INVESTMENT_DECISION_PRODUCT_V1``.

No new computation is performed here — this module only selects, renames, and packages output
keys from the extended ``technical_structure_context`` artifact.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

CONTRACT_VERSION = "market_structure_breakout_product_projection/v1"
MILESTONE = "TACTICAL_MARKET_STRUCTURE_AND_BREAKOUT_V3"


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


_IDENTITY_EXCLUDED = {"artifact_sha256", "artifact_identity", "requested_at"}


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {k: v for k, v in value.items() if k not in _IDENTITY_EXCLUDED}
    digest = _sha256(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


def _project_ticker(ticker: str, record: Mapping[str, Any], session: str) -> dict[str, Any]:
    swing = record.get("swing_structure") or {}
    bos = record.get("bos_context") or {}
    choch = record.get("choch_context") or {}
    brk_v3 = record.get("breakout_state_v3") or {}
    pivot = record.get("pivot_context") or {}
    trigger = record.get("trigger_context") or {}
    invalid = record.get("invalidation_context") or {}
    # V1 fields preserved in compact form
    structure = record.get("structure_context") or {}
    trend = record.get("trend_context") or {}
    contraction = record.get("contraction_context") or {}
    base = record.get("base_context") or {}
    brk_v1 = record.get("breakout_context") or {}
    rv = record.get("relative_volume") or {}
    eligibility = record.get("eligibility") or {}

    return {
        "ticker": ticker,
        "as_of_session": session,
        "eligible": eligibility.get("status") == "ELIGIBLE",
        "close_history_depth": record.get("close_history_depth"),
        # V1 compact
        "structure_status": structure.get("structure_status"),
        "trend_state": trend.get("trend_state"),
        "range_state": contraction.get("range_state"),
        "ma20_slope_state": (trend.get("ma20_slope") or {}).get("slope_state"),
        "base_status": base.get("base_status"),
        "breakout_event": brk_v1.get("event"),
        "relative_volume_provider_scoped": rv.get("relative_volume_provider_scoped"),
        # V3 swing structure
        "market_structure_state": swing.get("market_structure_state"),
        "swing_high_sequence": swing.get("swing_high_sequence"),
        "swing_low_sequence": swing.get("swing_low_sequence"),
        "confirmed_swing_count": swing.get("confirmed_swing_count"),
        # BOS / CHoCH
        "bos_state": bos.get("bos_state"),
        "bos_direction": bos.get("bos_direction"),
        "broken_level": bos.get("broken_level"),
        "bos_break_distance_pct": bos.get("break_distance_pct"),
        "choch_state": choch.get("choch_state"),
        # Pivot / Breakout V3
        "pivot_price": pivot.get("pivot_price"),
        "pivot_method": pivot.get("pivot_method"),
        "distance_to_pivot_pct": pivot.get("distance_to_pivot_pct"),
        "breakout_state_v3": brk_v3.get("breakout_state"),
        # Trigger / Invalidation
        "trigger_type": trigger.get("trigger_type"),
        "trigger_level": trigger.get("trigger_level"),
        "trigger_state": trigger.get("trigger_state"),
        "distance_to_trigger_pct": trigger.get("distance_to_trigger_pct"),
        "invalidation_level": invalid.get("invalidation_level"),
        "distance_to_invalidation_pct": invalid.get("distance_to_invalidation_pct"),
        # Metadata
        "high_low_basis": (record.get("high_low_basis") or {}).get("status"),
        "blockers": record.get("blockers", []),
        "fitness": "CURRENT_RESEARCH_ONLY",
        "authority": {
            "is_actionable": False,
            "requires_human_review": True,
            "not_a_recommendation_or_execution_instruction": True,
            "no_score_rank_target_or_probability": True,
        },
    }


def build_artifact(
    *,
    technical_structure: Mapping[str, Any],
    requested_at: str,
) -> dict[str, Any]:
    """Project the full ``technical_structure_context`` v2 artifact into compact records.

    Verifies source artifact identity before consuming it.
    """
    import technical_structure_context as tsc
    identity_check = tsc.content_identity(technical_structure)
    if technical_structure.get("artifact_sha256") != identity_check["artifact_sha256"]:
        raise ValueError("TECHNICAL_STRUCTURE_CONTEXT_IDENTITY_MISMATCH")

    session = technical_structure.get("session")
    source_records: Mapping[str, Any] = technical_structure.get("records") or {}

    records = {
        ticker: _project_ticker(ticker, rec, session)
        for ticker, rec in sorted(source_records.items())
    }

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "milestone": MILESTONE,
        "requested_at": requested_at,
        "session": session,
        "source_artifact": technical_structure.get("artifact_identity"),
        "coverage": {
            "candidate_count": len(records),
            "eligible_count": sum(1 for r in records.values() if r["eligible"]),
        },
        "authority_boundary": {
            "is_actionable": False,
            "requires_human_review": True,
            "not_a_recommendation": True,
            "no_universal_score": True,
        },
        "records": records,
    }
    identity = content_identity(artifact)
    artifact["artifact_sha256"] = identity["artifact_sha256"]
    artifact["artifact_identity"] = identity["artifact_identity"]
    return artifact
