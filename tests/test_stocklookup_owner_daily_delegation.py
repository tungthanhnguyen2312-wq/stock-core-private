"""CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1 section 5 / section 10 item
H: the zero-flag `stocklookup.py daily` invocation -- exactly what `stocklookup.ps1 daily` runs
every trading day -- must delegate to the same production entrypoint
(`tools.run_owner_daily.main`) the desktop one-click launcher (`tools/run_owner_daily.ps1`)
already uses, so the two owner-facing launchers cannot retain separate production semantics.
Every diagnostic/override flag must still take the pre-existing separate path -- never a second
production Daily gated behind a flag by accident."""
from __future__ import annotations

import json

import pytest

import stocklookup


def test_zero_flag_daily_delegates_to_run_owner_daily_main(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_owner_daily_main(argv):
        calls.append(argv)
        result_path = [p for p in argv if p.endswith(".json")][0]
        from pathlib import Path
        Path(result_path).write_text(json.dumps({
            "status": "PASS", "session": "2026-09-22", "daily_status": "COMPLETED",
            "ai_handoff": {"publication": {"status": "PUBLISHED_READY_FOR_AI"}},
            "dashboard": {"status": "READY"}, "action_center": {"status": "READY"},
        }), encoding="utf-8")
        return 0

    monkeypatch.setattr("tools.run_owner_daily.main", fake_owner_daily_main)
    monkeypatch.setattr(stocklookup, "ROOT", tmp_path)
    code = stocklookup.main(["daily"])
    assert code == 0
    assert len(calls) == 1
    assert "--result-path" in calls[0]
    # Zero-flag production Daily passes no session/root override to run_owner_daily.main --
    # both launchers must resolve run_workflow()'s own identical defaults, never independently
    # computed (possibly divergent) paths.
    assert calls[0] == ["--result-path", calls[0][1]]


@pytest.mark.parametrize("flag,value", [
    ("--session", "2026-09-20"),
    ("--no-new-provider-acquisition", None),
    ("--replay-local", None),
    ("--local-only", None),
    ("--preflight", None),
])
def test_diagnostic_flags_never_delegate_to_run_owner_daily_main(monkeypatch, flag, value, tmp_path):
    def _fail(*_a, **_k):
        pytest.fail(f"{flag} must not reach the shared production owner workflow")

    monkeypatch.setattr(stocklookup, "_run_owner_daily_workflow", _fail)
    argv = ["daily", flag] + ([value] if value is not None else [])

    # preflight_canonical_daily is imported locally inside main() at call-time, so patching the
    # module attribute here is picked up correctly; forcing a clean FAILED short-circuits main()
    # right after the routing decision this test actually cares about, with no real filesystem
    # access needed.
    import daily_execution_environment
    monkeypatch.setattr(daily_execution_environment, "preflight_canonical_daily", lambda *a, **k: {"status": "FAILED"})
    monkeypatch.setattr(daily_execution_environment, "format_preflight", lambda env: "")

    code = stocklookup.main(argv)  # must not raise via the failing delegation stub above
    assert code == 2
