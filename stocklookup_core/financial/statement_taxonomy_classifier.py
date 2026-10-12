"""Observe which financial-statement reporting taxonomy a filing uses -- nothing more.

This module deliberately does NOT determine `issuer_entity_type`. Those are two different
facts and conflating them is a fail-open route:

    statement_taxonomy   -- which Circular template the filing's item vocabulary belongs to.
                            Directly observable from the retained payload.
    issuer_entity_type   -- what kind of institution the issuer is. Authoritative source
                            remains `config/ticker_entity_profiles.csv` (hand-curated).
    model_applicability  -- whether a given model may run for that issuer. Needs the entity
                            type AND, for Altman Z', an industry qualification. See
                            `altman_applicability.py`.

An earlier version of this file claimed to output `entity_type` directly. Validating it
against the 15 hand-curated profiles caught a real false positive (SSI, a securities
broker, read as corporate because the broker template also carries current_assets /
current_liabilities / short_term_borrowings). Adding a client-asset exclusion fixed that
sample, but the episode is the point: statement vocabulary evidences the *form filed*, and
a form is not an institution. A fund manager, a holding company with financial operations,
an issuer migrating templates, a payload missing markers, or a provider renaming item_ids
can all break the vocabulary-to-institution leap while leaving the vocabulary-to-template
observation intact.

Taxonomy values, all directly evidenced by markers:
    corporate_vas                   -- corporate template (200/2014 or 202/2014/TT-BTC)
    credit_institution              -- credit-institution template (49/2014/TT-NHNN),
                                       asserted only on exclusive deposit-taking/SBV/
                                       interbank markers. Covers banks AND finance
                                       companies; the template cannot separate them.
    securities_company              -- broker template carrying client-asset/settlement lines
    financial_specialized_ambiguous -- specialized-financial vocabulary that does not
                                       exclusively evidence any one template. Insurance
                                       lands here: no exclusive insurance marker set has
                                       been validated, so it is never named.
    unknown                         -- insufficient marker evidence

15 hand-curated profiles are enough to catch a gross error, and did. They are NOT enough
to establish production accuracy over ~1,400 tickers, and this module's output must stay a
shadow overlay until a materially larger validation set exists.
"""
from __future__ import annotations

from typing import Any, Iterable

VERSION = "2.0.0"

TAXONOMIES = ("corporate_vas", "credit_institution", "securities_company",
              "financial_specialized_ambiguous", "unknown")

# Structural, template-defining balance-sheet items: they exist because of the form, not
# because of any particular business.
CORPORATE_MARKERS = ("current_assets", "current_liabilities", "short_term_borrowings", "inventories")
# Deposit-taking, central-bank and interbank lines: only an entity filing the
# credit-institution template reports these, so they are exclusive evidence for it.
CREDIT_INSTITUTION_EXCLUSIVE_MARKERS = (
    "deposits_from_customers", "balances_with_the_sbv",
    "placements_with_and_loans_to_other_credit_institutions",
)
# Lending lines are NOT exclusive: an insurer holds loans and advances too. BVH reports
# `loans_and_advances_to_customers` alongside three corporate markers and zero exclusive
# credit-institution markers, and an earlier version labelled it `credit_institution` on
# that single shared line -- a taxonomy claim the evidence did not support. A shared marker
# without an exclusive one now yields `financial_specialized_ambiguous` instead.
CREDIT_INSTITUTION_SHARED_MARKERS = ("loans_and_advances_to_customers",)
CREDIT_INSTITUTION_MARKERS = CREDIT_INSTITUTION_EXCLUSIVE_MARKERS + CREDIT_INSTITUTION_SHARED_MARKERS
# Broker template (210/2014/TT-BTC): these exist only because the filer holds client assets
# and settlement balances. None appears in any of the eight hand-curated corporates.
SECURITIES_MARKERS = (
    "available_for_sale_financial_assets_afs",
    "customerss_deposits_for_securities_trading",
    "collateral_financial_assets",
    "cash_blocked_for_trading_settlements_of_investors",
    "fa_deposited_at_vsd_not_yet_available_for_transaction_freely_traded",
)

MIN_CORPORATE_MARKERS = 3


def classify_statement_taxonomy(item_ids: Iterable[str], *, ticker: str | None = None,
                                 source: str | None = None, reporting_period: str | None = None,
                                 statement_scope: str | None = None) -> dict[str, Any]:
    """Pure. Returns the observed reporting taxonomy plus the evidence for the call.

    Never returns an `entity_type` key -- callers that need one must resolve it through the
    authoritative profile registry, optionally consulting this only as a shadow signal.
    """
    present = {str(item) for item in item_ids}
    corporate_hits = [marker for marker in CORPORATE_MARKERS if marker in present]
    credit_exclusive_hits = [m for m in CREDIT_INSTITUTION_EXCLUSIVE_MARKERS if m in present]
    credit_shared_hits = [m for m in CREDIT_INSTITUTION_SHARED_MARKERS if m in present]
    credit_hits = credit_exclusive_hits + credit_shared_hits
    securities_hits = [marker for marker in SECURITIES_MARKERS if marker in present]

    if credit_exclusive_hits and securities_hits:
        taxonomy = "financial_specialized_ambiguous"
        abstention = "exclusive_markers_from_more_than_one_specialized_financial_template_present"
    elif credit_exclusive_hits:
        taxonomy, abstention = "credit_institution", None
    elif securities_hits:
        taxonomy, abstention = "securities_company", None
    elif credit_shared_hits:
        # Specialized-financial vocabulary without exclusive evidence for any one template.
        # Never resolved to credit_institution, and never to insurance either -- no
        # exclusive insurance marker set has been validated.
        taxonomy = "financial_specialized_ambiguous"
        abstention = ("only non-exclusive financial markers observed "
                      f"({', '.join(credit_shared_hits)}); insufficient to name a specialized template")
    elif len(corporate_hits) >= MIN_CORPORATE_MARKERS:
        taxonomy, abstention = "corporate_vas", None
    else:
        taxonomy = "unknown"
        abstention = (f"fewer than {MIN_CORPORATE_MARKERS} corporate markers and no "
                      "specialized template markers observed")

    return {
        "classifier_version": VERSION,
        "ticker": ticker,
        "source": source,
        "reporting_period": reporting_period,
        "statement_scope": statement_scope,
        "statement_taxonomy": taxonomy,
        "classification_status": "observed" if abstention is None else "abstained",
        "abstention_reason": abstention,
        "marker_hits": {"corporate": len(corporate_hits), "credit_institution": len(credit_hits),
                         "credit_institution_exclusive": len(credit_exclusive_hits),
                         "credit_institution_shared": len(credit_shared_hits),
                         "securities": len(securities_hits)},
        "matched_markers": {"corporate": corporate_hits,
                             "credit_institution_exclusive": credit_exclusive_hits,
                             "credit_institution_shared": credit_shared_hits,
                             "securities": securities_hits},
    }
