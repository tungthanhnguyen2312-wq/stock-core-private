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
    write(tmp_path, "canonical_daily_operation.py", "import subprocess\nargv=[py, str(root / 'macro_sync.py')]\nsubprocess.run(argv)")
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
    assert launchers.argv_references('import subprocess\nsubprocess.run([py, "tools\\\\child.py"])') == {"tools/child.py"}
    assert launchers.argv_references('"""macro_sync.py"""\n# macro_sync.py') == set()
    with pytest.raises(ValueError):
        launchers.portable_path("../macro_sync.py")


@pytest.mark.parametrize('source', [
    "import importlib.util as u; u.spec_from_file_location('m','tools/b.py')",
    "import importlib.util; importlib.util.spec_from_file_location('m','tools/b.py')",
    "from importlib import util; util.spec_from_file_location('m','tools/b.py')",
    "from importlib.util import spec_from_file_location; spec_from_file_location('m','tools/b.py')",
    "from importlib.util import spec_from_file_location as load; load('m','tools/b.py')",
    "import importlib as il; il.import_module('tools.b')",
    "from importlib import import_module as load; load(name='tools.b')",
    "__import__('tools.b')",
    "__builtins__.__import__('tools.b')",
    "__import__('tools',fromlist=['b'])",
    "from builtins import __import__ as load; load('tools.b')",
    "import importlib.machinery as m; m.SourceFileLoader('b','tools/b.py')",
    "from importlib.machinery import SourceFileLoader as L; L('b','tools/b.py')",
    "import runpy as r; r.run_path('tools/b.py')",
    "import runpy as r; r.run_module('tools.b')",
    "import importlib.util as u\nload: object = u.spec_from_file_location\nload('b','tools/b.py')",
    "from runpy import run_path as r; r(path_name='tools/b.py')",
    "from importlib import util as u; load=u.spec_from_file_location; load('b','tools/'+'b.py')",
    "import importlib.util as u; getattr(u,'spec_from_file_location')('b','tools/b.py')",
])
def test_equivalent_loaders_cannot_add_backward_dependency(tmp_path, source):
    write(tmp_path, 'stocklookup_core/evidence/a.py', '')
    write(tmp_path, 'tools/b.py', '')
    before = guard.snapshot(tmp_path, POLICY)
    write(tmp_path, 'stocklookup_core/evidence/a.py', source)
    errors = guard.regressions(guard.snapshot(tmp_path, POLICY), before, POLICY)
    assert any('NEW_BACKWARD_DEPENDENCY' in error for error in errors)


@pytest.mark.parametrize('source', [
    "import importlib.util as u; u.spec_from_file_location('b',root/name)",
    "from runpy import run_path as r; r(path)",
    "import importlib; importlib.import_module(name=unknown)",
    "__import__('b', level=1)",
    "__import__('tools',fromlist=unknown)",
    "import importlib.util as u; getattr(u,unknown)('b')",
    "exec(source)", "eval(source)",
    "__builtins__['__import__'](name)",
    "from importlib import *\nimport_module('tools.b')",
    "__import__=unknown; __import__(name)",
    "import builtins as b; b.__dict__[unknown](name)",
    "import importlib.util as u; u.__dict__['spec_from_file_location']('b',path)",
    "import importlib.machinery as m; m.SourcelessFileLoader('b',path)",
    "if flag:\n from importlib.util import spec_from_file_location as load\nelse:\n from os import path as load\nload('b',path)",
    "import importlib.util as u; load=u.spec_from_file_location; load=unknown; load('b',path)",
])
def test_unknown_or_unsupported_dynamic_site_requires_exact_review(tmp_path, source):
    write(tmp_path, 'a.py', '')
    before = guard.snapshot(tmp_path, POLICY)
    write(tmp_path, 'a.py', source)
    after = guard.snapshot(tmp_path, POLICY)
    assert guard.regressions(after, before, POLICY)
    assert not guard.regressions(after, after, POLICY)


def test_external_import_and_non_loader_importlib_use_are_not_dependencies(tmp_path):
    write(tmp_path, 'a.py', "import importlib.util as u\nu.find_spec('requests')\n__import__('json')")
    after = guard.scan(tmp_path)
    assert not after['edges'] and not after['unresolved_dynamic']
    assert {row[3] for row in after['dynamic_sites']} == {'external'}


def test_alias_and_formatting_do_not_change_review_identity(tmp_path):
    write(tmp_path, 'a.py', "import importlib.util as u\nu.spec_from_file_location('b', unknown)")
    before = guard.snapshot(tmp_path, POLICY)
    write(tmp_path, 'a.py', "# formatting\nfrom importlib.util import spec_from_file_location as load\nload( 'b',unknown )")
    assert not guard.regressions(guard.snapshot(tmp_path, POLICY), before, POLICY)


def test_migration_uses_old_sources_and_rejects_different_anchor(tmp_path,monkeypatch):
    import subprocess,hashlib
    def git(*args):
        return subprocess.check_output(['git','-C',str(tmp_path),*args],text=True).strip()
    git('init')
    write(tmp_path,'stocklookup_core/evidence/a.py','')
    write(tmp_path,'tools/b.py','')
    prior = guard.encode(guard.snapshot(tmp_path,POLICY))
    write(tmp_path,guard.BASELINE,prior)
    git('add','.')
    git('-c','user.name=Fixture','-c','user.email=fixture@example.test','commit','-m','accepted fixture')
    accepted = git('rev-parse','HEAD')
    monkeypatch.setattr(guard,'MIGRATION_CHECKPOINT',accepted)
    monkeypatch.setattr(guard,'PRIOR_BASELINE_SHA256',hashlib.sha256(prior.encode()).hexdigest())
    migrated = guard.baseline_from_checkpoint(tmp_path,accepted,POLICY)
    write(tmp_path,'stocklookup_core/evidence/a.py','import tools.b')
    assert guard.encode(migrated) == guard.encode(guard.baseline_from_checkpoint(tmp_path,accepted,POLICY))
    assert guard.regressions(guard.snapshot(tmp_path,POLICY),migrated,POLICY)
    git('add','.')
    git('-c','user.name=Fixture','-c','user.email=fixture@example.test','commit','-m','unaccepted candidate')
    with pytest.raises(ValueError): guard.baseline_from_checkpoint(tmp_path,git('rev-parse','HEAD'),POLICY)


def test_baseline_identity_rejects_new_permissions_without_historical_git(monkeypatch):
    data = json.loads((ROOT/guard.BASELINE).read_text())
    def forbidden_git(*args,**kwargs): raise AssertionError('ordinary identity check must not need old Git objects')
    monkeypatch.setattr(guard.subprocess,'check_output',forbidden_git)
    assert guard.baseline_identity_valid(data)
    data['grandfathered_violations'].append(['stocklookup_core.evidence.NEW','tools.NEW','module_load','dynamic','file_load'])
    assert not guard.baseline_identity_valid(data)


@pytest.mark.parametrize('command', [
    "KEEP=('macro_sync.py',)\nargv=[py,str(root/'other.py')]\nsubprocess.run(argv)",
    "argv=[py,'macro_sync.py']",  # never dispatched
    "KEEP=['macro_sync.py']\nsubprocess.run([py,'other.py'])",
    "subprocess.run([py,'-m','macro_sync.py'])",
    "subprocess.run([py,'-c','print(1)','macro_sync.py'])",
    "argv=[py,'macro_sync.py']\nargv[1]='other.py'\nsubprocess.run(argv)",
    "subprocess.run([py,*unknown,'macro_sync.py'])",
])
def test_stale_literals_cannot_establish_invocation(tmp_path, command):
    write(tmp_path, 'macro_sync.py', '')
    write(tmp_path, 'caller.py', 'import subprocess\n' + command)
    manifest = {'targets': [{'path':'macro_sync.py'}], 'python_callers': {'caller.py':['macro_sync.py']}}
    assert launchers.check(tmp_path, manifest)


def test_valid_delegated_dispatch_and_python_flags(tmp_path):
    write(tmp_path, 'macro_sync.py', '')
    write(tmp_path, 'caller.py', "import subprocess\ndef dispatch(argv):\n return subprocess.run(argv)\nargv=[py,'-I','-X','utf8',str(root/'macro_sync.py')]\ndispatch(argv)")
    manifest = {'targets': [{'path':'macro_sync.py'}], 'python_callers': {'caller.py':['macro_sync.py']}}
    assert not launchers.check(tmp_path, manifest)


def test_bounded_dynamic_caller_requires_exact_reviewed_source(tmp_path):
    source = "import subprocess\nTASKS={'a':'macro_sync.py'}\nsubprocess.run(make_command(TASKS))"
    write(tmp_path, 'macro_sync.py', '')
    path = write(tmp_path, 'caller.py', source)
    manifest = {'targets':[{'path':'macro_sync.py'}], 'python_callers':{'caller.py':['macro_sync.py']}}
    assert launchers.check(tmp_path, manifest)
    manifest['bounded_callers'] = {'caller.py':{'ast_sha256':launchers.ast_digest(source),'targets':['macro_sync.py']}}
    assert not launchers.check(tmp_path, manifest)
    path.write_text(source.replace('make_command(TASKS)', "[py,'other.py']"))
    assert 'BOUNDED_LAUNCH_CONTRACT_CHANGED:caller.py' in launchers.check(tmp_path, manifest)


def test_non_python_command_changes_cannot_keep_stale_literal(tmp_path):
    import hashlib
    source = b'REM macro_sync.py\npython macro_sync.py\n'
    path = write(tmp_path, 'launch.bat', source.decode())
    manifest = {'targets':[], 'python_callers':{}, 'non_python_callers': {'launch.bat':{'sha256':hashlib.sha256(source).hexdigest()}}}
    assert not launchers.check(tmp_path, manifest)
    path.write_text('REM macro_sync.py\npython other.py\n')
    assert launchers.check(tmp_path, manifest)
