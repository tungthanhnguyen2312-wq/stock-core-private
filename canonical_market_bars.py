"""Pure canonical D/W/M projections over existing daily evidence; no acquisition."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import calendar as civil_calendar
from typing import Mapping, Sequence

import prospective_market_snapshot_contract as market
import market_only_pit_eligibility as pit
import session_bar_integrity as integrity

CONTRACT_VERSION = "canonical_market_bar/v1"
RESEARCH = "CURRENT_RESEARCH_PRICE_CONTEXT"


def _identity(body):
    body.update(market.content_identity(body, kind="canonical_market_bar"))
    return body


def period_bounds(session: str, timeframe: str):
    day = date.fromisoformat(session)
    if timeframe == "1D":
        return session, session
    if timeframe == "1W":
        start = day - timedelta(days=day.weekday())
        return start.isoformat(), (start + timedelta(days=6)).isoformat()
    if timeframe == "1M":
        return day.replace(day=1).isoformat(), day.replace(day=civil_calendar.monthrange(day.year,day.month)[1]).isoformat()
    raise ValueError("UNSUPPORTED_TIMEFRAME")


def project_daily(row: Mapping, *, ticker: str, source_identity: str) -> dict:
    """Copy existing values, semantics and exact row identity, without repricing."""
    prospective = "snapshot_identity" in row
    if row.get("ticker", ticker) != ticker:
        raise ValueError("DAILY_INSTRUMENT_MISMATCH")
    if prospective:
        expected = market.CONTRACT_VERSION + ":" + market.sha256_hex(market.canonical({k:v for k,v in row.items() if k != "snapshot_identity"}))
        if row["snapshot_identity"] != expected or row.get("instrument",{}).get("ticker") != ticker:
            raise ValueError("DAILY_SOURCE_IDENTITY_INVALID")
    session = row.get("trading_session") if prospective else row.get("session")
    date.fromisoformat(session)
    instrument = dict(row.get("instrument", {})) if prospective else {"ticker":ticker,"exchange":row.get("exchange"),"board":row.get("board")}
    ohlc = row.get("normalized",{}).get("ohlc",{}) if prospective else row
    values = {k:ohlc.get(k) for k in ("open","high","low","close")}
    valid = all(market._finite_number(v) and v > 0 for v in values.values())
    valid = valid and values["low"] <= min(values["open"],values["close"]) <= max(values["open"],values["close"]) <= values["high"]
    known = row.get("acquisition",{}).get("knowledge_available_at_utc") if prospective else row.get("retrieved_at")
    try: known = market._utc(known,"daily_known_at").isoformat()
    except ValueError: known = None
    native_basis = row.get("price_mode") or row.get("price_basis") or row.get("basis",{}).get("adjusted_raw_unknown_claim") or "UNKNOWN"
    uses = list(row.get("qualification",{}).get("allowed_uses",[])) if prospective else []
    basis = native_basis
    if "ADJUSTED_RETROSPECTIVE" in str(native_basis) or native_basis == pit.RETROSPECTIVE_ADJUSTED:
        basis = pit.RETROSPECTIVE_ADJUSTED
    elif native_basis == pit.PIT_CA_ADJUSTED:
        basis = pit.PIT_CA_ADJUSTED if known and pit._price_ready(row,mode=pit.PIT_CA_ADJUSTED,cutoff=market._utc(known,"known")) else "PIT_CA_ADJUSTED_UNQUALIFIED"
    elif market.USE_PROSPECTIVE_RAW_AS_TRADED_PRICE in uses:
        basis = pit.RAW_AS_TRADED
    elif native_basis == pit.RAW_AS_TRADED:
        basis = "RAW_CLAIM_UNQUALIFIED"
    volume = row.get("normalized",{}).get("volume_value",{}).get("volume") if prospective else row.get("volume")
    vq = row.get("volume_qualification",{})
    source = dict(row.get("source",{})) if prospective else {"provider":row.get("provider"),"route":"/price/ohlc" if row.get("dataset") == "DNSE_OHLC_1D" else row.get("route"),"field":row.get("field_identity",{}).get("volume")}
    allowed = [RESEARCH] if valid and (RESEARCH in uses or market.USE_CURRENT_SESSION_PRICE_RESEARCH in uses or
        (not prospective and row.get("qualification") == "CURRENT_MARKET_DESCRIPTIVE_QUALIFIED_ONLY")) else []
    warnings = ([] if valid else ["INVALID_OR_MISSING_DAILY_OHLC"]) + ([] if known else ["DAILY_KNOWLEDGE_TIME_UNKNOWN"])
    if basis == "PIT_CA_ADJUSTED_UNQUALIFIED": warnings.append("FACTOR_CHAIN_NOT_QUALIFIED")
    observation_id = row.get("snapshot_identity") or "retained_daily_observation:" + market.sha256_hex(market.canonical(row))
    return _identity({"contract_version":CONTRACT_VERSION,"instrument":instrument,"timeframe":"1D",
        "period_start":session,"period_end":session,"first_trading_session":session,"last_trading_session":session,
        **values,"volume":volume,"volume_unit":vq.get("unit",row.get("volume_unit","UNKNOWN")),
        "raw_lineage_identities":list(row.get("raw_lineage_identities",[])),"factor_chain":list(row.get("factor_chain",[])),
        "volume_basis":vq.get("basis",row.get("volume_basis","UNKNOWN")),"turnover":row.get("traded_value"),
        "turnover_unit":row.get("traded_value_unit"),"price_basis":basis,"source_price_basis":native_basis,
        "price_unit":row.get("board_basis",{}).get("unit",row.get("price_unit","UNKNOWN")),
        "source":source,"source_identities":[source_identity],"constituent_observation_identities":[observation_id],
        "constituent_sessions":[session],"constituent_count":1,"knowledge_available_at":known,
        "knowledge_cutoff":None,"finality":row.get("finality","SOURCE_FINALITY_UNDOCUMENTED"),
        "period_completeness":"DAILY_OBSERVATION","calendar_identity":None,"calendar_scope":None,
        "corporate_action_crossing":{"state":"UNKNOWN_EVENT_COVERAGE","factor_chain_state":"SOURCE_QUALIFIED_PIT_CHAIN" if basis == pit.PIT_CA_ADJUSTED else "NOT_ESTABLISHED","comparability":"PIT_NORMALIZED" if basis == pit.PIT_CA_ADJUSTED else "NOT_ESTABLISHED"},
        "fitness":{"allowed_uses":allowed,"source_allowed_uses":uses,"historical_pit_eligible":False,
                   "volume":"UNIT_UNDOCUMENTED" if vq.get("unit",row.get("volume_unit","UNKNOWN")) == "UNKNOWN" else "SOURCE_SCOPED",
                   "continuous_indicator_use":"NOT_ESTABLISHED","non_voting":True},"warnings":warnings,"status":"AVAILABLE" if valid else "UNAVAILABLE"})


def derive(rows: Sequence[Mapping], *, ticker: str, timeframe: str, period_session: str,
           knowledge_cutoff: str, source_identity: str, calendar_evidence: Mapping | None = None,
           ca_events: Sequence[Mapping] = (), requested_price_mode: str | None = None) -> dict:
    start,end = period_bounds(period_session,timeframe)
    cutoff = market._utc(knowledge_cutoff,"knowledge_cutoff")
    events = [e for e in ca_events if e.get("ticker") == ticker and e.get("ex_date")
              and start <= e["ex_date"] <= end and e.get("materiality_status") != "INFORMATIONAL_GOVERNANCE"
              and e.get("event_type") != "AGM" and e.get("knowledge_available_at", e.get("official_observed_at"))
              and market._utc(e.get("knowledge_available_at", e.get("official_observed_at")), "event_known") <= cutoff]
    eligible=[]
    for row in rows:
        day = row.get("trading_session",row.get("session"))
        if not day or not start <= day <= end or day > cutoff.astimezone(market.VN_TZ).date().isoformat(): continue
        daily = project_daily(row,ticker=ticker,source_identity=source_identity)
        if daily["knowledge_available_at"] and market._utc(daily["knowledge_available_at"],"known") <= cutoff:
            eligible.append(daily)
    # Resolve corrections by actual knowledge instant. Conflicting ties use the shared
    # session integrity rule; list order never selects an authoritative copy.
    by_day=defaultdict(list)
    for row in eligible: by_day[row["first_trading_session"]].append(row)
    chosen=[]
    for day,versions in sorted(by_day.items()):
        latest=max(r["knowledge_available_at"] for r in versions)
        same=[{**r,"session":day} for r in versions if r["knowledge_available_at"] == latest]
        resolved=integrity.resolve_session_bars(same,as_of_session=period_session if timeframe == "1D" else end)
        if resolved["status"] == integrity.CONFLICTING_DUPLICATE_REFUSED:
            raise ValueError(integrity.REFUSAL_REASON)
        chosen.extend({k:v for k,v in r.items() if k != "session"} for r in resolved["observations"])
    if timeframe == "1D" and chosen:
        body={k:v for k,v in chosen[0].items() if k not in ("artifact_identity","artifact_sha256")}
        body["knowledge_cutoff"]=knowledge_cutoff
        if events:
            body["corporate_action_crossing"] = {"state":"EVENTS_OBSERVED", "event_identities":sorted({e.get("event_id") or market.sha256_hex(market.canonical(e)) for e in events}),
                "factor_chain_state":"SOURCE_QUALIFIED_PIT_CHAIN" if body["price_basis"] == pit.PIT_CA_ADJUSTED else "NOT_ESTABLISHED", "comparability":"NOT_ESTABLISHED"}
            body["knowledge_available_at"] = max([body["knowledge_available_at"]] + [market._utc(e.get("knowledge_available_at", e.get("official_observed_at")), "event_known").isoformat() for e in events])
            body["warnings"] = sorted(set(body["warnings"] + ["CORPORATE_ACTION_CROSSING"]))
        if requested_price_mode and body["price_basis"] != requested_price_mode:
            body["status"]="UNAVAILABLE"
            body["fitness"]={**body["fitness"],"allowed_uses":[]}
            body["warnings"]=sorted(set(body["warnings"]+["FACTOR_CHAIN_NOT_QUALIFIED" if requested_price_mode == pit.PIT_CA_ADJUSTED else "REQUESTED_BASIS_UNAVAILABLE"]))
        return _identity(body)
    warnings=[]
    cal=dict(calendar_evidence or {})
    sessions=cal.get("sessions",[])
    if sessions != sorted(set(sessions)): raise ValueError("CALENDAR_NOT_SORTED_UNIQUE")
    cal_start=cal.get("window_start",sessions[0] if sessions else None)
    cal_end=cal.get("window_end",sessions[-1] if sessions else None)
    cal_known=cal.get("knowledge_available_at")
    cal_known_ok=not cal_known or market._utc(cal_known,"calendar_known") <= cutoff
    covered=bool(sessions and cal_start <= start <= end <= cal_end and cal_known_ok and cal.get("artifact_identity"))
    expected=[d for d in sessions if start <= d <= end] if covered else []
    observed=[r["first_trading_session"] for r in chosen]
    if cutoff.astimezone(market.VN_TZ).date().isoformat() <= end and timeframe != "1D":
        completeness="PARTIAL_CURRENT_PERIOD"
    elif not covered: completeness="CALENDAR_SCOPE_UNKNOWN"
    elif observed != expected: completeness="INCOMPLETE_SESSION_COVERAGE"
    else: completeness="COMPLETE"
    if completeness != "COMPLETE":warnings.append(completeness)
    signatures={(market.canonical(r["instrument"]),r["price_basis"],r["price_unit"],market.canonical(r["source"])) for r in chosen}
    compatible=bool(chosen) and len(signatures)==1 and all(r["status"] == "AVAILABLE" for r in chosen)
    if not compatible:warnings.append("PRICE_CONSTITUENTS_INCOMPATIBLE_OR_MISSING")
    bases=sorted({r["price_basis"] for r in chosen})
    basis=bases[0] if len(bases)==1 else "MIXED_OR_UNKNOWN"
    if requested_price_mode and basis != requested_price_mode:
        compatible=False;warnings.append("FACTOR_CHAIN_NOT_QUALIFIED" if requested_price_mode == pit.PIT_CA_ADJUSTED else "REQUESTED_BASIS_UNAVAILABLE")
    volume_values=[r["volume"] for r in chosen]
    volume_signatures={(r["volume_unit"],r["volume_basis"],market.canonical(r["source"])) for r in chosen}
    volume_compatible=bool(chosen) and len(volume_signatures)==1 and all(market._finite_number(v) and v >= 0 for v in volume_values)
    crossing={"state":"EVENTS_OBSERVED" if events else "UNKNOWN_EVENT_COVERAGE",
              "event_identities":sorted({e.get("event_id") or e.get("source_record_identity") or market.sha256_hex(market.canonical(e)) for e in events}),
              "factor_chain_state":"SOURCE_QUALIFIED_PIT_CHAIN" if basis == pit.PIT_CA_ADJUSTED and compatible else "NOT_ESTABLISHED",
              "comparability":"PIT_NORMALIZED" if basis == pit.PIT_CA_ADJUSTED and compatible else "NOT_ESTABLISHED"}
    if events:warnings.append("CORPORATE_ACTION_CROSSING")
    allowed=set.intersection(*(set(r["fitness"]["allowed_uses"]) for r in chosen)) if chosen else set()
    if not compatible:allowed.clear()
    knowns=[r["knowledge_available_at"] for r in chosen]
    knowns.extend(market._utc(e.get("knowledge_available_at", e.get("official_observed_at")), "event_known").isoformat() for e in events)
    if covered and cal_known:knowns.append(market._utc(cal_known,"cal_known").isoformat())
    values={"open":chosen[0]["open"],"high":max(r["high"] for r in chosen),"low":min(r["low"] for r in chosen),"close":chosen[-1]["close"]} if compatible else dict.fromkeys(("open","high","low","close"))
    return _identity({"contract_version":CONTRACT_VERSION,"instrument":chosen[0]["instrument"] if chosen else {"ticker":ticker,"exchange":None,"board":None},
        "timeframe":timeframe,"period_start":start,"period_end":end,"first_trading_session":observed[0] if observed else None,
        "last_trading_session":observed[-1] if observed else None,**values,"volume":sum(volume_values) if volume_compatible else None,
        "constituent_volume_values":volume_values,"volume_unit":chosen[0]["volume_unit"] if volume_compatible else "UNKNOWN",
        "volume_basis":chosen[0]["volume_basis"] if volume_compatible else "INCOMPATIBLE_OR_MISSING","turnover":None,"turnover_unit":None,
        "price_basis":basis,"source_price_bases":sorted({str(r["source_price_basis"]) for r in chosen}),
        "price_unit":chosen[0]["price_unit"] if compatible else "UNKNOWN","source_identities":sorted({s for r in chosen for s in r["source_identities"]}),
        "constituent_observation_identities":[r["constituent_observation_identities"][0] for r in chosen],
        "constituent_bar_identities":[r["artifact_identity"] for r in chosen],"constituent_sessions":observed,"constituent_count":len(chosen),
        "constituent_factor_chains":[{"observation_identity":r["constituent_observation_identities"][0],"raw_lineage_identities":r["raw_lineage_identities"],"factor_chain":r["factor_chain"]} for r in chosen if r["factor_chain"]],
        "knowledge_cutoff":knowledge_cutoff,"knowledge_available_at":max(knowns) if knowns else None,
        "finality":"DERIVED_FROM_SOURCE_OBSERVATIONS_NOT_PROVIDER_FINALITY_PROOF","period_completeness":completeness,
        "calendar_identity":cal.get("artifact_identity") if covered else None,"calendar_scope":cal.get("source") if covered else None,
        "expected_sessions":expected,"corporate_action_crossing":crossing,
        "fitness":{"allowed_uses":sorted(allowed),"historical_pit_eligible":False,"volume":"UNIT_UNDOCUMENTED" if volume_compatible and chosen[0]["volume_unit"] == "UNKNOWN" else "SOURCE_SCOPED_NUMERIC_AGGREGATE" if volume_compatible else "UNAVAILABLE",
                   "continuous_indicator_use":"NOT_ESTABLISHED","non_voting":True},
        "warnings":sorted(set(warnings+[w for r in chosen for w in r["warnings"]])),"status":"AVAILABLE" if compatible else "UNAVAILABLE"})


def research_projection(rows, *, ticker, target_session, knowledge_cutoff, source_identity, calendar_evidence=None, ca_events=()):
    """Group once; provide latest D, completed W/M, and honest latest-period fallback."""
    groups={tf:defaultdict(list) for tf in ("1D","1W","1M")}
    for row in rows:
        day=row.get("trading_session",row.get("session"))
        if not day or day > target_session:continue
        for tf in groups:groups[tf][period_bounds(day,tf)[0]].append(row)
    result={"contract_version":"market_bar_research_projection/v1","target_session":target_session,"knowledge_cutoff":knowledge_cutoff,"non_voting":True}
    for tf,periods in groups.items():
        bars=[derive(v,ticker=ticker,timeframe=tf,period_session=start,knowledge_cutoff=knowledge_cutoff,
            source_identity=source_identity,calendar_evidence=calendar_evidence,ca_events=ca_events) for start,v in sorted(periods.items())]
        available=[b for b in bars if b["status"] == "AVAILABLE" and RESEARCH in b["fitness"]["allowed_uses"]]
        completed=[b for b in available if b["period_completeness"] == "COMPLETE"]
        result[tf]={"latest_observed":available[-1] if available else None,"latest_completed":completed[-1] if completed else None,
                    "period_count":len(bars),"available_periods":len(available),"complete_periods":len(completed),
                    "status":"AVAILABLE" if available else "UNAVAILABLE","blocker":"NO_COMPLETE_CALENDAR_QUALIFIED_PERIOD" if tf != "1D" and not completed else None}
    daily=result['1D']['latest_observed']
    result["PIT_CA_ADJUSTED"]={"status":"AVAILABLE" if daily and daily['price_basis']==pit.PIT_CA_ADJUSTED else "UNAVAILABLE",
                               "reason":None if daily and daily['price_basis']==pit.PIT_CA_ADJUSTED else "FACTOR_CHAIN_NOT_QUALIFIED"}
    result.update(market.content_identity(result,kind="market_bar_research_projection"))
    return result


def governed_calendar_projection(value: Mapping) -> dict:
    if value.get("contract_version") != "governed_trading_session_calendar/v1" or value.get("source",{}).get("kind") != "EXPLICIT_GOVERNED_SESSION_EVIDENCE":
        raise ValueError("EXPLICIT_GOVERNED_CALENDAR_REQUIRED")
    sessions=value["sessions"]
    if not sessions or sessions != sorted(set(sessions)):raise ValueError("CALENDAR_NOT_SORTED_UNIQUE")
    return {**value,"artifact_identity":"governed_calendar:"+market.sha256_hex(market.canonical(value)),
            "window_start":sessions[0],"window_end":sessions[-1]}
