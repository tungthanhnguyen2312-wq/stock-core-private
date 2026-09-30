"""Replay the bounded historical real-factor evidence audit without network I/O."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bitemporal_semantic_contract import project_official_evidence_temporal_metadata
from corporate_action_events import classify_retained_document, extract_event_observation, extract_text
from official_corporate_action_ledger import build_ledger
from real_official_corporate_action_factor_evidence import select_candidates

EVENTS = ROOT / "operations-review/current-official-event-context-integration-v1-20260824/current_official_event_context_artifact.json"
UNIVERSE = ROOT / "operations-review/current-official-market-universe-refresh-v1-20260913/current_official_market_universe_artifact.json"
EVIDENCE = ROOT / "operations-review/historical-raw-pit-real-factor-chain-qualification-v1-20260930"
RETENTION = EVIDENCE / "official_document_retention"
OUTPUT = EVIDENCE / "historical_raw_pit_real_factor_chain_qualification_20260930.json"


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _page_publication_cutoff(payload: bytes) -> str:
    match = re.search(r"news-public-time[^>]*>\s*(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2})", payload.decode("utf-8", errors="strict"), re.I)
    if not match:
        raise ValueError("official_page_publication_datetime_missing")
    day, month, year, hour, minute = match.groups()
    return f"{year}-{month}-{day}T{hour}:{minute}:00+07:00"


def build_artifact() -> dict:
    events = json.loads(EVENTS.read_text(encoding="utf-8"))
    universe = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    manifest = json.loads((RETENTION / "official_document_acquisition_manifest.json").read_text(encoding="utf-8"))
    selection = select_candidates(
        events["all_current_universe_event_records"],
        reference_tickers=universe["records"].keys(), cutoff_date="2026-09-29",
        listing_by_ticker=universe["records"],
        admitted_route_tickers=universe["records"].keys(),
    )
    vbb_record = next(row for row in manifest["records"] if row["ticker"] == "VBB")
    vbb_payload = (RETENTION / vbb_record["relative_path"]).read_bytes()
    vbb_document = classify_retained_document(vbb_record, vbb_payload)
    vbb_document["published_at"] = _page_publication_cutoff(vbb_payload)
    vbb_observation = extract_event_observation(vbb_document, extract_text(vbb_payload, vbb_record["content_type"]))
    vbb_temporal = project_official_evidence_temporal_metadata({
        "document_id": vbb_record["document_id"], "sha256": vbb_record["sha256"],
        "source_authority": "exchange", "published_at": vbb_document["published_at"],
        "observed_at": vbb_record["observed_at"], "qualification_state": "QUALIFIED",
    })
    ledger = build_ledger([vbb_observation])
    klb_record = next(row for row in manifest["records"] if row["ticker"] == "KLB")
    return {
        "contract_version": "historical_raw_pit_real_factor_chain_qualification/v1",
        "milestone": "HISTORICAL_RAW_PIT_REAL_FACTOR_CHAIN_QUALIFICATION_V1",
        "terminal_disposition": "PARTIAL_OFFICIAL_EVIDENCE_ACQUIRED_NO_QUALIFIED_FACTOR_CHAIN",
        "authority_boundary": {
            "real_factor_chain_qualified_count": 0,
            "market_wide_raw_as_traded_promoted": False,
            "pit_backtest_eligible": False,
            "execution_replay_eligible": False,
            "active_universe": "UNKNOWN",
            "observed_market_ratio_used_as_factor": False,
        },
        "request_ledger": {"discovery_queries": 8, "official_http_document_requests": 2,
                           "official_http_retries": 0, "new_bytes_retained": sum(int(row["content_length"]) for row in manifest["records"])},
        "candidate_selection": selection,
        "official_documents": [
            {key: vbb_record.get(key) for key in ("document_id", "ticker", "canonical_url", "document_class", "sha256", "content_length", "observed_at")},
            {key: klb_record.get(key) for key in ("document_id", "ticker", "canonical_url", "document_class", "sha256", "content_length", "observed_at")},
        ],
        "event_outcomes": {
            "VBB:2026-06-26:BONUS": {
                "official_terms_observation": vbb_observation,
                "knowledge_cutoff": vbb_temporal["knowledge_resolution"],
                "knowledge_cutoff_citation": {"document_id": vbb_record["document_id"], "field": "news-public-time", "value": vbb_document["published_at"]},
                "ledger": ledger,
                "factor_chain": {"status": "NOT_QUALIFIED", "classification": "NOT_EXECUTED",
                                 "reason_codes": ["lifecycle_not_executed", "no_share_change_identity_for_ledger_link"]},
                "pit_price_series": "NOT_EVALUATED_NO_REAL_FACTOR_CHAIN_QUALIFIED",
            },
            "KLB:2025-09-24:STOCK_DIVIDEND": {
                "execution_evidence": {"document_id": klb_record["document_id"], "page": 2,
                    "citation": "HNX listing-change decision states stock-dividend issuance, 216,888,648 additional registered shares, 582,170,526 total registered shares, effective 2025-10-27"},
                "factor_chain": {"status": "NOT_QUALIFIED", "classification": "OTHER_EVIDENCE_GAP",
                                 "reason_codes": ["missing_event_linked_official_ratio_terms", "missing_historical_publication_cutoff"]},
                "pit_price_series": "NOT_EVALUATED_NO_REAL_FACTOR_CHAIN_QUALIFIED",
            },
            "VBB:2025-06-27:STOCK_DIVIDEND": {
                "factor_chain": {"status": "NOT_QUALIFIED", "classification": "OTHER_EVIDENCE_GAP",
                                 "reason_codes": ["no_exact_admitted_official_detail_locator_within_discovery_budget"]},
                "pit_price_series": "NOT_EVALUATED_NO_REAL_FACTOR_CHAIN_QUALIFIED",
            },
        },
        "prospective_regression": {"known_time_bar_count": 18514, "cross_source_qualified_bar_count": 6026,
                                    "status": "UNCHANGED_RETAINED_IDENTITIES_NOT_RECOMPUTED"},
    }


def main() -> None:
    artifact = build_artifact()
    artifact["artifact_sha256"] = hashlib.sha256(_canonical(artifact).encode("utf-8")).hexdigest()
    artifact["artifact_identity"] = "historical_raw_pit_real_factor_chain_qualification:" + artifact["artifact_sha256"]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    print(f"qualified factor chains: {artifact['authority_boundary']['real_factor_chain_qualified_count']}")


if __name__ == "__main__":
    main()
