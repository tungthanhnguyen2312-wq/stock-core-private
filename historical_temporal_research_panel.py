"""Rebuildable historical research memory over retained post-close projections.

The panel is research memory. It is not PIT backtest authority and it does not
promote adjusted history to RAW_AS_TRADED. Source evidence is read and never
rewritten. Only the two small per-session projections are opened:

- session_handoff_bundle.json
- opportunity_research_bundle.json

Enrichment products, T0 bodies, and velocity files stay unread.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

CONTRACT_VERSION = "historical_temporal_research_panel/v1"
PIT_AUTHORITATIVE = "PIT_AUTHORITATIVE"
RECONSTRUCTED_RESEARCH = "RECONSTRUCTED_RESEARCH"
EXPLANATORY_ONLY = "EXPLANATORY_ONLY"
UNKNOWN = "UNKNOWN"
TIERS = (PIT_AUTHORITATIVE, RECONSTRUCTED_RESEARCH, EXPLANATORY_ONLY, UNKNOWN)

IMPLEMENTED_OUTCOME_HORIZONS = (1, 3, 5, 10, 20)
POPULATIONS = (
    "PROSPECTIVE_GENUINE",
    "PIT_AUTHORITATIVE",
    "RECONSTRUCTED_RESEARCH",
    "EXPLANATORY_ONLY",
)
AFFECTED_CALCULATION_FIELDS = (
    "price_basis",
    "share_count",
    "eps_denominator",
    "valuation",
    "returns",
)
HANDOFF_NAME = "session_handoff_bundle.json"
OPPORTUNITY_NAME = "opportunity_research_bundle.json"
STORAGE_CHOICE = "JSON_PROJECTION"
STORAGE_RATIONALE = (
    "This slice is a few thousand small rows projected from the retained "
    "handoff and opportunity files. Parquet and DuckDB are not required."
)


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _field(value: Any, tier: str, status: str, **extra: Any) -> dict[str, Any]:
    row = {"value": value, "tier": tier, "status": status}
    row.update(extra)
    return row


def _missing(tier: str = UNKNOWN, status: str = "MISSING") -> dict[str, Any]:
    return _field(None, tier, status)


def classify_tier(requested: Any, qualification: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Accept a tier only when the supplied qualification supports it.

    PIT requires an explicit qualification id plus separate knowledge and event
    dates. Adjusted or restated history stays reconstructed. RAW_AS_TRADED is
    never emitted.
    """
    qual = _mapping(qualification)
    if requested == PIT_AUTHORITATIVE:
        if qual.get("adjusted_retrospective") or qual.get("restated_after_event"):
            return {"tier": RECONSTRUCTED_RESEARCH, "reason": "RETROSPECTIVE_ADJUSTMENT_NOT_PIT", "raw_as_traded": False}
        required = ("qualification_id", "knowledge_date", "event_date")
        if not all(qual.get(key) for key in required):
            return {"tier": UNKNOWN, "reason": "PIT_QUALIFICATION_ABSENT", "raw_as_traded": False}
        same_clock = qual.get("knowledge_date") == qual.get("event_date")
        if same_clock and qual.get("dates_intentionally_equal") is not True:
            return {"tier": UNKNOWN, "reason": "KNOWLEDGE_AND_EVENT_TIME_NOT_SEPARATED", "raw_as_traded": False}
        return {"tier": PIT_AUTHORITATIVE, "reason": "PIT_QUALIFICATION_PRESENT", "raw_as_traded": False}
    if requested in TIERS:
        return {"tier": requested, "reason": "REQUESTED_TIER", "raw_as_traded": False}
    return {"tier": UNKNOWN, "reason": "TIER_UNRECOGNIZED", "raw_as_traded": False}


def project_outcome(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Represent an outcome only when it was supplied and qualified.

    Horizons outside the implemented prospective set (1, 3, 5, 10, 20) are
    refused. T60 is not an implemented forward-feedback horizon.
    """
    if not isinstance(raw, Mapping) or not raw:
        return _missing(UNKNOWN, "NOT_OBSERVED")
    horizon = raw.get("horizon_sessions")
    if horizon not in IMPLEMENTED_OUTCOME_HORIZONS:
        return _field(None, UNKNOWN, "HORIZON_NOT_IMPLEMENTED", refused_horizon=horizon)
    if raw.get("observed_qualified") is not True:
        return _missing(UNKNOWN, "NOT_OBSERVED")
    population = raw.get("population")
    if population not in POPULATIONS:
        return _field(None, UNKNOWN, "POPULATION_UNCLASSIFIED", refused_population=population)
    tier = classify_tier(raw.get("tier") or RECONSTRUCTED_RESEARCH, raw.get("qualification"))
    return _field(
        {"horizon_sessions": horizon, "forward_return": raw.get("forward_return"), "population": population},
        tier["tier"],
        "OBSERVED",
        population=population,
    )


def apply_corporate_action_boundary(fields: Mapping[str, Any], boundary: Mapping[str, Any] | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Fail closed only for calculations the boundary names.

    A request to drop the ticker is ignored. Unaffected fields stay as supplied.
    """
    projected = {key: dict(value) if isinstance(value, Mapping) else value for key, value in fields.items()}
    if not isinstance(boundary, Mapping) or not boundary:
        return projected, []
    named = boundary.get("affected_fields")
    affected = AFFECTED_CALCULATION_FIELDS if named is None else tuple(named)
    reason = str(boundary.get("reason") or "CORPORATE_ACTION_BOUNDARY")
    closures: list[dict[str, Any]] = []
    for name in affected:
        if name not in AFFECTED_CALCULATION_FIELDS or name not in projected:
            continue
        current = dict(projected[name]) if isinstance(projected[name], Mapping) else _missing()
        current["value"] = None
        current["status"] = "INCOMPARABLE"
        current["reason"] = reason
        projected[name] = current
        closures.append({"field": name, "status": "INCOMPARABLE", "reason": reason})
    if boundary.get("drop_ticker") is True:
        closures.append({"field": "ticker", "status": "DROP_REFUSED", "reason": "TICKER_RETAINED"})
    return projected, closures


def _market_fields(market: Mapping[str, Any]) -> dict[str, Any]:
    breadth = market.get("breadth") if isinstance(market.get("breadth"), Mapping) else None
    regime = market.get("market_regime")
    return {
        "market_regime": _field(regime, RECONSTRUCTED_RESEARCH, "PRESENT") if regime else _missing(),
        "breadth": _field(dict(breadth), RECONSTRUCTED_RESEARCH, "PRESENT") if breadth else _missing(),
        "sector_regime": _missing() if market.get("sector_regime") is None else _field(market.get("sector_regime"), RECONSTRUCTED_RESEARCH, "PRESENT"),
        "leadership_concentration": _missing() if market.get("leadership_concentration") is None else _field(market.get("leadership_concentration"), RECONSTRUCTED_RESEARCH, "PRESENT"),
        "risk_appetite": _missing() if market.get("risk_appetite") is None else _field(market.get("risk_appetite"), RECONSTRUCTED_RESEARCH, "PRESENT"),
    }


def _base_fields(observation: Mapping[str, Any], tier: str) -> dict[str, Any]:
    market = observation.get("market") if isinstance(observation.get("market"), Mapping) else {}
    fields = _market_fields(market)
    tactical = observation.get("tactical_state")
    fields.update({
        "ohlcv": _missing(),
        "price_basis": _missing(),
        "technical_structure": _missing(),
        "participation": _missing(),
        "flow": _missing(),
        "relative_strength": _missing(),
        "financial_period": _missing(),
        "source_knowledge_date": _field(observation.get("knowledge_date"), tier, "PRESENT") if observation.get("knowledge_date") else _missing(),
        "evidence_tier": _field(tier, tier, "PRESENT"),
        "share_count": _missing(),
        "eps_denominator": _missing(),
        "valuation": _missing(),
        "valuation_method": _missing(),
        "valuation_exactness": _missing(),
        "corporate_event": _missing(),
        "corporate_actor": _missing(),
        "announcement_date": _field(observation.get("announcement_date"), tier, "PRESENT") if observation.get("announcement_date") else _missing(),
        "event_date": _field(observation.get("event_date"), tier, "PRESENT") if observation.get("event_date") else _missing(),
        "execution_state": _missing(),
        "tactical_state": _field(tactical, tier, "PRESENT") if tactical else _missing(),
        "strategy_state": _missing(),
        "trigger": _missing(),
        "confirmation": _missing(),
        "invalidation": _missing(),
        "uncertainty": _field("COHORT_MEMBERSHIP_ONLY", EXPLANATORY_ONLY, "PRESENT"),
        "decision_identity": _field(observation.get("source_identity"), EXPLANATORY_ONLY, "POINTER") if observation.get("source_identity") else _missing(EXPLANATORY_ONLY, "MISSING"),
        "returns": _missing(),
        "outcome": project_outcome(observation.get("outcome") if isinstance(observation.get("outcome"), Mapping) else None),
    })
    pointer = observation.get("prospective_snapshot_identity")
    if pointer:
        fields["decision_identity"] = _field(pointer, EXPLANATORY_ONLY, "POINTER")
    return fields


def build_row(observation: Mapping[str, Any]) -> dict[str, Any]:
    classified = classify_tier(observation.get("semantic_tier") or RECONSTRUCTED_RESEARCH, observation.get("qualification"))
    fields = _base_fields(observation, classified["tier"])
    fields, closures = apply_corporate_action_boundary(
        fields, observation.get("corporate_action_boundary") if isinstance(observation.get("corporate_action_boundary"), Mapping) else None,
    )
    identity_material = {
        "contract": CONTRACT_VERSION,
        "session": observation.get("session"),
        "ticker": observation.get("ticker"),
        "tactical_state": observation.get("tactical_state"),
        "source_identity": observation.get("source_identity"),
        "semantic_tier": classified["tier"],
        "tier_reason": classified["reason"],
        "closures": [item["field"] for item in closures],
        "fields": {name: {"status": item.get("status"), "tier": item.get("tier"), "value": item.get("value")} for name, item in fields.items()},
    }
    row_hash = _sha(identity_material)
    return {
        "row_identity": "historical_temporal_research_row:" + row_hash,
        "session": observation.get("session"),
        "ticker": observation.get("ticker"),
        "semantic_tier": classified["tier"],
        "tier_reason": classified["reason"],
        "source_class": observation.get("source_class") or "CANONICAL_POST_CLOSE_OPPORTUNITY_COHORT",
        "authority_promoted": False,
        "raw_as_traded": False,
        "fields": fields,
        "calculation_closures": closures,
    }


def _focus_coverage(rows: list[dict[str, Any]], focus_tickers: tuple[str, ...]) -> dict[str, Any]:
    coverage: dict[str, Any] = {}
    for ticker in focus_tickers:
        matched = [row for row in rows if row.get("ticker") == ticker]
        sessions = sorted({str(row.get("session")) for row in matched})
        coverage[ticker] = {
            "row_count": len(matched),
            "sessions": sessions,
            "status": "PRESENT" if matched else "NO_RETAINED_COHORT_EVIDENCE",
        }
    return coverage


def build_panel(observations: list[Mapping[str, Any]], *, focus_tickers: tuple[str, ...] = (), session_index: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    rows = [build_row(observation) for observation in observations]
    rows.sort(key=lambda row: (str(row.get("session")), str(row.get("ticker")), str(row.get("fields", {}).get("tactical_state", {}).get("value"))))
    identities = [row["row_identity"] for row in rows]
    tier_counts: dict[str, int] = {tier: 0 for tier in TIERS}
    for row in rows:
        tier_counts[row["semantic_tier"]] = tier_counts.get(row["semantic_tier"], 0) + 1
    body = {
        "contract_version": CONTRACT_VERSION,
        "storage_choice": STORAGE_CHOICE,
        "storage_rationale": STORAGE_RATIONALE,
        "authority_promoted": False,
        "raw_as_traded_promoted": False,
        "pit_backtest_authority": False,
        "row_count": len(rows),
        "row_identities": identities,
        "tier_counts": tier_counts,
        "session_index": [dict(item) for item in session_index] if session_index else [],
        "focus_coverage": _focus_coverage(rows, focus_tickers),
        "rows": rows,
    }
    panel_hash = _sha({"contract_version": CONTRACT_VERSION, "row_identities": identities})
    body["panel_identity"] = "historical_temporal_research_panel:" + panel_hash
    body["storage_footprint"] = {
        "persisted": False,
        "row_count": len(rows),
        "representation": "in_memory_json_projection",
        "source_policy": "handoff_and_opportunity_bundles_only",
        "excluded_families": [
            "integrated_investment_decision_product.json",
            "historical_context.json",
            "velocity",
            "t0_snapshot_body",
        ],
    }
    return body


def _session_name(name: str) -> bool:
    parts = name.split("-")
    return len(parts) == 3 and all(part.isdigit() for part in parts) and len(parts[0]) == 4


def _read_json(path: Path) -> tuple[Any, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, type(exc).__name__


def _market_from_handoff(handoff: Mapping[str, Any]) -> dict[str, Any]:
    breadth = handoff.get("breadth") if isinstance(handoff.get("breadth"), Mapping) else {}
    proof = handoff.get("market_session_proof") if isinstance(handoff.get("market_session_proof"), Mapping) else {}
    snapshot = handoff.get("prospective_decision_snapshot") if isinstance(handoff.get("prospective_decision_snapshot"), Mapping) else {}
    regime = breadth.get("breadth_descriptor")
    return {
        "market_regime": regime,
        "breadth": {
            "advancing": breadth.get("advancing"),
            "declining": breadth.get("declining"),
            "unchanged": breadth.get("unchanged"),
            "breadth_descriptor": breadth.get("breadth_descriptor"),
            "momentum_descriptor": breadth.get("momentum_descriptor"),
        } if breadth else None,
        "resolved_session": proof.get("resolved_completed_session"),
        "prospective_snapshot_identity": snapshot.get("identity"),
        "warnings": list(handoff.get("warnings") or []) if isinstance(handoff.get("warnings"), list) else [],
    }


def project_retained_session(session: str, handoff: Mapping[str, Any] | None, opportunity: Mapping[str, Any] | None, *, handoff_error: str | None = None, opportunity_error: str | None = None) -> dict[str, Any]:
    """Project one session from already-loaded small bundles."""
    files = []
    if handoff is not None or handoff_error:
        files.append(HANDOFF_NAME)
    if opportunity is not None or opportunity_error:
        files.append(OPPORTUNITY_NAME)
    if opportunity_error is not None or (opportunity is None and handoff_error is not None):
        return {
            "session": session,
            "session_status": "MALFORMED",
            "errors": {"handoff": handoff_error, "opportunity": opportunity_error},
            "observations": [],
            "duplicate_names_collapsed": 0,
            "files_read": files,
        }
    if opportunity is None:
        return {
            "session": session,
            "session_status": "COHORT_FILE_ABSENT",
            "errors": {},
            "observations": [],
            "duplicate_names_collapsed": 0,
            "files_read": files,
        }
    market = {} if handoff_error else _market_from_handoff(handoff or {})
    source_identity = opportunity.get("opportunity_prioritization_identity") or opportunity.get("current_research_decision_packet_identity")
    cohorts = opportunity.get("cohort_tickers_by_state")
    if not isinstance(cohorts, Mapping):
        return {
            "session": session,
            "session_status": "MALFORMED_COHORT",
            "errors": {},
            "observations": [],
            "duplicate_names_collapsed": 0,
            "files_read": files,
            "market_regime": market.get("market_regime"),
        }
    observations: list[dict[str, Any]] = []
    collapsed = 0
    for state in sorted(cohorts):
        names = cohorts.get(state)
        if not isinstance(names, list):
            continue
        seen: set[str] = set()
        for name in names:
            if not isinstance(name, str):
                continue
            ticker = name.strip().upper()
            if not ticker:
                continue
            if ticker in seen:
                collapsed += 1
                continue
            seen.add(ticker)
            observations.append({
                "session": session,
                "ticker": ticker,
                "tactical_state": state,
                "source_identity": source_identity,
                "source_class": "CANONICAL_POST_CLOSE_OPPORTUNITY_COHORT",
                "semantic_tier": RECONSTRUCTED_RESEARCH,
                "market": market,
                "prospective_snapshot_identity": market.get("prospective_snapshot_identity"),
            })
    return {
        "session": session,
        "session_status": "INDEXED" if handoff_error is None else "INDEXED_HANDOFF_UNREADABLE",
        "errors": {"handoff": handoff_error, "opportunity": None},
        "observations": observations,
        "duplicate_names_collapsed": collapsed,
        "files_read": files,
        "market_regime": market.get("market_regime"),
        "prospective_snapshot_identity": market.get("prospective_snapshot_identity"),
    }


def index_retained_root(root: Path, *, focus_tickers: tuple[str, ...] = ()) -> dict[str, Any]:
    """Index immediate session directories. Does not recurse into enrichment."""
    root = Path(root)
    projections = []
    observations: list[dict[str, Any]] = []
    for child in sorted(path for path in root.iterdir() if path.is_dir() and _session_name(path.name)):
        handoff_path = child / HANDOFF_NAME
        opportunity_path = child / OPPORTUNITY_NAME
        handoff = handoff_error = None
        opportunity = opportunity_error = None
        if handoff_path.is_file():
            handoff, handoff_error = _read_json(handoff_path)
        if opportunity_path.is_file():
            opportunity, opportunity_error = _read_json(opportunity_path)
        if isinstance(handoff, Mapping) or handoff is None:
            pass
        else:
            handoff_error = handoff_error or "NOT_A_MAPPING"
            handoff = None
        if opportunity is not None and not isinstance(opportunity, Mapping):
            opportunity_error = opportunity_error or "NOT_A_MAPPING"
            opportunity = None
        projected = project_retained_session(
            child.name,
            handoff if isinstance(handoff, Mapping) else None,
            opportunity if isinstance(opportunity, Mapping) else None,
            handoff_error=handoff_error,
            opportunity_error=opportunity_error,
        )
        projections.append({
            "session": projected["session"],
            "session_status": projected["session_status"],
            "row_count": len(projected["observations"]),
            "duplicate_names_collapsed": projected["duplicate_names_collapsed"],
            "files_read": projected["files_read"],
            "market_regime": projected.get("market_regime"),
        })
        observations.extend(projected["observations"])
    panel = build_panel(observations, focus_tickers=focus_tickers, session_index=projections)
    panel["source_root_name"] = root.name
    panel["sessions_opened"] = len(projections)
    return panel
