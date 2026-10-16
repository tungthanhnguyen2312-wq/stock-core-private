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
    legacy = types.ModuleType("isolated_legacy_retention")
    legacy.__file__ = str(ROOT / ARCHIVE)
    exec(compile(historical_bytes(ROOT, "prospective_decision_retention.py"), ARCHIVE, "exec"), legacy.__dict__)
    old_stream = types.ModuleType("isolated_historical_stream")
    old_stream.__file__ = streaming.__file__
    original_import = builtins.__import__
    def old_import(name, *args, **kwargs):
        if name == "prospective_decision_retention": return legacy
        if name == "prospective_feedback_streaming": return old_stream
        return original_import(name, *args, **kwargs)
    old_stream.__dict__["__builtins__"] = {**vars(builtins), "__import__": old_import}
    exec(compile(Path(streaming.__file__).read_text(encoding="utf-8"), streaming.__file__, "exec"), old_stream.__dict__)
    old_stream.import_module = lambda name: legacy if name == "prospective_decision_retention" else importlib.import_module(name)
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
