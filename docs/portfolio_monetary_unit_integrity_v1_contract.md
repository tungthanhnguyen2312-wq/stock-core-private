# Portfolio monetary-unit integrity V1

Milestone `PERSONAL_ACTION_CENTER_QUALIFIED_DECISION_SURFACE_V1`, wave R1
(`PERSONAL_ACTION_CENTER_QUALIFIED_DECISION_SURFACE_V1_R1_MONETARY_INTEGRITY`).
Base: released main `61c870c82648a67eed29d1842f88020e0326c4de`. Contract
`portfolio_monetary_unit_integrity/v1`. Authority effect NONE. Default on once
released: it narrows the private portfolio research path and never widens it.

## Defect

`portfolio_aware_decision.derive_portfolio_state` multiplied the current quantity
by the descriptive close and divided by NAV. The close comes from the same-session
descriptive artifact, whose own `price_basis_qualification.price_unit` is
`UNVERIFIED_RESEARCH_PRICE`. NAV, cash and margin are VND by the
[private portfolio field contract](private_portfolio_context_contract.md).
The governed sizing adapter already refuses that input with
`MONETARY_UNITS_NOT_EXPLICITLY_COMPARABLE`; the ordinary path did not.

The retained 2026-10-16 private Action Center was inspected locally and read-only.
Its NAV weights summed to about 0.0007 while cash alone was about 0.26 of NAV. Its
research size envelopes reached hundreds of times NAV. Every holding read
`binding_constraint=NONE`. These figures are diagnostic evidence of incompatible
units. They are not a conversion factor, and no private value is retained in Git.

## Rules

- A price mark carries `value`, `price_unit`, `price_basis`,
  `source_artifact_identity` and `session` exactly as its source declares them.
  `load_descriptive_price_marks` reads them from
  `technical_features.price_basis_qualification`. An absent unit is `UNDECLARED`.
  No unit is inferred from magnitude, formatting, a familiar ticker price, cost
  basis or another provider. There is no `x1000` rule.
- The account monetary unit is the account `currency` field when present, otherwise
  VND by field contract. Quantities are shares.
- `current_market_value` and NAV `current_weight` exist only on one of two paths:
  - **Verified units.** Every priced holding's price declares the account unit
    (`VERIFIED_COMPARABLE_UNITS`, method `QUANTITY_X_PRICE_IN_ACCOUNT_MONETARY_UNIT`).
  - **Owner anchor (derived proxy).** A broker-reported securities market value
    (`total_broker_reported_securities_market_value`, or the account
    `gross_market_value`) scales the equity-sleeve mix:
    `value_i = sleeve_i x anchor`. The status is `OWNER_ANCHORED_DERIVED_PROXY` and
    weights read `AVAILABLE_OWNER_ANCHORED_DERIVED_PROXY`. This path requires all of:
    - an anchor dated on the price session;
    - every confirmed holding priced from one price source and unit;
    - no `CURRENT_POSITION_UNRESOLVED` row;
    - when NAV, cash, receivables and margin are all known, the NAV identity
      `cash + securities + receivables - margin` reconciles within 1%.

  The anchor never converts a price and never unlocks a share quantity.
- Otherwise holding values and weights are unavailable
  (`UNAVAILABLE_MONETARY_UNIT_NOT_COMPARABLE`) with reason codes. Examples:
  `PRICE_UNIT_NOT_ACCOUNT_UNIT:<unit>`, `OWNER_ANCHOR_ABSENT`,
  `OWNER_ANCHOR_NOT_SAME_SESSION`, `OWNER_ANCHOR_NAV_IDENTITY_MISMATCH`,
  `UNRESOLVED_POSITION_BLOCKS_OWNER_ANCHOR`,
  `UNPRICED_CONFIRMED_HOLDING_BLOCKS_OWNER_ANCHOR`, `MIXED_PRICE_SOURCES_OR_UNITS`.
- `equity_sleeve_weight` is a unit-free ratio. It is computed over priced, active,
  confirmed holdings of one price source. It stays available whatever the unit, with
  limitations such as `COMMON_SOURCE_SCALE_ASSUMED_UNIT_NOT_VERIFIED`.
- Missing exposure is never zero exposure. Sector weights and gross exposure exist
  only when every active holding has a NAV weight and no position's existence is
  unresolved (`exposure_status`). A computed NAV uses account-unit values only and
  requires complete position truth.
- Share-denominated outputs need the entry reference price, and for risk sizing also
  the invalidation price, to declare the account unit. The covered outputs are:
  - risk-budget quantity;
  - remaining quantities for the single, sector and gross caps;
  - margin-debt room;
  - cash-fundable quantity;
  - margin research capacity quantity;
  - research size envelope shares;
  - Level-1 capacity shares.

  A trigger or invalidation boundary declares its unit through `price_basis.price_unit`
  (or `price_unit` / `unit`). Without the account unit these outputs are `None` with
  `MONETARY_UNITS_NOT_EXPLICITLY_COMPARABLE`, and risk sizing reads
  `UNAVAILABLE_MONETARY_UNIT_NOT_COMPARABLE`. Account-unit amounts (risk budget,
  deployable cash, remaining notional) and unit-free ratios (reward/risk, margin band)
  remain.
- Constraint evaluation is explicit. Each weight constraint carries `evaluation`:
  `EVALUATED_WITHIN_LIMIT`, `EVALUATED_BREACHED` or `NOT_EVALUABLE`, plus `reason`.
  Each record carries `binding_constraint_state`: `EVALUATED_BINDING`,
  `EVALUATED_NOT_BINDING`, `NOT_EVALUABLE` or `NOT_APPLICABLE`.
  `binding_constraint` reads `NOT_EVALUABLE`, never `NONE`, when a relevant constraint
  could not be evaluated. A held position's weight is relevant; so is any gating
  constraint for an add or probe.
- Quant risk follows the same rules:
  - The `EQUITY_SLEEVE_VOLATILITY` view and HHI use the sleeve mix and are unchanged.
  - The `NAV_SCALED_EQUITY_RISK` view, leave-one-to-cash sensitivity, coverage NAV
    weights, `equity_exposure_to_nav` and account-unit totals need qualified NAV
    weights. Without them they are unavailable with a status.
  - Account-level position values need account-unit market values.
- `project_portfolio_fit_for_integrated_decision` returns `None` (unknown) for an
  unevaluable held concentration or sector overlap, never `False`.

## Unchanged

Research posture, decision identity inputs, position truth, cost-basis context,
sector resolution, exclusions, margin economics thresholds and every Integrated
Decision, T0, Brief, AI handoff and Dashboard artifact are unchanged. The Integrated
Decision does not read these fields. The private AI research handoff carries no
weights. The optional `integrated_decision_artifact` argument of
`evaluate_from_retained_artifacts` lets a caller reuse an already-loaded Integrated
Decision of the same session instead of materializing a second full copy.

## Validation

Existing synthetic fixtures now declare their account unit explicitly:
`price_units="VND"` and boundary `price_basis.price_unit`. No assertion was relaxed.

The new tests in `tests/test_portfolio_aware_decision.py` (`test_unit_*`) and
`tests/test_personal_portfolio_quant_risk_decomposition.py` cover:
- undeclared and research units;
- explicit VND;
- incompatible and mixed units;
- stale, absent and mismatched anchors;
- a qualified anchor that is a proxy only;
- unresolved, unpriced and excluded holdings;
- sector and gross not evaluable;
- blocked risk, margin, envelope and capacity quantities;
- a genuine verified over-limit;
- `NONE` versus `NOT_EVALUABLE` binding;
- the defect-shape regression;
- declared units in descriptive marks;
- quant-risk sleeve parity with NAV-scaled outputs blocked.

## Not authoritative

Research prices remain `UNVERIFIED_RESEARCH_PRICE`. Anchored weights are a private
derived proxy, not exact canonical exposure. No share quantity, sizing, execution,
PIT or valuation authority follows.
