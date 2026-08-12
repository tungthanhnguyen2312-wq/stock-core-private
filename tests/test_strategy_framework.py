from __future__ import annotations

import json
from pathlib import Path

import pytest

from strategy_framework import (
    RegistryState,
    StrategyPlugin,
    SuspectInputPolicy,
    evaluate_strategy,
    load_strategy_registry,
    registry_records,
    validate_registry,
)


def plugin(**changes):
    data = {
        "strategy_id": "TEST_V1", "strategy_version": "1.0.0",
        "registry_state": RegistryState.IMPLEMENTATION_READY_FRAMEWORK, "execution_enabled": True,
        "execution_blocker": None, "required_features": ("market.close",),
        "optional_features": ("volume.ratio_5",), "accepted_feature_statuses": ("HISTORICAL_ONLY", "SUSPECT"),
        "accepted_pit_statuses": ("HISTORICAL_ONLY",), "accepted_price_bases": ("UNKNOWN",),
        "accepted_volume_bases": ("UNKNOWN",), "applicable_instrument_classes": ("EQUITY",),
        "applicable_sectors": ("ALL",), "eligibility_rules": ("TEST_CONTRACT",),
        "suspect_input_policy": SuspectInputPolicy.ALLOW_WITH_WARNING,
        "lineage_version": "1.0.0", "scoring_hook": lambda row: row["market.close"],
    }
    data.update(changes)
    return StrategyPlugin(**data)


def row(**changes):
    data = {
        "canonical_instrument_id": "DNSE:AAA", "session": "2026-08-01", "instrument_class": "EQUITY",
        "price_basis_status": "UNKNOWN", "volume_basis_status": "UNKNOWN", "pit_status": "HISTORICAL_ONLY",
        "quality_status": "CANONICAL", "feature_version": "1.0.0", "market.close": 10.0,
        "market.close__status": "HISTORICAL_ONLY", "volume.ratio_5": None,
        "volume.ratio_5__status": "BLOCKED", "volume.ratio_5__reason": "INSUFFICIENT_HISTORY",
    }
    data.update(changes)
    return data


def test_required_and_optional_feature_dependencies_are_distinct():
    result = evaluate_strategy(plugin(), row())
    assert result.eligible and result.score == 10.0
    assert result.component_statuses["volume.ratio_5"] == "BLOCKED"


def test_missing_feature_blocks_only_the_dependent_strategy():
    missing = evaluate_strategy(plugin(), row(**{"market.close": None}))
    independent = evaluate_strategy(plugin(required_features=("market.other",)), row(**{
        "market.other": 1.0, "market.other__status": "HISTORICAL_ONLY"}))
    assert not missing.eligible and "MISSING_REQUIRED_FEATURE" in missing.blockers
    assert independent.eligible


def test_insufficient_history_is_explicit_and_never_scored():
    result = evaluate_strategy(plugin(required_features=("market.ma_20",)), row(**{
        "market.ma_20": None, "market.ma_20__status": "BLOCKED",
        "market.ma_20__reason": "INSUFFICIENT_HISTORY"}))
    assert not result.eligible and result.score is None and result.rank is None
    assert "FEATURE_BLOCKED" in result.blockers
    assert "feature:market.ma_20:INSUFFICIENT_HISTORY" in result.reasons


def test_unknown_price_and_volume_bases_follow_each_strategy_contract():
    price_reject = evaluate_strategy(plugin(accepted_price_bases=("PIT_OBSERVED",)), row())
    volume_reject = evaluate_strategy(plugin(accepted_volume_bases=("QUALIFIED",)), row())
    assert "PRICE_BASIS_NOT_ACCEPTED" in price_reject.blockers
    assert "VOLUME_BASIS_NOT_ACCEPTED" in volume_reject.blockers


def test_blockers_are_strategy_specific_without_global_ticker_qualification():
    permissive = evaluate_strategy(plugin(), row())
    price_dependent = evaluate_strategy(plugin(accepted_price_bases=("PIT_OBSERVED",)), row())
    assert permissive.eligible
    assert not price_dependent.eligible and "PRICE_BASIS_NOT_ACCEPTED" in price_dependent.blockers


def test_suspect_policy_is_declared_per_strategy():
    suspect = row(**{"market.close__status": "SUSPECT"})
    allowed = evaluate_strategy(plugin(), suspect)
    rejected = evaluate_strategy(plugin(suspect_input_policy=SuspectInputPolicy.REJECT), suspect)
    assert allowed.eligible and "suspect_feature:market.close" in allowed.quality_metadata["warnings"]
    assert not rejected.eligible and "SUSPECT_INPUT_REJECTED" in rejected.blockers


def test_historical_only_pit_is_evaluated_explicitly():
    rejected = evaluate_strategy(plugin(accepted_pit_statuses=("QUALIFIED",)), row())
    assert "PIT_STATUS_NOT_ACCEPTED" in rejected.blockers


def test_ineligible_result_rejects_fake_score_and_preserves_lineage():
    result = evaluate_strategy(plugin(accepted_price_bases=("PIT_OBSERVED",)), row())
    assert result.score is None and result.rank is None
    assert result.strategy_lineage["strategy_version"] == "1.0.0"
    assert result.feature_lineage["feature_version"] == "1.0.0"
    with pytest.raises(ValueError, match="ineligible"):
        result.__class__(**{**result.__dict__, "score": 1.0})


def test_registry_is_machine_readable_consistent_and_unsupported_cannot_execute():
    config = Path("config/strategy_registry.json")
    payload = json.loads(config.read_text(encoding="utf-8"))
    registry = load_strategy_registry(config)
    validate_registry(registry)
    assert {item["strategy_id"] for item in registry_records(registry)} == set(registry)
    assert payload["schema_version"] == "1.0.0"
    unsupported = {"VALUE", "GROWTH", "CANSLIM", "SMC", "FLOW", "EVENT_DRIVEN"}
    assert unsupported <= set(registry)
    for strategy_id in unsupported:
        result = evaluate_strategy(registry[strategy_id], row())
        assert not registry[strategy_id].execution_enabled
        assert "STRATEGY_NOT_EXECUTABLE" in result.blockers
