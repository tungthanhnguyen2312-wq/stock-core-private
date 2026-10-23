import hashlib
import json
from pathlib import Path
import shutil
import types
import builtins
import importlib
import ast

import pytest
import prospective_decision_retention as retention
import prospective_feedback_streaming as streaming
from tools import qualify_e4_infrastructure as e4
from tools.verify_retention_reader_transition import historical_bytes, legacy_source_identity, active_reader_identity, ARCHIVE, MANIFEST
from test_prospective_t0_reuse_lineage import reuse, inventory

ROOT = Path(__file__).resolve().parents[1]


def test_original_closed_domains_recomputed_and_new_execution_is_separate():
    assert legacy_source_identity(ROOT, version="v1")["code_digest"] == "fa79baadcca197493b9ca70067fbd153f5e8bb7f50dfb6dbc6da53f253483d46"
    assert legacy_source_identity(ROOT, version="v2")["code_digest"] == "07c2a363df0e91a1dee230f0316a081249b247f7aa74bd67e04e45b1d1886567"
    new = active_reader_identity(ROOT)
    assert new["reader_version"] == retention.LINEAGE_READER_VERSION
    assert new["execution_code_digest"] == streaming.code_digest() == e4.source_identity(ROOT, version="v1")["code_digest"]
    assert new["execution_code_digest"] != legacy_source_identity(ROOT, version="v1")["code_digest"]
    assert not new["legacy_receipt_adoption"]


@pytest.mark.parametrize("target", [ARCHIVE, "prospective_decision_retention.py", MANIFEST])
def test_tampered_boundary_fails_closed(tmp_path, target):
    for relative in (ARCHIVE, "prospective_decision_retention.py", MANIFEST, "tests/fixtures/e2e3_frozen_sources.json"):
        p = tmp_path / relative; p.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT / relative, p)
    p = tmp_path / target
    if target == MANIFEST:
        value = json.loads(p.read_bytes()); value["legacy_sha256_lf"] = "0" * 64; p.write_text(json.dumps(value))
    else: p.write_bytes(p.read_bytes() + b"\n# tamper\n")
    with pytest.raises(ValueError, match="VERSION_BOUNDARY"):
        historical_bytes(tmp_path, "prospective_decision_retention.py")


def test_original_reader_remains_executable_and_excludes_only_new_reuse_route(reuse):
    old = types.ModuleType("frozen_retention_reader")
    exec(compile(historical_bytes(ROOT, "prospective_decision_retention.py"), ARCHIVE, "exec"), old.__dict__)
    result = old.discover_snapshots(reuse["root"])
    reasons = result["inventory"][0]["proof_reason_codes"]
    assert "HANDOFF_OPERATION_IDENTITY_MISMATCH" in reasons
    assert "HANDOFF_SOURCE_DECISION_IDENTITY_MISMATCH" in reasons
    assert not result["genuine_snapshots"]
    assert inventory(reuse)["genuine_snapshots"]


def test_old_verifier_cache_is_not_adopted(reuse):
    root = reuse["root"] / "cache"
    handle = streaming.load_snapshot_handle(reuse["path"], root)
    raw = handle.raw_sha256
    p = streaming._receipt_path(root, raw)
    value = json.loads(p.read_bytes())
    old = hashlib.sha256()
    for name in ("prospective_decision_retention", "bounded_artifact_stream", "prospective_feedback_streaming"):
        old.update(hashlib.sha256(historical_bytes(ROOT, name + ".py")).digest())
    assert value["code_digest"] == streaming._verification_code_digest() != old.hexdigest()
    value.update(code_digest=old.hexdigest(), valid=False)
    p.write_text(json.dumps(value), encoding="utf-8")
    metrics = {}
    assert streaming.load_snapshot_handle(reuse["path"], root, metrics).valid
    assert metrics["t0_receipt_misses"] == 1
    assert json.loads(p.read_bytes())["code_digest"] == streaming._verification_code_digest()


def test_actual_historical_verifier_rejects_new_receipt_and_reverse(reuse):
    # Exec the historical bytes of the stream and of every E4 V1 source whose historical
    # bytes differ from active source (the archived reader and any storage-prior source),
    # so the isolated stream is the original verifier, not active code with one swap.
    historical, modules, packages = {}, {}, {}
    for _, relative in e4.V1_SOURCES:
        content = historical_bytes(ROOT, relative)
        if relative == "prospective_feedback_streaming.py" or content != (ROOT / relative).read_bytes().replace(b"\r\n", b"\n"):
            historical[relative[:-3].replace("/", ".")] = (relative, content)
    assert "prospective_decision_retention" in historical
    original_import = builtins.__import__
    def load(name):
        if name not in modules:
            relative, content = historical[name]
            path = reuse["root"] / "historical-sources" / relative
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
            module = modules[name] = types.ModuleType("isolated_historical_" + name)
            module.__file__ = str(path)
            module.__dict__["__builtins__"] = {**vars(builtins), "__import__": old_import}
            exec(compile(content, str(path), "exec"), module.__dict__)
            if "import_module" in module.__dict__:
                module.import_module = lambda n: load(n) if n in historical else importlib.import_module(n)
        return modules[name]
    def old_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level == 0 and name in historical:
            module = load(name)
            if fromlist or "." not in name:
                return module
            # Python's plain dotted import returns the root package. Keep an
            # isolated package tree rather than mutating real imported packages.
            parts = name.split(".")
            for index in range(1, len(parts)):
                prefix = ".".join(parts[:index])
                package = packages.setdefault(prefix, types.ModuleType("isolated_" + prefix))
                child = module if index == len(parts) - 1 else packages.setdefault(
                    ".".join(parts[:index + 1]), types.ModuleType("isolated_" + ".".join(parts[:index + 1])))
                setattr(package, parts[index], child)
            return packages[parts[0]]
        return original_import(name, globals, locals, fromlist, level)
    old_stream = load("prospective_feedback_streaming")
    assert old_stream.retention is modules["prospective_decision_retention"]
    assert old_stream.code_digest() == legacy_source_identity(ROOT, version="v1")["code_digest"]
    cache = reuse["root"] / "bidirectional-cache"
    streaming.load_snapshot_handle(reuse["path"], cache)
    metrics = {}
    assert old_stream.load_snapshot_handle(reuse["path"], cache, metrics).valid
    assert metrics["t0_receipt_misses"] == 1
    metrics = {}
    assert streaming.load_snapshot_handle(reuse["path"], cache, metrics).valid
    assert metrics["t0_receipt_misses"] == 1


def test_snapshot_validator_writer_and_identity_algorithms_are_verbatim():
    old = ast.parse(historical_bytes(ROOT, "prospective_decision_retention.py"))
    new = ast.parse((ROOT / "prospective_decision_retention.py").read_text(encoding="utf-8"))
    functions = lambda tree: {node.name: ast.dump(node, include_attributes=False) for node in tree.body if isinstance(node, ast.FunctionDef)}
    before, after = functions(old), functions(new)
    for name in ("validate_snapshot", "build_snapshot", "write_immutable_snapshot", "_identity", "_hash"):
        assert before[name] == after[name], name
