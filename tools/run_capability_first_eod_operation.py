"""One-shot foreground capability-first EOD operation.

CHAIN
    resolve candidate completed market session
    -> evaluate completed-session evidence (fail closed before acquisition)
    -> existing capability-first EOD collector
    -> retained packet validation
    -> existing deterministic daily research materialization
    -> immutable identity / completion-record verification
    -> one terminal operation disposition/log
    -> compact handoff

This command is scheduler-safe: no OS scheduler is installed, no poll, no sleep,
no daemon, no background loop. An external operator or scheduler may invoke it
once around/after the configured 18:00 Asia/Ho_Chi_Minh safety floor.

Do not create another collector or research engine. Authority effect remains NONE.
"""
from __future__ import annotations

import argparse
from datetime import datetime, time
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atomic_io import atomic_write_json, validate_json_file
from completed_market_session_gate import (
    AUTHORITY_BOUNDARIES,
    DEFAULT_SAFETY_FLOOR,
    OPERATING_TIMEZONE,
    STATUS_ATTEMPT_ELIGIBLE,
    STATUS_READY,
    CompletedSessionGateError,
    evaluate_attempt_eligibility,
    evaluate_completed_market_session_gate,
    load_exact_session_evidence_from_root,
    load_json_mapping,
    parse_requested_at,
    parse_session_date,
)
from field_temporal_contract import canonical_json, stable_id
from tools import collect_market_evidence as collector_module
from tools.materialize_daily_market_research import (
    find_retained_session_packet,
    materialize_daily_market_research,
    validate_completed_bundle,
)
from vn_time import vn_now

CONTRACT_VERSION = "capability_first_eod_operation/v1"
DEFAULT_CONFIG_PATH = ROOT / "config" / "capability_first_eod_operation.json"
AUTHORITY_EFFECT = "NONE"

DISPOSITION_COMPLETED = "COMPLETED"
DISPOSITION_BLOCKED_BEFORE_COLLECTION = "BLOCKED_BEFORE_COLLECTION"
DISPOSITION_BLOCKED_POST_ACQUISITION = "BLOCKED_POST_ACQUISITION"
DISPOSITION_COLLECTOR_FAILED = "COLLECTOR_FAILED"
DISPOSITION_PACKET_INVALID = "PACKET_INVALID"
DISPOSITION_MATERIALIZATION_FAILED = "MATERIALIZATION_FAILED"
DISPOSITION_TAMPERED_PACKET = "TAMPERED_PACKET"


class EodOperationError(RuntimeError):
    """Fail-closed operation refusal."""


def load_schedule_config(path: Path | str | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        return {
            "schema_version": "capability_first_eod_operation_schedule_contract/v1",
            "operating_timezone": OPERATING_TIMEZONE,
            "safety_floor_local_time": "18:00",
            "scheduler_ready": True,
        }
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise EodOperationError("SCHEDULE_CONFIG_NOT_OBJECT")
    return payload


def parse_safety_floor(value: Any) -> time:
    if isinstance(value, time):
        return value
    text = str(value or "18:00").strip()
    parts = text.split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    return time(hour, minute)


def _verify_packet_identity(packet: Mapping[str, Any], packet_bytes: bytes | None = None) -> None:
    recorded = packet.get("packet_sha256")
    if not recorded:
        raise EodOperationError("PACKET_IDENTITY_MISSING")
    clean = {key: value for key, value in packet.items() if key not in {"packet_sha256", "packet_identity"}}
    digest = hashlib.sha256(canonical_json(clean).encode("utf-8")).hexdigest()
    if digest != recorded:
        raise EodOperationError("PACKET_IDENTITY_MISMATCH")
    identity = packet.get("packet_identity")
    if identity and identity != f"packet:{digest}" and identity != f"capability_first_eod_packet:{digest}":
        # Collector prefixes with "packet:"; tolerate the explicit collector prefix only.
        if not str(identity).endswith(str(recorded)):
            raise EodOperationError("PACKET_IDENTITY_PREFIX_MISMATCH")


def _packet_exact_session_ok(packet: Mapping[str, Any], session: str) -> tuple[bool, str]:
    if str(packet.get("session_date") or "") != session:
        return False, "PACKET_SESSION_MISMATCH"
    observations = packet.get("observations") if isinstance(packet.get("observations"), list) else []
    acquired = [
        row for row in observations
        if isinstance(row, Mapping)
        and row.get("status") == "ACQUIRED"
        and (row.get("provider_session_date") or row.get("session")) == session
    ]
    if not acquired:
        return False, "PACKET_EXACT_SESSION_OBSERVATIONS_MISSING"
    authority = packet.get("authority_boundaries") if isinstance(packet.get("authority_boundaries"), Mapping) else {}
    if authority.get("authority_effect") not in {None, "NONE"}:
        return False, "PACKET_AUTHORITY_EFFECT_NOT_NONE"
    return True, "PACKET_EXACT_SESSION_VALID"


def _operation_dir(out_dir: Path, session: str, digest: str) -> Path:
    return out_dir / "capability-first-eod-operation-v1" / session / f"op-{digest}"


def _write_immutable_json(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != encoded:
        raise EodOperationError("IMMUTABLE_OPERATION_RECORD_CONFLICT:" + path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        atomic_write_json(path, payload, validator=validate_json_file)


def _working_dates_probe() -> dict[str, Any]:
    """Exactly one DNSE working_dates GET through the approved secret-loading path."""
    from dnse_access import credential_status, credentials_for_request
    from dnse_bulk_market_data import fetch_capability_raw
    from dnse_secrets_env import ensure_credentials_loaded

    ensure_credentials_loaded()
    status = credential_status()
    if not status.get("configured"):
        raise EodOperationError("DNSE_CREDENTIAL_INJECTION_REQUIRED")
    api_key, api_secret = credentials_for_request()
    response = fetch_capability_raw("working_dates", api_key=api_key, api_secret=api_secret, query={})
    if not response.get("ok"):
        raise EodOperationError("WORKING_DATES_PROBE_FAILED:" + str(response.get("error_code")))
    body = response.get("body")
    if not isinstance(body, dict):
        raise EodOperationError("WORKING_DATES_PROBE_BODY_NOT_OBJECT")
    return {"body": body, "retrieved_at": response.get("retrieved_at")}


def _compact_handoff(record: Mapping[str, Any]) -> str:
    lines = [
        f"SESSION: {record.get('session')}",
        f"REQUESTED_AT: {record.get('requested_at')}",
        f"GATE_STATUS: {(record.get('session_gate') or {}).get('completion_gate_status')}",
        f"DISPOSITION: {record.get('final_disposition')}",
        f"REASON_CODES: {','.join(record.get('reason_codes') or [])}",
        f"EOD_COLLECTION_IDENTITY: {record.get('eod_collection_identity')}",
        f"RETAINED_PACKET_IDENTITY: {record.get('retained_packet_identity')}",
        f"CANONICAL_INTEGRATION_IDENTITY: {record.get('canonical_integration_identity')}",
        f"MARKET_RESEARCH_MATERIALIZATION_IDENTITY: {record.get('market_research_materialization_identity')}",
        f"COMPLETION_RECORD_IDENTITY: {record.get('completion_record_identity')}",
        f"OPERATION_IDENTITY: {record.get('operation_identity')}",
        f"IDEMPOTENT_REPLAY: {record.get('is_idempotent_replay')}",
        f"AUTHORITY_EFFECT: {record.get('authority_effect')}",
        f"SCHEDULER_READY: {record.get('scheduler_ready')}",
        f"COLLECTOR_INVOKED: {record.get('collector_invoked')}",
        f"MATERIALIZATION_INVOKED: {record.get('materialization_invoked')}",
    ]
    return "\n".join(lines)


def run_capability_first_eod_operation(
    *,
    requested_at: datetime | str | None = None,
    session: str | None = None,
    root: Path | str | None = None,
    out_dir: Path | str | None = None,
    packet_path: Path | str | None = None,
    working_dates_evidence: Mapping[str, Any] | None = None,
    exact_session_evidence: Mapping[str, Any] | None = None,
    working_dates_fetcher: Callable[[], Mapping[str, Any]] | None = None,
    allow_provider_probe: bool = False,
    collect_fetcher: Callable[..., dict[str, Any]] | None = None,
    allow_collect: bool = True,
    replay_only: bool = False,
    collect_kwargs: Mapping[str, Any] | None = None,
    config_path: Path | str | None = None,
    collector: Callable[..., Mapping[str, Any]] | None = None,
    materializer: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the bounded one-command capability-first EOD operation."""
    repo_root = Path(root) if root else ROOT
    config = load_schedule_config(config_path)
    safety_floor = parse_safety_floor(config.get("safety_floor_local_time"))
    instant = parse_requested_at(requested_at if requested_at is not None else vn_now())
    output_root = Path(out_dir) if out_dir else repo_root / "operations-review"

    resolved_exact = exact_session_evidence
    if resolved_exact is None:
        lookup_session = parse_session_date(session) if session else instant.date().isoformat()
        resolved_exact = load_exact_session_evidence_from_root(repo_root, lookup_session)

    gate = evaluate_attempt_eligibility(
        requested_at=instant,
        requested_session=session,
        timezone_name=str(config.get("operating_timezone") or OPERATING_TIMEZONE),
        safety_floor=safety_floor,
        working_dates_evidence=working_dates_evidence,
        exact_session_evidence=resolved_exact,
        working_dates_fetcher=working_dates_fetcher,
        allow_provider_probe=allow_provider_probe,
    )
    resolved_session = gate.get("resolved_session")
    collector_invoked = False
    materialization_invoked = False
    collect_fn = collector or collector_module.collect_market_evidence
    materialize_fn = materializer or materialize_daily_market_research

    def finish(
        *,
        disposition: str,
        reason_codes: list[str],
        packet: Mapping[str, Any] | None = None,
        packet_path_used: str | None = None,
        materialization: Mapping[str, Any] | None = None,
        is_idempotent_replay: bool = False,
        collector_called: bool = False,
        materialization_called: bool = False,
    ) -> dict[str, Any]:
        session_value = resolved_session or session
        identity_payload = {
            "contract_version": CONTRACT_VERSION,
            "session": session_value,
            "gate_identity": gate.get("gate_identity"),
            "completion_gate_status": gate.get("completion_gate_status"),
            "final_disposition": disposition,
            "packet_identity": None if packet is None else packet.get("packet_identity"),
            "materialization_identity": None if materialization is None else materialization.get("materialization_identity"),
            "requested_at": instant.isoformat() if disposition != DISPOSITION_COMPLETED else "SESSION_BOUND",
        }
        if disposition != DISPOSITION_COMPLETED:
            identity_payload["attempt_requested_at"] = instant.isoformat()
        digest = stable_id(identity_payload)
        operation_identity = f"capability_first_eod_operation:{digest}"
        run_dir = _operation_dir(output_root, str(session_value or "unresolved"), digest)
        completion = None
        if materialization and materialization.get("disposition") == "MATERIALIZATION_SUCCESS":
            run_directory = materialization.get("run_directory")
            if run_directory:
                completion_path = Path(run_directory)
                if not completion_path.is_absolute():
                    completion_path = repo_root / completion_path
                if (completion_path / "completion_record.json").is_file():
                    completion = json.loads((completion_path / "completion_record.json").read_text(encoding="utf-8"))
        record = {
            "schema_version": CONTRACT_VERSION,
            "session": session_value,
            "requested_at": instant.isoformat(),
            "session_gate": {
                "identity": gate.get("gate_identity"),
                "content_identity": gate.get("gate_content_identity"),
                "attempt_gate_status": gate.get("attempt_gate_status"),
                "completion_gate_status": gate.get("completion_gate_status") or gate.get("attempt_gate_status"),
                "provider_semantic_strength": gate.get("provider_semantic_strength"),
                "ready_semantic": gate.get("ready_semantic"),
            },
            "eod_collection_identity": None if packet is None else packet.get("packet_identity"),
            "retained_packet_identity": None if packet is None else packet.get("packet_identity"),
            "retained_packet_sha256": None if packet is None else packet.get("packet_sha256"),
            "retained_packet_path": packet_path_used,
            "canonical_integration_identity": None if materialization is None else materialization.get("canonical_integration_identity"),
            "market_research_materialization_identity": None if materialization is None else materialization.get("materialization_identity"),
            "completion_record_identity": None if not isinstance(completion, Mapping) else completion.get("completion_identity"),
            "final_disposition": disposition,
            "reason_codes": list(reason_codes),
            "is_idempotent_replay": is_idempotent_replay,
            "authority_effect": AUTHORITY_EFFECT,
            "authority_boundaries": dict(AUTHORITY_BOUNDARIES),
            "collector_invoked": collector_called,
            "materialization_invoked": materialization_called,
            "scheduler_ready": "YES" if config.get("scheduler_ready", True) else "NO",
            "operation_identity": operation_identity,
            "operation_directory": str(run_dir.as_posix()),
        }
        existing = run_dir / "operation_record.json"
        if existing.is_file():
            prior = json.loads(existing.read_text(encoding="utf-8"))
            skip = {"is_idempotent_replay", "collector_invoked", "materialization_invoked"}
            comparable_prior = {k: v for k, v in prior.items() if k not in skip}
            comparable_new = {k: v for k, v in record.items() if k not in skip}
            if comparable_prior == comparable_new:
                record = dict(prior)
                record["is_idempotent_replay"] = True
                return record
            raise EodOperationError("IMMUTABLE_OPERATION_RECORD_CONFLICT")
        run_dir.mkdir(parents=True, exist_ok=True)
        _write_immutable_json(run_dir / "session_gate.json", gate)
        _write_immutable_json(existing, record)
        return record

    if gate.get("attempt_gate_status") != STATUS_ATTEMPT_ELIGIBLE or not resolved_session:
        return finish(
            disposition=DISPOSITION_BLOCKED_BEFORE_COLLECTION,
            reason_codes=list(gate.get("reason_codes") or [str(gate.get("attempt_gate_status"))]),
        )

    def _existing_packet_path() -> Path | None:
        if packet_path:
            candidate = Path(packet_path)
            return candidate if candidate.is_file() else None
        collect_out = Path((collect_kwargs or {}).get("out_dir") or output_root / f"capability-first-eod-{resolved_session}")
        local_candidates = [
            collect_out / "session_packet.json",
            output_root / f"capability-first-eod-{resolved_session}" / "session_packet.json",
            output_root / f"capability-first-real-eod-{resolved_session}" / "session_packet.json",
            repo_root / "operations-review" / f"capability-first-eod-{resolved_session}" / "session_packet.json",
            repo_root / "operations-review" / f"capability-first-real-eod-{resolved_session}" / "session_packet.json",
        ]
        for candidate in local_candidates:
            if candidate.is_file():
                return candidate
        found = find_retained_session_packet(resolved_session)
        return Path(found) if found else None

    packet: dict[str, Any] | None = None
    packet_bytes: bytes | None = None
    packet_source: str | None = None
    existing_packet = _existing_packet_path()
    if existing_packet and Path(existing_packet).is_file():
        packet_source = str(Path(existing_packet).as_posix())
        packet_bytes = Path(existing_packet).read_bytes()
        try:
            loaded = json.loads(packet_bytes.decode("utf-8"))
        except Exception as exc:
            return finish(
                disposition=DISPOSITION_PACKET_INVALID,
                reason_codes=["MALFORMED_PACKET_JSON", str(exc)],
            )
        if not isinstance(loaded, dict):
            return finish(disposition=DISPOSITION_PACKET_INVALID, reason_codes=["PACKET_NOT_OBJECT"])
        packet = loaded
        try:
            _verify_packet_identity(packet, packet_bytes)
        except EodOperationError as exc:
            return finish(disposition=DISPOSITION_TAMPERED_PACKET, reason_codes=[str(exc)])
    elif allow_collect:
        c_kwargs = dict(collect_kwargs or {})
        c_kwargs.setdefault("session_date", resolved_session)
        c_kwargs.setdefault("out_dir", output_root / f"capability-first-eod-{resolved_session}")
        c_kwargs.setdefault("replay_only", replay_only)
        if collect_fetcher is not None:
            c_kwargs["fetcher"] = collect_fetcher
        collector_invoked = True
        try:
            collected = collect_fn(**c_kwargs)
        except Exception as exc:
            return finish(
                disposition=DISPOSITION_COLLECTOR_FAILED,
                reason_codes=["COLLECTOR_EXCEPTION", type(exc).__name__],
                collector_called=True,
            )
        if not isinstance(collected, dict):
            return finish(
                disposition=DISPOSITION_COLLECTOR_FAILED,
                reason_codes=["COLLECTOR_RETURNED_NON_OBJECT"],
                collector_called=True,
            )
        packet = collected
        packet_source = str(Path(c_kwargs["out_dir"]).joinpath("session_packet.json").as_posix())
        try:
            _verify_packet_identity(packet)
        except EodOperationError as exc:
            return finish(
                disposition=DISPOSITION_TAMPERED_PACKET,
                reason_codes=[str(exc)],
                packet=packet,
                packet_path_used=packet_source,
                collector_called=True,
            )
    else:
        return finish(
            disposition=DISPOSITION_PACKET_INVALID,
            reason_codes=["PACKET_NOT_FOUND_AND_COLLECT_DISABLED"],
        )

    ok, reason = _packet_exact_session_ok(packet, resolved_session)
    if not ok:
        return finish(
            disposition=DISPOSITION_PACKET_INVALID,
            reason_codes=[reason],
            packet=packet,
            packet_path_used=packet_source,
            collector_called=collector_invoked,
        )

    phase_b = evaluate_completed_market_session_gate(
        requested_at=instant,
        requested_session=resolved_session,
        timezone_name=str(config.get("operating_timezone") or OPERATING_TIMEZONE),
        safety_floor=safety_floor,
        working_dates_evidence=working_dates_evidence or {"workingDates": list(gate.get("working_dates") or [])},
        exact_session_evidence=packet,
        allow_provider_probe=False,
    )
    gate = dict(gate)
    gate["completion_gate_status"] = phase_b.get("completion_gate_status")
    gate["ready_semantic"] = phase_b.get("ready_semantic")
    gate["phase_b_identity"] = phase_b.get("gate_identity")
    if phase_b.get("completion_gate_status") != STATUS_READY:
        return finish(
            disposition=DISPOSITION_BLOCKED_POST_ACQUISITION,
            reason_codes=list(phase_b.get("reason_codes") or ["EXACT_SESSION_EVIDENCE_INSUFFICIENT"]),
            packet=packet,
            packet_path_used=packet_source,
            collector_called=collector_invoked,
        )

    materialization_invoked = True
    try:
        materialization = materialize_fn(
            session_date=resolved_session,
            packet_path=packet_source if packet_source and Path(packet_source).is_file() else None,
            raw_packet_dict=None if packet_source and Path(packet_source).is_file() else packet,
            out_dir=output_root,
            allow_collect=False,
            reference_at=f"{resolved_session}T18:00:00+07:00",
        )
    except Exception as exc:
        return finish(
            disposition=DISPOSITION_MATERIALIZATION_FAILED,
            reason_codes=["MATERIALIZER_EXCEPTION", type(exc).__name__],
            packet=packet,
            packet_path_used=packet_source,
            collector_called=collector_invoked,
            materialization_called=True,
        )
    if not isinstance(materialization, Mapping) or materialization.get("disposition") != "MATERIALIZATION_SUCCESS":
        return finish(
            disposition=DISPOSITION_MATERIALIZATION_FAILED,
            reason_codes=["MATERIALIZATION_NOT_SUCCESS", str((materialization or {}).get("disposition"))],
            packet=packet,
            packet_path_used=packet_source,
            materialization=materialization if isinstance(materialization, Mapping) else None,
            collector_called=collector_invoked,
            materialization_called=True,
        )
    run_directory = materialization.get("run_directory")
    if run_directory:
        run_path = Path(run_directory)
        if not run_path.is_absolute():
            run_path = repo_root / run_path
        validate_completed_bundle(
            run_path,
            expected_materialization_identity=str(materialization.get("materialization_identity")),
        )
    return finish(
        disposition=DISPOSITION_COMPLETED,
        reason_codes=["OPERATION_COMPLETED"],
        packet=packet,
        packet_path_used=packet_source,
        materialization=materialization,
        is_idempotent_replay=bool(materialization.get("is_idempotent_replay")),
        collector_called=collector_invoked,
        materialization_called=materialization_invoked,
    )


def parse_cli_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-shot foreground capability-first EOD operation (scheduler-safe; no OS job installed).",
    )
    parser.add_argument("--requested-at", default=None, help="ISO-8601 evaluation instant. Defaults to now in Asia/Ho_Chi_Minh.")
    parser.add_argument("--session", default=None, help="Optional explicit session YYYY-MM-DD.")
    parser.add_argument("--out-dir", default=None, help="Operation and materialization output root.")
    parser.add_argument("--packet-path", default=None, help="Existing retained session_packet.json.")
    parser.add_argument("--working-dates-path", default=None, help="Retained DNSE working_dates JSON.")
    parser.add_argument("--exact-session-evidence-path", default=None, help="Retained P3F9B scaleout artifact or EOD packet.")
    parser.add_argument("--config", default=None, help="Portable schedule contract JSON.")
    parser.add_argument("--offline", action="store_true", help="Never probe DNSE; require injected/retained working_dates.")
    parser.add_argument("--allow-provider-probe", action="store_true", help="Permit exactly one working_dates GET.")
    parser.add_argument("--replay-only", action="store_true", help="Collector replay from retained raw payloads.")
    parser.add_argument("--no-collect", action="store_true", help="Do not invoke the collector if no packet exists.")
    parser.add_argument("--universe", default=None)
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--max-requests", type=int, default=50)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_cli_args(argv)
    probe = bool(args.allow_provider_probe) and not args.offline
    if not args.offline and args.working_dates_path is None and not args.allow_provider_probe:
        # Operator default: one working_dates probe when evidence is not supplied.
        probe = True
    try:
        record = run_capability_first_eod_operation(
            requested_at=args.requested_at,
            session=args.session,
            out_dir=args.out_dir,
            packet_path=args.packet_path,
            working_dates_evidence=load_json_mapping(args.working_dates_path) if args.working_dates_path else None,
            exact_session_evidence=load_json_mapping(args.exact_session_evidence_path) if args.exact_session_evidence_path else None,
            working_dates_fetcher=_working_dates_probe if probe else None,
            allow_provider_probe=probe,
            allow_collect=not args.no_collect,
            replay_only=args.replay_only,
            collect_kwargs={
                "universe": args.universe,
                "symbols": args.symbols,
                "max_requests": args.max_requests,
            },
            config_path=args.config,
        )
    except (CompletedSessionGateError, EodOperationError) as exc:
        print(f"STATUS: REFUSE_CAPABILITY_FIRST_EOD_OPERATION")
        print(f"REASON: {exc}")
        return 2
    print(_compact_handoff(record))
    if record.get("final_disposition") == DISPOSITION_COMPLETED:
        return 0
    if record.get("final_disposition") == DISPOSITION_BLOCKED_BEFORE_COLLECTION:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
