from dataclasses import replace

import pytest

from test_market_only_pit_eligibility import DAYS, binding, observation
from market_only_pit_eligibility import evaluate, existing_vnm_requirements
from vnm_shadow_backtest import run_market_only_gross_replay


def replay_inputs():
    # Two-session fixture validates wiring only; production default remains SMA50.
    signal_requirement = replace(existing_vnm_requirements(),lookback_sessions=1)
    replay_requirement = replace(signal_requirement,volume_required=True)
    observations = [observation(d,close=11.+n) for n,d in enumerate(DAYS)]
    def gate(n,requirements):
        return evaluate(requirements=requirements,ticker="VNM",session=DAYS[n],knowledge_cutoff=DAYS[n]+"T10:00:00Z",
            market_versions=observations,calendar_sessions=DAYS,universe_versions=[binding()],ca_versions=[binding()])
    signal_gate = gate(0,signal_requirement)
    snapshot = {"ticker":"VNM","snapshot_id":"fixture:t0","knowledge_cutoff":signal_gate["knowledge_cutoff"],"state":"partial",
                "ranking":{"dimensions":{"technical_current_market_readiness":{"state":"available"}}},
                "scenarios":{"records":{"bull":{"state":"available"}}},
                "market_feature_lineage":{"signal_snapshot_identities":["fixture:t0"],"input_snapshot_identities":signal_gate["selected_snapshot_identities"],
                    "knowledge_cutoff":signal_gate["knowledge_cutoff"],"feature_knowledge_available_at":signal_gate["knowledge_cutoff"]}}
    return dict(snapshot=snapshot,entry_observation=observations[1],exit_observation=observations[2],signal_eligibility=signal_gate,
                entry_eligibility=gate(1,replay_requirement),exit_eligibility=gate(2,replay_requirement))


def test_existing_signal_and_return_primitives_yield_gross_without_net_or_execution():
    i = replay_inputs(); result = run_market_only_gross_replay(**i)
    assert result["gross_return"] == pytest.approx(13/12-1)
    assert result["net_return"] is None and result["execution_state"] == "UNAVAILABLE"
    assert result["state"] == "INFRASTRUCTURE_VALIDATION_ONLY" and result["live_orders"] == 0
    assert result == run_market_only_gross_replay(**i)


@pytest.mark.parametrize("mutation", ["future_feature","missing_feature_lineage","unbound_price","excluded_input","missing_signal","changed_price"])
def test_future_or_unbound_inputs_cannot_supply_replay(mutation):
    i = replay_inputs()
    if mutation == "future_feature": i["snapshot"]["market_feature_lineage"]["feature_knowledge_available_at"] = DAYS[1]+"T10:00:00Z"
    if mutation == "missing_feature_lineage": i["snapshot"].pop("market_feature_lineage")
    if mutation == "unbound_price": i["entry_observation"]["snapshot_identity"] = "not_bound"
    if mutation == "excluded_input": i["entry_eligibility"]["state"] = "EXCLUDED"
    if mutation == "missing_signal": i["snapshot"]["scenarios"] = {}
    if mutation == "changed_price": i["entry_observation"]["normalized"]["ohlc"]["close"] = 13.
    result = run_market_only_gross_replay(**i)
    assert result["state"] == "EXCLUDED" and result["gross_return"] is None and result["net_return"] is None
