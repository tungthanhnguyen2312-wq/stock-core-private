"""Human/AI decision evidence packet.

Python records measurements, eligibility, and provenance. AI may narrate only
inside the narration slot. The human capital decision is not delegated.
There is no buy score and no collapsed universal scalar.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from current_valuation_denominator_integrity import classify_claim

CONTRACT_VERSION = "human_ai_decision_evidence_packet/v2"
SECTIONS = ("market", "stock", "tactical", "comparison", "uncertainty", "history", "counter_thesis")
FORBIDDEN = ("buy_score", "recommendation", "probability", "expected_return", "target_price", "position_size", "sizing", "composite_score")
ANALOGUE_FIELDS = ("matching_method", "evidence_tier", "sample_size", "regime_similarity", "missing_dimensions")
EVIDENCE_TIERS = ("PIT_AUTHORITATIVE", "RECONSTRUCTED_RESEARCH", "EXPLANATORY_ONLY", "UNKNOWN")


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _reject_forbidden(payload: Mapping[str, Any], *, where: str) -> None:
    for key in FORBIDDEN:
        if key in payload:
            raise ValueError(f"FORBIDDEN_{where}_{key.upper()}")


def feature_vector(measurements: Mapping[str, Any] | None) -> dict[str, Any]:
    """Keep named measurements. Refuse a universal scalar."""
    if not isinstance(measurements, Mapping) or not measurements:
        return {"status": "MISSING", "measurements": {}, "collapsed_scalar": None}
    _reject_forbidden(measurements, where="FEATURE")
    if "value" in measurements and len(measurements) == 1:
        raise ValueError("FEATURE_VECTOR_COLLAPSED_SCALAR")
    cleaned = {name: measurements[name] for name in sorted(measurements)}
    return {"status": "PRESENT", "measurements": cleaned, "collapsed_scalar": None}


def qualify_analogue(analogue: Mapping[str, Any]) -> dict[str, Any]:
    """An analogue is usable only when its matching disclosure is complete."""
    missing = [field for field in ANALOGUE_FIELDS if analogue.get(field) in (None, "", [])]
    tier = analogue.get("evidence_tier")
    if tier not in EVIDENCE_TIERS:
        missing.append("evidence_tier")
    eligible = not missing
    return {
        "matching_method": analogue.get("matching_method"),
        "evidence_tier": tier if tier in EVIDENCE_TIERS else None,
        "sample_size": analogue.get("sample_size"),
        "regime_similarity": analogue.get("regime_similarity"),
        "missing_dimensions": list(analogue.get("missing_dimensions") or []),
        "forward_outcome": analogue.get("forward_outcome"),
        "status": "DISCLOSED" if eligible else "INCOMPLETE",
        "eligible": eligible,
        "disclosure_gaps": sorted(set(missing)),
    }


def _section(spec: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(spec, Mapping) or not spec:
        return {"status": "MISSING", "fields": {}}
    _reject_forbidden(spec, where="SECTION")
    fields = {}
    for name in sorted(spec):
        raw = spec[name]
        if isinstance(raw, Mapping) and "claim" in raw:
            fields[name] = {"claim": classify_claim(raw["claim"]), "value": raw.get("value")}
        elif raw is None:
            fields[name] = {"claim": "MISSING", "value": None}
        else:
            fields[name] = {"claim": "FACT", "value": raw}
    return {"status": "PRESENT", "fields": fields}


def _spine_view(spine: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(spine, Mapping) or not spine:
        return None
    _reject_forbidden(spine, where="SPINE")
    limitation = spine.get("retention_limitation")
    return {
        "coverage_state": spine.get("coverage_state"),
        "denominator_integrity": spine.get("denominator_integrity"),
        "ci_freshness": spine.get("ci_freshness"),
        "corporate_action_state": spine.get("corporate_action_state"),
        "analogue_evidence_tier": spine.get("analogue_evidence_tier"),
        "analogue_regime_similarity": spine.get("analogue_regime_similarity"),
        "analogue_outcomes": spine.get("analogue_outcomes"),
        "mfe": spine.get("mfe"),
        "mae": spine.get("mae"),
        "failure_rate": spine.get("failure_rate"),
        "sample_quality": spine.get("sample_quality"),
        "matched_control_readiness": spine.get("matched_control_readiness"),
        "matched_control_edge": spine.get("matched_control_edge"),
        "retention_limitation": limitation if isinstance(limitation, str) and limitation.strip() else None,
        "buy_score": None,
        "probability": None,
        "target_price": None,
    }


def build_packet(
    *,
    ticker: str,
    sections: Mapping[str, Mapping[str, Any] | None] | None = None,
    feature_measurements: Mapping[str, Any] | None = None,
    analogues: list[Mapping[str, Any]] | None = None,
    canonical_packet_identity: str | None = None,
    ai_narration: str | None = None,
    capital_decision: Any = None,
    spine: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one ticker packet. Input analogue order is preserved."""
    del capital_decision  # retained so a caller cannot sneak a delegated decision through
    supplied = sections or {}
    _reject_forbidden(supplied, where="PACKET")
    projected_sections = {name: _section(supplied.get(name) if isinstance(supplied.get(name), Mapping) else None) for name in SECTIONS}
    history = projected_sections["history"]
    qualified = [qualify_analogue(item) for item in analogues or []]
    history["analogues"] = qualified
    history["analogue_order"] = "INPUT_ORDER"
    history["cherry_pick"] = False
    if qualified and history["status"] == "MISSING":
        history["status"] = "PRESENT"
    spine_view = _spine_view(spine)
    if spine_view is not None:
        history["spine"] = spine_view
        if history["status"] == "MISSING":
            history["status"] = "PRESENT"
        if spine_view.get("retention_limitation"):
            history["fields"]["retention_limitation"] = {"claim": "FACT", "value": spine_view["retention_limitation"]}
            uncertainty = projected_sections["uncertainty"]
            uncertainty["fields"]["retention_limitation"] = {"claim": "FACT", "value": spine_view["retention_limitation"]}
            if uncertainty["status"] == "MISSING":
                uncertainty["status"] = "PRESENT"
    packet = {
        "contract_version": CONTRACT_VERSION,
        "ticker": ticker,
        "canonical_packet_identity": canonical_packet_identity,
        "sections": projected_sections,
        "feature_vector": feature_vector(feature_measurements),
        "owners": {"measurements": "PYTHON", "narration": "AI", "capital_decision": "HUMAN"},
        "ai_narration": {
            "authority": "NARRATION_ONLY",
            "status": "PRESENT" if isinstance(ai_narration, str) and ai_narration.strip() else "MISSING",
            "value": ai_narration if isinstance(ai_narration, str) and ai_narration.strip() else None,
        },
        "capital_decision": {"owner": "HUMAN", "status": "NOT_DELEGATED", "value": None},
        "is_actionable": False,
        "buy_score": None,
        "probability": None,
        "target_price": None,
    }
    packet["packet_identity"] = "human_ai_decision_evidence_packet:" + _sha({key: packet[key] for key in packet if key != "packet_identity"})
    return packet
