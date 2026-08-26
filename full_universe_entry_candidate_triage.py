"""Deterministic full-universe entry-candidate triage over retained current-session inputs.

Recovers ``full_universe_entry_candidate_triage/v1`` from the governed 2026-08-24
post-close artifact, its cohort_definitions, and consumer contracts. It does not
rank, recommend, size, or invent investment semantics.
"""
from __future__ import annotations

import copy
from collections import Counter
from statistics import median
from typing import Any, Mapping

from field_temporal_contract import stable_id
from current_market_screening_opportunity_comparison_foundation import content_identity as screening_identity
from market_wide_current_descriptive_research import content_identity as descriptive_identity
from watchlist_tactical_entry_classifier import content_identity as tactical_identity

CONTRACT_VERSION = "full_universe_entry_candidate_triage/v1"
ARTIFACT_TYPE = "FULL_UNIVERSE_ENTRY_CANDIDATE_TRIAGE"
JOB = "FULL_UNIVERSE_ENTRY_CANDIDATE_TRIAGE_V1"
ENTRY_RELEVANT_STATES = ("BASE_BUILDING", "BREAKOUT_READY", "EARLY_REVERSAL_CANDIDATE")
WATCHLIST = ("EVF", "FPT", "HPG", "NVL", "PAN", "PNJ", "POW", "PVD", "QNS", "SSI", "VNM")
COHORT_DEFINITIONS = {
    "BREAKOUT_CONFIRMATION_REVIEW": "Existing BREAKOUT_READY state and its retained confirmation/invalidation fields; never full-position-ready.",
    "EARLY_REVERSAL_RETURN_VOLUME_CONFIRMING": "Existing positive return together with existing elevated provider-relative volume; not a confirmed bottom.",
    "TACTICAL_DATA_LIMITED": "Liquidity or sector context unavailable, or fundamental trajectory absent/unavailable.",
    "TACTICAL_HIGH_PRIORITY_REVIEW": "Entry-relevant state; liquidity ELIGIBLE; market momentum bucket not LOWER_QUARTILE; sector bucket not LOWER_QUARTILE when available; and no explicit tactical/fundamental conflict. Missing fundamental context is not an eligibility condition.",
    "TACTICAL_WEAK_RELATIVE_CONTEXT": "Market or available sector momentum bucket is LOWER_QUARTILE.",
    "TACTICAL_WITH_FUNDAMENTAL_SUPPORT": "Trajectory context exists and is not UNAVAILABLE; this is descriptive context, not a recommendation.",
}
DATA_WARNINGS = [
    "Fundamental trajectory is descriptive provider research only; not an official audit or calculation-grade rating.",
    "Tactical entry state is not execution timing, sizing authority, or an investment recommendation.",
    "Relative ranking buckets are contemporaneous cross-sectional percentiles, not a forecast model.",
    "Liquidity eligibility is descriptive provider-composition availability only; not ADV20 or position-sizing authority.",
]
LIMITATIONS = [
    "PROHIBITED_SIZING_OR_EXECUTION_AUTHORITY",
    "PROHIBITED_POINT_IN_TIME_BACKTEST_AUTHORITY",
    "PROHIBITED_BUY_SELL_RECOMMENDATIONS",
    "PROHIBITED_ABSOLUTE_VALUATION_PROMOTION",
]
EARNINGS_CONTRACTING = frozenset({"DECREASED", "CONTRACTING", "DETERIORATING", "NEGATIVE"})


class FullUniverseEntryCandidateTriageError(ValueError):
    """A required input or recovered triage invariant was violated."""


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact))
    payload.pop("artifact_sha256", None)
    payload.pop("artifact_identity", None)
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": "full_universe_entry_candidate_triage:" + digest}


def replay(artifact: Mapping[str, Any]) -> None:
    identity = content_identity(artifact)
    if artifact.get("artifact_sha256") != identity["artifact_sha256"]:
        raise FullUniverseEntryCandidateTriageError("TRIAGE_IDENTITY_MISMATCH")
    if artifact.get("artifact_identity") != identity["artifact_identity"]:
        raise FullUniverseEntryCandidateTriageError("TRIAGE_IDENTITY_MISMATCH")


def _verify(artifact: Mapping[str, Any], identity_fn, label: str) -> None:
    identity = identity_fn(artifact)
    if artifact.get("artifact_sha256") != identity.get("artifact_sha256"):
        raise FullUniverseEntryCandidateTriageError(label + "_IDENTITY_MISMATCH")


def _market_volatility_median(descriptive: Mapping[str, Any]) -> float | None:
    values = []
    for record in (descriptive.get("records") or {}).values():
        if not isinstance(record, Mapping):
            continue
        technical = record.get("technical_features") or {}
        if technical.get("status") != "SHADOW_ONLY" or technical.get("is_current_session") is not True:
            continue
        vol = (technical.get("values") or {}).get("volatility_20d")
        if isinstance(vol, (int, float)) and not isinstance(vol, bool):
            values.append(float(vol))
    return median(values) if values else None


def _return_volume_evidence(
    descriptive_row: Mapping[str, Any],
    market: Mapping[str, Any],
    vol_median: float | None,
) -> dict[str, Any]:
    values = ((descriptive_row.get("technical_features") or {}).get("values") or {})
    close = values.get("close")
    ma20 = values.get("ma_20")
    rvol = values.get("relative_volume_provider_scoped")
    vol = values.get("volatility_20d")
    cohort_median = market.get("relative_volume_cohort_median")
    elevated = False
    if isinstance(rvol, (int, float)) and not isinstance(rvol, bool) and isinstance(cohort_median, (int, float)) and not isinstance(cohort_median, bool):
        elevated = float(rvol) > float(cohort_median)
    distance = None
    if isinstance(close, (int, float)) and not isinstance(close, bool) and isinstance(ma20, (int, float)) and not isinstance(ma20, bool) and ma20 != 0:
        distance = (float(close) - float(ma20)) / float(ma20)
    regime = None
    if isinstance(vol, (int, float)) and not isinstance(vol, bool) and vol_median is not None:
        regime = "BELOW_MARKET_MEDIAN" if float(vol) < vol_median else "AT_OR_ABOVE_MARKET_MEDIAN"
    return {
        "elevated_volume_vs_cohort_median": elevated,
        "ma20_distance_pct": distance,
        "momentum_20d": values.get("momentum_20d"),
        "relative_volume_bucket": market.get("relative_volume_bucket"),
        "relative_volume_provider_scoped": rvol,
        "return_1d": values.get("return_1d"),
        "volatility_regime_vs_market_median": regime,
    }


def _market_context(market: Mapping[str, Any]) -> dict[str, Any]:
    status = market.get("status") or "UNAVAILABLE"
    return {
        "momentum_bucket": market.get("momentum_bucket") if status == "AVAILABLE" else None,
        "momentum_percentile_descriptive": None,
        "relative_volume_bucket": market.get("relative_volume_bucket") if status == "AVAILABLE" else None,
        "relative_volume_percentile_descriptive": None,
        "status": status,
    }


def _sector_context(sector: Mapping[str, Any], *, classification_label: str | None) -> dict[str, Any]:
    status = sector.get("status") or "UNAVAILABLE"
    return {
        "classification_label": classification_label,
        "momentum_bucket": sector.get("momentum_bucket") if status == "AVAILABLE" else None,
        "momentum_percentile_descriptive": None,
        "status": status,
    }


def _conflict_flags(state: str, trajectory: Mapping[str, Any] | None) -> list[str]:
    if not trajectory:
        return []
    flags = []
    if state == "BASE_BUILDING" and trajectory.get("earnings_direction") in EARNINGS_CONTRACTING:
        flags.append("BASE_BUILDING_WITH_EARNINGS_CONTRACTING")
    return flags


def _high_priority(liquidity: str | None, market: Mapping[str, Any], sector: Mapping[str, Any], flags: list[str]) -> tuple[bool, list[str], list[str]]:
    evidence: list[str] = []
    exclusions: list[str] = []
    if liquidity == "ELIGIBLE":
        evidence.append("CURRENT_SESSION_DESCRIPTIVE_LIQUIDITY_ELIGIBLE")
    else:
        evidence.append("LIQUIDITY_NOT_ELIGIBLE")
        exclusions.append("LIQUIDITY_NOT_ELIGIBLE")
    market_bucket = market.get("momentum_bucket") if market.get("status") == "AVAILABLE" else None
    if market_bucket == "LOWER_QUARTILE":
        evidence.append("MARKET_LOWER_QUARTILE")
        exclusions.append("MARKET_LOWER_QUARTILE")
    else:
        evidence.append("MARKET_RELATIVE_CONTEXT_NOT_LOWER_QUARTILE")
    sector_status = sector.get("status")
    sector_bucket = sector.get("momentum_bucket") if sector_status == "AVAILABLE" else None
    if sector_status == "AVAILABLE" and sector_bucket == "LOWER_QUARTILE":
        evidence.append("SECTOR_LOWER_QUARTILE")
        exclusions.append("SECTOR_LOWER_QUARTILE")
    else:
        evidence.append("SECTOR_RELATIVE_CONTEXT_NOT_LOWER_QUARTILE_OR_UNAVAILABLE")
    if flags:
        evidence.extend(flags)
        exclusions.extend(flags)
    else:
        evidence.append("NO_EXPLICIT_TACTICAL_FUNDAMENTAL_CONFLICT")
    return not exclusions, exclusions, evidence


def build(
    *,
    descriptive: Mapping[str, Any],
    screening: Mapping[str, Any],
    tactical: Mapping[str, Any],
    fundamental: Mapping[str, Any] | None = None,
    session: str | None = None,
) -> dict[str, Any]:
    _verify(descriptive, descriptive_identity, "DESCRIPTIVE")
    _verify(screening, screening_identity, "SCREENING")
    _verify(tactical, tactical_identity, "TACTICAL")
    target = session or tactical.get("session")
    if not target:
        raise FullUniverseEntryCandidateTriageError("TRIAGE_SESSION_REQUIRED")
    if descriptive.get("session") != target or screening.get("session") != target or tactical.get("session") != target:
        raise FullUniverseEntryCandidateTriageError("TRIAGE_SESSION_COHERENCE_MISMATCH")
    screening_lineage = (screening.get("input_lineage") or {}).get("current_descriptive_artifact_identity")
    if screening_lineage != descriptive.get("artifact_identity"):
        raise FullUniverseEntryCandidateTriageError("SCREENING_DESCRIPTIVE_LINEAGE_MISMATCH")
    tactical_sources = tactical.get("source_artifacts") or {}
    if tactical_sources.get("descriptive") != descriptive.get("artifact_identity") or tactical_sources.get("screening") != screening.get("artifact_identity"):
        raise FullUniverseEntryCandidateTriageError("TACTICAL_UPSTREAM_LINEAGE_MISMATCH")

    fund_records = (fundamental or {}).get("records") or {}
    d_records = descriptive.get("records") or {}
    s_records = screening.get("records") or {}
    t_records = tactical.get("records") or {}
    vol_median = _market_volatility_median(descriptive)

    grouped: dict[str, list[dict[str, Any]]] = {state: [] for state in ENTRY_RELEVANT_STATES}
    for ticker in sorted(t_records):
        tactical_row = t_records[ticker]
        if not isinstance(tactical_row, Mapping):
            continue
        state = tactical_row.get("entry_state")
        if state not in ENTRY_RELEVANT_STATES:
            continue
        screen_row = s_records.get(ticker) or {}
        desc_row = d_records.get(ticker) or {}
        fund_row = fund_records.get(ticker) if isinstance(fund_records.get(ticker), Mapping) else None
        market = screen_row.get("market_relative_comparison") or {}
        sector = screen_row.get("sector_relative_comparison") or {}
        trajectory = (fund_row or {}).get("fundamental_trajectory_context") if fund_row else None
        if trajectory is not None and not isinstance(trajectory, Mapping):
            trajectory = None
        quality = copy.deepcopy(tactical_row.get("data_quality") or {})
        liquidity = quality.get("liquidity_status")
        flags = _conflict_flags(state, trajectory)
        eligible, exclusions, evidence = _high_priority(liquidity, market, sector, flags)
        fund_available = fund_row is not None
        entity = (fund_row or {}).get("entity_class") if fund_available else "corporate"
        record = {
            "authority_data_quality_limitations": {
                "fundamental": "AVAILABLE" if fund_available else "UNAVAILABLE",
                "tactical": copy.deepcopy(quality),
            },
            "current_return_volume_evidence": _return_volume_evidence(desc_row, market, vol_median),
            "data_quality": quality,
            "entity_class": entity,
            "entry_action": tactical_row.get("entry_action"),
            "evidence_against": copy.deepcopy(tactical_row.get("evidence_against") or []),
            "evidence_for": copy.deepcopy(tactical_row.get("evidence_for") or []),
            "existing_confirmation_trigger": tactical_row.get("confirmation_trigger"),
            "existing_invalidation": tactical_row.get("invalidation"),
            "fundamental_authority_tier": (fund_row or {}).get("authority_tier") if fund_available else "NOT_IN_COHORT",
            "fundamental_limitations": list((trajectory or {}).get("data_limitations") or []) if trajectory else [],
            "fundamental_trajectory_context": copy.deepcopy(trajectory) if trajectory else None,
            "high_priority_exclusion_reasons": exclusions,
            "high_priority_review_eligible": eligible,
            "high_priority_rule_evidence": evidence,
            "horizon": tactical_row.get("horizon"),
            "liquidity_status": liquidity,
            "market_relative_context": _market_context(market),
            "sector_relative_context": _sector_context(sector, classification_label=entity if fund_available else None),
            "stock_state_language": state,
            "tactical_fundamental_conflict_flags": flags,
            "tactical_state": state,
            "ticker": ticker,
            "ticker_structure_state": tactical_row.get("ticker_structure_state"),
            "why_review_now": [f"TACTICAL_STATE:{state}"] + evidence,
        }
        grouped[state].append(record)

    all_rows = [row for state in ENTRY_RELEVANT_STATES for row in grouped[state]]
    high_priority = [row for row in all_rows if row["high_priority_review_eligible"]]
    high_priority.sort(key=lambda row: row["ticker"])
    state_counts = {state: len(grouped[state]) for state in ENTRY_RELEVANT_STATES}

    def _tickers(predicate) -> list[str]:
        return sorted(row["ticker"] for row in all_rows if predicate(row))

    cohorts = {
        "BREAKOUT_CONFIRMATION_REVIEW": _tickers(lambda row: row["tactical_state"] == "BREAKOUT_READY"),
        "EARLY_REVERSAL_RETURN_VOLUME_CONFIRMING": _tickers(
            lambda row: row["tactical_state"] == "EARLY_REVERSAL_CANDIDATE"
            and isinstance((row["current_return_volume_evidence"] or {}).get("return_1d"), (int, float))
            and row["current_return_volume_evidence"]["return_1d"] > 0
            and row["current_return_volume_evidence"].get("elevated_volume_vs_cohort_median") is True
        ),
        "TACTICAL_DATA_LIMITED": _tickers(
            lambda row: row["liquidity_status"] != "ELIGIBLE"
            or row["sector_relative_context"].get("status") != "AVAILABLE"
            or row["authority_data_quality_limitations"]["fundamental"] == "UNAVAILABLE"
        ),
        "TACTICAL_HIGH_PRIORITY_REVIEW": [row["ticker"] for row in high_priority],
        "TACTICAL_WEAK_RELATIVE_CONTEXT": _tickers(
            lambda row: row["market_relative_context"].get("momentum_bucket") == "LOWER_QUARTILE"
            or (
                row["sector_relative_context"].get("status") == "AVAILABLE"
                and row["sector_relative_context"].get("momentum_bucket") == "LOWER_QUARTILE"
            )
        ),
        "TACTICAL_WITH_FUNDAMENTAL_SUPPORT": _tickers(
            lambda row: isinstance(row.get("fundamental_trajectory_context"), Mapping)
            and int((row["fundamental_trajectory_context"] or {}).get("available_dimension_count") or 0) > 0
        ),
    }
    artifact = {
        "schema_version": "1.0.0",
        "job": JOB,
        "artifact_type": ARTIFACT_TYPE,
        "source_market_session": target,
        "preopen_research_date": target,
        "source_artifact_identities": {
            "descriptive": descriptive.get("artifact_identity"),
            "frozen_tactical": tactical.get("artifact_identity"),
            "screening": screening.get("artifact_identity"),
            "tactical_self_verified": True,
        },
        "all_entry_relevant_records": {state: grouped[state] for state in ENTRY_RELEVANT_STATES},
        "high_priority_review_eligible_records": high_priority,
        "preopen_review_set": copy.deepcopy(high_priority),
        "cohorts": cohorts,
        "cohort_counts": {name: len(tickers) for name, tickers in cohorts.items()},
        "cohort_definitions": dict(COHORT_DEFINITIONS),
        "coverage": {
            "entry_relevant_total": len(all_rows),
            "high_priority_review_count": len(high_priority),
            "state_counts": state_counts,
            "watchlist_size": len(WATCHLIST),
        },
        "data_warnings": list(DATA_WARNINGS),
        "limitations": list(LIMITATIONS),
    }
    artifact.update(content_identity(artifact))
    return artifact
