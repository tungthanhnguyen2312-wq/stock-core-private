# Conditional Research Posture V2

Owner-directed job `RESEARCH_POSTURE_V2_FULL_IMPLEMENTATION_AND_CI`, milestone
`CONDITIONAL_RESEARCH_POSTURE_V2`; starting main
`168e0f712e3b57c6a626f0e76f36f471136f3232`. The Grok handoff is a proposal;
the owner's reconciliation and repository authority govern the implementation.

`integrated_investment_decision_product.py` remains the sole posture owner.
Contract/schema and all nine posture tokens remain unchanged. New constructions
carry `research_action_policy_version=v2` and `posture_condition_class` on every
record. `HOLD` remains readable in v1 but is never emitted by v2.

## First match wins

Qualification precedes technical votes. Rows use the existing calculated phase,
fundamental vocabulary, trigger predicates and numeric boundaries.

| Order | Condition after prior exclusions | Posture | Class |
|---|---|---|---|
| 1 | Ineligible tactical and insufficient fundamental | INSUFFICIENT_CURRENT_RESEARCH | UNQUALIFIED_TACTICAL_AND_FUNDAMENTAL |
| 2 | Ineligible, insufficient, unknown or conflicted tactical structure | WAIT_FOR_CONFIRMATION | UNQUALIFIED_TACTICAL_STRUCTURE |
| 3 | Qualified bearish BOS or downtrend without breakout/trigger | AVOID | BEARISH_STRUCTURE_ADVERSE |
| 4 | DETERIORATING plus bearish/distribution/breakdown, excluding failed breakout | AVOID | DISTRIBUTION_OR_BREAKDOWN_WITH_DETERIORATION |
| 5 | Failed breakout plus DETERIORATING | REDUCE | FAILED_BREAKOUT_WITH_DETERIORATION |
| 6 | Other failed breakout | WAIT_FOR_CONFIRMATION | FAILED_BREAKOUT_REBASE_REQUIRED |
| 7 | Existing extension predicate | HOLD_DO_NOT_ADD | EXTENDED_NO_CHASE |
| 8a | Fresh breakout predicate plus DETERIORATING | WAIT_FOR_CONFIRMATION | FUNDAMENTAL_DETERIORATION_VETO_NO_NEW_ENTRY |
| 8b | Fresh breakout emerging from downtrend/early reversal/setup | WAIT_FOR_CONFIRMATION | EARLY_REVERSAL_AWAITING_HIGHER_LOW |
| 8c | Fresh breakout plus available participation contradiction | WAIT_FOR_CONFIRMATION | PARTICIPATION_CONTRADICTION_NARROWS_ENTRY |
| 8d | Fresh breakout plus qualified bearish breadth | WAIT_FOR_CONFIRMATION | BEARISH_BREADTH_NARROWS_FRESH_ENTRY |
| 8e | Other valid fresh breakout | INITIATE_ON_BREAKOUT | FRESH_ENTRY_TRIGGER |
| 9a | Confirmed retest above invalidation, no deterioration, bearish breadth | WAIT_FOR_CONFIRMATION | BEARISH_BREADTH_NARROWS_FRESH_ENTRY |
| 9b | Other confirmed eligible retest above invalidation | ACCUMULATE_ON_RETEST | CONFIRMED_RETEST_ENTRY |
| 10a | Approaching defined trigger, no deterioration | WAIT_FOR_CONFIRMATION | PENDING_DEFINED_CONFIRMATION |
| 10b | Other early reversal/setup/CHoCH, no deterioration | EARLY_WATCH | EARLY_MONITOR_NO_TRIGGER |
| 11 | Remaining DETERIORATING | WAIT_FOR_CONFIRMATION | FUNDAMENTAL_DETERIORATION_VETO_NO_NEW_ENTRY |
| 12 | Qualified BASE_BUILDING without fresh trigger | EARLY_WATCH | BASE_UNCONFIRMED |
| 13 | Qualified established uptrend/continuation without a qualifying fresh entry | WAIT_FOR_CONFIRMATION | CONSTRUCTIVE_TREND_NO_FRESH_ENTRY |
| 14 | Remaining distribution risk | WAIT_FOR_CONFIRMATION | DISTRIBUTION_RISK_NO_FRESH_ENTRY |
| 15 | Remaining qualified breakdown/downtrend | AVOID | BEARISH_STRUCTURE_ADVERSE |
| 16 | Remaining observation | WAIT_FOR_CONFIRMATION | OBSERVATIONAL_NO_ENTRY |

After the table, `NO_CURRENT_EVIDENCE` rewrites **every** output to
`INSUFFICIENT_CURRENT_RESEARCH / MISSING_CURRENT_EVIDENCE`, preserving the ungated
posture and class in the currency gate. Dated `LAST_TRADE_AS_OF:<date>` remains
distinct from current-session and absent evidence. Trigger and invalidation
serialization remains intact. The compatibility map is enforced before identity.

## Owner reconciliation and precedence

Grok A7/P10 is overridden: qualified base is `EARLY_WATCH / BASE_UNCONFIRMED`.
Constructive trend retains the legacy WAIT token but explicitly says “no fresh
entry trigger”, “not an entry instruction”, the fundamental state, and “no owner
position is inferred”; it asserts no pending confirmation event.

Grok's general distribution/deterioration row would shadow its E2 failed-breakout
acceptance because failed breakout calculates DISTRIBUTION_RISK. The specific
failed-breakout row is exempted from that general row. Qualified bearish BOS still
wins, including contradictory bullish trigger/sector leadership (E3/H1).
An APPROACHING trigger calculates BREAKOUT_SETUP; its specific pending class
precedes generic early watch so the owner's brief can distinguish actual pending
confirmation from early monitoring. The phase calculation itself is unchanged.

INSUFFICIENT and MIXED never equal DETERIORATING. Missing participation/breadth
never invents a negative signal; existing AVAILABLE/session-qualified evidence
filters, <=0.60 acceleration, <=0.25 percentile, extension >0.05, and retest >0
invalidation predicates remain unchanged. Narrow leadership is non-bearish.
Participation narrows initiation only; breadth narrows initiation/retest only.

## Privacy, identity and downstream behavior

Security artifacts ignore the compatibility `portfolio_record` argument entirely.
Neutral legacy portfolio fields remain for schema compatibility, with unknown
position and no private values. The entire artifact, including its content
identity, is invariant across absent/held/not-held/unresolved private inputs.
Private holdings are consumed only by the explicit downstream Portfolio layer.
Constructive trend cannot enter ADD/PROBE lanes; downstream action is hold existing,
no add when not held, or NOT_EVALUATED/current position unresolved when unavailable.
Risk, leverage, add/probe ceilings and execution-qualified quantities are unchanged.

Missing record policy epoch means v1. Legacy decision identity uses the original
v1 field set and policy epoch; v2 includes the class. Legacy HOLD reads remain.
Cross-epoch transitions are `NOT_COMPARABLE_POLICY_CHANGE` before ordinary posture
transitions, even when posture is unchanged. Fundamental policy epochs remain
separate. Historical artifacts/T0 are never rewritten or reinterpreted.

All consumers pass posture/class/epoch from the Integrated Decision: decision
input, canonical packet/product, Daily brief, next-session brief, Workspace,
Screener, public read model, Action Center and Decision Surface Index, and Portfolio.
Packet source binding checks session, ticker set, content and decision identities.
Optional legacy packets without an Integrated Decision stay readable. The Daily
brief exposes exact class groups and constructive non-entry opportunities.

## Release and acceptance

Synthetic-only tests cover the Grok matrix, owner overrides, evidence currency,
qualification/conflicts, trigger/retest/extension/participation boundaries, holdings
independence, legacy identity, epochs, packet replay/projection and actual offline
workspace materialization across every surface. See
[acceptance](internal/RESEARCH_POSTURE_V2_ACCEPTANCE_20261009.md).

No new score, probability, target, provider, voting flow, trade/size/PIT/RAW authority,
production write, Daily/replay, deployment, merge or automatic successor is allowed
by this job. Capacity Phase 1 is released at the verified starting main (PR99 and
post-merge CI success); production reclaim and delivery reuse activation remain zero.
Posture V2 is COMPLETE: owner-authorized exact-head PR100 merge released
`314406e59b868d2a4207fa7af7798a31ee3b6906`; all four CI jobs at head `9eb5aef`
succeeded (run 37903228274). No production Daily or deployment was performed.
