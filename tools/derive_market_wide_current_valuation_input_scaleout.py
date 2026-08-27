"""Offline materializer for market-wide CURRENT RESEARCH valuation inputs.

Writes a new prospective artifact. It refuses to overwrite the governed
2026-08-21 / 2026-08-24 frozen valuation identities.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from field_temporal_contract import stable_id
from market_wide_current_fundamental_research import content_identity as fundamental_content_identity
from market_wide_current_valuation_input_scaleout import (
    attach_shadow_proxy_valuation,
    build_current_valuation_artifact,
    content_identity,
    official_research_universe_tickers,
)
from market_wide_current_shares_resolver import resolve_market_wide_shares
from tools.run_p3f6_mva_provider_share_proxy import _metadata

OPS = ROOT / "operations-review"
DEFAULT_OUTPUT = OPS / "market-wide-current-valuation-research-scaleout-v1" / "market_wide_current_valuation_artifact.json"
DEFAULT_REPORT = OPS / "market-wide-current-valuation-research-scaleout-v1" / "market_wide_current_valuation_research_scaleout_report.json"
DEFAULT_FUNDAMENTAL = OPS / "market-wide-current-fundamental-research-v1-20260823" / "market_wide_current_fundamental_research_artifact.json"
DEFAULT_SHARES = OPS / "p3f5-current-share-promotion-review-20260820" / "p3f5_current_share_promotion_review_artifact.json"
DEFAULT_P3E = OPS / "p3e-fundamental-coverage-closeout-20260820" / "p3e_fundamental_coverage_closeout_artifact.json"
DEFAULT_OFFICIAL_UNIVERSE = OPS / "current-official-market-universe-integration-v1-20260824" / "current_official_market_universe_artifact.json"
FROZEN_OUTPUTS = {
    (OPS / "market-wide-current-valuation-v1-20260824" / "market_wide_current_valuation_artifact.json").resolve(),
    (OPS / "market-wide-current-valuation-v1-20260824-session20260824" / "market_wide_current_valuation_artifact.json").resolve(),
    (OPS / "market-wide-current-valuation-v1-20260825-session20260825" / "market_wide_current_valuation_artifact.json").resolve(),
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_sources(price: dict, fundamental: dict, shares: dict, p3e: dict, official: dict | None) -> None:
    for source, hash_key in ((price, "snapshot_sha256"), (shares, "artifact_sha256"), (p3e, "artifact_sha256")):
        payload = dict(source)
        for key in ("artifact_sha256", "artifact_identity", "snapshot_sha256", "snapshot_identity"):
            payload.pop(key, None)
        if stable_id(payload) != source.get(hash_key):
            raise ValueError(f"SOURCE_SELF_VERIFICATION_FAILED:{hash_key}")
    if fundamental_content_identity(fundamental)["artifact_sha256"] != fundamental.get("artifact_sha256"):
        raise ValueError("SOURCE_SELF_VERIFICATION_FAILED:fundamental")
    if official is not None:
        from current_official_market_universe import _identity as official_identity
        expected = official_identity(official)
        if expected["artifact_sha256"] != official.get("artifact_sha256"):
            raise ValueError("SOURCE_SELF_VERIFICATION_FAILED:official_universe")


def _refuse_frozen_output(output: Path) -> None:
    if output.resolve() in FROZEN_OUTPUTS:
        raise ValueError("REFUSING_TO_OVERWRITE_FROZEN_VALUATION_ARTIFACT")


def _report(artifact: dict) -> dict:
    coverage = artifact["coverage"]
    return {
        "artifact_identity": artifact["artifact_identity"],
        "valuation_session": artifact["valuation_session"],
        "universe_denominator": coverage["universe_denominator"],
        "denominator_reconciles": coverage["denominator_reconciles"],
        "unexplained_denominator_drift": coverage["unexplained_denominator_drift"],
        "price_ready": coverage["price_ready"],
        "share_authority_tiers": coverage["share_authority_tiers"],
        "research_share_eligible": coverage["research_share_eligible"],
        "authoritative_share_ready": coverage["share_ready"],
        "financial_authority_tiers": coverage["financial_authority_tiers"],
        "entity_classes": coverage["entity_classes"],
        "metric_ready_counts": coverage["metric_ready_counts"],
        "metric_research_usable_counts": coverage["metric_research_usable_counts"],
        "metric_blocked_counts": coverage["metric_blocked_counts"],
        "metric_not_applicable_counts": coverage["metric_not_applicable_counts"],
        "blocked_reason_counts": coverage["blocked_reason_counts"],
        "sector_archetype_breakdown": coverage["sector_archetype_breakdown"],
        "input_coverage": coverage.get("input_coverage"),
        "first_blocker_counts": coverage.get("first_blocker_counts"),
        "value_strategy_readiness": artifact["value_strategy_readiness"],
        "authority_boundary": artifact["authority_boundary"],
        "shadow_proxy_valuation_coverage": artifact.get("shadow_proxy_valuation_coverage"),
    }


def materialize(output: Path = DEFAULT_OUTPUT, *, price: Path,
                fundamental: Path = DEFAULT_FUNDAMENTAL, shares: Path = DEFAULT_SHARES,
                p3e: Path = DEFAULT_P3E, official_universe: Path | None = DEFAULT_OFFICIAL_UNIVERSE,
                runtime_root: Path | None = None, report: Path = DEFAULT_REPORT,
                expected_session: str | None = None) -> dict:
    if runtime_root is None:
        raise ValueError("RUNTIME_ROOT_REQUIRED_FOR_RETAINED_PROVIDER_SHARE_INVENTORY")
    _refuse_frozen_output(output)
    price_source, fundamental_source, share_source, p3e_source = _load(price), _load(fundamental), _load(shares), _load(p3e)
    official_source = _load(official_universe) if official_universe is not None else None
    _verify_sources(price_source, fundamental_source, share_source, p3e_source, official_source)
    session = str(price_source["resolved_completed_session"])
    if expected_session is not None and session != expected_session:
        raise ValueError("VALUATION_PRICE_SESSION_MISMATCH:" + session + "!=" + expected_session)
    if str(price_source.get("retained_snapshot_session") or session) != session:
        raise ValueError("VALUATION_PRICE_SNAPSHOT_SESSION_NOT_EXACT:" + session)
    safety = resolve_market_wide_shares(runtime_root, session)
    if safety.get("status") != "measured" or not safety.get("counts_reconcile"):
        raise ValueError("RETAINED_SHARE_INVENTORY_UNREADABLE_OR_NONRECONCILING")
    artifact = build_current_valuation_artifact(
        price_snapshot=price_source, fundamental_artifact=fundamental_source,
        share_promotion_artifact=share_source, share_resolution=safety,
        official_universe=official_source, p3e_artifact=p3e_source,
    )
    official_tickers = official_research_universe_tickers(official_source)
    if official_tickers is not None and len(official_tickers) != artifact["coverage"]["universe_denominator"]:
        raise ValueError("OFFICIAL_UNIVERSE_DENOMINATOR_DRIFT")
    artifact = attach_shadow_proxy_valuation(
        authoritative_artifact=artifact, price_snapshot=price_source, p3e_artifact=p3e_source,
        provider_observations=_metadata(runtime_root), safety_states=safety["tickers"],
    )
    artifact["retained_provider_share_inventory"] = {
        "runtime_metadata_universe": safety["active_universe_count"],
        "usable_positive_observations": safety["usable_share_value_count"],
        "authority_counts": safety["counts"], "session": session,
    }
    artifact.update(content_identity(artifact))
    if content_identity(artifact)["artifact_sha256"] != artifact["artifact_sha256"]:
        raise ValueError("ARTIFACT_SELF_VERIFICATION_FAILED")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(_report(artifact), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--price", type=Path, required=True,
                        help="Exact-session P3F9B snapshot for the requested valuation session. No silent 2026-08-21 default.")
    parser.add_argument("--expected-session", help="Fail closed unless the price snapshot resolved session matches.")
    parser.add_argument("--fundamental", type=Path, default=DEFAULT_FUNDAMENTAL)
    parser.add_argument("--shares", type=Path, default=DEFAULT_SHARES)
    parser.add_argument("--p3e", type=Path, default=DEFAULT_P3E)
    parser.add_argument("--official-universe", type=Path, default=DEFAULT_OFFICIAL_UNIVERSE)
    args = parser.parse_args()
    artifact = materialize(
        args.output, runtime_root=args.runtime_root, price=args.price, fundamental=args.fundamental,
        shares=args.shares, p3e=args.p3e, official_universe=args.official_universe, report=args.report,
        expected_session=args.expected_session,
    )
    print(json.dumps({
        "artifact_identity": artifact["artifact_identity"],
        "valuation_session": artifact["valuation_session"],
        "universe_denominator": artifact["coverage"]["universe_denominator"],
        "denominator_reconciles": artifact["coverage"]["denominator_reconciles"],
        "price_ready": artifact["coverage"]["price_ready"],
        "metric_research_usable_counts": artifact["coverage"]["metric_research_usable_counts"],
        "metric_ready_counts": artifact["coverage"]["metric_ready_counts"],
        "value_strategy_eligible": artifact["value_strategy_readiness"]["eligible"],
        "value_strategy_blocked": artifact["value_strategy_readiness"]["blocked"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
