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


def test_relocated_modules_have_one_implementation_and_resolve():
    for old, new in LAYOUT["relocations"].items():
        path = ROOT / new
        assert path.is_file(), new
        assert (path.parent / "__init__.py").is_file(), new
        spec = importlib.util.find_spec(new[:-3].replace("/", "."))
        assert spec is not None and Path(spec.origin).resolve() == path.resolve(), new
        if old not in LAYOUT["compatibility_entrypoints"]:
            assert not (ROOT / old).exists(), old


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
    monkeypatch.chdir(tmp_path)
    for module in (financial_operational_proxy, fundamental_cross_sectional_scoring,
                   fundamental_market_opportunity_ranking, fundamental_research_cohort_scaleout, current_valuation_research_proxy):
        assert module.ROOT == ROOT
    seen = []
    monkeypatch.setattr(panel, "load_promoted_sector_extractions",
                        lambda path: seen.append(path) or {"promoted_sectors": {}})
    panel.load_promoted_sector_citations()
    assert seen == [ROOT / "config/promoted_sector_extractions.json"]
