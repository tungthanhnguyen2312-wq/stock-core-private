"""Read-only, deterministic P3-F5 review of the retained VCI share field."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from field_temporal_contract import stable_id
import market_wide_current_shares_resolver as resolver
import provider_share_promotion_review as review
from runtime_paths import runtime_root as resolve_runtime_root

VERSION = "1.0.0"
ARTIFACT_TYPE = "P3F5_CURRENT_SHARE_PROMOTION_REVIEW"
P3F3_PATH = ROOT / "operations-review" / "p3f3-operational-valuation-input-scaleout-20260820" / "p3f3_operational_valuation_input_scaleout_artifact.json"
P3F4_PATH = ROOT / "operations-review" / "p3f4-generic-current-share-authority-20260820" / "p3f4_generic_current_share_authority_artifact.json"
DEFAULT_OUTPUT_DIR = ROOT / "operations-review" / "p3f5-current-share-promotion-review-20260820"


def _metadata(runtime_root: Path) -> dict[str, dict[str, Any]]:
    database = runtime_root / "vn_stock.db"
    connection = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        rows = connection.execute("SELECT ticker, shares_outstanding, updated FROM metadata ORDER BY ticker").fetchall()
    finally:
        connection.close()
    result: dict[str, dict[str, Any]] = {}
    for ticker, value, updated in rows:
        integer = int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 and float(value).is_integer() else None
        result[str(ticker).upper()] = {"value": integer, "observed_on": str(updated)[:10] if updated else None,
                                      "raw_numeric_type": type(value).__name__ if value is not None else "null"}
    return result


def _official_record(anchor: dict[str, Any]) -> dict[str, Any]:
    return {"identity": ("common_shares_outstanding" if anchor.get("identity_type") == "current_shares_outstanding_after_event"
                         else "period_end_shares"), "value": anchor.get("value"),
            "effective_on": anchor.get("effective_date") or (f"{anchor.get('reporting_period')}-12-31" if anchor.get("reporting_frequency") == "annual" else None),
            "citation_id": anchor.get("citation_id")}


def build_review(runtime_root: Path) -> dict[str, Any]:
    p3f3 = json.loads(P3F3_PATH.read_text(encoding="utf-8"))
    p3f4 = json.loads(P3F4_PATH.read_text(encoding="utf-8"))
    session = p3f3["valuation_session"]["valuation_session"]
    metadata = _metadata(runtime_root)
    universe = resolver.resolve_market_wide_shares(runtime_root, session)
    anchors = resolver.load_official_anchors(runtime_root)
    planned = {entry["ticker"] for entry in p3f4["corporate_action_completeness"]
               if entry.get("status") == "NON_EXECUTED_PLANNED_ISSUANCE_BLOCKED"}
    comparisons = []
    for ticker, anchor in sorted(anchors.items()):
        provider = {"identity": review.PROVIDER_IDENTITY, **metadata.get(ticker, {})}
        official = _official_record(anchor)
        comparisons.append({"ticker": ticker, "provider": provider, "official": official,
                            "classification": review.classify_official_comparison(provider, official)})
    for ticker in sorted(planned):
        provider = {"identity": review.PROVIDER_IDENTITY, **metadata.get(ticker, {})}
        comparisons.append({"ticker": ticker, "provider": provider, "official": None,
                            "classification": review.classify_official_comparison(provider, None, corporate_action_ambiguous=True)})
    updates = [row["observed_on"] for row in metadata.values() if row["observed_on"]]
    type_counts = Counter(row["raw_numeric_type"] for row in metadata.values())
    cohort_rows = []
    for price in p3f3["current_price_authority_matrix"]:
        ticker = price["canonical_instrument"]["canonical_ticker"]
        resolution = universe["tickers"][ticker]
        cohort_rows.append({"ticker": ticker, "price_status": price["status"],
                            "provider_value": metadata.get(ticker, {}).get("value"),
                            "resolver_authority": resolution["authority"],
                            "freshness_state": review.provider_freshness_state(resolution)})
    artifact: dict[str, Any] = {
        "schema_version": VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "verdict": "P3F5_CURRENT_SHARE_PROMOTION_REVIEW_COMPLETE",
        "candidate": {"source": review.CANDIDATE_SOURCE, "field_path": "Company(source='VCI').overview().issue_share",
                      "semantic_identity": review.PROVIDER_IDENTITY, "unit": "shares", "authority": "NOT_PROMOTED",
                      "retention": "vn_stock.db:metadata.shares_outstanding with metadata.updated"},
        "source_quality": {"official_source_registry_membership": "NOT_AN_APPROVED_OFFICIAL_EVIDENCE_SOURCE",
                           "provider_documentation_retained": False, "schema_evidence": "meta_sync reads numeric issue_share into SQLite REAL"},
        "coverage_and_scalability": {"metadata_rows": len(metadata), "positive_integral_values": sum(row["value"] is not None for row in metadata.values()),
                                      "missing_or_nonintegral": sum(row["value"] is None for row in metadata.values()),
                                      "numeric_type_distribution": dict(sorted(type_counts.items())),
                                      "observation_date_min": min(updates) if updates else None, "observation_date_max": max(updates) if updates else None,
                                      "canonical_mapping": "ticker primary key; no separate provider-to-canonical mapping proof", "resolver_counts": universe["counts"],
                                      "counts_reconcile": universe["counts_reconcile"]},
        "official_comparison_matrix": comparisons,
        "freshness": {"valuation_session": session, "provider_interpretations": ["PROVIDER_REPORTED_CURRENT", "PROVIDER_REPORTED_STALE", "OBSERVED_WITHOUT_EFFECTIVE_DATE", "UNKNOWN"],
                      "observed_distribution": dict(sorted(Counter(review.provider_freshness_state(row) for row in universe["tickers"].values()).items())),
                      "rule": "latest provider observation does not prove valuation-date common-share validity"},
        "corporate_action_safety": {"share_changing_event_code": "ISS", "unresolved_event_behavior": "withhold provider value when timing is unresolved",
                                     "representative_findings": [entry for entry in p3f4["corporate_action_completeness"]],
                                     "no_inference": ["ex_date", "execution_date", "continuity", "resulting_common_shares"]},
        "proposed_authority_tiers": ["QUALIFIED_OFFICIAL_CURRENT_COMMON_OUTSTANDING", "PROVIDER_REPORTED_CURRENT_ISSUED_SHARES", "PROVIDER_REPORTED_STALE", "PERIOD_END_ONLY", "UNKNOWN"],
        "market_cap_semantic_decision": "ISSUED_SHARES_NOT_ALLOWED_FOR_MARKET_CAP_WITHOUT_SEPARATE_OWNER_APPROVED_PROXY_POLICY",
        "mva_allowed_use_review": {"envelope": review.MVA_ENVELOPE, "candidate_namespace": "PROVIDER_REPORTED_CURRENT_ISSUED_SHARES",
                                   "allowed_if_later_approved": "labelled shadow proxy observation only", "prohibited": ["qualified_official_label", "common_shares_outstanding_alias", "execution", "PIT_backtest", "liquidity_sizing", "automatic_P3F_activation"]},
        "projected_coverage_impact": {"authoritative_current": {"share_ready": 0, "both_ready": 0},
                                      "hypothetical_if_owner_approves_labelled_provider_proxy": review.projected_provider_proxy_coverage(cohort_rows),
                                      "cohort_rows": cohort_rows, "note": "projection is not authority activation or valuation output"},
        "recommendations": {"source": "MORE_EVIDENCE_REQUIRED", "allowed_use": "PROVIDER_PROXY_USE_ONLY", "authority_state": review.AUTHORITY_STATE},
        "risks": ["issued_shares may include treasury shares", "no effective-date semantics", "five-day lag at review session", "partial corporate-event coverage", "undated ISS events", "provider documentation absent"],
        "boundaries": {"p3g": "RESERVED_NOT_STARTED", "source_promotion": False, "runtime_mutation": False, "valuation_formula_change": False},
    }
    artifact["artifact_sha256"] = stable_id(artifact)
    artifact["artifact_identity"] = f"p3f5_current_share_promotion_review:{artifact['artifact_sha256']}"
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)
    artifact = build_review(resolve_runtime_root(args.runtime_root))
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True)
    (output / "p3f5_current_share_promotion_review_artifact.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Artifact identity: {artifact['artifact_identity']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
