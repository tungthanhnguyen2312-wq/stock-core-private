"""Admit one additive pre-Producer session-input freeze. Never mutates the checkout.

Owner Daily and Canonical producer qualification both refuse any tracked change. A
failed Producer can still leave ``config/daily_research_session_input_registry.json``
with exactly one new ``COMPLETED_RETAINED_EVIDENCE`` row after input registration.
That row is an input lock, not a completed Daily. Publication resume requires a
``LOCAL_COMPLETE`` operation and must not be manufactured by relabeling this row.

This classifier is the only shared admission of that narrower state. It does not
commit, stage, pull, reset, or rewrite frozen identities.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess

REGISTRY_RELATIVE = "config/daily_research_session_input_registry.json"
_PENDING_STATUS_CODES = frozenset({" M", "M ", "MM"})
_SESSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SEALED_OPERATION_STATES = frozenset({"LOCAL_COMPLETE", "PUBLISHED"})

# Kept aligned with canonical_post_close_pipeline.REQUIRED_REGISTRY_KEYS and
# OPTIONAL_REGISTRY_KEYS. The test, not an import of that pipeline, enforces it.
REQUIRED_INPUT_KEYS = (
    "descriptive", "screening", "tactical", "triage",
    "fundamental", "valuation", "catalyst", "corporate_intelligence",
)
OPTIONAL_INPUT_KEYS = ("official_universe", "event_context")
_ALLOWED_INPUT_KEYS = frozenset(REQUIRED_INPUT_KEYS) | frozenset(OPTIONAL_INPUT_KEYS)


@dataclass(frozen=True)
class PendingInputFreeze:
    admitted: bool
    session: str | None
    reason_code: str


def _reject(reason: str) -> PendingInputFreeze:
    return PendingInputFreeze(False, None, reason)


def _git(root: Path, *args: str) -> tuple[int, str]:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    return result.returncode, result.stdout


def _sole_registry_modification(root: Path) -> bool:
    code, out = _git(root, "status", "--porcelain", "--untracked-files=no")
    if code:
        return False
    lines = [line for line in out.splitlines() if line]
    return bool(lines) and all(
        line[:2] in _PENDING_STATUS_CODES
        and line[3:].replace("\\", "/") == REGISTRY_RELATIVE
        for line in lines
    )


def _load_json_bytes(raw: str) -> dict | None:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _additive_session(before: object, after: object) -> str | None:
    if not isinstance(before, dict) or not isinstance(after, dict):
        return None
    added = set(after) - set(before)
    removed = set(before) - set(after)
    changed = [key for key in set(before) & set(after) if before[key] != after[key]]
    if removed or changed or len(added) != 1:
        return None
    session = next(iter(added))
    if not isinstance(session, str) or not _SESSION_RE.fullmatch(session):
        return None
    return session


def _artifact_matches(root: Path, entry: object, identity: object) -> bool:
    if not isinstance(entry, dict) or set(entry) != {"path", "artifact_identity"}:
        return False
    if not isinstance(identity, str) or not identity or entry.get("artifact_identity") != identity:
        return False
    relative = entry.get("path")
    if not isinstance(relative, str) or not relative or os.path.isabs(relative):
        return False
    parts = Path(relative).parts
    if ".." in parts or any(part.endswith(":") for part in parts):
        return False
    path = (root / relative).resolve()
    root_resolved = root.resolve()
    prefix = os.path.normcase(str(root_resolved) + os.sep)
    if not os.path.normcase(str(path)).startswith(prefix):
        return False
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("artifact_identity") == identity


def _sealed_operation(root: Path, session: str) -> str | None:
    """Return a refusal reason when this session already has a sealed Daily operation.

    A missing tree is not a seal. An unreadable record under the session directory
    fails closed. Records for other sessions are ignored.
    """
    base = root / "operations-review" / "canonical-daily-operation-v1"
    if not base.is_dir():
        return None
    for path in base.glob("*/*/daily_operation_record.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            if session in path.parts:
                return "OPERATION_RECORD_UNREADABLE"
            continue
        if not isinstance(record, dict) or record.get("session") != session:
            continue
        if record.get("daily_operation_state") in _SEALED_OPERATION_STATES:
            return "SEALED_OPERATION_PRESENT"
    return None


def classify_pending_input_freeze(root: Path) -> PendingInputFreeze:
    """Return whether ``root`` contains exactly one faithful pre-Producer input freeze.

    Admitted only when the sole tracked change is an in-place registry modification,
    JSON versus ``HEAD`` adds one session to both ledgers and changes nothing else,
    the new row is ``COMPLETED_RETAINED_EVIDENCE`` with ``trading_day_valid`` true,
    every frozen identity matches the selection and the on-disk artifact, and that
    session has no ``LOCAL_COMPLETE`` or ``PUBLISHED`` operation record.
    """
    root = Path(root)
    if not _sole_registry_modification(root):
        return _reject("NOT_SOLE_REGISTRY_DIFF")
    code, head_raw = _git(root, "show", f"HEAD:{REGISTRY_RELATIVE}")
    if code:
        return _reject("REGISTRY_UNREADABLE")
    try:
        work_raw = (root / REGISTRY_RELATIVE).read_text(encoding="utf-8")
    except OSError:
        return _reject("REGISTRY_UNREADABLE")
    head = _load_json_bytes(head_raw)
    work = _load_json_bytes(work_raw)
    if head is None or work is None or set(head) != set(work):
        return _reject("NOT_ADDITIVE")
    for key in head:
        if key in ("sessions", "completed_sessions"):
            continue
        if head[key] != work[key]:
            return _reject("NOT_ADDITIVE")
    session = _additive_session(head.get("sessions"), work.get("sessions"))
    completed_session = _additive_session(head.get("completed_sessions"), work.get("completed_sessions"))
    if session is None or session != completed_session:
        return _reject("NOT_ADDITIVE")
    row = (work.get("completed_sessions") or {}).get(session)
    selection = (work.get("sessions") or {}).get(session)
    if (not isinstance(row, dict) or not isinstance(selection, dict)
            or row.get("status") != "COMPLETED_RETAINED_EVIDENCE"
            or row.get("trading_day_valid") is not True):
        return _reject("FREEZE_ROW_INVALID")
    lock = row.get("frozen_input_identities")
    if not isinstance(lock, dict) or set(selection) != set(lock):
        return _reject("FREEZE_ROW_INVALID")
    if not set(REQUIRED_INPUT_KEYS) <= set(selection) or not set(selection) <= _ALLOWED_INPUT_KEYS:
        return _reject("FREEZE_ROW_INVALID")
    if any(not _artifact_matches(root, selection[key], lock.get(key)) for key in selection):
        return _reject("ARTIFACT_IDENTITY_MISMATCH")
    sealed = _sealed_operation(root, session)
    if sealed:
        return _reject(sealed)
    return PendingInputFreeze(True, session, "PENDING_INPUT_FREEZE")
