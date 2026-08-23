"""Current-session human-review product assembled only from existing research contracts."""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Mapping

from field_temporal_contract import stable_id

CONTRACT_VERSION = "current_daily_decision_research_product/v2"
WATCHLIST = ("EVF", "FPT", "HPG", "NVL", "PAN", "PNJ", "POW", "PVD", "QNS", "SSI", "VNM")
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


def _card(ticker: str, tactical: Mapping[str, Any], peer: Mapping[str, Any] | None, fundamental: Mapping[str, Any] | None, valuation: Mapping[str, Any] | None, scenario: Mapping[str, Any] | None, corporate: Mapping[str, Any] | None = None) -> dict[str, Any]:
    state = tactical.get("entry_state"); peer = peer or {}; fundamental = fundamental or {}; scenario = scenario or {}
    return {"ticker": ticker, "current_decision_state": {"ticker_structure_state": tactical.get("ticker_structure_state"), "entry_state": state, "entry_action": tactical.get("entry_action"), "horizon": tactical.get("horizon"), "human_use_language": LANGUAGE.get(state, "technical evidence unavailable / no current tactical classification"), "is_actionable": False, "requires_human_review": True, "position_sizing_status": tactical.get("position_sizing_status", "NOT_EVALUATED")}, "why_it_is_on_radar": {"deterministic_reasons": tactical.get("evidence_for") or [], "evidence_for": tactical.get("evidence_for") or []}, "what_argues_against": {"evidence_against": tactical.get("evidence_against") or [], "conflicts": scenario.get("key_driver_conflicts") or [], "limitations": (tactical.get("data_quality") or {}).get("warnings") or []}, "peer_context": _peer_summary(peer, state), "fundamental_context": _fundamental_summary(fundamental), "valuation_context": _valuation_summary(valuation, peer), "corporate_intelligence_context": _corporate_summary(corporate), "scenario": {"bear_case": scenario.get("bear_case"), "base_case": scenario.get("base_case"), "bull_case": scenario.get("bull_case"), "probability_status": scenario.get("probability_status", "UNKNOWN_UNCALIBRATED")}, "trigger": tactical.get("confirmation_trigger"), "invalidation": tactical.get("invalidation"), "data_quality": tactical.get("data_quality") or {}, "thesis_counter_thesis": _claims(ticker, tactical, peer, fundamental), "authority_limitations": ["Entry action is tactical research state only, not execution authority.", "No target, probability, ranking, recommendation, sizing, portfolio, or execution instruction."]}


def build(*, descriptive: Mapping[str, Any], tactical: Mapping[str, Any], peer_relative: Mapping[str, Any], fundamental: Mapping[str, Any], valuation: Mapping[str, Any], scenario: Mapping[str, Any], triage: Mapping[str, Any], corporate_intelligence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    d, t, p, f, v, s = descriptive["records"], tactical["records"], peer_relative["records"], fundamental["records"], valuation["records"], scenario["records"]
    groups = {"EARLY_REVERSAL": "EARLY_REVERSAL_CANDIDATE", "BASE_BUILDING": "BASE_BUILDING", "BREAKOUT_CONFIRMATION": "BREAKOUT_READY", "UPTREND_ESTABLISHED_STRENGTH": "UPTREND_CONFIRMED", "DISTRIBUTION_OR_BREAKDOWN_RISK": {"DISTRIBUTION_RISK", "BREAKDOWN_RISK", "DOWNTREND"}}
    cohorts = {name: [ticker for ticker in sorted(t) if (t[ticker].get("entry_state") in state if isinstance(state, set) else t[ticker].get("entry_state") == state)] for name, state in groups.items()}
    high_priority = [row["ticker"] for row in triage.get("high_priority_review_eligible_records", []) if isinstance(row, Mapping)]
    entry_source = triage.get("all_entry_relevant_records", {}); entry_rows = [row for rows in entry_source.values() for row in rows] if isinstance(entry_source, Mapping) else entry_source; entry_90 = [row["ticker"] for row in entry_rows if isinstance(row, Mapping)]
    c = (corporate_intelligence or {}).get("records") or {}
    detailed = sorted(set(WATCHLIST) | set(high_priority) | set(entry_90)); cards = {ticker: _card(ticker, t.get(ticker) or {}, p.get(ticker), f.get(ticker), v.get(ticker), s.get(ticker), c.get(ticker)) for ticker in detailed if ticker in t}
    breadth = descriptive["market_breadth"]
    market_brief = {"source_market_session": descriptive["session"], "coverage": {"input_candidates": descriptive["validation"]["coverage"]["input_candidates"], "current_active_equity_denominator": breadth["current_active_equity_denominator"], "observed_session_cohort": breadth["observed_session_cohort"], "same_session_technical_feature_available_count": breadth["same_session_technical_feature_available_count"]}, "breadth_state": breadth["breadth_descriptor"]["descriptor"], "momentum_state": breadth["momentum_descriptor"]["descriptor"], "trend_state": breadth["trend"], "volatility_context": breadth["volatility"], "market_scenario_context": tactical.get("market_state"), "data_quality_limitations": [breadth["quality_state"], "NOT_AUTHORITATIVE_ACTIVE_UNIVERSE", "VOLATILITY_CONTEMPORANEOUS_CROSS_SECTION_ONLY"]}
    artifact = {"schema_version": "2.0.0", "contract_version": CONTRACT_VERSION, "session": descriptive["session"], "source_artifact_identities": {"descriptive": descriptive["artifact_identity"], "tactical": tactical["artifact_identity"], "peer_relative": peer_relative["artifact_identity"], "fundamental": fundamental["artifact_identity"], "valuation": valuation["artifact_identity"], "scenario": scenario["artifact_identity"], "triage": triage["artifact_identity"], "corporate_intelligence": (corporate_intelligence or {}).get("artifact_identity")}, "market_brief": market_brief, "research_cohorts": {name: {"membership_rule": "EXISTING_TACTICAL_ENTRY_STATE", "tickers": values, "count": len(values), "ordering": "TICKER_ASCENDING_NOT_RANKING"} for name, values in cohorts.items()}, "watchlist": {"tickers": list(WATCHLIST), "cards_available": sum(ticker in cards for ticker in WATCHLIST)}, "high_priority_full_universe_review_set": {"tickers": high_priority, "count": len(high_priority), "outside_watchlist": sorted(set(high_priority) - set(WATCHLIST)), "meaning": "Candidates for human research, not portfolio/watchlist inclusion."}, "detailed_research_cards": cards, "aggregate_validation": {"entry_relevant_90_count": len(entry_90), "detailed_card_count": len(cards), "scenario_disposition_counts": dict(sorted(Counter((s.get(ticker) or {}).get("scenario_disposition", "UNAVAILABLE") for ticker in cards).items()))}, "risk_data_gap_panel": {"technical_unavailable": sum(not bool((row.get("data_quality") or {}).get("technical_eligible")) for row in t.values()), "peer_context_unavailable": sum((row.get("technical_peer_context") or {}).get("status") != "AVAILABLE" for row in p.values()), "fundamental_context_unavailable": sum(ticker not in f for ticker in d), "valuation_peer_context_unavailable": len(d), "strict_valuation_ready": 0, "corporate_intelligence_unavailable": sum(card["corporate_intelligence_context"]["status"] == "NO_RETAINED_INTELLIGENCE" for card in cards.values())}, "what_to_verify_next": ["Use each card's exact confirmation trigger and invalidation; do not substitute new thresholds.", "Resolve retained fundamental and peer-context gaps only through their source contracts.", "Verify corporate event execution only through retained approved official evidence; planned/approved is not executed.", "Strict valuation and peer valuation comparison remain unavailable under current share/financial authority."], "authority_boundary": {"research_human_review_only": True, "is_actionable": False, "recommendation": "NOT_EMITTED", "probability": "UNKNOWN_UNCALIBRATED", "target_price_ranking_sizing_execution": "NOT_EMITTED"}}
    artifact.update(content_identity(artifact)); return artifact


def markdown(artifact: Mapping[str, Any]) -> str:
    market = artifact["market_brief"]; lines = ["# Current Daily Decision Research", "", f"Session: {artifact['session']}", "", "## Market brief", f"- Breadth: {market['breadth_state']}; momentum: {market['momentum_state']}.", f"- Coverage: {market['coverage']['same_session_technical_feature_available_count']} same-session technical records / {market['coverage']['current_active_equity_denominator']} current equity denominator; not an authoritative active universe.", f"- Data limits: {', '.join(market['data_quality_limitations'])}.", "", "## Today's research cohorts"]
    for name, cohort in artifact["research_cohorts"].items(): lines.append(f"- {name}: {cohort['count']} deterministic tactical records (ticker order only; not a ranking).")
    review = artifact["high_priority_full_universe_review_set"]; lines += ["", "## Full-universe discovery", f"- High-priority human-review set: {review['count']}; outside current watchlist: {', '.join(review['outside_watchlist']) or 'none'}.", "- Candidate means human research candidate only, not an investment instruction.", "", "## Detailed research cards"]
    card_tickers = sorted(set(artifact["watchlist"]["tickers"]) | set(review["tickers"]))
    for ticker in card_tickers:
        card = artifact["detailed_research_cards"].get(ticker)
        if not card: continue
        state = card["current_decision_state"]; peer = card["peer_context"]; scenario = card["scenario"]
        corporate = card["corporate_intelligence_context"]
        lines += [f"### {ticker}", f"- State: {state['human_use_language']} ({state['entry_state']}); action: {state['entry_action']}; horizon: {state['horizon']}.", f"- Why: {'; '.join(card['why_it_is_on_radar']['deterministic_reasons'][:2]) or 'No positive retained tactical reason.'}", f"- Against: {'; '.join(card['what_argues_against']['evidence_against'][:2]) or 'No separate retained counter-evidence item.'}", f"- Peer: {peer['peer_group'] or 'unavailable'}; unusual: {', '.join(peer['what_is_unusual'])}; peer framing: {peer['stock_specific_vs_sector_wide']}.", f"- Fundamental authority: {card['fundamental_context']['authority_tier'] or 'unavailable'}; valuation: strict={card['valuation_context']['strict_valuation_status']}, shadow proxy={card['valuation_context']['shadow_proxy_available']}.", f"- Corporate intelligence: {corporate['status']}; confirmed events: {len(corporate['confirmed'])}; pending verification: {len(corporate['planned_or_pending'])}.", f"- Scenario: Bull needs the existing trigger; Base is current continuation; Bear activates on existing invalidation. Probability: {scenario['probability_status']}.", f"- Trigger: {card['trigger'] or 'unavailable'}", f"- Invalidation: {card['invalidation'] or 'unavailable'}", "- Human review required; no sizing or execution instruction."]
    lines += ["", "## Risk and data gaps", f"- Technical unavailable: {artifact['risk_data_gap_panel']['technical_unavailable']}; peer context unavailable: {artifact['risk_data_gap_panel']['peer_context_unavailable']}; strict valuation ready: 0.", "", "## What to verify next"] + [f"- {item}" for item in artifact["what_to_verify_next"]]
    return "\n".join(lines) + "\n"
