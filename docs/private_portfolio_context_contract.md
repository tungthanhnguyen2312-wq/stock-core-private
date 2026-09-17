# Private Portfolio Context Foundation V1

`private_portfolio_context.py` imports an owner-maintained workbook only from
the local private root `%USERPROFILE%\.stocklookup\portfolio\`. It is not a
Daily input, provider, Dashboard feed, AI-handoff input, or portfolio sizing
engine. The existing `current_portfolio_risk_envelope/v1` remains the separate
explicit-exposure research contract.

## Owner commands

```powershell
.\stocklookup.ps1 portfolio import
.\stocklookup.ps1 portfolio status
```

The default workbook is `%USERPROFILE%\.stocklookup\portfolio\portfolio_input.xlsx`.
`portfolio import` reads it once in the foreground and writes private,
content-addressed artifacts under:

```text
%USERPROFILE%\.stocklookup\portfolio\imports\<workbook-sha256>\<import-layout-sha256>\
```

The source workbook, its values, and those local artifacts must never be copied
into the repository, test fixtures, operation reports, logs, or Git history.
`PORTFOLIO_CONTEXT_IMPORT_LAYOUT_V2` is itself content-addressed below the
workbook SHA. It lets this corrective write a new immutable revision beside a
prior layout for the same workbook instead of overwriting or repairing old
private artifacts.

## Workbook surfaces

The importer preserves the workbook as the human input surface. It reads the
existing `Trade`, `Dividend`, `Money`, `margin`, and `Total` sheets without
modifying them. `Total` is a non-authoritative reconciliation/view hint only;
it can produce a warning but can never overwrite derived quantities.

The following optional sheets use either a one-row field header table or a
two-column `field`/`value` table:

### `AccountSnapshot`

| Field | Meaning |
| --- | --- |
| `as_of_date` | Owner snapshot date (`YYYY-MM-DD`). |
| `currency` | Account currency. |
| `cash_available` | Available cash; omitted is unknown, never zero-filled. |
| `cash_reserved` | Reserved/settlement cash; optional. |
| `margin_debt` | Current outstanding margin principal; omitted is unknown and is never inferred from margin availability. |
| `margin_available_minimum` | Broker-reported minimum available margin; optional VND field, retained distinctly from debt. |
| `margin_available_maximum` | Broker-reported maximum available margin; optional VND field, retained distinctly from debt. |
| `annual_margin_rate_percent` | Annual margin rate as a percentage number: `13.5` means `13.5%` per annum, not `0.135%`. |
| `accrued_margin_interest` | Accrued account margin interest; optional. |
| `net_asset_value` | Broker-reported NAV; optional but required for later NAV-based policy checks. |
| `gross_market_value` | Broker-reported gross marked market value; optional. |

All cash, debt, availability, interest, NAV, and marked-value fields above are
VND by field contract even when Excel labels a cell `General` or applies no
currency format. The importer never infers or rescales a unit from numerical
magnitude or cell formatting.

Where the existing `margin` sheet already exposes clearly labelled account
fields, the importer reuses them as a legacy account source; a separate
`AccountSnapshot` duplicate is not required. A dedicated `AccountSnapshot`
field wins only on an explicit conflict, which is retained as a warning.

### `PortfolioPolicy`

`PortfolioPolicy` is optional. An owner value overrides the system default for
that field only. `portfolio_policy_v1` retains the raw owner value, effective
value, system candidate, unit, and per-field provenance. Defaults are a risk
boundary for a future consumer, not an instruction to sell an existing position
above a cap.

| Field | Meaning |
| --- | --- |
| `risk_budget_per_investment_decision_to_nav` | Risk budget for one investment decision divided by NAV. |
| `max_single_position_weight` | Maximum single-name weight. |
| `max_gross_exposure_to_nav` | Maximum gross exposure divided by NAV. |
| `max_margin_debt_to_nav` | Maximum margin debt divided by NAV. |
| `max_sector_weight` | Maximum sector weight where a future governed sector map is available. |
| `minimum_cash_reserve_to_nav` | Minimum cash reserve divided by NAV. |
| `max_margin_rate_percent_for_new_leveraged_exposure` | Annual rate ceiling for new leveraged exposure, expressed as a percentage number. |
| `max_ticker_financing_cost` | Maximum ticker-attributed financing cost. |
| `max_account_margin_cost` | Maximum account-level/unallocated margin cost. |

`SYSTEM_DEFAULT_POLICY_V1` supplies only an absent field with these deterministic
values: risk budget `0.01` NAV, maximum single position `0.30` NAV, maximum
sector `0.45` NAV, maximum gross exposure `1.15` NAV, maximum margin debt
`0.15` NAV, minimum cash reserve `0.05` NAV, and maximum new-leverage margin
rate `15.0` percent per annum. Other optional policy fields remain unavailable
unless the owner supplied them.

## Multi-account context (`PRIVATE_MULTI_BROKER_INVESTMENT_ACCOUNT_CONTEXT_V1`)

`AccountSnapshot` may hold more than one row -- each becomes one candidate
brokerage account instead of only the sheet's first row. Three additional
identity columns are recognized on that same sheet, additive to the
single-account fields above:

| Field | Meaning |
| --- | --- |
| `account_alias` | Owner-chosen stable identifier for this account (can be a real account number -- it never leaves this local root; see "Privacy" below). Required to disambiguate more than one row. |
| `broker` | Broker/company name, e.g. `SSI`. Optional. |
| `account_type` | Owner-defined account kind, e.g. `CASH`, `MARGIN`. Optional. |

A single alias-less row (every pre-existing legacy workbook) still imports as
exactly one account, `LEGACY_UNSPECIFIED_ACCOUNT`. More than one alias-less
row is genuinely ambiguous and is never guessed: each gets its own
row-qualified identity plus an `ACCOUNT_ALIAS_MISSING_FOR_MULTI_ACCOUNT_ROW`
reconciliation warning instead.

Example (no real owner values):

```text
as_of        account_alias   broker      cash_investable   margin_debt   broker_nav
2026-06-30   MAIN-CASH       BROKER_A    120000000         0             150000000
2026-06-30   MAIN-MARGIN     BROKER_B    30000000          10000000      95000000
```

Each row materializes an `investment_account_context/v1` record. A
deterministic `investment_accounts_portfolio_context/v1` aggregate sums
`total_broker_cash`, `total_reserved_cash`, `total_receivables`,
`total_margin_debt`, `total_broker_reported_nav`, and
`total_broker_reported_securities_market_value` -- but only across accounts
whose `as_of_date` and `currency` agree, and only for a field every such
account actually reports; otherwise that total (or the whole aggregate) is
`None`/`PARTIAL_MULTI_ACCOUNT_MISMATCH`, never a manufactured or partially
summed figure.

`Trade`, `Dividend`, and `Money` rows may also carry their own per-row account
column (`Tai khoan` / `So tai khoan` / `Account`). When present, it tags that
event's `source_account_id` and rolls up into each position's additive
`account_attribution` list (one row per account actually seen, plus an
`ACCOUNT_ATTRIBUTION_UNRESOLVED` bucket for events with no such column) --
this is a separate identifier namespace from `AccountSnapshot`'s own
`account_alias` and the two are never cross-referenced except by exact string
match. `account_attribution` is purely additive lineage; it never changes
`current_position_status`/`current_quantity`, which remain the sole
current-holding authority.

**Privacy:** `investment_account_context/v1` and its aggregate stay under the
same local-only root as everything else in this module. The one place a raw
`account_alias` must never appear is the external-upload-facing
`private_portfolio_research_handoff/v1` artifact, which instead anonymizes
each account to an ordinal `ACCOUNT_1`, `ACCOUNT_2`, ... label.

## Local artifacts

- `portfolio_event_ledger_v1.json` retains normalized trade, dividend, money,
  and financing events. `Money` and `margin` monetary fields carry explicit
  VND-by-field-identity semantics without number-format or magnitude inference.
- `portfolio_snapshot_v1.json` derives positions, weighted-average carrying
  cost, purchase/sale cashflows, first/last acquisition dates, current episode
  start and holding days, realized P&L when reconciliation permits, and unavailable unrealized
  P&L when no owner mark is supplied.
- `portfolio_policy_v1.json` retains owner-supplied and effective fields with
  source/default provenance; it is content-addressed even when the owner sheet
  is absent.
- `system_default_policy_v1.json` records the exact versioned defaults used for
  absent policy fields.
- `portfolio_import_manifest_v1.json` binds all private artifact identities to
  the source workbook SHA-256.
- `investment_accounts_v1.json` and `investment_accounts_portfolio_context_v1.json`
  hold the per-account and aggregate multi-broker context described above.

The current-position method is explicitly
`WEIGHTED_AVERAGE_CARRYING_COST`. Cash dividends and net sale proceeds affect
`LIFETIME_NET_CASH_OUTFLOW_PER_CURRENT_SHARE`, but never silently rewrite the
current carrying cost. Ticker-attributed financing is kept separate from
`ACCOUNT_MARGIN_COST`, which remains account-level and unallocated. The
foundation deliberately does not classify whether a purchase was at a market
top or bottom; retained events leave that work for a later governed
market-context contract.
