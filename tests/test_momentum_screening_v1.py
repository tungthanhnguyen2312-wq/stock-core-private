from __future__ import annotations

import json

import pandas as pd

from market_feature_store_v1 import build_historical
from momentum_screening_v1 import (
    MOMENTUM_DEPENDENCIES,
    evaluate_momentum,
    momentum_plugin,
    screen_momentum,
    write_momentum_artifacts,
)
from strategy_framework import load_strategy_registry


AS_OF = "2026-08-11"


def frame(rows):
    output = []
    for item in rows:
        name, session, ret, trend, volatility = item[:5]
        changes = item[5] if len(item) > 5 else {}
        row = {
            "canonical_instrument_id": f"DNSE:{name}", "session": session,
            "instrument_class": "EQUITY", "price_basis_status": "RAW_AS_TRADED",
            "volume_basis_status": "UNKNOWN", "pit_status": "HISTORICAL_ONLY",
            "quality_status": "CANONICAL", "feature_version": "1.0.0", "raw_observation_id": name,
            "price_basis_reason": "", "pit_reason": "historical_raw_availability_not_proven",
            "market.return_5d": ret, "market.distance_ma_5": trend, "market.volatility_5": volatility,
            "market.return_5d__status": "HISTORICAL_ONLY", "market.distance_ma_5__status": "HISTORICAL_ONLY",
            "market.volatility_5__status": "HISTORICAL_ONLY", "market.return_5d__reason": "",
            "market.distance_ma_5__reason": "", "market.volatility_5__reason": "",
        }
        row.update(changes)
        output.append(row)
    return pd.DataFrame(output)


def base_rows():
    return [("AAA", AS_OF, 0.10, 0.01, 0.10), ("BBB", AS_OF, 0.20, 0.02, 0.20),
            ("CCC", AS_OF, 0.30, 0.03, 0.30)]


def test_registry_integrates_implemented_momentum_with_exact_dependencies_and_weights():
    plugin = momentum_plugin()
    assert plugin.execution_enabled
    assert tuple(plugin.required_features) == MOMENTUM_DEPENDENCIES
    assert plugin.scoring_contract["minimum_history_sessions"] == 6
    assert sum(component["weight"] for component in plugin.scoring_contract["components"]) == 1.0
    assert load_strategy_registry()["BREAKOUT_FOUNDATION_V1"].execution_enabled is False


def test_vectorized_score_formula_and_explainability_are_deterministic():
    first = evaluate_momentum(frame(base_rows()), as_of=AS_OF)
    second = evaluate_momentum(frame(list(reversed(base_rows()))), as_of=AS_OF)
    assert first.ranked[["canonical_instrument_id", "score", "rank"]].to_dict("records") == second.ranked[["canonical_instrument_id", "score", "rank"]].to_dict("records")
    assert first.ranked.canonical_instrument_id.tolist() == ["DNSE:CCC", "DNSE:BBB", "DNSE:AAA"]
    assert first.ranked.score.round(6).tolist() == [86.666667, 66.666667, 46.666667]
    top = first.ranked.iloc[0]
    assert json.loads(top["weights"])["market.return_5d"] == 0.5
    assert "contract_lineage_id" in json.loads(top["strategy_lineage"])
    assert top["market.volatility_5__contribution"] > 0


def test_missing_and_insufficient_history_block_without_score_or_rank():
    values = base_rows()
    values[0] = (*values[0],)
    data = frame(values)
    data.loc[0, "market.return_5d"] = None
    data.loc[0, "market.return_5d__status"] = "BLOCKED"
    data.loc[0, "market.return_5d__reason"] = "INSUFFICIENT_HISTORY_OR_MISSING_INPUT"
    run = evaluate_momentum(data, as_of=AS_OF)
    blocked = run.eligibility[run.eligibility.canonical_instrument_id.eq("DNSE:AAA")].iloc[0]
    assert not bool(blocked.eligible)
    assert "FEATURE_BLOCKED" in json.loads(blocked.blockers)
    assert pd.isna(blocked.score) and pd.isna(blocked["rank"])


def test_suspect_is_a_warning_but_unknown_price_basis_blocks_and_unknown_volume_does_not():
    data = frame(base_rows())
    data.loc[0, "quality_status"] = "SUSPECT"
    for feature in MOMENTUM_DEPENDENCIES:
        data.loc[0, f"{feature}__status"] = "SUSPECT"
    run = evaluate_momentum(data, as_of=AS_OF)
    warning = json.loads(run.eligibility.iloc[0].quality_metadata)["warnings"]
    assert "suspect_feature:market.return_5d" in warning
    assert run.eligibility.iloc[0].eligible
    data.loc[1, "price_basis_status"] = "UNKNOWN"
    blocked = evaluate_momentum(data, as_of=AS_OF).eligibility.iloc[1]
    assert "PRICE_BASIS_NOT_ACCEPTED" in json.loads(blocked.blockers)
    assert "VOLUME_BASIS_NOT_ACCEPTED" not in json.loads(blocked.blockers)


def test_historical_only_pit_is_accepted_by_momentum_contract():
    result = evaluate_momentum(frame(base_rows()), as_of=AS_OF)
    assert result.eligibility.eligible.all()
    assert {json.loads(item)["pit_status"] for item in result.eligibility.pit_metadata} == {"HISTORICAL_ONLY"}


def test_eligible_only_ranking_ties_use_stable_secondary_instrument_order():
    data = frame([("ZZZ", AS_OF, .1, .1, .1), ("AAA", AS_OF, .1, .1, .1)])
    ranked = evaluate_momentum(data, as_of=AS_OF).ranked
    assert ranked.canonical_instrument_id.tolist() == ["DNSE:AAA", "DNSE:ZZZ"]
    assert ranked["rank"].tolist() == [1, 2]


def test_as_of_excludes_future_rows_and_missing_sessions_change_the_universe():
    data = frame([("AAA", "2026-08-10", .1, .1, .1), ("AAA", AS_OF, .2, .2, .2),
                  ("BBB", "2026-08-10", .9, .9, .01), ("CCC", AS_OF, .3, .3, .3)])
    earlier = evaluate_momentum(data, as_of="2026-08-10")
    latest = evaluate_momentum(data, as_of=AS_OF)
    assert set(earlier.eligibility.canonical_instrument_id) == {"DNSE:AAA", "DNSE:BBB"}
    assert set(latest.eligibility.canonical_instrument_id) == {"DNSE:AAA", "DNSE:BBB", "DNSE:CCC"}
    carried = latest.eligibility[latest.eligibility.canonical_instrument_id.eq("DNSE:BBB")].iloc[0]
    assert carried["feature_session"] == pd.Timestamp("2026-08-10", tz="UTC")
    assert latest.eligibility.loc[latest.eligibility.canonical_instrument_id.eq("DNSE:AAA"), "market.return_5d"].iloc[0] == .2


def test_phase3_rolling_features_flow_to_momentum_without_future_rows():
    rows = []
    for index, close in enumerate(range(10, 17), start=1):
        rows.append({"canonical_instrument_id": "DNSE:AAA", "session": f"2026-01-{index:02d}",
                     "open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 100,
                     "quality_status": "CANONICAL", "quality_flags": "[]", "raw_observation_id": f"AAA-{index}",
                     "instrument_class": "EQUITY", "price_basis_status": "RAW_AS_TRADED",
                     "volume_basis_status": "UNKNOWN"})
    historical, placeholders = build_historical(pd.DataFrame(rows))
    assert placeholders.empty
    run = evaluate_momentum(historical, as_of="2026-01-06")
    result = run.eligibility.iloc[0]
    assert result["market.return_5d"] == (15 / 10) - 1
    assert result["as_of"] == "2026-01-06T00:00:00+00:00"


def test_screener_filters_top_n_rank_score_subset_and_blocker_status():
    data = frame(base_rows())
    data.loc[0, "price_basis_status"] = "UNKNOWN"
    results = evaluate_momentum(data, as_of=AS_OF).eligibility
    assert screen_momentum(results, top_n=1).canonical_instrument_id.tolist() == ["DNSE:CCC"]
    assert screen_momentum(results, max_rank=1, min_score=80).canonical_instrument_id.tolist() == ["DNSE:CCC"]
    assert screen_momentum(results, instruments=["DNSE:BBB"]).canonical_instrument_id.tolist() == ["DNSE:BBB"]
    blocked = screen_momentum(results, eligible_only=False, statuses=["INELIGIBLE"], blockers=["PRICE_BASIS_NOT_ACCEPTED"])
    assert blocked.canonical_instrument_id.tolist() == ["DNSE:AAA"]


def test_artifacts_reconcile_and_preserve_empty_or_scored_outputs(tmp_path):
    run = evaluate_momentum(frame(base_rows()), as_of=AS_OF)
    paths = write_momentum_artifacts(run, tmp_path, top_n=2)
    assert all(path.exists() for path in paths.values())
    report = json.loads(paths["report"].read_text(encoding="utf-8"))
    assert report["exact_reconciliation"]
    assert report["candidate_instruments"] == 3
