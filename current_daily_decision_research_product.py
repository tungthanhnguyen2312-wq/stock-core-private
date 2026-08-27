"""Current-session human-review product assembled only from existing research contracts."""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Mapping

from field_temporal_contract import stable_id
from current_research_decision_packet_product import attach_shadow_to_daily_product, markdown as packet_shadow_markdown
from owner_research_focus import broader_watchlist, owner_focus_tickers

CONTRACT_VERSION = "current_daily_decision_research_product/v2"
WATCHLIST = broader_watchlist()
OWNER_FOCUS_TICKERS = owner_focus_tickers()
ABSENT_OWNER_FOCUS_STATUS = "OWNER_FOCUS_TICKER_ABSENT_FROM_CURRENT_SESSION_RESEARCH"
LANGUAGE = {"EARLY_REVERSAL_CANDIDATE": "early reversal / possible bottoming process", "BASE_BUILDING": "stabilizing / building a base", "BREAKOUT_READY": "breakout setup with current confirmation evidence", "UPTREND_CONFIRMED": "established uptrend; new-entry location must be assessed separately", "SIDEWAYS_NEUTRAL": "sideways / no current tactical edge", "DISTRIBUTION_RISK": "momentum deterioration / distribution risk", "DOWNTREND": "weak structure / avoid-new-entry context", "BREAKDOWN_RISK": "weak structure / avoid-new-entry context"}


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact)); payload.pop("artifact_sha256", None); payload.pop("artifact_identity", None)
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": "current_daily_decision_research_product:" + digest}


def _peer_summary(peer: Mapping[str, Any] | None, entry_state: str | None) -> dict[str, Any]:
    peer = peer or {}; technical = peer.get("technical_peer_context") or {}; metrics = technical.get("metrics") or {}
    unusual = [f"{name}:{value.get('descriptive_bucket')}" for name, value in metrics.items() if value.get("status") == "AVAILABLE" and value.get("descriptive_bucket") in {"UPPER_QUARTILE", "LOWER_QUARTILE"}]
    ordinary = [f"{name}:{value.get('descriptive_bucket')}" for name, value in metrics.items() if value.get("status") == "AVAILABLE" and value.get("descriptive_bucket") not in {"UPPER_QUARTILE", "LOWER_QUARTILE"}]
    distribution = technical.get("tactical_state_distribution") or {}; shared = distribution.get(entry_state, 0) >= max(1, technical.get("eligible_count", 0) / 2)
    return {"peer_group": (peer.get("peer_membership") or {}).get("peer_group_label"), "peer_group_level": (peer.get("peer_membership") or {}).get("peer_group_level"), "peer_group_size": (peer.get("peer_membership") or {}).get("member_count"), "what_is_unusual": unusual or ["NO_EXTREME_RETAINED_PEER_POSITION"], "what_is_not_unusual": ordinary or ["NO_COMPARABLE_PEER_METRIC"], "context_status": technical.get("status", "UNAVAILABLE"), "stock_specific_vs_sector_wide": "PEER_SHARED_STATE" if technical.get("status") == "AVAILABLE" and shared else "NOT_DETERMINED_OR_MIXED", "expectations_context": peer.get("expectations_context"), "limitations": peer.get("data_gaps") or []}


def _fundamental_summary(fundamental: Mapping[str, Any] | None) -> dict[str, Any]:
    row = fundamental or {}; context = row.get("fundamental_trajectory_context") or {}; alignment = context.get("revenue_vs_earnings_alignment")
    return {"authority_tier": row.get("authority_tier"), "revenue_direction": context.get("revenue_direction"), "earnings_direction": context.get("earnings_direction"), "revenue_vs_earnings_alignment": alignment, "operating_cash_flow_direction": context.get("operating_cash_flow_direction"), "limitations": context.get("data_limitations") or context.get("unavailable_or_partial_reasons") or ["FUNDAMENTAL_CONTEXT_UNAVAILABLE"]}


def _valuation_summary(valuation: Mapping[str, Any] | None, peer: Mapping[str, Any] | None) -> dict[str, Any]:
    valuation = valuation or {}; shadow = valuation.get("shadow_proxy_valuation") or {}; metrics = shadow.get("metrics") or {}
    return {"strict_valuation_status": valuation.get("status", "UNAVAILABLE"), "shadow_proxy_available": any(value.get("status") == "SHADOW_PROXY_READY" for value in metrics.values() if isinstance(value, Mapping)), "shadow_authority": shadow.get("authority_tier"), "peer_valuation_status": ((peer or {}).get("valuation_peer_context") or {}).get("status", "VALUATION_PEER_CONTEXT_UNAVAILABLE"), "authority_warning": "Shadow proxy is descriptive/non-authoritative and not common-shares-outstanding basis; no cheap/expensive or fair-value conclusion."}


def _claims(ticker: str, tactical: Mapping[str, Any], peer: Mapping[str, Any], fundamental: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    state = tactical.get("entry_state")
    thesis = [{"type": "FACT", "claim": f"Current deterministic entry state is {state or 'NOT_AVAILABLE'}.", "evidence_field": "tactical.entry_state", "authority": "CURRENT_DETERMINISTIC_RESEARCH"}]
    thesis += [{"type": "INFERENCE", "claim": reason, "evidence_field": "tactical.evidence_for", "authority": "CURRENT_DETERMINISTIC_RESEARCH"} for reason in (tactical.get("evidence_for") or [])]
    counter = [{"type": "INFERENCE", "claim": reason, "evidence_field": "tactical.evidence_against", "authority": "CURRENT_DETERMINISTIC_RESEARCH"} for reason in (tactical.get("evidence_against") or [])]
    counter += [{"type": "DATA_GAP", "claim": gap, "evidence_field": "peer_relative.data_gaps", "authority": "BLOCKED_OR_UNAVAILABLE"} for gap in (peer.get("data_gaps") or [])]
    questions = [{"type": "QUESTION_TO_VERIFY", "claim": tactical.get("confirmation_trigger") or "No retained confirmation trigger is available.", "evidence_field": "tactical.confirmation_trigger", "authority": "CURRENT_DETERMINISTIC_RESEARCH"}]
    if not fundamental.get("fundamental_trajectory_context"): questions.append({"type": "QUESTION_TO_VERIFY", "claim": "Can retained fundamental trajectory evidence become available without changing authority?", "evidence_field": "fundamental.fundamental_trajectory_context", "authority": "UNAVAILABLE"})
    return {"thesis": thesis, "counter_thesis": counter or [{"type": "DATA_GAP", "claim": "No separate retained counter-evidence item is available.", "evidence_field": "tactical.evidence_against", "authority": "UNAVAILABLE"}], "questions_to_verify": questions}


def _corporate_summary(corporate: Mapping[str, Any] | None) -> dict[str, Any]:
    corporate = corporate or {}; research = corporate.get("catalyst_research") or {}
    events = corporate.get("events") or []
    questions = research.get("watch_for_confirmation") or corporate.get("data_gaps")
    if not questions:
        questions = ["Verify whether later retained official disclosure changes this event's status or current relevance."] if events else ["No retained corporate intelligence evidence; verify through an approved source route."]
    return {"status": corporate.get("intelligence_disposition", "UNAVAILABLE"), "what_changed": research.get("recent_material_events") or [], "current_catalysts_or_risks": {"observed": research.get("observed_catalysts") or [], "adverse": research.get("adverse_event_risks") or []}, "confirmed": [{"event_id": event.get("event_id"), "status": event.get("status"), "evidence_identity": event.get("evidence_identity")} for event in events], "planned_or_pending": research.get("watch_for_execution") or [], "what_to_verify": questions, "source_authority_and_freshness": [{"event_id": event.get("event_id"), "authority_tier": event.get("authority_tier"), "freshness": event.get("freshness")} for event in events], "is_actionable": False}


def _strategy_summary(strategy: Mapping[str, Any] | None) -> dict[str, Any]:
    strategy = strategy or {}; rows = []
    for strategy_id, item in sorted((strategy.get("strategies") or {}).items()):
        requirements = item.get("requirements") or []
        reasons = [requirement.get("reason") for requirement in requirements if requirement.get("status") != "SATISFIED"]
        rows.append({"strategy_id": strategy_id, "strategy_version": item.get("strategy_version"), "status": item.get("status"), "why": (item.get("evidence_for") or reasons)[:2], "limitations": (item.get("limitations") or [])[:1]})
    return {"status": strategy.get("record_strategy_state", "UNAVAILABLE"), "eligible_strategy_ids": strategy.get("eligible_strategy_ids") or [], "strategies": rows, "tactical_relationship": strategy.get("tactical_context") or {}, "scenario_relationship": strategy.get("scenario_context") or {}, "source_artifact_identity": strategy.get("source_artifact_identity"), "is_actionable": False}


def _flow_summary(flow: Mapping[str, Any] | None) -> dict[str, Any]:
    flow = flow or {}
    if not flow: return {"status": "FLOW_UNAVAILABLE", "limitations": ["No current provider-scoped flow artifact is bound to this card."]}
    return {"status": "AVAILABLE" if flow.get("coverage", {}).get("available_dimensions", 0) else "FLOW_UNAVAILABLE", "traded_value_composition": {key: flow.get("traded_value", {}).get(key) for key in ("state", "put_through_share_of_total")}, "foreign_flow": flow.get("foreign_flow", {}).get("state"), "foreign_room": flow.get("foreign_room", {}).get("state"), "proprietary_flow": flow.get("proprietary_flow", {}).get("state"), "active_order": {key: flow.get("active_order_context", {}).get(key) for key in ("state", "active_net_ratio")}, "price_flow_relationships": flow.get("price_flow_relationships") or [], "limitations": ["Descriptive provider evidence only; causality, institutional intent, sizing, and execution are unknown/not emitted."]}


def _research_priority_summary(opportunity_record: Mapping[str, Any] | None) -> dict[str, Any]:
    if not opportunity_record:
        return {"status": "NOT_IN_RESEARCH_PRIORITY_QUEUE"}
    return {"status": "AVAILABLE", "research_priority_tier": opportunity_record.get("research_priority_tier"), "eligible_strategies": list(opportunity_record.get("eligible_strategies") or []), "lane_specific_priority": dict(opportunity_record.get("lane_specific_priority") or {}), "entry_relevant": opportunity_record.get("entry_relevant"), "priority_reasons": list(opportunity_record.get("priority_reasons") or []), "blocking_reasons": list(opportunity_record.get("blocking_reasons") or []), "authority_note": "research_priority_tier is a research-lane priority signal; it is separate from current_decision_state (tactical_state/entry_action/position_sizing_status), and PRIORITY_NOW is never BUY_NOW, full-position-ready, or sizing-ready."}


def _card(ticker: str, tactical: Mapping[str, Any], peer: Mapping[str, Any] | None, fundamental: Mapping[str, Any] | None, valuation: Mapping[str, Any] | None, scenario: Mapping[str, Any] | None, corporate: Mapping[str, Any] | None = None, strategy: Mapping[str, Any] | None = None, flow: Mapping[str, Any] | None = None, opportunity_record: Mapping[str, Any] | None = None) -> dict[str, Any]:
    state = tactical.get("entry_state"); peer = peer or {}; fundamental = fundamental or {}; scenario = scenario or {}
    return {"ticker": ticker, "status": "AVAILABLE", "current_decision_state": {"ticker_structure_state": tactical.get("ticker_structure_state"), "entry_state": state, "entry_action": tactical.get("entry_action"), "entry_action_is_research_label_not_execution_instruction": True, "horizon": tactical.get("horizon"), "human_use_language": LANGUAGE.get(state, "technical evidence unavailable / no current tactical classification"), "is_actionable": False, "requires_human_review": True, "position_sizing_status": tactical.get("position_sizing_status", "NOT_EVALUATED")}, "why_it_is_on_radar": {"deterministic_reasons": tactical.get("evidence_for") or [], "evidence_for": tactical.get("evidence_for") or []}, "what_argues_against": {"evidence_against": tactical.get("evidence_against") or [], "conflicts": scenario.get("key_driver_conflicts") or [], "limitations": (tactical.get("data_quality") or {}).get("warnings") or []}, "peer_context": _peer_summary(peer, state), "fundamental_context": _fundamental_summary(fundamental), "valuation_context": _valuation_summary(valuation, peer), "market_flow_positioning": _flow_summary(flow), "corporate_intelligence_context": _corporate_summary(corporate), "strategy_fit": _strategy_summary(strategy), "research_priority": _research_priority_summary(opportunity_record), "scenario": {"bear_case": scenario.get("bear_case"), "base_case": scenario.get("base_case"), "bull_case": scenario.get("bull_case"), "probability_status": scenario.get("probability_status", "UNKNOWN_UNCALIBRATED")}, "trigger": tactical.get("confirmation_trigger"), "invalidation": tactical.get("invalidation"), "data_quality": tactical.get("data_quality") or {}, "thesis_counter_thesis": _claims(ticker, tactical, peer, fundamental), "authority_limitations": ["Strategy eligibility is distinct from entry action, scenario, and portfolio action.", "Research priority tier is distinct from entry action, is_full_position_ready, and position_sizing_status.", "Entry action is a tactical research-state label only, not a recommendation, suggested trade, or execution authority.", "No target, probability, ranking, recommendation, sizing, portfolio, or execution instruction."], "is_actionable": False, "entry_action_is_research_label_not_execution_instruction": True}


def is_present_research_card(card: Mapping[str, Any] | None) -> bool:
    return isinstance(card, Mapping) and card.get("status") != ABSENT_OWNER_FOCUS_STATUS


def _absent_owner_focus_card(ticker: str) -> dict[str, Any]:
    """Explicit absence for an owner-focus ticker with no current-session tactical card."""
    return {
        "ticker": ticker,
        "status": ABSENT_OWNER_FOCUS_STATUS,
        "current_decision_state": {
            "ticker_structure_state": None,
            "entry_state": None,
            "entry_action": None,
            "entry_action_is_research_label_not_execution_instruction": True,
            "horizon": None,
            "human_use_language": "owner-focus ticker has no current-session tactical research card",
            "is_actionable": False,
            "requires_human_review": True,
            "position_sizing_status": "NOT_EVALUATED",
        },
        "why_it_is_on_radar": {"deterministic_reasons": [], "evidence_for": []},
        "what_argues_against": {"evidence_against": [], "conflicts": [], "limitations": [ABSENT_OWNER_FOCUS_STATUS]},
        "peer_context": {"peer_group": None, "peer_group_level": None, "peer_group_size": None, "what_is_unusual": [], "what_is_not_unusual": [], "context_status": "UNAVAILABLE", "stock_specific_vs_sector_wide": "NOT_DETERMINED_OR_MIXED", "expectations_context": None, "limitations": [ABSENT_OWNER_FOCUS_STATUS]},
        "fundamental_context": {"authority_tier": None, "limitations": [ABSENT_OWNER_FOCUS_STATUS]},
        "valuation_context": {"strict_valuation_status": "UNAVAILABLE", "shadow_proxy_available": False, "authority_warning": "No current-session research card."},
        "market_flow_positioning": {"status": "FLOW_UNAVAILABLE", "limitations": [ABSENT_OWNER_FOCUS_STATUS]},
        "corporate_intelligence_context": {"status": "NO_RETAINED_INTELLIGENCE", "what_changed": [], "current_catalysts_or_risks": {"observed": [], "adverse": []}, "confirmed": [], "planned_or_pending": [], "what_to_verify": ["Owner-focus ticker has no current-session research card; do not invent one."], "source_authority_and_freshness": [], "is_actionable": False},
        "strategy_fit": {"status": "UNAVAILABLE", "eligible_strategy_ids": [], "strategies": [], "tactical_relationship": {}, "scenario_relationship": {}, "source_artifact_identity": None, "is_actionable": False},
        "research_priority": {"status": "NOT_IN_RESEARCH_PRIORITY_QUEUE"},
        "scenario": {"bear_case": None, "base_case": None, "bull_case": None, "probability_status": "UNKNOWN_UNCALIBRATED"},
        "trigger": None,
        "invalidation": None,
        "data_quality": {},
        "thesis_counter_thesis": {"thesis": [], "counter_thesis": [], "questions_to_verify": []},
        "authority_limitations": ["Absence is explicit. Do not invent a card, ranking, or recommendation.", "Entry action is a tactical research-state label only, not a recommendation or execution instruction.", "No target, probability, ranking, recommendation, sizing, portfolio, or execution instruction."],
        "is_actionable": False,
        "entry_action_is_research_label_not_execution_instruction": True,
    }


def build(*, descriptive: Mapping[str, Any], tactical: Mapping[str, Any], peer_relative: Mapping[str, Any], fundamental: Mapping[str, Any], valuation: Mapping[str, Any], scenario: Mapping[str, Any], triage: Mapping[str, Any], corporate_intelligence: Mapping[str, Any] | None = None, strategy_classification: Mapping[str, Any] | None = None, portfolio_risk: Mapping[str, Any] | None = None, macro_context: Mapping[str, Any] | None = None, market_flow_positioning: Mapping[str, Any] | None = None, opportunity_decision_queue: Mapping[str, Any] | None = None, current_research_decision_packet: Mapping[str, Any] | None = None) -> dict[str, Any]:
    d, t, p, f, v, s = descriptive["records"], tactical["records"], peer_relative["records"], fundamental["records"], valuation["records"], scenario["records"]
    groups = {"EARLY_REVERSAL": "EARLY_REVERSAL_CANDIDATE", "BASE_BUILDING": "BASE_BUILDING", "BREAKOUT_CONFIRMATION": "BREAKOUT_READY", "UPTREND_ESTABLISHED_STRENGTH": "UPTREND_CONFIRMED", "DISTRIBUTION_OR_BREAKDOWN_RISK": {"DISTRIBUTION_RISK", "BREAKDOWN_RISK", "DOWNTREND"}}
    cohorts = {name: [ticker for ticker in sorted(t) if (t[ticker].get("entry_state") in state if isinstance(state, set) else t[ticker].get("entry_state") == state)] for name, state in groups.items()}
    high_priority = [row["ticker"] for row in triage.get("high_priority_review_eligible_records", []) if isinstance(row, Mapping)]
    entry_source = triage.get("all_entry_relevant_records", {}); entry_rows = [row for rows in entry_source.values() for row in rows] if isinstance(entry_source, Mapping) else entry_source; entry_90 = [row["ticker"] for row in entry_rows if isinstance(row, Mapping)]
    c = (corporate_intelligence or {}).get("records") or {}; strategies = (strategy_classification or {}).get("records") or {}; flows = (market_flow_positioning or {}).get("records") or {}
    opportunity_records = (opportunity_decision_queue or {}).get("records") or {}
    # Deliberately not unioned into `detailed`: embedding all ~190 PRIORITY_NOW cards here would
    # recreate the "one flat high-priority list" the decision queue exists to avoid. The full
    # PRIORITY_NOW dataset is exposed separately (research_priority_queue below + the standalone
    # daily_opportunity_decision_queue artifact); only cards already selected by existing rules
    # additionally show their research-priority context here.
    detailed = sorted(set(WATCHLIST) | set(OWNER_FOCUS_TICKERS) | set(high_priority) | set(entry_90))
    cards = {}
    for ticker in detailed:
        if ticker in t:
            cards[ticker] = _card(ticker, t.get(ticker) or {}, p.get(ticker), f.get(ticker), v.get(ticker), s.get(ticker), c.get(ticker), ({**strategies.get(ticker, {}), "source_artifact_identity": (strategy_classification or {}).get("artifact_identity")} if ticker in strategies else None), flows.get(ticker), opportunity_records.get(ticker))
        elif ticker in OWNER_FOCUS_TICKERS:
            cards[ticker] = _absent_owner_focus_card(ticker)
    breadth = descriptive["market_breadth"]
    market_brief = {"source_market_session": descriptive["session"], "coverage": {"input_candidates": descriptive["validation"]["coverage"]["input_candidates"], "current_active_equity_denominator": breadth["current_active_equity_denominator"], "observed_session_cohort": breadth["observed_session_cohort"], "same_session_technical_feature_available_count": breadth["same_session_technical_feature_available_count"]}, "breadth_state": breadth["breadth_descriptor"]["descriptor"], "momentum_state": breadth["momentum_descriptor"]["descriptor"], "trend_state": breadth["trend"], "volatility_context": breadth["volatility"], "market_scenario_context": tactical.get("market_state"), "data_quality_limitations": [breadth["quality_state"], "NOT_AUTHORITATIVE_ACTIVE_UNIVERSE", "VOLATILITY_CONTEMPORANEOUS_CROSS_SECTION_ONLY"]}
    artifact = {"schema_version": "2.1.0", "contract_version": CONTRACT_VERSION, "session": descriptive["session"], "source_artifact_identities": {"descriptive": descriptive["artifact_identity"], "tactical": tactical["artifact_identity"], "peer_relative": peer_relative["artifact_identity"], "fundamental": fundamental["artifact_identity"], "valuation": valuation["artifact_identity"], "scenario": scenario["artifact_identity"], "triage": triage["artifact_identity"], "corporate_intelligence": (corporate_intelligence or {}).get("artifact_identity"), "strategy_classification": (strategy_classification or {}).get("artifact_identity"), "portfolio_risk": (portfolio_risk or {}).get("artifact_identity"), "market_flow_positioning": (market_flow_positioning or {}).get("artifact_identity")}, "market_brief": market_brief, "portfolio_risk": portfolio_risk, "research_cohorts": {name: {"membership_rule": "EXISTING_TACTICAL_ENTRY_STATE", "tickers": values, "count": len(values), "ordering": "TICKER_ASCENDING_NOT_RANKING"} for name, values in cohorts.items()}, "watchlist": {"tickers": list(WATCHLIST), "cards_available": sum(ticker in cards and is_present_research_card(cards.get(ticker)) for ticker in WATCHLIST), "role": "BROADER_WATCHLIST_NOT_PORTFOLIO_HOLDINGS", "is_portfolio_holdings": False}, "owner_focus": {"tickers": list(OWNER_FOCUS_TICKERS), "cards_available": sum(is_present_research_card(cards.get(ticker)) for ticker in OWNER_FOCUS_TICKERS), "missing": [ticker for ticker in OWNER_FOCUS_TICKERS if not is_present_research_card(cards.get(ticker))], "role": "OWNER_FOCUS_REVIEW_SCOPE", "is_portfolio_holdings": False, "is_actionable": False}, "high_priority_full_universe_review_set": {"tickers": high_priority, "count": len(high_priority), "outside_watchlist": sorted(set(high_priority) - set(WATCHLIST)), "meaning": "Candidates for human research, not portfolio/watchlist inclusion.", "relationship_to_research_priority_queue": "This is the pre-existing tactical entry-timing review policy (a subset of research priority scoped to entry-relevant tactical states); it is not the full research-priority dataset. See research_priority_queue for the complete PRIORITY_NOW set and lane-specific queues."}, "detailed_research_cards": cards, "aggregate_validation": {"entry_relevant_90_count": len(entry_90), "detailed_card_count": len(cards), "scenario_disposition_counts": dict(sorted(Counter((s.get(ticker) or {}).get("scenario_disposition", "UNAVAILABLE") for ticker in cards).items()))}, "risk_data_gap_panel": {"technical_unavailable": sum(not bool((row.get("data_quality") or {}).get("technical_eligible")) for row in t.values()), "peer_context_unavailable": sum((row.get("technical_peer_context") or {}).get("status") != "AVAILABLE" for row in p.values()), "fundamental_context_unavailable": sum(ticker not in f for ticker in d), "valuation_peer_context_unavailable": len(d), "strict_valuation_ready": 0, "corporate_intelligence_unavailable": sum(card["corporate_intelligence_context"]["status"] == "NO_RETAINED_INTELLIGENCE" for card in cards.values()), "strategy_classification_unavailable": sum(card["strategy_fit"]["status"] == "UNAVAILABLE" for card in cards.values()), "market_flow_unavailable": sum(card["market_flow_positioning"]["status"] == "FLOW_UNAVAILABLE" for card in cards.values())}, "what_to_verify_next": ["Use each card's exact confirmation trigger and invalidation; do not substitute new thresholds.", "Flow/positioning is descriptive provider evidence only; verify exact session, source and limitations before interpretation.", "Strategy fit is a deterministic research classification, not an entry action or BUY instruction.", "Resolve retained fundamental and peer-context gaps only through their source contracts.", "Verify corporate event execution only through retained approved official evidence; planned/approved is not executed.", "Strict valuation and peer valuation comparison remain unavailable under current share/financial authority."], "authority_boundary": {"research_human_review_only": True, "is_actionable": False, "recommendation": "NOT_EMITTED", "probability": "UNKNOWN_UNCALIBRATED", "target_price_ranking_sizing_execution": "NOT_EMITTED", "entry_action_is_research_label_not_execution_instruction": True, "owner_focus_is_not_portfolio_holdings": True}}
    if portfolio_risk is None:
        artifact["source_artifact_identities"].pop("portfolio_risk")
        artifact.pop("portfolio_risk")
    if macro_context is not None:
        artifact["macro_context"] = macro_context
        artifact["source_artifact_identities"]["macro"] = macro_context.get("macro_artifact_identity")
    if opportunity_decision_queue is not None:
        summary = opportunity_decision_queue["entry_relevant_summary"]
        artifact["research_priority_queue"] = {
            "source_artifact_identity": opportunity_decision_queue["artifact_identity"],
            "meaning": "The complete current-session research-priority dataset across all strategy lanes (not entry timing; see entry_relevant on each record and current_decision_state.entry_action on each card).",
            "entry_relevant_summary": dict(summary),
            "full_priority_now_count": len(opportunity_decision_queue["full_priority_now"]),
            "lane_queue_counts": {lane: info["count"] for lane, info in opportunity_decision_queue["lane_queues"].items()},
            "multi_strategy_count": opportunity_decision_queue["multi_strategy"]["count"],
            "legacy_comparison_summary": {"legacy_high_priority_count": opportunity_decision_queue["legacy_comparison"]["legacy_high_priority_count"], "agreement_count": opportunity_decision_queue["legacy_comparison"]["agreement_count"], "newly_surfaced_count": len(opportunity_decision_queue["legacy_comparison"]["newly_surfaced"]), "downgraded_count": len(opportunity_decision_queue["legacy_comparison"]["downgraded"])},
            "authority_boundary": dict(opportunity_decision_queue["authority_boundary"]),
        }
        artifact["source_artifact_identities"]["opportunity_decision_queue"] = opportunity_decision_queue["artifact_identity"]
    if current_research_decision_packet is not None:
        attach_shadow_to_daily_product(artifact, current_research_decision_packet)
    artifact.update(content_identity(artifact)); return artifact


def markdown(artifact: Mapping[str, Any]) -> str:
    market = artifact["market_brief"]; lines = ["# Current Daily Decision Research", "", f"Session: {artifact['session']}", "", "## Market brief", f"- Breadth: {market['breadth_state']}; momentum: {market['momentum_state']}.", f"- Coverage: {market['coverage']['same_session_technical_feature_available_count']} same-session technical records / {market['coverage']['current_active_equity_denominator']} current equity denominator; not an authoritative active universe.", f"- Data limits: {', '.join(market['data_quality_limitations'])}.", "", "## Today's research cohorts"]
    for name, cohort in artifact["research_cohorts"].items(): lines.append(f"- {name}: {cohort['count']} deterministic tactical records (ticker order only; not a ranking).")
    review = artifact["high_priority_full_universe_review_set"]
    owner_focus = artifact.get("owner_focus") or {}
    lines += ["", "## Owner-focus review scope", f"- Owner-focus tickers: {', '.join(owner_focus.get('tickers') or []) or 'none'}.", f"- Present cards: {owner_focus.get('cards_available', 0)}; missing: {', '.join(owner_focus.get('missing') or []) or 'none'}.", "- Owner-focus is presentation/analysis scope only; it is not holdings, ranking, or a recommendation.", "- Complete owner-focus coverage before market discovery. Do not alphabetically sample the universe."]
    lines += ["", "## Full-universe discovery", f"- High-priority human-review set: {review['count']}; outside current watchlist: {', '.join(review['outside_watchlist']) or 'none'}.", "- Candidate means human research candidate only, not an investment instruction."]
    priority = artifact.get("research_priority_queue")
    if isinstance(priority, Mapping):
        summary = priority["entry_relevant_summary"]
        lines += ["", "## Research priority queue (all strategy lanes)", f"- PRIORITY_NOW: {summary['PRIORITY_NOW_TOTAL']} total, {summary['PRIORITY_NOW_ENTRY_RELEVANT']} entry-relevant, {summary['PRIORITY_NOW_NOT_ENTRY_RELEVANT']} research-only (not an entry setup).", f"- SETUP_WATCH entry-relevant: {summary['SETUP_WATCH_ENTRY_RELEVANT']}.", f"- Lane queues: {', '.join(f'{lane}={count}' for lane, count in priority['lane_queue_counts'].items())}.", f"- Multi-strategy tickers: {priority['multi_strategy_count']}.", "- Research priority is a research-lane signal, not BUY_NOW, full-position-ready, or sizing-ready; see full_priority_now/lane_queues in the source artifact for the complete list."]
    lines += ["", "## Detailed research cards"]
    card_tickers = list(owner_focus.get("tickers") or []) + sorted((set(artifact["watchlist"]["tickers"]) | set(review["tickers"])) - set(owner_focus.get("tickers") or []))
    for ticker in card_tickers:
        card = artifact["detailed_research_cards"].get(ticker)
        if not card: continue
        state = card["current_decision_state"]; peer = card["peer_context"]; scenario = card["scenario"]
        corporate = card["corporate_intelligence_context"]
        strategies = card["strategy_fit"]
        fit = ", ".join(f"{item['strategy_id']}={item['status']}" for item in strategies["strategies"]) or "unavailable"
        lines += [f"### {ticker}", f"- State: {state['human_use_language']} ({state['entry_state']}); action: {state['entry_action']}; horizon: {state['horizon']}.", f"- Why: {'; '.join(card['why_it_is_on_radar']['deterministic_reasons'][:2]) or 'No positive retained tactical reason.'}", f"- Against: {'; '.join(card['what_argues_against']['evidence_against'][:2]) or 'No separate retained counter-evidence item.'}", f"- Strategy fit: {fit}. This is separate from entry action and scenario probability.", f"- Peer: {peer['peer_group'] or 'unavailable'}; unusual: {', '.join(peer['what_is_unusual'])}; peer framing: {peer['stock_specific_vs_sector_wide']}.", f"- Fundamental authority: {card['fundamental_context']['authority_tier'] or 'unavailable'}; valuation: strict={card['valuation_context']['strict_valuation_status']}, shadow proxy={card['valuation_context']['shadow_proxy_available']}.", f"- Corporate intelligence: {corporate['status']}; confirmed events: {len(corporate['confirmed'])}; pending verification: {len(corporate['planned_or_pending'])}.", f"- Scenario: Bull needs the existing trigger; Base is current continuation; Bear activates on existing invalidation. Probability: {scenario['probability_status']}.", f"- Trigger: {card['trigger'] or 'unavailable'}", f"- Invalidation: {card['invalidation'] or 'unavailable'}", "- Human review required; no sizing or execution instruction."]
    portfolio = artifact.get("portfolio_risk")
    if isinstance(portfolio, Mapping):
        breached = [item["limit_id"] for item in portfolio.get("user_limit_results", []) if item.get("status") == "LIMIT_BREACH"]
        lines += ["", "## Portfolio risk (explicit input)", f"- Portfolio: {portfolio.get('portfolio_id')} ({portfolio.get('portfolio_kind')}); {len(portfolio.get('positions', []))} explicit positions.", f"- User-limit breaches: {', '.join(breached) or 'none declared'}.", "- Concentration context only; no allocation, sizing, VaR/CVaR, leverage, liquidity, or execution instruction."]
    packet_shadow = artifact.get("current_research_decision_packet_shadow")
    if isinstance(packet_shadow, Mapping):
        panel = dict(packet_shadow)
        panel["cards"] = {ticker: card.get("current_research_decision_packet") for ticker, card in artifact.get("detailed_research_cards", {}).items() if isinstance(card, Mapping) and isinstance(card.get("current_research_decision_packet"), Mapping)}
        panel["cards_requested"] = sorted(panel["cards"])
        lines += ["", packet_shadow_markdown(panel).rstrip()]
    macro = artifact.get("macro_context")
    if isinstance(macro, Mapping):
        regime = (macro.get("macro_regime") or {}).get("state", "UNAVAILABLE")
        lines += ["", "## Macro / top-down", f"- Regime: {regime}; session compatibility: {macro.get('status') or 'UNAVAILABLE'}.", "- Macro context is descriptive evidence only; it does not establish causality, probability, portfolio sensitivity, or a trading instruction."]
    lines += ["", "## Risk and data gaps", f"- Technical unavailable: {artifact['risk_data_gap_panel']['technical_unavailable']}; peer context unavailable: {artifact['risk_data_gap_panel']['peer_context_unavailable']}; strict valuation ready: 0.", "", "## What to verify next"] + [f"- {item}" for item in artifact["what_to_verify_next"]]
    return "\n".join(lines) + "\n"
