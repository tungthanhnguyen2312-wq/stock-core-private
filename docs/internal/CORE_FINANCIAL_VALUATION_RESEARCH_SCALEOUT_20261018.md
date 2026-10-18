# Core financial valuation research scaleout — retained acceptance

Implemented under [the owner-directed contract](../core_financial_valuation_research_scaleout_contract.md).
Native local implementation checkpoint: `ead8ef2724954a02b936e8ebb9692a8b157fbe46`;
disposition `LOCAL_IMPLEMENTATION_COMPLETE_NOT_PROMOTED`. Queue remains empty.
Starting local Git HEAD: `61c870c82648a67eed29d1842f88020e0326c4de`, independently
verified; local main was four commits behind the recorded remote-tracking ref.
VN30 implementation `096b8f16` was already incorporated via PR147, not redone.
Original main untracked data and other worktrees' WIP were preserved. Native
preflight was ON_TRACK / VERIFIED, including the multiple-writer check. No other
Daily/provider writer appeared in the bounded process observation.

## Implemented capability and exact result

The existing Financial V2 ratio/history owner and valuation peer owner now analyze
pretax margin, cash/assets, explicit interest-bearing debt/equity and debt/assets.
New history binds to the subject's exact operand provenance, statement family,
provider, scope, monetary representation and semantics, excluding later periods.
A longer competing source series cannot stand in for the subject's history.
Same-provider dimensionless ratios retain their established fitness when absolute
scale cancels; unknown currency/scale/scope remain unknown. Unknown scope blocks
peers. Own-provider history describes retained representations, not qualified
changes in consolidated economics or PIT histories when scope is unresolved.

Identical pinned Financial V2 evidence, 1,492 issuers, decision session 2026-10-16:

| Metric | Underlying READY values, unchanged | Usable own histories | Decision/AI peer comparisons | Outside retained VN30 peers |
|---|---:|---:|---:|---:|
| Pretax margin | 1,284 → 1,284 | 0 → 125 | 0 → 408 | 394 |
| Cash/assets | 1,276 → 1,276 | 0 → 1,149 | 0 → 430 | 416 |
| Explicit debt/equity | 1,276 → 1,276 | 0 → 1,149 | 0 → 430 | 416 |
| Explicit debt/assets | 1,276 → 1,276 | 0 → 1,149 | 0 → 430 | 416 |

Totals: **3,572 historical comparisons across 1,194 issuers** and **1,698 peer
comparisons across 431 issuers**. Of those peer comparisons, 1,642 cover 417
issuers outside the hash-verified August24 retained VN30 observation, not exact
October16 membership. Each balance-sheet history has 1,093 AVAILABLE and 56
PARTIAL; pretax margin has 125 PARTIAL and no AVAILABLE. No underlying metric-input
coverage gain is claimed. Source feature objects, method fitness, old histories
and old peer results were compared exactly and are unchanged.

Actual integrated decision → current-research input → AI delivery preserves each
new value, median, percentile, cohort, source basis and own-history context.
Own-history survives a blocked/small peer cohort independently. Future or
unresolved history subjects are withheld; stale history stays dated. Two retained
pretax subjects (ITD/TCH, labelled 2026-Q4) are withheld at this session; their raw
INSUFFICIENT_HISTORY verdict remains retained. No fiscal-label reinterpretation.

For example, HPG's retained 2026-Q1 debt/assets is 0.3494300512695575; its 31-member
basic-resources cohort median is 0.30553123855981346, percentile 0.5645161290322581.
Its seven prior observations span 0.35327716022743855 to 0.39337836580589625: below
its own retained historical range while above its peer median. These are distinct
descriptive observations, not a quality verdict or buy/sell instruction.

## Validation

- Core engine/valuation/peer integration: 160 tests passed before the final delivery
  addition; final ratio/peer/product projection selection: 47 passed, including 19
  new tests. Covers exact operands, competing providers/scopes, periods, zero and
  conflicting denominators, missing debt, applicability, medians, freshness and AI.
- Canonical materialization/product/scaleout/VN30 adjacency: 74 passed.
- Broader bank/securities, financial input integrity/flow, integrated decision,
  delivery, layout and offline smoke selection: 243 initially passed. Three delivery
  tests hit the real host's production-checkout binding; a process-local isolated
  test home resolved them without changing that binding. Entire delivery/layout
  selection then passed 49 tests. Adding the CI test required the existing caller
  hash refresh; no launcher behavior changed.
- Architecture/import selection: 126 initially passed; its one host-binding failure
  passed in the isolated test home. Native roadmap regression suite: 51 passed.
- Full 1,492-issuer retained acceptance verifies input hashes, baseline/candidate
  identities, unchanged source features, old history/peers and unchanged posture/
  fundamental policy, allowing only the new engine provenance binding. This is an
  isolated financial decision join, not a reconstructed or rewritten sealed Daily.
- `py_compile` and `git diff --check` pass. New tests join established Producer CI.
  No provider acquisition, live Daily, production, protected-evidence or seal edit.

Machine summary: [acceptance.json](CORE_FINANCIAL_VALUATION_RESEARCH_SCALEOUT_20261018.acceptance.json).
Detailed issuer comparisons and baseline/candidate engines remain under the
implementation worktree's ignored `.stocklookup/scratch/` directory. The replay
runner takes explicit paths and writes only a new separate output directory.

## True ceilings and recommended next major job

Unknown scope blocks 834 pretax and 802 observations per balance-sheet ratio from
peers. Another 42/44 are below five peers. Compatible source operands are missing
for 98/106; corporate peers are inapplicable to 110 specialist/unknown issuers.
Pretax history has 1,159 insufficient-depth source observations. These limits do
not justify loosened cohorts, inferred scope or provider calls.

Wider ceilings remain common-share continuity, exact monetary/EV identities,
normalized earnings/FCFF, specialist inputs and historical PIT/execution authority.
Missing exact evidence does not globally block independent Current Research.

Recommend **market-wide valuation versus balance-sheet divergence research**:
the content-verified October16 evaluated valuation artifact contains 764 usable
research P/B observations, with 337 overlapping this job's usable peer cohort.
Reuse these independent numerical owners to explain valuation versus leverage/
cash differences, preserving period, scope, proxy and share bases. This is a
ready retained-data integration candidate, not a new intrinsic valuation engine.
No successor was admitted or started. Release/deployment and Monday October19
Owner Daily remain separate owner actions.
