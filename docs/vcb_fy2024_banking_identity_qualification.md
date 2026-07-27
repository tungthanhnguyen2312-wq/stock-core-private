# VCB FY2024 Banking Identity Qualification (archetype pilot)

Bounded to VCB, FY2024 consolidated, one purpose: prove the existing
observation/evidence/canonicalization/model-applicability architecture can
represent a commercial bank correctly without forcing non-financial-company
identities onto it. Entity-type-driven throughout (`entity_type == "bank"`,
already assigned to VCB/BID/MBB/TCB in `config/ticker_entity_profiles.csv`)
-- no `ticker == "VCB"` condition anywhere in the source this touches.

## Official evidence

`vcb-consolidated-fy2024-audited-vas.pdf` (`data/official-evidence/`,
sha256 `63498215e56d0d61a6c27c161913395cdbac45a027017b308301b771e27aa104`,
90 pages, unqualified opinion, Ernst & Young Vietnam Limited, ref.
`12163420/E-67794777-HN`, signed 2025-03-28). Sourced from `static2.vietstock.vn`
(a known Vietnamese disclosure mirror), not `vietcombank.com.vn` directly --
the issuer's own domain is unreachable from this environment (browser
policy). No embedded PDF signature was found (unlike VNM's evidence).

**Provenance hardening (post-pilot addendum):** hash equality alone does not
imply official issuer provenance, so this record no longer qualifies on the
default hash-only path. It now declares the generic, versioned
`third_party_mirrored_unsigned_audited_issuer_document_v1` acceptance rule in
`semantic_evidence_bridge.py` (ticker-neutral, applies to any issuer document
sharing this hosting/signature profile): explicit `issuer_hosted: false`,
`source_host_classification: "third_party_mirror"`, and
`embedded_signature_status: "absent"` fields, plus an `evidence_acceptance`
block carrying issuer identity, auditor identity, audit opinion, report date,
reporting scope/period, a self-consistent document hash, an explicit
`provider_exact_match_status: "exact_match"` (content verified page-by-page:
company seal, EY seal and signatures, and printed figures cross-checked
against the independently re-synced provider data, never reconstructed from
the PDF), and a warning that third-party-mirror hosting is weaker than
issuer-hosted evidence. Missing any of these fails the record closed rather
than silently falling back to hash-only trust. See
`docs/semantic_evidence_bridge_contract.md` for the full rule contract.

## Provider recollection

Existing VCB observations were insufficient before this milestone:
`data_bctc/VCB_*_quarter.csv` covered the balance sheet back to 2018 but the
income statement/cash flow only back to 2025-Q3 -- no FY2024 income-statement
figures were retrievable from what was already synced. Ran the existing,
unmodified `bctc_sync.py scrape --tickers VCB --reports balance income
cashflow --period year` (VCB-only, provider-sourced via KBS/VCI through
`vnstock`, writes to `data_bctc/*_year.csv`, never touches `vn_stock.db` or
any evidence/PDF file) to fill the gap. All annual figures used below were
cross-checked against the PDF, not reconstructed from it.

## Banking identities qualified (FY2024, consolidated, VND)

| Canonical metric | Value | Citation |
|---|---|---|
| `interest_income` | 93,654,841,000,000 | B03/TCTD-HN line 1, Note 23, p.9 |
| `interest_expense` | 38,249,106,000,000 | B03/TCTD-HN line 2, Note 24, p.9 (sign rule, see below) |
| `net_interest_income` | 55,405,735,000,000 | B03/TCTD-HN line I, p.9 |
| `net_fee_and_commission_income` | 5,136,561,000,000 | B03/TCTD-HN line II, Note 25, p.9 |
| `net_gain_loss_fx_and_gold` | 5,291,751,000,000 | B03/TCTD-HN line III, Note 26, p.9 |
| `net_gain_loss_trading_securities` | 62,123,000,000 | B03/TCTD-HN line IV, Note 27, p.9 |
| `net_gain_loss_investment_securities` | 3,444,000,000 | B03/TCTD-HN line V, Note 28, p.9 |
| `bank_net_other_income` | 2,371,703,000,000 | B03/TCTD-HN line VI, Note 29, p.9 |
| `income_from_capital_contribution` | 307,179,000,000 | B03/TCTD-HN line VII, Note 30, p.9 |
| `bank_operating_expenses` | 23,027,363,000,000 | B03/TCTD-HN line VIII, Note 31, p.9 (sign rule) |
| `operating_profit_before_credit_provision` | 45,551,133,000,000 | B03/TCTD-HN line IX, p.9 |
| `provision_for_credit_losses` | 3,314,998,000,000 | B03/TCTD-HN line X, Note 32, p.9 (sign rule) |
| `profit_before_tax` | 42,236,135,000,000 | B03/TCTD-HN line XI, p.9 |
| `income_tax_expense` | 8,383,018,000,000 | B03/TCTD-HN line XII, p.10 (sign rule) |
| `net_profit_after_tax_total` | 33,853,117,000,000 | B03/TCTD-HN line XIII, p.10 |
| `net_income_attributable_to_parent` | 33,831,386,000,000 | B03/TCTD-HN line XV, p.10 -- reuses the existing `net_income_attributable_to_parent -> net_income` reconciliation, so P/E's `net_income` input resolves with zero new code |
| `cash_and_precious_metals` | 14,268,064,000,000 | B02/TCTD-HN line I, Note 4, p.6 |
| `balances_with_central_bank` | 49,340,493,000,000 | B02/TCTD-HN line II, Note 5, p.6 |
| `placements_with_other_credit_institutions` | 389,951,898,000,000 | B02/TCTD-HN line III, Note 6, p.6 |
| `customer_loans_gross` | 1,449,198,899,000,000 | B02/TCTD-HN line VI.1, Note 9, p.6 |
| `customer_loans_allowance` | -31,183,175,000,000 | B02/TCTD-HN line VI.2, Note 10, p.6 |
| `customer_loans_net` | 1,418,015,724,000,000 | B02/TCTD-HN line VI, p.6 (VCI reports this net figure directly) |
| `investment_securities_total` | 167,383,349,000,000 | B02/TCTD-HN line VIII, Note 11, p.6 |
| `total_assets` | 2,085,873,522,000,000 | B02/TCTD-HN "TONG TAI SAN CO", p.6 |
| `total_liabilities` | 1,889,664,354,000,000 | B02/TCTD-HN "TONG NO PHAI TRA", p.7 |
| `customer_deposits` | 1,514,664,850,000,000 | B02/TCTD-HN line III, Note 18, p.7 |
| `issued_debt_securities` | 24,125,059,000,000 | B02/TCTD-HN line VI, Note 20, p.7 |
| `total_equity` | 196,209,168,000,000 | B02/TCTD-HN line VIII, Note 22(a), p.7 |
| `minority_interest_equity` | 96,261,000,000 | B02/TCTD-HN line VIII.6, p.7 |
| period-end shares | 5,589,091,262 | Note 22(b), p.56 |
| weighted-average basic shares | 5,589,091,262 | Note 34(b), p.62 |

Not qualified: `funding_from_other_credit_institutions` (raw item id
`deposits_and_loans_from_other_credit_institutions` collides between the
face-of-statement total, 234,533,958,000,000, and a Note 17 sub-component,
223,171,381,000,000 -- same raw item id, different rows; the observation
store's own conflicting-identity rule correctly drops both rather than
guessing which is which). Reported here rather than force-resolved.

## Derived records

- `shareholders_equity` (parent-only) = `total_equity` - `minority_interest_equity`
  = 196,112,907,000,000. Existing `_derive_shareholders_equity` in
  `cash_flow_debt_mapping.py`, unchanged -- only its `_BANK` inputs are new.
  Confirmed against the PDF: NCI is presented as sub-line VIII.6 *within*
  "Von chu so huu", not additive outside it (same convention as HPG).
- `total_operating_income` = `operating_profit_before_credit_provision` +
  `bank_operating_expenses` = 68,578,496,000,000. New derivation
  (`_derive_total_operating_income`), added because the statement's own
  printed subtotal (before opex, before credit provision) is never itself a
  raw scraped row -- reverses the statement's own printed formula
  (I+...+VII-VIII=IX) rather than summing the income lines independently, so
  it can never silently drift from what page 9 actually prints.

## Sign convention (new to this milestone)

VCB's KBS-sourced income statement lines that are printed in parentheses
(subtraction terms in the statement's own running total) are stored by the
provider as plain positive magnitudes -- the same *kind* of mismatch the
existing HPG `interest_expenses` rule handles, just the opposite direction
(there: PDF positive/raw negative; here: PDF negative/raw positive). Four new
entries added to `semantic_evidence_bridge.py`'s `_SIGN_RULES`:
`interest_expense_and_similar_expenses`, `operating_expenses`,
`provision_for_credit_losses`, `corporate_income_tax`. Each independently
documented and covered by `test_vcb_banking_identity_qualification.py`.

## Model applicability

See the final report's applicability matrix. Summary of what changed vs.
what was already correct:
- `fundamental_quality.py`: unchanged. Its existing `entity_type in
  {"corporate","industrial"}` gate already returns `inapplicable` for
  `entity_type=="bank"` across all 7 models -- verified this is the *correct*
  outcome for each (growth_profitability/dupont_roe need a `revenue` identity
  this milestone deliberately does not fabricate for banks; financial_strength
  needs `total_debt`, prohibited; earnings_quality/piotroski's operating-cash-flow
  signal does not carry the same meaning for a bank's loan-driven cash flow).
- `relative_valuation.py`: one-line fix. The EV/Sales, EV/EBITDA gate checked
  `entity_type == "financial"`, a string that does not exist in
  `financial_mapping.ENTITY_TYPES` and so never fired for any real ticker.
  Changed to `entity_type == "bank"`. P/E, P/B, P/S are untouched and now
  correctly become `available` once qualified inputs exist.
- `intrinsic_valuation.py`: new gate. `entity_type` was read but never used;
  added an early return for `entity_type == "bank"` marking `net_net` and
  `fcff_dcf` `inapplicable` (both are ordinary-corporate formulations --
  current_assets/inventory/receivables and operating-cash-flow/CapEx/interest-
  bearing-debt -- that do not describe a bank's balance sheet or funding).
  `entity_type == "corporate"` behavior is byte-for-byte unchanged.
