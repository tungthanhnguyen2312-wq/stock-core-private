"""Test suite for canonical dashboard_release_publisher.py in Producer."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
import pytest

from dashboard_release_publisher import (
    DashboardReleaseError,
    publish_dashboard_release,
)


def test_publish_dashboard_release_exact_run_binding(tmp_path):
    # Setup dummy producer root & runtime root & web root
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    web_root = tmp_path / "web"
    web_root.mkdir()
    op_dir = tmp_path / "op-test-run-12345"
    op_dir.mkdir()

    session = "2026-08-28"

    # Seed runtime files
    (runtime_root / "screen_snapshot.csv").write_text(
        "ticker,exchange,date,structure,rs_rating,close\nVNM,HSX,2026-08-28,UP,85,72000\n",
        encoding="utf-8",
    )
    (runtime_root / "market_breadth.csv").write_text(
        "ticker,exchange,date\nVNM,HSX,2026-08-28\n",
        encoding="utf-8",
    )
    (runtime_root / "analysis_latest.json").write_text(
        json.dumps({"summary": {"session_date": "2026-08-28"}}),
        encoding="utf-8",
    )
    (runtime_root / "bundle_manifest.json").write_text(
        json.dumps({"freshness": {"reference_session": "2026-08-28"}}),
        encoding="utf-8",
    )

    result = publish_dashboard_release(
        session=session,
        operation_dir=op_dir,
        runtime_root=runtime_root,
        web_root=web_root,
        replay_local=True,
    )

    assert result["status"] == "DASHBOARD_RELEASE_READY"
    assert result["market_session"] == "2026-08-28"
    assert result["producer_run_identity"] == "op-test-run-12345"

    # Verify build_info was written
    build_info = json.loads((web_root / "data" / "build_info.json").read_text(encoding="utf-8"))
    assert build_info["market_session"] == "2026-08-28"
    assert build_info["producer_run_identity"] == "op-test-run-12345"
    assert build_info["release_status"] == "READY"
    assert "screen_snapshot.csv" in build_info["files"]

    # Verify screener_data.js was written
    screener_data = (web_root / "data" / "screener_data.js").read_text(encoding="utf-8")
    assert "SCREENER_DATA_META" in screener_data
    assert "2026-08-28" in screener_data


def test_publish_dashboard_release_fails_on_mixed_session(tmp_path):
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    web_root = tmp_path / "web"
    web_root.mkdir()
    op_dir = tmp_path / "op-mismatch"
    op_dir.mkdir()

    session = "2026-08-28"

    # Seed mismatched runtime files (analysis_latest.json has 2026-08-27)
    (runtime_root / "screen_snapshot.csv").write_text(
        "ticker,exchange,date\nVNM,HSX,2026-08-28\n",
        encoding="utf-8",
    )
    (runtime_root / "market_breadth.csv").write_text(
        "ticker,exchange,date\nVNM,HSX,2026-08-28\n",
        encoding="utf-8",
    )
    (runtime_root / "analysis_latest.json").write_text(
        json.dumps({"summary": {"session_date": "2026-08-27"}}),
        encoding="utf-8",
    )
    (runtime_root / "bundle_manifest.json").write_text(
        json.dumps({"freshness": {"reference_session": "2026-08-28"}}),
        encoding="utf-8",
    )

    with pytest.raises(DashboardReleaseError) as excinfo:
        publish_dashboard_release(
            session=session,
            operation_dir=op_dir,
            runtime_root=runtime_root,
            web_root=web_root,
            replay_local=True,
        )
    assert "MIXED_SESSION_DASHBOARD_RELEASE" in str(excinfo.value)


def _seed_release_inputs(runtime_root: Path, session: str) -> None:
    (runtime_root / "screen_snapshot.csv").write_text(
        f"ticker,exchange,date,structure,rs_rating,close\nVNM,HSX,{session},UP,85,72000\n", encoding="utf-8")
    (runtime_root / "market_breadth.csv").write_text(
        f"ticker,exchange,date\nVNM,HSX,{session}\n", encoding="utf-8")
    (runtime_root / "analysis_latest.json").write_text(
        json.dumps({"summary": {"session_date": session}}), encoding="utf-8")
    (runtime_root / "bundle_manifest.json").write_text(
        json.dumps({"freshness": {"reference_session": session}}), encoding="utf-8")


def _git(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def test_local_only_never_touches_the_real_web_root(tmp_path):
    """Structural guarantee, not caller discipline: local_only=True must leave a real Git
    working tree (the actual market-dashboard checkout) byte-for-byte and commit-for-commit
    unchanged, even though this function is handed that real directory as web_root."""
    runtime_root, web_root, operation = tmp_path / "runtime", tmp_path / "web", tmp_path / "operation"
    runtime_root.mkdir(); operation.mkdir()
    session = "2026-08-28"
    _seed_release_inputs(runtime_root, session)

    web_root.mkdir()
    _git(web_root, "init", "-q")
    _git(web_root, "config", "user.email", "test@example.com")
    _git(web_root, "config", "user.name", "Test")
    (web_root / "README.md").write_text("real dashboard checkout\n", encoding="utf-8")
    _git(web_root, "add", "README.md")
    _git(web_root, "commit", "-qm", "init")

    head_before = subprocess.run(["git", "-C", str(web_root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    status_before = subprocess.run(["git", "-C", str(web_root), "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True, check=True).stdout
    files_before = sorted(p.relative_to(web_root).as_posix() for p in web_root.rglob("*") if p.is_file() and ".git" not in p.parts)

    result = publish_dashboard_release(
        session=session, operation_dir=operation, runtime_root=runtime_root, web_root=web_root,
        replay_local=True, local_only=True,
    )

    assert result["status"] == "LOCAL_VALIDATED_NO_GIT_MUTATION"
    assert result["web_root"] == str(web_root)
    head_after = subprocess.run(["git", "-C", str(web_root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    status_after = subprocess.run(["git", "-C", str(web_root), "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True, check=True).stdout
    files_after = sorted(p.relative_to(web_root).as_posix() for p in web_root.rglob("*") if p.is_file() and ".git" not in p.parts)
    assert head_after == head_before
    assert status_after == status_before
    assert files_after == files_before
    assert not (web_root / "data").exists()


def test_local_only_still_validates_real_release_content(tmp_path):
    """local_only is genuine validation over a real sandbox build, not a stub: build_id/hashes
    must match what a real (non-pushing) release would compute for identical inputs, given the
    same producer_run_identity (the operation directory's own basename)."""
    root_a, root_b = tmp_path / "a", tmp_path / "b"
    runtime_a, web_a, op_a = root_a / "runtime", root_a / "web", root_a / "op-same-run-id"
    runtime_b, web_b, op_b = root_b / "runtime", root_b / "web", root_b / "op-same-run-id"
    for d in (runtime_a, web_a, op_a, runtime_b, web_b, op_b):
        d.mkdir(parents=True)
    session = "2026-08-28"
    _seed_release_inputs(runtime_a, session)
    _seed_release_inputs(runtime_b, session)

    real = publish_dashboard_release(session=session, operation_dir=op_a, runtime_root=runtime_a, web_root=web_a, replay_local=True)
    local = publish_dashboard_release(session=session, operation_dir=op_b, runtime_root=runtime_b, web_root=web_b, replay_local=True, local_only=True)

    assert real["status"] == "DASHBOARD_RELEASE_READY"
    assert local["status"] == "LOCAL_VALIDATED_NO_GIT_MUTATION"
    assert real["producer_run_identity"] == local["producer_run_identity"] == "op-same-run-id"
    assert real["dashboard_release_identity"] == local["dashboard_release_identity"]
    assert real["build_id"] == local["build_id"]


def test_local_only_wins_even_when_push_is_explicitly_true(tmp_path):
    """A caller asking for both must not get a confusing low-level git error from a directory
    that was never a real repository -- local_only silently and safely wins."""
    runtime_root, web_root, operation = tmp_path / "runtime", tmp_path / "web", tmp_path / "operation"
    runtime_root.mkdir(); web_root.mkdir(); operation.mkdir()
    session = "2026-08-28"
    _seed_release_inputs(runtime_root, session)
    result = publish_dashboard_release(
        session=session, operation_dir=operation, runtime_root=runtime_root, web_root=web_root,
        local_only=True, push=True,
    )
    assert result["status"] == "LOCAL_VALIDATED_NO_GIT_MUTATION"
    assert not (web_root / "data").exists()


def test_local_only_still_fails_closed_on_mixed_session(tmp_path):
    runtime_root, web_root, operation = tmp_path / "runtime", tmp_path / "web", tmp_path / "operation"
    runtime_root.mkdir(); web_root.mkdir(); operation.mkdir()
    _seed_release_inputs(runtime_root, "2026-08-28")
    (runtime_root / "analysis_latest.json").write_text(json.dumps({"summary": {"session_date": "2026-08-27"}}), encoding="utf-8")
    with pytest.raises(DashboardReleaseError, match="MIXED_SESSION_DASHBOARD_RELEASE"):
        publish_dashboard_release(
            session="2026-08-28", operation_dir=operation, runtime_root=runtime_root, web_root=web_root,
            replay_local=True, local_only=True,
        )


def test_stale_signal_json_and_js_are_removed_and_never_current(tmp_path):
    runtime_root, web_root, operation = tmp_path / "runtime", tmp_path / "web", tmp_path / "operation"
    runtime_root.mkdir(); web_root.mkdir(); operation.mkdir()
    session = "2026-08-28"
    _seed_release_inputs(runtime_root, session)
    for name in ("candle_signals", "sector_heatmap", "candlestick_patterns"):
        path = runtime_root / "data" / f"{name}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"scan_date": "2026-08-25", "generated_at": "2026-08-26T00:00:00Z"}), encoding="utf-8")
        stale_js = web_root / "data" / f"{name}.js"
        stale_js.parent.mkdir(exist_ok=True)
        stale_js.write_text("window.STALE = true;", encoding="utf-8")

    publish_dashboard_release(session, operation, runtime_root, web_root, replay_local=True)
    info = json.loads((web_root / "data/build_info.json").read_text(encoding="utf-8"))
    assert info["domains"]["signals"]["status"] == "STALE"
    assert info["domains"]["signals"]["components"]["candle_signals"]["source_session"] == "2026-08-25"
    for name in ("candle_signals", "sector_heatmap", "candlestick_patterns"):
        assert not (web_root / "data" / f"{name}.json").exists()
        assert not (web_root / "data" / f"{name}.js").exists()


def test_exact_signal_pairs_and_exact_cockpit_are_published(tmp_path):
    runtime_root, web_root, operation = tmp_path / "runtime", tmp_path / "web", tmp_path / "operation"
    runtime_root.mkdir(); web_root.mkdir(); operation.mkdir()
    session = "2026-08-28"
    _seed_release_inputs(runtime_root, session)
    for name in ("candle_signals", "sector_heatmap", "candlestick_patterns"):
        path = runtime_root / "data" / f"{name}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"scan_date": session, "generated_at": "2026-08-28T00:00:00Z"}), encoding="utf-8")
    (operation / "current_decision_cockpit_projection.json").write_text(
        json.dumps({"schema_version": "current_decision_cockpit_projection/v2", "session": session}), encoding="utf-8")

    publish_dashboard_release(session, operation, runtime_root, web_root, replay_local=True)
    info = json.loads((web_root / "data/build_info.json").read_text(encoding="utf-8"))
    assert info["domains"]["signals"]["status"] == "CURRENT"
    assert info["domains"]["cockpit"]["status"] == "CURRENT"
    assert json.loads((web_root / "data/current_decision_cockpit.json").read_text(encoding="utf-8"))["session"] == session
    for name in ("candle_signals", "sector_heatmap", "candlestick_patterns"):
        assert (web_root / "data" / f"{name}.json").exists()
        assert (web_root / "data" / f"{name}.js").exists()


def test_macro_domain_is_cadence_aware_at_release_session(tmp_path):
    runtime_root, web_root, operation = tmp_path / "runtime", tmp_path / "web", tmp_path / "operation"
    runtime_root.mkdir(); web_root.mkdir(); operation.mkdir()
    session = "2026-08-28"
    _seed_release_inputs(runtime_root, session)
    macro = {"schema_version": 1, "generated_at": "2026-08-19T00:00:00+07:00", "data_as_of": "2026-08-19",
             "indicators": [
                 {"key": "vix", "status": "available", "period": "2026-08-19", "freshness": {"stale_after_days": 7}},
                 {"key": "cpi", "status": "available", "period": "2026-07-01", "freshness": {"stale_after_days": 62}},
             ], "quality": {"catalog_count": 2, "available_count": 2, "missing_count": 0}}
    path = runtime_root / "data" / "macro_snapshot.json"; path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(macro), encoding="utf-8")

    publish_dashboard_release(session, operation, runtime_root, web_root, replay_local=True)
    info = json.loads((web_root / "data/build_info.json").read_text(encoding="utf-8"))
    snapshot = json.loads((web_root / "data/macro_snapshot.json").read_text(encoding="utf-8"))
    assert info["domains"]["macro"]["status"] == "PARTIAL"
    assert snapshot["indicators"][0]["freshness"]["status"] == "stale"
    assert snapshot["indicators"][1]["freshness"]["status"] == "current"


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def test_publish_dashboard_release_pushes_only_generated_files_and_is_idempotent(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "--bare", str(remote))
    web_root = tmp_path / "web"
    _git(tmp_path, "clone", str(remote), str(web_root))
    _git(web_root, "config", "user.email", "test@example.invalid")
    _git(web_root, "config", "user.name", "Stock Lookup test")
    (web_root / "dashboard.html").write_text("<!doctype html>", encoding="utf-8")
    (web_root / ".gitattributes").write_text("*.csv -text\n*.js -text\n*.json -text\n", encoding="utf-8")
    _git(web_root, "add", "--", "dashboard.html", ".gitattributes")
    _git(web_root, "commit", "-m", "initial dashboard")
    _git(web_root, "branch", "-M", "main")
    _git(web_root, "push", "-u", "origin", "main")
    monkeypatch.setenv("STOCK_LOOKUP_RELEASE_IDENTITY_TEST_FIXTURE", str(web_root))

    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    operation = tmp_path / "op-release"
    operation.mkdir()
    session = "2026-08-28"
    (runtime_root / "screen_snapshot.csv").write_text(
        "ticker,exchange,date,structure,rs_rating,close\nVNM,HSX,2026-08-28,UP,85,72000\n",
        encoding="utf-8",
    )
    (runtime_root / "market_breadth.csv").write_text("ticker,exchange,date\nVNM,HSX,2026-08-28\n", encoding="utf-8")
    (runtime_root / "analysis_latest.json").write_text(
        json.dumps({"summary": {"session_date": session}}), encoding="utf-8",
    )
    (runtime_root / "bundle_manifest.json").write_text(
        json.dumps({"freshness": {"reference_session": session}}), encoding="utf-8",
    )

    first = publish_dashboard_release(
        session=session, operation_dir=operation, runtime_root=runtime_root,
        web_root=web_root, replay_local=True, push=True,
    )
    assert first["status"] == "PUBLISHED_READY"
    assert set(first["staged"]).issubset({
        "screen_snapshot.csv", "market_breadth.csv", "analysis_latest.json", "bundle_manifest.json",
        "data/screener_data.js", "data/build_info.json", "data/build_info.js",
    })
    remote_head = _git(web_root, "ls-remote", "origin", "refs/heads/main").split()[0]
    assert remote_head == first["commit"]

    second = publish_dashboard_release(
        session=session, operation_dir=operation, runtime_root=runtime_root,
        web_root=web_root, replay_local=True, push=True,
    )
    assert second["status"] == "NO_OP_ALREADY_PUBLISHED"
    assert second["commit"] == first["commit"]
