"""Replay the bounded historical real-factor evidence audit without network I/O."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bitemporal_semantic_contract import project_official_evidence_temporal_metadata
from corporate_action_events import classify_retained_document, extract_event_observation, extract_text
from official_corporate_action_ledger import build_ledger
from real_official_corporate_action_factor_evidence import select_candidates

EVENTS = ROOT / "operations-review/current-official-event-context-integration-v1-20260824/current_official_event_context_artifact.json"
UNIVERSE = ROOT / "operations-review/current-official-market-universe-refresh-v1-20260913/current_official_market_universe_artifact.json"
PROSPECTIVE_MANIFEST = ROOT / "docs/prospective_raw_pit_publication_manifest.json"
EVIDENCE = ROOT / "operations-review/historical-raw-pit-real-factor-chain-qualification-v1-20260930"
RETENTION = EVIDENCE / "official_document_retention"
OUTPUT = EVIDENCE / "historical_raw_pit_real_factor_chain_qualification_20260930.json"
BASELINE_PROSPECTIVE_MANIFEST_REVISION = "b13609913fef14ca1d80e9e92d4a96da466c078e"

# Each document is bound to a source-record identity, never to a ticker alone.
# The runner first freezes candidate identities and then labels every retained
# document as cohort evidence or as ancillary evidence outside that cohort.
DOCUMENT_EVENT_BINDINGS: dict[str, dict[str, Any]] = {
    "d47f20f8d47d5c5229e5c2634506a5e2d0acb391df907206d4be145d3530a450": {
        "source_record_identity": "cc0fd92646b2e985a6c00495a85ce04d723eb2f77b04d082dea580c177e822ac:VBB:BONUS:2026-06-26:2026-06-29::1",
        "evidence_kind": "PARSEABLE_EX_RIGHT_NOTICE",
    },
    "9043002fc71e5231833ccee2350540fb3f4640e8212bc9df194ef3e6bf0d92e5": {
        "source_record_identity": "c24ad693bae5628adc5bcb056fc52115d080f53c7a2ac164b45fae96a0d347d4:KLB:STOCK_DIVIDEND:2025-09-24:2025-09-25::1",
        "evidence_kind": "VISUALLY_REVIEWED_LISTING_CHANGE_NOTICE",
        "executed_listing_change": {
            "page": 2,
            "citation": "HNX listing-change decision states stock-dividend issuance, 216,888,648 additional registered shares, 582,170,526 total registered shares, effective 2025-10-27",
        },
    },
}


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _page_publication_cutoff(payload: bytes) -> str:
    match = re.search(r"news-public-time[^>]*>\s*(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2})", payload.decode("utf-8", errors="strict"), re.I)
    if not match:
        raise ValueError("official_page_publication_datetime_missing")
    day, month, year, hour, minute = match.groups()
    return f"{year}-{month}-{day}T{hour}:{minute}:00+07:00"


def _prospective_identity(payload: bytes) -> dict[str, Any]:
    manifest = json.loads(payload)
    prospective = manifest["prospective_bars"]
    if (prospective["post_close_same_session"], prospective["raw_as_traded_qualified_cross_source"]) != (18514, 6026):
        raise ValueError("unexpected_retained_prospective_bar_counts")
    return {
        "manifest_sha256": hashlib.sha256(payload).hexdigest(),
        "artifact_identity": manifest["artifact_identity"],
        "authority_matrix_sha256": hashlib.sha256(_canonical(manifest["authority_matrix"]).encode()).hexdigest(),
        "snapshot_store_sha256": hashlib.sha256(_canonical(manifest["snapshot_store"]).encode()).hexdigest(),
        "known_time_bar_count": prospective["post_close_same_session"],
        "cross_source_qualified_bar_count": prospective["raw_as_traded_qualified_cross_source"],
        "dnse_identity_chain_sha256": manifest["snapshot_store"]["dnse"]["identity_chain_sha256"],
        "hose_identity_chain_sha256": manifest["snapshot_store"]["hose"]["identity_chain_sha256"],
    }


def _prospective_regression() -> dict[str, Any]:
    relative = PROSPECTIVE_MANIFEST.relative_to(ROOT).as_posix()
    baseline = subprocess.run(
        ["git", "show", f"{BASELINE_PROSPECTIVE_MANIFEST_REVISION}:{relative}"], cwd=ROOT,
        check=True, capture_output=True,
    ).stdout
    after = PROSPECTIVE_MANIFEST.read_bytes()
    before_identity, after_identity = _prospective_identity(baseline), _prospective_identity(after)
    comparison_fields = tuple(before_identity)
    changed = [field for field in comparison_fields if before_identity[field] != after_identity[field]]
    if changed:
        raise ValueError("retained_prospective_regression_identity_changed:" + ",".join(changed))
    return {
        "comparison_basis": "exact_git_content_before_correction_vs_current_retained_publication_manifest",
        "baseline_revision": BASELINE_PROSPECTIVE_MANIFEST_REVISION,
        "before": before_identity,
        "after": after_identity,
        "identity_fields_compared": list(comparison_fields),
        "changed_identity_fields": changed,
        "status": "UNCHANGED_RETAINED_IDENTITIES_CONFIRMED_NO_RECEIPT_RECOMPUTATION",
    }


def _candidate_key(candidate: Mapping[str, Any]) -> str:
    return f"{candidate['ticker']}:{candidate['ex_date']}:{candidate['event_type']}"


def _document_summary(record: Mapping[str, Any], binding: Mapping[str, Any] | None, selected: Mapping[str, Any] | None) -> dict[str, Any]:
    result = {key: record.get(key) for key in ("document_id", "ticker", "canonical_url", "document_class", "sha256", "content_length", "observed_at")}
    result["declared_source_record_identity"] = binding.get("source_record_identity") if binding else None
    result["cohort_membership"] = "FROZEN_COHORT_DOCUMENT" if selected else "ANCILLARY_OFFICIAL_EVIDENCE_NOT_IN_FROZEN_COHORT"
    return result


def _outcome_without_document(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "frozen_candidate_identity": candidate["frozen_candidate_identity"],
        "factor_chain": {"status": "NOT_QUALIFIED", "classification": "OTHER_EVIDENCE_GAP",
                         "reason_codes": ["NO_EXACT_RETAINED_DOCUMENT_BINDING"]},
        "pit_price_series": "NOT_EVALUATED_NO_REAL_FACTOR_CHAIN_QUALIFIED",
    }


def _bound_document_outcome(candidate: Mapping[str, Any], record: Mapping[str, Any], binding: Mapping[str, Any]) -> dict[str, Any]:
    outcome = _outcome_without_document(candidate)
    payload = (RETENTION / str(record["relative_path"])).read_bytes()
    if binding["evidence_kind"] == "PARSEABLE_EX_RIGHT_NOTICE":
        document = classify_retained_document(record, payload)
        document["published_at"] = _page_publication_cutoff(payload)
        observation = extract_event_observation(document, extract_text(payload, record["content_type"]))
        temporal = project_official_evidence_temporal_metadata({
            "document_id": record["document_id"], "sha256": record["sha256"], "source_authority": "exchange",
            "published_at": document["published_at"], "observed_at": record["observed_at"], "qualification_state": "QUALIFIED",
        })
        outcome.update({
            "official_terms_observation": observation,
            "knowledge_cutoff": temporal["knowledge_resolution"],
            "knowledge_cutoff_citation": {"document_id": record["document_id"], "field": "news-public-time", "value": document["published_at"]},
            "ledger": build_ledger([observation]),
            "factor_chain": {"status": "NOT_QUALIFIED", "classification": "NOT_EXECUTED",
                             "reason_codes": ["lifecycle_not_executed", "no_share_change_identity_for_ledger_link"]},
        })
    elif binding["evidence_kind"] == "VISUALLY_REVIEWED_LISTING_CHANGE_NOTICE":
        outcome.update({
            "execution_evidence": {"document_id": record["document_id"], **binding["executed_listing_change"]},
            "factor_chain": {"status": "NOT_QUALIFIED", "classification": "OTHER_EVIDENCE_GAP",
                             "reason_codes": ["missing_event_linked_official_ratio_terms", "missing_historical_publication_cutoff"]},
        })
    else:
        raise ValueError("unrecognized_document_evidence_kind")
    return outcome


def build_artifact() -> dict[str, Any]:
    events = json.loads(EVENTS.read_text(encoding="utf-8"))
    universe = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    manifest = json.loads((RETENTION / "official_document_acquisition_manifest.json").read_text(encoding="utf-8"))
    selection = select_candidates(
        events["all_current_universe_event_records"], reference_tickers=universe["records"].keys(),
        cutoff_date="2026-09-29", listing_by_ticker=universe["records"],
    )
    selected_by_identity = {row["source_record_identity"]: row for row in selection["candidates"]}
    documents: list[dict[str, Any]] = []
    bound_documents: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    for record in manifest["records"]:
        binding = DOCUMENT_EVENT_BINDINGS.get(str(record.get("document_id")))
        selected = selected_by_identity.get(binding["source_record_identity"]) if binding else None
        documents.append(_document_summary(record, binding, selected))
        if selected and binding:
            identity = selected["source_record_identity"]
            if identity in bound_documents:
                raise ValueError("multiple_documents_bound_to_frozen_candidate")
            bound_documents[identity] = (record, binding)
    outcomes = {}
    for candidate in selection["candidates"]:
        record_binding = bound_documents.get(candidate["source_record_identity"])
        outcomes[_candidate_key(candidate)] = (_bound_document_outcome(candidate, *record_binding)
                                               if record_binding else _outcome_without_document(candidate))
    return {
        "contract_version": "historical_raw_pit_real_factor_chain_qualification/v2",
        "milestone": "HISTORICAL_RAW_PIT_REAL_FACTOR_CHAIN_QUALIFICATION_V1",
        "terminal_disposition": "PARTIAL_OFFICIAL_EVIDENCE_ACQUIRED_NO_QUALIFIED_FACTOR_CHAIN",
        "authority_boundary": {
            "real_factor_chain_qualified_count": 0, "market_wide_raw_as_traded_promoted": False,
            "pit_backtest_eligible": False, "execution_replay_eligible": False, "active_universe": "UNKNOWN",
            "observed_market_ratio_used_as_factor": False,
        },
        "request_ledger": {"discovery_queries": 8, "official_http_document_requests": 2, "official_http_retries": 0,
                           "new_bytes_retained": sum(int(row["content_length"]) for row in manifest["records"])},
        "candidate_selection": selection,
        "official_documents": documents,
        "event_outcomes": outcomes,
        "prospective_regression": _prospective_regression(),
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
