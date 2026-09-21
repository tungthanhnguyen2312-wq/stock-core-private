"""Safety matrix for the shared checkout-cleanliness contract.

Both the owner-facing repository preflight (``tools/run_owner_daily.py``) and the
Canonical producer release qualification (``daily_execution_environment.py``)
must agree on what "clean" means for the SAME checkout. These tests exercise the
shared contract directly, then cross-check the two real call sites against it.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import checkout_cleanliness_contract as contract
import daily_execution_environment as env
from tools import run_owner_daily as workflow


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _repo_with_origin(tmp_path: Path) -> Path:
    """A real clone tracking a bare origin, HEAD == origin/main, tracked tree clean."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-q")
    _git(seed, "config", "user.email", "test@example.com")
    _git(seed, "config", "user.name", "Test")
    (seed / "README.md").write_text("seed\n")
    (seed / "config").mkdir()
    (seed / "config" / "app.json").write_text('{"k": "v"}\n')
    _git(seed, "add", "README.md", "config/app.json")
    _git(seed, "commit", "-qm", "seed")
    _git(seed, "branch", "-M", "main")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-u", "origin", "main")
    root = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(origin), str(root)], check=True)
    _git(root, "checkout", "-q", "main")
    return root


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")


# 1. clean checkout -> PASS
def test_clean_checkout_passes(tmp_path):
    root = _repo_with_origin(tmp_path)
    result = contract.classify_checkout_cleanliness(root)
    assert result.qualified is True
    assert result.reason_code == contract.CLEAN
    assert result.tracked_dirty_paths == ()
    assert result.unsafe_untracked_paths == ()


# 2. approved untracked retained data only -> PASS
def test_approved_untracked_runtime_evidence_alone_passes(tmp_path):
    root = _repo_with_origin(tmp_path)
    _touch(root / "data" / "dnse-foreign-flow" / "observations" / "HPG.json")
    result = contract.classify_checkout_cleanliness(root)
    assert result.qualified is True
    assert result.reason_code == contract.CLEAN
    assert result.approved_untracked_paths == ("data/dnse-foreign-flow/observations/HPG.json",)
    assert result.unsafe_untracked_paths == ()


# 3. tracked modified Python -> BLOCK
def test_tracked_modified_python_blocks(tmp_path):
    root = _repo_with_origin(tmp_path)
    (root / "run.py").write_text("print(1)\n", encoding="utf-8")
    _git(root, "add", "run.py")
    _git(root, "commit", "-qm", "add run.py")
    (root / "run.py").write_text("print(2)\n", encoding="utf-8")
    result = contract.classify_checkout_cleanliness(root)
    assert result.qualified is False
    assert result.reason_code == contract.TRACKED_DIRTY
    assert any("run.py" in p for p in result.tracked_dirty_paths)


# 4. tracked modified config -> BLOCK
def test_tracked_modified_config_blocks(tmp_path):
    root = _repo_with_origin(tmp_path)
    (root / "config" / "app.json").write_text('{"k": "changed"}\n', encoding="utf-8")
    result = contract.classify_checkout_cleanliness(root)
    assert result.qualified is False
    assert result.reason_code == contract.TRACKED_DIRTY
    assert any("config/app.json" in p for p in result.tracked_dirty_paths)


# 5. untracked root Python file -> BLOCK
def test_untracked_root_python_file_blocks(tmp_path):
    root = _repo_with_origin(tmp_path)
    (root / "foo.py").write_text("print('hi')\n", encoding="utf-8")
    result = contract.classify_checkout_cleanliness(root)
    assert result.qualified is False
    assert result.reason_code == contract.UNSAFE_UNTRACKED
    assert "foo.py" in result.unsafe_untracked_paths


# 6. untracked script under tools/ -> BLOCK
def test_untracked_tools_script_blocks(tmp_path):
    root = _repo_with_origin(tmp_path)
    _touch(root / "tools" / "release_session_contract.py")
    result = contract.classify_checkout_cleanliness(root)
    assert result.qualified is False
    assert result.reason_code == contract.UNSAFE_UNTRACKED
    assert "tools/release_session_contract.py" in result.unsafe_untracked_paths


# 7. untracked config file -> BLOCK
def test_untracked_config_file_blocks(tmp_path):
    root = _repo_with_origin(tmp_path)
    _touch(root / "config" / "override.json")
    result = contract.classify_checkout_cleanliness(root)
    assert result.qualified is False
    assert result.reason_code == contract.UNSAFE_UNTRACKED
    assert "config/override.json" in result.unsafe_untracked_paths


# 8. unknown untracked directory -> BLOCK unless explicitly governed
def test_unknown_untracked_directory_blocks(tmp_path):
    root = _repo_with_origin(tmp_path)
    _touch(root / "data" / "some-new-unreviewed-store" / "file.json")
    result = contract.classify_checkout_cleanliness(root)
    assert result.qualified is False
    assert result.reason_code == contract.UNSAFE_UNTRACKED
    assert "data/some-new-unreviewed-store/file.json" in result.unsafe_untracked_paths


# 9. approved runtime evidence subtree -> PASS
def test_full_approved_evidence_subtree_passes(tmp_path):
    root = _repo_with_origin(tmp_path)
    _touch(root / "data" / "market_raw_lake" / "raw" / "DNSE" / "trades" / "run1" / "u1.parquet")
    _touch(root / "data" / "market_raw_lake" / "checkpoints" / "DNSE__trades__abc.json")
    _touch(root / "data" / "market_raw_lake" / "manifests" / "DNSE__trades__run1.json")
    result = contract.classify_checkout_cleanliness(root)
    assert result.qualified is True
    assert len(result.approved_untracked_paths) == 3
    assert result.unsafe_untracked_paths == ()


# 10. HEAD != origin/main -> BLOCK (exercised at the release-qualification layer,
# since the shared contract itself only classifies the working tree)
def test_head_diverged_from_origin_main_blocks_release_qualification(tmp_path):
    root = _repo_with_origin(tmp_path)
    (root / "local.txt").write_text("local commit\n", encoding="utf-8")
    _git(root, "add", "local.txt")
    _git(root, "commit", "-qm", "local-only commit")
    result = env.producer_release_qualification(root)
    assert result["qualified"] is False
    assert result["reason_code"] == "RELEASE_CHECKOUT_NOT_AT_ORIGIN_MAIN"
    assert result["dirty"] is False  # working tree is clean -- only the ref diverged


# 11. owner preflight and Canonical producer qualification give equivalent
#     cleanliness decisions for the same fixture
@pytest.mark.parametrize("mutate,expect_qualified", [
    (lambda root: None, True),
    (lambda root: _touch(root / "data" / "dnse-foreign-flow" / "observations" / "VNM.json"), True),
    (lambda root: (root / "README.md").write_text("dirty\n", encoding="utf-8"), False),
    (lambda root: _touch(root / "unexpected_module.py"), False),
])
def test_owner_and_canonical_agree_on_cleanliness(tmp_path, mutate, expect_qualified):
    root = _repo_with_origin(tmp_path)
    mutate(root)

    canonical = env.producer_release_qualification(root)
    cleanliness = contract.classify_checkout_cleanliness(root)

    assert cleanliness.qualified is expect_qualified
    # Canonical qualification folds in the origin/main ref check too, but on this
    # fixture HEAD == origin/main, so its verdict must track cleanliness exactly.
    assert canonical["qualified"] is expect_qualified

    if expect_qualified:
        workflow.preflight_repository(root, expected_name=root.name, expected_remote_fragment="origin")
    else:
        with pytest.raises(workflow.OwnerDailyError):
            workflow.preflight_repository(root, expected_name=root.name, expected_remote_fragment="origin")


# 12. no helper deletes/moves/ignores evidence as a side effect
def test_classification_never_mutates_the_checkout(tmp_path):
    root = _repo_with_origin(tmp_path)
    evidence = root / "data" / "dnse-foreign-flow" / "observations" / "HPG.json"
    _touch(evidence)
    unsafe = root / "stray.py"
    unsafe.write_text("x = 1\n", encoding="utf-8")
    before = evidence.read_bytes()

    contract.classify_checkout_cleanliness(root)
    env.producer_release_qualification(root)
    try:
        workflow.preflight_repository(root, expected_name=root.name, expected_remote_fragment="origin")
    except workflow.OwnerDailyError:
        pass

    assert evidence.is_file()
    assert evidence.read_bytes() == before
    assert unsafe.is_file()


def test_approved_prefixes_match_declared_store_relative_constants():
    import canonical_fact_store
    import dnse_foreign_flow_store
    import dnse_market_risk_evidence_store
    import market_raw_lake
    import raw_financial_store

    declared = {
        module.STORE_RELATIVE.as_posix() + "/"
        for module in (
            canonical_fact_store, dnse_foreign_flow_store,
            dnse_market_risk_evidence_store, market_raw_lake, raw_financial_store,
        )
    }
    assert declared == set(contract.APPROVED_RUNTIME_EVIDENCE_PREFIXES)
