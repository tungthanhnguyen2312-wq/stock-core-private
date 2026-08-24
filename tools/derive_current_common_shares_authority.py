"""Offline materializer for current common-share authority and prospective valuation feed."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_common_shares_authority import (
    COMMON_OUTSTANDING,
    build_current_common_shares_authority,
)
from current_official_market_universe import _identity as official_identity
from field_temporal_contract import stable_id
from market_wide_current_fundamental_research import content_identity as fundamental_content_identity
from market_wide_current_valuation_input_scaleout import (
    build_current_valuation_artifact,
    content_identity,
    official_research_universe_tickers,
)

OPS = ROOT / "operations-review"
DEFAULT_OUTPUT_DIR = OPS / "current-common-shares-authority-and-scaleout-v1"
DEFAULT_OFFICIAL_UNIVERSE = OPS / "current-official-market-universe-integration-v1-20260824" / "current_official_market_universe_artifact.json"
DEFAULT_VALUATION = OPS / "market-wide-current-valuation-research-scaleout-v1" / "market_wide_current_valuation_artifact.json"
DEFAULT_VALUATION_REPORT = OPS / "market-wide-current-valuation-research-scaleout-v1" / "market_wide_current_valuation_research_scaleout_report.json"
DEFAULT_P3F4 = OPS / "p3f4-generic-current-share-authority-20260820" / "p3f4_generic_current_share_authority_artifact.json"
DEFAULT_P3F5 = OPS / "p3f5-current-share-promotion-review-20260820" / "p3f5_current_share_promotion_review_artifact.json"
DEFAULT_EVENTS = OPS / "current-official-event-context-integration-v1-20260824" / "current_official_event_context_artifact.json"
DEFAULT_PRICE = OPS / "p3f9b-market-wide-exact-session-scaleout-20260821" / "p3f9b_mva_exact_session_snapshot.json"
DEFAULT_FUNDAMENTAL = OPS / "market-wide-current-fundamental-research-v1-20260823" / "market_wide_current_fundamental_research_artifact.json"
DEFAULT_SHARES = OPS / "p3f5-current-share-promotion-review-20260820" / "p3f5_current_share_promotion_review_artifact.json"
DEFAULT_P3E = OPS / "p3e-fundamental-coverage-closeout-20260820" / "p3e_fundamental_coverage_closeout_artifact.json"
FROZEN_OUTPUTS = {
    (OPS / "market-wide-current-valuation-v1-20260824" / "market_wide_current_valuation_artifact.json").resolve(),
    (OPS / "market-wide-current-valuation-v1-20260824-session20260824" / "market_wide_current_valuation_artifact.json").resolve(),
}
FROZEN_IDENTITIES = {
    "market_wide_current_valuation:e6d015f2feee4cc5c5969d7a1fddac9d2f1b2b55918adb4ea199920e4455b29a",
    "market_wide_current_valuation:b9ca122464fa5e70c127bae642a32ac4dacc786f1682a828445c5754f4110388",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _refuse_frozen_output(output: Path) -> None:
    if output.resolve() in FROZEN_OUTPUTS:
        raise ValueError("REFUSING_TO_OVERWRITE_FROZEN_VALUATION_ARTIFACT")


def share_resolution_from_valuation(valuation: dict) -> dict:
    return {
        "resolver_version": "2.0.0",
        "session_date": valuation["valuation_session"],
        "status": "measured",
        "tickers": {
            ticker: dict(row.get("share_basis_input", {}).get("retained_evidence") or {})
            for ticker, row in (valuation.get("records") or {}).items()
        },
    }


def official_anchors_from_reviews(p3f4: dict, p3f5: dict) -> tuple[dict, dict]:
    coverage = (((p3f4.get("representative_proofs") or {}).get("executed_transition") or {}).get("bridge_result") or {}).get("coverage_through")
    common: dict[str, dict] = {}
    period_end: dict[str, dict] = {}
    for row in p3f5.get("official_comparison_matrix") or []:
        ticker = str(row.get("ticker") or "").upper()
        official = row.get("official") or {}
        if not ticker or not official:
            continue
        identity = official.get("identity")
        payload = {
            "identity": identity,
            "value": official.get("value"),
            "effective_date": official.get("effective_on"),
            "effective_on": official.get("effective_on"),
            "citation_id": official.get("citation_id"),
            "qualification_state": "QUALIFIED",
            "source": "official_retained_evidence",
        }
        if identity == COMMON_OUTSTANDING:
            payload["coverage_through"] = coverage
            common[ticker] = payload
        elif identity == "period_end_shares":
            period_end[ticker] = payload
    return common, period_end


def events_by_ticker(event_artifact: dict) -> dict[str, list[dict]]:
    rows = {}
    for ticker, record in (event_artifact.get("records") or {}).items():
        rows[str(ticker).upper()] = list(record.get("events") or [])
    return rows


def _metric_unlock(before: dict, after: dict) -> dict:
    methods = ("market_cap", "P/E", "P/B", "P/S", "enterprise_value", "EV/Sales", "EV/EBITDA")
    return {
        method: {
            "READY_before": (before.get("metric_ready_counts") or {}).get(method, 0),
            "READY_after": (after.get("metric_ready_counts") or {}).get(method, 0),
            "RESEARCH_USABLE_before": (before.get("metric_research_usable_counts") or {}).get(method, 0),
            "RESEARCH_USABLE_after": (after.get("metric_research_usable_counts") or {}).get(method, 0),
            "blocked_before": (before.get("metric_blocked_counts") or {}).get(method, 0),
            "blocked_after": (after.get("metric_blocked_counts") or {}).get(method, 0),
        }
        for method in methods
    }


def materialize(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    official_universe: Path = DEFAULT_OFFICIAL_UNIVERSE,
    valuation: Path = DEFAULT_VALUATION,
    valuation_report: Path = DEFAULT_VALUATION_REPORT,
    p3f4: Path = DEFAULT_P3F4,
    p3f5: Path = DEFAULT_P3F5,
    events: Path = DEFAULT_EVENTS,
    price: Path = DEFAULT_PRICE,
    fundamental: Path = DEFAULT_FUNDAMENTAL,
    shares: Path = DEFAULT_SHARES,
    p3e: Path = DEFAULT_P3E,
) -> dict:
    share_output = output_dir / "current_common_shares_authority_artifact.json"
    valuation_output = output_dir / "market_wide_current_valuation_artifact.json"
    report_output = output_dir / "current_common_shares_authority_scaleout_report.json"
    _refuse_frozen_output(valuation_output)
    official = _load(official_universe)
    prior_valuation = _load(valuation)
    prior_report = _load(valuation_report)
    p4, p5, event_artifact = _load(p3f4), _load(p3f5), _load(events)
    price_source, fundamental_source, share_source, p3e_source = _load(price), _load(fundamental), _load(shares), _load(p3e)
    expected_official = official_identity(official)
    if expected_official["artifact_sha256"] != official.get("artifact_sha256"):
        raise ValueError("SOURCE_SELF_VERIFICATION_FAILED:official_universe")
    for source, hash_key in ((price_source, "snapshot_sha256"), (share_source, "artifact_sha256"), (p3e_source, "artifact_sha256")):
        payload = dict(source)
        for key in ("artifact_sha256", "artifact_identity", "snapshot_sha256", "snapshot_identity"):
            payload.pop(key, None)
        if stable_id(payload) != source.get(hash_key):
            raise ValueError(f"SOURCE_SELF_VERIFICATION_FAILED:{hash_key}")
    if fundamental_content_identity(fundamental_source)["artifact_sha256"] != fundamental_source.get("artifact_sha256"):
        raise ValueError("SOURCE_SELF_VERIFICATION_FAILED:fundamental")
    if prior_valuation.get("artifact_identity") in FROZEN_IDENTITIES:
        raise ValueError("REFUSING_TO_TREAT_FROZEN_VALUATION_AS_MUTABLE_INPUT")
    session = str(prior_valuation["valuation_session"])
    common, period_end = official_anchors_from_reviews(p4, p5)
    share_artifact = build_current_common_shares_authority(
        session=session, official_universe=official,
        share_resolution=share_resolution_from_valuation(prior_valuation),
        official_common_anchors=common, official_period_end_anchors=period_end,
        official_events_by_ticker=events_by_ticker(event_artifact),
        source_identities={
            "official_universe": official.get("artifact_identity"),
            "prior_valuation": prior_valuation.get("artifact_identity"),
            "p3f4": p4.get("artifact_identity"),
            "p3f5": p5.get("artifact_identity"),
            "official_event_context": event_artifact.get("artifact_identity"),
        },
    )
    if official_research_universe_tickers(official) is None or len(share_artifact["records"]) != 1507:
        raise ValueError("OFFICIAL_UNIVERSE_DENOMINATOR_DRIFT")
    valuation_artifact = build_current_valuation_artifact(
        price_snapshot=price_source, fundamental_artifact=fundamental_source,
        share_promotion_artifact=share_source, share_resolution=share_resolution_from_valuation(prior_valuation),
        official_universe=official, p3e_artifact=p3e_source, share_authority_artifact=share_artifact,
    )
    valuation_artifact.update(content_identity(valuation_artifact))
    if valuation_artifact["artifact_identity"] in FROZEN_IDENTITIES:
        raise ValueError("FROZEN_VALUATION_IDENTITY_MUTATED")
    if content_identity(valuation_artifact)["artifact_sha256"] != valuation_artifact["artifact_sha256"]:
        raise ValueError("ARTIFACT_SELF_VERIFICATION_FAILED")
    report = {
        "share_artifact_identity": share_artifact["artifact_identity"],
        "valuation_artifact_identity": valuation_artifact["artifact_identity"],
        "prior_valuation_artifact_identity": prior_valuation.get("artifact_identity"),
        "as_of_session": session,
        "universe_denominator": share_artifact["coverage"]["universe_denominator"],
        "denominator_reconciles": share_artifact["coverage"]["denominator_reconciles"],
        "unexplained_count": share_artifact["coverage"]["unexplained_count"],
        "authority_tier_distribution": share_artifact["coverage"]["authority_tier_distribution"],
        "major_blocker_reasons": share_artifact["coverage"]["major_blocker_reasons"],
        "verdict": share_artifact["verdict"],
        "valuation_unlock": _metric_unlock(prior_report, valuation_artifact["coverage"]),
        "value_eligibility_before": (prior_report.get("value_strategy_readiness") or {}).get("eligible", 0),
        "value_eligibility_after": valuation_artifact["value_strategy_readiness"]["eligible"],
        "value_blocked_before": (prior_report.get("value_strategy_readiness") or {}).get("blocked", 1507),
        "value_blocked_after": valuation_artifact["value_strategy_readiness"]["blocked"],
        "frozen_identities_unchanged": sorted(FROZEN_IDENTITIES),
        "generic_authority_source_promoted": False,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    share_output.write_text(json.dumps(share_artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    valuation_output.write_text(json.dumps(valuation_artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"share": share_artifact, "valuation": valuation_artifact, "report": report}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    result = materialize(args.output_dir)
    print(json.dumps({
        "share_artifact_identity": result["share"]["artifact_identity"],
        "valuation_artifact_identity": result["valuation"]["artifact_identity"],
        "verdict": result["share"]["verdict"],
        "authority_tier_distribution": result["share"]["coverage"]["authority_tier_distribution"],
        "value_eligible": result["valuation"]["value_strategy_readiness"]["eligible"],
    }, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
