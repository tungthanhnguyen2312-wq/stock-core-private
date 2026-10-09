"""Small isolated fixtures; never retained production data or provider acquisition."""
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

import retained_evidence_catalog as catalog
import daily_session_level2_package as level2
from tools import storage_capacity_plan as capacity, vault_snapshot as v, vault_post_daily_adapter as adapter

SESSION = "2026-10-07"


def assert_writer_refused(path):
    code = """import sys
from pathlib import Path
from tools import vault_snapshot as v
try:
    with v.locked_file(Path(sys.argv[1]), writer=True):
        pass
except v.Refused:
    sys.exit(0)
sys.exit(1)
"""
    result = subprocess.run([sys.executable, "-c", code, str(path)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_source_owner_reuses_handle_and_retains_outer_lock(tmp_path):
    path = tmp_path / "proof.json"
    path.write_bytes(b"original")
    owner = v.LockedSources()
    with owner:
        owner.acquire(path)
        with owner.borrow(path) as first:
            fd = first.fileno()
            assert first.read() == b"original"
            with pytest.raises(v.Refused, match="already borrowed"):
                with owner.borrow(path):
                    pass
        assert_writer_refused(path)
        with owner.borrow(path) as second:
            assert second.fileno() == fd and second.tell() == 0
        assert_writer_refused(path)
    assert first.closed
    with pytest.raises(v.Refused, match="inactive"):
        owner.acquire(path)
    with v.locked_file(path, writer=True):
        pass


def test_adapter_locks_have_no_qualification_copy_gap(vault_fixture, monkeypatch):
    source, vault, expected, observer = vault_fixture
    pair = boundary_fixture(vault_fixture, qualified=True)
    original = v.locked_file
    acquired, active = [], set()

    @contextmanager
    def tracked(path, *, writer=False):
        with original(path, writer=writer) as stream:
            if not writer:
                acquired.append(path)
                active.add(path)
            try:
                yield stream
            finally:
                active.discard(path)

    monkeypatch.setattr(v, "locked_file", tracked)
    with adapter.qualified_boundary(source, *pair, max_bytes=64 * v.CHUNK) as owner:
        qualified = set(active)
        assert pair[0].absolute() in qualified
        def during_copy(path, stage):
            assert qualified <= active
            assert path in active
            assert_writer_refused(path)
        result = v.snapshot(source, vault, *pair, expected, observer=observer,
                            locked_sources=owner, on_chunk=during_copy)
        assert result["status"] == "VERIFIED" and qualified <= active
        assert len(acquired) == len(set(acquired))
        assert_writer_refused(source / "handoff.json")
    assert not active


def test_adapter_preserves_destination_writer_exclusivity(vault_fixture):
    source, vault, expected, observer = vault_fixture
    pair = boundary_fixture(vault_fixture, qualified=True)
    lock = vault / ".writer.lock"
    lock.touch()
    with v.locked_file(lock, writer=True):
        assert_writer_refused(lock)
        with pytest.raises(v.Refused, match="exclusivity"):
            adapter.snapshot_completed(source, vault, *pair, expected, opt_in=True, observer=observer)
    assert not list(vault.glob("snapshots/*/manifest.json"))


@pytest.mark.skipif(os.name == "nt", reason="POSIX permits replacement despite advisory flock")
@pytest.mark.parametrize("target", ["boundary", "source"])
def test_adapter_refuses_same_bytes_pathname_replacement(vault_fixture, target):
    source, vault, expected, observer = vault_fixture
    pair = boundary_fixture(vault_fixture, qualified=True)
    replaced = []
    def replace(path, stage):
        if replaced:
            return
        victim = pair[0] if target == "boundary" else path
        replacement = victim.with_name(victim.name + ".replacement")
        replacement.write_bytes(victim.read_bytes())
        os.replace(replacement, victim)
        replaced.append(victim)
    with pytest.raises(v.Refused, match="pathname/inode changed"):
        adapter.snapshot_completed(source, vault, *pair, expected, opt_in=True,
                                   observer=observer, on_chunk=replace)
    assert replaced and not list(vault.glob("snapshots/*/manifest.json"))


@pytest.mark.parametrize("target", ["payload", "registry", "boundary"])
def test_adapter_source_mutation_during_copy(vault_fixture, target):
    source, vault, expected, observer = vault_fixture
    pair = boundary_fixture(vault_fixture, qualified=True)
    attempted = []
    def mutate(path, stage):
        if attempted:
            return
        path = path if target == "payload" else source / "registry.json" if target == "registry" else pair[0]
        attempted.append(path)
        if os.name == "nt":
            with pytest.raises(PermissionError):
                path.write_bytes(b"mutation")
        else:
            path.write_bytes(b"mutation")
    if os.name == "nt":
        result = adapter.snapshot_completed(source, vault, *pair, expected, opt_in=True,
                                            observer=observer, on_chunk=mutate)
        assert result["status"] == "COMPLETE"
    else:
        with pytest.raises(v.Refused):
            adapter.snapshot_completed(source, vault, *pair, expected, opt_in=True,
                                       observer=observer, on_chunk=mutate)
        assert not list(vault.glob("snapshots/*/manifest.json"))
    assert attempted


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = v.canonical(value)
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)
    return dict(relative_path=path.name, sha256=v.sha(path))


def entry(root, *, state="ARCHIVED_COLD", role="exact_session_snapshot"):
    rel = level2.session_artifact_paths(root, SESSION)[role].relative_to(root).as_posix()
    return dict(relative_path=rel, session_identity=SESSION, artifact_identity="snapshot:original",
                artifact_role=role, state=state, original_size=3, sha256=v.digest(b"old"),
                source_seal_provenance={"source_identity": "original", "seal_sha256": "a"*64},
                vault=dict(snapshot_identity="verified-snapshot", manifest_path="snapshots/one/manifest.json",
                           manifest_sha256="a"*64, object_path="snapshots/one/files/original.json",
                           object_sha256=v.digest(b"old"), volume_id="W-fixture"),
                restore_procedure="Copy exact original bytes, verify native SHA, explicit local event",
                restore_preconditions=["Exact W volume", "Original seal verifier", "Owner approval"])


def install(root, entries):
    write(root / "config/retained_evidence_cold_catalog.json", dict(schema=catalog.SCHEMA, entries=entries))


@pytest.mark.parametrize("role", ["exact_session_snapshot", "dnse_only_exact_session_snapshot"])
def test_cold_blocks_before_any_provider_or_credential_work(tmp_path, monkeypatch, role):
    import mva_exact_session_snapshot as snapshotter
    import dnse_secrets_env
    install(tmp_path, [entry(tmp_path, role=role)])
    monkeypatch.setattr(snapshotter, "canonical_candidates", lambda *a: pytest.fail("provider preparation"))
    monkeypatch.setattr(snapshotter, "materialize_snapshot", lambda **k: pytest.fail("network"))
    monkeypatch.setattr(dnse_secrets_env, "ensure_credentials_loaded", lambda: pytest.fail("credentials"))
    with pytest.raises(catalog.ArchiveRestoreRequired, match="RESTORE_REQUIRED") as caught:
        level2.ensure_exact_session_snapshot(tmp_path, SESSION, tmp_path / "runtime")
    assert caught.value.locator["snapshot_identity"] == "verified-snapshot"


def test_fresh_attempt_cannot_bypass_session_cold_entry(tmp_path, monkeypatch):
    install(tmp_path, [entry(tmp_path)])
    with pytest.raises(catalog.ArchiveRestoreRequired):
        level2.ensure_exact_session_snapshot(tmp_path / "attempt", SESSION, tmp_path / "runtime",
                                            execution_root=tmp_path)


def test_registered_cold_canonical_blocks_fallback_regeneration(tmp_path):
    install(tmp_path, [entry(tmp_path)])
    attempt = tmp_path / "attempt"
    fallback = level2.session_artifact_paths(attempt, SESSION)["dnse_only_exact_session_snapshot"]
    fallback.parent.mkdir(parents=True)
    fallback.write_bytes(b"existing attempt bytes")
    with pytest.raises(catalog.ArchiveRestoreRequired):
        level2.ensure_exact_session_snapshot(attempt, SESSION, tmp_path / "runtime", execution_root=tmp_path)
    assert fallback.read_bytes() == b"existing attempt bytes"


@pytest.mark.parametrize("damage", ["unknown", "duplicate", "malformed", "wrong-session", "missing-local", "corrupt-local"])
def test_catalog_fails_closed(tmp_path, damage):
    row = entry(tmp_path)
    if damage == "unknown": row["state"] = "UNKNOWN_OR_CONFLICTED"
    if damage == "malformed": del row["vault"]["manifest_sha256"]
    if damage == "wrong-session": row["session_identity"] = "2026-10-06"
    if damage in {"missing-local", "corrupt-local"}: row["state"] = "PRESENT_ON_C"
    if damage == "corrupt-local":
        path = v.safe_path(tmp_path, row["relative_path"])
        path.parent.mkdir(parents=True)
        path.write_bytes(b"bad")
    install(tmp_path, [row, row] if damage == "duplicate" else [row])
    with pytest.raises(catalog.EvidenceIntegrityError):
        catalog.resolve(tmp_path, row["relative_path"], session_identity=SESSION)


def test_explicit_missing_local_differs_from_never_retained_and_completion_claim(tmp_path):
    install(tmp_path, [])
    rel = entry(tmp_path)["relative_path"]
    assert catalog.resolve(tmp_path, rel) == "NEVER_RETAINED"
    catalog.guard_acquisition(tmp_path, SESSION)
    write(tmp_path / "config/daily_research_session_input_registry.json",
          dict(completed_sessions={SESSION: dict(status="COMPLETED_RETAINED_EVIDENCE")}))
    with pytest.raises(catalog.EvidenceIntegrityError, match="COMPLETED_SESSION_EVIDENCE_MISSING"):
        catalog.guard_acquisition(tmp_path, SESSION)
    row = entry(tmp_path, state="PRESENT_ON_C")
    install(tmp_path, [row])
    with pytest.raises(catalog.EvidenceIntegrityError, match="LOCAL_EVIDENCE_MISSING"):
        catalog.resolve(tmp_path, rel)


def test_never_retained_keeps_governed_acquisition_boundary(tmp_path, monkeypatch):
    import mva_exact_session_snapshot as snapshotter
    install(tmp_path, [])
    class ReachedEligibleAcquisition(Exception): pass
    def reached(*args): raise ReachedEligibleAcquisition()
    monkeypatch.setattr(snapshotter, "canonical_candidates", reached)
    with pytest.raises(ReachedEligibleAcquisition):
        level2.ensure_exact_session_snapshot(tmp_path, SESSION, tmp_path / "runtime")


def test_local_present_reuses_normal_snapshot_and_does_not_read_cold_fallback(tmp_path, monkeypatch):
    row = entry(tmp_path, role="dnse_only_exact_session_snapshot")
    install(tmp_path, [row])
    path = level2.session_artifact_paths(tmp_path, SESSION)["exact_session_snapshot"]
    path.parent.mkdir(parents=True)
    path.write_text('{"snapshot_identity":"original"}')
    monkeypatch.setattr(level2, "_canonical_snapshot_gate_satisfied", lambda *a, **k: True)
    assert level2.ensure_exact_session_snapshot(tmp_path, SESSION, tmp_path / "runtime") == path


def test_feedback_cold_fails_and_original_t0_is_untouched(tmp_path):
    import prospective_decision_outcome_feedback as feedback
    t0 = tmp_path / "operations-review/prospective-decision-retention-v1/original/t0.json"
    t0.parent.mkdir(parents=True)
    t0.write_bytes(b"original sealed T0")
    before = v.fingerprint(t0)
    install(tmp_path, [entry(tmp_path)])
    with pytest.raises(catalog.ArchiveRestoreRequired):
        feedback.retained_session_snapshots(tmp_path, [SESSION])
    assert v.fingerprint(t0) == before and t0.read_bytes() == b"original sealed T0"


def test_explicit_verified_local_event_then_consumer_read(tmp_path):
    row = entry(tmp_path)
    install(tmp_path, [row])
    local = v.safe_path(tmp_path, row["relative_path"])
    local.parent.mkdir(parents=True)
    local.write_bytes(b"old")  # isolated restore fixture
    with pytest.raises(catalog.ArchiveRestoreRequired):
        catalog.resolve(tmp_path, row["relative_path"])
    row["state"] = "PRESENT_ON_C"
    install(tmp_path, [row])  # fixture-only event; there is no production catalog writer
    assert catalog.resolve(tmp_path, row["relative_path"]) == "PRESENT_ON_C"
    assert local.read_bytes() == b"old" and v.sha(local) == row["sha256"]


@pytest.fixture
def vault_fixture(tmp_path):
    source, vault = tmp_path / "source", tmp_path / "vault"
    source.mkdir(); vault.mkdir()
    expected = dict(source=dict(id="C-fixture", label="source", healthy=True),
                    destination=dict(id="W-fixture", label="vault", healthy=True))
    def observer(path):
        return expected["destination" if Path(path).is_relative_to(vault) else "source"].copy()
    return source, vault, expected, observer


def boundary_fixture(fixture, *, qualified=False):
    source, _, _, _ = fixture
    from daily_research_session_operations import _identity
    from daily_producer_pipeline import _run_identity
    operation = dict(market_session=SESSION)
    operation["operation_identity"] = _identity(operation)
    op = operation["operation_identity"]
    run = _run_identity(SESSION, "producer-head", "consumer-head", {}, op)
    documents = dict(registry=dict(completed_sessions={SESSION: dict(status="COMPLETED_RETAINED_EVIDENCE", trading_day_valid=True)}),
        completion_record=dict(session=SESSION, daily_operation_state="LOCAL_COMPLETE", daily_producer_status="COMPLETED",
            runtime_release_status="READY", trusted_subset_status="READY", acquisition=dict(resolved_completed_session=SESSION),
            daily_producer_operation_identity=op, daily_producer_run_identity=run),
        handoff=dict(market_session_proof=dict(resolved_completed_session=SESSION),
            daily_producer=dict(status="COMPLETED", run_identity=run, operation_identity=op)),
        producer_manifest=dict(target_market_session=SESSION, run_identity=run, producer_head="producer-head",
            consumer_head="consumer-head", source_plan={}, daily_session_operation=dict(identity=op)),
        operation_manifest=operation)
    proof = {}
    for key, doc in documents.items():
        path = source / (key + ".json")
        proof[key] = write(path, doc)
    if not (source / "historical-feedback.bin").exists():
        (source / "historical-feedback.bin").write_bytes(b"evidence-native-bytes")
    files = []
    for path in source.iterdir():
        if path.name == "registry.json": continue
        files.append(dict(relative_path=path.name, size=path.stat().st_size, sha256=v.sha(path),
                          family="IMMUTABLE_SESSION", state="COMPLETE", immutable=True, lock_dependent=False))
    b = dict(schema="vault_completed_boundary/v1", status="COMPLETE", session_identity=SESSION,
             source_identity=op, cutoff="2026-10-07T15:00:00+07:00", files=files,
             receipt_refs=[proof[k] for k in ("completion_record", "handoff", "producer_manifest")],
             seal_refs=[proof["operation_manifest"]])
    if qualified: b["completion_proof"] = proof
    path = source.parent / "boundary.json"
    write(path, b)
    return path, v.sha(path)


def proposal_fixture():
    candidate = dict(relative_path="historical-feedback.bin", group="G2", session_identity=SESSION,
        artifact_identity="feedback:original", second_copy="OWNER_ACCEPTED_SINGLE_COPY",
        restore_procedure="Copy pinned object to exact path, native hash then consumer verifier",
        restore_preconditions=["Owner exact-path approval", "W GUID", "Seal provenance"],
        reader_dependency_closure=dict(status="VERIFIED", proof_sha256="a"*64, runtime=[], code=[], manifest=[],
                                      cross_session=[], external=[]))
    return dict(schema="capacity_exact_path_proposal/v1", keep_sessions=["2026-10-08", "2026-10-09", "2026-10-12"],
                candidates=[candidate])


def run_plan(fixture, proposal, **kwargs):
    source, vault, expected, observer = fixture
    pair = boundary_fixture(fixture)
    snapshot = v.snapshot(source, vault, *pair, expected, observer=observer)
    manifest = vault / "snapshots" / snapshot["snapshot_identity"] / "manifest.json"
    return capacity.plan(source, vault, proposal, v.digest(v.canonical(proposal)), manifest,
                         snapshot["manifest_sha256"], expected, observer=observer, **kwargs)


def test_deterministic_verified_plan_and_no_production_apply(vault_fixture):
    proposal = proposal_fixture()
    first = run_plan(vault_fixture, proposal)
    assert first["reclaimed_bytes"] == 0 and first["potential_allocation_bytes"] > 0
    assert first["candidates"][0]["eligible"]
    assert first["production_apply_implemented"] is False
    assert run_plan(vault_fixture, proposal) == first


@pytest.mark.parametrize("blocker", ["active", "unknown", "recent", "second", "hardlink", "t0", "mva", "G4"])
def test_candidate_refusal_even_with_byte_match(vault_fixture, blocker):
    p = proposal_fixture(); row = p["candidates"][0]
    if blocker == "active": row["reader_dependency_closure"]["runtime"] = ["active reader"]
    if blocker == "unknown": del row["reader_dependency_closure"]
    if blocker == "recent": p["keep_sessions"][0] = SESSION
    if blocker == "second": del row["second_copy"]
    if blocker == "hardlink": row["group"] = "G1"
    if blocker == "t0": row["relative_path"] = "operations-review/prospective-decision-retention-v1/s/t0.json"
    if blocker == "mva": row["relative_path"] = "p3f9b_mva_exact_session_snapshot.json"
    if blocker == "G4": row["group"] = "G4"
    result = run_plan(vault_fixture, p)
    assert not result["candidates"][0]["eligible"] and result["potential_allocation_bytes"] == 0


def test_plan_byte_ceiling(vault_fixture):
    with pytest.raises(v.Refused, match="ceiling"):
        run_plan(vault_fixture, proposal_fixture(), max_bytes=1)


def test_synthetic_apply_undo_restore_and_independent_reads():
    assert capacity.rehearsal(b'{"original":"identity"}\n') == dict(linked=True, independent_consumer_read=True,
        undo_independent=True, restored=True, production_mutation=False)


def test_adapter_opt_in_completion_parity_and_retry(vault_fixture):
    source, vault, expected, observer = vault_fixture
    pair = boundary_fixture(vault_fixture, qualified=True)
    before = {p.name: p.read_bytes() for p in source.iterdir()}
    with pytest.raises(v.Refused, match="opt-in"):
        adapter.snapshot_completed(source, vault, *pair, expected, observer=observer)
    first = adapter.snapshot_completed(source, vault, *pair, expected, opt_in=True, observer=observer)
    assert first["status"] == "COMPLETE" and not first["daily_completion_changed"]
    assert adapter.snapshot_completed(source, vault, *pair, expected, opt_in=True, observer=observer) == first
    assert {p.name: p.read_bytes() for p in source.iterdir()} == before


@pytest.mark.parametrize("failure", ["incomplete", "wrong-handoff", "tampered", "mutable", "seal", "wrong-volume", "missing-volume"])
def test_adapter_refuses_bad_completion_and_optional_missing_vault(vault_fixture, failure):
    source, vault, expected, observer = vault_fixture
    path, sha = boundary_fixture(vault_fixture, qualified=True)
    b = json.loads(path.read_bytes())
    if failure in {"incomplete", "wrong-handoff"}:
        key = "registry" if failure == "incomplete" else "handoff"
        doc_path = source / b["completion_proof"][key]["relative_path"]
        doc = json.loads(doc_path.read_bytes())
        if failure == "incomplete": doc["completed_sessions"][SESSION]["status"] = "PENDING"
        else: doc["daily_producer"]["run_identity"] = "different"
        write(doc_path, doc)
        b["completion_proof"][key]["sha256"] = v.sha(doc_path)
    if failure == "tampered": (source / "operation_manifest.json").write_bytes(b"tampered")
    if failure == "mutable": b["files"][0]["relative_path"] = "config/accumulator.json"
    if failure == "seal": b["seal_refs"] = [b["receipt_refs"][0]]
    write(path, b); sha = v.sha(path)
    if failure in {"wrong-volume", "missing-volume"}:
        def bad_observer(p):
            if failure == "missing-volume": raise v.Refused("missing W")
            return dict(id="wrong", label="wrong", healthy=True)
        result = adapter.snapshot_completed(source, vault, path, sha, expected, opt_in=True, observer=bad_observer)
        assert result["status"] == "OPTIONAL_BACKUP_UNAVAILABLE" and not result["daily_completion_changed"]
    else:
        with pytest.raises((v.Refused, KeyError)):
            adapter.snapshot_completed(source, vault, path, sha, expected, opt_in=True, observer=observer)
    assert not list(vault.glob("snapshots/*/manifest.json"))


def test_adapter_interrupted_copy_and_resume(vault_fixture):
    source, vault, expected, observer = vault_fixture
    pair = boundary_fixture(vault_fixture, qualified=True)
    def crash(*a): raise RuntimeError("interrupted")
    with pytest.raises(RuntimeError, match="interrupted"):
        adapter.snapshot_completed(source, vault, *pair, expected, opt_in=True, observer=observer, on_chunk=crash)
    assert not list(vault.glob("snapshots/*/manifest.json"))
    result = adapter.snapshot_completed(source, vault, *pair, expected, opt_in=True, observer=observer)
    assert result["status"] == "COMPLETE"


def test_adapter_original_t0_closure_and_fingerprints_never_resealed(vault_fixture):
    from prospective_t0_seal_index import publish
    source, vault, expected, observer = vault_fixture
    path, _ = boundary_fixture(vault_fixture, qualified=True)
    b = json.loads(path.read_bytes())
    t0_path = source / "t0/prospective_decision_snapshot.json"
    t0_path.parent.mkdir()
    t0_path.write_bytes(b"synthetic original T0 bytes")
    snapshot_id = "prospective_decision_snapshot:synthetic-original"
    import prospective_decision_retention as retention
    metadata = dict(contract_version=retention.CONTRACT_VERSION, decision_count=1,
                    snapshot_identity=snapshot_id, session=SESSION,
                    source_integrated_decision_artifact=dict(artifact_identity="iid:original"),
                    daily_session_operation_identity=b["source_identity"])
    ref = publish(t0_path, metadata, {}, created_at="2026-10-07T15:00:00+07:00", file_sha256=v.sha(t0_path))
    ref["path"] = Path(ref["path"]).relative_to(source).as_posix()
    handoff_path = source / "handoff.json"
    handoff = json.loads(handoff_path.read_bytes())
    handoff["prospective_decision_snapshot"] = dict(identity=snapshot_id,
        path=t0_path.relative_to(source).as_posix(), seal_index=ref)
    write(handoff_path, handoff)
    hsha = v.sha(handoff_path)
    b["completion_proof"]["handoff"]["sha256"] = hsha
    next(r for r in b["receipt_refs"] if r["relative_path"] == "handoff.json")["sha256"] = hsha
    next(r for r in b["files"] if r["relative_path"] == "handoff.json").update(sha256=hsha, size=handoff_path.stat().st_size)
    for native_path in t0_path.parent.iterdir():
        b["files"].append(dict(relative_path=native_path.relative_to(source).as_posix(),
            size=native_path.stat().st_size, sha256=v.sha(native_path), family="T0",
            state="COMPLETE", immutable=True, lock_dependent=False))
    before = {p.name: (p.read_bytes(), v.fingerprint(p)) for p in t0_path.parent.iterdir()}
    write(path, b)
    result = adapter.snapshot_completed(source, vault, path, v.sha(path), expected, opt_in=True, observer=observer)
    assert result["status"] == "COMPLETE"
    assert {p.name: (p.read_bytes(), v.fingerprint(p)) for p in t0_path.parent.iterdir()} == before
