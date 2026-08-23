"""Current, evidence-bound corporate intelligence from retained source chains only.

This is deliberately a join/materialization boundary, not an event crawler.  It
keeps event facts, lifecycle states, and research descriptors separate so that a
proposal can never become an execution merely through downstream use.
"""
from __future__ import annotations

import copy
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from field_temporal_contract import stable_id

CONTRACT_VERSION = "market_wide_current_corporate_intelligence/v1"
FACT_FIELDS = ("ticker", "fact_id", "fact_type", "value", "source_type", "source_identity", "source_url", "retrieved_at", "effective_or_announced_date", "evidence_identity", "authority_tier", "freshness", "status", "limitations")
EVENT_FIELDS = ("event_id", "ticker", "event_type", "announcement_date", "effective_date", "record_date", "ex_date", "payment_date", "status", "material_evidence", "source_authority", "authority_tier", "freshness", "event_horizon", "unknown_fields", "limitations")


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact)); payload.pop("artifact_sha256", None); payload.pop("artifact_identity", None)
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": "market_wide_current_corporate_intelligence:" + digest}


def _event_id(seed: Mapping[str, Any]) -> str:
    return "corporate_intelligence_event:" + stable_id(seed)


def _fact(event: Mapping[str, Any]) -> dict[str, Any]:
    payload = {key: event.get(key) for key in ("event_id", "event_type", "status", "announcement_date", "effective_date", "record_date", "ex_date", "payment_date")}
    fact = {
        "ticker": event["ticker"], "fact_type": "CORPORATE_ACTION_EVENT_STATUS", "value": payload,
        "source_type": event["source_authority"], "source_identity": event["evidence_identity"],
        "source_url": event["source_urls"], "retrieved_at": event["retrieved_at"],
        "effective_or_announced_date": event["effective_date"] or event["announcement_date"],
        "evidence_identity": event["evidence_identity"], "authority_tier": event["authority_tier"],
        "freshness": event["freshness"], "status": event["status"], "limitations": event["limitations"],
    }
    fact["fact_id"] = "corporate_intelligence_fact:" + stable_id(fact)
    return fact


def _freshness(announcement_date: str | None, session: str) -> str:
    if not announcement_date:
        return "DATE_UNKNOWN"
    try:
        return "CURRENT_90_DAYS" if (date.fromisoformat(session) - date.fromisoformat(announcement_date)).days <= 90 else "HISTORICAL_OVER_90_DAYS"
    except ValueError:
        return "DATE_UNKNOWN"


def _event(*, ticker: str, event_type: str, announcement_date: str | None, effective_date: str | None,
           record_date: str | None, ex_date: str | None, payment_date: str | None, status: str,
           status_basis: str, source_authority: str, authority_tier: str, retrieved_at: str,
           source_urls: list[str], evidence_identity: str, material_evidence: list[str], session: str,
           limitations: list[str]) -> dict[str, Any]:
    event = {
        "ticker": ticker, "event_type": event_type, "announcement_date": announcement_date,
        "effective_date": effective_date, "record_date": record_date, "ex_date": ex_date,
        "payment_date": payment_date, "status": status, "status_basis": status_basis,
        "material_evidence": material_evidence, "source_authority": source_authority,
        "authority_tier": authority_tier, "retrieved_at": retrieved_at, "source_urls": source_urls,
        "evidence_identity": evidence_identity, "freshness": _freshness(announcement_date, session),
        "event_horizon": "CURRENT_RESEARCH_WINDOW" if _freshness(announcement_date, session) == "CURRENT_90_DAYS" else "HISTORICAL_CONTEXT",
        "unknown_fields": [name for name, value in (("effective_date", effective_date), ("record_date", record_date), ("ex_date", ex_date), ("payment_date", payment_date)) if value is None],
        "limitations": limitations,
    }
    event["event_id"] = _event_id(event)
    return event


def load_retained_events(root: Path, session: str) -> list[dict[str, Any]]:
    """Read only the three retained official chains with explicit lifecycle evidence."""
    catalyst_path = root / "operations-review/catalyst-event-research-context-v1-20260820/catalyst_event_research_context_artifact.json"
    catalyst = json.loads(catalyst_path.read_text(encoding="utf-8"))
    hpg_source = next(item for item in catalyst["event_facts"] if item["ticker"] == "HPG")
    hpg = _event(
        ticker="HPG", event_type="CORPORATE_ACTION", announcement_date=hpg_source.get("observed_date"),
        effective_date=hpg_source.get("effective_date"), record_date=None, ex_date=None,
        payment_date=None, status="EXECUTED", status_basis="retained official ledger lifecycle executed",
        source_authority="ISSUER_IR_AND_OFFICIAL_LEDGER", authority_tier="OFFICIAL_QUALIFIED",
        retrieved_at="2026-08-20", source_urls=list(hpg_source.get("source_urls") or []),
        evidence_identity=hpg_source["evidence_identity"], material_evidence=[hpg_source.get("qualification_reason") or "official ledger qualification"],
        session=session, limitations=["Official ex-date is absent; effective/listing/trading dates are not substituted for ex-date.", "Observed execution is not a price-impact claim."],
    )
    vnm_path = root / "operations-review/vnm-2024-cash-dividend-official-evidence/source-manifest.json"
    vnm_source = json.loads(vnm_path.read_text(encoding="utf-8"))
    vnm_urls = [item["canonical_url"] for item in vnm_source["sources"]]
    vnm = _event(
        ticker="VNM", event_type="DIVIDEND", announcement_date="2024-12-05", effective_date=None,
        record_date="2024-12-27", ex_date=None, payment_date="2025-02-28", status="EXECUTED",
        status_basis="issuer annual report states completed; VSDC record-date notice corroborates payment chain",
        source_authority="VSDC_AND_ISSUER_IR", authority_tier="OFFICIAL_QUALIFIED", retrieved_at=vnm_source["observed_at"],
        source_urls=vnm_urls, evidence_identity="retained_source_manifest:" + stable_id(vnm_source),
        material_evidence=["Issuer annual report: 2024-12-05 resolution, VND 500 payment and completed status.", "VSDC notice: record date 2024-12-27 and payment date 2025-02-28."],
        session=session, limitations=["Record date is retained separately from ex-date.", "No qualified ex-date or price-adjustment authority."],
    )
    vcb_path = root / "operations-review/non-cash-corporate-action-official-evidence/source-manifest.json"
    vcb_source = json.loads(vcb_path.read_text(encoding="utf-8"))
    observation = vcb_source["official_observation"]
    vcb = _event(
        ticker="VCB", event_type="BONUS_OR_STOCK_DIVIDEND", announcement_date=observation["announcement_date"],
        effective_date=None, record_date=observation["record_date"], ex_date=None, payment_date=None,
        status="APPROVED", status_basis="official observation explicitly approved_not_completed",
        source_authority="ISSUER_IR", authority_tier="OFFICIAL_QUALIFIED", retrieved_at=vcb_source["observed_at"],
        source_urls=[vcb_source["document"]["canonical_url"]], evidence_identity="retained_source_manifest:" + stable_id(vcb_source),
        material_evidence=[vcb_source["document"]["citation"]], session=session,
        limitations=["Approved/planned issuance is not executed issuance.", "Completion, amendment, and supersession evidence is missing.", "Record date is not an ex-date."],
    )
    return sorted((hpg, vcb, vnm), key=lambda item: (item["ticker"], item["event_id"]))


def _catalyst_surface(events: list[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    current = [event for event in events if event["freshness"] == "CURRENT_90_DAYS"]
    pending = [event for event in events if event["status"] in {"PLANNED", "PROPOSED", "APPROVED", "ANNOUNCED"}]
    historical = [event for event in events if event["freshness"] != "CURRENT_90_DAYS"]
    def descriptor(event: Mapping[str, Any], descriptor_type: str, direction: str, note: str) -> dict[str, Any]:
        return {"event_id": event["event_id"], "descriptor": descriptor_type, "direction": direction, "status": event["status"], "note": note, "evidence_identity": event["evidence_identity"]}
    return {
        "recent_material_events": current,
        "observed_catalysts": [descriptor(event, "OBSERVED_EVENT_CONTEXT", "DIRECTION_UNCLEAR", "Observed fact; no price-impact claim.") for event in current],
        "potential_catalysts": [descriptor(event, "WATCH_FOR_EXECUTION", "DIRECTION_UNCLEAR", "Approved but completion remains unproven.") for event in pending],
        "adverse_event_risks": [],
        "watch_for_execution": [descriptor(event, "WATCH_FOR_EXECUTION", "DIRECTION_UNCLEAR", "Verify later official completion/amendment/cancellation evidence.") for event in pending],
        "watch_for_confirmation": [descriptor(event, "WATCH_FOR_CONFIRMATION", "DIRECTION_UNCLEAR", "No current evidence confirms continuing relevance.") for event in pending],
        "historical_context": historical,
        "data_gaps": ["No retained current corporate intelligence evidence." ] if not events else [],
    }


def build(*, descriptive: Mapping[str, Any], fundamental: Mapping[str, Any], session: str, root: Path) -> dict[str, Any]:
    if descriptive.get("session") != session or not isinstance(descriptive.get("records"), Mapping):
        raise ValueError("CORPORATE_INTELLIGENCE_DESCRIPTIVE_SESSION_OR_RECORDS_INVALID")
    if not isinstance(fundamental.get("records"), Mapping):
        raise ValueError("CORPORATE_INTELLIGENCE_FUNDAMENTAL_RECORDS_INVALID")
    events = load_retained_events(root, session)
    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for event in events: by_ticker.setdefault(event["ticker"], []).append(event)
    records = {}
    for ticker in sorted(descriptive["records"]):
        ticker_events = by_ticker.get(ticker, [])
        facts = [_fact(event) for event in ticker_events]
        surface = _catalyst_surface(ticker_events)
        disposition = "CURRENT_INTELLIGENCE_AVAILABLE" if surface["recent_material_events"] else "HISTORICAL_INTELLIGENCE_ONLY" if ticker_events else "NO_RETAINED_INTELLIGENCE"
        record = {"ticker": ticker, "intelligence_disposition": disposition, "facts": facts, "events": ticker_events,
                  "ownership_context": {"status": "UNAVAILABLE", "reason": "No retained market-wide, current shareholder snapshot was supplied to this materialization."},
                  "governance_context": {"status": "UNAVAILABLE", "reason": "No retained management/board-change event with current governance semantics was supplied."},
                  "corporate_action_context": {"status": "AVAILABLE" if ticker_events else "UNAVAILABLE", "events": [event["event_id"] for event in ticker_events]},
                  "catalyst_research": surface,
                  "data_gaps": ([] if ticker_events else ["NO_RETAINED_INTELLIGENCE_IS_A_DATA_GAP_NOT_ZERO_CORPORATE_ACTIVITY"]),
                  "source_context": {"fundamental_artifact_identity": fundamental.get("artifact_identity"), "event_evidence_only": True}}
        record["corporate_intelligence_record_id"] = "corporate_intelligence_record:" + stable_id(record)
        records[ticker] = record
    event_types, statuses, tiers, freshness = (Counter(event[key] for event in events) for key in ("event_type", "status", "authority_tier", "freshness"))
    coverage = {"universe_count": len(records), "any_intelligence_coverage": sum(bool(row["events"]) for row in records.values()), "current_event_coverage": sum(bool(row["catalyst_research"]["recent_material_events"]) for row in records.values()), "ownership_coverage": 0, "governance_coverage": 0, "corporate_action_coverage": sum(bool(row["corporate_action_context"]["events"]) for row in records.values()), "event_type_counts": dict(sorted(event_types.items())), "event_status_counts": dict(sorted(statuses.items())), "authority_tier_counts": dict(sorted(tiers.items())), "freshness_counts": dict(sorted(freshness.items())), "disposition_counts": dict(sorted(Counter(row["intelligence_disposition"] for row in records.values()).items()))}
    artifact = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "session": session,
                "source_artifact_identities": {"descriptive": descriptive["artifact_identity"], "fundamental": fundamental["artifact_identity"], "prior_catalyst_context": "catalyst_event_research_context:fcbada853866b0136a6c106da17b687dced1a8fe1a5c4021923b7582ed0c50fb"},
                "schema": {"corporate_fact_required_fields": list(FACT_FIELDS), "event_required_fields": list(EVENT_FIELDS), "catalyst_descriptor_types": ["OBSERVED_EVENT_CONTEXT", "WATCH_FOR_EXECUTION", "WATCH_FOR_CONFIRMATION", "HISTORICAL_CONTEXT_ONLY"]},
                "records": records, "events": events, "coverage": coverage,
                "authority_boundary": {"retained_evidence_only": True, "event_fact_separate_from_catalyst_interpretation": True, "planned_or_approved_not_executed": True, "record_date_not_ex_date": True, "no_price_impact_probability_target_or_recommendation": True, "no_raw_as_traded_or_pit_promotion": True},
                "data_limitations": ["No generic issuer-event feed is approved.", "No retained market-wide current ownership or governance-change corpus is available.", "No missing-intelligence state implies absence of corporate activity."], "is_actionable": False}
    artifact.update(content_identity(artifact)); return artifact


def prospective_context(artifact: Mapping[str, Any]) -> dict[str, Any]:
    rows = [{"ticker": ticker, "corporate_intelligence_record_id": record["corporate_intelligence_record_id"], "intelligence_disposition": record["intelligence_disposition"], "event_ids": [event["event_id"] for event in record["events"]], "event_statuses": [event["status"] for event in record["events"]]} for ticker, record in sorted(artifact["records"].items())]
    payload = {"schema_version": "1.0.0", "contract_version": "prospective_research_learning/corporate_intelligence_context/v1", "research_session": artifact["session"], "source_artifact_identities": {"corporate_intelligence": artifact["artifact_identity"]}, "frozen_records": rows, "cohort_count": len(rows), "future_outcomes": "PENDING_FUTURE_OBSERVATION", "authority_boundary": "IDENTITY_FREEZE_ONLY_NOT_OUTCOME_OR_CAUSALITY"}
    payload["snapshot_id"] = "prospective_research_snapshot:" + stable_id(payload)
    return payload
