"""Read-only current official corporate-event context from retained exchange data."""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any, Mapping

CONTRACT_VERSION = "current_official_event_context/v1"
CURRENT_STATES = {"UPCOMING", "EX_DATE_TODAY", "RECENT"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact)); payload.pop("artifact_sha256", None); payload.pop("artifact_identity", None)
    digest = hashlib.sha256(_canonical(payload)).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"current_official_event_context:{digest}"}


def _verify(artifact: Mapping[str, Any], label: str) -> None:
    payload = copy.deepcopy(dict(artifact)); digest = payload.pop("artifact_sha256", None); identity = payload.pop("artifact_identity", None)
    expected = hashlib.sha256(_canonical(payload)).hexdigest()
    if digest != expected or not isinstance(identity, str) or not identity.endswith(expected): raise ValueError(f"{label}_IDENTITY_MISMATCH")


def _captures(artifact: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(item.get("sha256")): item for item in artifact.get("captures", []) if item.get("sha256")}


def _iso_timestamp(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).date().isoformat()
    return value if isinstance(value, str) and value else None


def _state(ex_date: str | None, session: date) -> tuple[str, int | None]:
    if not ex_date: return "DATE_INCOMPLETE", None
    try: delta = (date.fromisoformat(ex_date) - session).days
    except ValueError: return "UNKNOWN", None
    return ("UPCOMING" if delta > 0 else "EX_DATE_TODAY" if delta == 0 else "RECENT" if delta >= -30 else "PAST"), delta


def _type(raw: str | None) -> tuple[str, str]:
    mapping = {"CASH_DIVIDEND": ("CASH_DIVIDEND", "PRICE_SHARE_AFFECTING"), "STOCK_DIVIDEND": ("STOCK_DIVIDEND", "PRICE_SHARE_AFFECTING"),
               "BONUS_ISSUE": ("BONUS", "PRICE_SHARE_AFFECTING"), "RIGHTS_ISSUE": ("RIGHTS", "PRICE_SHARE_AFFECTING"),
               "AGM": ("AGM", "INFORMATIONAL_GOVERNANCE"), "OTHER": ("OTHER", "UNKNOWN_APPLICABILITY")}
    return mapping.get(str(raw), ("UNKNOWN", "UNKNOWN_APPLICABILITY"))


def _event(*, ticker: str, raw_type: str | None, ex_date: str | None, record_date: str | None, execution_date: str | None,
           source: str, source_identity: str, source_url: str | None, observed_at: str | None, qualification: str, warnings: list[str], session: date) -> dict[str, Any]:
    event_type, materiality = _type(raw_type); state, delta = _state(ex_date, session)
    item = {"ticker": ticker, "event_type": event_type, "published_at": None, "ex_date": ex_date, "record_date": record_date,
            "execution_date": execution_date, "event_state": state, "days_to_ex_date": delta if delta is not None and delta >= 0 else None,
            "days_since_ex_date": -delta if delta is not None and delta < 0 else None, "source": source, "source_identity": source_identity,
            "source_url": source_url, "official_observed_at": observed_at, "qualification": qualification,
            "materiality_status": materiality, "publication_availability": "UNKNOWN_NOT_RETAINED", "pit_suitability": "LIMITED_PUBLICATION_TIME_UNKNOWN",
            "warnings": warnings + ["Source execution/payment dates are calendar observations, not proof of executed lifecycle.", "No event impact, probability, score, target, or recommendation is derived."]}
    item["event_id"] = "current_official_event:" + hashlib.sha256(_canonical(item)).hexdigest()
    return item


def build_artifact(*, official_universe: Mapping[str, Any], hnx: Mapping[str, Any], hose: Mapping[str, Any], research_session: str) -> dict[str, Any]:
    for label, artifact in (("OFFICIAL_UNIVERSE", official_universe), ("HNX", hnx), ("HOSE", hose)): _verify(artifact, label)
    session = date.fromisoformat(research_session)
    current = {ticker for ticker, row in official_universe.get("records", {}).items() if row.get("stocklookup_candidate") and row.get("current_universe_status") in {"OFFICIAL_CURRENT_EXCHANGE_SECURITY", "OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE"}}
    if len(current) != official_universe.get("reconciliation", {}).get("official_total_match"): raise ValueError("OFFICIAL_CURRENT_DENOMINATOR_MISMATCH")
    hnx_capture, hose_capture = _captures(hnx), _captures(hose)
    rights_scope = hnx.get("rights_scope") or {}
    window_warning = (["HNX retained rights index is scoped to inclusive ex-dates " + " through ".join(rights_scope["requested_ex_date_window"]) + "; outside-window evidence remains unresolved."] if rights_scope.get("requested_ex_date_window") else [])
    all_events: list[dict[str, Any]] = []
    for row in hnx.get("datasets", {}).get("hnx_official_rights_event_index/v1", []):
        identity = str(row.get("source_identity")); capture = hnx_capture.get(identity, {})
        all_events.append(_event(ticker=str(row.get("ticker")).upper(), raw_type=row.get("event_type"), ex_date=row.get("ex_date"), record_date=row.get("record_date"), execution_date=row.get("execution_date"), source="hnx_official_rights_event_index/v1", source_identity=identity, source_url=row.get("source_url"), observed_at=capture.get("retrieved_at"), qualification=str(row.get("qualification") or "UNKNOWN"), warnings=window_warning + (["AGM is informational/governance context and never a price-adjustment instruction."] if row.get("event_type") == "AGM" else []), session=session))
    for row in hose.get("datasets", {}).get("hose_public_event_hpg/v1", []):
        identity = str(row.get("source_identity")); capture = hose_capture.get(identity, {})
        all_events.append(_event(ticker=str(row.get("ticker")).upper(), raw_type="CASH_DIVIDEND" if row.get("event_type_raw") else None, ex_date=_iso_timestamp(row.get("ex_date")), record_date=_iso_timestamp(row.get("record_date")), execution_date=None, source="hose_public_event_hpg/v1", source_identity=identity, source_url=None, observed_at=capture.get("retrieved_at"), qualification=str(row.get("qualification") or "UNKNOWN"), warnings=["HOSE public event-index detail remains scoped; no economics or price mutation is inferred."], session=session))
    all_events.sort(key=lambda item: (item["ticker"], item["ex_date"] or "", item["event_id"]))
    # The upstream rights index has no stable row id. Retain deterministic
    # per-source ordering so duplicate-looking official rows remain distinct.
    occurrences: Counter[str] = Counter()
    for item in all_events:
        base = f"{item['source_identity']}:{item['ticker']}:{item['event_type']}:{item['ex_date'] or ''}:{item['record_date'] or ''}:{item['execution_date'] or ''}"
        occurrences[base] += 1
        item["source_record_identity"] = f"{base}:{occurrences[base]}"
        event_seed = dict(item); event_seed.pop("event_id", None)
        item["event_id"] = "current_official_event:" + hashlib.sha256(_canonical(event_seed)).hexdigest()
    scoped = [item for item in all_events if item["ticker"] in current]
    excluded = [item for item in all_events if item["ticker"] not in current]
    by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in scoped: by_ticker[item["ticker"]].append(item)
    ci_events = [item for item in scoped if item["event_state"] in CURRENT_STATES and item["qualification"] == "EX_DATE_OFFICIAL_QUALIFIED"]
    counts, types = Counter(item["event_state"] for item in scoped), Counter(item["event_type"] for item in scoped)
    artifact = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "research_session": research_session,
                "source_coverage_scopes": {"hnx_rights": rights_scope, "hose_events": "HPG_PUBLIC_EVENT_INDEX_ONLY"},
                "source_artifact_identities": {"official_universe": official_universe["artifact_identity"], "hnx": hnx["artifact_identity"], "hose": hose["artifact_identity"]},
                "current_official_universe": {"count": len(current), "scope": "STOCKLOOKUP_CANDIDATES_WITH_RETAINED_CURRENT_OFFICIAL_EXCHANGE_PRESENCE"},
                "records": {ticker: {"ticker": ticker, "qualified_official_events_available": bool(events), "events": events,
                                      "event_types": sorted({event["event_type"] for event in events}), "current_or_recent_event_count": sum(event["event_state"] in CURRENT_STATES for event in events),
                                      "data_gaps": ["NO_CURRENT_OFFICIAL_EVENT_CONTEXT_RETAINED"] if not events else []} for ticker, events in sorted(by_ticker.items())},
                "all_current_universe_event_records": scoped, "excluded_noncurrent_or_official_only_event_records": excluded,
                "corporate_intelligence_adapter": {"events": ci_events, "status": "READY_CURRENT_CONTEXT_PIT_LIMITED", "limitations": ["Only upcoming/today/recent events with explicit qualified ex-date enter CI current-context adapter.", "Publication date/time is unavailable; adapter is not suitable for historical known-at replay."]},
                "coverage": {"event_context_tickers": len(by_ticker), "event_context_records": len(scoped), "upcoming_events": counts["UPCOMING"], "ex_date_today_events": counts["EX_DATE_TODAY"], "recent_events": counts["RECENT"], "past_events": counts["PAST"], "date_incomplete_events": counts["DATE_INCOMPLETE"], "unknown_events": counts["UNKNOWN"], "cash_dividend_context": types["CASH_DIVIDEND"], "stock_dividend_context": types["STOCK_DIVIDEND"], "bonus_context": types["BONUS"], "rights_context": types["RIGHTS"], "agm_context": types["AGM"], "other_context": types["OTHER"]},
                "authority_boundary": "CURRENT_FACTUAL_EVENT_CONTEXT_ONLY; NO_EVENT_SCORE_OR_IMPACT; NO_PRICE_ADJUSTMENT_RAW_AS_TRADED_PIT_OR_BACKTEST_PROMOTION", "missing_is_zero": False}
    artifact.update(_identity(artifact)); return artifact


def replay(artifact: Mapping[str, Any]) -> None:
    _verify(artifact, "CURRENT_OFFICIAL_EVENT_CONTEXT")
    events = artifact.get("all_current_universe_event_records", [])
    if len({item["event_id"] for item in events}) != len(events): raise ValueError("EVENT_ID_DUPLICATE")
    if any(item["ex_date"] is None and item["event_state"] not in {"DATE_INCOMPLETE", "UNKNOWN"} for item in events): raise ValueError("MISSING_EX_DATE_INFERRED")


def project_session_context(artifact: Mapping[str, Any], *, session: str, cutoff: str) -> dict[str, Any]:
    """Reclassify retained qualified dates for one session, preserving source evidence.

    The parent remains immutable. No acquisition, publication-time inference, new
    universe membership, lifecycle qualification or ex-date inference occurs here.
    """
    from corporate_currency_rollforward import context_known_by
    _verify(artifact, "RETAINED_OFFICIAL_EVENT_CONTEXT")
    if artifact.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("OFFICIAL_EVENT_CONTEXT_CONTRACT_INVALID")
    boundary = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    if boundary.tzinfo is None or boundary.date().isoformat() != session:
        raise ValueError("EVENT_SESSION_CUTOFF_INVALID")
    if not context_known_by(dict(artifact), boundary):
        raise ValueError("EVENT_CONTEXT_NOT_KNOWN_BY_SESSION_CUTOFF")
    if artifact.get("research_session") == session:
        return dict(artifact)
    if str(artifact.get("research_session") or "") > session:
        raise ValueError("EVENT_CONTEXT_SOURCE_SESSION_AFTER_TARGET")
    value = copy.deepcopy(dict(artifact))
    value["research_session"] = session
    value["projection_source_artifact_identity"] = artifact["artifact_identity"]
    value["session_cutoff"] = cutoff
    as_of = date.fromisoformat(session)
    for group in ("all_current_universe_event_records", "excluded_noncurrent_or_official_only_event_records"):
        for item in value.get(group, []):
            state, delta = _state(item.get("ex_date"), as_of)
            item.update(event_state=state, days_to_ex_date=delta if delta is not None and delta >= 0 else None,
                        days_since_ex_date=-delta if delta is not None and delta < 0 else None)
            item["source_event_id"] = item["event_id"]
            seed = {k: v for k, v in item.items() if k != "event_id"}
            item["event_id"] = "current_official_event:" + hashlib.sha256(_canonical(seed)).hexdigest()
    by_ticker = defaultdict(list)
    for item in value["all_current_universe_event_records"]:
        by_ticker[item["ticker"]].append(item)
    value["records"] = {ticker: {"ticker": ticker, "qualified_official_events_available": bool(events), "events": events,
        "event_types": sorted({e["event_type"] for e in events}), "current_or_recent_event_count": sum(e["event_state"] in CURRENT_STATES for e in events),
        "data_gaps": []} for ticker, events in sorted(by_ticker.items())}
    value["corporate_intelligence_adapter"]["events"] = [e for events in by_ticker.values() for e in events
        if e["event_state"] in CURRENT_STATES and e["qualification"] == "EX_DATE_OFFICIAL_QUALIFIED"]
    counts = Counter(e["event_state"] for events in by_ticker.values() for e in events)
    for key, state in (("upcoming_events", "UPCOMING"), ("ex_date_today_events", "EX_DATE_TODAY"), ("recent_events", "RECENT"),
                       ("past_events", "PAST"), ("date_incomplete_events", "DATE_INCOMPLETE"), ("unknown_events", "UNKNOWN")):
        value["coverage"][key] = counts[state]
    value.update(_identity(value))
    replay(value)
    return value
