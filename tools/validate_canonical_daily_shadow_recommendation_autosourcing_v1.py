"""Summarize a bounded retained canonical autosourcing replay without acquisition."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


CONTRACT_VERSION = "canonical_daily_shadow_recommendation_autosourcing_validation/v1"


def _canon(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_identity", "artifact_sha256"}}
    digest = hashlib.sha256(_canon(payload)).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"canonical_daily_shadow_recommendation_autosourcing:{digest}"}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("VALIDATION_INPUT_NOT_OBJECT:" + path.name)
    return value


def _retention(cards: Mapping[str, Any], field: str) -> dict[str, Any]:
    retained = sum((card.get(field) or {}).get("status") == "RETAINED" for card in cards.values() if isinstance(card, Mapping))
    reasons = Counter(
        (card.get(field) or {}).get("reason")
        for card in cards.values() if isinstance(card, Mapping) and (card.get(field) or {}).get("status") != "RETAINED"
    )
    return {"retained": retained, "unavailable": len(cards) - retained, "unavailable_reasons": dict(sorted((str(key), value) for key, value in reasons.items()))}


def _session(run_manifest_path: Path, bundle_path: Path) -> dict[str, Any]:
    manifest, bundle = _load(run_manifest_path), _load(bundle_path)
    session = bundle.get("session")
    shadow = manifest.get("daily_session_shadow_recommendation")
    if not isinstance(session, str) or not isinstance(shadow, Mapping) or shadow.get("session") != session:
        raise ValueError("AUTOSOURCED_SESSION_LINEAGE_MISMATCH")
    chain_path = Path(str(shadow.get("path") or ""))
    chain = _load(chain_path)
    if chain.get("session") != session or chain.get("artifact_identity") != shadow.get("artifact_identity"):
        raise ValueError("AUTOSOURCED_CHAIN_IDENTITY_MISMATCH")
    recommendation = chain.get("shadow_security_recommendation") or {}
    if (recommendation.get("metadata") or {}).get("as_of_session") != session:
        raise ValueError("AUTOSOURCED_RECOMMENDATION_SESSION_MISMATCH")
    cards = bundle.get("ticker_research_contexts") or {}
    return {
        "session": session,
        "autosource_status": shadow.get("status"),
        "chain_identity": chain.get("artifact_identity"),
        "recommendation_identity": recommendation.get("artifact_identity"),
        "source_artifact_identities": chain.get("source_artifact_identities"),
        "recommendation_coverage": {
            "evaluated": recommendation.get("denominator"),
            "ready": ((recommendation.get("validation") or {}).get("readiness_counts") or {}).get("RECOMMENDATION_READY", 0),
            "labels": ((recommendation.get("validation") or {}).get("recommendation_counts") or {}),
        },
        "bundle": {
            "denominator": len(cards),
            "recommendation": _retention(cards, "recommendation_retention"),
            "fundamental_invalidation": _retention(cards, "fundamental_invalidation_retention"),
        },
    }


def build(*, run_27: Path, bundle_27: Path, run_28: Path, bundle_28: Path, lifecycle: Path) -> dict[str, Any]:
    sessions = [_session(run_27, bundle_27), _session(run_28, bundle_28)]
    replay = _load(lifecycle)
    artifact: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "canonical_dependency_order": [
            "qualified_session_inputs", "daily_session_shadow_recommendation", "daily_research_session_operation",
            "current_daily_decision_research_product", "ai_research_session_bundle", "multi_session_lifecycle",
        ],
        "sessions": sessions,
        "lifecycle_compatibility": {
            "previous_session": replay.get("previous_session"), "current_session": replay.get("current_session"),
            "comparable_count": replay.get("comparable_count"),
            "recommendation_transition_matrix": (replay.get("coverage") or {}).get("recommendation_transitions"),
            "invalidation_transition_matrix": (replay.get("coverage") or {}).get("fundamental_invalidation_transitions"),
            "artifact_identity": replay.get("artifact_identity"),
        },
        "fail_closed_cases": [
            "WRONG_SESSION_OR_MISSING_AUTOSOURCE_LINEAGE_REJECTED",
            "IMMUTABLE_SAME_SESSION_SOURCE_CONFLICT_REJECTED",
            "CORRUPTED_RETAINED_AUTOSOURCE_ARTIFACT_REJECTED",
        ],
        "ordinary_per_security_unavailability": "RETAINED_AS_EXPLICIT_CARD_REASON_WITHOUT_GLOBAL_FAILURE",
        "authority_effect": "NONE", "is_actionable": False,
        "warnings": ["BOUNDED_RETAINED_REPLAY_ONLY", "NO_NETWORK", "NO_PRIMARY_REGISTRY_OR_CANONICAL_ARTIFACT_WRITE"],
    }
    artifact.update(_identity(artifact))
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run-27", "bundle-27", "run-28", "bundle-28", "lifecycle"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    artifact = build(run_27=args.run_27, bundle_27=args.bundle_27, run_28=args.run_28, bundle_28=args.bundle_28, lifecycle=args.lifecycle)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canon(artifact))
    print(json.dumps({"artifact_identity": artifact["artifact_identity"], "artifact_sha256": artifact["artifact_sha256"]}))


if __name__ == "__main__":
    main()
