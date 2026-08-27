"""CURRENT_FINANCIAL_FACT_COVERAGE_RECOVERY_AND_SCALEOUT_V1.

Follow-on inside the existing current-fundamental / current-valuation evidence lane (not a new
valuation engine, financial model, or provider promotion). Widens
``market_wide_current_fundamental_research.py``'s frozen 523-name 2026-08-20 cohort to the full
1,507-name official research universe by reusing three already-existing, unmodified build
functions (see ``financial_fact_coverage_recovery.py``) against the exact same retained raw/
canonical financial stores, official evidence panel, and source registry those functions already
read. Then reruns the unchanged ``market_wide_current_valuation_input_scaleout`` valuation formulas
with the wider fundamental artifact substituted for the narrow one, holding price, share-authority
(the already-recovered 2026-08-27 share artifact), official-universe, and P3E inputs identical --
isolating the financial-fact-coverage effect alone from the preceding shares-recovery milestone's
own effect.

Writes only to a new, non-frozen ``operations-review`` directory. No frozen prior artifact is
rewritten, no network call is made, and no VALUE/authority promotion occurs.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import financial_fact_coverage_recovery as ffcr
import market_wide_current_fundamental_research as mwcfr
import p3f10_fundamental_evidence_scaleout as p3f10mod
import p3f13_official_financial_evidence_scaleout as p3f13mod
from market_wide_current_valuation_input_scaleout import build_current_valuation_artifact, content_identity as valuation_identity
from field_temporal_contract import stable_id

OPS = ROOT / "operations-review"
OUTPUT_DIR = OPS / "current-financial-fact-coverage-recovery-and-scaleout-v1-20260827"

DEFAULT_OFFICIAL_UNIVERSE = OPS / "current-official-market-universe-integration-v1-20260824" / "current_official_market_universe_artifact.json"
DEFAULT_P3F5 = OPS / "p3f5-current-share-promotion-review-20260820" / "p3f5_current_share_promotion_review_artifact.json"
DEFAULT_SHARE_AUTHORITY = OPS / "current-common-shares-authority-recovery-and-scaleout-v1-20260827" / "current_common_shares_authority_recovered_artifact.json"
DEFAULT_PRICE_SNAPSHOT = (
    OPS / "canonical-post-close-v1" / "2026-08-26" / "post-close-attempt-191900" / "operations-review"
    / "p3f9b-market-wide-exact-session-scaleout-20260826" / "p3f9b_mva_exact_session_snapshot.json"
)
NARROW_FUNDAMENTAL = OPS / "market-wide-current-fundamental-research-v1-20260823" / "market_wide_current_fundamental_research_artifact.json"

SESSION = "2026-08-26"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_wide_fundamental_artifact(*, official_tickers: list[str], as_of_session: str) -> tuple[dict, dict, dict]:
    raw_state = _read(p3f10mod.DEFAULT_RAW_STATE)
    canonical_state = _read(p3f10mod.DEFAULT_CANONICAL_STATE)
    p3e = _read(p3f10mod.DEFAULT_P3E)
    registry = _read(p3f10mod.DEFAULT_REGISTRY)
    manifest = _read(p3f13mod.DEFAULT_MANIFEST)

    p3f10_wide = ffcr.build_extended_p3f10_artifact(
        official_tickers=official_tickers, raw_state=raw_state, canonical_state=canonical_state,
        p3e=p3e, registry=registry, as_of_session=as_of_session,
    )
    p3f13_wide = ffcr.build_extended_p3f13_artifact(
        p3f10_wide=p3f10_wide, p3e=p3e, registry=registry, manifest_records=manifest.get("records", []),
        evidence_root=p3f13mod.DEFAULT_EVIDENCE_ROOT, raw_obs_dir=p3f13mod.DEFAULT_RAW_OBS_DIR,
    )
    provider_series = mwcfr.load_retained_provider_series(mwcfr.DEFAULT_CANONICAL_FACTS_ROOT)
    fundamental_wide = ffcr.build_extended_fundamental_artifact(
        p3f10_wide=p3f10_wide, p3f13_wide=p3f13_wide,
        requested_at=f"{as_of_session}T00:00:00Z", provider_series_by_ticker=provider_series,
    )
    return p3f10_wide, p3f13_wide, fundamental_wide


def build_valuation(*, fundamental_artifact: dict, price: dict, p3f5: dict, official: dict,
                    p3e: dict, share_authority: dict) -> dict:
    valuation = build_current_valuation_artifact(
        price_snapshot=price, fundamental_artifact=fundamental_artifact, share_promotion_artifact=p3f5,
        official_universe=official, p3e_artifact=p3e, share_authority_artifact=share_authority,
    )
    valuation.update(valuation_identity(valuation))
    return valuation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", default=SESSION)
    parser.add_argument("--official-universe", type=Path, default=DEFAULT_OFFICIAL_UNIVERSE)
    parser.add_argument("--share-authority", type=Path, default=DEFAULT_SHARE_AUTHORITY)
    parser.add_argument("--price-snapshot", type=Path, default=DEFAULT_PRICE_SNAPSHOT)
    parser.add_argument("--narrow-fundamental", type=Path, default=NARROW_FUNDAMENTAL)
    args = parser.parse_args()

    official = _read(args.official_universe)
    official_tickers = ffcr.official_research_universe_tickers(official)
    if len(official_tickers) != 1507:
        raise ValueError(f"OFFICIAL_UNIVERSE_DENOMINATOR_DRIFT:{len(official_tickers)}")

    p3f10_wide, p3f13_wide, fundamental_wide = build_wide_fundamental_artifact(
        official_tickers=official_tickers, as_of_session=args.session,
    )

    canonical_presence = ffcr.load_canonical_metric_presence(mwcfr.DEFAULT_CANONICAL_FACTS_ROOT)
    official_facts = ffcr.load_official_facts_by_ticker(p3f13_wide)
    identity_inventory = ffcr.build_financial_identity_inventory(fundamental_wide, canonical_presence, official_facts)
    if not identity_inventory["residual_zero"]:
        raise ValueError(f"IDENTITY_INVENTORY_RESIDUAL_NONZERO:{identity_inventory['residual']}")

    p3e = _read(p3f10mod.DEFAULT_P3E)
    p3f5 = _read(DEFAULT_P3F5)
    price = _read(args.price_snapshot)
    share_authority = _read(args.share_authority)
    fundamental_narrow = _read(args.narrow_fundamental)

    valuation_narrow = build_valuation(
        fundamental_artifact=fundamental_narrow, price=price, p3f5=p3f5, official=official,
        p3e=p3e, share_authority=share_authority,
    )
    valuation_wide = build_valuation(
        fundamental_artifact=fundamental_wide, price=price, p3f5=p3f5, official=official,
        p3e=p3e, share_authority=share_authority,
    )

    report = ffcr.build_recovery_coverage_report(
        narrow_fundamental=fundamental_narrow, wide_fundamental=fundamental_wide,
        narrow_valuation=valuation_narrow, wide_valuation=valuation_wide,
        identity_inventory=identity_inventory,
    )
    report["as_of_session"] = args.session
    report["source_artifacts"] = {
        "p3f10_wide": p3f10_wide.get("artifact_identity"),
        "p3f13_wide": p3f13_wide.get("artifact_identity"),
        "fundamental_wide": fundamental_wide.get("artifact_identity"),
        "fundamental_narrow": fundamental_narrow.get("artifact_identity"),
        "valuation_narrow": valuation_narrow.get("artifact_identity"),
        "valuation_wide": valuation_wide.get("artifact_identity"),
        "share_authority": share_authority.get("artifact_identity"),
        "official_universe": official.get("artifact_identity"),
    }
    report["report_sha256"] = stable_id(report)

    _write(OUTPUT_DIR / "p3f10_wide_artifact.json", p3f10_wide)
    _write(OUTPUT_DIR / "p3f13_wide_artifact.json", p3f13_wide)
    _write(OUTPUT_DIR / "market_wide_current_fundamental_research_wide_artifact.json", fundamental_wide)
    _write(OUTPUT_DIR / "financial_identity_inventory.json", identity_inventory)
    _write(OUTPUT_DIR / "market_wide_current_valuation_artifact.json", valuation_wide)
    _write(OUTPUT_DIR / "recovery_report.json", report)

    print(json.dumps({
        "fundamental_wide_identity": fundamental_wide.get("artifact_identity"),
        "valuation_wide_identity": valuation_wide.get("artifact_identity"),
        "identity_inventory_residual": identity_inventory["residual"],
        "authority_tier_distribution_after": report["authority_tier_distribution"]["after"],
        "entity_class_distribution_after": report["entity_class_distribution"]["after"],
        "metric_research_usable_counts_after": report["valuation_metric_research_usable_counts"]["after_financial_fact_recovery"],
        "first_blocker_counts_overall_after": report["first_blocker_counts_overall"]["after_financial_fact_recovery"],
        "value_strategy_activated": report["authority_boundary"]["value_strategy_activated"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
