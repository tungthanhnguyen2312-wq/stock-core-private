# Cash-flow, Debt and Earnings Item Mapping Qualification

Audit date: 2026-07-26. Read-only `vnstock==4.0.4` probes covered HPG, PAN and
VCB with KBS/VCI `income_statement`, `balance_sheet` and `cash_flow`, annual
and quarterly invocation. VCI annual schemas were stable across the two
corporates; VCB uses a distinct bank schema. KBS balance sheets were empty.

| Canonical metric | VCI exact item code | Scope | Qualification |
|---|---|---|---|
| Operating cash flow | `net_cash_inflows_outflows_from_operating_activities` (corporate); `net_cash_from_operating_activities` (bank) | cash flow | qualified item identity |
| Investing cash flow | `net_cash_inflows_outflows_from_investing_activities` (corporate); `net_cash_from_investing_activities` (bank) | cash flow | qualified item identity |
| Financing cash flow | `net_cash_inflows_outflows_from_financing_activities` | corporate cash flow | qualified item identity; unavailable for observed VCB schema |
| Capital expenditure | `purchases_of_fixed_assets_and_other_long_term_assets` | cash flow | qualified direct item; raw sign preserved; never aggregate CFI |
| Short/long borrowings | `short_term_borrowings`, `long_term_borrowings` | corporate balance sheet | qualified item identity |
| Total interest-bearing debt | compatible short + long borrowings | corporate balance sheet | derived only with both component provenance |
| Interest expense | `interest_expenses` (corporate); `interest_and_similar_expenses` (bank) | income statement | qualified item identity; finance cost excluded |
| Parent-attributable income | `attributable_to_parent_company` | income statement | qualified item identity |
| Cash and equivalents | `cash_and_cash_equivalents` | corporate balance sheet | qualified item identity; unavailable for observed VCB bank balance schema |
| Revenue | `net_sales` | income statement | qualified item identity (net of sales deductions; VCI also exposes gross `sales`, not retained) |
| Total profit after tax (consolidated total, including non-controlling interest) | `net_profit_loss_after_tax` | income statement | qualified item identity; kept distinct from parent-attributable income, never aliased to it |
| Non-controlling interest, income statement | `minority_interests` | income statement | qualified item identity |
| Total assets | `total_assets` | corporate balance sheet | qualified item identity |
| Total liabilities | `liabilities` | corporate balance sheet | qualified item identity |
| Current assets | `current_assets` | corporate balance sheet | qualified item identity |
| Receivables | `accounts_receivable` | corporate balance sheet | qualified item identity (net of doubtful-debt provision; VCI also exposes `trade_accounts_receivable`, not retained) |
| Inventory | `inventories_net` | corporate balance sheet | qualified item identity (net of decline provision) |
| Total equity (including non-controlling interest) | `owners_equity` | corporate balance sheet | qualified item identity |
| Non-controlling interest, balance sheet | `minority_interests` | corporate balance sheet | qualified item identity |
| Shareholders' equity (parent-only) | compatible total equity minus minority interest equity | corporate balance sheet | derived only with both component provenance; VCI never reports the parent-only subtotal directly |

VCI responses do not provide consolidated/separate scope, currency, scale, or
quarterly standalone-versus-cumulative semantics in general. The mapper
records these as `unknown`/`partial` and never subtracts periods. For HPG
FY2024 annual specifically, `semantic_evidence_bridge.py` cross-references
`data/official-evidence/qualification_citations.jsonl` against the audited
consolidated statement to qualify scope/currency/scale by exact citation, and
`reconcile_metric_identities` exposes `total_interest_bearing_debt` and
`net_income_attributable_to_parent` under the `total_debt`/`net_income` names
several downstream contracts expect -- see
`docs/semantic_evidence_bridge_contract.md`. Outside that bounded evidence
set, the general limitation stands: no new records are added to production
canonical financial output until an append-only qualified raw observation is
retained and, where scope/currency/scale matter, cited.
