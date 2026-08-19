"""Market-wide issuer archetype resolution and per-metric model applicability.

THE GAP THIS CLOSES
    The 2026-08-03 market-wide readiness audit found that EBITDA / EV-EBITDA are marked
    `not_applicable` for only the 7 manually-profiled non-corporate tickers, while the 83
    tickers the generated taxonomy separately evidences as specialized financial filers
    fall into plain `unavailable` -- i.e. the pipeline reports "we could not compute a bank's
    EBITDA" where the truth is "a bank has no EBITDA". `unavailable` invites someone to go
    find the missing input; `not_applicable` closes the question. This module makes the
    difference structural rather than per-ticker.

TWO EVIDENCE FAMILIES, NOT ONE
    `statement_taxonomy_sidecar.py` classifies the *balance sheet* only, which leaves 109
    tickers that have an income statement but no retained balance sheet unclassified, and
    leaves the insurance template permanently `financial_specialized_ambiguous` because no
    exclusive insurance marker set exists on the balance sheet.

    This module adds a second, independent family: the **income statement**. Its marker
    sets were derived from the retained payloads and validated market-wide before being
    written down (1,453 income-statement payloads; see
    `docs/market_wide_financial_normalization_contract.md` for the validation record):

        * zero of the markers below appear in the union of all 1,261 corporate-template
          income statements;
        * each set matches 100% of its group and 0% of the other two;
        * the insurance set resolves 12 of the 13 tickers the balance-sheet classifier can
          only call `financial_specialized_ambiguous`.

    The income-statement evidence lives here, deliberately not inside
    `statement_taxonomy_classifier.py`: that module is pinned at VERSION 2.0.0 and its
    output feeds `statement_taxonomy_sidecar.json`, which is hash-bound into the shipped
    bundle. Adding markers there would move `classifier_version` and therefore the sidecar
    fingerprint, changing a production artifact for a reason unrelated to this milestone.

THE AUTHORITY ORDER IS UNCHANGED
    1. `config/ticker_entity_profiles.csv` -- the only thing that may *name* an issuer's
       institution type.
    2. Generated statement evidence -- may only ever *withhold* a corporate model. A
       corporate template never grants a corporate archetype, and an absent archetype is
       never read as corporate.
    3. Unknown -- yields `insufficient_evidence`, never a default.

    Disagreement between the two evidence families does not restore a corporate model: two
    families disputing *which* specialized financial template a filer uses still agree that
    it is one. Withholding is the fail-closed direction and stays.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable, Mapping

VERSION = "1.0.0"

#: Institution types a manual profile may name, and whether the corporate earnings models
#: apply to them. The vocabulary matches `config/ticker_entity_profiles.csv`.
CORPORATE_ENTITY_TYPES = frozenset({"corporate"})
FINANCIAL_ENTITY_TYPES = frozenset({"bank", "securities", "insurance", "finance_company"})

#: Generated evidence families. These name a *reporting template*, never an institution.
FINANCIAL_TEMPLATE_FAMILIES = ("credit_institution", "securities_company", "insurance")

#: Income-statement markers exclusive to the credit-institution template (49/2014/TT-NHNN).
#: Interest/fee/provision lines exist only because the filer intermediates credit.
CREDIT_INSTITUTION_INCOME_MARKERS = (
    "net_interest_income",
    "interest_income_and_similar_income",
    "provision_for_credit_losses",
    "operating_profit_before_provision_for_credit_losses",
    "net_fee_and_commission_income",
)

#: Income-statement markers exclusive to the broker template (210/2014/TT-BTC). Custody,
#: advisory and covered-warrant revaluation lines exist only because the filer holds and
#: trades client assets.
SECURITIES_INCOME_MARKERS = (
    "revenue_from_securities_custody_services",
    "revenue_from_investment_advisory_services",
    "gains_from_financial_assets_at_fair_value_through_profit_or_loss_fvtpl",
    "interest_income_from_loans_and_receivables",
    "gain_from_revaluation_of_outstanding_covered_warrant_payables",
)

#: Income-statement markers exclusive to the insurance template. Premium, reinsurance,
#: claim-reserve and underwriting lines have no corporate-template counterpart. This is the
#: set the balance sheet could not supply.
INSURANCE_INCOME_MARKERS = (
    "total_net_revenue_from_insurance_business",
    "reinsurance_premium_ceded_2",
    "increase_decrese_in_gross_unearned_premium_reserve",
    "claim_and_maturity_payment_expenses",
    "other_underwriting_expenses",
)

_INCOME_MARKER_SETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("credit_institution", CREDIT_INSTITUTION_INCOME_MARKERS),
    ("securities_company", SECURITIES_INCOME_MARKERS),
    ("insurance", INSURANCE_INCOME_MARKERS),
)

#: How the balance-sheet taxonomy vocabulary maps onto the families above.
#: `financial_specialized_ambiguous` evidences "some specialized financial template" and is
#: enough to withhold, which is all this module asks of it.
_BALANCE_SHEET_FAMILY = {
    "credit_institution": "credit_institution",
    "securities_company": "securities_company",
    "financial_specialized_ambiguous": "financial_specialized_ambiguous",
}

#: Metrics that are defined only for the corporate earnings model.
CORPORATE_ONLY_METRICS = ("ebitda", "ev_ebitda")

#: What to look at instead, per template family. Named so a `not_applicable` result points
#: somewhere rather than just closing a door.
SUBSTITUTE_METRICS = {
    "credit_institution": ("p_b", "roe", "net_interest_margin", "cost_to_income_ratio",
                           "non_performing_loan_ratio", "loan_loss_coverage",
                           "capital_adequacy_ratio"),
    "securities_company": ("p_b", "roe", "brokerage_market_share", "margin_lending_book",
                           "cost_to_income_ratio"),
    "insurance": ("p_b", "roe", "combined_ratio", "loss_ratio", "expense_ratio",
                  "solvency_margin"),
    "financial_specialized_ambiguous": ("p_b", "roe"),
}

_AUTHORITY_MANUAL = "manual_profile"
_AUTHORITY_PROMOTED = "promoted_record_authority"
_AUTHORITY_GENERATED = "generated_statement_evidence"
_AUTHORITY_UNKNOWN = "unknown"

_STATUS_NOT_APPLICABLE = "not_applicable"
_STATUS_APPLICABLE = "applicable_subject_to_inputs"
_STATUS_INSUFFICIENT = "insufficient_evidence"


def load_entity_profiles(
    path: Path | str | None = None,
    promoted_path: Path | str | None = None,
    *,
    use_layered: bool = True,
) -> dict[str, str]:
    """`config/ticker_entity_profiles.csv` + promoted records -> {TICKER: entity_type}.

    Under Layered Authority Topology B (use_layered=True), merges seed authority and
    owner-approved promoted records from config/promoted_entity_classifications.json.
    """
    if not use_layered:
        if not path:
            return {}
        p = Path(path)
        if not p.is_file():
            return {}
        profiles: dict[str, str] = {}
        with p.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                ticker = str(row.get("ticker") or "").strip().upper()
                entity_type = str(row.get("entity_type") or "").strip().lower()
                if ticker and entity_type and entity_type not in {"unknown", "none", "null"}:
                    profiles[ticker] = entity_type
        return profiles

    from entity_classification_contract import load_layered_entity_profiles
    return load_layered_entity_profiles(seed_path=path, promoted_path=promoted_path)


def classify_income_statement(item_ids: Iterable[str]) -> dict[str, Any]:
    """Observe which specialized financial template an income statement evidences.

    Returns `{"template_family", "matched_markers", "reason"}`. `template_family` is None
    for anything that is not positively evidenced -- including a perfectly ordinary
    corporate income statement, which this function deliberately refuses to name.
    """
    present = {str(item).strip() for item in item_ids if str(item).strip()}
    matched = {family: sorted(marker for marker in markers if marker in present)
               for family, markers in _INCOME_MARKER_SETS}
    hits = sorted(family for family, markers in matched.items() if markers)
    if not hits:
        return {"template_family": None, "matched_markers": {},
                "reason": ("no exclusive specialized-financial income-statement marker; "
                           "absence of financial markers is never read as corporate")}
    if len(hits) > 1:
        return {"template_family": "financial_specialized_conflicted",
                "matched_markers": {family: matched[family] for family in hits},
                "reason": ("income statement carries exclusive markers of more than one "
                           f"specialized financial template ({', '.join(hits)})")}
    family = hits[0]
    return {"template_family": family, "matched_markers": {family: matched[family]},
            "reason": (f"income statement carries {len(matched[family])} marker(s) exclusive "
                       f"to the {family} template")}


def _balance_sheet_family(taxonomy: Any) -> str | None:
    return _BALANCE_SHEET_FAMILY.get(str(taxonomy or "").strip())


def resolve_archetype(ticker: str, *, manual_entity_type: Any = None,
                      balance_sheet_taxonomy: Any = None,
                      income_statement_family: Any = None) -> dict[str, Any]:
    """Resolve one issuer's archetype under the fixed authority order.

    `issuer_entity_type` is populated only from a manual profile. `template_family` carries
    generated evidence and is populated only when a specialized financial template is
    positively evidenced.
    """
    manual = str(manual_entity_type or "").strip().lower()
    manual = manual if manual and manual not in {"unknown", "none", "null"} else None

    authority_override = None
    reason_override = None
    if manual:
        authority_override = _AUTHORITY_MANUAL
        reason_override = "manually verified entity profile takes precedence over generated evidence"
    else:
        from entity_classification_contract import resolve_layered_entity_classification
        layered_res = resolve_layered_entity_classification(ticker)
        if layered_res.is_positive_authority and layered_res.resolved_entity_class.value in CORPORATE_ENTITY_TYPES | FINANCIAL_ENTITY_TYPES:
            manual = layered_res.resolved_entity_class.value
            if layered_res.authority_tier == "promoted_record_authority":
                authority_override = _AUTHORITY_PROMOTED
                reason_override = f"approved promoted entity record takes precedence: {layered_res.reason}"
            else:
                authority_override = _AUTHORITY_MANUAL
                reason_override = "manually verified entity profile takes precedence over generated evidence"

    bs_family = _balance_sheet_family(balance_sheet_taxonomy)
    is_family = str(income_statement_family or "").strip() or None

    evidence = {
        "balance_sheet_taxonomy": (str(balance_sheet_taxonomy).strip()
                                   if balance_sheet_taxonomy else None),
        "balance_sheet_family": bs_family,
        "income_statement_family": is_family,
    }

    observed = [family for family in (bs_family, is_family) if family]
    specific = {family for family in observed
                if family in FINANCIAL_TEMPLATE_FAMILIES}
    if not observed:
        agreement = "no_generated_evidence"
    elif len(observed) == 1:
        agreement = "single_family_only"
    elif len(specific) > 1:
        agreement = "conflicting"
    elif bs_family == "financial_specialized_ambiguous" and is_family in FINANCIAL_TEMPLATE_FAMILIES:
        # The income statement resolves what the balance sheet could only call ambiguous.
        agreement = "income_statement_disambiguates"
    elif bs_family == is_family:
        agreement = "agreeing"
    else:
        agreement = "conflicting"

    if agreement == "income_statement_disambiguates":
        template_family = is_family
    elif agreement == "conflicting":
        template_family = "financial_specialized_conflicted"
    elif specific:
        template_family = sorted(specific)[0]
    elif observed:
        template_family = observed[0]
    else:
        template_family = None

    financial_evidence = template_family is not None

    if manual:
        return {
            "ticker": str(ticker).upper(),
            "issuer_entity_type": manual,
            "authority": authority_override or _AUTHORITY_MANUAL,
            "template_family": template_family,
            "generated_evidence": evidence,
            "evidence_agreement": agreement,
            "reason": reason_override or "manually verified entity profile takes precedence over generated evidence",
        }
    if financial_evidence:
        return {
            "ticker": str(ticker).upper(),
            "issuer_entity_type": None,
            "authority": _AUTHORITY_GENERATED,
            "template_family": template_family,
            "generated_evidence": evidence,
            "evidence_agreement": agreement,
            "reason": (f"statement evidence ({agreement}) positively evidences the "
                       f"{template_family} template; sufficient to withhold corporate "
                       "models, not sufficient to name the issuer's institution type"),
        }
    return {
        "ticker": str(ticker).upper(),
        "issuer_entity_type": None,
        "authority": _AUTHORITY_UNKNOWN,
        "template_family": None,
        "generated_evidence": evidence,
        "evidence_agreement": agreement,
        "reason": ("no manually verified profile and no positive specialized-financial "
                   "evidence; an absent archetype is never read as corporate"),
    }


def metric_applicability(archetype: Mapping[str, Any], metric: str) -> dict[str, Any]:
    """Whether `metric` is defined for this issuer at all, before asking about inputs.

    `not_applicable` means the metric has no meaning for this filer and no input will ever
    make it computable. `insufficient_evidence` means we do not yet know which it is --
    never a silent `applicable`.
    """
    entity_type = str(archetype.get("issuer_entity_type") or "").strip().lower() or None
    template_family = archetype.get("template_family")
    authority = archetype.get("authority")

    if metric not in CORPORATE_ONLY_METRICS:
        return {"metric": metric, "status": _STATUS_APPLICABLE, "authority": authority,
                "reason": f"{metric} is not restricted to the corporate earnings model",
                "substitute_metrics": []}

    if entity_type in FINANCIAL_ENTITY_TYPES:
        family = template_family if template_family in SUBSTITUTE_METRICS else None
        return {
            "metric": metric, "status": _STATUS_NOT_APPLICABLE, "authority": authority or _AUTHORITY_MANUAL,
            "reason": (f"issuer_entity_type={entity_type!r} is a financial filer; {metric} is "
                       "not defined for it and no input can make it computable"),
            "substitute_metrics": list(SUBSTITUTE_METRICS.get(family or "", ("p_b", "roe"))),
        }
    if entity_type in CORPORATE_ENTITY_TYPES:
        return {"metric": metric, "status": _STATUS_APPLICABLE, "authority": authority or _AUTHORITY_MANUAL,
                "reason": (f"issuer_entity_type={entity_type!r}; {metric} is defined and its "
                           "availability depends only on qualified inputs"),
                "substitute_metrics": []}
    if template_family:
        return {
            "metric": metric, "status": _STATUS_NOT_APPLICABLE, "authority": _AUTHORITY_GENERATED,
            "reason": (f"statement evidence evidences the {template_family} template; {metric} "
                       "is not defined for a specialized financial filer"),
            "substitute_metrics": list(SUBSTITUTE_METRICS.get(str(template_family), ("p_b", "roe"))),
        }
    if entity_type:
        return {"metric": metric, "status": _STATUS_INSUFFICIENT, "authority": _AUTHORITY_MANUAL,
                "reason": (f"issuer_entity_type={entity_type!r} is outside the known corporate "
                           "and financial vocabularies; applicability is undetermined"),
                "substitute_metrics": []}
    return {"metric": metric, "status": _STATUS_INSUFFICIENT, "authority": _AUTHORITY_UNKNOWN,
            "reason": ("issuer archetype unresolved; a corporate model is never granted by "
                       "default, so applicability stays undetermined"),
            "substitute_metrics": []}


def evaluate_ticker(ticker: str, *, manual_entity_type: Any = None,
                    balance_sheet_taxonomy: Any = None,
                    income_statement_item_ids: Iterable[str] | None = None,
                    metrics: Iterable[str] = CORPORATE_ONLY_METRICS) -> dict[str, Any]:
    """Full archetype + applicability verdict for one ticker."""
    income = (classify_income_statement(income_statement_item_ids)
              if income_statement_item_ids is not None
              else {"template_family": None, "matched_markers": {},
                    "reason": "no income-statement payload retained for this ticker"})
    archetype = resolve_archetype(
        ticker,
        manual_entity_type=manual_entity_type,
        balance_sheet_taxonomy=balance_sheet_taxonomy,
        income_statement_family=income["template_family"],
    )
    archetype["income_statement_evidence"] = income
    return {
        "ticker": str(ticker).upper(),
        "classifier_version": VERSION,
        "archetype": archetype,
        "metric_applicability": {metric: metric_applicability(archetype, metric)
                                 for metric in metrics},
    }
