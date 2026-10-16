"""Immutable prospective T0 snapshots for canonical Integrated Decisions.

The canonical post-close bundle is a useful handoff index, but its historical
``integrated_investment_decision_product`` path is a session-shaped working
path.  It is not itself an immutable T0 container.  This module seals the
already-produced decision record at T0 under a content-addressed path, binds it
to the completed Daily operation, and leaves every later outcome observation in
a separate downstream artifact.

It serializes conditions already emitted by tactical watchlist boundaries or
the verified structural product projection. It neither creates a
second strategy engine nor turns a research boundary into an execution order.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from retained_evidence_catalog import historical_paths, original_path
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


CONTRACT_VERSION = "prospective_decision_snapshot/v1"
CONDITION_CONTRACT_VERSION = "retained_strategy_boundary_condition/v1"
HEALTH_CONTRACT_VERSION = "prospective_decision_corpus_health/v2"
LINEAGE_READER_VERSION = "prospective_t0_origination_lineage/v2"
SNAPSHOT_PREFIX = "prospective_decision_snapshot:"
RECORD_PREFIX = "prospective_decision_snapshot_record:"

GENUINE = "GENUINE_PROSPECTIVE_DECISION"
EXCLUDED = "EXCLUDE_TEMPORAL_PROVENANCE_UNQUALIFIED"
FIELD_NOT_RETAINED = "FIELD_NOT_RETAINED_AT_T0"

REQUIRED_AXES = (
    "FUNDAMENTAL", "VALUATION", "TACTICAL_STRUCTURE", "MOMENTUM",
    "PARTICIPATION_CONFIRMATION", "MARKET_SECTOR", "OPPORTUNITY_PRIORITY",
)
_REQUIRED_AXIS_FIELDS = (
    "state", "fitness", "supporting_reason_codes", "contradicting_reason_codes",
    "blocker_reason_codes", "method", "lineage",
)


class ProspectiveDecisionRetentionError(ValueError):
    """Raised when a prospective snapshot cannot prove its retained lineage."""


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _json_bytes(value: Any, *, pretty: bool = False):
    """Bounded encoding batches; canonical bytes match the standing dumps contract.

    Pretty output preserves the old text writer's native newline translation.
    Canonical identity bytes always use the original compact UTF-8 representation.
    """
    records = value.get('records') if isinstance(value,dict) else None
    if (pretty and isinstance(records,(dict,list)) and all(isinstance(k,str) for k in value)
            and (not isinstance(records,dict) or all(isinstance(k,str) for k in records))):
        from bounded_artifact_stream import pretty_record_chunks
        yield from pretty_record_chunks(value)
        return
    encoder = (json.JSONEncoder(ensure_ascii=False, sort_keys=True, indent=2) if pretty else
               json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
    buffer = bytearray()
    for chunk in encoder.iterencode(value):
        data = (chunk.replace("\n", os.linesep) if pretty else chunk).encode("utf-8")
        if len(buffer) + len(data) > 64 * 1024:
            if buffer:
                yield bytes(buffer)
                buffer.clear()
            if len(data) > 64 * 1024:
                yield data
                continue
        buffer.extend(data)
    if pretty:
        buffer.extend(os.linesep.encode("utf-8"))
    if buffer:
        yield bytes(buffer)


def _hash(value: Any) -> str:
    if isinstance(value, dict):
        from bounded_artifact_stream import record_mapping_digest
        return record_mapping_digest(value)
    digest = hashlib.sha256()
    for block in _json_bytes(value):
        digest.update(block)
    return digest.hexdigest()


def _identity(payload: dict[str, Any], prefix: str, field: str) -> dict[str, Any]:
    payload[field] = prefix + _hash(payload)
    return payload


def _load(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(original_path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _condition_operator(operator: Any) -> str | None:
    return {
        "FUTURE_CLOSE_GT_RESISTANCE_LEVEL": ">",
        "FUTURE_CLOSE_LT_RESISTANCE_LEVEL": "<",
        "FUTURE_CLOSE_LT_SUPPORT_LEVEL": "<",
        "FUTURE_CLOSE_GT_STRUCTURAL_LEVEL": ">",
        "FUTURE_CLOSE_LT_STRUCTURAL_LEVEL": "<",
    }.get(operator)


def serialize_boundary_condition(
    boundary: Mapping[str, Any] | None, *, role: str, source_strategy_identity: str | None,
) -> dict[str, Any]:
    """Preserve existing boundary semantics without reducing a narrative rule to one.

    Only an existing ``READY`` close-vs-fixed-T0-level boundary is evaluable
    from the retained close-series contract.  Dynamic MA/momentum boundaries
    stay fully serialized, but explicitly require an already-retained future
    strategy measurement rather than a new evaluator here.
    """
    raw = dict(boundary or {})
    operator = _condition_operator(raw.get("comparison_operator"))
    level = raw.get("baseline_value")
    fixed_close = (
        raw.get("status") == "READY"
        and raw.get("source_metric") in {"support", "resistance", "trigger_level", "invalidation_level"}
        and operator is not None
        and isinstance(level, (int, float))
        and not isinstance(level, bool) and math.isfinite(level) and level > 0
    )
    if fixed_close:
        status = "MACHINE_EVALUABLE"
        reason_codes = ["EXISTING_READY_FIXED_T0_CLOSE_BOUNDARY"]
        reference_field = "close"
        activation = "FIRST_LATER_COMPLETED_SESSION_WITH_RETAINED_CLOSE_SATISFIES_FIXED_T0_BOUNDARY"
    elif raw:
        status = "NOT_MACHINE_EVALUABLE"
        reason_codes = [
            "EXISTING_BOUNDARY_NOT_REDUCED_TO_NEW_TRIGGER_ENGINE",
            "FUTURE_STRATEGY_MEASUREMENT_REQUIRED" if raw.get("status") == "READY" else "BOUNDARY_NOT_READY_OR_NARRATIVE",
        ]
        reference_field = raw.get("source_metric")
        activation = "SERIALIZED_EXISTING_STRATEGY_SEMANTICS_ONLY"
    else:
        status = "NOT_MACHINE_EVALUABLE"
        reason_codes = ["BOUNDARY_NOT_RETAINED_AT_T0"]
        reference_field = None
        activation = "NO_RETAINED_BOUNDARY"
    payload: dict[str, Any] = {
        "condition_version": CONDITION_CONTRACT_VERSION,
        "role": role,
        "status": status,
        "operator": operator,
        "strategy_operator": raw.get("comparison_operator"),
        "reference_field": reference_field,
        "reference_level": level if fixed_close else None,
        "required_state": raw.get("boundary_type"),
        "activation_semantics": activation,
        "source_strategy_identity": source_strategy_identity,
        "source_rule": raw.get("source_rule"),
        "source_metric": raw.get("source_metric"),
        "source_boundary_status": raw.get("status"),
        "source_boundary_type": raw.get("boundary_type"),
        "source_method": raw.get("method"),
        "source_lineage": raw.get("evidence_lineage") or {},
        "reason_codes": reason_codes + list(raw.get("warnings") or []),
        "narrative_reason": raw.get("reason"),
        "authority_boundary": "RETAINED_RESEARCH_BOUNDARY_NOT_EXECUTION_OR_STOP_LOSS",
    }
    return _identity(payload, "retained_strategy_boundary_condition:", "condition_identity")


def serialize_structural_condition(
    record: Mapping[str, Any], *, role: str, session: str,
    source_identity: str | None,
) -> dict[str, Any]:
    """Serialize the projected V3 measurement using the standing close evaluator.

    The producer projection owns direction. Never borrow a watchlist rule,
    infer direction from price distance, or reconstruct an old retained T0.
    """
    level = record.get(f"{role}_level")
    operator = record.get(f"{role}_close_comparison_operator")
    qualified = (
        record.get("eligible") is True and record.get("as_of_session") == session
        and bool(source_identity) and operator in {">", "<"}
        and isinstance(level, (int, float)) and not isinstance(level, bool)
        and math.isfinite(level) and level > 0
    )
    boundary = {
        "status": "READY" if qualified else "UNAVAILABLE",
        "source_metric": f"{role}_level",
        "comparison_operator": "FUTURE_CLOSE_GT_STRUCTURAL_LEVEL" if operator == ">" else "FUTURE_CLOSE_LT_STRUCTURAL_LEVEL" if operator == "<" else None,
        "baseline_value": level if qualified else None,
        "boundary_type": record.get("trigger_type") if role == "trigger" else record.get("invalidation_method"),
        "method": "market_structure_breakout_product_projection/v1",
        "evidence_lineage": {"as_of_session": record.get("as_of_session"), "source_artifact_identity": source_identity},
        "warnings": [] if qualified else ["STRUCTURAL_CONDITION_INPUT_UNQUALIFIED"],
        "reason": "Fixed T0 structural close boundary; analytical research only.",
    }
    return serialize_boundary_condition(boundary, role=role, source_strategy_identity=source_identity)


def _axis_completeness(record: Mapping[str, Any]) -> dict[str, Any]:
    axes = record.get("evidence_axes")
    if not isinstance(axes, Mapping):
        return {"status": FIELD_NOT_RETAINED, "missing_axes": list(REQUIRED_AXES), "complete": False}
    missing: list[str] = []
    incomplete: dict[str, list[str]] = {}
    for name in REQUIRED_AXES:
        axis = axes.get(name)
        if not isinstance(axis, Mapping):
            missing.append(name)
            continue
        absent = [field for field in _REQUIRED_AXIS_FIELDS if field not in axis]
        if absent:
            incomplete[name] = absent
    portfolio = axes.get("PORTFOLIO_FIT")
    if isinstance(portfolio, Mapping) and portfolio.get("state") not in {None, "NOT_PROVIDED"}:
        absent = [field for field in _REQUIRED_AXIS_FIELDS if field not in portfolio]
        if absent:
            incomplete["PORTFOLIO_FIT"] = absent
    # CORPORATE_INTELLIGENCE_CATALYST_EVENT_RISK_DECISION_INTEGRATION_V1: same treatment as
    # PORTFOLIO_FIT above, not REQUIRED_AXES -- NO_QUALIFIED_CORPORATE_EVENT is a legitimate,
    # common, non-blocking result (mission Section 18), never a completeness penalty. Only
    # genuinely absent (state NOT_PROVIDED, meaning the axis could not even be attempted this
    # session) or structurally malformed is tracked here.
    corporate_intelligence = axes.get("CORPORATE_INTELLIGENCE")
    if isinstance(corporate_intelligence, Mapping) and corporate_intelligence.get("state") not in {None, "NOT_PROVIDED"}:
        absent = [field for field in _REQUIRED_AXIS_FIELDS if field not in corporate_intelligence]
        if absent:
            incomplete["CORPORATE_INTELLIGENCE"] = absent
    return {
        "status": "COMPLETE" if not missing and not incomplete else "INCOMPLETE",
        "complete": not missing and not incomplete,
        "missing_axes": missing,
        "incomplete_axis_fields": incomplete,
        "portfolio_fit_retained": isinstance(portfolio, Mapping) and portfolio.get("state") != "NOT_PROVIDED",
        "corporate_intelligence_retained": isinstance(corporate_intelligence, Mapping) and corporate_intelligence.get("state") != "NOT_PROVIDED",
    }


def build_snapshot(
    *, session: str, operation_identity: str, producer_run_identity: str | None,
    integrated_artifact: Mapping[str, Any], exact_session_snapshot: Mapping[str, Any] | None = None,
    progress_callback=None,
) -> dict[str, Any]:
    """Create the immutable T0 payload from the current canonical decision artifact."""
    if integrated_artifact.get("contract_version") != "integrated_investment_decision_product/v1":
        raise ProspectiveDecisionRetentionError("INTEGRATED_DECISION_CONTRACT_INVALID")
    if integrated_artifact.get("session") != session:
        raise ProspectiveDecisionRetentionError("INTEGRATED_DECISION_SESSION_MISMATCH")
    artifact_identity = integrated_artifact.get("artifact_identity")
    if not isinstance(artifact_identity, str) or not artifact_identity:
        raise ProspectiveDecisionRetentionError("INTEGRATED_DECISION_IDENTITY_MISSING")
    if not isinstance(operation_identity, str) or not operation_identity:
        raise ProspectiveDecisionRetentionError("DAILY_OPERATION_IDENTITY_MISSING")
    records = integrated_artifact.get("records")
    if not isinstance(records, Mapping) or not records:
        raise ProspectiveDecisionRetentionError("INTEGRATED_DECISION_RECORDS_MISSING")
    from owner_daily_progress import safe_callback
    def report(status):
        safe_callback(progress_callback, {"component": "Canonical Daily", "subtask": "t0_records",
            "task_label": "Tạo bản ghi T0", "progress_kind": "RECORDS",
            "completed": len(retained), "total": len(records), "status": status})
    retained: dict[str, Any] = {}
    report("BEGIN")
    price_records = (exact_session_snapshot or {}).get("records") or {}
    for ticker, decision in sorted(records.items()):
        if not isinstance(decision, Mapping) or decision.get("ticker") != ticker or decision.get("as_of_session") != session:
            raise ProspectiveDecisionRetentionError("INTEGRATED_DECISION_RECORD_SESSION_OR_TICKER_MISMATCH:" + str(ticker))
        decision_identity = decision.get("decision_identity")
        if not isinstance(decision_identity, str) or not decision_identity:
            raise ProspectiveDecisionRetentionError("INTEGRATED_DECISION_RECORD_IDENTITY_MISSING:" + str(ticker))
        record: dict[str, Any] = {
            "ticker": ticker,
            "decision_session": session,
            "integrated_decision_identity": decision_identity,
            "canonical_operation_identity": operation_identity,
            "source_decision_artifact_identity": artifact_identity,
            "prospective_snapshot_contract_version": CONTRACT_VERSION,
            "t0_contract_versions": {
                "integrated_decision_contract": integrated_artifact.get("contract_version", FIELD_NOT_RETAINED),
                "research_action_policy_version": integrated_artifact.get("research_action_policy_version", FIELD_NOT_RETAINED),
                "fundamental_policy_version": decision.get("fundamental_decision_policy_version", FIELD_NOT_RETAINED),
            },
            "known_at": decision.get("known_at", FIELD_NOT_RETAINED),
            "evidence_axis_snapshot": _axis_completeness(decision),
            "trigger_condition": dict((decision.get("trigger") or {}).get("condition") or {
                "status": FIELD_NOT_RETAINED, "reason_codes": [FIELD_NOT_RETAINED],
            }),
            "invalidation_condition": dict((decision.get("invalidation") or {}).get("condition") or {
                "status": FIELD_NOT_RETAINED, "reason_codes": [FIELD_NOT_RETAINED],
            }),
            "t0_close_observation": next((dict(row) for row in ((price_records.get(ticker) or {}).get("observations") or [])
                                            if isinstance(row, Mapping) and row.get("session") == session), None),
            # This is the complete known-at-T0 Integrated Decision record.  It
            # includes posture, priority, why-now, coherence, all axes and the
            # source lineage; nothing is reconstructed by a later evaluator.
            "integrated_decision_at_t0": dict(decision),
        }
        retained[ticker] = _identity(record, RECORD_PREFIX, "prospective_snapshot_record_identity")
        if len(retained) % 64 == 0 or len(retained) == len(records):
            report("RUNNING")
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "session": session,
        "daily_session_operation_identity": operation_identity,
        "daily_producer_run_identity": producer_run_identity,
        "source_integrated_decision_artifact": {
            "contract_version": integrated_artifact.get("contract_version"),
            "artifact_identity": artifact_identity,
            "artifact_sha256": integrated_artifact.get("artifact_sha256"),
            "session": session,
        },
        "t0_price_snapshot": {
            "snapshot_identity": (exact_session_snapshot or {}).get("snapshot_identity"),
            "resolved_completed_session": (exact_session_snapshot or {}).get("resolved_completed_session"),
        },
        "decision_count": len(retained),
        "records": retained,
        "authority_boundary": {
            "immutable_t0_only": True,
            "future_market_observations_not_embedded": True,
            "no_policy_mutation": True,
            "no_recommendation_reconstruction": True,
            "no_execution_or_stop_loss": True,
        },
    }
    result = _identity(payload, SNAPSHOT_PREFIX, "snapshot_identity")
    report("END")
    return result


def snapshot_path(root: str | Path, snapshot: Mapping[str, Any]) -> Path:
    identity = str(snapshot.get("snapshot_identity") or "")
    digest = identity.removeprefix(SNAPSHOT_PREFIX)
    if len(digest) != 64:
        raise ProspectiveDecisionRetentionError("SNAPSHOT_IDENTITY_INVALID")
    return Path(root) / "operations-review" / "prospective-decision-retention-v1" / str(snapshot["session"]) / digest / "prospective_decision_snapshot.json"


def write_immutable_snapshot(root: str | Path, snapshot: Mapping[str, Any], *, on_written=None) -> Path:
    path = snapshot_path(root, snapshot)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        before = path.stat()
        existing, existing_size = hashlib.sha256(), 0
        with path.open('rb') as source:
            for block in iter(lambda: source.read(1024*1024), b''):
                existing.update(block); existing_size += len(block)
        expected, size = hashlib.sha256(), 0
        for block in _json_bytes(snapshot, pretty=True):
            expected.update(block); size += len(block)
        after = path.stat()
        if ((before.st_size,before.st_mtime_ns) != (after.st_size,after.st_mtime_ns)
                or existing_size != size or existing.digest() != expected.digest()):
            raise ProspectiveDecisionRetentionError('IMMUTABLE_PROSPECTIVE_SNAPSHOT_CONFLICT:'+str(path))
        if on_written: on_written(path, existing.hexdigest())
        return path
    temporary = None
    try:
        digest, size = hashlib.sha256(), 0
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".snapshot-", suffix=".tmp", delete=False) as out:
            temporary = Path(out.name)
            for block in _json_bytes(snapshot, pretty=True):
                out.write(block)
                digest.update(block)
                size += len(block)
            out.flush()
            os.fsync(out.fileno())
        if path.exists():
            before = path.stat()
            existing, existing_size = hashlib.sha256(), 0
            with path.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    existing.update(block)
                    existing_size += len(block)
            after = path.stat()
            if ((before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
                    or existing_size != size or existing.digest() != digest.digest()):
                raise ProspectiveDecisionRetentionError("IMMUTABLE_PROSPECTIVE_SNAPSHOT_CONFLICT:" + str(path))
            if on_written: on_written(path, digest.hexdigest())
            return path
        os.replace(temporary, path)
        if on_written: on_written(path, digest.hexdigest())
        return path
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def validate_snapshot(snapshot: Mapping[str, Any]) -> bool:
    body = dict(snapshot)
    identity = body.pop("snapshot_identity", None)
    if identity != SNAPSHOT_PREFIX + _hash(body):
        return False
    if snapshot.get("contract_version") != CONTRACT_VERSION:
        return False
    for ticker, row in (snapshot.get("records") or {}).items():
        if not isinstance(row, Mapping) or row.get("ticker") != ticker:
            return False
        record = dict(row)
        record_identity = record.pop("prospective_snapshot_record_identity", None)
        if record_identity != RECORD_PREFIX + _hash(record):
            return False
    return True


def _operation_manifests(root: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    base = root / "operations-review" / "daily-research-session-operations-v1"
    for path in historical_paths(root, "operations-review/daily-research-session-operations-v1", "*/*/run_manifest.json"):
        manifest = _load(path)
        identity = (manifest or {}).get("operation_identity")
        if isinstance(identity, str) and identity:
            rows[identity] = {"path": _relative(root, path), "manifest": manifest}
    return rows


def _handoff_by_snapshot(root: Path) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    base = root / "operations-review" / "canonical-post-close-v1"
    for path in historical_paths(root, "operations-review/canonical-post-close-v1", "*/session_handoff_bundle.json"):
        bundle = _load(path)
        snapshot = (bundle or {}).get("prospective_decision_snapshot") or {}
        identity = snapshot.get("identity") if isinstance(snapshot, Mapping) else None
        if isinstance(identity, str) and identity:
            result.setdefault(identity, []).append({"path": _relative(root, path), "bundle": bundle})
    return result


def _verified_origination_operation(root, operation, *, identity, session, decision):
    """Verify the existing operation hash domain; never infer provenance from a date."""
    from stocklookup_core.evidence.field_identity import stable_id

    if not isinstance(operation, Mapping):
        return False
    manifest = operation["manifest"]
    body = {k: v for k, v in manifest.items() if k != "operation_identity"}
    try:
        expected = "daily_research_session_operation:" + stable_id(body)
        path = root / "operations-review/daily-research-session-operations-v1" / session / expected.split(":")[1] / "run_manifest.json"
    except (TypeError, ValueError):
        return False
    return bool(identity == expected == manifest.get("operation_identity") and
                (root / operation["path"]).resolve() == path.resolve() and
                manifest.get("contract_version") == "daily_research_session_operation/v1" and
                manifest.get("market_session") == session and
                manifest.get("generation_context") == "DAILY_PRODUCER_RETAINED_COMPLETED_SESSION" and
                (manifest.get("outputs") or {}).get("integrated_investment_decision_product") == decision)


def _original_reuse_reasons(root, path, snapshot, handoff, operations):
    """Two independent operation proofs joined only by the verified original seal.

    Called only for explicit reuse/mismatches. Existing same-operation admission is
    unchanged. No publication, cache writes, current-view reconstruction or prices.
    """
    bundle = handoff["bundle"]
    bound = bundle.get("prospective_decision_snapshot") or {}
    session = snapshot.get("session")
    identity = snapshot.get("snapshot_identity")
    source = snapshot.get("source_integrated_decision_artifact") or {}
    original = snapshot.get("daily_session_operation_identity")
    later = bundle.get("daily_session_operation_identity")
    decision = source.get("artifact_identity")
    later_decision = bundle.get("integrated_investment_decision_product_identity")
    reasons = []
    if bound.get("retention") != "ORIGINAL_SESSION_T0_REUSED" or bound.get("status") != "RETAINED":
        reasons.append("ORIGINAL_T0_REUSE_NOT_PROVEN")
    if bound.get("identity") != identity or bundle.get("session") != session:
        reasons.append("ORIGINAL_T0_REUSE_SCOPE_MISMATCH")
    for value in (decision, later_decision):
        prefix = "integrated_investment_decision_product/v1:"
        suffix = value.removeprefix(prefix) if isinstance(value, str) else ""
        if not isinstance(value, str) or not value.startswith(prefix) or len(suffix) != 64 or any(c not in "0123456789abcdef" for c in suffix):
            reasons.append("REUSE_DECISION_SOURCE_IDENTITY_INVALID")
    if source.get("session") != session or source.get("contract_version") != "integrated_investment_decision_product/v1" or source.get("artifact_sha256") != str(decision).split(":")[-1]:
        reasons.append("ORIGINAL_T0_SOURCE_BINDING_INVALID")
    if not _verified_origination_operation(root, operations.get(original), identity=original, session=session, decision=decision):
        reasons.append("ORIGINAL_T0_OPERATION_PROOF_INVALID")
    if not _verified_origination_operation(root, operations.get(later), identity=later, session=session, decision=later_decision):
        reasons.append("REUSE_HANDOFF_OPERATION_PROOF_INVALID")
    if bound.get("source_integrated_decision_artifact_identity") != decision:
        reasons.append("REUSE_HANDOFF_ORIGINAL_SOURCE_MISMATCH")
    if not isinstance(bound.get("path"), str) or original_path(root / bound["path"], root=root).resolve() != path.resolve():
        reasons.append("REUSE_HANDOFF_SNAPSHOT_PATH_MISMATCH")
    if reasons:
        return sorted(set(reasons))
    try:
        import prospective_market_snapshot_contract as market

        ref = dict(bound.get("seal_index") or {})
        from retained_evidence_catalog import t0_reference
        ref = t0_reference(root, path, ref)
        ref_path = root / ref["path"]
        if ref.get("status") != "RETAINED" or ref_path.resolve() != (path.parent / "prospective_t0_seal_index.json").resolve():
            raise ValueError("SEAL_PATH_OR_STATUS")
        receipt_path = path.parent / "prospective_t0_snapshot_write_receipt.json"
        if ref_path.stat().st_size > 8 * 1024 * 1024 or receipt_path.stat().st_size > 64 * 1024:
            raise ValueError("SEAL_SIZE_LIMIT")
        index, receipt = _load(ref_path), _load(receipt_path)
        # Consume the existing seal interface's exact content-identity domains.
        # No import of its orchestration/technical dispatch closure is needed to
        # prove origination, and no technical-context authority is granted here.
        for value, kind in ((index, "prospective_t0_seal_index"), (receipt, "prospective_t0_snapshot_write_receipt")):
            if value.get("contract_version") != kind + "/v1" or any(value.get(k) != v for k, v in market.content_identity(value, kind=kind).items()):
                raise ValueError("SEAL_CONTENT_IDENTITY")
        stat = path.stat()
        fingerprint = {"bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns, "ctime_ns": stat.st_ctime_ns,
                       "device": stat.st_dev, "inode": stat.st_ino}
        fingerprint_valid = receipt.get("snapshot_fingerprint") == fingerprint
        if ref.get("storage_location"):
            from retained_evidence_catalog import t0_location_valid
            fingerprint_valid = t0_location_valid(ref, ref_path, index, receipt)
        if (ref.get("artifact_identity") != index["artifact_identity"] or
            ref.get("write_receipt_identity") != receipt["artifact_identity"] or
            index.get("snapshot_identity") != identity or receipt.get("snapshot_identity") != identity or
            index.get("session") != session or receipt.get("session") != session or
            index.get("snapshot_file") != path.name or not fingerprint_valid or
            receipt.get("index_identity") != index["artifact_identity"] or receipt.get("index_sha256") != index["artifact_sha256"] or
            receipt.get("snapshot_file_sha256") != index.get("snapshot_file_sha256") or
            index.get("operation_identity") != original or index.get("source_integrated_decision_artifact") != source or
            index.get("evaluation_scope") != "ORIGINAL_T0_VERIFIED_PROJECTION" or
            index.get("authority_status") != "SNAPSHOT_DERIVED_INDEX_ONLY" or
            receipt.get("index_created_at") != index.get("index_created_at") or
            len(index["records"]) != snapshot.get("decision_count") or not index["records"]):
            raise ValueError("SEAL_ORIGINATION_BINDING")
        # Use the writer's original selection rule, never a newly sealed competing
        # same-date snapshot. This does not qualify or publish a capture session.
        capture_path = root / "operations-review/prospective-pit-capture-v1/sessions" / (session + ".json")
        if capture_path.exists() and capture_path.stat().st_size > 1024 * 1024:
            raise ValueError("CAPTURE_BINDING_SIZE_LIMIT")
        capture = _load(capture_path) if capture_path.exists() else None
        if capture_path.exists():
            expected = market.content_identity(capture, kind="prospective_capture_complete_session")
            if (any(capture.get(k) != v for k, v in expected.items()) or capture.get("session") != session or
                capture.get("contract_version") != "prospective_capture_complete_session/v1"):
                raise ValueError("ORIGINAL_CAPTURE_BINDING_INVALID")
        original_bound = (capture or {}).get("t0_decision_snapshot_identity")
        if original_bound:
            if original_bound != identity:
                raise ValueError("COMPETING_T0_CAPTURE_BINDING")
        else:
            sealed = list(path.parent.parent.glob("*/prospective_t0_snapshot_write_receipt.json"))
            if len(sealed) != 1 or sealed[0].parent.resolve() != path.parent.resolve():
                raise ValueError("AMBIGUOUS_ORIGINAL_T0_SEALS")
        count = 0
        def verify_record(ticker, row):
            nonlocal count
            sealed = index["records"].get(ticker) or {}
            if (row.get("decision_session") != session or row.get("canonical_operation_identity") != original or
                row.get("source_decision_artifact_identity") != decision or
                sealed.get("snapshot_record_identity") != row.get("prospective_snapshot_record_identity") or
                sealed.get("source_decision_artifact_identity") != decision or
                sealed.get("integrated_decision_identity") != row.get("integrated_decision_identity")):
                raise ValueError("SEALED_RECORD_ORIGINATION")
            count += 1
        records = snapshot.get("records")
        from bounded_artifact_stream import source_hash
        if isinstance(records, Mapping):
            for ticker, record in records.items():
                verify_record(ticker, record)
        else:
            # Reuse the existing bounded source seam without importing the full
            # feedback observer back into its own origination dependency.
            from bounded_artifact_stream import stream_artifact
            metadata, digest, _ = stream_artifact(path, excluded={"snapshot_identity"}, on_record=verify_record)
            if metadata.get("snapshot_identity") != identity or SNAPSHOT_PREFIX + digest != identity:
                raise ValueError("ORIGINAL_STREAM_SOURCE_CHANGED")
        raw_sha = source_hash(path)
        if raw_sha != index["snapshot_file_sha256"] or (not isinstance(records, Mapping) and raw_sha != snapshot.raw_sha256):
            raise ValueError("ORIGINAL_WRITE_HASH_OR_STREAM_SOURCE_CHANGED")
        if count != snapshot.get("decision_count"):
            raise ValueError("SEALED_RECORD_COUNT")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return ["ORIGINAL_T0_SEAL_OR_RECORD_PROOF_INVALID"]
    return []


def _handoff_snapshot_inventory(root: Path) -> list[dict[str, Any]]:
    base = root / "operations-review" / "canonical-post-close-v1"
    rows: list[dict[str, Any]] = []
    for path in historical_paths(root, "operations-review/canonical-post-close-v1", "*/session_handoff_bundle.json"):
        bundle = _load(path) or {}
        declared = bundle.get("prospective_decision_snapshot") or {}
        rows.append({
            "session": bundle.get("session"), "canonical_handoff_path": _relative(root, path),
            "snapshot_identity": declared.get("identity") if isinstance(declared, Mapping) else None,
            "snapshot_status": declared.get("status") if isinstance(declared, Mapping) else "NOT_RETAINED_LEGACY_HANDOFF",
            "snapshot_reason": declared.get("reason") if isinstance(declared, Mapping) else "NO_MODERN_PROSPECTIVE_SNAPSHOT_FIELD",
        })
    return rows


def discover_snapshots(root: str | Path, *, payload_projection: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
                       snapshot_loader: Callable[[Path], Mapping[str, Any] | None] | None = None,
                       snapshot_validator: Callable[[Mapping[str, Any]], bool] | None = None) -> dict[str, Any]:
    """Inventory immutable snapshots and admit only canonical-operation-bound ones.

    ``snapshot_loader``/``snapshot_validator`` are resource-containment seams (header-only handle plus a
    streamed identity proof); the defaults keep the original full-parse behaviour.
    """
    repository = Path(root)
    load_snapshot = snapshot_loader or _load
    validate = snapshot_validator or validate_snapshot
    operations = _operation_manifests(repository)
    handoffs = _handoff_by_snapshot(repository)
    base = repository / "operations-review" / "prospective-decision-retention-v1"
    inventory: list[dict[str, Any]] = []
    genuine: list[dict[str, Any]] = []
    for path in historical_paths(repository, "operations-review/prospective-decision-retention-v1", "*/*/prospective_decision_snapshot.json"):
        snapshot = load_snapshot(path)
        if not snapshot:
            continue
        identity = snapshot.get("snapshot_identity")
        source = snapshot.get("source_integrated_decision_artifact") or {}
        operation_identity = snapshot.get("daily_session_operation_identity")
        operation = operations.get(operation_identity) if isinstance(operation_identity, str) else None
        matches = handoffs.get(identity, []) if isinstance(identity, str) else []
        handoff = matches[0] if len(matches) == 1 else None
        reasons: list[str] = []
        qualified_reuse = False
        if not validate(snapshot):
            reasons.append("SNAPSHOT_CONTENT_IDENTITY_INVALID")
        if len(matches) > 1:
            reasons.append("AMBIGUOUS_T0_HANDOFF_BINDINGS")
        if not isinstance(operation, Mapping):
            reasons.append("DAILY_OPERATION_MANIFEST_NOT_RETAINED")
        else:
            manifest = operation["manifest"]
            if manifest.get("market_session") != snapshot.get("session"):
                reasons.append("DAILY_OPERATION_SESSION_MISMATCH")
            if manifest.get("generation_context") != "DAILY_PRODUCER_RETAINED_COMPLETED_SESSION":
                reasons.append("DAILY_OPERATION_REPLAY_OR_UNQUALIFIED")
        if not isinstance(handoff, Mapping):
            reasons.append("CANONICAL_HANDOFF_SNAPSHOT_BINDING_MISSING")
        else:
            bundle = handoff["bundle"]
            bound = bundle.get("prospective_decision_snapshot") or {}
            if bound.get("identity") != identity:
                reasons.append("HANDOFF_SNAPSHOT_IDENTITY_MISMATCH")
            if bundle.get("session") != snapshot.get("session"):
                reasons.append("HANDOFF_SESSION_MISMATCH")
            mismatch = []
            if bundle.get("daily_session_operation_identity") != operation_identity:
                mismatch.append("HANDOFF_OPERATION_IDENTITY_MISMATCH")
            if bundle.get("integrated_investment_decision_product_identity") != source.get("artifact_identity"):
                mismatch.append("HANDOFF_SOURCE_DECISION_IDENTITY_MISMATCH")
            if mismatch or bound.get("retention") == "ORIGINAL_SESSION_T0_REUSED":
                reuse_reasons = _original_reuse_reasons(repository, path, snapshot, handoff, operations)
                if reuse_reasons:
                    reasons.extend(mismatch + reuse_reasons)
                else:
                    qualified_reuse = True
        status = GENUINE if not reasons else EXCLUDED
        row = {
            "snapshot_path": _relative(repository, path), "snapshot_identity": identity,
            "session": snapshot.get("session"), "decision_count": snapshot.get("decision_count"),
            "source_decision_artifact_identity": source.get("artifact_identity"),
            "daily_session_operation_identity": operation_identity, "classification": status,
            "proof_reason_codes": reasons or [
                "IMMUTABLE_SNAPSHOT_CONTENT_IDENTITY_VALID",
                "CANONICAL_HANDOFF_BINDS_SNAPSHOT_AND_SOURCE_DECISION",
                "RETAINED_DAILY_OPERATION_BINDS_SAME_COMPLETED_SESSION",
            ],
            "canonical_handoff_path": handoff.get("path") if isinstance(handoff, Mapping) else None,
            "operation_manifest_path": operation.get("path") if isinstance(operation, Mapping) else None,
        }
        if qualified_reuse and status == GENUINE:
            row["proof_reason_codes"] = ["IMMUTABLE_SNAPSHOT_CONTENT_IDENTITY_VALID", "QUALIFIED_ORIGINAL_T0_REUSE",
                                         "ORIGINAL_AND_HANDOFF_OPERATIONS_INDEPENDENTLY_VERIFIED"]
            row["lineage_proof"] = {"contract_version": LINEAGE_READER_VERSION,
                "origination_operation_identity": operation_identity,
                "origination_decision_identity": source.get("artifact_identity"),
                "handoff_operation_identity": bundle["daily_session_operation_identity"],
                "handoff_decision_identity": bundle["integrated_investment_decision_product_identity"]}
        inventory.append(row)
        if status == GENUINE:
            genuine.append({"snapshot": payload_projection(snapshot) if payload_projection else snapshot, "inventory": row})
    return {
        "contract_version": CONTRACT_VERSION,
        "inventory": inventory,
        "genuine_snapshots": genuine,
        "classification_counts": dict(sorted(Counter(row["classification"] for row in inventory).items())),
        "handoff_snapshot_inventory": _handoff_snapshot_inventory(repository),
    }


def maturity_state(*, horizon_status: str, later_completed_sessions: int, required_sessions: int) -> str:
    """Map existing forward-bridge facts to the retention maturation contract."""
    if horizon_status == "MATURE":
        return "MATURED"
    if horizon_status in {"CLOSE_PRICE_NOT_RETAINED", "PRICE_BASIS_INCOMPATIBLE"}:
        return "PRICE_SERIES_UNQUALIFIED"
    if horizon_status == "T0_SESSION_NOT_IN_GOVERNED_CHAIN":
        return "TEMPORAL_PROVENANCE_UNQUALIFIED"
    if later_completed_sessions == 0:
        return "PENDING"
    if later_completed_sessions < required_sessions:
        return "INSUFFICIENT_FUTURE_DEPTH"
    return "PRICE_SERIES_UNQUALIFIED"


def evaluate_serialized_close_condition(
    condition: Mapping[str, Any] | None, *, ticker: str, chain: Sequence[str], start_session: str,
    snapshots: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Evaluate only an already-serialized fixed-level close condition.

    This is a generic comparison over the retained condition, not a trigger
    generator; dynamic strategy measurements remain explicitly non-evaluable.
    """
    condition = condition if isinstance(condition, Mapping) else {}
    if condition.get("status") != "MACHINE_EVALUABLE":
        return {"status": "NOT_MACHINE_EVALUABLE", "event_session": None, "condition_identity": condition.get("condition_identity"), "reason_codes": list(condition.get("reason_codes") or [])}
    if start_session not in chain:
        return {"status": "TEMPORAL_PROVENANCE_UNQUALIFIED", "event_session": None, "condition_identity": condition.get("condition_identity"), "reason_codes": ["T0_SESSION_NOT_IN_GOVERNED_CHAIN"]}
    if (condition.get("source_method") == "market_structure_breakout_product_projection/v1"
            and (condition.get("source_lineage") or {}).get("as_of_session") != start_session):
        return {"status": "TEMPORAL_PROVENANCE_UNQUALIFIED", "event_session": None, "condition_identity": condition.get("condition_identity"), "reason_codes": ["STRUCTURAL_CONDITION_T0_SESSION_MISMATCH"]}
    level, operator = condition.get("reference_level"), condition.get("operator")
    if (not isinstance(level, (int, float)) or isinstance(level, bool)
            or not math.isfinite(level) or level <= 0 or operator not in {">", "<"}):
        return {"status": "NOT_MACHINE_EVALUABLE", "event_session": None, "condition_identity": condition.get("condition_identity"), "reason_codes": ["SERIALIZED_CONDITION_INCOMPLETE"]}
    body = dict(condition)
    identity = body.pop("condition_identity", None)
    if identity != "retained_strategy_boundary_condition:" + _hash(body):
        return {"status": "NOT_MACHINE_EVALUABLE", "event_session": None, "condition_identity": identity, "reason_codes": ["SERIALIZED_CONDITION_IDENTITY_INVALID"]}
    from integrated_decision_prospective_feedback import retained_session_price_observations, _compatible_close_series, _qualified_close
    observations = retained_session_price_observations(snapshots, ticker)
    t0 = observations.get(start_session)
    if not t0 or not _qualified_close(t0.get("close")):
        return {"status": "PRICE_SERIES_UNQUALIFIED", "event_session": None, "condition_identity": identity, "reason_codes": ["T0_PRICE_BASIS_NOT_RETAINED"]}
    observed = 0
    incomplete = False
    for session in chain[chain.index(start_session) + 1:]:
        row = ((snapshots.get(session) or {}).get("records") or {}).get(ticker) or {}
        matches = [item for item in (row.get("observations") or []) if isinstance(item, Mapping) and item.get("session") == session]
        if len(matches) != 1:
            incomplete = True
            continue
        if not _compatible_close_series(t0, matches[0]):
            incomplete = True
            continue
        close = matches[0].get("close")
        if (not isinstance(close, (int, float)) or isinstance(close, bool)
                or not math.isfinite(close) or close <= 0):
            incomplete = True
            continue
        observed += 1
        if (operator == ">" and close > level) or (operator == "<" and close < level):
            if incomplete:
                return {"status": "PRICE_SERIES_UNQUALIFIED", "event_session": None, "condition_identity": identity,
                        "reason_codes": ["FIRST_EVENT_ORDER_UNPROVEN_AFTER_MISSING_OR_INCOMPATIBLE_PRICE"]}
            return {"status": "SATISFIED", "event_session": session, "condition_identity": condition.get("condition_identity"), "reason_codes": ["SERIALIZED_FIXED_T0_LEVEL_SATISFIED"]}
    return {"status": "NOT_SATISFIED_YET" if observed and not incomplete else "PRICE_SERIES_UNQUALIFIED", "event_session": None, "condition_identity": condition.get("condition_identity"), "reason_codes": ["NO_LATER_RETAINED_CLOSE" if not observed else "NO_LATER_CLOSE_SATISFIED_FIXED_T0_LEVEL"]}


def _maturity_diagnosis(horizon: Mapping[str, Any]) -> str:
    """Describe existing outcome fitness; never evaluate prices or infer maturity."""
    fitness = horizon.get("series_fitness")
    status = horizon.get("status")
    if status == "T0_SESSION_NOT_IN_GOVERNED_CHAIN":
        return "T0_SESSION_NOT_QUALIFIED"
    if fitness in {"T0_CLOSE_NOT_RETAINED", "START_CLOSE_NOT_RETAINED"}:
        return "T0_CLOSE_NOT_RETAINED"
    if fitness == "T0_CLOSE_VALUE_INVALID":
        return "T0_CLOSE_INVALID"
    if status == "PENDING_NOT_ENOUGH_FUTURE_SESSIONS":
        return "PENDING_COMPLETED_SESSION_DEPTH"
    if status == "PRICE_BASIS_INCOMPATIBLE":
        return "PRICE_SERIES_INCOMPATIBLE"
    if status == "CLOSE_PRICE_NOT_RETAINED":
        return "FUTURE_CLOSE_NOT_RETAINED" if fitness == "EXACT_CLOSE_MISSING" else "FUTURE_CLOSE_INVALID" if fitness == "CLOSE_VALUE_INVALID" else "UNRESOLVED_CLOSE_GAP"
    return "MATURE_ENDPOINT_RETURN" if status == "MATURE" else "UNKNOWN_OUTCOME_FITNESS"


def _maturity_health(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    from integrated_decision_prospective_feedback import FORWARD_HORIZONS
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    seen = set()
    excluded = 0
    for row in records:
        if (row.get("temporal_qualification") or {}).get("status") != GENUINE:
            excluded += 1
            continue
        key = (row.get("ticker"), row.get("decision_session"), row.get("decision_identity"))
        if any(not isinstance(value, str) or not value for value in key):
            raise ValueError("CORPUS_HEALTH_DECISION_BINDING_REQUIRED")
        if key in seen:
            raise ValueError("CORPUS_HEALTH_DUPLICATE_DECISION")
        seen.add(key)
        grouped.setdefault(key[1], []).append(row)
    sessions = []
    totals: dict[str, Counter[str]] = {}
    for session, entries in sorted(grouped.items()):
        horizons: dict[str, dict[str, Any]] = {}
        names = sorted(set(FORWARD_HORIZONS) | {name for row in entries for name in (row.get("forward_outcomes") or {}).get("horizons", {})})
        for name in names:
            diagnoses: Counter[str] = Counter()
            states: Counter[str] = Counter()
            endpoint_gaps: Counter[str] = Counter()
            for row in entries:
                h = ((row.get("forward_outcomes") or {}).get("horizons") or {}).get(name) or {}
                h = h if isinstance(h, Mapping) else {}
                diagnosis = _maturity_diagnosis(h)
                diagnoses[diagnosis] += 1
                states[str(h.get("maturation_state") or "UNKNOWN")] += 1
                endpoint = h.get("future_session")
                if diagnosis in {"FUTURE_CLOSE_NOT_RETAINED", "FUTURE_CLOSE_INVALID", "PRICE_SERIES_INCOMPATIBLE"} and isinstance(endpoint, str) and endpoint:
                    endpoint_gaps[endpoint] += 1
            totals.setdefault(name, Counter()).update(diagnoses)
            horizons[name] = {"decision_count": len(entries), "diagnosis_counts": dict(sorted(diagnoses.items())),
                              "maturation_state_counts": dict(sorted(states.items())),
                              "affected_future_sessions": dict(sorted(endpoint_gaps.items()))}
        sessions.append({"session": session, "decision_count": len(entries), "horizons": horizons,
            "evidence_axis_snapshot_complete": dict(sorted(Counter(str((r.get("evidence_axes") or {}).get("status", FIELD_NOT_RETAINED)) for r in entries).items())),
            "trigger_condition_evaluable": dict(sorted(Counter(str(((r.get("trigger") or {}).get("condition") or {}).get("status", FIELD_NOT_RETAINED)) for r in entries).items())),
            "invalidation_condition_evaluable": dict(sorted(Counter(str(((r.get("invalidation") or {}).get("condition") or {}).get("status", FIELD_NOT_RETAINED)) for r in entries).items()))})
    return {"admitted_decision_count": len(seen), "excluded_temporal_record_count": excluded,
            "sessions": sessions, "horizon_diagnosis_counts": {name: dict(sorted(counts.items())) for name, counts in sorted(totals.items())},
            "interpretation": "EXISTING_ENDPOINT_FITNESS_ONLY_NOT_CALIBRATION_ELIGIBILITY_OR_COMPLETE_PATH_FITNESS",
            "no_historical_t0_backfill": True, "authority_effect": "NONE"}


def build_corpus_health(
    *, snapshot_inventory: Mapping[str, Any], feedback_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact operational health view; never reconstructs a missing legacy T0 field."""
    feedback_by_snapshot: set[str] = {
        str(row.get("t0_snapshot_identity")) for row in ((feedback_artifact or {}).get("feedback_records") or [])
        if row.get("t0_snapshot_identity")
    }
    rows: list[dict[str, Any]] = []
    for entry in snapshot_inventory.get("inventory") or []:
        rows.append({
            "session": entry.get("session"), "canonical_prospective_snapshot_exists": True,
            "identity_qualified": entry.get("classification") == GENUINE,
            "snapshot_identity": entry.get("snapshot_identity"), "decision_count": entry.get("decision_count"),
            "outcome_artifact_exists": entry.get("snapshot_identity") in feedback_by_snapshot,
            "reason_codes": entry.get("proof_reason_codes") or [],
        })
    known_sessions = {row["session"] for row in rows}
    for handoff in snapshot_inventory.get("handoff_snapshot_inventory") or []:
        session = handoff.get("session")
        if not isinstance(session, str) or session in known_sessions:
            continue
        rows.append({
            "session": session, "canonical_prospective_snapshot_exists": False,
            "identity_qualified": False, "snapshot_identity": None, "decision_count": None,
            "outcome_artifact_exists": False,
            "reason_codes": [str(handoff.get("snapshot_status")), str(handoff.get("snapshot_reason"))],
        })
    maturity = _maturity_health((feedback_artifact or {}).get("feedback_records") or [])
    return _identity({
        "schema_version": "1.0.0", "contract_version": HEALTH_CONTRACT_VERSION,
        "sessions": sorted(rows, key=lambda row: (str(row["session"]), str(row["snapshot_identity"]))),
        "outcome_maturity": maturity,
        "authority_boundary": "OPERATIONS_HEALTH_ONLY_NO_POLICY_OR_DECISION_INPUT",
    }, "prospective_decision_corpus_health:", "artifact_identity")
