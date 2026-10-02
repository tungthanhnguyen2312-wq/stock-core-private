"""Exact-byte IID working-view promotion without a second serialization."""
import copy
import hashlib
import importlib
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

import canonical_post_close_pipeline as pipeline
import integrated_investment_decision_product as iid
import prospective_decision_outcome_feedback as feedback
from _integrated_decision_fixture import integrated_decision

SESSION = "2026-10-02"


def _written(tmp_path):
    artifact = integrated_decision(SESSION, ["FPT"])
    source, destination = tmp_path / "canonical.json", tmp_path / "view/iid.json"
    receipt = pipeline._write_json(source, artifact, capture_iid_receipt=True)
    destination.parent.mkdir()
    destination.write_bytes(b'{"previous":"valid"}\n')
    return artifact, source, destination, receipt


def test_exact_canonical_bytes_json_and_identity_preserved(tmp_path, monkeypatch):
    artifact, source, destination, receipt = _written(tmp_path)
    before, stat = source.read_bytes(), source.stat()
    assert before == (json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    assert receipt.serialized_sha256 == hashlib.sha256(before).hexdigest()
    monkeypatch.setattr(pipeline.json, "dump", lambda *a, **k: pytest.fail("second serialization"))
    pipeline._copy_iid_working_view(source, destination, session=SESSION, artifact=artifact, receipt=receipt)
    assert source.read_bytes() == destination.read_bytes() == before
    assert source.stat() == stat
    assert json.loads(destination.read_bytes()) == artifact
    assert iid.content_identity(artifact)["artifact_identity"] == artifact["artifact_identity"]


@pytest.mark.parametrize("failure", ["serialization", "write"])
def test_canonical_receipt_write_failure_preserves_source_and_view(tmp_path, monkeypatch, failure):
    artifact, source, destination, receipt = _written(tmp_path)
    source_bytes, destination_bytes = source.read_bytes(), destination.read_bytes()
    def fail(value, writer, **kwargs):
        writer.write("{partial")
        raise MemoryError("injected encoding failure")
    if failure == "serialization":
        monkeypatch.setattr(pipeline.json, "dump", fail)
    else:
        monkeypatch.setattr(pipeline._ReceiptWriter, "write", lambda *a: (_ for _ in ()).throw(OSError("write failure")))
    with pytest.raises((MemoryError, OSError)):
        pipeline._write_json(source, artifact, capture_iid_receipt=True)
    assert source.read_bytes() == source_bytes and destination.read_bytes() == destination_bytes
    assert not source.with_name(source.name + ".tmp").exists()


@pytest.mark.parametrize("damage", ["missing", "empty", "size", "same-stat-corruption", "other-session-bytes"])
def test_source_damage_preserves_previous_destination(tmp_path, damage):
    artifact, source, destination, receipt = _written(tmp_path)
    previous, stat = destination.read_bytes(), source.stat()
    if damage == "missing":
        source.unlink()
    elif damage == "empty":
        source.write_bytes(b"")
    elif damage == "size":
        source.write_bytes(source.read_bytes() + b" ")
    else:
        content = source.read_bytes()
        source.write_bytes(b"!" + content[1:] if damage == "same-stat-corruption" else content.replace(SESSION.encode(), b"2026-10-01"))
        os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    with pytest.raises((pipeline.CanonicalPostCloseError, FileNotFoundError)):
        pipeline._copy_iid_working_view(source, destination, session=SESSION, artifact=artifact, receipt=receipt)
    assert destination.read_bytes() == previous
    assert not list(destination.parent.glob(".iid-copy-*.tmp"))


@pytest.mark.parametrize("mismatch", ["receipt", "path", "session", "contract_version", "artifact_identity", "artifact_sha256", "empty"])
def test_unbound_receipts_and_headers_are_rejected(tmp_path, mismatch):
    artifact, source, destination, receipt = _written(tmp_path)
    before = destination.read_bytes()
    if mismatch == "receipt":
        receipt = None
    elif mismatch == "path":
        receipt = replace(receipt, path=tmp_path / "latest.json")
    elif mismatch == "empty":
        receipt = replace(receipt, size=0)
    else:
        artifact[mismatch] = "wrong"
    with pytest.raises(pipeline.CanonicalPostCloseError):
        pipeline._copy_iid_working_view(source, destination, session=SESSION, artifact=artifact, receipt=receipt)
    assert destination.read_bytes() == before


@pytest.mark.parametrize("failure", [None, "read", "replace", "fsync"])
def test_bounded_copy_and_failure_cleanup(tmp_path, monkeypatch, failure):
    artifact, source, destination, receipt = _written(tmp_path)
    previous, original_open, sizes = destination.read_bytes(), Path.open, []
    class Reader:
        def __enter__(self):
            self.handle = original_open(source, "rb")
            return self
        def __exit__(self, *args):
            self.handle.close()
        def read(self, size):
            sizes.append(size)
            assert 0 < size <= 1024 * 1024
            if failure == "read" and len(sizes) > 1:
                raise OSError("partial copy failure")
            return self.handle.read(min(size, 32) if failure == "read" else size)
    monkeypatch.setattr(Path, "open", lambda path, *a, **k: Reader() if path == source and a == ("rb",) else original_open(path, *a, **k))
    def fail(*args):
        raise OSError("promotion failure")
    if failure in ("replace", "fsync"):
        monkeypatch.setattr(pipeline.os, failure, fail)
    with monkeypatch.context() as guarded:
        guarded.setattr(Path, "read_bytes", lambda *_: pytest.fail("whole-file read"))
        if failure:
            with pytest.raises(OSError):
                pipeline._copy_iid_working_view(source, destination, session=SESSION, artifact=artifact, receipt=receipt)
        else:
            pipeline._copy_iid_working_view(source, destination, session=SESSION, artifact=artifact, receipt=receipt)
    assert sizes
    assert destination.read_bytes() == (previous if failure else source.read_bytes())
    assert not list(destination.parent.glob(".iid-copy-*.tmp"))


def _pipeline_fixture(tmp_path, monkeypatch, artifact):
    paths = pipeline.level2.session_artifact_paths(tmp_path, SESSION)
    original_load = pipeline._load
    retained = {paths["descriptive_research"]: {"records": {}},
                paths["exact_session_snapshot"]: {"records": {"FPT": {}}, "snapshot_identity": "snapshot:test"},
                paths["technical_recovery"]: {"artifact_identity": "technical:test"}}
    monkeypatch.setattr(pipeline, "_load", lambda path: retained.get(path) or original_load(path))
    monkeypatch.setattr(pipeline.level2, "resolve_technical_recovery_artifact", lambda *a, **k: {"selected_path": paths["technical_recovery"]})
    for name in ("technical_structure_context", "market_structure_breakout_product_projection", "market_wide_relative_volume_research", "tactical_momentum_context", "tactical_confirmation_context"):
        monkeypatch.setattr(importlib.import_module(name), "build_artifact", lambda **k: {"records": {"FPT": {}}})
    fin = importlib.import_module("canonical_daily_financial_v2_materialization")
    for name in ("build_engine_artifact", "build_evaluated_valuation_artifact"):
        monkeypatch.setattr(fin, name, lambda **k: {})
    monkeypatch.setattr(fin, "build_session_artifact", lambda **k: {"financial_analysis_product": {"records": {}}})
    monkeypatch.setattr(importlib.import_module("financial_v2_current_input_authority"), "resolve", lambda *a: {})
    monkeypatch.setattr(importlib.import_module("entity_classification_contract"), "resolve_current_research_entity_applicability", lambda *a: {})
    monkeypatch.setattr(importlib.import_module("canonical_current_product_projections"), "materialize_current_fundamental_feature_store_context", lambda **k: {"status": "UNAVAILABLE"})
    monkeypatch.setattr(pipeline, "resolve_current_session_priority_queue", lambda *a, **k: (None, {"status": "UNAVAILABLE"}))
    monkeypatch.setattr(iid, "build_artifact", lambda **k: copy.deepcopy(artifact))
    return paths


@pytest.mark.parametrize("failure", [None, "canonical-write", "copy", "wrong-session", "wrong-identity", "wrong-contract"])
def test_actual_enrichment_serializes_once_and_retains_both_p2a_summaries(tmp_path, monkeypatch, failure):
    artifact = integrated_decision(SESSION, ["FPT"])
    expected = copy.deepcopy(artifact)
    if failure in ("wrong-session", "wrong-identity", "wrong-contract"):
        artifact[{"wrong-session": "session", "wrong-identity": "artifact_identity", "wrong-contract": "contract_version"}[failure]] = "wrong"
    paths = _pipeline_fixture(tmp_path, monkeypatch, artifact)
    canonical = paths["integrated_investment_decision_product"]
    destination = pipeline.enrichment_output_path(tmp_path, SESSION, "integrated_investment_decision_product")
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b'{"previous":"valid"}\n')
    previous = destination.read_bytes()
    manifest = tmp_path / "run_manifest.json"
    manifest.write_text(json.dumps({"market_session": SESSION, "outputs": {"integrated_investment_decision_product": expected["artifact_identity"]}}))
    manifest_bytes = manifest.read_bytes()
    original_write, original_copy = pipeline._write_json, pipeline._copy_iid_working_view
    serializations, copies = [], []
    def write(path, value, **kwargs):
        if value.get("contract_version") == iid.CONTRACT_VERSION:
            serializations.append(path)
            if failure == "canonical-write":
                raise OSError("canonical write failure")
        return original_write(path, value, **kwargs)
    def promote(source, target, **kwargs):
        copies.append((source, target))
        if failure == "copy":
            raise OSError("copy failure")
        return original_copy(source, target, **kwargs)
    original_load = feedback._load_json
    def no_iid_parse(path):
        assert path not in (canonical, destination)
        return original_load(path)
    monkeypatch.setattr(pipeline, "_write_json", write)
    monkeypatch.setattr(pipeline, "_copy_iid_working_view", promote)
    monkeypatch.setattr(feedback, "_load_json", no_iid_parse)
    result = pipeline.build_enrichment_components(tmp_path, SESSION)["integrated_investment_decision_product"]
    assert manifest.read_bytes() == manifest_bytes
    if failure:
        assert result["status"] != "BUILT" and result["reason"]
        assert destination.read_bytes() == previous
        if failure == "canonical-write":
            assert not copies
        return
    assert result["status"] == "BUILT", result
    assert result["artifact"] == expected
    assert serializations == [canonical] and copies == [(canonical, destination)]
    assert canonical.read_bytes() == destination.read_bytes()
    cache = feedback._read_summary_cache(tmp_path)
    for path in (canonical, destination):
        entry = cache[feedback._relative(tmp_path, path)]
        assert entry["header"]["artifact_identity"] == expected["artifact_identity"]
        assert entry["source"] == feedback._source_fingerprint(path)
