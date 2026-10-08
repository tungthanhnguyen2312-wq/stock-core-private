"""Small offline fixtures only: no production paths, acquisition, or live vault writes."""
import json
import os
from pathlib import Path
import shutil
import sqlite3

import pytest

from tools import vault_snapshot as v
from tools import vault_retention as r


@pytest.fixture
def fixture(tmp_path):
    source, vault = tmp_path / "source", tmp_path / "vault"
    source.mkdir()
    vault.mkdir()
    (source / "t0.json").write_bytes(b'{"sealed":"original"}')
    (source / "seal.json").write_bytes(b'{"seal":"native"}')
    (source / "receipt.json").write_bytes(b'{"completion":"native"}')
    expected = {"source": dict(id="C-fixture", label="fixture", healthy=True),
                "destination": dict(id="W-fixture", label="vault", healthy=True)}

    def observer(path):
        return expected["destination" if Path(path).is_relative_to(vault) else "source"].copy()

    return source, vault, expected, observer


def boundary(fixture, *, extra=(), name="boundary.json", **overrides):
    source, vault, expected, observer = fixture
    files = []
    for rel in ("t0.json", "seal.json", "receipt.json", *extra):
        p = source / rel
        files.append(dict(relative_path=rel, size=p.stat().st_size, sha256=v.sha(p), family="T0",
                          state="COMPLETE", immutable=True, lock_dependent=False))
    value = dict(schema="vault_completed_boundary/v1", status="COMPLETE", session_identity="session:1",
                 source_identity="source:retained", cutoff="2026-10-08T15:00:00+07:00", files=files,
                 receipt_refs=[dict(relative_path="receipt.json", sha256=v.sha(source / "receipt.json"))],
                 seal_refs=[dict(relative_path="seal.json", sha256=v.sha(source / "seal.json"))])
    value.update(overrides)
    path = source.parent / name
    path.write_bytes(v.canonical(value))
    return path, v.sha(path)


def run(fixture, pair=None, **kwargs):
    source, vault, expected, observer = fixture
    pair = pair or boundary(fixture)
    return v.snapshot(source, vault, *pair, expected, observer=observer, **kwargs)


def manifest(fixture, result):
    return fixture[1] / "snapshots" / result["snapshot_identity"] / "manifest.json"


def test_first_snapshot_and_idempotent_repeat(fixture):
    pair = boundary(fixture)
    first = run(fixture, pair)
    before = {str(p): p.read_bytes() for p in fixture[1].rglob("*") if p.is_file()}
    assert run(fixture, pair) == first
    assert first["copied_files"] == 3
    assert first["reused_files"] == 0
    assert {str(p): p.read_bytes() for p in fixture[1].rglob("*") if p.is_file()} == before


def test_new_file_reuses_verified_large_file_without_hash_or_copy(fixture, monkeypatch):
    source, vault, _, _ = fixture
    (source / "large.bin").write_bytes(b"a" * (2 * v.CHUNK + 19))
    first = run(fixture, boundary(fixture, extra=["large.bin"]))
    previous = manifest(fixture, first)
    (source / "new.bin").write_bytes(b"new")
    pair = boundary(fixture, extra=["large.bin", "new.bin"], name="new-boundary.json")
    original_sha = v.sha

    def limited_sha(path):
        assert Path(path).name != "large.bin", "unchanged large object was unnecessarily rehashed"
        return original_sha(path)

    monkeypatch.setattr(v, "sha", limited_sha)
    second = run(fixture, pair, previous=previous, previous_sha=first["manifest_sha256"])
    assert (second["copied_files"], second["reused_files"]) == (1, 4)
    rows = json.loads(manifest(fixture, second).read_bytes())["files"]
    assert next(x for x in rows if x["relative_path"] == "large.bin")["vault_path"].startswith(
        "snapshots/" + first["snapshot_identity"])


def test_changed_file_is_new_version_preserves_old_t0(fixture):
    source, _, _, _ = fixture
    (source / "version.bin").write_bytes(b"old")
    first = run(fixture, boundary(fixture, extra=["version.bin"]))
    original = manifest(fixture, first).read_bytes()
    t0_before = (source / "t0.json").read_bytes()
    (source / "version.bin").write_bytes(b"updated")
    second = run(fixture, boundary(fixture, extra=["version.bin"], name="updated.json"),
                 previous=manifest(fixture, first), previous_sha=first["manifest_sha256"])
    assert second["copied_files"] == 1 and second["reused_files"] == 3
    assert manifest(fixture, first).read_bytes() == original
    assert (source / "t0.json").read_bytes() == t0_before


def test_source_mutation_detected_before_completion(fixture, monkeypatch):
    real = v.fingerprint
    changed = False

    def mutate(path, stage):
        nonlocal changed
        changed = True

    def observed(path):
        fp = real(path)
        if changed and Path(path).is_relative_to(fixture[0]):
            fp["change"] += 1
        return fp

    monkeypatch.setattr(v, "fingerprint", observed)
    with pytest.raises(v.Refused, match="mutated"):
        run(fixture, on_chunk=mutate)
    assert not list(fixture[1].rglob("manifest.json"))


@pytest.mark.skipif(os.name != "nt", reason="mandatory native Windows deny-write enforcement")
def test_source_writer_is_denied_while_copying(fixture):
    def attempt(path, stage):
        with pytest.raises(PermissionError):
            path.write_bytes(b"illegal mutation")
    run(fixture, on_chunk=attempt)


def test_interruption_resume_verifies_existing_prefix(fixture):
    (fixture[0] / "large.bin").write_bytes(b"a" * (2 * v.CHUNK + 11))
    pair = boundary(fixture, extra=["large.bin"])

    def interrupt(path, stage):
        raise RuntimeError("synthetic interruption")

    with pytest.raises(RuntimeError):
        run(fixture, pair, on_chunk=interrupt)
    assert not list(fixture[1].rglob("manifest.json"))
    result = run(fixture, pair)
    assert result["status"] == "VERIFIED"
    assert result["copied_files"] == 4


def test_corrupt_resume_prefix_refused(fixture):
    pair = boundary(fixture)
    with pytest.raises(RuntimeError):
        run(fixture, pair, on_chunk=lambda *_: (_ for _ in ()).throw(RuntimeError()))
    stage = next(fixture[1].rglob("*.partial"))
    stage.write_bytes(b"corrupt")
    with pytest.raises(v.Refused, match="prefix"):
        run(fixture, pair)


def test_interrupted_final_receipt_can_be_completed_without_recopy(fixture, monkeypatch):
    pair = boundary(fixture)
    publish = v.publish

    def interrupted(path, data):
        if path.name == "receipt.json":
            raise RuntimeError("receipt publication interrupted")
        publish(path, data)

    monkeypatch.setattr(v, "publish", interrupted)
    with pytest.raises(RuntimeError):
        run(fixture, pair)
    assert len(list(fixture[1].rglob("manifest.json"))) == 1
    monkeypatch.setattr(v, "publish", publish)
    result = run(fixture, pair)
    assert result["status"] == "VERIFIED"
    assert len(list(fixture[1].rglob("manifest.json"))) == 1


@pytest.mark.parametrize("kind", ["missing", "wrong", "unhealthy", "same-volume"])
def test_destination_volume_refused(fixture, kind):
    pair = boundary(fixture)
    source, vault, expected, original = fixture
    if kind == "missing":
        vault.rmdir()
    def observer(path):
        result = original(path)
        if path == vault:
            if kind == "wrong":
                result["id"] = "another-drive"
            elif kind == "unhealthy":
                result["healthy"] = False
        return result
    if kind == "same-volume":
        expected["destination"] = expected["source"].copy()
    with pytest.raises(v.Refused):
        v.snapshot(source, vault, *pair, expected, observer=observer)
    assert not list(vault.rglob("manifest.json"))


def test_incomplete_temporary_and_accumulator_exclusion(fixture):
    source, _, _, _ = fixture
    for name in ("live.json", "scratch.tmp", "partial.json"):
        (source / name).write_bytes(b"unsealed")
    pair = boundary(fixture, extra=["live.json", "scratch.tmp", "partial.json"])
    data = json.loads(pair[0].read_bytes())
    for row in data["files"]:
        if row["relative_path"] == "live.json":
            row["family"] = "MUTABLE_ACCUMULATOR"
        if row["relative_path"] == "partial.json":
            row["state"] = "INCOMPLETE"
    pair[0].write_bytes(v.canonical(data))
    result = run(fixture, (pair[0], v.sha(pair[0])))
    assert result["copied_files"] == 3
    assert len(json.loads(manifest(fixture, result).read_bytes())["excluded"]) == 3


@pytest.mark.parametrize("field,value", [("status", "INCOMPLETE"), ("seal_refs", []), ("cutoff", None)])
def test_old_timestamp_is_not_completion(fixture, field, value):
    with pytest.raises(v.Refused, match="boundary"):
        run(fixture, boundary(fixture, **{field: value}))


def test_native_seal_hash_required(fixture):
    pair = boundary(fixture)
    (fixture[0] / "seal.json").write_bytes(b"edited seal")
    with pytest.raises(v.Refused):
        run(fixture, pair)


def test_sqlite_bytes_cannot_be_mislabelled_raw_evidence(fixture):
    path = fixture[0] / "disguised.bin"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE retained (x)")
    con.commit()
    con.close()
    with pytest.raises(v.Refused, match="separate Backup API"):
        run(fixture, boundary(fixture, extra=["disguised.bin"]))
    assert not list(fixture[1].rglob("manifest.json"))


def test_manifest_tamper_refused(fixture):
    result = run(fixture)
    path = manifest(fixture, result)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(v.Refused, match="tampered"):
        v.read_manifest(path, result["manifest_sha256"])


def test_prior_vault_mutation_refused(fixture):
    first = run(fixture)
    row = json.loads(manifest(fixture, first).read_bytes())["files"][0]
    (fixture[1] / row["vault_path"]).write_bytes(b"bad")
    (fixture[0] / "new.bin").write_bytes(b"new")
    with pytest.raises(v.Refused, match="vault object mutated"):
        run(fixture, boundary(fixture, extra=["new.bin"]), previous=manifest(fixture, first),
            previous_sha=first["manifest_sha256"])


def test_restore_verification_exact_bytes_no_operational_promotion(fixture, tmp_path):
    result = run(fixture)
    restored = tmp_path / "restore"
    restored.mkdir()
    for row in json.loads(manifest(fixture, result).read_bytes())["files"]:
        dest = restored / row["relative_path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fixture[1] / row["vault_path"], dest)
    verdict = v.restore_verify(fixture[1], manifest(fixture, result), result["manifest_sha256"],
                               restored, fixture[2]["destination"], observer=fixture[3])
    assert verdict["operational_fingerprint_compatibility"] == "NOT_GRANTED"
    (restored / "t0.json").write_bytes(b"tampered")
    with pytest.raises(v.Refused, match="differ"):
        v.restore_verify(fixture[1], manifest(fixture, result), result["manifest_sha256"],
                         restored, fixture[2]["destination"], observer=fixture[3])


@pytest.mark.skipif(os.name != "nt", reason="closed database exclusivity is Windows-only")
def test_sqlite_supported_backup_consistency_and_source_unchanged(fixture):
    source = fixture[0] / "runtime.db"
    with sqlite3.connect(source) as con:
        con.execute("CREATE TABLE retained (identity TEXT)")
        con.execute("INSERT INTO retained VALUES ('original')")
    con.close()
    before = source.read_bytes()
    result = v.sqlite_backup(source, fixture[1], "db/version1.db", fixture[2], v.sha(source), observer=fixture[3])
    assert result["backup_api"] and result["integrity_check"] == "ok"
    assert source.read_bytes() == before
    with sqlite3.connect(fixture[1] / "db/version1.db") as restored:
        assert restored.execute("SELECT * FROM retained").fetchall() == [("original",)]
    restored.close()
    with pytest.raises(v.Refused, match="already exists"):
        v.sqlite_backup(source, fixture[1], "db/version1.db", fixture[2], v.sha(source), observer=fixture[3])


@pytest.mark.skipif(os.name != "nt", reason="native Windows exclusivity")
@pytest.mark.parametrize("kind", ["sidecar", "identity", "open-writer"])
def test_sqlite_unclear_identity_or_writer_refused(fixture, kind):
    source = fixture[0] / "runtime.db"
    con = sqlite3.connect(source)
    con.execute("CREATE TABLE retained (x)")
    con.commit()
    if kind != "open-writer":
        con.close()
    if kind == "sidecar":
        Path(str(source) + "-wal").write_bytes(b"live")
    expected_sha = "0" * 64 if kind == "identity" else v.sha(source)
    try:
        with pytest.raises(v.Refused):
            v.sqlite_backup(source, fixture[1], "db/new.db", fixture[2], expected_sha, observer=fixture[3])
    finally:
        con.close()


def test_hardlink_allocation_not_double_counted(fixture):
    path = fixture[0] / "large.bin"
    path.write_bytes(b"x" * 8193)
    alias = fixture[0] / "alias.bin"
    os.link(path, alias)
    one, two = v.fingerprint(path), v.fingerprint(alias)
    allocation = r.unique_allocation([dict(volume="fake", **one), dict(volume="fake", **two)])
    assert allocation["logical_bytes"] == 16386
    assert allocation["unique_physical_bytes"] == one["physical_bytes"]
    assert allocation["file_ids"] == 1 and one["links"] == 2
    assert allocation["reclaimable_bytes"] == "UNKNOWN_WITHOUT_LINK_CLOSURE"


def proof():
    return dict(source_volume="C-GUID", physical_allocation_bytes=4096, evidence_identity="native:sha",
                verified_coverage=dict(status="VERIFIED", complete=True, manifest_sha256="m" * 64,
                                       restore_receipt_sha256="r" * 64, destination_volume="W-GUID",
                                       absolute_paths=["C:/fixture/file"]),
                runtime_refs=[], code_refs=[], manifest_refs=[], cross_session_dependencies=[],
                hardlink_consequences="exclusive single link", restore_destination="C:/fixture/file",
                restore_procedure="explicit verified native restore", invalidates_without_vault=True)


def candidate():
    return dict(rank=1, absolute_paths=["C:/fixture/file"], classification="EXACT_DUPLICATE")


def test_verified_backup_with_active_runtime_reference_never_delete_eligible():
    evidence = proof()
    evidence["runtime_refs"] = ["Daily retained lookup"]
    result = r.classify(candidate(), evidence, vault_available=True)
    assert result["category"] == "ACTIVE_REQUIRED"
    assert not result["cold_preflight_pass"] and not result["deletion_authorized"]


@pytest.mark.parametrize("category", r.CATEGORIES)
def test_retention_categories_require_proofs_and_never_authorize_deletion(category):
    evidence = proof()
    if category == "ACTIVE_REQUIRED":
        evidence["runtime_refs"] = ["runtime"]
    elif category == "HISTORICAL_DISTINCT":
        evidence["historically_distinct"] = True
    elif category == "EXACT_DUPLICATE_BUT_REFERENCED":
        evidence["manifest_refs"] = ["identity"]
    elif category == "UNVERIFIED_OR_UNKNOWN":
        evidence["physical_allocation_bytes"] = None
    elif category == "REGENERABLE_WITH_PROOF":
        evidence["regeneration_proof"] = {"recipe_identity": "recipe", "inputs_retained": True, "golden_sha": "golden"}
    result = r.classify(candidate(), evidence, vault_available=True)
    assert result["category"] == category
    assert result["execute"] is False and result["deletion_authorized"] is False


def test_missing_vault_invalidates_cold_candidate_and_never_reacquires():
    assert r.classify(candidate(), proof(), vault_available=False)["category"] == "UNVERIFIED_OR_UNKNOWN"
    assert r.archive_resolution(local_present=False, archive_registered=True, vault_available=False) == "ARCHIVE_UNAVAILABLE"
    assert r.archive_resolution(local_present=False, archive_registered=True, vault_available=True) == "EXPLICIT_RESTORE_REQUIRED"
    assert r.archive_resolution(local_present=False, archive_registered=False, vault_available=True).endswith("NO_AUTOMATIC_REACQUISITION")


def test_backup_boolean_and_unknown_dependencies_cannot_qualify_retention():
    evidence = proof()
    evidence["verified_coverage"] = True
    assert r.classify(candidate(), evidence, vault_available=True)["category"] == "UNVERIFIED_OR_UNKNOWN"
    evidence = proof()
    evidence["cross_session_dependencies"] = "UNKNOWN"
    assert r.classify(candidate(), evidence, vault_available=True)["category"] == "UNVERIFIED_OR_UNKNOWN"


def test_retention_preserves_equal_ranks_as_distinct_candidates():
    first = candidate()
    second = {**first, "absolute_paths": ["C:/fixture/other"]}
    report = r.retention_report(dict(mode="PROPOSAL_ONLY_NO_DELETION", candidates=[first, second]), {},
                                vault_available=True)
    assert len(report["candidates"]) == 2
    assert len({x["candidate_identity"] for x in report["candidates"]}) == 2


def test_capacity_preserves_25gib_guard_and_backup_not_a_solution():
    observed = dict(recent={"2026-10-07": {"bytes": 6 * r.GIB, "families": {"t0": r.GIB}}})
    result = r.capacity_model(125 * r.GIB, 3525 * r.GIB, observed,
                              dict(verified_reclaimable_bytes=0, conditional_bytes=4096, unknown_bytes="UNKNOWN"))
    assert result["whole_sessions_until_guard"] == {"observed_logical_mean": 16, "planning_8_GiB": 12, "stressed_12_GiB": 8}
    assert not result["backup_alone_solves_capacity"]
    assert result["measured_physical_growth"] == "UNKNOWN"
    assert len(result["projections"]) == 9


@pytest.mark.parametrize("relative", ["../escape", "C:/escape", "/escape", "a\\b"])
def test_traversal_rejected(fixture, relative):
    with pytest.raises(v.Refused):
        v.safe_path(fixture[0], relative)


def test_retained_77_candidate_report_does_not_claim_cold_or_deletion_authority():
    root = Path(__file__).resolve().parents[1]
    report = json.loads((root / "docs/internal/VAULT_RETENTION_PREFLIGHT_20261009.json").read_bytes())
    assert len(report["candidates"]) == 77
    assert len({x["candidate_identity"] for x in report["candidates"]}) == 77
    assert report["counts"] == dict(ACTIVE_REQUIRED=40, VERIFIED_RECOVERABLE_COLD_CANDIDATE=0,
                                    HISTORICAL_DISTINCT=7, EXACT_DUPLICATE_BUT_REFERENCED=8,
                                    UNVERIFIED_OR_UNKNOWN=22, REGENERABLE_WITH_PROOF=0)
    assert all(set(r.PROOFS) <= set(x["proof"]) and not x["execute"] and not x["deletion_authorized"]
               for x in report["candidates"])
