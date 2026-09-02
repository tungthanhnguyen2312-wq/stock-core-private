"""Tests for LEGACY_ENTITY_CLASSIFICATION_TRACKED_AUTHORITY_RECOVERY_V1.

MARKET_WIDE_FINANCIAL_ENTITY_CLASSIFICATION_SCALEOUT_V1 (94e6aba) reported a final
1,382 INDUSTRIAL / 85 LIMITED / 25 UNKNOWN entity-family split, but 520 of the 526 tickers
it called "already-classified, preserved byte-identical" were in fact supplied only through
`market_wide_financial_analysis_v2_scaleout.build_scaleout()`'s optional `legacy_records`
argument, itself populated at replay time from an untracked sibling-worktree artifact. This
module recovers that classification into a fourth, tracked `entity_classification_contract`
authority tier (`config/promoted_entity_classifications_legacy_recovery_v1.json`) and proves
the market-wide chain no longer needs the untracked artifact to reproduce the entity-family
split.

Two of the legacy artifact's 523 records (F88, OGC) carry `issuer_type="unknown"` -- the old
engine's binary corporate-vs-not-corporate split had still bucketed them into
`OTHER_FINANCIAL_LIMITED_ANALYSIS` by default, which is not positive evidence of a specific
financial entity class (independently corroborated: FUNDAMENTAL_ENTITY_CLASS_AND_SECTOR_
APPLICABILITY_SCALEOUT_V1, 2026-08-23, separately found both UNKNOWN). They are correctly
never promoted, which is why a faithful recovery reproduces 1,382 / 83 / 27, not 1,382 / 85 / 25.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from entity_classification_contract import (
    ClassificationStatus,
    ConfidenceSemantics,
    DEFAULT_LEGACY_RECOVERY_CLASSIFICATIONS_PATH,
    EntityClass,
    EntityClassificationRecord,
    EvidenceTier,
    load_layered_entity_profiles,
    load_legacy_recovery_entity_classifications,
    load_promoted_entity_classifications,
    load_scaleout_promoted_entity_classifications,
    load_seed_profiles,
    resolve_layered_entity_classification,
)

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = DEFAULT_LEGACY_RECOVERY_CLASSIFICATIONS_PATH
PERIOD_SEMANTICS_DIR = ROOT / "operations-review" / "market-wide-structured-financial-period-semantics-v1-20260831"
CONSUMING_MILESTONE_CHECKPOINT = "94e6abae38d71aa4f43331d2d212f38fa7de1cf7"

# Legacy issuer_type was "unknown" for these two -- never positive evidence, never promoted.
LEGACY_UNKNOWN_TICKERS = {"F88", "OGC"}


def _synthetic_record(ticker: str, entity_class: EntityClass, evidence_tier: EvidenceTier,
                      reason: str = "synthetic") -> EntityClassificationRecord:
    return EntityClassificationRecord(
        issuer_identity=f"candidate:synthetic:{ticker}", ticker=ticker, legal_name=None,
        entity_class=entity_class, classification_status=ClassificationStatus.QUALIFIED,
        confidence_semantics=ConfidenceSemantics.DETERMINISTIC_PROOF, evidence_tier=evidence_tier,
        classification_evidence_id=f"synthetic_hash_{ticker}", source_id="test", source_record_id=None,
        effective_from=None, knowledge_available_at=None, verified_at="2026-09-02T00:00:00Z",
        classification_reason=reason,
    )


def test_manifest_exists_and_is_well_formed():
    assert MANIFEST_PATH.is_file(), "the recovery manifest must be tracked and present"
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert data["authority_type"] == "RECOVERED_PREVIOUSLY_ACCEPTED_CURRENT_STATE_AUTHORITY"
    assert data["authority_scope"] == "CURRENT_STATE_ONLY"
    assert data["historical_pit_authority"] == "NOT_ESTABLISHED"
    assert data["source_consuming_milestone_checkpoint"] == CONSUMING_MILESTONE_CHECKPOINT
    assert data["source_cohort_selector"] == "LEGACY_HISTORICAL_FROZEN_523_V1"
    records = data["promoted_records"]
    assert len(records) == data["promoted_record_count"] == 488
    assert data["class_breakdown"] == {
        "corporate": 431, "bank": 22, "securities": 30, "insurance": 5, "finance_company": 0, "unknown": 0,
    }
    for ticker in LEGACY_UNKNOWN_TICKERS:
        assert ticker not in records, f"{ticker}'s legacy issuer_type is unknown; must never be promoted"
    for ticker, rec in records.items():
        assert rec["classification_status"] == "QUALIFIED"
        assert rec["entity_class"] in {"corporate", "bank", "securities", "insurance", "finance_company"}
        assert rec["evidence_tier"] == "legacy_accepted_milestone_replay"
        assert rec["supporting_evidence"]["consuming_milestone_checkpoint"] == CONSUMING_MILESTONE_CHECKPOINT
        assert rec["supporting_evidence"]["legacy_source_cohort_selector"] == "LEGACY_HISTORICAL_FROZEN_523_V1"


def test_manifest_deterministic_from_the_tool():
    """Re-running the promotion tool against the same legacy artifact must reproduce the
    manifest's record set and class breakdown exactly (excluding the volatile verified_at
    timestamp and the evidence hash that is bound to it)."""
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import run_legacy_entity_classification_recovery_v1 as runner

    legacy_artifact = (
        ROOT.parent.parent / "worktrees" / "stock-core-financial-analysis-engine-v2-20260901"
        / "operations-review" / "market-wide-financial-analysis-engine-v2-20260901"
        / "financial_analysis_context_v2_artifact.json"
    )
    if not legacy_artifact.is_file():
        pytest.skip("retained sibling-worktree legacy engine artifact not present on this machine")

    promotion, diagnostics = runner.build_recovery(
        legacy_engine_artifact=legacy_artifact, generated_at="2026-09-02T00:00:00+00:00",
    )
    assert diagnostics["legacy_record_count"] == 523
    assert diagnostics["recovered_count"] == 488
    assert diagnostics["already_tracked_identical_count"] == 33
    assert diagnostics["conflict_count"] == 0
    assert diagnostics["legacy_unknown_count"] == 2
    assert set(promotion["promoted_records"]) == set(
        json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["promoted_records"]
    )


def test_manifest_never_duplicates_seed_or_original_promoted():
    """Recovery fills gaps only -- it must never re-list a ticker seed/original-promoted own."""
    seed = load_seed_profiles()
    promoted = load_promoted_entity_classifications()
    recovery = load_legacy_recovery_entity_classifications()
    assert set(recovery) & set(seed) == set()
    assert set(recovery) & set(promoted) == set()


def test_recovery_tier_disjoint_from_scaleout_tier_in_practice():
    """The scale-out milestone classified only the population still unclassified after this
    legacy cohort, so in practice no ticker is named by both tiers."""
    recovery = load_legacy_recovery_entity_classifications()
    scaleout = load_scaleout_promoted_entity_classifications()
    assert set(recovery) & set(scaleout) == set()


def test_seed_authority_wins_over_legacy_recovery():
    res = resolve_layered_entity_classification("HPG")
    assert res.authority_tier == "curated_seed_authority"
    assert res.resolved_entity_class == EntityClass.CORPORATE


def test_original_promoted_authority_wins_over_legacy_recovery():
    res = resolve_layered_entity_classification("AAA")
    assert res.authority_tier == "promoted_record_authority"


def test_legacy_recovery_fills_a_real_tracked_gap():
    recovery = load_legacy_recovery_entity_classifications()
    seed, promoted = load_seed_profiles(), load_promoted_entity_classifications()
    sample = next(t for t in sorted(recovery) if t not in seed and t not in promoted)
    res = resolve_layered_entity_classification(sample)
    assert res.authority_tier == "legacy_recovery_record_authority"
    assert res.classification_status == ClassificationStatus.QUALIFIED
    assert res.is_positive_authority is True
    assert res.resolved_entity_class.value == recovery[sample].entity_class.value


def test_legacy_recovery_precedes_scaleout_when_both_could_apply():
    """Synthetic same-ticker case (the real tiers are disjoint today, see above): when a
    legacy-recovery record and a scale-out record both exist, legacy-recovery must win."""
    legacy_rec = _synthetic_record("ZZZ9", EntityClass.CORPORATE, EvidenceTier.LEGACY_ACCEPTED_MILESTONE_REPLAY)
    scaleout_rec = _synthetic_record("ZZZ9", EntityClass.SECURITIES, EvidenceTier.EXCHANGE_INDUSTRY_CLASSIFICATION)
    res = resolve_layered_entity_classification(
        "ZZZ9", seed_profiles={}, promoted_records={},
        legacy_recovery_records={"ZZZ9": legacy_rec}, scaleout_promoted_records={"ZZZ9": scaleout_rec},
    )
    assert res.authority_tier == "legacy_recovery_record_authority"
    assert res.resolved_entity_class == EntityClass.CORPORATE


def test_scaleout_still_resolves_names_legacy_recovery_does_not_cover():
    scaleout = load_scaleout_promoted_entity_classifications()
    recovery = load_legacy_recovery_entity_classifications()
    sample = [t for t in sorted(scaleout) if t not in recovery][:25]
    assert sample, "expected scale-out-only tickers to sample from"
    for ticker in sample:
        res = resolve_layered_entity_classification(ticker)
        assert res.authority_tier == "scaleout_promoted_record_authority"
        assert res.resolved_entity_class.value == scaleout[ticker].entity_class.value


def test_conflict_between_seed_and_legacy_recovery_fails_closed():
    conflicting = _synthetic_record("HPG", EntityClass.BANK, EvidenceTier.LEGACY_ACCEPTED_MILESTONE_REPLAY,
                                    reason="synthetic conflict")
    res = resolve_layered_entity_classification(
        "HPG", seed_profiles={"HPG": "corporate"}, promoted_records={},
        legacy_recovery_records={"HPG": conflicting},
    )
    assert res.classification_status == ClassificationStatus.CONFLICT
    assert res.resolved_entity_class == EntityClass.UNKNOWN
    assert res.is_positive_authority is False
    assert "disagrees with legacy-recovery record" in res.reason


def test_legacy_unknown_tickers_remain_unknown():
    """F88/OGC's own legacy issuer_type was unknown; they must never gain positive authority."""
    recovery = load_legacy_recovery_entity_classifications()
    for ticker in LEGACY_UNKNOWN_TICKERS:
        assert ticker not in recovery
        res = resolve_layered_entity_classification(ticker)
        assert res.resolved_entity_class == EntityClass.UNKNOWN
        assert res.is_positive_authority is False


def test_unnamed_ticker_still_resolves_unknown():
    res = resolve_layered_entity_classification("ZZZ_NOT_IN_ANY_TIER")
    assert res.resolved_entity_class == EntityClass.UNKNOWN
    assert res.classification_status == ClassificationStatus.UNKNOWN
    assert res.is_positive_authority is False


def test_layered_profiles_merged_count_includes_recovery_tier():
    seed, promoted = load_seed_profiles(), load_promoted_entity_classifications()
    recovery = load_legacy_recovery_entity_classifications()
    scaleout = load_scaleout_promoted_entity_classifications()
    profiles = load_layered_entity_profiles()
    assert len(profiles) == len(seed) + len(promoted) + len(recovery) + len(scaleout)
    # No ticker's resolved class in the merged view can disagree with its owning tier.
    for ticker, entity_type in profiles.items():
        res = resolve_layered_entity_classification(ticker)
        assert res.resolved_entity_class.value == entity_type


@pytest.mark.skipif(not PERIOD_SEMANTICS_DIR.is_dir(), reason="retained period-semantics evidence not present")
def test_current_replay_reproduces_entity_distribution_without_legacy_records():
    """The point of this milestone: market_wide_financial_analysis_v2_scaleout.build_scaleout()
    reproduces the (evidence-supported) entity-family split from tracked repository inputs
    alone -- no legacy_records argument, no sibling-worktree artifact required."""
    import market_wide_financial_analysis_v2_scaleout as scaleout
    import market_wide_fundamental_feature_store as store

    semantics_summary = json.loads(
        (PERIOD_SEMANTICS_DIR / "structured_financial_period_semantics_artifact.json").read_text(encoding="utf-8")
    )
    with gzip.open(PERIOD_SEMANTICS_DIR / "structured_financial_period_semantics_facts.jsonl.gz", "rt",
                   encoding="utf-8") as handle:
        semantic_rows = [json.loads(line) for line in handle if line.strip()]

    feature_artifact = store.build_artifact(
        semantic_rows=semantic_rows, period_semantics_identity=semantics_summary["artifact_identity"],
        requested_at="2026-09-02T00:00:00+07:00",
    )
    records = feature_artifact.pop("records")
    artifact = scaleout.build_scaleout(
        semantic_rows=semantic_rows, feature_records=records, feature_store_artifact=feature_artifact,
        period_semantics_identity=semantics_summary["artifact_identity"], requested_at="2026-09-02T00:00:00+07:00",
    )  # deliberately no legacy_records argument at all

    assert artifact["coverage"]["ticker_denominator"] == 1492
    assert artifact["coverage"]["zero_silent_ticker_drops"] is True
    assert artifact["scaleout"]["legacy_523_regression_ticker_count"] == 0
    dist = artifact["coverage"]["issuer_family_distribution"]
    # 1,382 is exact; LIMITED/UNKNOWN are 2 short of the historically-quoted 85/25 because
    # F88/OGC are correctly excluded (see module docstring) -- COHERENT_PARTIAL_BY_
    # UNRECOVERABLE_LEGACY_AUTHORITY, not a forced/optimized number.
    assert dist == {
        "INDUSTRIAL_FINANCIAL_ANALYSIS": 1382,
        "OTHER_FINANCIAL_LIMITED_ANALYSIS": 83,
        "UNCLASSIFIED_GENERIC_FINANCIAL_ANALYSIS": 27,
    }
    assert artifact["coverage"]["current_research_ready_count"] == 1380


@pytest.mark.skipif(not PERIOD_SEMANTICS_DIR.is_dir(), reason="retained period-semantics evidence not present")
def test_bank_specialist_tickers_remain_governed_by_pre_existing_authority():
    for ticker in ("ABB", "ACB", "BID", "MBB", "TCB", "VCB"):
        res = resolve_layered_entity_classification(ticker)
        assert res.resolved_entity_class == EntityClass.BANK
        assert res.authority_tier in {"curated_seed_authority", "promoted_record_authority"}
