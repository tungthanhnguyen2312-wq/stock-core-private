"""Financial Operational Proxy / v1.

Milestone: FINANCIAL_OPERATIONAL_PROXY_FOUNDATION_AND_RESEARCH_TIER_ACTIVATION_V1.

This module sits strictly between two already-existing, unmodified layers:

  * `canonical_financial_facts.py` / `canonical_fact_store.py` -- Layer-3 provider-tier
    canonical financial facts (raw provider observations resolved into a per-fact
    `status` of qualified/provider_reported/partial/conflicted/unavailable/not_applicable).
  * `p3f13_official_financial_evidence_scaleout.py` -- the 13-issuer, 138-fact official
    -qualified panel (`refreshed_panel_data`).

Neither layer is changed here. This module classifies already-retained provider-tier
facts into three explicit evidence/use tiers with a purpose-specific fitness-for-use
matrix, and derives a small, bounded set of same-source scale-invariant historical
-fundamental metrics (margin, ROA/ROE, cash-flow quality, leverage trend).

Pivot this milestone makes: financial-data semantics move from a binary
NOT AUTHORITATIVE -> NOT USABLE framing toward FITNESS FOR USE BY EVIDENCE TIER.

Three evidence tiers (see `EVIDENCE_TIERS`):
  1. OPERATIONAL_PROXY -- identifiable provider/source, ticker, reporting period, period
     type, canonical metric identity, statement scope when available, original + (if
     allowed) normalized value, no unresolved catastrophic semantic contradiction. Does
     NOT require page/row official citation. Used for market-wide research, screening,
     growth/trend, DuPont-style fundamental-quality research, valuation *research*, gap
     detection.
  2. VERIFIED_RESEARCH_EVIDENCE -- a provider observation corroborated by qualifying
     independent evidence (an exact-value match against an `AUTHORITATIVE_EVIDENCE`
     fact for the identical ticker + canonical_metric + statement_scope + reporting_period,
     or the pre-existing, already-tested `provider_financial_semantic_basis.
     classify_provider_exact_research_usable` per-fact citation-agreement route). Higher
     confidence than OPERATIONAL_PROXY. Still never silently becomes PIT/absolute
     authority and never becomes AUTHORITATIVE_EVIDENCE by itself.
  3. AUTHORITATIVE_EVIDENCE -- the existing official-qualified path
     (`p3f13_official_financial_evidence_scaleout.refreshed_panel_data`, unmodified,
     unweakened). Facts of this tier are passed through verbatim, never reclassified.

No provider fact may silently overwrite an authoritative fact (`merge_document_qualified_
facts_into_panel` is never called from this module). A `VALUE_CONFLICT` against an
authoritative fact fails the conflicting observation closed for every use -- it is
explicitly conflict-marked in the output, never silently dropped and never promoted.

Sector safety: classification is bounded to `entity_type == "corporate"` in this
milestone (see `SUPPORTED_ENTITY_TYPES`). Bank/securities/insurance/finance_company
tickers receive an explicit `ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE` disposition and
zero operational-proxy facts -- consistent with "Do not solve a new sector architecture
in this milestone" and with `financial_fact_coverage_recovery.REQUIRED_IDENTITIES_BY_ENTITY`,
which defines a structurally different (and much smaller) identity set for those sectors
that provider raw observations do not currently expose at all.

Absolute vs scale-invariant distinction (the load-bearing rule of this module): a same
-ticker, same-provider, same-statement-scope pair of observations shares whatever unknown
common scale factor the provider applies, so a ratio or period-over-period growth
computed from that pair is invariant to that unresolved scale. An *absolute* value is
not. Concretely:
  * `revenue_growth`, `earnings_growth`, `net_margin_trend`, `roa_trend`, `roe_trend`,
    `cash_flow_quality_trend`, `leverage_trend` are scale-invariant research constructs
    and may be OPERATIONAL_PROXY research/trend-eligible even while currency/scale are
    unresolved.
  * A raw absolute value (revenue in VND, total assets in VND) is never valuation
    -research-eligible while its own currency/scale are unresolved -- and this module
    never guesses a scale to make one match. `market_cap / revenue`, P/S, EV/Sales,
    EV/EBITDA remain blocked exactly as before; this module only *reports* whether a
    provider fact could feed valuation research (see `fitness_for_use`), it never wires
    itself into `market_wide_current_valuation_input_scaleout.py`'s absolute gates.

Does not: acquire data, call a network, run OCR, call a Vision/LLM API, mutate a
production DB, touch the Dashboard, or emit VALUE/target-price/recommendation/
probability/ranking/position-sizing/PIT-backtest authority. `is_actionable` is always
`False` on every record this module produces.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from financial_entity_applicability import (
    CORPORATE_ENTITY_TYPES,
    CORPORATE_ONLY_METRICS,
    FINANCIAL_ENTITY_TYPES,
)
from financial_fact_coverage_recovery import CORPORATE_IDENTITIES
from provider_financial_semantic_basis import (
    classify_provider_exact_research_usable,
)
from semantic_evidence_bridge import financial_identity_is_stock_metric

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "financial_operational_proxy/v1"
ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Evidence tiers. New names -- checked against every existing tier vocabulary in this
# repository (market_wide_current_fundamental_research.{OFFICIAL_TIER,PROVIDER_TIER,
# BLOCKED_TIER}, financial_fact_coverage_recovery.REQUIRED_CELL_STATES,
# provider_financial_semantic_basis.SHAPE_VERDICTS, canonical_financial_facts.STATUS_*,
# evidence_qualification_tiers.TIERS) -- none of these three strings collides with any
# existing tier/status/verdict constant anywhere in the codebase.
# ---------------------------------------------------------------------------
OPERATIONAL_PROXY = "OPERATIONAL_PROXY"
VERIFIED_RESEARCH_EVIDENCE = "VERIFIED_RESEARCH_EVIDENCE"
AUTHORITATIVE_EVIDENCE = "AUTHORITATIVE_EVIDENCE"
EVIDENCE_TIERS = (OPERATIONAL_PROXY, VERIFIED_RESEARCH_EVIDENCE, AUTHORITATIVE_EVIDENCE)

# The one bounded, explicit contract under which OPERATIONAL_PROXY may upgrade to
# VERIFIED_RESEARCH_EVIDENCE. Zero generalization beyond the exact fact it fires on.
UPGRADE_CONTRACT = (
    "operational_proxy_to_verified_research_evidence/v1: an OPERATIONAL_PROXY fact "
    "upgrades to VERIFIED_RESEARCH_EVIDENCE only when its own (ticker, canonical_metric, "
    "statement_scope, reporting_period) key reconciles EXACT_MATCH against an "
    "AUTHORITATIVE_EVIDENCE fact carrying the identical key, or when the pre-existing "
    "provider_financial_semantic_basis.classify_provider_exact_research_usable per-fact "
    "citation-agreement route independently marks it eligible. Never a shape-wide or "
    "ticker-wide generalization; never AUTHORITATIVE_EVIDENCE."
)

# ---------------------------------------------------------------------------
# Reconciliation vocabulary. Distinct from (and does not replace) the existing coarse
# EXACT_MATCH / VALUE_CONFLICT / NOT_COMPARABLE_NEW_KEY classifier in
# official_financial_structural_table.reconcile_against_existing_panel, which reconciles
# a *candidate fact awaiting ingress* against the panel. This classifier instead
# reconciles an already-retained *provider research fact* against the panel, for tiering
# -- a different purpose that module does not serve.
# ---------------------------------------------------------------------------
EXACT_MATCH = "EXACT_MATCH"
VALUE_CONFLICT = "VALUE_CONFLICT"
NOT_COMPARABLE_SCOPE = "NOT_COMPARABLE_SCOPE"
NOT_COMPARABLE_PERIOD = "NOT_COMPARABLE_PERIOD"
NOT_COMPARABLE_UNIT = "NOT_COMPARABLE_UNIT"
NO_OFFICIAL_COMPARATOR = "NO_OFFICIAL_COMPARATOR"
RECONCILIATION_STATES = (
    EXACT_MATCH, VALUE_CONFLICT, NOT_COMPARABLE_SCOPE, NOT_COMPARABLE_PERIOD,
    NOT_COMPARABLE_UNIT, NO_OFFICIAL_COMPARATOR,
)

# Bounded to corporate this milestone -- see module docstring "Sector safety".
SUPPORTED_ENTITY_TYPES = frozenset({"corporate"})

# The exact canonical metric identities this module will ever classify -- the same
# corporate identity tuple financial_fact_coverage_recovery.py already uses, reused
# verbatim, never widened with a new name invented here.
ELIGIBLE_METRICS = frozenset(CORPORATE_IDENTITIES)

# Cross-metric derived ratios evaluated for "historical fundamental use". `family` marks
# whether numerator/denominator are drawn from the same statement family (a strictly
# safer scale-sharing claim: one provider call, one representation) or cross-statement
# (both from the same provider/ticker/period, but two different statement-family calls --
# flagged with an explicit warning, never silently treated as equally safe).
DERIVED_RATIO_METRICS = (
    # (derived_metric_id, numerator_metric, denominator_metric, family, description)
    ("net_margin", "net_income", "revenue", "same_statement_family",
     "net_income / revenue -- both income_statement"),
    ("roa", "net_income", "total_assets", "cross_statement_family",
     "net_income / total_assets -- income_statement over balance_sheet"),
    ("roe", "net_income", "shareholders_equity", "cross_statement_family",
     "net_income / shareholders_equity -- income_statement over balance_sheet"),
    ("cash_flow_quality", "operating_cash_flow", "net_income", "cross_statement_family",
     "operating_cash_flow / net_income -- cash_flow over income_statement"),
    ("leverage_debt_to_equity", "total_interest_bearing_debt", "shareholders_equity", "same_statement_family",
     "total_interest_bearing_debt / shareholders_equity -- both balance_sheet"),
)
CROSS_STATEMENT_WARNING = (
    "CROSS_STATEMENT_FAMILY_SAME_SCALE_ASSUMED: numerator and denominator come from "
    "different statement families; this module asserts they share the same unresolved "
    "provider scale only because they carry the same provider + ticker + reporting_period "
    "+ statement_scope, never because the actual transform was independently proven."
)


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    """Deterministic content identity. Excludes the identity fields themselves *and* every
    operational/wall-clock timestamp field, so re-running this module at a different wall
    -clock moment over byte-identical inputs yields a byte-identical identity."""
    payload = {
        key: value for key, value in artifact.items()
        if key not in {"artifact_sha256", "artifact_identity", "generated_at", "requested_at"}
    }
    digest = _hash(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


# ---------------------------------------------------------------------------
# Fitness-for-use. Six independent, purpose-specific booleans -- never one collapsed
# `usable` flag. See module docstring for the load-bearing absolute-vs-scale-invariant
# distinction that `valuation_research_eligible` encodes.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FitnessForUse:
    display_eligible: bool
    research_eligible: bool
    trend_eligible: bool
    valuation_research_eligible: bool
    authoritative_financial_eligible: bool
    pit_backtest_eligible: bool
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "display_eligible": self.display_eligible,
            "research_eligible": self.research_eligible,
            "trend_eligible": self.trend_eligible,
            "valuation_research_eligible": self.valuation_research_eligible,
            "authoritative_financial_eligible": self.authoritative_financial_eligible,
            "pit_backtest_eligible": self.pit_backtest_eligible,
            "reason_codes": list(self.reason_codes),
        }


_BLOCKED_FITNESS_REASON = {
    "ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE": "entity type is outside the corporate scope this milestone supports",
    "METRIC_NOT_IN_BOUNDED_IDENTITY_SET": "canonical_metric is outside the bounded corporate identity set reused from financial_fact_coverage_recovery.CORPORATE_IDENTITIES",
    "IDENTITY_INCOMPLETE": "ticker, canonical_metric, reporting_period, or provider is missing",
    "VALUE_CONFLICT_WITH_AUTHORITATIVE_EVIDENCE": "this exact fact numerically disagrees with an AUTHORITATIVE_EVIDENCE fact for the same key",
}


def fitness_for_use(*, tier: str | None, currency: Any, scale: Any,
                    reason_codes: Sequence[str] = ()) -> FitnessForUse:
    """Purpose-specific eligibility for one fact. Never a single global boolean."""
    if tier is None:
        codes = tuple(reason_codes) or ("NO_TIER_ASSIGNED",)
        return FitnessForUse(False, False, False, False, False, False, reason_codes=codes)

    if tier == AUTHORITATIVE_EVIDENCE:
        return FitnessForUse(
            display_eligible=True, research_eligible=True, trend_eligible=True,
            valuation_research_eligible=True, authoritative_financial_eligible=True,
            pit_backtest_eligible=False,
            reason_codes=("PIT_BACKTEST_REQUIRES_SEPARATE_QUALIFICATION_NOT_GRANTED_HERE",),
        )

    if tier == VERIFIED_RESEARCH_EVIDENCE:
        # An exact-match upgrade resolves currency/scale by copying the comparator it
        # matched, but it must never silently become authoritative or PIT-eligible.
        return FitnessForUse(
            display_eligible=True, research_eligible=True, trend_eligible=True,
            valuation_research_eligible=True, authoritative_financial_eligible=False,
            pit_backtest_eligible=False,
            reason_codes=(
                "VERIFIED_RESEARCH_EVIDENCE_NEVER_AUTOMATICALLY_AUTHORITATIVE",
                "PIT_BACKTEST_REQUIRES_SEPARATE_QUALIFICATION_NOT_GRANTED_HERE",
            ),
        )

    # OPERATIONAL_PROXY. valuation_research_eligible is fact-specific: true only when this
    # exact fact's own currency AND scale are independently known -- never inferred, never
    # assumed from provider/library schema evidence alone (that bar was already closed at
    # zero shapes by provider_financial_semantic_basis.py; this module does not reopen it).
    scale_resolved = currency not in (None, "unknown", "") and scale not in (None, "unknown", "")
    codes = list(reason_codes)
    if not scale_resolved:
        codes.append("ABSOLUTE_MONETARY_SCALE_UNRESOLVED")
    return FitnessForUse(
        display_eligible=True, research_eligible=True, trend_eligible=True,
        valuation_research_eligible=scale_resolved,
        authoritative_financial_eligible=False, pit_backtest_eligible=False,
        reason_codes=tuple(codes),
    )


# ---------------------------------------------------------------------------
# Reconciliation against the AUTHORITATIVE_EVIDENCE (P3-F13) panel.
# ---------------------------------------------------------------------------
def build_official_index(refreshed_panel_data: Mapping[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Index P3-F13's own refreshed_panel_data by (ticker, canonical_metric) -> qualified
    facts. Reads the panel; never mutates or re-derives it."""
    index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for issuer in refreshed_panel_data.get("issuers", []) or []:
        ticker = str(issuer.get("issuer_identity", {}).get("ticker", "")).upper()
        for fact in issuer.get("facts", []) or []:
            if fact.get("qualification_state") != "QUALIFIED":
                continue
            key = (ticker, str(fact.get("canonical_metric")))
            index.setdefault(key, []).append(fact)
    return index


def _period_compatible(canonical_metric: str, provider_period: Any, official_period: Any) -> bool:
    """Same identity comparison already established by canonical_fact_store.
    load_official_citations / semantic_evidence_bridge.financial_identity_is_stock_metric:
    an annual balance-sheet (instant) fact and its Q4 observation identify the same
    instant, so a quarterly provider fact may compare against an annual official fact
    only for that one narrow, already-approved case. Flows never get this alias -- FY
    revenue is not Q4 revenue."""
    if str(provider_period) == str(official_period):
        return True
    if not financial_identity_is_stock_metric(canonical_metric):
        return False
    official_text = str(official_period)
    return official_text.isdigit() and str(provider_period) == f"{official_text}-Q4"


def reconcile_against_official(*, ticker: str, canonical_metric: str, reporting_period: Any,
                               statement_scope: Any, value: Any, currency: Any, scale: Any,
                               official_index: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    """Classify one provider fact against the AUTHORITATIVE_EVIDENCE panel.

    Value comparison never guesses a scale transform. It compares the raw provider
    value directly against the official value (the realistic case: retained data shows
    provider raw values are already base-currency far more often than not -- this is
    exactly how canonical_financial_facts.py's own official-agreement check already
    finds matches), or -- only when this fact's own currency/scale are independently
    already known -- the scale-adjusted value. When currency/scale are unknown and the
    raw values disagree, the honest answer is NOT_COMPARABLE_UNIT, never a guessed
    VALUE_CONFLICT and never a guessed EXACT_MATCH.
    """
    candidates = list(official_index.get((str(ticker).upper(), str(canonical_metric)), []))
    if not candidates:
        return {"reconciliation_status": NO_OFFICIAL_COMPARATOR, "reason_codes": ["NO_AUTHORITATIVE_FACT_FOR_TICKER_AND_METRIC"],
                "official_fact_reference": None}

    scope_period_matches = [
        fact for fact in candidates
        if fact.get("statement_scope") == statement_scope
        and _period_compatible(canonical_metric, reporting_period, fact.get("reporting_period"))
    ]
    if scope_period_matches:
        official = scope_period_matches[0]
        reference = {"canonical_metric": official.get("canonical_metric"), "reporting_period": official.get("reporting_period"),
                     "statement_scope": official.get("statement_scope"), "citation_id": official.get("source_lineage", {}).get("citation_id"),
                     "value": official.get("value")}
        try:
            provider_value = float(value)
            official_value = float(official.get("value"))
        except (TypeError, ValueError):
            return {"reconciliation_status": NOT_COMPARABLE_UNIT, "reason_codes": ["PROVIDER_OR_OFFICIAL_VALUE_NOT_NUMERIC"],
                    "official_fact_reference": reference}
        if provider_value == official_value:
            return {"reconciliation_status": EXACT_MATCH, "reason_codes": [], "official_fact_reference": reference}
        scale_known = currency not in (None, "unknown", "") and scale not in (None, "unknown", "")
        if scale_known:
            try:
                if provider_value * float(scale) == official_value:
                    return {"reconciliation_status": EXACT_MATCH, "reason_codes": ["MATCHED_AFTER_KNOWN_SCALE"],
                            "official_fact_reference": reference}
            except (TypeError, ValueError):
                pass
            return {"reconciliation_status": VALUE_CONFLICT, "reason_codes": ["VALUE_DISAGREES_WITH_AUTHORITATIVE_EVIDENCE_UNDER_KNOWN_SCALE"],
                    "official_fact_reference": reference}
        return {"reconciliation_status": NOT_COMPARABLE_UNIT,
                "reason_codes": ["PROVIDER_CURRENCY_OR_SCALE_UNKNOWN_CANNOT_RULE_OUT_SCALE_EXPLAINING_THE_DIFFERENCE"],
                "official_fact_reference": reference}

    scope_matches = [fact for fact in candidates if fact.get("statement_scope") == statement_scope]
    period_matches = [
        fact for fact in candidates
        if _period_compatible(canonical_metric, reporting_period, fact.get("reporting_period"))
    ]
    if not scope_matches:
        return {"reconciliation_status": NOT_COMPARABLE_SCOPE,
                "reason_codes": ["AUTHORITATIVE_COMPARATOR_EXISTS_ONLY_FOR_A_DIFFERENT_STATEMENT_SCOPE"],
                "official_fact_reference": None}
    if not period_matches:
        return {"reconciliation_status": NOT_COMPARABLE_PERIOD,
                "reason_codes": ["AUTHORITATIVE_COMPARATOR_EXISTS_ONLY_FOR_A_DIFFERENT_REPORTING_PERIOD"],
                "official_fact_reference": None}
    # Neither the scope-only nor period-only bucket is empty, yet no fact shared both --
    # this can only happen if distinct facts separately matched scope and matched period.
    # Scope is the more fundamental identity dimension (a wrong statement scope makes a
    # metric mean something else entirely), so it is reported first.
    return {"reconciliation_status": NOT_COMPARABLE_SCOPE,
            "reason_codes": ["AUTHORITATIVE_COMPARATOR_SCOPE_AND_PERIOD_MATCH_DIFFERENT_FACTS"],
            "official_fact_reference": None}


# ---------------------------------------------------------------------------
# Per-fact classification.
# ---------------------------------------------------------------------------
def classify_operational_proxy_fact(fact: Mapping[str, Any], *, entity_type: str | None,
                                    official_index: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
                                    semantic_basis_registry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Classify one already-retained provider-tier canonical fact
    (canonical_financial_facts.py's fact shape) into an evidence tier with a
    purpose-specific fitness-for-use matrix. Pure; performs no I/O and no network call."""
    ticker = str(fact.get("ticker") or "").upper()
    canonical_metric = str(fact.get("canonical_metric") or "")
    reporting_period = fact.get("reporting_period")
    statement_scope = fact.get("statement_scope")
    period_type = fact.get("period_type")
    provider = fact.get("provider")
    value = fact.get("value")
    currency = fact.get("currency")
    scale = fact.get("scale")
    entity_type_normalized = (str(entity_type).strip().lower() if entity_type else None)

    base_record: dict[str, Any] = {
        "ticker": ticker,
        "entity_type": entity_type_normalized,
        "provider": provider,
        "source_record_identity": fact.get("fact_id") or list(fact.get("source_observation_ids") or []) or None,
        "reporting_period": reporting_period,
        "period_type": period_type,
        "canonical_metric": canonical_metric,
        "provider_raw_value": value,
        "normalized_value": None,
        "currency_status": "known" if currency not in (None, "unknown", "") else "unknown",
        "unit_scale_status": "known" if scale not in (None, "unknown", "") else "unknown",
        "statement_scope": statement_scope,
        "statement_scope_status": "known" if statement_scope not in (None, "unknown", "") else "unknown",
    }

    if entity_type_normalized not in SUPPORTED_ENTITY_TYPES:
        reason = ["ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE"]
        base_record.update({
            "evidence_tier": None, "fitness_for_use": fitness_for_use(tier=None, currency=currency, scale=scale, reason_codes=reason).to_dict(),
            "warnings": [_BLOCKED_FITNESS_REASON["ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE"]], "reason_codes": reason,
            "official_reconciliation": None,
        })
        return base_record

    if canonical_metric not in ELIGIBLE_METRICS:
        reason = ["METRIC_NOT_IN_BOUNDED_IDENTITY_SET"]
        base_record.update({
            "evidence_tier": None, "fitness_for_use": fitness_for_use(tier=None, currency=currency, scale=scale, reason_codes=reason).to_dict(),
            "warnings": [_BLOCKED_FITNESS_REASON["METRIC_NOT_IN_BOUNDED_IDENTITY_SET"]], "reason_codes": reason,
            "official_reconciliation": None,
        })
        return base_record

    identity_complete = all([ticker, canonical_metric, reporting_period not in (None, ""), provider not in (None, "")])
    if not identity_complete or value is None:
        reason = ["IDENTITY_INCOMPLETE"]
        base_record.update({
            "evidence_tier": None, "fitness_for_use": fitness_for_use(tier=None, currency=currency, scale=scale, reason_codes=reason).to_dict(),
            "warnings": [_BLOCKED_FITNESS_REASON["IDENTITY_INCOMPLETE"]], "reason_codes": reason,
            "official_reconciliation": None,
        })
        return base_record

    reconciliation = reconcile_against_official(
        ticker=ticker, canonical_metric=canonical_metric, reporting_period=reporting_period,
        statement_scope=statement_scope, value=value, currency=currency, scale=scale,
        official_index=official_index,
    )
    exact_usable = classify_provider_exact_research_usable(fact, registry=semantic_basis_registry)

    warnings: list[str] = []
    reason_codes: list[str] = list(reconciliation["reason_codes"])
    if reconciliation["reconciliation_status"] == VALUE_CONFLICT:
        tier = None
        reason_codes = ["VALUE_CONFLICT_WITH_AUTHORITATIVE_EVIDENCE"] + reason_codes
        warnings.append(_BLOCKED_FITNESS_REASON["VALUE_CONFLICT_WITH_AUTHORITATIVE_EVIDENCE"])
        warnings.append("AUTHORITATIVE_EVIDENCE_REMAINS_UNCHANGED_THIS_OBSERVATION_FAILS_CLOSED")
    elif reconciliation["reconciliation_status"] == EXACT_MATCH or exact_usable.get("eligible"):
        tier = VERIFIED_RESEARCH_EVIDENCE
        if exact_usable.get("eligible") and reconciliation["reconciliation_status"] != EXACT_MATCH:
            reason_codes.append(f"UPGRADED_VIA_{exact_usable.get('route')}")
        base_record["normalized_value"] = value
    else:
        tier = OPERATIONAL_PROXY

    fitness = fitness_for_use(tier=tier, currency=currency, scale=scale)
    base_record.update({
        "evidence_tier": tier,
        "fitness_for_use": fitness.to_dict(),
        "warnings": warnings,
        "reason_codes": sorted(set(reason_codes)) if reason_codes else [],
        "official_reconciliation": {
            "reconciliation_status": reconciliation["reconciliation_status"],
            "reason_codes": reconciliation["reason_codes"],
            "official_fact_reference": reconciliation["official_fact_reference"],
            "upgrade_contract": UPGRADE_CONTRACT if tier == VERIFIED_RESEARCH_EVIDENCE else None,
        },
    })
    return base_record


# ---------------------------------------------------------------------------
# Derived scale-invariant historical-fundamental metrics.
# ---------------------------------------------------------------------------
def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _same_representation(numerator_fact: Mapping[str, Any], denominator_fact: Mapping[str, Any]) -> bool:
    """The exact, checkable precondition the milestone requires: both compared
    observations share provider + ticker + reporting_period + statement_scope. This is
    what makes the ratio invariant to whatever their shared unknown scale actually is --
    it does not require knowing the scale, only that it is the same on both sides."""
    return (
        numerator_fact.get("provider") == denominator_fact.get("provider")
        and numerator_fact.get("ticker") == denominator_fact.get("ticker")
        and numerator_fact.get("reporting_period") == denominator_fact.get("reporting_period")
        and numerator_fact.get("statement_scope") == denominator_fact.get("statement_scope")
    )


def _ratio_level_series(*, ticker: str, derived_metric_id: str, numerator_metric: str,
                        denominator_metric: str, family: str, facts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One ratio observation per period where a same-representation numerator/denominator
    pair exists among provider_reported facts. Never mixes two different providers'
    values into one ratio."""
    by_metric_period: dict[tuple[str, Any], list[Mapping[str, Any]]] = {}
    for fact in facts:
        if fact.get("status") != "provider_reported":
            continue
        if fact.get("canonical_metric") not in (numerator_metric, denominator_metric):
            continue
        by_metric_period.setdefault((str(fact.get("canonical_metric")), fact.get("reporting_period")), []).append(fact)

    series: list[dict[str, Any]] = []
    numerator_periods = {period for (metric, period) in by_metric_period if metric == numerator_metric}
    for period in sorted(numerator_periods, key=str):
        for numerator_fact in by_metric_period.get((numerator_metric, period), []):
            for denominator_fact in by_metric_period.get((denominator_metric, period), []):
                if not _same_representation(numerator_fact, denominator_fact):
                    continue
                numerator_value = _numeric(numerator_fact.get("value"))
                denominator_value = _numeric(denominator_fact.get("value"))
                if numerator_value is None or denominator_value is None or denominator_value == 0:
                    continue
                warnings = [CROSS_STATEMENT_WARNING] if family == "cross_statement_family" else []
                series.append({
                    "reporting_period": period,
                    "provider": numerator_fact.get("provider"),
                    "statement_scope": numerator_fact.get("statement_scope"),
                    "ratio_value": numerator_value / denominator_value,
                    "numerator_source_record_identity": numerator_fact.get("fact_id"),
                    "denominator_source_record_identity": denominator_fact.get("fact_id"),
                    "warnings": warnings,
                })
                break  # one compatible pair per period is sufficient; do not multiply-count
    return series


def derive_ratio_metric(*, ticker: str, derived_metric_id: str, numerator_metric: str,
                        denominator_metric: str, family: str, description: str,
                        facts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """One derived historical-fundamental metric: a scale-invariant ratio series plus its
    period-over-period trend. A derived result's evidence tier can never exceed the
    weakest tier among its required inputs -- both inputs here are always provider-tier
    (OPERATIONAL_PROXY at best), so a derived ratio is always OPERATIONAL_PROXY, never
    VERIFIED_RESEARCH_EVIDENCE or AUTHORITATIVE_EVIDENCE, regardless of how clean the
    series is."""
    series = _ratio_level_series(
        ticker=ticker, derived_metric_id=derived_metric_id, numerator_metric=numerator_metric,
        denominator_metric=denominator_metric, family=family, facts=facts,
    )
    result: dict[str, Any] = {
        "ticker": ticker,
        "derived_metric_id": derived_metric_id,
        "description": description,
        "method": "same_representation_ratio_and_trend/v1",
        "numerator_metric": numerator_metric,
        "denominator_metric": denominator_metric,
        "statement_family_relationship": family,
        "input_evidence_tiers": [OPERATIONAL_PROXY, OPERATIONAL_PROXY],
        "result_evidence_tier": OPERATIONAL_PROXY if series else None,
        "absolute_or_scale_invariant": "scale_invariant",
        "source_periods": [point["reporting_period"] for point in series],
        "level_series": series,
        "trend": None,
        "input_warnings": sorted({warning for point in series for warning in point["warnings"]}),
        "status": "AVAILABLE" if len(series) >= 1 else "BLOCKED",
        "blocked_reason": None if series else "NO_SAME_REPRESENTATION_NUMERATOR_DENOMINATOR_PAIR",
        "fitness_for_use": None,
    }
    if len(series) >= 2:
        ordered = sorted(series, key=lambda point: str(point["reporting_period"]))
        first, last = ordered[0], ordered[-1]
        if first["ratio_value"] != 0:
            growth_fraction = (last["ratio_value"] - first["ratio_value"]) / abs(first["ratio_value"])
        else:
            growth_fraction = None
        result["trend"] = {
            "from_period": first["reporting_period"], "to_period": last["reporting_period"],
            "from_ratio_value": first["ratio_value"], "to_ratio_value": last["ratio_value"],
            "direction": "INCREASED" if last["ratio_value"] > first["ratio_value"] else (
                "DECREASED" if last["ratio_value"] < first["ratio_value"] else "UNCHANGED"),
            "growth_fraction": growth_fraction,
        }
    result["fitness_for_use"] = fitness_for_use(
        tier=result["result_evidence_tier"], currency=None, scale=None,
        reason_codes=() if series else ("NO_SAME_REPRESENTATION_NUMERATOR_DENOMINATOR_PAIR",),
    ).to_dict()
    return result


def derive_all_ratio_metrics(*, ticker: str, entity_type: str | None,
                             facts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if (str(entity_type).strip().lower() if entity_type else None) not in SUPPORTED_ENTITY_TYPES:
        return []
    return [
        derive_ratio_metric(
            ticker=ticker, derived_metric_id=derived_metric_id, numerator_metric=numerator_metric,
            denominator_metric=denominator_metric, family=family, description=description, facts=facts,
        )
        for derived_metric_id, numerator_metric, denominator_metric, family, description in DERIVED_RATIO_METRICS
    ]


# ---------------------------------------------------------------------------
# Per-ticker and artifact-level assembly.
# ---------------------------------------------------------------------------
def build_ticker_operational_proxy(*, ticker: str, entity_type: str | None,
                                   facts: Sequence[Mapping[str, Any]],
                                   official_index: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
                                   semantic_basis_registry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    ticker = str(ticker).upper()
    entity_type_normalized = (str(entity_type).strip().lower() if entity_type else None)
    supported = entity_type_normalized in SUPPORTED_ENTITY_TYPES

    provider_facts = [fact for fact in facts if fact.get("status") in ("provider_reported", "qualified", "conflicted")]
    classified = [
        classify_operational_proxy_fact(
            fact, entity_type=entity_type_normalized, official_index=official_index,
            semantic_basis_registry=semantic_basis_registry,
        )
        for fact in provider_facts if fact.get("canonical_metric") in ELIGIBLE_METRICS
    ]
    derived = derive_all_ratio_metrics(ticker=ticker, entity_type=entity_type_normalized, facts=facts) if supported else []

    tier_counts: dict[str, int] = {tier: 0 for tier in EVIDENCE_TIERS}
    for record in classified:
        if record["evidence_tier"] in tier_counts:
            tier_counts[record["evidence_tier"]] += 1
    conflict_count = sum(1 for record in classified if "VALUE_CONFLICT_WITH_AUTHORITATIVE_EVIDENCE" in record["reason_codes"])

    return {
        "ticker": ticker,
        "entity_type": entity_type_normalized,
        "entity_type_supported_this_milestone": supported,
        "facts": classified,
        "derived_metrics": derived,
        "tier_counts": tier_counts,
        "conflict_count": conflict_count,
        "is_actionable": False,
    }


def build_operational_proxy_artifact(*, tickers: Sequence[str], facts_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]],
                                     entity_type_by_ticker: Mapping[str, str | None],
                                     refreshed_panel_data: Mapping[str, Any], requested_at: str,
                                     semantic_basis_registry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build the complete `financial_operational_proxy/v1` artifact for `tickers`.

    Pure aggregation over already-retained inputs (canonical facts per ticker, the
    P3-F13 official panel). No network, no OCR, no DB, no acquisition.
    """
    official_index = build_official_index(refreshed_panel_data)
    tickers_sorted = sorted({str(ticker).upper() for ticker in tickers})
    records = {
        ticker: build_ticker_operational_proxy(
            ticker=ticker, entity_type=entity_type_by_ticker.get(ticker),
            facts=facts_by_ticker.get(ticker, []), official_index=official_index,
            semantic_basis_registry=semantic_basis_registry,
        )
        for ticker in tickers_sorted
    }

    coverage_tier_counts: dict[str, int] = {tier: 0 for tier in EVIDENCE_TIERS}
    conflict_total = 0
    entity_supported_count = 0
    for record in records.values():
        for tier, count in record["tier_counts"].items():
            coverage_tier_counts[tier] += count
        conflict_total += record["conflict_count"]
        entity_supported_count += int(record["entity_type_supported_this_milestone"])

    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": "FINANCIAL_OPERATIONAL_PROXY",
        "milestone": "FINANCIAL_OPERATIONAL_PROXY_FOUNDATION_AND_RESEARCH_TIER_ACTIVATION_V1",
        "requested_at": requested_at,
        "evidence_tiers": list(EVIDENCE_TIERS),
        "upgrade_contract": UPGRADE_CONTRACT,
        "reconciliation_states": list(RECONCILIATION_STATES),
        "supported_entity_types_this_milestone": sorted(SUPPORTED_ENTITY_TYPES),
        "eligible_metrics": sorted(ELIGIBLE_METRICS),
        "derived_ratio_metric_registry": [
            {"derived_metric_id": derived_metric_id, "numerator_metric": numerator_metric,
             "denominator_metric": denominator_metric, "statement_family_relationship": family,
             "description": description}
            for derived_metric_id, numerator_metric, denominator_metric, family, description in DERIVED_RATIO_METRICS
        ],
        "cohort_ticker_count": len(tickers_sorted),
        "records": records,
        "coverage": {
            "tier_counts": coverage_tier_counts,
            "conflict_count": conflict_total,
            "entity_type_supported_ticker_count": entity_supported_count,
            "entity_type_unsupported_ticker_count": len(tickers_sorted) - entity_supported_count,
        },
        "authority_boundary": {
            "official_qualified_facts_unchanged": True,
            "no_provider_fact_overwrites_authoritative_fact": True,
            "operational_proxy_never_automatically_authoritative": True,
            "verified_research_evidence_never_automatically_authoritative": True,
            "no_value_ranking_recommendation_target_probability_sizing_pit_promotion": True,
            "no_network_no_ocr_no_vision_no_new_provider": True,
        },
        "ticker_specific_branch_audit": {"status": "PASS", "production_ticker_literals": []},
        "is_actionable": False,
    }
    artifact.update(content_identity(artifact))
    return artifact
