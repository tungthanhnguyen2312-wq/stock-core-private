"""Adversarial dependency/path checks; fixture edits never touch production files."""
import json
from pathlib import Path

import pytest

from tools import check_architecture as guard
from tools import check_daily_launchers as launchers

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / guard.POLICY).read_text(encoding="utf-8"))


def write(root, relative, source):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_repository_dependency_ratchet():
    baseline = json.loads((ROOT / guard.BASELINE).read_text(encoding="utf-8"))
    assert not guard.regressions(guard.snapshot(ROOT, POLICY), baseline, POLICY)


def test_baseline_is_byte_deterministic_and_portable(tmp_path, monkeypatch):
    write(tmp_path, "a.py", "import b\n")
    write(tmp_path, "b.py", "")
    first = guard.encode(guard.snapshot(tmp_path, POLICY))
    monkeypatch.chdir(tmp_path.parent)
    assert guard.encode(guard.snapshot(tmp_path, POLICY)) == first
    assert guard.module_name("stocklookup_core\\evidence\\__init__.py") == "stocklookup_core.evidence"
    assert str(tmp_path) not in first


def test_new_backward_dependency_rejected(tmp_path):
    write(tmp_path, "stocklookup_core/evidence/a.py", "")
    write(tmp_path, "tools/b.py", "")
    baseline = guard.snapshot(tmp_path, POLICY)
    write(tmp_path, "stocklookup_core/evidence/a.py", "import tools.b\n")
    assert any("NEW_BACKWARD_DEPENDENCY" in e for e in guard.regressions(guard.snapshot(tmp_path, POLICY), baseline, POLICY))


def test_new_eager_cycle_rejected_and_old_cycle_preserved(tmp_path):
    write(tmp_path, "a.py", "import b\n")
    write(tmp_path, "b.py", "import a\n")
    write(tmp_path, "c.py", "")
    baseline = guard.snapshot(tmp_path, POLICY)
    assert not guard.regressions(guard.snapshot(tmp_path, POLICY), baseline, POLICY)
    write(tmp_path, "a.py", "import b\nimport c\n")
    write(tmp_path, "c.py", "import a\n")
    assert any("NEW_EAGER_CYCLE" in e for e in guard.regressions(guard.snapshot(tmp_path, POLICY), baseline, POLICY))


def test_new_edge_inside_old_scc_is_not_a_baseline_bypass(tmp_path):
    for name, target in [("a", "b"), ("b", "c"), ("c", "a")]:
        write(tmp_path, name + ".py", "import " + target)
    baseline = guard.snapshot(tmp_path, POLICY)
    write(tmp_path, "a.py", "import b\nimport c")
    assert any("NEW_EAGER_CYCLE" in e for e in guard.regressions(guard.snapshot(tmp_path, POLICY), baseline, POLICY))


def test_lazy_to_eager_cycle_promotion_rejected(tmp_path):
    write(tmp_path, "a.py", "import b")
    write(tmp_path, "b.py", "def f():\n import a")
    baseline = guard.snapshot(tmp_path, POLICY)
    write(tmp_path, "b.py", "import a")
    assert any("NEW_EAGER_CYCLE" in e for e in guard.regressions(guard.snapshot(tmp_path, POLICY), baseline, POLICY))


def test_relative_type_lazy_and_dynamic_imports(tmp_path):
    write(tmp_path, "stocklookup_core/evidence/__init__.py", '"""package"""')
    write(tmp_path, "stocklookup_core/evidence/b.py", "")
    write(tmp_path, "stocklookup_core/evidence/a.py", """from typing import TYPE_CHECKING as TC
from importlib import import_module as load
from . import b
if TC:
 import stocklookup_core.evidence.b
def f():
 from .b import value
 load('stocklookup_core.evidence.b')
load(unknown)
for name in ('stocklookup_core.evidence.b',):
 load(name)
""")
    data = guard.scan(tmp_path)
    edges = [e for e in data["edges"] if e[0].endswith(".a") and e[1].endswith(".b")]
    assert {e[2] for e in edges} == {"module_load", "lazy", "type_checking"}
    assert {e[3] for e in edges} == {"static", "dynamic"}
    assert len(data["unresolved_dynamic"]) == 1


def test_default_dynamic_import_evaluates_at_module_load(tmp_path):
    write(tmp_path, "a.py", "import importlib\ndef f(x=importlib.import_module('b')):\n pass")
    write(tmp_path, "b.py", "")
    assert ["a", "b", "module_load", "dynamic", "import_module"] in [list(e) for e in guard.scan(tmp_path)["edges"]]


def test_new_unresolved_dynamic_requires_review(tmp_path):
    write(tmp_path, "a.py", "")
    baseline = guard.snapshot(tmp_path, POLICY)
    write(tmp_path, "a.py", "__import__(name)")
    assert any("NEW_UNRESOLVED_DYNAMIC" in e for e in guard.regressions(guard.snapshot(tmp_path, POLICY), baseline, POLICY))


def test_parameter_shadowing_does_not_invent_a_resolved_dynamic_edge(tmp_path):
    write(tmp_path, "b.py", "")
    write(tmp_path, "a.py", "name='b'\ndef f(name):\n __import__(name)")
    data = guard.scan(tmp_path)
    assert not data["edges"]
    assert len(data["unresolved_dynamic"]) == 1


def test_conditional_name_does_not_hide_an_unknown_dynamic_target(tmp_path):
    write(tmp_path, "a.py", "name='b'\nif condition:\n name='c'\n__import__(name)")
    write(tmp_path, "b.py", "")
    write(tmp_path, "c.py", "")
    data = guard.scan(tmp_path)
    assert not data["edges"]
    assert len(data["unresolved_dynamic"]) == 1


def test_candidate_cannot_overwrite_enforced_baseline(tmp_path):
    write(tmp_path, guard.POLICY, json.dumps(POLICY))
    with pytest.raises(SystemExit):
        guard.main(["--root", str(tmp_path), "--write-candidate", str(tmp_path / guard.BASELINE)])


def test_reviewed_daily_path_set_exists_and_compiles():
    manifest = json.loads((ROOT / "config/daily_path_launchers.json").read_text(encoding="utf-8"))
    assert len(manifest["targets"]) == 31
    assert not launchers.check(ROOT, manifest)


@pytest.mark.parametrize("displacement", ["deleted", "stocklookup_core/macro/macro_sync.py"])
def test_missing_or_mislocated_macro_launcher_fails(tmp_path, displacement):
    write(tmp_path, "canonical_daily_operation.py", "argv=[py, str(root / 'macro_sync.py')]")
    manifest = {"targets": [{"path": "macro_sync.py"}], "python_callers": {"canonical_daily_operation.py": ["macro_sync.py"]}}
    write(tmp_path, "macro_sync.py", "print('fixture')")
    assert not launchers.check(tmp_path, manifest)
    if displacement == "deleted":
        (tmp_path / "macro_sync.py").unlink()
    else:
        destination = tmp_path / displacement
        destination.parent.mkdir(parents=True)
        (tmp_path / "macro_sync.py").rename(destination)
    assert launchers.check(tmp_path, manifest) == ["MISSING_PATH_LAUNCHER:macro_sync.py"]


def test_launcher_path_change_is_detected_even_if_old_file_survives(tmp_path):
    write(tmp_path, "macro_sync.py", "")
    write(tmp_path, "caller.py", "argv=[py, str(root / 'stocklookup_core' / 'macro' / 'macro_sync.py')]")
    manifest = {"targets": [{"path": "macro_sync.py"}], "python_callers": {"caller.py": ["macro_sync.py"]}}
    assert "LAUNCH_PATH_CONTRACT_CHANGED:caller.py:macro_sync.py" in launchers.check(tmp_path, manifest)


def test_launcher_parsing_handles_both_path_separators_and_ignores_prose():
    assert launchers.argv_references('argv=[py, "tools\\\\child.py"]') == {"tools/child.py"}
    assert launchers.argv_references('"""macro_sync.py"""\n# macro_sync.py') == set()
    with pytest.raises(ValueError):
        launchers.portable_path("../macro_sync.py")
