"""Qualified, historical-only fundamental analytics for the corporate research cohort.

This is the canonical analytical layer above already-qualified annual facts.  It is pure:
there are no provider calls, prices, rankings, forecasts, or I/O.  Every calculated field
names the fact identities that supplied it and fails closed on a scope, period, unit, currency
or denominator incompatibility.
"""
from __future__ import annotations

from typing import Any, Mapping

SCHEMA_VERSION = "1.0.0"
CORE = ("cash_and_equivalents", "net_income", "operating_cash_flow",
        "shareholders_equity", "total_interest_bearing_debt")


def _map(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _period(row: Mapping[str, Any]) -> str | None:
    identity = _map(row.get("period_identity"))
    value = identity.get("period") or row.get("reporting_period")
    return str(value) if value is not None else None


def _is_qualified_annual(row: Any) -> bool:
    identity = _map(_map(row).get("period_identity"))
    return (isinstance(row, Mapping) and row.get("quality_state") == "available"
            and row.get("value") is not None and row.get("statement_scope") == "consolidated"
            and identity.get("period_type") == "annual" and _period(row) is not None)


def _reference(row: Mapping[str, Any]) -> dict[str, Any]:
    evidence = _map(row.get("evidence"))
    return {"canonical_metric": row.get("canonical_metric"), "reporting_period": _period(row),
            "value": row.get("value"), "currency": row.get("currency"), "unit_scale": row.get("unit_scale"),
            "statement_scope": row.get("statement_scope"), "citation_id": evidence.get("citation_id"),
            "evidence_id": evidence.get("evidence_id"),
            "observation_ids": sorted(str(value) for value in (row.get("observation_ids") or []) if value)}


def _metric(status: str, *, value: float | int | None = None, applicability: str = "applicable",
            reason_codes: list[str] | None = None, inputs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"status": status, "value": value, "applicability": applicability,
            "reason_codes": sorted(set(reason_codes or [])), "source_fact_identities": inputs or []}


def adapt_official_annual_facts(records: list[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """Adapt the existing official annual projection to this canonical reader shape.

    This is an authority-preserving field mapping only: it does not infer values, aggregate
    debt, change scope, or promote a non-official record.  The caller retains the original
    projection separately; the returned rows carry its citation, evidence and source IDs.
    """
    output = []
    for record in records or []:
        if not isinstance(record, Mapping) or record.get("canonical_metric") not in CORE:
            continue
        if record.get("status") not in {"official_reported", "qualified"}:
            continue
        if record.get("period_type") != "annual" or record.get("statement_scope") != "consolidated":
            continue
        if record.get("value") is None or not record.get("reporting_period"):
            continue
        output.append({
            "canonical_metric": record.get("canonical_metric"), "value": record.get("value"),
            "quality_state": "available", "period_identity": {"period": str(record["reporting_period"]), "period_type": "annual"},
            "statement_scope": "consolidated", "currency": record.get("currency"),
            "unit_scale": record.get("scale"), "source": record.get("provider"),
            "observation_ids": list(record.get("source_observation_ids") or []),
            "evidence": {"evidence_id": record.get("evidence_id"), "citation_id": record.get("citation_id")},
        })
    return sorted(output, key=lambda row: (str(row["period_identity"]["period"]), str(row["canonical_metric"])))


def merge_official_annual_facts(financial_canonical: Mapping[str, Any] | None,
                                official_records: list[Mapping[str, Any]] | None) -> dict[str, Any]:
    """Overlay exact official annual rows on an existing canonical reader input."""
    base = _map(financial_canonical)
    official = adapt_official_annual_facts(official_records)
    official_keys = {(row["canonical_metric"], row["period_identity"]["period"]) for row in official}
    retained = [dict(row) for row in base.get("records") or [] if isinstance(row, Mapping)
                and (row.get("canonical_metric"), _period(row)) not in official_keys]
    return {**base, "status": base.get("status", "available"), "records": retained + official}


def _candidates(financial_canonical: Mapping[str, Any]) -> tuple[dict[str, dict[str, dict[str, Any]]], list[str]]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in financial_canonical.get("records") or []:
        if not _is_qualified_annual(row) or row.get("canonical_metric") not in CORE:
            continue
        grouped.setdefault(_period(row), {}).setdefault(str(row["canonical_metric"]), []).append(dict(row))
    selected: dict[str, dict[str, dict[str, Any]]] = {}
    blocked: list[str] = []
    for period, by_metric in grouped.items():
        selected[period] = {}
        for name, rows in by_metric.items():
            values = {row.get("value") for row in rows}
            if len(rows) == 1:
                selected[period][name] = rows[0]
            elif len(values) == 1:
                blocked.append(f"duplicate_qualified_fact:{period}:{name}")
            else:
                blocked.append(f"conflicting_qualified_fact:{period}:{name}")
    return selected, sorted(set(blocked))


def _same_unit(*rows: Mapping[str, Any] | None) -> bool:
    return all(row is not None for row in rows) and len({row.get("currency") for row in rows if row}) == 1 and len({row.get("unit_scale") for row in rows if row}) == 1


def _period_analytics(period: str, facts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    get = facts.get
    cash, income, ocf, equity, debt = (get(name) for name in CORE)
    refs = {name: _reference(row) for name, row in facts.items()}
    metrics: dict[str, dict[str, Any]] = {}
    if income is None:
        metrics["earnings_state"] = _metric("unavailable", applicability="blocked", reason_codes=["net_income_missing"])
    else:
        state = "profitable" if income["value"] > 0 else "loss_making" if income["value"] < 0 else "break_even"
        metrics["earnings_state"] = _metric("available", value=income["value"], reason_codes=[state], inputs=[refs["net_income"]])
    if ocf is None:
        metrics["operating_cash_flow_state"] = _metric("unavailable", applicability="blocked", reason_codes=["operating_cash_flow_missing"])
    else:
        state = "positive" if ocf["value"] > 0 else "negative" if ocf["value"] < 0 else "zero"
        metrics["operating_cash_flow_state"] = _metric("available", value=ocf["value"], reason_codes=[f"operating_cash_flow_{state}"], inputs=[refs["operating_cash_flow"]])
    if not _same_unit(ocf, income):
        metrics["operating_cash_flow_to_net_income"] = _metric("unavailable", applicability="blocked", reason_codes=["cash_conversion_currency_or_scale_mismatch"])
    elif income["value"] <= 0:
        metrics["operating_cash_flow_to_net_income"] = _metric("not_applicable", applicability="not_applicable", reason_codes=["net_income_nonpositive_ratio_interpretation_not_applicable"], inputs=[refs["operating_cash_flow"], refs["net_income"]])
    else:
        ratio = ocf["value"] / income["value"]
        metrics["operating_cash_flow_to_net_income"] = _metric("available", value=ratio,
            reason_codes=["cash_conversion_positive" if ratio > 0 else "earnings_positive_operating_cash_flow_negative"],
            inputs=[refs["operating_cash_flow"], refs["net_income"]])
    if not _same_unit(debt, equity) or equity["value"] == 0:
        metrics["debt_to_equity"] = _metric("unavailable", applicability="blocked", reason_codes=["debt_equity_currency_scale_or_zero_denominator"])
    else:
        metrics["debt_to_equity"] = _metric("available", value=debt["value"] / equity["value"], inputs=[refs["total_interest_bearing_debt"], refs["shareholders_equity"]])
    if not _same_unit(cash, debt):
        metrics["cash_to_debt"] = _metric("unavailable", applicability="blocked", reason_codes=["cash_debt_currency_or_scale_mismatch"])
        metrics["net_debt"] = _metric("unavailable", applicability="blocked", reason_codes=["cash_debt_currency_or_scale_mismatch"])
    elif debt["value"] == 0:
        metrics["cash_to_debt"] = _metric("not_applicable", applicability="not_applicable", reason_codes=["debt_zero_denominator"], inputs=[refs["cash_and_equivalents"], refs["total_interest_bearing_debt"]])
        metrics["net_debt"] = _metric("available", value=-cash["value"], reason_codes=["net_cash_position"], inputs=[refs["cash_and_equivalents"], refs["total_interest_bearing_debt"]])
    else:
        net_debt = debt["value"] - cash["value"]
        metrics["cash_to_debt"] = _metric("available", value=cash["value"] / debt["value"], inputs=[refs["cash_and_equivalents"], refs["total_interest_bearing_debt"]])
        metrics["net_debt"] = _metric("available", value=net_debt, reason_codes=["net_debt_position" if net_debt > 0 else "net_cash_position" if net_debt < 0 else "cash_equals_debt"], inputs=[refs["cash_and_equivalents"], refs["total_interest_bearing_debt"]])
    net_debt = metrics["net_debt"]
    if net_debt["status"] != "available" or not _same_unit(cash, debt, equity) or equity["value"] == 0:
        metrics["net_debt_to_equity"] = _metric("unavailable", applicability="blocked", reason_codes=["net_debt_equity_currency_scale_or_zero_denominator"])
    else:
        metrics["net_debt_to_equity"] = _metric("available", value=net_debt["value"] / equity["value"], inputs=[*net_debt["source_fact_identities"], refs["shareholders_equity"]])
    return {"reporting_period": period, "currency": next(iter({row.get("currency") for row in facts.values()}), None),
            "unit_scale": next(iter({row.get("unit_scale") for row in facts.values()}), None), "metrics": metrics,
            "source_facts": [refs[name] for name in sorted(refs)]}


def _predicates(metrics: Mapping[str, Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    risks, strengths = [], []
    earnings, ocf, net_debt = metrics.get("earnings_state", {}), metrics.get("operating_cash_flow_state", {}), metrics.get("net_debt", {})
    if "loss_making" in earnings.get("reason_codes", []): risks.append({"predicate": "loss_making_period", "sources": earnings.get("source_fact_identities", [])})
    if "operating_cash_flow_negative" in ocf.get("reason_codes", []): risks.append({"predicate": "negative_operating_cash_flow", "sources": ocf.get("source_fact_identities", [])})
    if "earnings_positive_operating_cash_flow_negative" in metrics.get("operating_cash_flow_to_net_income", {}).get("reason_codes", []): risks.append({"predicate": "earnings_positive_operating_cash_flow_negative", "sources": metrics["operating_cash_flow_to_net_income"].get("source_fact_identities", [])})
    if "net_debt_position" in net_debt.get("reason_codes", []): risks.append({"predicate": "net_debt_position", "sources": net_debt.get("source_fact_identities", [])})
    if "profitable" in earnings.get("reason_codes", []): strengths.append({"predicate": "positive_earnings", "sources": earnings.get("source_fact_identities", [])})
    if "operating_cash_flow_positive" in ocf.get("reason_codes", []): strengths.append({"predicate": "positive_operating_cash_flow", "sources": ocf.get("source_fact_identities", [])})
    if "cash_conversion_positive" in metrics.get("operating_cash_flow_to_net_income", {}).get("reason_codes", []): strengths.append({"predicate": "positive_cash_conversion", "sources": metrics["operating_cash_flow_to_net_income"].get("source_fact_identities", [])})
    if "net_cash_position" in net_debt.get("reason_codes", []): strengths.append({"predicate": "net_cash_position", "sources": net_debt.get("source_fact_identities", [])})
    return risks, strengths


def build(ticker: str, financial_canonical: Mapping[str, Any] | None) -> dict[str, Any]:
    source = financial_canonical if isinstance(financial_canonical, Mapping) else {}
    candidates, blocked = _candidates(source)
    complete = {period: rows for period, rows in candidates.items() if all(metric in rows for metric in CORE)}
    periods = sorted(complete)
    if not periods:
        return {"schema_version": SCHEMA_VERSION, "ticker": str(ticker).upper(), "status": "unavailable", "historical_only": True, "market_dependent": False, "is_actionable": False, "qualified_annual_periods": [], "trend_status": "insufficient_history", "metrics": {}, "risk_predicates": [], "strength_predicates": [], "scenarios": {}, "historical_conclusion": {"code": "insufficient_evidence", "reason_codes": ["complete_qualified_annual_metric_set_missing"], "source_fact_identities": []}, "blocking_reasons": sorted(set(blocked + ["complete_qualified_annual_metric_set_missing"]))}
    latest = periods[-1]
    analysis = _period_analytics(latest, complete[latest])
    risks, strengths = _predicates(analysis["metrics"])
    trend = {"status": "available", "periods": periods[-2:]} if len(periods) >= 2 else {"status": "insufficient_history", "periods": periods}
    risk_names, strength_names = [x["predicate"] for x in risks], [x["predicate"] for x in strengths]
    if {"loss_making_period", "negative_operating_cash_flow"}.issubset(risk_names): code = "historically_loss_and_cashflow_stressed"
    elif "net_debt_position" in risk_names and not strengths: code = "historically_leverage_sensitive"
    elif {"positive_earnings", "positive_operating_cash_flow", "net_cash_position"}.issubset(strength_names): code = "historically_financially_resilient"
    else: code = "historically_mixed"
    scenarios = {
        "bear": {"status": "available", "kind": "conditional_hypothesis", "required_conditions": [f"next qualified annual reporting retains: {name}" for name in risk_names] or ["next qualified annual reporting weakens a cited fundamental condition"], "market_claims": False},
        "base": {"status": "available", "kind": "conditional_hypothesis", "required_conditions": ["next qualified annual reporting remains scope, currency, and evidence compatible with the cited period"], "market_claims": False},
        "bull": {"status": "available", "kind": "conditional_hypothesis", "required_conditions": [f"next qualified annual reporting retains or adds: {name}" for name in strength_names] or ["next qualified annual reporting improves a cited fundamental condition"], "market_claims": False},
    }
    return {"schema_version": SCHEMA_VERSION, "ticker": str(ticker).upper(), "status": "available", "historical_only": True, "market_dependent": False, "is_actionable": False, "qualified_annual_periods": periods, "analysis_period": latest, "currency": analysis["currency"], "unit_scale": analysis["unit_scale"], "metrics": analysis["metrics"], "risk_predicates": risks, "strength_predicates": strengths, "trend_status": trend["status"], "trend": trend, "scenarios": scenarios, "invalidation_conditions": ["A later qualified annual fact changes a cited predicate.", "A cited source fact loses annual, consolidated, currency, unit, or provenance compatibility."], "historical_conclusion": {"code": code, "reason_codes": sorted(risk_names + strength_names + [trend["status"]]), "source_fact_identities": analysis["source_facts"], "confidence_state": "single_period_historical" if len(periods) == 1 else "multi_period_historical"}, "blocking_reasons": blocked}


def build_comparative_matrix(analyses: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Return a descriptive cohort artifact without cross-ticker ranking or FX conversion.

    Ratios and categorical states retain their ticker-local provenance.  Absolute monetary
    amounts are intentionally excluded so VND and USD reporters are never compared.
    """
    rows: list[dict[str, Any]] = []
    def comparable_metric(value: Mapping[str, Any], *, include_value: bool) -> dict[str, Any]:
        result = {"status": value.get("status"), "applicability": value.get("applicability"),
                  "reason_codes": list(value.get("reason_codes") or [])}
        if include_value and value.get("status") == "available":
            result["value"] = value.get("value")
        result["source_fact_identities"] = [
            {key: source.get(key) for key in ("canonical_metric", "reporting_period", "currency", "unit_scale", "citation_id", "evidence_id")}
            for source in value.get("source_fact_identities") or [] if isinstance(source, Mapping)
        ]
        return result
    for ticker in sorted(str(value).upper() for value in analyses):
        analysis = _map(analyses.get(ticker))
        metrics = _map(analysis.get("metrics"))
        include = ("earnings_state", "operating_cash_flow_state", "operating_cash_flow_to_net_income",
                   "debt_to_equity", "cash_to_debt", "net_debt_to_equity")
        rows.append({
            "ticker": ticker,
            "status": analysis.get("status", "unavailable"),
            "analysis_period": analysis.get("analysis_period"),
            "qualified_annual_periods": list(analysis.get("qualified_annual_periods") or []),
            "trend_status": analysis.get("trend_status", "insufficient_history"),
            "metrics": {name: comparable_metric(_map(metrics.get(name)), include_value=name not in {"earnings_state", "operating_cash_flow_state"}) for name in include},
            "historical_conclusion_code": _map(analysis.get("historical_conclusion")).get("code"),
            "risk_predicates": [item.get("predicate") for item in analysis.get("risk_predicates") or [] if isinstance(item, Mapping)],
            "strength_predicates": [item.get("predicate") for item in analysis.get("strength_predicates") or [] if isinstance(item, Mapping)],
            "limitations": list(analysis.get("blocking_reasons") or []),
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "available" if rows else "unavailable",
        "historical_only": True,
        "market_dependent": False,
        "is_actionable": False,
        "descriptive_only": True,
        "ranking_prohibited": True,
        "fx_conversion_prohibited": True,
        "absolute_monetary_comparisons_prohibited": True,
        "rows": rows,
        "limitations": [
            "Rows are ticker-local qualified annual observations, not a ranking or recommendation.",
            "USD and VND monetary amounts are not converted or compared across tickers.",
            "Trend statements require at least two complete qualified annual periods for that ticker.",
        ],
    }
