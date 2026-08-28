"""FINANCIAL_OPERATIONAL_PROXY_FOUNDATION_AND_RESEARCH_TIER_ACTIVATION_V1.

Builds the new `financial_operational_proxy/v1` artifact (see `financial_operational_proxy.py`)
over a bounded, real, retained-evidence proof cohort, then demonstrates a real before -> after
integration into the existing `market_wide_current_fundamental_research.py` research consumer via
its new optional `operational_proxy_by_ticker` attach point.

Proof cohort (regression evidence, not the product universe -- the architecture in
`financial_operational_proxy.py` is parameterized over any ticker list and is not limited to
these names):
  * HPG, VNM, PAN, FPT, PVD, NVL, POW, SSI, PNJ -- ordinary corporate issuers that are both
    owner-focus (`config/owner_research_focus.json`) and already OFFICIAL_QUALIFIED in the
    current 13-issuer P3-F13 panel, each with real retained provider financial history. HPG,
    PAN, and FPT independently reconcile at least one fact EXACT_MATCH against that panel,
    proving the OPERATIONAL_PROXY -> VERIFIED_RESEARCH_EVIDENCE upgrade fires on real data, not
    only in a synthetic test fixture.
  * VCB -- a bank. Sector-safety negative case: `financial_operational_proxy.py` is bounded to
    `entity_type == "corporate"` this milestone, so VCB must receive zero operational-proxy
    facts regardless of what provider data is retained for it.
  * A32 -- a corporate ticker with a confirmed zero retained-provider-financial-source
    disposition (`financial_authority_tiers.BLOCKED` in the 2026-08-27 financial-fact-coverage
    -recovery artifact). No-source negative case, distinct from the sector-safety one.

Foreground, offline, deterministic: reads only already-retained bytes under
`operations-review/`, makes no network call, runs no OCR, calls no Vision/LLM API, mutates no
production DB, and touches no Dashboard/valuation/ranking/recommendation/sizing/PIT authority.
Writes only to a new, non-frozen `operations-review/` directory; no frozen prior artifact is
rewritten.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import canonical_fact_store as store  # noqa: E402
import financial_operational_proxy as fop  # noqa: E402
import market_wide_current_fundamental_research as mwcfr  # noqa: E402
import p3f13_official_financial_evidence_scaleout as p3f13mod  # noqa: E402

OPS = ROOT / "operations-review"
OUTPUT_DIR = OPS / "financial-operational-proxy-foundation-and-research-tier-activation-v1-20260828"
RUNTIME_ROOT = OPS / "p1f-milestone-20260803" / "shadow-build-b"
PROFILES_PATH = ROOT / "config" / "ticker_entity_profiles.csv"

# Full proof cohort for the standalone operational-proxy artifact (ticker-list-agnostic).
PROOF_COHORT = ["HPG", "VNM", "PAN", "FPT", "PVD", "NVL", "POW", "SSI", "PNJ", "VCB", "A32"]
# The subset market_wide_current_fundamental_research.py's own frozen 523-name P3F10 cohort
# actually covers -- A32 is outside that pre-existing, unrelated cohort boundary (a constraint
# of that consumer, not introduced here), so the mwcfr before/after integration below is scoped
# to this subset. A32's negative-case behaviour is still fully proven in the standalone artifact.
MWCFR_COHORT_SUBSET = ["HPG", "VNM", "PAN", "FPT", "PVD", "NVL", "POW", "SSI", "PNJ", "VCB"]

OWNER_FOCUS_OVERLAP = ["HPG", "VNM", "PAN", "FPT", "PVD", "NVL", "POW", "SSI", "PNJ"]


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requested-at", default="2026-08-28T00:00:00+07:00",
                        help="Fixed timestamp for deterministic offline replay (excluded from artifact content identity).")
    args = parser.parse_args()

    profiles = store.load_entity_profiles(PROFILES_PATH)
    citations = store.load_official_citations(RUNTIME_ROOT)

    facts_by_ticker: dict[str, list[dict[str, Any]]] = {}
    entity_type_by_ticker: dict[str, str | None] = {}
    for ticker in PROOF_COHORT:
        built = store.build_ticker_facts(RUNTIME_ROOT, ticker, profiles=profiles, official_citations=citations)
        facts_by_ticker[ticker] = built["facts"]
        entity_type_by_ticker[ticker] = built["applicability"]["archetype"].get("issuer_entity_type")

    p3f13_current = p3f13mod.execute()
    panel = p3f13_current["refreshed_panel_data"]

    proxy_artifact = fop.build_operational_proxy_artifact(
        tickers=PROOF_COHORT, facts_by_ticker=facts_by_ticker, entity_type_by_ticker=entity_type_by_ticker,
        refreshed_panel_data=panel, requested_at=args.requested_at,
    )

    # BEFORE: the existing research consumer, called exactly as every existing caller already
    # calls it -- no operational_proxy_by_ticker kwarg at all.
    p3f10_frozen = json.loads(mwcfr.DEFAULT_P3F10_FROZEN.read_text(encoding="utf-8"))
    provider_series = mwcfr.load_retained_provider_series(mwcfr.DEFAULT_CANONICAL_FACTS_ROOT)
    before_artifact = mwcfr.build_artifact(
        p3f10_frozen=p3f10_frozen, p3f13_current=p3f13_current, requested_at=args.requested_at,
        provider_series_by_ticker=provider_series,
    )

    # AFTER: the identical call, with only the new optional attach added.
    after_artifact = mwcfr.build_artifact(
        p3f10_frozen=p3f10_frozen, p3f13_current=p3f13_current, requested_at=args.requested_at,
        provider_series_by_ticker=provider_series,
        operational_proxy_by_ticker={ticker: proxy_artifact["records"][ticker] for ticker in MWCFR_COHORT_SUBSET},
    )

    before_official_qualified = sum(1 for row in before_artifact["records"].values() if row["authority_tier"] == mwcfr.OFFICIAL_TIER)
    after_official_qualified = sum(1 for row in after_artifact["records"].values() if row["authority_tier"] == mwcfr.OFFICIAL_TIER)
    before_provider_research = sum(1 for row in before_artifact["records"].values() if row["authority_tier"] == mwcfr.PROVIDER_TIER)
    after_provider_research = sum(1 for row in after_artifact["records"].values() if row["authority_tier"] == mwcfr.PROVIDER_TIER)

    reconciliation_overlap_tickers = sorted(
        ticker for ticker in PROOF_COHORT
        if proxy_artifact["records"].get(ticker, {}).get("tier_counts", {}).get("VERIFIED_RESEARCH_EVIDENCE", 0) > 0
    )

    report: dict[str, Any] = {
        "milestone": "FINANCIAL_OPERATIONAL_PROXY_FOUNDATION_AND_RESEARCH_TIER_ACTIVATION_V1",
        "proof_cohort": PROOF_COHORT,
        "proof_cohort_roles": {
            "ordinary_corporate_official_qualified_with_provider_history": MWCFR_COHORT_SUBSET[:-1],
            "owner_focus_overlap": OWNER_FOCUS_OVERLAP,
            "negative_sector_blocked_case": "VCB",
            "negative_no_source_blocked_case": "A32",
            "authoritative_reconciliation_overlap_cases": reconciliation_overlap_tickers,
        },
        "operational_proxy_artifact_identity": proxy_artifact["artifact_identity"],
        "operational_proxy_coverage": proxy_artifact["coverage"],
        "per_ticker_tier_counts": {ticker: proxy_artifact["records"][ticker]["tier_counts"] for ticker in PROOF_COHORT},
        "before_after_research_consumer": {
            "before": {
                "artifact_identity": before_artifact["artifact_identity"],
                "official_qualified_issuer_count": before_official_qualified,
                "provider_research_issuer_count": before_provider_research,
                "has_operational_proxy_coverage_section": "operational_proxy_coverage" in before_artifact,
                "records_with_operational_proxy_key": sum(1 for row in before_artifact["records"].values() if "operational_proxy" in row),
            },
            "after": {
                "artifact_identity": after_artifact["artifact_identity"],
                "official_qualified_issuer_count": after_official_qualified,
                "provider_research_issuer_count": after_provider_research,
                "operational_proxy_coverage": after_artifact.get("operational_proxy_coverage"),
                "records_with_operational_proxy_key": sum(1 for row in after_artifact["records"].values() if "operational_proxy" in row),
            },
        },
        "authority_boundary": {
            "official_qualified_issuer_count_unchanged": before_official_qualified == after_official_qualified,
            "provider_research_issuer_count_unchanged": before_provider_research == after_provider_research,
            "before_artifact_identity_differs_from_after": before_artifact["artifact_identity"] != after_artifact["artifact_identity"],
            "new_provider_added": False,
            "new_official_evidence_acquired": False,
            "ocr_used": False,
            "vision_used": False,
            "network_used": False,
            "production_db_touched": False,
            "dashboard_touched": False,
            "value_ranking_recommendation_target_probability_sizing_pit_promoted": False,
        },
    }

    _write(OUTPUT_DIR / "financial_operational_proxy_artifact.json", proxy_artifact)
    _write(OUTPUT_DIR / "market_wide_current_fundamental_research_before_artifact.json", before_artifact)
    _write(OUTPUT_DIR / "market_wide_current_fundamental_research_after_artifact.json", after_artifact)
    _write(OUTPUT_DIR / "before_after_report.json", report)

    print(json.dumps({
        "operational_proxy_identity": proxy_artifact["artifact_identity"],
        "coverage": proxy_artifact["coverage"],
        "reconciliation_overlap_tickers": reconciliation_overlap_tickers,
        "before_official_qualified": before_official_qualified,
        "after_official_qualified": after_official_qualified,
        "official_qualified_unchanged": before_official_qualified == after_official_qualified,
        "after_operational_proxy_coverage": after_artifact.get("operational_proxy_coverage"),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
