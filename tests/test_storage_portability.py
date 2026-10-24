"""Bounded offline fixtures; all writes stay under pytest's isolated T scratch root."""
import importlib
import copy
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import runtime_paths as runtime
import retained_evidence_catalog as catalog
import prospective_t0_seal_index as seals
import retained_evidence_catalog as storage
from tools import vault_snapshot as vault


@pytest.fixture
def volumes(tmp_path, monkeypatch):
    source, hot, cold = [tmp_path / name for name in ("original-C", "workspace-T", "archive-W")]
    for path in (source, hot, cold):
        path.mkdir()
    identities = {"C": dict(id="guid:C", label="system", healthy=True),
                  "T": dict(id="guid:T", label="Lexar", healthy=True),
                  "W": dict(id="guid:W", label="WD", healthy=True)}
    def observer(path):
        return identities["W" if Path(path).is_relative_to(cold) else
                          "T" if Path(path).is_relative_to(hot) else "C"].copy()
    monkeypatch.setattr(vault, "native_volume", observer)
    return source, hot, cold, identities, observer


def write_catalog(root, entries):
    (root / "config").mkdir(exist_ok=True)
    (root / "config/retained_evidence_cold_catalog.json").write_bytes(
        vault.canonical(dict(schema=catalog.SCHEMA, entries=entries)))


def profile_fixture(volumes, monkeypatch):
    monkeypatch.delenv(runtime.RUNTIME_ROOT_ENV, raising=False)
    source, hot, cold, ids, observer = volumes
    roles = {role: str(hot / name) for role, name in runtime.ROLE_NAMES.items()}
    for path in roles.values():
        Path(path).mkdir()
    profile = dict(schema="stocklookup_workspace/v1", parent=str(hot), roles=roles,
                   hot_volume=copy.deepcopy(ids["T"]), capacity={
                       "system": dict(path=str(source), volume=ids["C"], reserve_bytes=25*1024**3),
                       "workload": dict(path=str(hot), volume=ids["T"], reserve_bytes=140*1024**3)},
                   staging_bytes=1024, writer_bytes=2048)
    selected = hot / "profile.json"
    selected.write_bytes(vault.canonical(profile))
    monkeypatch.setenv(runtime.WORKSPACE_PROFILE_ENV, str(selected))
    return profile, selected


def test_legacy_no_archive_requirement(tmp_path, monkeypatch):
    monkeypatch.delenv(runtime.WORKSPACE_PROFILE_ENV, raising=False)
    monkeypatch.delenv(runtime.RUNTIME_ROOT_ENV, raising=False)
    assert runtime.runtime_root(tmp_path) == tmp_path
    assert runtime.workspace_path("consumer", tmp_path) == tmp_path
    assert catalog.resolve(tmp_path, "missing.json") == "NEVER_RETAINED"



def test_workspace_all_roles_release_identity_and_db(volumes, monkeypatch):
    profile, _ = profile_fixture(volumes, monkeypatch)
    qualified = runtime.workspace_profile()
    assert {str(p) for p in qualified["paths"].values()} == set(profile["roles"].values())
    assert runtime.runtime_root() == qualified["paths"]["runtime"]
    # Existing release guards still enforce main/origin/exact publisher authority.
    spec = importlib.util.spec_from_file_location("portable_release_fixture", Path(__file__).parents[1] / "release_checkout_identity.py")
    release = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release)
    try:
        # Real temporary Git repositories; no fetch/pull/push or network.
        web = qualified["paths"]["dashboard"]
        for role in ("producer", "consumer", "dashboard"):
            checkout = qualified["paths"][role]
            def git(*args):
                result = subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, text=True, check=True)
                return result.stdout.strip()
            git("init", "-b", "main")
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-m", "fixture")
            git("remote", "add", "origin", "https://github.com/tungthanhnguyen2312-wq/" + checkout.name + ".git")
            if role == "dashboard":
                release.assert_web_checkout_identity(web, branch=git("branch", "--show-current"),
                    origin_url=git("remote", "get-url", "origin"), git_toplevel=Path(git("rev-parse", "--show-toplevel")),
                    head=git("rev-parse", "HEAD"), origin_main=git("rev-parse", "HEAD"), live=True)
        release.assert_web_checkout_identity(qualified["paths"]["dashboard"], branch="main",
            origin_url="https://github.com/tungthanhnguyen2312-wq/stocklookup-dashboard.git",
            live=True, head="a", origin_main="a")
        for kwargs in ({"branch": "feature/test"}, {"origin_url": "https://other/repo"},
                       {"live": True, "head": "a", "origin_main": "b"}):
            with pytest.raises(release.ReleaseIdentityError):
                release.assert_web_checkout_identity(qualified["paths"]["dashboard"], **kwargs)
        release.assert_producer_publisher_file(qualified["paths"]["producer"] / "tools/publish_release.py",
                                              role="publish_release")
        release.assert_runtime_root_identity(qualified["paths"]["runtime"])
        monkeypatch.setenv(runtime.RUNTIME_ROOT_ENV, str(volumes[0]))
        with pytest.raises(ValueError, match="CONFLICT"):
            runtime.runtime_root()
    finally:
        monkeypatch.delenv(runtime.WORKSPACE_PROFILE_ENV)


@pytest.mark.parametrize("fault", ["wrong_guid", "missing_disk", "missing_role", "sibling_mismatch",
                                 "capacity_wrong_volume", "capacity_wrong_path"])
def test_workspace_fail_closed(volumes, monkeypatch, fault):
    profile, selected = profile_fixture(volumes, monkeypatch)
    if fault == "wrong_guid":
        profile["hot_volume"]["id"] = "wrong"
    elif fault == "missing_disk":
        profile["parent"] += "-missing"
    elif fault == "missing_role":
        del profile["roles"]["consumer"]
    elif fault == "sibling_mismatch":
        profile["roles"]["dashboard"] = str(volumes[0])
    elif fault == "capacity_wrong_volume":
        profile["capacity"]["workload"]["volume"] = volumes[3]["W"]
    else:
        profile["capacity"]["workload"]["path"] = str(volumes[2])
    selected.write_bytes(vault.canonical(profile))
    with pytest.raises(vault.Refused):
        runtime.workspace_profile()


def test_capacity_separate_guards(volumes, monkeypatch):
    profile, _ = profile_fixture(volumes, monkeypatch)
    budget = profile["capacity"]
    healthy = lambda path: SimpleNamespace(free=200*1024**3)
    result = storage.capacity_admission(budget, staging_bytes=10*1024**3, writer_bytes=20*1024**3, usage=healthy)
    assert result["workload"]["required_bytes"] == 170*1024**3
    with pytest.raises(vault.Refused, match="INSUFFICIENT_CAPACITY:workload"):
        storage.capacity_admission(budget, staging_bytes=40*1024**3, writer_bytes=30*1024**3, usage=healthy)
    with pytest.raises(vault.Refused, match="NOT_WRITABLE"):
        storage.capacity_admission(budget, staging_bytes=0, writer_bytes=0, usage=healthy, writable=lambda p: False)
    with pytest.raises(vault.Refused, match="INSUFFICIENT_CAPACITY:system"):
        storage.capacity_admission(budget, staging_bytes=0, writer_bytes=0,
            usage=lambda p: SimpleNamespace(free=(20 if p == volumes[0] else 200)*1024**3))


def t0_fixture(source):
    path = source / "operations-review/prospective-decision-retention-v1/2026-10-05/digest/prospective_decision_snapshot.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"sealed":"original T0 bytes"}')
    metadata = dict(contract_version="prospective_decision_snapshot/v1", decision_count=1,
                    session="2026-10-05", snapshot_identity="snapshot:original",
                    source_integrated_decision_artifact={"artifact_identity": "iid:original"},
                    daily_session_operation_identity="operation:original")
    reference = seals.publish(path, metadata, {}, created_at="2026-10-05T09:00:00+00:00", file_sha256=vault.sha(path))
    return path, reference


def test_portable_t0_original_copy_and_adversaries(volumes):
    source, hot, cold, ids, observer = volumes
    original, ref = t0_fixture(source)
    target = hot / original.relative_to(source)
    target.parent.mkdir(parents=True)
    shutil.copyfile(original, target)
    for name in ("prospective_t0_seal_index.json", "prospective_t0_snapshot_write_receipt.json"):
        shutil.copyfile(original.parent / name, target.parent / name)
    immutable = {p: p.read_bytes() for p in original.parent.iterdir()}
    copied_ref = {**ref, "path": str(target.parent / "prospective_t0_seal_index.json")}
    assert seals.fingerprint(target) != seals.fingerprint(original)
    with pytest.raises(ValueError, match="BINDING_INVALID"):
        seals.load_verified(copied_ref, expected_snapshot_identity="snapshot:original", session="2026-10-05")
    proof = seals.register_portable_copy(original, target, hot / "location.json", artifact_identity="snapshot:original",
        session="2026-10-05", expected_volume=ids["T"], provenance={"operation": "operation:original"}, t0_reference=ref)
    copied_ref.update(storage_location=proof, original_snapshot_path=str(original))
    bindings = seals.load_verified(copied_ref, expected_snapshot_identity="snapshot:original", session="2026-10-05")
    assert bindings.identity == "snapshot:original"
    with pytest.raises(ValueError):
        seals.load_verified(copied_ref, expected_snapshot_identity="snapshot:other", session="2026-10-05")
    with pytest.raises(vault.Refused, match="IDENTITY_MISMATCH"):
        storage.verify_location(proof, original_path=str(original), artifact_identity="false-reuse", session="2026-10-05")
    with pytest.raises(vault.Refused):
        storage.verify_location(proof, original_path=str(original), artifact_identity="snapshot:original",
                                session="2026-10-05", observer=lambda p: ids["W"])
    target.write_bytes(b"changed")
    with pytest.raises(vault.Refused):
        seals.load_verified(copied_ref, expected_snapshot_identity="snapshot:original", session="2026-10-05")
    assert all(path.read_bytes() == raw for path, raw in immutable.items())


def archive_fixture(volumes):
    source, hot, cold, ids, observer = volumes
    original, t0_ref = t0_fixture(source)
    paths = list(original.parent.iterdir())
    rel = original.relative_to(source).as_posix()
    receipt_rel = (original.parent / "prospective_t0_snapshot_write_receipt.json").relative_to(source).as_posix()
    index_rel = (original.parent / "prospective_t0_seal_index.json").relative_to(source).as_posix()
    boundary = dict(schema="vault_completed_boundary/v1", status="COMPLETE", session_identity="2026-10-05",
        source_identity="operation:original", cutoff="2026-10-05T09:00:00+00:00",
        files=[dict(relative_path=p.relative_to(source).as_posix(), size=p.stat().st_size, sha256=vault.sha(p),
                    family="T0", state="COMPLETE", immutable=True, lock_dependent=False) for p in paths],
        receipt_refs=[dict(relative_path=receipt_rel, sha256=vault.sha(source / receipt_rel))],
        seal_refs=[dict(relative_path=index_rel, sha256=vault.sha(source / index_rel))])
    boundary_path = hot / "boundary.json"
    boundary_path.write_bytes(vault.canonical(boundary))
    result = vault.snapshot(source, cold, boundary_path, vault.sha(boundary_path),
        {"source": ids["C"], "destination": ids["W"]}, observer=observer)
    manifest_rel = "snapshots/" + result["snapshot_identity"] + "/manifest.json"
    manifest = json.loads((cold / manifest_rel).read_bytes())
    row = next(row for row in manifest["files"] if row["relative_path"] == rel)
    archive_proof = seals.register_portable_copy(original, cold / row["vault_path"], hot / "archive-proof.json",
        artifact_identity="snapshot:original", session="2026-10-05", expected_volume=ids["W"],
        provenance=result, t0_reference=t0_ref)
    entry = dict(relative_path=rel, original_path=str(original), session_identity="2026-10-05",
        artifact_identity="snapshot:original", artifact_role="t0_snapshot", state="ARCHIVED_COLD",
        original_size=original.stat().st_size, sha256=vault.sha(original), source_seal_provenance="operation:original",
        restore_procedure="explicit staged restore", restore_preconditions=["pinned proof"], archive_location=archive_proof,
        vault=dict(snapshot_identity=result["snapshot_identity"], manifest_path=manifest_rel,
                   manifest_sha256=result["manifest_sha256"], object_path=row["vault_path"],
                   object_sha256=row["sha256"], volume_id=ids["W"]["id"]))
    return entry, manifest, t0_ref


def test_vault_restore_catalog_t0_continuity(volumes, monkeypatch):
    source, hot, cold, ids, observer = volumes
    entry, manifest, ref = archive_fixture(volumes)
    write_catalog(hot, [entry])
    with pytest.raises(catalog.ArchiveRestoreRequired):
        catalog.historical_paths(hot, "operations-review/prospective-decision-retention-v1", "*/*/prospective_decision_snapshot.json")
    proof = storage.restore_registered(entry, cold, hot, hot / "restored-location.json",
        expected_archive_volume=ids["W"], expected_hot_volume=ids["T"])
    target = hot / entry["relative_path"]
    # Restore the pinned index/receipt closure explicitly as independent exact entries.
    for row in manifest["files"]:
        if row["relative_path"] != entry["relative_path"]:
            shutil.copyfile(cold / row["vault_path"], hot / row["relative_path"])
    restored_ref = {**ref, "path": str(target.parent / "prospective_t0_seal_index.json"),
                    "storage_location": proof, "original_snapshot_path": entry["original_path"]}
    assert seals.load_verified(restored_ref, expected_snapshot_identity=entry["artifact_identity"],
                               session=entry["session_identity"]).identity == "snapshot:original"
    write_catalog(hot, [{**entry, "state": "PRESENT_QUALIFIED", "storage_location": proof}])
    monkeypatch.setenv("STOCK_LOOKUP_EVIDENCE_CATALOG_ROOT", str(hot))
    assert catalog.original_path(Path(entry["original_path"])) == target
    assert catalog.historical_paths(hot, "operations-review/prospective-decision-retention-v1",
        "*/*/prospective_decision_snapshot.json") == [target]
    # W is no longer needed for this explicitly qualified hot dependency.
    monkeypatch.setattr(vault, "native_volume", lambda p: ids["T"])
    assert catalog.resolve(hot, entry["relative_path"]) == "PRESENT_QUALIFIED"
    (hot / "rehearsal-measurements.json").write_bytes(vault.canonical(dict(
        native_snapshot_bytes=entry["original_size"], closure_files=len(manifest["files"]),
        closure_logical_bytes=sum(row["size"] for row in manifest["files"]),
        original_fingerprint=seals.fingerprint(Path(entry["original_path"])),
        restored_fingerprint=seals.fingerprint(target), original_identity=entry["artifact_identity"],
        portable_t0="PASS", explicit_vault_restore="PASS", production_bytes_moved=0)))


@pytest.mark.parametrize("fault", ["missing_volume", "corrupt_manifest", "corrupt_object", "wrong_session", "bad_proof", "false_original_fingerprint"])
def test_archive_errors_never_acquire_or_shorten_history(volumes, fault):
    source, hot, cold, ids, observer = volumes
    entry, manifest, ref = archive_fixture(volumes)
    if fault == "missing_volume":
        observer = lambda p: ids["C"]
    elif fault == "corrupt_manifest":
        (cold / entry["vault"]["manifest_path"]).write_bytes(b"invalid")
    elif fault == "corrupt_object":
        (cold / entry["vault"]["object_path"]).write_bytes(b"invalid")
    elif fault == "wrong_session":
        entry["session_identity"] = "2026-10-09"
    elif fault == "bad_proof":
        Path(entry["archive_location"]["path"]).write_bytes(b"invalid")
    else:
        row = next(r for r in manifest["files"] if r["relative_path"] == entry["relative_path"])
        row["source_fingerprint"]["inode"] += 1
        path = cold / entry["vault"]["manifest_path"]
        path.write_bytes(vault.canonical(manifest))
        entry["vault"]["manifest_sha256"] = vault.sha(path)
    with pytest.raises(vault.Refused):
        storage.restore_registered(entry, cold, hot, hot / "restore.json", expected_archive_volume=ids["W"],
                                    expected_hot_volume=ids["T"], observer=observer)
    assert not (hot / entry["relative_path"]).exists()
    write_catalog(hot, [entry])
    import prospective_decision_retention as retention
    with pytest.raises(catalog.ArchiveRestoreRequired):
        retention.discover_snapshots(hot)


def test_mutable_storage_candidates_refused(tmp_path):
    for name in ("active.db", "active.sqlite3", "journal-wal", "accumulators/state.json", "cache/item.json"):
        with pytest.raises(vault.Refused):
            storage.immutable_candidate(tmp_path / name)


def test_storage_only_receipt_cannot_qualify_t0(volumes):
    source, hot, cold, ids, observer = volumes
    original, ref = t0_fixture(source)
    target = hot / original.relative_to(source)
    target.parent.mkdir(parents=True)
    shutil.copyfile(original, target)
    for name in ("prospective_t0_seal_index.json", "prospective_t0_snapshot_write_receipt.json"):
        shutil.copyfile(original.parent / name, target.parent / name)
    proof = storage.register_copy(original, target, hot / "storage-only.json", artifact_identity="snapshot:original",
        session="2026-10-05", expected_volume=ids["T"], provenance={"native_content_only": True})
    copied = {**ref, "path": str(target.parent / "prospective_t0_seal_index.json"),
              "storage_location": proof, "original_snapshot_path": str(original)}
    with pytest.raises(ValueError, match="BINDING_INVALID"):
        seals.load_verified(copied, expected_snapshot_identity="snapshot:original", session="2026-10-05")


def test_frozen_source_transition_preserves_pins_and_rejects_tampering(tmp_path):
    from tools.verify_retention_reader_transition import historical_bytes, STORAGE_MANIFEST
    root = Path(__file__).resolve().parents[1]
    spec = json.loads((root / STORAGE_MANIFEST).read_bytes())
    pins = json.loads((root / "tests/fixtures/e2e3_frozen_sources.json").read_bytes())["source_sha256_lf"]
    for relative in spec["sources"]:
        assert vault.digest(historical_bytes(root, relative)) == pins[relative]
    # Copy only this tiny diagnostic closure, with a changed active source.
    relative = "runtime_paths.py"
    for path in (STORAGE_MANIFEST, "tests/fixtures/e2e3_frozen_sources.json", relative,
                 spec["sources"][relative]["archive"]):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / path, target)
    (tmp_path / relative).write_bytes(b"tampered source")
    with pytest.raises(ValueError, match="BINDING_INVALID"):
        historical_bytes(tmp_path, relative)


def register_fixture_tree(source, hot, ids, *, snapshot=None, reference=None):
    """Exact synthetic closure only; never called on an operator data root."""
    entries = []
    for number, original in enumerate(p for p in source.rglob("*") if p.is_file()):
        rel = original.relative_to(source).as_posix()
        target = hot / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        is_t0 = original == snapshot
        identity = json.loads(original.read_bytes()).get("snapshot_identity") if is_t0 else "fixture:" + vault.sha(original)
        register = seals.register_portable_copy if is_t0 else storage.register_copy
        t0_kwargs = {"t0_reference": reference} if is_t0 else {}
        proof = register(original, target, hot / ("proof-" + str(number) + ".json"),
            artifact_identity=identity, session="2026-10-05", expected_volume=ids["T"],
            provenance={"fixture": "immutable exact synthetic closure"}, **t0_kwargs)
        entries.append(dict(relative_path=rel, original_path=str(original), session_identity="2026-10-05",
            artifact_identity=identity, artifact_role="t0_snapshot" if is_t0 else "fixture_dependency",
            state="PRESENT_QUALIFIED", original_size=original.stat().st_size, sha256=vault.sha(original),
            source_seal_provenance="fixture:original", storage_location=proof))
    write_catalog(hot, entries)
    return entries


def test_real_snapshot_origination_and_cohort_survive_copy(volumes, monkeypatch):
    from test_prospective_t0_reuse_lineage import reuse, inventory
    import prospective_decision_retention as retention
    source, hot, cold, ids, observer = volumes
    case = reuse.__wrapped__(source)
    before = inventory(case)
    ref = case["handoff"]["prospective_decision_snapshot"]["seal_index"]
    register_fixture_tree(source, hot, ids, snapshot=case["path"], reference=ref)
    monkeypatch.setenv("STOCK_LOOKUP_EVIDENCE_CATALOG_ROOT", str(hot))
    after = retention.discover_snapshots(hot)
    assert [r["snapshot_identity"] for r in before["inventory"]] == [r["snapshot_identity"] for r in after["inventory"]]
    assert [r["classification"] for r in after["inventory"]] == [retention.GENUINE]
    assert before["genuine_snapshots"][0]["snapshot"] == after["genuine_snapshots"][0]["snapshot"]
    assert seals.load_verified(ref, expected_snapshot_identity=case["snapshot"]["snapshot_identity"],
                               session="2026-10-05").identity == case["snapshot"]["snapshot_identity"]


def test_capture_depth_and_maturity_survive_copy(volumes, monkeypatch):
    from test_prospective_pit_capture import capture_session
    import prospective_pit_capture_retention as capture
    source, hot, cold, ids, observer = volumes
    capture_session(source)
    cutoff = "2026-10-06T12:00:00Z"
    before = capture.load_chain(source, as_of=cutoff)
    register_fixture_tree(source, hot, ids)
    monkeypatch.setenv("STOCK_LOOKUP_EVIDENCE_CATALOG_ROOT", str(hot))
    after = capture.load_chain(hot, as_of=cutoff)
    assert before.sessions == after.sessions == ["2026-10-05"]
    assert before.records == after.records
    for horizon in (5, 10, 20):
        assert before.next_n_sessions("2026-10-05", horizon) == after.next_n_sessions("2026-10-05", horizon)
    value = next(iter(after.records.values()))
    assert capture.verify_complete_session(hot, value) == value


def test_feedback_missing_archived_iid_blocks_before_discovery(volumes):
    import prospective_decision_outcome_feedback as feedback
    source, hot, cold, ids, observer = volumes
    entry, manifest, ref = archive_fixture(volumes)
    rel = "operations-review/canonical-post-close-v1/2026-10-05/enrichment/integrated_investment_decision_product.json"
    write_catalog(hot, [{**entry, "relative_path": rel, "artifact_role": "iid"}])
    with pytest.raises(catalog.ArchiveRestoreRequired):
        feedback._artifact_paths(hot)


def test_actual_consumer_dashboard_reads_and_protected_write_guard(volumes, monkeypatch):
    """Read-only source imports; temporary siblings and DB stay in the T fixture."""
    profile, _ = profile_fixture(volumes, monkeypatch)
    paths = runtime.workspace_profile()["paths"]
    bindings = runtime.workspace_environment()
    from daily_execution_environment import resolve_roots
    for key, value in bindings.items():
        monkeypatch.setenv(key, value)
    roots = resolve_roots(paths["producer"])
    assert roots.retained_evidence_root == paths["retained"]
    assert roots.output_root == paths["retained"]
    db = paths["runtime"] / "vn_stock.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE fixture (value TEXT)")
        connection.execute("INSERT INTO fixture VALUES ('retained fixture')")
    # These exact source files are inspected, never written or copied as whole repos.
    workspace = Path("C:/Projects/StockLookup")
    consumer = workspace / "ai-core-private/builders/build_ticker_context.py"
    dashboard = workspace / "market-dashboard/publish_dashboard.py"
    if not consumer.is_file() or not dashboard.is_file():
        pytest.skip("host-local Consumer/Dashboard source fixtures absent")
    code = r'''
import importlib.util, json, os, pathlib, sys
workspace, hot = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
denied = []
def guard(event, args):
    if event in {"socket.connect", "socket.getaddrinfo"}:
        raise RuntimeError("offline rehearsal forbids network")
    if event == "open":
        path, mode, flags = args
        writing = isinstance(mode, str) and any(c in mode for c in "wax+")
        writing = writing or isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
        if writing and isinstance(path, (str, bytes)) and pathlib.Path(path).resolve().is_relative_to(workspace):
            denied.append(str(path)); raise PermissionError("PROTECTED_C_WRITE_DENIED")
    if event in {"os.remove", "os.rename", "os.mkdir", "os.rmdir", "os.link", "os.symlink"}:
        if any(isinstance(p, str) and pathlib.Path(p).resolve().is_relative_to(workspace) for p in args[:2]):
            denied.append(event); raise PermissionError("PROTECTED_C_WRITE_DENIED")
sys.addaudithook(guard)
sys.path[:0] = [str(workspace / "ai-core-private"), str(workspace / "ai-core-private/builders"),
                str(workspace / "market-dashboard")]
def load(name, original, target):
    module = type(sys)(name)
    module.__file__ = str(target)
    sys.modules[name] = module
    exec(compile(original.read_bytes(), str(target), "exec"), module.__dict__)
    return module
consumer = load("portable_consumer_read", workspace / "ai-core-private/builders/build_ticker_context.py",
                hot / "ai-core-private/builders/build_ticker_context.py")
assert consumer.resolve_dashboard_runtime_root() == hot / "dashboard-runtime"
with consumer._connect_read_only(hot / "dashboard-runtime/vn_stock.db") as connection:
    assert connection.execute("SELECT value FROM fixture").fetchone()[0] == "retained fixture"
dashboard = load("portable_dashboard_read", workspace / "market-dashboard/publish_dashboard.py",
                 hot / "market-dashboard/publish_dashboard.py")
assert dashboard.get_default_backend_root() == hot / "dashboard-runtime"
try:
    (workspace / "stock-core-private/.storage-portability-forbidden-write").write_text("must be denied")
except PermissionError:
    pass
else:
    raise AssertionError("write guard did not deny protected path")
print(json.dumps(dict(consumer_read="PASS", dashboard_read="PASS", protected_writes=0, denied_write_attempts=len(denied))))
'''
    result = subprocess.run([sys.executable, "-B", "-c", code, str(workspace), str(volumes[1])],
                            capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1])["protected_writes"] == 0


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows PowerShell profile routing")
def test_native_powershell_profile_router(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    parent = tmp_path / "workspace"
    roles = {role: str(parent / name) for role, name in runtime.ROLE_NAMES.items()}
    for path in roles.values():
        Path(path).mkdir(parents=True)
    profile = tmp_path / "profile.json"
    profile.write_bytes(vault.canonical(dict(schema="stocklookup_workspace/v1", parent=str(parent),
        roles=roles, hot_volume=vault.native_volume(parent))))
    tools = Path(roles["producer"]) / "tools"
    tools.mkdir()
    for name in ("run_owner_daily.ps1", "owner_daily_presentation.ps1"):
        shutil.copyfile(root / "tools" / name, tools / name)
    dummy = tmp_path / "dummy.py"
    dummy.write_text('''import argparse,json,pathlib
p=argparse.ArgumentParser()
p.add_argument('--runtime-root');p.add_argument('--result-path');p.add_argument('--progress-path')
a=p.parse_args()
pathlib.Path(a.result_path).write_text(json.dumps(dict(status='PASS',session='2026-10-05',
    telemetry=dict(elapsed_seconds=0),action_center=dict(view_open=dict(status='READY')),
    observed_runtime=a.runtime_root)))
''', encoding="utf-8")
    monkeypatch.setenv(runtime.WORKSPACE_PROFILE_ENV, str(profile))
    monkeypatch.setenv("STOCK_LOOKUP_PYTHON", sys.executable)
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", str(tools / "run_owner_daily.ps1"), "-EntryScript", str(dummy), "-NoPause"],
        cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    results = list(Path(roles["logs"]).glob("*.result.json"))
    assert len(results) == 1
    assert Path(json.loads(results[0].read_bytes())["observed_runtime"]) == Path(roles["runtime"])


def test_draft_provider_worker_bundle_pins_portable_runtime_paths_without_profile_closure(tmp_path):
    """The worker bundle carries runtime_paths.py alone; its profile branch must stay unreachable there."""
    import os
    import provider_build_manifest as build_manifest
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "config" / "provider_build_manifest.json").read_text(encoding="utf-8"))
    bound = {item["relative_path"]: item for item in manifest["worker"]["source_files"]}
    assert bound["runtime_paths.py"] == build_manifest.file_identity(root / "runtime_paths.py", "runtime_paths.py")
    assert "retained_evidence_catalog.py" not in bound
    assert manifest["status"] == build_manifest.STATUS_DRAFT and manifest["launch_authorized"] is False
    assert runtime.WORKSPACE_PROFILE_ENV not in manifest["environment"]["allowed_names"]
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    shutil.copyfile(root / "runtime_paths.py", bundle / "runtime_paths.py")
    environment = {k: v for k, v in os.environ.items()
                   if k not in {runtime.WORKSPACE_PROFILE_ENV, runtime.RUNTIME_ROOT_ENV}}
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import runtime_paths as r; "
            "assert r.workspace_environment() == {}; r.runtime_root(sys.argv[1]); "
            "assert 'retained_evidence_catalog' not in sys.modules")
    result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code, str(bundle)], cwd=bundle,
                            env=environment, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
