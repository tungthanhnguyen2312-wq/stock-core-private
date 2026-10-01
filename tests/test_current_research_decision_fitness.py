from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

import current_research_decision_input as m


def _item(ticker: str, evidence_class: str, *, states=None, authorities=None,
          reasons=None, gated=False, posture="EARLY_WATCH"):
    states = states or {}
    authorities = authorities or {}
    reasons = reasons or {}
    dims = {}
    for name in m.DIMENSIONS:
        dims[name] = {
            "state": states.get(name, m.AVAILABLE),
            "authority": authorities.get(name, m.RESEARCH_QUALIFIED),
            "reason_codes": list(reasons.get(name, [])),
        }
    return {
        "contract_version": m.CONTRACT_VERSION,
        "ticker": ticker,
        "session": "2026-10-01",
        "evidence_class": evidence_class,
        "dimensions": dims,
        "synthesis": {
            "research_action_posture": posture,
            "action_posture_gated_by_current_evidence": gated,
        },
    }


def _record(item):
    return {"current_research_decision_input": item}


def test_decision_fitness_coverage_preserves_dimension_states_and_counts_gaps():
    records = {
        "AAA": _record(_item("AAA", m.CLASS_FULL)),
        "BBB": _record(_item(
            "BBB", m.CLASS_PARTIAL,
            states={"VALUATION": m.BLOCKED},
            authorities={"VALUATION": m.NO_AUTHORITY, "FUNDAMENTAL": m.RESEARCH_PROXY},
            reasons={"VALUATION": ["VALUATION_NO_USABLE_RELATIVE_METHOD"]},
        )),
        "CCC": _record(_item(
            "CCC", m.CLASS_INSUFFICIENT,
            states={"MARKET": m.BLOCKED, "TECHNICAL": m.BLOCKED, "VALUATION": m.BLOCKED},
            authorities={"MARKET": m.NO_AUTHORITY, "TECHNICAL": m.NO_AUTHORITY, "VALUATION": m.NO_AUTHORITY},
            reasons={
                "MARKET": ["NO_CURRENT_EVIDENCE"],
                "TECHNICAL": ["INSUFFICIENT_TECHNICAL_STRUCTURE_SERIES"],
                "VALUATION": ["VALUATION_CONTEXT_NOT_PROVIDED"],
            },
            posture="INSUFFICIENT_CURRENT_RESEARCH",
        )),
        "DDD": _record(_item(
            "DDD", m.CLASS_OUT_OF_SCOPE,
            states={name: m.NON_APPLICABLE for name in m.DIMENSIONS},
            authorities={name: m.NO_AUTHORITY for name in m.DIMENSIONS},
            reasons={name: ["OUTSIDE_CURRENT_RESEARCH_SCOPE"] for name in m.DIMENSIONS},
            posture="INSUFFICIENT_CURRENT_RESEARCH",
        )),
    }

    coverage = m.decision_fitness_coverage(records)

    assert coverage["denominator_count"] == 4
    assert coverage["research_usable_count"] == 2
    assert coverage["blocked_current_research_count"] == 1
    assert coverage["outside_scope_count"] == 1
    assert coverage["decision_fitness_distribution"] == {
        m.FITNESS_BLOCKED: 1,
        m.FITNESS_FULL: 1,
        m.FITNESS_OUTSIDE_SCOPE: 1,
        m.FITNESS_PARTIAL: 1,
    }
    assert coverage["dimension_available_count"]["MARKET"] == 2
    assert coverage["dimension_available_count"]["VALUATION"] == 1
    assert coverage["proxy_dimension_count"]["FUNDAMENTAL"] == 1

    gap = {(x["dimension"], x["reason_code"]): x["affected_tickers"]
           for x in coverage["gap_reason_prevalence"]}
    assert gap[("VALUATION", "VALUATION_NO_USABLE_RELATIVE_METHOD")] == 1
    assert gap[("MARKET", "NO_CURRENT_EVIDENCE")] == 1
    assert coverage["interpretation_boundary"]["counts_are_descriptive_not_priority_scores"] is True


def test_current_evidence_gate_forces_blocked_without_rewriting_evidence_class():
    item = _item("AAA", m.CLASS_PARTIAL, gated=True, posture="INSUFFICIENT_CURRENT_RESEARCH")
    view = m.build_ticker_decision_fitness(item)

    assert view["evidence_class"] == m.CLASS_PARTIAL
    assert view["decision_fitness_state"] == m.FITNESS_BLOCKED
    assert view["research_usable"] is False
    assert view["action_posture_gated_by_current_evidence"] is True


def test_decision_fitness_artifact_is_order_deterministic_and_read_only():
    aaa = _record(_item("AAA", m.CLASS_FULL))
    bbb = _record(_item(
        "BBB", m.CLASS_TECHNICAL,
        states={"FUNDAMENTAL": m.BLOCKED, "VALUATION": m.BLOCKED},
        authorities={"FUNDAMENTAL": m.NO_AUTHORITY, "VALUATION": m.NO_AUTHORITY},
        reasons={"FUNDAMENTAL": ["FUNDAMENTAL_CONTEXT_ABSENT"], "VALUATION": ["VALUATION_CONTEXT_NOT_PROVIDED"]},
    ))
    source_a = {
        "session": "2026-10-01",
        "artifact_identity": "integrated_investment_decision_product:test",
        "records": {"AAA": aaa, "BBB": bbb},
    }
    source_b = copy.deepcopy(source_a)
    source_b["records"] = {"BBB": source_b["records"]["BBB"], "AAA": source_b["records"]["AAA"]}

    a = m.build_decision_fitness_artifact(integrated_decision_artifact=source_a, requested_at="2026-10-01T18:00:00+07:00")
    b = m.build_decision_fitness_artifact(integrated_decision_artifact=source_b, requested_at="2026-10-01T18:00:00+07:00")

    assert a["artifact_identity"] == b["artifact_identity"]
    assert list(a["records"]) == ["AAA", "BBB"]
    assert a["authority_boundary"]["read_model_only"] is True
    assert a["authority_boundary"]["is_actionable"] is False
    assert "decision_fitness" not in source_a["records"]["AAA"]


def test_decision_fitness_rejects_wrong_contract():
    item = _item("AAA", m.CLASS_FULL)
    item["contract_version"] = "wrong/v1"
    with pytest.raises(ValueError, match="CURRENT_RESEARCH_DECISION_INPUT_CONTRACT_REQUIRED"):
        m.build_ticker_decision_fitness(item)


def test_decision_fitness_cli_runs_from_repo_root(tmp_path):
    source = {
        "session": "2026-10-01",
        "artifact_identity": "integrated_investment_decision_product:test",
        "records": {"AAA": _record(_item("AAA", m.CLASS_FULL))},
    }
    input_path = tmp_path / "integrated.json"
    output_path = tmp_path / "fitness.json"
    input_path.write_text(json.dumps(source), encoding="utf-8")

    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            "tools/build_current_research_decision_fitness.py",
            "--input", str(input_path),
            "--output", str(output_path),
            "--requested-at", "2026-10-01T18:00:00+07:00",
        ],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact["coverage"]["denominator_count"] == 1
    assert artifact["coverage"]["research_usable_count"] == 1
    assert "ARTIFACT_IDENTITY=current_research_coverage_decision_fitness:" in completed.stdout
