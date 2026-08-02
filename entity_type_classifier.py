"""Deterministic entity-archetype classification from a statement's own item vocabulary.

Why this exists: `config/ticker_entity_profiles.csv` is hand-maintained and holds 15 rows,
so `MappingRegistry.entity_type_for()` returns "unknown" for ~98.7% of the universe. Every
entity-scoped mapping rule and derivation then silently no-ops for those tickers --
`retained_earnings` (blocking Altman for ~1,100 tickers), `ebitda`, `sga`, and the
corporate interest-expense derivations all require `entity_type == "corporate"`. That one
15-row file, not any evidence gap, is what has been forcing per-ticker manual work.

The classification is not an inference about the business: a Vietnamese issuer files its
balance sheet under a specific Circular template, and the template determines the item
vocabulary. Presence of `loans_and_advances_to_customers` / `deposits_from_customers` /
`balances_with_the_sbv` means the issuer filed under the credit-institution template
(49/2014/TT-NHNN); presence of `current_assets` / `short_term_borrowings` means the
corporate template (200/2014 or 202/2014/TT-BTC). Reading which form was filed is
observation, not inference.

Deliberately conservative -- it classifies `corporate` and nothing else:

  - `corporate` vs credit institution separates cleanly and with no overlap (validated
    against all 15 hand-curated profiles: the 8 corporates hit corporate markers and zero
    credit-institution markers; the 4 banks and the finance company hit the reverse).
  - `bank` vs `finance_company` is NOT separable this way -- EVF (a finance company) files
    the same credit-institution template as BID/MBB/TCB/VCB and is indistinguishable by
    vocabulary. Asserting one would be a guess.
  - `securities` and `insurance` are not reliably separable either (SSI and BVH both carry
    mostly corporate-template markers).

So anything that is not confidently corporate returns "unknown" and stays hand-curated.
Widening this beyond `corporate` requires its own evidence, not a lowered threshold.
"""
from __future__ import annotations

from typing import Any, Iterable

VERSION = "1.0.0"

# Structural, template-defining balance-sheet items. Chosen because they exist because of
# the form, not because of any particular business: a credit institution's balance sheet
# has no current/non-current split at all, and a corporate one has no SBV balances.
CORPORATE_MARKERS = ("current_assets", "current_liabilities", "short_term_borrowings", "inventories")
CREDIT_INSTITUTION_MARKERS = (
    "loans_and_advances_to_customers", "deposits_from_customers", "balances_with_the_sbv",
    "placements_with_and_loans_to_other_credit_institutions",
)
# A securities company files a broker-specific template (Circular 210/2014/TT-BTC) that
# still carries current_assets / current_liabilities / short_term_borrowings, so the
# corporate markers alone do NOT exclude it -- validating against the hand-curated
# profiles caught exactly that false positive on SSI. These items exist only because the
# filer holds client assets and settlement balances; none appears in any of the eight
# hand-curated corporates' statements.
SECURITIES_MARKERS = (
    "available_for_sale_financial_assets_afs",
    "customerss_deposits_for_securities_trading",
    "collateral_financial_assets",
    "cash_blocked_for_trading_settlements_of_investors",
    "fa_deposited_at_vsd_not_yet_available_for_transaction_freely_traded",
)
# Both thresholds are deliberate: a single shared item name is not enough to assert a
# template, and any credit-institution marker at all disqualifies the corporate call.
MIN_CORPORATE_MARKERS = 3
MAX_CREDIT_INSTITUTION_MARKERS_FOR_CORPORATE = 0


def classify(item_ids: Iterable[str]) -> dict[str, Any]:
    """Pure. Returns {"entity_type", "confidence_basis", "corporate_marker_hits",
    "credit_institution_marker_hits", "matched_markers"}.

    entity_type is "corporate" or "unknown" -- never a guessed subtype.
    """
    present = {str(item) for item in item_ids}
    corporate_hits = [marker for marker in CORPORATE_MARKERS if marker in present]
    credit_hits = [marker for marker in CREDIT_INSTITUTION_MARKERS if marker in present]
    securities_hits = [marker for marker in SECURITIES_MARKERS if marker in present]

    if securities_hits:
        # Broker template: shares the corporate current/non-current split, so it must be
        # excluded explicitly or it is read as corporate. Subtype not asserted here.
        entity_type = "unknown"
        basis = "securities_broker_template_observed_subtype_not_asserted"
    elif (len(corporate_hits) >= MIN_CORPORATE_MARKERS
            and len(credit_hits) <= MAX_CREDIT_INSTITUTION_MARKERS_FOR_CORPORATE):
        entity_type, basis = "corporate", "corporate_statement_template_observed"
    elif credit_hits:
        # Known to be a credit institution, but bank vs finance_company is not decidable
        # from the template -- report why rather than picking one.
        entity_type = "unknown"
        basis = "credit_institution_template_observed_but_bank_vs_finance_company_not_decidable"
    else:
        entity_type, basis = "unknown", "no_template_matched_with_sufficient_markers"

    return {
        "entity_type": entity_type, "confidence_basis": basis,
        "corporate_marker_hits": len(corporate_hits),
        "credit_institution_marker_hits": len(credit_hits),
        "securities_marker_hits": len(securities_hits),
        "matched_markers": {"corporate": corporate_hits, "credit_institution": credit_hits,
                             "securities": securities_hits},
        "classifier_version": VERSION,
    }
