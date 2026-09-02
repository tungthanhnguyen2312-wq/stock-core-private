"""Focused unit tests for stocklookup.py's best-effort daily_integrated_decision_brief wiring
(Section 15: automatic, no extra owner flags, never gates publication, never silently reuses a
stale prior-session artifact)."""
from __future__ import annotations

import json

import stocklookup


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_skips_cleanly_when_no_decision_brief_path(tmp_path, capsys):
    result = stocklookup._daily_integrated_decision_brief("2026-08-28", tmp_path, None)
    assert result is None
    assert "DAILY_INTEGRATED_DECISION_BRIEF_SKIPPED" in capsys.readouterr().out


def test_never_raises_and_reports_status_on_unexpected_failure(tmp_path, capsys, monkeypatch):
    decision_brief_path = tmp_path / "next_session_decision_brief.json"
    _write(decision_brief_path, {"current_session": "2026-08-28"})

    def boom(**kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr("daily_integrated_decision_brief.build_from_session", boom)
    result = stocklookup._daily_integrated_decision_brief("2026-08-28", tmp_path, decision_brief_path)
    assert result is None
    assert "DAILY_INTEGRATED_DECISION_BRIEF_SKIPPED" in capsys.readouterr().out


def test_skips_when_integrated_decision_product_not_yet_materialized(tmp_path, capsys, monkeypatch):
    """Section 15: if the current integrated decision artifact is missing, do not silently fall
    back to a stale prior-session product -- fail explicit/soft, never substitute."""
    decision_brief_path = tmp_path / "next_session_decision_brief.json"
    _write(decision_brief_path, {"current_session": "2026-08-28"})
    monkeypatch.setattr("daily_integrated_decision_brief.build_from_session", lambda **kwargs: None)
    result = stocklookup._daily_integrated_decision_brief("2026-08-28", tmp_path, decision_brief_path)
    assert result is None
    assert "INTEGRATED_INVESTMENT_DECISION_PRODUCT_NOT_MATERIALIZED" in capsys.readouterr().out


def test_writes_the_brief_when_build_succeeds(tmp_path, monkeypatch):
    decision_brief_path = tmp_path / "next_session_decision_brief.json"
    _write(decision_brief_path, {"current_session": "2026-08-28"})
    fake_brief = {"contract_version": "daily_integrated_decision_brief/v1", "session": "2026-08-28"}
    captured = {}

    def fake_build(**kwargs):
        captured.update(kwargs)
        return fake_brief

    monkeypatch.setattr("daily_integrated_decision_brief.build_from_session", fake_build)
    result = stocklookup._daily_integrated_decision_brief("2026-08-28", tmp_path, decision_brief_path)
    assert result == tmp_path / "daily_integrated_decision_brief.json"
    assert json.loads(result.read_text(encoding="utf-8")) == fake_brief
    assert captured["session"] == "2026-08-28"
    assert captured["next_session_brief"] == {"current_session": "2026-08-28"}


def test_content_conflict_is_refused_not_silently_overwritten(tmp_path, monkeypatch, capsys):
    decision_brief_path = tmp_path / "next_session_decision_brief.json"
    _write(decision_brief_path, {"current_session": "2026-08-28"})
    existing = tmp_path / "daily_integrated_decision_brief.json"
    existing.write_text('{"different":"payload"}\n', encoding="utf-8")
    monkeypatch.setattr("daily_integrated_decision_brief.build_from_session", lambda **kwargs: {"session": "2026-08-28"})
    result = stocklookup._daily_integrated_decision_brief("2026-08-28", tmp_path, decision_brief_path)
    assert result is None
    assert "CONTENT_CONFLICT_SKIPPED" in capsys.readouterr().out
    assert existing.read_text(encoding="utf-8") == '{"different":"payload"}\n'
