"""Offline AST ratchet, extending config/repository_layout.json; imports no product code.

--write-candidate writes a review artifact, never overwrites the enforced baseline.
Deliberate relocation requires reviewing its diff alongside the layout manifest.
"""
from __future__ import annotations

import argparse
import ast
import json
import hashlib
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "config/architecture_dependency_baseline.json"
POLICY = "config/architecture_dependency_policy.json"
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
        self.symbols = {"__import__": "builtins.__import__", "exec": "builtins.exec", "eval": "builtins.eval"}
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


def regressions(current: dict, baseline: dict, policy: dict) -> list[str]:
    errors = []
    grandfathered = {tuple(e) for e in baseline["grandfathered_violations"]}
    for edge in current["edges"]:
        if forbidden(edge, policy) and tuple(edge) not in grandfathered:
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
    errors = regressions(data, baseline, policy)
    print("\n".join(errors) if errors else "ARCHITECTURE_RATCHET:PASS")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
