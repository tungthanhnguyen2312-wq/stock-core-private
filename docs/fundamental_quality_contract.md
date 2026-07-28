# Fundamental Quality Contract

`fundamental_quality` v1.2.0 consumes only canonical records whose evidence bridge
has qualified value, statement scope, period, currency/scale, observation identity,
and citation lineage. Every model returns direct input classification
(`qualified`, `missing`, `stale`, or `incomparable`), component facts, and the
lineage used. Direct input facts retain their existing payload. A derived input
fact additionally emits deterministic `component_lineage` ordered by component
metric and identity; every component preserves its observation/citation/evidence
identities, derivation role, value, period/frequency, scope, currency, and scale.
Missing, duplicate, conflicting, incomparable, or sector-inapplicable components
make the dependent model unavailable; the Consumer passes these Producer facts
through unchanged and never recomputes them. Null is never zero; negative values remain valid; annual, quarterly,
and TTM records never mix. Numeric output is not a recommendation, target price,
or actionable composite score.

## Corporate activation

For explicitly classified corporate/industrial entities, HPG and VNM may expose
only evidence-backed FY2024 components: growth/profitability, DuPont ROE,
earnings quality, financial strength, and the limited (not nine-point-rescaled)
Piotroski facts. Altman remains inapplicable without a qualified variant; Beneish
remains unavailable until every exact variable is qualified.

## Bank activation

For banks, all corporate cash-flow/debt/Piotroski/Altman/Beneish variants are
sector-inapplicable. `bank_financial_quality` is a component-fact set only: net
interest income, net income, loans/deposits, credit-cost, ROA, and ROE, each
requiring the same FY scope and evidence lineage. It emits no composite score.
VCB may expose it only when loans, deposits, net interest income, provision, total
assets, total equity, and parent net income are all qualified.

## Runtime behavior

The Producer passes the model through `analysis_bundle.json`; the Consumer only
passes through the producer result and never recomputes it. Missing, stale,
incomparable, incompatible-scope, or sector-inapplicable inputs fail closed with
component-level warnings and reasons. No valuation contract changes.
