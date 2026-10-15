# Conditional opportunity evidence in the existing Action Center

Milestone `CURRENT_RESEARCH_CONDITIONAL_OPPORTUNITY_AND_EARLY_REVERSAL_V1`.
Base: released V6 main `e76d3053185fff23ee8dfc02e0d9690e9f9a5ca5`.
Authority effect NONE. One optional consumer presentation; no new classifier,
ranking, action policy, production activation or Dashboard schema.

## Demonstrated gap and selected fix

The baseline Action Center JSON already retains why-now, phase, posture,
counter-thesis and uncertainty. Its Markdown watchlist renders only ticker/action;
discovery renders only lane/tickers. The evidence condensation also omits the
Integrated Decision's existing `priority_posture_reconciliation`, opportunity
priority and serialized boundary conditions. This is a loss at the final
presentation boundary, not evidence that the posture policy is wrong.

Twelve synthetic engine-to-consumer cases show 0/12 why-now explanations in the
baseline Markdown and 0/12 priority explanations in per-ticker evidence. These
are synthetic coverage measurements, not estimates of production incidence.
No retained session was rewritten or used to claim a market-wide defect rate.

Two fixes were compared:

1. Render existing condensed evidence only. Small, but cannot recover discarded
   condition direction/activation, price-basis lineage or priority reconciliation.
2. Opt in to a bounded evidence extension inside the existing Action Center and
   render those retained fields. Selected: one source module, one acceptance test
   module and this contract. No new standalone artifact or consumer project.

## Interface and compatibility

`personal_investment_decision_action_center.build_artifact` and its existing
`evaluate_from_retained_artifacts` resolver accept the keyword-only argument
`include_conditional_research=False`. False preserves default JSON, content hash,
Markdown and Daily call shape. No production caller enables it.

True adds `conditional_research` to evidence on already-selected holdings,
watchlist and discovery rows, plus `conditional_research_presentation` coverage.
It preserves source priority, reconciliation, legacy watchlist classification,
breakout state, technical/fundamental support, financial synthesis, evidence
currency lineage, exact-use limitations and source identities. Missing fields
remain missing; no stronger class or fallback boundary is synthesized.

The opt-in requires the exact Integrated Decision contract/session, native
artifact content identity, each ticker/session and native decision identity.
A supplied coverage artifact must match the session. These are integrity and
binding checks, not independent authentication or evidence promotion.

The existing Markdown renderer displays per-ticker why-now, setup, independent
watchlist/entry lens, canonical posture/class, priority/reconciliation, measured
confirmation/invalidation, counter-thesis, uncertainty, fitness and lineage.
An unavailable priority or counter-thesis stays explicitly unavailable/empty.
It does not create a disagreement rule: the source reconciliation is passed
through even when it says priority context was not provided.

Numeric display requires current price coverage, canonical `CURRENT_SESSION`
evidence currency, explicitly verified price basis, and a source machine-evaluable
condition whose reference level matches the boundary. Otherwise numeric levels
and distances are withheld in both the extension and its condensed evidence.
Qualitative state, conditions, warnings and source identity survive. This
conservative display restriction does not retract the retained research measurement.
The unit label is passed through; a research number never becomes VND by inference.

Condition projections carry `source_condition_identity`, identifying the retained
source condition, not the hash of a narrowed copy. Future activation semantics
are distinct from the source's observed `trigger_state`. No future close is
evaluated and no invalidation event is invented. Structural and watchlist
conditions stay separate; no borrowed level/direction. Invalidation remains
analytical context, never an execution stop.

## Twelve scenario acceptance

The test builds the existing watchlist classifier over its canonical synthetic
descriptive/screening/fundamental fixtures. Existing priority policy supplies lane
tiers; the real queue builder supplies entry relevance; the real Integrated
Decision builder supplies phase, policy/class, conditions and evidence currency;
the real asymmetric builder supplies research context; the real Action Center
build and Markdown render complete the consumer trace. Watchlist fixtures use
the same synthetic session as V3 inputs, with independent supplied measurements;
they are not asserted to be a retained real-world session.
The priority test uses a bounded twelve-record queue; it does not claim the
official universe's 1,507-record coverage or bypass its production producer gate.

| Scenario | Watchlist state | Integrated phase | Research priority | Unchanged canonical posture |
|---|---|---|---|---|
| Continuing decline | DOWNTREND | BREAKDOWN | MONITOR | AVOID |
| Stabilizing decline | SELLING_PRESSURE_EASING | BREAKDOWN | MONITOR | AVOID |
| Base | BASE_BUILDING | BASE_BUILDING | PRIORITY_NOW | EARLY_WATCH |
| Early bullish reversal | EARLY_REVERSAL_CANDIDATE | EARLY_REVERSAL | PRIORITY_NOW | EARLY_WATCH |
| Established uptrend | UPTREND_CONFIRMED | TREND_CONTINUATION | PRIORITY_NOW | WAIT_FOR_CONFIRMATION |
| Breakout attempt | BREAKOUT_READY | BREAKOUT_SETUP | PRIORITY_NOW | WAIT_FOR_CONFIRMATION |
| Confirmed breakout | BREAKOUT_READY | BREAKOUT_CONFIRMED | PRIORITY_NOW | INITIATE_ON_BREAKOUT |
| Failed breakout | DISTRIBUTION_RISK | DISTRIBUTION_RISK | MONITOR | WAIT_FOR_CONFIRMATION |
| Strong stock / weak breadth | BREAKOUT_READY | BREAKOUT_CONFIRMED | PRIORITY_NOW | WAIT_FOR_CONFIRMATION |
| Missing financials | EARLY_REVERSAL_CANDIDATE | EARLY_REVERSAL | PRIORITY_NOW | EARLY_WATCH |
| Stale financial context | EARLY_REVERSAL_CANDIDATE | EARLY_REVERSAL | PRIORITY_NOW | EARLY_WATCH |
| Insufficient technical history | unclassified | INSUFFICIENT | MONITOR | WAIT_FOR_CONFIRMATION |

Every row now displays its source confirmation/invalidation operators and future
activation semantics, policy reason, blocker/counter-evidence and source identity.
Eleven synthetic rows retain explicitly qualified levels; the insufficient-history
row withholds numeric boundaries and shows the qualification reason. Additional
adversarial cases cover absent session evidence, missing/mixed basis, stale marks,
missing coverage, conflicting levels, missing legacy conditions, altered identity,
session mismatch and owner exclusions.

The absent-fundamental case remains `INSUFFICIENT` / `ABSENT` on the fundamental
axis, while technical research stays visible. The stale case remains `STALE_ONLY`,
never silently becomes current financial support. Qualified technical evidence
does not confer PIT, financial, portfolio, liquidity, sizing or execution authority.

## Measured interpretation changes

- Why-now/setup/priority/conditions visible: 0/12 to 12/12 watchlist rows.
- Three PRIORITY_NOW plus WAIT outcomes now expose the existing explanation:
  constructive trend without a fresh entry, pending trigger, bearish breadth.
- Four EARLY_WATCH setups remain four research opportunities with conditions,
  including absent/stale financial context; no capital-action posture strengthens.
- One missing-history boundary pair explicitly withheld; all source condition
  fitness/reasons remain visible. Separate conflict/missing-boundary cases narrow
  display without moving posture or inventing a condition.
- Canonical posture, decision identity, evidence currency, action remap,
  attention bucket, lane membership and portfolio availability remain identical
  across all twelve baseline/candidate cases. Optional content identity changes
  because the presentation contains more information.
- Coverage is unique displayed tickers / full Integrated Decision denominator.
  Existing selection/exclusions remain; the feature does not claim discovery
  coverage for every unselected WAIT case.

For example, a breakout attempt previously read only `WAIT_FOR_CONFIRMATION`.
It now shows `BREAKOUT_READY` as the independent entry lens, `BREAKOUT_SETUP`
as V3 phase, `PRIORITY_NOW` as research attention, and
`PENDING_DEFINED_CONFIRMATION` as the canonical policy reason. Its observed state
is `APPROACHING`; close-above confirmation is a future condition. The canonical
decision stays WAIT. An early reversal remains EARLY_WATCH despite absent
fundamentals, with the missing financial axis and execution limitations visible.

## Offline use

Use the existing local resolver over approved retained artifacts; it reads only
the retained completed session and optional private portfolio. It performs no
Daily or provider operation. Do not supply a production output path for preview.

```python
from pathlib import Path
import personal_investment_decision_action_center as ac

preview = ac.evaluate_from_retained_artifacts(
    repo_root=Path("/path/to/approved/research/checkout"),
    session="YYYY-MM-DD", requested_at="explicit-request-time",
    include_conditional_research=True,
)
text = ac.markdown(preview)
# Inspect text or use the existing private output writers in an explicit preview root.
```

No new launcher or automatic activation is admitted. Release review remains
separate from this local implementation. Native state/checkpoints govern status;
the leased ACTIVE_STATE file and all prior VRE records are preserved.

## Validation disposition

The focused optional-view and existing Action Center selection passes 41 tests,
including fourteen new acceptance/adversarial/resolver/portfolio tests. The
technical/fundamental/valuation and temporal additional selection passes 168
tests (overlaps acceptance; counts are not additive). V2/coverage selection has
141 passes and ten missing-retained-artifact failures, identical on the released
baseline and candidate. Required hermetic V2 cases pass; unavailable retained
fixtures are not represented as passing evidence.

The matched broad selection on both source versions has 684 passes, 54 passing
subtests, two failures, one error and one skip. Exact failed IDs match:

- `test_current_research_decision_convergence.py::test_ordinary_daily_enrichment_binds_operational_fundamental_context`
- `test_current_research_decision_convergence.py::test_ordinary_daily_binding_failure_degrades_to_no_bridge_without_losing_the_decision`
- Retained-evidence setup error:
  `test_daily_opportunity_decision_queue.py::test_real_retained_universe_matches_milestone_ground_truth`.

The convergence tests expect BUILT but observe UNAVAILABLE on both versions;
their baseline behavior is retained, not repaired or suppressed in this scope.
The queue error requires the absent governed August24 triage artifact. Coverage
tests require absent August24/September21 retained source artifacts. There are
zero new failed IDs in either matched selection. No missing fixture was fabricated,
no assertion was weakened and no marker was changed to hide these limitations.

The independent released-baseline default identity for the twelve-case fixture is
`personal_investment_decision_action_center/v1:ad9e9f15b1e26f1ddff4d2783c74fdd55ce7bf67184d06c06bfc6e7e8f3ca97d`,
also asserted by the candidate golden test. A separately captured pre-edit
twelve-record trace is exactly equal after the change: JSON, content identity
and Markdown. Local validation logs and synthetic before/after previews are
external operator evidence; native completion records identify the durable source.
