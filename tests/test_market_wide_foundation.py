from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd

from market_data_contracts import (
    ExceptionDisposition,
    FeatureStatus,
    PitFinancialFact,
    PriceBasis,
    RawObservation,
    canonicalize_market_record,
    financial_facts_available_as_of,
)
from market_feature_store import (
    StrategyDeclaration,
    build_cross_sectional_snapshot,
    build_historical_features,
    quality_exceptions,
    strategy_is_eligible,
)


def raw_observation() -> RawObservation:
    return RawObservation(
        provider="DNSE", dataset="daily_ohlc", instrument="HPG", retrieved_at="2026-08-11T00:00:00Z",
        request_identity="daily:HPG:2026-08-10", raw_payload_hash="a" * 64, schema_version="provider-v1",
        raw_payload={"close": 100, "unknown_semantic_field": "retained"}, source_event_time="2026-08-10",
        provenance={"source": "first_party_contract"},
    )


def test_raw_record_survives_unknown_semantics_and_canonical_unit_transform_is_deterministic():
    raw = raw_observation()
    first = canonicalize_market_record(raw, exchange="HOSE", board="G1", instrument_class="EQUITY",
                                       fields={"volume": 2, "close": 100}, unit_multiplier=100)
    second = canonicalize_market_record(raw, exchange="HOSE", board="G1", instrument_class="EQUITY",
                                        fields={"close": 100, "volume": 2}, unit_multiplier=100)
    assert raw.record()["raw_payload"]["unknown_semantic_field"] == "retained"
    assert first.fields["volume"] == 200
    assert first.record() == second.record()


def test_anomaly_goes_to_exception_queue_without_deleting_raw_observation():
    records = [{"observation_id": "raw-1", "ticker": "HPG", "date": "2026-01-01", "open": 10,
                "high": 9, "low": 8, "close": 11, "volume": 100}]
    exceptions = quality_exceptions(records)
    assert len(records) == 1
    assert exceptions[0].rule == "impossible_ohlc_relation"
    assert exceptions[0].disposition == ExceptionDisposition.UNRESOLVED


def test_pit_never_exposes_period_end_or_restatement_before_actual_publication():
    original = PitFinancialFact("fundamental.revenue", "HPG", 100, "2025-12-31", "2026-01-30",
                                "2026-01-30", "2026-01-30", None, "annual.pdf", "consolidated",
                                "audited", FeatureStatus.QUALIFIED)
    restated = PitFinancialFact("fundamental.revenue", "HPG", 90, "2025-12-31", "2026-01-30",
                                "2026-01-30", "2026-04-15", "2026-04-15", "restatement.pdf",
                                "consolidated", "audited", FeatureStatus.QUALIFIED)
    assert financial_facts_available_as_of([original, restated], "2026-01-29") == []
    assert financial_facts_available_as_of([original, restated], "2026-02-01") == [original]
    assert financial_facts_available_as_of([original, restated], "2026-04-14") == [original]
    assert financial_facts_available_as_of([original, restated], "2026-04-15") == [original, restated]


def test_vectorized_features_are_deterministic_and_golden_ticker_compatible():
    frame = pd.DataFrame([
        {"ticker": "VNM", "date": "2026-01-02", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 10},
        {"ticker": "HPG", "date": "2026-01-03", "open": 12, "high": 13, "low": 11, "close": 12, "volume": 12},
        {"ticker": "HPG", "date": "2026-01-01", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 10},
        {"ticker": "HPG", "date": "2026-01-02", "open": 11, "high": 12, "low": 10, "close": 11, "volume": 11},
        {"ticker": "VNM", "date": "2026-01-01", "open": 9, "high": 10, "low": 8, "close": 9, "volume": 9},
        {"ticker": "VNM", "date": "2026-01-03", "open": 11, "high": 12, "low": 10, "close": 11, "volume": 11},
    ])
    first = build_historical_features(frame, price_basis=PriceBasis.ADJUSTED_RETROSPECTIVE)
    second = build_historical_features(frame.sample(frac=1, random_state=4), price_basis=PriceBasis.ADJUSTED_RETROSPECTIVE)
    pd.testing.assert_frame_equal(first, second)
    hpg = first[first.ticker.eq("HPG")].reset_index(drop=True)
    assert hpg.loc[2, "market.ma_3"] == 11
    assert hpg.loc[2, "feature_status"] == FeatureStatus.DERIVED.value
    snapshot = build_cross_sectional_snapshot(first, session="2026-01-03")
    assert snapshot.ticker.tolist() == ["HPG", "VNM"]


def test_historical_eleven_ticker_set_is_explicitly_a_regression_corpus_not_a_universe():
    from export_ai_bundle import DEFAULT_TICKERS
    assert len(DEFAULT_TICKERS) == 11
    architecture = Path("docs/market_wide_ingest_first_architecture.md").read_text(encoding="utf-8")
    assert "golden/regression corpus" in architecture


def test_proxy_is_explicit_and_one_missing_input_blocks_only_dependent_strategy_feature():
    declaration = StrategyDeclaration("VALUE", ("fundamental.roe.average_equity",),
                                      (FeatureStatus.QUALIFIED,), (PriceBasis.PIT_OBSERVED,), pit_required=True)
    eligible, reason = strategy_is_eligible(declaration, {
        "instrument_class": "EQUITY", "price_basis": PriceBasis.PIT_OBSERVED.value,
        "pit_status": FeatureStatus.QUALIFIED.value,
        "fundamental.roe.average_equity": None,
        "fundamental.roe.ending_equity_proxy": 0.12,
        "feature_statuses": {"fundamental.roe.average_equity": FeatureStatus.BLOCKED.value,
                             "fundamental.roe.ending_equity_proxy": FeatureStatus.DERIVED_PROXY.value},
    })
    assert not eligible and reason == "missing_feature:fundamental.roe.average_equity"


def test_strategy_dependency_fails_closed_and_deterministic_core_has_no_network_or_llm_dependency():
    declaration = StrategyDeclaration("MOMENTUM", ("market.return_1d",),
                                      (FeatureStatus.DERIVED,), (PriceBasis.PIT_OBSERVED,))
    eligible, reason = strategy_is_eligible(declaration, {"instrument_class": "EQUITY", "price_basis": "UNKNOWN",
                                                           "market.return_1d": .1, "feature_statuses": {"market.return_1d": "DERIVED"}})
    assert not eligible and reason == "price_basis_not_accepted"
    source = Path("market_feature_store.py").read_text(encoding="utf-8")
    imports = {node.names[0].name.split(".")[0] for node in ast.walk(ast.parse(source)) if isinstance(node, (ast.Import, ast.ImportFrom)) and node.names}
    assert not ({"requests", "anthropic", "openai", "socket"} & imports)
