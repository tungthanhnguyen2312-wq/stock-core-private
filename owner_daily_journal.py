"""Durable owner-operation journal for the owner Daily workflow.

A hard terminal close, console kill, or machine sleep during `stocklookup.ps1 daily` (or the
desktop one-click launcher) cannot execute any `finally`/exception-handler cleanup code -- there
is no process left to run it. This module is the durable, session-addressed record of stage
progression that survives such a kill, written synchronously by the owner workflow itself at
each stage transition and read synchronously at the START of the next ordinary invocation, so
that invocation can resume from the last durably-recorded stage instead of blindly reacquiring
or recomputing already-completed work.

See CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1.

No background worker, no polling loop, no sleep. Exactly one journal file per repository root,
holding the single most recent run (a new run supersedes, never merges with, an older one).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

CONTRACT_VERSION = "owner_daily_journal/v1"

STARTED = "STARTED"
SESSION_RESOLVED = "SESSION_RESOLVED"
LOCAL_COMPLETE = "LOCAL_COMPLETE"
PRODUCER_STATE_RETAINED = "PRODUCER_STATE_RETAINED"
PRESENTATION_BOUND = "PRESENTATION_BOUND"
DASHBOARD_PUBLISHED = "DASHBOARD_PUBLISHED"
AI_HANDOFF_PUBLISHED = "AI_HANDOFF_PUBLISHED"
ACTION_CENTER_READY = "ACTION_CENTER_READY"
COMPLETE = "COMPLETE"

FAILED = "FAILED"
INTERRUPTED = "INTERRUPTED"
BLOCKED = "BLOCKED"

#: Monotonic ordering for the advancing stages. A stage not in this tuple (the three failure-
#: metadata states above) never moves the recorded `stage` itself -- see `advance()`.
STAGE_ORDER = (
    STARTED, SESSION_RESOLVED, LOCAL_COMPLETE, PRODUCER_STATE_RETAINED, PRESENTATION_BOUND,
    DASHBOARD_PUBLISHED, AI_HANDOFF_PUBLISHED, ACTION_CENTER_READY, COMPLETE,
)
FAILURE_METADATA_STAGES = frozenset({FAILED, INTERRUPTED, BLOCKED})


class OwnerDailyJournalError(ValueError):
    """Raised only for a genuine programming misuse (advancing the wrong run, an unknown
    stage name) -- never for an unreadable/missing journal, which is always treated as
    "no usable journal yet", not an error."""


def journal_path(root: Path) -> Path:
    return Path(root) / "operations-review" / "owner-daily-journal-v1" / "journal.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_journal(root: Path) -> dict[str, Any] | None:
    """Read-only. Never raises: a missing or corrupted journal is simply "not present yet"."""
    return _load(journal_path(root))


def start_run(root: Path, *, intended_session: str | None = None) -> dict[str, Any]:
    """Begin a NEW journal entry for a fresh owner-workflow invocation.

    Always creates a fresh ``run_id`` -- an existing journal (any session, any prior outcome,
    including one still mid-flight from an interrupted run) is unconditionally superseded, never
    merged into. Call this exactly once, before any material work in the owner workflow, so an
    interrupted run always leaves at least this much durable state. The caller is expected to
    check ``resumable_state()`` BEFORE calling this, if it wants to resume rather than
    supersede an existing in-flight run.
    """
    entry = {
        "contract_version": CONTRACT_VERSION,
        "run_id": uuid.uuid4().hex,
        "started_at": _now_iso(),
        "intended_session": intended_session,
        "resolved_session": None,
        "stage": STARTED,
        "stage_history": [{"stage": STARTED, "at": _now_iso()}],
        "failure": None,
        "attestation": None,
    }
    _atomic_write(journal_path(root), entry)
    return entry


def advance(
    root: Path, run_id: str, stage: str, *,
    resolved_session: str | None = None, detail: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Monotonically advance the CURRENT run's journal to ``stage``.

    Idempotent: advancing to a stage already reached (or passed) is a no-op that returns the
    journal unchanged -- a normal-Daily rerun of an already-complete step must never regress or
    duplicate history. Refuses to advance a journal that does not belong to ``run_id`` (raises
    ``OwnerDailyJournalError``): this is what stops a stale journal from an earlier run being
    silently mistaken for the current one. ``detail`` is optional, additive, small context
    (e.g. identities) recorded alongside the stage transition.
    """
    current = read_journal(root)
    if current is None or current.get("run_id") != run_id:
        raise OwnerDailyJournalError("JOURNAL_RUN_IDENTITY_MISMATCH_OR_MISSING")
    if stage in FAILURE_METADATA_STAGES:
        current["failure"] = {"stage": stage, "at": _now_iso(), "detail": dict(detail or {})}
        _atomic_write(journal_path(root), current)
        return current
    if stage not in STAGE_ORDER:
        raise OwnerDailyJournalError(f"JOURNAL_UNKNOWN_STAGE:{stage}")
    if resolved_session is not None:
        if current.get("resolved_session") not in (None, resolved_session):
            raise OwnerDailyJournalError("JOURNAL_SESSION_IDENTITY_MISMATCH")
        current["resolved_session"] = resolved_session
    current_index = STAGE_ORDER.index(current["stage"]) if current.get("stage") in STAGE_ORDER else -1
    target_index = STAGE_ORDER.index(stage)
    if target_index <= current_index:
        if resolved_session is not None and current.get("resolved_session") != resolved_session:
            _atomic_write(journal_path(root), current)
        return current
    current["stage"] = stage
    entry = {"stage": stage, "at": _now_iso()}
    if detail:
        entry["detail"] = dict(detail)
    current["stage_history"].append(entry)
    if stage == COMPLETE and detail:
        current["attestation"] = dict(detail)
    _atomic_write(journal_path(root), current)
    return current


def resumable_state(root: Path, *, intended_session: str | None = None) -> dict[str, Any]:
    """Read-only classification of what the next ordinary owner invocation should do.

    - ``{"action": "START_FRESH"}``: no usable journal, or its resolved session (once known)
      differs from ``intended_session`` -- a different day's run is not resumable as today's.
    - ``{"action": "RESUME", "run_id", "stage", "resolved_session", "failure"}``: an interrupted
      or partially-completed run for the same (or not-yet-resolved) session exists; the caller
      should continue from ``stage`` rather than repeating already-durable work.
    - ``{"action": "ALREADY_COMPLETE", "run_id", "resolved_session"}``: that session's owner
      workflow already reached COMPLETE; the caller should treat a rerun as an idempotent
      replay, never a fresh acquisition.
    """
    journal = read_journal(root)
    if journal is None:
        return {"action": "START_FRESH"}
    resolved = journal.get("resolved_session")
    if intended_session is not None and resolved is not None and resolved != intended_session:
        return {"action": "START_FRESH"}
    stage = journal.get("stage")
    if stage == COMPLETE:
        return {"action": "ALREADY_COMPLETE", "run_id": journal.get("run_id"), "resolved_session": resolved}
    if stage not in STAGE_ORDER:
        return {"action": "START_FRESH"}
    if STAGE_ORDER.index(stage) <= STAGE_ORDER.index(STARTED) and resolved is None:
        # Never even resolved a session -- there is nothing safe to resume into.
        return {"action": "START_FRESH"}
    return {
        "action": "RESUME", "run_id": journal.get("run_id"), "stage": stage,
        "resolved_session": resolved, "failure": journal.get("failure"),
    }
