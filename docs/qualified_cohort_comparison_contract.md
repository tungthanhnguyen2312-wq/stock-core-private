# Qualified cohort comparison contract

`qualified_cohort_comparison.py` is a pure Producer projection over the five-ticker qualified
historical cohort: HPG, VNM, PAN, PVD and NVL. It consumes only the existing historical
fundamental analytics and their provenance; it does not calculate a financial ratio, acquire
evidence, fetch market data, convert currency, or rank an investment.

It makes cross-sectional historical context explicit while keeping `multi_period_trend` at
`insufficient_history` until compatible qualified annual history exists. Each row carries
states, dimensionless ratios, conclusions, risk/strength predicates, sub-conclusions, and
source fact identities. Net-debt funding is rendered as a position only; absolute monetary
amounts never enter cross-company output. PVD remains USD.

The only relative position codes are descriptive observations over this fixed cohort (for
example, lowest observed debt/equity). They are not scores, peer claims, or recommendations.
The Consumer passes this section through verbatim; the Dashboard may render it but must never
recompute a metric or imply valuation, liquidity, return, ranking, sizing, or allocation.
