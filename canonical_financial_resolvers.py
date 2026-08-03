"""Deterministic scope / unit / sign / basis resolvers for canonical financial facts.

WHAT THIS IS
    Layer 3's evidence layer. Before a raw observation may be called a canonical fact, five
    dimensions the retained payloads never state have to be resolved: statement scope,
    currency, unit scale, sign convention and cumulative-vs-period-only basis. This module
    resolves each one **only from evidence the retained payloads actually carry**, and
    returns `unknown` whenever they do not carry it.

THE RULE THAT SHAPES EVERY FUNCTION HERE
    `docs/market_wide_financial_normalization_contract.md` layer 3, and the milestone brief:
    *do not infer a qualified value from provider conventions unless the convention is
    directly demonstrated and documented.* Vietnamese listed issuers do file in VND under
    VAS, and their quarterly cash-flow statements usually are cumulative year-to-date. Both
    are conventions. Neither is written anywhere in the retained bytes, so neither is
    asserted here. What is asserted is what the numbers themselves demonstrate.

WHAT EACH RESOLVER CAN AND CANNOT DEMONSTRATE

    statement_scope
        A non-zero `minority_interests` line can only exist in a consolidated statement, so
        it *grants* `consolidated`. A zero or absent line grants nothing: a consolidated
        group with no non-controlling interest looks identical to a separate statement. The
        asymmetry is deliberate and mirrors the taxonomy authority rule in
        `financial_entity_applicability.py` -- positive evidence resolves, absence never does.

    sign_convention
        Demonstrated by the statement's own arithmetic: whether `gross_profit` reconciles to
        `revenue + cost_of_goods_sold` (costs carried negative) or `revenue - cost_of_goods_sold`
        (costs carried positive). Measured over the retained universe this is `expenses_positive`
        wherever it is determinable at all, but it is re-derived per payload rather than
        assumed, because a single provider changing convention would otherwise flip every
        expense-bearing metric silently.

    balance_identity
        `total_assets == liabilities + owners_equity` demonstrates that the balance sheet's
        own line items share one scale and one sign convention. A violation is a real
        conflict, not a rounding nuisance, and downgrades every balance-sheet metric.

    cross_statement_scale
        `balance_sheet.cash_and_cash_equivalents` must equal the cash-flow statement's
        end-of-period cash for the same period. This is the only direct evidence in the
        retained payloads that a balance-sheet number and a cash-flow number may be combined
        at all -- which is exactly what EBITDA and the debt/cash bridge do. Over a 250-ticker
        sample it holds exactly for 347 ticker-periods, within thousand-rounding for 17, and
        **diverges for 314**. The divergences are real (mismatched scope between a VCI balance
        sheet and a KBS cash flow, stale or repeated period columns), so this resolver is a
        gate, not a diagnostic.

    currency and absolute scale
        Not demonstrable from the retained payloads at all. There is no currency column, no
        unit header, and no anchor inside the bytes that fixes the absolute unit. They stay
        `unknown` unless an independently qualified official citation agrees with the value,
        which is what `official_agreement` handles.

    cumulative_state
        Demonstrated by the cash-flow statement's own beginning-of-period cash: if every
        quarter of one year opens on the same balance, the presentation is cumulative
        year-to-date; if each quarter opens on the prior quarter's close, it is period-only.
        The line is sparsely retained, so this frequently and correctly returns `unknown`.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

VERSION = "1.0.0"

#: Values every resolver may return in place of a resolution.
UNKNOWN = "unknown"

#: Relative tolerance for "these two numbers are the same number". Statement values are
#: exact integers in the retained payloads; this only absorbs float round-tripping.
_REL_TOLERANCE = 1e-9

#: Cash-flow payloads from one provider are rounded to the nearest thousand, so an otherwise
#: exact cross-statement match can differ by up to 1000 in absolute terms. Treated as
#: coherent-with-reduced-precision, never as divergent, and always flagged.
_THOUSAND_ROUNDING = 1000.0

_BALANCE_SHEET_CASH = "cash_and_cash_equivalents"
_MINORITY_INTERESTS = ("minority_interests", "minority_interests_before_2015")

_CF_END_CASH = (
    "cash_and_cash_equivalents_at_the_end_of_the_period",
    "cash_and_cash_equivalents_at_end_of_the_period",
    "cash_and_cash_equivalents_at_the_end_of_period",
    "cash_and_cash_equivalents_at_end_of_period",
)
_CF_BEGIN_CASH = (
    "cash_and_cash_equivalents_at_beginning_of_the_period",
    "cash_and_cash_equivalents_at_the_beginning_of_the_period",
    "cash_and_cash_equivalents_at_beginning_of_period",
    "cash_and_cash_equivalents_at_the_beginning_of_period",
)

_PERIOD_RE = re.compile(r"^(?P<year>\d{4})(?:-Q(?P<quarter>[1-4]))?$")

_QUARTER_BOUNDS = {
    1: ("01-01", "03-31"),
    2: ("04-01", "06-30"),
    3: ("07-01", "09-30"),
    4: ("10-01", "12-31"),
}


def _same(left: Any, right: Any, *, absolute: float = 0.0) -> bool:
    try:
        a, b = float(left), float(right)
    except (TypeError, ValueError):
        return False
    return abs(a - b) <= max(absolute, abs(a) * _REL_TOLERANCE, _REL_TOLERANCE)


def _value(items: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in items and items[key] is not None:
            return items[key]
    return None


def _first_key(items: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        if key in items and items[key] is not None:
            return key
    return None


def period_bounds(reporting_period: str, cumulative_state: str) -> dict[str, str | None]:
    """Calendar start/end for a reporting period, conditioned on the cumulative basis.

    `period_end` is pure calendar arithmetic on the period label and is always available.
    `period_start` is not: a cumulative year-to-date column labelled `2025-Q3` starts on
    2025-01-01, a period-only one starts on 2025-07-01, and with the basis `unknown` the
    start genuinely is unknown. Returning a quarter start regardless would manufacture the
    single fact the basis resolver exists to withhold.
    """
    match = _PERIOD_RE.match(str(reporting_period).strip())
    if match is None:
        return {"period_start": None, "period_end": None}
    year = match.group("year")
    quarter = match.group("quarter")
    if quarter is None:
        return {"period_start": f"{year}-01-01", "period_end": f"{year}-12-31"}
    start, end = _QUARTER_BOUNDS[int(quarter)]
    if cumulative_state == "cumulative_ytd":
        return {"period_start": f"{year}-01-01", "period_end": f"{year}-{end}"}
    if cumulative_state == "period_only":
        return {"period_start": f"{year}-{start}", "period_end": f"{year}-{end}"}
    return {"period_start": None, "period_end": f"{year}-{end}"}


def resolve_statement_scope(balance_sheet_items: Mapping[str, Any]) -> dict[str, Any]:
    """Consolidated on positive non-controlling-interest evidence; never `separate`.

    A non-zero minority interest cannot appear in a separate (parent-only) statement, so it
    grants `consolidated`. Nothing in the retained payloads can grant `separate`: a zero or
    absent NCI line is equally consistent with a parent-only filing and with a consolidated
    group that wholly owns every subsidiary.
    """
    key = _first_key(balance_sheet_items, _MINORITY_INTERESTS)
    if key is None:
        return {"statement_scope": UNKNOWN, "evidence": None,
                "reason": "no minority-interest line retained; scope is not evidenced"}
    value = balance_sheet_items[key]
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return {"statement_scope": UNKNOWN, "evidence": key,
                "reason": "minority-interest line is not numeric"}
    if numeric != 0.0:
        return {"statement_scope": "consolidated", "evidence": key,
                "reason": (f"{key} = {value} is non-zero; a non-controlling interest exists "
                           "only in a consolidated statement")}
    return {"statement_scope": UNKNOWN, "evidence": key,
            "reason": ("minority interest is zero, which a separate statement and a wholly "
                       "owned consolidated group produce identically; absence never grants scope")}


def resolve_sign_convention(income_statement_items: Mapping[str, Any]) -> dict[str, Any]:
    """Whether cost lines are carried positive or negative, from the gross-profit identity."""
    revenue = _value(income_statement_items, "revenue", "net_sales", "sales")
    cogs = _value(income_statement_items, "cost_of_goods_sold", "cost_of_sales")
    gross = _value(income_statement_items, "gross_profit")
    if revenue is None or cogs is None or gross is None:
        return {"sign_convention": UNKNOWN, "evidence": None,
                "reason": "revenue, cost of sales and gross profit are not all retained"}
    if _same(gross, float(revenue) - float(cogs)):
        return {"sign_convention": "expenses_positive", "evidence": "gross_profit_identity",
                "reason": "gross_profit reconciles to revenue - cost_of_goods_sold"}
    if _same(gross, float(revenue) + float(cogs)):
        return {"sign_convention": "expenses_negative", "evidence": "gross_profit_identity",
                "reason": "gross_profit reconciles to revenue + cost_of_goods_sold"}
    return {"sign_convention": UNKNOWN, "evidence": "gross_profit_identity",
            "reason": ("gross_profit reconciles to neither revenue - cost nor revenue + cost; "
                       "the sign convention is not demonstrated")}


def resolve_balance_identity(balance_sheet_items: Mapping[str, Any]) -> dict[str, Any]:
    """`total_assets == liabilities + owners_equity`: one scale and one sign on the sheet."""
    assets = _value(balance_sheet_items, "total_assets")
    liabilities = _value(balance_sheet_items, "liabilities", "total_liabilities")
    equity = _value(balance_sheet_items, "owners_equity", "capital_and_reserves")
    if assets is None or liabilities is None or equity is None:
        return {"balance_identity": UNKNOWN, "reason": "assets, liabilities or equity not retained"}
    if _same(assets, float(liabilities) + float(equity)):
        return {"balance_identity": "satisfied",
                "reason": "total_assets = liabilities + owners_equity"}
    return {"balance_identity": "violated",
            "reason": (f"total_assets ({assets}) != liabilities + owners_equity "
                       f"({float(liabilities) + float(equity)})")}


def resolve_cross_statement_scale(balance_sheet_items: Mapping[str, Any],
                                  cash_flow_items: Mapping[str, Any]) -> dict[str, Any]:
    """Whether a balance-sheet number and a cash-flow number may be combined at all.

    The only direct evidence available: end-of-period cash is reported by both statements
    and must be the same number. Divergence means the two payloads do not describe the same
    entity-period at the same scale, so any metric mixing them is `conflicted`.
    """
    key = _first_key(cash_flow_items, _CF_END_CASH)
    if key is None:
        return {"cross_statement_scale": UNKNOWN,
                "reason": "cash-flow statement retains no end-of-period cash line"}
    sheet_cash = _value(balance_sheet_items, _BALANCE_SHEET_CASH)
    if sheet_cash is None:
        return {"cross_statement_scale": UNKNOWN,
                "reason": "balance sheet retains no cash and cash equivalents line"}
    flow_cash = cash_flow_items[key]
    if _same(sheet_cash, flow_cash):
        return {"cross_statement_scale": "coherent", "evidence": key,
                "reason": "balance-sheet cash equals cash-flow end-of-period cash exactly"}
    if _same(sheet_cash, flow_cash, absolute=_THOUSAND_ROUNDING):
        return {"cross_statement_scale": "coherent_thousand_rounded", "evidence": key,
                "reason": ("balance-sheet cash equals cash-flow end-of-period cash to within "
                           "thousand-rounding; the cash-flow payload carries reduced precision")}
    return {"cross_statement_scale": "divergent", "evidence": key,
            "reason": (f"balance-sheet cash ({sheet_cash}) and cash-flow end-of-period cash "
                       f"({flow_cash}) disagree beyond thousand-rounding; the two statements "
                       "are not compatible for this period")}


def resolve_cumulative_state(cash_flow_by_period: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Cumulative year-to-date vs period-only, from beginning-of-period cash across quarters.

    `cash_flow_by_period` maps `reporting_period` -> item map, for one ticker. Quarters of
    one calendar year that all open on the same cash balance evidence a cumulative
    presentation; quarters that open on distinct balances evidence a period-only one.
    """
    by_year: dict[str, dict[str, Any]] = {}
    for period, items in cash_flow_by_period.items():
        match = _PERIOD_RE.match(str(period).strip())
        if match is None or match.group("quarter") is None:
            continue
        key = _first_key(items, _CF_BEGIN_CASH)
        if key is None:
            continue
        by_year.setdefault(match.group("year"), {})[match.group("quarter")] = items[key]

    usable = {year: quarters for year, quarters in by_year.items() if len(quarters) >= 2}
    if not usable:
        return {"cumulative_state": UNKNOWN, "years_tested": 0,
                "reason": ("fewer than two quarters of one year retain a beginning-of-period "
                           "cash line; the presentation basis is not demonstrated")}

    verdicts: set[str] = set()
    for quarters in usable.values():
        distinct = {round(float(value), 6) for value in quarters.values()
                    if isinstance(value, (int, float))}
        verdicts.add("cumulative_ytd" if len(distinct) == 1 else "period_only")
    if len(verdicts) == 1:
        state = verdicts.pop()
        return {"cumulative_state": state, "years_tested": len(usable),
                "reason": ("every tested year opens each quarter on the same cash balance"
                           if state == "cumulative_ytd"
                           else "quarters of a tested year open on distinct cash balances")}
    return {"cumulative_state": UNKNOWN, "years_tested": len(usable),
            "reason": "tested years disagree about the presentation basis"}


def resolve_currency_and_scale(official_agreement: Mapping[str, Any] | None) -> dict[str, Any]:
    """Currency and absolute unit scale, which only an official citation can establish.

    The retained payloads carry no currency column, no unit header and no internal anchor
    that fixes the absolute unit, so there is nothing here to demonstrate. When an
    independently qualified official citation reports the same identity and its value agrees
    digit-for-digit, that citation's currency and scale carry over; otherwise both stay
    `unknown` and the fact cannot rise above `provider_reported`.
    """
    if not official_agreement or not official_agreement.get("agrees"):
        return {"currency": UNKNOWN, "scale": UNKNOWN, "authority": UNKNOWN,
                "reason": ("retained payloads carry no currency or unit evidence and no "
                           "qualified official citation agrees with this value")}
    return {
        "currency": official_agreement.get("currency") or UNKNOWN,
        "scale": official_agreement.get("scale") or "units",
        "authority": "official_citation_agreement",
        "reason": (f"value agrees exactly with qualified official citation "
                   f"{official_agreement.get('citation_id')}"),
    }
