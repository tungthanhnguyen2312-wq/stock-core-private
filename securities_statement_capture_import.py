"""Retained-statement importer for `securities_financial_research_component/v1`.

This is the securities-firm counterpart to `tcbs_bank_capture_import.py`'s role for
banks: it owns the native-vocabulary knowledge (which raw retained item id means
which specialist concept) so `securities_financial_research_component.py` itself
stays provider/vocabulary-agnostic, exactly mirroring the existing contract/importer
split.

UNLIKE THE BANK IMPORTER, this one has no live provider capture bundle to parse.
Its input is `raw_financial_observations.extract_payload_file()`'s output over the
already-retained `data_bctc/<TICKER>_{balance_sheet,income_statement}_quarter.parquet`
payloads (or an equivalent already-loaded raw observation list) -- it performs no
network acquisition and writes nothing.

VOCABULARY EVIDENCE (2026-09-02 direct retained-corpus proof; see
`operations-review/securities-specialist-financial-research-foundation-v1-20260902/
REPORT.md` for the full per-field PROVIDER/NATIVE_ITEM_ID/... table and the
41-ticker/9-field coverage scan this table is drawn from):

    balance_sheet (provider VCI for all 41 governed securities tickers; point-in-time
    by the same item-id-agnostic `balance_sheet_period_end` route the generic engine
    already uses for total_assets/shareholders_equity, VCI included):
        financial_assets_at_fair_value_through_profit_or_loss_fvtpl -> fvtpl_financial_assets
        total_assets                                                -> total_assets
        loans                                                        -> margin_lending_receivable
            NATIVE LABEL: "Các khoản cho vay" / "Loans", filed under the statement's
            "Tài sản tài chính ngắn hạn" (short-term financial assets) section. This is
            the sole "loans" balance-sheet line in the retained CTCK (securities-company)
            statement template; it is not itself labelled "margin" in the retained bytes.
            LIMITATION: the native label does not explicitly restrict this balance to
            margin-trading loans versus other loan types the CTCK chart of accounts might
            in principle carry; no note-level (thuyet minh) breakdown is retained to
            independently disaggregate it. Carried as a documented limitation, not
            silently upgraded to an unqualified claim.

    income_statement (provider KBS for all 41 governed securities tickers, quarterly;
    STANDALONE_QUARTER by the same item-id-agnostic `kbs_income_statement_quarter_
    contract/v1` route already used for the generic `gross_profit` canonical metric):
        revenue_from_brokerage_services                              -> brokerage_revenue
        interest_income_from_loans_and_receivables                   -> loan_receivable_interest_income
        gains_from_financial_assets_at_fair_value_through_profit_or_loss_fvtpl -> fvtpl_gain
        loss_from_financial_assets_at_fair_value_through_profit_or_loss_fvtpl  -> fvtpl_loss
            SIGN_SEMANTICS LIMITATION: both lines are retained predominantly as
            non-negative magnitudes under their directional label (gain / loss), but a
            minority of retained ticker-quarters carry a negative value on one or the
            other (e.g. FTS/PHS/TVB on the gain line; APG/ART/DSC and others on the loss
            line) -- so neither is silently abs()'d, and no combined net feature is built
            from them in this milestone (see financial_analysis_engine_v2.py: only the
            raw components are retained, not a computed fvtpl_gain_loss ratio).
        net_profit_from_securities_business_20_50_40_60_61_62         -> securities_business_profit
        revenue_from_securities_business_01_11                        -> total_securities_operating_income
            DENOMINATOR COMPATIBILITY PROOF: this is the statement's own "Cong doanh thu
            hoat dong (01->11)" subtotal. Verified by direct arithmetic (not label
            similarity) against SSI 2026-Q1 retained values that it equals the exact sum
            of items 1.1 through 1.11, of which both brokerage_revenue (1.6) and
            loan_receivable_interest_income (1.3) are literal addends -- the gate
            MARKET_WIDE_REVENUE_MIX requires (task Section 8) before a mix ratio may use
            it as a denominator.

Only `period_variant_index == 0` (the primary, non-duplicate reporting-period column)
is imported; a `_1`-suffixed duplicate/restated column is skipped, never silently
averaged or preferred over the primary one.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import securities_financial_research_component as component

#: statement_family -> {raw_item_id: metric_id}. The single reviewable place this
#: milestone's native-vocabulary mapping lives; see module docstring for the
#: evidence behind each entry.
BALANCE_SHEET_VOCABULARY: dict[str, str] = {
    "financial_assets_at_fair_value_through_profit_or_loss_fvtpl": "fvtpl_financial_assets",
    "total_assets": "total_assets",
    "loans": "margin_lending_receivable",
}
INCOME_STATEMENT_VOCABULARY: dict[str, str] = {
    "revenue_from_brokerage_services": "brokerage_revenue",
    "interest_income_from_loans_and_receivables": "loan_receivable_interest_income",
    "gains_from_financial_assets_at_fair_value_through_profit_or_loss_fvtpl": "fvtpl_gain",
    "loss_from_financial_assets_at_fair_value_through_profit_or_loss_fvtpl": "fvtpl_loss",
    "net_profit_from_securities_business_20_50_40_60_61_62": "securities_business_profit",
    "revenue_from_securities_business_01_11": "total_securities_operating_income",
}

#: Raw item ids whose retained balance is documented as a limitation even though
#: it is imported (see module docstring): recorded on the built observation's
#: `limitations`, never silently dropped.
_LIMITATIONS_BY_METRIC_ID: dict[str, tuple[str, ...]] = {
    "margin_lending_receivable": (
        "NATIVE_LABEL_DOES_NOT_EXPLICITLY_RESTRICT_TO_MARGIN_TRADING_LOANS",
    ),
}


def _quarter_from_reporting_period(reporting_period: Any) -> tuple[int, int] | None:
    text = str(reporting_period or "")
    if "-Q" not in text:
        return None
    year_text, _, quarter_text = text.partition("-Q")
    if not (year_text.isdigit() and quarter_text.isdigit()):
        return None
    return int(year_text), int(quarter_text)


def securities_component_from_raw_observation(
    raw_observation: Mapping[str, Any], *, retrieved_at: str | None = None,
) -> dict[str, Any] | None:
    """Map one `raw_financial_observations.py`-shaped raw observation into a
    `securities_financial_research_component/v1` observation, or `None` when the
    raw observation is outside this milestone's proven, item-id-agnostic period-
    semantics routes or recognized vocabulary.

    Never raises on an out-of-scope row -- returning `None` is the normal,
    expected outcome for the vast majority of a securities-firm statement's rows
    (only a bounded named subset is mapped; see the module docstring).
    """
    statement_family = raw_observation.get("statement_family")
    if statement_family not in component.STATEMENT_FAMILIES:
        return None
    if raw_observation.get("period_variant_index") not in (0, None):
        return None  # duplicate/restated period column; primary column only

    vocabulary = BALANCE_SHEET_VOCABULARY if statement_family == component.BALANCE_SHEET else INCOME_STATEMENT_VOCABULARY
    raw_item_id = str(raw_observation.get("raw_item_id") or "")
    metric_id = vocabulary.get(raw_item_id)
    if metric_id is None:
        return None

    provider = raw_observation.get("provider")
    if statement_family == component.INCOME_STATEMENT and provider != "KBS":
        # VCI_PERIOD_DURATION_REMAINS_UNKNOWN: the KBS quarterly income-statement
        # route is the only proven STANDALONE_QUARTER evidence; anything else on
        # this statement family fails closed by never being built at all.
        return None
    if raw_observation.get("period_type") != "quarterly":
        return None
    period = _quarter_from_reporting_period(raw_observation.get("reporting_period"))
    if period is None:
        return None
    year, quarter = period

    raw_value = raw_observation.get("raw_value")
    if (not isinstance(raw_value, (int, float)) or isinstance(raw_value, bool)
            or not math.isfinite(raw_value)):
        return None  # NaN/inf: real extract_payload() output never carries these, but fail closed rather than raise

    source_file = raw_observation.get("source_file")
    source_sha256 = raw_observation.get("source_sha256")
    source_identity = f"{source_file}#{source_sha256}" if source_file and source_sha256 else str(source_file or "unknown")

    return component.build_observation(
        provider=str(provider),
        ticker=str(raw_observation.get("ticker") or ""),
        entity_type="securities",
        year=year,
        quarter=quarter,
        period_kind=component.QUARTER,
        period_semantics_status=component.DOCUMENTED_PROVIDER_CONTRACT,
        statement_family=statement_family,
        metric_id=metric_id,
        raw_value=raw_value,
        source_identity=source_identity,
        retrieved_at=str(retrieved_at or raw_observation.get("scraped_at") or ""),
        fitness=component.STRUCTURED_RESEARCH_COMPONENT,
        currency=raw_observation.get("raw_currency"),
        scale=raw_observation.get("raw_scale"),
        limitations=_LIMITATIONS_BY_METRIC_ID.get(metric_id, ()),
    )


def import_raw_observations(raw_observations: Sequence[Mapping[str, Any]], *,
                            retrieved_at: str | None = None) -> dict[str, Any]:
    """Map a sequence of raw observations (e.g. from one or more
    `raw_financial_observations.extract_payload_file()` results, concatenated)
    into `securities_financial_research_component/v1` observations.

    Deterministic and pure: no I/O, no clock read (unless `retrieved_at` is
    omitted and a row's own `scraped_at` is used instead, both retained values).
    """
    observations: list[dict[str, Any]] = []
    skipped_out_of_scope = 0
    for raw_observation in raw_observations:
        built = securities_component_from_raw_observation(raw_observation, retrieved_at=retrieved_at)
        if built is None:
            skipped_out_of_scope += 1
            continue
        observations.append(built)
    return {
        "import_contract": f"{component.CONTRACT_VERSION}/importer",
        "raw_observations_seen": len(raw_observations),
        "observations_built": len(observations),
        "skipped_out_of_scope": skipped_out_of_scope,
        "observations": observations,
    }
