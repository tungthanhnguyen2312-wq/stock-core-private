# Qualified historical fundamental analytics contract

`qualified_historical_fundamental_analytics.py` is a pure Producer contract for the
corporate cohort HPG, VNM, PAN, PVD and NVL. It accepts only `available`, annual,
consolidated canonical facts with an explicit reporting period, currency, unit scale and
evidence identity. It makes no provider call, database write, market-data lookup or runtime
publication.

For one complete annual fact set it derives earnings and operating-cash-flow states,
OCF/net-income (only when net income is positive), debt/equity, cash/debt, net debt and
net-debt/equity. Zero denominators, missing facts, scope conflicts, unit/currency conflicts
and non-positive-income ratio interpretation fail closed with a status and reason code.
PVD remains USD throughout; no conversion is attempted.

Trend output is `insufficient_history` unless at least two complete qualified annual periods
exist. The descriptive cohort artifact contains states and ratios only: it excludes monetary
amounts, forbids FX conversion, rankings and recommendations, and is not actionable.

The research brief projects the analytics result without recomputing it. It explicitly labels
risks, strengths, conditional bear/base/bull conditions, invalidation conditions and what
cannot yet be concluded. Piotroski, Beneish, DuPont and Altman remain independently gated by
their existing prerequisites; this contract does not activate them.
