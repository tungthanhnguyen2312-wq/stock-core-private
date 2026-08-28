"""Research-only opportunity matrix over retained fundamental and current-market artifacts.

This module deliberately produces buckets rather than a universal investment score.  It keeps
security quality, current market structure, tactical state, valuation, and data confidence in
separate fields.  In particular, valuation is optional enrichment and confidence never changes a
quality or market classification.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent
CONTRACT_VERSION = "fundamental_plus_market_opportunity_ranking/v1"
FUNDAMENTAL_INPUT = ROOT / "operations-review" / "fundamental-cross-sectional-scoring-and-ranking-v1-20260828" / "artifact.json"
MARKET_INPUT = ROOT / "operations-review" / "market-wide-current-descriptive-research-v1-20260825" / "market_wide_current_descriptive_research_artifact.json"
TACTICAL_INPUT = ROOT / "operations-review" / "watchlist-tactical-entry-decision-v1-20260825" / "watchlist_tactical_entry_classifier_artifact.json"
VALUATION_INPUT = ROOT / "operations-review" / "current-valuation-research-proxy-and-relative-value-axis-v1-20260828" / "artifact.json"

FUNDAMENTAL_QUALITY_AXES = (
    "PROFITABILITY_QUALITY",
    "CAPITAL_EFFICIENCY",
    "BALANCE_SHEET_TRAJECTORY",
)
HIGH_QUALITY_THRESHOLD = 0.75
STRONG_SETUP_STATES = frozenset({"BREAKOUT_READY", "UPTREND_CONFIRMED"})
WEAK_SETUP_STATES = frozenset({"DISTRIBUTION_RISK", "BREAKDOWN_RISK", "DOWNTREND"})
SUPER_SETUP_CONSTRUCTIVE_STATES = frozenset({"BREAKOUT_READY", "EARLY_REVERSAL_CANDIDATE"})
CONSTRUCTIVE_SETUP_STATES = frozenset({"BREAKOUT_READY", "EARLY_REVERSAL_CANDIDATE", "UPTREND_CONFIRMED", "BASE_BUILDING"})
SUPER_SETUP_PERCENTILE_FLOOR = 0.80
HIGH_RISK_SPECULATION_PERCENTILE_CEILING = 0.25


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"fundamental_plus_market_opportunity_ranking:{digest}"}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fundamental_quality(record: Mapping[str, Any]) -> dict[str, Any]:
    axes = record.get("axes") or {}
    available = [
        (axis, axes[axis].get("score"))
        for axis in FUNDAMENTAL_QUALITY_AXES
        if axes.get(axis, {}).get("axis_status") == "READY_RESEARCH_ONLY"
        and isinstance(axes[axis].get("score"), (int, float))
    ]
    if not available:
        return {
            "status": "INSUFFICIENT_INPUTS", "rank": None, "quality_band": None,
            "axes_used": [], "axes_missing": list(FUNDAMENTAL_QUALITY_AXES),
            "method": "AVAILABLE_FUNDAMENTAL_AXIS_MEAN/v1", "warnings": ["MISSING_NOT_NEUTRAL"],
        }
    score = sum(value for _, value in available) / len(available)
    used = {axis for axis, _ in available}
    return {
        "status": "READY_RESEARCH_ONLY", "rank": score,
        "quality_band": "HIGH_QUALITY" if score >= HIGH_QUALITY_THRESHOLD else "LOWER_QUALITY",
        "axes_used": [axis for axis, _ in available],
        "axes_missing": [axis for axis in FUNDAMENTAL_QUALITY_AXES if axis not in used],
        "method": "AVAILABLE_FUNDAMENTAL_AXIS_MEAN/v1",
        "warnings": ["GROWTH_MOMENTUM_OPTIONAL_NOT_USED_IN_QUALITY_RANK"],
    }


def _market_strength(market: Mapping[str, Any] | None, tactical: Mapping[str, Any] | None, session: str | None) -> dict[str, Any]:
    technical = (market or {}).get("technical_features") or {}
    eligible = (
        technical.get("status") == "SHADOW_ONLY"
        and technical.get("is_current_session") is True
        and technical.get("feature_as_of_session") == session
        and bool(tactical)
        and tactical.get("entry_state") is not None
    )
    if not eligible:
        return {
            "status": "INSUFFICIENT_INPUTS", "market_technical_rank": None,
            "trend_state": (market or {}).get("trend_state"), "momentum_20d": None,
            "method": "RETAINED_CURRENT_SESSION_TACTICAL_STATE/v1", "warnings": ["CURRENT_SESSION_TECHNICAL_OR_TACTICAL_INPUT_UNAVAILABLE"],
        }
    entry_state = tactical["entry_state"]
    if entry_state in STRONG_SETUP_STATES:
        rank = "STRONG"
    elif entry_state == "BASE_BUILDING":
        rank = "BASE_BUILDING"
    elif entry_state == "EARLY_REVERSAL_CANDIDATE":
        rank = "EARLY_REVERSAL"
    elif entry_state in WEAK_SETUP_STATES:
        rank = "WEAK"
    else:
        rank = "NEUTRAL_OR_UNCONFIRMED"
    values = technical.get("values") or {}
    return {
        "status": "READY_RESEARCH_ONLY", "market_technical_rank": rank,
        "trend_state": (market or {}).get("trend_state"), "momentum_20d": values.get("momentum_20d"),
        "method": "RETAINED_CURRENT_SESSION_TACTICAL_STATE/v1", "warnings": list(technical.get("warnings") or []),
    }


def _valuation(valuation: Mapping[str, Any] | None, market_session: str | None) -> dict[str, Any]:
    relative = (valuation or {}).get("relative_value_axis") or {}
    ready = relative.get("axis_status") == "READY_RESEARCH_ONLY" and isinstance(relative.get("score"), (int, float))
    price_session = (valuation or {}).get("price_session")
    warnings: list[str] = []
    if ready and price_session != market_session:
        warnings.append("VALUATION_SESSION_DIFFERS_FROM_MARKET_SESSION_OPTIONAL_ENRICHMENT_ONLY")
    return {
        "status": "READY_RESEARCH_ONLY" if ready else "INSUFFICIENT_INPUTS",
        "relative_value_rank": relative.get("score") if ready else None,
        "price_session": price_session,
        "metrics": (valuation or {}).get("metrics") or {},
        "size_context": {
            "market_cap": (valuation or {}).get("market_cap_size_context"),
            "enterprise_value": (valuation or {}).get("enterprise_value_size_context"),
        },
        "method": relative.get("method"), "warnings": warnings + list((valuation or {}).get("warnings") or []),
    }


def _cohort_percentile(values: list[float], value: float) -> float | None:
    """Inclusive empirical percentile within the actual valid corporate-quality cohort."""
    return sum(candidate <= value for candidate in values) / len(values) if values else None


def _research_classifications(*, entity_class: str, quality: Mapping[str, Any], tactical_state: str | None,
                              cohort_size: int) -> dict[str, dict[str, Any]]:
    percentile = quality.get("actual_comparable_cohort_percentile")
    basis = quality.get("ranking_basis")
    eligible = entity_class == "corporate" and isinstance(percentile, (int, float)) and tactical_state is not None
    common = {
        "ranking_basis": basis,
        "comparable_cohort_size": cohort_size,
        "fundamental_quality_percentile": percentile,
        "tactical_state": tactical_state,
    }
    if not eligible:
        unavailable = {**common, "status": "INSUFFICIENT_INPUTS", "reason": "CORPORATE_COMPARABLE_QUALITY_OR_CURRENT_TACTICAL_STATE_UNAVAILABLE"}
        return {"SUPER_SETUP_RESEARCH": unavailable, "HIGH_RISK_SPECULATION": dict(unavailable)}
    super_setup = tactical_state in SUPER_SETUP_CONSTRUCTIVE_STATES and percentile >= SUPER_SETUP_PERCENTILE_FLOOR
    high_risk = tactical_state in CONSTRUCTIVE_SETUP_STATES and percentile <= HIGH_RISK_SPECULATION_PERCENTILE_CEILING
    return {
        "SUPER_SETUP_RESEARCH": {
            **common, "status": "PRESENT" if super_setup else "NOT_PRESENT",
            "technical_requirement": "BREAKOUT_READY_OR_EARLY_REVERSAL_CANDIDATE",
            "fundamental_requirement": "TOP_20_PERCENT_OF_ACTUAL_COMPARABLE_COHORT",
            "research_only": True,
        },
        "HIGH_RISK_SPECULATION": {
            **common, "status": "RESEARCH_WARNING" if high_risk else "NOT_PRESENT",
            "technical_requirement": "EXISTING_CONSTRUCTIVE_TACTICAL_STATE",
            "fundamental_requirement": "BOTTOM_25_PERCENT_OF_ACTUAL_COMPARABLE_COHORT",
            "research_only": True, "portfolio_action": "NOT_EMITTED",
        },
    }


def _bucket(quality: Mapping[str, Any], market: Mapping[str, Any], tactical_state: str | None) -> tuple[str, list[str]]:
    quality_band = quality.get("quality_band")
    market_rank = market.get("market_technical_rank")
    lanes: list[str] = []
    if market_rank == "EARLY_REVERSAL":
        if quality.get("status") == "READY_RESEARCH_ONLY":
            lanes.append("EARLY_REVERSAL")
        return "EARLY_REVERSAL_RESEARCH", lanes
    if quality_band == "HIGH_QUALITY" and market_rank == "STRONG":
        lanes.append("QUALITY_MOMENTUM")
        return "HIGH_QUALITY_STRONG_SETUP", lanes
    if quality_band == "HIGH_QUALITY" and market_rank == "BASE_BUILDING":
        lanes.append("QUALITY_BASE_BUILDING")
        return "HIGH_QUALITY_BASE_BUILDING", lanes
    if quality_band == "HIGH_QUALITY" and market_rank == "WEAK":
        return "HIGH_QUALITY_WEAK_SETUP", lanes
    if quality_band == "LOWER_QUALITY" and market_rank == "STRONG":
        return "LOWER_QUALITY_STRONG_SETUP", lanes
    if quality.get("status") != "READY_RESEARCH_ONLY":
        return "INSUFFICIENT_FUNDAMENTAL_DATA", lanes
    if market.get("status") != "READY_RESEARCH_ONLY":
        return "FUNDAMENTAL_ONLY_RESEARCH", lanes
    return "FUNDAMENTAL_AND_MARKET_RESEARCH", lanes


def build_artifact(*, fundamental: Mapping[str, Any], market: Mapping[str, Any], tactical: Mapping[str, Any], valuation: Mapping[str, Any]) -> dict[str, Any]:
    """Build the full fundamental-market research matrix from retained source artifacts."""
    fundamental_records = fundamental.get("records") or {}
    market_records = market.get("records") or {}
    tactical_records = tactical.get("records") or {}
    valuation_records = valuation.get("records") or {}
    market_session = market.get("session")
    if tactical.get("session") != market_session:
        raise ValueError("MARKET_TACTICAL_SESSION_MISMATCH")

    quality_by_ticker = {ticker: _fundamental_quality(record) for ticker, record in fundamental_records.items()}
    comparable_values = sorted(
        quality["rank"] for ticker, quality in quality_by_ticker.items()
        if fundamental_records[ticker].get("entity_class") == "corporate"
        and quality.get("status") == "READY_RESEARCH_ONLY"
        and isinstance(quality.get("rank"), (int, float))
    )
    ranking_basis = "CORPORATE_VALID_FUNDAMENTAL_QUALITY_COHORT_EMPIRICAL_PERCENTILE/v1"
    for ticker, quality in quality_by_ticker.items():
        if fundamental_records[ticker].get("entity_class") == "corporate" and isinstance(quality.get("rank"), (int, float)):
            quality["actual_comparable_cohort_percentile"] = _cohort_percentile(comparable_values, quality["rank"])
            quality["ranking_basis"] = ranking_basis
            quality["actual_comparable_cohort_size"] = len(comparable_values)
        else:
            quality["actual_comparable_cohort_percentile"] = None
            quality["ranking_basis"] = "NOT_APPLICABLE_NON_CORPORATE_OR_INSUFFICIENT_FUNDAMENTAL_QUALITY"
            quality["actual_comparable_cohort_size"] = len(comparable_values)

    records: dict[str, dict[str, Any]] = {}
    coverage: Counter[str] = Counter()
    entity_classes: Counter[str] = Counter()
    sector_exclusions: Counter[str] = Counter()
    for ticker in sorted(fundamental_records):
        fundamental_record = fundamental_records[ticker]
        market_record = market_records.get(ticker)
        tactical_record = tactical_records.get(ticker)
        quality = quality_by_ticker[ticker]
        technical = _market_strength(market_record, tactical_record, market_session)
        tactical_state = (tactical_record or {}).get("entry_state")
        relative_value = _valuation(valuation_records.get(ticker), market_session)
        entity_class = fundamental_record.get("entity_class", "unknown")
        bucket, lanes = _bucket(quality, technical, tactical_state)
        classifications = _research_classifications(
            entity_class=entity_class, quality=quality, tactical_state=tactical_state, cohort_size=len(comparable_values),
        )
        if relative_value["status"] == "READY_RESEARCH_ONLY" and technical["market_technical_rank"] == "STRONG":
            lanes.append("VALUE_WITH_CONFIRMATION")
        missing = [name for name, candidate in (
            ("FUNDAMENTAL_QUALITY", quality), ("MARKET_TECHNICAL_STRENGTH", technical), ("TACTICAL_SETUP", {"status": "READY_RESEARCH_ONLY" if tactical_state else "INSUFFICIENT_INPUTS"}),
            ("RELATIVE_VALUE", relative_value), ("DATA_CONFIDENCE", fundamental_record.get("data_confidence") or {}),
        ) if candidate.get("status") != "READY_RESEARCH_ONLY"]
        warnings = list(quality["warnings"]) + list(technical["warnings"]) + list(relative_value["warnings"])
        if entity_class != "corporate":
            sector_exclusions[entity_class] += 1
            warnings.append("CORPORATE_FUNDAMENTAL_COMPARISON_NOT_APPLICABLE")
        record = {
            "ticker": ticker, "entity_class": entity_class, "sector": entity_class,
            "market_session": market_session,
            "fundamental_axes": fundamental_record.get("axes") or {},
            "fundamental_quality": quality,
            "market_technical_strength": technical,
            "tactical_setup": {
                "status": "READY_RESEARCH_ONLY" if tactical_state else "INSUFFICIENT_INPUTS",
                "state": tactical_state, "ticker_structure_state": (tactical_record or {}).get("ticker_structure_state"),
                "rule_id": (tactical_record or {}).get("rule_id"),
                "method": "watchlist_tactical_entry_classifier/v1 state only; actions excluded",
            },
            "relative_value": relative_value,
            "data_confidence": fundamental_record.get("data_confidence") or {"status": "INSUFFICIENT_INPUTS", "score": None},
            "research_classifications": classifications,
            "opportunity_lanes": lanes,
            "opportunity_research_priority": {"status": "BUCKET_ONLY", "bucket": bucket, "global_score": None, "method": "PARETO_STYLE_SEPARATE_DIMENSIONS_NO_GLOBAL_COMPOSITE/v1"},
            "warnings": sorted(set(warnings)), "missing_dimensions": missing,
        }
        records[ticker] = record
        coverage["fundamental_eligible"] += quality["status"] == "READY_RESEARCH_ONLY"
        coverage["market_technical_eligible"] += technical["status"] == "READY_RESEARCH_ONLY"
        coverage["fundamental_market_overlap"] += quality["status"] == "READY_RESEARCH_ONLY" and technical["status"] == "READY_RESEARCH_ONLY"
        coverage[bucket] += 1
        coverage["valuation_enriched"] += relative_value["status"] == "READY_RESEARCH_ONLY"
        coverage["missing_valuation_but_otherwise_eligible"] += relative_value["status"] != "READY_RESEARCH_ONLY" and quality["status"] == "READY_RESEARCH_ONLY" and technical["status"] == "READY_RESEARCH_ONLY"
        coverage["SUPER_SETUP_RESEARCH"] += classifications["SUPER_SETUP_RESEARCH"]["status"] == "PRESENT"
        coverage["HIGH_RISK_SPECULATION"] += classifications["HIGH_RISK_SPECULATION"]["status"] == "RESEARCH_WARNING"
        entity_classes[entity_class] += 1

    for bucket in (
        "HIGH_QUALITY_STRONG_SETUP", "HIGH_QUALITY_BASE_BUILDING", "HIGH_QUALITY_WEAK_SETUP",
        "LOWER_QUALITY_STRONG_SETUP", "EARLY_REVERSAL_RESEARCH", "INSUFFICIENT_FUNDAMENTAL_DATA",
    ):
        coverage.setdefault(bucket, 0)
    artifact: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION, "denominator": len(records), "residual": 0,
        "source_artifacts": {
            "fundamental": fundamental.get("artifact_sha256"), "market": market.get("artifact_identity"),
            "tactical": tactical.get("artifact_identity"), "valuation": valuation.get("artifact_sha256"),
        },
        "session_coherence": {
            "market_session": market_session, "tactical_session": tactical.get("session"),
            "market_tactical_exact_session_match": True,
            "valuation_session_handling": "OPTIONAL_ENRICHMENT_LABELLED_PER_RECORD_AND_EXCLUDED_FROM_CORE_BUCKET",
        },
        "coverage": {**dict(sorted(coverage.items())), "entity_classes": dict(sorted(entity_classes.items())), "sector_exclusions": dict(sorted(sector_exclusions.items()))},
        "research_priority_method": "PARETO_STYLE_SEPARATE_DIMENSIONS_NO_GLOBAL_COMPOSITE/v1",
        "classification_contract": {
            "ranking_basis": ranking_basis, "actual_comparable_cohort_size": len(comparable_values),
            "super_setup": "BREAKOUT_READY_OR_EARLY_REVERSAL_CANDIDATE_AND_TOP_20_PERCENT",
            "high_risk_speculation": "CONSTRUCTIVE_TACTICAL_STATE_AND_BOTTOM_25_PERCENT_WARNING_ONLY",
            "sector_relative_ranking": "NOT_EMITTED_NO_SUFFICIENT_RETAINED_SECTOR_PEER_COHORT",
        },
        "authority_boundary": {
            "research_only": True, "action_authority": False, "target_or_return_or_probability": False,
            "position_sizing": False, "pit": False, "new_evidence_acquired": False,
            "authoritative_counts_before": 13, "authoritative_counts_after": 13,
            "valuation_optional_enrichment_only": True, "market_cap_or_ev_is_relative_value": False,
        },
        "records": records,
    }
    artifact.update(_identity(artifact))
    return artifact


def execute() -> dict[str, Any]:
    return build_artifact(fundamental=_load(FUNDAMENTAL_INPUT), market=_load(MARKET_INPUT), tactical=_load(TACTICAL_INPUT), valuation=_load(VALUATION_INPUT))
