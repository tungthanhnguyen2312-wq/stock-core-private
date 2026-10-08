"""Bind existing macro, breadth, and sector artifacts into one decision context.

This module does not acquire observations, invent indicators, or emit a score.
Axis states are read from the supplying artifact. A missing input stays UNKNOWN.
"""
from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Mapping

from current_macro_regime import session_context
from field_temporal_contract import stable_id

CONTRACT_VERSION = "macro_market_regime_decision_context/v1"
MILESTONE_ID = "MACRO_MARKET_REGIME_DECISION_CONTEXT_CONVERGENCE_V1"
DISPOSITION = "PARTIAL_MACRO_MARKET_REGIME_DECISION_CONTEXT_READY"
OCTOBER_7_LAST_SESSION = "2026-10-07"
KNOWLEDGE_AVAILABLE_AT = "2026-10-08T06:10:00Z"

MACRO_AXES = (
    "DOMESTIC_RATES",
    "INFLATION_PRESSURE",
    "FX_PRESSURE",
    "CREDIT_CONTEXT",
    "DOMESTIC_LIQUIDITY",
    "GLOBAL_RATES",
    "USD_PRESSURE",
    "COMMODITY_CONTEXT",
)
MARKET_AXES = (
    "PRICE_REGIME",
    "MARKET_BREADTH",
    "PARTICIPATION",
    "LIQUIDITY_RISK_APPETITE",
    "FOREIGN_FLOW",
    "VOLATILITY_STRESS",
)
SECTOR_AXES = (
    "SECTOR_RELATIVE_STRENGTH",
    "SECTOR_PARTICIPATION",
    "LEADERSHIP_PERSISTENCE",
    "LEADERSHIP_DETERIORATION",
)
MACRO_CONTRACT = "current_macro_regime/v1"
BREADTH_CONTRACT = "market_regime_breadth_context/v1"
SECTOR_CONTRACT = "current_market_sector_leadership_context/v1"
PRESENTATION_CONTRACT = "macro_presentation_context/v1"
NON_OFFICIAL_AUTHORITIES = {
    "UNOFFICIAL_MARKET_DATA_SOURCE",
    "FIRST_PARTY_QUOTE_UNOFFICIAL_TRANSPORT",
    "UNKNOWN_SOURCE_AUTHORITY",
}
RESTRICTIVE_MACRO = {"TIGHTENING", "ACCELERATING", "RISING", "PRESSURE", "RESTRICTIVE"}
SUPPORTIVE_MACRO = {"EASING", "SUPPORTIVE"}
SUPPORTIVE_MARKET = {
    "BREADTH_POSITIVE",
    "EMPIRICAL_COHORT_TREND_PARTICIPATION_BROAD",
    "BROAD_PARTICIPATION",
    "MOMENTUM_BREADTH_POSITIVE",
}
RESTRICTIVE_MARKET = {
    "BREADTH_NEGATIVE",
    "EMPIRICAL_COHORT_TREND_PARTICIPATION_NARROW",
    "DETERIORATING_BREADTH",
    "MOMENTUM_BREADTH_NEGATIVE",
}
FORBIDDEN_KEYS = {
    "buy_score",
    "recommendation",
    "probability",
    "expected_return",
    "forecast_return",
    "target_price",
    "target_vnindex",
    "position_size",
    "sizing",
    "composite_score",
    "regime_score",
    "risk_on_score",
    "buy_market",
    "sell_market",
    "sector_expected_return",
    "allocation",
}
DOMESTIC_SELECTION = (
    {
        "metric_id": "vn_usd_vnd",
        "axis": "FX_PRESSURE",
        "authority": "SBV central/reference USD/VND",
        "reason": "Highest-priority missing domestic axis. No retained first-party series and no governed machine-readable locator.",
    },
    {
        "metric_id": "vn_policy_rate",
        "axis": "DOMESTIC_RATES",
        "authority": "SBV policy or operating rate",
        "reason": "Requires a retained SBV publication naming the rate and effective date. None is retained.",
    },
    {
        "metric_id": "vn_credit_growth",
        "axis": "CREDIT_CONTEXT",
        "authority": "SBV credit growth release",
        "reason": "Requires a retained SBV credit release stating basis and as-of date. None is retained.",
    },
)


def _reject_forbidden(value: Any, *, where: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key) in FORBIDDEN_KEYS:
                raise ValueError(f"FORBIDDEN_{where}_{str(key).upper()}")
            _reject_forbidden(item, where=where)
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden(item, where=where)


def _dimension(*, axis: str, state: str, evidence: list[dict[str, Any]], freshness: Mapping[str, Any], authority: str, limitations: list[str]) -> dict[str, Any]:
    row = {
        "axis": axis,
        "state": state,
        "evidence": evidence,
        "freshness": dict(freshness),
        "authority": authority,
        "limitations": limitations,
    }
    _reject_forbidden(row, where="DIMENSION")
    return row


def _unknown(axis: str, reason: str) -> dict[str, Any]:
    return _dimension(
        axis=axis,
        state="UNKNOWN",
        evidence=[],
        freshness={"status": "UNKNOWN"},
        authority="ABSENT",
        limitations=[reason],
    )


def _identity_ok(artifact: Mapping[str, Any] | None, contract: str) -> bool:
    return isinstance(artifact, Mapping) and artifact.get("contract_version") == contract and bool(artifact.get("artifact_identity"))


def _closed_session(session: str | None) -> bool:
    """The completed 2026-10-07 Daily is closed. Earlier sessions stay readable
    only through the macro session-knowledge rule, which refuses later evidence."""
    return session == OCTOBER_7_LAST_SESSION


def _macro_dimensions(macro: Mapping[str, Any] | None, session: str | None, cutoff: str | None = None) -> dict[str, dict[str, Any]]:
    if not _identity_ok(macro, MACRO_CONTRACT):
        return {axis: _unknown(axis, "NO_EXPLICIT_MACRO_ARTIFACT_IDENTITY") for axis in MACRO_AXES}
    if _closed_session(session):
        return {axis: _unknown(axis, "COMPLETED_OCTOBER_7_SESSION_NOT_REWRITTEN") for axis in MACRO_AXES}
    bound = session_context(macro, session, cutoff=cutoff) if session and session != "SCRATCH_CURRENT" else {"status": "AVAILABLE", "state_axes": macro.get("state_axes"), "observations": macro.get("observations")}
    if bound.get("status") != "AVAILABLE":
        reason = str(bound.get("reason") or "MACRO_NOT_KNOWN_FOR_SESSION")
        return {axis: _unknown(axis, reason) for axis in MACRO_AXES}
    axes = bound.get("state_axes") or {}
    observations = bound.get("observations") or {}
    rows: dict[str, dict[str, Any]] = {}
    for axis in MACRO_AXES:
        source = axes.get(axis) if isinstance(axes, Mapping) else None
        if not isinstance(source, Mapping) or not source.get("state"):
            rows[axis] = _unknown(axis, "AXIS_ABSENT_FROM_EXPLICIT_MACRO_ARTIFACT")
            continue
        observation_ids = [str(item) for item in source.get("observation_ids") or []]
        evidence = []
        freshness = {"status": "UNKNOWN"}
        authority = "OFFICIAL_PUBLIC_SOURCE"
        limitations = list(source.get("limitations") or [])
        unavailable = False
        for indicator_id in observation_ids:
            observation = observations.get(indicator_id) if isinstance(observations, Mapping) else None
            if not isinstance(observation, Mapping):
                unavailable = True
                continue
            evidence.append({
                "artifact_identity": macro.get("artifact_identity"),
                "indicator_id": indicator_id,
                "source_identity": observation.get("source_identity"),
                "observation_date": observation.get("observation_date"),
                "released_at": observation.get("released_at"),
                "retrieved_at": observation.get("retrieved_at"),
                "knowledge_time": observation.get("known_at") or observation.get("retrieved_at"),
                "value": observation.get("value"),
                "unit": observation.get("unit"),
                "raw_payload_sha256": observation.get("raw_payload_sha256"),
                "freshness": copy.deepcopy(observation.get("freshness")),
                "authority": observation.get("authority"),
                "temporal": copy.deepcopy(observation.get("temporal")),
                "value_present": observation.get("value") is not None,
            })
            freshness = dict(observation.get("freshness") or freshness)
            authority = str(observation.get("authority") or authority)
            if observation.get("status") != "AVAILABLE":
                unavailable = True
                limitations.append("OBSERVATION_UNAVAILABLE")
        state = "UNKNOWN" if unavailable or not evidence else str(source["state"])
        rows[axis] = _dimension(
            axis=axis,
            state=state,
            evidence=evidence,
            freshness=freshness,
            authority=authority if state != "UNKNOWN" else "OFFICIAL_SOURCE_ROUTE_ATTEMPTED",
            limitations=limitations or ["NO_QUALIFIED_CHANGE"],
        )
    return rows


def _descriptor_value(artifact: Mapping[str, Any], prefix: str) -> str | None:
    for row in artifact.get("descriptors") or []:
        if isinstance(row, Mapping) and str(row.get("descriptor") or "").startswith(prefix):
            return str(row["descriptor"])
    return None


def _market_dimensions(breadth: Mapping[str, Any] | None, sector: Mapping[str, Any] | None, presentation: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    breadth_ok = _identity_ok(breadth, BREADTH_CONTRACT)
    sector_ok = _identity_ok(sector, SECTOR_CONTRACT)
    if breadth_ok:
        breadth_state = _descriptor_value(breadth, "BREADTH_")
        participation = _descriptor_value(breadth, "EMPIRICAL_COHORT_TREND_PARTICIPATION_")
        volatility = None
        vol = (breadth.get("breadth") or {}).get("volatility") if isinstance(breadth.get("breadth"), Mapping) else None
        if isinstance(vol, Mapping):
            volatility = vol.get("descriptor")
        evidence = [{"artifact_identity": breadth.get("artifact_identity"), "research_session": breadth.get("research_session")}]
        freshness = {"status": "CURRENT_RESEARCH_ONLY", "session": breadth.get("research_session")}
        rows["MARKET_BREADTH"] = _dimension(
            axis="MARKET_BREADTH",
            state=breadth_state or "UNKNOWN",
            evidence=evidence,
            freshness=freshness,
            authority="EMPIRICAL_ACTIVE_SHADOW_ONLY",
            limitations=[] if breadth_state else ["BREADTH_DESCRIPTOR_ABSENT"],
        )
        rows["PARTICIPATION"] = _dimension(
            axis="PARTICIPATION",
            state=participation or "UNKNOWN",
            evidence=evidence,
            freshness=freshness,
            authority="EMPIRICAL_ACTIVE_SHADOW_ONLY",
            limitations=[] if participation else ["PARTICIPATION_DESCRIPTOR_ABSENT"],
        )
        rows["PRICE_REGIME"] = _dimension(
            axis="PRICE_REGIME",
            state=breadth_state or "UNKNOWN",
            evidence=evidence,
            freshness=freshness,
            authority="EMPIRICAL_ACTIVE_SHADOW_ONLY",
            limitations=["PRICE_REGIME_IS_THE_EXISTING_TREND_BREADTH_DESCRIPTOR"],
        )
        rows["VOLATILITY_STRESS"] = _dimension(
            axis="VOLATILITY_STRESS",
            state=str(volatility) if volatility else "UNKNOWN",
            evidence=evidence if volatility else [],
            freshness=freshness,
            authority="SHADOW_ONLY" if volatility else "ABSENT",
            limitations=["CONTEMPORANEOUS_CROSS_SECTION_ONLY_NOT_HISTORICAL_REGIME"] if volatility else ["VOLATILITY_DESCRIPTOR_ABSENT"],
        )
        rows["LIQUIDITY_RISK_APPETITE"] = _unknown("LIQUIDITY_RISK_APPETITE", "PROVIDER_RELATIVE_VOLUME_IS_NOT_LIQUIDITY_OR_TURNOVER")
    else:
        for axis in ("PRICE_REGIME", "MARKET_BREADTH", "PARTICIPATION", "LIQUIDITY_RISK_APPETITE", "VOLATILITY_STRESS"):
            rows[axis] = _unknown(axis, "NO_EXPLICIT_BREADTH_ARTIFACT_IDENTITY")
    if sector_ok:
        market = sector.get("market") if isinstance(sector.get("market"), Mapping) else {}
        state = str(market.get("current_breadth_state") or "UNKNOWN")
        evidence = [{"artifact_identity": sector.get("artifact_identity"), "session": sector.get("session"), "field": "market.current_breadth_state"}]
        exact = _dimension(
            axis="EXACT_SESSION_BREADTH",
            state=state,
            evidence=evidence,
            freshness={"status": "CURRENT_SESSION_DESCRIPTIVE_ONLY", "session": sector.get("session")},
            authority="CURRENT_SESSION_DESCRIPTIVE",
            limitations=list(market.get("warnings") or ["NO_PRIOR_SESSION_COMPARISON"]),
        )
        rows["EXACT_SESSION_BREADTH"] = exact
    if _identity_ok(presentation, PRESENTATION_CONTRACT):
        flow = presentation.get("foreign_flow") if isinstance(presentation.get("foreign_flow"), Mapping) else {}
        status = str(flow.get("status") or "UNAVAILABLE").upper()
        rows["FOREIGN_FLOW"] = _dimension(
            axis="FOREIGN_FLOW",
            state="UNKNOWN" if status in {"UNAVAILABLE", "UNKNOWN", ""} else status,
            evidence=[{"artifact_identity": presentation.get("artifact_identity"), "source": flow.get("source")}],
            freshness={"status": status},
            authority="PRESENTATION_ONLY_NOT_ANALYTICAL",
            limitations=["MACRO_SYNC_FOREIGN_FLOW_IS_NOT_QUALIFIED_DNSE_FLOW"],
        )
    else:
        rows["FOREIGN_FLOW"] = _unknown("FOREIGN_FLOW", "NO_EXPLICIT_PRESENTATION_ARTIFACT")
    return rows


def _sector_dimensions(sector: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not _identity_ok(sector, SECTOR_CONTRACT):
        return {axis: _unknown(axis, "NO_EXPLICIT_SECTOR_LEADERSHIP_ARTIFACT_IDENTITY") for axis in SECTOR_AXES}
    groups = ((sector.get("groups") or {}).get("records") or {}) if isinstance(sector.get("groups"), Mapping) else {}
    leading = []
    weakening = []
    for key, row in sorted(groups.items()):
        if not isinstance(row, Mapping):
            continue
        item = {"group_key": key, "group_identity": row.get("group_identity"), "leadership_state": row.get("leadership_state")}
        if row.get("leadership_state") == "LEADING" and row.get("status") == "AVAILABLE":
            leading.append(item)
        if row.get("leadership_state") == "WEAKENING":
            weakening.append(item)
    evidence = [{"artifact_identity": sector.get("artifact_identity"), "session": sector.get("session")}]
    freshness = {"status": "CURRENT_CROSS_SECTIONAL_ONLY_NOT_HISTORICAL_PIT", "session": sector.get("session")}
    market_state = str((sector.get("market") or {}).get("current_breadth_state") or "UNKNOWN")
    return {
        "SECTOR_RELATIVE_STRENGTH": _dimension(
            axis="SECTOR_RELATIVE_STRENGTH",
            state="LEADING_GROUPS_PRESENT" if leading else "NO_LEADING_GROUP",
            evidence=evidence + leading,
            freshness=freshness,
            authority="CURRENT_CROSS_SECTIONAL_DESCRIPTIVE",
            limitations=["RELATIVE_STRENGTH_IS_WITHIN_SESSION_PERCENTILE_NOT_A_RETURN_FORECAST"],
        ),
        "SECTOR_PARTICIPATION": _dimension(
            axis="SECTOR_PARTICIPATION",
            state=market_state,
            evidence=evidence,
            freshness=freshness,
            authority="CURRENT_SESSION_DESCRIPTIVE",
            limitations=["SECTOR_PARTICIPATION_USES_THE_EXISTING_EXACT_SESSION_BREADTH_STATE"],
        ),
        "LEADERSHIP_PERSISTENCE": _unknown("LEADERSHIP_PERSISTENCE", "IMPROVING_AND_LAGGING_REQUIRE_A_PRIOR_COMPARABLE_SESSION_AND_ARE_NOT_EMITTED"),
        "LEADERSHIP_DETERIORATION": _dimension(
            axis="LEADERSHIP_DETERIORATION",
            state="WEAKENING" if weakening else "NO_WEAKENING_GROUP_OBSERVED",
            evidence=evidence + weakening,
            freshness=freshness,
            authority="CURRENT_CROSS_SECTIONAL_DESCRIPTIVE",
            limitations=["ONE_SESSION_CANNOT_PROVE_A_ROTATION_PATH"],
        ),
    }


def _presentation_quarantine(presentation: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not _identity_ok(presentation, PRESENTATION_CONTRACT):
        return []
    indicators = presentation.get("indicators") or {}
    quarantined = []
    if isinstance(indicators, Mapping):
        for key, row in sorted(indicators.items()):
            if not isinstance(row, Mapping):
                continue
            authority = str(row.get("source_authority") or "UNKNOWN_SOURCE_AUTHORITY")
            if authority in NON_OFFICIAL_AUTHORITIES or authority == "OFFICIAL_MULTILATERAL_SOURCE":
                quarantined.append({
                    "indicator": key,
                    "source": row.get("source"),
                    "source_authority": authority,
                    "promoted_to_regime_axis": False,
                    "reason": "PRESENTATION_AVAILABILITY_IS_NOT_SOURCE_AUTHORITY",
                })
    return quarantined


def _conflicts(macro_rows: Mapping[str, Mapping[str, Any]], market_rows: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    macro_states = {axis: row["state"] for axis, row in macro_rows.items()}
    market_states = {axis: row["state"] for axis, row in market_rows.items() if axis in {"MARKET_BREADTH", "PARTICIPATION", "EXACT_SESSION_BREADTH"}}
    supportive_market = [axis for axis, state in market_states.items() if state in SUPPORTIVE_MARKET]
    restrictive_market = [axis for axis, state in market_states.items() if state in RESTRICTIVE_MARKET]
    supportive_macro = [axis for axis, state in macro_states.items() if state in SUPPORTIVE_MACRO]
    restrictive_macro = [axis for axis, state in macro_states.items() if state in RESTRICTIVE_MACRO]
    conflicts = []
    if supportive_market and restrictive_macro:
        conflicts.append({
            "kind": "MACRO_MARKET_CONFLICT",
            "macro_axes": restrictive_macro,
            "market_axes": supportive_market,
            "winner": None,
        })
    if restrictive_market and supportive_macro:
        conflicts.append({
            "kind": "MACRO_MARKET_CONFLICT",
            "macro_axes": supportive_macro,
            "market_axes": restrictive_market,
            "winner": None,
        })
    breadth = market_rows.get("MARKET_BREADTH", {}).get("state")
    exact = market_rows.get("EXACT_SESSION_BREADTH", {}).get("state")
    if breadth in SUPPORTIVE_MARKET and exact in RESTRICTIVE_MARKET or breadth in RESTRICTIVE_MARKET and exact in SUPPORTIVE_MARKET:
        conflicts.append({
            "kind": "BREADTH_IDENTITY_CONFLICT",
            "cohort_breadth": breadth,
            "exact_session_breadth": exact,
            "winner": None,
        })
    return conflicts


def _coverage(dimensions: Mapping[str, Mapping[str, Any]], sector: Mapping[str, Any] | None) -> dict[str, Any]:
    macro = [dimensions[axis] for axis in MACRO_AXES]
    qualified = [row["axis"] for row in macro if row["state"] != "UNKNOWN"]
    unavailable = [row["axis"] for row in macro if row["state"] == "UNKNOWN"]
    official = [row["axis"] for row in macro if row["state"] != "UNKNOWN" and str(row["authority"]).startswith("OFFICIAL")]
    pit = [
        row["axis"] for row in macro
        if row["freshness"].get("historical_pit") == "DATE_LEVEL_QUALIFIED_AFTER_PUBLICATION_DATE"
    ]
    current_only = [axis for axis in qualified if axis not in pit]
    ticker_count = 0
    if isinstance(sector, Mapping):
        ticker_count = int(((sector.get("coverage") or {}).get("ticker_sector_context_available_count")) or 0)
    return {
        "qualified_macro_dimensions": qualified,
        "unavailable_macro_dimensions": unavailable,
        "official_macro_dimensions": official,
        "nonofficial_dimensions_promoted": [],
        "market_regime_bound": dimensions["MARKET_BREADTH"]["state"] != "UNKNOWN",
        "breadth_bound": dimensions["MARKET_BREADTH"]["state"] != "UNKNOWN" or dimensions.get("EXACT_SESSION_BREADTH", {}).get("state") not in (None, "UNKNOWN"),
        "sector_leadership_bound": dimensions["SECTOR_RELATIVE_STRENGTH"]["state"] != "UNKNOWN",
        "tickers_with_sector_context": ticker_count,
        "historical_pit_macro_dimensions": pit,
        "current_research_only_macro_dimensions": current_only,
    }


def build_context(
    *,
    macro: Mapping[str, Any] | None = None,
    breadth: Mapping[str, Any] | None = None,
    sector_leadership: Mapping[str, Any] | None = None,
    presentation: Mapping[str, Any] | None = None,
    session: str | None = None,
    knowledge_available_at: str | None = None,
    cutoff: str | None = None,
) -> dict[str, Any]:
    """Bind explicit upstream identities. There is no latest-file lookup."""
    _reject_forbidden({"macro": macro, "breadth": breadth, "sector_leadership": sector_leadership, "presentation": presentation}, where="INPUT")
    knowledge_available_at = knowledge_available_at or cutoff or (macro or {}).get("retrieved_at") or datetime.now(UTC).isoformat()
    if session and session != "SCRATCH_CURRENT" and not _closed_session(session):
        # Explicit market artifacts must be from the receiving session and content verified.
        for name, supplied, field in (("breadth", breadth, "research_session"), ("sector", sector_leadership, "session")):
            if supplied is not None:
                if supplied.get(field) != session:
                    raise ValueError("REGIME_CONTEXT_SESSION_MISMATCH:" + name)
                payload = {k: v for k, v in supplied.items() if k not in {"artifact_sha256", "artifact_identity"}}
                if supplied.get("artifact_sha256") != stable_id(payload):
                    raise ValueError("REGIME_UPSTREAM_IDENTITY_INVALID:" + name)
    if _closed_session(session):
        macro_rows = _macro_dimensions(None, session)
        for row in macro_rows.values():
            row["limitations"] = ["COMPLETED_OCTOBER_7_SESSION_NOT_REWRITTEN"]
    else:
        macro_rows = _macro_dimensions(macro, session, cutoff)
    market_rows = {} if _closed_session(session) else _market_dimensions(breadth, sector_leadership, presentation)
    if _closed_session(session):
        market_rows = {axis: _unknown(axis, "COMPLETED_OCTOBER_7_SESSION_NOT_REWRITTEN") for axis in (*MARKET_AXES, "EXACT_SESSION_BREADTH")}
        sector_rows = {axis: _unknown(axis, "COMPLETED_OCTOBER_7_SESSION_NOT_REWRITTEN") for axis in SECTOR_AXES}
    else:
        sector_rows = _sector_dimensions(sector_leadership)
    dimensions = {**macro_rows, **market_rows, **sector_rows}
    regime = (macro or {}).get("macro_regime") if _identity_ok(macro, MACRO_CONTRACT) and not _closed_session(session) else None
    if session and session != "SCRATCH_CURRENT" and _identity_ok(macro, MACRO_CONTRACT) and not _closed_session(session):
        bound = session_context(macro, session, cutoff=cutoff)
        if bound.get("status") != "AVAILABLE":
            regime = None
        else:
            regime = bound.get("macro_regime")
    conflicts = [] if _closed_session(session) else _conflicts(macro_rows, market_rows)
    artifact = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "milestone_id": MILESTONE_ID,
        "disposition": DISPOSITION,
        "knowledge_available_at": knowledge_available_at,
        "session": session,
        "cutoff": cutoff,
        "temporal": {
            "knowledge_available_at": knowledge_available_at,
            "october_7_records_changed": False,
            "eligible_for_completed_october_7": False,
            "session_bind": "EXCLUDED_COMPLETED_OCTOBER_7" if _closed_session(session) else "SCRATCH_OR_LATER_SESSION",
        },
        "upstream_identities": {
            "macro": None if not _identity_ok(macro, MACRO_CONTRACT) else macro.get("artifact_identity"),
            "breadth": None if not _identity_ok(breadth, BREADTH_CONTRACT) else breadth.get("artifact_identity"),
            "sector_leadership": None if not _identity_ok(sector_leadership, SECTOR_CONTRACT) else sector_leadership.get("artifact_identity"),
            "presentation": None if not _identity_ok(presentation, PRESENTATION_CONTRACT) else presentation.get("artifact_identity"),
        },
        "macro_regime": {
            "state": (regime or {}).get("state") if isinstance(regime, Mapping) else "UNKNOWN",
            "supporting_axes": list((regime or {}).get("supporting_axes") or []) if isinstance(regime, Mapping) else [],
            "restrictive_axes": list((regime or {}).get("restrictive_axes") or []) if isinstance(regime, Mapping) else [],
            "unavailable_axes": list((regime or {}).get("unavailable_axes") or []) if isinstance(regime, Mapping) else list(MACRO_AXES),
            "meaning": "Descriptive context. Axes stay independent. No equity forecast.",
        },
        "dimensions": dimensions,
        "conflicts": conflicts,
        "macro_sector_relationship": "RELATIONSHIP_NOT_FORMALIZED",
        "presentation_quarantine": _presentation_quarantine(presentation),
        "domestic_macro_evidence": {
            "selected_dimensions": list(DOMESTIC_SELECTION),
            "http_requests": 0,
            "new_retained_bytes": 0,
            "outcome": "UNKNOWN_NO_RETAINED_FIRST_PARTY_METRIC",
            "not_promoted": ["Vietcombank quote", "SJC quote", "Yahoo Finance", "World Bank annual series"],
        },
        "coverage": _coverage(dimensions, None if _closed_session(session) else sector_leadership),
        "authority_boundary": {
            "source_authority_separate_from_presentation_availability": True,
            "historical_pit": "NOT_PROMOTED_FROM_LATEST_VINTAGE",
            "forecast_probability_target_recommendation_sizing_execution": "NOT_EMITTED",
            "company_economics": "NOT_MODIFIED",
            "tactical_posture": "NOT_MODIFIED",
            "october_7_records": "NOT_REWRITTEN",
        },
        "is_actionable": False,
    }
    _reject_forbidden(artifact, where="CONTEXT")
    artifact.update({"artifact_sha256": stable_id(artifact), "artifact_identity": "macro_market_regime_decision_context:" + stable_id(artifact)})
    # stable_id of artifact includes nothing circular if we hash before inserting identity.
    payload = {key: value for key, value in artifact.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = stable_id(payload)
    artifact["artifact_sha256"] = digest
    artifact["artifact_identity"] = "macro_market_regime_decision_context:" + digest
    return artifact


def validate_context(context: Mapping[str, Any], session: str | None) -> None:
    """Validate the receiving session and immutable content before delivery."""
    from current_macro_regime import _knowledge_timestamp
    if context.get("contract_version") != CONTRACT_VERSION or context.get("session") != session:
        raise ValueError("REGIME_CONTEXT_SESSION_MISMATCH")
    payload = {k: v for k, v in context.items() if k not in {"artifact_sha256", "artifact_identity"}}
    digest = stable_id(payload)
    if context.get("artifact_sha256") != digest or context.get("artifact_identity") != "macro_market_regime_decision_context:" + digest:
        raise ValueError("REGIME_CONTEXT_IDENTITY_INVALID")
    if session != "SCRATCH_CURRENT":
        cutoff = _knowledge_timestamp(context.get("cutoff"))
        known = _knowledge_timestamp(context.get("knowledge_available_at"))
        if cutoff is None or known is None or known > cutoff:
            raise ValueError("REGIME_CONTEXT_KNOWLEDGE_AFTER_CUTOFF_OR_MISSING")
        if cutoff.astimezone(timezone(timedelta(hours=7))).date().isoformat() != session:
            raise ValueError("REGIME_CONTEXT_CUTOFF_SESSION_MISMATCH")


def stock_relationship(context: Mapping[str, Any], ticker: str, ticker_row: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Expose sector and macro context beside company economics. Do not merge them."""
    leadership = None
    group = None
    if isinstance(ticker_row, Mapping):
        slot = ticker_row.get("sector_leadership_context")
        if isinstance(slot, Mapping):
            leadership = slot.get("leadership_state")
            group = slot.get("group_key")
    row = {
        "ticker": ticker,
        "sector_group": group,
        "sector_leadership_state": leadership or "UNKNOWN",
        "macro_regime_state": (context.get("macro_regime") or {}).get("state"),
        "macro_axis_states": {axis: (context.get("dimensions") or {}).get(axis, {}).get("state") for axis in MACRO_AXES},
        "relationship": "RELATIONSHIP_NOT_FORMALIZED",
        "company_economics": "NOT_MODIFIED",
    }
    _reject_forbidden(row, where="STOCK_RELATIONSHIP")
    return row


def packet_section_overlay(context: Mapping[str, Any], *, decision_session: str | None = None) -> dict[str, Any]:
    """Fields for the existing market, uncertainty, and counter-thesis sections."""
    if _closed_session(decision_session) or context.get("temporal", {}).get("session_bind") == "EXCLUDED_COMPLETED_OCTOBER_7":
        return {"bind_status": "EXCLUDED_COMPLETED_OCTOBER_7", "market": {}, "uncertainty": {}, "counter_thesis": {}}
    validate_context(context, decision_session)
    dimensions = context.get("dimensions") or {}
    missing = [axis for axis, row in dimensions.items() if isinstance(row, Mapping) and row.get("state") == "UNKNOWN"]
    leading = [
        item for item in (dimensions.get("SECTOR_RELATIVE_STRENGTH") or {}).get("evidence") or []
        if isinstance(item, Mapping) and item.get("leadership_state") == "LEADING"
    ]
    overlay = {
        "bind_status": "BOUND",
        "market": {
            "regime_context_identity": context.get("artifact_identity"),
            "macro_regime": (context.get("macro_regime") or {}).get("state"),
            "macro_axes": {axis: (dimensions.get(axis) or {}).get("state") for axis in MACRO_AXES},
            "market_breadth_regime": (dimensions.get("MARKET_BREADTH") or {}).get("state"),
            "exact_session_breadth": (dimensions.get("EXACT_SESSION_BREADTH") or {}).get("state"),
            "participation": (dimensions.get("PARTICIPATION") or {}).get("state"),
            "liquidity_risk_appetite_state": (dimensions.get("LIQUIDITY_RISK_APPETITE") or {}).get("state"),
            "sector_leadership": [item.get("group_identity") for item in leading],
            "macro_sector_relationship": context.get("macro_sector_relationship"),
            "upstream_identities": copy.deepcopy(context.get("upstream_identities")),
            "regime_evidence": copy.deepcopy(context.get("dimensions")),
            "knowledge_available_at": context.get("knowledge_available_at"),
            "cutoff": context.get("cutoff"),
        },
        "uncertainty": {
            "missing_dimensions": {"claim": {"present": True, "warning": True}, "value": missing},
        },
        "counter_thesis": {
            "usd_pressure_state": (dimensions.get("USD_PRESSURE") or {}).get("state"),
            "domestic_liquidity_state": (dimensions.get("DOMESTIC_LIQUIDITY") or {}).get("state"),
            "breadth_state": (dimensions.get("MARKET_BREADTH") or {}).get("state"),
            "leadership_deterioration_state": (dimensions.get("LEADERSHIP_DETERIORATION") or {}).get("state"),
            "global_rates_state": (dimensions.get("GLOBAL_RATES") or {}).get("state"),
            "conflicts": {"claim": {"conflict": True, "present": True}, "value": context.get("conflicts") or []} if context.get("conflicts") else [],
        },
    }
    _reject_forbidden(overlay, where="PACKET_OVERLAY")
    return overlay


def decision_answers(context: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic answers. No capital recommendation."""
    dimensions = context.get("dimensions") or {}
    leading = [
        item.get("group_identity")
        for item in (dimensions.get("SECTOR_RELATIVE_STRENGTH") or {}).get("evidence") or []
        if isinstance(item, Mapping) and item.get("leadership_state") == "LEADING"
    ]
    supportive = [axis for axis in MACRO_AXES if (dimensions.get(axis) or {}).get("state") in SUPPORTIVE_MACRO | {"STABLE"}]
    pressure = [axis for axis in MACRO_AXES if (dimensions.get(axis) or {}).get("state") in RESTRICTIVE_MACRO]
    unknown = [axis for axis, row in dimensions.items() if isinstance(row, Mapping) and row.get("state") == "UNKNOWN"]
    breadth = (dimensions.get("EXACT_SESSION_BREADTH") or {}).get("state") or (dimensions.get("MARKET_BREADTH") or {}).get("state")
    participation = (dimensions.get("PARTICIPATION") or {}).get("state")
    if breadth in SUPPORTIVE_MARKET:
        breadth_direction = "BROAD_ON_THIS_SESSION"
    elif breadth in RESTRICTIVE_MARKET:
        breadth_direction = "NARROW_OR_DETERIORATING_ON_THIS_SESSION"
    else:
        breadth_direction = "UNKNOWN_VERSUS_PRIOR_SESSION"
    return {
        "macro_backdrop": (context.get("macro_regime") or {}).get("state"),
        "axes_supporting_or_pressuring": {"supportive_or_stable": supportive, "pressure": pressure},
        "unknown_dimensions": unknown,
        "breadth_versus_prior_session": breadth_direction,
        "leadership_breadth": participation or breadth,
        "leading_sectors": leading,
        "macro_market_conflict": context.get("conflicts") or [],
        "evidence": {
            axis: (dimensions.get(axis) or {}).get("evidence")
            for axis in list(MACRO_AXES) + ["MARKET_BREADTH", "PARTICIPATION", "SECTOR_RELATIVE_STRENGTH"]
        },
        "authority_split": {
            "historical_pit_macro_dimensions": context.get("coverage", {}).get("historical_pit_macro_dimensions"),
            "current_research_only_macro_dimensions": context.get("coverage", {}).get("current_research_only_macro_dimensions"),
            "market_and_sector": "CURRENT_RESEARCH_OR_CURRENT_SESSION_DESCRIPTIVE",
        },
        "capital_recommendation": None,
    }


def scratch_acceptance() -> dict[str, Any]:
    """One explicit scratch context. Not an October 8 session artifact."""
    from current_macro_regime import build as build_macro

    def row(identifier: str, value: float | None, previous: float | None, **extra: Any) -> dict[str, Any]:
        base = {
            "indicator_id": identifier,
            "country_or_region": "fixture",
            "category": "fixture",
            "value": value,
            "unit": "fixture",
            "observation_date": "2026-09-30",
            "released_at": extra.get("released_at"),
            "source": extra.get("source", "official"),
            "source_identity": extra.get("source_identity", identifier),
            "url": "https://official.example/" + identifier,
            "retrieved_at": KNOWLEDGE_AVAILABLE_AT,
            "freshness": {"status": extra.get("freshness", "CURRENT_RESEARCH_NOT_HISTORICAL_PIT")},
            "revision_state": "SOURCE_LATEST_VINTAGE_RELEASE_DATE_NOT_RETAINED",
            "authority": extra.get("authority", "OFFICIAL_PUBLIC_SOURCE"),
            "status": "AVAILABLE" if value is not None else "UNAVAILABLE",
            "limitations": list(extra.get("limitations") or []),
            "previous_observation_date": "2026-09-29",
            "previous_value": previous,
            "raw_payload_sha256": "scratch",
        }
        return base

    observations = [
        row("us_fed_funds", 4.0, 4.1),
        row("us_cpi", 300.0, 299.0),
        row("us_treasury_2y", 4.0, 3.9),
        row("us_treasury_10y", 4.0, 4.0),
        row("usd_emerging_markets", 110.0, 112.0),
        row("wti_oil", 80.0, 78.0),
        row("vn_cpi_yoy", 3.2, 3.2, released_at="2026-10-06", freshness="DATE_LEVEL_PUBLICATION", limitations=["Publication date is date-level. The regime artifact does not promote historical PIT."]),
    ]
    for identifier in ("vn_policy_rate", "vn_usd_vnd", "vn_credit_growth", "vn_system_liquidity", "vn_government_bond_yield"):
        observations.append(row(identifier, None, None, authority="OFFICIAL_SOURCE_ROUTE_ATTEMPTED", limitations=["NO_RETAINED_FIRST_PARTY_EXPLICIT_METRIC"]))
    macro = build_macro(observations=observations, raw_sources=[{"source_identity": "scratch"}], retrieved_at=KNOWLEDGE_AVAILABLE_AT)
    breadth = {
        "contract_version": BREADTH_CONTRACT,
        "artifact_identity": "market_regime_breadth_context:scratch",
        "research_session": "SCRATCH_CURRENT",
        "descriptors": [
            {"descriptor": "BREADTH_POSITIVE", "rule_identity": BREADTH_CONTRACT},
            {"descriptor": "MOMENTUM_BREADTH_POSITIVE", "rule_identity": BREADTH_CONTRACT},
            {"descriptor": "EMPIRICAL_COHORT_TREND_PARTICIPATION_BROAD", "rule_identity": BREADTH_CONTRACT},
        ],
        "breadth": {"volatility": {"descriptor": "CROSS_SECTIONAL_VOLATILITY_PARTIAL", "authority_tier": "SHADOW_ONLY"}},
        "authority_boundary": {"not_bull_bear_call_forecast_or_timing": True},
    }
    sector = {
        "contract_version": SECTOR_CONTRACT,
        "artifact_identity": "current_market_sector_leadership_context:scratch",
        "session": "SCRATCH_CURRENT",
        "market": {"current_breadth_state": "BROAD_PARTICIPATION", "warnings": ["NO_PRIOR_SESSION_COMPARISON_SO_IMPROVING_BREADTH_IS_NOT_EMITTED"]},
        "groups": {"records": {
            "QUALIFIED|industry|Banks": {"group_identity": "Banks", "leadership_state": "LEADING", "status": "AVAILABLE"},
            "QUALIFIED|industry|Real estate": {"group_identity": "Real estate", "leadership_state": "MIXED", "status": "AVAILABLE"},
        }},
        "coverage": {"ticker_sector_context_available_count": 2, "official_universe_count": 4},
        "ticker_contexts": {"ACB": {"sector_leadership_context": {"status": "AVAILABLE", "group_key": "QUALIFIED|industry|Banks", "leadership_state": "LEADING"}}},
        "authority_boundary": {"current_research_only": True, "is_actionable": False},
    }
    presentation = {
        "contract_version": PRESENTATION_CONTRACT,
        "artifact_identity": "macro_presentation_context:scratch",
        "indicators": {
            "usd_vnd_vcb": {"source": "Vietcombank", "source_authority": "FIRST_PARTY_QUOTE_UNOFFICIAL_TRANSPORT", "value": 25450},
            "vnindex_yahoo": {"source": "Yahoo Finance", "source_authority": "UNOFFICIAL_MARKET_DATA_SOURCE", "value": 1200},
        },
        "foreign_flow": {"status": "unavailable", "reason": "not_in_snapshot", "source": "macro_sync_runtime_snapshot"},
    }
    context = build_context(macro=macro, breadth=breadth, sector_leadership=sector, presentation=presentation, session="SCRATCH_CURRENT", knowledge_available_at=KNOWLEDGE_AVAILABLE_AT)
    return {
        "context": context,
        "answers": decision_answers(context),
        "stock_relationship": stock_relationship(context, "ACB", sector["ticker_contexts"]["ACB"]),
        "scratch": True,
        "october_8_session_artifact": False,
    }


def milestone_report() -> dict[str, Any]:
    scratch = scratch_acceptance()
    context = scratch["context"]
    return {
        "milestone_id": MILESTONE_ID,
        "disposition": DISPOSITION,
        "knowledge_available_at": KNOWLEDGE_AVAILABLE_AT,
        "october_7_records_changed": False,
        "october_8_session_artifact": False,
        "network": context["domestic_macro_evidence"],
        "coverage": context["coverage"],
        "macro_regime": context["macro_regime"],
        "answers": scratch["answers"],
        "conflicts": context["conflicts"],
        "macro_sector_relationship": context["macro_sector_relationship"],
        "upstream_identities": context["upstream_identities"],
        "ui_effect": "NONE",
        "successor_started": False,
    }
