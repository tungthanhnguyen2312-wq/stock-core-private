"""Dedicated, session-addressed record of post-handoff presentation-projection binding state.

``canonical_daily_operation.py``'s own persisted ``daily_operation_record.json`` deliberately
excludes ``post_handoff_*`` fields (signal velocity, flow-price divergence, the presentation
projection itself, the runtime restage outcome): their status can genuinely vary run-to-run
(a transient network hiccup, a cohort maturing later) without meaning the sealed Daily Producer
result changed -- see that module's own ``persistable`` exclusion set. That is correct for the
immutable analytical record, but it means nothing governed can answer "was a presentation
projection actually collected and lineage-verified for this exact session" without re-deriving
it. This module is that dedicated, additive answer: written once by ``canonical_daily_
operation.py`` right after it computes the post-handoff block, and read by the owner journal
(to decide whether ``PRESENTATION_BOUND`` may be recorded), the release-ready runtime
materializer (to know what to restage on a completed-session replay), and the AI handoff
publisher (to expose the same identities additively). See
CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1.

Never a decision input, never analytical authority -- presentation/research-observer state only.
Read/write here never raises: a missing or corrupted attestation is simply "not attested yet",
exactly like ``owner_daily_journal.read_journal``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

CONTRACT_VERSION = "post_handoff_presentation_attestation/v1"

BOUND = "BOUND"
LEGITIMATE_UNAVAILABLE = "LEGITIMATE_UNAVAILABLE"
UNKNOWN = "UNKNOWN"


def attestation_path(output_root: Path, session: str) -> Path:
    return Path(output_root) / "operations-review" / "post-handoff-presentation-attestation-v1" / session / "attestation.json"


def write_attestation(
    output_root: Path,
    session: str,
    *,
    presentation_projection: Mapping[str, Any],
    signal_velocity: Mapping[str, Any] | None = None,
    flow_price_divergence: Mapping[str, Any] | None = None,
    post_handoff_prospective_decision_feedback: Mapping[str, Any] | None = None,
    runtime_restage: Mapping[str, Any] | None = None,
    daily_producer_run_identity: str | None = None,
    canonical_daily_operation_identity: str | None = None,
) -> dict[str, Any]:
    """Best-effort: called by ``canonical_daily_operation.py`` only after the already-completed
    Daily Producer result and AI handoff sealing -- a write failure here (disk full, permissions)
    must never revise or block the already-sealed Daily result. The caller is expected to wrap
    this in its own non-blocking try/except, exactly like every other post-handoff observer in
    ``canonical_post_close_pipeline.py``."""
    record = {
        "contract_version": CONTRACT_VERSION,
        "session": session,
        "presentation_projection": dict(presentation_projection),
        "signal_velocity": dict(signal_velocity) if signal_velocity else None,
        "flow_price_divergence_shadow": dict(flow_price_divergence) if flow_price_divergence else None,
        "post_handoff_prospective_decision_feedback": (
            dict(post_handoff_prospective_decision_feedback) if post_handoff_prospective_decision_feedback else None
        ),
        "runtime_restage": dict(runtime_restage) if runtime_restage else None,
        "sealed_producer_workspace_artifact_identity": presentation_projection.get(
            "sealed_producer_workspace_artifact_identity"
        ),
        "daily_producer_run_identity": daily_producer_run_identity,
        "canonical_daily_operation_identity": canonical_daily_operation_identity,
    }
    path = attestation_path(output_root, session)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return record


def read_attestation(output_root: Path, session: str) -> dict[str, Any] | None:
    """Read-only. Never raises: a missing or corrupted attestation is simply "not attested yet"."""
    path = attestation_path(output_root, session)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def presentation_bound_state(attestation: Mapping[str, Any] | None) -> str:
    """Classify what the owner journal may durably conclude about presentation binding.

    ``BOUND``: the projection was collected AND lineage-verified against the sealed Producer
    Workspace (``restage_runtime_with_presentation_projection`` would actually apply it).
    ``LEGITIMATE_UNAVAILABLE``: the projection genuinely could not be produced (a declared,
    explicit ``UNAVAILABLE`` -- not silence). ``UNKNOWN``: no attestation exists at all, or its
    shape does not support either conclusion -- the caller must NOT record ``PRESENTATION_BOUND``
    on this basis; "the kernel was expected to have attempted it" is never sufficient.
    """
    if not isinstance(attestation, Mapping):
        return UNKNOWN
    projection = attestation.get("presentation_projection")
    if not isinstance(projection, Mapping):
        return UNKNOWN
    status = projection.get("status")
    if status == "COLLECTED" and projection.get("lineage_status") == "VERIFIED_AGAINST_SEALED_PRODUCER_WORKSPACE":
        return BOUND
    if status == "UNAVAILABLE":
        return LEGITIMATE_UNAVAILABLE
    return UNKNOWN
