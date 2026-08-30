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
