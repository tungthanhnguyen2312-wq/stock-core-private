"""MARKET_WIDE_FUNDAMENTAL_RESEARCH_COHORT_SCALEOUT_V1 -- downstream replay.

Bounded, retained-evidence-only BEFORE/AFTER replay of the existing downstream chain
(``fundamental_market_opportunity_ranking`` -> ``thesis_catalyst_downside_research_cases``
-> ``shadow_action_readiness`` -> ``fundamental_thesis_invalidation_precision`` ->
``action_instrumentation`` -> ``shadow_security_recommendation``, via
``daily_session_shadow_recommendation.build`` -- reused completely unmodified) for sessions
2026-08-27 and 2026-08-28, run twice per session:

  BEFORE: the existing narrow 523-member ``fundamental_cross_sectional_scoring`` artifact
          (today's real ``daily_session_shadow_recommendation.SHARED_CONTEXT_RELATIVE_PATHS
          ['fundamental']`` default -- unchanged).
  AFTER:  the new wide artifact this milestone produced
          (``fundamental_research_cohort_scaleout.build_wide_fundamental_cross_sectional_artifact``),
          substituted in through nothing more than a different input value -- the engine
          itself is byte-identical code in both runs.

Then replays the existing Session Bundle retention contract
(``current_daily_decision_research_product.attach_decision_context``) against a
reconstructed copy of each session's own retained canonical bundle, and the existing
multi-session lifecycle engine (``multi_session_thesis_recommendation_lifecycle
.build_artifact``) over the two reconstructed bundles, once for BEFORE and once for AFTER.

Reads only already-retained local artifacts (no network, no registry mutation, no
canonical-artifact overwrite -- every write lands under ``--output-dir``, defaulting to a
path inside this worktree). Session-specific and shared-context source artifacts default to
explicit CLI paths because the bulk retained per-session evidence they come from is large,
gitignored, operator-local data not tracked in a fresh worktree (see the sibling derivation
script's module docstring for the same constraint).
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_daily_decision_research_product import attach_decision_context  # noqa: E402
from daily_session_shadow_recommendation import build as build_daily_session_shadow_recommendation  # noqa: E402
from multi_session_thesis_recommendation_lifecycle import (  # noqa: E402
    CONTRACT_VERSION as LIFECYCLE_CONTRACT,
    build_artifact as build_lifecycle_artifact,
)

VALIDATION_CONTRACT = "market_wide_fundamental_research_cohort_scaleout_downstream_replay/v1"
VARIANTS = ("before_narrow", "after_wide")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canon(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_bytes())


def _reconstruct_bundle(bundle: Mapping[str, Any], *, shadow: Mapping[str, Any] | None) -> dict[str, Any]:
    """Apply the existing, unmodified attach_decision_context() to a retained bundle copy.
    Identical in shape to produce_and_validate_daily_session_shadow_recommendation_v1.py's own
    helper -- kept local (not imported) so this script has no dependency on another tools/*.py
    module needing its own sys.path wiring."""
    reconstructed = json.loads(json.dumps(bundle))
    attach_decision_context(reconstructed["ticker_research_contexts"], session=reconstructed["session"], shadow_security_recommendation=shadow)
    reconstructed["validation_replay"] = {
        "role": "BOUNDED_VALIDATION_REPLAY_NOT_CANONICAL",
        "milestone": "MARKET_WIDE_FUNDAMENTAL_RESEARCH_COHORT_SCALEOUT_V1",
        "reconstructed_from_original_session_bundle": True,
        "no_network": True, "no_registry_mutation": True,
        "not_a_replacement_for_the_canonical_retained_artifact": True,
    }
    return reconstructed


def _bundle_retention_coverage(cards: Mapping[str, Mapping[str, Any]], retention_field: str) -> dict[str, Any]:
    retained = sum(1 for card in cards.values() if (card.get(retention_field) or {}).get("status") == "RETAINED")
    reasons = Counter(
        (card.get(retention_field) or {}).get("reason")
        for card in cards.values() if (card.get(retention_field) or {}).get("status") != "RETAINED"
    )
    unavailable = len(cards) - retained
    result = {
        "denominator": len(cards), "retained": retained, "unavailable": unavailable,
        "reason_code_distribution": {str(reason): count for reason, count in sorted(reasons.items(), key=lambda item: str(item[0]))},
    }
    assert result["retained"] + result["unavailable"] == result["denominator"], "COVERAGE_RECONCILIATION_FAILED"
    return result


def produce_session(*, session: str, market: Mapping[str, Any], tactical: Mapping[str, Any],
                    fundamental: Mapping[str, Any], valuation: Mapping[str, Any], events: Mapping[str, Any],
                    ttm: Mapping[str, Any], risk_research: Mapping[str, Any], a1_temporal: Mapping[str, Any],
                    a2_temporal: Mapping[str, Any], canonical_bundle: Mapping[str, Any]) -> dict[str, Any]:
    if market.get("session") != session:
        raise ValueError("PRODUCE_SESSION:MARKET_SESSION_MISMATCH:" + str(market.get("session")))
    chain = build_daily_session_shadow_recommendation(
        market=market, tactical=tactical, fundamental=fundamental, valuation=valuation,
        events=events, ttm=ttm, risk_research=risk_research, valuation_research=valuation,
        a1_temporal=a1_temporal, a2_temporal=a2_temporal,
    )
    if canonical_bundle.get("session") != session:
        raise ValueError("PRODUCE_SESSION:CANONICAL_BUNDLE_SESSION_MISMATCH")
    reconstructed_bundle = _reconstruct_bundle(canonical_bundle, shadow=chain["shadow_security_recommendation"])
    return {"session": session, "chain": chain, "reconstructed_bundle": reconstructed_bundle}


def _engine_coverage(chain: Mapping[str, Any]) -> dict[str, Any]:
    rec = chain["shadow_security_recommendation"]
    readiness = rec["validation"]["readiness_counts"]
    fundamental_status = rec["validation"]["fundamental_boundary_status"]
    return {
        "opportunity_ranking_denominator": chain["denominator_by_stage"]["opportunity_ranking"],
        "recommendation_evaluated": rec["denominator"],
        "recommendation_ready": readiness.get("RECOMMENDATION_READY", 0),
        "recommendation_conditional": readiness.get("RECOMMENDATION_CONDITIONAL", 0),
        "recommendation_not_ready": readiness.get("RECOMMENDATION_NOT_READY", 0),
        "recommendation_label_distribution": dict(sorted(rec["validation"]["recommendation_counts"].items())),
        "invalidation_available": fundamental_status.get("READY", 0) + fundamental_status.get("CONDITIONAL", 0),
        "invalidation_unavailable": fundamental_status.get("UNAVAILABLE", 0),
        "invalidation_state_distribution": dict(sorted(fundamental_status.items())),
    }


def run_variant(*, variant: str, fundamental: Mapping[str, Any], sessions: dict[str, dict[str, Any]],
                output_dir: Path) -> dict[str, Any]:
    produced: dict[str, dict[str, Any]] = {}
    for session, spec in sessions.items():
        produced[session] = produce_session(session=session, fundamental=fundamental, **{
            key: value for key, value in spec.items() if key != "session"
        })

    outputs: dict[str, Any] = {}
    for session, result in produced.items():
        chain_bytes = _canon(result["chain"])
        bundle_bytes = _canon(result["reconstructed_bundle"])
        chain_path = output_dir / variant / f"{session}_daily_session_shadow_recommendation.json"
        bundle_path = output_dir / variant / f"{session}_session_bundle_validation_replay.json"
        chain_path.parent.mkdir(parents=True, exist_ok=True)
        chain_path.write_bytes(chain_bytes)
        bundle_path.write_bytes(bundle_bytes)
        outputs[session] = {"chain_path": chain_path, "chain_sha256": _sha256(chain_bytes),
                             "bundle_path": bundle_path, "bundle_sha256": _sha256(bundle_bytes)}

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
    lifecycle_path = output_dir / variant / "lifecycle_replay.json"
    lifecycle_path.write_bytes(_canon(lifecycle))

    per_session_report = {}
    for session, result in produced.items():
        bundle_cards = result["reconstructed_bundle"]["ticker_research_contexts"]
        per_session_report[session] = {
            "session_bundle_denominator": len(bundle_cards),
            "engine_coverage": _engine_coverage(result["chain"]),
            "bundle_retention": {
                "recommendation": _bundle_retention_coverage(bundle_cards, "recommendation_retention"),
                "fundamental_invalidation": _bundle_retention_coverage(bundle_cards, "fundamental_invalidation_retention"),
            },
            "source_identities": {
                "daily_session_shadow_recommendation_artifact_identity": result["chain"]["artifact_identity"],
                "shadow_security_recommendation_artifact_identity": result["chain"]["shadow_security_recommendation"]["artifact_identity"],
            },
        }

    return {
        "variant": variant,
        "fundamental_denominator": len((fundamental.get("records") or {})),
        "fundamental_artifact_sha256": fundamental.get("artifact_sha256"),
        "sessions": ordered_sessions,
        "per_session": per_session_report,
        "lifecycle_replay": {
            "previous_session": previous_session, "current_session": current_session,
            "denominator": lifecycle["denominator"], "comparable_count": lifecycle["comparable_count"],
            "initial_only_count": lifecycle["initial_only_count"], "previous_only_count": lifecycle["previous_only_count"],
            "lifecycle_ready_count": lifecycle["lifecycle_ready_count"],
            "lifecycle_state_distribution": lifecycle["coverage"]["lifecycle_states"],
            "material_change_count": lifecycle["coverage"]["material_change_count"],
            "recommendation_transition_matrix": dict(sorted(lifecycle["coverage"]["recommendation_transitions"].items())),
            "invalidation_transition_matrix": dict(sorted(lifecycle["coverage"]["fundamental_invalidation_transitions"].items())),
            "artifact_identity": lifecycle["artifact_identity"],
        },
        "outputs": {
            session: {"chain_path": str(outputs[session]["chain_path"]), "chain_sha256": outputs[session]["chain_sha256"],
                      "bundle_path": str(outputs[session]["bundle_path"]), "bundle_sha256": outputs[session]["bundle_sha256"]}
            for session in ordered_sessions
        } | {"lifecycle_replay": {"path": str(lifecycle_path), "sha256": _sha256(_canon(lifecycle))}},
    }


def _delta(before: Mapping[str, Any], after: Mapping[str, Any], *path: str) -> dict[str, Any]:
    def _get(d: Mapping[str, Any]) -> Any:
        for key in path:
            d = d[key]
        return d
    return {"before": _get(before), "after": _get(after)}


def build_comparison_report(*, before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    sessions = before["sessions"]
    per_session_delta = {}
    for session in sessions:
        b, a = before["per_session"][session], after["per_session"][session]
        per_session_delta[session] = {
            "session_bundle_denominator": {"before": b["session_bundle_denominator"], "after": a["session_bundle_denominator"],
                                           "note": "Session Bundle denominator is driven by market/tactical, not the fundamental cohort; expected unchanged."},
            "opportunity_ranking_denominator": {"before": b["engine_coverage"]["opportunity_ranking_denominator"], "after": a["engine_coverage"]["opportunity_ranking_denominator"]},
            "recommendation_bundle_retention": {"before": b["bundle_retention"]["recommendation"], "after": a["bundle_retention"]["recommendation"]},
            "invalidation_bundle_retention": {"before": b["bundle_retention"]["fundamental_invalidation"], "after": a["bundle_retention"]["fundamental_invalidation"]},
            "recommendation_ready_count": {"before": b["engine_coverage"]["recommendation_ready"], "after": a["engine_coverage"]["recommendation_ready"]},
        }
    return {
        "contract_version": VALIDATION_CONTRACT,
        "milestone": "MARKET_WIDE_FUNDAMENTAL_RESEARCH_COHORT_SCALEOUT_V1",
        "sessions": sessions,
        "fundamental_cohort": {"before_denominator": before["fundamental_denominator"], "after_denominator": after["fundamental_denominator"]},
        "per_session": per_session_delta,
        "lifecycle_comparable_recommendation_context": {
            "before": before["lifecycle_replay"]["comparable_count"], "after": after["lifecycle_replay"]["comparable_count"],
        },
        "lifecycle_recommendation_transition_matrix": {"before": before["lifecycle_replay"]["recommendation_transition_matrix"], "after": after["lifecycle_replay"]["recommendation_transition_matrix"]},
        "lifecycle_invalidation_transition_matrix": {"before": before["lifecycle_replay"]["invalidation_transition_matrix"], "after": after["lifecycle_replay"]["invalidation_transition_matrix"]},
        "engines_reused_verbatim": [
            "fundamental_market_opportunity_ranking", "thesis_catalyst_downside_research_cases",
            "shadow_action_readiness", "fundamental_thesis_invalidation_precision",
            "action_instrumentation", "shadow_security_recommendation",
            "current_daily_decision_research_product.attach_decision_context",
            "multi_session_thesis_recommendation_lifecycle",
        ],
        "authority_effect": "NONE", "is_actionable": False,
        "research_tier": "PROSPECTIVE_MULTI_SESSION_RESEARCH_ONLY",
        "canonical_artifacts_untouched": True, "no_network": True, "no_registry_mutation": True,
        "new_recommendation_generated": False, "upstream_invalidation_recomputed": False,
        "scoring_rule_changed": False,
        "before_detail": before, "after_detail": after,
    }


def _session_inputs(prefix: str, session: str, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "session": session,
        "market": _load(getattr(args, f"{prefix}_market")),
        "tactical": _load(getattr(args, f"{prefix}_tactical")),
        "canonical_bundle": _load(getattr(args, f"{prefix}_bundle")),
        "valuation": _load(args.valuation), "events": _load(args.events), "ttm": _load(args.ttm),
        "risk_research": _load(args.risk_research), "a1_temporal": _load(args.a1_temporal), "a2_temporal": _load(args.a2_temporal),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-27-market", type=Path, required=True)
    parser.add_argument("--session-27-tactical", type=Path, required=True)
    parser.add_argument("--session-27-bundle", type=Path, required=True)
    parser.add_argument("--session-28-market", type=Path, required=True)
    parser.add_argument("--session-28-tactical", type=Path, required=True)
    parser.add_argument("--session-28-bundle", type=Path, required=True)
    parser.add_argument("--fundamental-narrow", type=Path, required=True)
    parser.add_argument("--fundamental-wide", type=Path, required=True)
    parser.add_argument("--valuation", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--ttm", type=Path, required=True)
    parser.add_argument("--risk-research", type=Path, required=True)
    parser.add_argument("--a1-temporal", type=Path, required=True)
    parser.add_argument("--a2-temporal", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    sessions = {
        "2026-08-27": _session_inputs("session_27", "2026-08-27", args),
        "2026-08-28": _session_inputs("session_28", "2026-08-28", args),
    }
    fundamental_narrow = _load(args.fundamental_narrow)
    fundamental_wide = _load(args.fundamental_wide)

    before = run_variant(variant="before_narrow", fundamental=fundamental_narrow, sessions=sessions, output_dir=args.output_dir)
    after = run_variant(variant="after_wide", fundamental=fundamental_wide, sessions=sessions, output_dir=args.output_dir)
    report = build_comparison_report(before=before, after=after)
    payload_bytes = _canon(report)
    report["artifact_sha256"] = _sha256(payload_bytes)
    report_path = args.output_dir / "downstream_replay_comparison_report.json"
    report_path.write_bytes(_canon(report))
    print(json.dumps({"report_path": str(report_path), "report_sha256": report["artifact_sha256"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
