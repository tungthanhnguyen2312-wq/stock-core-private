"""MARKET_WIDE_FUNDAMENTAL_RESEARCH_COHORT_SCALEOUT_V1.

Widens ``fundamental_cross_sectional_scoring.py``'s frozen 523-name 2026-08-20 cohort to
the full official research universe by reusing ``fundamental_research_cohort_scaleout.py``
(itself a thin orchestration layer over the already-existing, unmodified
``financial_fact_coverage_recovery`` / ``market_wide_historical_fundamentals_scaleout`` /
``fundamental_cross_sectional_scoring`` builders).

Bulk retained raw/canonical financial evidence used by this replay is large, gitignored,
operator-local data (``operations-review/p1f-milestone-20260803/...``,
``operations-review/governed-official-evidence-v1/...``): it is not git-tracked in a fresh
worktree, so ``--evidence-root`` must point at wherever it is actually retained on this
machine (the primary Producer checkout by default). This script only *reads* from that
root; every write goes under ``--output-dir`` (defaults to a path inside this worktree).
No network call, no registry mutation, no primary-checkout write.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fundamental_research_cohort_scaleout as scaleout  # noqa: E402
import financial_fact_coverage_recovery as ffcr  # noqa: E402
import p3f10_fundamental_evidence_scaleout as p3f10mod  # noqa: E402
import p3f13_official_financial_evidence_scaleout as p3f13mod  # noqa: E402
import market_wide_historical_fundamentals_scaleout as mwhfs  # noqa: E402
from field_temporal_contract import stable_id  # noqa: E402

OPS = ROOT / "operations-review"
OUTPUT_DIR = OPS / "market-wide-fundamental-research-cohort-scaleout-v1-20260830"

DEFAULT_OFFICIAL_UNIVERSE = OPS / "current-official-market-universe-integration-v1-20260824" / "current_official_market_universe_artifact.json"
AS_OF_SESSION = "2026-08-30"
REQUESTED_AT = "2026-08-30T00:00:00+07:00"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _relative(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=ROOT,
                         help="Root whose operations-review/ and config/ hold the retained raw/"
                              "canonical financial evidence this replay reads (read-only). "
                              "Defaults to this worktree; pass the primary checkout's root if the "
                              "bulk data is not git-tracked in the worktree.")
    parser.add_argument("--official-universe", type=Path, default=None,
                         help="Defaults to <evidence-root>/operations-review/current-official-"
                              "market-universe-integration-v1-20260824/"
                              "current_official_market_universe_artifact.json")
    parser.add_argument("--session", default=AS_OF_SESSION)
    parser.add_argument("--requested-at", default=REQUESTED_AT)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    evidence_root: Path = args.evidence_root
    official_universe_path = args.official_universe or (
        evidence_root / "operations-review" / "current-official-market-universe-integration-v1-20260824"
        / "current_official_market_universe_artifact.json"
    )

    official = _read(official_universe_path)
    official_tickers = ffcr.official_research_universe_tickers(official)
    universe_records = official.get("records") or {}
    universe_candidate_count = sum(1 for row in universe_records.values() if row.get("stocklookup_candidate"))

    raw_state = _read(evidence_root / p3f10mod.DEFAULT_RAW_STATE.relative_to(p3f10mod.ROOT))
    canonical_state = _read(evidence_root / p3f10mod.DEFAULT_CANONICAL_STATE.relative_to(p3f10mod.ROOT))
    p3e = _read(evidence_root / p3f10mod.DEFAULT_P3E.relative_to(p3f10mod.ROOT))
    registry = _read(evidence_root / p3f10mod.DEFAULT_REGISTRY.relative_to(p3f10mod.ROOT))
    manifest = _read(evidence_root / p3f13mod.DEFAULT_MANIFEST.relative_to(p3f13mod.ROOT))
    evidence_root_dir = evidence_root / p3f13mod.DEFAULT_EVIDENCE_ROOT.relative_to(p3f13mod.ROOT)
    raw_obs_dir = evidence_root / p3f13mod.DEFAULT_RAW_OBS_DIR.relative_to(p3f13mod.ROOT)

    wide_historical_fundamentals = scaleout.build_wide_historical_fundamentals_artifact(
        official_tickers=official_tickers, raw_state=raw_state, canonical_state=canonical_state,
        p3e=p3e, registry=registry, manifest_records=manifest.get("records", []),
        evidence_root=evidence_root_dir, raw_obs_dir=raw_obs_dir,
        as_of_session=args.session, requested_at=args.requested_at,
    )
    wide_cross_sectional = scaleout.build_wide_fundamental_cross_sectional_artifact(
        wide_historical_fundamentals=wide_historical_fundamentals,
    )

    # Narrow (existing, untouched-default) run for the reconciliation/lineage-diff comparison --
    # calls the exact same unmodified engines with zero arguments, i.e. today's real production
    # default behavior, so "before" in this report is not a synthetic baseline.
    narrow_historical_fundamentals = mwhfs.execute(cohort_selector="LEGACY_HISTORICAL_FROZEN_523_V1")
    narrow_cross_sectional = scaleout.build_wide_fundamental_cross_sectional_artifact(
        wide_historical_fundamentals=narrow_historical_fundamentals,
    )
    narrow_tickers = sorted(narrow_cross_sectional["records"])

    reconciliation = scaleout.build_root_cause_reconciliation(
        universe_raw_denominator=len(universe_records), universe_candidate_count=universe_candidate_count,
        official_tickers=official_tickers, narrow_cohort_tickers=narrow_tickers,
        wide_historical_fundamentals=wide_historical_fundamentals, wide_cross_sectional=wide_cross_sectional,
    )
    lineage_diff = scaleout.build_narrow_vs_wide_lineage_diff(
        narrow_historical_fundamentals=narrow_historical_fundamentals,
        wide_historical_fundamentals=wide_historical_fundamentals, narrow_tickers=narrow_tickers,
    )
    newly_admitted_samples = scaleout.sample_newly_admitted_lineage(
        wide_cross_sectional=wide_cross_sectional, wide_historical_fundamentals=wide_historical_fundamentals,
        narrow_tickers=narrow_tickers,
    )
    still_unavailable_samples = scaleout.sample_still_unavailable(
        official_tickers=official_tickers, wide_historical_fundamentals=wide_historical_fundamentals,
        narrow_tickers=narrow_tickers,
    )
    sector_special_case_samples = scaleout.sample_sector_special_case(
        wide_cross_sectional=wide_cross_sectional, wide_historical_fundamentals=wide_historical_fundamentals,
        narrow_tickers=narrow_tickers,
    )

    report = {
        "contract_version": scaleout.CONTRACT_VERSION,
        "artifact_type": scaleout.ARTIFACT_TYPE,
        "milestone": scaleout.MILESTONE,
        "as_of_session": args.session,
        "requested_at": args.requested_at,
        "evidence_root_used": str(evidence_root),
        "root_cause_reconciliation": reconciliation,
        "narrow_subset_lineage_diff": lineage_diff,
        "newly_admitted_sample": newly_admitted_samples,
        "still_unavailable_sample": still_unavailable_samples,
        "sector_special_case_sample": sector_special_case_samples,
        "narrow_cohort_identity": narrow_cross_sectional.get("artifact_sha256"),
        "wide_cohort_identity": wide_cross_sectional.get("artifact_sha256"),
        "coverage_before_after": {
            "narrow_denominator": narrow_cross_sectional["denominator"],
            "wide_denominator": wide_cross_sectional["denominator"],
            "narrow_axis_ready": narrow_cross_sectional["coverage"]["axis_ready"],
            "wide_axis_ready": wide_cross_sectional["coverage"]["axis_ready"],
        },
        "authority_boundary": {
            "research_only": True, "network_used": False, "ocr_used": False,
            "new_provider_added": False, "valuation_unlocked": False, "recommendation_or_sizing": False,
            "authoritative_counts_before": 13, "authoritative_counts_after": 13,
            "scoring_formula_changed": False, "percentile_definition_changed": False,
            "thresholds_changed": False, "narrow_default_callers_rewired": False,
        },
        "warnings": [
            "Percentile-based axis scores for previously-covered (narrow-523) tickers recompute "
            "against the wider comparable population by design; this is the correct behavior of an "
            "unmodified percentile-based cross-sectional method operating over a wider population, "
            "not a scoring-rule change. See narrow_subset_lineage_diff for proof that underlying "
            "facts/derived_metrics are untouched.",
            "This is a new, additive research artifact. fundamental_cross_sectional_scoring.execute() "
            "and daily_session_shadow_recommendation.SHARED_CONTEXT_RELATIVE_PATHS['fundamental'] are "
            "NOT rewired by this milestone; the narrow 523-member cohort remains the operational "
            "default until a separate, owner-authorized cutover milestone.",
        ],
    }
    report["report_sha256"] = stable_id(report)

    output_dir: Path = args.output_dir
    _write(output_dir / "wide_p3f10_and_p3f13_source" / "market_wide_historical_fundamentals_wide_artifact.json", wide_historical_fundamentals)
    _write(output_dir / "fundamental_cross_sectional_scoring_wide_artifact.json", wide_cross_sectional)
    _write(output_dir / "fundamental_cross_sectional_scoring_narrow_reproduction_artifact.json", narrow_cross_sectional)
    _write(output_dir / "root_cause_reconciliation_report.json", report)

    print(json.dumps({
        "narrow_denominator": narrow_cross_sectional["denominator"],
        "wide_denominator": wide_cross_sectional["denominator"],
        "newly_admitted_count": reconciliation["newly_admitted_tickers"]["count"],
        "still_unavailable_count": len(scaleout.sample_still_unavailable(
            official_tickers=official_tickers, wide_historical_fundamentals=wide_historical_fundamentals,
            narrow_tickers=narrow_tickers, limit=10**9)),
        "terminal_disposition_distribution": reconciliation["terminal_disposition_distribution"]["overall"],
        "narrow_subset_facts_byte_identical": lineage_diff["narrow_subset_facts_byte_identical"],
        "wide_cohort_identity": wide_cross_sectional.get("artifact_sha256"),
        "report_sha256": report["report_sha256"],
        "output_dir": str(output_dir),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
