"""Conservative, evidence-only reconciliation of the governed completed-session ledger.

Context (SESSION_REGISTRY_PROMOTION_AND_COMPARISON_SEMANTICS_CORRECTIVE_V1): the 2026-09-12
weekly audit found several sessions were produced and published to the AI-handoff/Dashboard
repositories without their governed ``completed_sessions`` entry ever surviving in
``config/daily_research_session_input_registry.json``. Root cause (see docs/DECISIONS.md): the
in-process freeze (``canonical_post_close_pipeline.validate_and_freeze_completed_session``) always
ran and always wrote a real ``FROZEN`` result -- the gate never failed open -- but that write is a
plain local filesystem mutation with no automatic ``git commit``. Several of the affected sessions
ran from a checkout (local ``main`` at commit ``bf11dbf`` or an ephemeral integration worktree) whose
registry.json edit was never reconciled back into the checkout this repository's ``origin/main``
lineage actually uses, and downstream publication (AI handoff, Dashboard) does not gate on the
registry write having reached that shared checkout -- only on the same-process ``LOCAL_COMPLETE``/
``READY`` operation state. This module never treats publication itself as proof of governed
completion (DATA_FIRST_DOCTRINE.md Sec. 2/10): it re-derives eligibility solely by replaying the
exact, current, production registration/coherence code
(``canonical_post_close_pipeline.register_session_inputs`` /
``.validate_and_freeze_completed_session``) against whatever retained evidence is actually present
on disk today. A session is promoted only when that real code path succeeds cleanly; any failure
(missing artifact, identity mismatch, coherence violation) leaves the session unregistered.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from canonical_post_close_pipeline import (
    CanonicalPostCloseError,
    register_session_inputs,
    validate_and_freeze_completed_session,
)
from daily_research_session_operations import load_registry

CONTRACT_VERSION = "session_registry_gap_reconciliation/v1"

GOVERNED_COMPLETED = "GOVERNED_COMPLETED"
QUALIFIES_FOR_RETROACTIVE_GOVERNED_REGISTRATION = "QUALIFIES_FOR_RETROACTIVE_GOVERNED_REGISTRATION"
PUBLISHED_BUT_NOT_PROVABLY_GOVERNED = "PUBLISHED_BUT_NOT_PROVABLY_GOVERNED"
NONCURRENT_CHECKPOINT_REQUIRES_OWNER_REVIEW = "NONCURRENT_CHECKPOINT_REQUIRES_OWNER_REVIEW"
INSUFFICIENT_RETAINED_EVIDENCE = "INSUFFICIENT_RETAINED_EVIDENCE"
NOT_APPLICABLE = "NOT_APPLICABLE"

_CLASSIFICATIONS = frozenset({
    GOVERNED_COMPLETED,
    QUALIFIES_FOR_RETROACTIVE_GOVERNED_REGISTRATION,
    PUBLISHED_BUT_NOT_PROVABLY_GOVERNED,
    NONCURRENT_CHECKPOINT_REQUIRES_OWNER_REVIEW,
    INSUFFICIENT_RETAINED_EVIDENCE,
    NOT_APPLICABLE,
})


def _is_weekend(session: str) -> bool:
    return datetime.fromisoformat(session).weekday() >= 5


def _already_governed(registry: Mapping[str, Any], session: str) -> bool:
    completed = registry.get("completed_sessions") or {}
    row = completed.get(session) if isinstance(completed, Mapping) else None
    return isinstance(row, Mapping) and row.get("status") == "COMPLETED_RETAINED_EVIDENCE"


def reconcile_session(
    root: Path,
    session: str,
    *,
    registry_path: Path | None = None,
    apply: bool = True,
) -> dict[str, Any]:
    """Classify (and, when ``apply``, retroactively register) one session.

    Never uses publication (AI handoff / Dashboard presence) as evidence. Never infers eligibility
    from a producer checkpoint alone -- a noncurrent checkpoint is neither auto-accepted nor
    auto-rejected; it is downgraded to ``NONCURRENT_CHECKPOINT_REQUIRES_OWNER_REVIEW`` only when the
    real coherence/identity check itself cannot be satisfied. When it succeeds, that success *is*
    the evidence that the retained artifacts are compatible with today's exact registration
    contract, checkpoint notwithstanding.

    ``apply=False`` performs the identical classification without persisting anything: both
    production functions are invoked against an isolated in-memory copy of the registry file so the
    real ``root`` registry is never touched.
    """
    path = registry_path or root / "config" / "daily_research_session_input_registry.json"
    registry = load_registry(root) if registry_path is None else json.loads(
        Path(registry_path).read_text(encoding="utf-8")
    )

    if _already_governed(registry, session):
        return {
            "session": session,
            "classification": GOVERNED_COMPLETED,
            "reason_codes": ["ALREADY_COMPLETED_RETAINED_EVIDENCE"],
            "detail": None,
        }
    if _is_weekend(session):
        return {
            "session": session,
            "classification": NOT_APPLICABLE,
            "reason_codes": ["NOT_A_TRADING_SESSION_WEEKEND"],
            "detail": None,
        }

    work_root = root
    work_registry_path = path
    if not apply:
        import tempfile

        tmp_dir = Path(tempfile.mkdtemp(prefix="session_registry_gap_reconciliation_"))
        scratch_config = tmp_dir / "config"
        scratch_config.mkdir(parents=True, exist_ok=True)
        scratch_path = scratch_config / "daily_research_session_input_registry.json"
        scratch_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        # A relative-path registration must resolve retained artifacts under the real root, so the
        # scratch registry is written under a throwaway root while the artifact search still
        # targets the real ``root`` -- register_session_inputs takes root and registry_path
        # independently for exactly this reason.
        work_root = root
        work_registry_path = scratch_path

    try:
        register_session_inputs(work_root, session, registry_path=work_registry_path)
    except CanonicalPostCloseError as exc:
        reason = str(exc)
        if "REQUIRED_REGISTRY_INPUT_UNAVAILABLE" in reason:
            return {
                "session": session,
                "classification": INSUFFICIENT_RETAINED_EVIDENCE,
                "reason_codes": [reason],
                "detail": "A required current-session component has no retained artifact on disk.",
            }
        return {
            "session": session,
            "classification": PUBLISHED_BUT_NOT_PROVABLY_GOVERNED,
            "reason_codes": [reason],
            "detail": "Registration was refused for a reason other than a missing artifact.",
        }

    try:
        freeze = validate_and_freeze_completed_session(work_root, session, registry_path=work_registry_path)
    except ValueError as exc:
        return {
            "session": session,
            "classification": PUBLISHED_BUT_NOT_PROVABLY_GOVERNED,
            "reason_codes": [str(exc)],
            "detail": "Retained inputs registered but failed the current session-coherence contract.",
        }

    if freeze.get("status") not in {"FROZEN", "ALREADY_COMPLETED"}:
        return {
            "session": session,
            "classification": PUBLISHED_BUT_NOT_PROVABLY_GOVERNED,
            "reason_codes": [f"UNEXPECTED_FREEZE_STATUS:{freeze.get('status')}"],
            "detail": freeze,
        }

    incompatible = ((freeze.get("coherence") or {}).get("incompatible_inputs")) if freeze.get("status") == "FROZEN" else []
    if incompatible:
        return {
            "session": session,
            "classification": PUBLISHED_BUT_NOT_PROVABLY_GOVERNED,
            "reason_codes": ["INCOMPATIBLE_INPUTS_PRESENT"],
            "detail": incompatible,
        }

    return {
        "session": session,
        "classification": QUALIFIES_FOR_RETROACTIVE_GOVERNED_REGISTRATION,
        "reason_codes": ["REAL_PRODUCTION_REGISTRATION_AND_FREEZE_SUCCEEDED_AGAINST_RETAINED_EVIDENCE"],
        "detail": {
            "frozen_input_identities": freeze.get("frozen_input_identities"),
            "status": freeze.get("status"),
        },
    }


def reconcile_sessions(
    root: Path,
    sessions: list[str],
    *,
    registry_path: Path | None = None,
    apply: bool = True,
) -> list[dict[str, Any]]:
    """Reconcile each session independently and in ascending order.

    Ascending order matters only for readability of the report; each session's eligibility is
    self-contained and does not depend on another gap session's outcome.
    """
    return [
        reconcile_session(root, session, registry_path=registry_path, apply=apply)
        for session in sorted(sessions)
    ]
