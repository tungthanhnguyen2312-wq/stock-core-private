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


def argv_references(source: str) -> set[str]:
    """Recognize path-valued AST expressions, excluding prose/comments/docstrings.

    This is a bounded static guard over reviewed callers, not runtime reachability.
    Producer-root and tools path joins are preserved as exact relative paths.
    """
    result = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.List, ast.Tuple)):
            for element in node.elts:
                if isinstance(element, ast.Constant) and isinstance(element.value, str) and element.value.endswith(".py"):
                    result.add(portable_path(element.value))
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            values = []
            part = node
            while isinstance(part, ast.BinOp) and isinstance(part.op, ast.Div):
                if isinstance(part.right, ast.Constant) and isinstance(part.right.value, str):
                    values.insert(0, part.right.value)
                else:
                    break
                part = part.left
            if values and values[-1].endswith(".py"):
                result.add(portable_path("/".join(values)))
        if isinstance(node, ast.Call) and ast.unparse(node.func).endswith(("producer_script", "with_name")):
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) and node.args[0].value.endswith(".py"):
                result.add(portable_path(node.args[0].value))
    return result


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
        references = argv_references(path.read_text(encoding="utf-8-sig"))
        for target in targets:
            if portable_path(target) not in references:
                errors.append("LAUNCH_PATH_CONTRACT_CHANGED:" + caller + ":" + target)
    return sorted(errors)


def main():
    manifest = json.loads((ROOT / "config/daily_path_launchers.json").read_text(encoding="utf-8"))
    errors = check(ROOT, manifest)
    print("\n".join(errors) if errors else "DAILY_PATH_LAUNCHERS:PASS")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
