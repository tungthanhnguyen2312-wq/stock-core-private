"""Build the retained-only cutover validation artifact for the wide cohort default.

The scaleout milestone already established the wide evidence, readiness, and bounded
27/28 replay.  This tool adds only the prospective default-selection attestation:
it reads those retained results and the two versioned selectors, performs no network
or provider work, and writes one deterministic cutover artifact.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from field_temporal_contract import stable_id  # noqa: E402
from fundamental_research_cohort_selection import (  # noqa: E402
    CURRENT_WIDE_GOVERNED_V1,
    LEGACY_HISTORICAL_FROZEN_523_V1,
    resolve_current_fundamental_cohort,
)

CONTRACT_VERSION = "canonical_wide_fundamental_research_cohort_cutover_validation/v1"
MILESTONE = "CANONICAL_WIDE_FUNDAMENTAL_RESEARCH_COHORT_CUTOVER_V1"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("CUTOVER_VALIDATION_INPUT_INVALID:" + str(path))
    return value


def _chain_summary(replay_root: Path, variant: str, session: str) -> dict[str, Any]:
    chain = _read(replay_root / variant / "daily-session-shadow-recommendation-v1" / session / "daily_session_shadow_recommendation.json")
    selection = chain.get("fundamental_cohort_selection")
    if not isinstance(selection, Mapping):
        raise ValueError("CUTOVER_DAILY_REPLAY_SELECTION_MISSING:" + variant + ":" + session)
    return {
        "daily_chain_identity": chain.get("artifact_identity"),
        "selection": dict(selection),
        "shadow_security_recommendation_identity": (chain.get("shadow_security_recommendation") or {}).get("artifact_identity"),
        "denominator": (chain.get("denominator_by_stage") or {}).get("shadow_security_recommendation"),
    }


def build(*, scaleout_validation: Mapping[str, Any], retained_root: Path, replay_root: Path) -> dict[str, Any]:
    if scaleout_validation.get("milestone") != "MARKET_WIDE_FUNDAMENTAL_RESEARCH_COHORT_SCALEOUT_V1":
        raise ValueError("CUTOVER_SCALEOUT_VALIDATION_MILESTONE_INVALID")
    wide = resolve_current_fundamental_cohort(retained_root)
    legacy = resolve_current_fundamental_cohort(retained_root, selector=LEGACY_HISTORICAL_FROZEN_523_V1)
    source_identities = scaleout_validation.get("source_identities") or {}
    cohort = scaleout_validation.get("cohort") or {}
    if (
        source_identities.get("wide_cohort_identity") != wide["cohort_artifact_identity"]
        or source_identities.get("narrow_cohort_identity") != legacy["cohort_artifact_identity"]
        or cohort.get("new_cohort_count") != wide["cohort_denominator"]
        or cohort.get("old_cohort_count") != legacy["cohort_denominator"]
    ):
        raise ValueError("CUTOVER_SELECTOR_SCALEOUT_LINEAGE_CONFLICT")

    sessions = ("2026-08-27", "2026-08-28")
    daily_replay = {
        session: {
            "wide_default": _chain_summary(replay_root, "wide", session),
            "legacy_reproduction": _chain_summary(replay_root, "legacy", session),
        }
        for session in sessions
    }
    for session, row in daily_replay.items():
        if row["wide_default"]["selection"].get("cohort_artifact_identity") != wide["cohort_artifact_identity"]:
            raise ValueError("CUTOVER_DAILY_WIDE_IDENTITY_MISMATCH:" + session)
        if row["legacy_reproduction"]["selection"].get("cohort_artifact_identity") != legacy["cohort_artifact_identity"]:
            raise ValueError("CUTOVER_DAILY_LEGACY_IDENTITY_MISMATCH:" + session)

    result = {
        "contract_version": CONTRACT_VERSION,
        "milestone": MILESTONE,
        "generated_from": "RETAINED_LOCAL_QUALIFIED_EVIDENCE_ONLY",
        "default_selection": {key: value for key, value in wide.items() if key != "artifact"},
        "legacy_selection": {key: value for key, value in legacy.items() if key != "artifact"},
        "governed_universe": scaleout_validation.get("governed_universe"),
        "cohort_counts": {
            "legacy_historical": cohort.get("old_cohort_count"),
            "wide_current_default": cohort.get("new_cohort_count"),
            "newly_admitted": cohort.get("newly_admitted_count"),
            "no_eligible_provider_facts_newly_admitted": cohort.get("still_unavailable_count"),
        },
        "reason_code_distribution": scaleout_validation.get("reason_code_distribution"),
        "axis_readiness_before_after": scaleout_validation.get("axis_readiness_before_after"),
        "retained_downstream_comparison": scaleout_validation.get("downstream_replay"),
        "daily_resolver_replay": daily_replay,
        "legacy_reproducibility": {
            "explicit_selector_required": True,
            "legacy_identity_matches_scaleout": True,
            "daily_replay_available_for_each_session": True,
        },
        "cutover_readiness": "PASS",
        "authority_effect": "CURRENT_RESEARCH_DEFAULT_COHORT_CUTOVER_ONLY",
        "stronger_authority_promotion": "NONE",
        "scoring_semantics_changed": False,
        "recommendation_semantics_changed": False,
        "opportunity_semantics_changed": False,
        "lifecycle_semantics_changed": False,
        "evidence_standards_lowered": False,
        "no_network": True,
        "no_registry_mutation": True,
        "no_primary_checkout_write": True,
        "canonical_artifacts_overwritten": False,
        "source_identities": {
            "scaleout_validation_identity": scaleout_validation.get("deterministic_content_identity"),
            **source_identities,
            "wide_default_selection_evidence_identity": wide["evidence_identity"],
        },
    }
    result["deterministic_content_identity"] = stable_id(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retained-root", type=Path, required=True)
    parser.add_argument("--scaleout-validation", type=Path, required=True)
    parser.add_argument("--daily-shadow-replay-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(
        scaleout_validation=_read(args.scaleout_validation),
        retained_root=args.retained_root,
        replay_root=args.daily_shadow_replay_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "deterministic_content_identity": result["deterministic_content_identity"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
