"""Offline AST ratchet, extending config/repository_layout.json; imports no product code.

--write-candidate writes a review artifact, never overwrites the enforced baseline.
Deliberate relocation requires reviewing its diff alongside the layout manifest.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "config/architecture_dependency_baseline.json"
POLICY = "config/architecture_dependency_policy.json"


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
        self.dynamic_names = {"__import__", "importlib.import_module", "importlib.util.spec_from_file_location"}
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

    def visit_Import(self, node):
        for alias in node.names:
            self.edge(alias.name, "static", "import")
            if alias.name == "importlib" and alias.asname:
                self.dynamic_names.add(alias.asname + ".import_module")
                self.dynamic_names.add(alias.asname + ".util.spec_from_file_location")
            if alias.name == "typing" and alias.asname:
                self.typing_names.add(alias.asname + ".TYPE_CHECKING")

    def visit_ImportFrom(self, node):
        base = self.resolve("." * node.level + (node.module or ""))
        self.edge(base, "static", "from")
        for alias in node.names:
            self.edge(base + "." + alias.name, "static", "from")
            if base in {"importlib", "importlib.util"} and alias.name in {"import_module", "spec_from_file_location"}:
                self.dynamic_names.add(alias.asname or alias.name)
            if base == "typing" and alias.name == "TYPE_CHECKING":
                self.typing_names.add(alias.asname or alias.name)

    def visit_Assign(self, node):
        self.visit(node.value)
        value = self.literal(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.bindings[target.id] = value

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
        for statement in node.body:
            for child in ast.walk(statement):
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                    self.bindings.pop(child.id, None)
        # An argument can shadow a same-named constant in the enclosing scope.
        for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs, node.args.vararg, node.args.kwarg]:
            if arg is not None:
                self.bindings.pop(arg.arg, None)
        if self.context != "type_checking":
            self.context = "lazy"
        for statement in node.body:
            self.visit(statement)
        self.context, self.bindings = old_context, old_bindings

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
        function = ast.unparse(node.func)
        if function in self.dynamic_names:
            value = self.literal(node.args[0]) if node.args else None
            if function.endswith("spec_from_file_location"):
                self.unresolved.add((self.source, self.context, ast.unparse(node)))
            elif isinstance(value, str):
                if value.startswith("."):
                    package = self.literal(node.args[1]) if len(node.args) > 1 else None
                    package = next((self.literal(k.value) for k in node.keywords if k.arg == "package"), package)
                    if isinstance(package, str):
                        prior = self.package
                        self.package = package
                        self.edge(value, "dynamic", "import_module")
                        self.package = prior
                    else:
                        self.unresolved.add((self.source, self.context, ast.unparse(node)))
                else:
                    self.edge(value, "dynamic", "import_module")
            else:
                self.unresolved.add((self.source, self.context, ast.unparse(node)))
        self.generic_visit(node)


def scan(root: Path) -> dict:
    paths = source_paths(root)
    modules = {module_name(p.relative_to(root).as_posix()) for p in paths}
    edges, unresolved = set(), set()
    for path in paths:
        name = module_name(path.relative_to(root).as_posix())
        package = name if path.name == "__init__.py" else name.rpartition(".")[0]
        visitor = ImportVisitor(name, modules, package)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8-sig"), filename=path.relative_to(root).as_posix()))
        edges.update(visitor.edges)
        unresolved.update(visitor.unresolved)
    return {"schema": 1, "modules": sorted(modules), "edges": sorted(edges), "unresolved_dynamic": sorted(unresolved)}


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


def snapshot(root: Path, policy: dict) -> dict:
    data = scan(root)
    data["grandfathered_violations"] = [e for e in data["edges"] if forbidden(e, policy)]
    data["eager_cycle_edges"] = cycle_edges(data["edges"], eager=True)
    data["runtime_cycle_edges"] = cycle_edges(data["edges"], eager=False)
    data["eager_sccs"] = cyclic_components(data["edges"], eager=True)[1]
    data["runtime_sccs"] = cyclic_components(data["edges"], eager=False)[1]
    return data


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
    return sorted(errors)


def encode(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-candidate", type=Path)
    args = parser.parse_args(argv)
    policy = json.loads((args.root / POLICY).read_text(encoding="utf-8"))
    data = snapshot(args.root, policy)
    if args.write_candidate:
        if args.write_candidate.resolve() == (args.root / BASELINE).resolve():
            parser.error("candidate must differ from enforced baseline; review and copy explicitly")
        args.write_candidate.write_text(encode(data), encoding="utf-8", newline="\n")
        return 0
    baseline = json.loads((args.root / BASELINE).read_text(encoding="utf-8"))
    errors = regressions(data, baseline, policy)
    print("\n".join(errors) if errors else "ARCHITECTURE_RATCHET:PASS")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
