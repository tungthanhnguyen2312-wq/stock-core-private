"""Bounded, retained-evidence-only validation replay.

Milestone: SESSION_BUNDLE_DECISION_CONTEXT_AND_LIFECYCLE_ENRICHMENT_V1.

Reconstructs validation copies of two retained Session Bundles with the corrected
bundle builder (current_daily_decision_research_product.attach_decision_context),
then replays the existing multi-session lifecycle engine over them. Reads only
already-retained local artifacts (no network, no registry mutation, no write to any
canonical/production path). Writes one bounded validation artifact describing exact
coverage, reconciliation, and the lifecycle replay result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from current_daily_decision_research_product import attach_decision_context  # noqa: E402
from multi_session_thesis_recommendation_lifecycle import (  # noqa: E402
    CONTRACT_VERSION as LIFECYCLE_CONTRACT,
    build_artifact,
)

VALIDATION_CONTRACT = "session_bundle_decision_context_lifecycle_enrichment_validation/v1"
RETENTION_FIELDS = ("recommendation_retention", "fundamental_invalidation_retention")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canon(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _load(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    return json.loads(raw), _sha256(raw)


def _reconstruct(bundle: Mapping[str, Any], *, shadow: Mapping[str, Any] | None) -> dict[str, Any]:
    """Apply the corrected bundle-builder attach step to an already-retained bundle.

    This does not re-derive the bundle from raw upstream inputs (descriptive, tactical,
    peer, fundamental, valuation, scenario, triage, ...): those are already immutable,
    retained, and unaffected by this milestone. Only the two newly-retained decision-
    context fields are added, via the exact same `attach_decision_context` call the live
    Daily Producer builder now makes.
    """
    reconstructed = json.loads(json.dumps(bundle))  # deep copy via round-trip; bundle is plain JSON
    attach_decision_context(reconstructed["ticker_research_contexts"], session=reconstructed["session"], shadow_security_recommendation=shadow)
    reconstructed["validation_replay"] = {
        "role": "BOUNDED_VALIDATION_REPLAY_NOT_CANONICAL",
        "milestone": "SESSION_BUNDLE_DECISION_CONTEXT_AND_LIFECYCLE_ENRICHMENT_V1",
        "reconstructed_from_original_session_bundle": True,
        "original_content_preserved_except_added_decision_context_fields": True,
        "no_network": True,
        "no_registry_mutation": True,
        "not_a_replacement_for_the_canonical_retained_artifact": True,
    }
    return reconstructed


def _coverage(cards: Mapping[str, Mapping[str, Any]], retention_field: str) -> dict[str, Any]:
    retained = sum(1 for card in cards.values() if (card.get(retention_field) or {}).get("status") == "RETAINED")
    session_mismatch = sum(1 for card in cards.values() if str((card.get(retention_field) or {}).get("reason") or "").startswith("SESSION_MISMATCH"))
    reasons = Counter(
        (card.get(retention_field) or {}).get("reason")
        for card in cards.values()
        if (card.get(retention_field) or {}).get("status") != "RETAINED"
    )
    unavailable = len(cards) - retained
    upstream_present_wrong_session = session_mismatch
    result = {
        "denominator": len(cards),
        "upstream_present": retained + upstream_present_wrong_session,
        "retained": retained,
        "unavailable": unavailable,
        "unavailable_due_to_session_mismatch": session_mismatch,
        "reason_code_distribution": {str(reason): count for reason, count in sorted(reasons.items(), key=lambda item: str(item[0]))},
    }
    assert result["retained"] + result["unavailable"] == result["denominator"], "COVERAGE_RECONCILIATION_FAILED"
    return result


def _session_report(bundle: Mapping[str, Any]) -> dict[str, Any]:
    cards = bundle["ticker_research_contexts"]
    return {
        "session": bundle["session"],
        "denominator": len(cards),
        "recommendation": _coverage(cards, "recommendation_retention"),
        "fundamental_invalidation": _coverage(cards, "fundamental_invalidation_retention"),
    }


def _lifecycle_examples(lifecycle: Mapping[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
    """Material changes first (the actually-interesting records), then other transitions."""
    records = lifecycle["records"]
    material = sorted(ticker for ticker, record in records.items() if record["material_change"])
    other_transitions = sorted(
        ticker for ticker, record in records.items()
        if not record["material_change"] and record["thesis_lifecycle_state"] not in {"UNCHANGED", "INITIAL_OBSERVATION"}
    )
    examples = []
    for ticker in (material + other_transitions)[:limit]:
        record = records[ticker]
        examples.append({
            "ticker": ticker, "thesis_lifecycle_state": record["thesis_lifecycle_state"],
            "material_change": record["material_change"], "material_change_reasons": record["material_change_reasons"],
            "reason_codes": record["reason_codes"],
        })
    return examples


def run(*, bundle_27: Path, bundle_28: Path, shadow_path: Path, output_dir: Path) -> dict[str, Any]:
    raw_27, raw_27_sha = _load(bundle_27)
    raw_28, raw_28_sha = _load(bundle_28)
    # artifact_sha256 on `shadow` is a content hash over its own payload (verified by
    # attach_decision_context's fail-closed check), not the file's raw bytes.
    shadow, _ = _load(shadow_path)

    reconstructed_27 = _reconstruct(raw_27, shadow=shadow)
    reconstructed_28 = _reconstruct(raw_28, shadow=shadow)

    output_dir.mkdir(parents=True, exist_ok=True)
    path_27 = output_dir / "2026-08-27_session_bundle_validation_replay.json"
    path_28 = output_dir / "2026-08-28_session_bundle_validation_replay.json"
    bytes_27 = _canon(reconstructed_27)
    bytes_28 = _canon(reconstructed_28)
    path_27.write_bytes(bytes_27)
    path_28.write_bytes(bytes_28)

    # Determinism proof: reconstruct again independently and require byte-identical output.
    repeat_27 = _canon(_reconstruct(raw_27, shadow=shadow))
    repeat_28 = _canon(_reconstruct(raw_28, shadow=shadow))
    deterministic_bundle_identity = (repeat_27 == bytes_27) and (repeat_28 == bytes_28)

    previous_for_lifecycle = dict(reconstructed_27)
    previous_for_lifecycle["source_artifact_sha256"] = _sha256(bytes_27)
    current_for_lifecycle = dict(reconstructed_28)
    current_for_lifecycle["source_artifact_sha256"] = _sha256(bytes_28)

    lifecycle = build_artifact(
        previous_bundle=previous_for_lifecycle,
        current_bundle=current_for_lifecycle,
        qualified_session_chain=["2026-08-27", "2026-08-28"],
    )
    lifecycle_repeat = build_artifact(
        previous_bundle=previous_for_lifecycle,
        current_bundle=current_for_lifecycle,
        qualified_session_chain=["2026-08-27", "2026-08-28"],
    )
    deterministic_lifecycle_identity = lifecycle == lifecycle_repeat and lifecycle["artifact_sha256"] == lifecycle_repeat["artifact_sha256"]

    lifecycle_path = output_dir / "multi_session_thesis_recommendation_lifecycle_replay.json"
    lifecycle_path.write_bytes(_canon(lifecycle))

    report_27 = _session_report(reconstructed_27)
    report_28 = _session_report(reconstructed_28)

    recommendation_transition_matrix = dict(sorted(lifecycle["coverage"]["recommendation_transitions"].items()))
    invalidation_transitions = dict(sorted(lifecycle["coverage"]["fundamental_invalidation_transitions"].items()))

    validation: dict[str, Any] = {
        "contract_version": VALIDATION_CONTRACT,
        "milestone": "SESSION_BUNDLE_DECISION_CONTEXT_AND_LIFECYCLE_ENRICHMENT_V1",
        "lifecycle_contract_version": LIFECYCLE_CONTRACT,
        "generated_from": "BOUNDED_LOCAL_RETAINED_ARTIFACTS_ONLY",
        "no_network": True,
        "no_registry_mutation": True,
        "no_runtime_db_mutation": True,
        "canonical_artifacts_untouched": True,
        "source_session_identities": {
            "2026-08-27": {"path": str(bundle_27), "raw_sha256": raw_27_sha, "operation_identity": raw_27.get("operation_identity"), "product_identity": raw_27.get("product_identity")},
            "2026-08-28": {"path": str(bundle_28), "raw_sha256": raw_28_sha, "operation_identity": raw_28.get("operation_identity"), "product_identity": raw_28.get("product_identity")},
        },
        "decision_context_source": {
            "path": str(shadow_path), "contract_version": shadow.get("contract_version"),
            "artifact_identity": shadow.get("artifact_identity"), "as_of_session": (shadow.get("metadata") or {}).get("as_of_session"),
            "denominator": shadow.get("denominator"),
            "session_coherence_note": "This retained artifact's as_of_session does not equal either replay session; section-5 session coherence therefore rejects attachment for both sessions and reports it explicitly, rather than presenting a misdated payload as current.",
        },
        "coverage": {"2026-08-27": report_27, "2026-08-28": report_28},
        "lifecycle_replay": {
            "denominator": lifecycle["denominator"],
            "comparable_count": lifecycle["comparable_count"],
            "initial_only_count": lifecycle["initial_only_count"],
            "previous_only_count": lifecycle["previous_only_count"],
            "lifecycle_ready_count": lifecycle["lifecycle_ready_count"],
            "insufficient_evidence_count": lifecycle["insufficient_evidence_count"],
            "lifecycle_state_distribution": lifecycle["coverage"]["lifecycle_states"],
            "material_change_count": lifecycle["coverage"]["material_change_count"],
            "recommendation_transition_matrix": recommendation_transition_matrix,
            "recommendation_label_change_count": recommendation_transition_matrix.get("STATE_CHANGED", 0),
            "fundamental_invalidation_transitions": invalidation_transitions,
            "invalidation_newly_activated_count": invalidation_transitions.get("INVALIDATION_ACTIVATED", 0),
            "invalidation_cleared_count": invalidation_transitions.get("INVALIDATION_CLEARED", 0),
            "tactical_transitions": lifecycle["coverage"]["tactical_transitions"],
            "strategy_transitions": lifecycle["coverage"]["strategy_transitions"],
            "opportunity_transitions": lifecycle["coverage"]["opportunity_transitions"],
            "missing_dimension_counts": lifecycle["coverage"]["missing_dimension_counts"],
            "warnings": lifecycle["warnings"],
            "artifact_identity": lifecycle["artifact_identity"],
            "artifact_sha256": lifecycle["artifact_sha256"],
        },
        "major_empirical_examples": _lifecycle_examples(lifecycle),
        "determinism": {
            "deterministic_bundle_identity": deterministic_bundle_identity,
            "deterministic_lifecycle_identity": deterministic_lifecycle_identity,
        },
        "outputs": {
            "2026-08-27_validation_replay": {"path": str(path_27), "sha256": _sha256(bytes_27)},
            "2026-08-28_validation_replay": {"path": str(path_28), "sha256": _sha256(bytes_28)},
            "lifecycle_replay": {"path": str(lifecycle_path), "sha256": _sha256(_canon(lifecycle))},
        },
        "authority_effect": "NONE",
        "research_tier": "PROSPECTIVE_MULTI_SESSION_RESEARCH_ONLY",
        "is_actionable": False,
        "new_recommendation_generated": False,
        "upstream_invalidation_recomputed": False,
    }
    payload_bytes = _canon(validation)
    validation["artifact_sha256"] = _sha256(payload_bytes)
    validation_path = output_dir / "validation_artifact.json"
    validation_path.write_bytes(_canon(validation))
    return {"validation": validation, "validation_path": validation_path, "validation_sha256": _sha256(_canon(validation))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-27", type=Path, required=True)
    parser.add_argument("--bundle-28", type=Path, required=True)
    parser.add_argument("--shadow-security-recommendation", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(bundle_27=args.bundle_27, bundle_28=args.bundle_28, shadow_path=args.shadow_security_recommendation, output_dir=args.output_dir)
    print(json.dumps({"validation_path": str(result["validation_path"]), "validation_sha256": result["validation_sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
