"""Actual DRO -> Producer owner-file publication, using synthetic native deliveries."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from atomic_io import AtomicWriteError
import immutable_delivery as publication
import daily_research_session_operations as dro
import daily_producer_pipeline as producer
from daily_producer_pipeline import _retain_owner_delivery, _write_immutable, DailyProducerError
from tools.vault_snapshot import fingerprint
from test_ai_research_session_delivery import _operation


def allocation(paths):
    unique = {}
    for path in paths:
        fp = fingerprint(path)
        unique[(fp["device"], fp["inode"])] = fp["physical_bytes"]
    return {"physical_bytes": sum(unique.values()), "distinct_file_ids": len(unique)}


def operation_fixture():
    op = _operation()
    # One realistic full-universe denominator; no padding or fabricated GiB fixture.
    tickers = ["AAA", *[f"S{i:04d}" for i in range(1682)]]
    op["inputs"] = {"descriptive": {"records": {t: {} for t in tickers}},
                    "tactical": {"records": {}}, "fundamental": {"records": {}},
                    "valuation": {"records": {}}, "corporate_intelligence": {"records": {}}}
    op.update(snapshot={"snapshot_id": "snapshot:original"}, corporate_snapshot={"snapshot_id": "corporate:original"},
              strategy_snapshot={"snapshot_id": "strategy:original"})
    return op


def test_actual_dro_producer_allocation_and_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(dro, "markdown", lambda product: "synthetic presentation\n")
    op = operation_fixture()
    plain, linked = tmp_path / "plain", tmp_path / "linked"
    dro.materialize(plain / "operation", op)
    before_manifest = _retain_owner_delivery(plain / "operation", plain / "run")
    dro.materialize(linked / "operation", op, protect_delivery=True)
    after_manifest = _retain_owner_delivery(linked / "operation", linked / "run", reuse_delivery=True)
    assert before_manifest == after_manifest
    names = sorted(publication.DELIVERIES)
    before_paths = [plain / directory / name for directory in ("operation", "run") for name in names]
    after_paths = [linked / directory / name for directory in ("operation", "run") for name in names]
    before, after = allocation(before_paths), allocation(after_paths)
    family_allocations = {}
    for name in names:
        family_before = allocation([p for p in before_paths if p.name == name])
        family_after = allocation([p for p in after_paths if p.name == name])
        assert family_before["distinct_file_ids"] == 2 and family_after["distinct_file_ids"] == 1
        assert family_before["physical_bytes"] == 2 * family_after["physical_bytes"] > 0
        family_allocations[name] = {"before": family_before, "after": family_after,
            "saved_bytes": family_before["physical_bytes"] - family_after["physical_bytes"]}
    assert before["distinct_file_ids"] == 4 and after["distinct_file_ids"] == 2
    assert before["physical_bytes"] == 2 * after["physical_bytes"] > 0
    assert all(publication.sha(a) == publication.sha(b) for a, b in zip(before_paths, after_paths))
    native_before = {p: (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_ino) for p in after_paths}
    dro.materialize(linked / "operation", op, protect_delivery=True)
    assert _retain_owner_delivery(linked / "operation", linked / "run", reuse_delivery=True) == after_manifest
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_ino) for p in after_paths} == native_before
    assert _retain_owner_delivery(linked / "operation", linked / "run", reuse_delivery=False) == after_manifest
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_ino) for p in after_paths} == native_before
    with pytest.raises(DailyProducerError, match="IMMUTABLE_DAILY_PRODUCER_CONTENT_CONFLICT"):
        _write_immutable(after_paths[0], b"conflicting replay")
    # All original consumer-visible paths and manifest bytes remain usable.
    for name in ("ai_research_bundle_manifest.json", *names):
        assert (plain / "run" / name).read_bytes() == (linked / "run" / name).read_bytes()
    report = {"before": before, "after": after, "saved_bytes": before["physical_bytes"]-after["physical_bytes"],
              "source_sha_parity": True, "manifest_parity": True, "replay_parity": True,
              "record_count": 1683, "logical_bytes_by_family": {n: (linked / "run" / n).stat().st_size for n in names},
              "physical_allocation_by_family": family_allocations,
              "production_savings_bytes": 0}
    print("CAPACITY_WRITER_MEASUREMENT=" + json.dumps(report, sort_keys=True))


def test_completed_delivery_denies_cross_process_write(tmp_path):
    path = tmp_path / "ai_research_full_universe.ndjson"
    publication.publish_bytes(path, b'{"ticker":"AAA"}\n', protect=True)
    code = """import sys
from pathlib import Path
try:
 Path(sys.argv[1]).write_bytes(b'corrupted')
except PermissionError:
 sys.exit(0)
sys.exit(1)
"""
    result = subprocess.run([sys.executable, "-c", code, str(path)], capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert path.read_bytes() == b'{"ticker":"AAA"}\n'


def test_producer_entry_integrates_opt_in_and_preserves_run_identity(tmp_path, monkeypatch):
    op = operation_fixture()
    op["manifest"]["authority_boundary"] = op["product"]["authority_boundary"]
    monkeypatch.setattr(dro, "markdown", lambda product: "synthetic presentation\n")
    monkeypatch.setattr(producer, "load_registry", lambda *a: {})
    monkeypatch.setattr(producer, "completed_session_gate", lambda *a, **k: {"status": "PASS"})
    monkeypatch.setattr(producer, "resolve_inputs", lambda *a: (op["inputs"], {}))
    monkeypatch.setattr(producer, "validate_coherence", lambda *a: {"session": "2026-08-21"})
    monkeypatch.setattr(producer, "build_acquisition_plan", lambda *a, **k: {"items": []})
    shadow = {"artifact_identity": "shadow-chain:original", "source_artifact_identities": {},
              "fundamental_cohort_selection": {}, "fundamental_thesis_invalidation_precision": {"artifact_identity": "invalidation:original"},
              "shadow_security_recommendation": {"metadata": {"as_of_session": "2026-08-21"}, "artifact_identity": "shadow:original"}}
    monkeypatch.setattr(producer, "resolve_or_build_daily_session_shadow_recommendation",
                        lambda *a, **k: {"chain": shadow, "path": tmp_path / "shadow.json"})
    monkeypatch.setattr(producer, "materialize_and_write_current_product_projections", lambda **k: {"status": "UNAVAILABLE"})
    def materialize_operation(*a, **kw):
        folder = kw["output_root"] / "operation"
        dro.materialize(folder, op, protect_delivery=kw.get("protect_delivery", False))
        return op, folder
    monkeypatch.setattr(producer, "run_session_operation", materialize_operation)
    def run(mode):
        return producer.run_daily_producer(tmp_path, session="2026-08-21", latest_completed_session=False,
            producer_head="producer", consumer_head="consumer", output_root=tmp_path / mode / "run",
            operation_output_root=tmp_path / mode / "operation", reuse_immutable_delivery=mode == "linked")
    plain, linked = run("plain"), run("linked")
    assert plain["status"] == linked["status"] == "COMPLETED"
    assert plain["run_identity"] == linked["run_identity"]
    assert plain["manifest"]["ai_delivery"] == linked["manifest"]["ai_delivery"]
    assert plain["manifest"]["ai_dashboard_parity"] == linked["manifest"]["ai_dashboard_parity"]
    assert run("linked")["manifest"] == linked["manifest"]
    for name in publication.DELIVERIES:
        assert (linked["run_dir"] / name).stat().st_ino == (linked["operation_dir"] / name).stat().st_ino


@pytest.mark.parametrize("existing", [False, True])
def test_crash_before_publication_and_partial_retry(tmp_path, existing):
    target = tmp_path / "ai_research_full_universe.ndjson"
    if existing:
        publication.publish_bytes(target, b"complete", protect=True)
    def crash(stage):
        assert stage.read_bytes() == b"complete"
        raise RuntimeError("crash before publication")
    if existing:
        assert publication.publish_bytes(target, b"complete", protect=True, on_stage=crash) == "REUSED"
    else:
        with pytest.raises(RuntimeError, match="crash before"):
            publication.publish_bytes(target, b"complete", protect=True, on_stage=crash)
        assert not target.exists()
    assert not list(tmp_path.glob(".delivery-staging-*"))
    publication.publish_bytes(target, b"complete", protect=True)
    assert target.read_bytes() == b"complete"


def test_concurrent_publication_and_conflict(tmp_path):
    target = tmp_path / "ai_research_full_universe.ndjson"
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: publication.publish_bytes(target, b"complete", protect=True,
            on_stage=lambda stage: barrier.wait(timeout=15)), range(2)))
    assert results.count("PUBLISHED_IMMUTABLE") == 1
    assert target.read_bytes() == b"complete" and publication.protected(target)
    with pytest.raises(AtomicWriteError, match="CONTENT_CONFLICT"):
        publication.publish_bytes(target, b"conflict", protect=True)


@pytest.mark.parametrize("legacy", [False, True])
def test_cross_volume_or_legacy_is_independent_copy(tmp_path, legacy):
    source, target = tmp_path / "source" / "ai_research_full_universe.ndjson", tmp_path / "run" / "ai_research_full_universe.ndjson"
    publication.publish_bytes(source, b"complete", protect=not legacy)
    native_before = fingerprint(source)
    publication.retain_alias(source, target, expected_sha=publication.sha(source), expected_size=8,
                             volume=lambda p: "SOURCE" if Path(p) == source else "DESTINATION")
    assert source.stat().st_ino != target.stat().st_ino
    assert source.read_bytes() == target.read_bytes() == b"complete"
    assert fingerprint(source) == native_before


def test_crash_after_alias_publication_resumes_without_copy(tmp_path, monkeypatch):
    source, target = tmp_path / "operation" / "ai_research_full_universe.ndjson", tmp_path / "run" / "ai_research_full_universe.ndjson"
    publication.publish_bytes(source, b"complete", protect=True)
    original = publication._sync_directory
    def crash(path):
        raise RuntimeError("crash after publication")
    monkeypatch.setattr(publication, "_sync_directory", crash)
    with pytest.raises(RuntimeError, match="crash after"):
        publication.retain_alias(source, target, expected_sha=publication.sha(source), expected_size=8)
    monkeypatch.setattr(publication, "_sync_directory", original)
    assert publication.retain_alias(source, target, expected_sha=publication.sha(source), expected_size=8) == "REUSED"
    assert source.stat().st_ino == target.stat().st_ino


def test_partial_existing_output_and_wrong_source_proof_refuse(tmp_path):
    source, target = tmp_path / "operation" / "ai_research_full_universe.ndjson", tmp_path / "run" / "ai_research_full_universe.ndjson"
    publication.publish_bytes(source, b"complete", protect=True)
    with pytest.raises(AtomicWriteError, match="SOURCE_PROOF_MISMATCH"):
        publication.retain_alias(source, target, expected_sha="a"*64, expected_size=8)
    assert not target.exists()
    target.parent.mkdir(exist_ok=True); target.write_bytes(b"partial")
    with pytest.raises(AtomicWriteError, match="CONTENT_CONFLICT"):
        publication.retain_alias(source, target, expected_sha=publication.sha(source), expected_size=8)
    assert source.read_bytes() == b"complete" and target.read_bytes() == b"partial"


def test_delivery_publication_refuses_t0_and_symlink_domains(tmp_path):
    target = tmp_path / "prospective-decision-retention-v1" / "ai_research_full_universe.ndjson"
    with pytest.raises(AtomicWriteError, match="PROTECTED_EVIDENCE_DOMAIN"):
        publication.publish_bytes(target, b"complete", protect=True)
    assert not target.exists()


def test_retention_metadata_overlap_and_protection_never_authorize_apply():
    from tools.capacity_retained_eligibility import reconcile
    receipt = {"result": "VERIFIED", "source": {"root": "C:\\evidence", "volume_guid": "C-guid"},
               "destination": {"root": "W:\\backup", "volume_guid": "W-guid"}}
    row = dict(relative_path="operations-review/family-20261005/file.json", size=8, allocation_estimate=4096,
               c_file_id=42, vault_sha256="a"*64)
    candidates = {"vault_coverage": {"receipt_sha256": "b"*64, "ledger_sha256": "c"*64},
                  "groups": {"G1_IDENTICAL": [row], "G5_ONE_OFF": [row]}}
    keep = ["2026-10-08", "2026-10-07", "2026-10-06"]
    report = reconcile(candidates, receipt, keep)
    assert report["conditional_union_physical_bytes_estimate"] == 4096
    assert report["verified_reclaimable_bytes"] == 0 and report["production_apply_implemented"] is False
    assert all(r["eligibility"] == "BLOCKED" for g in report["groups"].values() for r in g["rows"])
    protected = reconcile(candidates, receipt, [*keep, "2026-10-05"])
    assert protected["conditional_union_physical_bytes_estimate"] == 0


def test_native_scope_continuation_preserves_prior_completion_and_history(tmp_path):
    from tools.stocklookup_roadmap import main
    state_path = Path(__file__).resolve().parents[1] / "docs/ROADMAP_STATE.json"
    state = json.loads(state_path.read_bytes())
    mid = state["current"]["milestone"]
    state["current"]["state"] = "COMPLETE"
    milestone = next(m for m in state["milestones"] if m["milestone_id"] == mid)
    milestone.update(state="COMPLETE", checkpoint="prior-checkpoint", terminal_disposition="PRIOR_PARTIAL_SUBSET")
    fixture = tmp_path / "state.json"
    fixture.write_text(json.dumps(state, indent=2), encoding="utf-8")
    args = ["--state-file", str(fixture), "--repo", str(tmp_path / "absent-repo"), "--continue-scope", mid,
            "--owner-override", "--scope-note", "OWNER_DIRECTIVE: bounded writer completion"]
    assert main(args) == 0
    continued = json.loads(fixture.read_bytes())
    after = next(m for m in continued["milestones"] if m["milestone_id"] == mid)
    assert continued["current"]["state"] == "ACTIVE"
    assert after["scope_continuations"][-1]["prior_checkpoint"] == "prior-checkpoint"
    assert after["scope_continuations"][-1]["prior_terminal_disposition"] == "PRIOR_PARTIAL_SUBSET"
    assert [m for m in continued["milestones"] if m["milestone_id"] != mid] == [m for m in state["milestones"] if m["milestone_id"] != mid]
    with pytest.raises(SystemExit):
        main(args)
