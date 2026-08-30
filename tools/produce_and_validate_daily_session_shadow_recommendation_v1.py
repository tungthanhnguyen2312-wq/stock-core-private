"""Bounded, retained-evidence-only end-to-end production + validation replay.

Milestone: DAILY_SESSION_SHADOW_RECOMMENDATION_AND_INVALIDATION_PRODUCTION_V1.

For each target session:

  1. Resolve same-session raw research (market/tactical) plus legitimately reused
     context (fundamental cross-sectional scoring, valuation-research proxy, corporate
     events, TTM, A1/A2 temporal, portfolio risk) and call
     daily_session_shadow_recommendation.build() -- the existing shadow-recommendation
     and structured fundamental-invalidation engines, reused verbatim, evaluated
     against THIS session's own inputs instead of the frozen 2026-08-25 cohort.
  2. Feed the resulting same-session shadow_security_recommendation artifact into the
     existing, unmodified Session Bundle retention contract
     (current_daily_decision_research_product.attach_decision_context) against a
     reconstructed copy of the retained canonical Session Bundle for that session.
  3. Replay the existing multi-session lifecycle engine over the two reconstructed,
     now-enriched Session Bundles.

Reads only already-retained local artifacts (no network, no registry mutation, no
canonical-artifact overwrite). Writes one bounded validation artifact.
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
from daily_session_shadow_recommendation import build as build_daily_session_shadow_recommendation  # noqa: E402
from multi_session_thesis_recommendation_lifecycle import (  # noqa: E402
    CONTRACT_VERSION as LIFECYCLE_CONTRACT,
    build_artifact as build_lifecycle_artifact,
)

VALIDATION_CONTRACT = "daily_session_shadow_recommendation_production_validation/v1"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canon(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_bytes())


def _reconstruct_bundle(bundle: Mapping[str, Any], *, shadow: Mapping[str, Any] | None) -> dict[str, Any]:
    """Apply the existing, unmodified attach_decision_context() to a retained bundle copy."""
    reconstructed = json.loads(json.dumps(bundle))  # deep copy via round-trip; bundle is plain JSON
    attach_decision_context(reconstructed["ticker_research_contexts"], session=reconstructed["session"], shadow_security_recommendation=shadow)
    reconstructed["validation_replay"] = {
        "role": "BOUNDED_VALIDATION_REPLAY_NOT_CANONICAL",
        "milestone": "DAILY_SESSION_SHADOW_RECOMMENDATION_AND_INVALIDATION_PRODUCTION_V1",
        "reconstructed_from_original_session_bundle": True,
        "original_content_preserved_except_added_decision_context_fields": True,
        "no_network": True,
        "no_registry_mutation": True,
        "not_a_replacement_for_the_canonical_retained_artifact": True,
    }
    return reconstructed


def _bundle_retention_coverage(cards: Mapping[str, Mapping[str, Any]], retention_field: str) -> dict[str, Any]:
    retained = sum(1 for card in cards.values() if (card.get(retention_field) or {}).get("status") == "RETAINED")
    reasons = Counter(
        (card.get(retention_field) or {}).get("reason")
        for card in cards.values()
        if (card.get(retention_field) or {}).get("status") != "RETAINED"
    )
    unavailable = len(cards) - retained
    result = {
        "denominator": len(cards), "retained": retained, "unavailable": unavailable,
        "reason_code_distribution": {str(reason): count for reason, count in sorted(reasons.items(), key=lambda item: str(item[0]))},
    }
    assert result["retained"] + result["unavailable"] == result["denominator"], "COVERAGE_RECONCILIATION_FAILED"
    return result


def _engine_coverage(chain: Mapping[str, Any]) -> dict[str, Any]:
    rec = chain["shadow_security_recommendation"]
    readiness = rec["validation"]["readiness_counts"]
    fundamental_status = rec["validation"]["fundamental_boundary_status"]
    return {
        "recommendation_evaluated": rec["denominator"],
        "recommendation_ready": readiness.get("RECOMMENDATION_READY", 0),
        "recommendation_conditional": readiness.get("RECOMMENDATION_CONDITIONAL", 0),
        "recommendation_not_ready": readiness.get("RECOMMENDATION_NOT_READY", 0),
        "recommendation_blocked": 0,
        "recommendation_blocked_note": "Not applicable: shadow_security_recommendation/v1's own vocabulary is READY/CONDITIONAL/NOT_READY; there is no separate BLOCKED status to report.",
        "recommendation_label_distribution": dict(sorted(rec["validation"]["recommendation_counts"].items())),
        "invalidation_evaluated": rec["denominator"],
        "invalidation_available": fundamental_status.get("READY", 0) + fundamental_status.get("CONDITIONAL", 0),
        "invalidation_unavailable": fundamental_status.get("UNAVAILABLE", 0),
        "invalidation_state_distribution": dict(sorted(fundamental_status.items())),
        "residual": rec["residual"],
    }


def _lifecycle_examples(lifecycle: Mapping[str, Any], *, limit: int = 8) -> list[dict[str, Any]]:
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
            "current_recommendation_label": (record.get("current_recommendation") or {}).get("recommendation_label"),
            "previous_recommendation_label": (record.get("previous_recommendation") or {}).get("recommendation_label"),
        })
    return examples


def produce_session(*, session: str, market_path: Path, tactical_path: Path, fundamental_path: Path,
                    valuation_path: Path, events_path: Path, ttm_path: Path, risk_research_path: Path,
                    a1_temporal_path: Path, a2_temporal_path: Path, canonical_bundle_path: Path) -> dict[str, Any]:
    market, tactical = _load(market_path), _load(tactical_path)
    fundamental, valuation = _load(fundamental_path), _load(valuation_path)
    events, ttm = _load(events_path), _load(ttm_path)
    risk_research = _load(risk_research_path)
    a1_temporal, a2_temporal = _load(a1_temporal_path), _load(a2_temporal_path)
    if market.get("session") != session:
        raise ValueError("PRODUCE_SESSION:MARKET_SESSION_MISMATCH:" + str(market.get("session")))

    chain = build_daily_session_shadow_recommendation(
        market=market, tactical=tactical, fundamental=fundamental, valuation=valuation,
        events=events, ttm=ttm, risk_research=risk_research, valuation_research=valuation,
        a1_temporal=a1_temporal, a2_temporal=a2_temporal,
    )
    canonical_bundle = _load(canonical_bundle_path)
    if canonical_bundle.get("session") != session:
        raise ValueError("PRODUCE_SESSION:CANONICAL_BUNDLE_SESSION_MISMATCH")
    reconstructed_bundle = _reconstruct_bundle(canonical_bundle, shadow=chain["shadow_security_recommendation"])
    return {
        "session": session, "chain": chain, "canonical_bundle": canonical_bundle,
        "canonical_bundle_sha256": _sha256(canonical_bundle_path.read_bytes()),
        "reconstructed_bundle": reconstructed_bundle,
    }


def run(*, sessions: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    produced: dict[str, dict[str, Any]] = {}
    for spec in sessions:
        session = spec["session"]
        produced[session] = produce_session(**{key: value for key, value in spec.items() if key != "session"}, session=session)

    outputs: dict[str, Any] = {}
    for session, result in produced.items():
        chain_bytes = _canon(result["chain"])
        bundle_bytes = _canon(result["reconstructed_bundle"])
        chain_path = output_dir / f"{session}_daily_session_shadow_recommendation.json"
        bundle_path = output_dir / f"{session}_session_bundle_validation_replay.json"
        chain_path.write_bytes(chain_bytes)
        bundle_path.write_bytes(bundle_bytes)
        # determinism proof: rebuild independently and require byte-identical output
        repeat_spec = next(spec for spec in sessions if spec["session"] == session)
        repeat = produce_session(**{key: value for key, value in repeat_spec.items() if key != "session"}, session=session)
        deterministic = _canon(repeat["chain"]) == chain_bytes and _canon(repeat["reconstructed_bundle"]) == bundle_bytes
        outputs[session] = {
            "chain_path": chain_path, "chain_sha256": _sha256(chain_bytes),
            "bundle_path": bundle_path, "bundle_sha256": _sha256(bundle_bytes),
            "deterministic": deterministic,
        }

    ordered_sessions = sorted(produced)
    if len(ordered_sessions) != 2:
        raise ValueError("EXACTLY_TWO_SESSIONS_REQUIRED_FOR_LIFECYCLE_REPLAY")
    previous_session, current_session = ordered_sessions
    previous_for_lifecycle = dict(produced[previous_session]["reconstructed_bundle"])
    previous_for_lifecycle["source_artifact_sha256"] = outputs[previous_session]["bundle_sha256"]
    current_for_lifecycle = dict(produced[current_session]["reconstructed_bundle"])
    current_for_lifecycle["source_artifact_sha256"] = outputs[current_session]["bundle_sha256"]

    lifecycle = build_lifecycle_artifact(
        previous_bundle=previous_for_lifecycle, current_bundle=current_for_lifecycle,
        qualified_session_chain=ordered_sessions,
    )
    lifecycle_repeat = build_lifecycle_artifact(
        previous_bundle=previous_for_lifecycle, current_bundle=current_for_lifecycle,
        qualified_session_chain=ordered_sessions,
    )
    deterministic_lifecycle = lifecycle == lifecycle_repeat and lifecycle["artifact_sha256"] == lifecycle_repeat["artifact_sha256"]
    lifecycle_path = output_dir / "lifecycle_replay.json"
    lifecycle_path.write_bytes(_canon(lifecycle))

    per_session_report = {}
    for session, result in produced.items():
        bundle_cards = result["reconstructed_bundle"]["ticker_research_contexts"]
        per_session_report[session] = {
            "daily_producer_denominator": len(bundle_cards),
            "engine_coverage": _engine_coverage(result["chain"]),
            "bundle_retention": {
                "recommendation": _bundle_retention_coverage(bundle_cards, "recommendation_retention"),
                "fundamental_invalidation": _bundle_retention_coverage(bundle_cards, "fundamental_invalidation_retention"),
            },
            "source_identities": {
                "canonical_bundle_sha256": result["canonical_bundle_sha256"],
                "daily_session_shadow_recommendation_artifact_identity": result["chain"]["artifact_identity"],
                "shadow_security_recommendation_artifact_identity": result["chain"]["shadow_security_recommendation"]["artifact_identity"],
            },
        }

    recommendation_transitions = dict(sorted(lifecycle["coverage"]["recommendation_transitions"].items()))
    invalidation_transitions = dict(sorted(lifecycle["coverage"]["fundamental_invalidation_transitions"].items()))
    validation: dict[str, Any] = {
        "contract_version": VALIDATION_CONTRACT,
        "milestone": "DAILY_SESSION_SHADOW_RECOMMENDATION_AND_INVALIDATION_PRODUCTION_V1",
        "lifecycle_contract_version": LIFECYCLE_CONTRACT,
        "generated_from": "BOUNDED_LOCAL_RETAINED_ARTIFACTS_ONLY",
        "no_network": True, "no_registry_mutation": True, "no_runtime_db_mutation": True,
        "canonical_artifacts_untouched": True,
        "recommendation_engine_reused_unchanged": True,
        "invalidation_engine_reused_unchanged": True,
        "sessions": ordered_sessions,
        "per_session": per_session_report,
        "lifecycle_replay": {
            "previous_session": previous_session, "current_session": current_session,
            "denominator": lifecycle["denominator"], "comparable_count": lifecycle["comparable_count"],
            "initial_only_count": lifecycle["initial_only_count"], "previous_only_count": lifecycle["previous_only_count"],
            "lifecycle_ready_count": lifecycle["lifecycle_ready_count"],
            "lifecycle_state_distribution": lifecycle["coverage"]["lifecycle_states"],
            "material_change_count": lifecycle["coverage"]["material_change_count"],
            "recommendation_transition_matrix": recommendation_transitions,
            "recommendation_label_change_count": recommendation_transitions.get("STATE_CHANGED", 0),
            "invalidation_transition_matrix": invalidation_transitions,
            "invalidation_newly_activated_count": invalidation_transitions.get("INVALIDATION_ACTIVATED", 0),
            "invalidation_cleared_count": invalidation_transitions.get("INVALIDATION_CLEARED", 0),
            "tactical_transitions": lifecycle["coverage"]["tactical_transitions"],
            "strategy_transitions": lifecycle["coverage"]["strategy_transitions"],
            "warnings": lifecycle["warnings"],
            "artifact_identity": lifecycle["artifact_identity"], "artifact_sha256": lifecycle["artifact_sha256"],
        },
        "major_empirical_examples": _lifecycle_examples(lifecycle),
        "determinism": {
            "deterministic_daily_session_artifacts": all(outputs[s]["deterministic"] for s in ordered_sessions),
            "deterministic_lifecycle_identity": deterministic_lifecycle,
        },
        "outputs": {
            session: {"chain_path": str(outputs[session]["chain_path"]), "chain_sha256": outputs[session]["chain_sha256"],
                      "bundle_path": str(outputs[session]["bundle_path"]), "bundle_sha256": outputs[session]["bundle_sha256"]}
            for session in ordered_sessions
        } | {"lifecycle_replay": {"path": str(lifecycle_path), "sha256": _sha256(_canon(lifecycle))}},
        "authority_effect": "NONE",
        "research_tier": "PROSPECTIVE_MULTI_SESSION_RESEARCH_ONLY",
        "is_actionable": False,
        "new_recommendation_generated": False,
        "upstream_invalidation_recomputed": False,
        "canonical_pipeline_global_failure_behavior_changed": False,
    }
    payload_bytes = _canon(validation)
    validation["artifact_sha256"] = _sha256(payload_bytes)
    validation_path = output_dir / "validation_artifact.json"
    validation_path.write_bytes(_canon(validation))
    return {"validation": validation, "validation_path": validation_path, "validation_sha256": _sha256(_canon(validation))}


def _session_spec(prefix: str, session: str, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "session": session,
        "market_path": getattr(args, f"{prefix}_market"),
        "tactical_path": getattr(args, f"{prefix}_tactical"),
        "fundamental_path": args.fundamental,
        "valuation_path": args.valuation,
        "events_path": args.events,
        "ttm_path": args.ttm,
        "risk_research_path": args.risk_research,
        "a1_temporal_path": args.a1_temporal,
        "a2_temporal_path": args.a2_temporal,
        "canonical_bundle_path": getattr(args, f"{prefix}_bundle"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-27-market", type=Path, required=True)
    parser.add_argument("--session-27-tactical", type=Path, required=True)
    parser.add_argument("--session-27-bundle", type=Path, required=True)
    parser.add_argument("--session-28-market", type=Path, required=True)
    parser.add_argument("--session-28-tactical", type=Path, required=True)
    parser.add_argument("--session-28-bundle", type=Path, required=True)
    parser.add_argument("--fundamental", type=Path, required=True)
    parser.add_argument("--valuation", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--ttm", type=Path, required=True)
    parser.add_argument("--risk-research", type=Path, required=True)
    parser.add_argument("--a1-temporal", type=Path, required=True)
    parser.add_argument("--a2-temporal", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    sessions = [
        _session_spec("session_27", "2026-08-27", args),
        _session_spec("session_28", "2026-08-28", args),
    ]
    result = run(sessions=sessions, output_dir=args.output_dir)
    print(json.dumps({"validation_path": str(result["validation_path"]), "validation_sha256": result["validation_sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
