"""Fail-closed execution-environment contract for owner-facing canonical Daily.

This module intentionally owns *environment* qualification only.  It never performs a
provider request, mutates a registry, writes an artifact, or changes analytical authority.
Keeping these checks ahead of ``acquire_and_materialize`` means a checkout problem cannot spend
market-data budget before a deterministic refusal explains what is wrong.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping


RUNTIME_ROOT_ENV = "STOCK_LOOKUP_RUNTIME_ROOT"
RETAINED_EVIDENCE_ROOT_ENV = "STOCK_LOOKUP_RETAINED_EVIDENCE_ROOT"
OUTPUT_ROOT_ENV = "STOCK_LOOKUP_OPERATION_OUTPUT_ROOT"
NO_NEW_PROVIDER_ACQUISITION = "NO_NEW_PROVIDER_ACQUISITION"


class DailyExecutionEnvironmentError(RuntimeError):
    """A pre-acquisition refusal with a stable, owner-visible code."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(code + (":" + detail if detail else ""))


@dataclass(frozen=True)
class DailyExecutionRoots:
    producer_code_root: Path
    retained_evidence_root: Path
    runtime_root: Path | None
    output_root: Path


def _configured_path(value: str | Path | None) -> Path | None:
    if value is None or not str(value).strip():
        return None
    return Path(value).expanduser().resolve()


def resolve_roots(
    producer_code_root: Path,
    *,
    runtime_root: str | Path | None = None,
    retained_evidence_root: str | Path | None = None,
    output_root: str | Path | None = None,
) -> DailyExecutionRoots:
    """Resolve the three roots without guessing a worktree-parent sibling.

    Legacy production remains compatible: a producer checkout directly below a workspace may
    use its adjacent ``dashboard-runtime`` when no explicit runtime is supplied.  A checkout in
    a ``worktrees`` directory deliberately has no such fallback and must be configured.
    """
    producer = Path(producer_code_root).expanduser().resolve()
    retained = _configured_path(retained_evidence_root) or _configured_path(os.environ.get(RETAINED_EVIDENCE_ROOT_ENV)) or producer
    output = _configured_path(output_root) or _configured_path(os.environ.get(OUTPUT_ROOT_ENV)) or producer
    explicit_runtime = _configured_path(runtime_root) or _configured_path(os.environ.get(RUNTIME_ROOT_ENV))
    if explicit_runtime is None and producer.parent.name.lower() != "worktrees":
        adjacent = producer.parent / "dashboard-runtime"
        if adjacent.is_dir():
            explicit_runtime = adjacent.resolve()
    return DailyExecutionRoots(producer, retained, explicit_runtime, output)


def _git(root: Path, *args: str) -> tuple[int, str]:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, encoding="utf-8",
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
    )
    return result.returncode, result.stdout.strip()


def producer_release_qualification(producer_root: Path) -> dict[str, Any]:
    """Require a clean checkout exactly at the locally governed ``origin/main`` ref."""
    root = Path(producer_root)
    code, head = _git(root, "rev-parse", "HEAD")
    origin_code, origin_main = _git(root, "rev-parse", "origin/main")
    dirty_code, dirty = _git(root, "status", "--porcelain")
    result = {
        "producer_code_root": str(root), "head": head or None,
        "origin_main": origin_main or None, "dirty": bool(dirty),
        "qualified": False,
    }
    if code or origin_code or dirty_code:
        result["reason_code"] = "GIT_RELEASE_AUTHORITY_UNAVAILABLE"
        return result
    if dirty:
        result["reason_code"] = "RELEASE_CHECKOUT_DIRTY"
        return result
    if head != origin_main:
        result["reason_code"] = "RELEASE_CHECKOUT_NOT_AT_ORIGIN_MAIN"
        return result
    result.update(qualified=True, reason_code="PASS")
    return result


def _artifact_contract(path: Path, expected_contract: str | None) -> str | None:
    if not path.is_file():
        return "MISSING"
    # Companion record streams and diagnostics are governed by the enclosing Financial V2
    # authority artifact.  They are not standalone JSON contracts and therefore cannot be asked
    # to carry an artifact identity of their own.
    if expected_contract is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "UNREADABLE_OR_INVALID_JSON"
    if expected_contract and payload.get("contract_version") != expected_contract:
        return "CONTRACT_MISMATCH"
    identity = payload.get("artifact_identity") or payload.get("snapshot_identity")
    if not isinstance(identity, str) or not identity:
        return "IDENTITY_MISSING"
    return None


def required_retained_inputs(
    retained_root: Path,
    session: str,
    *,
    producer_registry_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Return the bounded static/governed closure required before Daily acquisition.

    Current-session products are intentionally absent: they are outputs, not evidence that may be
    silently copied from another operation.  The list mirrors the static inputs reached by the
    Level-2 builders and the pinned Financial V2 authority resolver.
    """
    from daily_session_level2_package import session_artifact_paths
    import financial_v2_current_input_authority as financial_authority

    root = Path(retained_root)
    registry_root = Path(producer_registry_root or root)
    paths = session_artifact_paths(root, session)
    items: list[tuple[str, Path, str | None]] = [
        ("research_universe_qualification", root / "operations-review" / "market-wide-current-research-universe-qualification-v1-20260823" / "market_wide_current_research_universe_artifact.json", "market_wide_current_research_universe/v1"),
        ("fundamental_retained_context", paths["fundamental"], "market_wide_current_fundamental_research/v1"),
        ("official_universe", paths["official_universe"], "current_official_market_universe/v1"),
        ("official_event_context", paths["official_event_context"], "current_official_event_context/v1"),
        ("catalyst_context", paths["catalyst"], "catalyst_event_research_context/v1"),
        ("historical_research_context", paths["historical_context"], "market_wide_historical_research_context/v1"),
        ("financial_momentum_context", paths["financial_momentum"], "current_financial_momentum_context/v1"),
        ("corporate_event_context", paths["corporate_event_context"], "current_corporate_event_context/v1"),
    ]
    try:
        authority = financial_authority.resolve(root)
        for name in (
            "semantics_artifact_path", "semantics_facts_path", "feature_store_artifact_path",
            "feature_store_records_path", "classification_diagnostics_path", "industry_snapshot_path",
        ):
            items.append(("financial_v2_" + name.removesuffix("_path"), getattr(authority, name), None))
    except Exception:
        # Resolve failure is represented as exact missing authority entries below rather than
        # being allowed to escape as a generic FileNotFoundError after acquisition starts.
        items.append(("financial_v2_current_input_authority", root / "operations-review" / "financial-v2-current-input-authority", None))

    result: list[dict[str, Any]] = []
    for name, path, contract in items:
        reason = _artifact_contract(path, contract)
        result.append({
            "contract": name, "path": str(path), "expected_contract_version": contract,
            "status": "AVAILABLE" if reason is None else "UNAVAILABLE", "reason_code": reason,
        })

    # The registry is intentionally resolved from the Producer checkout.  It is mutable control
    # state, so allowing a retained-evidence checkout to supply it would silently let a different
    # release decide which previous session is governed.  The selected prior bundle itself is
    # immutable retained evidence and must live under ``root``.
    registry_path = registry_root / "config" / "daily_research_session_input_registry.json"
    registry: Mapping[str, Any] | None = None
    registry_reason: str | None = None
    try:
        candidate = json.loads(registry_path.read_text(encoding="utf-8"))
        if not isinstance(candidate, Mapping) or candidate.get("contract_version") != "daily_research_session_input_registry/v1":
            registry_reason = "CONTRACT_MISMATCH"
        else:
            registry = candidate
    except (OSError, ValueError):
        registry_reason = "UNREADABLE_OR_INVALID_JSON" if registry_path.is_file() else "MISSING"
    result.append({
        "contract": "producer_session_input_registry",
        "path": str(registry_path),
        "expected_contract_version": "daily_research_session_input_registry/v1",
        "status": "AVAILABLE" if registry is not None else "UNAVAILABLE",
        "reason_code": registry_reason,
    })
    if registry is not None:
        completed = registry.get("completed_sessions")
        previous = sorted(
            str(candidate_session)
            for candidate_session, row in (completed or {}).items()
            if str(candidate_session) < session
            and isinstance(row, Mapping)
            and row.get("status") == "COMPLETED_RETAINED_EVIDENCE"
        )
        if previous:
            prior = previous[-1]
            candidates: list[Path] = []
            for bundle in (root / "operations-review" / "daily-research-session-operations-v1" / prior).glob("*/ai_research_session_bundle.json"):
                try:
                    payload = json.loads(bundle.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if payload.get("session") == prior and isinstance(payload.get("operation_identity"), str):
                    candidates.append(bundle)
            previous_reason = None if len(candidates) == 1 else (
                "MISSING" if not candidates else "AMBIGUOUS_GOVERNED_PREVIOUS_OPERATION"
            )
            result.append({
                "contract": "governed_previous_session_bundle",
                "path": str(candidates[0]) if len(candidates) == 1 else str(root / "operations-review" / "daily-research-session-operations-v1" / prior),
                "expected_contract_version": "governed_previous_session_bundle/via_operation_identity",
                "status": "AVAILABLE" if previous_reason is None else "UNAVAILABLE",
                "reason_code": previous_reason,
                "previous_session": prior,
            })
        else:
            result.append({
                "contract": "governed_previous_session_bundle",
                "path": None,
                "expected_contract_version": "governed_previous_session_bundle/via_operation_identity",
                "status": "AVAILABLE",
                "reason_code": "NOT_APPLICABLE_NO_PRIOR_COMPLETED_SESSION",
                "previous_session": None,
            })
    return result


def missing_retained_inputs(
    retained_root: Path,
    session: str,
    *,
    producer_registry_root: Path | None = None,
) -> list[dict[str, Any]]:
    return [
        row for row in required_retained_inputs(
            retained_root, session, producer_registry_root=producer_registry_root,
        ) if row["status"] != "AVAILABLE"
    ]


def _snapshot_plan(output_root: Path, session: str) -> list[dict[str, Any]]:
    from daily_session_level2_package import _canonical_snapshot_gate_satisfied, session_artifact_paths
    from field_temporal_contract import stable_id

    paths = session_artifact_paths(output_root, session)
    snapshot_path = paths["exact_session_snapshot"]
    snapshot: Mapping[str, Any] | None = None
    valid = False
    evidence_path = paths["multi_source_market_evidence"]
    if snapshot_path.is_file():
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            evidence = json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.is_file() else None
            identity_payload = copy.deepcopy(snapshot)
            stored_sha = identity_payload.pop("snapshot_sha256", None)
            identity_payload.pop("snapshot_identity", None)
            records = snapshot.get("records")
            candidate_count = snapshot.get("candidate_count")
            exact_count = snapshot.get("exact_session_observed_count")
            valid = (
                snapshot.get("contract_version") == "p3f9_exact_session_mva_snapshot/v2"
                and snapshot.get("resolved_completed_session") == session
                and isinstance(stored_sha, str)
                and stable_id(identity_payload) == stored_sha
                and snapshot.get("snapshot_identity") == "p3f9_exact_session_snapshot:" + stored_sha
                and snapshot.get("materialization_scope") == "FULL_CANONICAL_CANDIDATE_SET"
                and isinstance(records, Mapping)
                and candidate_count == len(records)
                and isinstance(exact_count, int) and exact_count >= 0
                and isinstance(evidence, Mapping)
                and evidence.get("contract_version") == "multi_source_exact_session_market_evidence/v1"
                and evidence.get("target_session") == session
                and _canonical_snapshot_gate_satisfied(snapshot_path, evidence_path)
            )
        except (OSError, ValueError, TypeError):
            valid = False
    records = snapshot.get("records") if isinstance(snapshot, Mapping) else {}
    count = len(records) if isinstance(records, Mapping) else 0
    result = [{
        "component": "EXACT_SESSION_SNAPSHOT",
        "classification": "REUSABLE_QUALIFIED" if valid else "REQUIRES_PROVIDER_ACQUISITION",
        "provider_call_class": "EXACT_SESSION_MARKET_ACQUISITION" if not valid else None,
        "expected_provider_calls": 0 if valid else "MARKET_WIDE_EXACT_SESSION_ACQUISITION",
        "path": str(snapshot_path),
    }]
    result.append({
        "component": "BREADTH_AND_UNIVERSE_RESOLUTION",
        "classification": "REUSABLE_QUALIFIED" if paths["universe_resolution"].is_file() else "RECOMPUTABLE_FROM_RETAINED_INPUTS",
        "provider_call_class": None, "expected_provider_calls": 0,
    })
    result.append({
        "component": "LIQUIDITY_RESEARCH",
        "classification": "REUSABLE_QUALIFIED" if paths["liquidity_research"].is_file() else "REQUIRES_PROVIDER_ACQUISITION",
        "provider_call_class": None if paths["liquidity_research"].is_file() else "DNSE_TRADES_LATEST_AND_OHLC_PER_CANDIDATE",
        "expected_provider_calls": 0 if paths["liquidity_research"].is_file() else 2 * count,
    })
    result.append({
        "component": "TECHNICAL_RECOVERY",
        "classification": "REUSABLE_QUALIFIED" if paths["technical_recovery"].is_file() else "REQUIRES_PROVIDER_ACQUISITION",
        "provider_call_class": None if paths["technical_recovery"].is_file() else "DNSE_OHLC_WITH_FEATURE_SAFE_RECOVERY",
        "expected_provider_calls": 0 if paths["technical_recovery"].is_file() else "ONE_OR_MORE_PER_RECOVERY_CANDIDATE",
    })
    result.append({
        "component": "DOWNSTREAM_DETERMINISTIC_PRODUCTS",
        "classification": "RECOMPUTABLE_FROM_RETAINED_INPUTS",
        "provider_call_class": None, "expected_provider_calls": 0,
    })
    return result


def build_resume_plan(
    output_root: Path,
    session: str,
    *,
    missing_retained_contracts: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Classify every known boundary before acquisition is allowed.

    A missing retained contract is deliberately part of the plan, rather than merely a
    preflight error string.  This keeps an owner-visible distinction between a component
    that can be recomputed, one that would need a provider request, and one which has no
    governed input from which it may safely proceed.
    """
    components = _snapshot_plan(Path(output_root), session)
    components.extend({
        "component": "RETAINED_INPUT:" + contract,
        "classification": "BLOCKED_MISSING_GOVERNED_INPUT",
        "provider_call_class": None,
        "expected_provider_calls": 0,
    } for contract in missing_retained_contracts)
    provider_components = [row for row in components if row["classification"] == "REQUIRES_PROVIDER_ACQUISITION"]
    return {
        "contract_version": "daily_execution_environment_resume_plan/v1",
        "session": session,
        "components": components,
        "provider_required_components": [row["component"] for row in provider_components],
        "provider_acquisition_permitted_by_default": True,
    }


def preflight_canonical_daily(
    producer_code_root: Path,
    *,
    session: str,
    runtime_root: str | Path | None = None,
    retained_evidence_root: str | Path | None = None,
    output_root: str | Path | None = None,
    no_new_provider_acquisition: bool = False,
) -> dict[str, Any]:
    """Evaluate every production-environment gate before provider acquisition."""
    roots = resolve_roots(
        producer_code_root, runtime_root=runtime_root,
        retained_evidence_root=retained_evidence_root, output_root=output_root,
    )
    release = producer_release_qualification(roots.producer_code_root)
    runtime_reason = None
    if roots.runtime_root is None:
        runtime_reason = "RUNTIME_ROOT_UNCONFIGURED"
    elif not roots.runtime_root.is_dir():
        runtime_reason = "RUNTIME_ROOT_UNAVAILABLE"
    elif not (roots.runtime_root / "vn_stock.db").is_file():
        runtime_reason = "RUNTIME_CAPABILITY_VN_STOCK_DB_MISSING"
    retained = required_retained_inputs(
        roots.retained_evidence_root,
        session,
        producer_registry_root=roots.producer_code_root,
    )
    missing = [row for row in retained if row["status"] != "AVAILABLE"]
    plan = build_resume_plan(
        roots.output_root,
        session,
        missing_retained_contracts=[row["contract"] for row in missing],
    )
    failure: str | None = None
    detail = ""
    if not release["qualified"]:
        failure, detail = "FAILED_PREFLIGHT_PRODUCER:RELEASE_CHECKOUT_NOT_QUALIFIED", str(release.get("reason_code"))
    elif runtime_reason:
        failure, detail = "FAILED_PREFLIGHT_RUNTIME:CAPABILITY_NOT_QUALIFIED", runtime_reason
    elif missing:
        failure = "FAILED_PREFLIGHT_RETAINED_EVIDENCE:STATIC_DEPENDENCY_UNAVAILABLE"
        detail = ",".join(row["contract"] for row in missing)
    elif no_new_provider_acquisition and plan["provider_required_components"]:
        failure = "FAILED_PREFLIGHT_RESUME:NO_NEW_PROVIDER_ACQUISITION_COMPONENTS_REQUIRED"
        detail = ",".join(plan["provider_required_components"])
    return {
        "contract_version": "daily_production_execution_environment_preflight/v1",
        "session": session,
        "roots": {
            "producer_code_root": str(roots.producer_code_root),
            "retained_evidence_root": str(roots.retained_evidence_root),
            "runtime_root": str(roots.runtime_root) if roots.runtime_root else None,
            "output_root": str(roots.output_root),
        },
        "producer_release": release,
        "runtime": {"status": "PASS" if runtime_reason is None else "BLOCKED", "reason_code": runtime_reason},
        "retained_inputs": retained,
        "missing_retained_contracts": [row["contract"] for row in missing],
        "resume_plan": plan,
        "no_new_provider_acquisition": no_new_provider_acquisition,
        "status": "PASS" if failure is None else "BLOCKED",
        "failure_code": failure,
        "failure_detail": detail or None,
    }


def require_preflight(**kwargs: Any) -> dict[str, Any]:
    result = preflight_canonical_daily(**kwargs)
    if result["status"] != "PASS":
        raise DailyExecutionEnvironmentError(str(result["failure_code"]), str(result.get("failure_detail") or ""))
    return result


def format_preflight(result: Mapping[str, Any]) -> str:
    roots = result["roots"]
    release = result["producer_release"]
    plan = result["resume_plan"]
    lines = [
        "DAILY_EXECUTION_PREFLIGHT",
        f"PREFLIGHT_STATUS: {result['status']}",
        f"PRODUCER_QUALIFICATION: {'PASS' if release.get('qualified') else 'BLOCKED'}",
        f"PRODUCER_HEAD: {release.get('head') or 'UNRESOLVED'}",
        f"RELEASE_AUTHORITY: {release.get('origin_main') or 'UNRESOLVED'}",
        f"RUNTIME_ROOT: {roots.get('runtime_root') or 'UNCONFIGURED'}",
        f"RETAINED_EVIDENCE_ROOT: {roots['retained_evidence_root']}",
        f"OUTPUT_ROOT: {roots['output_root']}",
        f"INTENDED_SESSION: {result['session']}",
        "PROVIDER_REQUIRED_COMPONENTS: " + (",".join(plan["provider_required_components"]) or "NONE"),
    ]
    if result.get("failure_code"):
        lines.append("REFUSAL: " + str(result["failure_code"]) + (":" + str(result["failure_detail"]) if result.get("failure_detail") else ""))
    return "\n".join(lines)
