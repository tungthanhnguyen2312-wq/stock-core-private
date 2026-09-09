# Portfolio-Aware Decision And Risk Sizing V1 — Contract

`PORTFOLIO_AWARE_DECISION_AND_RISK_SIZING_V1`. Implemented in `portfolio_aware_decision.py`
(`CONTRACT_VERSION = "portfolio_aware_decision/v1"`, with two nested, independently identified
sub-contracts: `portfolio_risk_sizing/v1` and `margin_economics/v1`). Turns the existing objective
Integrated Investment Decision into a private, personalized portfolio decision layer:

```
Market Decision x Private Portfolio State x Risk Policy
    -> Portfolio-Aware Action + Risk Quantity Ceiling + Funding/Margin Context
```

## Why this module, not another engine

`integrated_investment_decision_product.py` already owns security attractiveness
(`research_action_posture`, `trigger`, `invalidation`, evidence axes, thesis/counter-thesis).
This module never recomputes any of that; it consumes the finished per-ticker record and joins
it against portfolio state and policy. Guiding Principle 5 of that module ("security
attractiveness kept strictly separate from portfolio fit") is preserved: this module's output
never mutates `research_action_posture`, and a security-level `AVOID`/`REDUCE` never becomes a
portfolio-level sell instruction.

`current_portfolio_risk_envelope.py` remains the standing public, explicit-portfolio
concentration/risk boundary and is not duplicated: it already reports
`position_sizing_status: "BLOCKED"` and `blocked_risk_dimensions` for VaR/CVaR/leverage/execution
because exact liquidity/PIT/policy authority is not established anywhere in this repository. This
module reuses that exact boundary rather than building a second risk engine:
`execution_qualified_quantity` stays unconditionally `NOT_QUALIFIED` here too.

`private_portfolio_context.py` (Foundation) is consumed read-only: this module never re-parses
the owner workbook and never writes to the ledger/snapshot/policy/manifest directories
`import_workbook()` owns. Its own generated output reuses the same approved private root under a
`portfolio_aware_decisions\` subdirectory — never `operations-review/`, Git, the Dashboard, or the
AI-handoff repository.

## Owner profile: CORE_LONG_TERM_WITH_TACTICAL_OVERLAY

A long-term core position and an unrelated tactical opportunity are not in conflict. Existing
exposure above a policy cap means `OVER_LIMIT_REVIEW` (no new addition by default), **never** an
automatic sell — the underlying `research_action_posture` is preserved untouched, so a valid
signal stays visibly valid (e.g. `SIGNAL_VALID_BUT_NO_ADD`-equivalent via
`OVER_LIMIT_REVIEW`/`NO_ADD` + the unchanged security posture) rather than being rewritten into a
fabricated bearish thesis. Cost basis and lifetime cash-recovery breakeven
(`cost_basis_context`, read straight from the private snapshot's own already-computed fields) are
surfaced as **context only** — no constraint, sizing, or eligibility computation in this module
reads them; `authority_boundary.cost_basis_and_breakeven_are_context_only_never_a_market_trigger`
documents this on every record.

## Architecture

```
PRIVATE PORTFOLIO STATE (private_portfolio_context.portfolio_snapshot/v1, read-only;
  embeds account_snapshot/v1 + effective portfolio_policy/v1, itself owner-override ->
  SYSTEM_DEFAULT_POLICY_V2 per field)
        +
CURRENT SECURITY DECISION (integrated_investment_decision_product per-ticker record:
  research_action_posture, trigger, invalidation, evidence_axes, thesis)
        +
CURRENT MARKET CONTEXT (best-effort retained descriptive-research close prices, optional
  governed sector snapshot -- read-only, never fetched)
        v
derive_portfolio_state()  ->  portfolio_state/v1
        v
build_ticker_portfolio_aware_decision()  ->  portfolio_aware_decision/v1 record
  (nests portfolio_risk_sizing/v1 and margin_economics/v1)
```

## Sizing modes: FULL vs PROBE

* `FULL_RISK_BUDGET` — the security decision's own posture is `INITIATE_ON_BREAKOUT` or
  `ACCUMULATE_ON_RETEST` (trigger already fired, or a bullish retest is confirmed). Uses the full
  `risk_budget_per_investment_decision_to_nav`.
* `PROBE_RISK_BUDGET` — the posture is `EARLY_WATCH`: the existing, already-governed product's own
  early-entry/monitoring state (early bullish structural reversal / base compression, *before* any
  breakout trigger), **and** that same product already supplies a deterministic invalidation level
  and a proposed entry/trigger reference (`_probe_eligible`). Uses `probe_risk_budget_multiplier`
  (default `0.50`) times the normal risk budget. A probe is never manufactured from oversold status
  or subjective judgment — it is a pure, deterministic read of two already-existing fields.
* `NOT_APPLICABLE` — everything else (`HOLD`, `AVOID`, `WAIT_FOR_CONFIRMATION`,
  `INSUFFICIENT_CURRENT_RESEARCH`, excluded/held-above-cap positions).

Both modes go through the *same* concentration, cash-reserve, gross-exposure, and risk-budget
gates (`_decide_portfolio_action_research`); a probe is never exempted from any of them. The
resulting `portfolio_action_research` value is symmetric per mode:
`ADD_WITHIN_RISK_CEILING` / `ADD_WITHIN_EVALUATED_CONSTRAINTS` / `ADD_ELIGIBLE_SIZING_UNAVAILABLE`
for `FULL_RISK_BUDGET`, and the `PROBE_*` equivalents for `PROBE_RISK_BUDGET`. Both modes share the
single negative bucket `NO_ADD` (with `binding_constraint` explaining why) rather than doubling the
taxonomy for a blocked outcome.

## Risk quantity ceiling (`portfolio_risk_sizing/v1`)

`portfolio_risk_quantity_ceiling` is the deterministic minimum of every *qualified* ceiling:

* **risk-budget ceiling** — `(effective_nav * risk_budget_fraction) / per_share_downside`, where
  `per_share_downside = |entry_reference_price - invalidation_level|` (never zero-substituted: a
  missing invalidation or entry price returns an explicit `UNAVAILABLE_*` sizing status, never a
  silent zero ceiling);
* **single-position ceiling** — remaining notional room to `max_single_position_weight`;
* **sector ceiling** — remaining notional room to `max_sector_weight`, only when a sector is
  actually resolved (`resolve_sector_by_ticker`: explicit caller input, then an already-loaded
  `exchange_industry_classification` snapshot, else the honest `NOT_EVALUATED_MISSING_SECTOR` —
  never `UNCONSTRAINED`, and never silently narrows the ceiling);
* **gross-exposure ceiling** — remaining notional room to `max_gross_exposure_to_nav`;
* **cash-funded ceiling** — deployable cash (`cash_available - minimum_cash_reserve_to_nav * NAV`)
  divided by the entry price, reported separately in `cash_funding_capacity` (not blended into the
  risk ceiling — it is a funding-source check, not a risk check).

`portfolio_constraint_completeness` (`FULL` / `PARTIAL` / `INSUFFICIENT` / `NOT_APPLICABLE`) and
`constraints_evaluated` / `constraints_not_evaluated` record exactly which of the five gating
constraints actually cleared vs. were never evaluated, so a sector-unevaluated add is reported as
`*_WITHIN_EVALUATED_CONSTRAINTS`, never conflated with a fully-qualified `*_WITHIN_RISK_CEILING`.

`execution_qualified_quantity` is always `None` / `NOT_QUALIFIED`: given the project's current
authority, exact liquidity/execution inputs are unqualified, so the risk ceiling never silently
promotes to an execution instruction, matching `current_portfolio_risk_envelope/v1`'s own boundary.

## Margin economics (`margin_economics/v1`, tactical trades only)

Produced only when `sizing_mode` is `FULL_RISK_BUDGET` or `PROBE_RISK_BUDGET` (a genuine new
tactical decision sleeve this session); otherwise `status: "NOT_APPLICABLE"`.

Factual account inputs are preserved separately and never blended: `current_margin_debt`,
`margin_available_minimum`, `margin_available_maximum`, `annual_margin_rate_percent`
(`margin_account_context`; `13.5` means 13.5% p.a., never re-scaled).

Given `entry_price`, `invalidation_price` (`downside_per_share`), an optional caller-supplied
`reward_boundary` (deterministic tactical upside/target — **nothing upstream in this repository
emits one today**; no target price is ever fabricated anywhere in this codebase, confirmed by
`security_decision_context.py`'s own `no_target_price: True` invariant and
`current_valuation_opportunity_integration.py`'s `target_price: "NOT_EMITTED"`), and the policy
defaults below:

```
financing_cost_per_share  = entry_price * (annual_margin_rate_percent / 100) * (tactical_margin_holding_days / 365)
gross_upside_per_share    = reward_boundary - entry_price
financing_adjusted_upside = gross_upside_per_share - financing_cost_per_share
net_reward_risk           = financing_adjusted_upside / downside_per_share
financing_cost_fraction   = financing_cost_per_share / gross_upside_per_share
```

`status` has three layers, never conflated:

* `NOT_APPLICABLE` — not a tactical decision sleeve this session.
* `NOT_EVALUATED` — it is, but a required input is missing (no reward/upside basis, no rate basis,
  degenerate/negative downside, or the policy defaults themselves are unavailable). **This is the
  realistic outcome for every real record today**, since no qualified reward boundary exists
  upstream — margin selection is honestly `NOT_EVALUATED` rather than inventing a target or a
  probability.
* `EVALUATED` — the full calculation ran; `margin_research_band` carries the result:
  * `financing_cost_fraction > max_financing_cost_fraction_of_gross_upside` (default `0.20`) ->
    `NO_MARGIN` (`FINANCING_COST_EXCEEDS_POLICY_MAX_FRACTION_OF_GROSS_UPSIDE`) — a formerly
    attractive trade can become ineligible purely on financing drag, independent of the R/R gate;
  * `net_reward_risk < min_net_reward_risk_for_margin` (default `2.0`) -> `NO_MARGIN`
    (`BELOW_MIN_NET_REWARD_RISK_ECONOMICS`), capacity `0`;
  * `net_reward_risk >= strong_net_reward_risk_for_max_margin` (default `3.0`) -> `MAX_BAND`,
    capacity = factual `margin_available_maximum`;
  * otherwise -> `INTERPOLATED_MIN_TO_MAX`, capacity linearly interpolated between factual
    `margin_available_minimum` (at exactly `2.0`) and `margin_available_maximum` (approaching
    `3.0`) — the MIN band described in the program brief is this interpolation's own `2.0` edge,
    not a fourth separate band.

`research_capacity.final_margin_research_capacity_quantity` then caps that notional capacity again
by single-position, sector, gross-exposure, and max-margin-debt-to-NAV remaining room, **and by the
risk-budget ceiling itself** — a research funding ceiling never exceeds the risk ceiling it would
fund. This is a research funding ceiling only (`authority_boundary.
research_funding_ceiling_not_execution_instruction`), never an execution instruction, and the
system never permanently chooses MIN or MAX by policy.

## Versioned system policy defaults (owner-overridable)

Added additively to `private_portfolio_context.py`'s existing `portfolio_policy/v1` field set
(same owner-workbook-override -> system-default resolution every other policy field already uses).
Adding fields required bumping `SYSTEM_DEFAULT_POLICY_VERSION` from `SYSTEM_DEFAULT_POLICY_V1` to
`SYSTEM_DEFAULT_POLICY_V2` — `_import_layout()` folds that version string into its own identity, so
an already-materialized immutable `portfolio_snapshot_v1.json` at a V1 layout directory is never
silently mutated to carry five new fields under an unchanged version string; a fresh
`import_workbook()` re-run against the same, unchanged real workbook lands in a new, additional V2
layout directory instead, alongside (not replacing) the frozen V1 one.

| field | default |
|---|---|
| `probe_risk_budget_multiplier` | `0.50` |
| `tactical_margin_holding_days` | `30` |
| `min_net_reward_risk_for_margin` | `2.0` |
| `strong_net_reward_risk_for_max_margin` | `3.0` |
| `max_financing_cost_fraction_of_gross_upside` | `0.20` |

## Owner-excluded positions

`excluded_tickers` marks a position `is_active: False` / `EXCLUDED_INACTIVE`. Excluded positions
are never counted in sector or gross-exposure weights and their `portfolio_action_research` is
unconditionally `EXCLUDED_FROM_ACTIVE_PORTFOLIO` — they participate only as a read-only, clearly
labelled row, never in active exposure/action output.

## CLI

`.\stocklookup.ps1 portfolio evaluate [--session YYYY-MM-DD] [--sector-snapshot PATH]
[--exclude TICKER ...] [--portfolio-root PATH]`. Read-only: no Daily run, no provider call, no
workbook re-parse. Defaults to the latest retained completed session with a materialized
Integrated Decision artifact (`operations-review/canonical-post-close-v1/<date>/enrichment/
integrated_investment_decision_product.json`, lexicographically latest dated directory — the same
idiom `daily_session_level2_package._latest_official_event_context_dir` already uses). The full
record set is written only under the private portfolio root
(`%USERPROFILE%\.stocklookup\portfolio\portfolio_aware_decisions\<session>\
portfolio_aware_decision_v1.json`); **console output is identities, counts, statuses, and
reason-code counts only** (`public_console_summary`) — never holdings, quantities, prices, NAV,
cash, or margin balances.

## Private output contract

`portfolio_aware_decision_v1` (per-ticker records nesting `portfolio_risk_sizing/v1` and
`margin_economics/v1`) retains, per ticker: the source Integrated Decision identity
(`evidence_lineage.security_decision_identity`), the portfolio snapshot/policy identities
(`evidence_lineage.portfolio_state_identity`), existing exposure context (`current_quantity`,
`current_weight`, `cost_basis_context`, `existing_position_lane_context`), the unchanged market
decision (`security_research_action_posture`, `trigger`, `invalidation`), the personalized
disposition (`portfolio_action_research`, `sizing_mode`), every applicable ceiling and calculation
trace (`portfolio_risk_sizing`, the five `*_constraint` objects), the margin research band/status
(`margin_economics`), blockers/reason codes (`binding_constraint`,
`portfolio_constraint_completeness`), `execution_qualified_quantity`, and a deterministic
`portfolio_decision_identity`.
