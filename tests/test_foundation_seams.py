"""Frozen baseline behavior, policy ownership and lightweight foundation boundaries."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from stocklookup_core.evidence import session_registry as registry
from stocklookup_core.evidence import temporal_freshness as temporal
from stocklookup_core.financial import period_freshness as financial
from stocklookup_core.valuation import freshness as valuation
from stocklookup_core.decision import opportunity_axis_freshness as legacy

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests/fixtures/e2e3_freshness_baseline.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_freshness_matches_immutable_e1_behavior(case):
    """Expected envelopes/errors were captured by executing E1, not the new code."""
    function = getattr(legacy, case["name"])
    try:
        value = function(**case["kwargs"])
        if case["name"] == "completed_quarter_lag":
            assert isinstance(value, tuple)
        outcome = {"value": value}
    except Exception as error:
        outcome = {"error_type": type(error).__name__, "error": str(error)}
    # JSON evidence encodes the original tuple as an array; its Python type is checked above.
    assert json.loads(json.dumps(outcome, ensure_ascii=False)) == case["result"]


def test_foundation_accepts_explicit_policy_without_owning_axes():
    assert not hasattr(temporal, "AXIS_CONTRACTS")
    kwargs = dict(axis="caller_defined_axis", decision_session="2026-10-11", source_session="2026-10-10")
    stale = temporal.classify_freshness(contract={"older_usable": False, "period_based": False}, **kwargs)
    usable = temporal.classify_freshness(contract={"older_usable": True, "period_based": False}, **kwargs)
    assert stale["freshness_status"] == "STALE_NOT_USABLE_FOR_THIS_AXIS"
    assert usable["freshness_status"] == "STALE_BUT_RESEARCH_USABLE"
    assert not stale["rewritten_as_current"] and not usable["rewritten_as_current"]
    with pytest.raises(ValueError, match="UNKNOWN_OPPORTUNITY_AXIS"):
        legacy.classify_axis_freshness(**kwargs)


def test_legacy_exports_and_domain_contracts_share_identity(monkeypatch):
    assert legacy.FutureInformationError is temporal.FutureInformationError
    assert legacy.completed_quarter_lag is temporal.completed_quarter_lag
    assert legacy.reporting_period_basis is temporal.reporting_period_basis
    assert legacy.classify_financial_period_freshness is financial.classify_financial_period_freshness
    assert legacy.axis_is_research_usable is valuation.axis_is_research_usable
    assert legacy.AXIS_CONTRACTS["fundamental"] is financial.FUNDAMENTAL_CONTRACT
    assert legacy.AXIS_CONTRACTS["valuation"] is valuation.VALUATION_CONTRACT
    monkeypatch.setitem(legacy.AXIS_CONTRACTS["fundamental"], "older_usable", False)
    assert not financial.classify_financial_period_freshness(
        source_period="2026-Q2", decision_session="2026-10-11", maximum_completed_quarter_lag=2
    )["older_evidence_usable"]
    monkeypatch.setitem(legacy.AXIS_CONTRACTS["valuation"], "older_usable", False)
    args = dict(decision_session="2026-10-11", source_session="2026-10-10")
    assert valuation.classify_valuation_freshness(**args) == legacy.classify_axis_freshness(axis="valuation", **args)
    with pytest.raises(legacy.FutureInformationError):
        temporal.assert_artifact_session_not_future("2026-10-12", decision_session="2026-10-11", label="source")


@pytest.mark.parametrize("reverse", [False, True])
def test_fresh_interpreter_import_orders_keep_compatibility(reverse):
    names = ["stocklookup_core.decision.opportunity_axis_freshness", "stocklookup_core.financial.period_freshness",
             "stocklookup_core.evidence.temporal_freshness", "stocklookup_core.valuation.freshness"]
    if reverse:
        names.reverse()
    script = "\n".join("import " + name for name in names) + "\n" + '''
from stocklookup_core.decision import opportunity_axis_freshness as old
from stocklookup_core.financial import period_freshness as new
from stocklookup_core.evidence import temporal_freshness as temporal
assert old.classify_financial_period_freshness is new.classify_financial_period_freshness
assert old.FutureInformationError is temporal.FutureInformationError
assert old.AXIS_CONTRACTS['fundamental'] is new.FUNDAMENTAL_CONTRACT
assert 'canonical_daily_operation' not in __import__('sys').modules
'''
    subprocess.run([sys.executable, "-c", script], cwd=ROOT, check=True, capture_output=True, text=True)


def test_registry_default_override_errors_and_legacy_callable(tmp_path, monkeypatch):
    from daily_research_session_operations import load_registry
    assert load_registry is registry.load_registry
    root = tmp_path / "root"
    (root / "config").mkdir(parents=True)
    path = root / "config/daily_research_session_input_registry.json"
    payload = {"contract_version": "daily_research_session_input_registry/v1", "sessions": {"α": None}}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    monkeypatch.chdir(foreign)
    assert load_registry(root) == payload == registry.load_registry(root)
    override = tmp_path / "override.json"
    override.write_text(json.dumps(dict(payload, sessions={"β": 0})), encoding="utf-8")
    assert registry.load_registry(root, override)["sessions"] == {"β": 0}
    assert path.read_text(encoding="utf-8") == json.dumps(payload, ensure_ascii=False)
    for text, error, match in [("{}", ValueError, "SESSION_INPUT_REGISTRY_CONTRACT_INVALID"),
                               ("[1]", AttributeError, "get"), ("{bad", json.JSONDecodeError, None)]:
        override.write_text(text, encoding="utf-8")
        with pytest.raises(error, match=match):
            registry.load_registry(root, override)
    with pytest.raises(FileNotFoundError):
        registry.load_registry(root, tmp_path / "missing.json")


def test_foundation_imports_do_not_load_orchestration_or_domain_policy():
    script = '''
import sys
from stocklookup_core.evidence import session_registry, temporal_freshness
assert not any(name.startswith(('stocklookup_core.decision.', 'stocklookup_core.financial.',
                                'stocklookup_core.valuation.')) for name in sys.modules)
assert 'daily_research_session_operations' not in sys.modules
assert 'prospective_decision_retention' not in sys.modules
'''
    subprocess.run([sys.executable, "-c", script], cwd=ROOT, check=True, capture_output=True, text=True)
    for filename in ("session_registry.py", "temporal_freshness.py"):
        tree = ast.parse((ROOT / "stocklookup_core/evidence" / filename).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name.split(".")[0] in sys.stdlib_module_names for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0 and node.module.split(".")[0] in sys.stdlib_module_names


def test_frozen_source_and_relocation_contracts_remain_exact():
    manifest = json.loads((ROOT / "tests/fixtures/e2e3_frozen_sources.json").read_text(encoding="utf-8"))
    for filename, expected in manifest["source_sha256_lf"].items():
        from tools.verify_retention_reader_transition import historical_bytes
        assert hashlib.sha256(historical_bytes(ROOT, filename)).hexdigest() == expected, filename
    layout = json.loads((ROOT / "config/repository_layout.json").read_text(encoding="utf-8"))
    # Every addition belongs to an exact reviewed, pairwise-disjoint cohort map.
    bulk = json.loads((ROOT / "tests/fixtures/bulk_root_package_consolidation_relocations.json").read_text(encoding="utf-8"))
    bulk_v2 = json.loads((ROOT / "tests/fixtures/bulk_root_package_consolidation_v2_relocations.json").read_text(encoding="utf-8"))
    hub_v3 = json.loads((ROOT / "tests/fixtures/root_hub_dependency_reduction_v3_relocations.json").read_text(encoding="utf-8"))
    w1 = json.loads((ROOT / "tests/fixtures/root_historical_surface_w1_relocations.json").read_text(encoding="utf-8"))
    w2 = json.loads((ROOT / "tests/fixtures/source_root_dependency_wave2_relocations.json").read_text(encoding="utf-8"))
    w3 = json.loads((ROOT / "tests/fixtures/root_tool_engine_w3_relocations.json").read_text(encoding="utf-8"))
    groups = [manifest["relocations"], bulk["relocations"], bulk_v2["relocations"], hub_v3["relocations"], w1["relocations"], w2["relocations"], w3["relocations"], layout["root_consolidation_v4"]["relocations"], layout["root_dependency_breakout_v5"]["relocations"]]
    assert sum(map(len, groups)) == len(set().union(*groups))  # pairwise disjoint accepted maps
    assert layout["relocations"] == {k: v for group in groups for k, v in group.items()}


@pytest.mark.parametrize("target", ["orchestrator", "stocklookup_core.decision.policy", "tools.runner"])
def test_new_upward_dependencies_from_foundation_fail_closed(tmp_path, target):
    from tools import check_architecture as guard
    policy = json.loads((ROOT / guard.POLICY).read_text(encoding="utf-8"))
    path = tmp_path / (target.replace(".", "/") + ".py")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    baseline = guard.snapshot(tmp_path, policy)
    path = tmp_path / "stocklookup_core/evidence/foundation.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("import " + target + "\n", encoding="utf-8")
    assert any("NEW_BACKWARD_DEPENDENCY" in error for error in
               guard.regressions(guard.snapshot(tmp_path, policy), baseline, policy))
