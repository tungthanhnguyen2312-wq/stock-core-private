from pathlib import Path
import copy

import pytest

from expectations_scenario_research import build, write_immutable
from run_expectations_scenario_research import inputs


def test_scenarios_are_deterministic_evidence_bound_and_unqualified_for_probabilities(tmp_path: Path):
    pack, dossiers, tasks, relative = inputs()
    first = build(pack, dossiers, tasks, relative)
    prior = {scenario["ticker"]: scenario for scenario in first["scenarios"]}
    replay = build(pack, dossiers, tasks, relative, previous_by_ticker=prior)
    assert first["coverage"]["attempted_cases"] == 25
    assert first["coverage"]["partial_cases"] == 25
    assert [s["scenario_content_identity"] for s in first["scenarios"]] == [s["scenario_content_identity"] for s in replay["scenarios"]]
    assert all(s["probability_status"] == "UNQUALIFIED" for s in first["scenarios"])
    assert all(s["expectations"]["MARKET_IMPLIED_EXPECTATION"]["status"] == "UNAVAILABLE" for s in first["scenarios"])
    assert all(s["scenarios"]["BULL"]["catalysts"][0]["status"] == "NO_EVIDENCE_BACKED_CATALYST" for s in first["scenarios"])
    assert all(s["scenarios"]["BULL"]["invalidation_or_reversal_conditions"][1]["task_identity"] in s["relevant_research_task_identities"] for s in first["scenarios"])
    for scenario in first["scenarios"]:
        for lane in scenario["scenarios"].values():
            assert all(driver["classification"] in {"FACT", "INFERENCE", "HYPOTHESIS", "DATA_GAP"} for driver in lane["drivers"])
    path = tmp_path / "scenario.json"; write_immutable(path, first["scenarios"][0]);
    with pytest.raises(ValueError): write_immutable(path, {**first["scenarios"][0], "ticker": "MUTATED"})
    changed_dossiers = copy.deepcopy(dossiers)
    ticker = first["scenarios"][0]["ticker"]
    changed_dossiers[ticker]["thesis"].append({"type": "INFERENCE", "claim": "Test-only changed thesis.",
                                                "authority": "SHADOW_ONLY", "evidence_field": "test"})
    changed = build(pack, changed_dossiers, tasks, relative, previous_by_ticker=prior)
    changed_scenario = next(item for item in changed["scenarios"] if item["ticker"] == ticker)
    assert changed_scenario["prior_scenario_content_identity"] == prior[ticker]["scenario_content_identity"]
