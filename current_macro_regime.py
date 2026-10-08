"""Evidence-bound current macro regime; descriptive research only, never a forecast."""
from __future__ import annotations

import copy
import base64
import csv
import hashlib
import io
import json
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Mapping
from urllib.request import Request, urlopen

from field_temporal_contract import stable_id
from freshness_history import freshness_envelope, parse_timestamp

CONTRACT_VERSION = "current_macro_regime/v1"
RULE_VERSION = "macro_axes_rules/v1"
FRED = {
    "us_fed_funds": ("DFF", "United States", "global_rates", "percent"),
    "us_cpi": ("CPIAUCSL", "United States", "inflation", "index_1982_84_100"),
    "us_treasury_2y": ("DGS2", "United States", "global_rates", "percent"),
    "us_treasury_10y": ("DGS10", "United States", "global_rates", "percent"),
    "usd_emerging_markets": ("DTWEXEMEGS", "United States", "usd", "index_2006_100"),
    "wti_oil": ("DCOILWTICO", "United States", "energy", "usd_per_barrel"),
}


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(value)); payload.pop("artifact_identity", None); payload.pop("artifact_sha256", None)
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": "current_macro_regime:" + digest}


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fetch(url: str) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": "StockLookup-current-macro-regime/1.0"})
    with urlopen(request, timeout=30) as response:
        raw = response.read()
    return raw, hashlib.sha256(raw).hexdigest()


def _fred_observation(indicator_id: str, code: str, region: str, category: str, unit: str, retrieved_at: str) -> tuple[dict[str, Any], dict[str, Any]]:
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + code
    raw, payload_hash = _fetch(url)
    retrieved_at = _now()
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    usable = [(row.get("observation_date"), row.get(code)) for row in rows if row.get("observation_date") and row.get(code) not in (None, ".", "")]
    if not usable: raise ValueError("FRED_NO_USABLE_OBSERVATION:" + code)
    latest_date, latest_value = usable[-1]; previous = usable[-2] if len(usable) > 1 else (None, None)
    observation = {"indicator_id": indicator_id, "country_or_region": region, "category": category, "value": float(latest_value), "unit": unit, "observation_date": latest_date, "released_at": None, "source": "Federal Reserve Bank of St. Louis FRED", "source_identity": "FRED:" + code, "url": url, "retrieved_at": retrieved_at, "freshness": {"frequency": "DAILY_OR_MONTHLY_SERIES", "status": "CURRENT_RESEARCH_NOT_HISTORICAL_PIT"}, "revision_state": "SOURCE_LATEST_VINTAGE_RELEASE_DATE_NOT_RETAINED", "authority": "OFFICIAL_PUBLIC_SOURCE", "status": "AVAILABLE", "limitations": ["FRED graph CSV does not provide release timestamps; not historical PIT."], "previous_observation_date": previous[0], "previous_value": float(previous[1]) if previous[1] is not None else None, "raw_payload_sha256": payload_hash}
    return observation, {"source_identity": "FRED:" + code, "url": url, "retrieved_at": retrieved_at, "sha256": payload_hash, "raw_payload_base64": base64.b64encode(raw).decode("ascii"), "status": "RETAINED"}


def _unavailable(indicator_id: str, category: str, reason: str, retrieved_at: str) -> dict[str, Any]:
    return {"indicator_id": indicator_id, "country_or_region": "Vietnam", "category": category, "value": None, "unit": "UNKNOWN", "observation_date": None, "released_at": None, "source": "State Bank of Vietnam official portal", "source_identity": "SBV:" + indicator_id, "url": "https://www.sbv.gov.vn/", "retrieved_at": retrieved_at, "freshness": {"status": "UNKNOWN"}, "revision_state": "UNKNOWN", "authority": "OFFICIAL_SOURCE_ROUTE_ATTEMPTED", "status": "UNAVAILABLE", "limitations": [reason], "previous_observation_date": None, "previous_value": None, "raw_payload_sha256": None}


def acquire() -> dict[str, Any]:
    retrieved_at = _now(); observations: list[dict[str, Any]] = []; raw_sources: list[dict[str, Any]] = []
    for indicator_id, (code, region, category, unit) in FRED.items():
        try:
            observation, raw = _fred_observation(indicator_id, code, region, category, unit, retrieved_at); observations.append(observation); raw_sources.append(raw)
        except Exception as exc:
            observations.append({"indicator_id": indicator_id, "country_or_region": region, "category": category, "value": None, "unit": unit, "observation_date": None, "released_at": None, "source": "Federal Reserve Bank of St. Louis FRED", "source_identity": "FRED:" + code, "url": "https://fred.stlouisfed.org/series/" + code, "retrieved_at": retrieved_at, "freshness": {"status": "UNKNOWN"}, "revision_state": "UNKNOWN", "authority": "OFFICIAL_PUBLIC_SOURCE", "status": "UNAVAILABLE", "limitations": ["ACQUISITION_FAILED:" + type(exc).__name__], "previous_observation_date": None, "previous_value": None, "raw_payload_sha256": None})
    try:
        from vietnam_official_macro_evidence import acquire as acquire_vietnam, current_macro_observations
        vietnam = acquire_vietnam(retrieved_at=retrieved_at)
        vietnam_known_at = _now()
        observations.extend({**row, "known_at": vietnam_known_at} for row in current_macro_observations(vietnam))
        raw_sources.append({"source_identity": "vietnam_official_macro_evidence", "artifact_identity": vietnam["artifact_identity"], "sha256": vietnam["artifact_sha256"], "status": "RETAINED_EVIDENCE_ARTIFACT", "evidence_artifact": vietnam})
    except Exception as exc:
        observations += [_unavailable("vn_cpi_yoy", "inflation", "VIETNAM_OFFICIAL_MACRO_ACQUISITION_FAILED:" + type(exc).__name__, retrieved_at), _unavailable("vn_policy_rate", "domestic_rates", "NO_MACHINE_READABLE_CURRENT_OFFICIAL_POLICY_RATE_OBSERVATION_RETAINED", retrieved_at), _unavailable("vn_usd_vnd", "fx", "NO_MACHINE_READABLE_CURRENT_OFFICIAL_SBV_FX_OBSERVATION_RETAINED", retrieved_at), _unavailable("vn_credit_growth", "credit", "NO_CURRENT_OFFICIAL_CREDIT_RELEASE_RETAINED", retrieved_at), _unavailable("vn_system_liquidity", "liquidity", "NO_QUALIFIED_OFFICIAL_SYSTEM_LIQUIDITY_PROXY_RETAINED", retrieved_at), _unavailable("vn_government_bond_yield", "government_bonds", "NO_CURRENT_MACHINE_READABLE_OFFICIAL_BOND_YIELD_RETAINED", retrieved_at)]
    return build(observations=observations, raw_sources=raw_sources, retrieved_at=_now())


def _axis(observations: Mapping[str, Mapping[str, Any]], axis: str) -> dict[str, Any]:
    def item(key: str) -> Mapping[str, Any]: return observations.get(key) or {}
    def movement(key: str, threshold: float = 0.01) -> str:
        row = item(key); value, previous = row.get("value"), row.get("previous_value")
        if row.get("status") != "AVAILABLE": return "UNKNOWN"
        if not isinstance(value, (int, float)) or not isinstance(previous, (int, float)): return "UNKNOWN"
        return "UP" if value - previous > threshold else "DOWN" if previous - value > threshold else "FLAT"
    rules = {
        "DOMESTIC_RATES": ("vn_policy_rate", {"DOWN": "EASING", "UP": "TIGHTENING", "FLAT": "STABLE"}),
        "INFLATION_PRESSURE": ("vn_cpi_yoy", {"DOWN": "EASING", "UP": "ACCELERATING", "FLAT": "STABLE"}),
        "FX_PRESSURE": ("vn_usd_vnd", {"DOWN": "EASING", "UP": "ACCELERATING", "FLAT": "STABLE"}),
        "CREDIT_CONTEXT": ("vn_credit_growth", {"DOWN": "WEAKENING", "UP": "IMPROVING", "FLAT": "STABLE"}),
        "DOMESTIC_LIQUIDITY": ("vn_system_liquidity", {"DOWN": "TIGHTENING", "UP": "EASING", "FLAT": "NEUTRAL"}),
        "GLOBAL_RATES": ("us_fed_funds", {"DOWN": "EASING", "UP": "TIGHTENING", "FLAT": "NEUTRAL"}),
        "USD_PRESSURE": ("usd_emerging_markets", {"DOWN": "EASING", "UP": "RISING", "FLAT": "NEUTRAL"}),
        "COMMODITY_CONTEXT": ("wti_oil", {"DOWN": "SUPPORTIVE", "UP": "PRESSURE", "FLAT": "NEUTRAL"}),
    }
    key, mapping = rules[axis]; direction = movement(key); state = mapping.get(direction, "UNKNOWN")
    return {"axis": axis, "state": state, "rule_version": RULE_VERSION, "observation_ids": [key], "rule": "latest minus immediately preceding retained observation; no change is inferred when either is unavailable", "limitations": list(item(key).get("limitations") or [])}


def build(*, observations: list[Mapping[str, Any]], raw_sources: list[Mapping[str, Any]], retrieved_at: str) -> dict[str, Any]:
    indexed = {str(row["indicator_id"]): dict(row) for row in observations}; axes = {name: _axis(indexed, name) for name in ("DOMESTIC_RATES", "INFLATION_PRESSURE", "FX_PRESSURE", "CREDIT_CONTEXT", "DOMESTIC_LIQUIDITY", "GLOBAL_RATES", "USD_PRESSURE", "COMMODITY_CONTEXT")}
    supportive = [name for name, row in axes.items() if row["state"] in {"EASING", "SUPPORTIVE"}]; restrictive = [name for name, row in axes.items() if row["state"] in {"TIGHTENING", "ACCELERATING", "RISING", "PRESSURE"}]; unknown = [name for name, row in axes.items() if row["state"] == "UNKNOWN"]
    regime = "INSUFFICIENT_EVIDENCE" if len(unknown) > 4 else "MIXED" if supportive and restrictive else "SUPPORTIVE" if supportive else "RESTRICTIVE" if restrictive else "INSUFFICIENT_EVIDENCE"
    artifact = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "retrieved_at": retrieved_at, "current_research_as_of": retrieved_at[:10], "observations": indexed, "raw_sources": list(raw_sources), "state_axes": axes, "macro_regime": {"state": regime, "rule_version": RULE_VERSION, "supporting_axes": supportive, "restrictive_axes": restrictive, "unavailable_axes": unknown, "meaning": "Descriptive current-research context, not an equity forecast or causal conclusion."}, "events": [], "human_research": {"vietnam": ["Vietnam CPI is retained from dated NSO releases; all other domestic dimensions remain unavailable without an explicit retained first-party metric."], "global": ["Global observations are official-source latest-vintage current research; their release timestamps are unavailable in FRED graph CSV and therefore they are not historical PIT."], "what_to_verify_next": ["Obtain a source-bound SBV current policy, FX, credit, and liquidity observation.", "Obtain an official HNX or government-bond current yield observation.", "Retain release timestamps or vintages before historical macro PIT use."]}, "authority_boundary": {"current_research_only": True, "historical_pit": "NOT_EMITTED", "forecast_probability_target_recommendation_sizing_execution": "NOT_EMITTED", "macro_sector_beta_or_sensitivity": "NOT_EMITTED"}, "is_actionable": False}
    artifact.update(content_identity(artifact)); return artifact


def _knowledge_timestamp(value: Any) -> datetime | None:
    """An intraday knowledge claim requires an explicit timezone, never an assumed UTC."""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def session_context(macro: Mapping[str, Any] | None, session: str, *, cutoff: str | None = None) -> dict[str, Any]:
    if not macro: return {"status": "UNAVAILABLE", "reason": "NO_EXPLICIT_MACRO_ARTIFACT_BOUND", "is_actionable": False}
    reference = _knowledge_timestamp(cutoff)
    if reference is None:
        return {"status": "UNAVAILABLE", "reason": "EXPLICIT_MACRO_CUTOFF_REQUIRED", "is_actionable": False}
    if reference.astimezone(timezone(timedelta(hours=7))).date().isoformat() != session:
        return {"status": "UNAVAILABLE", "reason": "MACRO_CUTOFF_SESSION_MISMATCH", "is_actionable": False}
    if macro.get("contract_version") != CONTRACT_VERSION or any(macro.get(key) != value for key, value in content_identity(macro).items()):
        return {"status": "UNAVAILABLE", "reason": "MACRO_ARTIFACT_IDENTITY_INVALID", "is_actionable": False}
    known = _knowledge_timestamp(macro.get("retrieved_at"))
    if known is None or known > reference:
        return {"status": "UNAVAILABLE", "reason": "MACRO_EVIDENCE_NOT_KNOWN_BY_RETAINED_EQUITY_SESSION", "macro_artifact_identity": macro.get("artifact_identity"), "is_actionable": False}
    rows = []
    excluded = {}
    for identifier, source in (macro.get("observations") or {}).items():
        row = copy.deepcopy(source)
        reasons = []
        retrieved = _knowledge_timestamp(row.get("retrieved_at"))
        knowledge = _knowledge_timestamp(row.get("known_at") or row.get("retrieved_at"))
        if retrieved is None or knowledge is None or max(retrieved, knowledge) > reference:
            reasons.append("OBSERVATION_NOT_KNOWN_AT_CUTOFF")
        release = row.get("released_at")
        if release:
            published = parse_timestamp(release) if len(str(release)) == 10 else _knowledge_timestamp(release)
            if published is None or (len(str(release)) > 10 and published > reference) or (len(str(release)) == 10 and str(release) > session):
                reasons.append("RELEASE_AFTER_CUTOFF_OR_INVALID")
        freshness = dict(row.get("freshness") or {})
        freshness["historical_pit"] = "NOT_PROMOTED"
        next_release = freshness.get("next_expected_official_release")
        # NSO has its own retained release-calendar rule; never replace it with a day threshold.
        if next_release:
            if session >= str(next_release)[:10]: reasons.append("NEXT_OFFICIAL_RELEASE_DUE")
        elif identifier in FRED:
            domain = "macro_monthly" if identifier == "us_cpi" else "macro_daily"
            envelope = freshness_envelope(domain=domain, as_of_date=row.get("observation_date"), generated_at=row.get("retrieved_at"), source=row.get("source"), reference_at=reference)
            envelope["is_actionable"] = False
            freshness["cadence_assessment"] = envelope
            if envelope["freshness_status"] not in {"current", "expiring"}: reasons.append("FRED_OBSERVATION_STALE_OR_UNKNOWN")
        if str(freshness.get("status", "UNKNOWN")).upper() in {"STALE", "STALE_OR_UNAVAILABLE", "UNKNOWN", "UNAVAILABLE"}:
            reasons.append("OBSERVATION_FRESHNESS_NOT_CURRENT")
        if row.get("authority") != "OFFICIAL_PUBLIC_SOURCE": reasons.append("OBSERVATION_AUTHORITY_NOT_QUALIFIED")
        row["freshness"] = freshness
        row["temporal"] = {"cutoff": cutoff, "knowledge_time": row.get("known_at") or row.get("retrieved_at"), "release_precision": "DATE_ONLY" if release and len(str(release)) == 10 else "TIMESTAMP" if release else "UNKNOWN", "historical_pit": "NOT_PROMOTED", "excluded_reasons": reasons}
        if reasons:
            excluded[identifier] = reasons
            row["status"] = "UNAVAILABLE"
            row["limitations"] = list(row.get("limitations") or []) + reasons
        rows.append(row)
    narrowed = build(observations=rows, raw_sources=[], retrieved_at=macro["retrieved_at"])
    return {"status": "AVAILABLE", "macro_artifact_identity": macro.get("artifact_identity"), "cutoff": cutoff, "macro_regime": narrowed["macro_regime"], "state_axes": narrowed["state_axes"], "observations": narrowed["observations"], "excluded_observations": excluded, "is_actionable": False}
