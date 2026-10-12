"""Execute immutable V1 and candidate foundations on identical synthetic inputs."""
import ast
import copy
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import subprocess
import sys

import pytest

import bounded_artifact_stream as v1_stream
import daily_session_level2_package as v1_paths
import prospective_decision_retention as v1_json
from field_temporal_contract import _sanitize_for_json
from stocklookup_core.evidence import artifact_stream, bounded_json, session_paths
from tools import qualify_e4_infrastructure as qualifier

ROOT = Path(__file__).resolve().parents[1]
UNAVAILABLE = "current-official-event-context-integration-v1-UNAVAILABLE"
VALUES = [
    None, {}, [], "", "Tiếng Việt\n\t\"\\😀", {"z": 1, "a": "Việt Nam"},
    {"empty": [], "nested": {"z": [True, None, -0.0, 1.25, 1e100]}},
    {"records": {}}, {"records": []},
    {"z": 1, "records": {"VNM": {"price": -0.0}, "FPT": {"name": "Việt"}}, "a": []},
    {"records": [{"name": "Việt"}, {}, []], "meta": {"x": "\r\n"}},
    {1: "integer"}, {None: "null"}, {"a": 1, 2: 3},
    {"records": {1: "integer"}}, {"records": {"a": 1, 2: 3}},
    float("nan"), float("inf"), float("-inf"),
    {"records": {"A": {"nan": float("nan"), "infinity": float("inf")}}},
    {"records": [{"nan": float("nan")}]},
    {"unserializable": object()}, {"unicode": "\ud800"},
] + [{"records": {"A": {"value": "ấ" * size}, "B": {"value": "x" * size}}} for size in (65535, 65536, 65537)]


def result(function):
    try:
        return ("ok", function())
    except Exception as exc:
        return ("error", type(exc), str(exc))


@pytest.mark.parametrize("value", VALUES)
@pytest.mark.parametrize("pretty", [False, True])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_exact_bytes_errors_hashes_and_batches(value, pretty, newline, monkeypatch):
    monkeypatch.setattr(os, "linesep", newline)
    before = result(lambda: list(v1_json._json_bytes(value, pretty=pretty)))
    after = result(lambda: list(bounded_json.json_bytes(value, pretty=pretty)))
    assert after == before  # batches, exceptions and messages, not just concatenated bytes
    if after[0] == "ok":
        raw = b"".join(after[1])
        assert hashlib.sha256(raw).digest() == hashlib.sha256(b"".join(before[1])).digest()
        assert list(bounded_json.json_bytes(value, pretty=pretty)) == after[1]
        if pretty:
            assert raw.endswith(newline.encode())
        else:
            assert result(lambda: bounded_json.canonical_bytes(value)) == ("ok", raw)


@pytest.mark.parametrize("size", [65535, 65536, 65537])
def test_chunk_boundary_large_token(size):
    value = {"x": "x" * size, "z": 0}
    chunks = list(bounded_json.json_bytes(value))
    assert chunks == list(v1_json._json_bytes(value))
    assert max(map(len, chunks)) == size + 2  # original permits one token larger than 64 KiB


@pytest.mark.parametrize("value", [v for v in VALUES if isinstance(v, dict)])
def test_mapping_digest_exact_errors_and_content_identity(value):
    assert result(lambda: bounded_json.record_mapping_digest(value)) == result(lambda: v1_stream.record_mapping_digest(value))
    from stocklookup_core.decision import integrated_investment_decision_product as product
    assert result(lambda: product.content_identity(value)) == result(lambda: {
        "artifact_sha256": v1_stream.record_mapping_digest({k: v for k, v in value.items() if k not in product._IDENTITY_EXCLUDED}),
        "artifact_identity": product.CONTRACT_VERSION + ":" + v1_stream.record_mapping_digest({k: v for k, v in value.items() if k not in product._IDENTITY_EXCLUDED})})


@pytest.mark.parametrize("root", [Path("absent"), Path("."), PurePosixPath("/var/data"),
                                  PurePosixPath("relative/../nested"), PureWindowsPath("C:/data"),
                                  PureWindowsPath("C:relative"), PureWindowsPath("//host/share"),
                                  PureWindowsPath("D:/cross/root")])
@pytest.mark.parametrize("session", ["2026-10-08", "", "bad-session", "2026-10-08/nested", "../nested"])
def test_all_fixed_paths_against_original_path_flavours(root, session, monkeypatch):
    calls = []
    monkeypatch.setattr(v1_paths, "_latest_official_event_context_dir", lambda *a, **kw: calls.append((a, kw)) or UNAVAILABLE)
    original = v1_paths.session_artifact_paths(root, session)
    candidate = session_paths.session_artifact_paths(root, session, official_event_context_dir=UNAVAILABLE)
    assert candidate == original
    assert list(candidate) == list(original)
    assert len(candidate) == 50
    assert calls == [((root / "operations-review",), {"as_of_session": session})]
    assert session_paths.fixed_session_artifact_paths(root, session) == {k: v for k, v in original.items() if k != "official_event_context"}


@pytest.mark.parametrize("root,session", [(None, "2026-10-08"), ("raw-string", "2026-10-08"), (Path("."), None), (Path("."), 42)])
def test_invalid_input_error_parity(root, session):
    assert result(lambda: v1_paths.session_artifact_paths(root, session)) == result(lambda: session_paths.session_artifact_paths(root, session, official_event_context_dir=UNAVAILABLE))


def test_no_discovery_or_writes_and_explicit_event_selection(tmp_path, monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("unexpected I/O")
    for method in ("glob", "exists", "is_dir", "mkdir", "resolve", "open"):
        monkeypatch.setattr(Path, method, forbidden)
    directory = "current-official-event-context-integration-v1-20261008"
    paths = session_paths.session_artifact_paths(tmp_path, "2026-10-08", official_event_context_dir=directory)
    assert paths["official_event_context"] == tmp_path / "operations-review" / directory / "current_official_event_context_artifact.json"
    assert "20260823" in str(paths["fundamental"])
    assert "20260824" in str(paths["named_20260824_triage"])
    assert "official_event_context" not in session_paths.fixed_session_artifact_paths(tmp_path, "2026-10-08")
    with pytest.raises(TypeError):
        session_paths.session_artifact_paths(tmp_path, "2026-10-08")


def test_legacy_discovery_and_cpc_monkeypatch_remain_intact(tmp_path, monkeypatch):
    import canonical_post_close_pipeline as cpc
    assert cpc.level2 is v1_paths
    original = v1_paths.session_artifact_paths
    marker = {"exact_session_snapshot": tmp_path / "patched"}
    monkeypatch.setattr(cpc.level2, "session_artifact_paths", lambda *a, **kw: marker)
    assert v1_paths.session_artifact_paths(tmp_path, "2026-10-08") is marker
    assert session_paths.fixed_session_artifact_paths(tmp_path, "2026-10-08") is not marker
    for session in ("20261007", "20261009"):
        folder = tmp_path / "operations-review" / ("current-official-event-context-integration-v1-" + session)
        folder.mkdir(parents=True)
        (folder / "current_official_event_context_artifact.json").write_text("{}")
    legacy = original(tmp_path, "2026-10-08")
    assert legacy["official_event_context"].parent.name.endswith("20261007")
    assert legacy == session_paths.session_artifact_paths(tmp_path, "2026-10-08", official_event_context_dir=legacy["official_event_context"].parent.name)


@pytest.mark.parametrize("text", ['{}', '{"a":1,"records":{}}', '{"records":{"A":{"v":"Việt"},"B":{}}}',
                                '{"records":{"A":{},"A":{}}}', '{"b":1,"a":2}', '{"records":{"B":{},"A":{}}}',
                                '{"records":{}} trailing', '{"records":', '{"a":NaN,"records":{}}',
                                '{"a":Infinity,"records":{}}'])
@pytest.mark.parametrize("sanitize", [False, True])
def test_stream_parser_hash_and_failure_parity(tmp_path, text, sanitize):
    path = tmp_path / "synthetic.json"
    path.write_text(text, encoding="utf-8")
    before_rows, after_rows = [], []
    before = result(lambda: v1_stream.stream_artifact(path, excluded=set(), on_record=lambda *r: before_rows.append(r), sanitize=sanitize))
    after = result(lambda: artifact_stream.stream_artifact(path, excluded=set(), on_record=lambda *r: after_rows.append(r), sanitize=_sanitize_for_json if sanitize else None))
    assert before == after
    assert before_rows == after_rows
    assert artifact_stream.source_hash(path) == v1_stream.source_hash(path)


@pytest.mark.parametrize("reader", [v1_stream.ObjectStream, artifact_stream.ObjectStream])
def test_bounded_reader_limits_and_unsorted_duplicate_keys(reader):
    parser = reader(io.StringIO('{"a":"' + 'x' * 400 + '"}'), limit=100)
    with pytest.raises(ValueError, match="ACCEPTANCE_JSON_MEMBER_LIMIT"):
        for key in parser.members():
            parser.value()
    parser = reader(io.StringIO('{"a":1,"a":2}'), sorted_required=False)
    with pytest.raises(ValueError, match="ACCEPTANCE_OBJECT_DUPLICATE_OR_NON_STRING_KEY"):
        for key in parser.members():
            parser.value()


def test_large_records_remain_record_bounded(monkeypatch):
    value = {"records": {str(i): {"text": "ấ" * 500} for i in range(2000)}, "session": "2026-10-08"}
    expected = hashlib.sha256(v1_stream.canonical_bytes(value)).hexdigest()
    original = json.JSONEncoder.encode
    def guarded(self, member):
        assert member is not value and member is not value["records"]
        return original(self, member)
    monkeypatch.setattr(json.JSONEncoder, "encode", guarded)
    assert bounded_json.record_mapping_digest(value) == expected
    chunks = bounded_json.json_bytes(value, pretty=True)
    assert max(len(chunk) for chunk in chunks) < 4096


@pytest.mark.parametrize("order", [
    ["prospective_decision_retention", "bounded_artifact_stream", "stocklookup_core.evidence.bounded_json"],
    ["bounded_artifact_stream", "prospective_decision_retention", "stocklookup_core.evidence.bounded_json"],
    ["stocklookup_core.evidence.bounded_json", "stocklookup_core.evidence.artifact_stream", "prospective_decision_retention"],
    ["stocklookup_core.evidence.session_paths", "daily_session_level2_package", "canonical_post_close_pipeline"],
])
def test_import_order_and_foundation_isolation(order):
    source = "import importlib,sys\n"
    source += "for name in " + repr(order) + ": importlib.import_module(name)\n"
    source += "from stocklookup_core.evidence import bounded_json as j\nassert b''.join(j.json_bytes({'x':'Việt'})) == '{\"x\":\"Việt\"}'.encode()\n"
    subprocess.run([sys.executable, "-c", source], cwd=ROOT, check=True, capture_output=True)


def test_foundations_never_import_orchestration():
    source = '''from stocklookup_core.evidence import bounded_json, artifact_stream, session_paths
import sys
assert not {'daily_session_level2_package','prospective_decision_retention','bounded_artifact_stream','canonical_post_close_pipeline'} & set(sys.modules)
'''
    subprocess.run([sys.executable, "-c", source], cwd=ROOT, check=True, capture_output=True)
    for file in ("bounded_json.py", "session_paths.py", "artifact_stream.py"):
        tree = ast.parse((ROOT / "stocklookup_core/evidence" / file).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(n.name.split('.')[0] in sys.stdlib_module_names for n in node.names)
            if isinstance(node, ast.ImportFrom):
                assert node.module.split('.')[0] in sys.stdlib_module_names or node.module == "stocklookup_core.evidence.bounded_json"


def test_source_identity_version_mismatch_is_not_byte_parity(tmp_path):
    import prospective_feedback_streaming as feedback
    before = qualifier.source_identity(ROOT, version="v1")
    candidate = qualifier.source_identity(ROOT, version="v2")
    assert before["code_digest"] == feedback.code_digest()
    assert before["code_digest"] != candidate["code_digest"]
    retained = {**copy.deepcopy(candidate), "input_digest": "fixed"}
    assert qualifier.candidate_reuse_eligible(retained, candidate, input_digest="fixed")
    for key, bad in (("source_version", "v1"), ("contract_version", "unknown"), ("code_digest", "0" * 64), ("input_digest", "different")):
        changed = {**retained, key: bad}
        assert not qualifier.candidate_reuse_eligible(changed, candidate, input_digest="fixed")
    assert not qualifier.candidate_reuse_eligible({**before, "input_digest": "fixed"}, candidate, input_digest="fixed")
    assert not qualifier.candidate_reuse_eligible({"code_digest": candidate["code_digest"], "input_digest": "fixed"}, candidate, input_digest="fixed")
    assert retained == {**candidate, "input_digest": "fixed"}
    with pytest.raises(ValueError, match="UNSUPPORTED"):
        qualifier.source_identity(ROOT, version="v3")
    with pytest.raises(FileNotFoundError):
        qualifier.source_identity(tmp_path, version="v2")
    for item in candidate["sources"].values():
        path = tmp_path / item["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / item["path"]).read_bytes())
    assert qualifier.source_identity(tmp_path, version="v2") == candidate
    foundation = tmp_path / "stocklookup_core/evidence/bounded_json.py"
    foundation.write_bytes(foundation.read_bytes() + b"\n# changed candidate source\n")
    modified = qualifier.source_identity(tmp_path, version="v2")
    assert modified["code_digest"] != candidate["code_digest"]
    assert qualifier.source_identity(tmp_path, version="v1") == before
    assert not qualifier.candidate_reuse_eligible(retained, modified, input_digest="fixed")


def test_offline_qualifier_executes_candidate_and_preserves_v1_sources():
    qualified = qualifier.qualify(ROOT)
    assert qualified["production_v2_activation"] == "NOT_AUTHORIZED"
    assert not qualified["v1_reuse_eligible_for_v2"]
    assert all(row["byte_parity"] for row in qualified["outputs"])
    manifest = json.loads((ROOT / "tests/fixtures/e2e3_frozen_sources.json").read_text(encoding="utf-8"))
    for path, expected in manifest["source_sha256_lf"].items():
        assert hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == expected


def baseline_module(relative):
    """Only the three reviewed library modules; never inspect/execute a CLI runner."""
    import types
    source = subprocess.check_output(["git", "show", "0061d5f8afe4275ef6cf1dd7ba44930f559d2278:" + relative], cwd=ROOT)
    module = types.ModuleType("e4_baseline_library")
    exec(compile(source, relative, "exec"), module.__dict__)
    return module


def test_daily_brief_actual_baseline_and_candidate_join(tmp_path, monkeypatch):
    from stocklookup_core.decision import daily_integrated_decision_brief as candidate
    from test_daily_integrated_decision_brief import _record
    baseline = baseline_module("stocklookup_core/decision/daily_integrated_decision_brief.py")
    session = "2026-08-28"
    paths = v1_paths.session_artifact_paths(tmp_path, session)
    values = {
        "integrated_investment_decision_product": {"session": session, "artifact_identity": "integrated_investment_decision_product/v1:fixture", "records": {"VNM": _record("VNM", posture="WAIT_FOR_CONFIRMATION")}, "coverage": {}},
        "descriptive_research": {"session": session, "artifact_identity": "descriptive:fixture"},
        "sector_leadership": {"session": session, "artifact_identity": "sector:fixture", "records": {}},
        "exact_session_snapshot": {"session": session, "snapshot_identity": "prices:fixture", "records": {}},
    }
    for key, value in values.items():
        paths[key].parent.mkdir(parents=True, exist_ok=True)
        paths[key].write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(candidate.feedback_bridge, "governed_session_chain", lambda *a, **kw: [])
    monkeypatch.setattr(candidate.feedback_bridge, "build_prospective_feedback_status", lambda **kw: {"status": "UNAVAILABLE", "reason_codes": ["SYNTHETIC_NO_CHAIN"]})
    args = {"root": tmp_path, "session": session, "next_session_brief": {"current_session": session, "artifact_identity": "next_session_decision_brief/v2:fixture", "previous_qualified_session": None}}
    before = baseline.build_from_session(**args)
    after = candidate.build_from_session(**args)
    assert after == before and after is not None
    assert bounded_json.canonical_bytes(after) == bounded_json.canonical_bytes(before)
    paths["integrated_investment_decision_product"].unlink()
    assert baseline.build_from_session(**args) is candidate.build_from_session(**args) is None


@pytest.mark.parametrize("stage", ["t0", "current"])
def test_thesis_real_streamed_baseline_and_candidate_products(tmp_path, stage):
    from stocklookup_core.research import thesis_evidence_production as candidate
    from test_thesis_evidence_stage2 import fixture
    baseline = baseline_module("stocklookup_core/research/thesis_evidence_production.py")
    args, *_ = fixture(tmp_path, two=True)
    args.pop("output_root")
    baseline.build(**args, output_root=tmp_path / "baseline", stage=stage, origin="SEAL_TIME")
    candidate.build(**args, output_root=tmp_path / "candidate", stage=stage, origin="SEAL_TIME")
    before = {path.relative_to(tmp_path / "baseline").as_posix(): path.read_bytes() for path in (tmp_path / "baseline").rglob("*.ndjson")}
    after = {path.relative_to(tmp_path / "candidate").as_posix(): path.read_bytes() for path in (tmp_path / "candidate").rglob("*.ndjson")}
    assert before and after == before
    manifests = [json.loads(next((tmp_path / directory).rglob("manifest.json")).read_bytes()) for directory in ("baseline", "candidate")]
    assert manifests[0]["input_digest"] == manifests[1]["input_digest"]
    assert manifests[0]["matrix_identity_digest"] == manifests[1]["matrix_identity_digest"]
