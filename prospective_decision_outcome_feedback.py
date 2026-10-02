"""Retained-only prospective decision feedback and policy diagnostics.

This is a downstream observer over the existing integrated-decision artifact
and P3F9B exact-session close snapshots.  It deliberately does not rebuild a
decision, choose a later artifact for an older session, or write into any
decision-producing path.  ``integrated_decision_prospective_feedback`` remains
the sole forward-close calculator; this module supplies the missing corpus and
temporal qualification contracts plus descriptive diagnostics.
"""
from __future__ import annotations

import hashlib
import json
import os
import statistics
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import daily_session_level2_package as level2
import fundamental_signal_consumption_contract as fundamental_signals
import integrated_decision_prospective_feedback as forward_bridge
import prospective_decision_outcome_measurement as outcome_measurement
import prospective_decision_retention as retention


CONTRACT_VERSION = "prospective_decision_outcome_feedback/v3"
TEMPORAL_CONTRACT_VERSION = "retained_integrated_decision_temporal_qualification/v1"
OUTCOME_POLICY_VERSION = "prospective_outcome_diagnostic_policy/v1"
FIELD_NOT_RETAINED = "FIELD_NOT_RETAINED_AT_T0"
GENUINE = "GENUINE_PROSPECTIVE_DECISION"
REPLAY_ONLY = "REPLAY_ONLY"
RETROSPECTIVELY_REBUILT = "RETROSPECTIVELY_REBUILT"
CURRENT_VIEW_OF_OLD_SESSION = "CURRENT_VIEW_OF_OLD_SESSION"
UNKNOWN_TEMPORAL_STATUS = "UNKNOWN_TEMPORAL_STATUS"
EXCLUDED = "EXCLUDE_TEMPORAL_PROVENANCE_UNQUALIFIED"

# These are analytical labels only.  They neither change an existing posture
# nor claim calibrated success probabilities.
OUTCOME_POLICY_CONSTANTS = {
    "positive_return_strictly_greater_than": 0.0,
    "adverse_return_strictly_less_than": 0.0,
    "material_upside_return_greater_than_or_equal_to": 0.03,
    "large_close_adverse_excursion_less_than_or_equal_to": -0.05,
    "basis_horizon_for_outcome_label": "forward_close_return_5",
    "version": OUTCOME_POLICY_VERSION,
}
REQUIRED_TICKERS = ("FPT", "HPG", "SSI", "QNS", "PVD", "PNJ", "VNM")
_GENUINE_CONTEXT = "DAILY_PRODUCER_RETAINED_COMPLETED_SESSION"
SUMMARY_CONTRACT_VERSION = "integrated_decision_classification_summary/v1"
SUMMARY_CACHE_CONTRACT_VERSION = "integrated_decision_classification_summary_cache/v1"
_SUMMARY_CACHE_PATH = Path("operations-review/prospective-decision-outcome-feedback-v1/_artifact_summary_cache.json")
_SUMMARY_CACHE_MAX_BYTES = 8 * 1024 * 1024
_SUMMARY_CACHE_MAX_ENTRIES = 2048
_SUMMARY_FIELDS = ("artifact_identity", "session", "requested_at", "contract_version")


class ProspectiveFeedbackError(ValueError):
    """Raised only for malformed retained-contract input or immutable conflicts."""


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(payload: dict[str, Any], prefix: str, field: str = "artifact_identity") -> dict[str, Any]:
    payload[field] = prefix + hashlib.sha256(_canon(payload).encode("utf-8")).hexdigest()
    return payload


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _source_fingerprint(path: Path) -> dict[str, Any] | None:
    """Validate current bytes with bounded memory; file metadata alone is never proof."""
    try:
        before = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            return None
        return {"size": after.st_size, "mtime_ns": after.st_mtime_ns, "sha256": digest.hexdigest()}
    except OSError:
        return None


def _read_summary_cache(root: Path) -> dict[str, Any]:
    try:
        path = root / _SUMMARY_CACHE_PATH
        if path.stat().st_size > _SUMMARY_CACHE_MAX_BYTES:
            return {}
        cache = _load_json(path)
        entries = (cache or {}).get("entries")
        if (cache or {}).get("contract_version") != SUMMARY_CACHE_CONTRACT_VERSION or not isinstance(entries, dict):
            return {}
        return entries if len(entries) <= _SUMMARY_CACHE_MAX_ENTRIES else {}
    except (OSError, UnicodeError):
        return {}


def _write_summary_cache(root: Path, entries: Mapping[str, Any]) -> None:
    """Best-effort, bounded atomic derived state; analytical results never depend on writes."""
    temporary = None
    try:
        payload = _canon({"contract_version": SUMMARY_CACHE_CONTRACT_VERSION,
                          "entries": dict(sorted(entries.items())[:_SUMMARY_CACHE_MAX_ENTRIES])}).encode("utf-8")
        if len(payload) > _SUMMARY_CACHE_MAX_BYTES:
            return
        path = root / _SUMMARY_CACHE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".iid-summary-", suffix=".tmp", delete=False) as out:
            temporary = Path(out.name)
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    except (OSError, TypeError, ValueError):
        pass
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _make_summary(rel: str, fingerprint: Mapping[str, Any], artifact: Mapping[str, Any]) -> dict[str, Any]:
    return _identity({"contract_version": SUMMARY_CONTRACT_VERSION, "source_path": rel,
                      "source": dict(fingerprint), "header": {key: artifact.get(key) for key in _SUMMARY_FIELDS},
                      "record_count": len(artifact.get("records") or {})}, "iid-summary:", "summary_identity")


def _valid_summary(entry: Any, rel: str, fingerprint: Any, link: Any) -> bool:
    if not isinstance(entry, dict) or fingerprint is None:
        return False
    unsigned = {key: value for key, value in entry.items() if key != "summary_identity"}
    try:
        if entry.get("summary_identity") != _identity(unsigned, "iid-summary:", "summary_identity")["summary_identity"]:
            return False
    except (TypeError, ValueError):
        return False
    header = entry.get("header")
    count = entry.get("record_count")
    if (entry.get("contract_version") != SUMMARY_CONTRACT_VERSION or entry.get("source_path") != rel
            or entry.get("source") != fingerprint or not isinstance(header, dict)
            or set(header) != set(_SUMMARY_FIELDS) or type(count) is not int or count < 0):
        return False
    if any(value is not None and not isinstance(value, str) for value in header.values()):
        return False
    if link is not None:
        if header["artifact_identity"] != link["artifact_identity"] or header["session"] != link["session"]:
            return False
        manifest = (link.get("operation") or {}).get("manifest")
        if not isinstance(manifest, Mapping):
            return False
        if manifest.get("operation_identity") != link["operation_identity"] or manifest.get("market_session") != header["session"]:
            return False
        outputs = manifest.get("outputs") or {}
        if not isinstance(outputs, Mapping):
            return False
        declared = outputs.get("integrated_investment_decision_product")
        if isinstance(declared, Mapping):
            declared = declared.get("artifact_identity") or declared.get("identity")
        if declared is not None and declared != header["artifact_identity"]:
            return False
    return True


def retain_iid_classification_summary(root: str | Path, path: Path, artifact: Mapping[str, Any]) -> None:
    """Emit from the writer's existing in-memory artifact, without decoding or serializing the IID."""
    repository = Path(root)
    fingerprint = _source_fingerprint(path)
    if fingerprint is None or not artifact:
        return
    try:
        entries = _read_summary_cache(repository)
        rel = _relative(repository, path)
        entries[rel] = _make_summary(rel, fingerprint, artifact)
        _write_summary_cache(repository, entries)
    except (TypeError, ValueError):
        pass


def _load_iid(path: Path, metrics: dict[str, int] | None) -> dict[str, Any] | None:
    if metrics is not None:
        metrics["full_iid_parses"] = metrics.get("full_iid_parses", 0) + 1
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        metrics["full_iid_bytes_parsed"] = metrics.get("full_iid_bytes_parsed", 0) + size
    return _load_json(path)


def _operation_manifests(root: Path) -> dict[str, dict[str, Any]]:
    base = root / "operations-review" / "daily-research-session-operations-v1"
    result: dict[str, dict[str, Any]] = {}
    if not base.is_dir():
        return result
    for path in sorted(base.glob("*/*/run_manifest.json")):
        manifest = _load_json(path)
        if not manifest:
            continue
        identity = manifest.get("operation_identity")
        if isinstance(identity, str) and identity:
            result[identity] = {"path": _relative(root, path), "manifest": manifest}
    return result


def _handoff_bundles(root: Path, operations: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return only complete canonical handoffs with an identity-bound decision artifact."""
    base = root / "operations-review" / "canonical-post-close-v1"
    rows: list[dict[str, Any]] = []
    if not base.is_dir():
        return rows
    for path in sorted(base.glob("*/session_handoff_bundle.json")):
        bundle = _load_json(path)
        if not bundle:
            continue
        session = bundle.get("session")
        op_identity = bundle.get("daily_session_operation_identity")
        artifact_identity = bundle.get("integrated_investment_decision_product_identity")
        artifact_ref = (bundle.get("deeper_bundles") or {}).get("integrated_investment_decision_product")
        producer = bundle.get("daily_producer") or {}
        proof = bundle.get("market_session_proof") or {}
        if not all(isinstance(value, str) and value for value in (session, op_identity, artifact_identity, artifact_ref)):
            continue
        artifact_path = (root / artifact_ref).resolve()
        rows.append({
            "path": _relative(root, path), "bundle": bundle, "session": session,
            "operation_identity": op_identity, "operation": operations.get(op_identity),
            "artifact_identity": artifact_identity, "artifact_path": artifact_path,
            "producer_completed": producer.get("status") == "COMPLETED",
            "resolved_completed_session": proof.get("resolved_completed_session"),
            "prospective_snapshot_identity": ((bundle.get("prospective_decision_snapshot") or {}).get("identity")),
        })
    return rows


def _artifact_paths(root: Path) -> list[Path]:
    operations = root / "operations-review"
    # Bounded legacy namespaces plus exact canonical handoff references; no recursive review scan.
    found = set(operations.glob("*/integrated_investment_decision_product_artifact.json"))
    found.update((operations / "canonical-post-close-v1").glob("*/enrichment/integrated_investment_decision_product.json"))
    found.update(link["artifact_path"] for link in _handoff_bundles(root, _operation_manifests(root)))
    return sorted(found)


def _observed_time_matches_session(artifact: Mapping[str, Any], session: str) -> bool:
    observed = artifact.get("requested_at")
    # The modern contract is ISO.  Older retained artifacts have a legacy
    # month/day/year timestamp and are intentionally not admitted by this new
    # temporal gate rather than being parsed with locale-dependent semantics.
    return isinstance(observed, str) and observed.startswith(session + "T")


def _qualify_linked_artifact(link: Mapping[str, Any], artifact: Mapping[str, Any]) -> dict[str, Any]:
    session = link["session"]
    operation = link.get("operation") or {}
    manifest = operation.get("manifest") if isinstance(operation, Mapping) else None
    reasons: list[str] = []
    if artifact.get("contract_version") != "integrated_investment_decision_product/v1":
        reasons.append("INTEGRATED_DECISION_CONTRACT_INVALID")
    if artifact.get("artifact_identity") != link["artifact_identity"]:
        reasons.append("HANDOFF_ARTIFACT_IDENTITY_MISMATCH")
    if artifact.get("session") != session:
        reasons.append("ARTIFACT_SESSION_MISMATCH")
    if not _observed_time_matches_session(artifact, session):
        reasons.append("ARTIFACT_OBSERVED_TIME_NOT_SESSION_BOUND")
    if not link.get("producer_completed"):
        reasons.append("DAILY_PRODUCER_NOT_COMPLETED")
    if link.get("resolved_completed_session") != session:
        reasons.append("COMPLETED_SESSION_PROOF_MISMATCH")
    if not isinstance(manifest, Mapping):
        reasons.append("DAILY_OPERATION_MANIFEST_NOT_RETAINED")
    else:
        if manifest.get("market_session") != session:
            reasons.append("DAILY_OPERATION_SESSION_MISMATCH")
        if manifest.get("generation_context") != _GENUINE_CONTEXT:
            reasons.append("DAILY_OPERATION_REPLAY_OR_UNQUALIFIED")
    status = GENUINE if not reasons else EXCLUDED
    return {
        "contract_version": TEMPORAL_CONTRACT_VERSION, "status": status,
        "decision_session": session, "artifact_observed_at": artifact.get("requested_at"),
        "decision_artifact_identity": artifact.get("artifact_identity"),
        "daily_session_operation_identity": link["operation_identity"],
        "canonical_handoff_path": link["path"],
        "operation_manifest_path": operation.get("path") if isinstance(operation, Mapping) else None,
        "proof_reason_codes": reasons or [
            "CANONICAL_HANDOFF_BINDS_ARTIFACT_IDENTITY",
            "RETAINED_DAILY_OPERATION_BINDS_SAME_COMPLETED_SESSION",
            "ARTIFACT_OBSERVED_TIME_IS_SAME_SESSION",
        ],
    }


def discover_prospective_corpus(root: str | Path, *, payload_projection=None,
                                use_summary_cache: bool = True, cache_metrics: dict[str, int] | None = None) -> dict[str, Any]:
    """Inventory every retained integrated-decision artifact without promoting copies or replays."""
    repository = Path(root)
    if cache_metrics is not None:
        for key in ("full_iid_parses", "full_iid_bytes_parsed", "summary_hits", "avoided_iid_bytes"):
            cache_metrics.setdefault(key, 0)
    operations = _operation_manifests(repository)
    handoffs = _handoff_bundles(repository, operations)
    links = {item["artifact_path"]: item for item in handoffs}
    linked_identities = {item["artifact_identity"] for item in handoffs}
    inventory: list[dict[str, Any]] = []
    genuine: list[dict[str, Any]] = []
    entries = _read_summary_cache(repository) if use_summary_cache else {}
    retained_entries: dict[str, Any] = {}
    for path in _artifact_paths(repository):
        link = links.get(path.resolve())
        # Modern working views cannot be T0 authorities; their immutable snapshots are read below.
        if link is not None and link.get("prospective_snapshot_identity"):
            continue
        rel = _relative(repository, path)
        fingerprint = _source_fingerprint(path) if use_summary_cache else None
        entry = entries.get(rel)
        summary_hit = use_summary_cache and _valid_summary(entry, rel, fingerprint, link)
        # A summary can never replace the record payload of a genuine legacy authority.
        if summary_hit and link is not None and _qualify_linked_artifact(link, entry["header"])["status"] == GENUINE:
            summary_hit = False
        if summary_hit:
            artifact = entry["header"]
            record_count = entry["record_count"]
            retained_entries[rel] = entry
            if cache_metrics is not None:
                cache_metrics["summary_hits"] = cache_metrics.get("summary_hits", 0) + 1
                cache_metrics["avoided_iid_bytes"] = cache_metrics.get("avoided_iid_bytes", 0) + fingerprint["size"]
        else:
            artifact = _load_iid(path, cache_metrics)
            if artifact:
                record_count = len(artifact.get("records") or {})
                if fingerprint is not None:
                    try:
                        current = path.stat()
                        if (current.st_size, current.st_mtime_ns) == (fingerprint["size"], fingerprint["mtime_ns"]):
                            retained_entries[rel] = _make_summary(rel, fingerprint, artifact)
                    except (OSError, TypeError, ValueError):
                        pass
        if not artifact:
            continue
        link = links.get(path.resolve())
        if link is not None:
            if link.get("prospective_snapshot_identity"):
                classification = CURRENT_VIEW_OF_OLD_SESSION
                temporal = {
                    "contract_version": TEMPORAL_CONTRACT_VERSION, "status": classification,
                    "decision_session": artifact.get("session"), "artifact_observed_at": artifact.get("requested_at"),
                    "decision_artifact_identity": artifact.get("artifact_identity"),
                    "proof_reason_codes": ["IMMUTABLE_PROSPECTIVE_SNAPSHOT_IS_CANONICAL_T0_SOURCE"],
                }
            else:
                temporal = _qualify_linked_artifact(link, artifact)
                classification = temporal["status"]
        else:
            lowered = rel.lower()
            if "replay" in lowered:
                classification, reason = REPLAY_ONLY, "REPLAY_PATH_NOT_ELIGIBLE"
            elif artifact.get("artifact_identity") in linked_identities:
                classification, reason = CURRENT_VIEW_OF_OLD_SESSION, "NONCANONICAL_COPY_OF_BOUND_ARTIFACT"
            elif "canonical-post-close-v1" in lowered:
                classification, reason = CURRENT_VIEW_OF_OLD_SESSION, "CANONICAL_HANDOFF_BINDING_MISSING"
            elif "integrated-investment-decision-product-v1-" in lowered:
                classification, reason = UNKNOWN_TEMPORAL_STATUS, "NO_CANONICAL_HANDOFF_BINDING"
            else:
                classification, reason = RETROSPECTIVELY_REBUILT, "NONCANONICAL_ARTIFACT_PROVENANCE"
            temporal = {
                "contract_version": TEMPORAL_CONTRACT_VERSION, "status": classification,
                "decision_session": artifact.get("session"), "artifact_observed_at": artifact.get("requested_at"),
                "decision_artifact_identity": artifact.get("artifact_identity"), "proof_reason_codes": [reason],
            }
        row = {
            "artifact_path": rel, "artifact_identity": artifact.get("artifact_identity"),
            "contract_version": artifact.get("contract_version"), "decision_session": artifact.get("session"),
            "artifact_observed_at": artifact.get("requested_at"), "record_count": record_count,
            "classification": classification, "temporal_qualification": temporal,
        }
        inventory.append(row)
        if classification == GENUINE:
            genuine.append({"artifact": payload_projection(artifact) if payload_projection else artifact, "artifact_path": rel, "temporal": temporal})
        del artifact
    if use_summary_cache and retained_entries != entries:
        _write_summary_cache(repository, retained_entries)
    return {
        "contract_version": TEMPORAL_CONTRACT_VERSION,
        "inventory": sorted(inventory, key=lambda row: (str(row["decision_session"]), row["artifact_path"])),
        "genuine_artifacts": sorted(genuine, key=lambda row: (str(row["artifact"].get("session")), row["artifact_path"])),
        "qualified_session_chain": sorted({row["artifact"].get("session") for row in genuine if isinstance(row["artifact"].get("session"), str)}),
        "classification_counts": dict(sorted(Counter(row["classification"] for row in inventory).items())),
    }


def retained_session_snapshots(root: str | Path, sessions: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Load exact completed-session snapshots only when their own session identity matches."""
    repository = Path(root)
    snapshots: dict[str, dict[str, Any]] = {}
    for session in sorted(set(sessions)):
        path = level2.session_artifact_paths(repository, session)["exact_session_snapshot"]
        snapshot = _load_json(path)
        if snapshot and snapshot.get("resolved_completed_session") == session and isinstance(snapshot.get("snapshot_identity"), str):
            snapshots[session] = snapshot
    return snapshots


def _snapshot_t0_price_observations(candidates: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Expose only the T0 close copies sealed inside immutable snapshots.

    Each row was copied from its exact-session P3F9B source at T0.  This is
    not a history rebuild; it simply lets later feedback use the same sealed
    T0 price fact even when the original session-shaped working path moved.
    """
    snapshots: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        snapshot = candidate.get("snapshot") or {}
        session = snapshot.get("session")
        if not isinstance(session, str) or session in snapshots:
            continue
        records: dict[str, Any] = {}
        for ticker, entry in (snapshot.get("records") or {}).items():
            row = (entry or {}).get("t0_close_observation") if isinstance(entry, Mapping) else None
            if isinstance(row, Mapping) and row.get("session") == session:
                records[ticker] = {"observations": [dict(row)]}
        snapshots[session] = {
            "resolved_completed_session": session,
            "snapshot_identity": ((snapshot.get("t0_price_snapshot") or {}).get("snapshot_identity")),
            "records": records,
        }
    return snapshots


def _project_decision_for_feedback(record):
    keys = ("ticker", "as_of_session", "decision_identity", "research_action_posture", "policy_version",
            "fundamental_decision_policy_version", "evidence_axis_coherence", "priority_posture_reconciliation",
            "fundamental_state", "valuation_context_summary", "market_structure_state", "momentum_context",
            "participation", "market_sector_context", "trigger", "invalidation", "source_identities",
            "scenario_condition_context", "benchmark", "known_at", "target_condition_at_t0", "qualified_tactical_signal_at_t0", "forward_driver_context_at_t0", "intrinsic_scenario_at_t0")
    projected = {key: record[key] for key in keys if key in record}
    if "evidence_axes" in record:
        projected["evidence_axes"] = {key: {f: axis.get(f) for f in ("state", "fitness", "lineage", "method")}
                                      for key, axis in (record.get("evidence_axes") or {}).items() if isinstance(axis, Mapping)}
    corporate = record.get("corporate_intelligence_context") or {}
    if "forward_driver_context" in corporate:
        driver = corporate["forward_driver_context"]
        projected["forward_driver_context_at_t0"] = {key: driver.get(key) for key in ("contract_version", "context_identity", "session_fitness", "qualified_driver_count", "drivers")}
    if "intrinsic_scenario_valuation" in record:
        model = record["intrinsic_scenario_valuation"]
        projected["intrinsic_scenario_at_t0"] = {"projection_identity": model.get("projection_identity"),
            "method_readiness": {name: row.get("readiness") for name, row in (model.get("methods") or {}).items()},
            "authority_effect": model.get("authority_effect")}
    return projected


def _project_snapshot_for_feedback(snapshot):
    return {**{key: value for key, value in snapshot.items() if key != "records"}, "records": {
        ticker: {**{key: value for key, value in retained.items() if key != "integrated_decision_at_t0"},
                 "integrated_decision_at_t0": _project_decision_for_feedback(retained["integrated_decision_at_t0"])}
        for ticker, retained in snapshot["records"].items()}}


def _project_artifact_for_feedback(artifact):
    return {**{key: value for key, value in artifact.items() if key != "records"},
            "records": {ticker: _project_decision_for_feedback(row) for ticker, row in artifact["records"].items()}}


def _modern_snapshot_candidates(root: str | Path) -> dict[str, Any]:
    discovery = retention.discover_snapshots(root, payload_projection=_project_snapshot_for_feedback)
    genuine = discovery["genuine_snapshots"]
    chain = sorted({row["snapshot"].get("session") for row in genuine if isinstance(row["snapshot"].get("session"), str)})
    # Prefer the immutable T0 price copy for each prospective session.  A
    # completed market observations can mature cases even when no decision snapshot exists.
    snapshots = _snapshot_t0_price_observations(genuine)
    return {"discovery": discovery, "genuine": genuine, "chain": chain, "snapshots": snapshots}


def resolve_completed_market_observations(root):
    """Every qualified completed Daily session, independently of T0 case admission."""
    repository = Path(root)
    operations = _operation_manifests(repository)
    qualified = []
    for link in _handoff_bundles(repository, operations):
        manifest = (link.get("operation") or {}).get("manifest") or {}
        if (link["producer_completed"] and link["resolved_completed_session"] == link["session"] and
            manifest.get("market_session") == link["session"] and manifest.get("generation_context") == _GENUINE_CONTEXT):
            qualified.append(link["session"])
    chain = sorted(set(qualified))
    return chain, retained_session_snapshots(repository, chain)


def _compact_axes(record: Mapping[str, Any]) -> dict[str, Any]:
    axes = record.get("evidence_axes")
    if not isinstance(axes, Mapping):
        return {"status": FIELD_NOT_RETAINED, "axis_states": {}}
    return {
        "status": "RETAINED", "axis_states": {
            str(name): {"state": value.get("state"), "fitness": value.get("fitness"), "lineage": value.get("lineage"), "method": value.get("method", FIELD_NOT_RETAINED)}
            for name, value in sorted(axes.items()) if isinstance(value, Mapping)
        },
    }


def _state(record: Mapping[str, Any], key: str, nested_key: str | None = None) -> Any:
    value = record.get(key)
    if nested_key and isinstance(value, Mapping):
        return value.get(nested_key, FIELD_NOT_RETAINED)
    return value if value is not None else FIELD_NOT_RETAINED


def _outcome_label(record: Mapping[str, Any], outcome: Mapping[str, Any]) -> dict[str, Any]:
    h5 = (outcome.get("horizons") or {}).get("forward_close_return_5") or {}
    if h5.get("status") != forward_bridge.MATURE:
        return {"label": "INSUFFICIENT_FORWARD_DEPTH", "reason_codes": [str(h5.get("status"))], "basis_horizon": "forward_close_return_5"}
    value = h5.get("return")
    close5 = (outcome.get("close_path_by_horizon") or {}).get("close_excursion_5") or {}
    adverse = close5.get("CLOSE_MAE")
    posture = record.get("research_action_posture", FIELD_NOT_RETAINED)
    positive = isinstance(value, (int, float)) and value > OUTCOME_POLICY_CONSTANTS["positive_return_strictly_greater_than"]
    negative = isinstance(value, (int, float)) and value < OUTCOME_POLICY_CONSTANTS["adverse_return_strictly_less_than"]
    volatile = isinstance(adverse, (int, float)) and adverse <= OUTCOME_POLICY_CONSTANTS["large_close_adverse_excursion_less_than_or_equal_to"]
    if posture == "INITIATE_ON_BREAKOUT":
        label = "POSITIVE_BUT_VOLATILE" if positive and volatile else "FOLLOW_THROUGH" if positive else "FALSE_BREAKOUT_OUTCOME" if negative else "OUTCOME_UNQUALIFIED"
    elif posture == "ACCUMULATE_ON_RETEST":
        label = "ACCUMULATION_SETUP_WORKED" if positive else "ACCUMULATION_SETUP_FAILED" if negative else "OUTCOME_UNQUALIFIED"
    elif posture == "EARLY_WATCH":
        label = "EARLY_WATCH_WORKED" if positive else "EARLY_WATCH_FAILED" if negative else "OUTCOME_UNQUALIFIED"
    elif posture in {"WAIT_FOR_CONFIRMATION", "AVOID", "INSUFFICIENT_CURRENT_RESEARCH"}:
        label = "WAIT_MISSED_UPSIDE" if positive else "WAIT_AVOIDED_DRAWDOWN" if negative else "OUTCOME_UNQUALIFIED"
    else:
        label = "FOLLOW_THROUGH" if positive else "FAILED_FOLLOW_THROUGH" if negative else "OUTCOME_UNQUALIFIED"
    return {"label": label, "reason_codes": ["DESCRIPTIVE_CLOSE_RETURN_ONLY"], "basis_horizon": "forward_close_return_5"}


def _trigger_invalidation(
    record: Mapping[str, Any], *, snapshots: Mapping[str, Mapping[str, Any]], chain: Sequence[str],
) -> dict[str, Any]:
    trigger_condition = (record.get("trigger") or {}).get("condition")
    invalidation_condition = (record.get("invalidation") or {}).get("condition")
    if isinstance(trigger_condition, Mapping) or isinstance(invalidation_condition, Mapping):
        return {
            "trigger": retention.evaluate_serialized_close_condition(
                trigger_condition, ticker=str(record.get("ticker")), chain=chain,
                start_session=str(record.get("as_of_session")), snapshots=snapshots,
            ),
            "invalidation": retention.evaluate_serialized_close_condition(
                invalidation_condition, ticker=str(record.get("ticker")), chain=chain,
                start_session=str(record.get("as_of_session")), snapshots=snapshots,
            ),
            "authority_boundary": "SERIALIZED_EXISTING_STRATEGY_CONDITIONS_NOT_TRADE_EXECUTION",
        }
    # Legacy Integrated records preserve levels/states, not a serializable
    # forward-evaluable operator.  Do not guess that a level implies >= or <=.
    return {
        "trigger": {"status": "T0_TRIGGER_EVENT_NOT_EVALUABLE_CONDITION_NOT_RETAINED", "snapshot": record.get("trigger")},
        "invalidation": {"status": "T0_INVALIDATION_EVENT_NOT_EVALUABLE_CONDITION_NOT_RETAINED", "snapshot": record.get("invalidation")},
        "authority_boundary": "RESEARCH_INSTRUMENTATION_NOT_TRADE_EXECUTION",
    }


def feedback_diagnostics(record, *, chain, snapshots, horizon_sessions=5):
    start = record["as_of_session"]
    prefix = chain[:chain.index(start) + horizon_sessions + 1] if start in chain else []
    events = _trigger_invalidation(record, snapshots=snapshots, chain=prefix)
    converted = {}
    for name, role in (("trigger", "confirmation"), ("invalidation", "invalidation")):
        event = events[name]
        status = event.get("status")
        position = prefix.index(event["event_session"]) - prefix.index(start) if event.get("event_session") in prefix else None
        converted[role] = {**event, "status": ("CONFIRMED" if role == "confirmation" else "INVALIDATED") if status == "SATISFIED" else
                           ("NOT_CONFIRMED_YET" if role == "confirmation" else "NOT_INVALIDATED_YET") if status == "NOT_SATISFIED_YET" else "BOUNDARY_NOT_EVALUABLE",
                           "sessions_to_event": position}
    ordering = "NOT_EVALUABLE" if any(e["status"] == "BOUNDARY_NOT_EVALUABLE" for e in converted.values()) else outcome_measurement._ordering(converted["confirmation"], converted["invalidation"])
    if (converted["confirmation"].get("sessions_to_event") is not None and
        converted["confirmation"].get("sessions_to_event") == converted["invalidation"].get("sessions_to_event")):
        ordering = "SAME_SESSION_ORDER_UNRESOLVED"
    return {"confirmation": converted["confirmation"], "invalidation": converted["invalidation"], "event_ordering": ordering,
            "basis_horizon": f"T{horizon_sessions}", "completed_session_window": list(prefix[prefix.index(start)+1:]) if start in prefix else []}


def _feedback_record(*, artifact: Mapping[str, Any], source_path: str, temporal: Mapping[str, Any], record: Mapping[str, Any],
                     snapshots: Mapping[str, Mapping[str, Any]], chain: Sequence[str],
                     t0_snapshot: Mapping[str, Any] | None = None, t0_snapshot_record: Mapping[str, Any] | None = None) -> dict[str, Any]:
    outcome = forward_bridge.evaluate_decision_forward_outcome(
        decision_record=record, p3f9b_snapshot=None, governed_chain=chain, retained_session_snapshots=snapshots,
    )
    if record.get("as_of_session") in chain:
        later_sessions = len(chain) - chain.index(record["as_of_session"]) - 1
    else:
        later_sessions = 0
    for horizon in (outcome.get("horizons") or {}).values():
        if isinstance(horizon, dict):
            horizon["maturation_state"] = retention.maturity_state(
                horizon_status=str(horizon.get("status")), later_completed_sessions=later_sessions,
                required_sessions=int(horizon.get("required_completed_future_sessions") or 0),
            )
    axes = _compact_axes(record)
    coherence = _state(record, "evidence_axis_coherence", "state")
    priority = _state(record, "priority_posture_reconciliation", "research_priority_tier")
    feedback = {
        "decision_identity": record.get("decision_identity"), "ticker": record.get("ticker"),
        "decision_session": artifact.get("session"), "research_action_posture": record.get("research_action_posture", FIELD_NOT_RETAINED),
        "opportunity_priority": priority, "coherence_state": coherence,
        "fundamental_state": _state(record, "fundamental_state"),
        # The fundamental decision-policy epoch the T0 decision was made under (never rewritten).
        "fundamental_decision_policy_version": record.get("fundamental_decision_policy_version", FIELD_NOT_RETAINED),
        "valuation_state": _state(record, "valuation_context_summary", "status"),
        "tactical_structure_state": _state(record, "market_structure_state"),
        "momentum_state": _state(record, "momentum_context", "status"),
        "participation_state": _state(record, "participation", "status"),
        "market_sector_state": _state(record, "market_sector_context", "market_regime"),
        "trigger": record.get("trigger"), "invalidation": record.get("invalidation"),
        "evidence_axes": axes, "source_artifact": {"path": source_path, "identity": artifact.get("artifact_identity"), "observed_at": artifact.get("requested_at")},
        "t0_snapshot_identity": (t0_snapshot or {}).get("snapshot_identity"),
        "t0_snapshot_record_identity": (t0_snapshot_record or {}).get("prospective_snapshot_record_identity"),
        "temporal_qualification": dict(temporal), "forward_outcomes": outcome,
        "trigger_invalidation_outcome": _trigger_invalidation(record, snapshots=snapshots, chain=chain),
    }
    feedback["t0_contract_versions"] = dict((t0_snapshot_record or {}).get("t0_contract_versions") or {
        "integrated_decision_contract": artifact.get("contract_version", FIELD_NOT_RETAINED),
        "research_action_policy_version": artifact.get("research_action_policy_version", record.get("policy_version", FIELD_NOT_RETAINED)),
        "fundamental_policy_version": record.get("fundamental_decision_policy_version", FIELD_NOT_RETAINED),
    })
    feedback["source_type"] = "IMMUTABLE_INTEGRATED_T0" if t0_snapshot else "QUALIFIED_LEGACY_INTEGRATED_T0"
    feedback["known_at"] = (t0_snapshot_record or {}).get("known_at", record.get("known_at", FIELD_NOT_RETAINED))
    feedback["source_identities_at_t0"] = dict(record.get("source_identities") or {})
    feedback["scenario_condition_context_at_t0"] = record.get("scenario_condition_context", FIELD_NOT_RETAINED)
    feedback["forward_driver_context_at_t0"] = record.get("forward_driver_context_at_t0", FIELD_NOT_RETAINED)
    feedback["intrinsic_scenario_at_t0"] = record.get("intrinsic_scenario_at_t0", FIELD_NOT_RETAINED)
    feedback["target_condition_at_t0"] = record.get("target_condition_at_t0", FIELD_NOT_RETAINED)
    feedback["benchmark"] = record.get("benchmark", FIELD_NOT_RETAINED)
    feedback["feedback_diagnostics"] = feedback_diagnostics(record, chain=chain, snapshots=snapshots)
    t5 = (outcome.get("horizons") or {}).get("forward_close_return_5") or {}
    signal = record.get("qualified_tactical_signal_at_t0") or {}
    shim = {"research_action_posture_at_t0": feedback["research_action_posture"], "research_stance_at_t0": FIELD_NOT_RETAINED,
            "horizons": {"T5": {"status": t5.get("status"), "return": t5.get("return")}},
            **feedback["feedback_diagnostics"],
            "qualified_tactical_signal_at_t0": isinstance(signal, Mapping) and signal.get("status") == "CONFIRMED" and bool(signal.get("source_identity"))}
    feedback["feedback_taxonomy"] = outcome_measurement.classify_feedback_taxonomy(shim)
    feedback["outcome_classification"] = _outcome_label(record, outcome)  # legacy descriptive price label, never a false-negative verdict
    return _identity(feedback, "prospective_decision_feedback_record:", "feedback_identity")



SETTLED_CONTRACT_VERSION = "settled_prospective_feedback_contribution/v1"
SETTLED_CACHE_VERSION = "settled_prospective_feedback_cache/v1"
_SETTLED_CACHE_PATH = Path("operations-review/prospective-decision-outcome-feedback-v1/_settled_cache.json")
_SETTLED_MAX_BYTES = 64 * 1024 * 1024
_SETTLED_MAX_ENTRIES = 8192


def _settled_hash(value):
    # Contributions and selected projected inputs are bounded per-record objects.
    # Container/snapshot hashing remains streaming; use the standing fast encoder
    # for these small cache bindings rather than walking every scalar in Python.
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


class SettledFeedbackCache:
    """Run-scoped derived contributions, validated against current dependency content.

    A complete bounded price window is required even for unqualified horizons:
    the standing close-path and diagnostics contain depth-sensitive fields. Open
    conditions never settle. Missing future prices alone do not settle a condition.
    """
    def __init__(self, root, chain, snapshots, *, enabled=True, metrics=None):
        self.root, self.chain, self.snapshots = Path(root), list(chain), snapshots
        self.enabled, self.metrics = enabled, metrics
        self.entries, self.retained, self.session_proofs = {}, {}, {}
        if enabled:
            try:
                path = self.root / _SETTLED_CACHE_PATH
                if path.stat().st_size <= _SETTLED_MAX_BYTES:
                    value = _load_json(path) or {}
                    entries = value.get("entries")
                    if value.get("contract_version") == SETTLED_CACHE_VERSION and isinstance(entries, dict) and len(entries) <= _SETTLED_MAX_ENTRIES:
                        self.entries = entries
            except (OSError, UnicodeError):
                pass

    def _bump(self, name):
        if self.metrics is not None:
            self.metrics[name] = self.metrics.get(name, 0) + 1

    def _proof(self, through):
        prefix = self.chain[:self.chain.index(through) + 1]
        for session in prefix:
            if session not in self.session_proofs:
                snapshot = self.snapshots.get(session)
                self.session_proofs[session] = {
                    "snapshot_identity": (snapshot or {}).get("snapshot_identity"),
                    "content_sha256": retention._hash(snapshot),
                }
        return {"session_sequence": prefix, "snapshots": {s: self.session_proofs[s] for s in prefix}, "terminal_through_session": through}

    def _terminal(self, row):
        start = row["forward_outcomes"]["as_of_session"]
        if start not in self.chain:
            return None  # a later admission of T0 can change the result
        index = self.chain.index(start)
        last = index + max(forward_bridge.FORWARD_HORIZONS.values())
        if last >= len(self.chain):
            return None
        horizons = row["forward_outcomes"]["horizons"]
        if any(h.get("status") not in {forward_bridge.MATURE, forward_bridge.PRICE_NOT_RETAINED, forward_bridge.PRICE_BASIS_INCOMPATIBLE} for h in horizons.values()):
            return None
        for role in ("trigger", "invalidation"):
            event = row["trigger_invalidation_outcome"][role]
            status = event.get("status")
            if status == "SATISFIED" and event.get("event_session") in self.chain:
                last = max(last, self.chain.index(event["event_session"]))
            elif status in {"NOT_MACHINE_EVALUABLE", "T0_TRIGGER_EVENT_NOT_EVALUABLE_CONDITION_NOT_RETAINED", "T0_INVALIDATION_EVENT_NOT_EVALUABLE_CONDITION_NOT_RETAINED"}:
                pass
            elif status == "TEMPORAL_PROVENANCE_UNQUALIFIED" and "STRUCTURAL_CONDITION_T0_SESSION_MISMATCH" in event.get("reason_codes", []):
                pass  # immutable T0 mismatch; extension cannot repair it
            elif status == "PRICE_SERIES_UNQUALIFIED" and "T0_PRICE_BASIS_NOT_RETAINED" in event.get("reason_codes", []):
                pass  # immutable T0 dependency is part of the proof
            else:
                return None
        return self.chain[last]

    def evaluate(self, **kwargs):
        if not self.enabled:
            return _feedback_record(chain=self.chain, snapshots=self.snapshots, **kwargs)
        inputs = dict(kwargs)
        # Feedback only reads the T0 container identity; never rehash every ticker
        # in that container once per decision. The selected record is bound below.
        if isinstance(inputs.get("artifact"), Mapping):
            inputs["artifact"] = {k: v for k, v in inputs["artifact"].items() if k != "records"}
        if isinstance(inputs.get("t0_snapshot"), Mapping):
            inputs["t0_snapshot"] = {k: v for k, v in inputs["t0_snapshot"].items() if k != "records"}
        binding = {"contract_version": SETTLED_CONTRACT_VERSION,
                   "feedback_contract": CONTRACT_VERSION, "forward_contract": forward_bridge.CONTRACT_VERSION,
                   "condition_contract": retention.CONDITION_CONTRACT_VERSION,
                   "outcome_contract": outcome_measurement.CONTRACT_VERSION,
                   "policy": OUTCOME_POLICY_CONSTANTS, "horizons": forward_bridge.FORWARD_HORIZONS,
                   "inputs": inputs}
        key = _settled_hash(binding)
        entry = self.entries.get(key)
        try:
            if isinstance(entry, dict):
                body = {k: v for k, v in entry.items() if k != "contribution_identity"}
                through = entry["proof"]["terminal_through_session"]
                if (entry.get("binding_sha256") == key and through in self.chain
                        and entry["proof"] == self._proof(through)
                        and entry["contribution_identity"] == _settled_hash(body)
                        and self._terminal(entry["feedback"]) == through):
                    self.retained[key] = entry
                    self._bump("settled_hits")
                    return entry["feedback"]
        except (KeyError, TypeError, ValueError):
            pass
        self._bump("settled_misses")
        row = _feedback_record(chain=self.chain, snapshots=self.snapshots, **kwargs)
        through = self._terminal(row)
        if through is not None:
            entry = {"contract_version": SETTLED_CONTRACT_VERSION, "binding_sha256": key,
                     "proof": self._proof(through), "feedback": row}
            entry["contribution_identity"] = _settled_hash(entry)
            self.retained[key] = entry
        return row

    def finish(self):
        if not self.enabled:
            return
        temporary = None
        try:
            entries, size = {}, 128
            for key, value in sorted(self.retained.items()):
                added = len(_canon({key: value}).encode("utf-8")) + 1
                if len(entries) >= _SETTLED_MAX_ENTRIES or size + added > _SETTLED_MAX_BYTES:
                    continue
                entries[key], size = value, size + added
            payload = _canon({"contract_version": SETTLED_CACHE_VERSION, "entries": entries}).encode("utf-8")
            if len(payload) > _SETTLED_MAX_BYTES:
                return
            path = self.root / _SETTLED_CACHE_PATH
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".settled-", suffix=".tmp", delete=False) as out:
                temporary = Path(out.name)
                out.write(payload)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, path)
        except (OSError, TypeError, ValueError):
            pass
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def _by_policy_epoch(groups: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    """Split every outcome group by fundamental decision-policy epoch: decisions made under
    different fundamental policies are never pooled or compared (NOT_COMPARABLE_POLICY_CHANGE)."""
    split: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for value, members in groups.items():
        for item in members:
            split[(str(item.get("fundamental_decision_policy_version")), value)].append(item)
    return split


def _summary(groups: Mapping[str, Sequence[Mapping[str, Any]]], *, dimension: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for (epoch, value), members in sorted(_by_policy_epoch(groups).items()):
        mature = [
            item for item in members
            if (item["forward_outcomes"]["horizons"].get("forward_close_return_5") or {}).get("status") == forward_bridge.MATURE
        ]
        row = {"dimension": dimension, "value": value, "fundamental_decision_policy_version": epoch,
               "sample_size": len(members), "mature_T5_sample_size": len(mature)}
        if mature:
            returns = [item["forward_outcomes"]["horizons"]["forward_close_return_5"]["return"] for item in mature]
            excursions = [item["forward_outcomes"]["close_path_by_horizon"]["close_excursion_5"] for item in mature]
            row.update({
                "median_forward_return_T5": _median(returns),
                "observed_positive_rate_T5": {"value": sum(value > 0 for value in returns) / len(returns), "N": len(returns)},
                "median_CLOSE_MFE_T5": _median([item["CLOSE_MFE"] for item in excursions if item.get("status") == forward_bridge.MATURE]),
                "median_CLOSE_MAE_T5": _median([item["CLOSE_MAE"] for item in excursions if item.get("status") == forward_bridge.MATURE]),
            })
        rows.append(row)
    return {"groups": rows, "authority_boundary": "DESCRIPTIVE_SAMPLE_STATISTICS_NOT_CALIBRATION_OR_CAUSAL_RANKING",
            "cross_policy_epoch_comparison": fundamental_signals.NOT_COMPARABLE_POLICY_CHANGE}


def _false_negatives(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    conservative = {"WAIT_FOR_CONFIRMATION", "EARLY_WATCH", "INSUFFICIENT_CURRENT_RESEARCH", "AVOID"}
    for item in records:
        h5 = item["forward_outcomes"]["horizons"].get("forward_close_return_5") or {}
        if (item["research_action_posture"] not in conservative or h5.get("status") != forward_bridge.MATURE or
            (item.get("feedback_taxonomy") or {}).get("label") not in {"MISSED_BREAKOUT", "POSSIBLE_FALSE_NEGATIVE", "POLICY_TOO_DEFENSIVE", "TACTICAL_SIGNAL_NOT_INTEGRATED"}):
            continue
        if h5.get("return", 0.0) < OUTCOME_POLICY_CONSTANTS["material_upside_return_greater_than_or_equal_to"]:
            continue
        axes = item["evidence_axes"]
        explanation = "FEATURE_FITNESS_MISSING" if axes["status"] == FIELD_NOT_RETAINED else "POLICY_TOO_CONSERVATIVE_CANDIDATE"
        findings.append({"feedback_identity": item["feedback_identity"], "ticker": item["ticker"], "decision_identity": item["decision_identity"], "posture": item["research_action_posture"], "T5_return": h5["return"], "evidence_at_T0": axes, "trigger": item["trigger"], "coherence_state": item["coherence_state"], "likely_explanation": explanation})
    return findings


def _failed_setups(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    entry_postures = {"INITIATE_ON_BREAKOUT", "ACCUMULATE_ON_RETEST"}
    for item in records:
        h5 = item["forward_outcomes"]["horizons"].get("forward_close_return_5") or {}
        if item["research_action_posture"] not in entry_postures or h5.get("status") != forward_bridge.MATURE:
            continue
        if h5.get("return", 0.0) >= OUTCOME_POLICY_CONSTANTS["adverse_return_strictly_less_than"]:
            continue
        findings.append({"feedback_identity": item["feedback_identity"], "ticker": item["ticker"], "decision_identity": item["decision_identity"], "posture": item["research_action_posture"], "T5_return": h5["return"], "classification": "NORMAL_MARKET_UNCERTAINTY", "reason": "NO_FORWARD_EVALUABLE_T0_INVALIDATION_CONDITION_RETAINED"})
    return findings


def build_feedback_artifact(root: str | Path, *, resolved_context: dict | None = None,
                            use_summary_cache: bool = True, use_settled_cache: bool = True,
                            cache_metrics: dict[str, int] | None = None) -> dict[str, Any]:
    """Build a deterministic retained-only feedback artifact for the local corpus."""
    corpus = discover_prospective_corpus(root, payload_projection=_project_artifact_for_feedback,
                                        use_summary_cache=use_summary_cache, cache_metrics=cache_metrics)
    modern = _modern_snapshot_candidates(root)
    legacy_chain = corpus["qualified_session_chain"]
    legacy_snapshots = retained_session_snapshots(root, legacy_chain)
    completed_chain, completed_snapshots = resolve_completed_market_observations(root)
    # Fixture/legacy qualified snapshots already prove completion under the standing contract.
    # Actual market handoffs admit observations even when that session has no T0 case.
    chain = sorted(set(completed_chain) | set(legacy_chain) | set(modern["chain"]))
    snapshots = {**completed_snapshots, **legacy_snapshots, **modern["snapshots"]}
    if resolved_context is not None:
        resolved_context.update(chain=chain, snapshots=snapshots)
    settled = SettledFeedbackCache(root, chain, snapshots, enabled=use_settled_cache, metrics=cache_metrics)
    records: list[dict[str, Any]] = []
    # Modern snapshots are the sole T0 source for future runs.  Their full
    # decision content, condition serialization and T0 close facts were sealed
    # before the canonical handoff; a later mutable integrated-artifact path is
    # therefore never consulted here.
    for candidate in modern["genuine"]:
        snapshot = candidate["snapshot"]
        inventory = candidate["inventory"]
        source = snapshot.get("source_integrated_decision_artifact") or {}
        artifact = {
            "session": snapshot.get("session"), "artifact_identity": source.get("artifact_identity"),
            "contract_version": source.get("contract_version", FIELD_NOT_RETAINED), "requested_at": None,
        }
        temporal = {
            "contract_version": TEMPORAL_CONTRACT_VERSION, "status": GENUINE,
            "decision_session": snapshot.get("session"),
            "decision_artifact_identity": source.get("artifact_identity"),
            "daily_session_operation_identity": snapshot.get("daily_session_operation_identity"),
            "canonical_handoff_path": inventory.get("canonical_handoff_path"),
            "operation_manifest_path": inventory.get("operation_manifest_path"),
            "proof_reason_codes": inventory.get("proof_reason_codes"),
        }
        for ticker, retained in sorted((snapshot.get("records") or {}).items()):
            if not isinstance(retained, Mapping):
                continue
            decision = retained.get("integrated_decision_at_t0")
            if not isinstance(decision, Mapping) or decision.get("ticker") != ticker:
                continue
            records.append(settled.evaluate(
                artifact=artifact, source_path=inventory["snapshot_path"], temporal=temporal,
                record=decision,
                t0_snapshot=snapshot, t0_snapshot_record=retained,
            ))
    # Legacy candidates retain their prior conservative qualification.  They
    # remain useful only for the fields they actually captured at T0.
    for candidate in corpus["genuine_artifacts"]:
        artifact = candidate["artifact"]
        for ticker, decision in sorted((artifact.get("records") or {}).items()):
            if not isinstance(decision, Mapping) or decision.get("ticker") != ticker:
                continue
            records.append(settled.evaluate(artifact=artifact, source_path=candidate["artifact_path"], temporal=candidate["temporal"], record=decision))
    settled.finish()
    records.sort(key=lambda row: (str(row["decision_session"]), str(row["ticker"]), str(row["decision_identity"])))
    by_posture: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_coherence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_axis: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        by_posture[str(row["research_action_posture"])].append(row)
        by_coherence[str(row["coherence_state"])].append(row)
        axes = row["evidence_axes"]
        if axes["status"] == FIELD_NOT_RETAINED:
            by_axis[FIELD_NOT_RETAINED].append(row)
        else:
            for name, axis in axes["axis_states"].items():
                by_axis[name + ":" + str(axis.get("state"))].append(row)
    false_negatives = _false_negatives(records)
    failed_setups = _failed_setups(records)
    horizon_coverage = {
        name: dict(sorted(Counter(row["forward_outcomes"]["horizons"][name]["status"] for row in records).items()))
        for name in forward_bridge.FORWARD_HORIZONS
    }
    required = {
        ticker: [row for row in records if row["ticker"] == ticker] or [{"ticker": ticker, "status": "NO_PROSPECTIVE_CASE"}]
        for ticker in REQUIRED_TICKERS
    }
    policy_candidates = [{
        "disposition": "MORE_PROSPECTIVE_EVIDENCE_REQUIRED", "current_rule": "Outcome feedback never mutates current daily posture policy.",
        "observed_prospective_counterexamples": len(false_negatives) + len(failed_setups), "sample_size": sum(1 for row in records if row["forward_outcomes"]["horizons"]["forward_close_return_5"]["status"] == forward_bridge.MATURE),
        "why_current_rule_may_be_too_restrictive_or_loose": "No mature T5 close-return sample exists in the temporally qualified corpus.",
        "possible_bounded_change": None, "expected_affected_cohort": None, "risk_of_change": "LOOK_AHEAD_OR_THIN_SAMPLE_OVERFIT", "evidence_strength": "INSUFFICIENT", "policy_mutated": False,
    }]
    corpus_health = retention.build_corpus_health(
        snapshot_inventory=modern["discovery"], feedback_artifact={"feedback_records": records},
    )
    artifact = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "outcome_policy_constants": OUTCOME_POLICY_CONSTANTS,
        "prospective_corpus": {"candidate_artifact_count": len(corpus["inventory"]), "genuine_artifact_count": len(corpus["genuine_artifacts"]), "immutable_snapshot_count": len(modern["discovery"]["inventory"]), "genuine_immutable_snapshot_count": len(modern["genuine"]), "genuine_decision_count": len(records), "unique_sessions": sorted(set(legacy_chain) | set(modern["chain"])), "unique_tickers": len({row["ticker"] for row in records}), "classification_counts": corpus["classification_counts"], "snapshot_classification_counts": modern["discovery"]["classification_counts"]},
        "temporal_qualification": {"artifact_inventory": corpus["inventory"], "immutable_snapshot_inventory": modern["discovery"]["inventory"], "handoff_snapshot_inventory": modern["discovery"]["handoff_snapshot_inventory"], "qualified_session_chain": chain, "retained_snapshot_sessions": sorted(set(legacy_snapshots) | set(modern["snapshots"])), "temporal_gate": "LEGACY_CANONICAL_HANDOFF_OR_IMMUTABLE_T0_SNAPSHOT_PLUS_RETAINED_DAILY_OPERATION"},
        "feedback_records": records, "forward_outcome_coverage": {"horizons": horizon_coverage, "close_excursions": {"CLOSE_MFE_CLOSE_MAE_ONLY": True, "intraday_mfe_mae": "NOT_CLAIMED"}},
        "posture_outcome_summary": _summary(by_posture, dimension="research_action_posture"),
        "coherence_outcome_summary": _summary(by_coherence, dimension="evidence_axis_coherence"),
        "evidence_axis_outcome_summary": _summary(by_axis, dimension="evidence_axis_state"),
        "false_negative_cases": false_negatives, "failed_setup_cases": failed_setups,
        "trigger_invalidation_outcomes": [row["trigger_invalidation_outcome"] | {"feedback_identity": row["feedback_identity"], "ticker": row["ticker"]} for row in records],
        "prospective_corpus_health": corpus_health,
        "policy_diagnostic_candidates": policy_candidates, "required_ticker_cases": required,
        "authority_boundary": {"downstream_observation_only": True, "no_retroactive_recommendation_reconstruction": True, "no_policy_mutation": True, "no_probability_or_calibration": True, "no_raw_as_traded_or_pit_authority": True, "no_daily_decision_feedback_loop": True},
    }
    return _identity(artifact, "prospective_decision_outcome_feedback:")


def evidence_views(artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Small, non-duplicative views used by the milestone evidence package."""
    return {
        "prospective_corpus_inventory.json": {"prospective_corpus": artifact["prospective_corpus"], "artifact_inventory": artifact["temporal_qualification"]["artifact_inventory"], "required_ticker_cases": artifact["required_ticker_cases"]},
        "temporal_qualification.json": artifact["temporal_qualification"],
        "forward_outcome_coverage.json": artifact["forward_outcome_coverage"],
        "posture_outcome_summary.json": artifact["posture_outcome_summary"],
        "coherence_outcome_summary.json": artifact["coherence_outcome_summary"],
        "evidence_axis_outcome_summary.json": artifact["evidence_axis_outcome_summary"],
        "false_negative_cases.json": {"cases": artifact["false_negative_cases"], "sample_note": "Only temporally-qualified, mature T5 cases may appear."},
        "failed_setup_cases.json": {"cases": artifact["failed_setup_cases"], "sample_note": "Only temporally-qualified, mature T5 entry-relevant cases may appear."},
        "trigger_invalidation_outcomes.json": {"outcomes": artifact["trigger_invalidation_outcomes"], "authority_boundary": "NO_TRADE_EXECUTION_OR_INFERRED_BOUNDARY_OPERATOR"},
        "prospective_corpus_health.json": artifact["prospective_corpus_health"],
        "policy_diagnostic_candidates.json": {"candidates": artifact["policy_diagnostic_candidates"], "policy_mutated": False},
        "product_feedback_gap_matrix.json": {
            "gaps": [
                {"area": "forward_close_depth", "state": "PARTIAL_BY_EVIDENCE", "detail": "Only retained canonical sessions and exact close snapshots are used."},
                {"area": "evidence_axis_snapshot", "state": "FIELD_NOT_RETAINED_AT_T0", "detail": "Qualified legacy artifacts predate additive axis snapshots; no backfill is allowed."},
                {"area": "trigger_invalidation", "state": "BOUNDARY_OPERATOR_NOT_RETAINED_AT_T0", "detail": "Levels/states are retained but not a forward-evaluable condition."},
                {"area": "intraday_excursion", "state": "UNAVAILABLE_HIGH_LOW_BASIS", "detail": "Only CLOSE_MFE/CLOSE_MAE are emitted."},
            ],
            "authority_boundary": artifact["authority_boundary"],
        },
    }
