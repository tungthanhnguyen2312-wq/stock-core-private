"""Canonical daily one-command operation: post-close eligibility through publication.

Operational composition over existing modules. Not a second orchestrator and not a
second market-acquisition owner.

CHAIN
    resolve intended session
    -> Phase A attempt eligibility (ATTEMPT_ELIGIBLE)
    -> exactly one governed market-wide acquisition (canonical P3F9B / existing
       canonical_post_close_pipeline.acquire_and_materialize)
    -> Phase B exact-session completion (EXACT_SESSION_OBSERVED_AFTER_SAFETY_FLOOR)
    -> existing current-research / Level-2 materialization (owned by acquire_and_materialize)
    -> exact input registration (only after Phase B)
    -> Canonical Daily Producer
    -> decision packet
    -> prospective cohort collection
    -> canonical Dashboard runtime materialization
    -> canonical trusted-subset materialization
    -> optional tools/release_orchestrator.py all --live --expected-session --complete-publication
    -> one terminal daily-operation attestation

Acquisition owner decision (from actual contracts, not assumption):
    tools/collect_market_evidence.py emits capability_first_eod_collector/v1 packets
    (default STANDARD_COHORT, max_requests=50). That packet cannot satisfy
    canonical_post_close_pipeline.assert_post_close_eligible, which requires
    p3f9_exact_session_mva_snapshot/v2 + FULL_CANONICAL_CANDIDATE_SET. Daily Producer,
    runtime release, and trusted subset all consume that canonical snapshot.
    Therefore the canonical P3F9B route is the single market-wide acquisition owner
    for this command. Capability-first EOD remains an independent lower-level
    capability and is never invoked here.

Authority effect remains NONE. No OS scheduler, poll, sleep, or background loop.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from canonical_dashboard_runtime_release import (
    CanonicalRuntimeReleaseError,
    materialize_canonical_runtime_release,
)
from canonical_post_close_pipeline import (
    CanonicalPostCloseError,
    PreCutoffArtifactError,
    acquire_and_materialize,
    assert_post_close_eligible,
    build_decision_packet,
    build_enrichment_components,
    build_tiered_bundle,
    evaluate_dashboard_runtime_readiness,
    register_session_inputs,
    run_prospective_collection,
    validate_and_freeze_completed_session,
)
from canonical_trusted_subset_release import (
    CanonicalTrustedSubsetError,
    materialize_canonical_trusted_subset,
)
from completed_market_session_gate import (
    AUTHORITY_BOUNDARIES,
    DEFAULT_SAFETY_FLOOR,
    OPERATING_TIMEZONE,
    READY_SEMANTIC,
    STATUS_ATTEMPT_ELIGIBLE,
    STATUS_BLOCKED,
    STATUS_NON_WORKING_DATE,
    STATUS_PROVIDER_EVIDENCE_UNAVAILABLE,
    STATUS_READY,
    STATUS_SESSION_MISMATCH,
    STATUS_TOO_EARLY,
    CompletedSessionGateError,
    evaluate_attempt_eligibility,
    evaluate_completed_market_session_gate,
    load_exact_session_evidence_from_root,
    load_json_mapping,
    parse_requested_at,
    parse_session_date,
)
from daily_producer_pipeline import DailyProducerError, run_daily_producer
from field_temporal_contract import stable_id
from governed_publication_completion import PublicationCompletionError
from vn_time import VN_TZ, vn_now

ROOT = Path(__file__).resolve().parent
CONTRACT_VERSION = "canonical_daily_operation/v1"
MARKET_ACQUISITION_OWNER = "canonical_p3f9b_exact_session"
AUTHORITY_EFFECT = "NONE"

STATE_PUBLISHED = "PUBLISHED"
STATE_LOCAL_COMPLETE = "LOCAL_COMPLETE"

STAGE_TOO_EARLY = "TOO_EARLY"
STAGE_NON_WORKING_DATE = "NON_WORKING_DATE"
STAGE_FUTURE_SESSION = "FUTURE_SESSION"
STAGE_PROVIDER_EVIDENCE_UNAVAILABLE = "PROVIDER_EVIDENCE_UNAVAILABLE"
STAGE_BLOCKED_PRE_ACQUISITION = "BLOCKED_PRE_ACQUISITION_SESSION_EVIDENCE"
STAGE_BLOCKED_ACQUISITION = "BLOCKED_ACQUISITION"
STAGE_BLOCKED_POST_ACQUISITION = "BLOCKED_POST_ACQUISITION_SESSION_MISMATCH"
STAGE_BLOCKED_INPUT_REGISTRATION = "BLOCKED_INPUT_REGISTRATION"
STAGE_BLOCKED_DAILY_PRODUCER = "BLOCKED_DAILY_PRODUCER"
STAGE_BLOCKED_RUNTIME_RELEASE = "BLOCKED_RUNTIME_RELEASE"
STAGE_BLOCKED_TRUSTED_SUBSET = "BLOCKED_TRUSTED_SUBSET"
STAGE_BLOCKED_SESSION_IDENTITY = "BLOCKED_SESSION_IDENTITY_MISMATCH"


class CanonicalDailyOperationError(CanonicalPostCloseError):
    """Fail-closed refusal at an exact daily-operation stage."""

    def __init__(self, stage: str, message: str | None = None, *, local_state: Mapping[str, Any] | None = None):
        self.stage = stage
        self.local_state = dict(local_state or {})
        super().__init__(message or stage)


def _git_head(path: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return None


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != encoded:
        raise CanonicalDailyOperationError("IMMUTABLE_OPERATION_RECORD_CONFLICT", path.name)
    if not path.exists():
        path.write_text(encoded, encoding="utf-8")


def _working_dates_probe() -> dict[str, Any]:
    """Exactly one DNSE working_dates GET. Not a market-wide acquisition."""
    from dnse_access import credential_status, credentials_for_request
    from dnse_bulk_market_data import fetch_capability_raw
    from dnse_secrets_env import ensure_credentials_loaded

    ensure_credentials_loaded()
    status = credential_status()
    if not status.get("configured"):
        raise CanonicalDailyOperationError(STAGE_PROVIDER_EVIDENCE_UNAVAILABLE, "DNSE_CREDENTIAL_INJECTION_REQUIRED")
    api_key, api_secret = credentials_for_request()
    response = fetch_capability_raw("working_dates", api_key=api_key, api_secret=api_secret, query={})
    if not response.get("ok"):
        raise CanonicalDailyOperationError(
            STAGE_PROVIDER_EVIDENCE_UNAVAILABLE,
            "WORKING_DATES_PROBE_FAILED:" + str(response.get("error_code")),
        )
    body = response.get("body")
    if not isinstance(body, dict):
        raise CanonicalDailyOperationError(STAGE_PROVIDER_EVIDENCE_UNAVAILABLE, "WORKING_DATES_PROBE_BODY_NOT_OBJECT")
    return {"body": body, "retrieved_at": response.get("retrieved_at")}


def map_phase_a_stage(gate: Mapping[str, Any]) -> str:
    status = gate.get("attempt_gate_status")
    reasons = list(gate.get("reason_codes") or [])
    if status == STATUS_TOO_EARLY:
        return STAGE_TOO_EARLY
    if status == STATUS_NON_WORKING_DATE:
        return STAGE_NON_WORKING_DATE
    if status == STATUS_PROVIDER_EVIDENCE_UNAVAILABLE:
        return STAGE_PROVIDER_EVIDENCE_UNAVAILABLE
    if status == STATUS_SESSION_MISMATCH:
        return STAGE_BLOCKED_PRE_ACQUISITION
    if status == STATUS_BLOCKED and "FUTURE_SESSION" in reasons:
        return STAGE_FUTURE_SESSION
    return STAGE_BLOCKED_PRE_ACQUISITION


def map_phase_b_stage(gate: Mapping[str, Any]) -> str:
    status = gate.get("completion_gate_status")
    if status == STATUS_READY:
        return STATUS_READY
    return STAGE_BLOCKED_POST_ACQUISITION


def release_orchestrator_argv(
    session: str,
    *,
    runtime_root: Path,
    producer_root: Path,
    web_dir: Path | None = None,
) -> list[str]:
    argv = [
        "all",
        "--live",
        "--expected-session", session,
        "--complete-publication",
        "--backend-dir", str(Path(runtime_root)),
        "--producer-dir", str(Path(producer_root)),
    ]
    if web_dir is not None:
        argv += ["--web-dir", str(Path(web_dir))]
    return argv


def invoke_release_orchestrator_complete_publication(
    session: str,
    *,
    runtime_root: Path,
    producer_root: Path,
    web_dir: Path | None = None,
    runner: Callable[[list[str]], Any] | None = None,
) -> dict[str, Any]:
    """Delegate fully to the existing orchestrator. Do not reimplement CI/Pages."""
    argv = release_orchestrator_argv(
        session, runtime_root=runtime_root, producer_root=producer_root, web_dir=web_dir,
    )
    command = [sys.executable, str(producer_root / "tools" / "release_orchestrator.py"), *argv]
    if runner is not None:
        result = runner(argv)
        if isinstance(result, Mapping):
            payload = dict(result)
            payload.setdefault("argv", argv)
            payload.setdefault("command", command)
            return payload
        return {"argv": argv, "command": command, "runner_result": result}
    tools_dir = str(Path(producer_root) / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import release_orchestrator

    args = release_orchestrator.build_parser().parse_args(argv)
    rc = release_orchestrator.orchestrate(args)
    if rc != 0:
        raise CanonicalDailyOperationError(
            "BLOCKED_PUBLICATION_ORCHESTRATOR_EXIT",
            f"release_orchestrator_exit={rc}",
        )
    return {
        "argv": argv,
        "command": command,
        "orchestrator_exit": rc,
        "publication_state": STATE_PUBLISHED,
    }


def _producer_session(producer_result: Mapping[str, Any], fallback: str) -> str:
    return str(producer_result.get("session") or fallback)


def print_daily_operation_handoff(record: Mapping[str, Any]) -> None:
    publication = record.get("publication") if isinstance(record.get("publication"), Mapping) else {}
    print(f"DAILY_OPERATION_STATE={record.get('daily_operation_state')}")
    print(f"SESSION={record.get('session')}")
    print(f"SESSION_GATE={record.get('session_gate_semantic') or record.get('session_gate')}")
    print(f"DAILY_PRODUCER={record.get('daily_producer_status')}")
    print(f"RUNTIME_RELEASE={record.get('runtime_release_status')}")
    print(f"TRUSTED_SUBSET={record.get('trusted_subset_status')}")
    print(f"DASHBOARD_RELEASE_SHA={publication.get('release_source_sha') or publication.get('dashboard_release_sha') or ''}")
    print(f"DASHBOARD_CI={publication.get('dashboard_ci_status') or ''}")
    print(f"DEPLOY_PAGES={publication.get('deploy_pages_status') or ''}")
    print(f"PUBLIC_BYTE_IDENTITY={publication.get('public_byte_identity') or ''}")
    print(f"AUTHORITY_EFFECT={record.get('authority_effect')}")
    print(f"MARKET_ACQUISITION_OWNER={record.get('market_acquisition_owner')}")
    print(f"OPERATION_IDENTITY={record.get('operation_identity')}")
    if record.get("stage"):
        print(f"STAGE={record.get('stage')}")


def run_canonical_daily_operation(
    root: Path,
    runtime_root: Path,
    session: str | None = None,
    *,
    now: datetime | None = None,
    workers: int = 12,
    complete_publication: bool = False,
    working_dates_evidence: Mapping[str, Any] | None = None,
    exact_session_evidence: Mapping[str, Any] | None = None,
    working_dates_fetcher: Callable[[], Mapping[str, Any]] | None = None,
    allow_provider_probe: bool = False,
    acquire_fn: Callable[..., Mapping[str, Any]] | None = None,
    producer_fn: Callable[..., Mapping[str, Any]] | None = None,
    runtime_fn: Callable[..., Mapping[str, Any]] | None = None,
    trusted_fn: Callable[..., Mapping[str, Any]] | None = None,
    publication_runner: Callable[[list[str]], Any] | None = None,
    web_dir: Path | None = None,
    out_dir: Path | str | None = None,
    consumer_root: Path | None = None,
) -> dict[str, Any]:
    """Foreground one-shot daily operation. Tests must inject ``now`` / ``requested_at``."""
    root = Path(root)
    runtime_root = Path(runtime_root)
    instant = now or vn_now()
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=VN_TZ)
    else:
        instant = instant.astimezone(VN_TZ)
    output_root = Path(out_dir) if out_dir else root / "operations-review"
    acquire = acquire_fn or acquire_and_materialize
    produce = producer_fn or run_daily_producer
    runtime_materialize = runtime_fn or materialize_canonical_runtime_release
    trusted_materialize = trusted_fn or materialize_canonical_trusted_subset
    probe = working_dates_fetcher
    if probe is None and allow_provider_probe:
        probe = _working_dates_probe

    explicit_session = parse_session_date(session) if session else None
    # A historical completed session may have fallen out of DNSE's current
    # forward working_dates window.  Reuse only the existing retained DNSE
    # exact-session evidence for that exact request; this is read-only and
    # never turns a different session, a weekday, or civil time into proof.
    resolved_exact_evidence = exact_session_evidence
    if resolved_exact_evidence is None and explicit_session:
        resolved_exact_evidence = load_exact_session_evidence_from_root(root, explicit_session)
    try:
        phase_a = evaluate_attempt_eligibility(
            requested_at=instant,
            requested_session=explicit_session,
            timezone_name=OPERATING_TIMEZONE,
            safety_floor=DEFAULT_SAFETY_FLOOR,
            working_dates_evidence=working_dates_evidence,
            exact_session_evidence=resolved_exact_evidence,
            working_dates_fetcher=probe,
            allow_provider_probe=allow_provider_probe,
            allow_historical_target_session_acquisition=True,
        )
    except CompletedSessionGateError as exc:
        raise CanonicalDailyOperationError(STAGE_BLOCKED_PRE_ACQUISITION, str(exc)) from exc

    if phase_a.get("attempt_gate_status") != STATUS_ATTEMPT_ELIGIBLE:
        raise CanonicalDailyOperationError(
            map_phase_a_stage(phase_a),
            ",".join(phase_a.get("reason_codes") or [str(phase_a.get("attempt_gate_status"))]),
            local_state={"phase_a": phase_a},
        )
    resolved_session = str(phase_a.get("resolved_session") or "")
    if not resolved_session:
        raise CanonicalDailyOperationError(STAGE_BLOCKED_PRE_ACQUISITION, "INTENDED_SESSION_UNRESOLVED")

    acquisition_calls = 0

    def _acquire() -> Mapping[str, Any]:
        nonlocal acquisition_calls
        acquisition_calls += 1
        return acquire(root, resolved_session, runtime_root, workers=workers, now=instant)

    try:
        acquisition = _acquire()
    except CanonicalPostCloseError as exc:
        raise CanonicalDailyOperationError(STAGE_BLOCKED_ACQUISITION, str(exc), local_state={"phase_a": phase_a}) from exc
    except Exception as exc:
        raise CanonicalDailyOperationError(
            STAGE_BLOCKED_ACQUISITION, f"{type(exc).__name__}:{exc}", local_state={"phase_a": phase_a},
        ) from exc

    if acquisition_calls != 1:
        raise CanonicalDailyOperationError(STAGE_BLOCKED_ACQUISITION, "DUPLICATE_MARKET_ACQUISITION")

    snapshot = acquisition.get("snapshot") if isinstance(acquisition, Mapping) else None
    if not isinstance(snapshot, Mapping):
        raise CanonicalDailyOperationError(STAGE_BLOCKED_ACQUISITION, "EXACT_SESSION_SNAPSHOT_MISSING_AFTER_ACQUISITION")
    if str(acquisition.get("resolved_completed_session") or snapshot.get("resolved_completed_session")) != resolved_session:
        raise CanonicalDailyOperationError(
            STAGE_BLOCKED_POST_ACQUISITION,
            "P3F9B_ACQUIRED_SESSION_MISMATCH",
            local_state={"phase_a": phase_a, "acquisition": {"resolved": acquisition.get("resolved_completed_session")}},
        )
    if snapshot.get("contract_version") == "p3f9_exact_session_mva_snapshot/v2":
        try:
            assert_post_close_eligible(snapshot, resolved_session, now=instant)
        except PreCutoffArtifactError as exc:
            raise CanonicalDailyOperationError(STAGE_BLOCKED_POST_ACQUISITION, str(exc), local_state={"phase_a": phase_a}) from exc

    phase_b_working = working_dates_evidence
    if phase_b_working is None:
        phase_b_working = {"workingDates": list(phase_a.get("working_dates") or [])}
    phase_b = evaluate_completed_market_session_gate(
        requested_at=instant,
        requested_session=resolved_session,
        timezone_name=OPERATING_TIMEZONE,
        safety_floor=DEFAULT_SAFETY_FLOOR,
        working_dates_evidence=phase_b_working,
        exact_session_evidence=snapshot,
        allow_provider_probe=False,
    )
    if phase_b.get("completion_gate_status") != STATUS_READY:
        raise CanonicalDailyOperationError(
            map_phase_b_stage(phase_b),
            ",".join(phase_b.get("reason_codes") or [str(phase_b.get("completion_gate_status"))]),
            local_state={"phase_a": phase_a, "phase_b": phase_b, "acquisition": acquisition},
        )

    artifact_root = Path(acquisition.get("artifact_root") or root)
    try:
        registration = register_session_inputs(root, resolved_session, artifact_root=artifact_root)
        freeze = validate_and_freeze_completed_session(root, resolved_session)
    except CanonicalPostCloseError as exc:
        raise CanonicalDailyOperationError(STAGE_BLOCKED_INPUT_REGISTRATION, str(exc)) from exc

    producer_head, consumer_head = _git_head(root), _git_head(root.parent / "ai-core-private")
    try:
        producer_result = produce(
            root, session=resolved_session, latest_completed_session=False,
            producer_head=producer_head or "UNKNOWN", consumer_head=consumer_head or "UNKNOWN",
            now=instant,
        )
    except DailyProducerError as exc:
        raise CanonicalDailyOperationError(STAGE_BLOCKED_DAILY_PRODUCER, str(exc)) from exc
    except CanonicalPostCloseError as exc:
        raise CanonicalDailyOperationError(STAGE_BLOCKED_DAILY_PRODUCER, str(exc)) from exc

    if not isinstance(producer_result, Mapping) or producer_result.get("status") not in {None, "COMPLETED", "PASS"}:
        status = None if not isinstance(producer_result, Mapping) else producer_result.get("status")
        if status not in {"COMPLETED", "PASS"} and producer_result.get("run_identity"):
            # Daily Producer historically returns status COMPLETED; tolerate run_identity as success.
            pass
        elif status not in {"COMPLETED", "PASS"}:
            raise CanonicalDailyOperationError(STAGE_BLOCKED_DAILY_PRODUCER, f"DAILY_PRODUCER_STATUS:{status}")

    producer_session = _producer_session(producer_result, resolved_session)
    if producer_session != resolved_session:
        raise CanonicalDailyOperationError(
            STAGE_BLOCKED_SESSION_IDENTITY,
            f"DAILY_PRODUCER_SESSION_MISMATCH:expected={resolved_session}:observed={producer_session}",
        )

    try:
        runtime_materialized = runtime_materialize(root, runtime_root, resolved_session)
    except CanonicalRuntimeReleaseError as exc:
        raise CanonicalDailyOperationError(STAGE_BLOCKED_RUNTIME_RELEASE, str(exc)) from exc

    runtime_release = evaluate_dashboard_runtime_readiness(runtime_root, resolved_session)
    runtime_session = str(
        (runtime_materialized or {}).get("session")
        or runtime_release.get("resolved_session")
        or ""
    )
    if not runtime_release.get("ready") or runtime_session != resolved_session:
        raise CanonicalDailyOperationError(
            STAGE_BLOCKED_RUNTIME_RELEASE,
            runtime_release.get("reason") or f"RUNTIME_SESSION_MISMATCH:{runtime_session}",
        )

    try:
        trusted = trusted_materialize(
            root, runtime_root, resolved_session, consumer_root=consumer_root,
        )
    except CanonicalTrustedSubsetError as exc:
        raise CanonicalDailyOperationError(STAGE_BLOCKED_TRUSTED_SUBSET, str(exc)) from exc

    trusted_session = str((trusted or {}).get("session") or "")
    if not trusted.get("trusted_subset_ready") or trusted_session != resolved_session:
        raise CanonicalDailyOperationError(
            STAGE_BLOCKED_TRUSTED_SUBSET,
            f"TRUSTED_SUBSET_SESSION_MISMATCH:expected={resolved_session}:observed={trusted_session}",
        )
    if not (producer_session == runtime_session == trusted_session == resolved_session):
        raise CanonicalDailyOperationError(
            STAGE_BLOCKED_SESSION_IDENTITY,
            "runtime={}:trusted={}:producer={}:expected={}".format(
                runtime_session, trusted_session, producer_session, resolved_session,
            ),
        )

    enrichment = build_enrichment_components(root, resolved_session, artifact_root=artifact_root)
    operation = producer_result.get("operation") if isinstance(producer_result.get("operation"), Mapping) else {}
    decision_packet = build_decision_packet(
        root, resolved_session, opportunity=operation.get("opportunity"), enrichment=enrichment,
        artifact_root=artifact_root,
    )
    prospective = run_prospective_collection(root, resolved_session, artifact_root=artifact_root)
    tiers = build_tiered_bundle(
        root, resolved_session, acquisition=acquisition, producer_result=producer_result,
        decision_packet=decision_packet, prospective=prospective, enrichment=enrichment,
        producer_head=producer_head, consumer_head=consumer_head, artifact_root=artifact_root,
        runtime_release=runtime_release,
    )

    publication: dict[str, Any] | None = None
    state = STATE_LOCAL_COMPLETE
    if complete_publication:
        try:
            publication = invoke_release_orchestrator_complete_publication(
                resolved_session,
                runtime_root=runtime_root,
                producer_root=root,
                web_dir=web_dir,
                runner=publication_runner,
            )
        except PublicationCompletionError as exc:
            local = {
                "phase_a": phase_a,
                "phase_b": phase_b,
                "acquisition": acquisition,
                "producer_result": {"status": producer_result.get("status"), "run_identity": producer_result.get("run_identity")},
                "runtime_release": runtime_release,
                "trusted_subset": {"session": trusted_session, "ready": True},
            }
            raise CanonicalDailyOperationError(
                "BLOCKED_PUBLICATION_" + str(exc.code),
                str(exc),
                local_state=local,
            ) from exc
        except CanonicalDailyOperationError:
            raise
        except Exception as exc:
            raise CanonicalDailyOperationError(
                "BLOCKED_PUBLICATION_ORCHESTRATOR_EXIT",
                f"{type(exc).__name__}:{exc}",
                local_state={"runtime_release": runtime_release, "trusted_subset": {"session": trusted_session}},
            ) from exc
        if str(publication.get("publication_state") or "").upper() == STATE_PUBLISHED:
            state = STATE_PUBLISHED
        elif publication.get("orchestrator_exit") == 0 and complete_publication:
            state = STATE_PUBLISHED
            publication.setdefault("publication_state", STATE_PUBLISHED)

    producer_status = "COMPLETED" if producer_result.get("run_identity") or producer_result.get("status") in {"COMPLETED", "PASS"} else str(producer_result.get("status"))
    identity_payload = {
        "contract_version": CONTRACT_VERSION,
        "session": resolved_session,
        "phase_a_identity": phase_a.get("gate_identity"),
        "phase_b_identity": phase_b.get("gate_identity"),
        "acquisition_identity": snapshot.get("snapshot_identity") or snapshot.get("artifact_identity"),
        "daily_producer_run_identity": producer_result.get("run_identity"),
        "decision_packet_identity": (decision_packet or {}).get("artifact_identity"),
        "prospective_identity": ((prospective or {}).get("snapshot") or {}).get("snapshot_id"),
        "runtime_session": runtime_session,
        "trusted_session": trusted_session,
        "publication_state": state,
        "authority_effect": AUTHORITY_EFFECT,
    }
    digest = stable_id(identity_payload)
    operation_identity = f"canonical_daily_operation:{digest}"
    run_dir = output_root / "canonical-daily-operation-v1" / resolved_session / f"op-{digest}"
    record = {
        "schema_version": CONTRACT_VERSION,
        "session": resolved_session,
        "requested_at": instant.isoformat(),
        "daily_operation_state": state,
        "session_gate_semantic": READY_SEMANTIC if state in {STATE_PUBLISHED, STATE_LOCAL_COMPLETE} else None,
        "session_gate": READY_SEMANTIC,
        "phase_a": {
            "identity": phase_a.get("gate_identity"),
            "status": phase_a.get("attempt_gate_status"),
            "resolved_session": phase_a.get("resolved_session"),
        },
        "phase_b": {
            "identity": phase_b.get("gate_identity"),
            "status": phase_b.get("completion_gate_status"),
            "ready_semantic": phase_b.get("ready_semantic"),
        },
        "market_acquisition_owner": MARKET_ACQUISITION_OWNER,
        "capability_first_collector_invoked": False,
        "canonical_p3f9b_invoked": True,
        "market_acquisition_attempts": acquisition_calls,
        "acquisition": {
            "resolved_completed_session": acquisition.get("resolved_completed_session"),
            "snapshot_identity": snapshot.get("snapshot_identity") or snapshot.get("artifact_identity"),
            "coverage": acquisition.get("coverage"),
            "eligibility": acquisition.get("eligibility"),
        },
        "registration": registration,
        "freeze": freeze,
        "daily_producer_status": producer_status,
        "daily_producer_run_identity": producer_result.get("run_identity"),
        "daily_producer_operation_identity": ((operation.get("manifest") or {}).get("operation_identity")
                                              if isinstance(operation, Mapping) else None),
        "decision_packet_identity": (decision_packet or {}).get("artifact_identity"),
        "prospective_cohort_identity": ((prospective or {}).get("snapshot") or {}).get("snapshot_id"),
        "runtime_release_status": "READY" if runtime_release.get("ready") else "NOT_READY",
        "runtime_release": runtime_release,
        "trusted_subset_status": "READY" if trusted.get("trusted_subset_ready") else "NOT_READY",
        "trusted_subset": {
            "session": trusted_session,
            "trusted_subset_ready": trusted.get("trusted_subset_ready"),
            "records_fingerprint": trusted.get("records_fingerprint"),
        },
        "publication": publication,
        "tiers": {
            "session_handoff_bundle": _rel(root, Path(tiers["bundle_dir"]) / "session_handoff_bundle.json") if isinstance(tiers, Mapping) and tiers.get("bundle_dir") else None,
        },
        "authority_effect": AUTHORITY_EFFECT,
        "authority_boundaries": dict(AUTHORITY_BOUNDARIES),
        "is_idempotent_replay": bool((acquisition.get("eligibility") or {}).get("reused_existing_eligible_artifact")),
        "operation_identity": operation_identity,
        "operation_directory": str(run_dir.as_posix()),
        "producer_result": producer_result,
        "decision_packet": decision_packet,
        "prospective": prospective,
        "enrichment": enrichment,
    }
    persistable = {k: v for k, v in record.items() if k not in {"producer_result", "decision_packet", "prospective", "enrichment"}}
    persistable["lineage"] = {
        "session_gate_phase_a": phase_a.get("gate_identity"),
        "session_gate_phase_b": phase_b.get("gate_identity"),
        "acquisition": snapshot.get("snapshot_identity") or snapshot.get("artifact_identity"),
        "daily_producer": producer_result.get("run_identity"),
        "decision_packet": (decision_packet or {}).get("artifact_identity"),
        "prospective_cohort": ((prospective or {}).get("snapshot") or {}).get("snapshot_id"),
        "runtime_release_session": runtime_session,
        "trusted_subset_session": trusted_session,
        "publication_attestation": None if not publication else publication.get("attestation_identity"),
    }
    existing = run_dir / "daily_operation_record.json"
    if existing.is_file():
        prior = json.loads(existing.read_text(encoding="utf-8"))
        skip = {"is_idempotent_replay"}
        comparable_prior = {k: v for k, v in prior.items() if k not in skip}
        comparable_new = {k: v for k, v in persistable.items() if k not in skip}
        if comparable_prior == comparable_new:
            merged = dict(record)
            merged.update(prior)
            merged["is_idempotent_replay"] = True
            return merged
        raise CanonicalDailyOperationError("IMMUTABLE_OPERATION_RECORD_CONFLICT")
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "phase_a_gate.json", phase_a)
    _write_json(run_dir / "phase_b_gate.json", phase_b)
    _write_json(existing, persistable)
    return record


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def parse_cli_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Canonical daily one-command operation.")
    parser.add_argument("--runtime-root", default=None)
    parser.add_argument("--session", default=None)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--complete-publication", action="store_true")
    parser.add_argument("--requested-at", default=None)
    parser.add_argument("--working-dates-path", default=None)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--allow-provider-probe", action="store_true")
    parser.add_argument("--web-dir", default=None)
    parser.add_argument("--out-dir", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_cli_args(argv)
    from runtime_paths import RUNTIME_ROOT_ENV, runtime_root as resolve_runtime_root

    configured = args.runtime_root or None
    root_path = resolve_runtime_root(configured) if configured or __import__("os").environ.get(RUNTIME_ROOT_ENV) else None
    if root_path is None:
        print("[canonical_daily_operation] --runtime-root or STOCK_LOOKUP_RUNTIME_ROOT is required", file=sys.stderr)
        return 2
    if not Path(root_path).is_dir():
        print(f"[canonical_daily_operation] runtime root does not exist: {root_path}", file=sys.stderr)
        return 2
    probe = bool(args.allow_provider_probe) and not args.offline
    if not args.offline and args.working_dates_path is None and not args.allow_provider_probe:
        probe = True
    instant = parse_requested_at(args.requested_at) if args.requested_at else vn_now()
    try:
        record = run_canonical_daily_operation(
            ROOT,
            Path(root_path),
            args.session,
            now=instant,
            workers=args.workers,
            complete_publication=args.complete_publication,
            working_dates_evidence=load_json_mapping(args.working_dates_path) if args.working_dates_path else None,
            working_dates_fetcher=_working_dates_probe if probe else None,
            allow_provider_probe=probe,
            web_dir=Path(args.web_dir) if args.web_dir else None,
            out_dir=args.out_dir,
        )
    except CanonicalDailyOperationError as exc:
        print(f"DAILY_OPERATION_STATE={exc.stage}")
        print(f"STAGE={exc.stage}")
        print(f"REASON={exc}")
        return 2 if exc.stage in {STAGE_TOO_EARLY, STAGE_NON_WORKING_DATE, STAGE_FUTURE_SESSION, STAGE_PROVIDER_EVIDENCE_UNAVAILABLE, STAGE_BLOCKED_PRE_ACQUISITION} else 1
    print_daily_operation_handoff(record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
