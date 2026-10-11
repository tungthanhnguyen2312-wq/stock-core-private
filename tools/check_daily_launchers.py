"""Static path contract for the reviewed invocation set; never executes a launcher."""
from __future__ import annotations

import ast
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def portable_path(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or ":" in value:
        raise ValueError("Launcher must be repository relative: " + value)
    return path.as_posix()


def ast_digest(source: str) -> str:
    import hashlib
    return hashlib.sha256(ast.dump(ast.parse(source), include_attributes=False).encode()).hexdigest()


def invocation_paths(source: str) -> tuple[set[str], list[str]]:
    """Backward slice only argv passed to subprocess or verified local dispatch wrappers.

    Ambiguous/mutated commands are unresolved; caller pins cover audited construction
    that needs interprocedural flow (TASKS, steps, bundle copying, argv_plans).
    """
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    aliases = {'subprocess': 'subprocess'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name == 'subprocess': aliases[item.asname or item.name] = 'subprocess'
        if isinstance(node, ast.ImportFrom) and node.module == 'subprocess':
            for item in node.names: aliases[item.asname or item.name] = 'subprocess.' + item.name
    def callable_name(node):
        if isinstance(node, ast.Name): return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute): return callable_name(node.value) + '.' + node.attr
        return ''
    sinks = {'subprocess.run', 'subprocess.Popen', 'subprocess.check_call', 'subprocess.check_output'}
    functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    wrappers = {}
    for fn in functions:
        parameters = [a.arg for a in fn.args.args]
        for call in ast.walk(fn):
            if isinstance(call, ast.Call) and callable_name(call.func) in sinks | {'runner', 'self.runner'} and call.args and isinstance(call.args[0], ast.Name):
                if call.args[0].id in parameters:
                    index = parameters.index(call.args[0].id)
                    if parameters and parameters[0] == 'self': index -= 1
                    wrappers[fn.name] = index
    def scope(node):
        while node in parents:
            node = parents[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)): return node
        return tree
    def value(node, call, seen=frozenset()):
        if isinstance(node, ast.Constant): return node.value
        if isinstance(node, ast.Name):
            if node.id in {'py', 'python_exe'}: return '@python'
            if node.id in {'root', 'ROOT', 'SCRIPT_DIR', 'code_dir', 'producer', 'producer_root', 'producer_dir'}: return ''
            if node.id in seen: return None
            assignments = [n for n in ast.walk(scope(call)) if isinstance(n, (ast.Assign, ast.AnnAssign)) and scope(n) == scope(call) and n.lineno < call.lineno and any(isinstance(t, ast.Name) and t.id == node.id for t in (n.targets if isinstance(n, ast.Assign) else [n.target]))]
            if len(assignments) != 1: return None
            # Subscript writes or structural list mutations invalidate the initial argv.
            for n in ast.walk(scope(call)):
                if not assignments[0].lineno < getattr(n, 'lineno', 0) < call.lineno: continue
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id == node.id for t in n.targets): return None
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == node.id and n.func.attr in {'insert', 'pop', 'remove', 'clear', 'reverse', 'sort'}: return None
            return value(assignments[0].value, call, seen | {node.id})
        if isinstance(node, ast.Attribute) and callable_name(node) == 'sys.executable': return '@python'
        if isinstance(node, (ast.List, ast.Tuple)):
            return [value(n, call, seen) if not isinstance(n, ast.Starred) else None for n in node.elts]
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.Add)):
            left, right = value(node.left, call, seen), value(node.right, call, seen)
            if isinstance(left, str) and isinstance(right, str):
                return (left.rstrip('/') + '/' + right.lstrip('/')).lstrip('/') if isinstance(node.op, ast.Div) else left + right
        if isinstance(node, ast.Call) and node.args:
            name = callable_name(node.func)
            if name in {'str', 'Path', 'pathlib.Path'}: return value(node.args[0], call, seen)
            if name == 'producer_script':
                definitions = [fn for fn in functions if fn.name == name]
                if len(definitions) == 1 and any(isinstance(n, ast.Return) and isinstance(n.value, ast.BinOp) and isinstance(n.value.op, ast.Div) and isinstance(n.value.left, ast.Name) and n.value.left.id == 'SCRIPT_DIR' and isinstance(n.value.right, ast.Name) and n.value.right.id == definitions[0].args.args[0].arg for n in ast.walk(definitions[0])):
                    return value(node.args[0], call, seen)
        return None
    found, unresolved = set(), []
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call): continue
        name = callable_name(call.func)
        if name in sinks: index = 0
        elif name.split('.')[-1] in wrappers: index = wrappers[name.split('.')[-1]]
        else: continue
        expression = call.args[index] if len(call.args) > index else next((k.value for k in call.keywords if k.arg in {'args', 'argv', 'command'}), None)
        command = value(expression, call) if expression is not None else None
        if not isinstance(command, list) or not command: unresolved.append(ast.unparse(call)); continue
        executable = command[0]
        if executable != '@python' and not (isinstance(executable, str) and executable.rsplit('/',1)[-1].lower().startswith('python')): continue
        script = None
        index = 1
        while index < len(command):
            item = command[index]
            if item in {'-c', '-m'}: break
            if item in {'-X', '-W'}:
                index += 2
                continue
            if isinstance(item, str) and item.startswith('-') and item != '--':
                index += 1
                continue
            if item == '--':
                index += 1
                item = command[index] if index < len(command) else None
            script = item
            break
        if isinstance(script, str) and script.endswith('.py'):
            try: found.add(portable_path(script))
            except ValueError: unresolved.append(ast.unparse(call))
        elif script is None: unresolved.append(ast.unparse(call))
    return found, sorted(set(unresolved))


def argv_references(source: str) -> set[str]:
    return invocation_paths(source)[0]


def check(root: Path, manifest: dict) -> list[str]:
    errors = []
    for entry in manifest["targets"]:
        target = portable_path(entry["path"])
        path = root / target
        if not path.is_file():
            errors.append("MISSING_PATH_LAUNCHER:" + target)
            continue
        try:
            compile(path.read_text(encoding="utf-8-sig"), target, "exec")
        except (SyntaxError, UnicodeError) as exc:
            errors.append("INVALID_PATH_LAUNCHER:" + target + ":" + str(exc))
    for caller, targets in manifest["python_callers"].items():
        path = root / portable_path(caller)
        if not path.is_file():
            errors.append("MISSING_LAUNCH_CALLER:" + caller)
            continue
        source = path.read_text(encoding="utf-8-sig")
        references = argv_references(source)
        bounded = manifest.get("bounded_callers", {}).get(caller, {})
        bounded_ok = bounded.get("ast_sha256") == ast_digest(source)
        if bounded and not bounded_ok:
            errors.append('BOUNDED_LAUNCH_CONTRACT_CHANGED:' + caller)
        for target in targets:
            if portable_path(target) not in references and not (bounded_ok and target in bounded.get("targets", [])):
                errors.append("LAUNCH_PATH_CONTRACT_CHANGED:" + caller + ":" + target)
    for caller, contract in manifest.get('non_python_callers', {}).items():
        import hashlib
        path = root / portable_path(caller)
        if not path.is_file() or hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() != contract['sha256']:
            errors.append('BOUNDED_LAUNCH_CONTRACT_CHANGED:' + caller)
    return sorted(errors)


def main():
    manifest = json.loads((ROOT / "config/daily_path_launchers.json").read_text(encoding="utf-8"))
    errors = check(ROOT, manifest)
    print("\n".join(errors) if errors else "DAILY_PATH_LAUNCHERS:PASS")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
