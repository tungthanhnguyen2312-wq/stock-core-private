"""Deterministic, non-ranking comparison of a bounded research shortlist."""
from __future__ import annotations
import hashlib, json
from typing import Any, Mapping, Sequence
import copy
from itertools import combinations

TECHNICAL = ("close", "momentum_20d", "volatility_20d", "relative_volume_provider_scoped")
SUPPORTED = frozenset(("CURRENT_OBSERVABLE_STATE", "RELATIVE_CONTEXT", "FUNDAMENTAL_EVIDENCE",
                       "RESEARCH_LENS_AVAILABILITY", "SCENARIO_COUNTER_THESIS", "EVIDENCE_QUALITY"))
INTEGRATED_EXPLANATIONS = {
    "VALUATION_DISCOUNT_WITH_FINANCIAL_DETERIORATION":"The sector-relative valuation discount coexists with repeated or company-specific financial weakness; investigate a value-trap thesis before treating cheapness as support.",
    "VALUATION_DISCOUNT_WITH_RESILIENCE_COUNTERTHESIS":"The sector-relative valuation discount has recovery or relative-resilience support; missing profitability and contrary evidence can still invalidate that thesis.",
    "FINANCIAL_STRENGTH_WITHOUT_FRESH_ENTRY_CONFIRMATION":"Financial improvement does not establish a qualified current entry; the existing strategy confirmation and invalidation conditions remain controlling.",
    "EXISTING_POLICY_QUALIFIED_ENTRY_CONDITION":"The existing strategy owner admits a qualified conditional entry case; this comparison grants no execution or sizing authority.",
    "QUALIFIED_ENTRY_CONDITION_WITH_FINANCIAL_COUNTEREVIDENCE":"The existing conditional entry case has financial counterevidence; tactical confirmation does not erase the financial risk.",
    "FINANCIAL_WEAKNESS_SHARED_WITH_RETAINED_SECTOR_SAMPLE":"Adverse financial changes are shared with the retained compatible sector sample; this alone does not establish company-specific failure or economic causation.",
    "CURRENT_TIMING_COMPARISON_UNKNOWN":"Current-session tactical evidence is unavailable; historical financial evidence must not substitute for a current trading signal.",
    "QUALIFIED_VALUATION_FINANCIAL_COMPARISON_UNKNOWN":"Qualified valuation versus financial evidence is insufficient; retain the independent evidence and its gaps.",
    "OBSERVED_ADVERSE_STRUCTURE_DOWNSIDE_CONDITION":"The existing strategy owner observes an adverse structural condition now; the bear case, invalidation boundary and counter-thesis govern downside research regardless of valuation or financial support."}
# Fitness members the profile already carries elsewhere (or that duplicate the full Integrated
# Decision record) are summarized and referenced by the source decision identity, not re-copied.
_SUMMARY_ONLY_DIMENSIONS = frozenset(("VALUATION", "FUNDAMENTAL", "CORPORATE"))
_COMPARED_MEASURES = ("cash_to_assets","debt_to_assets","debt_to_equity","pbt_margin","net_margin","gross_margin")

def _canon(x: Any) -> str: return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
def _hash(x: Any) -> str: return hashlib.sha256(_canon(x).encode()).hexdigest()


def _integrated_profile(ticker, record, bound, source, session):
    research = record.get("valuation_balance_sheet_divergence") or {}
    trajectory = research.get("multi_period_financial_context") or {}
    resilience = research.get("sector_relative_financial_resilience") or {}
    dimensions = (record.get("current_research_decision_input") or {}).get("dimensions") or {}
    low = research.get("status") == "AVAILABLE" and research.get("assessment", "").startswith("LOW_PB_")
    weak = trajectory.get("assessment") == "PERSISTENT_DETERIORATION" or resilience.get("assessment") == "COMPANY_SPECIFIC_WEAKNESS"
    strong = trajectory.get("assessment") in {"RECOVERY", "SUCCESSIVE_IMPROVEMENT"} or resilience.get("assessment") == "RESILIENCE_AGAINST_WEAK_PEERS"
    technical = dimensions.get("TECHNICAL") or {"state":"BLOCKED","reason_codes":["QUALIFIED_TECHNICAL_CONTEXT_ABSENT"]}
    timing_known = technical.get("state") in {"AVAILABLE","PARTIAL"} and record.get("evidence_currency") == "CURRENT_SESSION"
    condition = record.get("posture_condition_class")
    qualified_entry = timing_known and (bound.get("bull_case") or {}).get("case_status") == "CONDITIONAL"
    findings = []
    if low and weak:
        findings.append("VALUATION_DISCOUNT_WITH_FINANCIAL_DETERIORATION")
    if low and strong:
        findings.append("VALUATION_DISCOUNT_WITH_RESILIENCE_COUNTERTHESIS")
    if strong and timing_known and not qualified_entry:
        findings.append("FINANCIAL_STRENGTH_WITHOUT_FRESH_ENTRY_CONFIRMATION")
    if qualified_entry:
        findings.append("EXISTING_POLICY_QUALIFIED_ENTRY_CONDITION" if not weak else "QUALIFIED_ENTRY_CONDITION_WITH_FINANCIAL_COUNTEREVIDENCE")
    if resilience.get("assessment") == "DETERIORATION_SHARED_WITH_SECTOR_SAMPLE":
        findings.append("FINANCIAL_WEAKNESS_SHARED_WITH_RETAINED_SECTOR_SAMPLE")
    if not timing_known:
        findings.append("CURRENT_TIMING_COMPARISON_UNKNOWN")
    if research.get("status") != "AVAILABLE":
        findings.append("QUALIFIED_VALUATION_FINANCIAL_COMPARISON_UNKNOWN")
    if timing_known and (bound.get("bear_case") or {}).get("observed_adverse") is True:
        findings.append("OBSERVED_ADVERSE_STRUCTURE_DOWNSIDE_CONDITION")
    return {"ticker":ticker,"research_session":session,"source_integrated_identity":source,
        "source_decision_identity":record["decision_identity"],
        "research_action_posture":record["research_action_posture"],"posture_condition_class":condition,
        "research_action_policy_version":record["research_action_policy_version"],
        "evidence_currency":record.get("evidence_currency"),"finding_codes":findings,
        "research_conclusion":" ".join(INTEGRATED_EXPLANATIONS[f] for f in findings) or "The available sources do not establish a differentiated financial/timing thesis; inspect the independent evidence and gaps.",
        "valuation_financial_research":copy.deepcopy(research),
        "fundamental_synthesis":copy.deepcopy(record.get("fundamental_synthesis")),
        "timing_and_conditions":{k:copy.deepcopy(v) for k,v in bound.items() if k != "integrated_context"},
        "decision_fitness_dimensions":{name:({"state":d.get("state"),"reason_codes":copy.deepcopy(d.get("reason_codes")),
                "authority":copy.deepcopy(d.get("authority")),"detail":"SEE_SOURCE_DECISION_IDENTITY"}
            if name in _SUMMARY_ONLY_DIMENSIONS else copy.deepcopy(d)) for name,d in dimensions.items()},
        "trigger":copy.deepcopy(record.get("trigger")),"invalidation":copy.deepcopy(record.get("invalidation")),
        "counter_thesis":copy.deepcopy(record.get("counter_thesis") or []),
        "material_uncertainties":copy.deepcopy(record.get("material_uncertainties") or []),
        "corporate_evidence":copy.deepcopy(record.get("corporate_intelligence_context") or {}),
        "participation":copy.deepcopy(record.get("participation") or {}),
        "source_identities":copy.deepcopy(record.get("source_identities") or {}),
        "liquidity":copy.deepcopy(dimensions.get("LIQUIDITY") or {"state":"BLOCKED","reason_codes":["LIQUIDITY_RESEARCH_ABSENT"]}),
        "limitations":["CONDITIONAL_CURRENT_RESEARCH_NOT_AN_EXECUTION_INSTRUCTION","FINANCIAL_REPORT_PERIODS_ARE_NOT_CURRENT_TRADING_SIGNALS",
            "OWNER_POLICY_IS_PASSED_THROUGH_UNCHANGED","NO_PORTFOLIO_OR_HOLDINGS_ASSUMED"],"is_actionable":False}


def _pb_signature(research):
    """Same source/accounting keys used by the existing divergence peer owner."""
    from stocklookup_core.valuation import current_research_valuation_context as owner
    valuation = research.get("valuation") or {}
    method = valuation.get("source_method") or {}
    peer = valuation.get("peer_context") or {}
    if research.get("status") != "AVAILABLE" or peer.get("status") != "READY_RESEARCH_ONLY":
        return None
    basis = method.get("equity_monetary_basis") or {}
    price_basis = method.get("market_cap_monetary_basis") or {}
    return (owner._peer_key({"entity_class":research.get("issuer_type")},method),valuation.get("cohort_id"),
        method.get("book_period"),method.get("statement_scope"),method.get("equity_definition"),
        (method.get("equity_lineage") or {}).get("provider"),basis.get("currency"),basis.get("normalized_unit"),
        basis.get("native_scale"),basis.get("basis_status"),price_basis.get("basis_status"),price_basis.get("basis_source"))


def _integrated_pair(left, right, profiles):
    a,b = profiles[left],profiles[right]
    ar,br = a["valuation_financial_research"],b["valuation_financial_research"]
    numeric,exclusions = {},{}
    signature = _pb_signature(ar)
    if signature and signature[0] and signature == _pb_signature(br):
        numeric["research_pb"] = {"left":ar["valuation"]["source_method"]["value"],"right":br["valuation"]["source_method"]["value"],
            "left_percentile":ar["valuation"]["peer_context"]["percentile"],"right_percentile":br["valuation"]["peer_context"]["percentile"],
            "basis":copy.deepcopy(ar["valuation"]["source_method"]),"source_paths":[f"profiles.{t}.valuation_financial_research.valuation" for t in (left,right)]}
    else:
        exclusions["research_pb"] = "SAME_SECTOR_METHOD_PERIOD_SCOPE_SHARE_AND_MONETARY_BASIS_NOT_ESTABLISHED"
    ac = (ar.get("sector_relative_financial_resilience") or {}).get("metric_comparisons") or {}
    bc = (br.get("sector_relative_financial_resilience") or {}).get("metric_comparisons") or {}
    for fid in _COMPARED_MEASURES:
        x,y = ac.get(fid) or {},bc.get(fid) or {}
        if (x.get("status") == y.get("status") == "AVAILABLE" and x.get("comparability_basis") == y.get("comparability_basis")
                and x.get("periods") == y.get("periods") and x.get("peer_members") == y.get("peer_members")):
            numeric[fid] = {"left":((ar.get("financial_measures") or {}).get(fid) or {}).get("value"),
                "right":((br.get("financial_measures") or {}).get(fid) or {}).get("value"),
                "basis":copy.deepcopy(x["comparability_basis"]),"periods":list(x["periods"]),
                "left_trajectory":copy.deepcopy(x),"right_trajectory":copy.deepcopy(y),
                "source_paths":[f"profiles.{t}.valuation_financial_research.financial_measures.{fid}" for t in (left,right)]}
        else:
            exclusions[fid] = "QUALIFIED_SAME_WINDOW_SECTOR_ACCOUNTING_PEER_COMPARISON_UNAVAILABLE"
    contrasts = []
    if a["finding_codes"] != b["finding_codes"]:
        contrasts.append({"observation":"DIFFERENT_FINANCIAL_OR_TIMING_RESEARCH_CONDITIONS",
            "left":a["finding_codes"],"right":b["finding_codes"],"source_paths":[f"profiles.{t}.finding_codes" for t in (left,right)]})
    if a["posture_condition_class"] != b["posture_condition_class"]:
        contrasts.append({"observation":"DIFFERENT_EXISTING_STRATEGY_CONDITIONS","left":a["posture_condition_class"],
            "right":b["posture_condition_class"],"source_paths":[f"profiles.{t}.timing_and_conditions" for t in (left,right)]})
    return {"left":left,"right":right,"comparability":"PARTIALLY_COMPARABLE" if numeric else "INDEPENDENT_RESEARCH_CONTEXT_ONLY",
        "qualified_numerical_axes":numeric,"exclusions":exclusions,"conditional_contrasts":contrasts,
        "conclusion":"Compare the cited financial theses alongside each security's unchanged policy conditions and counterevidence. A valuation discount does not override deterioration or an unconfirmed entry condition.",
        "risk_reward":"SOURCE_TRIGGER_AND_INVALIDATION_CONDITIONS_ONLY_NO_RETURN_OR_RISK_REWARD_ESTIMATE",
        "preference":"NO_WINNER_OR_ALLOCATION_INFERRED","is_actionable":False}


def build_integrated_comparisons(requests, *, integrated_decision, bind_scenarios):
    """Existing shortlist comparison, using verified current decision inputs (2–5 selected securities).

    Batch admission verifies the source once. No caller-provided measurements, lenses,
    policy, portfolio state or prevalidated-token shortcut can enter this boundary.
    ``bind_scenarios`` is the existing root owner ``current_evidence_bound_scenario.
    bind_integrated_scenarios``, supplied by the composition root so this core module takes
    no backward dependency; its output is re-checked against the verified source below.
    """
    if not isinstance(integrated_decision, Mapping):
        raise ValueError("SELECTED_COMPARISON_REQUIRES_VERIFIED_INTEGRATED_DECISION")
    session = integrated_decision.get("session")
    selections = []
    for request in requests:
        if not isinstance(request,Mapping) or set(request) - {"tickers","research_session"}:
            raise ValueError("UNSUPPORTED_SELECTED_COMPARISON_REQUEST")
        raw = request.get("tickers")
        if not isinstance(raw,(list,tuple)) or not all(isinstance(t,str) and t == t.strip().upper() for t in raw):
            raise ValueError("EXPLICIT_UNIQUE_UPPERCASE_TICKERS_REQUIRED")
        if not 2 <= len(raw) <= 5 or len(set(raw)) != len(raw):
            raise ValueError("SELECT_TWO_TO_FIVE_UNIQUE_SECURITIES")
        if request.get("research_session") != session:
            raise ValueError("MIXED_OR_UNKNOWN_RESEARCH_SESSION")
        selections.append(tuple(raw))
    if not selections:
        raise ValueError("EXPLICIT_COMPARISON_REQUEST_REQUIRED")
    tickers = sorted({t for selected in selections for t in selected})
    binding = bind_scenarios(session=session,integrated_decision=integrated_decision,tickers=tickers)
    if (binding.get("integrated_artifact_identity") != integrated_decision.get("artifact_identity")
            or binding.get("session") != session or binding.get("research_action_policy_version") != "v2"
            or set(binding.get("records") or {}) != set(tickers)
            or any(binding["records"][t].get("decision_identity") != integrated_decision["records"][t].get("decision_identity") for t in tickers)):
        raise ValueError("SELECTED_COMPARISON_SCENARIO_BINDING_MISMATCH")
    profiles = {t:_integrated_profile(t,integrated_decision["records"][t],binding["records"][t],
        integrated_decision["artifact_identity"],session) for t in tickers}
    outputs = []
    for request,selected in zip(requests,selections):
        output = {"schema_version":"1.1.0","contract_version":"evidence_aware_candidate_comparison/v1",
            "mode":"INTEGRATED_CURRENT_RESEARCH","comparison_request":dict(request),"research_session":session,
            "ordered_tickers":list(selected),"source_artifact_identities":{"integrated_decision":integrated_decision["artifact_identity"],
                **copy.deepcopy(integrated_decision.get("source_artifacts") or {})},
            "profiles":{t:copy.deepcopy(profiles[t]) for t in selected},
            "pairwise":[_integrated_pair(a,b,profiles) for a,b in combinations(selected,2)],
            "questions_requiring_human_judgment":["Do the next compatible financial observations confirm the thesis or expose one-off balance-sheet movements?",
                "Are the source's confirmation and invalidation conditions still qualified for the intended research session?",
                "Could missing profitability, catalysts or liquidity evidence invalidate the apparent opportunity?"],
            "authority_boundary":{"not_ranking_or_recommendation":True,"no_composite_score_or_winner":True,
                "no_mutation_of_source_artifacts":True,"historical_pit_liquidity_sizing_valuation":"NOT_PROMOTED"}}
        output["comparison_identity"] = "candidate_comparison:"+_hash(output)
        output["output_identity"] = "candidate_comparison_output:"+_hash(output)
        outputs.append(output)
    return outputs


def build_integrated_comparison(request, *, integrated_decision, bind_scenarios):
    return build_integrated_comparisons([request],integrated_decision=integrated_decision,bind_scenarios=bind_scenarios)[0]


def verified_comparison_for_source(comparison, *, integrated_decision, tickers_in_scope):
    """Embed a comparison built upstream: identity, source and scope must all match."""
    view = verified_integrated_comparison(comparison)
    if (not isinstance(integrated_decision, Mapping)
            or view["source_artifact_identities"].get("integrated_decision") != integrated_decision.get("artifact_identity")
            or view["research_session"] != integrated_decision.get("session")):
        raise ValueError("SELECTED_COMPARISON_SOURCE_MISMATCH")
    if not set(view["ordered_tickers"]) <= set(tickers_in_scope):
        raise ValueError("SELECTED_COMPARISON_OUTSIDE_SCOPE")
    return view


def verified_integrated_comparison(comparison):
    body = {k:v for k,v in comparison.items() if k not in {"output_identity","comparison_identity"}}
    if (comparison.get("contract_version") != "evidence_aware_candidate_comparison/v1"
            or comparison.get("mode") != "INTEGRATED_CURRENT_RESEARCH"
            or comparison.get("comparison_identity") != "candidate_comparison:"+_hash(body)
            or comparison.get("output_identity") != "candidate_comparison_output:"+_hash({**body,"comparison_identity":comparison["comparison_identity"]})):
        raise ValueError("SELECTED_COMPARISON_IDENTITY_INVALID")
    return copy.deepcopy(comparison)


def _md_value(value):
    return "UNKNOWN" if value is None else (f"{value:.4g}" if isinstance(value,float) else str(value))


def _md_list(value):
    return ", ".join(map(str, value if isinstance(value, (list, tuple)) else [value])) or "none"


def _md_boundary(row, level_key, distance_key):
    row = row or {}
    condition = row.get("condition") or {}
    text = str(row.get("trigger_type") or row.get("invalidation_method") or "UNKNOWN")
    if row.get(level_key) is not None:
        text += f" at {_md_value(row.get(level_key))} (close {condition.get('operator') or '?'} level; distance {_md_value(row.get(distance_key))})"
    if row.get("trigger_state"):
        text += f"; state {row['trigger_state']}"
    return text + f"; machine evaluation {condition.get('status', 'UNKNOWN')}"


def integrated_comparison_markdown(comparison):
    view = verified_integrated_comparison(comparison)
    lines = ["## Selected investment opportunity research", "",
        f"Session: {view['research_session']}; source: `{view['source_artifact_identities']['integrated_decision']}`; comparison: `{view['comparison_identity']}`.", ""]
    for ticker,profile in view["profiles"].items():
        cases = profile["timing_and_conditions"]
        dims = profile["decision_fitness_dimensions"]
        research = profile["valuation_financial_research"]
        valuation = research.get("valuation") or {}
        method = valuation.get("source_method") or {}
        peer = valuation.get("peer_context") or {}
        liquidity = profile["liquidity"]
        lines += [f"### {ticker}", "",
            f"- Existing policy (unchanged): **{profile['research_action_posture']}** / {profile['posture_condition_class']}; evidence currency {profile['evidence_currency']}.",
            f"- Research conclusion: {profile['research_conclusion']}",
            f"- Valuation: research P/B {_md_value(method.get('value'))} (book {method.get('book_period', 'UNKNOWN')}, {method.get('statement_scope', 'UNKNOWN')}, share basis {method.get('share_basis', 'UNKNOWN')}); "
            f"peer percentile {_md_value(peer.get('percentile'))} in `{valuation.get('cohort_id', 'UNKNOWN')}`; finding {research.get('assessment', 'UNKNOWN')}.",
            f"- Financial trajectory: {(research.get('multi_period_financial_context') or {}).get('assessment', 'UNKNOWN')}; "
            f"sector-relative: {(research.get('sector_relative_financial_resilience') or {}).get('assessment', 'UNKNOWN')}.",
            f"- Technical structure: {(dims.get('TECHNICAL') or {}).get('state', 'UNKNOWN')}. Confirmation: {_md_boundary(profile['trigger'], 'trigger_level', 'distance_to_trigger_pct')}.",
            f"- Invalidation: {_md_boundary(profile['invalidation'], 'invalidation_level', 'distance_to_invalidation_pct')}.",
            "- Existing scenario cases: " + "; ".join(
                f"{name.split('_')[0]} {(cases.get(name) or {}).get('case_status', 'UNKNOWN')} ({(cases.get(name) or {}).get('reason_code', 'UNKNOWN')})"
                for name in ("bull_case", "base_case", "bear_case")) + "; probabilities uncalibrated.",
            f"- Liquidity research: {liquidity.get('state', 'UNKNOWN')}; execution capacity {(liquidity.get('execution') or {}).get('state', 'UNKNOWN')} (no sizing authority).",
            f"- Counter-thesis: {_md_list(profile['counter_thesis']) if profile['counter_thesis'] else 'none recorded'}.",
            f"- Material uncertainties: {_md_list(profile['material_uncertainties']) if profile['material_uncertainties'] else 'none recorded'}.",
            "", "| Financial measure | Reported ratio | Own trajectory | Sector-relative evidence |", "|---|---|---|---|"]
        for fid in _COMPARED_MEASURES:
            metric = (research.get("financial_measures") or {}).get(fid)
            if metric is None:
                continue
            trend = (((research.get("multi_period_financial_context") or {}).get("metric_trajectories") or {}).get(fid) or {})
            sector = (((research.get("sector_relative_financial_resilience") or {}).get("metric_comparisons") or {}).get(fid) or {})
            value = _md_value(metric.get("value")) if metric.get("status") == "AVAILABLE" else "UNKNOWN"
            lines.append(f"| {fid} | {value} | {trend.get('assessment', 'UNKNOWN')} | {sector.get('assessment', 'UNKNOWN')} |")
        lines += ["", f"Financial evidence: `{research.get('source_context_identity', 'UNKNOWN')}`; exact periods and source observations remain in the companion JSON.", ""]
    for pair in view["pairwise"]:
        lines += [f"### {pair['left']} versus {pair['right']}", "", f"- Comparability: {pair['comparability']}."]
        for axis,row in pair["qualified_numerical_axes"].items():
            lines.append(f"- {axis}: {pair['left']} {_md_value(row.get('left'))} vs {pair['right']} {_md_value(row.get('right'))} (same qualified sector/method/period basis).")
        for contrast in pair["conditional_contrasts"]:
            lines.append(f"- {contrast['observation']}: {pair['left']} {_md_list(contrast['left'])}; {pair['right']} {_md_list(contrast['right'])}.")
        if pair["exclusions"]:
            reasons = sorted(set(pair["exclusions"].values()))
            lines.append(f"- Not numerically comparable: {', '.join(pair['exclusions'])} ({'; '.join(reasons)}).")
        lines += [f"- {pair['conclusion']}", ""]
    lines += ["Current Research only. Source reporting periods are preserved; no target price, probability, score, winner, portfolio sizing or execution authority."]
    return "\n".join(lines) + "\n"


def validate_request(request: Mapping[str, Any], known: set[str], session: str) -> tuple[str, ...]:
    tickers = tuple(str(x).upper() for x in request.get("tickers", ()))
    summary = request.get("mode") == "REVIEW_PACK_SUMMARY"
    if not (2 <= len(tickers) <= (25 if summary else 10)) or len(set(tickers)) != len(tickers): raise ValueError("INVALID_SHORTLIST_SIZE")
    if any(t not in known for t in tickers): raise ValueError("UNKNOWN_TICKER")
    if request.get("research_session") != session: raise ValueError("MIXED_OR_UNKNOWN_RESEARCH_SESSION")
    if not set(request.get("dimensions", ())).issubset(SUPPORTED): raise ValueError("UNSUPPORTED_COMPARISON_DIMENSION")
    return tickers

def _cell(value: Any, authority: str, lineage: str, verdict: str = "COMPARABLE") -> dict[str, Any]:
    return {"value": value, "authority_tier": authority, "evidence_lineage": lineage, "comparability": verdict}

def _technical(tickers: Sequence[str], daily: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows=[]
    for metric in TECHNICAL:
        cells={t:_cell(daily[t]["ai_ready_brief"]["facts"].get(metric), "DERIVED_PROXY" if metric=="relative_volume_provider_scoped" else "SHADOW_ONLY", f"daily_research.{t}.facts.{metric}", "MISSING_INPUT" if daily[t]["ai_ready_brief"]["facts"].get(metric) is None else "COMPARABLE") for t in tickers}
        rows.append({"dimension":metric,"section":"CURRENT_OBSERVABLE_STATE","metric_identity":metric,"method":"retained_daily_research/v1","session":daily[tickers[0]]["ai_ready_brief"]["facts"]["session"],"unit":"VND" if metric=="close" else "DECIMAL_OR_STATE","cells":cells,"comparability":"COMPARABLE" if all(c["comparability"]=="COMPARABLE" for c in cells.values()) else "MISSING_INPUT"})
    trend={t:_cell(daily[t]["research_summary"]["trend_state"],"SHADOW_ONLY",f"daily_research.{t}.trend_state") for t in tickers}
    rows.append({"dimension":"trend_state","section":"CURRENT_OBSERVABLE_STATE","cells":trend,"comparability":"COMPARABLE"})
    return rows

def _relative(tickers: Sequence[str], contexts: Mapping[str, Any]) -> list[dict[str, Any]]:
    source=[contexts[t] for t in tickers]; ids={x["cohort"]["cohort_identity"] for x in source if x.get("cohort") and x["context_status"]=="AVAILABLE"}
    verdict="COMPARABLE" if len(ids)==1 and len(source)==len(ids)*0+len(source) and all(x["context_status"]=="AVAILABLE" for x in source) else "NOT_COMPARABLE_COHORT"
    cells={}
    for t in tickers:
        row=contexts[t]; cells[t]=_cell(row.get("cohort",{}).get("cohort_identity"),row.get("relative_context_authority","UNAVAILABLE"),f"relative_context.{t}", verdict if row["context_status"]=="AVAILABLE" else "MISSING_INPUT")
    return [{"dimension":"relative_context","section":"RELATIVE_CONTEXT","comparability":verdict,"reason":"DIRECT_PERCENTILE_COMPARISON_REQUIRES_ONE_SHARED_COHORT_IDENTITY","cells":cells}]

def _fundamentals(tickers: Sequence[str], daily: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{"dimension":"individual_like_for_like_fundamental_values","section":"FUNDAMENTAL_EVIDENCE","comparability":"COMPARISON_UNAVAILABLE","reason":"NO_INDIVIDUAL_LIKE_FOR_LIKE_FUNDAMENTAL_METRIC_RETAINED_IN_DAILY_RESEARCH","cells":{t:_cell(None,daily[t]["research_summary"]["fundamental_authority"],f"daily_research.{t}.fundamental_context","NOT_COMPARABLE_SEMANTICS") for t in tickers}}]

def _lenses(tickers: Sequence[str], eligibility: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows=[]
    for lens in sorted(next(iter(eligibility.values()))["lenses"]):
        rows.append({"dimension":lens,"section":"RESEARCH_LENS_AVAILABILITY","comparability":"COMPARABLE","cells":{t:_cell(eligibility[t]["lenses"][lens]["eligibility"],eligibility[t]["lenses"][lens]["authority_ceiling"],f"eligibility.{t}.{lens}") for t in tickers}})
    return rows

def _statements(tickers: Sequence[str], daily: Mapping[str, Any]) -> list[dict[str, Any]]:
    out=[]
    for left,right in zip(tickers,tickers[1:]):
        for metric,label in (("momentum_20d","20-day momentum"),("volatility_20d","observed volatility")):
            a,b=daily[left]["ai_ready_brief"]["facts"].get(metric),daily[right]["ai_ready_brief"]["facts"].get(metric)
            if isinstance(a,(int,float)) and isinstance(b,(int,float)) and a!=b:
                relation="higher" if a>b else "lower"; out.append({"classification":"FACT","statement":f"{left} has {relation} {label} than {right}.","fields":[f"daily_research.{left}.facts.{metric}",f"daily_research.{right}.facts.{metric}"]})
    return out

def build(request: Mapping[str, Any], *, product: Mapping[str, Any], relative: Mapping[str, Any], eligibility: Mapping[str, Any], scenarios: Mapping[str, Any], dossiers: Mapping[str, Any], tasks: Mapping[str, Any], events: Mapping[str, Any], screener: Mapping[str, Any], review_pack: Mapping[str, Any], market_context: Mapping[str, Any]|None=None, downside_context: Mapping[str, Any]|None=None, price_structure: Mapping[str, Any]|None=None, setup_context: Mapping[str, Any]|None=None) -> dict[str, Any]:
    daily={x["ticker"]:x for x in product["stock_research"]}; tickers=validate_request(request,set(daily),product["daily_market_research"]["session"])
    contexts={x["ticker"]:x for x in relative["records"]}; lenses={x["ticker"]:x for x in eligibility["records"]}; scen={x["ticker"]:x for x in scenarios["scenarios"]}; ev={x["ticker"]:x for x in events["records"]}
    matrix=[]
    dimensions=set(request["dimensions"])
    if "CURRENT_OBSERVABLE_STATE" in dimensions: matrix += _technical(tickers,daily)
    if "RELATIVE_CONTEXT" in dimensions: matrix += _relative(tickers,contexts)
    if "FUNDAMENTAL_EVIDENCE" in dimensions: matrix += _fundamentals(tickers,daily)
    if "RESEARCH_LENS_AVAILABILITY" in dimensions: matrix += _lenses(tickers,lenses)
    if "SCENARIO_COUNTER_THESIS" in dimensions:
        matrix.append({"dimension":"scenario_counter_thesis","section":"SCENARIO_COUNTER_THESIS","comparability":"COMPARABLE","cells":{t:_cell({"scenario_status":scen.get(t,{}).get("scenario_qualification_status","MISSING"),"counter_thesis":dossiers[t]["counter_thesis_hash"],"catalyst_status":ev[t]["catalyst_research_status"]},"RESEARCH_SHADOW",f"scenario_dossier_event.{t}","MISSING_INPUT" if t not in scen else "COMPARABLE") for t in tickers}})
    if "EVIDENCE_QUALITY" in dimensions:
        matrix.append({"dimension":"evidence_quality","section":"EVIDENCE_QUALITY","comparability":"COMPARABLE","cells":{t:_cell({"fundamental_authority":daily[t]["research_summary"]["fundamental_authority"],"warnings":daily[t]["warnings"],"open_task_count":sum(x["ticker"]==t for x in tasks.values())},daily[t]["research_summary"]["fundamental_authority"],f"dossier_task_daily.{t}") for t in tickers}})
    if market_context:
        matrix.append({"dimension":"shared_market_context","section":"MARKET_CONTEXT","comparability":"COMPARABLE","shared_context":True,"value":{"trend_descriptor":market_context['breadth']['trend']['descriptor']['descriptor'],"momentum_descriptor":market_context['breadth']['momentum']['descriptor']['descriptor'],"positive_trend_research_count":market_context['research_participation']['positive_trend_research_count'],"cohort_authority":market_context['cohort']['authority']},"authority_tier":"EMPIRICAL_ACTIVE_SHADOW_ONLY","evidence_lineage":market_context['artifact_identity']})
    if downside_context:
        by={x['ticker']:x for x in downside_context['records']}
        matrix.append({"dimension":"downside_uncertainty_vector","section":"DOWNSIDE_UNCERTAINTY","comparability":"COMPARABLE","cells":{t:_cell({'technical':by[t]['domains']['TECHNICAL_DOWNSIDE_CONTEXT']['status'],'evidence_uncertainty':by[t]['domains']['EVIDENCE_UNCERTAINTY']['status'],'execution':by[t]['domains']['EXECUTION_RISK_STATUS']['status'],'human_review_reasons':by[t]['human_downside_review_reasons']},'RESEARCH_SHADOW',by[t]['domains']['TECHNICAL_DOWNSIDE_CONTEXT']['source_identity']) for t in tickers}})
    if price_structure:
        by={x['ticker']:x for x in price_structure['records']}
        matrix.append({'dimension':'price_structure','section':'PRICE_STRUCTURE','comparability':'COMPARABLE','cells':{t:_cell({'state':by[t]['structure_status'],'range_position':by[t].get('range_position'),'resistance_distance':by[t]['levels']['prior_19_session_close_resistance']['distance_from_close'],'support_distance':by[t]['levels']['prior_19_session_close_support']['distance_from_close']},'SHADOW_ONLY',price_structure['artifact_identity']) for t in tickers}})
    if setup_context:
        by={x['ticker']:x for x in setup_context['records']}; shared=set.intersection(*(set(by[t]['active_setup_ids']) for t in tickers)) if tickers else set(); union=set.union(*(set(by[t]['active_setup_ids']) for t in tickers)) if tickers else set()
        matrix.append({'dimension':'setup_context','section':'SETUP_CONTEXT','comparability':'COMPARABLE','shared_active_setup_ids':sorted(shared),'differing_active_setup_ids':sorted(union-shared),'cells':{t:_cell({'active_setup_ids':by[t]['active_setup_ids'],'record_setup_state':by[t]['record_setup_state'],'active_setup_authorities':by[t]['active_setup_authorities'],'unavailable_setup_reasons':by[t]['unavailable_setup_reasons']},'RESEARCH_SHADOW',setup_context['artifact_identity']) for t in tickers}})
    sources={"daily_product":product["artifact_identity"],"relative":relative["artifact_identity"],"eligibility":eligibility["artifact_identity"],"scenario":scenarios["artifact_identity"],"event":events["artifact_identity"],"screener":screener["artifact_identity"],"review_pack":review_pack["artifact_identity"],"market_context":market_context.get('artifact_identity') if market_context else None,"downside_context":downside_context.get('artifact_identity') if downside_context else None,"price_structure":price_structure.get('artifact_identity') if price_structure else None,"setup_context":setup_context.get('artifact_identity') if setup_context else None}
    output={"schema_version":"1.0.0","contract_version":"evidence_aware_candidate_comparison/v1","comparison_request":dict(request),"research_session":request["research_session"],"ordered_tickers":list(tickers),"source_artifact_identities":sources,"matrix":matrix,"pairwise_observable_statements":_statements(tickers,daily),"questions_requiring_human_judgment":["Evidence provenance and missing capability are not measures of company quality or investment attractiveness."],"authority_boundary":{"not_ranking_or_recommendation":True,"no_composite_score_or_winner":True,"no_mutation_of_source_artifacts":True,"historical_pit_liquidity_sizing_valuation":"NOT_PROMOTED"}}
    output["comparison_identity"]="candidate_comparison:"+_hash({"request":request,"sources":sources,"matrix":matrix}); output["output_identity"]="candidate_comparison_output:"+_hash(output)
    return output
