"""Coverage-aware, current-session screening and relative-comparison consumer.

This module deliberately emits independent descriptive flags.  It neither ranks
instruments nor combines flags into an opportunity score or recommendation.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from statistics import median
from typing import Any, Mapping


CONTRACT_VERSION = "current_market_screening_and_opportunity_comparison_foundation/v1"
SOURCE_CONTRACT = "market_wide_current_descriptive_research/v1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return {
        "artifact_sha256": digest,
        "artifact_identity": f"current_market_screening_opportunity_comparison_foundation:{digest}",
    }


def _verify_source_identity(source: Mapping[str, Any]) -> None:
    payload = {key: value for key, value in source.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    if source.get("artifact_sha256") != digest:
        raise ValueError("CURRENT_DESCRIPTIVE_ARTIFACT_IDENTITY_MISMATCH")
    if source.get("artifact_identity") != f"market_wide_current_descriptive_research:{digest}":
        raise ValueError("CURRENT_DESCRIPTIVE_ARTIFACT_IDENTITY_MISMATCH")


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _position(values: Mapping[str, float], value: float) -> tuple[float, str]:
    """Return a tie-aware descriptive percentile, not an ordinal rank."""
    ordered = sorted(values.values())
    less = sum(item < value for item in ordered)
    equal = sum(item == value for item in ordered)
    percentile = (less + (equal + 1) / 2) / len(ordered)
    if percentile >= 0.75:
        return percentile, "UPPER_QUARTILE"
    if percentile >= 0.5:
        return percentile, "UPPER_MIDDLE"
    if percentile >= 0.25:
        return percentile, "LOWER_MIDDLE"
    return percentile, "LOWER_QUARTILE"


def _coverage(*, denominator: int, observed: int, eligible: int, session: str, source_identity: str,
              quality_state: str) -> dict[str, Any]:
    return {
        "current_descriptive_denominator": denominator,
        "observed_session_cohort": observed,
        "eligible_count": eligible,
        "coverage_ratio": _ratio(eligible, denominator),
        "session": session,
        "source_artifact_identity": source_identity,
        "quality_state": quality_state,
    }


def _technical_eligible(record: Mapping[str, Any]) -> bool:
    technical = record.get("technical_features", {})
    return technical.get("status") == "SHADOW_ONLY" and technical.get("is_current_session") is True


def _unavailable_technical_reason(record: Mapping[str, Any]) -> str:
    technical = record.get("technical_features", {})
    if technical.get("status") == "SHADOW_ONLY":
        return "STALE_TECHNICAL_FEATURE_NOT_CURRENT_SESSION"
    if record.get("activity_and_session_state") == "ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION":
        return "SESSION_MISSING_TECHNICAL_FEATURE_UNAVAILABLE"
    return "TECHNICAL_FEATURE_UNAVAILABLE"


def _sector_positions(source: Mapping[str, Any]) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    positions: dict[str, Mapping[str, Any]] = {}
    sector_by_ticker: dict[str, Mapping[str, Any]] = {}
    for sector_key, sector in source.get("sector_breadth", {}).get("sectors", {}).items():
        if sector.get("status") != "AVAILABLE":
            continue
        for position in sector.get("member_relative_positions", []):
            ticker = position.get("ticker")
            if ticker:
                positions[str(ticker)] = position
                sector_by_ticker[str(ticker)] = {"sector_key": sector_key, **sector}
    return positions, sector_by_ticker


def build_artifact(source: Mapping[str, Any]) -> dict[str, Any]:
    """Build the deterministic current-session comparison artifact from one retained source artifact."""
    _verify_source_identity(source)
    if source.get("contract_version") != SOURCE_CONTRACT:
        raise ValueError("CURRENT_DESCRIPTIVE_CONTRACT_VERSION_UNSUPPORTED")
    records = source.get("records")
    coverage_input = source.get("validation", {}).get("coverage", {})
    if not isinstance(records, Mapping):
        raise ValueError("CURRENT_DESCRIPTIVE_RECORDS_INVALID")
    denominator = int(coverage_input.get("current_active_equity_denominator", 0))
    observed = int(coverage_input.get("observed_session_cohort", 0))
    if denominator <= 0 or observed <= 0:
        raise ValueError("CURRENT_DESCRIPTIVE_COVERAGE_INVALID")
    session = str(source.get("session"))
    source_identity = str(source["artifact_identity"])
    in_scope = {ticker: record for ticker, record in records.items() if record.get("in_current_descriptive_scope")}
    if len(in_scope) != denominator:
        raise ValueError("CURRENT_DESCRIPTIVE_DENOMINATOR_MISMATCH")
    technical = {ticker: record for ticker, record in in_scope.items() if _technical_eligible(record)}
    liquidity = {ticker: record for ticker, record in in_scope.items() if record.get("liquidity", {}).get("status") == "ELIGIBLE"}
    technical_liquidity = set(technical) & set(liquidity)
    positions, sector_by_ticker = _sector_positions(source)
    sector_eligible = set(technical) & set(positions)

    momentum = {ticker: float(record["technical_features"]["values"]["momentum_20d"]) for ticker, record in technical.items()}
    relative_volume = {
        ticker: float(record["technical_features"]["values"]["relative_volume_provider_scoped"])
        for ticker, record in technical.items()
    }
    momentum_median = median(momentum.values())
    relative_volume_median = median(relative_volume.values())
    common_quality = "PARTIAL_COVERAGE_EXPLICIT_CURRENT_SESSION_ONLY"

    screen_definitions = {
        "TREND_AND_POSITIVE_MOMENTUM": {
            "predicate": "trend_state == ABOVE_MA20 AND momentum_20d > 0",
            "eligible_intersection": "same-session technical features only",
            "independent_flag": True,
            "not_a_recommendation_or_score": True,
        },
        "MOMENTUM_ABOVE_COHORT_MEDIAN": {
            "predicate": "momentum_20d > median(momentum_20d among same-session technical eligible records)",
            "eligible_intersection": "same-session technical features only",
            "independent_flag": True,
            "not_an_ordinal_market_ranking": True,
        },
        "RELATIVE_VOLUME_ABOVE_COHORT_MEDIAN": {
            "predicate": "relative_volume_provider_scoped > median(relative_volume_provider_scoped among same-session technical eligible records)",
            "eligible_intersection": "same-session technical features only",
            "provider_scoped_not_liquidity_authority": True,
            "independent_flag": True,
        },
        "TECHNICAL_AND_CURRENT_DESCRIPTIVE_LIQUIDITY": {
            "predicate": "same-session technical eligibility AND CURRENT_SESSION_LIQUIDITY_RESEARCH == ELIGIBLE",
            "eligible_intersection": "same-session technical features intersect current descriptive liquidity",
            "independent_flag": True,
            "does_not_compute_value_turnover_adv_adtv_or_execution": True,
        },
    }
    screen_coverage = {
        "TREND_AND_POSITIVE_MOMENTUM": _coverage(denominator=denominator, observed=observed, eligible=len(technical),
                                                   session=session, source_identity=source_identity, quality_state=common_quality),
        "MOMENTUM_ABOVE_COHORT_MEDIAN": _coverage(denominator=denominator, observed=observed, eligible=len(technical),
                                                    session=session, source_identity=source_identity, quality_state=common_quality),
        "RELATIVE_VOLUME_ABOVE_COHORT_MEDIAN": _coverage(denominator=denominator, observed=observed, eligible=len(technical),
                                                            session=session, source_identity=source_identity, quality_state=common_quality),
        "TECHNICAL_AND_CURRENT_DESCRIPTIVE_LIQUIDITY": _coverage(
            denominator=denominator, observed=observed, eligible=len(technical_liquidity), session=session,
            source_identity=source_identity, quality_state=common_quality,
        ),
    }
    members: dict[str, Any] = {}
    counts: Counter[str] = Counter()
    for ticker in sorted(records):
        record = records[ticker]
        technical_ok = ticker in technical
        liquidity_ok = ticker in liquidity
        row: dict[str, Any] = {
            "ticker": ticker,
            "coverage_context": _coverage(denominator=denominator, observed=observed, eligible=denominator, session=session,
                                             source_identity=source_identity, quality_state=common_quality),
            "screen_membership": {},
            "market_relative_comparison": {},
            "sector_relative_comparison": {},
            "liquidity_context": {},
        }
        if technical_ok:
            momentum_value = momentum[ticker]
            volume_value = relative_volume[ticker]
            momentum_percentile, momentum_bucket = _position(momentum, momentum_value)
            volume_percentile, volume_bucket = _position(relative_volume, volume_value)
            row["screen_membership"].update({
                "TREND_AND_POSITIVE_MOMENTUM": {"status": "ELIGIBLE", "member": record.get("trend_state") == "ABOVE_MA20" and momentum_value > 0},
                "MOMENTUM_ABOVE_COHORT_MEDIAN": {"status": "ELIGIBLE", "member": momentum_value > momentum_median},
                "RELATIVE_VOLUME_ABOVE_COHORT_MEDIAN": {"status": "ELIGIBLE", "member": volume_value > relative_volume_median},
            })
            row["market_relative_comparison"] = {
                "status": "AVAILABLE",
                "momentum_20d": momentum_value,
                "momentum_percentile_descriptive": momentum_percentile,
                "momentum_bucket": momentum_bucket,
                "momentum_cohort_median": momentum_median,
                "relative_volume_provider_scoped": volume_value,
                "relative_volume_percentile_descriptive": volume_percentile,
                "relative_volume_bucket": volume_bucket,
                "relative_volume_cohort_median": relative_volume_median,
                "coverage": screen_coverage["MOMENTUM_ABOVE_COHORT_MEDIAN"],
                "authority": "CURRENT_DESCRIPTIVE_SHADOW_ONLY_NOT_ORDINAL_RANKING",
            }
        else:
            reason = _unavailable_technical_reason(record)
            for screen in ("TREND_AND_POSITIVE_MOMENTUM", "MOMENTUM_ABOVE_COHORT_MEDIAN", "RELATIVE_VOLUME_ABOVE_COHORT_MEDIAN"):
                row["screen_membership"][screen] = {"status": "UNAVAILABLE", "reason": reason, "member": None}
            row["market_relative_comparison"] = {"status": "UNAVAILABLE", "reason": reason,
                                                   "coverage": screen_coverage["MOMENTUM_ABOVE_COHORT_MEDIAN"]}
        if technical_ok and liquidity_ok:
            row["screen_membership"]["TECHNICAL_AND_CURRENT_DESCRIPTIVE_LIQUIDITY"] = {"status": "ELIGIBLE", "member": True}
        else:
            reason = _unavailable_technical_reason(record) if not technical_ok else str(record["liquidity"].get("reason", "LIQUIDITY_UNAVAILABLE"))
            row["screen_membership"]["TECHNICAL_AND_CURRENT_DESCRIPTIVE_LIQUIDITY"] = {"status": "UNAVAILABLE", "reason": reason, "member": None}
        for screen, membership in row["screen_membership"].items():
            membership["coverage"] = screen_coverage[screen]

        if ticker in sector_eligible:
            source_position = positions[ticker]
            sector = sector_by_ticker[ticker]
            row["sector_relative_comparison"] = {
                "status": "AVAILABLE",
                "sector_key": sector["sector_key"],
                "classification_label": sector.get("classification_label"),
                "momentum_20d": source_position["momentum_20d"],
                "momentum_percentile_descriptive": source_position["percentile"],
                "momentum_bucket": source_position["descriptive_bucket"],
                "sector_median_momentum_20d": sector.get("median_momentum_20d"),
                "coverage": _coverage(denominator=denominator, observed=observed, eligible=len(sector_eligible),
                                         session=session, source_identity=source_identity, quality_state=common_quality),
                "authority": "RETAINED_PROVIDER_DESCRIPTIVE_SECTOR_CONTEXT_NOT_RANKING",
            }
        else:
            classification = record.get("sector_classification", {})
            if not technical_ok:
                reason = _unavailable_technical_reason(record)
            elif classification.get("classification_authority") != "PROVIDER_DESCRIPTIVE_CLASSIFICATION":
                reason = "SECTOR_IDENTITY_UNAVAILABLE_OR_UNSUPPORTED"
            else:
                reason = "SECTOR_RELATIVE_COVERAGE_INSUFFICIENT"
            row["sector_relative_comparison"] = {
                "status": "UNAVAILABLE", "reason": reason,
                "coverage": _coverage(denominator=denominator, observed=observed, eligible=len(sector_eligible),
                                         session=session, source_identity=source_identity, quality_state=common_quality),
            }
        if liquidity_ok:
            liquidity_record = record["liquidity"]
            reconciliation = liquidity_record.get("g1_v_reconciliation", {})
            row["liquidity_context"] = {
                "status": "ELIGIBLE",
                "session": liquidity_record.get("session"),
                "board_composition": liquidity_record.get("board_composition"),
                "g1_v_reconciliation_verdict": reconciliation.get("verdict"),
                "g1_v_reconciliation_warning": reconciliation if reconciliation.get("exact_match") is False else None,
                "value_status": liquidity_record.get("value_status"),
                "coverage": _coverage(denominator=denominator, observed=observed, eligible=len(liquidity),
                                         session=session, source_identity=source_identity, quality_state=common_quality),
                "authority": "CURRENT_SESSION_DESCRIPTIVE_ONLY_GROSS_TRADE_AMOUNT_NON_AUTHORITATIVE",
            }
        else:
            row["liquidity_context"] = {
                "status": "UNAVAILABLE", "reason": record.get("liquidity", {}).get("reason", "LIQUIDITY_UNAVAILABLE"),
                "coverage": _coverage(denominator=denominator, observed=observed, eligible=len(liquidity),
                                         session=session, source_identity=source_identity, quality_state=common_quality),
            }
        for screen, membership in row["screen_membership"].items():
            if membership.get("member") is True:
                counts[screen] += 1
        members[ticker] = row

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "session": session,
        "input_lineage": {"current_descriptive_artifact_identity": source_identity, **source.get("validation", {}).get("lineage", {})},
        "coverage_disclosure": {
            "denominator": denominator,
            "observed_session_cohort": observed,
            "same_session_technical_feature_count": len(technical),
            "current_descriptive_liquidity_eligible_count": len(liquidity),
            "technical_and_liquidity_intersection_count": len(technical_liquidity),
            "sector_relative_eligible_count": len(sector_eligible),
            "quality_state": common_quality,
            "missing_is_not_zero": True,
        },
        "screen_definitions": screen_definitions,
        "screen_coverage": screen_coverage,
        "screen_membership_counts": {screen: counts[screen] for screen in sorted(screen_definitions)},
        "market_relative_comparison": {
            "status": "AVAILABLE_FOR_SAME_SESSION_TECHNICAL_ELIGIBLE_RECORDS_ONLY",
            "coverage": screen_coverage["MOMENTUM_ABOVE_COHORT_MEDIAN"],
            "momentum_20d_cohort_median": momentum_median,
            "relative_volume_provider_scoped_cohort_median": relative_volume_median,
            "ordinal_ranking": "NOT_EMITTED",
        },
        "sector_relative_comparison": {
            "status": "PARTIAL_AVAILABLE_FAILS_CLOSED_WHERE_SECTOR_IDENTITY_OR_COVERAGE_INSUFFICIENT",
            "coverage": _coverage(denominator=denominator, observed=observed, eligible=len(sector_eligible), session=session,
                                     source_identity=source_identity, quality_state=common_quality),
            "available_sector_count": source.get("sector_breadth", {}).get("sector_count_available"),
            "insufficient_sector_count": source.get("sector_breadth", {}).get("sector_count_insufficient_coverage"),
        },
        "quality_warnings": source.get("liquidity_features", {}).get("reconciliation_warnings", []),
        "blocked_outputs": {
            "ordinal_market_ranking": "RANKING_PROHIBITED",
            "opportunity_score": "SCORING_PROHIBITED",
            "buy_sell_recommendation": "RECOMMENDATION_PROHIBITED",
            "target_price_expected_return_or_probability": "FORECAST_PROHIBITED",
            "portfolio_weight_position_size_or_execution": "SIZING_EXECUTION_PROHIBITED",
            "traded_value_turnover_adv_adtv": "GROSS_TRADE_AMOUNT_NON_AUTHORITATIVE_SCALE_BASIS_UNRESOLVED",
            "raw_as_traded_pit_or_backtest": "NOT_PROMOTED_OR_OUT_OF_SCOPE",
        },
        "authority_boundary": {
            "technical_features": "CURRENT_DESCRIPTIVE_SHADOW_ONLY_PROVIDER_SCOPED",
            "relative_volume": "PROVIDER_SCOPED_PROXY_NOT_LIQUIDITY_AUTHORITY",
            "current_session_liquidity": "DESCRIPTIVE_ONLY",
            "gross_trade_amount": "NON_AUTHORITATIVE_SCALE_BASIS_UNRESOLVED",
            "screen_flags": "INDEPENDENT_DESCRIPTIVE_FLAGS_NOT_SCORE_OR_RECOMMENDATION",
        },
        "records": members,
    }
    return {**artifact, **content_identity(artifact)}
