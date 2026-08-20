# P3-B Fundamental Research Readiness Contract

`fundamental_research_readiness/v1` evaluates only the authoritative Phase-2
multi-period financial panel. It has no runtime, production database, market
price, volume, liquidity, valuation, strategy, or Consumer/Dashboard dependency.

Each metric result contains its identity, exact value when calculable, method,
status, entity class, periods, statement scope, currency, input fact IDs,
evidence lineage, warnings, blocker, and PIT eligibility. Positive calculations
accept only Phase-2 facts that are `QUALIFIED`, positive authority, non-null, and
PIT eligible. A `CONFLICT` fact can never enter a positive calculation.

The explicit metric statuses are `EXACT_QUALIFIED`, `DERIVED_PROXY`, `MISSING`,
`BLOCKED`, `CONFLICT`, and `NOT_APPLICABLE`. Average-balance ROA/ROE is an exact
derivation; ending-balance ROA/ROE is visibly `DERIVED_PROXY`, never equivalent.
No missing value is converted to zero, and all multi-input calculations require
the same period, statement scope, currency, and unit scale.

Corporate debt and cash-flow metrics are corporate-only. Banks expose only
bank-compatible earnings/equity, loan/deposit, and credit-cost calculations.
Securities expose only their own earnings/equity, FVTPL-assets, and margin-loan
identities. Insurance, finance-company, unknown, and unpromoted classes fail
closed. The engine produces separate metric-family states and a `READY`,
`PARTIAL`, or `BLOCKED` fundamental-research readiness record per issuer.

It never produces a quality/composite score, ranking, recommendation, valuation,
target price, DCF, peer multiple, portfolio sizing, backtest, or price/liquidity
readiness verdict.
