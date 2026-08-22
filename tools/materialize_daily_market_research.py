"""Daily market research materialization operator for capability-first EOD session packets.

PIPELINE
    retained EOD market-evidence session packet (session_packet.json)
    -> canonical integration (canonical_market_evidence_integration.py)
    -> per-use usability projection
    -> MARKET_WIDE_DETERMINISTIC_RESEARCH_ARTIFACT (market_analysis_artifact.py)
    -> retained run manifest (run_manifest.json)

GOVERNANCE & INVARIANT DISCIPLINE
    1. Operates only on completed market sessions. Exact session date is mandatory.
    2. Consumes already-retained EOD session packets by default; never fetches live data
       unless explicitly authorized via --collect / allow_collect=True.
    3. Strict session gating: requested_session == packet.session_date == admitted observations.
       Wrong-session, future, or stale packets fail closed immediately.
    4. Atomic writing & validation: files are written via atomic_io and validated before promotion.
    5. Authority boundaries remain strictly NONE:
       - RAW_AS_TRADED = NOT_PROMOTED
       - pit_backtest_eligible = False
       - liquidity_sizing_authority = BLOCKED
       - valuation_authority = False
       - recommendation_authority = False
       - database_mutated = False
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping, Sequence

# Ensure repository root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atomic_io import atomic_write_json, validate_json_file
import canonical_market_evidence_integration as canonical_integration_module
from field_temporal_contract import canonical_json, stable_id
import market_analysis_artifact as research_consumer
import market_capability_taxonomy as taxonomy
from tools import collect_market_evidence as collector_module

RUN_SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "daily_market_research_materialization/v1"
REQUIRED_BUNDLE_FILES = (
    "canonical_integration.json",
    "market_research_artifact.json",
    "run_manifest.json",
    "completion_record.json",
)

AUTHORITY_BOUNDARIES = {
    "authority_effect": "NONE",
    "raw_as_traded_promoted": False,
    "pit_backtest_eligible": False,
    "liquidity_sizing_authority": "BLOCKED",
    "valuation_authority": False,
    "recommendation_authority": False,
    "database_mutated": False,
}


class MaterializationError(RuntimeError):
    """Raised when daily market research materialization encounters a contract violation."""


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of file bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _format_rel_path(target: Path, base: Path = ROOT) -> str:
    """Format path relative to repository root if possible, or as normalized path string."""
    try:
        return str(target.resolve().relative_to(base.resolve())).replace("\\", "/")
    except ValueError:
        return str(target.resolve()).replace("\\", "/")


def find_retained_session_packet(session_date: str, candidate_dir: Path | str | None = None) -> Path | None:
    """Search approved repository locations for an existing retained session packet."""
    candidates: list[Path] = []
    if candidate_dir:
        candidates.append(Path(candidate_dir) / "session_packet.json")
        candidates.append(Path(candidate_dir))

    # Standard repository locations
    candidates.extend([
        ROOT / "operations-review" / f"capability-first-eod-{session_date}" / "session_packet.json",
        ROOT / "operations-review" / f"daily-market-evidence-{session_date}" / "session_packet.json",
        ROOT / "operations-review" / "evidence" / f"session_packet_{session_date}.json",
        ROOT / "data" / "retained-eod" / session_date / "session_packet.json",
    ])

    for c in candidates:
        if c.is_file():
            return c
    return None


def _bundle_root(out_dir: Path | str | None, session_date: str) -> Path:
    """Return the parent containing immutable runs for one requested session."""
    base = Path(out_dir).resolve() if out_dir else ROOT / "operations-review"
    return base / f"daily-market-research-{session_date}"


def _manifest_content_payload(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return the non-recursive, clock-independent manifest identity payload."""
    return {
        key: value
        for key, value in manifest.items()
        if key not in {"run_timestamp", "manifest_content_identity", "manifest_identity"}
    }


def _completion_content_payload(completion: Mapping[str, Any]) -> dict[str, Any]:
    """Return the non-recursive completion-record identity payload."""
    return {
        key: value
        for key, value in completion.items()
        if key not in {"completion_content_identity", "completion_identity"}
    }


def _materialization_digest(
    *,
    session_date: str,
    source_packet_content_sha256: str,
    source_packet_sha256: str,
    source_packet_identity: str,
    canonical_integration_identity: str,
    research_artifact_content_hash: str,
    permitted_use: str,
    reference_at: Any,
) -> str:
    """Hash only deterministic identity-bearing inputs for immutable run addressing."""
    return stable_id({
        "contract_version": CONTRACT_VERSION,
        "session_date": session_date,
        "source_packet_content_sha256": source_packet_content_sha256,
        "source_packet_sha256": source_packet_sha256,
        "source_packet_identity": source_packet_identity,
        "canonical_integration_identity": canonical_integration_identity,
        "research_artifact_content_hash": research_artifact_content_hash,
        "permitted_use": permitted_use,
        "reference_at": str(reference_at),
    })


def validate_completed_bundle(
    run_dir: Path | str,
    *,
    expected_materialization_identity: str | None = None,
) -> dict[str, Any]:
    """Validate a complete immutable bundle, including the external manifest hash inventory."""
    resolved_run_dir = Path(run_dir)
    if not resolved_run_dir.is_dir():
        raise MaterializationError(f"completed_bundle_directory_missing:{resolved_run_dir}")
    for filename in REQUIRED_BUNDLE_FILES:
        file_path = resolved_run_dir / filename
        if not file_path.is_file():
            raise MaterializationError(f"completed_bundle_file_missing:{filename}")
        validate_json_file(file_path)

    manifest = json.loads((resolved_run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    completion = json.loads((resolved_run_dir / "completion_record.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(completion, dict):
        raise MaterializationError("completed_bundle_metadata_malformed")
    materialization_identity = str(manifest.get("materialization_identity", ""))
    if expected_materialization_identity and materialization_identity != expected_materialization_identity:
        raise MaterializationError("completed_bundle_identity_mismatch")
    if manifest.get("manifest_content_identity") != stable_id(_manifest_content_payload(manifest)):
        raise MaterializationError("manifest_content_identity_mismatch")
    if completion.get("completion_content_identity") != stable_id(_completion_content_payload(completion)):
        raise MaterializationError("completion_content_identity_mismatch")
    if completion.get("materialization_identity") != materialization_identity:
        raise MaterializationError("completion_manifest_identity_mismatch")
    if completion.get("manifest_content_identity") != manifest.get("manifest_content_identity"):
        raise MaterializationError("completion_manifest_content_identity_mismatch")

    inventory = completion.get("file_inventory")
    if not isinstance(inventory, Mapping):
        raise MaterializationError("completion_inventory_missing")
    for filename in REQUIRED_BUNDLE_FILES[:-1]:
        record = inventory.get(filename)
        file_path = resolved_run_dir / filename
        if not isinstance(record, Mapping):
            raise MaterializationError(f"completion_inventory_record_missing:{filename}")
        if record.get("sha256") != _sha256_file(file_path):
            raise MaterializationError(f"completion_inventory_hash_mismatch:{filename}")
        if record.get("size_bytes") != file_path.stat().st_size:
            raise MaterializationError(f"completion_inventory_size_mismatch:{filename}")

    output_files = manifest.get("output_files")
    if not isinstance(output_files, Mapping):
        raise MaterializationError("manifest_output_inventory_missing")
    for filename in ("canonical_integration.json", "market_research_artifact.json"):
        record = output_files.get(filename)
        if not isinstance(record, Mapping) or record.get("sha256") != _sha256_file(resolved_run_dir / filename):
            raise MaterializationError(f"manifest_output_hash_mismatch:{filename}")
    integration = json.loads((resolved_run_dir / "canonical_integration.json").read_text(encoding="utf-8"))
    artifact = json.loads((resolved_run_dir / "market_research_artifact.json").read_text(encoding="utf-8"))
    if manifest.get("canonical_integration_sha256") != integration.get("integration_sha256"):
        raise MaterializationError("canonical_integration_identity_mismatch")
    if manifest.get("research_artifact_content_hash") != artifact.get("content_hash"):
        raise MaterializationError("research_artifact_identity_mismatch")
    return manifest


def materialize_daily_market_research(
    *,
    session_date: str,
    packet_path: Path | str | None = None,
    out_dir: Path | str | None = None,
    allow_collect: bool = False,
    collect_kwargs: Mapping[str, Any] | None = None,
    permitted_use: str = canonical_integration_module.USE_WITHIN_SERIES_ANALYTICS,
    raw_packet_dict: Mapping[str, Any] | None = None,
    reference_at: Any = None,
) -> dict[str, Any]:
    """Execute the daily market research materialization pipeline for a completed session.

    Parameters
    ----------
    session_date : str
        The exact target market session date (YYYY-MM-DD).
    packet_path : Path | str | None
        Path to an existing retained session_packet.json.
    out_dir : Path | str | None
        Destination directory for retained materialization outputs.
    allow_collect : bool
        If True and no packet is found, allows invoking the EOD evidence collector.
    collect_kwargs : Mapping[str, Any] | None
        Additional keyword arguments for collector invocation.
    permitted_use : str
        The downstream research use case to apply.
    raw_packet_dict : Mapping[str, Any] | None
        In-memory packet dictionary for direct/testing execution.
    reference_at : Any
        Optional reference timestamp.

    Returns
    -------
    dict[str, Any]
        Complete machine-readable run manifest.
    """
    clean_session = str(session_date).strip()
    if not clean_session or len(clean_session) != 10 or clean_session[4] != "-" or clean_session[7] != "-":
        raise MaterializationError(f"invalid_session_date_format:{session_date}")

    run_start_time = datetime.now(timezone.utc).isoformat()
    resolved_bundle_root = _bundle_root(out_dir, clean_session)

    # 1. Resolve or Acquire EOD Session Packet
    packet: dict[str, Any] | None = None
    packet_bytes: bytes | None = None
    packet_source_path: str = "IN_MEMORY_DICT" if raw_packet_dict else "UNRESOLVED"
    execution_mode = "RETAINED_PACKET_CONSUMPTION"

    if raw_packet_dict is not None:
        packet = dict(raw_packet_dict)
        packet_bytes = canonical_json(packet).encode("utf-8")
    elif packet_path:
        p_path = Path(packet_path).resolve()
        if not p_path.is_file():
            res = _build_fail_manifest(
                session_date=clean_session,
                run_start_time=run_start_time,
                disposition="PACKET_NOT_FOUND",
                reason=f"Specified packet file does not exist: {p_path}",
                execution_mode="RETAINED_PACKET_CONSUMPTION",
                source_packet_path=str(p_path),
            )
            return res
        try:
            packet_bytes = p_path.read_bytes()
            packet = json.loads(packet_bytes.decode("utf-8"))
            packet_source_path = str(p_path)
        except Exception as exc:
            return _build_fail_manifest(
                session_date=clean_session,
                run_start_time=run_start_time,
                disposition="MALFORMED_PACKET_JSON",
                reason=f"Failed to parse packet JSON at {p_path}: {exc}",
                execution_mode="RETAINED_PACKET_CONSUMPTION",
                source_packet_path=str(p_path),
            )
    else:
        found_path = find_retained_session_packet(clean_session)
        if found_path is not None:
            packet_bytes = found_path.read_bytes()
            packet = json.loads(packet_bytes.decode("utf-8"))
            packet_source_path = str(found_path)
        elif allow_collect:
            execution_mode = "MANUAL_COLLECTION_AND_MATERIALIZATION"
            c_kwargs = dict(collect_kwargs or {})
            c_kwargs.setdefault("session_date", clean_session)
            packet = collector_module.collect_market_evidence(**c_kwargs)
            packet_bytes = canonical_json(packet).encode("utf-8")
            packet_source_path = "MANUAL_COLLECTOR_EXECUTION"
        else:
            return _build_fail_manifest(
                session_date=clean_session,
                run_start_time=run_start_time,
                disposition="PACKET_NOT_FOUND",
                reason=f"No retained EOD session packet found for session {clean_session} and allow_collect=False.",
                execution_mode=execution_mode,
                source_packet_path=packet_source_path,
            )

    if not isinstance(packet, dict):
        return _build_fail_manifest(
            session_date=clean_session,
            run_start_time=run_start_time,
            disposition="MALFORMED_PACKET",
            reason="Loaded packet is not a valid JSON dictionary.",
            execution_mode=execution_mode,
            source_packet_path=packet_source_path,
        )

    # 2. Strict Session Date Gate
    packet_session = str(packet.get("session_date", "")).strip()
    if packet_session != clean_session:
        return _build_fail_manifest(
            session_date=clean_session,
            run_start_time=run_start_time,
            disposition="EXACT_SESSION_MISMATCH",
            reason=f"Requested session date '{clean_session}' does not match packet session date '{packet_session}'.",
            execution_mode=execution_mode,
            source_packet_path=packet_source_path,
            packet_identity=packet.get("packet_identity"),
            packet_sha256=packet.get("packet_sha256"),
        )

    packet_sha256 = packet.get("packet_sha256") or stable_id(packet)
    packet_identity = packet.get("packet_identity") or f"capability_first_eod_packet:{packet_sha256}"
    source_packet_content_sha256 = hashlib.sha256(packet_bytes or canonical_json(packet).encode("utf-8")).hexdigest()

    # 3. Canonical Integration Step
    canonical_integration = canonical_integration_module.integrate_session_packet(packet)
    integration_identity = canonical_integration.get("integration_identity")
    integration_sha256 = canonical_integration.get("integration_sha256")

    # 4. Research Artifact Construction Step
    session_ref_time = reference_at or f"{clean_session}T18:00:00+07:00"
    research_artifact = research_consumer.build_market_research_artifact(
        canonical_integration=canonical_integration,
        as_of_session=clean_session,
        permitted_use=permitted_use,
        reference_at=session_ref_time,
    )

    artifact_id = research_artifact.get("artifact_id")
    artifact_hash = research_artifact.get("content_hash")
    artifact_status = research_artifact.get("status", "SUCCESS")

    # 5. Extract Diagnostic Statistics
    counts_by_status = canonical_integration.get("counts_by_status", {})
    counts_by_usability = canonical_integration.get("counts_by_usability", {})
    counts_by_family = canonical_integration.get("counts_by_family", {})
    counts_by_source = canonical_integration.get("counts_by_source", {})

    sources_represented = sorted(counts_by_source.keys())
    capabilities_represented = sorted(counts_by_family.keys())

    missing_count = counts_by_status.get("MISSING_REQUESTED_SESSION", 0) + counts_by_status.get("UNAVAILABLE_PROVIDER_NATIVE_FIELDS", 0)
    rate_limited_count = counts_by_status.get("PROVIDER_RATE_LIMITED", 0)
    budget_exhausted_count = counts_by_status.get("BUDGET_EXHAUSTED", 0)
    conflicting_count = sum(
        1 for o in canonical_integration.get("observations", [])
        if str(o.get("conflict_state", "CLEAN")) not in ("CLEAN", "NONE")
    ) or counts_by_usability.get(taxonomy.CONFLICTING, 0)

    # 6. Address the immutable run using only deterministic identity-bearing inputs.
    materialization_digest = _materialization_digest(
        session_date=clean_session,
        source_packet_content_sha256=source_packet_content_sha256,
        source_packet_sha256=str(packet_sha256),
        source_packet_identity=str(packet_identity),
        canonical_integration_identity=str(integration_identity),
        research_artifact_content_hash=str(artifact_hash),
        permitted_use=permitted_use,
        reference_at=session_ref_time,
    )
    materialization_identity = f"daily_market_research_run:{materialization_digest}"
    final_run_dir = resolved_bundle_root / f"run-{materialization_digest}"

    # 7. An existing complete matching identity is immutable and safely reusable.
    if final_run_dir.exists():
        prior_manifest = validate_completed_bundle(
            final_run_dir,
            expected_materialization_identity=materialization_identity,
        )
        replay_manifest = dict(prior_manifest)
        replay_manifest["is_idempotent_replay"] = True
        return replay_manifest

    # 8. Build all output in one staging directory. It remains non-authoritative until the
    # complete bundle validates and the directory is atomically renamed into final_run_dir.
    resolved_bundle_root.mkdir(parents=True, exist_ok=True)
    staging_run_dir = Path(tempfile.mkdtemp(
        prefix=f".{materialization_digest}.staging-",
        dir=resolved_bundle_root,
    ))
    integration_target_path = staging_run_dir / "canonical_integration.json"
    artifact_target_path = staging_run_dir / "market_research_artifact.json"
    manifest_target_path = staging_run_dir / "run_manifest.json"
    completion_target_path = staging_run_dir / "completion_record.json"

    # Write and individually validate component JSON only inside the staging directory.
    atomic_write_json(integration_target_path, canonical_integration, validator=validate_json_file)
    atomic_write_json(artifact_target_path, research_artifact, validator=validate_json_file)

    output_files = {
        "canonical_integration.json": {
            "path": "canonical_integration.json",
            "size_bytes": integration_target_path.stat().st_size,
            "sha256": _sha256_file(integration_target_path),
        },
        "market_research_artifact.json": {
            "path": "market_research_artifact.json",
            "size_bytes": artifact_target_path.stat().st_size,
            "sha256": _sha256_file(artifact_target_path),
        },
    }

    # 9. Manifest identity is deliberately content-only: it excludes its own identity and clock.
    manifest: dict[str, Any] = {
        "run_schema_version": RUN_SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "requested_session_date": clean_session,
        "run_timestamp": run_start_time,
        "execution_mode": execution_mode,
        "permitted_use_applied": permitted_use,
        "source_packet_path": packet_source_path,
        "source_packet_identity": packet_identity,
        "source_packet_sha256": packet_sha256,
        "source_packet_content_sha256": source_packet_content_sha256,
        "canonical_integration_identity": integration_identity,
        "canonical_integration_sha256": integration_sha256,
        "research_artifact_identity": artifact_id,
        "research_artifact_content_hash": artifact_hash,
        "artifact_status": artifact_status,
        "total_canonical_observations": canonical_integration.get("total_canonical_observations", 0),
        "total_candidates_processed": research_artifact.get("total_candidates_processed", 0),
        "records_emitted": research_artifact.get("records_emitted", 0),
        "counts_by_observation_status": counts_by_status,
        "counts_by_usability_state": counts_by_usability,
        "counts_by_family": counts_by_family,
        "counts_by_source": counts_by_source,
        "sources_represented": sources_represented,
        "capabilities_represented": capabilities_represented,
        "missing_observations_count": missing_count,
        "rate_limited_observations_count": rate_limited_count,
        "budget_exhausted_observations_count": budget_exhausted_count,
        "conflicting_observations_count": conflicting_count,
        "authority_boundaries": dict(AUTHORITY_BOUNDARIES),
        "materialization_identity": materialization_identity,
        "materialization_digest": materialization_digest,
        "run_directory": _format_rel_path(final_run_dir),
        "output_files": output_files,
        "disposition": "MATERIALIZATION_SUCCESS",
        "is_idempotent_replay": False,
    }
    manifest_content_identity = stable_id(_manifest_content_payload(manifest))
    manifest["manifest_content_identity"] = manifest_content_identity
    manifest["manifest_identity"] = f"daily_market_research_manifest:{manifest_content_identity}"
    atomic_write_json(manifest_target_path, manifest, validator=validate_json_file)

    # The completion record is external to run_manifest.json, so it can truthfully inventory
    # the full manifest bytes without a recursive in-file self-hash claim.
    completion: dict[str, Any] = {
        "run_schema_version": RUN_SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "materialization_identity": materialization_identity,
        "manifest_content_identity": manifest_content_identity,
        "file_inventory": {
            filename: {
                "size_bytes": (staging_run_dir / filename).stat().st_size,
                "sha256": _sha256_file(staging_run_dir / filename),
            }
            for filename in REQUIRED_BUNDLE_FILES[:-1]
        },
    }
    completion_content_identity = stable_id(_completion_content_payload(completion))
    completion["completion_content_identity"] = completion_content_identity
    completion["completion_identity"] = f"daily_market_research_completion:{completion_content_identity}"
    atomic_write_json(completion_target_path, completion, validator=validate_json_file)

    validate_completed_bundle(staging_run_dir, expected_materialization_identity=materialization_identity)
    os.replace(staging_run_dir, final_run_dir)
    promoted_manifest = validate_completed_bundle(final_run_dir, expected_materialization_identity=materialization_identity)
    return promoted_manifest


def _build_fail_manifest(
    *,
    session_date: str,
    run_start_time: str,
    disposition: str,
    reason: str,
    execution_mode: str,
    source_packet_path: str,
    packet_identity: str | None = None,
    packet_sha256: str | None = None,
) -> dict[str, Any]:
    """Construct a fail-closed run manifest record for failed materialization."""
    manifest = {
        "run_schema_version": RUN_SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "requested_session_date": session_date,
        "run_timestamp": run_start_time,
        "execution_mode": execution_mode,
        "source_packet_path": source_packet_path,
        "source_packet_identity": packet_identity,
        "source_packet_sha256": packet_sha256,
        "canonical_integration_identity": None,
        "canonical_integration_sha256": None,
        "research_artifact_identity": None,
        "research_artifact_content_hash": None,
        "authority_boundaries": dict(AUTHORITY_BOUNDARIES),
        "disposition": disposition,
        "error_reason": reason,
        "is_actionable": False,
        "authority_effect": "NONE",
    }
    deterministic_payload = {k: v for k, v in manifest.items() if k != "run_timestamp"}
    digest = stable_id(deterministic_payload)
    manifest["manifest_sha256"] = digest
    manifest["manifest_identity"] = f"daily_market_research_manifest:{digest}"
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Materialize deterministic daily market research artifact from retained capability-first EOD session packets."
    )
    parser.add_argument("--date", "-d", required=True, help="Completed market session date (YYYY-MM-DD).")
    parser.add_argument("--packet-path", "-p", help="Explicit path to source session_packet.json.")
    parser.add_argument("--out-dir", "-o", help="Custom output directory for materialized artifacts.")
    parser.add_argument(
        "--allow-collect",
        action="store_true",
        help="Allow running the EOD collector if no retained session packet exists. Default: False (consume existing only).",
    )
    parser.add_argument(
        "--permitted-use",
        default=canonical_integration_module.USE_WITHIN_SERIES_ANALYTICS,
        help=f"Permitted downstream use case. Default: {canonical_integration_module.USE_WITHIN_SERIES_ANALYTICS}",
    )
    args = parser.parse_args(argv)

    try:
        manifest = materialize_daily_market_research(
            session_date=args.date,
            packet_path=args.packet_path,
            out_dir=args.out_dir,
            allow_collect=args.allow_collect,
            permitted_use=args.permitted_use,
        )
        print(json.dumps(manifest, indent=2))
        return 0 if manifest.get("disposition") == "MATERIALIZATION_SUCCESS" else 1
    except Exception as exc:
        print(f"ERROR: Daily market research materialization failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
