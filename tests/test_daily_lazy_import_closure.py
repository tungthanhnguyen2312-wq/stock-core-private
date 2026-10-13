"""G2: cold, offline import closure of the Owner Daily call graph, lazy and resume paths included.

PR #132 executed the function-local imports of tools/run_owner_daily.py only (one hop). This test
computes every module statically reachable from the Daily entries (E0 edges, lazy included, plus the
reviewed launcher manifest), then in ONE fresh interpreter imports each module and executes every
import statement found inside a function body of it: the module, then each imported symbol. Nothing
is called. Providers, optional extras, sockets and subprocesses are refused; an audit hook records any
write or launch so import-time side effects fail loudly. No retained evidence, no credentials.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import textwrap
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path

from tools import check_architecture as guard

ROOT = Path(__file__).resolve().parents[1]
LAUNCHERS = ROOT / "config/daily_path_launchers.json"
ENTRIES = ("stocklookup", "tools.run_owner_daily", "daily_analysis_pipeline", "canonical_daily_operation",
           "tools.release_orchestrator", "publish_dashboard")
# Absent from the hermetic tier by design (docs/CI_AND_DEPENDENCY_TIERS.md); refused here everywhere so
# the result is identical locally and in hosted CI. A refusal is accepted only for exactly that package.
OPTIONAL = ("fitz", "pypdf", "PIL", "duckdb", "websockets", "psutil", "pandas_ta", "anthropic")
PROVIDERS = ("vnstock", "vnai")
# Exact, reviewed exclusions: module -> reason. Every other reachable module is imported cold.
EXCLUDED_MODULES: dict[str, str] = {}
NON_DAILY_LAUNCH_TARGETS = {"ai_analyzer", "bctc_processor", "metadata_registry_export", "tools.provider_containment_probe",
                            "tools.run_provider_os_containment_qualification", "tools.verify_dependency_tiers"}


@lru_cache(maxsize=4)
def daily_reachable(root: Path = ROOT) -> list[str]:
    scan = guard.scan(root)
    graph = defaultdict(set)
    for source, target, context, *_ in scan["edges"]:
        if context != "type_checking":
            graph[source].add(target)
    manifest = json.loads((root / "config/daily_path_launchers.json").read_text(encoding="utf-8"))
    for caller, targets in manifest["python_callers"].items():
        graph[guard.module_name(caller)].update(guard.module_name(t) for t in targets)
    for caller, spec in manifest.get("bounded_callers", {}).items():
        graph[guard.module_name(caller)].update(guard.module_name(t) for t in spec.get("targets", []))
    seen, queue = set(ENTRIES), deque(ENTRIES)
    while queue:
        for target in graph.get(queue.popleft(), ()):
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return tuple(sorted(seen))


def lazy_import_plan(root: Path, modules: list[str]) -> list[dict]:
    """Every import statement inside a function body: [{importer, line, module, names}]. Imports in
    an except-ImportError handler are deliberate fallbacks for a failed primary and are skipped."""
    plan = []
    paths = {guard.module_name(p.relative_to(root).as_posix()): p for p in guard.source_paths(root)}
    for name in modules:
        path = paths[name]
        source = path.read_text(encoding="utf-8-sig")
        package = name if path.name == "__init__.py" else name.rpartition(".")[0]
        references, _ = guard.import_references(ast.parse(source), source)
        for ref in references:
            if ref["context"] != "lazy" or ref["fallback"] or ref["kind"] == "dynamic":
                continue
            module = ref["module"]
            if ref["level"]:
                parts = package.split(".")[:len(package.split(".")) - ref["level"] + 1]
                module = ".".join(parts + ([module] if module else []))
            plan.append({"importer": name, "line": ref["line"], "module": module,
                         "names": [n for n in ref["names"] if n != "*"]})
    unique = {(p["importer"], p["line"], p["module"], tuple(p["names"])): p for p in plan}
    return [unique[k] for k in sorted(unique)]


CHILD = textwrap.dedent('''
    import importlib, json, os, socket, sys, tempfile, time
    root, tools, plan_file, modules_file = sys.argv[1:5]
    optional, providers, siblings = (set(a.split(",")) for a in sys.argv[5:8])
    # The stdlib probes the temp directory once (os.open write + os.remove) on first gettempdir();
    # prime that cache so the audit records only side effects of repository code.
    tempfile.gettempdir()
    class Refuse:
        def find_spec(self, name, path=None, target=None):
            top = name.partition(".")[0]
            if top in providers or top in optional:
                raise ModuleNotFoundError(("PROVIDER_BLOCKED:" if top in providers else "OPTIONAL_BLOCKED:") + name, name=top)
    sys.meta_path.insert(0, Refuse())
    events = []
    def no_network(*a, **k):
        # Recorded before refusing, so an import that catches and swallows the OSError still fails.
        events.append(["network", "connect_refused", repr(a[-1:])[:160]])
        raise OSError("NETWORK_BLOCKED")
    socket.socket.connect = socket.socket.connect_ex = no_network
    socket.create_connection = no_network
    # builtin open() passes a mode string; os.open() passes mode None and integer flags.
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
    mutations = {"os.mkdir", "os.rename", "os.replace", "os.remove", "os.rmdir", "os.truncate", "os.link",
                 "os.symlink", "shutil.rmtree", "shutil.copyfile", "shutil.move"}
    launches = {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.startfile"}
    def audit(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            target = os.fsdecode(args[0]).replace(os.sep, "/")
            mode, flags = args[1], args[2]
            if isinstance(mode, str) and any(c in mode for c in "wax+") or isinstance(flags, int) and flags & write_flags:
                events.append(["write", target])
            elif "/operations-review/" in target or target.startswith(root.replace(os.sep, "/") + "/data/"):
                events.append(["retained_read", target])
        elif event in mutations:
            events.append(["fs_mutation", event, os.fsdecode(args[0]) if isinstance(args[0], (str, bytes, os.PathLike)) else repr(args[0])])
        elif event in ("socket.connect", "socket.getaddrinfo", "socket.sendto", "socket.sendmsg"):
            # Recorded even when the refused connect is caught and swallowed at import time.
            events.append(["network", event, repr(args[1:] if event.startswith("socket.s") or event == "socket.connect" else args)[:160]])
        elif event == "socket.bind":
            address = args[1]
            # Loopback, ephemeral port: the IPv6-support probe urllib3 runs when requests is imported.
            if not (isinstance(address, tuple) and address[:2] in (("::1", 0), ("127.0.0.1", 0))):
                events.append(["network", event, repr(address)[:160]])
        elif event == "sqlite3.connect":
            events.append(["sqlite", repr(args[0])[:160]])
        elif event in launches:
            events.append(["launch", event])
    sys.addaudithook(audit)
    sys.path[:0] = [root, tools]
    result = {"module_errors": {}, "lazy_errors": [], "optional": [], "events": events, "modules": 0, "statements": 0}
    def classify(exc):
        text = str(exc)
        top = (getattr(exc, "name", None) or "").partition(".")[0]
        if isinstance(exc, ModuleNotFoundError) and (top in optional or top in providers):
            return "optional", text
        if isinstance(exc, ModuleNotFoundError) and top in siblings:
            return "optional", "SIBLING_REPOSITORY:" + text
        if isinstance(exc, ModuleNotFoundError) and top in sys.stdlib_module_names:
            return "optional", "PLATFORM_ABSENT_STDLIB:" + text  # e.g. fcntl/resource on Windows
        return "error", type(exc).__name__ + ":" + text
    started = time.perf_counter()
    for name in json.load(open(modules_file, encoding="utf-8")):
        try:
            importlib.import_module(name)
            result["modules"] += 1
        except BaseException as exc:
            kind, text = classify(exc)
            (result["optional"].append([name, text]) if kind == "optional" else result["module_errors"].__setitem__(name, text))
    for item in json.load(open(plan_file, encoding="utf-8")):
        result["statements"] += 1
        try:
            target = importlib.import_module(item["module"])
            for symbol in item["names"]:
                if not hasattr(target, symbol):
                    importlib.import_module(item["module"] + "." + symbol)
        except BaseException as exc:
            kind, text = classify(exc)
            row = [item["importer"], item["line"], item["module"], item["names"], text]
            (result["optional"] if kind == "optional" else result["lazy_errors"]).append(row)
    result["seconds"] = round(time.perf_counter() - started, 2)
    leaked = sorted(m for m in sys.modules if m.partition(".")[0] in providers)
    result["provider_modules_loaded"] = leaked
    print("CLOSURE_RESULT=" + json.dumps(result))
''')


def run_closure(root: Path, workdir: Path, modules: list[str] | None = None) -> dict:
    modules = modules if modules is not None else [m for m in daily_reachable(root) if m not in EXCLUDED_MODULES]
    plan = lazy_import_plan(root, modules)
    (workdir / "modules.json").write_text(json.dumps(modules), encoding="utf-8")
    (workdir / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    runtime = workdir / "runtime"
    runtime.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("STOCK_LOOKUP", "STOCKLOOKUP", "PYTHONSTARTUP", "DNSE", "ANTHROPIC"))}
    env.update(STOCK_LOOKUP_RUNTIME_ROOT=str(runtime), PYTHONDONTWRITEBYTECODE="1", PYTHONPATH="")
    completed = subprocess.run(
        [sys.executable, "-B", "-c", CHILD, str(root), str(root / "tools"), str(workdir / "plan.json"),
         str(workdir / "modules.json"), ",".join(OPTIONAL), ",".join(PROVIDERS), ",".join(guard.SIBLING_REPOSITORY_PACKAGES)],
        cwd=workdir, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    line = next((l for l in completed.stdout.splitlines() if l.startswith("CLOSURE_RESULT=")), None)
    assert line, (completed.returncode, completed.stderr[-4000:])
    result = json.loads(line.partition("=")[2])
    result["plan"], result["module_count"] = len(plan), len(modules)
    return result


def closure_failures(result: dict) -> dict:
    """Every reason a closure run is not a clean, side-effect-free import. Empty means pass."""
    failures = {
        "module_errors": result["module_errors"],
        "lazy_errors": result["lazy_errors"][:20],
        "events": result["events"][:20],
        "provider_modules_loaded": result["provider_modules_loaded"],
        # A module whose body stopped at a refused optional/provider/sibling import was never
        # executed past that line, so a later broken import in it would pass unseen.
        "masked_modules": [r for r in result["optional"] if len(r) == 2],
        "unaccounted_modules": result["module_count"] - result["modules"],
        "unexecuted_statements": result["plan"] - result["statements"],
    }
    return {key: value for key, value in failures.items() if value}


def test_daily_reachable_set_covers_the_entries_and_reviewed_launch_targets():
    reachable = set(daily_reachable())
    manifest = json.loads(LAUNCHERS.read_text(encoding="utf-8"))
    targets = {guard.module_name(t["path"]) for t in manifest["targets"]}
    assert set(ENTRIES) <= reachable
    assert {"tools.run_owner_daily", "canonical_post_close_pipeline", "export_ai_bundle"} <= reachable
    # Reviewed launch targets outside the Daily graph (legacy run.py recipes, provider qualification,
    # CI tooling). A new target must be reached from Daily or be added here deliberately.
    assert targets - reachable == NON_DAILY_LAUNCH_TARGETS
    assert not set(EXCLUDED_MODULES) - reachable, "stale exclusion"


def test_daily_call_graph_imports_cold_offline_including_every_lazy_statement(tmp_path):
    result = run_closure(ROOT, tmp_path)
    assert closure_failures(result) == {}
    assert result["module_count"] >= 400 and result["plan"] >= 500, "reachability collapsed; the closure proves nothing"


# Synthetic tree: each module plants one defect class; the closure must report every one of them,
# and must not report the two benign stdlib/third-party probes.
SYNTHETIC = {
    "good.py": "def helper():\n    from good import VALUE\n    return VALUE\nVALUE = 1\n",
    "stale_symbol.py": "def run():\n    from good import REMOVED\n",
    "stale_module.py": "def run():\n    import removed_root_module\n",
    "broken_body.py": "import removed_root_module\n",
    "os_open_writer.py": ("import os\nos.close(os.open(os.path.join(os.environ['STOCK_LOOKUP_RUNTIME_ROOT'], 'x'),"
                          " os.O_WRONLY | os.O_CREAT))\n"),
    "text_writer.py": "import os\nopen(os.path.join(os.environ['STOCK_LOOKUP_RUNTIME_ROOT'], 'y'), 'w').close()\n",
    "mkdir_writer.py": "import os\nos.mkdir(os.path.join(os.environ['STOCK_LOOKUP_RUNTIME_ROOT'], 'd'))\n",
    "swallowed_dial.py": ("import socket\ntry:\n    socket.create_connection(('192.0.2.1', 9), timeout=0.01)\n"
                          "except OSError:\n    pass\n"),
    "sqlite_opener.py": "import sqlite3\nsqlite3.connect(':memory:').close()\n",
    "launcher.py": "import subprocess, sys\nsubprocess.run([sys.executable, '-c', 'pass'])\n",
    "provider_user.py": "def run():\n    import vnstock\n",
    "masked.py": "import fitz\nimport removed_root_module\n",
    "benign_tempdir.py": "import tempfile\nCACHE = tempfile.gettempdir()\n",
    "benign_loopback.py": "import socket\ns = socket.socket()\ns.bind(('127.0.0.1', 0))\ns.close()\n",
}


def test_closure_reports_every_planted_defect_and_no_benign_probe(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    for name, body in SYNTHETIC.items():
        (root / name).write_text(body, encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    result = run_closure(root, work, modules=sorted(Path(n).stem for n in SYNTHETIC))
    failures = closure_failures(result)
    assert set(failures["module_errors"]) == {"broken_body"}
    assert "removed_root_module" in failures["module_errors"]["broken_body"]
    assert sorted((r[0], r[2], tuple(r[3])) for r in result["lazy_errors"]) == [
        ("stale_module", "removed_root_module", ()), ("stale_symbol", "good", ("REMOVED",))]
    # Exactly the planted side effects: nothing from benign_tempdir / benign_loopback.
    kinds = sorted((e[0], e[1].rsplit("/", 1)[-1] if e[0] == "write" else e[1]) for e in result["events"])
    assert kinds == [("fs_mutation", "os.mkdir"), ("launch", "subprocess.Popen"), ("network", "connect_refused"),
                     ("sqlite", "':memory:'"), ("write", "x"), ("write", "y")], result["events"]
    assert [r[0] for r in failures["masked_modules"]] == ["masked"]
    assert [r[0] for r in result["optional"] if len(r) != 2] == ["provider_user"]
    assert "good" not in failures["module_errors"] and result["provider_modules_loaded"] == []
