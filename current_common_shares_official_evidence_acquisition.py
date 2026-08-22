"""Read-only qualification of the bounded official current-common-share acquisition batch."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from field_temporal_contract import stable_id

CONTRACT_VERSION = "current_common_shares_official_evidence_acquisition/v1"
QUALIFIED = "CURRENT_COMMON_OUTSTANDING_QUALIFIED"
RETAINED_UNRESOLVED = "EVIDENCE_RETAINED_BUT_CURRENTNESS_UNRESOLVED"
ACTION_UNRESOLVED = "CORPORATE_ACTION_EXECUTION_UNRESOLVED"
CONFLICTING = "CONFLICTING_OFFICIAL_EVIDENCE"
NEEDS_ROUTE = "NEEDS_OWNER_SOURCE_ROUTE_APPROVAL"
NOT_FOUND = "OFFICIAL_EVIDENCE_NOT_FOUND"


def _records(manifests: Sequence[Mapping[str, Any]], ticker: str) -> list[dict[str, Any]]:
    rows = [dict(row) for manifest in manifests for row in manifest.get("records", []) if row.get("ticker") == ticker]
    return sorted(rows, key=lambda row: (str(row.get("published_at") or ""), str(row.get("sha256") or "")))


def build_acquisition_result(*, p3f3: Mapping[str, Any], p3f4: Mapping[str, Any], p3f5: Mapping[str, Any],
                             p3f6: Mapping[str, Any], manifests: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Reconcile retained sources without inferring a share transition or route."""
    cohort = sorted(row["canonical_instrument"]["canonical_ticker"] for row in p3f3["current_price_authority_matrix"])
    target = p3f6["provider_proxy_coverage"]["valuation_date"]
    comparisons = list(p3f5["official_comparison_matrix"])
    common = {row["ticker"]: row["official"] for row in comparisons
              if isinstance(row.get("official"), Mapping)
              and row["official"].get("identity") == "common_shares_outstanding"}
    action_blocked = {row["ticker"]: list(row.get("blockers") or []) for row in p3f6["corporate_action_blocks"]}
    transition = p3f4["representative_proofs"]["executed_transition"]["bridge_result"]
    coverage = transition["coverage_through"]
    rows = []
    for ticker in cohort:
        evidence = _records(manifests, ticker)
        result = ACTION_UNRESOLVED if ticker in action_blocked else (RETAINED_UNRESOLVED if evidence else NOT_FOUND)
        official = common.get(ticker)
        denominator = None
        effective = None
        continuity = None
        notes = []
        if official:
            denominator, effective, continuity = official["value"], official["effective_on"], coverage
            notes.append("Executed common-share count retained; continuity does not reach valuation date.")
        if ticker in action_blocked:
            notes.append("Retained corporate-action timing/result is unresolved; no execution or resulting shares inferred.")
        if not evidence:
            notes.append("No retained official document is available for this bounded cohort item.")
        rows.append({"ticker": ticker, "result": result, "official_documents": [{
            "document_id": row.get("document_id"), "source_id": row.get("source_id"), "source_url": row.get("canonical_url"),
            "sha256": row.get("sha256"), "published_at": row.get("published_at"), "document_class": row.get("document_class"),
            "extraction_status": row.get("extraction_status"),
        } for row in evidence], "current_common_shares": denominator, "effective_date": effective,
            "continuity_through": continuity, "covered_through_valuation_date": False,
            "blockers": action_blocked.get(ticker, ["CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN"]),
            "route_requirement": "NO_OWNER_ROUTE_APPROVAL_REQUIRED; FINITE_POST_PERIOD_LOCATOR_NOT_RETAINED",
            "notes": notes})
    artifact = {"contract_version": CONTRACT_VERSION, "valuation_date": target, "cohort": cohort,
                "source_artifact_identities": {"p3f3": p3f3.get("artifact_identity"), "p3f4": p3f4.get("artifact_identity"),
                                                 "p3f5": p3f5.get("artifact_identity"), "p3f6": p3f6.get("artifact_identity")},
                "acquisition_scope": {"new_live_document": "HPG official issuer-IR listing-change notice",
                                      "previous_1024_byte_capture": "PRESERVED_NON_CITABLE_STREAM_TRUNCATION",
                                      "network_requests": 2, "retries": 0, "runtime_or_database_writes": False},
                "acquired_source_citations": [{"ticker": "HPG", "source_url": "https://www.hoaphat.com.vn/tin-tuc/thong-bao-ve-ngay-giao-dich-co-phieu-phat-hanh-tra-co-tuc-nam-2025-1.html",
                    "document_sha256": "e7ceec0fb6b6edb9aa12fd88c45d151dbd5f0ad22d46fbe0fdf81f6bb88bc78c",
                    "retrieved_at": "2026-08-22T11:09:12.607459Z", "issuer_identity": "HPG",
                    "evidence_span": "Số lượng chứng khoán sau khi thay đổi niêm yết: 8.442.964.520 cổ phiếu; Ngày thay đổi niêm yết có hiệu lực: 02/07/2026.",
                    "status": "EXECUTED_LISTING_CHANGE", "record_date": None, "ex_date": None,
                    "effective_date": "2026-07-02", "currentness_verdict": "COVERAGE_THROUGH_2026_08_19_NOT_PROVEN"}],
                "symbol_results": rows,
                "summary": {"cohort_denominator": len(cohort), "qualified_for_valuation_date": 0,
                            "result_counts": dict(sorted(Counter(row["result"] for row in rows).items()))},
                "denominator_eligibility": [{"ticker": row["ticker"], "eligible": False,
                                               "reason": row["blockers"][0]} for row in rows],
                "boundaries": {"valuation_implemented": False, "provider_proxy_promoted": False,
                               "historical_pit_promoted": False, "raw_as_traded_promoted": False,
                               "authority_remains_fail_closed": True},
                "verdict": "NO_QUALIFYING_CURRENT_SHARE_EVIDENCE"}
    artifact["artifact_sha256"] = stable_id(artifact)
    artifact["artifact_identity"] = f"current_common_shares_official_evidence_acquisition:{artifact['artifact_sha256']}"
    return artifact
