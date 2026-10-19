"""Split code/evidence roots: session outputs are sealed under the governed retained root.

2026-10-19 (first T: Daily): the Producer sealed its run under retained evidence and the
runtime release, Dashboard companions and publisher pointer still searched the checkout only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import canonical_dashboard_runtime_release as release
import dashboard_release_publisher as publisher
import dashboard_session_companions as companions
from stocklookup_core.evidence import evidence_roots

SESSION = "2026-10-19"


@pytest.fixture
def split(tmp_path, monkeypatch):
    import runtime_paths
    producer, retained = tmp_path / "producer", tmp_path / "retained"
    producer.mkdir()
    retained.mkdir()
    monkeypatch.delenv(evidence_roots.RETAINED_EVIDENCE_ROOT_ENV, raising=False)
    monkeypatch.setenv(evidence_roots.OPERATION_OUTPUT_ROOT_ENV, str(retained))
    monkeypatch.setattr(runtime_paths, "workspace_profile", lambda **_k: None)
    return producer, retained


def _run(root: Path, run: str = "abc") -> Path:
    path = root / "operations-review/daily-producer-runs-v1" / SESSION / run / "run_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"target_market_session": SESSION, "run_identity": "daily_producer_run:" + run}), encoding="utf-8")
    return path


def test_governed_roots_order_and_dedupe(split, monkeypatch):
    producer, retained = split
    monkeypatch.setenv(evidence_roots.RETAINED_EVIDENCE_ROOT_ENV, str(retained))
    assert evidence_roots.governed_evidence_roots(producer) == [producer.resolve(), retained.resolve()]


def test_single_root_is_unchanged(tmp_path, monkeypatch):
    import runtime_paths
    monkeypatch.delenv(evidence_roots.OPERATION_OUTPUT_ROOT_ENV, raising=False)
    monkeypatch.delenv(evidence_roots.RETAINED_EVIDENCE_ROOT_ENV, raising=False)
    monkeypatch.setattr(runtime_paths, "workspace_profile", lambda **_k: None)
    assert evidence_roots.governed_evidence_roots(tmp_path) == [tmp_path.resolve()]


def test_core_resolver_does_not_consult_the_root_profile_module(tmp_path, monkeypatch):
    monkeypatch.delenv(evidence_roots.OPERATION_OUTPUT_ROOT_ENV, raising=False)
    monkeypatch.delenv(evidence_roots.RETAINED_EVIDENCE_ROOT_ENV, raising=False)
    # Layering: only the bound environment adds roots (runtime_paths.workspace_environment).
    assert "runtime_paths" not in Path(evidence_roots.__file__).read_text(encoding="utf-8").split('"""', 2)[2]
    assert evidence_roots.governed_evidence_roots(tmp_path) == [tmp_path.resolve()]


def test_runtime_release_finds_producer_run_under_retained_root(split, monkeypatch):
    producer, retained = split
    _run(retained)
    monkeypatch.setattr(release, "_load", lambda p: json.loads(Path(p).read_text(encoding="utf-8")) if Path(p).is_file() else {})
    with pytest.raises(release.CanonicalRuntimeReleaseError, match="DAILY_PRODUCER_LINEAGE_MISMATCH"):
        # Located (count=1); the empty fixture then fails the lineage check, not MISSING.
        release._producer_run(producer, SESSION, {k: (Path("x"), {"artifact_identity": k}) for k in
                                                  ("descriptive", "screening", "tactical", "triage")},
                              run_identity="daily_producer_run:abc")


def test_runtime_release_runs_in_both_roots_stay_ambiguous(split):
    producer, retained = split
    _run(retained, "abc")
    _run(producer, "def")
    with pytest.raises(release.CanonicalRuntimeReleaseError, match="count=2"):
        release._producer_run(producer, SESSION, {})


def test_lineage_path_outside_checkout_is_recorded_absolute(split):
    producer, retained = split
    inside = producer / "operations-review/a.json"
    outside = retained / "operations-review/b.json"
    assert release._root_relative_native(producer, inside) == str(Path("operations-review/a.json"))
    assert release._root_relative_native(producer, outside) == str(outside.resolve())


def test_companions_find_producer_run_under_retained_root(split):
    producer, retained = split
    _run(retained)
    path, data = companions._unique_producer_run(producer, SESSION, run_identity="daily_producer_run:abc")
    assert path.is_relative_to(retained) and data["run_identity"] == "daily_producer_run:abc"
    assert companions._rel(producer, path) == str(path.resolve())


def test_publisher_pointer_resolves_under_retained_root(split, monkeypatch):
    producer, retained = split
    monkeypatch.setattr(publisher, "PRODUCER_ROOT", producer)
    operation = retained / "operations-review/daily-research-session-operations-v1" / SESSION / "op"
    operation.mkdir(parents=True)
    runs = retained / "operations-review/daily-producer-runs-v1"
    (runs / SESSION / "abc").mkdir(parents=True)
    (runs / SESSION / "abc" / "run_manifest.json").write_text(json.dumps(
        {"daily_session_operation": {"directory": str(operation)}}), encoding="utf-8")
    (runs / "LATEST_COMPLETED_RUN.json").write_text(json.dumps(
        {"session": SESSION, "run_identity": "daily_producer_run:abc", "relative_directory": f"{SESSION}/abc"}), encoding="utf-8")
    assert publisher._current_producer_run_identity(SESSION, operation) == "daily_producer_run:abc"
    with pytest.raises(publisher.DashboardReleaseError, match="LINEAGE_MISMATCH"):
        publisher._current_producer_run_identity(SESSION, retained)


def test_publisher_single_root_relative_directory_still_matches(tmp_path, monkeypatch):
    import runtime_paths
    monkeypatch.delenv(evidence_roots.OPERATION_OUTPUT_ROOT_ENV, raising=False)
    monkeypatch.delenv(evidence_roots.RETAINED_EVIDENCE_ROOT_ENV, raising=False)
    monkeypatch.setattr(runtime_paths, "workspace_profile", lambda **_k: None)
    monkeypatch.setattr(publisher, "PRODUCER_ROOT", tmp_path)
    rel = f"operations-review/daily-research-session-operations-v1/{SESSION}/op"
    (tmp_path / rel).mkdir(parents=True)
    runs = tmp_path / "operations-review/daily-producer-runs-v1"
    (runs / SESSION / "abc").mkdir(parents=True)
    (runs / SESSION / "abc" / "run_manifest.json").write_text(json.dumps(
        {"daily_session_operation": {"directory": rel}}), encoding="utf-8")
    (runs / "LATEST_COMPLETED_RUN.json").write_text(json.dumps(
        {"session": SESSION, "run_identity": "daily_producer_run:abc", "relative_directory": f"{SESSION}/abc"}), encoding="utf-8")
    assert publisher._current_producer_run_identity(SESSION, tmp_path / rel) == "daily_producer_run:abc"
