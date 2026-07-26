# Semantic Evidence Bridge Contract

`semantic_evidence_bridge.py` is the single reader that links
`data/official-evidence/manifest.json` and `qualification_citations.jsonl`
(both runtime data, outside source Git) to canonical records produced by
`financial_observations.canonical_records`. It contains no ticker-specific
logic; scope is entirely a property of the citation data, which today holds
exactly the 19 HPG/annual/2024 citations from the bounded evidence bridge and
its core-observation-expansion follow-up (9 cash-flow/debt/income items plus
10 revenue/profit/assets/equity/liquidity items, all exact-matched against the
same audited consolidated FY2024 statement).

`load_verified_citations` fails closed per record: a missing manifest or
citations file yields `status: "unavailable"` with an empty result (legacy,
pre-citation behavior). A present file still fails closed, per citation, on
evidence hash mismatch, non-deterministic citation ID, unsupported
`statement_scope` (only `consolidated` is recognized), an `observation_id`
absent from the current `observations.jsonl`, an identity/value mismatch
against that observation, or two differing citations for the same
`observation_id`. `observations.jsonl` is only ever read, never written.

Value verification is signed, never by absolute value. Absent an explicit,
cited, versioned entry in `_SIGN_RULES`, a citation must match the raw value
exactly. The only current entry is `("income_statement", "interest_expenses")`
v1: the consolidated statement (form B02-DN/HN) prints the interest-expense
breakdown unsigned, while VCI stores it negative.

`enrich_canonical_records` returns a new by-ticker structure; inputs and
`observations.jsonl` are never mutated. A direct record is upgraded
(`statement_scope`/`currency`/`unit_scale`/`quality_state`, plus an additive
`evidence` block) only when its single backing observation has a verified
citation. A derived record (e.g. `total_interest_bearing_debt`,
`shareholders_equity`) is upgraded only when every required component (per
`_DERIVED_COMPONENTS`, mirroring `cash_flow_debt_mapping.py`'s own
`_derive_total_debt`/`_derive_shareholders_equity`) is itself upgraded with
mutually compatible scope/currency/scale; its `observation_ids` and `evidence`
then list every component. Records with no verified citation pass through
unchanged.

`reconcile_metric_identities` runs after enrichment and exposes an
already-qualified record under the name a downstream contract expects, via
the centralized, versioned `_METRIC_IDENTITY_MAP` -- never a bare string
alias, and never for a record without a verified `evidence` block (an
unresolved identity leaves the downstream input unavailable rather than being
aliased into existence). Two entries exist today: `total_interest_bearing_debt`
-> `total_debt` (fundamental_quality/intrinsic_valuation/relative_valuation
all use `total_debt` as an enterprise-value/net-debt input -- interest-bearing
borrowings, not total liabilities) and `net_income_attributable_to_parent` ->
`net_income` (their ratios pair `net_income` with parent-only
`shareholders_equity`/EPS, so by convention it excludes non-controlling
interest). `net_profit_after_tax_total` (the consolidated total including
non-controlling interest) is deliberately never reconciled to `net_income` --
it is a genuinely different figure, kept separate. The original,
precisely-named record is always retained alongside its reconciled copy, so a
name collision with a pre-existing record of the same target name never
deletes or silently overwrites either fact.

Downstream callers must still resolve their own cross-metric period
consistency: this module guarantees each individual record's scope, only a
caller like `fundamental_quality.py`'s `_latest_common_period` or
`export_ai_bundle.py`'s `_financial_input` decides which period wins when two
"available" records compete for the same canonical name (e.g. this bridge's
FY2024 citation vs. `official_evidence.py`'s FY2025 narrative bridge).
