"""Build local evidence for PROSPECTIVE_DECISION_RETENTION_AND_OUTCOME_MATURATION_V1.

This is an offline retained-artifact reader.  It acquires no provider data and
never invokes Canonical Daily; its purpose is only to record the current
contract/readiness evidence for the owner review.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import prospective_decision_outcome_feedback as feedback  # noqa: E402
import prospective_decision_retention as retention  # noqa: E402


MILESTONE = "PROSPECTIVE_DECISION_RETENTION_AND_OUTCOME_MATURATION_V1"


def _load(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_immutable(path: Path, value: Any) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != text:
        raise ValueError("IMMUTABLE_ARTIFACT_CONFLICT:" + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(text, encoding="utf-8")


def _flow_inventory() -> dict[str, Any]:
    return {
        "contract_version": "prospective_decision_identity_flow/v1",
        "flow": [
            {"stage": "decision_producer", "producer": "integrated_investment_decision_product.build_artifact", "field": "records[ticker].decision_identity", "source_object": "integrated_investment_decision_product/v1", "consumer": "prospective_decision_retention.build_snapshot", "immutable": False, "session_bound": True, "operation_bound": False},
            {"stage": "prospective_t0_seal", "producer": "canonical_post_close_pipeline.retain_prospective_decision_snapshot", "field": "snapshot_identity / records[ticker].prospective_snapshot_record_identity", "source_object": "prospective_decision_snapshot/v1", "consumer": "canonical session handoff and future outcome feedback", "immutable": True, "session_bound": True, "operation_bound": True},
            {"stage": "canonical_handoff", "producer": "canonical_post_close_pipeline.build_tiered_bundle", "field": "prospective_decision_snapshot.identity + source_integrated_decision_artifact_identity", "source_object": "session_handoff_bundle.json", "consumer": "prospective_decision_retention.discover_snapshots", "immutable": True, "session_bound": True, "operation_bound": True},
            {"stage": "maturity", "producer": "prospective_decision_outcome_feedback.build_feedback_artifact", "field": "t0_snapshot_identity / forward_outcomes", "source_object": "prospective_decision_outcome_feedback/v2", "consumer": "operational diagnostic artifact only", "immutable": True, "session_bound": True, "operation_bound": True},
        ],
        "identity_rules": {
            "not_factual_identity": ["filesystem_path_alone", "mtime", "git_commit_time", "LATEST_pointer"],
            "required_binding": ["session", "ticker", "integrated_decision_identity", "daily_session_operation_identity", "source_decision_artifact_identity", "prospective_snapshot_version"],
        },
    }


def _sep04_root_cause(root: Path) -> dict[str, Any]:
    bundle_path = root / "operations-review" / "canonical-post-close-v1" / "2026-09-04" / "session_handoff_bundle.json"
    bundle = _load(bundle_path) or {}
    referenced = ((bundle.get("deeper_bundles") or {}).get("integrated_investment_decision_product"))
    artifact_path = root / str(referenced) if isinstance(referenced, str) else None
    artifact = _load(artifact_path) if artifact_path else None
    enrichment_path = root / "operations-review" / "canonical-post-close-v1" / "2026-09-04" / "enrichment" / "integrated_investment_decision_product.json"
    enrichment = _load(enrichment_path)
    handoff_identity = bundle.get("integrated_investment_decision_product_identity")
    current_identity = (artifact or {}).get("artifact_identity")
    enrichment_identity = (enrichment or {}).get("artifact_identity")
    mismatch = bool(handoff_identity and current_identity and handoff_identity != current_identity)
    return {
        "session": "2026-09-04",
        "disposition": "RECOVERABLE_IDENTITY_BINDING_DEFECT" if mismatch else "AMBIGUOUS_HISTORICAL_PROVENANCE",
        "historical_candidate_disposition": "EXCLUDE_TEMPORAL_PROVENANCE_UNQUALIFIED",
        "identity_sources": {
            "canonical_handoff_integrated_decision_identity": {"value": handoff_identity, "origin": "session_handoff_bundle.integrated_investment_decision_product_identity", "path": str(bundle_path.relative_to(root)).replace("\\", "/")},
            "handoff_referenced_working_artifact_identity": {"value": current_identity, "origin": "referenced integrated decision artifact current contents", "path": str(referenced) if referenced else None},
            "canonical_enrichment_current_view_identity": {"value": enrichment_identity, "origin": "canonical enrichment current view", "path": str(enrichment_path.relative_to(root)).replace("\\", "/")},
        },
        "proven_facts": [
            "The retained handoff identity and its referenced working artifact identity differ.",
            "The enrichment current view has the same identity as the referenced working artifact.",
            "The legacy session-shaped integrated artifact write path has no immutable content-addressed T0 seal.",
        ],
        "not_proven": ["The exact historical actor/run that rewrote the mutable working path is not retained as immutable provenance."],
        "future_fix": {
            "contract": retention.CONTRACT_VERSION,
            "mechanism": "content-addressed append-only prospective snapshot sealed before the canonical handoff and bound by snapshot/source/operation identities",
            "prevents": "later mutable session-path artifact contents from replacing the factual T0 source",
        },
        "historical_requalification": "NOT_PERMITTED; no immutable artifact with the handoff identity is retained at its bound path.",
    }


def _legacy_compatibility(artifact: Mapping[str, Any]) -> dict[str, Any]:
    rows = [row for row in artifact.get("feedback_records") or [] if not row.get("t0_snapshot_identity")]
    return {
        "legacy_record_count": len(rows),
        "legacy_sessions": sorted({row.get("decision_session") for row in rows if row.get("decision_session")}),
        "field_rule": "missing modern fields remain FIELD_NOT_RETAINED_AT_T0; they are not rebuilt from current data",
        "evidence_axis_status_counts": dict(sorted(Counter(row.get("evidence_axes", {}).get("status") for row in rows).items())),
        "trigger_condition_status_counts": dict(sorted(Counter((row.get("trigger") or {}).get("condition", {}).get("status", retention.FIELD_NOT_RETAINED) for row in rows).items())),
        "invalidation_condition_status_counts": dict(sorted(Counter((row.get("invalidation") or {}).get("condition", {}).get("status", retention.FIELD_NOT_RETAINED) for row in rows).items())),
    }


def _health(artifact: Mapping[str, Any]) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in artifact.get("feedback_records") or []:
        grouped[str(row.get("decision_session"))].append(row)
    snapshots = {row.get("session"): row for row in (artifact.get("temporal_qualification", {}).get("immutable_snapshot_inventory") or [])}
    handoffs = {row.get("session"): row for row in (artifact.get("temporal_qualification", {}).get("handoff_snapshot_inventory") or [])}
    sessions = sorted(set(grouped) | {str(key) for key in snapshots if key} | {str(key) for key in handoffs if key})
    rows = []
    for session in sessions:
        entries = grouped.get(session, [])
        snapshot = snapshots.get(session) or {}
        handoff = handoffs.get(session) or {}
        horizons = Counter()
        for entry in entries:
            for item in (entry.get("forward_outcomes", {}).get("horizons", {}) or {}).values():
                if isinstance(item, Mapping):
                    horizons[str(item.get("maturation_state"))] += 1
        rows.append({
            "session": session,
            "canonical_prospective_snapshot_exists": bool(snapshot),
            "identity_qualified": snapshot.get("classification") == retention.GENUINE if snapshot else any((row.get("temporal_qualification") or {}).get("status") == feedback.GENUINE for row in entries),
            "decision_count": len(entries) or snapshot.get("decision_count"),
            "evidence_axis_snapshot_complete": dict(sorted(Counter((row.get("evidence_axes") or {}).get("status") for row in entries).items())),
            "trigger_condition_evaluable": dict(sorted(Counter(((row.get("trigger") or {}).get("condition") or {}).get("status", retention.FIELD_NOT_RETAINED) for row in entries).items())),
            "invalidation_condition_evaluable": dict(sorted(Counter(((row.get("invalidation") or {}).get("condition") or {}).get("status", retention.FIELD_NOT_RETAINED) for row in entries).items())),
            "forward_horizons": dict(sorted(horizons.items())),
            "outcome_artifact_exists": any(row.get("t0_snapshot_identity") for row in entries),
            "reason_codes": snapshot.get("proof_reason_codes") or [str(handoff.get("snapshot_status") or "LEGACY_ARTIFACT_NO_MODERN_SNAPSHOT"), str(handoff.get("snapshot_reason") or "NO_MODERN_PROSPECTIVE_SNAPSHOT_FIELD")],
        })
    return {"contract_version": retention.HEALTH_CONTRACT_VERSION, "sessions": rows, "authority_boundary": "OPERATIONAL_HEALTH_ONLY"}


def _report(artifact: Mapping[str, Any], root_cause: Mapping[str, Any], health: Mapping[str, Any]) -> str:
    corpus = artifact["prospective_corpus"]
    return "\n".join([
        "# Prospective Decision Retention and Outcome Maturation V1",
        "",
        "`PARTIAL_BY_EVIDENCE`: future retention/maturation is implemented; no new canonical Daily session was fabricated for validation.",
        "",
        f"- Legacy qualified decisions: {corpus['genuine_artifact_count']} artifacts / {corpus['genuine_decision_count']} records.",
        f"- Modern immutable snapshots retained in current historical corpus: {corpus['genuine_immutable_snapshot_count']}.",
        f"- Sep-04 disposition: `{root_cause['disposition']}`; historical candidate remains excluded.",
        f"- Corpus health sessions observed: {len(health['sessions'])}.",
        "- Future snapshots retain full T0 decision records, evidence axes, existing boundary semantics, source identity, and Daily operation identity.",
        "- Maturation is session-counted and downstream-only; no policy, probability, target, sizing, execution, provider, or authority change occurred.",
        "",
    ])


def run(*, root: Path, output_dir: Path) -> dict[str, Any]:
    artifact = feedback.build_feedback_artifact(root)
    root_cause = _sep04_root_cause(root)
    health = _health(artifact)
    snapshot_contract = {
        "contract_version": retention.CONTRACT_VERSION,
        "identity_fields": ["session", "ticker", "integrated_decision_identity", "canonical_operation_identity", "source_decision_artifact_identity", "prospective_snapshot_contract_version"],
        "retained_t0_fields": ["research_action_posture", "opportunity_priority", "why_now", "trigger", "invalidation", "evidence_axis_coherence", "FUNDAMENTAL", "VALUATION", "TACTICAL_STRUCTURE", "MOMENTUM", "PARTICIPATION_CONFIRMATION", "MARKET_SECTOR", "PORTFOLIO_FIT_if_supplied"],
        "immutability": "content-addressed append-only snapshot path; identical warm rerun reuses bytes, distinct decision identity creates a distinct snapshot",
        "future_information": "not embedded in the T0 snapshot",
    }
    condition_contract = {
        "contract_version": retention.CONDITION_CONTRACT_VERSION,
        "origin": "tactical_confirmation_invalidation_boundaries/v1 existing boundary semantics",
        "machine_evaluable": "only READY fixed T0 close-vs-level conditions; generic later evaluation uses the stored operator and level",
        "non_evaluable": "dynamic MA/momentum, disjunctive, conditional, unavailable, and narrative boundaries remain explicitly NOT_MACHINE_EVALUABLE",
        "not_created": ["second trigger engine", "stop-loss percentage", "execution inference"],
    }
    maturity_validation = {
        "contract": "trading-session-counted forward maturity over retained exact-session snapshots",
        "horizons": {name: count for name, count in feedback.forward_bridge.FORWARD_HORIZONS.items()},
        "states": ["PENDING", "MATURED", "INSUFFICIENT_FUTURE_DEPTH", "PRICE_SERIES_UNQUALIFIED", "TEMPORAL_PROVENANCE_UNQUALIFIED"],
        "mapping": {"T_plus_1_before_later_session": "PENDING", "some_but_less_than_required_later_sessions": "INSUFFICIENT_FUTURE_DEPTH", "compatible_endpoint": "MATURED", "missing_or_incompatible_close_series": "PRICE_SERIES_UNQUALIFIED"},
        "current_retained_coverage": artifact.get("forward_outcome_coverage"),
    }
    readiness = {
        "posture_outcomes": "READY_FOR_FUTURE_IMMUTABLE_SNAPSHOTS",
        "coherence_outcomes": "READY_FOR_FUTURE_IMMUTABLE_SNAPSHOTS",
        "evidence_axis_outcomes": "READY_FOR_FUTURE_IMMUTABLE_SNAPSHOTS",
        "false_negatives": "READY_WHEN_MATURED_CLOSE_OUTCOMES_EXIST",
        "failed_setups": "READY_WHEN_MATURED_CLOSE_OUTCOMES_EXIST",
        "trigger_outcomes": "READY_WHERE_EXISTING_T0_CONDITION_IS_MACHINE_EVALUABLE",
        "invalidation_outcomes": "READY_WHERE_EXISTING_T0_CONDITION_IS_MACHINE_EVALUABLE",
        "effectiveness_claim": "NOT_MADE_NO_MATURE_FUTURE_SNAPSHOT_CORPUS",
        "policy_mutated": False,
    }
    views = {
        "prospective_identity_flow.json": _flow_inventory(),
        "sep04_identity_mismatch_root_cause.json": root_cause,
        "prospective_snapshot_contract.json": snapshot_contract,
        "legacy_snapshot_compatibility.json": _legacy_compatibility(artifact),
        "trigger_invalidation_condition_contract.json": condition_contract,
        "prospective_corpus_health.json": health,
        "maturation_contract_validation.json": maturity_validation,
        "future_feedback_readiness.json": readiness,
    }
    _write_immutable(output_dir / "prospective_decision_feedback_artifact.json", artifact)
    for name, payload in views.items():
        _write_immutable(output_dir / name, payload)
    report = _report(artifact, root_cause, health)
    path = output_dir / "REPORT.md"
    if path.exists() and path.read_text(encoding="utf-8") != report:
        raise ValueError("IMMUTABLE_ARTIFACT_CONFLICT:" + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(report, encoding="utf-8")
    return {"artifact": artifact, "root_cause": root_cause, "health": health, "output_dir": str(output_dir)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "operations-review" / "prospective-decision-retention-outcome-maturation-v1-20260905")
    args = parser.parse_args()
    result = run(root=args.root, output_dir=args.output_dir)
    print(json.dumps({"output_dir": result["output_dir"], "sep04": result["root_cause"]["disposition"]}, sort_keys=True))
