# SSI securities-sector semantics pilot (v1.0.0)

Frozen at FY2024 / 2024-12-31. Producer-only and read-only.

## Inventory

The retained `financial-observations/observations.jsonl` store contains no SSI rows. Runtime VCI balance-sheet export has SSI 2024-Q2, Q3, Q4 only; no FY2024 annual observation. KBS income/cash-flow exports currently begin in 2025. Snapshot equity and `shares_period_end` are derived proxies and carry `unit_unknown`; neither has a cited annual share identity. Thus no FY2024 provider observation satisfies annual period, consolidated scope, unit, observation ID, and citation ID simultaneously.

## Gates

The pack accepts only VCI/KBS, annual FY2024, consolidated, cited observations. Monetary metrics require VND; share metrics require shares. It handles: brokerage revenue, margin lending balance, proprietary-trading assets/result, interest income/expense, parent-attributable profit, equity, and two distinct share identities. Every other state uses `ssi_fy2024_qualified_annual_provider_identity_missing`.

Securities entities treat FCFF, Net-Net, EV/EBITDA, EV/Sales, and corporate-debt semantics as inapplicable. No bank or industrial meaning is reused.