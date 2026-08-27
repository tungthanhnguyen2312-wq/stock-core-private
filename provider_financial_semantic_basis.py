"""provider_financial_semantic_basis/v1 -- absolute semantic-basis qualification for already-
retained provider (VCI/KBS) financial facts.

WHAT THIS IS
    A follow-on inside the existing Layer-3 canonical-financial-facts lane
    (`canonical_financial_facts.py`, `canonical_financial_resolvers.py`, `canonical_fact_store.py`)
    and the current-fundamental-research inventory (`financial_fact_coverage_recovery.py`,
    `market_wide_current_fundamental_research.py`). It adds no new financial model, valuation
    engine, or provider, and promotes nothing to `OFFICIAL_QUALIFIED`.

    It answers one question precisely: for each (provider, statement_family) shape retained
    market-wide, is there enough evidence -- provider-owned schema/library-contract evidence
    *and* consistent, multi-issuer, multi-magnitude official-anchor reconciliation -- to grant a
    GENERALIZED currency/scale semantic to every fact of that shape? The answer, checked against
    the full retained evidence base, is no for every shape tested (see `SEMANTIC_BASIS_UNRESOLVED`
    below); this module still earns a narrower, per-fact `PROVIDER_EXACT_RESEARCH_USABLE` tier for
    the individual facts that are independently reconciled against a qualified official citation,
    with zero generalization to any other fact.

WHY BOTH LEGS ARE REQUIRED, NOT EITHER
    Leg 1 (schema/library-contract evidence) is necessary but not sufficient: KBS's own adapter
    (`vnstock.explorer.kbs.financial.Finance`) requests `unit=1000` and multiplies every value by
    1000.0 before returning it (see `KBS_FINANCE_INFO_SCHEMA_EVIDENCE`), and 99.97% of a 5,943-row
    market-wide sample of retained KBS values are exact multiples of 1000 -- a striking, code-
    explained pattern. But this is a *ratio identity*: it is internally consistent with "the
    provider reports whole thousands of VND" without independently anchoring the absolute unit,
    exactly the trap `docs/kbs_empirical_basis_qualification.md` already names for a different
    provider ("a ratio identity constrains only the ratio ... without one the honest answer is
    unresolved, not the plausible-looking option"). Only an independent official citation closes
    that gap, which is why leg 2 is mandatory even when leg 1 is unusually strong.

WHY THE ONE SHAPE WITH REAL RECONCILIATION EVIDENCE STILL FAILS
    `('VCI', 'balance_sheet')`, FY-end via the existing `annual_year_end_is_q4_end` alias, is the
    only shape with any multi-issuer official-anchor evidence at all: 6 of 8 tested issuers
    (FPT, HPG, NVL, PAN, POW, QNS; magnitudes spanning 8.86T-114.6T VND) agree digit-for-digit on
    `shareholders_equity`, and 5 of 7 tested (adding NVL/PAN/POW/QNS after the citation-mapping fix
    in `canonical_fact_store.load_official_citations`) agree on `cash_and_cash_equivalents`. But
    PVD and VNM *disagree* on the same shape and metric -- PVD by ~25,250x (a real, unexplained
    contradiction, not rounding), VNM by ~2.7%. A shape with real, reproducible counter-examples in
    its own tested sample is not "consistent reconciliation"; it fails the bar the milestone sets
    ("no single-ticker proof may become market-wide authority") applied honestly to a small-sample
    proof with visible contradictions.

    Every other shape (KBS income_statement/cash_flow; VCI income_statement/cash_flow) has zero
    reachable reconciliation at all: the only retained official citations are annual, the only
    retained provider payloads are quarterly (`data_bctc/*_year.parquet` do not exist for any
    ticker in the runtime store -- a pre-existing filename-collision bug, `bctc_sync.py`'s own
    "[VÁ P0-1 12/07/2026]" comment, silently deleted them before the fix shipped), and the
    stock-vs-flow alias that lets an annual citation stand in for a Q4 balance-sheet fact does not
    and must not apply to flow metrics (revenue, net_income, operating_cash_flow) -- `FY2024
    revenue is not Q4 revenue`, per `canonical_fact_store.load_official_citations`'s own docstring.

WHAT THIS MODULE DOES NOT DO
    - Does not touch `market_wide_current_fundamental_research.OFFICIAL_TIER` classification.
    - Does not widen `docs/kbs_empirical_basis_qualification.md`'s or
      `docs/vci_volume_basis_qualification.md`'s price/volume verdicts (disjoint evidence domain).
    - Does not acquire any new payload, call any network endpoint, or add a provider.
    - Does not activate VALUE/READY, ranking, recommendation, sizing, or execution.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from canonical_financial_facts import METRIC_REGISTRY, STATUS_QUALIFIED
from field_temporal_contract import stable_id

CONTRACT_VERSION = "provider_financial_semantic_basis/v1"
SCHEMA_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Phase 6 -- outcome-state vocabulary (exactly the five states the milestone names)
# ---------------------------------------------------------------------------

PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED = "PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED"
PROVIDER_TREND_ONLY = "PROVIDER_TREND_ONLY"
PROVIDER_METADATA_PARTIAL = "PROVIDER_METADATA_PARTIAL"
SEMANTIC_BASIS_UNRESOLVED = "SEMANTIC_BASIS_UNRESOLVED"
NOT_APPLICABLE = "NOT_APPLICABLE"
SHAPE_VERDICTS = frozenset({
    PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED, PROVIDER_TREND_ONLY,
    PROVIDER_METADATA_PARTIAL, SEMANTIC_BASIS_UNRESOLVED, NOT_APPLICABLE,
})

#: The per-fact tier this module can grant. Distinct from `canonical_financial_facts.
#: STATUS_QUALIFIED`, which is a fact-level currency/scale resolution, and from
#: `market_wide_current_fundamental_research.OFFICIAL_TIER`, which is a ticker-level panel
#: membership. A fact may be `STATUS_QUALIFIED` and still never reach `OFFICIAL_QUALIFIED`.
PROVIDER_EXACT_RESEARCH_USABLE = "PROVIDER_EXACT_RESEARCH_USABLE"

#: Phase 6's named non-authoritative valuation-input use, kept distinct from an authoritative one.
CURRENT_RESEARCH_NONAUTHORITATIVE_VALUATION_INPUT = "CURRENT_RESEARCH_NONAUTHORITATIVE_VALUATION_INPUT"

ALLOWED_USES = (
    "descriptive_context",
    "provider_series_growth",
    "sector_aware_research",
    "shadow_comparison",
    CURRENT_RESEARCH_NONAUTHORITATIVE_VALUATION_INPUT,
)
FORBIDDEN_USES = (
    "official_label",
    "historical_pit_claim",
    "execution_actionability",
    "target_price",
    "buy_sell_recommendation",
    "cross_sectional_ranking",
    "portfolio_sizing",
    "authoritative_valuation_input",
    "backtesting",
)

# ---------------------------------------------------------------------------
# Phase 1/2 -- provider/endpoint schema evidence, cited to installed library source.
# Both dicts describe the adapter this repo actually calls (`bctc_sync.py` ->
# `vnstock.api.financial.Finance(source=..., symbol=...).<method>(period=...)`), not a live probe:
# the installed library source is more precise than a fresh network capture, because it shows the
# exact transform applied, not merely a schema snapshot. Verified against `vnstock==4.0.4`
# (the version pinned in this environment and the one `bctc_sync.py`/`financial_observations.py`
# actually import).
# ---------------------------------------------------------------------------

KBS_FINANCE_INFO_SCHEMA_EVIDENCE: dict[str, Any] = {
    "provider": "KBS",
    "library": "vnstock", "library_version": "4.0.4",
    "endpoint_contract": "vnstock.explorer.kbs.financial.Finance._fetch_financial_data (KBS SAS finance-info API)",
    "source_citation": (
        "vnstock/explorer/kbs/financial.py:558-577 (_fetch_financial_data request params), "
        ":128-331 (_parse_financial_response Head/Audit/Unit extraction), "
        ":333-440 (_fetch_series_data pagination + unit_multiplier=1000.0)"
    ),
    "statement_families_reachable": ("income_statement", "balance_sheet", "cash_flow", "financial_ratios"),
    "statement_families_empirically_populated": ("income_statement", "cash_flow"),
    "statement_families_empirically_empty_reason": {
        "balance_sheet": "KBS CDKT response is empty for every retained ticker (0/1,493 KBS-sourced "
                          "balance_sheet payloads; VCI supplies 100% of retained balance_sheet data, "
                          "confirmed via bctc_sync scrape_meta.csv crosstab, and independently by "
                          "docs/financial_identity_source_qualification.md's 2026-07-26 probe)",
    },
    "request_contract": {"type": "KQKD|CDKT|LCTT|CSTC", "termtype": "1=year,2=quarter",
                          "unit": 1000, "languageid": 1, "unit_comment": "Đơn vị ngàn đồng (thousand VND)"},
    "response_head_fields_extracted_by_installed_library": ("YearPeriod", "TermName", "AuditedStatus", "United"),
    "response_head_fields_named_in_library_but_not_extracted": ("PeriodBegin", "PeriodEnd", "ReportDate", "LastUpdate", "TermNameEN"),
    "response_head_fields_note": (
        "The installed adapter's own docstring (financial.py:160) states 'Head contains: YearPeriod, "
        "TermName, TermNameEN, AuditedStatus, ReportDate, etc.', naming ReportDate/PeriodBegin/"
        "PeriodEnd as real endpoint fields it simply does not read into the DataFrame it returns."
    ),
    "period_basis_evidence": {
        "Q1": "SINGLE_QUARTER", "Q2": "SINGLE_QUARTER", "Q3": "SINGLE_QUARTER", "Q4": "SINGLE_QUARTER",
        "FY": "NOT_IN_QUARTER_ENDPOINT",
        "basis": "provider_owned_kbs_kqkd_quarter_schema_periodbegin_periodend_bounded_2026-08-23",
        "basis_note": "pre-existing finding, unchanged; already wired into "
                       "market_wide_current_fundamental_research.KBS_KQKD_QUARTER_SEMANTICS/_period_basis",
    },
    "unit_multiplier_applied_by_library": 1000.0,
    "unit_multiplier_evidence": (
        "financial.py:566 sends params['unit']=1000 (\"Đơn vị ngàn đồng\"); financial.py:367 passes "
        "unit_multiplier=1000.0 into _parse_financial_response; financial.py:259 applies "
        "value = float(value) * unit_multiplier to every cell before returning the DataFrame."
    ),
    "unit_multiplier_empirical_corroboration": (
        "99.966% (5,940/5,943) of a random 60-ticker, non-zero, KBS-sourced sample of retained "
        "raw_value observations under data/market-wide-financials/observations/ are exact integer "
        "multiples of 1000 -- consistent with, but not independent proof of, the request+multiplier "
        "contract above. A ratio/pattern match is leg-1 corroboration only; see module docstring."
    ),
    "retained_bytes_carry_head_metadata": False,
    "retained_bytes_reason": (
        "bctc_sync.py:95-98 calls vnstock.api.financial.Finance(source=source, symbol=symbol) and "
        "bctc_sync.py:164-168 persists exactly the pandas DataFrame that method returns to parquet. "
        "Head/Audit/Unit dicts are consumed internally by _parse_financial_response and never appear "
        "in that DataFrame -- the metadata is discarded by the vnstock library itself, one layer "
        "above anything this repository's retention code touches. There is no retained raw byte on "
        "disk today from which PeriodBegin/PeriodEnd/AuditedStatus/LastUpdate could be recovered; "
        "recovering them would require a new request to the endpoint, which Phase 4 evaluates below."
    ),
    "currency_scale_schema_evidence_sufficient_alone": False,
}

VCI_FINANCE_SCHEMA_EVIDENCE: dict[str, Any] = {
    "provider": "VCI",
    "library": "vnstock", "library_version": "4.0.4",
    "endpoint_contract": "vnstock.explorer.vci.financial.Finance (VCI IQ finance-report API)",
    "source_citation": "vnstock/explorer/vci/financial.py (full module: zero occurrences of "
                        "unit/scale/currency/multiplier/VND of any kind)",
    "statement_families_reachable": ("income_statement", "balance_sheet", "cash_flow"),
    "statement_families_empirically_dominant": ("balance_sheet",),
    "request_contract": {"period": "year|quarter"},
    "response_fields_observed": ("yearReport", "lengthReport", "publicDate", "createDate", "updateDate"),
    "response_fields_evidence": (
        "market_wide_current_fundamental_research.VCI_INCOME_STATEMENT_SEMANTICS (2026-08-23 bounded "
        "review) plus docs/financial_statement_semantic_qualification.md's 2026-07-26 audit of "
        "vnstock/explorer/vci/financial.py: no consolidated/separate parameter, no response-scope "
        "parser, no currency mapping, no scale mapping, no cumulative-basis marker."
    ),
    "period_basis_evidence": {"Q1": "UNKNOWN", "Q2": "UNKNOWN", "Q3": "UNKNOWN", "Q4": "UNKNOWN", "FY": "UNKNOWN"},
    "unit_multiplier_applied_by_library": None,
    "unit_multiplier_evidence": "No unit/scale request parameter and no value multiplier anywhere in "
                                 "vnstock/explorer/vci/financial.py; values pass through unmodified.",
    "unit_multiplier_empirical_corroboration": (
        "Only 13.6% (3,383/24,885) of a random 60-ticker, non-zero, VCI-sourced sample are exact "
        "multiples of 1000 -- consistent with full VND-unit precision and the absence of any "
        "provider-side rescaling, unlike KBS."
    ),
    "retained_bytes_carry_head_metadata": False,
    "retained_bytes_reason": "The VCI adapter's own response never carries scope/currency/scale "
                              "metadata to discard; there is nothing upstream of this repository's "
                              "retention layer for a repair to recover.",
    "currency_scale_schema_evidence_sufficient_alone": False,
}

SCHEMA_EVIDENCE_BY_PROVIDER: dict[str, Mapping[str, Any]] = {
    "KBS": KBS_FINANCE_INFO_SCHEMA_EVIDENCE,
    "VCI": VCI_FINANCE_SCHEMA_EVIDENCE,
}

#: Reused, not duplicated: which canonical identities are reachable from which statement family,
#: read directly off the existing Layer-3 metric registry.
IDENTITIES_BY_STATEMENT_FAMILY: dict[str, tuple[str, ...]] = {}
for _metric, _definition in METRIC_REGISTRY.items():
    _families = {c.statement_family for c in _definition.get("candidates", [])} or {_definition.get("statement")}
    for _family in _families:
        if _family:
            IDENTITIES_BY_STATEMENT_FAMILY.setdefault(str(_family), []).append(_metric)
IDENTITIES_BY_STATEMENT_FAMILY = {k: tuple(sorted(v)) for k, v in IDENTITIES_BY_STATEMENT_FAMILY.items()}

#: Minimum distinct issuers *and* the minimum ratio between the smallest and largest agreeing
#: magnitude for a shape's reconciliation to even be eligible for consideration as "discriminating".
#: Both are read off the milestone brief ("prefer anchors spanning materially different magnitudes
#: and more than one issuer"); they gate eligibility only -- see `NO_DISAGREEMENT_TOLERANCE` below
#: for the actual pass/fail rule, which is stricter than either of these.
MIN_DISCRIMINATING_ISSUERS = 2
MIN_DISCRIMINATING_MAGNITUDE_RATIO = 5.0

#: The qualification rule is zero-tolerance: any reproducible disagreement inside a shape's own
#: tested anchor set means the shape is not "consistent reconciliation", full stop. This is
#: deliberately stricter than a majority vote -- see module docstring for the PVD/VNM evidence this
#: exists to catch.
NO_DISAGREEMENT_TOLERANCE = 0


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"provider_financial_semantic_basis:{digest}"}


# ---------------------------------------------------------------------------
# Phase 3 -- official-anchor reconciliation (pure: takes already-built facts, does no I/O itself)
# ---------------------------------------------------------------------------

def _fact_shape(fact: Mapping[str, Any]) -> tuple[Any, Any]:
    return (fact.get("provider"), fact.get("statement_family"))


def reconcile_official_anchors(facts_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    """Group every retained fact by (provider, statement_family) and record, per shape, which
    facts independently agree with a qualified official citation (`status == qualified`) and which
    ones reproducibly disagree (`official_citation_disagrees` conflict). Pure aggregation over
    caller-supplied facts; makes no network call and reads no file itself.
    """
    agree: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    disagree: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    tested: dict[tuple, set[str]] = defaultdict(set)

    for ticker, facts in facts_by_ticker.items():
        for fact in facts:
            shape = _fact_shape(fact)
            has_citation_check = fact.get("status") == STATUS_QUALIFIED or any(
                c.get("kind") == "official_citation_disagrees" for c in (fact.get("conflicts") or [])
            )
            if not has_citation_check:
                continue
            tested[shape].add(str(ticker).upper())
            if fact.get("status") == STATUS_QUALIFIED:
                agree[shape].append(dict(fact))
            else:
                disagree[shape].append(dict(fact))

    shapes = sorted(set(agree) | set(disagree), key=str)
    per_shape: dict[str, Any] = {}
    for shape in shapes:
        agreeing = agree.get(shape, [])
        disagreeing = disagree.get(shape, [])
        agreeing_values = [abs(float(f["value"])) for f in agreeing if isinstance(f.get("value"), (int, float))]
        per_shape[str(shape)] = {
            "provider": shape[0], "statement_family": shape[1],
            "tested_issuer_count": len(tested[shape]),
            "agree_count": len(agreeing),
            "disagree_count": len(disagreeing),
            "agreeing_tickers": sorted({f["ticker"] for f in agreeing}),
            "disagreeing_tickers": sorted({f["ticker"] for f in disagreeing}),
            "agreeing_metrics": sorted({f["canonical_metric"] for f in agreeing}),
            "agreeing_periods": sorted({f["reporting_period"] for f in agreeing}),
            "magnitude_min": min(agreeing_values) if agreeing_values else None,
            "magnitude_max": max(agreeing_values) if agreeing_values else None,
            "disagreements": [
                {
                    "ticker": f["ticker"], "canonical_metric": f["canonical_metric"],
                    "reporting_period": f["reporting_period"],
                    "provider_value": f.get("value"),
                    "official_value": next(
                        (c.get("official_value") for c in f.get("conflicts", [])
                         if c.get("kind") == "official_citation_disagrees"), None),
                }
                for f in disagreeing
            ],
        }
    return {
        "contract_version": CONTRACT_VERSION, "artifact_type": "OFFICIAL_ANCHOR_RECONCILIATION",
        "shapes": per_shape,
    }


def _is_consistent(shape_reconciliation: Mapping[str, Any]) -> bool:
    """A shape is 'consistent reconciliation' only with zero disagreements in its own tested
    sample -- see `NO_DISAGREEMENT_TOLERANCE`. Meeting the discriminating-anchor minimums without
    also meeting this is still not consistent; the two checks are independent and both required.
    """
    return shape_reconciliation.get("disagree_count", 0) <= NO_DISAGREEMENT_TOLERANCE


def _is_discriminating(shape_reconciliation: Mapping[str, Any]) -> bool:
    issuers = len(shape_reconciliation.get("agreeing_tickers") or [])
    lo, hi = shape_reconciliation.get("magnitude_min"), shape_reconciliation.get("magnitude_max")
    ratio = (hi / lo) if (lo not in (None, 0) and hi is not None) else 0.0
    return issuers >= MIN_DISCRIMINATING_ISSUERS and ratio >= MIN_DISCRIMINATING_MAGNITUDE_RATIO


# ---------------------------------------------------------------------------
# Phase 5 -- versioned provider/endpoint-scoped semantic-basis contract
# ---------------------------------------------------------------------------

def evaluate_semantic_basis_contract(
    *, provider: str, statement_family: str,
    reconciliation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """One `provider_financial_semantic_basis/v1` contract row for one (provider, statement_family)
    shape. Never infers scale/currency from magnitude alone (`resolve_currency_and_scale`'s own
    rule, reused here at the shape level): a shape reaches `PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED`
    only with schema evidence *and* zero-disagreement, discriminating, multi-issuer reconciliation.
    """
    schema = SCHEMA_EVIDENCE_BY_PROVIDER.get(provider)
    recon = dict(reconciliation or {})
    has_schema = schema is not None
    has_duration_evidence = bool(schema) and any(
        v != "UNKNOWN" for k, v in schema.get("period_basis_evidence", {}).items() if k != "basis"
    )
    consistent = _is_consistent(recon) if recon else False
    discriminating = _is_discriminating(recon) if recon else False
    has_any_agreement = (recon.get("agree_count") or 0) > 0
    identities = IDENTITIES_BY_STATEMENT_FAMILY.get(statement_family, ())
    empty_reason = (schema or {}).get("statement_families_empirically_empty_reason", {}).get(statement_family)

    if not identities:
        verdict = NOT_APPLICABLE
        currency = scale = statement_scope = "NOT_APPLICABLE"
        reason = (f"no canonical identity in the existing valuation contract "
                  f"(canonical_financial_facts.METRIC_REGISTRY) is sourced from statement_family="
                  f"{statement_family!r}; this shape has nothing for the inventory to classify")
    elif empty_reason:
        verdict = NOT_APPLICABLE
        currency = scale = statement_scope = "NOT_APPLICABLE"
        reason = f"endpoint reachable in principle but empirically returns no data market-wide: {empty_reason}"
    elif has_schema and consistent and discriminating:
        verdict = PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED
        currency, scale, statement_scope = "VND", "units", "REQUIRES_PER_FACT_MINORITY_INTEREST_EVIDENCE"
        reason = "provider-owned schema/library-contract evidence plus zero-disagreement, " \
                 "discriminating, multi-issuer official-anchor reconciliation"
    elif recon.get("disagree_count"):
        verdict = SEMANTIC_BASIS_UNRESOLVED
        currency = scale = statement_scope = "UNKNOWN_FAIL_CLOSED"
        reason = (f"{recon['disagree_count']} of {recon['disagree_count'] + recon.get('agree_count', 0)} "
                  "tested official-anchor comparisons disagree within this shape's own sample "
                  "(see reconciliation.disagreements) -- a single-issuer proof (or a proof with a live "
                  "counter-example) may not become market-wide authority")
    elif has_schema and has_duration_evidence and not has_any_agreement:
        verdict = PROVIDER_METADATA_PARTIAL
        currency = scale = statement_scope = "UNKNOWN_FAIL_CLOSED"
        reason = "provider-owned schema/library-contract evidence resolves duration/period-basis " \
                 "for some metric families, but no official-anchor reconciliation is reachable for " \
                 "this shape (annual citation vs. quarterly-only retained payloads for flow metrics, " \
                 "or zero retained citations at all) -- currency/scale/full scope remain unresolved"
    else:
        verdict = SEMANTIC_BASIS_UNRESOLVED
        currency = scale = statement_scope = "UNKNOWN_FAIL_CLOSED"
        reason = "no provider-owned schema/library-contract evidence and no reachable official-anchor " \
                 "reconciliation for this shape"

    period_basis = (schema or {}).get("period_basis_evidence", {}).get("basis") if has_duration_evidence else "UNKNOWN"

    contract = {
        "contract_version": CONTRACT_VERSION,
        "provider": provider,
        "endpoint_contract": (schema or {}).get("endpoint_contract"),
        "statement_family": statement_family,
        "canonical_identity": list(identities),
        "canonical_identity_note": "currency/scale is a statement-level (per source payload) "
                                    "convention, not a per-line-item one; this contract governs "
                                    "every identity reachable from this statement_family uniformly, "
                                    "never a single cherry-picked identity",
        "currency": currency,
        "scale": scale,
        "statement_scope": statement_scope,
        "period_basis": period_basis,
        "qualification_evidence": {
            "schema_evidence": schema,
            "reconciliation": recon or None,
            "discriminating": discriminating,
            "consistent": consistent,
        },
        "allowed_uses": list(ALLOWED_USES) if verdict == PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED else [],
        "forbidden_uses": list(FORBIDDEN_USES),
        "verdict": verdict,
        "verdict_reason": reason,
    }
    return contract


def build_semantic_basis_registry(reconciliation: Mapping[str, Any]) -> dict[str, Any]:
    """The full Phase-5 registry: one contract per (provider, statement_family) shape that has
    either schema evidence on file (`SCHEMA_EVIDENCE_BY_PROVIDER`) or any observed reconciliation
    attempt, so a shape with real counter-evidence is never silently omitted.
    """
    shapes_recon = (reconciliation or {}).get("shapes", {})
    shape_keys: set[tuple[str, str]] = set()
    for provider, schema in SCHEMA_EVIDENCE_BY_PROVIDER.items():
        for family in schema.get("statement_families_reachable", ()):
            shape_keys.add((provider, family))
    for key_str, row in shapes_recon.items():
        if row.get("provider") and row.get("statement_family"):
            shape_keys.add((row["provider"], row["statement_family"]))

    contracts = {}
    for provider, family in sorted(shape_keys):
        recon_row = next(
            (row for row in shapes_recon.values()
             if row.get("provider") == provider and row.get("statement_family") == family),
            None,
        )
        contract = evaluate_semantic_basis_contract(provider=provider, statement_family=family, reconciliation=recon_row)
        contracts[f"{provider}:{family}"] = contract

    verdict_counts: dict[str, int] = {verdict: 0 for verdict in SHAPE_VERDICTS}
    for contract in contracts.values():
        verdict_counts[contract["verdict"]] += 1

    registry = {
        "contract_version": CONTRACT_VERSION, "schema_version": SCHEMA_VERSION,
        "artifact_type": "PROVIDER_FINANCIAL_SEMANTIC_BASIS_REGISTRY",
        "contracts": contracts,
        "verdict_counts": dict(sorted(verdict_counts.items())),
        "any_shape_absolute_research_qualified": any(
            c["verdict"] == PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED for c in contracts.values()
        ),
    }
    registry.update(content_identity(registry))
    return registry


# ---------------------------------------------------------------------------
# Phase 6 -- per-fact PROVIDER_EXACT_RESEARCH_USABLE boundary
#
# Two independent routes, evaluated generically (no ticker literal anywhere):
#   (a) shape route: the fact's own (provider, statement_family) shape reached
#       PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED in the registry -> every compatible-period fact of
#       that exact shape qualifies. Never true today (see module docstring); wired for the future.
#   (b) per-fact route: this exact fact was independently reconciled against a qualified official
#       citation (`status == qualified`, `authority == official_citation_agreement`), *and* its own
#       statement_scope is independently evidenced (not `unknown`) -- belt-and-suspenders against a
#       scope mismatch that happened to produce a coincidentally-matching value. Zero generalization
#       to any other ticker, period, or metric.
# ---------------------------------------------------------------------------

def classify_provider_exact_research_usable(
    fact: Mapping[str, Any], *, registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Decide whether one already-built canonical fact may carry
    `PROVIDER_EXACT_RESEARCH_USABLE`. Pure; reads only the fields on `fact` and the shape verdict
    in `registry` (if supplied). Returns `{"eligible": bool, "reason": str, ...}`.
    """
    shape_key = f"{fact.get('provider')}:{fact.get('statement_family')}"
    shape_contract = (registry or {}).get("contracts", {}).get(shape_key)
    if shape_contract and shape_contract.get("verdict") == PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED:
        return {
            "eligible": True, "route": "SHAPE_CONTRACT",
            "reason": f"shape {shape_key} carries {PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED}",
            "tier": PROVIDER_EXACT_RESEARCH_USABLE,
            "research_use_label": CURRENT_RESEARCH_NONAUTHORITATIVE_VALUATION_INPUT,
            "allowed_uses": list(ALLOWED_USES), "forbidden_uses": list(FORBIDDEN_USES),
        }

    if fact.get("status") != STATUS_QUALIFIED:
        return {"eligible": False, "route": None, "reason": "fact status is not qualified (no "
                "independent official-citation agreement)", "tier": None}
    if fact.get("unit_authority") != "official_citation_agreement":
        return {"eligible": False, "route": None, "reason": "qualified status not backed by "
                "official_citation_agreement authority", "tier": None}
    if fact.get("statement_scope") in (None, "unknown"):
        return {"eligible": False, "route": None, "reason": "statement_scope is independently "
                "unresolved for this fact; an exact value match alone does not establish scope "
                "(test: consolidated/separate mismatch must fail closed)", "tier": None}
    if fact.get("currency") in (None, "unknown") or fact.get("scale") in (None, "unknown"):
        return {"eligible": False, "route": None, "reason": "currency or scale still unknown on "
                "this fact despite qualified status", "tier": None}

    return {
        "eligible": True, "route": "PER_FACT_OFFICIAL_CITATION_AGREEMENT",
        "reason": f"fact independently reconciled against official citation "
                  f"(ticker={fact.get('ticker')}, metric={fact.get('canonical_metric')}, "
                  f"period={fact.get('reporting_period')}); no generalization to any other fact",
        "tier": PROVIDER_EXACT_RESEARCH_USABLE,
        "research_use_label": CURRENT_RESEARCH_NONAUTHORITATIVE_VALUATION_INPUT,
        "allowed_uses": list(ALLOWED_USES), "forbidden_uses": list(FORBIDDEN_USES),
    }


# ---------------------------------------------------------------------------
# Bounded, targeted evidence loader for Phase 7: only ever touches the tickers that appear as an
# official-citation key, because only those tickers can possibly reach PROVIDER_EXACT_RESEARCH_
# USABLE via the per-fact route. Zero network; reads only already-retained `dashboard-runtime`
# bytes (data_bctc/*.parquet via the existing raw store, data/official-evidence/*.jsonl citations).
# ---------------------------------------------------------------------------

def load_provider_exact_research_evidence(
    runtime_root: Path | str, *, registry: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Per ticker with at least one official citation, per canonical_metric: every fact this
    module would mark `PROVIDER_EXACT_RESEARCH_USABLE`. Bounded to that ticker set by construction
    -- a ticker with zero citations cannot reach this tier via the per-fact route, and the shape
    route (checked identically here) needs no per-ticker evidence at all.
    """
    import canonical_fact_store as store  # local import: this module has no other reason to load
    # the store/DataFrame dependency chain, so importable-without-pandas stays true for every other
    # function here (all pure, all synthetic-fact-testable, as the test suite relies on).

    runtime_root = Path(runtime_root)
    official_citations = store.load_official_citations(runtime_root)
    tickers = sorted({key[0] for key in official_citations})
    if not tickers:
        return {}
    profiles = store.load_entity_profiles(Path(__file__).with_name("config") / "ticker_entity_profiles.csv")

    evidence: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for ticker in tickers:
        built = store.build_ticker_facts(runtime_root, ticker, profiles=profiles, official_citations=official_citations)
        usable_by_metric: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for fact in built.get("facts", []):
            decision = classify_provider_exact_research_usable(fact, registry=registry)
            if decision["eligible"]:
                usable_by_metric[str(fact["canonical_metric"])].append({
                    "reporting_period": fact["reporting_period"], "period_type": fact["period_type"],
                    "provider": fact["provider"], "statement_family": fact["statement_family"],
                    "value": fact["value"], "currency": fact["currency"], "scale": fact["scale"],
                    "route": decision["route"],
                })
        if usable_by_metric:
            evidence[ticker] = dict(usable_by_metric)
    return evidence
