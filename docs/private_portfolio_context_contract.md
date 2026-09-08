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
%USERPROFILE%\.stocklookup\portfolio\imports\<workbook-sha256>\
```

The source workbook, its values, and those local artifacts must never be copied
into the repository, test fixtures, operation reports, logs, or Git history.

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
| `margin_debt` | Outstanding margin principal; omitted is unknown. |
| `accrued_margin_interest` | Accrued account margin interest; optional. |
| `net_asset_value` | Broker-reported NAV; optional but required for later NAV-based policy checks. |
| `gross_market_value` | Broker-reported gross marked market value; optional. |

### `PortfolioPolicy`

`PortfolioPolicy` is optional. If present, maintain `as_of_date`, `currency`,
and only the owner-selected limits below. Omitted limits remain unavailable;
they are never inferred.

| Field | Meaning |
| --- | --- |
| `max_single_position_weight` | Maximum single-name weight. |
| `max_gross_exposure_to_nav` | Maximum gross exposure divided by NAV. |
| `max_margin_debt_to_nav` | Maximum margin debt divided by NAV. |
| `max_sector_weight` | Maximum sector weight where a future governed sector map is available. |
| `max_ticker_financing_cost` | Maximum ticker-attributed financing cost. |
| `max_account_margin_cost` | Maximum account-level/unallocated margin cost. |

## Local artifacts

- `portfolio_event_ledger_v1.json` retains normalized trade, dividend, money,
  and financing events.
- `portfolio_snapshot_v1.json` derives positions, weighted-average carrying
  cost, purchase/sale cashflows, first/last acquisition dates, current episode
  start and holding days, realized P&L when reconciliation permits, and unavailable unrealized
  P&L when no owner mark is supplied.
- `portfolio_policy_v1.json` retains `PortfolioPolicy` as `PROVIDED` or
  `NOT_PROVIDED`; it is content-addressed even when absent.
- `portfolio_import_manifest_v1.json` binds all private artifact identities to
  the source workbook SHA-256.

The current-position method is explicitly
`WEIGHTED_AVERAGE_CARRYING_COST`. Cash dividends and net sale proceeds affect
`LIFETIME_NET_CASH_OUTFLOW_PER_CURRENT_SHARE`, but never silently rewrite the
current carrying cost. Ticker-attributed financing is kept separate from
`ACCOUNT_MARGIN_COST`, which remains account-level and unallocated. The
foundation deliberately does not classify whether a purchase was at a market
top or bottom; retained events leave that work for a later governed
market-context contract.
