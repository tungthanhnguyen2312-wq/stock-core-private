"""`official_issuer_disclosure/v1`: one deterministic projection over retained official evidence.

WHAT THIS IS
    A read-only join over documents already retained by `official_document_store` (or, for the
    HNX insider/major-holder pilot, the sibling acquisition manifest this milestone adds in
    `tools/run_official_issuer_disclosure_acquisition.py`). It computes no new evidence: every
    field is either copied from a retained manifest record or from the deterministic parse of
    that same record's own bytes (`hnx_disclosure_feed_parser`, `insider_and_major_holder_events`,
    `audit_opinion_evidence`). Raw retained bytes remain authority; this module is the
    deterministic projection the milestone calls for, never a second source of truth.

SOURCE_ID -> EXCHANGE
    Recorded once here because no retained manifest record carries it: which authority each
    registry `source_id` speaks for. `vsdc` is a depository, not an exchange, and is labelled
    as such rather than assigned to HOSE or HNX by guess.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

VERSION = "1.0.0"

_EXCHANGE_BY_SOURCE = {
    "hose": "HOSE", "hnx": "HNX", "vsdc": "VSDC", "issuer_ir": "ISSUER_IR",
}

#: document_type -> coarse disclosure_type. Anything not listed keeps its raw document_type
#: verbatim as disclosure_type, rather than being forced into a bucket that does not fit.
_DISCLOSURE_TYPE_BY_DOCUMENT_TYPE = {
    "insider_transaction_notice": "INSIDER_TRANSACTION",
    "major_shareholder_notice": "MAJOR_SHAREHOLDER",
    "corporate_action_notice": "CORPORATE_ACTION",
    "ex_right_notice": "CORPORATE_ACTION",
    "last_registration_date_notice": "CORPORATE_ACTION",
    "listing_change_notice": "LISTING_CHANGE",
    "agm_document_or_resolution": "GOVERNANCE",
    "corporate_governance_report": "GOVERNANCE",
    "amendment_or_supersession_notice": "AMENDMENT_OR_CANCELLATION",
    "annual_report": "FINANCIAL_REPORT",
    "audited_annual_financial_statements": "FINANCIAL_REPORT",
    "reviewed_interim_financial_statements": "FINANCIAL_REPORT",
}

QUALIFICATION_STRUCTURED = "STRUCTURED_FACTS_AVAILABLE"
QUALIFICATION_PARTIAL = "STRUCTURED_FACTS_PARTIAL"
QUALIFICATION_METADATA_ONLY = "METADATA_ONLY"


def project_disclosure_record(*, manifest_record: Mapping[str, Any], source_id: str,
                              detail: Mapping[str, Any] | None = None,
                              observation_state: str | None = None,
                              observation_warnings: Iterable[str] | None = None) -> dict[str, Any]:
    """One `official_issuer_disclosure/v1` row from one retained document's manifest record.

    `detail` is the optional `hnx_disclosure_feed_parser.parse_disclosure_detail` result for
    documents this milestone structurally extracts; its absence is not an error -- a corporate
    action notice retained under the pre-existing pillar has no such parse and stays
    `METADATA_ONLY`, which is exactly true of it.
    """
    document_type = str(manifest_record.get("document_type") or manifest_record.get("document_class") or "")
    warnings = list(observation_warnings or [])
    if detail is not None:
        if not detail.get("ticker"):
            warnings = warnings or ["ticker_not_recognised_in_this_document"]
        qualification = (QUALIFICATION_STRUCTURED if detail.get("extraction_complete")
                         else QUALIFICATION_PARTIAL if detail.get("fields") else QUALIFICATION_METADATA_ONLY)
    else:
        qualification = QUALIFICATION_METADATA_ONLY

    ticker = (detail.get("ticker") if detail is not None else None) or manifest_record.get("ticker")
    return {
        "schema_version": VERSION,
        "record_type": "official_issuer_disclosure/v1",
        "filing_id": manifest_record.get("document_id"),
        "ticker": str(ticker).upper() if ticker else None,
        "issuer_name": None,  # not explicitly stated as a distinct field on any retained notice
        "exchange": _EXCHANGE_BY_SOURCE.get(str(source_id), str(source_id).upper()),
        "disclosure_type": _DISCLOSURE_TYPE_BY_DOCUMENT_TYPE.get(document_type, document_type or "UNKNOWN"),
        "document_type": document_type,
        "title": (detail.get("title") if detail is not None else None) or manifest_record.get("title"),
        "published_at": manifest_record.get("published_at")
                        or (detail.get("published_at_raw") if detail is not None else None),
        "event_date": None,  # per-fact-family event dates live in the typed observation, not here
        "source": manifest_record.get("source_authority"),
        "official_url": manifest_record.get("source_url") or manifest_record.get("canonical_url"),
        "document_url": manifest_record.get("final_url") or manifest_record.get("source_url")
                        or manifest_record.get("canonical_url"),
        "content_identity": manifest_record.get("relative_path"),
        "retrieved_at": manifest_record.get("observed_at"),
        "sha256": manifest_record.get("content_sha256") or manifest_record.get("sha256"),
        "language": "vi",
        "amendment_status": "AMENDMENT" if manifest_record.get("supersedes_document_id") else "ORIGINAL",
        "supersedes": manifest_record.get("supersedes_document_id"),
        "parse_status": manifest_record.get("parser_status") or manifest_record.get("extraction_status"),
        "qualification": qualification,
        "observation_state": observation_state,
        "warnings": sorted(set(warnings)),
    }


#: A registration notice and its own later result notice are *expected* to report different
#: states for the same transaction (that is the announcement -> registration -> execution
#: lifecycle this milestone is required to keep as separate facts, not a contradiction). Only
#: documents within the *same* stage are compared for conflict: two registrations, or two
#: results, that disagree about the same actor on the same day.
_REGISTRATION_STATES = {"REGISTERED_BUY", "REGISTERED_SELL"}
_RESULT_STATES = {"EXECUTED_BUY", "EXECUTED_SELL", "PARTIALLY_EXECUTED", "NOT_EXECUTED"}


def _stage(state: str) -> str | None:
    if state in _REGISTRATION_STATES:
        return "registration"
    if state in _RESULT_STATES:
        return "result"
    return None


def detect_conflicts(records: Iterable[Mapping[str, Any]],
                     observations: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Same ticker + same actor + same calendar day + same lifecycle stage + contradictory
    states, with no supersession link between them. A registration document and a result
    document about the very same trade normally carry different states by design (see
    `insider_and_major_holder_events`) and must never be compared against each other here --
    only two documents that both claim to be a *registration*, or both claim to be a *result*,
    for the same actor on the same day can genuinely disagree. Returns an empty list, correctly,
    when nothing in the batch conflicts; nothing here manufactures a conflict to prove itself."""
    by_group: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        obs = observations.get(str(record.get("filing_id")))
        if not obs or record.get("amendment_status") == "AMENDMENT":
            continue
        stage = _stage(str(obs.get("state")))
        if stage is None:
            continue
        published = str(record.get("published_at") or "")[:10]
        key = (str(record.get("ticker")), str(obs.get("actor_name") or obs.get("holder_name") or ""),
              published, stage)
        by_group.setdefault(key, []).append(record)
    conflicts = []
    for (ticker, actor, day, stage), group in by_group.items():
        states = {str(observations[str(r.get("filing_id"))].get("state")) for r in group}
        if len(group) > 1 and len(states) > 1:
            conflicts.append({"ticker": ticker, "actor": actor, "day": day, "stage": stage,
                              "filing_ids": sorted(str(r.get("filing_id")) for r in group),
                              "states": sorted(states), "resolution": "CONFLICTING_EVIDENCE"})
    return conflicts


def coverage_report(*, universe_count: int, source_visible_issuers: int,
                    disclosure_records: Iterable[Mapping[str, Any]],
                    insider_observations: Iterable[Mapping[str, Any]],
                    major_holder_observations: Iterable[Mapping[str, Any]],
                    audit_evaluations: Iterable[Mapping[str, Any]],
                    unavailable: int, source_rejected: int,
                    parse_blocked: int, semantic_blocked: int) -> dict[str, Any]:
    records = list(disclosure_records)
    tickers = sorted({r["ticker"] for r in records if r.get("ticker")})
    amended = sum(1 for r in records if r.get("amendment_status") == "AMENDMENT")
    audits = list(audit_evaluations)
    return {
        "schema_version": VERSION,
        "UNIVERSE_COUNT": universe_count,
        "SOURCE_VISIBLE_ISSUERS": source_visible_issuers,
        "DISCLOSURES_DISCOVERED": len(records) + unavailable + source_rejected + parse_blocked + semantic_blocked,
        "DISCLOSURES_RETAINED": len(records),
        "DISCLOSURE_TICKERS": len(tickers),
        "disclosure_tickers": tickers,
        "INSIDER_REGISTRATION_EVENTS": sum(1 for o in insider_observations
                                          if str(o.get("state", "")).startswith("REGISTERED_")),
        "INSIDER_EXECUTION_EVENTS": sum(1 for o in insider_observations
                                        if str(o.get("state", "")) in
                                        {"EXECUTED_BUY", "EXECUTED_SELL", "PARTIALLY_EXECUTED", "NOT_EXECUTED"}),
        "MAJOR_HOLDER_EVENTS": sum(1 for o in major_holder_observations
                                   if str(o.get("state", "")) != "UNKNOWN_MAJOR_HOLDER_EVENT"),
        "AUDIT_DOCUMENTS": len(audits),
        "AUDIT_OPINION_QUALIFIED": sum(1 for a in audits if a.get("qualification") == "EXTRACTED"),
        "AMENDED_DISCLOSURES": amended,
        "CANCELLED_DISCLOSURES": sum(1 for r in records if r.get("disclosure_type") == "AMENDMENT_OR_CANCELLATION"),
        "UNAVAILABLE": unavailable,
        "PROVIDER_OR_SOURCE_REJECTED": source_rejected,
        "PARSE_BLOCKED": parse_blocked,
        "SEMANTIC_BLOCKED": semantic_blocked,
    }
