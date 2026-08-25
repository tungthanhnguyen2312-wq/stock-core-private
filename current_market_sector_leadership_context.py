"""Current-session official-universe breadth and sector participation context.

This is a deterministic read-only projection of the retained current descriptive, screening, and
official-universe artifacts.  It never recalculates technical features, changes a strategy/queue,
or emits a score or ordinal market ranking.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter, defaultdict
from statistics import median
from typing import Any, Mapping

import current_official_market_universe as official_universe_module
from current_market_screening_opportunity_comparison_foundation import content_identity as screening_content_identity
from market_wide_current_descriptive_research import content_identity as descriptive_content_identity
from sector_relative_research_context import MIN_COHORT_MEMBERS, _bucket


CONTRACT_VERSION = "current_market_sector_leadership_context/v1"
CURRENT_BREADTH_THRESHOLD = 0.60
OFFICIAL_CURRENT_STATUSES = frozenset({
    official_universe_module.OFFICIAL_CURRENT_EXCHANGE_SECURITY,
    official_universe_module.OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE,
})


class CurrentMarketSectorLeadershipContextError(ValueError):
    """A retained input did not meet this context's exact current-session contract."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact))
    payload.pop("artifact_sha256", None)
    payload.pop("artifact_identity", None)
    digest = hashlib.sha256(_canonical(payload)).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"current_market_sector_leadership_context:{digest}"}


def _verify_descriptive(artifact: Mapping[str, Any]) -> None:
    if artifact.get("contract_version") != "market_wide_current_descriptive_research/v1":
        raise CurrentMarketSectorLeadershipContextError("CURRENT_DESCRIPTIVE_CONTRACT_UNSUPPORTED")
    if artifact.get("artifact_sha256") != descriptive_content_identity(artifact)["artifact_sha256"]:
        raise CurrentMarketSectorLeadershipContextError("CURRENT_DESCRIPTIVE_IDENTITY_MISMATCH")


def _verify_screening(artifact: Mapping[str, Any], descriptive: Mapping[str, Any]) -> None:
    if artifact.get("contract_version") != "current_market_screening_and_opportunity_comparison_foundation/v1":
        raise CurrentMarketSectorLeadershipContextError("CURRENT_SCREENING_CONTRACT_UNSUPPORTED")
    if artifact.get("artifact_sha256") != screening_content_identity(artifact)["artifact_sha256"]:
        raise CurrentMarketSectorLeadershipContextError("CURRENT_SCREENING_IDENTITY_MISMATCH")
    if artifact.get("session") != descriptive.get("session"):
        raise CurrentMarketSectorLeadershipContextError("SCREENING_SESSION_MISMATCH")
    if artifact.get("input_lineage", {}).get("current_descriptive_artifact_identity") != descriptive.get("artifact_identity"):
        raise CurrentMarketSectorLeadershipContextError("SCREENING_DESCRIPTIVE_LINEAGE_MISMATCH")


def _verify_official_universe(artifact: Mapping[str, Any]) -> None:
    try:
        official_universe_module._verify(artifact, "CURRENT_OFFICIAL_MARKET_UNIVERSE")
    except Exception as exc:
        raise CurrentMarketSectorLeadershipContextError("CURRENT_OFFICIAL_UNIVERSE_IDENTITY_MISMATCH") from exc


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _percentile(values: list[float], value: float) -> float:
    below = sum(item < value for item in values)
    equal = sum(item == value for item in values)
    return (below + .5 * equal) / len(values)


def _classification_key(record: Mapping[str, Any]) -> tuple[str, str, str] | None:
    classification = record.get("sector_classification")
    if not isinstance(classification, Mapping):
        return None
    label = classification.get("entity_class") or classification.get("safe_normalized_label")
    if not isinstance(label, str) or not label:
        return None
    return (
        str(classification.get("classification_authority", "QUALIFIED_CLASSIFICATION")),
        str(classification.get("classification_namespace", "QUALIFIED_ENTITY_CLASS")),
        label,
    )


def _current_technical(record: Mapping[str, Any]) -> dict[str, Any] | None:
    technical = record.get("technical_features")
    values = technical.get("values") if isinstance(technical, Mapping) else None
    if not (
        isinstance(technical, Mapping)
        and technical.get("status") == "SHADOW_ONLY"
        and technical.get("is_current_session") is True
        and isinstance(values, Mapping)
        and isinstance(values.get("return_1d"), (int, float))
        and not isinstance(values.get("return_1d"), bool)
        and isinstance(values.get("momentum_20d"), (int, float))
        and not isinstance(values.get("momentum_20d"), bool)
        and record.get("trend_state") in {"ABOVE_MA20", "AT_OR_BELOW_MA20"}
    ):
        return None
    return {
        "return_1d": float(values["return_1d"]),
        "momentum_20d": float(values["momentum_20d"]),
        "trend_state": record["trend_state"],
    }


def _breadth_state(*, advance_ratio: float | None, decline_ratio: float | None,
                   positive_momentum_ratio: float | None, negative_momentum_ratio: float | None,
                   trend_above_ratio: float | None, trend_below_ratio: float | None,
                   observed: int) -> tuple[str, dict[str, Any]]:
    inputs = {
        "advance_ratio": advance_ratio, "decline_ratio": decline_ratio,
        "positive_momentum_ratio": positive_momentum_ratio, "negative_momentum_ratio": negative_momentum_ratio,
        "trend_above_ma20_ratio": trend_above_ratio, "trend_at_or_below_ma20_ratio": trend_below_ratio,
        "threshold": CURRENT_BREADTH_THRESHOLD,
    }
    if observed < MIN_COHORT_MEMBERS:
        return "DATA_LIMITED", {"rule": "OBSERVED_EXACT_SESSION_COUNT_BELOW_MINIMUM", **inputs}
    if advance_ratio >= CURRENT_BREADTH_THRESHOLD and positive_momentum_ratio >= CURRENT_BREADTH_THRESHOLD and trend_above_ratio >= CURRENT_BREADTH_THRESHOLD:
        return "BROAD_PARTICIPATION", {"rule": "ADVANCE_POSITIVE_MOMENTUM_AND_ABOVE_MA20_ALL_AT_OR_ABOVE_THRESHOLD", **inputs}
    if decline_ratio >= CURRENT_BREADTH_THRESHOLD and negative_momentum_ratio >= CURRENT_BREADTH_THRESHOLD and trend_below_ratio >= CURRENT_BREADTH_THRESHOLD:
        return "DETERIORATING_BREADTH", {"rule": "DECLINE_NEGATIVE_MOMENTUM_AND_AT_OR_BELOW_MA20_ALL_AT_OR_ABOVE_THRESHOLD", **inputs}
    if advance_ratio > decline_ratio and advance_ratio >= .50:
        return "NARROW_LEADERSHIP", {"rule": "ADVANCERS_EXCEED_DECLINERS_BUT_BROAD_PARTICIPATION_THRESHOLD_NOT_MET", **inputs}
    return "MIXED_BREADTH", {"rule": "NO_BROAD_OR_DETERIORATING_OR_NARROW_PARTICIPATION_RULE_MET", **inputs}


def _summarize_members(members: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    observed = len(members)
    returns = [facts["return_1d"] for _, facts in members]
    momentum = [facts["momentum_20d"] for _, facts in members]
    advancing = sum(value > 0 for value in returns)
    declining = sum(value < 0 for value in returns)
    positive_momentum = sum(value > 0 for value in momentum)
    negative_momentum = sum(value < 0 for value in momentum)
    above = sum(facts["trend_state"] == "ABOVE_MA20" for _, facts in members)
    below = sum(facts["trend_state"] == "AT_OR_BELOW_MA20" for _, facts in members)
    return {
        "exact_session_observed_count": observed,
        "advancing": advancing, "declining": declining, "unchanged": observed - advancing - declining,
        "advance_ratio": _ratio(advancing, observed), "decline_ratio": _ratio(declining, observed),
        "positive_momentum_count": positive_momentum, "positive_momentum_ratio": _ratio(positive_momentum, observed),
        "negative_momentum_count": negative_momentum, "negative_momentum_ratio": _ratio(negative_momentum, observed),
        "trend_participation": {
            "above_ma20_count": above, "above_ma20_ratio": _ratio(above, observed),
            "at_or_below_ma20_count": below, "at_or_below_ma20_ratio": _ratio(below, observed),
        },
        "median_momentum_20d": median(momentum) if momentum else None,
    }


def _group_state(summary: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    trend = summary["trend_participation"]
    return _breadth_state(
        advance_ratio=summary["advance_ratio"], decline_ratio=summary["decline_ratio"],
        positive_momentum_ratio=summary["positive_momentum_ratio"], negative_momentum_ratio=summary["negative_momentum_ratio"],
        trend_above_ratio=trend["above_ma20_ratio"], trend_below_ratio=trend["at_or_below_ma20_ratio"],
        observed=summary["exact_session_observed_count"],
    )


def _leadership_state(summary: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Express the transparent breadth result in sector-leadership vocabulary.

    The underlying ratios and rule remain intact.  ``IMPROVING`` is deliberately unavailable:
    this contract has one exact session, not a prior comparable leadership observation.
    """
    breadth_state, rule = _group_state(summary)
    mapping = {
        "BROAD_PARTICIPATION": "LEADING",
        "NARROW_LEADERSHIP": "LEADING",
        "MIXED_BREADTH": "MIXED",
        "DETERIORATING_BREADTH": "WEAKENING",
        "DATA_LIMITED": "DATA_LIMITED",
    }
    return mapping[breadth_state], {
        **rule,
        "breadth_state": breadth_state,
        "leadership_vocabulary_note": "IMPROVING_AND_LAGGING_REQUIRE_A_PRIOR_COMPARABLE_SESSION_AND_ARE_NOT_EMITTED",
    }


def build_artifact(*, current_descriptive: Mapping[str, Any], current_screening: Mapping[str, Any],
                   current_official_universe: Mapping[str, Any]) -> dict[str, Any]:
    """Create the smallest transparent current-session leadership projection.

    Official-master membership is current reference context, not a daily session input.  The
    session-bound technical/relative evidence is verified solely against the supplied descriptive
    and screening siblings, which must identify the exact same source artifact.
    """
    _verify_descriptive(current_descriptive)
    _verify_screening(current_screening, current_descriptive)
    _verify_official_universe(current_official_universe)
    records = current_descriptive.get("records")
    screening_records = current_screening.get("records")
    official_records = current_official_universe.get("records")
    if not isinstance(records, Mapping) or not isinstance(screening_records, Mapping) or not isinstance(official_records, Mapping):
        raise CurrentMarketSectorLeadershipContextError("INPUT_RECORDS_INVALID")
    if set(records) != set(screening_records):
        raise CurrentMarketSectorLeadershipContextError("SCREENING_TICKER_SET_MISMATCH")

    official_tickers = sorted(
        ticker for ticker, row in official_records.items()
        if isinstance(row, Mapping) and row.get("stocklookup_candidate") is True
        and row.get("current_universe_status") in OFFICIAL_CURRENT_STATUSES
    )
    if not official_tickers or any(ticker not in records for ticker in official_tickers):
        raise CurrentMarketSectorLeadershipContextError("OFFICIAL_TICKER_NOT_IN_CURRENT_DESCRIPTIVE_RECORDS")
    expected_official = current_official_universe.get("reconciliation", {}).get("official_total_match")
    if expected_official != len(official_tickers):
        raise CurrentMarketSectorLeadershipContextError("OFFICIAL_UNIVERSE_DENOMINATOR_MISMATCH")

    current_rows: dict[str, dict[str, Any]] = {}
    groups: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    unknown_sector: list[str] = []
    for ticker in official_tickers:
        technical = _current_technical(records[ticker])
        if technical is not None:
            current_rows[ticker] = technical
        key = _classification_key(records[ticker])
        if key is None:
            unknown_sector.append(ticker)
        else:
            groups[key].append(ticker)

    market_summary = _summarize_members(sorted(current_rows.items()))
    market_state, market_rule = _group_state(market_summary)
    market = {
        "session": current_descriptive["session"],
        "official_universe_count": len(official_tickers),
        "exact_session_observed_count": market_summary.pop("exact_session_observed_count"),
        "missing_current_session_count": len(official_tickers) - len(current_rows),
        "breadth_coverage_ratio": _ratio(len(current_rows), len(official_tickers)),
        **market_summary,
        "current_breadth_state": market_state,
        "breadth_state_rule": market_rule,
        "warnings": [
            "CURRENT_SESSION_DESCRIPTIVE_ONLY",
            "MISSING_CURRENT_SESSION_BARS_ARE_COVERAGE_GAPS_NOT_UNCHANGED_OR_ZERO_RETURNS",
            "NO_PRIOR_SESSION_COMPARISON_SO_IMPROVING_BREADTH_IS_NOT_EMITTED",
        ],
    }

    group_rows: dict[str, dict[str, Any]] = {}
    sector_positions: dict[str, dict[str, Any]] = {}
    for key, members in sorted(groups.items()):
        authority, namespace, label = key
        observed_members = [(ticker, current_rows[ticker]) for ticker in sorted(members) if ticker in current_rows]
        group_key = "|".join(key)
        base = {
            "group_key": group_key, "group_identity": label, "classification_authority": authority,
            "classification_namespace": namespace, "group_scope": (
                "PROVIDER_DESCRIPTIVE_INDUSTRY" if authority == "PROVIDER_DESCRIPTIVE_CLASSIFICATION" else "QUALIFIED_ENTITY_CLASS"
            ),
            "universe_member_count": len(members), "exact_session_observed_count": len(observed_members),
            "missing_current_session_count": len(members) - len(observed_members),
            "coverage_ratio": _ratio(len(observed_members), len(members)),
            "minimum_member_requirement": MIN_COHORT_MEMBERS,
        }
        if len(observed_members) < MIN_COHORT_MEMBERS:
            group_rows[group_key] = {
                **base, "status": "DATA_LIMITED", "leadership_state": "DATA_LIMITED",
                "relative_strength_distribution": {
                    "status": "UNAVAILABLE", "reason": "EXACT_SESSION_OBSERVED_MEMBERS_BELOW_MINIMUM",
                    "valid_observation_count": len(observed_members),
                },
                "warnings": ["EXACT_SESSION_OBSERVED_MEMBERS_BELOW_MINIMUM", "MISSING_MEMBERS_NOT_TREATED_AS_UNCHANGED_OR_ZERO"],
            }
            continue
        summary = _summarize_members(observed_members)
        state, rule = _leadership_state(summary)
        momentum_values = [facts["momentum_20d"] for _, facts in observed_members]
        distribution = Counter()
        for ticker, facts in observed_members:
            percentile = _percentile(momentum_values, facts["momentum_20d"])
            bucket = _bucket(percentile)
            distribution[bucket] += 1
            sector_positions[ticker] = {
                "status": "AVAILABLE", "momentum_20d": facts["momentum_20d"],
                "momentum_percentile_descriptive": percentile, "momentum_bucket": bucket,
                "peer_median_momentum_20d": summary["median_momentum_20d"], "valid_observation_count": len(observed_members),
            }
        group_rows[group_key] = {
            **base, "status": "AVAILABLE", **summary, "leadership_state": state,
            "leadership_rule": rule,
            "relative_strength_distribution": {
                "metric": "momentum_20d", "method": "tie_aware_percentile_within_current_exact_session_group",
                "bucket_counts": dict(sorted(distribution.items())), "valid_observation_count": len(observed_members),
            },
            "warnings": ["CURRENT_CROSS_SECTIONAL_ONLY_NOT_HISTORICAL_PIT_RELATIVE_STRENGTH"],
        }

    ticker_rows: dict[str, dict[str, Any]] = {}
    market_momentum_values = [facts["momentum_20d"] for facts in current_rows.values()]
    for ticker in official_tickers:
        record = records[ticker]
        technical = current_rows.get(ticker)
        key = _classification_key(record)
        group_key = "|".join(key) if key is not None else None
        group = group_rows.get(group_key) if group_key else None
        if technical is None:
            ticker_rows[ticker] = {
                "ticker": ticker, "status": "DATA_LIMITED", "coverage_limitations": ["NO_CURRENT_EXACT_SESSION_TECHNICAL_CONTEXT"],
                "market_relative_momentum": {"status": "UNAVAILABLE", "reason": "NO_CURRENT_EXACT_SESSION_TECHNICAL_CONTEXT"},
                "sector_relative_momentum": {"status": "UNAVAILABLE", "reason": "NO_CURRENT_EXACT_SESSION_TECHNICAL_CONTEXT"},
                "breadth_support_state": "DATA_LIMITED", "sector_leadership_context": {"status": "UNAVAILABLE", "reason": "NO_CURRENT_EXACT_SESSION_TECHNICAL_CONTEXT"},
            }
            continue
        market_percentile = _percentile(market_momentum_values, technical["momentum_20d"])
        market_relative = {
            "status": "AVAILABLE", "momentum_20d": technical["momentum_20d"],
            "momentum_percentile_descriptive": market_percentile, "momentum_bucket": _bucket(market_percentile),
            "peer_median_momentum_20d": market["median_momentum_20d"], "valid_observation_count": len(current_rows),
            "authority": "CURRENT_CROSS_SECTIONAL_DESCRIPTIVE_NOT_ORDINAL_RANKING",
        }
        if key is None:
            sector_relative = {"status": "UNAVAILABLE", "reason": "SECTOR_IDENTITY_UNKNOWN"}
            sector_context = {"status": "UNAVAILABLE", "reason": "SECTOR_IDENTITY_UNKNOWN"}
        elif group is None or group["status"] != "AVAILABLE":
            sector_relative = {"status": "UNAVAILABLE", "reason": "SECTOR_EXACT_SESSION_COVERAGE_DATA_LIMITED"}
            sector_context = {"status": "DATA_LIMITED", "group_key": group_key}
        else:
            sector_relative = sector_positions[ticker]
            sector_context = {"status": "AVAILABLE", "group_key": group_key, "leadership_state": group["leadership_state"],
                              "group_coverage_ratio": group["coverage_ratio"]}
        if market_state == "BROAD_PARTICIPATION" and sector_context.get("leadership_state") == "LEADING":
            support = "MARKET_AND_GROUP_BREADTH_SUPPORT"
        elif sector_context.get("leadership_state") == "LEADING":
            support = "GROUP_ONLY_SUPPORT_MARKET_NOT_BROAD"
        elif market_state == "BROAD_PARTICIPATION":
            support = "MARKET_ONLY_SUPPORT_GROUP_NOT_BROAD"
        elif sector_context["status"] != "AVAILABLE":
            support = "DATA_LIMITED"
        else:
            support = "ISOLATED_OR_MIXED_PARTICIPATION"
        ticker_rows[ticker] = {
            "ticker": ticker, "status": "AVAILABLE" if sector_context["status"] == "AVAILABLE" else "PARTIAL",
            "market_relative_momentum": market_relative,
            "market_trend_participation_context": {"ticker_trend_state": technical["trend_state"], "market_above_ma20_ratio": market["trend_participation"]["above_ma20_ratio"]},
            "sector_relative_momentum": sector_relative,
            "sector_trend_participation_context": None if group is None or group.get("status") != "AVAILABLE" else {"ticker_trend_state": technical["trend_state"], "group_above_ma20_ratio": group["trend_participation"]["above_ma20_ratio"]},
            "breadth_support_state": support, "sector_leadership_context": sector_context,
            "coverage_limitations": [] if sector_context["status"] == "AVAILABLE" else [sector_context.get("reason", "SECTOR_CONTEXT_DATA_LIMITED")],
        }

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "session": current_descriptive["session"],
        "research_mode": "CURRENT_SESSION_DESCRIPTIVE_MARKET_AND_SECTOR_CONTEXT",
        "input_lineage": {
            "current_descriptive_artifact_identity": current_descriptive["artifact_identity"],
            "current_screening_artifact_identity": current_screening["artifact_identity"],
            "current_official_universe_artifact_identity": current_official_universe["artifact_identity"],
            "technical_session": current_descriptive["session"],
            "official_universe_scope": "CURRENT_EXCHANGE_MASTER_MEMBERSHIP_NOT_HISTORICAL_OR_PIT",
        },
        "market": market,
        "groups": {"group_count": len(group_rows), "available_group_count": sum(row["status"] == "AVAILABLE" for row in group_rows.values()),
                   "data_limited_group_count": sum(row["status"] != "AVAILABLE" for row in group_rows.values()), "records": dict(sorted(group_rows.items()))},
        "ticker_contexts": ticker_rows,
        "coverage": {
            "official_universe_count": len(official_tickers), "exact_session_observed_count": len(current_rows),
            "missing_current_session_count": len(official_tickers) - len(current_rows),
            "unknown_sector_identity_count": len(unknown_sector),
            "ticker_sector_context_available_count": sum(row["sector_leadership_context"]["status"] == "AVAILABLE" for row in ticker_rows.values()),
            "ticker_data_limited_count": sum(row["status"] == "DATA_LIMITED" for row in ticker_rows.values()),
        },
        "state_rules": {"threshold": CURRENT_BREADTH_THRESHOLD, "minimum_group_observed_members": MIN_COHORT_MEMBERS,
                        "rule_note": "Transparent independent breadth/momentum/trend ratios; no weighted composite or score."},
        "blocked_outputs": {
            "global_or_ticker_ranking_score": "NOT_EMITTED", "strategy_eligibility": "NOT_MODIFIED",
            "research_priority": "NOT_MODIFIED", "entry_action": "NOT_MODIFIED", "daily_decision_queue": "NOT_MODIFIED",
            "value_valuation_target_price": "NOT_EMITTED", "sizing_execution": "NOT_EMITTED",
            "raw_as_traded_pit_backtest": "NOT_EMITTED",
        },
        "authority_boundary": {
            "is_actionable": False, "current_research_only": True, "current_cross_sectional_relative_strength_not_historical_pit": True,
            "missing_current_session_bar_is_not_zero": True, "no_opaque_global_score": True,
            "no_strategy_priority_entry_or_sizing_mutation": True,
        },
    }
    artifact.update(content_identity(artifact))
    return artifact


def replay(artifact: Mapping[str, Any]) -> None:
    if artifact.get("contract_version") != CONTRACT_VERSION or artifact.get("artifact_sha256") != content_identity(artifact)["artifact_sha256"]:
        raise CurrentMarketSectorLeadershipContextError("ARTIFACT_IDENTITY_MISMATCH")
    market = artifact.get("market", {})
    coverage = artifact.get("coverage", {})
    if market.get("official_universe_count") != coverage.get("official_universe_count"):
        raise CurrentMarketSectorLeadershipContextError("OFFICIAL_DENOMINATOR_RECONCILIATION_FAILED")
    if market.get("exact_session_observed_count", 0) + market.get("missing_current_session_count", 0) != market.get("official_universe_count"):
        raise CurrentMarketSectorLeadershipContextError("CURRENT_SESSION_COVERAGE_RECONCILIATION_FAILED")
