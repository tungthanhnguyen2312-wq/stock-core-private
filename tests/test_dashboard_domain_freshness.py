"""Focused optional-domain tests for the canonical daily release path."""
from __future__ import annotations

import subprocess

import canonical_daily_operation as operation


def test_macro_refresh_success_is_explicit(monkeypatch, tmp_path):
    monkeypatch.setattr(operation.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "ok", ""))
    result = operation.refresh_macro_snapshot(tmp_path, tmp_path / "runtime")
    assert result == {"status": "REFRESHED", "reason_code": None}


def test_macro_refresh_external_failure_is_nonfatal_and_truthful(monkeypatch, tmp_path):
    monkeypatch.setattr(operation.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "network unavailable"))
    result = operation.refresh_macro_snapshot(tmp_path, tmp_path / "runtime")
    assert result["status"] == "FAILED"
    assert result["reason_code"] == "MACRO_SYNC_EXTERNAL_OR_PIPELINE_FAILURE"


def test_macro_refresh_passes_a_total_subprocess_deadline(monkeypatch, tmp_path):
    captured = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(args[0], 0, "ok", "")

    monkeypatch.setattr(operation.subprocess, "run", fake_run)
    operation.refresh_macro_snapshot(tmp_path, tmp_path / "runtime")
    assert captured.get("timeout") == operation.MACRO_SYNC_SUBPROCESS_TIMEOUT_SECONDS


def test_macro_refresh_subprocess_timeout_is_nonfatal_and_truthful(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout"))

    monkeypatch.setattr(operation.subprocess, "run", fake_run)
    result = operation.refresh_macro_snapshot(tmp_path, tmp_path / "runtime")
    assert result["status"] == "FAILED"
    assert result["reason_code"] == "MACRO_SYNC_SUBPROCESS_TIMEOUT"
    assert result["timeout_seconds"] == operation.MACRO_SYNC_SUBPROCESS_TIMEOUT_SECONDS
