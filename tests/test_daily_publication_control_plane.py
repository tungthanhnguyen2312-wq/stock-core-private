"""Regression coverage for the single Daily Dashboard publication control plane."""
from __future__ import annotations

from pathlib import Path

import pytest

import stocklookup
from tools import run_owner_daily as owner


SESSION = "2026-09-17"
RUN_ID = "daily_producer_run:exact"
SHA = "a" * 40


def test_normal_daily_delegates_to_the_completed_session_owner_adapter(monkeypatch, tmp_path):
    """Normal CLI and retained-session replay meet at one adapter, not two publishers."""
    seen = {}

    def _owner_adapter(root, runtime_root, session, **kwargs):
        seen.update(root=root, runtime_root=runtime_root, session=session, **kwargs)
        return {"status": "READY", "publication_state": "PUBLISHED", "expected_session": session}

    monkeypatch.setattr(owner, "publish_dashboard_release", _owner_adapter)
    result = stocklookup.complete_governed_dashboard_publication(
        session=SESSION,
        runtime_root=tmp_path / "runtime",
        web_root=tmp_path / "web",
        producer_run_identity=RUN_ID,
    )

    assert result["publication_state"] == "PUBLISHED"
    assert seen["root"] == stocklookup.ROOT
    assert seen["runtime_root"] == tmp_path / "runtime"
    assert seen["session"] == SESSION
    assert seen["producer_run_identity"] == RUN_ID
    assert seen["complete_publication"] is True


@pytest.mark.parametrize("state", ["GITHUB_SOURCE_UPDATED", None])
def test_normal_daily_never_translates_source_update_into_published(monkeypatch, tmp_path, state):
    monkeypatch.setattr(
        owner,
        "publish_dashboard_release",
        lambda *args, **kwargs: {"status": "READY", "publication_state": state},
    )
    with pytest.raises(RuntimeError, match="GOVERNED_PUBLICATION_COMPLETION_UNATTESTED"):
        stocklookup.complete_governed_dashboard_publication(
            session=SESSION,
            runtime_root=tmp_path / "runtime",
            web_root=tmp_path / "web",
            producer_run_identity=RUN_ID,
        )


def test_remote_completion_failure_retains_exact_recoverable_source_sha(monkeypatch, tmp_path):
    class _Result:
        returncode = 2
        stdout = ""
        stderr = (
            "[STATE] GITHUB_SOURCE_UPDATED: source retained\n"
            f"RECOVERABLE_RELEASE_SOURCE_SHA={SHA}\n"
            "BLOCKER=CI_FAILED\n"
        )

    monkeypatch.setattr(owner, "materialize_release_ready_runtime", lambda *args, **kwargs: {})
    monkeypatch.setattr(owner, "materialize_canonical_trusted_subset", lambda *args, **kwargs: {})
    monkeypatch.setattr(owner.subprocess, "run", lambda *args, **kwargs: _Result())

    result = owner.publish_dashboard_release(tmp_path, tmp_path / "runtime", SESSION, web_dir=tmp_path / "web")

    assert result["status"] == "FAILED"
    assert result["publication_state"] == "GITHUB_SOURCE_UPDATED"
    assert result["recoverable_release_source_sha"] == SHA
    assert "RELEASE_ORCHESTRATOR_EXIT_2" in result["reason"]


def test_legacy_publisher_is_not_a_remote_control_plane():
    source = Path(stocklookup.__file__).read_text(encoding="utf-8")
    legacy = (stocklookup.ROOT / "dashboard_release_publisher.py").read_text(encoding="utf-8")
    assert "complete_governed_dashboard_publication(" in source
    assert "LEGACY_DASHBOARD_PUBLISHER_REMOTE_DISABLED" in legacy
    assert '"git", "push"' not in legacy[legacy.index("def publish_dashboard_release("):]
