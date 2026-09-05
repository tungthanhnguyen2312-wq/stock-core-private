"""Structure + momentum + participation synthesis (TACTICAL_MOMENTUM_PARTICIPATION_CONFIRMATION_V1).

This is evidence synthesis, not scoring. It never counts "N of M signals agree" toward a
threshold: RSI direction and MACD sign/cross both derive from the same underlying close-price
path, so they are folded into a single MOMENTUM_DIRECTION axis rather than two independent votes.
Only three genuinely distinct evidence axes ever contribute a reason: momentum direction
(EMA/gain-loss-smoothing based), RSI divergence (confirmed-swing-pivot based), and participation
(volume based, an entirely separate provider field). Each axis contributes at most one supporting
and one contradicting reason code; the overall state is a deterministic function of which axes are
present, never a numeric sum.

Consumes ``market_structure_breakout_product_projection`` (structure), ``tactical_momentum_context``
(momentum), and ``market_wide_relative_volume_research`` (participation). Structure stance reuses
``integrated_investment_decision_product.evaluate_tactical_phase`` -- the same already-governed
phase classification exposed as ``tactical_phase`` on the integrated record -- rather than a second,
independently-derived structure algorithm that could silently disagree with it.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from integrated_investment_decision_product import evaluate_tactical_phase

CONTRACT_VERSION = "tactical_confirmation_context/v1"
MILESTONE = "TACTICAL_MOMENTUM_PARTICIPATION_CONFIRMATION_V1"

# Reuses technical_structure_context.py's own established compression/expansion convention
# (COMPRESSION_RATIO / EXPANSION_RATIO) rather than inventing new participation thresholds.
PARTICIPATION_EXPANSION_RATIO = 1.3
PARTICIPATION_COMPRESSION_RATIO = 0.7

_STANCE_VALUES = ("BULLISH", "BEARISH", "NEUTRAL", "INSUFFICIENT_EVIDENCE")
_CONFIRMATION_STATES = ("CONFIRMED", "PARTIALLY_CONFIRMED", "NEUTRAL", "CONTRADICTED", "INSUFFICIENT_EVIDENCE")

_AUTHORITY_BOUNDARY: dict[str, Any] = {
    "evidence_synthesis_not_scoring": True,
    "no_vote_counting_across_correlated_measurements": True,
    "not_smart_money_or_institutional_activity_evidence": True,
    "not_a_recommendation_or_execution_instruction": True,
    "is_actionable": False,
    "ranking_recommendation_sizing_execution": "NOT_EMITTED",
}


class TacticalConfirmationContextError(ValueError):
    """A retained input or an invariant of this contract is violated."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


_IDENTITY_EXCLUDED_KEYS = {"artifact_sha256", "artifact_identity", "requested_at"}


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in _IDENTITY_EXCLUDED_KEYS}
    digest = _hash(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"tactical_confirmation_context:{digest}"}


# ── Structure stance (reuses the already-governed tactical_phase classification) ──────────────

# integrated_investment_decision_product.TACTICAL_* constants, mirrored as bare strings to avoid
# importing anything beyond the one pure function this module actually calls.
_BULLISH_PHASES = frozenset({"BREAKOUT_CONFIRMED", "RETEST_AFTER_BREAKOUT", "TREND_CONTINUATION", "EARLY_REVERSAL", "EXTENDED", "BREAKOUT_SETUP"})
_BEARISH_PHASES = frozenset({"BREAKDOWN", "DISTRIBUTION_RISK"})
_NEUTRAL_PHASES = frozenset({"BASE_BUILDING", "MIXED"})


def structure_stance(structure_record: Mapping[str, Any] | None) -> tuple[str, str]:
    """Return (stance, tactical_phase) via the existing, already-tested tactical_phase
    classification (integrated_investment_decision_product.evaluate_tactical_phase) -- no second
    structure algorithm, and no risk of disagreeing with the tactical_phase already exposed
    alongside this context on the same integrated record."""
    phase, _supports, _counters = evaluate_tactical_phase(structure_record)
    if phase in _BULLISH_PHASES:
        return "BULLISH", phase
    if phase in _BEARISH_PHASES:
        return "BEARISH", phase
    if phase in _NEUTRAL_PHASES:
        return "NEUTRAL", phase
    return "INSUFFICIENT_EVIDENCE", phase


# ── Momentum axis (RSI direction + MACD sign/cross folded into ONE axis; divergence separate) ──

def _combined_momentum_direction(rsi: Mapping[str, Any], macd: Mapping[str, Any]) -> str:
    rsi_dir = rsi.get("direction") if rsi.get("status") == "AVAILABLE" else None
    macd_sign = macd.get("sign") if macd.get("status") == "AVAILABLE" else None
    if rsi_dir is None and macd_sign is None:
        return "UNAVAILABLE"
    bullish = rsi_dir == "RISING" or macd_sign == "POSITIVE"
    bearish = rsi_dir == "FALLING" or macd_sign == "NEGATIVE"
    if bullish and bearish:
        return "MIXED"
    if bullish:
        return "BULLISH"
    if bearish:
        return "BEARISH"
    return "MIXED"


def _momentum_axis(stance: str, momentum_record: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    supports: list[str] = []
    contradicts: list[str] = []
    if stance not in ("BULLISH", "BEARISH"):
        return supports, contradicts

    rsi = momentum_record.get("rsi") or {}
    macd = momentum_record.get("macd") or {}
    divergence = momentum_record.get("rsi_divergence") or {}

    direction = _combined_momentum_direction(rsi, macd)
    if direction == stance:
        supports.append("MOMENTUM_DIRECTION_ALIGNED")
    elif direction != "UNAVAILABLE" and direction != "MIXED":
        contradicts.append("MOMENTUM_DIRECTION_MISALIGNED")

    if divergence.get("status") == "AVAILABLE":
        bullish_candidate = divergence.get("bullish_divergence_candidate")
        bearish_candidate = divergence.get("bearish_divergence_candidate")
        if stance == "BULLISH" and bullish_candidate:
            supports.append("BULLISH_RSI_DIVERGENCE_CANDIDATE")
        if stance == "BEARISH" and bearish_candidate:
            supports.append("BEARISH_RSI_DIVERGENCE_CANDIDATE")
        if stance == "BULLISH" and bearish_candidate:
            contradicts.append("BEARISH_RSI_DIVERGENCE_CANDIDATE_AGAINST_STRUCTURE")
        if stance == "BEARISH" and bullish_candidate:
            contradicts.append("BULLISH_RSI_DIVERGENCE_CANDIDATE_AGAINST_STRUCTURE")

    return supports, contradicts


# ── Participation axis (volume based -- a genuinely separate provider field) ──────────────────

def participation_state(participation_record: Mapping[str, Any] | None) -> str:
    """PARTICIPATION_EXPANDING / PARTICIPATION_CONTRACTING / PARTICIPATION_NEUTRAL / INSUFFICIENT_EVIDENCE."""
    record = participation_record or {}
    if record.get("acceleration_status") != "READY":
        return "INSUFFICIENT_EVIDENCE"
    ratio = record.get("volume_acceleration_ratio")
    if not isinstance(ratio, (int, float)):
        return "INSUFFICIENT_EVIDENCE"
    if ratio >= PARTICIPATION_EXPANSION_RATIO:
        return "PARTICIPATION_EXPANDING"
    if ratio <= PARTICIPATION_COMPRESSION_RATIO:
        return "PARTICIPATION_CONTRACTING"
    return "PARTICIPATION_NEUTRAL"


def price_volume_state(price_direction: str | None, participation: str) -> str:
    """PRICE_VOLUME_CONFIRMATION / PRICE_VOLUME_CONTRADICTION / NEUTRAL / INSUFFICIENT_EVIDENCE.

    Direction-agnostic by design: a price move in EITHER direction accompanied by expanding
    participation is "confirmed" (real participation behind the move); a move on contracting
    participation is "contradicted" (weak participation), regardless of which way price moved."""
    if price_direction not in ("UP", "DOWN") or participation == "INSUFFICIENT_EVIDENCE":
        return "INSUFFICIENT_EVIDENCE"
    if participation == "PARTICIPATION_EXPANDING":
        return "PRICE_VOLUME_CONFIRMATION"
    if participation == "PARTICIPATION_CONTRACTING":
        return "PRICE_VOLUME_CONTRADICTION"
    return "NEUTRAL"


def _participation_axis(
    stance: str, participation_record: Mapping[str, Any] | None, price_direction: str | None,
) -> tuple[list[str], list[str], dict[str, Any]]:
    supports: list[str] = []
    contradicts: list[str] = []
    p_state = participation_state(participation_record)
    pv_state = price_volume_state(price_direction, p_state)
    detail = {"participation_state": p_state, "price_volume_state": pv_state}
    if stance in ("BULLISH", "BEARISH"):
        if pv_state == "PRICE_VOLUME_CONFIRMATION":
            supports.append("PRICE_VOLUME_CONFIRMATION")
        elif pv_state == "PRICE_VOLUME_CONTRADICTION":
            contradicts.append("PRICE_VOLUME_CONTRADICTION")
    return supports, contradicts, detail


# ── Overall synthesis ──────────────────────────────────────────────────────────

def _overall_state(stance: str, supports: list[str], contradicts: list[str]) -> str:
    if stance == "INSUFFICIENT_EVIDENCE":
        return "INSUFFICIENT_EVIDENCE"
    if stance == "NEUTRAL":
        return "NEUTRAL"
    if supports and contradicts:
        return "PARTIALLY_CONFIRMED"
    if supports:
        return "CONFIRMED"
    if contradicts:
        return "CONTRADICTED"
    return "NEUTRAL"


def evaluate_ticker(
    *, structure_record: Mapping[str, Any] | None, momentum_record: Mapping[str, Any] | None,
    participation_record: Mapping[str, Any] | None,
) -> dict[str, Any]:
    stance, phase_label = structure_stance(structure_record)
    momentum_record = momentum_record or {}
    momentum_supports, momentum_contradicts = _momentum_axis(stance, momentum_record)
    price_direction = momentum_record.get("price_direction_1d")
    participation_supports, participation_contradicts, participation_detail = _participation_axis(
        stance, participation_record, price_direction,
    )
    supports = momentum_supports + participation_supports
    contradicts = momentum_contradicts + participation_contradicts
    state = _overall_state(stance, supports, contradicts)
    return {
        "structure_stance": stance,
        "structure_phase_label": phase_label,
        "tactical_confirmation_state": state,
        "supporting_reasons": supports,
        "contradicting_reasons": contradicts,
        "momentum_direction": _combined_momentum_direction(momentum_record.get("rsi") or {}, momentum_record.get("macd") or {}),
        "participation_detail": participation_detail,
        "price_direction_1d": price_direction,
        "authority_boundary": _AUTHORITY_BOUNDARY,
    }


# ── Public build_artifact ─────────────────────────────────────────────────────

def build_artifact(
    *, structure_projection: Mapping[str, Any], momentum: Mapping[str, Any],
    participation: Mapping[str, Any], requested_at: str,
) -> dict[str, Any]:
    """Join structure + momentum + participation for every ticker in the structure projection.
    Zero silent drops: every candidate gets a record."""
    session = structure_projection.get("session")
    if not session:
        raise TacticalConfirmationContextError("SESSION_MISSING")
    if momentum.get("target_session") is not None and momentum.get("target_session") != session:
        raise TacticalConfirmationContextError("MOMENTUM_SESSION_MISMATCH")

    structure_records = structure_projection.get("records") or {}
    momentum_records = momentum.get("records") or {}
    participation_records = participation.get("records") or {}

    records: dict[str, dict[str, Any]] = {}
    for ticker in sorted(structure_records):
        records[ticker] = evaluate_ticker(
            structure_record=structure_records.get(ticker),
            momentum_record=momentum_records.get(ticker),
            participation_record=participation_records.get(ticker),
        )

    from collections import Counter
    state_counts = Counter(record["tactical_confirmation_state"] for record in records.values())
    stance_counts = Counter(record["structure_stance"] for record in records.values())

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "milestone": MILESTONE,
        "requested_at": requested_at, "session": session,
        "source_artifacts": {
            "structure_projection": structure_projection.get("artifact_identity"),
            "momentum": momentum.get("artifact_identity"),
            "participation": participation.get("artifact_identity"),
        },
        "coverage": {
            "candidate_count": len(records),
            "tactical_confirmation_state_counts": dict(sorted(state_counts.items())),
            "structure_stance_counts": dict(sorted(stance_counts.items())),
        },
        "authority_boundary": _AUTHORITY_BOUNDARY,
        "records": records,
    }
    identity = content_identity(artifact)
    artifact["artifact_sha256"], artifact["artifact_identity"] = identity["artifact_sha256"], identity["artifact_identity"]
    return artifact
