"""MARKET_WIDE_FUNDAMENTAL_RESEARCH_COHORT_SCALEOUT_V1 -- consolidated validation artifact.

Pure aggregation over the two bounded reports the sibling derivation/replay tools already
wrote (no recomputation, no new evidence, no network): reads
``root_cause_reconciliation_report.json`` and ``downstream_replay_comparison_report.json``
from ``--input-dir`` and writes one consolidated validation artifact matching this
milestone's required schema.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from field_temporal_contract import stable_id  # noqa: E402

CONTRACT_VERSION = "market_wide_fundamental_research_cohort_scaleout_validation/v1"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build(*, reconciliation: dict, replay: dict) -> dict:
    root_cause = reconciliation["root_cause_reconciliation"]
    universe = root_cause["universe"]
    per_session = replay["per_session"]

    validation = {
        "contract_version": CONTRACT_VERSION,
        "milestone": "MARKET_WIDE_FUNDAMENTAL_RESEARCH_COHORT_SCALEOUT_V1",
        "generated_from": "BOUNDED_LOCAL_RETAINED_ARTIFACTS_ONLY",
        "no_network": True, "no_registry_mutation": True, "no_primary_checkout_write": True,
        "governed_universe": {
            "raw_denominator": universe["raw_denominator"],
            "stocklookup_candidate": universe["stocklookup_candidate"],
            "applicable_official_research_universe": universe["applicable_official_research_universe"],
        },
        "cohort": {
            "old_cohort_count": root_cause["narrow_cohort_size"],
            "old_cohort_source": root_cause["narrow_cohort_source"],
            "new_cohort_count": root_cause["wide_cohort_size"],
            "newly_admitted_count": root_cause["newly_admitted_tickers"]["count"],
            "still_unavailable_count": (
                root_cause["newly_admitted_tickers"]["terminal_disposition_distribution"].get("NO_ELIGIBLE_PROVIDER_FACTS", 0)
                + len(root_cause["residual_official_tickers_missing_from_wide_manifest"])
            ),
            "still_unavailable_definition": "Newly-admitted tickers with terminal_disposition NO_ELIGIBLE_PROVIDER_FACTS (no retained usable financial fact) plus any official-universe ticker absent from the wide manifest entirely (residual). Excludes ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE, which is a deliberate sector-scope boundary, not an evidence gap.",
        },
        "reason_code_distribution": {
            "overall_terminal_disposition": root_cause["terminal_disposition_distribution"]["overall"],
            "by_entity_type": root_cause["terminal_disposition_distribution"]["by_entity_type"],
            "reason_family_map": root_cause["reason_family_map"],
            "newly_admitted_terminal_disposition": root_cause["newly_admitted_tickers"]["terminal_disposition_distribution"],
        },
        "axis_readiness_before_after": reconciliation["coverage_before_after"],
        "sample_newly_admitted_lineage": reconciliation["newly_admitted_sample"],
        "sample_still_unavailable": reconciliation["still_unavailable_sample"],
        "sample_sector_special_case": reconciliation["sector_special_case_sample"],
        "narrow_subset_lineage_diff": reconciliation["narrow_subset_lineage_diff"],
        "downstream_replay": {
            "session_2026_08_27": per_session.get("2026-08-27"),
            "session_2026_08_28": per_session.get("2026-08-28"),
            "recommendation_coverage_delta": {
                "2026-08-27": per_session["2026-08-27"]["recommendation_bundle_retention"],
                "2026-08-28": per_session["2026-08-28"]["recommendation_bundle_retention"],
            },
            "invalidation_coverage_delta": {
                "2026-08-27": per_session["2026-08-27"]["invalidation_bundle_retention"],
                "2026-08-28": per_session["2026-08-28"]["invalidation_bundle_retention"],
            },
            "lifecycle_comparable_recommendation_context": replay["lifecycle_comparable_recommendation_context"],
            "lifecycle_recommendation_transition_matrix": replay["lifecycle_recommendation_transition_matrix"],
            "lifecycle_invalidation_transition_matrix": replay["lifecycle_invalidation_transition_matrix"],
        },
        "warnings": reconciliation["warnings"] + [
            "Session Bundle denominators (106 for 2026-08-27, 123 for 2026-08-28) are driven by "
            "market/tactical same-session inputs, not the fundamental cohort; they are unchanged "
            "before vs after by design -- the delta this milestone produces is in how many of those "
            "same bundle names now find a fundamental-cohort match, not in how many names exist.",
        ],
        "authority_effect": "NONE",
        "is_actionable": False,
        "research_tier": "PROSPECTIVE_MULTI_SESSION_RESEARCH_ONLY",
        "scoring_semantics_changed": False,
        "recommendation_semantics_changed": False,
        "evidence_standards_lowered": False,
        "source_identities": {
            "root_cause_reconciliation_report_sha256": reconciliation["report_sha256"],
            "downstream_replay_comparison_report_sha256": replay["artifact_sha256"],
            "wide_cohort_identity": reconciliation["wide_cohort_identity"],
            "narrow_cohort_identity": reconciliation["narrow_cohort_identity"],
        },
    }
    validation["deterministic_content_identity"] = stable_id(
        {k: v for k, v in validation.items() if k != "deterministic_content_identity"}
    )
    return validation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    reconciliation = _read(args.input_dir / "root_cause_reconciliation_report.json")
    replay = _read(args.input_dir / "replay" / "downstream_replay_comparison_report.json")
    validation = build(reconciliation=reconciliation, replay=replay)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output), "deterministic_content_identity": validation["deterministic_content_identity"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
