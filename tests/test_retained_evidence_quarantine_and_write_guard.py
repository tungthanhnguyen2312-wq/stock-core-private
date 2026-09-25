"""RETAINED_EVIDENCE_INCIDENT_20260925 protections: the quarantine registry and the test-session
write guard that keeps tests out of canonical retained evidence.

Hermetic: tracked files, tmp_path and child interpreters only. Every write probe targets a
scratch directory that the test itself registers as protected; nothing here writes, or even
tries to write, under a real ``operations-review``.
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import _canonical_evidence_write_guard as guard
import retained_evidence_quarantine as quarantine

ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"

IID_0825 = "operations-review/integrated-investment-decision-product-v1-20260825/integrated_investment_decision_product_artifact.json"
IID_0904 = "operations-review/integrated-investment-decision-product-v1-20260904/integrated_investment_decision_product_artifact.json"
PRODUCTION_0904 = "integrated_investment_decision_product/v1:55173e1a18839c746037f77f2735dd5828e74fd481525515297c490483e7e68b"


def _link_directory(link: Path, target: Path) -> None:
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


# ---------------------------------------------------------------------------------------------
# Quarantine registry
# ---------------------------------------------------------------------------------------------


def test_registry_classifies_both_incident_iids_and_never_calls_them_pristine():
    registry = quarantine.load_registry()
    by_path = {entry["path"]: entry for entry in registry["quarantined"]}
    assert by_path[IID_0825]["classification"] == "CONTAMINATED_UNRECOVERABLE"
    assert by_path[IID_0904]["classification"] == "NON_PRISTINE_ORIGINAL_RECONSTRUCTABLE"
    assert by_path[IID_0904]["authoritative_production_identity"] == PRODUCTION_0904
    assert "authoritative_production_identity" not in by_path[IID_0825]
    assert {entry["classification"] for entry in registry["quarantined"]} <= set(quarantine.CLASSIFICATIONS)
    assert all(len(entry["observed_sha256"]) == 64 for entry in registry["quarantined"])
    # Every IID-folder file of both sessions is quarantined (the folders mixed generations).
    for token in ("20260825", "20260904"):
        folder = f"operations-review/integrated-investment-decision-product-v1-{token}/"
        assert sum(path.startswith(folder) for path in by_path) == 7
    assert quarantine.iid_posture_replay_excluded("2026-08-25", registry)
    assert quarantine.iid_posture_replay_excluded("2026-09-04", registry)
    assert not quarantine.iid_posture_replay_excluded("2026-09-24", registry)
    verified = {entry["path"] for entry in registry["incident_touched_content_verified"]}
    assert not verified & set(by_path)


def test_require_unquarantined_refuses_quarantined_paths_and_passes_others(tmp_path):
    for relative in (IID_0825, IID_0904):
        with pytest.raises(quarantine.QuarantinedRetainedEvidence) as caught:
            quarantine.require_unquarantined(
                tmp_path / relative, evidence_root=tmp_path, use=quarantine.USE_RETAINED_REGRESSION_BASELINE,
            )
        assert caught.value.code == "RETAINED_EVIDENCE_QUARANTINED"
        assert caught.value.relative_path == relative
    clean = tmp_path / "operations-review/integrated-investment-decision-product-v1-20260924/integrated_investment_decision_product_artifact.json"
    assert quarantine.require_unquarantined(clean, evidence_root=tmp_path, use=quarantine.USE_IID_DEPENDENT_POSTURE_REPLAY) == clean
    with pytest.raises(ValueError, match="UNKNOWN_RETAINED_EVIDENCE_USE"):
        quarantine.require_unquarantined(clean, evidence_root=tmp_path, use="ANYTHING")
    # Outside the evidence root nothing is claimed either way.
    assert quarantine.quarantine_entry(tmp_path / "elsewhere.json", evidence_root=tmp_path / "operations-review") is None


def test_a_link_cannot_launder_a_quarantined_file(tmp_path):
    evidence_root = tmp_path / "producer"
    folder = evidence_root / "operations-review" / "integrated-investment-decision-product-v1-20260825"
    folder.mkdir(parents=True)
    (folder / "integrated_investment_decision_product_artifact.json").write_text("{}", encoding="utf-8")
    link = tmp_path / "innocent-looking"
    _link_directory(link, folder)
    entry = quarantine.quarantine_entry(
        link / "integrated_investment_decision_product_artifact.json", evidence_root=evidence_root,
    )
    assert entry is not None and entry["classification"] == "CONTAMINATED_UNRECOVERABLE"


def test_declared_evidence_matching_names_the_file_or_its_folder_only():
    folder = "operations-review/integrated-investment-decision-product-v1-20260904"
    assert len(quarantine.quarantined_entries_named_by(folder)) == 7
    assert len(quarantine.quarantined_entries_named_by(IID_0825)) == 1
    assert quarantine.quarantined_entries_named_by("operations-review") == []
    assert quarantine.quarantined_entries_named_by(
        "operations-review/p3f9b-market-wide-exact-session-scaleout-20260904/p3f9b_mva_exact_session_snapshot.json"
    ) == []


@pytest.mark.parametrize("payload", ("not json", json.dumps({"contract_version": "other"}), json.dumps({
    "contract_version": quarantine.CONTRACT_VERSION, "quarantined": [], "iid_posture_replay_excluded_sessions": [],
})))
def test_a_missing_or_malformed_registry_never_reads_as_nothing_quarantined(tmp_path, payload):
    path = tmp_path / "registry.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(quarantine.QuarantineRegistryError):
        quarantine.load_registry(path)
    with pytest.raises(quarantine.QuarantineRegistryError):
        quarantine.load_registry(tmp_path / "absent.json")


def test_verify_pins_reports_unchanged_changed_and_absent_bytes_read_only(tmp_path):
    import hashlib

    evidence_root = tmp_path / "producer"
    for name, content in (("same.json", b"pinned"), ("drifted.json", b"rewritten")):
        target = evidence_root / "operations-review" / "x" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({
        "contract_version": quarantine.CONTRACT_VERSION,
        "iid_posture_replay_excluded_sessions": [],
        "quarantined": [
            {"path": f"operations-review/x/{name}", "classification": "NON_PRISTINE_CONTENT_UNVERIFIED",
             "observed_sha256": hashlib.sha256(b"pinned").hexdigest()}
            for name in ("same.json", "drifted.json", "absent.json")
        ],
    }), encoding="utf-8")
    rows = {row["path"].rsplit("/", 1)[1]: row["status"] for row in quarantine.verify_pins(evidence_root, quarantine.load_registry(registry_path))}
    assert rows == {"same.json": quarantine.PIN_MATCH, "drifted.json": quarantine.PIN_DRIFTED, "absent.json": quarantine.PIN_ABSENT}


def test_coherence_replay_excludes_the_quarantined_0825_baseline_without_reading_it(monkeypatch):
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import run_core_daily_decision_coherence_replay as replay
    finally:
        sys.path.remove(str(ROOT / "tools"))

    def refuse(path):
        raise AssertionError(f"quarantined baseline must not be loaded: {path}")

    monkeypatch.setattr(replay, "_load", refuse)
    result = replay._regression_projection_check()
    assert result["status"] == "EXCLUDED_RETAINED_EVIDENCE_QUARANTINED"
    assert result["preserves_previously_valid_tactical_states"] is None
    assert {path for path, _ in result["quarantined_baselines"]} == {
        IID_0825, IID_0825.replace("integrated_investment_decision_product_artifact", "market_structure_breakout_v3_projection_artifact"),
    }


# ---------------------------------------------------------------------------------------------
# Canonical-evidence write guard
# ---------------------------------------------------------------------------------------------


def test_guard_is_installed_and_protects_this_checkout_and_the_producer_main_checkout():
    assert guard.is_installed()
    protected = set(guard.protected_roots())
    for name in ("operations-review", "data"):
        assert os.path.normcase(os.path.realpath(ROOT / name)) in protected
    main = guard.producer_main_checkout(ROOT)
    if main is not None:  # running from a linked git worktree
        assert os.path.normcase(os.path.realpath(main / "operations-review")) in protected


def test_producer_main_checkout_is_resolved_from_a_worktree_gitdir(tmp_path):
    main = tmp_path / "main"
    gitdir = main / ".git" / "worktrees" / "wt"
    gitdir.mkdir(parents=True)
    (gitdir / "commondir").write_text("../..\n", encoding="utf-8")
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    assert guard.producer_main_checkout(worktree) == main.resolve()
    assert guard.producer_main_checkout(main) is None  # .git is a directory: not a worktree


def _mutations(protected: Path, outside: Path):
    existing = protected / "existing.json"
    return {
        "open_w": lambda: open(protected / "new.json", "w").close(),
        "open_a": lambda: open(existing, "a").close(),
        "open_rplus": lambda: open(existing, "r+").close(),
        "write_text": lambda: (protected / "new.json").write_text("x", encoding="utf-8"),
        "os_open_creat": lambda: os.close(os.open(protected / "new.json", os.O_WRONLY | os.O_CREAT)),
        "replace_into": lambda: os.replace(outside / "src.json", protected / "new.json"),
        "replace_out_of": lambda: os.replace(existing, outside / "moved.json"),
        "copyfile_into": lambda: shutil.copyfile(outside / "src.json", protected / "new.json"),
        "copy2_into": lambda: shutil.copy2(outside / "src.json", protected / "new.json"),
        "remove": lambda: os.remove(existing),
        "mkdir": lambda: (protected / "sub").mkdir(),
        "utime": lambda: os.utime(existing),
        "rmtree": lambda: shutil.rmtree(protected),
    }


@pytest.mark.parametrize("mutation", sorted(_mutations(Path("p"), Path("o"))))
def test_every_mutation_under_a_protected_root_is_refused_and_recorded(tmp_path, mutation):
    protected = tmp_path / "producer" / "operations-review"
    protected.mkdir(parents=True)
    (protected / "existing.json").write_text("retained", encoding="utf-8")
    outside = tmp_path / "scratch"
    outside.mkdir()
    (outside / "src.json").write_text("scratch", encoding="utf-8")
    before = sorted((p.relative_to(protected).as_posix(), p.read_bytes() if p.is_file() else None) for p in protected.rglob("*"))
    with guard.protect_temporarily(protected):
        with pytest.raises(guard.CanonicalEvidenceWriteRefused, match=guard.REFUSAL_CODE):
            _mutations(protected, outside)[mutation]()
        assert (protected / "existing.json").read_text(encoding="utf-8") == "retained"  # reads stay allowed
    recorded = guard.drain_violations()
    assert len(recorded) == 1 and recorded[0].startswith(guard.REFUSAL_CODE)
    after = sorted((p.relative_to(protected).as_posix(), p.read_bytes() if p.is_file() else None) for p in protected.rglob("*"))
    assert after == before


def test_write_through_a_junction_or_symlink_is_refused(tmp_path):
    protected = tmp_path / "producer" / "operations-review"
    protected.mkdir(parents=True)
    worktree_ops = tmp_path / "worktree" / "operations-review"
    worktree_ops.parent.mkdir()
    _link_directory(worktree_ops, protected)
    with guard.protect_temporarily(protected):
        with pytest.raises(guard.CanonicalEvidenceWriteRefused):
            (worktree_ops / "rebuilt.json").write_text("{}", encoding="utf-8")
        (tmp_path / "worktree" / "unrelated.json").write_text("{}", encoding="utf-8")  # scratch stays writable
    assert guard.drain_violations()
    assert list(protected.iterdir()) == []


def test_a_swallowed_refusal_is_still_recorded(tmp_path):
    protected = tmp_path / "producer" / "operations-review"
    protected.mkdir(parents=True)
    with guard.protect_temporarily(protected):
        try:  # the enrichment builder deliberately catches broad exceptions per component
            (protected / "x.json").write_text("{}", encoding="utf-8")
        except Exception:
            pass
    assert len(guard.drain_violations()) == 1


def test_a_test_that_writes_into_protected_evidence_fails_at_teardown_even_if_it_swallows_the_error(tmp_path):
    canon = tmp_path / "canon"
    (canon / "operations-review").mkdir(parents=True)
    (tmp_path / "test_child.py").write_text(textwrap.dedent(
        f"""
        from pathlib import Path

        def test_swallows():
            try:
                (Path({str(canon)!r}) / "operations-review" / "x.json").write_text("{{}}")
            except Exception:
                pass

        def test_clean(tmp_path):
            (tmp_path / "ok.json").write_text("{{}}")
        """
    ), encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if not key.startswith("STOCKLOOKUP_")}
    env.update(PYTHONPATH=str(TESTS_DIR), STOCKLOOKUP_RETAINED_EVIDENCE_ROOT=str(canon))
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "_canonical_evidence_write_guard", "-p", "no:cacheprovider",
         "-q", f"--rootdir={tmp_path}", "test_child.py"],
        cwd=tmp_path, capture_output=True, text=True, timeout=180, env=env,
    )
    assert completed.returncode == 1, completed.stdout + completed.stderr
    # test_swallows passes its call phase and then errors at teardown; test_clean passes.
    assert "2 passed, 1 error" in completed.stdout
    assert "ERROR test_child.py::test_swallows" in completed.stdout
    assert "CANONICAL_EVIDENCE_WRITE_REFUSED" in completed.stdout
    assert not (canon / "operations-review" / "x.json").exists()


def test_no_test_builds_enrichment_components_into_the_retained_root():
    """The incident writers passed the repository root as the enrichment builder's artifact
    root. Every call in tests must name scratch artifact/output roots explicitly."""
    offenders = []
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name != "build_enrichment_components":
                continue
            keywords = {kw.arg for kw in node.keywords}
            if None in keywords:  # **roots from tests/_retained_scratch.enrichment_roots
                continue
            if not {"artifact_root", "output_root"} <= keywords:
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []
