import copy

import pytest

from current_market_screening_opportunity_comparison_foundation import build_artifact
from market_wide_current_descriptive_research import content_identity as descriptive_identity


def _technical(*, current=True, momentum=0.0, relative_volume=1.0):
    return {
        "status": "SHADOW_ONLY",
        "is_current_session": current,
        "values": {"momentum_20d": momentum, "relative_volume_provider_scoped": relative_volume},
    }


def _liquidity(*, eligible=True, warning=False):
    if not eligible:
        return {"status": "UNAVAILABLE", "reason": "NO_CURRENT_SESSION_ACTIVE_BOARD"}
    reconciliation = {"verdict": "EXACT", "exact_match": True}
    if warning:
        reconciliation = {"verdict": "OTHER", "exact_match": False, "delta": 4.0}
    return {
        "status": "ELIGIBLE", "session": "2026-08-21", "board_composition": {"MATCHED_ROUND_LOT": {}},
        "g1_v_reconciliation": reconciliation,
        "value_status": "GROSS_TRADE_AMOUNT_RETAINED_ONLY_NON_AUTHORITATIVE_SCALE_BASIS_UNRESOLVED",
    }


def _source():
    provider_sector = {
        "classification_authority": "PROVIDER_DESCRIPTIVE_CLASSIFICATION",
        "classification_label": "industrial",
    }
    records = {
        "AAA": {
            "ticker": "AAA", "in_current_descriptive_scope": True, "activity_and_session_state": "ACTIVE_LISTED_OBSERVED",
            "technical_features": _technical(momentum=0.20, relative_volume=1.5), "trend_state": "ABOVE_MA20",
            "liquidity": _liquidity(), "sector_classification": provider_sector,
        },
        "BBB": {
            "ticker": "BBB", "in_current_descriptive_scope": True, "activity_and_session_state": "ACTIVE_LISTED_OBSERVED",
            "technical_features": _technical(current=False, momentum=0.10, relative_volume=1.0), "trend_state": "ABOVE_MA20",
            "liquidity": _liquidity(), "sector_classification": provider_sector,
        },
        "CCC": {
            "ticker": "CCC", "in_current_descriptive_scope": True, "activity_and_session_state": "ACTIVE_LISTED_OBSERVED",
            "technical_features": _technical(momentum=-0.10, relative_volume=0.5), "trend_state": "AT_OR_BELOW_MA20",
            "liquidity": _liquidity(eligible=False), "sector_classification": provider_sector,
        },
        "SHB": {
            "ticker": "SHB", "in_current_descriptive_scope": True, "activity_and_session_state": "ACTIVE_LISTED_OBSERVED",
            "technical_features": _technical(momentum=-0.20, relative_volume=0.8), "trend_state": "AT_OR_BELOW_MA20",
            "liquidity": _liquidity(warning=True), "sector_classification": provider_sector,
        },
        "OLD": {
            "ticker": "OLD", "in_current_descriptive_scope": False, "activity_and_session_state": "INACTIVE_OR_DELISTED",
            "technical_features": {"status": "MISSING", "is_current_session": False, "values": {}}, "trend_state": None,
            "liquidity": {"status": "UNAVAILABLE", "reason": "NOT_IN_SCOPE"}, "sector_classification": {},
        },
    }
    sector_key = "PROVIDER_DESCRIPTIVE_CLASSIFICATION|fixture|industrial"
    source = {
        "schema_version": "1.0.0", "contract_version": "market_wide_current_descriptive_research/v1", "session": "2026-08-21",
        "records": records,
        "sector_breadth": {
            "sector_count_available": 1, "sector_count_insufficient_coverage": 1,
            "sectors": {
                sector_key: {
                    "status": "AVAILABLE", "sector_key": sector_key, "classification_label": "industrial",
                    "median_momentum_20d": -0.10,
                    "member_relative_positions": [
                        {"ticker": "AAA", "momentum_20d": 0.20, "percentile": 0.75, "descriptive_bucket": "UPPER_QUARTILE"},
                        {"ticker": "SHB", "momentum_20d": -0.20, "percentile": 0.25, "descriptive_bucket": "LOWER_QUARTILE"},
                    ],
                },
                "PROVIDER_DESCRIPTIVE_CLASSIFICATION|fixture|small": {
                    "status": "UNAVAILABLE_INSUFFICIENT_COVERAGE", "classification_label": "small",
                    "member_relative_positions": [],
                },
            },
        },
        "liquidity_features": {"reconciliation_warnings": [{"ticker": "SHB", "g1_v_reconciliation": {"verdict": "OTHER"}}]},
        "validation": {
            "coverage": {"current_active_equity_denominator": 4, "observed_session_cohort": 3},
            "lineage": {"liquidity_artifact_identity": "fixture-liquidity"},
        },
    }
    return {**source, **descriptive_identity(source)}


def test_build_is_deterministic_and_preserves_true_intersections():
    source = _source()
    first = build_artifact(source)
    second = build_artifact(source)

    assert first["artifact_identity"] == second["artifact_identity"]
    assert first["coverage_disclosure"] == {
        "denominator": 4,
        "observed_session_cohort": 3,
        "same_session_technical_feature_count": 3,
        "current_descriptive_liquidity_eligible_count": 3,
        "technical_and_liquidity_intersection_count": 2,
        "sector_relative_eligible_count": 2,
        "quality_state": "PARTIAL_COVERAGE_EXPLICIT_CURRENT_SESSION_ONLY",
        "missing_is_not_zero": True,
    }
    assert first["screen_membership_counts"] == {
        "MOMENTUM_ABOVE_COHORT_MEDIAN": 1,
        "RELATIVE_VOLUME_ABOVE_COHORT_MEDIAN": 1,
        "TECHNICAL_AND_CURRENT_DESCRIPTIVE_LIQUIDITY": 2,
        "TREND_AND_POSITIVE_MOMENTUM": 1,
    }
    liquidity_intersection = first["records"]["CCC"]["screen_membership"]["TECHNICAL_AND_CURRENT_DESCRIPTIVE_LIQUIDITY"]
    assert liquidity_intersection["status"] == "UNAVAILABLE"
    assert liquidity_intersection["reason"] == "NO_CURRENT_SESSION_ACTIVE_BOARD"
    assert liquidity_intersection["member"] is None
    assert liquidity_intersection["coverage"]["eligible_count"] == 2
    assert first["records"]["BBB"]["market_relative_comparison"]["reason"] == "STALE_TECHNICAL_FEATURE_NOT_CURRENT_SESSION"
    assert first["records"]["OLD"]["market_relative_comparison"]["status"] == "UNAVAILABLE"


def test_sector_fails_closed_and_shb_warning_propagates_to_liquidity_context():
    artifact = build_artifact(_source())

    assert artifact["records"]["AAA"]["sector_relative_comparison"]["status"] == "AVAILABLE"
    assert artifact["records"]["CCC"]["sector_relative_comparison"]["reason"] == "SECTOR_RELATIVE_COVERAGE_INSUFFICIENT"
    shb_liquidity = artifact["records"]["SHB"]["liquidity_context"]
    assert shb_liquidity["g1_v_reconciliation_verdict"] == "OTHER"
    assert shb_liquidity["g1_v_reconciliation_warning"]["delta"] == 4.0
    assert shb_liquidity["authority"] == "CURRENT_SESSION_DESCRIPTIVE_ONLY_GROSS_TRADE_AMOUNT_NON_AUTHORITATIVE"


def test_identity_or_contract_mismatch_fails_closed():
    source = _source()
    source["records"]["AAA"]["trend_state"] = "AT_OR_BELOW_MA20"
    with pytest.raises(ValueError, match="CURRENT_DESCRIPTIVE_ARTIFACT_IDENTITY_MISMATCH"):
        build_artifact(source)

    source = _source()
    source["contract_version"] = "unrecognized"
    source = {**source, **descriptive_identity(source)}
    with pytest.raises(ValueError, match="CURRENT_DESCRIPTIVE_CONTRACT_VERSION_UNSUPPORTED"):
        build_artifact(source)
