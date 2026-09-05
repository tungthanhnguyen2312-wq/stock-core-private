"""Market-wide current descriptive research: breadth, sector, cross-sectional, and liquidity.

Reuses the existing market-wide pipeline; creates no new feature store, digest, workbench,
packet, case, or orchestration abstraction:

- ``mva_daily_research_bundle.market_features()`` (unmodified import) for per-ticker technical
  features -- close, return_1d, momentum_20d, ma_3/5/20, volatility_20d, relative volume.
- ``market_regime_breadth_context._descriptor()`` (unmodified import) for the same 0.60-threshold
  breadth/momentum descriptor rule already used market-wide.
- ``sector_relative_research_context.MIN_COHORT_MEMBERS`` / ``_bucket()`` (unmodified import) for
  the same fail-closed minimum-cohort-size rule and percentile bucketing.
- ``market_wide_current_liquidity_research.content_identity()`` (unmodified import) to verify the
  retained liquidity artifact before attaching any of its records.
- The retained ``current_universe_status_and_session_coverage_resolution`` artifact (this
  project's own immediately preceding milestone) for the corrected 1,510
  ``current_active_equity_denominator`` / 960 ``observed_session_cohort`` split -- read, not
  rebuilt.
- The retained P3F9B exact-session snapshot for OHLC history -- re-read, never refetched.

A CRITICAL correctness point ``market_features()`` does not itself expose: it computes over
whatever chronological window it is handed, without asserting that the window's last row is the
*target* session. For a ``SESSION_MISSING`` ticker the window's last row is necessarily an
*earlier* session. This module labels every technical-feature result with the actual
``feature_as_of_session`` it was computed against and an explicit ``is_current_session`` flag, and
restricts same-session breadth/sector aggregation (advancing/declining, momentum descriptors) to
records where that flag is true -- otherwise a stale prior-session return could silently be
counted as "today's" breadth, exactly the "partial coverage masquerading as full-market breadth"
failure mode this milestone must avoid.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from statistics import median
from typing import Any, Mapping, Sequence

from field_temporal_contract import stable_id as _p3f9b_stable_id
from market_regime_breadth_context import _descriptor
from mva_daily_research_bundle import market_features
import market_wide_current_liquidity_research as liquidity_module
from sector_relative_research_context import MIN_COHORT_MEMBERS, _bucket
from technical_structure_context import resolve_target_session_observations

CONTRACT_VERSION = "market_wide_current_descriptive_research/v1"
LOOKBACK_SESSIONS = 20

IN_SCOPE_ACTIVITY_STATES = frozenset({"ACTIVE_LISTED_OBSERVED", "ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION"})
LIQUIDITY_ELIGIBLE_DISPOSITION = "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE"


# Proven structural insufficiency after the extended-history recovery attempt. Acquisition
# failures (FETCH_FAILED, MALFORMED_RESPONSE) and TARGET_SESSION_NOT_RECOVERED remain
# recoverable same-session gaps and must not be treated as lifetime insufficiency.
PROVEN_STRUCTURAL_TECHNICAL_INSUFFICIENCY_STATES = frozenset({
    "INSUFFICIENT_HISTORY_AFTER_EXTENDED_LOOKBACK",
})


def _assert_no_recoverable_same_session_technical_gap(
    records: Mapping[str, Mapping[str, Any]], snapshot_records: Mapping[str, Any],
    recovery_records: Mapping[str, Any] | None = None,
    close_mismatch_rejected: frozenset[str] = frozenset(),
) -> None:
    """Future sessions must not emit exact-session bars without same-session technicals unless
    unrecoverable. ``close_mismatch_rejected`` (see ``resolve_target_session_observations``) is
    unrecoverable for the identical reason ``INSUFFICIENT_HISTORY_AFTER_EXTENDED_LOOKBACK`` is: a
    genuine, correctly-enforced safety refusal, not a code defect this gate should ever flag."""
    unrecoverable = set(close_mismatch_rejected)
    if recovery_records:
        for ticker, rec in recovery_records.items():
            if isinstance(rec, Mapping) and rec.get("state") in PROVEN_STRUCTURAL_TECHNICAL_INSUFFICIENCY_STATES:
                unrecoverable.add(ticker)
    gaps = [
        ticker for ticker, record in records.items()
        if record.get("in_current_descriptive_scope")
        and (snapshot_records.get(ticker) or {}).get("disposition") == "EXACT_SESSION_RETAINED"
        and ticker not in unrecoverable
        and not (
            (record.get("technical_features") or {}).get("status") == "SHADOW_ONLY"
            and (record.get("technical_features") or {}).get("is_current_session") is True
        )
    ]
    if gaps:
        raise MarketWideCurrentDescriptiveResearchError(
            "RECOVERABLE_SAME_SESSION_TECHNICAL_HISTORY_GAP:" + ",".join(gaps[:20])
        )

BLOCKED_OUTPUTS = {
    "stock_rankings": "RANKING_PROHIBITED",
    "buy_sell_recommendations": "RECOMMENDATION_PROHIBITED",
    "probabilities_or_target_prices": "FORECAST_PROHIBITED",
    "portfolio_weights_or_position_sizes": "SIZING_EXECUTION_PROHIBITED",
    "historical_raw_as_traded_or_pit": "RAW_AS_TRADED_NOT_PROMOTED",
    "corporate_action_or_ex_date": "OUT_OF_SCOPE_THIS_MILESTONE",
    "backtesting": "OUT_OF_SCOPE_THIS_MILESTONE",
    "historical_membership_or_active_universe_promotion": "OUT_OF_SCOPE_THIS_MILESTONE",
    "traded_value_turnover_adv_adtv": "GROSS_TRADE_AMOUNT_NON_AUTHORITATIVE_SCALE_UNRESOLVED",
}


class MarketWideCurrentDescriptiveResearchError(ValueError):
    """A retained input or an invariant of this contract is violated."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    """Recompute this artifact's content hash from its own bytes, excluding the identity fields
    it carries itself. Mirrors market_wide_current_liquidity_research.content_identity() so a
    downstream consumer (export_ai_bundle.py) can verify a retained artifact reproduces its own
    recorded artifact_sha256 before attaching any of its records to a bundle."""
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = _hash(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"market_wide_current_descriptive_research:{digest}"}


def _verify_local_identity(artifact: Mapping[str, Any], *, hash_key: str, identity_key: str, label: str) -> None:
    if artifact.get(hash_key) != content_identity(artifact)["artifact_sha256"]:
        raise MarketWideCurrentDescriptiveResearchError(f"{label}_IDENTITY_MISMATCH")


def _verify_p3f9b_identity(snapshot: Mapping[str, Any]) -> None:
    payload = {key: value for key, value in snapshot.items() if key not in {"snapshot_sha256", "snapshot_identity"}}
    if snapshot.get("snapshot_sha256") != _p3f9b_stable_id(payload):
        raise MarketWideCurrentDescriptiveResearchError("P3F9B_SNAPSHOT_IDENTITY_MISMATCH")


def _verify_liquidity_identity(artifact: Mapping[str, Any]) -> None:
    identity = liquidity_module.content_identity(artifact)
    if artifact.get("artifact_sha256") != identity["artifact_sha256"]:
        raise MarketWideCurrentDescriptiveResearchError("LIQUIDITY_ARTIFACT_IDENTITY_MISMATCH")


def _feature_rows(pf_record: Mapping[str, Any]) -> list[dict[str, Any]]:
    observations = pf_record.get("observations")
    if not isinstance(observations, list):
        return []
    return [
        {"date": row.get("session"), "close": row.get("close"), "volume": row.get("volume")}
        for row in observations if isinstance(row, Mapping) and row.get("session")
    ]


def _technical_features(pf_record: Mapping[str, Any], *, target_session: str,
                        provenance: Mapping[str, Any] | None = None) -> dict[str, Any]:
    rows = _feature_rows(pf_record)
    result = market_features(rows)
    dates = sorted(str(row["date"]) for row in rows)
    latest = dates[-1] if dates else None
    return {
        **result,
        "feature_as_of_session": latest,
        "is_current_session": latest == target_session,
        "technical_history_provenance": dict(provenance or {"source": "RETAINED_P3F9B_EXACT_SESSION_SNAPSHOT"}),
    }


def _trend_state(values: Mapping[str, Any]) -> str | None:
    close, ma20 = values.get("close"), values.get("ma_20")
    if not isinstance(close, (int, float)) or not isinstance(ma20, (int, float)):
        return None
    return "ABOVE_MA20" if close > ma20 else "AT_OR_BELOW_MA20"


def _liquidity_view(ticker: str, liquidity_artifact: Mapping[str, Any]) -> dict[str, Any]:
    record = liquidity_artifact.get("records", {}).get(ticker)
    if not isinstance(record, Mapping):
        return {"status": "UNAVAILABLE", "reason": "NO_LIQUIDITY_RECORD"}
    if record.get("disposition") != LIQUIDITY_ELIGIBLE_DISPOSITION:
        return {"status": "UNAVAILABLE", "liquidity_disposition": record.get("disposition"), "reason": record.get("reason")}
    return {
        "status": "ELIGIBLE",
        "session": record.get("session"),
        "board_composition": record.get("board_composition"),
        "g1_v_reconciliation": record.get("g1_v_reconciliation"),
        "current_ohlc_v": record.get("current_ohlc_v"),
        "liquidity_research_contract": record.get("liquidity_research_contract"),
        "value_status": record.get("value_status"),
    }


def _classification_key(classification: Mapping[str, Any]) -> tuple[str, str, str | None]:
    return (
        str(classification.get("classification_authority", "QUALIFIED_CLASSIFICATION")),
        str(classification.get("classification_namespace", "QUALIFIED_ENTITY_CLASS")),
        classification.get("entity_class") or classification.get("safe_normalized_label"),
    )


def _same_session_momentum(records: Sequence[Mapping[str, Any]]) -> list[float]:
    return [
        record["technical_features"]["values"]["momentum_20d"]
        for record in records
        if record["technical_features"].get("status") == "SHADOW_ONLY" and record["technical_features"]["is_current_session"]
        and isinstance(record["technical_features"]["values"].get("momentum_20d"), (int, float))
    ]


def _sector_breadth(records: Sequence[Mapping[str, Any]], classifications: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str | None], list[dict[str, Any]]] = {}
    for record in records:
        classification = classifications.get(record["ticker"])
        if not classification:
            continue
        grouped.setdefault(_classification_key(classification), []).append(record)

    sectors: dict[str, dict[str, Any]] = {}
    for key, members in sorted(grouped.items()):
        authority, namespace, label = key
        same_session = [
            record for record in members
            if record["technical_features"].get("status") == "SHADOW_ONLY" and record["technical_features"]["is_current_session"]
        ]
        cohort_key = f"{authority}|{namespace}|{label}"
        total_members = len(members)
        eligible = len(same_session)
        if eligible < MIN_COHORT_MEMBERS:
            sectors[cohort_key] = {
                "classification_authority": authority, "classification_namespace": namespace, "classification_label": label,
                "total_classified_members": total_members, "same_session_eligible_count": eligible,
                "minimum_member_requirement": MIN_COHORT_MEMBERS, "status": "UNAVAILABLE_INSUFFICIENT_COVERAGE",
            }
            continue
        returns = [record["technical_features"]["values"]["return_1d"] for record in same_session]
        momentum = [record["technical_features"]["values"]["momentum_20d"] for record in same_session]
        advancing = sum(value > 0 for value in returns)
        declining = sum(value < 0 for value in returns)
        sorted_momentum = sorted(momentum)
        member_relative_positions = []
        for record in sorted(same_session, key=lambda item: item["ticker"]):
            value = record["technical_features"]["values"]["momentum_20d"]
            below = sum(item < value for item in sorted_momentum)
            equal = sum(item == value for item in sorted_momentum)
            percentile = (below + 0.5 * equal) / len(sorted_momentum)
            member_relative_positions.append({
                "ticker": record["ticker"], "momentum_20d": value, "percentile": percentile,
                "descriptive_bucket": _bucket(percentile),
            })
        sectors[cohort_key] = {
            "classification_authority": authority, "classification_namespace": namespace, "classification_label": label,
            "total_classified_members": total_members, "same_session_eligible_count": eligible,
            "coverage_ratio": eligible / total_members,
            "minimum_member_requirement": MIN_COHORT_MEMBERS, "status": "AVAILABLE",
            "advancing": advancing, "declining": declining, "unchanged": eligible - advancing - declining,
            "advance_ratio": advancing / eligible,
            "median_momentum_20d": median(momentum),
            "momentum_descriptor": _descriptor(sum(v > 0 for v in momentum), sum(v < 0 for v in momentum), len(momentum), prefix="SECTOR_MOMENTUM_BREADTH"),
            "member_tickers": sorted(record["ticker"] for record in same_session),
            "member_relative_positions": member_relative_positions,
        }
    available = sum(1 for sector in sectors.values() if sector["status"] == "AVAILABLE")
    return {
        "method": "reuses_sector_relative_research_context.MIN_COHORT_MEMBERS_and_market_regime_breadth_context._descriptor",
        "sector_count_total": len(sectors), "sector_count_available": available,
        "sector_count_insufficient_coverage": len(sectors) - available,
        "sectors": dict(sorted(sectors.items())),
    }


def build_artifact(
    *, universe_resolution_artifact: Mapping[str, Any], p3f9b_snapshot: Mapping[str, Any],
    liquidity_artifact: Mapping[str, Any], entity_classifications: Mapping[str, Mapping[str, Any]],
    technical_history_recovery_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    _verify_local_identity(universe_resolution_artifact, hash_key="artifact_sha256", identity_key="artifact_identity",
                           label="UNIVERSE_RESOLUTION_ARTIFACT")
    _verify_p3f9b_identity(p3f9b_snapshot)
    _verify_liquidity_identity(liquidity_artifact)

    ur_records = universe_resolution_artifact.get("records")
    pf_records = p3f9b_snapshot.get("records")
    liq_records = liquidity_artifact.get("records")
    if not isinstance(ur_records, Mapping) or not isinstance(pf_records, Mapping) or not isinstance(liq_records, Mapping):
        raise MarketWideCurrentDescriptiveResearchError("INPUT_RECORDS_INVALID")
    if not (set(ur_records) == set(pf_records) == set(liq_records)):
        raise MarketWideCurrentDescriptiveResearchError("CANDIDATE_DENOMINATOR_MISMATCH")

    target_session = p3f9b_snapshot.get("resolved_completed_session")
    if not target_session or target_session != universe_resolution_artifact.get("input_candidates", {}).get("resolved_completed_session"):
        raise MarketWideCurrentDescriptiveResearchError("SESSION_MISMATCH_BETWEEN_UNIVERSE_RESOLUTION_AND_P3F9B_SNAPSHOT")
    if liquidity_artifact.get("resolved_completed_session") != target_session:
        raise MarketWideCurrentDescriptiveResearchError("SESSION_MISMATCH_BETWEEN_LIQUIDITY_ARTIFACT_AND_P3F9B_SNAPSHOT")
    liquidity_snapshot_identity = liquidity_artifact.get("universe", {}).get("source_snapshot_identity")
    if liquidity_snapshot_identity != p3f9b_snapshot.get("snapshot_identity"):
        raise MarketWideCurrentDescriptiveResearchError("LIQUIDITY_ARTIFACT_SNAPSHOT_IDENTITY_MISMATCH")

    recovery_overrides: Mapping[str, Any] = {}
    recovery_identity = None
    if technical_history_recovery_artifact is not None:
        recovered_identity = content_identity(technical_history_recovery_artifact)
        if technical_history_recovery_artifact.get("artifact_sha256") != recovered_identity["artifact_sha256"]:
            raise MarketWideCurrentDescriptiveResearchError("TECHNICAL_HISTORY_RECOVERY_IDENTITY_MISMATCH")
        if technical_history_recovery_artifact.get("target_session") != target_session:
            raise MarketWideCurrentDescriptiveResearchError("TECHNICAL_HISTORY_RECOVERY_SESSION_MISMATCH")
        if technical_history_recovery_artifact.get("source_lineage", {}).get("p3f9b_snapshot_identity") != p3f9b_snapshot.get("snapshot_identity"):
            raise MarketWideCurrentDescriptiveResearchError("TECHNICAL_HISTORY_RECOVERY_SNAPSHOT_IDENTITY_MISMATCH")
        recovery_overrides = technical_history_recovery_artifact.get("recovered_history_overrides", {})
        if not isinstance(recovery_overrides, Mapping):
            raise MarketWideCurrentDescriptiveResearchError("TECHNICAL_HISTORY_RECOVERY_OVERRIDES_INVALID")
        recovery_identity = technical_history_recovery_artifact.get("artifact_identity")

    current_active_equity_denominator = universe_resolution_artifact["current_active_equity_denominator"]["count"]
    observed_session_cohort_count = universe_resolution_artifact["observed_session_cohort"]["count"]

    records: dict[str, dict[str, Any]] = {}
    close_mismatch_rejected: set[str] = set()
    for ticker in sorted(ur_records):
        ur = ur_records[ticker]
        activity_state = ur["activity_and_session_state"]
        in_scope = activity_state in IN_SCOPE_ACTIVITY_STATES

        if in_scope:
            # Same invariant technical_structure_context/tactical_momentum_context/
            # market_wide_relative_volume_research already enforce, via the identical shared
            # function: the recovery series is a single-provider (DNSE) fetch independent of the
            # multi-source exact-session snapshot other current-research consumers treat as this
            # session's authoritative close. Adopting it here without this check would let a
            # target-session close mismatch (real 2026-09-04 evidence: up to ~11% apart) silently
            # flow into technical_features.values/trend_state instead of being rejected.
            override = recovery_overrides.get(ticker)
            winning_record, history_source = resolve_target_session_observations(
                pf_record=pf_records[ticker], recovery_override=override, target_session=target_session,
            )
            if history_source == "RETAINED_TECHNICAL_HISTORY_RECOVERY":
                technical = _technical_features(
                    {"observations": winning_record.get("observations", [])}, target_session=target_session,
                    provenance={
                        "source": "RETAINED_DNSE_EXTENDED_HISTORY_RECOVERY",
                        "recovery_artifact_identity": recovery_identity,
                        "recovery_payload_sha256": override.get("payload_sha256") if isinstance(override, Mapping) else None,
                    },
                )
            else:
                if history_source == "RECOVERY_REJECTED_TARGET_SESSION_CLOSE_MISMATCH":
                    close_mismatch_rejected.add(ticker)
                technical = _technical_features(pf_records[ticker], target_session=target_session)
        else:
            technical = {"status": "NOT_APPLICABLE", "reason": "OUT_OF_CURRENT_DESCRIPTIVE_SCOPE",
                        "feature_as_of_session": None, "is_current_session": False, "values": {}}

        trend_state = (
            _trend_state(technical["values"])
            if technical.get("status") == "SHADOW_ONLY" and technical["is_current_session"] else None
        )

        records[ticker] = {
            "ticker": ticker,
            "activity_and_session_state": activity_state,
            "membership_state": ur.get("membership_state"),
            "in_current_descriptive_scope": in_scope,
            "technical_features": technical,
            "trend_state": trend_state,
            "liquidity": _liquidity_view(ticker, liquidity_artifact) if in_scope else {"status": "NOT_APPLICABLE", "reason": "OUT_OF_CURRENT_DESCRIPTIVE_SCOPE"},
            "sector_classification": entity_classifications.get(ticker),
        }

    recovery_all_records = technical_history_recovery_artifact.get("records", {}) if technical_history_recovery_artifact else None
    _assert_no_recoverable_same_session_technical_gap(
        records, pf_records, recovery_all_records, close_mismatch_rejected=frozenset(close_mismatch_rejected),
    )

    in_scope_records = [record for record in records.values() if record["in_current_descriptive_scope"]]
    same_session_records = [record for record in in_scope_records if record["technical_features"].get("is_current_session")]
    same_session_shadow = [record for record in same_session_records if record["technical_features"]["status"] == "SHADOW_ONLY"]
    stale_but_available = [
        record for record in in_scope_records
        if record["technical_features"]["status"] == "SHADOW_ONLY" and not record["technical_features"]["is_current_session"]
    ]

    returns = [record["technical_features"]["values"]["return_1d"] for record in same_session_shadow]
    momentum = [record["technical_features"]["values"]["momentum_20d"] for record in same_session_shadow]
    volatility = [record["technical_features"]["values"]["volatility_20d"] for record in same_session_shadow]
    relvol = [record["technical_features"]["values"]["relative_volume_provider_scoped"] for record in same_session_shadow
             if isinstance(record["technical_features"]["values"].get("relative_volume_provider_scoped"), (int, float))]
    advancing, declining = sum(v > 0 for v in returns), sum(v < 0 for v in returns)
    trend_above = sum(record["trend_state"] == "ABOVE_MA20" for record in same_session_shadow)
    trend_below = sum(record["trend_state"] == "AT_OR_BELOW_MA20" for record in same_session_shadow)

    market_breadth = {
        "current_active_equity_denominator": current_active_equity_denominator,
        "observed_session_cohort": observed_session_cohort_count,
        "same_session_technical_feature_available_count": len(same_session_shadow),
        "coverage_ratio_of_denominator": len(same_session_shadow) / current_active_equity_denominator,
        "coverage_ratio_of_observed_session_cohort": (len(same_session_shadow) / observed_session_cohort_count) if observed_session_cohort_count else None,
        "stale_feature_available_but_not_current_session_count": len(stale_but_available),
        "session": target_session,
        "quality_state": (
            "PARTIAL_COVERAGE_EXPLICIT" if len(same_session_shadow) < current_active_equity_denominator else "FULL_COVERAGE_OF_DENOMINATOR"
        ),
        "advancing": advancing, "declining": declining, "unchanged": len(same_session_shadow) - advancing - declining,
        "advance_ratio": (advancing / len(same_session_shadow)) if same_session_shadow else None,
        "trend": {"above_ma20": trend_above, "at_or_below_ma20": trend_below, "unavailable": len(same_session_shadow) - trend_above - trend_below},
        "breadth_descriptor": _descriptor(advancing, declining, len(same_session_shadow), prefix="MARKET_BREADTH"),
        "momentum_descriptor": _descriptor(sum(v > 0 for v in momentum), sum(v < 0 for v in momentum), len(momentum), prefix="MOMENTUM_BREADTH"),
        "volatility": {
            "available_count": len(volatility), "median": median(volatility) if volatility else None,
            "authority_tier": "SHADOW_ONLY", "warning": "CONTEMPORANEOUS_CROSS_SECTION_ONLY_NOT_HISTORICAL_REGIME",
        },
        "provider_relative_volume": {
            "available_count": len(relvol), "unavailable_count": len(same_session_shadow) - len(relvol),
            "authority_tier": "DERIVED_PROXY", "warning": "NOT_LIQUIDITY_OR_TURNOVER",
        },
        "authority_boundary": {"not_authoritative_market_universe": True, "not_bull_bear_call_forecast_or_timing": True,
                               "no_ranking_or_recommendation": True, "no_historical_volatility_regime": True},
    }

    sector_breadth = _sector_breadth(same_session_records, entity_classifications)

    cross_sectional_features = {
        "feature_set": ["close", "return_1d", "ma_3", "ma_5", "ma_20", "momentum_20d", "volatility_20d", "relative_volume_provider_scoped"],
        "method": "mva_daily_research_bundle.market_features (reused unmodified)",
        "current_active_equity_denominator": current_active_equity_denominator,
        "same_session_available_count": len(same_session_shadow),
        "same_session_coverage_ratio": len(same_session_shadow) / current_active_equity_denominator,
        "stale_prior_session_available_count": len(stale_but_available),
        "not_applicable_out_of_scope_count": sum(1 for record in records.values() if not record["in_current_descriptive_scope"]),
        "unavailable_count": sum(1 for record in in_scope_records if record["technical_features"]["status"] != "SHADOW_ONLY"),
    }

    liquidity_eligible = [record for record in in_scope_records if record["liquidity"]["status"] == "ELIGIBLE"]
    reconciliation_warnings = [
        {"ticker": record["ticker"], "g1_v_reconciliation": record["liquidity"]["g1_v_reconciliation"]}
        for record in liquidity_eligible
        if isinstance(record["liquidity"].get("g1_v_reconciliation"), Mapping)
        and record["liquidity"]["g1_v_reconciliation"].get("verdict") not in {"EXACT_MATCH", None}
    ]
    liquidity_features = {
        "current_active_equity_denominator": current_active_equity_denominator,
        "eligible_count": len(liquidity_eligible),
        "coverage_ratio": len(liquidity_eligible) / current_active_equity_denominator,
        "board_semantics_preserved": ["G1", "G4", "T1", "T3", "T4", "T6"],
        "reconciliation_warnings": reconciliation_warnings,
        "value_status": "GROSS_TRADE_AMOUNT_RETAINED_ONLY_NON_AUTHORITATIVE_SCALE_BASIS_UNRESOLVED",
        "authority_boundary": dict(liquidity_artifact.get("authority_boundary", {})),
        "source_liquidity_artifact_disposition_counts": dict(liquidity_artifact.get("coverage", {}).get("disposition_counts", {})),
    }

    universe_status_counts = Counter(record["activity_and_session_state"] for record in records.values())

    validation = {
        "coverage": {
            "input_candidates": len(records),
            "current_active_equity_denominator": current_active_equity_denominator,
            "observed_session_cohort": observed_session_cohort_count,
            "same_session_technical_feature_available_count": len(same_session_shadow),
            "stale_feature_available_but_not_current_session_count": len(stale_but_available),
            "technical_feature_unavailable_count": sum(1 for record in in_scope_records if record["technical_features"]["status"] != "SHADOW_ONLY"),
            "universe_status_counts": dict(sorted(universe_status_counts.items())),
        },
        "available_outputs": ["market_breadth", "sector_breadth", "cross_sectional_features", "liquidity_features"],
        "blocked_outputs": dict(sorted(BLOCKED_OUTPUTS.items())),
        "lineage": {
            "universe_resolution_artifact_identity": universe_resolution_artifact.get("artifact_identity"),
            "p3f9b_snapshot_identity": p3f9b_snapshot.get("snapshot_identity"),
            "liquidity_artifact_identity": liquidity_artifact.get("artifact_identity"),
            "technical_history_recovery_artifact_identity": recovery_identity,
            "session": target_session,
        },
        "session": target_session,
    }

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "session": target_session,
        "input_lineage": validation["lineage"],
        "market_breadth": market_breadth,
        "sector_breadth": sector_breadth,
        "cross_sectional_features": cross_sectional_features,
        "liquidity_features": liquidity_features,
        "validation": validation,
        "promotion_recommendation": {
            "state": "OWNER_REVIEW_REQUIRED_NOT_AUTHORITATIVE",
            "reason": "Current descriptive market-wide research only; no ranking, recommendation, historical PIT, or portfolio authority is created.",
        },
        "authority_boundary": {
            "ranking_recommendation_valuation": "NOT_EMITTED",
            "portfolio_sizing_execution": "NOT_EMITTED",
            "historical_pit_raw_as_traded": "NOT_TOUCHED",
            "corporate_action_ex_date": "NOT_TOUCHED",
            "active_universe_promotion": "NOT_TOUCHED",
            "QUALIFIED_LIQUIDITY_INPUTS": False,
            "gross_trade_amount": "NON_AUTHORITATIVE_SCALE_BASIS_UNRESOLVED",
        },
        "records": records,
    }
    artifact_sha256 = _hash(artifact)
    artifact["artifact_sha256"] = artifact_sha256
    artifact["artifact_identity"] = f"market_wide_current_descriptive_research:{artifact_sha256}"
    return artifact
