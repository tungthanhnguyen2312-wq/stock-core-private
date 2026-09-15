"""Write the bounded real-official corporate-action factor-evidence audit.

Offline replay only: the one permitted HNX RSS request was retained beforehand by
``official_document_acquisition``.  This command makes no network/provider/Daily call.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from hnx_disclosure_feed_parser import parse_disclosure_rss  # noqa: E402
from official_source_registry import load_registry  # noqa: E402
from real_official_corporate_action_factor_evidence import select_candidates  # noqa: E402

EVENTS = REPO_ROOT / "operations-review/current-official-event-context-integration-v1-20260824/current_official_event_context_artifact.json"
UNIVERSE = REPO_ROOT / "operations-review/current-official-market-universe-refresh-v1-20260913/current_official_market_universe_artifact.json"
RETENTION = REPO_ROOT / "operations-review/real-official-corporate-action-factor-chain-evidence-v1-20260915/official_document_retention"
MANIFEST = RETENTION / "official_document_acquisition_manifest.json"
OUTPUT = RETENTION.parent / "real_official_corporate_action_factor_chain_evidence_20260915.json"
SESSION = "2026-09-15"


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(artifact: dict) -> None:
    artifact["artifact_sha256"] = hashlib.sha256(_canonical(artifact).encode("utf-8")).hexdigest()
    artifact["artifact_identity"] = "real_official_corporate_action_factor_chain_evidence:" + artifact["artifact_sha256"]


def build_artifact() -> dict:
    event_context = json.loads(EVENTS.read_text(encoding="utf-8"))
    universe = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    feed = next((row for row in manifest["records"] if row.get("document_class") == "disclosure_rss_feed"), None)
    if feed is None:
        raise ValueError("retained_hnx_disclosure_rss_missing")
    raw_path = RETENTION / str(feed["relative_path"])
    parsed = parse_disclosure_rss(raw_path.read_bytes(), feed_url=str(feed["canonical_url"]), source_id="hnx", registry=load_registry())
    selection = select_candidates(
        event_context["all_current_universe_event_records"],
        reference_tickers=universe["records"].keys(), cutoff_date=SESSION,
    )
    target_tickers = {row["ticker"] for row in selection["candidates"]}
    target_feed_rows = [row for row in parsed["items"] if any(ticker in (row.get("title") or "") for ticker in target_tickers)]
    return {
        "contract_version": "real_official_corporate_action_factor_chain_evidence/v1",
        "milestone": "REAL_OFFICIAL_CORPORATE_ACTION_FACTOR_CHAIN_EVIDENCE_V1",
        "session": SESSION,
        "authority_boundary": {
            "official_index_bridge": "EXPLICIT_EX_DATE_ONLY_NOT_LEDGER_OBSERVATION",
            "ledger_ratio_or_share_count_inferred": False,
            "planned_or_future_execution_treated_as_executed": False,
            "provider_network_calls": False,
            "daily_execution": False,
            "runtime_root_written": False,
            "dashboard_publication": False,
        },
        "source_artifacts": {
            "hnx_rights_event_index": {
                "path": str(EVENTS.relative_to(REPO_ROOT)),
                "artifact_identity": event_context.get("artifact_identity"),
                "source_contract": "hnx_official_rights_event_index/v1",
            },
            "reference_collection": {
                "path": str(UNIVERSE.relative_to(REPO_ROOT)),
                "artifact_identity": universe.get("artifact_identity"),
                "record_count": len(universe["records"]),
            },
            "retained_hnx_disclosure_feed": {
                "document_id": feed["document_id"], "content_sha256": feed["sha256"],
                "canonical_url": feed["canonical_url"], "observed_at": feed["observed_at"],
                "extraction_status": feed["extraction_status"],
            },
        },
        "candidate_selection": selection,
        "retained_feed_parse": {
            "item_count": parsed["item_count"], "candidate_count": parsed["candidate_count"],
            "target_tickers": sorted(target_tickers), "target_item_count": len(target_feed_rows),
            "target_items": target_feed_rows,
        },
        "factor_chain_evaluation": {
            "real_factor_chain_qualified_count": 0,
            "ledger_observations_emitted": 0,
            "reason": "no_exact_candidate_official_detail_notice_locator_in_retained_approved_hnx_rss_window",
        },
        "pit_price_series_qualification": {
            "status": "NOT_EVALUATED_NO_REAL_FACTOR_CHAIN_QUALIFIED",
            "reason": "raw_input_basis_authority_not_requested_without_real_factor_chain",
        },
        "source_ceiling": {
            "status": "OFFICIAL_EVIDENCE_ACQUIRED_PARTIAL_BY_SOURCE_CEILING",
            "reason_codes": [
                "retained_hnx_rss_window_has_no_exact_candidate_detail_locator",
                "hnx_rights_event_index_has_no_ratio_or_executed_lifecycle_fields",
                "no_operator_supplied_finite_vsdc_or_issuer_ir_document_url",
                "unbounded_historical_search_or_url_pattern_invention_prohibited",
            ],
        },
    }


def main() -> None:
    artifact = build_artifact()
    _identity(artifact)
    OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(REPO_ROOT)}")
    print(f"artifact_identity: {artifact['artifact_identity']}")
    print("selected:", ", ".join(row["ticker"] for row in artifact["candidate_selection"]["candidates"]))
    print("factor_chain_qualified:", artifact["factor_chain_evaluation"]["real_factor_chain_qualified_count"])


if __name__ == "__main__":
    main()
