# Liquidity execution-capacity and research sizing

Status: `LIQUIDITY_EXECUTION_CAPACITY_AND_SIZING_V1 = CLOSED / IMPLEMENTED /
RETAINED_ACCEPTANCE_PASS / LIQUIDITY_EXECUTION_CAPACITY_AND_SIZING_PARTIAL` (2026-09-29).

## Public current-session capacity

`execution_capacity_policy/v1` is policy, not evidence. It validates an optional minimum ADTV20,
positive exchange lot sizes, participation strictly greater than zero and at most one, and a
positive governed-session liquidation horizon capped at 20. No repository evidence authorizes a
real participation or horizon value, so `EXECUTION_CAPACITY_POLICY_UNBOUND_V1` leaves both fields
unbound. Exchange lot rules are likewise unbound until source-qualified; no market rule is guessed.

`execution_capacity_research_envelope/v1` consumes only
`official_exchange_liquidity_research/v1` and calculates, with exact Decimal arithmetic:

```
capacity_notional_vnd = ADTV20_MATCHED_ALL_VND × participation × governed sessions
capacity_shares = floor_to_declared_lot(capacity_notional_vnd / current_price)
```

The notional can remain usable when a lot rule is absent, while the share field stays absent with
`LOT_RULE_UNBOUND`. A published exact-zero ADTV window is valid and produces zero under a bound
policy. Incomplete/missing windows are never forward-filled. Historical T0 requests fail with
`PIT_REQUIRED_HISTORICAL_USE`.

Every result is `RESEARCH_SCOPED_LEVEL1_ENVELOPE`, never a live instruction, fill/VWAP/execution
price guarantee, or market-impact-adjusted quantity. The canonical unbound-policy retained run over
2026-09-28 has 1,683 BLOCKED records: 457 policy-unbound exact-ADTV records, 1,047 rights-gated
HNX/UPCoM records and 179 unresolved/conflicting routes. Current-session liquidity remains eligible
for 952; exact ADTV20 remains 457 (HOSE 403, retained HNX 28, retained UPCoM 26).

## Private research size

`research_size_envelope/v1` is nested in the existing private portfolio-aware sizing path. It
reuses, rather than replaces, that engine:

- risk cap: existing explicit IID entry/invalidation risk budget calculation;
- liquidity cap: public Level-1 capacity shares when qualified;
- concentration cap: the tightest qualified existing single-name, sector and gross-exposure room;
- cash funding remains the existing separate funding constraint.

The research quantity is the minimum qualified cap. Completeness is `FULL`, `PARTIAL` or
`INSUFFICIENT`. Missing explicit invalidation omits only the risk cap; equal entry and invalidation
fails as `UNAVAILABLE_DEGENERATE_DOWNSIDE`. ATR/NATR/arbitrary stops and target prices are never
substituted. `execution_qualified_quantity` remains `None / NOT_QUALIFIED`.

`SYSTEM_DEFAULT_POLICY_V3` preserves all bound V2 values and adds the capacity-policy fields with
per-field provenance. Participation, horizon and optional minimum ADTV are `UNBOUND` absent owner
input. A policy identity change changes the research-envelope identity; cross-epoch comparison is
`NOT_COMPARABLE_POLICY_CHANGE`.

## Authority boundary

| Use | State |
|---|---|
| `CURRENT_SESSION_EXECUTION_CAPACITY_RESEARCH` | scoped `ELIGIBLE/PARTIAL` by evidence and policy |
| `CURRENT_SESSION_RISK_SIZE_RESEARCH` | private scoped `ELIGIBLE/PARTIAL` |
| `LIVE_POSITION_SIZING` | `BLOCKED` |
| `PORTFOLIO_CAPITAL_ALLOCATION` | `BLOCKED` |
| `HISTORICAL_PIT_SIZE_REPLAY` | `BLOCKED` |
| `PIT_BACKTEST` | `BLOCKED` |
| `EXECUTION_REPLAY` | `BLOCKED` |

`ACTIVE_UNIVERSE = UNKNOWN` does not block a currently identified qualified ticker. It continues to
block survivorship-safe historical ranking, market-wide allocation and PIT uses. Intrinsic valuation
is not an input. The new path has no dependency on Vnstock, live KBS/VCI, `gtgd20_ty`, legacy average
volume or `risk_liquidity.average_volume`.

Public Daily integration is additive under `LIQUIDITY.qualified_research.execution_capacity_research`.
It is non-voting, component-local, and contains no NAV, holdings, cost basis, account alias or owner
quantity. Private Action Center and decision-packet surfaces may carry the private envelope only in
their already-local artifacts.

The retained Integrated Decision snapshot predates `current_research_decision_input` (0 of 1,683
records contain it). Acceptance therefore rebuilds that input with the current builder both with
and without the retained official record, checks the capacity fields against the standalone engine,
and verifies zero changes to posture, decision identity, evidence class and non-liquidity dimensions.
This is a reconstruction check, not a claim that those nested bytes existed in the old snapshot.
