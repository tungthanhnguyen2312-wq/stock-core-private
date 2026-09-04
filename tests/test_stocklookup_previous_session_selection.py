"""DAILY_GOVERNED_PREVIOUS_SESSION_AND_DEGRADED_SOURCE_FINAL_HARDENING_V1 -- Defect A.

stocklookup.py::_previous previously selected the latest retained operation bundle strictly
before the current session by EXISTENCE alone (a run_manifest.json + matching
ai_research_session_bundle.json on disk). next_session_decision_brief.build_artifact separately
requires ANY previous_session it is given to be governed-qualified
(daily_research_session_operations.frozen_input_identities(registry, session) is not None), and
raises SESSION_NOT_GOVERNED_QUALIFIED otherwise -- so a retained-but-unqualified bundle (e.g. an
interrupted or superseded earlier attempt) selected by _previous would be rejected one layer
later, surfacing as a confusing SKIPPED status for an unrelated stale bundle instead of the
correct "no previous" fallback.
"""
from __future__ import annotations

import json
from pathlib import Path

import stocklookup


def _write_registry(root: Path, *, qualified_sessions) -> None:
    completed = {
        session: {
            "status": "COMPLETED_RETAINED_EVIDENCE",
            "frozen_input_identities": {"descriptive": f"market_wide_current_descriptive_research:{session}"},
        }
        for session in qualified_sessions
    }
    registry = {
        "schema_version": "1.0.0",
        "contract_version": "daily_research_session_input_registry/v1",
        "completed_sessions": completed,
        "sessions": {},
    }
    path = root / "config" / "daily_research_session_input_registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry), encoding="utf-8")


def _write_bundle(root: Path, session: str, *, run_id: str = "run-0001") -> Path:
    directory = root / "operations-review" / "daily-research-session-operations-v1" / session / run_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "run_manifest.json").write_text(json.dumps({"market_session": session}), encoding="utf-8")
    bundle = directory / "ai_research_session_bundle.json"
    bundle.write_text(json.dumps({"session": session}), encoding="utf-8")
    return bundle


def test_previous_skips_a_more_recent_but_unqualified_bundle_for_an_older_qualified_one(tmp_path):
    """Required regression 1: 2026-08-28 exists but is NOT governed-qualified; 2026-08-25 is
    older but IS qualified -> must select 2026-08-25, never the merely-more-recent 2026-08-28."""
    _write_registry(tmp_path, qualified_sessions=["2026-08-25"])
    _write_bundle(tmp_path, "2026-08-25")
    unqualified_bundle = _write_bundle(tmp_path, "2026-08-28")

    result = stocklookup._previous("2026-08-29", tmp_path)

    assert result is not None
    assert result != unqualified_bundle
    assert json.loads(result.read_text(encoding="utf-8"))["session"] == "2026-08-25"


def test_previous_returns_none_when_only_unqualified_bundles_exist(tmp_path):
    """Required regression 2: no governed-qualified session precedes the current one -> None,
    never a selection that would later blow up with SESSION_NOT_GOVERNED_QUALIFIED."""
    _write_registry(tmp_path, qualified_sessions=[])
    _write_bundle(tmp_path, "2026-08-28")

    assert stocklookup._previous("2026-08-29", tmp_path) is None


def test_previous_still_selects_the_latest_among_multiple_qualified_sessions(tmp_path):
    """Existing ordering behavior (latest-by-date) must survive the added qualification filter."""
    _write_registry(tmp_path, qualified_sessions=["2026-08-24", "2026-08-25"])
    _write_bundle(tmp_path, "2026-08-24")
    newest_bundle = _write_bundle(tmp_path, "2026-08-25")

    result = stocklookup._previous("2026-08-29", tmp_path)

    assert result == newest_bundle


def test_previous_never_selects_a_session_on_or_after_current(tmp_path):
    """Pre-existing invariant, unaffected by this fix: only strictly-before sessions qualify.
    Neither 2026-08-26 (equal) nor 2026-08-27 (after) is a valid "previous" for current=2026-08-26."""
    _write_registry(tmp_path, qualified_sessions=["2026-08-26", "2026-08-27"])
    _write_bundle(tmp_path, "2026-08-26")
    _write_bundle(tmp_path, "2026-08-27")

    assert stocklookup._previous("2026-08-26", tmp_path) is None
