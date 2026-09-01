"""End-to-end replay regression for MARKET_WIDE_FINANCIAL_ENTITY_CLASSIFICATION_SCALEOUT_V1.

Reruns the real market-wide chain (feature store -> Financial V2 engine/scaleout ->
product integration) against this repo's own committed retained-evidence inputs plus the
config/promoted_entity_classifications_scaleout_v1.json this milestone produced, and
checks it against every number named in the milestone brief:

  - exact 1,492 structured-financial denominator, zero silent ticker drops
  - the original 520-ticker legacy regression oracle is byte-for-byte unaffected
  - the pre-existing 455 industrial + 71 limited-financial tickers keep their exact
    feature semantics (not just their family label)
  - product denominator stays 1,699 with zero silent ticker drops
  - the six-label security-stance distribution is unchanged

The legacy engine artifact and the opportunity/decision-context artifacts are retained
evidence from sibling milestone worktrees on this workspace, not part of this repo's own
git history (see AGENTS.md / operations-review/ conventions) -- this test skips instead of
failing when a fresh checkout does not have that sibling evidence on disk.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = REPO_ROOT.parent.parent
PERIOD_SEMANTICS_DIR = REPO_ROOT / "operations-review" / "market-wide-structured-financial-period-semantics-v1-20260831"
LEGACY_ENGINE_ARTIFACT = (
    WORKSPACE_ROOT / "worktrees" / "stock-core-financial-analysis-engine-v2-20260901"
    / "operations-review" / "market-wide-financial-analysis-engine-v2-20260901"
    / "financial_analysis_context_v2_artifact.json"
)
PRODUCT_CONTEXT_DIR = (
    WORKSPACE_ROOT / "worktrees" / "stock-core-financial-analysis-v2-product-ai-bundle-integration-v1-20260901"
    / "operations-review" / "financial-analysis-v2-product-ai-bundle-integration-v1-20260901"
)

EXPECTED_STANCE_DISTRIBUTION = {
    "ACCUMULATE_RESEARCH_CANDIDATE": 183, "AVOID_NEW_ENTRY": 344, "HIGH_RISK_SPECULATION_ONLY": 30,
    "INITIATE_RESEARCH_CANDIDATE": 52, "INSUFFICIENT_EVIDENCE": 188, "WAIT_FOR_CONFIRMATION": 902,
}

pytestmark = pytest.mark.skipif(
    not (LEGACY_ENGINE_ARTIFACT.is_file() and (PRODUCT_CONTEXT_DIR / "opportunity_context_artifact.json").is_file()),
    reason="Sibling-worktree retained evidence (legacy engine / opportunity / decision context "
           "artifacts) not present on this machine; see module docstring.",
)


@pytest.fixture(scope="module")
def before_after_artifacts(tmp_path_factory):
    import market_wide_fundamental_feature_store as store
    import market_wide_financial_analysis_v2_scaleout as scaleout
    from financial_analysis_product_projection import build_product_projection
    from security_decision_context import build_ticker_decision

    semantics_summary = json.loads((PERIOD_SEMANTICS_DIR / "structured_financial_period_semantics_artifact.json")
                                   .read_text(encoding="utf-8"))
    with gzip.open(PERIOD_SEMANTICS_DIR / "structured_financial_period_semantics_facts.jsonl.gz", "rt",
                   encoding="utf-8") as handle:
        semantic_rows = [json.loads(line) for line in handle if line.strip()]
    legacy = json.loads(LEGACY_ENGINE_ARTIFACT.read_text(encoding="utf-8")).get("records", {})
    opportunity = json.loads((PRODUCT_CONTEXT_DIR / "opportunity_context_artifact.json").read_text(encoding="utf-8"))

    def build_engine_artifact(requested_at: str) -> dict:
        feature_artifact = store.build_artifact(
            semantic_rows=semantic_rows, period_semantics_identity=semantics_summary["artifact_identity"],
            requested_at=requested_at,
        )
        records = feature_artifact.pop("records")
        return scaleout.build_scaleout(
            semantic_rows=semantic_rows, feature_records=records, feature_store_artifact=feature_artifact,
            period_semantics_identity=semantics_summary["artifact_identity"], requested_at=requested_at,
            legacy_records=legacy,
        )

    # "before": temporarily hide the scale-out promotion tier so the feature store falls
    # back to exactly today's pre-milestone 40-ticker layered authority.
    scaleout_promoted_path = REPO_ROOT / "config" / "promoted_entity_classifications_scaleout_v1.json"
    assert scaleout_promoted_path.is_file(), "This milestone's own promotion output must exist to replay it"
    moved_aside = tmp_path_factory.mktemp("hidden") / "promoted_entity_classifications_scaleout_v1.json"
    scaleout_promoted_path.rename(moved_aside)
    try:
        before = build_engine_artifact("2026-09-01T00:00:00+07:00")
    finally:
        moved_aside.rename(scaleout_promoted_path)
    after = build_engine_artifact("2026-09-01T00:00:00+07:00")

    product_after = build_product_projection(financial_context=after, product_tickers=sorted(opportunity["records"]),
                                             requested_at="2026-09-01T00:00:00+07:00")
    decisions_after = {ticker: build_ticker_decision({**record, "financial_analysis": product_after["records"][ticker]})
                       for ticker, record in opportunity["records"].items()}
    return before, after, product_after, decisions_after


def test_denominator_unchanged_and_zero_drops(before_after_artifacts):
    before, after, _product, _decisions = before_after_artifacts
    assert before["coverage"]["ticker_denominator"] == 1492
    assert after["coverage"]["ticker_denominator"] == 1492
    assert after["coverage"]["zero_silent_ticker_drops"] is True
    assert set(before["records"]) == set(after["records"])


def test_before_matches_milestone_brief_baseline(before_after_artifacts):
    before, _after, _p, _d = before_after_artifacts
    assert before["coverage"]["issuer_family_distribution"] == {
        "INDUSTRIAL_FINANCIAL_ANALYSIS": 455,
        "OTHER_FINANCIAL_LIMITED_ANALYSIS": 71,
        "UNCLASSIFIED_GENERIC_FINANCIAL_ANALYSIS": 966,
    }
    assert before["coverage"]["current_research_ready_count"] == 455


def test_legacy_regression_oracle_is_byte_identical(before_after_artifacts):
    before, after, _p, _d = before_after_artifacts
    legacy_tickers = {t for t, r in before["records"].items()
                      if any(f.get("source_tier") == "LEGACY_V2_REGRESSION_ORACLE" for f in r["features"].values())}
    assert len(legacy_tickers) == 520

    def strip_volatile(rec):
        r = dict(rec)
        r.pop("source_identities", None)
        return r

    for ticker in legacy_tickers:
        assert strip_volatile(before["records"][ticker]) == strip_volatile(after["records"][ticker]), ticker


def test_previously_classified_tickers_preserve_exact_feature_semantics(before_after_artifacts):
    before, after, _p, _d = before_after_artifacts
    already_classified = {t for t, r in before["records"].items()
                          if r["analysis_family"] != "UNCLASSIFIED_GENERIC_FINANCIAL_ANALYSIS"}
    assert len(already_classified) == 526  # 455 industrial + 71 limited, today's baseline

    def strip_volatile(rec):
        r = dict(rec)
        r.pop("source_identities", None)
        return r

    for ticker in already_classified:
        assert strip_volatile(before["records"][ticker]) == strip_volatile(after["records"][ticker]), ticker


def test_scaleout_widens_industrial_and_limited_without_inflating_unknown_away(before_after_artifacts):
    _before, after, _p, _d = before_after_artifacts
    dist = after["coverage"]["issuer_family_distribution"]
    assert dist["INDUSTRIAL_FINANCIAL_ANALYSIS"] >= 455
    assert dist["OTHER_FINANCIAL_LIMITED_ANALYSIS"] >= 71
    assert (dist["INDUSTRIAL_FINANCIAL_ANALYSIS"] + dist["OTHER_FINANCIAL_LIMITED_ANALYSIS"]
           + dist["UNCLASSIFIED_GENERIC_FINANCIAL_ANALYSIS"]) == 1492


def test_product_denominator_and_zero_drops_unchanged(before_after_artifacts):
    _before, _after, product_after, _d = before_after_artifacts
    assert product_after["coverage"]["ticker_denominator"] == 1699
    assert product_after["coverage"]["zero_silent_ticker_drops"] is True
    assert product_after["coverage"]["compact_coverage"] == 1492
    assert product_after["coverage"]["absent_coverage"] == 207


def test_classification_never_lights_readiness_by_itself(before_after_artifacts):
    """current_research_ready must only ever be true alongside INDUSTRIAL_FINANCIAL_ANALYSIS
    -- classification widens which tickers are even considered, it never manufactures the
    READY feature that actually earns the flag."""
    _before, after, _p, _d = before_after_artifacts
    offenders = [t for t, r in after["records"].items()
                if r["current_research_ready"] and r["analysis_family"] != "INDUSTRIAL_FINANCIAL_ANALYSIS"]
    assert offenders == []


def test_mixed_provider_roa_proxy_never_promoted_to_ready(before_after_artifacts):
    _before, after, _p, _d = before_after_artifacts
    fitness_values = {rec["features"]["mixed_provider_roa_proxy"]["fitness"]
                      for rec in after["records"].values() if "mixed_provider_roa_proxy" in rec["features"]}
    assert "READY" not in fitness_values


def test_security_stance_distribution_unchanged(before_after_artifacts):
    _before, _after, _product, decisions_after = before_after_artifacts
    distribution: dict[str, int] = {}
    for decision in decisions_after.values():
        stance = decision["research_stance"]
        distribution[stance] = distribution.get(stance, 0) + 1
    assert distribution == EXPECTED_STANCE_DISTRIBUTION
