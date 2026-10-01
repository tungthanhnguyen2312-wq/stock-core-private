"""Fail-closed intrinsic valuation over explicitly qualified canonical inputs."""
from __future__ import annotations
import math
from typing import Any, Mapping
SCHEMA_VERSION=METHOD_VERSION="1.0.0"

def n(v):
 if v is None or isinstance(v,bool): return None
 try: v=float(v)
 except (TypeError,ValueError,OverflowError): return None
 return None if not math.isfinite(v) else (int(v) if v.is_integer() else v)
def out(name,state="unavailable",**kw):
 x={"method":name,"method_version":METHOD_VERSION,"state":state,"applicability":"unknown","valuation_date":None,"historical_input_periods":[],"statement_scope":None,"forecast_horizon":None,"assumptions":[],"required_inputs":[],"used_inputs":[],"missing_inputs":[],"scenario_name":None,"sensitivity_dimensions":[],"enterprise_value":None,"equity_value":None,"per_share_value":None,"warnings":[],"interpretation_limits":["No target price, recommendation, or forced model output."],"is_actionable":False};x.update(kw);return x
def q(r,metric):
 if not isinstance(r,Mapping) or r.get("canonical_metric")!=metric:return None,"required_canonical_input_missing"
 if r.get("quality_state")!="available" or r.get("statement_scope") not in {"consolidated","separate"}:return None,"canonical_scope_or_quality_unqualified"
 if not isinstance(r.get("period_identity"),Mapping):return None,"financial_period_missing"
 v=n(r.get("value"));return (v,None) if v is not None else (None,"canonical_value_missing_or_malformed")
def evaluate_intrinsic_valuation(inputs:Mapping[str,Any]|None,reference_at:str|None=None):
 d=inputs if isinstance(inputs,Mapping) else {}; fin=d.get("financial") if isinstance(d.get("financial"),Mapping) else {}; entity=str(d.get("entity_type") or "unknown"); methods={}
 # Both methods below are ordinary-corporate formulations: FCFF nets ordinary operating
 # cash flow, CapEx, and interest-bearing debt (a bank's funding is customer deposits
 # and interbank placements, never qualified here as total_debt); Net-Net nets
 # current_assets/inventory/receivables against total_liabilities, a classification a
 # bank's balance sheet does not use. Both are inapplicable to the bank archetype
 # itself, not merely missing inputs -- entity_type=="bank" only, never ticker-specific.
 if entity in {"bank", "securities", "insurance", "finance_company"}:
  return {"schema_version":SCHEMA_VERSION,"reference_at":reference_at,"status":"unknown","methods":{
    "fcff_dcf": out("fcff_dcf","inapplicable",applicability="inapplicable",
        warnings=["fcff_ordinary_operating_cash_flow_capex_and_interest_bearing_debt_formulation_not_qualified_for_non_corporate_financial_archetype"]),
    "net_net": out("net_net","inapplicable",applicability="inapplicable",
        warnings=["net_net_current_assets_inventory_receivables_identity_not_qualified_for_non_corporate_financial_balance_sheet_structure"]),
   }, "warnings":["DDM, FCFE, RNAV, and SOTP are absent until their source contracts are qualified."]}
 # FCFF requires standalone compatible cash-flow components, explicit forecast and sourced WACC/terminal assumptions.
 vals={}; missing=[]
 for m in ("operating_cash_flow","capital_expenditure","total_debt","cash_and_equivalents"):
  vals[m],bad=q(fin.get(m),m)
  if bad:missing.append(bad+":"+m)
 periods=[fin.get(m,{}).get("period_identity",{}).get("period") for m in vals if isinstance(fin.get(m),Mapping)]
 scopes={fin.get(m,{}).get("statement_scope") for m in vals if isinstance(fin.get(m),Mapping)}
 assumptions=d.get("fcff_assumptions") if isinstance(d.get("fcff_assumptions"),Mapping) else {}
 assumption_ok=all(assumptions.get(k) is not None and isinstance(assumptions.get(k+"_source"),str) for k in ("wacc","terminal_growth","forecast_fcff"))
 if not missing and len(set(periods))==1 and len(scopes)==1 and assumption_ok and vals["capital_expenditure"]>=0:
  ev=assumptions["forecast_fcff"]/(assumptions["wacc"]-assumptions["terminal_growth"]) if assumptions["wacc"]>assumptions["terminal_growth"] else None
  methods["fcff_dcf"]=out("fcff_dcf","available" if ev is not None else "incomparable",applicability="applicable",valuation_date=reference_at,historical_input_periods=periods,statement_scope=scopes.pop(),forecast_horizon=assumptions.get("forecast_horizon"),assumptions=[{"name":k,"value":assumptions[k],"source":assumptions[k+"_source"]} for k in ("wacc","terminal_growth","forecast_fcff")],used_inputs=list(vals),sensitivity_dimensions=["wacc","terminal_growth"],enterprise_value=ev,warnings=[] if ev is not None else ["terminal_growth_must_be_below_wacc"])
 else: methods["fcff_dcf"]=out("fcff_dcf","unavailable",missing_inputs=missing+([] if assumption_ok else ["sourced_wacc_terminal_growth_and_forecast"]),warnings=["FCFF is not derived from unknown, cumulative, or incompatible cash flow."])
 # Net-Net needs qualified balance-sheet components and a share basis consistent with
 # them. "period_end" is the semantically correct identity here (equity-base
 # consistency with a balance-sheet snapshot); "basic"/"diluted" (weighted-average,
 # EPS-style) remain accepted for backward compatibility but are not what this
 # method's own documentation asks for. Never widened to accept an unrelated identity
 # such as a live/valuation-date share count, and never substituted from one to another.
 net={}; miss=[]
 for m in ("current_assets","cash_and_equivalents","receivables","inventory","total_liabilities"):
  net[m],bad=q(fin.get(m),m)
  if bad:miss.append(bad+":"+m)
 share=d.get("share_count") if isinstance(d.get("share_count"),Mapping) else {}; sv=n(share.get("value"))
 ps=[fin.get(m,{}).get("period_identity",{}).get("period") for m in net if isinstance(fin.get(m),Mapping)]; ss={fin.get(m,{}).get("statement_scope") for m in net if isinstance(fin.get(m),Mapping)}
 # If the share count declares its own period, it must match the balance-sheet
 # components' single common period; if it declares none, we don't retroactively
 # require one (legacy callers with no period_identity are unaffected).
 share_period=share.get("period_identity",{}).get("period") if isinstance(share.get("period_identity"),Mapping) else None
 share_period_ok=share_period is None or (len(ps)>0 and len(set(ps))==1 and share_period==ps[0])
 shareok=sv is not None and sv>0 and share.get("semantics") in {"basic","diluted","period_end"} and share_period_ok
 if not miss and len(set(ps))==1 and len(ss)==1 and shareok:
  equity=net["cash_and_equivalents"]+net["receivables"]+net["inventory"]-net["total_liabilities"]
  methods["net_net"]=out("net_net","available",applicability="applicable",valuation_date=reference_at,historical_input_periods=ps,statement_scope=ss.pop(),used_inputs=list(net)+["share_count"],equity_value=equity,per_share_value=equity/sv,is_actionable=bool(d.get("current_price_actionable") is True),warnings=[] if d.get("current_price_actionable") is True else ["current_price_not_actionable"])
 else: methods["net_net"]=out("net_net","unavailable",missing_inputs=miss+([] if shareok else ["qualified_share_count"]))
 return {"schema_version":SCHEMA_VERSION,"reference_at":reference_at,"status":"available" if any(x["state"]=="available" for x in methods.values()) else "unknown","methods":methods,"warnings":["DDM, FCFE, RNAV, and SOTP are absent until their source contracts are qualified."]}


# Current Research uses the legacy evaluators below only after a stronger governed
# input/assumption boundary. No legacy source label is upgraded into this contract.
import copy
import hashlib
import json
from collections import Counter
from datetime import date

CURRENT_SCENARIO_CONTRACT = "current_research_intrinsic_scenario/v1"
ASSUMPTION_CONTRACT = "current_research_valuation_assumption/v1"
CASES = ("BEAR", "BASE", "BULL")
METHODS = ("FCFF_DCF", "FCFE", "DDM", "RESIDUAL_INCOME", "RNAV", "SOTP", "NET_NET", "REVERSE_FCFF")
FINANCIAL_FAMILIES = {"bank", "securities", "insurance", "finance_company"}
IMPLEMENTED = {"FCFF_DCF", "NET_NET", "REVERSE_FCFF"}
REQUIRED_FINANCIAL = {
    "FCFF_DCF": ("operating_cash_flow", "capital_expenditure", "total_debt", "cash_and_equivalents"),
    "NET_NET": ("current_assets", "cash_and_equivalents", "receivables", "inventory", "total_liabilities"),
    "REVERSE_FCFF": ("operating_cash_flow", "capital_expenditure", "total_debt", "cash_and_equivalents"),
    "FCFE": ("qualified_equity_cash_flow",), "DDM": ("qualified_dividend_per_share",),
    "RESIDUAL_INCOME": ("common_equity_book_value", "attributable_net_income"),
    "RNAV": ("reproducible_asset_components",), "SOTP": ("reproducible_segment_components",),
}
ASSUMPTION_DEFINITIONS = {
    "wacc": ("DECIMAL_RATE", "NOMINAL_COST_OF_CAPITAL"),
    "terminal_growth": ("DECIMAL_RATE", "PERPETUAL_NOMINAL_FCFF_GROWTH"),
    "forecast_fcff": ("MONEY", "NEXT_PERIOD_STEADY_STATE_FCFF"),
    "cash_realization_ratio": ("DECIMAL_RATIO", "CASH_COMPONENT_REALIZATION_RATIO"),
    "receivables_realization_ratio": ("DECIMAL_RATIO", "RECEIVABLES_COMPONENT_REALIZATION_RATIO"),
    "inventory_realization_ratio": ("DECIMAL_RATIO", "INVENTORY_COMPONENT_REALIZATION_RATIO"),
    "growth_lower": ("DECIMAL_RATE", "ADMISSIBLE_TERMINAL_GROWTH_LOWER_BOUND"),
    "growth_upper": ("DECIMAL_RATE", "ADMISSIBLE_TERMINAL_GROWTH_UPPER_BOUND"),
    "cost_of_equity": ("DECIMAL_RATE", "NOMINAL_COST_OF_EQUITY"),
    "forecast_fcfe": ("MONEY", "EXPLICIT_EQUITY_CASH_FLOW_FORECAST"),
    "forecast_dividend": ("MONEY_PER_SHARE", "EXPLICIT_COMMON_DIVIDEND_FORECAST"),
    "forecast_residual_income": ("MONEY", "EXPLICIT_COMMON_EQUITY_RESIDUAL_INCOME_FORECAST"),
    "component_values": ("MONEY", "REPRODUCIBLE_COMPONENT_VALUE"),
}
REQUIRED_ASSUMPTIONS = {
    "FCFF_DCF": ("wacc", "terminal_growth", "forecast_fcff"),
    "REVERSE_FCFF": ("wacc", "forecast_fcff", "growth_lower", "growth_upper"),
    "NET_NET": ("cash_realization_ratio", "receivables_realization_ratio", "inventory_realization_ratio"),
    "FCFE": ("cost_of_equity", "forecast_fcfe"),
    "DDM": ("cost_of_equity", "forecast_dividend"),
    "RESIDUAL_INCOME": ("cost_of_equity", "forecast_residual_income"),
    "RNAV": ("component_values",), "SOTP": ("component_values",),
}


def _safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return "NONFINITE:" + str(value)
    if isinstance(value, Mapping):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    return value


def scenario_identity(value):
    return hashlib.sha256(json.dumps(_safe(value), sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _day(value):
    try:
        return date.fromisoformat(value) if isinstance(value, str) and len(value) == 10 else None
    except ValueError:
        return None


def validate_assumption(record, *, ticker, entity_family, session, case, name, qualified_sources=None):
    """One canonical contract. Caller-supplied assumptions are never generated defaults."""
    row = copy.deepcopy(record) if isinstance(record, Mapping) else {}
    reasons = []
    if not row:
        empty = dict(contract_version=ASSUMPTION_CONTRACT, ticker=ticker, entity_family=entity_family,
                     valuation_session=session, case=case, name=name, value=None, fitness="BLOCKED",
                     unit=ASSUMPTION_DEFINITIONS[name][0], semantic_definition=ASSUMPTION_DEFINITIONS[name][1],
                     forecast_period=None, horizon=None, source_period=None, derivation_method=None,
                     source_class=None, source_identity=None, warnings=[],
                     limitations=["MODEL_ASSUMPTION_NOT_FUTURE_FACT"],
                     blocker_reason_codes=["GOVERNED_ASSUMPTION_MISSING:" + name])
        empty["assumption_identity"] = ASSUMPTION_CONTRACT + ":" + scenario_identity(empty)
        return empty
    allowed = {"ticker", "entity_family", "valuation_session", "case", "name", "value", "unit",
               "semantic_definition", "forecast_period", "horizon", "source_class", "source_identity",
               "source_period", "derivation_method", "input_identities", "fitness", "warnings",
               "limitations", "blocker_reason_codes", "monetary_basis"}
    if set(row) - allowed:
        reasons.append("ASSUMPTION_FIELDS_OUTSIDE_CONTRACT")
        row = {key: value for key, value in row.items() if key in allowed}
    for field, expected in (("ticker", ticker), ("entity_family", entity_family),
                            ("valuation_session", session), ("case", case), ("name", name)):
        if row.get(field) != expected:
            reasons.append("ASSUMPTION_BINDING_MISMATCH:" + field)
    for field in ("warnings", "limitations", "blocker_reason_codes", "input_identities"):
        if field in row and (not isinstance(row[field], list) or any(not isinstance(v, str) for v in row[field])):
            reasons.append("ASSUMPTION_LIST_FIELD_MALFORMED:" + field)
            row[field] = []
    number = n(row.get("value"))
    if number is None:
        reasons.append("ASSUMPTION_VALUE_MALFORMED:" + name)
    definition = ASSUMPTION_DEFINITIONS[name]
    if (row.get("unit"), row.get("semantic_definition")) != definition:
        reasons.append("ASSUMPTION_SEMANTICS_INCOMPATIBLE:" + name)
    if not isinstance(row.get("source_class"), str) or row.get("source_class") not in {"QUALIFIED_RETAINED_EVIDENCE", "DERIVED_QUALIFIED_EVIDENCE", "GOVERNED_CONFIG"}:
        reasons.append("ASSUMPTION_SOURCE_CLASS_UNQUALIFIED:" + name)
    for field in ("source_identity", "source_period", "forecast_period", "horizon"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            reasons.append("ASSUMPTION_PROVENANCE_MISSING:" + field)
    if row.get("source_class") == "DERIVED_QUALIFIED_EVIDENCE" and (
            not row.get("derivation_method") or not row.get("input_identities")):
        reasons.append("ASSUMPTION_DERIVATION_LINEAGE_MISSING:" + name)
    if row.get("source_class") in ("QUALIFIED_RETAINED_EVIDENCE", "DERIVED_QUALIFIED_EVIDENCE"):
        source_key = row.get("source_identity")
        if row.get("source_class") == "DERIVED_QUALIFIED_EVIDENCE":
            ids = row.get("input_identities") or []
            if row.get("derivation_method") != "QUALIFIED_VALUE_IDENTITY_V1" or len(ids) != 1:
                reasons.append("DETERMINISTIC_ASSUMPTION_POLICY_NOT_SUPPORTED:" + name)
            source_key = ids[0] if len(ids) == 1 else None
        reference = (qualified_sources or {}).get(source_key) if isinstance(source_key, str) else None
        if (not isinstance(reference, Mapping) or reference.get("fitness") != "READY" or
            reference.get("source_identity") != source_key or reference.get("ticker") != ticker or
            reference.get("entity_family") != entity_family or
            any(reference.get(field) != row.get(field) for field in
                ("unit", "semantic_definition", "forecast_period", "horizon", "source_period", "monetary_basis")) or
            n(reference.get("value")) is None or n(reference.get("value")) != number):
            reasons.append("QUALIFIED_ASSUMPTION_SOURCE_BINDING_UNPROVEN:" + name)
        else:
            row["qualified_source_lineage"] = copy.deepcopy(reference)
    if row.get("fitness") != "READY" or row.get("blocker_reason_codes"):
        reasons.append("ASSUMPTION_FITNESS_NOT_READY:" + name)
    if number is not None:
        if name.endswith("realization_ratio") and not 0 <= number <= 1:
            reasons.append("REALIZATION_RATIO_OUTSIDE_DOMAIN:" + name)
        if name in {"wacc", "cost_of_equity", "forecast_fcff"} and number <= 0:
            reasons.append("ASSUMPTION_ECONOMICS_INVALID:" + name)
    row = _safe(row)
    row.update(contract_version=ASSUMPTION_CONTRACT, blocker_reason_codes=sorted(set(reasons)),
               fitness="BLOCKED" if reasons else "READY",
               limitations=sorted(set(row.get("limitations") or []) | {"MODEL_ASSUMPTION_NOT_FUTURE_FACT"}))
    row["assumption_identity"] = ASSUMPTION_CONTRACT + ":" + scenario_identity(row)
    return row


def _financial_readiness(data, method):
    reasons = []
    financial = data.get("financial") or {}
    periods, scopes, units = set(), set(), set()
    for metric in REQUIRED_FINANCIAL[method]:
        row = financial.get(metric) or {}
        value, bad = q(row, metric)
        if bad:
            reasons.append(bad.upper() + ":" + metric)
        if row:
            period = row.get("period_identity") or {}
            if not period.get("period") or not period.get("period_type"):
                reasons.append("FINANCIAL_PERIOD_INCOMPLETE:" + metric)
            periods.add(json.dumps(period, sort_keys=True))
            scopes.add(row.get("statement_scope"))
            unit = row.get("unit") or {}
            if unit.get("currency") in (None, "unknown", "UNKNOWN") or n(unit.get("scale")) is None or n(unit.get("scale")) <= 0:
                reasons.append("MONETARY_BASIS_UNQUALIFIED:" + metric)
            units.add(json.dumps(unit, sort_keys=True))
            if not row.get("source_identity"):
                reasons.append("FINANCIAL_LINEAGE_MISSING:" + metric)
            if row.get("source_conflicts"):
                reasons.append("FINANCIAL_SOURCE_CONFLICT:" + metric)
            if value is not None and metric not in {"operating_cash_flow", "qualified_equity_cash_flow", "attributable_net_income"} and value < 0:
                reasons.append("FINANCIAL_COMPONENT_ECONOMICS_INVALID:" + metric)
            end = _day(period.get("period_end"))
            session = _day(data.get("valuation_session"))
            if not end or not session or end > session:
                reasons.append("FINANCIAL_PERIOD_INVALID_OR_FUTURE:" + metric)
    if len(periods) > 1 or len(scopes) > 1 or len(units) > 1:
        reasons.append("FINANCIAL_PERIOD_SCOPE_OR_UNIT_INCOMPATIBLE")
    if method in {"FCFF_DCF", "REVERSE_FCFF"}:
        for metric in ("operating_cash_flow", "capital_expenditure"):
            if (financial.get(metric) or {}).get("period_identity", {}).get("period_type") not in {"annual", "standalone_quarter", "ttm"}:
                reasons.append("CASH_FLOW_DURATION_NOT_QUALIFIED:" + metric)
    share = data.get("share_count") or {}
    share_value = n(share.get("value"))
    if share_value is None or share_value <= 0 or share.get("semantics") != "period_end" or not share.get("source_identity") or share.get("fitness") != "READY":
        reasons.append("PERIOD_END_SHARE_DENOMINATOR_UNQUALIFIED")
    if share and (json.dumps(share.get("period_identity") or {}, sort_keys=True) not in periods or
                  share.get("statement_scope") not in scopes):
        reasons.append("SHARE_PERIOD_SCOPE_MISMATCH")
    return sorted(set(reasons))


def method_readiness(data, method, case):
    family = data.get("entity_family", "unknown")
    if not isinstance(family, str) or family not in ({"corporate"} | FINANCIAL_FAMILIES):
        return {"state": "BLOCKED", "reason_codes": ["ENTITY_APPLICABILITY_UNRESOLVED"], "assumptions": []}
    if family in FINANCIAL_FAMILIES and method in {"FCFF_DCF", "NET_NET", "REVERSE_FCFF", "RNAV", "SOTP"}:
        return {"state": "NOT_APPLICABLE", "reason_codes": ["ORDINARY_CORPORATE_METHOD_NOT_QUALIFIED_FOR_FINANCIAL_FAMILY"], "assumptions": []}
    reasons = _financial_readiness(data, method)
    method_sets = (data.get("assumption_sets") or {}).get(method) or {}
    supplied = method_sets.get(case) or [] if isinstance(method_sets, Mapping) else []
    if not isinstance(method_sets, Mapping) or not isinstance(supplied, list):
        reasons.append("ASSUMPTION_SET_SHAPE_INVALID")
        supplied = []
    by_name = {}
    for row in supplied:
        name = row.get("name") if isinstance(row, Mapping) else None
        if not isinstance(name, str) or name not in REQUIRED_ASSUMPTIONS[method]:
            reasons.append("ASSUMPTION_NAME_OUTSIDE_METHOD_CONTRACT")
            continue
        if name in by_name:
            reasons.append("DUPLICATE_ASSUMPTION:" + str(name))
        by_name[name] = row
    assumptions = [validate_assumption(by_name.get(name), ticker=data.get("ticker"), entity_family=family,
                                      session=data.get("valuation_session"), case=case, name=name,
                                      qualified_sources=data.get("qualified_assumption_sources"))
                   for name in REQUIRED_ASSUMPTIONS[method]]
    reasons.extend(reason for row in assumptions for reason in row["blocker_reason_codes"])
    if assumptions and len({scenario_identity({"forecast_period": r.get("forecast_period"), "horizon": r.get("horizon")}) for r in assumptions}) > 1:
        reasons.append("ASSUMPTION_FORECAST_HORIZON_INCOMPATIBLE")
    values = {r["name"]: n(r.get("value")) for r in assumptions if r.get("name")}
    if method == "FCFF_DCF" and all(values.get(k) is not None for k in ("wacc", "terminal_growth")):
        if values["wacc"] <= values["terminal_growth"] or n(values["wacc"] - values["terminal_growth"]) is None:
            reasons.append("WACC_MUST_EXCEED_TERMINAL_GROWTH")
    if method == "REVERSE_FCFF" and all(values.get(k) is not None for k in ("wacc", "growth_lower", "growth_upper")):
        if not values["growth_lower"] < values["growth_upper"] < values["wacc"]:
            reasons.append("REVERSE_BOUNDS_NOT_ADMISSIBLE")
    if method == "NET_NET" and not _financial_readiness(data, method):
        f = data["financial"]
        if sum(n(f[k]["value"]) for k in ("cash_and_equivalents", "receivables", "inventory")) > n(f["current_assets"]["value"]):
            reasons.append("CURRENT_ASSET_COMPONENTS_EXCEED_TOTAL")
    # Money-valued assumptions require the same explicitly declared monetary basis.
    units = [(data.get("financial") or {}).get(metric, {}).get("unit") for metric in REQUIRED_FINANCIAL[method]
             if (data.get("financial") or {}).get(metric, {}).get("unit")]
    for row in assumptions:
        if isinstance(row.get("unit"), str) and row.get("unit") in {"MONEY", "MONEY_PER_SHARE"} and (not row.get("monetary_basis") or any(row["monetary_basis"] != unit for unit in units)):
            reasons.append("ASSUMPTION_MONETARY_BASIS_INCOMPATIBLE:" + row.get("name", "unknown"))
    if method == "REVERSE_FCFF":
        reasons.extend(_comparison_price(data)[1])
    if method in {"RNAV", "SOTP"}:
        for metric in REQUIRED_FINANCIAL[method]:
            record = (data.get("financial") or {}).get(metric) or {}
            components = record.get("components")
            if not isinstance(components, list) or not components:
                reasons.append("REPRODUCIBLE_COMPONENT_CATALOG_REQUIRED:" + metric)
            elif any(not isinstance(c, Mapping) or n(c.get("value")) is None or
                     not c.get("source_identity") or c.get("unit") != record.get("unit") or
                     c.get("period_identity") != record.get("period_identity") or
                     c.get("statement_scope") != record.get("statement_scope") for c in components):
                reasons.append("COMPONENT_VALUE_LINEAGE_OR_BASIS_INCOMPATIBLE:" + metric)
    state = "BLOCKED" if reasons else "READY" if method in IMPLEMENTED else "NOT_IMPLEMENTED_FOR_QUALIFIED_INPUTS"
    return {"state": state, "reason_codes": sorted(set(reasons)), "assumptions": assumptions,
            "implementation_status": "IMPLEMENTED" if method in IMPLEMENTED else "NOT_IMPLEMENTED",
            "applicability": "APPLICABLE_CONDITIONAL_ON_QUALIFIED_INPUTS"}


def measure_method_readiness(inputs):
    """Measure evidence readiness independently of numeric valuation or policy changes."""
    counts = {method: Counter() for method in METHODS}
    by_family = {}
    blockers = {method: Counter() for method in METHODS}
    for ticker, data in sorted(inputs.items()):
        family = data.get("entity_family", "unknown")
        by_family.setdefault(family, {method: Counter() for method in METHODS})
        for method in METHODS:
            cases = [method_readiness(data, method, case) for case in CASES]
            state = ("READY" if all(c["state"] == "READY" for c in cases) else
                     "PARTIAL" if any(c["state"] == "READY" for c in cases) else cases[0]["state"])
            counts[method][state] += 1
            by_family[family][method][state] += 1
            blockers[method].update({r for c in cases for r in c["reason_codes"]})
    return {"denominator": len(inputs),
            "entity_family_counts": dict(sorted(Counter(d.get("entity_family", "unknown") for d in inputs.values()).items())),
            "method_readiness": {m: dict(sorted(v.items())) for m, v in counts.items()},
            "method_by_entity_family": {f: {m: dict(sorted(v.items())) for m, v in ms.items()} for f, ms in sorted(by_family.items())},
            "blocker_prevalence": {m: dict(sorted(v.items(), key=lambda kv: (-kv[1], kv[0]))) for m, v in blockers.items()}}


def inputs_from_semantic_rows(rows, *, tickers, session, entities, assumptions=None):
    """Conservative adapter over canonical code's retained semantic rows.

    Exact semantic aliases only. No total-liability debt, investing-CF CapEx,
    monetary-scale inference, share-basis invention or historical forecast extrapolation.
    Latest common-source period selection is deterministic; conflicting duplicates block.
    """
    aliases = {"cash_and_cash_equivalents": "cash_and_equivalents", "total_interest_bearing_debt": "total_debt"}
    required = {metric for metrics in REQUIRED_FINANCIAL.values() for metric in metrics}
    candidates = {}
    for raw in rows:
        ticker, metric = raw.get("ticker"), aliases.get(raw.get("canonical_metric"), raw.get("canonical_metric"))
        if ticker not in tickers or metric not in (required | {"shares_outstanding"}):
            continue
        key = (ticker, metric)
        rank = (str(raw.get("period_end") or ""), scenario_identity(raw))
        candidates.setdefault(key, []).append((rank, raw))
    result = {}
    for ticker in sorted(tickers):
        entity = entities.get(ticker) or {}
        family = entity.get("entity_class") if entity.get("applicability_status") == "RESOLVED" else "unknown"
        financial = {}
        for metric in sorted(required):
            values = candidates.get((ticker, metric)) or []
            if not values:
                continue
            raw = max(values, key=lambda pair: pair[0])[1]
            latest = [r for rank, r in values if rank[0] == str(raw.get("period_end") or "")]
            conflicts = ["DUPLICATE_LATEST_PERIOD_SOURCE_CONFLICT"] if len({scenario_identity(r) for r in latest}) > 1 else list(raw.get("source_conflicts") or [])
            lineage = raw.get("source_lineage") or {}
            period_type = {"STANDALONE_QUARTER": "standalone_quarter", "FULL_YEAR": "annual"}.get(raw.get("period_semantic_state"), "unknown")
            if raw.get("period_semantic_state") == "POINT_IN_TIME_BALANCE_SHEET":
                period_type = {"annual": "annual", "quarterly": "standalone_quarter"}.get(raw.get("native_period_type"), "unknown")
            financial[metric] = dict(canonical_metric=metric, value=raw.get("normalized_candidate_value"),
                                    quality_state="available" if raw.get("research_semantic_state") == "RESEARCH_SEMANTIC_READY" else "unavailable",
                                    statement_scope=raw.get("statement_scope"), unit=raw.get("normalized_candidate_unit"),
                                    period_identity={"period": raw.get("native_period_label"), "period_type": period_type,
                                                     "period_end": raw.get("period_end")},
                                    source_identity=lineage.get("fact_id") if raw.get("lineage_complete") else None,
                                    source_lineage=copy.deepcopy(lineage), source_conflicts=conflicts,
                                    warnings=list(raw.get("source_warnings") or []))
        share = {}
        share_candidates = candidates.get((ticker, "shares_outstanding")) or []
        if share_candidates:
            raw_share = max(share_candidates, key=lambda pair: pair[0])[1]
            # The name shares_outstanding alone never proves a period-end denominator basis.
            if (raw_share.get("share_basis") == "PERIOD_END_OUTSTANDING" and raw_share.get("lineage_complete")
                    and raw_share.get("research_semantic_state") == "RESEARCH_SEMANTIC_READY"):
                share = dict(value=raw_share.get("normalized_candidate_value"), semantics="period_end",
                             period_identity={"period": raw_share.get("native_period_label"),
                                              "period_type": {"annual": "annual", "quarterly": "standalone_quarter"}.get(raw_share.get("native_period_type"), "unknown"),
                                              "period_end": raw_share.get("period_end")},
                             statement_scope=raw_share.get("statement_scope"),
                             source_identity=(raw_share.get("source_lineage") or {}).get("fact_id"), fitness="READY")
        result[ticker] = dict(ticker=ticker, entity_family=family or "unknown", valuation_session=session,
                              financial=financial, share_count=share, assumption_sets=(assumptions or {}).get(ticker) or {},
                              limitations=["NO_FORECAST_GENERATION", "NO_SHARE_BASIS_OR_MONETARY_SCALE_INFERENCE"])
    return result



def _comparison_price(data, method="REVERSE_FCFF"):
    price = data.get("price_input") or {}
    share = data.get("share_count") or {}
    basis = next(((data.get("financial") or {}).get(metric, {}).get("unit") for metric in REQUIRED_FINANCIAL[method]
                  if (data.get("financial") or {}).get(metric, {}).get("unit")), None)
    value = n(price.get("value"))
    if (value is None or value <= 0 or price.get("fitness") != "READY" or
        price.get("session") != data.get("valuation_session") or not price.get("source_identity") or
        price.get("unit") != basis or not price.get("share_basis_identity") or
        price.get("share_basis_identity") != share.get("source_identity")):
        return None, ["CURRENT_PRICE_PERIOD_SHARE_OR_UNIT_COMPARISON_UNQUALIFIED"]
    return value, []


def _calculate_current_case(data, method, case, readiness):
    values = {row["name"]: n(row["value"]) for row in readiness["assumptions"]}
    financial = data.get("financial") or {}
    case_record = dict(case=case, conditional_interpretation="IF this governed assumption set holds, this method returns the stated model value.",
                       reference_case_meaning="BASE is a reference assumption case, never most likely.",
                       readiness=readiness["state"], reason_codes=list(readiness["reason_codes"]),
                       assumptions=readiness["assumptions"], enterprise_value=None, equity_value=None,
                       per_share_model_value=None, implied_terminal_growth=None, current_price_comparison=None,
                       monetary_basis=copy.deepcopy(next((financial.get(metric, {}).get("unit") for metric in REQUIRED_FINANCIAL[method]
                                                         if financial.get(metric, {}).get("unit")), None)),
                       output_unit="DECLARED_NATIVE_MONETARY_BASIS_PER_SHARE" if method != "REVERSE_FCFF" else "DECIMAL_RATE",
                       warnings=[], limitations=["CURRENT_RESEARCH_ONLY", "NO_TARGET_PRICE_AUTHORITY",
                                                "NO_ACTIONABILITY", "NO_CROSS_METHOD_AVERAGING"],
                       invalidation_conditions=["A bound financial input becomes incompatible, conflicting or unavailable.",
                                                "A governed assumption is withdrawn or revised.",
                                                "Share-period, scope or monetary basis ceases to match."])
    case_record["assumption_set_identity"] = ASSUMPTION_CONTRACT + ":" + scenario_identity(
        {"method": method, "case": case, "assumptions": readiness["assumptions"]})
    if readiness["state"] == "READY":
        shares = n(data["share_count"]["value"])
        if method == "FCFF_DCF":
            legacy = dict(financial=financial, entity_type="corporate", fcff_assumptions={
                **values, **{name + "_source": row["source_identity"] for name, row in
                             ((row["name"], row) for row in readiness["assumptions"])}})
            ev = evaluate_intrinsic_valuation(legacy, data["valuation_session"])["methods"]["fcff_dcf"]["enterprise_value"]
            equity = ev - n(financial["total_debt"]["value"]) + n(financial["cash_and_equivalents"]["value"])
            case_record.update(enterprise_value=ev, equity_value=equity, per_share_model_value=equity / shares)
        elif method == "NET_NET":
            adjusted = copy.deepcopy(financial)
            for metric, assumption in (("cash_and_equivalents", "cash_realization_ratio"),
                                       ("receivables", "receivables_realization_ratio"),
                                       ("inventory", "inventory_realization_ratio")):
                adjusted[metric]["value"] = n(adjusted[metric]["value"]) * values[assumption]
            legacy = dict(financial=adjusted, entity_type="corporate", share_count=data["share_count"])
            evaluated = evaluate_intrinsic_valuation(legacy, data["valuation_session"])["methods"]["net_net"]
            case_record.update(equity_value=evaluated["equity_value"], per_share_model_value=evaluated["per_share_value"])
        else:
            from market_wide_implied_growth_reverse_valuation_research import solve_fcff_terminal_growth
            price, blocked = _comparison_price(data, method)
            if price is None:
                case_record.update(readiness="BLOCKED", reason_codes=blocked)
            else:
                market_ev = price * shares + n(financial["total_debt"]["value"]) - n(financial["cash_and_equivalents"]["value"])
                solved = solve_fcff_terminal_growth(forecast_fcff=values["forecast_fcff"], discount_rate=values["wacc"],
                                                    market_enterprise_value=market_ev,
                                                    lower_bound=values["growth_lower"], upper_bound=values["growth_upper"])
                case_record["readiness"] = solved["state"]
                case_record["reason_codes"] = [] if solved["state"] == "READY" else [solved["reason"]]
                case_record["implied_terminal_growth"] = solved.get("value")
                case_record["reverse_solver"] = solved
                case_record["market_enterprise_value"] = market_ev
                case_record["limitations"].append("MODEL_IMPLICATION_NOT_FORECAST")
        if case_record.get("per_share_model_value") is not None:
            price, blocked = _comparison_price(data, method)
            case_record["current_price_comparison"] = (
                {"state": "READY", "current_price": price, "absolute_difference": case_record["per_share_model_value"] - price,
                 "relative_difference": case_record["per_share_model_value"] / price - 1,
                 "source_identity": data["price_input"]["source_identity"], "role": "CONDITIONAL_NUMERIC_COMPARISON_ONLY"}
                if price is not None else {"state": "BLOCKED", "reason_codes": blocked})
        numeric = [case_record.get(k) for k in ("enterprise_value", "equity_value", "per_share_model_value", "implied_terminal_growth")]
        if any(v is not None and n(v) is None for v in numeric):
            case_record.update(readiness="BLOCKED", reason_codes=["MODEL_ARITHMETIC_NONFINITE"],
                               enterprise_value=None, equity_value=None, per_share_model_value=None, implied_terminal_growth=None)
    case_record["case_identity"] = CURRENT_SCENARIO_CONTRACT + ":" + scenario_identity(case_record)
    return case_record


def _case_state(cases):
    states = [row["readiness"] for row in cases.values()]
    return "READY" if all(s == "READY" for s in states) else "PARTIAL" if "READY" in states else states[0]


def _sensitivity(data, cases):
    ready = [row for row in cases.values() if row["readiness"] == "READY"]
    metadata = {(r.get("forecast_period"), r.get("horizon")) for row in ready for r in row["assumptions"]}
    if len(metadata) != 1:
        return {"state": "BLOCKED", "reason_codes": ["COMPATIBLE_GOVERNED_CASE_COORDINATES_UNAVAILABLE"], "grid": []}
    coordinates = {name: sorted({n(r["value"]) for row in ready for r in row["assumptions"] if r["name"] == name})
                   for name in ("wacc", "terminal_growth")}
    if not all(coordinates.values()) or not any(len(v) > 1 for v in coordinates.values()):
        return {"state": "BLOCKED", "reason_codes": ["DISTINCT_GOVERNED_SENSITIVITY_COORDINATES_UNAVAILABLE"], "grid": []}
    grid = []
    for row in ready:
        fcff = next(n(r["value"]) for r in row["assumptions"] if r["name"] == "forecast_fcff")
        for wacc in coordinates["wacc"]:
            for growth in coordinates["terminal_growth"]:
                ev = fcff / (wacc - growth) if wacc > growth else None
                grid.append({"forecast_case": row["case"], "wacc": wacc, "terminal_growth": growth,
                             "enterprise_value": ev if ev is not None and n(ev) is not None else None, "state": "READY" if ev is not None and n(ev) is not None else "BLOCKED",
                             "coordinate_source_identities": sorted({r["assumption_identity"] for case in ready for r in case["assumptions"]
                                                                      if r["name"] in coordinates}),
                             "derivation_method": "CROSS_GOVERNED_RATE_COORDINATES_SAME_FORECAST_PERIOD"})
    return {"state": "READY", "dimensions": ["wacc", "terminal_growth"], "grid": grid}


def build_current_scenario_valuation(data):
    """Governed intrinsic valuation projection; absence never rejects a research ticker."""
    methods = {}
    for method in METHODS:
        cases = {case: _calculate_current_case(data, method, case, method_readiness(data, method, case)) for case in CASES}
        values = [c["per_share_model_value"] for c in cases.values() if c["readiness"] == "READY" and c["per_share_model_value"] is not None]
        methods[method] = dict(method=method, method_version="FCFF_STEADY_STATE_PERPETUITY_V1" if method == "FCFF_DCF" else
                             "NET_NET_COMPONENT_REALIZATION_V1" if method == "NET_NET" else "EXISTING_REVERSE_FCFF_V1" if method == "REVERSE_FCFF" else "NOT_IMPLEMENTED",
                             readiness=_case_state(cases), cases=cases,
                             entity_applicability="UNRESOLVED" if data.get("entity_family", "unknown") not in ({"corporate"} | FINANCIAL_FAMILIES) else
                                                  "NOT_APPLICABLE_TO_ORDINARY_CORPORATE_VARIANT" if all(c["readiness"] == "NOT_APPLICABLE" for c in cases.values()) else "APPLICABLE_CONDITIONAL_ON_QUALIFIED_INPUTS",
                             implementation_status="IMPLEMENTED" if method in IMPLEMENTED else "NOT_IMPLEMENTED",
                             formula={"FCFF_DCF": "EV = forecast_fcff / (wacc - terminal_growth); equity = EV - interest_bearing_debt + cash; per_share = equity / period_end_shares",
                                      "NET_NET": "equity = cash * cash_ratio + receivables * receivables_ratio + inventory * inventory_ratio - total_liabilities; per_share = equity / period_end_shares",
                                      "REVERSE_FCFF": "Solve market_EV = forecast_fcff / (wacc - implied_growth), bounded below WACC; market_EV = current_price * qualified_shares + interest_bearing_debt - cash"}.get(method),
                             conditional_per_share_range={"minimum": min(values), "maximum": max(values)} if values else None,
                             sensitivity=_sensitivity(data, cases) if method == "FCFF_DCF" else
                                         {"state": "NOT_APPLICABLE", "reason_codes": ["METHOD_HAS_NO_IMPLEMENTED_RATE_GRID"], "grid": []},
                             input_lineage={metric: copy.deepcopy((data.get("financial") or {}).get(metric)) for metric in REQUIRED_FINANCIAL[method]},
                             share_lineage=copy.deepcopy(data.get("share_count") or {}))
    payload = dict(contract_version=CURRENT_SCENARIO_CONTRACT, ticker=data.get("ticker"), entity_family=data.get("entity_family", "unknown"),
                   valuation_session=data.get("valuation_session"), methods=methods,
                   cross_method_dispersion={method: value["conditional_per_share_range"] for method, value in methods.items()
                                            if value["conditional_per_share_range"] is not None},
                   case_definitions={"BEAR": "Conditional valuation assumption case.", "BASE": "Reference valuation assumption case; not most likely.",
                                     "BULL": "Conditional valuation assumption case."},
                   authority_effect="NONE", is_actionable=False,
                   limitations=["NO_CROSS_METHOD_AVERAGING", "NO_FORECAST_FROM_EVENT_LABELS", "NO_GLOBAL_RESEARCH_BLOCKER", "NO_TARGET_PRICE_AUTHORITY"])
    payload = _safe(payload)
    payload["projection_identity"] = CURRENT_SCENARIO_CONTRACT + ":" + scenario_identity(payload)
    return payload


def consume_current_projection(projection, *, ticker=None, session=None):
    """Verify a produced projection before additive consumer pass-through."""
    valid = isinstance(projection, Mapping) and projection.get("contract_version") == CURRENT_SCENARIO_CONTRACT
    if valid:
        payload = {k: v for k, v in projection.items() if k != "projection_identity"}
        valid = projection.get("projection_identity") == CURRENT_SCENARIO_CONTRACT + ":" + scenario_identity(payload)
        valid = valid and (ticker is None or projection.get("ticker") == ticker)
        valid = valid and (session is None or projection.get("valuation_session") == session)
    if valid:
        return copy.deepcopy(projection)
    header = projection if isinstance(projection, Mapping) else {}
    result = build_current_scenario_valuation({"ticker": ticker or header.get("ticker"),
        "valuation_session": session or header.get("valuation_session"),
        "entity_family": header.get("entity_family", "unknown") if isinstance(header.get("entity_family", "unknown"), str) else "unknown"})
    result["limitations"].append("INTRINSIC_PROJECTION_IDENTITY_OR_BINDING_INVALID")
    result.pop("projection_identity")
    result["projection_identity"] = CURRENT_SCENARIO_CONTRACT + ":" + scenario_identity(result)
    return result


def bind_forward_driver_explanation(projection, context, *, ticker=None, session=None):
    """Drivers identify evidence to review, never adjust a numeric assumption."""
    result = consume_current_projection(projection, ticker=ticker, session=session)
    result["forward_driver_explanation"] = {
        "context_identity": (context or {}).get("context_identity"),
        "evidence": [{key: copy.deepcopy(driver.get(key)) for key in
                     ("event_identity", "source_identities", "event_type", "status", "known_dates", "fitness", "qualified", "direction")}
                     for driver in (context or {}).get("drivers") or []],
        "review_condition": "Qualified follow-up and explicit governed assumption revision are required before any model input can change.",
        "numeric_adjustment": "NONE", "planned_is_not_executed": True, "record_date_is_not_ex_date": True,
    }
    result.pop("projection_identity", None)
    result["projection_identity"] = CURRENT_SCENARIO_CONTRACT + ":" + scenario_identity(result)
    return result



def load_governed_assumption_config(path):
    from pathlib import Path
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # Configuration absence/invalidity is a model blocker, not a financial-axis failure.
        return {}, ASSUMPTION_CONTRACT + ":INVALID:" + scenario_identity({"failure": type(exc).__name__})
    if not isinstance(config, Mapping) or config.get("contract_version") != ASSUMPTION_CONTRACT or not isinstance(config.get("assumption_sets"), Mapping):
        return {}, ASSUMPTION_CONTRACT + ":INVALID:" + scenario_identity(config)
    return config["assumption_sets"], ASSUMPTION_CONTRACT + ":" + scenario_identity(config)



def current_scenario_coverage(projections):
    projections = list(projections)
    methods = {method: Counter() for method in METHODS}
    by_family, blockers = {}, {method: Counter() for method in METHODS}
    source_classes = Counter()
    with_values = reverse_only = sensitivity = price_comparison = 0
    case_available = Counter({case: 0 for case in CASES})
    for projection in projections:
        family = projection["entity_family"]
        by_family.setdefault(family, {method: Counter() for method in METHODS})
        has_value = has_reverse = has_sensitivity = has_comparison = False
        available_cases = set()
        for method, row in projection["methods"].items():
            methods[method][row["readiness"]] += 1
            by_family[family][method][row["readiness"]] += 1
            blockers[method].update({reason for case in row["cases"].values() for reason in case["reason_codes"]})
            has_sensitivity |= row["sensitivity"]["state"] == "READY"
            for case, case_row in row["cases"].items():
                value = case_row["readiness"] == "READY" and case_row["per_share_model_value"] is not None
                has_value |= value
                if value:
                    available_cases.add(case)
                has_reverse |= case_row["readiness"] == "READY" and case_row["implied_terminal_growth"] is not None
                has_comparison |= (case_row.get("current_price_comparison") or {}).get("state") == "READY"
                source_classes.update(r["source_class"] for r in case_row["assumptions"] if isinstance(r.get("source_class"), str))
        with_values += has_value
        reverse_only += has_reverse and not has_value
        sensitivity += has_sensitivity
        price_comparison += has_comparison
        case_available.update(available_cases)
    return dict(denominator=len(projections),
                entity_family_counts=dict(sorted(Counter(p["entity_family"] for p in projections).items())),
                method_readiness={m: dict(sorted(c.items())) for m, c in methods.items()},
                method_by_entity_family={f: {m: dict(sorted(c.items())) for m, c in ms.items()} for f, ms in sorted(by_family.items())},
                blocker_prevalence={m: dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))) for m, c in blockers.items()},
                tickers_with_at_least_one_scenario_valued_method=with_values,
                reverse_implied_only_tickers=reverse_only, tickers_with_no_intrinsic_method=len(projections)-with_values,
                assumption_source_distribution=dict(sorted(source_classes.items())),
                bear_base_bull_availability=dict(sorted(case_available.items())),
                sensitivity_available=sensitivity, current_price_comparison_available=price_comparison)
