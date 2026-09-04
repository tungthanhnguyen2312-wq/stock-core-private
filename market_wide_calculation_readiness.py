"""Deterministic market-wide calculation readiness over canonical financial facts.

WHAT THIS IS
    Layer 4 of `docs/market_wide_financial_normalization_contract.md`, fed market-wide instead
    of per ticker. It decides, for each ticker-period, whether EBITDA, market capitalisation,
    enterprise value, EV/EBITDA, P/E, P/B and ROE may be computed **at all**, and computes the
    ones that may. It introduces no new valuation model, produces no score, and ranks nothing.

WHAT "READY" MEANS HERE
    Not "the inputs exist". Ready means every input is a canonical fact whose status is usable,
    and the inputs satisfy an explicit compatibility contract: one period, one statement scope,
    one currency, one unit scale, one cumulative basis, one sign convention, and -- for any
    metric that spans two statements -- a passing cross-statement coherence check. An input set
    that fails any clause yields `blocked` with the failing clause named, never a number.

THE EBITDA RECONCILIATION CONTRACT

        ebitda = profit_before_tax + interest_expense + depreciation_and_amortization

    Every term is a canonical fact, and the result carries its formula lineage: the three
    source `fact_id`s, each term's status, and the reconciliation identity itself, so the
    number can be re-derived and audited without re-reading the payloads.

    Two clauses in that contract do real work:

    * **Sign.** The formula adds interest and depreciation back to pre-tax profit, which is
      only correct if those lines are carried as positive magnitudes. The sign convention is
      resolved from the statement's own gross-profit arithmetic; where it is `unknown` the
      addition is not performed, because adding a negative expense would silently subtract it.
    * **Cross-statement coherence.** `profit_before_tax` is an income-statement fact and
      `depreciation_and_amortization` is a cash-flow fact. The retained cash-flow payloads
      carry period labels that do not always identify the period their numbers describe, so
      the canonical fact layer marks a cash-flow fact `conflicted` when end-of-period cash
      disagrees with the balance sheet. Those facts are refused here rather than blended.

WHY ENTERPRISE VALUE IS ZERO AND SAYS SO PRECISELY
    EV needs market capitalisation, which needs a share count and a price. Neither exists as a
    qualified input: no retained provider line carries a share count (`common_shares` is a
    paid-in capital amount in currency, and converting it needs an assumed par value), and the
    price basis is `unknown / verified: false` universe-wide. So EV is `blocked`, and the block
    names both causes separately instead of collapsing them into "no data".

    The balance-sheet half of EV -- interest-bearing debt and cash -- **is** ready for a large
    part of the universe, and that is reported, because it is what will make EV immediately
    computable once pillar B qualifies a price basis. Reporting it is not a claim that EV is
    available.

THE THREE MARKET-CAPITALISATION IDENTITIES ARE NEVER CONFLATED
    snapshot          current price x current shares. Screening only.
    historical_point_in_time   price on a stated past date x shares on that date.
    unavailable       neither is qualified.

    A snapshot market capitalisation, if one existed, would license current screening and
    nothing else. It would never license an adjusted return, a backtest, a volatility, a beta
    or a risk ranking, all of which need a qualified *series*, not a point. This module
    therefore emits no series and sets no actionability flag.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from canonical_financial_facts import (
    STATUS_CONFLICTED,
    STATUS_NOT_APPLICABLE,
    STATUS_PARTIAL,
    STATUS_PROVIDER_REPORTED,
    STATUS_QUALIFIED,
    STATUS_UNAVAILABLE,
)
from canonical_financial_resolvers import UNKNOWN

VERSION = "1.0.0"
POLICY_VERSION = "market-wide-calculation-readiness/1.0.0"

READY = "ready"
BLOCKED = "blocked"
NOT_APPLICABLE = "not_applicable"

#: Statuses a computation may consume. `partial` is admitted but never silently: it forces the
#: result to `partial` too and records which term was substituted.
USABLE_STATUSES = (STATUS_QUALIFIED, STATUS_PROVIDER_REPORTED, STATUS_PARTIAL)
STRICT_STATUSES = (STATUS_QUALIFIED, STATUS_PROVIDER_REPORTED)

#: The reconciliation identity, recorded on every EBITDA result as its lineage.
EBITDA_FORMULA = "profit_before_tax + interest_expense + depreciation_and_amortization"
EBITDA_TERMS = ("profit_before_tax", "interest_expense", "depreciation_and_amortization")

EV_FORMULA = "market_capitalisation + total_interest_bearing_debt - cash_and_cash_equivalents"
EV_TERMS = ("total_interest_bearing_debt", "cash_and_cash_equivalents")

#: Why market capitalisation is unavailable. Two independent causes, reported separately.
MARKET_CAP_BLOCKERS = (
    "share_count_not_evidenced_by_any_retained_provider_line",
    "price_basis_unknown_and_unverified_universe_wide",
)

#: Capabilities that a snapshot market capitalisation would still not unlock. Listed so the
#: boundary is explicit in the artifact rather than only in prose.
STILL_BLOCKED_BY_PRICE_BASIS = (
    "adjusted_return", "backtest", "volatility", "beta", "correlation",
    "risk_ranking", "historical_valuation_series", "position_sizing",
)


def _facts_by_period(facts: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Mapping[str, Any]]]:
    grouped: dict[str, dict[str, Mapping[str, Any]]] = {}
    for fact in facts:
        grouped.setdefault(str(fact["reporting_period"]), {})[str(fact["canonical_metric"])] = fact
    return grouped


def _compatibility(terms: Sequence[Mapping[str, Any]], *,
                   require_cross_statement: bool) -> list[str]:
    """Every compatibility clause the term set violates. Empty means compatible."""
    failures: list[str] = []
    if len({str(term["reporting_period"]) for term in terms}) > 1:
        failures.append("incompatible_reporting_periods")
    scopes = {str(term["statement_scope"]) for term in terms}
    if len(scopes) > 1:
        failures.append("incompatible_statement_scopes")
    if len({str(term["currency"]) for term in terms}) > 1:
        failures.append("incompatible_currencies")
    if len({str(term["scale"]) for term in terms}) > 1:
        failures.append("incompatible_unit_scales")
    bases = {str(term["cumulative_state"]) for term in terms}
    if len(bases) > 1:
        failures.append("incompatible_cumulative_bases")
    if any(str(term["status"]) == STATUS_CONFLICTED for term in terms):
        failures.append("conflicted_input_fact")
    if require_cross_statement:
        cross = {str(term["cross_statement_scale"]) for term in terms}
        if "divergent" in cross:
            failures.append("cross_statement_scale_divergent")
        if UNKNOWN in cross:
            failures.append("cross_statement_scale_unverifiable")
    return failures


def _result(metric: str, state: str, *, period: str, value: Any = None,
            reason: str = "", terms: Mapping[str, Any] | None = None,
            formula: str | None = None, status: str | None = None,
            blocked_by: Sequence[str] = (), warnings: Sequence[str] = ()) -> dict[str, Any]:
    return {
        "metric": metric,
        "reporting_period": period,
        "readiness": state,
        "status": status,
        "value": value,
        "formula": formula,
        "reason": reason,
        "blocked_by": list(blocked_by),
        "terms": dict(terms or {}),
        "warnings": sorted(set(warnings)),
        "policy_version": POLICY_VERSION,
    }


def evaluate_ebitda(period_facts: Mapping[str, Mapping[str, Any]], period: str,
                    applicability: Mapping[str, Any]) -> dict[str, Any]:
    """EBITDA for one ticker-period under the reconciliation contract, or a named block."""
    verdict = (applicability.get("metric_applicability") or {}).get("ebitda") or {}
    if verdict.get("status") == "not_applicable":
        return _result("ebitda", NOT_APPLICABLE, period=period,
                       status=STATUS_NOT_APPLICABLE,
                       reason=str(verdict.get("reason") or "metric undefined for this filer"),
                       blocked_by=["metric_not_defined_for_template_family"])

    terms = {name: period_facts.get(name) for name in EBITDA_TERMS}
    missing = sorted(name for name, fact in terms.items() if fact is None)
    if missing:
        return _result("ebitda", BLOCKED, period=period, status=STATUS_UNAVAILABLE,
                       formula=EBITDA_FORMULA,
                       reason=f"no canonical fact for: {', '.join(missing)}",
                       blocked_by=[f"missing_term:{name}" for name in missing])

    unusable = sorted(name for name, fact in terms.items()
                      if str(fact["status"]) not in USABLE_STATUSES)
    if unusable:
        return _result(
            "ebitda", BLOCKED, period=period,
            status=(STATUS_CONFLICTED
                    if any(str(terms[name]["status"]) == STATUS_CONFLICTED for name in unusable)
                    else STATUS_UNAVAILABLE),
            formula=EBITDA_FORMULA,
            reason=f"unusable term status: " + ", ".join(
                f"{name}={terms[name]['status']}" for name in unusable),
            blocked_by=[f"unusable_term:{name}:{terms[name]['status']}" for name in unusable],
            terms={name: fact["fact_id"] for name, fact in terms.items()})

    ordered = [terms[name] for name in EBITDA_TERMS]
    failures = _compatibility(ordered, require_cross_statement=True)

    signs = {str(fact["sign_convention"]) for fact in ordered}
    if UNKNOWN in signs:
        failures.append("sign_convention_unknown")
    elif signs != {"expenses_positive"}:
        # The add-back is only valid with expenses carried positive. Rather than negating and
        # hoping, refuse: a wrong sign here turns an add-back into a subtraction silently.
        failures.append("sign_convention_not_add_back_compatible")

    if failures:
        return _result("ebitda", BLOCKED, period=period, status=STATUS_CONFLICTED,
                       formula=EBITDA_FORMULA,
                       reason="compatibility contract failed: " + ", ".join(sorted(set(failures))),
                       blocked_by=sorted(set(failures)),
                       terms={name: fact["fact_id"] for name, fact in terms.items()})

    value = sum(float(fact["value"]) for fact in ordered)
    value = int(value) if float(value).is_integer() else value
    status = (STATUS_PARTIAL
              if any(str(fact["status"]) == STATUS_PARTIAL for fact in ordered)
              else (STATUS_QUALIFIED
                    if all(str(fact["status"]) == STATUS_QUALIFIED for fact in ordered)
                    else STATUS_PROVIDER_REPORTED))
    warnings = sorted({warning for fact in ordered for warning in fact["warnings"]})

    return _result(
        "ebitda", READY, period=period, value=value, status=status, formula=EBITDA_FORMULA,
        reason="all three terms usable, compatible and sign-consistent",
        terms={
            name: {
                "fact_id": fact["fact_id"], "value": fact["value"], "status": fact["status"],
                "raw_item_id": fact["raw_item_id"], "dialect": fact["dialect"],
                "source_observation_ids": fact["source_observation_ids"],
            }
            for name, fact in terms.items()
        },
        warnings=warnings)


def evaluate_market_capitalisation(period: str,
                                   session_price: float | int | None = None,
                                   effective_shares: Mapping[str, Any] | int | None = None,
                                   *, price_basis_verified: bool = False) -> dict[str, Any]:
    """Reconstructed current snapshot market cap when price and shares are resolved, or blocked.

    A market cap has two legs and is only as qualified as the weaker one. `price_basis_verified`
    is what carries the price leg's authority in; without it the result can never be
    `qualified`, however well-evidenced the share count is. The share leg contributes its
    concept as well as its value: an `ISSUED_SHARES` count does not deduct treasury shares, so
    a cap built on it is not comparable with one built on shares outstanding, and says so.
    """
    price_val = float(session_price) if session_price is not None and not isinstance(session_price, bool) and float(session_price) > 0 else None
    shares_val = None
    shares_status = STATUS_UNAVAILABLE
    shares_authority = "unresolved"
    shares_concept = "unknown_share_concept"
    if isinstance(effective_shares, Mapping):
        shares_val = effective_shares.get("value")
        shares_status = str(effective_shares.get("status") or effective_shares.get("qualification") or STATUS_UNAVAILABLE)
        shares_authority = str(effective_shares.get("authority") or "dated_shares_timeline")
        shares_concept = str(effective_shares.get("share_concept") or "unknown_share_concept")
    elif isinstance(effective_shares, (int, float)) and not isinstance(effective_shares, bool) and effective_shares > 0:
        shares_val = int(effective_shares)
        shares_status = STATUS_QUALIFIED
        shares_authority = "official_shares_fact"
        shares_concept = "current_common_shares_outstanding"

    if price_val is not None and shares_val is not None and shares_val > 0:
        market_cap_val = round(price_val * shares_val, 2)
        shares_qualified = shares_status in (STATUS_QUALIFIED, "qualified", "current_qualified")
        status = STATUS_QUALIFIED if (shares_qualified and price_basis_verified) else STATUS_PROVIDER_REPORTED
        warnings = ["current_snapshot_only_does_not_unlock_historical_series_or_backtest"]
        if not price_basis_verified:
            warnings.append("price_basis_unverified_market_capitalisation_cannot_be_qualified")
        if shares_concept == "ISSUED_SHARES":
            warnings.append("share_count_is_issued_shares_treasury_not_deducted_not_comparable_"
                            "with_shares_outstanding")
        return _result(
            "market_capitalisation", READY, period=period, value=market_cap_val, status=status,
            formula="resolved_session_price * current_effective_shares",
            reason="current snapshot reconstructed from resolved session price and current effective shares outstanding",
            terms={
                "session_price": price_val,
                "price_basis_verified": bool(price_basis_verified),
                "current_effective_shares": shares_val,
                "shares_authority": shares_authority,
                "share_concept": shares_concept,
                "basis_type": "current_snapshot",
            },
            warnings=warnings)

    return _result(
        "market_capitalisation", BLOCKED, period=period, status=STATUS_UNAVAILABLE,
        reason=("no retained provider line carries a share count, and the price basis is "
                "unknown and unverified universe-wide"),
        blocked_by=list(MARKET_CAP_BLOCKERS),
        warnings=["snapshot_market_capitalisation_unavailable",
                  "historical_point_in_time_market_capitalisation_unavailable"])


def evaluate_enterprise_value(period_facts: Mapping[str, Mapping[str, Any]], period: str,
                              market_cap: Mapping[str, Any]) -> dict[str, Any]:
    """EV, plus whether its balance-sheet half would be ready if a price basis existed."""
    terms = {name: period_facts.get(name) for name in EV_TERMS}
    missing = sorted(name for name, fact in terms.items() if fact is None)
    components_ready = False
    component_failures: list[str] = []

    if not missing:
        unusable = [name for name, fact in terms.items()
                    if str(fact["status"]) not in USABLE_STATUSES]
        component_failures = _compatibility(list(terms.values()), require_cross_statement=False)
        component_failures.extend(f"unusable_term:{name}" for name in sorted(unusable))
        components_ready = not component_failures
    else:
        component_failures = [f"missing_term:{name}" for name in missing]

    if market_cap["readiness"] == READY and components_ready:
        debt = float(terms["total_interest_bearing_debt"]["value"])
        cash = float(terms["cash_and_cash_equivalents"]["value"])
        ev_val = round(float(market_cap["value"]) + debt - cash, 2)
        status = STATUS_QUALIFIED if market_cap["status"] == STATUS_QUALIFIED and all(str(f["status"]) == STATUS_QUALIFIED for f in terms.values()) else STATUS_PROVIDER_REPORTED
        return _result(
            "enterprise_value", READY, period=period, value=ev_val, status=status,
            formula=EV_FORMULA,
            reason="current market capitalisation and balance-sheet terms available and compatible",
            terms={
                "market_capitalisation": market_cap["value"],
                "total_interest_bearing_debt": debt,
                "cash_and_cash_equivalents": cash,
            },
            warnings=["current_snapshot_enterprise_value_only"])

    blocked_by = list(market_cap["blocked_by"]) + sorted(set(component_failures))
    return _result(
        "enterprise_value", BLOCKED, period=period, status=STATUS_UNAVAILABLE,
        formula=EV_FORMULA,
        reason=("market capitalisation is unavailable, so enterprise value cannot be computed "
                "for any ticker regardless of balance-sheet coverage"),
        blocked_by=blocked_by,
        terms={"balance_sheet_components_ready": components_ready,
               **{name: (fact["fact_id"] if fact else None) for name, fact in terms.items()}},
        warnings=["historical_enterprise_value_unavailable"])


def evaluate_ev_ebitda(ebitda: Mapping[str, Any], enterprise_value: Mapping[str, Any],
                       period: str) -> dict[str, Any]:
    if ebitda["readiness"] == NOT_APPLICABLE:
        return _result("ev_ebitda", NOT_APPLICABLE, period=period, status=STATUS_NOT_APPLICABLE,
                       reason="EBITDA is not defined for this filer, so neither is EV/EBITDA",
                       blocked_by=["metric_not_defined_for_template_family"])
    if enterprise_value["readiness"] == READY and ebitda["readiness"] == READY and float(ebitda["value"]) > 0:
        val = round(float(enterprise_value["value"]) / float(ebitda["value"]), 4)
        status = STATUS_QUALIFIED if enterprise_value["status"] == STATUS_QUALIFIED and ebitda["status"] == STATUS_QUALIFIED else STATUS_PROVIDER_REPORTED
        return _result(
            "ev_ebitda", READY, period=period, value=val, status=status,
            formula="enterprise_value / ebitda",
            reason="enterprise value and EBITDA are ready and compatible",
            terms={"enterprise_value": enterprise_value["value"], "ebitda": ebitda["value"]})

    blocked_by = list(enterprise_value["blocked_by"])
    reason = "enterprise value or EBITDA is unavailable"
    if ebitda["readiness"] != READY:
        blocked_by.append("ebitda_not_ready")
    elif float(ebitda["value"]) <= 0:
        # EBITDA is a genuine, usable fact here -- just not a positive one. Falling through to
        # the generic "unavailable" reason above would be indistinguishable from a missing
        # input, when this is instead the explicit non-fabrication refusal the negative/zero
        # denominator invariant requires: a negative or zero EBITDA multiple is not meaningful
        # and is never computed, exactly like PE_NOT_MEANINGFUL for negative earnings elsewhere.
        blocked_by.append("negative_or_zero_ebitda_denominator")
        reason = "EBITDA is zero or negative; EV/EBITDA is not a meaningful multiple"
    return _result("ev_ebitda", BLOCKED, period=period, status=STATUS_UNAVAILABLE,
                   formula="enterprise_value / ebitda",
                   reason=reason,
                   blocked_by=sorted(set(blocked_by)))


def evaluate_price_ratio(metric: str, denominator: Mapping[str, Any] | None, period: str,
                         market_cap: Mapping[str, Any], denominator_name: str) -> dict[str, Any]:
    """P/E and P/B. Calculated when current market cap and fundamental denominator are ready."""
    blocked_by = list(market_cap["blocked_by"])
    denominator_ready = (denominator is not None
                         and str(denominator["status"]) in USABLE_STATUSES)
    if denominator is None:
        blocked_by.append(f"missing_term:{denominator_name}")
    elif not denominator_ready:
        blocked_by.append(f"unusable_term:{denominator_name}:{denominator['status']}")

    if market_cap["readiness"] == READY and denominator_ready and float(denominator["value"]) != 0:
        ratio_val = round(float(market_cap["value"]) / float(denominator["value"]), 4)
        status = STATUS_QUALIFIED if market_cap["status"] == STATUS_QUALIFIED and str(denominator["status"]) == STATUS_QUALIFIED else STATUS_PROVIDER_REPORTED
        return _result(
            metric, READY, period=period, value=ratio_val, status=status,
            formula=f"market_capitalisation / {denominator_name}",
            reason=f"current market capitalisation and {denominator_name} are ready",
            terms={"market_capitalisation": market_cap["value"], denominator_name: denominator["fact_id"]})

    return _result(
        metric, BLOCKED, period=period, status=STATUS_UNAVAILABLE,
        formula=f"market_capitalisation / {denominator_name}",
        reason="market capitalisation is unavailable",
        blocked_by=sorted(set(blocked_by)),
        terms={"denominator_ready": denominator_ready,
               denominator_name: denominator["fact_id"] if denominator else None})


def evaluate_roe(period_facts: Mapping[str, Mapping[str, Any]], period: str) -> dict[str, Any]:
    """Return on equity -- the one ratio here that needs no price at all.

    Reported as a single-period ratio and never annualised. The retained payloads are
    quarterly and their cumulative basis is frequently `unknown`, so multiplying a quarter by
    four would manufacture a trailing-twelve-month figure the evidence does not support.
    """
    net_income = period_facts.get("net_income")
    equity = period_facts.get("shareholders_equity")
    missing = [name for name, fact in (("net_income", net_income),
                                       ("shareholders_equity", equity)) if fact is None]
    if missing:
        return _result("roe", BLOCKED, period=period, status=STATUS_UNAVAILABLE,
                       formula="net_income / shareholders_equity",
                       reason=f"no canonical fact for: {', '.join(missing)}",
                       blocked_by=[f"missing_term:{name}" for name in missing])

    unusable = [name for name, fact in (("net_income", net_income),
                                        ("shareholders_equity", equity))
                if str(fact["status"]) not in USABLE_STATUSES]
    failures = _compatibility([net_income, equity], require_cross_statement=False)
    failures.extend(f"unusable_term:{name}" for name in unusable)
    try:
        denominator = float(equity["value"])
    except (TypeError, ValueError):
        denominator = 0.0
    if denominator == 0.0:
        failures.append("zero_or_non_numeric_equity")

    if failures:
        return _result("roe", BLOCKED, period=period, status=STATUS_CONFLICTED,
                       formula="net_income / shareholders_equity",
                       reason="compatibility contract failed: " + ", ".join(sorted(set(failures))),
                       blocked_by=sorted(set(failures)))

    value = round(float(net_income["value"]) / denominator, 10)
    status = (STATUS_PARTIAL
              if STATUS_PARTIAL in {str(net_income["status"]), str(equity["status"])}
              else (STATUS_QUALIFIED
                    if {str(net_income["status"]), str(equity["status"])} == {STATUS_QUALIFIED}
                    else STATUS_PROVIDER_REPORTED))
    return _result(
        "roe", READY, period=period, value=value, status=status,
        formula="net_income / shareholders_equity",
        reason="both terms usable and compatible; single-period ratio, not annualised",
        terms={"net_income": {"fact_id": net_income["fact_id"], "value": net_income["value"],
                              "status": net_income["status"]},
               "shareholders_equity": {"fact_id": equity["fact_id"], "value": equity["value"],
                                       "status": equity["status"]}},
        warnings=["single_period_ratio_not_annualised"])


def evaluate_ticker(ticker: str, facts: Sequence[Mapping[str, Any]],
                    applicability: Mapping[str, Any],
                    session_price: float | int | None = None,
                    effective_shares: Mapping[str, Any] | int | None = None,
                    *, price_basis_verified: bool = False) -> dict[str, Any]:
    """Every readiness verdict for one ticker, one entry per period."""
    by_period = _facts_by_period(facts)
    periods: list[dict[str, Any]] = []
    for period in sorted(by_period):
        period_facts = by_period[period]
        ebitda = evaluate_ebitda(period_facts, period, applicability)
        market_cap = evaluate_market_capitalisation(period, session_price=session_price,
                                                    effective_shares=effective_shares,
                                                    price_basis_verified=price_basis_verified)
        enterprise_value = evaluate_enterprise_value(period_facts, period, market_cap)
        periods.append({
            "reporting_period": period,
            "ebitda": ebitda,
            "market_capitalisation": market_cap,
            "enterprise_value": enterprise_value,
            "ev_ebitda": evaluate_ev_ebitda(ebitda, enterprise_value, period),
            "pe": evaluate_price_ratio("pe", period_facts.get("net_income"), period,
                                       market_cap, "net_income"),
            "pb": evaluate_price_ratio("pb", period_facts.get("shareholders_equity"), period,
                                       market_cap, "shareholders_equity"),
            "roe": evaluate_roe(period_facts, period),
        })
    return {
        "ticker": str(ticker).upper(),
        "policy_version": POLICY_VERSION,
        "readiness_version": VERSION,
        "periods": periods,
        "still_blocked_by_price_basis": list(STILL_BLOCKED_BY_PRICE_BASIS),
    }


CAPABILITIES = ("ebitda", "market_capitalisation", "enterprise_value", "ev_ebitda",
                "pe", "pb", "roe")


def build_readiness_report(per_ticker: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Deterministic market-wide readiness counts. Counts and reasons only, never a ranking."""
    ready_tickers: dict[str, set[str]] = {name: set() for name in CAPABILITIES}
    not_applicable: dict[str, set[str]] = {name: set() for name in CAPABILITIES}
    blocked_reasons: dict[str, dict[str, int]] = {name: {} for name in CAPABILITIES}
    ev_components_ready: set[str] = set()
    ticker_count = 0

    for entry in per_ticker:
        ticker_count += 1
        ticker = str(entry["ticker"])
        for period in entry["periods"]:
            for name in CAPABILITIES:
                verdict = period[name]
                if verdict["readiness"] == READY:
                    ready_tickers[name].add(ticker)
                elif verdict["readiness"] == NOT_APPLICABLE:
                    not_applicable[name].add(ticker)
                else:
                    for reason in verdict["blocked_by"]:
                        bucket = blocked_reasons[name]
                        bucket[reason] = bucket.get(reason, 0) + 1
            if period["enterprise_value"]["terms"].get("balance_sheet_components_ready"):
                ev_components_ready.add(ticker)

    return {
        "policy_version": POLICY_VERSION,
        "readiness_version": VERSION,
        "ticker_count": ticker_count,
        "ready_ticker_counts": {name: len(ready_tickers[name]) for name in CAPABILITIES},
        "not_applicable_ticker_counts": {name: len(not_applicable[name]) for name in CAPABILITIES},
        "enterprise_value_balance_sheet_components_ready": len(ev_components_ready),
        "top_blockers": {
            name: dict(sorted(blocked_reasons[name].items(),
                              key=lambda item: (-item[1], item[0]))[:12])
            for name in CAPABILITIES
        },
        "market_capitalisation_blockers": list(MARKET_CAP_BLOCKERS),
        "still_blocked_by_price_basis": list(STILL_BLOCKED_BY_PRICE_BASIS),
        "ready_tickers": {name: sorted(ready_tickers[name])[:200] for name in CAPABILITIES},
    }
