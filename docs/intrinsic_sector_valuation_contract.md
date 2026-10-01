# Intrinsic and sector valuation contract

## Current Research R5 — 2026-10-01

`current_research_intrinsic_scenario/v1` extends `intrinsic_valuation.py`; it does not introduce a second valuation engine. The legacy `evaluate_intrinsic_valuation` interface and qualified FCFF/Net-Net behavior remain available. The new boundary reuses that evaluator and the existing bounded reverse FCFF solver in `market_wide_implied_growth_reverse_valuation_research.py`.

The projection is conditional research context with authority effect NONE and `is_actionable=false`. It never supplies a target price, probability, recommendation, upside ranking, sizing rule or global ticker rejection. Relative valuation remains an independent, unchanged context.

### Canonical assumptions

`current_research_valuation_assumption/v1` binds ticker, entity family, valuation session, BEAR/BASE/BULL case, name/value/unit, semantic definition, forecast period/horizon, source class/identity/period, derivation method/input identities, fitness, warnings, limitations and blocker reasons. Missing assumptions carry explicit null metadata and exact dependent-method blockers. Assumption and method/case-set identities are deterministic content hashes.

Origins are QUALIFIED_RETAINED_EVIDENCE, DERIVED_QUALIFIED_EVIDENCE or GOVERNED_CONFIG. Retained/derived assumptions require a matching qualified source registry entry with the same value and semantics; an event identity alone cannot qualify a numeric forecast. The only registered transformation is `QUALIFIED_VALUE_IDENTITY_V1`, with one explicitly bound qualified input; no historical extrapolation policy is introduced. Every accepted input remains labelled MODEL_ASSUMPTION_NOT_FUTURE_FACT. Unknown fields, malformed/non-finite values, mismatched bindings, absent provenance, conflicting forecast horizons and invalid domains fail closed locally.

`config/current_research_valuation_assumptions.json` is the governed production source. Its `assumption_sets` is deliberately empty: R5 does not manufacture forecasts, discount rates, terminal growth, payout, beta, ERP, consensus or probabilities. Missing or malformed governed configuration produces an explicit GOVERNED_ASSUMPTION_CONFIG_UNAVAILABLE_OR_INVALID context and no numeric assumptions; it cannot cascade into failure of the relative or financial axis. Supplied sets use ticker → method → case → assumption records. Explicit future owner-governed entries must retain their provenance; neither absence nor event labels create defaults.

### Input fitness and applicability

Required financial rows must have canonical metric semantics, available quality, explicit consolidated/separate scope, complete common period identity, non-future period end, compatible declared currency and positive numeric native monetary scale, source identity and no source conflict. No unknown scale is inferred. Native monetary units are retained in each case's `monetary_basis`; per-share outputs are labelled DECLARED_NATIVE_MONETARY_BASIS_PER_SHARE, not silently converted to currency units.

Shares must be positive, qualified period-end outstanding shares with explicit source identity and matching period/scope. Weighted-average EPS shares cannot be substituted. Current price comparisons require a positive qualified price at the valuation session with the same monetary basis and the exact qualified share-basis identity. Price absence blocks comparison and reverse valuation; it does not block an otherwise qualified forward method.

The Financial V2 semantic adapter deterministically selects retained latest rows and exposes conflicting duplicates. It maps only the exact existing cash and interest-bearing-debt metric aliases. Generic investing cash flow is never CapEx; total liabilities are never interest-bearing debt; book-value labels are never RNAV. Historical cash flow is evidence, not automatically a forecast. Existing research qualification does not prove monetary scale or share basis.

Readiness is READY (all three cases usable), PARTIAL (some usable), BLOCKED (required evidence/assumptions invalid or missing), NOT_APPLICABLE (ordinary corporate variant inappropriate), or NOT_IMPLEMENTED_FOR_QUALIFIED_INPUTS (inputs qualify but no supported calculator exists). Implementation status is separately exposed even when evidence is missing. Unresolved entity families remain BLOCKED with ENTITY_APPLICABILITY_UNRESOLVED.

Bank, securities, insurance and finance-company issuers are NOT_APPLICABLE to ordinary FCFF, reverse FCFF, Net-Net, RNAV and SOTP variants. Equity methods are separately assessed without borrowing corporate assumptions. Specialized financial-sector variants require their own qualified implementation.

### Supported calculations

| Method | Version and conditional calculation | Boundaries |
| --- | --- | --- |
| FCFF_DCF | FCFF_STEADY_STATE_PERPETUITY_V1: EV = next-period steady-state FCFF / (WACC − terminal growth); equity = EV − interest-bearing debt + cash; per-share = equity / qualified period-end shares | This is the existing steady-state perpetuity, not a new multiyear forecast model. Positive FCFF/WACC, WACC > growth, finite arithmetic and explicit matching assumptions are required. |
| NET_NET | NET_NET_COMPONENT_REALIZATION_V1: cash × cash realization + receivables × receivables realization + inventory × inventory realization − total liabilities, divided by qualified shares | Explicit component ratios in [0,1]; components cannot exceed current assets. A negative result is reported as model arithmetic, not a recommendation. |
| REVERSE_FCFF | EXISTING_REVERSE_FCFF_V1: existing solver finds growth consistent with qualified market EV and supplied FCFF/WACC/bounds | Market EV = price × qualified shares + debt − cash. Admissible explicit bounds must be below WACC. Result is MODEL_IMPLICATION_NOT_FORECAST; out-of-bounds solutions stay blocked. |

FCFE, DDM, RESIDUAL_INCOME, RNAV and SOTP have explicit input/assumption readiness contracts but no new calculator. Qualified test inputs reach NOT_IMPLEMENTED_FOR_QUALIFIED_INPUTS and produce no number; missing retained inputs remain BLOCKED. RNAV/SOTP also require explicit reproducible component catalogs with values, units, periods, scope and provenance.

Cases retain formula/version, exact financial/share lineage, governed assumptions, assumption-set/case identity, numeric output or exact blocker, warnings, limitations and invalidation conditions. Ranges remain separate by method. `cross_method_dispersion` exposes those separate ranges; it never averages them.

FCFF sensitivity uses only distinct WACC/growth coordinates already present in ready governed cases with matching forecast period/horizon. Each cell binds its case forecast and coordinate identities. No perturbation step or new rate is invented; inadmissible/overflowing cells remain blocked. Missing variation yields an explicit unavailable sensitivity context.

### Producers and consumers

Canonical post-close → canonical Financial V2 materialization → existing evaluated valuation rows with additive `intrinsic_scenario_valuation` → valuation-axis / Integrated Decision → Current Research decision-input VALUATION context. Existing opportunity re-evaluation preserves a verified projection. Projection consumers verify content identity and ticker/session bindings; invalid projection data blocks only this context. The Integrated Decision binds R4 forward drivers as explanatory follow-up conditions without modifying model numbers or posture policy.

The evaluated-valuation wrapper and integrated product hashes include additive context and the new wrapper binding. Per-record decision identities retain their existing contract. No policy consumes conditional model upside.

### Retained acceptance and reopen gates

The exact ordinary 2026-10-01 denominator is 1,683: corporate 1,386; bank 28; securities 41; insurance 13; finance company 1; unresolved 214. Before/after readiness is unchanged: FCFF_DCF/NET_NET/REVERSE_FCFF/RNAV/SOTP each BLOCKED 1,600, NOT_APPLICABLE 83; FCFE/DDM/RESIDUAL_INCOME each BLOCKED 1,683. READY, PARTIAL and NOT_IMPLEMENTED_FOR_QUALIFIED_INPUTS are zero in this retained cohort. No numeric cases, reverse-only tickers, sensitivity or price comparisons qualify; no assumption sources exist. This is source coverage, not an architectural failure.

See [portable acceptance](internal/R5_INTRINSIC_SCENARIO_ACCEPTANCE.json) for method/family distributions, exact reason prevalence, source hashes and identity deltas. The baseline is the merged R4 pure explanatory join on the same retained Daily; no historical Daily is overwritten.

Reopen only with qualified retained inputs and explicitly governed assumptions:

- FCFF: compatible OCF/CapEx, cash and interest-bearing debt with declared units/lineage; qualified shares; sourced FCFF/WACC/growth. No generic TTM/EBITDA acquisition is reopened.
- Net-Net: same-period qualified cash, receivables, inventory, liabilities/current assets, compatible monetary/share basis and explicit realization ratios.
- Reverse: qualified FCFF/WACC/bounds plus same-session price/share/unit proof and valid market-EV bridge.
- FCFE/DDM/residual income: their own qualified equity cash-flow/dividend/common-equity earnings inputs, cost-of-equity and explicit forecasts, followed by separately validated method implementation.
- RNAV/SOTP: reproducible qualified component catalogs, component assumptions and separately validated sector-appropriate implementation.
- Unresolved entities: qualified entity evidence, independently of monetary/forecast readiness.

These are evidence gates, not permission to acquire anything in R5. R3 remains PARTIAL_BY_EVIDENCE / TERMINAL_FOR_CURRENT_SOURCE_SET; its existing reopen gates remain closed. R6 is NEXT and not started.
