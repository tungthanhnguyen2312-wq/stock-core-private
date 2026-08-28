"""Fail-closed flow-period normalization, TTM, and current-YTD bridge foundation.

This is an adapter over already-retained canonical facts.  It never alters a raw or
canonical fact, fetches data, or treats a quarter label as duration evidence.  It
records the exact source contract used for the narrow KBS income-statement case and
otherwise requires an explicit retained flow basis before making a subtraction.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from market_wide_current_fundamental_research import (
    INCOME_STATEMENT_PERIOD_SEMANTICS_VERSION,
    KBS_KQKD_QUARTER_SEMANTICS,
)

CONTRACT_VERSION = "financial_flow_semantics_and_ttm_bridge/v1"
FLOW_BASES = ("STANDALONE_QUARTER", "CUMULATIVE_YTD", "FULL_YEAR", "UNKNOWN")
FLOW_METRICS = ("revenue", "net_income", "operating_cash_flow", "depreciation_and_amortization")
SUPPORTED_ENTITY_TYPES = frozenset({"corporate"})


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items()
               if key not in {"artifact_sha256", "artifact_identity", "requested_at"}}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


def _period_key(value: Any) -> tuple[int, int] | None:
    text = str(value or "")
    try:
        year, quarter = text.split("-Q", 1)
        q = int(quarter)
        return (int(year), q) if q in {1, 2, 3, 4} else None
    except (ValueError, TypeError):
        return None


def _year(value: Any) -> int | None:
    key = _period_key(value)
    if key:
        return key[0]
    try:
        return int(str(value)[:4])
    except ValueError:
        return None


def flow_semantics(fact: Mapping[str, Any]) -> dict[str, Any]:
    """Classify one flow fact from retained explicit evidence only.

    `period_type` and a reporting label are copied for provenance but never independently
    decide duration.  Explicitly carried future metadata is accepted so the same contract
    can construct the prescribed YTD and full-year bridge without a redesign.
    """
    result = {
        "flow_period_basis": "UNKNOWN", "period_start": fact.get("period_start"),
        "period_end": fact.get("period_end"), "duration_months": fact.get("duration_months"),
        "statement_scope": fact.get("statement_scope"), "currency": fact.get("currency"),
        "scale": fact.get("scale"), "provider": fact.get("provider"),
        "source_sha256": fact.get("source_sha256"), "method": "NONE_SEMANTICS_UNRESOLVED",
        "evidence": "retained_canonical_fact_fields", "reason": "FLOW_PERIOD_BASIS_UNKNOWN",
    }
    explicit = str(fact.get("flow_period_basis") or "")
    if explicit in FLOW_BASES and explicit != "UNKNOWN":
        result.update({"flow_period_basis": explicit, "method": "DIRECT_RETAINED_FLOW_METADATA",
                       "evidence": str(fact.get("flow_period_basis_evidence") or "retained_flow_period_basis"),
                       "reason": None})
        return result
    # Existing provider-owned endpoint contract, already used by the current fundamental
    # consumer.  It is limited to KBS KQKD termtype=2 and income-statement flows.
    if (fact.get("provider") == "KBS" and fact.get("statement_family") == "income_statement"
            and _period_key(fact.get("reporting_period"))):
        result.update({"flow_period_basis": "STANDALONE_QUARTER", "method": "DIRECT_KBS_KQKD_QUARTER",
                       "evidence": KBS_KQKD_QUARTER_SEMANTICS["evidence"], "reason": None,
                       "duration_months": 3,
                       "semantic_contract_version": INCOME_STATEMENT_PERIOD_SEMANTICS_VERSION})
        return result
    # Cash-flow resolver evidence is intentionally narrower than a provider-wide claim.
    if (fact.get("canonical_metric") == "operating_cash_flow" and fact.get("cumulative_state") == "period_only"
            and fact.get("period_start") and fact.get("period_end")):
        result.update({"flow_period_basis": "STANDALONE_QUARTER", "method": "DIRECT_RETAINED_CASH_FLOW_RESOLVER",
                       "evidence": "retained_cash_flow_beginning_cash_basis_resolver", "reason": None})
    elif fact.get("cumulative_state") == "cumulative_ytd":
        result.update({"flow_period_basis": "CUMULATIVE_YTD", "method": "DIRECT_RETAINED_CUMULATIVE_STATE",
                       "evidence": "retained_canonical_cumulative_state", "reason": None})
    return result


def _usable(fact: Mapping[str, Any]) -> bool:
    return (fact.get("status") in {"provider_reported", "qualified", "partial"}
            and isinstance(fact.get("value"), (int, float)) and not isinstance(fact.get("value"), bool))


def _compatible(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    fields = ("ticker", "canonical_metric", "provider", "statement_scope", "currency", "scale")
    return all(a.get(field) == b.get(field) for field in fields)


def _same_representation(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    fields = ("ticker", "provider", "statement_scope", "currency", "scale")
    return all(a.get(field) == b.get(field) for field in fields)


def _quarter_record(fact: Mapping[str, Any], semantic: Mapping[str, Any], value: float,
                    method: str, inputs: Sequence[Mapping[str, Any]], quarter_override: int | None = None) -> dict[str, Any]:
    return {
        "ticker": fact.get("ticker"), "canonical_metric": fact.get("canonical_metric"),
        "reporting_period": fact.get("reporting_period"), "fiscal_year": _year(fact.get("reporting_period")),
        "quarter": quarter_override or (_period_key(fact.get("reporting_period")) or (None, None))[1],
        "value": value, "provider": fact.get("provider"), "statement_scope": fact.get("statement_scope"),
        "currency": fact.get("currency"), "scale": fact.get("scale"),
        "flow_period_basis": "STANDALONE_QUARTER", "derivation_method": method,
        "derived": method != "DIRECT_STANDALONE_QUARTER", "operands": [item.get("fact_id") for item in inputs],
        "semantic_evidence": semantic.get("evidence"),
        "source_fact_ids": [item.get("fact_id") for item in inputs],
        "source_sha256s": sorted({str(item.get("source_sha256")) for item in inputs if item.get("source_sha256")}),
        "warnings": [], "evidence_tier": "OPERATIONAL_PROXY", "fitness_for_use": {
            "display_eligible": True, "research_eligible": True, "trend_eligible": True,
            "valuation_research_eligible": False, "authoritative_financial_eligible": False,
            "pit_backtest_eligible": False,
        }, "is_actionable": False,
    }


def standalone_quarters(facts: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], Counter]:
    """Return direct or subtraction-derived standalone quarters; never make Q labels proof."""
    candidates = [fact for fact in facts if fact.get("canonical_metric") in FLOW_METRICS and _usable(fact)]
    direct: dict[tuple[str, str, int, int], tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    ytd: dict[tuple[str, str, int, int], tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    full: dict[tuple[str, str, int], tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    blockers = Counter()
    for fact in candidates:
        key = _period_key(fact.get("reporting_period"))
        semantic = flow_semantics(fact)
        if semantic["flow_period_basis"] == "UNKNOWN":
            blockers[semantic["reason"]] += 1
            continue
        year = _year(fact.get("reporting_period"))
        if semantic["flow_period_basis"] == "STANDALONE_QUARTER" and key:
            direct[(str(fact["ticker"]), str(fact["canonical_metric"]), key[0], key[1])] = (fact, semantic)
        elif semantic["flow_period_basis"] == "CUMULATIVE_YTD" and key:
            ytd[(str(fact["ticker"]), str(fact["canonical_metric"]), key[0], key[1])] = (fact, semantic)
        elif semantic["flow_period_basis"] == "FULL_YEAR" and year is not None:
            full[(str(fact["ticker"]), str(fact["canonical_metric"]), year)] = (fact, semantic)
    output = []
    for _, (fact, semantic) in sorted(direct.items()):
        output.append(_quarter_record(fact, semantic, float(fact["value"]), "DIRECT_STANDALONE_QUARTER", [fact]))
    # Required deterministic transformations.  Exact comparability gates precede every subtraction.
    for (ticker, metric, year, quarter), (fact, semantic) in sorted(ytd.items()):
        if quarter == 1:
            output.append(_quarter_record(fact, semantic, float(fact["value"]), "Q1_YTD_AS_Q1_STANDALONE", [fact]))
            continue
        previous = ytd.get((ticker, metric, year, quarter - 1)) if quarter in {2, 3} else None
        prior = previous[0] if previous else None
        if prior is None or not _compatible(fact, prior):
            blockers["YTD_SUBTRACTION_INPUTS_INCOMPATIBLE_OR_MISSING"] += 1
            continue
        method = "Q2_YTD_MINUS_Q1_YTD" if quarter == 2 else "Q3_YTD_MINUS_H1_YTD"
        output.append(_quarter_record(fact, semantic, float(fact["value"]) - float(prior["value"]), method, [fact, prior]))
    for (ticker, metric, year), (annual, semantic) in sorted(full.items()):
        prior_ytd = ytd.get((ticker, metric, year, 3))
        if prior_ytd is None or not _compatible(annual, prior_ytd[0]):
            blockers["Q4_FULL_YEAR_MINUS_9M_YTD_INPUTS_INCOMPATIBLE_OR_MISSING"] += 1
            continue
        output.append(_quarter_record(annual, semantic, float(annual["value"]) - float(prior_ytd[0]["value"]),
                                      "Q4_FULL_YEAR_MINUS_9M_YTD", [annual, prior_ytd[0]], quarter_override=4))
    return sorted(output, key=lambda row: (row["ticker"], row["canonical_metric"], row["fiscal_year"], row["quarter"])), blockers


def _ttm(quarters: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    if len(quarters) < 4:
        return None
    latest = sorted(quarters, key=lambda row: (row["fiscal_year"], row["quarter"]))[-4:]
    positions = [(row["fiscal_year"], row["quarter"]) for row in latest]
    expected = [(latest[0]["fiscal_year"] + (latest[0]["quarter"] - 1 + i) // 4,
                 (latest[0]["quarter"] - 1 + i) % 4 + 1) for i in range(4)]
    if positions != expected or any(not _compatible(latest[0], row) for row in latest[1:]):
        return None
    return {"ticker": latest[0]["ticker"], "canonical_metric": latest[0]["canonical_metric"],
            "value": sum(row["value"] for row in latest), "as_of_period": latest[-1]["reporting_period"],
            "source_periods": [row["reporting_period"] for row in latest], "provider": latest[0]["provider"],
            "statement_scope": latest[0]["statement_scope"], "currency": latest[0]["currency"], "scale": latest[0]["scale"],
            "method": "TTM_ROLLING_4_STANDALONE_QUARTERS", "evidence_tier": "OPERATIONAL_PROXY",
            "fitness_for_use": latest[0]["fitness_for_use"], "is_actionable": False}


def ytd_bridge_ttm(facts: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Apply CURRENT_YTD + PRIOR_FULL_YEAR - PRIOR_SAME_PERIOD_YTD when explicit.

    Labels merely align an already-proved flow basis; they never establish it.  The result
    therefore remains absent for today's retained VCI/KBS source shapes unless a fact itself
    carries cumulative-YTD/full-year semantics.
    """
    ytd: dict[tuple[str, str, int, int], tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    full: dict[tuple[str, str, int], tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    for fact in facts:
        if fact.get("canonical_metric") not in FLOW_METRICS or not _usable(fact):
            continue
        semantic = flow_semantics(fact)
        key = _period_key(fact.get("reporting_period"))
        if semantic["flow_period_basis"] == "CUMULATIVE_YTD" and key:
            ytd[(str(fact["ticker"]), str(fact["canonical_metric"]), key[0], key[1])] = (fact, semantic)
        elif semantic["flow_period_basis"] == "FULL_YEAR" and (year := _year(fact.get("reporting_period"))) is not None:
            full[(str(fact["ticker"]), str(fact["canonical_metric"]), year)] = (fact, semantic)
    result: dict[str, dict[str, Any]] = {}
    for (ticker, metric, year, quarter), (current, current_semantic) in sorted(ytd.items()):
        prior_ytd = ytd.get((ticker, metric, year - 1, quarter))
        prior_full = full.get((ticker, metric, year - 1))
        if prior_ytd is None or prior_full is None:
            continue
        operands = [current, prior_full[0], prior_ytd[0]]
        if not all(_compatible(current, operand) for operand in operands[1:]):
            continue
        result[metric] = {
            "ticker": ticker, "canonical_metric": metric,
            "value": float(current["value"]) + float(prior_full[0]["value"]) - float(prior_ytd[0]["value"]),
            "as_of_period": current.get("reporting_period"), "source_periods": [
                current.get("reporting_period"), prior_full[0].get("reporting_period"), prior_ytd[0].get("reporting_period")],
            "provider": current.get("provider"), "statement_scope": current.get("statement_scope"),
            "currency": current.get("currency"), "scale": current.get("scale"),
            "method": "TTM_YTD_BRIDGE", "operands": [item.get("fact_id") for item in operands],
            "semantic_evidence": [current_semantic.get("evidence"), prior_full[1].get("evidence"), prior_ytd[1].get("evidence")],
            "evidence_tier": "OPERATIONAL_PROXY", "fitness_for_use": {
                "display_eligible": True, "research_eligible": True, "trend_eligible": True,
                "valuation_research_eligible": False, "authoritative_financial_eligible": False,
                "pit_backtest_eligible": False}, "is_actionable": False,
        }
    return result


def _known(value: Any) -> str:
    return "KNOWN" if value not in {None, "", "unknown", "UNKNOWN"} else "UNKNOWN"


def _coverage_before_after(facts_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    before_basis, after_basis = Counter(), Counter()
    scope, currency, scale = Counter(), Counter(), Counter()
    retained_depth: Counter[int] = Counter()
    for facts in facts_by_ticker.values():
        periods: set[str] = set()
        for fact in facts:
            if fact.get("canonical_metric") not in FLOW_METRICS or not _usable(fact):
                continue
            periods.add(str(fact.get("reporting_period")))
            before_basis[str(fact.get("flow_period_basis") or "UNKNOWN")] += 1
            after_basis[flow_semantics(fact)["flow_period_basis"]] += 1
            scope[_known(fact.get("statement_scope"))] += 1
            currency[_known(fact.get("currency"))] += 1
            scale[_known(fact.get("scale"))] += 1
        retained_depth[len(periods)] += 1
    stable = lambda values: {"before": dict(sorted(values.items())), "after": dict(sorted(values.items()))}
    return {"flow_period_basis": {"before": dict(sorted(before_basis.items())), "after": dict(sorted(after_basis.items()))},
            "statement_scope": stable(scope), "currency": stable(currency), "scale": stable(scale),
            "retained_flow_period_depth_before": dict(sorted(retained_depth.items()))}


def build_ticker_record(*, ticker: str, entity_type: str | None,
                        facts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if entity_type not in SUPPORTED_ENTITY_TYPES:
        return {"ticker": ticker, "entity_type": entity_type, "status": "BLOCKED", "blocker": "ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE",
                "standalone_quarters": [], "ttm": {}, "derived_metrics": {}, "is_actionable": False}
    quarters, blockers = standalone_quarters(facts)
    by_metric: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in quarters:
        by_metric[row["canonical_metric"]].append(row)
    ttm = {metric: value for metric, series in sorted(by_metric.items()) if (value := _ttm(series)) is not None}
    ytd_bridge = ytd_bridge_ttm(facts)
    derived: dict[str, Any] = {}
    revenue, income = ttm.get("revenue"), ttm.get("net_income")
    if revenue and income and revenue["value"] != 0 and _same_representation(revenue, income):
        derived["ttm_net_margin"] = {"status": "AVAILABLE", "value": income["value"] / revenue["value"],
            "method": "TTM_NET_INCOME_DIVIDED_BY_TTM_REVENUE", "evidence_tier": "OPERATIONAL_PROXY", "is_actionable": False}
    else:
        derived["ttm_net_margin"] = {"status": "BLOCKED", "blocker": "TTM_REVENUE_AND_NET_INCOME_COMPATIBLE_PAIR_REQUIRED"}
    # Exact EBITDA is intentionally impossible until the canonical registry contains exact EBIT.
    derived["ttm_ebitda"] = {"status": "BLOCKED", "blocker": "EXACT_EBIT_IDENTITY_NOT_RETAINED;_EBIT_CONTEXT_PROXY_NOT_EBITDA"}
    return {"ticker": ticker, "entity_type": entity_type, "status": "AVAILABLE" if ttm else "BLOCKED",
            "blocker": None if ttm else "BLOCKED_INSUFFICIENT_COMPATIBLE_STANDALONE_QUARTERS",
            "standalone_quarters": quarters, "ttm": ttm, "ttm_ytd_bridge": ytd_bridge, "derived_metrics": derived,
            "flow_blockers": dict(sorted(blockers.items())), "is_actionable": False}


def build_artifact(*, tickers: Sequence[str], facts_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]],
                   entity_type_by_ticker: Mapping[str, str | None], requested_at: str) -> dict[str, Any]:
    names = sorted({str(ticker).upper() for ticker in tickers})
    records = {ticker: build_ticker_record(ticker=ticker, entity_type=entity_type_by_ticker.get(ticker),
                                            facts=facts_by_ticker.get(ticker, [])) for ticker in names}
    ttm_counts = Counter(metric for record in records.values() for metric in record["ttm"])
    bridge_counts = Counter(metric for record in records.values() for metric in record.get("ttm_ytd_bridge", {}))
    derived_counts = Counter(metric for record in records.values()
                             for metric, value in record["derived_metrics"].items() if value.get("status") == "AVAILABLE")
    standalone_depth = Counter(len({row["reporting_period"] for row in record.get("standalone_quarters", [])})
                              for record in records.values())
    lookback_8q = Counter()
    for record in records.values():
        by_metric: dict[str, set[str]] = defaultdict(set)
        for row in record.get("standalone_quarters", []):
            by_metric[row["canonical_metric"]].add(str(row["reporting_period"]))
        for metric, periods in by_metric.items():
            if len(periods) >= 8:
                lookback_8q[metric] += 1
    artifact = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION,
        "milestone": "FINANCIAL_FLOW_SEMANTICS_AND_TTM_BRIDGE_FOUNDATION_V1", "requested_at": requested_at,
        "records": records,
        "coverage": {"denominator": len(names), "terminal_count": len(records), "residual": len(names) - len(records),
            "ttm_rolling_4q_by_metric": dict(sorted(ttm_counts.items())), "ttm_ytd_bridge_by_metric": dict(sorted(bridge_counts.items())),
            "derived_metrics": dict(sorted(derived_counts.items())), "semantic_coverage": _coverage_before_after(facts_by_ticker),
            "standalone_period_depth_after": dict(sorted(standalone_depth.items())),
            "lookback_8q_or_more_by_metric": dict(sorted(lookback_8q.items())),
            "both_revenue_and_net_income_ttm": sum(
                "revenue" in record["ttm"] and "net_income" in record["ttm"] for record in records.values()),
            "terminal_blockers": dict(sorted(Counter(record.get("blocker") or "AVAILABLE" for record in records.values()).items())),
            "flow_basis_evidence": "KBS_KQKD direct standalone quarter; retained cash-flow resolver; otherwise unknown"},
        "valuation_context": {"status": "BLOCKED", "reason": "CURRENCY_SCALE_DENOMINATOR_SEMANTICS_INSUFFICIENT",
                              "labels_supported": ["TTM", "LFY", "ANNUALIZED_RUN_RATE"], "rankings_promoted": False,
                              "coverage": {"pe_ttm": 0, "ps_ttm": 0, "ev_sales_ttm": 0, "ev_ebitda_ttm": 0,
                                           "pe_lfy": 0, "ps_lfy": 0, "ev_sales_lfy": 0, "ev_ebitda_lfy": 0,
                                           "lfy_revenue": 0, "lfy_earnings": 0,
                                           "annualized_run_rate_research_proxy": 0,
                                           "ebitda_exact": 0, "ebit_context_proxy": 0}},
        "authority_boundary": {"authoritative_evidence_promoted": False, "authoritative_issuer_count_before": 13,
            "authoritative_issuer_count_after": 13, "no_value_ranking_target_recommendation_sizing_probability_pit": True,
            "network_used": False, "new_provider": False, "is_actionable": False}}
    artifact.update(content_identity(artifact))
    return artifact
