"""CI_HERMETIC_DEPENDENCY_AND_EVIDENCE_TIER_V1: dependency split, constraints, provider-import
block, test-tier markers and the CI workflow wiring.

Hermetic: tracked files, tmp_path and child interpreters only -- no network, no provider
packages, no retained evidence.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import _test_tiers as tiers

ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"
BLOCK_DIR = TESTS_DIR / "provider_import_block"
WORKFLOW = ROOT / ".github" / "workflows" / "producer-ci.yml"

sys.path.insert(0, str(ROOT / "tools"))
import verify_dependency_tiers as vdt  # noqa: E402


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _tracked_texts() -> tuple[str, str, str, str]:
    return (
        _read(vdt.CORE_REQUIREMENTS), _read(vdt.TEST_REQUIREMENTS),
        _read(vdt.PROVIDER_REQUIREMENTS), _read(vdt.CONSTRAINTS),
    )


def _child_env(**extra: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("STOCKLOOKUP_")}
    env.pop("PYTHONPATH", None)
    env.update(extra)
    return env


# ---------------------------------------------------------------------------------------------
# Dependency split and constraints
# ---------------------------------------------------------------------------------------------


def test_tracked_dependency_tiers_have_no_violation():
    assert vdt.static_violations(*_tracked_texts()) == []


def test_core_tier_declares_no_provider_package_and_providers_keep_vnstock():
    core, test, providers, _ = _tracked_texts()
    core_names = set(vdt.parse_requirement_names(core)) | set(vdt.parse_requirement_names(test))
    assert not core_names & {"vnstock", "vnai", "anthropic"}
    assert {"pandas", "numpy", "requests", "pyarrow", "openpyxl", "pytest"} <= core_names
    assert {"vnstock", "anthropic"} <= set(vdt.parse_requirement_names(providers))


def test_every_constraint_is_an_exact_pin_and_covers_the_core_closure():
    pins = vdt.parse_constraints(_read(vdt.CONSTRAINTS))
    for name in ("pandas", "numpy", "requests", "pyarrow", "openpyxl", "pytest", "packaging"):
        assert name in pins
    assert not set(pins) & vdt.PROVIDER_DISTRIBUTIONS


@pytest.mark.parametrize(
    ("core", "test", "providers", "constraints", "code"),
    [
        ("pandas>=2\nvnstock>=4\n", "pytest\n", "vnstock\n", "pandas==2.3.3\npytest==9.1.1\nvnstock==4.0.8\n", "PROVIDER_PACKAGE_IN_CORE_TIER"),
        ("pandas>=2\n", "pytest\nanthropic\n", "vnstock\n", "pandas==2.3.3\npytest==9.1.1\nanthropic==1\n", "PROVIDER_PACKAGE_IN_CORE_TIER"),
        ("pandas>=2\nnumpy\n", "pytest\n", "vnstock\n", "pandas==2.3.3\npytest==9.1.1\n", "CORE_REQUIREMENT_NOT_PINNED"),
        ("pandas>=2\n", "pytest\n", "anthropic\n", "pandas==2.3.3\npytest==9.1.1\n", "PROVIDER_REQUIREMENT_UNDECLARED"),
        ("pandas>=2\n", "pytest\n", "vnstock\n", "pandas==2.3.3\npytest==9.1.1\nvnai==2.6.1\n", "PROVIDER_PACKAGE_CONSTRAINED"),
        ("pandas>=2\n", "pytest\n", "vnstock\nrandom-lib\n", "pandas==2.3.3\npytest==9.1.1\n", "UNCLASSIFIED_PROVIDER_REQUIREMENT"),
        ("pandas>=2\n", "pytest\n", "vnstock\n", "pandas>=2.3\npytest==9.1.1\n", "DEPENDENCY_FILE_UNPARSEABLE"),
        ("-r other.txt\n", "pytest\n", "vnstock\n", "pytest==9.1.1\n", "DEPENDENCY_FILE_UNPARSEABLE"),
    ],
)
def test_static_violations_detect_each_tier_breach(core, test, providers, constraints, code):
    violations = vdt.static_violations(core, test, providers, constraints)
    assert any(line.startswith(code + ":") for line in violations), violations


def test_requirement_names_are_canonicalised_and_comments_ignored():
    text = "# header\nPyYAML>=6  # trailing\ncharset_normalizer==3.5.1\nfoo.bar ; python_version<'4'\n"
    assert vdt.parse_requirement_names(text) == ["pyyaml", "charset-normalizer", "foo-bar"]
    with pytest.raises(ValueError, match="duplicate"):
        vdt.parse_constraints("six==1.17.0\nSix==1.16.0\n")


def test_installed_violations_flag_drift_unpinned_and_missing(monkeypatch):
    monkeypatch.setattr(vdt, "_requirement_closure", lambda roots: {"a": "1.0", "b": "2.0", "c": "", "pip": "25"})
    monkeypatch.setattr(vdt, "BLOCKED_PROVIDER_MODULES", ())
    violations = vdt.installed_violations(["a"], {"a": "1.1"})
    assert any(line.startswith("INSTALLED_VERSION_DRIFT: a==1.0") for line in violations)
    assert any(line.startswith("INSTALLED_DISTRIBUTION_NOT_PINNED: b==2.0") for line in violations)
    assert any(line.startswith("CORE_DISTRIBUTION_NOT_INSTALLED: c") for line in violations)
    assert not any("pip" in line for line in violations)


def test_installed_violations_flag_an_importable_provider(monkeypatch):
    monkeypatch.setattr(vdt, "_requirement_closure", lambda roots: {})
    monkeypatch.setattr(vdt, "BLOCKED_PROVIDER_MODULES", ("json",))  # any importable stand-in
    assert vdt.installed_violations([], {}) == ["PROVIDER_MODULE_IMPORTABLE_IN_CORE_TIER: json"]


# ---------------------------------------------------------------------------------------------
# Provider-import block (tests/provider_import_block/sitecustomize.py)
# ---------------------------------------------------------------------------------------------


def test_blocked_provider_module_lists_agree():
    import ast

    tree = ast.parse((BLOCK_DIR / "sitecustomize.py").read_text(encoding="utf-8"))
    assigned = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    }
    assert assigned["BLOCKED_PROVIDER_MODULES"] == tiers.PROVIDER_RUNTIME_MODULES
    assert tuple(vdt.BLOCKED_PROVIDER_MODULES) == tiers.PROVIDER_RUNTIME_MODULES


_BLOCK_PROBE = textwrap.dedent(
    """
    import importlib, importlib.util, json, os, subprocess, sys
    results = {"active": os.environ.get("STOCKLOOKUP_PROVIDER_IMPORT_BLOCK")}
    for name in ("vnstock", "vnstock.api.quote", "vnai"):
        try:
            importlib.import_module(name)
            results[name] = "IMPORTED"
        except ModuleNotFoundError as exc:
            results[name] = str(exc)
    try:
        importlib.util.find_spec("vnstock")
        results["find_spec"] = "NO_ERROR"
    except ImportError as exc:
        results["find_spec"] = type(exc).__name__
    results["pandas_ok"] = importlib.import_module("pandas").__name__
    results["vnstock_in_sys_modules"] = "vnstock" in sys.modules
    child = subprocess.run(
        [sys.executable, "-c", "import vnstock"], capture_output=True, text=True, check=False,
    )
    results["child_returncode"] = child.returncode
    results["child_blocked"] = "PROVIDER_RUNTIME_BLOCKED:vnstock" in child.stderr
    print(json.dumps(results))
    """
)


def test_provider_import_block_refuses_vnstock_and_vnai_in_process_and_in_children():
    import json

    completed = subprocess.run(
        [sys.executable, "-c", _BLOCK_PROBE],
        capture_output=True, text=True, check=True, timeout=120,
        env=_child_env(PYTHONPATH=str(BLOCK_DIR)),
    )
    results = json.loads(completed.stdout.strip().splitlines()[-1])
    assert results["active"] == "ACTIVE"
    # A submodule import is refused at its top-level package, exactly like an absent package.
    for name, refused in (("vnstock", "vnstock"), ("vnstock.api.quote", "vnstock"), ("vnai", "vnai")):
        assert results[name].startswith(f"PROVIDER_RUNTIME_BLOCKED:{refused} "), results
    assert results["find_spec"] == "ModuleNotFoundError"
    assert results["pandas_ok"] == "pandas"
    assert results["vnstock_in_sys_modules"] is False
    assert results["child_returncode"] != 0 and results["child_blocked"] is True


def test_provider_import_block_is_opt_in_only():
    completed = subprocess.run(
        [sys.executable, "-c", "import os, sys; print(os.environ.get('STOCKLOOKUP_PROVIDER_IMPORT_BLOCK'), "
         "any(type(f).__name__ == 'ProviderImportBlocker' for f in sys.meta_path))"],
        capture_output=True, text=True, check=True, timeout=60, env=_child_env(),
    )
    assert completed.stdout.split() == ["None", "False"]


# ---------------------------------------------------------------------------------------------
# Test-tier markers (tests/_test_tiers.py), exercised as an isolated plugin in a child pytest
# ---------------------------------------------------------------------------------------------

_TIERED_TESTS = textwrap.dedent(
    """
    import pytest

    @pytest.mark.retained_evidence("evidence/present.json")
    def test_present_evidence_runs():
        assert True

    @pytest.mark.retained_evidence("evidence/present.json")
    def test_present_evidence_real_failure_still_fails():
        assert False, "GENUINE_REGRESSION"

    @pytest.mark.retained_evidence("evidence/present.json", "evidence/absent.json")
    def test_absent_evidence():
        raise AssertionError("must never run without its evidence")

    @pytest.mark.provider_runtime("vnstock")
    def test_needs_vnstock():
        raise AssertionError("must never run without vnstock")

    def test_hermetic():
        assert True
    """
)


def _run_tiered(tmp_path: Path, *args: str, source: str = _TIERED_TESTS, **env: str):
    (tmp_path / "evidence").mkdir(exist_ok=True)
    (tmp_path / "evidence" / "present.json").write_text("{}", encoding="utf-8")
    (tmp_path / "test_tiered.py").write_text(source, encoding="utf-8")
    junit = tmp_path / "junit.xml"
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "_test_tiers", "-p", "no:cacheprovider", "-q", "-rs",
         f"--junitxml={junit}", f"--rootdir={tmp_path}", "test_tiered.py", *args],
        cwd=tmp_path, capture_output=True, text=True, timeout=180,
        env=_child_env(PYTHONPATH=os.pathsep.join((str(BLOCK_DIR), str(TESTS_DIR))), **env),
    )
    outcomes: dict[str, tuple[str, str]] = {}
    if junit.is_file():
        for case in ET.parse(junit).getroot().iter("testcase"):
            status, message = "passed", ""
            for child in case:
                if child.tag in {"failure", "error", "skipped"}:
                    status, message = child.tag, (child.get("message") or "") + (child.text or "")
            outcomes[case.get("name")] = (status, message)
    return completed, outcomes


def test_strict_policy_fails_absent_evidence_and_runs_present_evidence(tmp_path):
    completed, outcomes = _run_tiered(tmp_path)
    assert completed.returncode == 1
    assert outcomes["test_present_evidence_runs"][0] == "passed"
    assert outcomes["test_present_evidence_real_failure_still_fails"][0] == "failure"
    assert "GENUINE_REGRESSION" in outcomes["test_present_evidence_real_failure_still_fails"][1]
    status, message = outcomes["test_absent_evidence"]
    assert status == "error" and "RETAINED_EVIDENCE_REQUIRED: evidence/absent.json" in message
    assert "evidence/present.json" not in message.split("is missing")[0]
    status, message = outcomes["test_needs_vnstock"]
    assert status == "skipped" and "PROVIDER_RUNTIME_ABSENT: vnstock" in message
    assert outcomes["test_hermetic"][0] == "passed"


def test_skip_if_absent_policy_skips_only_absent_evidence_with_explicit_reason(tmp_path):
    completed, outcomes = _run_tiered(tmp_path, STOCKLOOKUP_RETAINED_EVIDENCE_POLICY="skip-if-absent")
    status, message = outcomes["test_absent_evidence"]
    assert status == "skipped"
    assert "RETAINED_EVIDENCE_ABSENT: evidence/absent.json" in message
    # Present evidence is never skipped, and a genuine failure there still fails the run.
    assert outcomes["test_present_evidence_runs"][0] == "passed"
    assert outcomes["test_present_evidence_real_failure_still_fails"][0] == "failure"
    assert completed.returncode == 1
    assert "RETAINED_EVIDENCE_ABSENT: evidence/absent.json" in completed.stdout


def test_strict_provider_policy_fails_an_absent_provider(tmp_path):
    _, outcomes = _run_tiered(tmp_path, "-k", "vnstock", STOCKLOOKUP_PROVIDER_RUNTIME_POLICY="strict")
    status, message = outcomes["test_needs_vnstock"]
    assert status == "error" and "PROVIDER_RUNTIME_REQUIRED: vnstock" in message


def test_hermetic_marker_expression_deselects_both_tiers(tmp_path):
    completed, outcomes = _run_tiered(tmp_path, "-m", "not retained_evidence and not provider_runtime")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert set(outcomes) == {"test_hermetic"}
    assert "4 deselected" in completed.stdout


@pytest.mark.parametrize(
    ("marker", "expected"),
    [
        ("@pytest.mark.retained_evidence()", "must name its evidence paths"),
        ("@pytest.mark.retained_evidence('/abs/path.json')", "must be repository-relative"),
        ("@pytest.mark.retained_evidence('evidence/../../escape.json')", "must be repository-relative"),
        ("@pytest.mark.retained_evidence('C:/Projects/x.json')", "must be repository-relative"),
        ("@pytest.mark.retained_evidence('operations-review\\\\x.json')", "must use '/' separators"),
        ("@pytest.mark.provider_runtime()", "must name its modules"),
    ],
)
def test_malformed_tier_marker_is_a_usage_error_at_collection(tmp_path, marker, expected):
    source = f"import pytest\n\n{marker}\ndef test_x():\n    assert True\n"
    completed, _ = _run_tiered(tmp_path, source=source)
    assert completed.returncode == pytest.ExitCode.USAGE_ERROR
    assert expected in completed.stderr + completed.stdout


_QUARANTINED_TESTS = textwrap.dedent(
    """
    import pytest

    @pytest.mark.retained_evidence(
        "operations-review/integrated-investment-decision-product-v1-20260825/integrated_investment_decision_product_artifact.json")
    def test_quarantined_file():
        raise AssertionError("must never run against quarantined evidence")

    @pytest.mark.retained_evidence("operations-review/integrated-investment-decision-product-v1-20260904")
    def test_quarantined_folder():
        raise AssertionError("must never run against quarantined evidence")

    @pytest.mark.retained_evidence("evidence/present.json")
    def test_unquarantined():
        assert True
    """
)


@pytest.mark.parametrize("policy", ("strict", "skip-if-absent"))
def test_quarantined_retained_evidence_fails_under_every_policy_present_or_absent(tmp_path, policy):
    # The 09-04 folder exists in this scratch root and the 08-25 file does not: neither may run.
    (tmp_path / "operations-review" / "integrated-investment-decision-product-v1-20260904").mkdir(parents=True)
    completed, outcomes = _run_tiered(
        tmp_path, source=_QUARANTINED_TESTS, STOCKLOOKUP_RETAINED_EVIDENCE_POLICY=policy,
    )
    assert completed.returncode == 1
    for name, classification in (
        ("test_quarantined_file", "CONTAMINATED_UNRECOVERABLE"),
        ("test_quarantined_folder", "NON_PRISTINE_ORIGINAL_RECONSTRUCTABLE"),
    ):
        status, message = outcomes[name]
        assert status == "error" and "RETAINED_EVIDENCE_QUARANTINED" in message, (name, message)
        assert classification in message
    assert outcomes["test_unquarantined"][0] == "passed"


def test_retained_evidence_root_variable_is_where_presence_is_checked(tmp_path):
    source_root = tmp_path / "producer"
    (source_root / "evidence").mkdir(parents=True)
    (source_root / "evidence" / "absent.json").write_text("{}", encoding="utf-8")
    (source_root / "evidence" / "present.json").write_text("{}", encoding="utf-8")
    run_root = tmp_path / "worktree"
    run_root.mkdir()
    _, outcomes = _run_tiered(run_root, "-k", "absent_evidence", STOCKLOOKUP_RETAINED_EVIDENCE_ROOT=str(source_root))
    status, message = outcomes["test_absent_evidence"]
    # Present under the configured root, so the tier lets it run (and its own body fails).
    assert status == "failure" and "must never run without its evidence" in message


def test_unknown_policy_value_is_a_usage_error(tmp_path):
    completed, _ = _run_tiered(tmp_path, STOCKLOOKUP_RETAINED_EVIDENCE_POLICY="skip")
    assert completed.returncode == pytest.ExitCode.USAGE_ERROR
    assert "STOCKLOOKUP_RETAINED_EVIDENCE_POLICY='skip'" in completed.stderr + completed.stdout


# ---------------------------------------------------------------------------------------------
# Workflow wiring (text-level: the core tier has no YAML parser dependency)
# ---------------------------------------------------------------------------------------------


def test_workflow_installs_only_the_constrained_core_tier():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    code = "\n".join(line for line in workflow.splitlines() if not line.lstrip().startswith("#"))
    assert "requirements-providers.txt" not in code
    assert "CORE_INSTALL: python -m pip install -r requirements.txt -r requirements-test.txt -c constraints.txt" in workflow
    install_lines = [line.strip() for line in workflow.splitlines() if "pip install" in line and "--upgrade pip" not in line]
    assert install_lines == [
        "CORE_INSTALL: python -m pip install -r requirements.txt -r requirements-test.txt -c constraints.txt",
    ]
    assert workflow.count("run: ${{ env.CORE_INSTALL }}") == 4
    assert "PYTHONPATH: ${{ github.workspace }}/tests/provider_import_block" in workflow
    assert "python tools/verify_dependency_tiers.py --installed" in workflow
    assert "secrets." not in workflow


def test_workflow_separates_hermetic_and_retained_evidence_tiers():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "HERMETIC_MARKERS: not retained_evidence and not provider_runtime" in workflow
    lines = [line.strip().removeprefix("- ") for line in workflow.splitlines()]
    pytest_lines = [line for line in lines if line.startswith(("pytest ", "run: pytest "))]
    assert len(pytest_lines) == 4
    hermetic = [line for line in pytest_lines if '-m "${{ env.HERMETIC_MARKERS }}"' in line]
    retained = [line for line in pytest_lines if "-m retained_evidence" in line]
    assert len(hermetic) == 3 and len(retained) == 1
    assert "STOCKLOOKUP_RETAINED_EVIDENCE_POLICY: skip-if-absent" in workflow
    # Tiering replaces ad-hoc deselection of evidence-dependent tests.
    assert "--deselect" not in workflow


def test_every_focused_selection_entry_exists():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    block = workflow.split("FOCUSED_SELECTION: >-", 1)[1].split("\n\njobs:", 1)[0]
    entries = [line.strip() for line in block.splitlines() if line.strip()]
    assert entries and all(entry.startswith("tests/") for entry in entries)
    for entry in entries:
        path, _, node = entry.partition("::")
        assert (ROOT / path).is_file(), entry
        if node:
            assert f"def {node}(" in (ROOT / path).read_text(encoding="utf-8") or f"class {node}(" in (ROOT / path).read_text(encoding="utf-8"), entry
