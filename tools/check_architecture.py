"""Offline AST ratchet, extending config/repository_layout.json; imports no product code.

--write-candidate writes a review artifact, never overwrites the enforced baseline.
Deliberate relocation requires reviewing its diff alongside the layout manifest.
"""
from __future__ import annotations

import argparse
import ast
import json
import hashlib
import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "config/architecture_dependency_baseline.json"
POLICY = "config/architecture_dependency_policy.json"
LAYOUT = "config/repository_layout.json"
MIGRATION_CHECKPOINT = "d2ba70324a5d458091ac54549466a9bec57d6434"
MIGRATED_BASELINE_SHA256 = '6b3eed9a1236481cf02fec38bd76553ea7ba56d4bd86918d4c37c1695aa19dbf'
PRIOR_BASELINE_SHA256 = "749a59996a4d245ea3056289c5d59f443bf2ca60f7b61fe8dc4217f951772b26"


def module_name(path: str) -> str:
    parts = list(PurePosixPath(path.replace("\\", "/")).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def source_paths(root: Path) -> list[Path]:
    paths = list(root.glob("*.py"))
    for folder in ("tools", "stocklookup_core"):
        paths.extend((root / folder).rglob("*.py"))
    return sorted(paths, key=lambda p: p.relative_to(root).as_posix())


def layer(module: str) -> str:
    parts = module.split(".")
    if parts[0] == "stocklookup_core":
        return parts[1] if len(parts) > 1 else "package"
    return "tools" if parts[0] == "tools" else "root"


class ImportVisitor(ast.NodeVisitor):
    def __init__(self, source: str, modules: set[str], package: str):
        self.source, self.modules, self.package = source, modules, package
        self.context = "module_load"
        self.edges: set[tuple[str, ...]] = set()
        self.unresolved: set[tuple[str, ...]] = set()
        self.bindings: dict[str, object] = {}
        self.symbols = {"__builtins__": "builtins", "__import__": "builtins.__import__", "exec": "builtins.exec", "eval": "builtins.eval"}
        self.dynamic_sites: set[tuple[str, ...]] = set()
        self.typing_names = {"TYPE_CHECKING", "typing.TYPE_CHECKING"}

    def literal(self, node):
        if isinstance(node, ast.Name):
            return self.bindings.get(node.id)
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            values = [self.literal(n) for n in node.elts]
            return values if all(v is not None for v in values) else None
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = self.literal(node.left), self.literal(node.right)
            if isinstance(left, str) and isinstance(right, str):
                return left + right
        return None

    def resolve(self, name: str) -> str:
        if not name.startswith("."):
            return name
        count = len(name) - len(name.lstrip("."))
        parts = self.package.split(".") if self.package else []
        if count > len(parts):
            raise ValueError(f"Invalid relative import in {self.source}: {name}")
        return ".".join(parts[:len(parts) - count + 1] + [name[count:]]).rstrip(".")

    def edge(self, name: str, kind: str, form: str):
        name = self.resolve(name)
        parts = name.split(".")
        # importing a child also executes its package initializers
        for index in range(1, len(parts) + 1):
            target = ".".join(parts[:index])
            if target in self.modules:
                self.edges.add((self.source, target, self.context, kind, form))

    def bind_symbol(self, name, origin):
        old = self.symbols.get(name)
        if old and old.startswith(('importlib', 'runpy', 'builtins.__import__', 'builtins.exec', 'builtins.eval')) and old != origin:
            self.symbols[name] = old if '.<computed>' in old else old + '.<computed>'
        else:
            self.symbols[name] = origin

    def visit_Import(self, node):
        for alias in node.names:
            self.edge(alias.name, "static", "import")
            self.bind_symbol(alias.asname or alias.name.split('.')[0], alias.name if alias.asname else alias.name.split('.')[0])
            if alias.name == "typing" and alias.asname:
                self.typing_names.add(alias.asname + ".TYPE_CHECKING")

    def visit_ImportFrom(self, node):
        base = self.resolve("." * node.level + (node.module or ""))
        self.edge(base, "static", "from")
        for alias in node.names:
            if alias.name == '*' and base in {'importlib', 'importlib.util', 'importlib.machinery', 'runpy', 'builtins'}:
                self.dynamic_sites.add((self.source, self.context, base + '.*', 'unsupported', ast.dump(node, include_attributes=False)))
            self.edge(base + "." + alias.name, "static", "from")
            self.bind_symbol(alias.asname or alias.name, base + "." + alias.name)
            if base == "typing" and alias.name == "TYPE_CHECKING":
                self.typing_names.add(alias.asname or alias.name)

    def visit_Assign(self, node):
        self.visit(node.value)
        value = self.literal(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.bindings[target.id] = value
                symbol = self.symbol(node.value)
                if symbol:
                    self.bind_symbol(target.id, symbol)
                elif target.id in self.symbols and self.symbols[target.id].startswith(('importlib', 'runpy', 'builtins.__import__', 'builtins.exec', 'builtins.eval')):
                    if '.<computed>' not in self.symbols[target.id]:
                        self.symbols[target.id] += '.<computed>'

    def visit_AnnAssign(self, node):
        self.visit(node.annotation)
        if node.value is not None:
            self.visit_Assign(ast.Assign(targets=[node.target], value=node.value))

    def symbol(self, node):
        if isinstance(node, ast.Name):
            return self.symbols.get(node.id)
        if isinstance(node, ast.Attribute):
            base = self.symbol(node.value)
            return base + '.' + node.attr if base else None
        if isinstance(node, ast.Subscript):
            base = self.symbol(node.value)
            return base + '.<computed>' if base and base.startswith(('importlib', 'runpy', 'builtins')) else None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'getattr' and len(node.args) >= 2:
            base = self.symbol(node.args[0])
            member = self.literal(node.args[1])
            return base + '.' + member if base and isinstance(member, str) else base + '.<computed>' if base else None
        if isinstance(node, ast.Call) and self.symbol(node.func) == 'importlib.machinery.SourceFileLoader':
            return 'importlib.machinery.SourceFileLoader.instance'
        return None

    def file_target(self, node):
        value = self.literal(node)
        if isinstance(value, str):
            normalized = value.replace('\\', '/')
            if ':' not in normalized and not normalized.startswith('/') and '..' not in PurePosixPath(normalized).parts:
                return module_name(normalized) if normalized.endswith('.py') else None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'with_name':
            if ast.unparse(node.func.value) in {'Path(__file__)', 'pathlib.Path(__file__)'} and node.args:
                name = self.literal(node.args[0])
                if isinstance(name, str) and '/' not in name and '\\' not in name and name.endswith('.py'):
                    return '.'.join(filter(None, [self.package, name[:-3]]))
        if isinstance(node, ast.Call) and ast.unparse(node.func) in {'str', 'Path', 'pathlib.Path'} and node.args:
            return self.file_target(node.args[0])
        return None

    def dynamic_call(self, node, function):
        loaders = {'importlib.import_module': ('module', 0, 'name'), 'builtins.__import__': ('module', 0, 'name'),
                   'importlib.util.spec_from_file_location': ('file', 1, 'location'),
                   'importlib.machinery.SourceFileLoader': ('file', 1, 'path'), 'runpy.run_path': ('file', 0, 'path_name'),
                   'runpy.run_module': ('module', 0, 'mod_name')}
        if function not in loaders:
            unsupported = function in {'builtins.exec', 'builtins.eval'}
            if function:
                unsupported |= (function.startswith(('importlib.', 'runpy.')) and
                                function.endswith(('.load_module', '.exec_module', '.SourcelessFileLoader', '.ExtensionFileLoader', '._run_module_as_main')))
                unsupported |= function.startswith(('importlib.', 'runpy.', 'builtins.')) and '.<computed>' in function
            if unsupported:
                identity = ast.dump(ast.Call(func=ast.Name(id=function), args=node.args, keywords=node.keywords), include_attributes=False)
                self.dynamic_sites.add((self.source, self.context, function, 'unsupported', identity))
            return
        kind, position, keyword = loaders[function]
        argument = node.args[position] if len(node.args) > position else next((k.value for k in node.keywords if k.arg == keyword), None)
        value = self.literal(argument) if argument is not None else None
        target = self.file_target(argument) if kind == 'file' and argument is not None else value
        if kind == 'module' and isinstance(target, str) and target.startswith('.'):
            package = self.literal(node.args[1]) if len(node.args) > 1 else next((self.literal(k.value) for k in node.keywords if k.arg == 'package'), None)
            if isinstance(package, str):
                prior = self.package
                self.package = package
                target = self.resolve(target)
                self.package = prior
            else:
                target = None
        fromlist = []
        if function == 'builtins.__import__':
            level = self.literal(node.args[4]) if len(node.args) > 4 else next((self.literal(k.value) for k in node.keywords if k.arg == 'level'), 0)
            listed = node.args[3] if len(node.args) > 3 else next((k.value for k in node.keywords if k.arg == 'fromlist'), None)
            fromlist = self.literal(listed) if listed is not None else []
            if level != 0 or fromlist is None:
                target = None
        internal = isinstance(target, str) and any(target == m or target.startswith(m + '.') or m.startswith(target + '.') for m in self.modules)
        classification = 'internal' if internal else 'external' if kind == 'module' and isinstance(target, str) else 'unresolved'
        # Canonical callable + AST arguments: stable across aliases, formatting and line shifts.
        identity = ast.dump(ast.Call(func=ast.Name(id=function), args=node.args, keywords=node.keywords), include_attributes=False)
        self.dynamic_sites.add((self.source, self.context, function, classification, identity))
        if internal:
            self.edge(target, 'dynamic', 'file_load' if kind == 'file' else 'import_module')
            for member in fromlist or []:
                if isinstance(member, str): self.edge(target + '.' + member, 'dynamic', 'import_module')
        elif classification == 'unresolved':
            self.unresolved.add((self.source, self.context, identity))

    def visit_For(self, node):
        self.visit(node.iter)
        values = self.literal(node.iter)
        saved = self.bindings.copy()
        if isinstance(node.target, ast.Name) and isinstance(values, list):
            for value in values:
                self.bindings[node.target.id] = value
                for statement in node.body:
                    self.visit(statement)
        else:
            for statement in node.body:
                self.visit(statement)
        self.bindings = saved
        for statement in node.orelse:
            self.visit(statement)
        # A loop can run zero times or assign different values on different paths.
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                self.bindings.pop(child.id, None)

    visit_AsyncFor = visit_For

    def visit_If(self, node):
        self.visit(node.test)
        test = node.test
        negated = isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)
        guard = test.operand if negated else test
        is_type = ast.unparse(guard) in self.typing_names
        old = self.context
        before = self.bindings.copy()
        if is_type and not negated:
            self.context = "type_checking"
        for statement in node.body:
            self.visit(statement)
        body_bindings = self.bindings.copy()
        self.bindings = before.copy()
        self.context = "type_checking" if is_type and negated else old
        for statement in node.orelse:
            self.visit(statement)
        self.bindings = {key: value for key, value in body_bindings.items()
                         if key in self.bindings and self.bindings[key] == value}
        self.context = old

    def visit_Try(self, node):
        self.generic_visit(node)
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                self.bindings.pop(child.id, None)

    visit_TryStar = visit_Try
    visit_While = visit_Try

    def visit_ClassDef(self, node):
        before = self.bindings.copy()
        self.generic_visit(node)
        self.bindings = before

    def visit_FunctionDef(self, node):
        # Defaults/decorators/annotations are evaluated at definition time.
        for value in [*node.decorator_list, *node.args.defaults, *node.args.kw_defaults, node.returns]:
            if value is not None:
                self.visit(value)
        for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs, node.args.vararg, node.args.kwarg]:
            if arg is not None and arg.annotation is not None:
                self.visit(arg.annotation)
        old_context, old_bindings = self.context, self.bindings.copy()
        old_symbols = self.symbols.copy()
        for statement in node.body:
            for child in ast.walk(statement):
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                    self.bindings.pop(child.id, None)
        # An argument can shadow a same-named constant in the enclosing scope.
        for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs, node.args.vararg, node.args.kwarg]:
            if arg is not None:
                self.bindings.pop(arg.arg, None)
                self.symbols.pop(arg.arg, None)
        if self.context != "type_checking":
            self.context = "lazy"
        for statement in node.body:
            self.visit(statement)
        self.context, self.bindings = old_context, old_bindings
        self.symbols = old_symbols

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node):
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                self.visit(default)
        old = self.context
        if old != "type_checking":
            self.context = "lazy"
        self.visit(node.body)
        self.context = old

    def visit_Call(self, node):
        symbol = self.symbol(node.func)
        if not symbol and isinstance(node.func, ast.Attribute) and node.func.attr in {'spec_from_file_location', 'SourceFileLoader', 'run_path', 'run_module', 'import_module'}:
            # A recognizable loader API through an opaque receiver is internal-capable.
            symbol = {'spec_from_file_location':'importlib.util.spec_from_file_location',
                      'SourceFileLoader':'importlib.machinery.SourceFileLoader', 'run_path':'runpy.run_path',
                      'run_module':'runpy.run_module', 'import_module':'importlib.import_module'}[node.func.attr]
        if not symbol and isinstance(node.func, ast.Attribute) and node.func.attr in {'load_module', 'exec_module'}:
            symbol = 'importlib.<computed>.' + node.func.attr
        self.dynamic_call(node, symbol)
        self.generic_visit(node)


def scan_sources(sources: dict[str, str]) -> dict:
    modules = {module_name(p) for p in sources}
    edges, unresolved, sites = set(), set(), set()
    for path, source in sorted(sources.items()):
        name = module_name(path)
        package = name if path.endswith('/__init__.py') else name.rpartition(".")[0]
        visitor = ImportVisitor(name, modules, package)
        visitor.visit(ast.parse(source.lstrip('\ufeff'), filename=path))
        edges.update(visitor.edges)
        unresolved.update(visitor.unresolved)
        sites.update(visitor.dynamic_sites)
    return {"schema": 2, "modules": sorted(modules), "edges": sorted(edges), "unresolved_dynamic": sorted(unresolved), 'dynamic_sites': sorted(sites)}


def scan(root: Path) -> dict:
    return scan_sources({p.relative_to(root).as_posix(): p.read_text(encoding='utf-8-sig') for p in source_paths(root)})


def cyclic_components(edges, *, eager: bool) -> tuple[dict, list]:
    graph: dict[str, set[str]] = {}
    for source, target, context, *_ in edges:
        if context == "type_checking" or (eager and context != "module_load"):
            continue
        graph.setdefault(source, set()).add(target)
        graph.setdefault(target, set())
    # Tarjan SCCs; compare cyclic edges too, so a new cycle inside an old SCC fails.
    indices, low, stack, on_stack, components = {}, {}, [], set(), []
    def visit(node):
        indices[node] = low[node] = len(indices)
        stack.append(node)
        on_stack.add(node)
        for target in sorted(graph[node]):
            if target not in indices:
                visit(target)
                low[node] = min(low[node], low[target])
            elif target in on_stack:
                low[node] = min(low[node], indices[target])
        if low[node] == indices[node]:
            component = []
            while True:
                target = stack.pop()
                on_stack.remove(target)
                component.append(target)
                if target == node:
                    break
            components.append(component)
    for node in sorted(graph):
        if node not in indices:
            visit(node)
    return graph, sorted(sorted(group) for group in components
                         if len(group) > 1 or group[0] in graph[group[0]])


def cycle_edges(edges, *, eager: bool) -> list[list[str]]:
    graph, components = cyclic_components(edges, eager=eager)
    membership = {node: index for index, group in enumerate(components) for node in group}
    return sorted([source, target] for source in graph for target in graph[source]
                  if source in membership and target in membership and membership[source] == membership[target])


def forbidden(edge, policy) -> bool:
    source, target = map(layer, edge[:2])
    return source != target and target not in policy["allowed_dependencies"].get(source, [])


def annotate(data: dict, policy: dict) -> dict:
    data["grandfathered_violations"] = [e for e in data["edges"] if forbidden(e, policy)]
    data["eager_cycle_edges"] = cycle_edges(data["edges"], eager=True)
    data["runtime_cycle_edges"] = cycle_edges(data["edges"], eager=False)
    data["eager_sccs"] = cyclic_components(data["edges"], eager=True)[1]
    data["runtime_sccs"] = cyclic_components(data["edges"], eager=False)[1]
    return data


def snapshot(root: Path, policy: dict) -> dict:
    return annotate(scan(root), policy)


def relocated_origins(baseline: dict, relocations: dict | None) -> dict[str, str]:
    """New module -> sealed-baseline root module, for layout relocations made after the baseline."""
    known = set(baseline.get("modules", []))
    origins = {}
    for old, new in (relocations or {}).items():
        old_module, new_module = module_name(old), module_name(new)
        if old_module in known and new_module not in known:
            origins[new_module] = old_module
    return origins


def relocation_carried(current: dict, baseline: dict, policy: dict, relocations: dict | None) -> tuple[set, list[str]]:
    """Reviewed relocated debt: each listed row must be a sealed-baseline edge renamed by the layout manifest.

    Without a layout manifest nothing is carried, so every listed row stays an ordinary violation.
    """
    if relocations is None:
        return set(), []
    origins = relocated_origins(baseline, relocations)
    sealed = {tuple(e) for e in baseline["edges"]}
    present = {tuple(e) for e in current["edges"]}
    carried, errors = set(), []
    for row in map(tuple, policy.get("relocated_debt_edges", [])):
        origin = (origins.get(row[0], row[0]), origins.get(row[1], row[1])) + row[2:]
        if origin == row or origin not in sealed:
            errors.append("RELOCATED_DEBT_NOT_IN_SEALED_BASELINE:" + repr(row))
        elif row not in present:
            errors.append("STALE_RELOCATED_DEBT:" + repr(row))
        else:
            carried.add(row)
    return carried, errors


def regressions(current: dict, baseline: dict, policy: dict, relocations: dict | None = None) -> list[str]:
    grandfathered = {tuple(e) for e in baseline["grandfathered_violations"]}
    carried, errors = relocation_carried(current, baseline, policy, relocations)
    for edge in current["edges"]:
        if forbidden(edge, policy) and tuple(edge) not in grandfathered and tuple(edge) not in carried:
            errors.append("NEW_BACKWARD_DEPENDENCY:" + repr(edge))
    for key in ("eager_cycle_edges", "runtime_cycle_edges", "unresolved_dynamic"):
        old = {tuple(e) for e in baseline[key]}
        for row in current[key]:
            if tuple(row) not in old:
                errors.append("NEW_" + key.upper() + ":" + repr(row))
    accepted = {tuple(row) for row in baseline.get('dynamic_sites', [])}
    for row in current.get('dynamic_sites', []):
        if row[3] == 'unsupported' and tuple(row) not in accepted:
            errors.append('NEW_UNSUPPORTED_DYNAMIC:' + repr(row))
    return sorted(errors)


def baseline_from_checkpoint(root: Path, checkpoint: str, policy: dict) -> dict:
    """Migration reads only immutable checkpoint sources, never current candidate code."""
    sha = subprocess.check_output(['git', '-C', str(root), 'rev-parse', checkpoint + '^{commit}'], text=True).strip()
    if sha != MIGRATION_CHECKPOINT:
        raise ValueError('Migration must use the reviewed immutable E0 checkpoint')
    names = subprocess.check_output(['git', '-C', str(root), 'ls-tree', '-r', '--name-only', sha], text=True).splitlines()
    names = [p for p in names if p.endswith('.py') and ('/' not in p or p.startswith(('tools/', 'stocklookup_core/')))]
    request = ''.join(sha + ':' + p + '\n' for p in names).encode()
    output = subprocess.run(['git', '-C', str(root), 'cat-file', '--batch'], input=request, capture_output=True, check=True).stdout
    sources, offset = {}, 0
    for name in names:
        end = output.index(b'\n', offset)
        size = int(output[offset:end].split()[-1])
        sources[name] = output[end+1:end+1+size].decode('utf-8-sig')
        offset = end+size+2
    old_bytes = subprocess.check_output(['git', '-C', str(root), 'show', sha + ':' + BASELINE])
    if hashlib.sha256(old_bytes).hexdigest() != PRIOR_BASELINE_SHA256:
        raise ValueError('Reviewed prior baseline identity changed')
    old = json.loads(old_bytes)
    data = annotate(scan_sources(sources), policy)
    # Preserve old exact permissions; add only newly exposed debt in immutable old sources.
    for key in ('grandfathered_violations', 'eager_cycle_edges', 'runtime_cycle_edges'):
        data[key] = sorted(set(map(tuple, old[key])) | set(map(tuple, data[key])))
    data['migration'] = {'checkpoint': sha, 'prior_baseline_sha256': hashlib.sha256(old_bytes).hexdigest(), 'reason': 'Expanded loader classification of immutable accepted sources only'}
    return data


# --- Missing internal import guard (G3) ---------------------------------------------------------
# E0 drops an import whose target is not a current module, so a stale `import old_root_name` or
# `from stocklookup_core.x import removed` looked "external" and passed. This pass is closed-world:
# every absolute import is internal, stdlib, a declared third-party distribution, a reviewed sibling
# repository package, or a reviewed guarded legacy alias. Unknown names are reported as UNDECLARED,
# never assumed internal. Separate pass: E0 edges and the sealed baseline identity are unchanged.

# Import name -> declaring file. requirements*.txt entries must all appear here (drift-tested).
DECLARED_EXTERNAL = {
    "pandas": "requirements.txt", "numpy": "requirements.txt", "requests": "requirements.txt",
    "pyarrow": "requirements.txt", "openpyxl": "requirements.txt", "pytest": "requirements-test.txt",
    "_pytest": "requirements-test.txt", "anthropic": "requirements-providers.txt",
    "certifi": "transitive of requests", "packaging": "transitive of pytest",
    # Optional local-only extras, declared nowhere (docs/CI_AND_DEPENDENCY_TIERS.md); import sites
    # must stay lazy or guarded so the hermetic tier never needs them.
    "PIL": "optional OCR extra", "fitz": "optional PDF extra", "pypdf": "optional PDF extra",
    "duckdb": "optional benchmark extra", "websockets": "optional DNSE stream extra",
    "psutil": "optional resource-observer extra", "pandas_ta": "optional legacy indicator extra",
    "vnstock": "retired provider; refused by tests/provider_import_block",
    "vnai": "retired provider; refused by tests/provider_import_block",
}
# Packages that live in another repository and are put on sys.path at the call site.
SIBLING_REPOSITORY_PACKAGES = {
    "builders": "ai-core-private (Consumer) package, inserted from consumer_root at the call site",
    "metadata_registry_reader": "ai-core-private builders/ module, inserted from consumer_root",
    "metadata_registry_shadow_compare": "ai-core-private builders/ module, inserted from consumer_root",
    "vnstock_worker_protocol": "provider worker bundle module loaded beside the fake worker fixture",
}
# Legacy installed-package spelling, only ever imported as the guarded fallback of a root import.
GUARDED_LEGACY_ALIASES = {"stock_core_private": "pre-rename package alias; except ImportError fallback"}
IMPORT_ERROR_NAMES = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}


def guard_source_paths(root: Path, include_tests: bool = True) -> list[Path]:
    paths = source_paths(root)
    if include_tests:
        paths += sorted((root / "tests").rglob("*.py"), key=lambda p: p.relative_to(root).as_posix())
    return paths


def former_internal_names(baseline: dict, layout: dict) -> dict[str, str]:
    """Module names that were repository-owned once -> where they went (or '' if removed)."""
    moved = {module_name(old): module_name(new) for old, new in (layout.get("relocations") or {}).items()}
    names = {m: moved.get(m, "") for m in baseline.get("modules", [])}
    names.update({module_name(p): moved.get(module_name(p), "") for p in layout.get("grandfathered_root_python", [])})
    names.update(moved)
    return names


def module_exports(tree: ast.Module, source: str = "global := globals( vars(") -> tuple[set[str], bool]:
    """Names bound at module level; open=True when the namespace cannot be closed statically."""
    names, open_namespace = set(), False
    def bind(target):
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                bind(element)
        elif isinstance(target, ast.Starred):
            bind(target.value)
    def walk(statements):
        nonlocal open_namespace
        for node in statements:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
                open_namespace |= node.name == "__getattr__"
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    bind(target)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and node.value is not None or isinstance(node, ast.AnnAssign):
                bind(node.target)
            elif isinstance(node, ast.Import):
                names.update(a.asname or a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    open_namespace |= alias.name == "*"
                    names.add(alias.asname or alias.name)
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.With, ast.AsyncWith)):
                if hasattr(node, "target"):
                    bind(node.target)
                for item in getattr(node, "items", []):
                    if item.optional_vars is not None:
                        bind(item.optional_vars)
            for field in ("body", "orelse", "finalbody"):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    walk(getattr(node, field, []) or [])
            for handler in getattr(node, "handlers", []) or []:
                if handler.name:
                    names.add(handler.name)
                walk(handler.body)
            for case in getattr(node, "cases", []) or []:
                walk(case.body)
    walk(tree.body)
    if not any(token in source for token in ("global ", ":=", "globals(", "vars(")):
        return names, open_namespace
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            names.update(node.names)
        elif isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"globals", "vars"}:
            open_namespace = True  # globals()[name] = ... / vars().update(...)
    return names, open_namespace


STATEMENT_FIELDS = ("body", "orelse", "finalbody", "handlers", "cases")


def import_references(tree: ast.Module, source: str = "import_module __import__") -> tuple[list[dict], bool]:
    """Every import-like reference with line, execution context and guard state; plus whether the
    file manipulates sys.path. Import statements are statements, so expressions are descended only
    when the text can hold a dynamic loader call (this runs over every source and test file in CI)."""
    references, sys_names, path_bases = [], {"sys"}, set()
    uses_sys_path = False
    full = "import_module" in source or "__import__" in source
    aliases = set(re.findall(r"^\s*import\s+sys\s+as\s+(\w+)", source, re.M)) | {"sys"}
    if any(re.search(r"\b" + alias + r"\.path\b", source) for alias in aliases) or \
            re.search(r"^\s*from\s+sys\s+import\s[^\n]*\bpath\b", source, re.M):
        uses_sys_path = True
    stack = [(tree, "module_load", False, False)]
    while stack:
        node, context, guarded, fallback = stack.pop()
        def add(kind, module, names=(), level=0):
            references.append({"line": node.lineno, "context": context, "guarded": guarded, "fallback": fallback,
                               "kind": kind, "module": module, "names": list(names), "level": level,
                               "statement": ast.unparse(node).splitlines()[0][:160]})
        if isinstance(node, ast.Import):
            for alias in node.names:
                add("import", alias.name)
                if alias.name == "sys":
                    sys_names.add(alias.asname or "sys")
            continue
        if isinstance(node, ast.ImportFrom):
            add("from", node.module or "", [a.name for a in node.names], node.level)
            uses_sys_path |= node.module == "sys" and any(a.name == "path" for a in node.names)
            continue
        if isinstance(node, ast.Attribute) and node.attr == "path" and isinstance(node.value, ast.Name):
            path_bases.add(node.value.id)
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if name in {"import_module", "__import__"} and node.args and isinstance(node.args[0], ast.Constant)                     and isinstance(node.args[0].value, str) and not node.args[0].value.startswith("."):
                add("dynamic", node.args[0].value)
        elif isinstance(node, ast.If):
            test = node.test
            if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING" or isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
                stack.extend((s, "type_checking", guarded, fallback) for s in node.body)
                stack.extend((s, context, guarded, fallback) for s in node.orelse)
                continue
        elif isinstance(node, (ast.Try, ast.TryStar)):
            caught = set()
            for handler in node.handlers:
                types = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type] if handler.type else []
                caught |= {ast.unparse(t).rpartition(".")[2] for t in types} if types else {"BaseException"}
            catches = bool(caught & IMPORT_ERROR_NAMES)
            stack.extend((s, context, guarded or catches, fallback) for s in node.body)
            stack.extend((s, context, guarded, fallback) for s in [*node.orelse, *node.finalbody])
            stack.extend((s, context, guarded, fallback or catches) for h in node.handlers for s in h.body)
            continue
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            inner = context if context == "type_checking" else "lazy"
            heads = [*getattr(node, "decorator_list", []), *node.args.defaults, *node.args.kw_defaults]
            stack.extend((h, context, guarded, fallback) for h in heads if h is not None)
            body = node.body if isinstance(node.body, list) else [node.body]
            stack.extend((s, inner, guarded, fallback) for s in body)
            continue
        if full:
            stack.extend((child, context, guarded, fallback) for child in ast.iter_child_nodes(node))
        else:
            for field in STATEMENT_FIELDS:
                stack.extend((child, context, guarded, fallback) for child in getattr(node, field, ()) or ())
    return references, uses_sys_path or bool(path_bases & sys_names)


def internal_import_findings(sources: dict[str, str], former: dict[str, str] | None = None) -> list[dict]:
    """Classify every absolute import; return findings that are INTERNAL_MISSING or UNDECLARED.

    Resolution follows CPython: repository root first; a non-package script directory (tools/,
    tests/, root) also resolves bare sibling names, because the script's own directory is sys.path[0];
    a file that manipulates sys.path may additionally resolve tools/ and tests/ siblings.
    """
    import sys as _sys
    former = former or {}
    # One pass per file; trees are dropped at once (retaining ~1,700 trees makes GC dominate).
    parsed = {}
    for path, source in sorted(sources.items()):
        tree = ast.parse(source.lstrip("﻿"), filename=path)
        parsed[path] = (import_references(tree, source), module_exports(tree, source))
        del tree
    modules = {module_name(p): p for p in sources}
    packages = {".".join(m.split(".")[:i]) for m in modules for i in range(1, len(m.split(".")))}
    packages |= {module_name(p) for p in sources if p.endswith("/__init__.py")}
    script_dirs = {PurePosixPath(p).parent.as_posix() for p in sources} - {""}
    script_dirs = {d for d in script_dirs if d + "/__init__.py" not in sources}
    stdlib = set(_sys.stdlib_module_names) | {"__future__"}
    # Current repository top-level names, and former bare root / tools-script names.
    internal_tops = {m.split(".")[0] for m in modules}
    former_tops = {m for m in former if "." not in m} | {m[6:] for m in former if m.startswith("tools.") and m.count(".") == 1}

    def exists(name):
        return name in modules or name in packages

    def exports(name):
        path = modules.get(name)
        return parsed[path][1] if path else (set(), True)

    def candidates(path, name, uses_sys_path):
        """Absolute dotted names `name` may resolve to for this importer, in sys.path order."""
        own = PurePosixPath(path).parent.as_posix()
        found = [name]
        dirs = [own] if own in script_dirs else []
        if uses_sys_path:
            dirs += [d for d in ("tools", "tests") if d != own]
        found += [d.replace("/", ".") + "." + name for d in dirs if d]
        return found

    findings = []
    for path, ((references, uses_sys_path), _exports) in parsed.items():
        importer = module_name(path)
        package = importer if path.endswith("/__init__.py") else importer.rpartition(".")[0]
        for ref in sorted(references, key=lambda r: (r["line"], r["module"])):
            module = ref["module"]
            if ref["level"]:
                parts = package.split(".") if package else []
                if ref["level"] > len(parts) + (1 if path.endswith("/__init__.py") else 0):
                    findings.append(dict(ref, path=path, verdict="INTERNAL_MISSING", reason="RELATIVE_BEYOND_TOP", target=module))
                    continue
                base = parts[:len(parts) - ref["level"] + 1]
                module = ".".join(base + ([module] if module else []))
                choices = [module]
            else:
                top = module.split(".")[0]
                if top in stdlib:
                    continue
                choices = candidates(path, module, uses_sys_path)
            resolved = next((c for c in choices if exists(c)), None)
            if resolved is None:
                if ref["level"]:
                    findings.append(dict(ref, path=path, verdict="INTERNAL_MISSING", reason="NO_SUCH_MODULE", target=module))
                    continue
                top = module.split(".")[0]
                if top in internal_tops or any(c in former or c.split(".")[0] in former_tops for c in choices):
                    hint = next((former[c] for c in choices if former.get(c)), "")
                    findings.append(dict(ref, path=path, verdict="INTERNAL_MISSING",
                                         reason="RELOCATED" if hint else "NO_SUCH_MODULE", target=module, hint=hint))
                elif top in DECLARED_EXTERNAL or top in SIBLING_REPOSITORY_PACKAGES:
                    continue
                elif top in GUARDED_LEGACY_ALIASES and (ref["guarded"] or ref["fallback"]):
                    continue
                else:
                    findings.append(dict(ref, path=path, verdict="UNDECLARED", reason="UNKNOWN_TOP_LEVEL", target=module))
                continue
            if ref["kind"] != "from":
                continue
            for name in ref["names"]:
                if name == "*" or exists(resolved + "." + name):
                    continue
                defined, open_namespace = exports(resolved)
                if name not in defined and not open_namespace:
                    findings.append(dict(ref, path=path, verdict="INTERNAL_MISSING", reason="NO_SUCH_SYMBOL",
                                         target=resolved + ":" + name))
    return findings


def format_finding(f: dict) -> str:
    hint = f" -> {f['hint']}" if f.get("hint") else ""
    guard = ":guarded" if f["guarded"] else ":fallback" if f.get("fallback") else ""
    return (f"{f['verdict']}:{f['reason']}:{f['path']}:{f['line']}:{f['context']}{guard}:"
            f"{f['target']}{hint} | {f['statement']}")


def internal_import_errors(root: Path, baseline: dict | None = None, layout: dict | None = None,
                           include_tests: bool = True) -> list[str]:
    baseline = baseline if baseline is not None else json.loads((root / BASELINE).read_text(encoding="utf-8"))
    layout = layout if layout is not None else json.loads((root / LAYOUT).read_text(encoding="utf-8"))
    sources = {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8-sig") for p in guard_source_paths(root, include_tests)}
    return [format_finding(f) for f in internal_import_findings(sources, former_internal_names(baseline, layout))]


def encode(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def baseline_identity_valid(baseline):
    # Normal CI can be a shallow checkout: no historical Git object is required.
    return hashlib.sha256(encode(baseline).encode('utf-8')).hexdigest() == MIGRATED_BASELINE_SHA256


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-candidate", type=Path)
    parser.add_argument("--migrate-baseline-from")
    args = parser.parse_args(argv)
    policy = json.loads((args.root / POLICY).read_text(encoding="utf-8"))
    if args.migrate_baseline_from and not args.write_candidate:
        parser.error("migration requires a separate review candidate")
    data = baseline_from_checkpoint(args.root, args.migrate_baseline_from, policy) if args.migrate_baseline_from else snapshot(args.root, policy)
    if args.write_candidate:
        if args.write_candidate.resolve() == (args.root / BASELINE).resolve():
            parser.error("candidate must differ from enforced baseline; review and copy explicitly")
        args.write_candidate.write_text(encode(data), encoding="utf-8", newline="\n")
        return 0
    baseline = json.loads((args.root / BASELINE).read_text(encoding="utf-8"))
    if not baseline_identity_valid(baseline):
        print("BASELINE_IDENTITY_CHANGED:reviewed checkpoint migration differs")
        return 1
    layout = json.loads((args.root / LAYOUT).read_text(encoding="utf-8")) if (args.root / LAYOUT).is_file() else {}
    errors = regressions(data, baseline, policy, layout.get("relocations"))
    errors += internal_import_errors(args.root, baseline, layout)
    print("\n".join(errors) if errors else "ARCHITECTURE_RATCHET:PASS")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
