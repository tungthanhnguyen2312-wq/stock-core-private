"""Source placement and relocated import contracts; never inspect runtime evidence."""
import ast
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = json.loads((ROOT / "config/repository_layout.json").read_text(encoding="utf-8"))


def test_root_python_additions_require_a_reviewed_placement_exception():
    allowed = set(LAYOUT["grandfathered_root_python"])
    actual = {p.name for p in ROOT.glob("*.py")}
    assert actual <= allowed, f"Place implementation in stocklookup_core/ or reusable tools in tools/: {actual - allowed}"


def test_dependency_direction_and_cycle_ratchet():
    from tools import check_architecture as guard
    policy = json.loads((ROOT / guard.POLICY).read_text(encoding="utf-8"))
    baseline = json.loads((ROOT / guard.BASELINE).read_text(encoding="utf-8"))
    assert not guard.regressions(guard.snapshot(ROOT, policy), baseline, policy, LAYOUT["relocations"])


def test_reviewed_path_launchers_survive_layout_changes():
    from tools.check_daily_launchers import check
    manifest = json.loads((ROOT / "config/daily_path_launchers.json").read_text(encoding="utf-8"))
    assert not check(ROOT, manifest)


def test_relocated_modules_have_one_implementation_and_resolve():
    for old, new in LAYOUT["relocations"].items():
        path = ROOT / new
        assert path.is_file(), new
        assert (path.parent / "__init__.py").is_file(), new
        spec = importlib.util.find_spec(new[:-3].replace("/", "."))
        assert spec is not None and Path(spec.origin).resolve() == path.resolve(), new
        if old not in LAYOUT["compatibility_entrypoints"]:
            assert not (ROOT / old).exists(), old


E1_OFFICIAL_EXCHANGE_EVIDENCE = (
    "corporate_action_events", "corporate_action_evidence_registry", "hnx_disclosure_feed_parser",
    "hnx_filing_evidence_binding", "hnx_financial_filing_scaleout", "hnx_multi_attachment_binding",
    "hnx_official_issuer_profile_multi_gate", "hose_source_surface_authority_qualification",
    "insider_and_major_holder_events", "official_authority_candidates", "official_issuer_disclosure_registry",
    "official_listing_page_parser", "real_official_corporate_action_factor_evidence",
)


def test_e1_official_exchange_evidence_has_no_root_path_or_shim():
    from tools import check_architecture as guard
    policy = json.loads((ROOT / guard.POLICY).read_text(encoding="utf-8"))
    for name in E1_OFFICIAL_EXCHANGE_EVIDENCE:
        assert LAYOUT["relocations"][name + ".py"] == f"stocklookup_core/evidence/{name}.py"
        assert name + ".py" not in LAYOUT["grandfathered_root_python"]
        assert name + ".py" not in LAYOUT["compatibility_entrypoints"]
        assert importlib.util.find_spec(name) is None, name
    carried = {row[0].rsplit(".", 1)[1] for row in policy["relocated_debt_edges"]}
    assert carried <= set(E1_OFFICIAL_EXCHANGE_EVIDENCE)


BULK = json.loads((ROOT / "tests/fixtures/bulk_root_package_consolidation_relocations.json").read_text(encoding="utf-8"))
BULK_V2 = json.loads((ROOT / "tests/fixtures/bulk_root_package_consolidation_v2_relocations.json").read_text(encoding="utf-8"))
HUB_V3 = json.loads((ROOT / "tests/fixtures/root_hub_dependency_reduction_v3_relocations.json").read_text(encoding="utf-8"))
# Accepted V1, V2 and V3 cohort maps stay separate fixtures; checks below cover their disjoint union.
BULK_RELOCATIONS = {**BULK["relocations"], **BULK_V2["relocations"], **HUB_V3["relocations"]}
assert len(BULK_RELOCATIONS) == len(BULK["relocations"]) + len(BULK_V2["relocations"]) + len(HUB_V3["relocations"])


def test_bulk_relocations_are_exact_without_root_path_shim_or_carried_debt():
    from tools import check_architecture as guard
    policy = json.loads((ROOT / guard.POLICY).read_text(encoding="utf-8"))
    carried = {row[0] for row in policy["relocated_debt_edges"]}
    for old, new in BULK_RELOCATIONS.items():
        assert LAYOUT["relocations"][old] == new
        assert old not in LAYOUT["grandfathered_root_python"] and old not in LAYOUT["compatibility_entrypoints"]
        assert not (ROOT / old).exists() and importlib.util.find_spec(old[:-3]) is None, old
        assert new.count("/") == 2 and new.startswith("stocklookup_core/"), new
        assert new[:-3].replace("/", ".") not in carried, new  # the E1 carry allowance is not extended


def test_root_names_imported_by_executed_historical_sources_are_not_relocated():
    """Parity harnesses and replays execute immutable accepted sources by their original import names."""
    import subprocess
    moved = {old[:-3] for old in BULK_RELOCATIONS}
    for name in BULK["retained_root_for_historical_execution"]:
        assert (ROOT / name).is_file() and name not in LAYOUT["relocations"], name
    for ref, relative in BULK["historically_executed_sources"]:
        source = subprocess.check_output(["git", "show", f"{ref}:{relative}"], cwd=ROOT)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names = [node.module]
            else:
                continue
            assert not moved.intersection(name.split(".")[0] for name in names), (ref, relative, names)


def _root_identity_only_hub_importers(seam):
    """Root modules importing only the field-identity primitives through the temporal hub path."""
    found = set()
    for path in ROOT.glob("*.py"):
        tree = ast.parse(path.read_bytes().decode("utf-8-sig"))
        nodes = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == seam["hub"] and not n.level]
        if nodes and all({a.name for a in n.names} <= set(seam["primitives"]) for n in nodes):
            found.add(path.name)
    return found


def test_field_identity_primitives_have_one_owner_and_hub_reexport_is_identical():
    """V3: the temporal hub re-exports, never re-implements, the field-identity primitives."""
    import importlib
    seam = HUB_V3["identity_seam"]
    owner = importlib.import_module(seam["owner"])
    hub = importlib.import_module(seam["hub"])
    for name in seam["primitives"]:
        assert getattr(hub, name) is getattr(owner, name), name
        assert getattr(owner, name).__module__ == seam["owner"], name
    # Only frozen/protected sources and Daily launcher targets keep the hub path for these names.
    assert _root_identity_only_hub_importers(seam) == set(seam["retained_hub_importers"])
    for new in HUB_V3["relocations"].values():
        tree = ast.parse((ROOT / new).read_bytes().decode("utf-8-sig"))
        assert not [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                    and seam["hub"] in ([a.name for a in n.names] if isinstance(n, ast.Import) else [n.module])], new


# Exact (module -> top-level package) pairs whose import chain needs a documented optional dependency
# outside the hermetic core install (docs/CI_AND_DEPENDENCY_TIERS.md "Undeclared optional imports").
# cited_evidence_backup -> evidence.official_document_retrieval -> `from pypdf import PdfReader`
# (unchanged from the E6 root module). Absence is tolerated only for that exact missing name.
OPTIONAL_IMPORT_DEPENDENCIES = {"stocklookup_core.evidence.cited_evidence_backup": "pypdf"}

_IMPORT_PROBE = r'''
import importlib, importlib.util, json, sys, traceback
modules, rooted, root, optional = json.loads(sys.argv[1])
report = {"failed": {}, "optional_absent": {}, "root_mismatch": {}}
for name in modules:  # one interpreter, the original manifest order
    try:
        importlib.import_module(name)
    except ModuleNotFoundError as error:
        missing = (error.name or "").split(".")[0]
        if optional.get(name) == missing and importlib.util.find_spec(missing) is None:
            report["optional_absent"][name] = missing
        else:
            report["failed"][name] = traceback.format_exc()
    except BaseException:
        report["failed"][name] = traceback.format_exc()
for name in rooted:
    value = getattr(sys.modules.get(name), "ROOT", None)
    if str(value) != root:
        report["root_mismatch"][name] = repr(value)
report["imported"] = sorted(name for name in modules if name in sys.modules)
report["providers"] = sorted(m for m in sys.modules if m.split(".")[0] in ("vnstock", "vnai"))
print("IMPORT_PROBE_REPORT=" + json.dumps(report, sort_keys=True))
'''


def test_bulk_relocated_modules_import_cleanly_and_keep_checkout_root(tmp_path):
    import os
    import subprocess
    import sys
    modules = [new[:-3].replace("/", ".") for new in BULK_RELOCATIONS.values()]
    assert len(modules) == len(set(modules)) == len(BULK_RELOCATIONS)
    assert set(OPTIONAL_IMPORT_DEPENDENCIES) <= set(modules)
    rooted = [m for m, new in zip(modules, BULK_RELOCATIONS.values())
              if "ROOT=Path(__file__).resolve().parents[2]" in (ROOT / new).read_text(encoding="utf-8").replace(" ", "")]
    assert not set(rooted) & set(OPTIONAL_IMPORT_DEPENDENCIES)
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(ROOT), os.environ.get("PYTHONPATH")]))}
    payload = json.dumps([modules, rooted, str(ROOT), OPTIONAL_IMPORT_DEPENDENCIES])
    completed = subprocess.run([sys.executable, "-c", _IMPORT_PROBE, payload], cwd=tmp_path, env=env,
                               capture_output=True, text=True, encoding="utf-8")
    diagnostic = f"exit={completed.returncode}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    assert completed.returncode == 0, diagnostic
    lines = [line for line in completed.stdout.splitlines() if line.startswith("IMPORT_PROBE_REPORT=")]
    assert len(lines) == 1, diagnostic
    report = json.loads(lines[0].split("=", 1)[1])
    assert report["failed"] == {}, "\n".join(f"{name}:\n{trace}" for name, trace in report["failed"].items())
    assert report["root_mismatch"] == {}, report["root_mismatch"]
    assert report["providers"] == [], report["providers"]
    absent = set(report["optional_absent"])
    assert report["imported"] == sorted(set(modules) - absent), set(modules) - absent - set(report["imported"])
    for name, package in report["optional_absent"].items():
        assert importlib.util.find_spec(package) is None, (name, package)  # never excused when installed


def test_import_probe_fails_on_missing_required_dependency_and_wrong_root(tmp_path):
    """Negative controls: the optional allowance is exact and the probe still detects real failures."""
    import os
    import subprocess
    import sys
    package = tmp_path / "probe_pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "needs_required.py").write_text("import surely_absent_required_dependency\n", encoding="utf-8")
    (package / "needs_optional.py").write_text("import surely_absent_optional_dependency\n", encoding="utf-8")
    (package / "wrong_root.py").write_text("ROOT = 'elsewhere'\n", encoding="utf-8")
    (package / "fine.py").write_text("ROOT = 'expected'\n", encoding="utf-8")
    modules = ["probe_pkg.needs_required", "probe_pkg.needs_optional", "probe_pkg.wrong_root", "probe_pkg.fine"]
    optional = {"probe_pkg.needs_optional": "surely_absent_optional_dependency",
                "probe_pkg.needs_required": "some_other_dependency"}
    payload = json.dumps([modules, ["probe_pkg.wrong_root", "probe_pkg.fine"], "expected", optional])
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(tmp_path), os.environ.get("PYTHONPATH")]))}
    completed = subprocess.run([sys.executable, "-c", _IMPORT_PROBE, payload], cwd=tmp_path, env=env,
                               capture_output=True, text=True, encoding="utf-8", check=True)
    report = json.loads(completed.stdout.splitlines()[-1].split("=", 1)[1])
    assert list(report["failed"]) == ["probe_pkg.needs_required"]
    assert "surely_absent_required_dependency" in report["failed"]["probe_pkg.needs_required"]
    assert report["optional_absent"] == {"probe_pkg.needs_optional": "surely_absent_optional_dependency"}
    assert report["root_mismatch"] == {"probe_pkg.wrong_root": "'elsewhere'"}
    assert report["imported"] == ["probe_pkg.fine", "probe_pkg.wrong_root"]


def test_recreated_root_copy_of_relocated_evidence_fails_placement(tmp_path, monkeypatch):
    (tmp_path / "corporate_action_events.py").write_text("", encoding="utf-8")
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    with pytest.raises(AssertionError, match="corporate_action_events.py"):
        test_root_python_additions_require_a_reviewed_placement_exception()


def test_relocated_imports_and_reflection_targets_are_not_stale():
    old_modules = {p[:-3] for p in LAYOUT["relocations"]}
    paths = list(ROOT.glob("*.py"))
    for folder in ("stocklookup_core", "tools", "tests"):
        paths.extend((ROOT / folder).rglob("*.py"))
    stale = []
    for path in paths:
        source = path.read_text(encoding="utf-8-sig")
        if not any(name in source for name in old_modules):
            continue
        for node in ast.walk(ast.parse(source)):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                names = [node.module]
            elif (isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                  and isinstance(node.iter, (ast.Tuple, ast.List))):
                imports_loop_target = any(
                    isinstance(call, ast.Call)
                    and isinstance(call.func, (ast.Name, ast.Attribute))
                    and ast.unparse(call.func).endswith(("import_module", "__import__"))
                    and call.args and isinstance(call.args[0], ast.Name)
                    and call.args[0].id == node.target.id
                    for statement in node.body for call in ast.walk(statement)
                )
                if imports_loop_target:
                    names = [value.value.split(".")[0] for value in node.iter.elts
                             if isinstance(value, ast.Constant) and isinstance(value.value, str)]
            elif isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute)):
                call = ast.unparse(node.func)
                if call.endswith(("import_module", "__import__", "patch")) and node.args:
                    value = node.args[0]
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        names = [value.value.split(".")[0]]
            if old_modules.intersection(names):
                stale.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not stale, stale


def test_import_loop_guard_detects_the_iid_fixture_regression(tmp_path, monkeypatch):
    source = (ROOT / "tests/test_iid_single_serialization.py").read_text(encoding="utf-8")
    fixture = tmp_path / "iid_fixture.py"
    fixture.write_text(source, encoding="utf-8")
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    test_relocated_imports_and_reflection_targets_are_not_stale()
    stale = source.replace("stocklookup_core.tactical.market_structure_breakout_product_projection",
                           "market_structure_breakout_product_projection", 1)
    assert stale != source
    fixture.write_text(stale, encoding="utf-8")
    with pytest.raises(AssertionError, match="iid_fixture.py"):
        test_relocated_imports_and_reflection_targets_are_not_stale()


def test_package_initializers_do_not_activate_runtime_work():
    for path in (ROOT / "stocklookup_core").rglob("__init__.py"):
        nodes = ast.parse(path.read_text(encoding="utf-8")).body
        assert all(isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                   and isinstance(n.value.value, str) for n in nodes), path


def test_packaged_defaults_still_use_checkout_root_after_cwd_change(tmp_path, monkeypatch):
    from stocklookup_core.financial import financial_operational_proxy, fundamental_cross_sectional_scoring
    from stocklookup_core.financial import fundamental_market_opportunity_ranking, fundamental_research_cohort_scaleout
    from stocklookup_core.financial import multi_period_financial_panel as panel
    from stocklookup_core.valuation import current_valuation_research_proxy
    from stocklookup_core.portfolio import private_portfolio_context
    monkeypatch.chdir(tmp_path)
    assert private_portfolio_context.REPOSITORY_ROOT == ROOT
    for module in (financial_operational_proxy, fundamental_cross_sectional_scoring,
                   fundamental_market_opportunity_ranking, fundamental_research_cohort_scaleout, current_valuation_research_proxy):
        assert module.ROOT == ROOT
    seen = []
    monkeypatch.setattr(panel, "load_promoted_sector_extractions",
                        lambda path: seen.append(path) or {"promoted_sectors": {}})
    panel.load_promoted_sector_citations()
    assert seen == [ROOT / "config/promoted_sector_extractions.json"]


W1 = json.loads((ROOT / "tests/fixtures/root_historical_surface_w1_relocations.json").read_text(encoding="utf-8"))


def test_w1_historical_surface_is_archived_under_tools_replay_without_root_shim():
    """Wave 1: historical runners, pilots and legacy materializers leave the root; nothing runs them Daily."""
    import subprocess
    launch = json.loads((ROOT / "config/daily_path_launchers.json").read_text(encoding="utf-8"))
    launched = {t["path"] for t in launch["targets"]}
    assert sorted(W1["relocations"]) == sorted(m for c in W1["cohorts"].values() for m in c["modules"])
    for old, new in W1["relocations"].items():
        assert LAYOUT["relocations"][old] == new and new not in BULK_RELOCATIONS.values()
        assert old not in LAYOUT["grandfathered_root_python"] and old not in LAYOUT["compatibility_entrypoints"]
        assert not (ROOT / old).exists() and importlib.util.find_spec(old[:-3]) is None, old
        assert new.startswith("tools/replay/") and new.count("/") == 3, new
        assert old not in launched and new not in launched, old
    moved = {old[:-3] for old in W1["relocations"]}
    for ref, relative in BULK["historically_executed_sources"]:
        source = subprocess.check_output(["git", "show", f"{ref}:{relative}"], cwd=ROOT)
        for node in ast.walk(ast.parse(source)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module] if isinstance(node, ast.ImportFrom) and node.module and not node.level else []
            assert not moved.intersection(n.split(".")[0] for n in names), (ref, relative, names)
