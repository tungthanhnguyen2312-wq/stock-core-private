# October 22 research quality acceptance

Base main `ec3044245ecfb1b53531fe2613113bf870d31c1c`; PR179 post-merge run
39800988612 completed with all five jobs successful. Source-only Owner scope:
[contract](../post_daily_20261022_research_decision_quality_closeout_contract.md).

## Demonstrated corrections

1. `technical_structure_context._swing_structure_context` used `not higher` as
   `lower`. Equal confirmed highs/lows became LH/LL and RANGE was unreachable.
   Strict comparisons now retain EH/EL, with RANGE when either side is equal.
   Existing BOS/pivot/trigger/invalidation owners recompute from identical closes.
2. Integrated breakout explanations called unavailable fundamentals
   “non-conflicting” and the setup “actionable”. They now name the evidence
   availability, preserve mixed fundamentals and explicit bearish recovery
   counter-evidence, and distinguish volume magnitude from bullish confirmation.
   No existing posture predicate, threshold, strategy or voting axis changes.
3. Projection/delivery lost the thesis orientation, horizon and basis of structural
   invalidation. Those fields and shared-level caveats now survive AI/cockpit.
   Opt-in scenario binding keeps an upward bearish-structure resolution as source
   context, rather than also using it as a downside Bear activation. Observed
   adverse evidence still admits its own Bear case; legacy unscoped inputs stay readable.
4. Packet Markdown omitted the financial period of historical momentum. HPG/SSI/PVD
   FY2024 states now retain `financial_period=2024` and a non-confirmation caveat.
   No financial fact, comparable period or direction is substituted.

## Actual retained session

Operation `a85ed21197e16c2511c5a818cd8b7b9a268af4898716171cecad197238780b70`;
original IID `c89efa31490d5cf44486d60e9c943bb3cee2c59e5057c5ca3ceb923af4b83017`.
LATEST and the immutable build manifest agree on session 2026-10-22, original
Producer checkpoint `b473321b`, and READY_FOR_AI. PR179 is not repeated.

| Ticker | Before → corrected diagnostic | Retained independent strategy view |
|---|---|---|
| EVF | Equal highs 11.6 falsely LH/early bearish → EH/RANGE, bullish BOS; invalidation above 11.6 → below 11.45. INITIATE stays conditional, fundamentals NOT_APPLICABLE_ENTITY. | Owner multi-week WAIT remains separate. |
| VNM | Equal highs 58.4 falsely DOWNTREND → EH/RANGE; invalidation below 57.2. AVOID → WAIT, FUNDAMENTAL_DETERIORATION_VETO_NO_NEW_ENTRY. Trigger still approaches 58.4. | No positive fundamental confirmation. |
| NVL | Measurements/posture unchanged; upward 10.55 resolves bearish structure, not long-setup failure. Recovery conflicts remain explicit. | Short-term distribution warning remains. |
| HPG/FPT | WAIT with approaching structural triggers; unchanged. | MA-based trend/breakdown lenses remain distinct. |
| PAN/PNJ | EARLY_WATCH; unchanged. | Neutral/downtrend MA lens is not overwritten. |
| SSI/POW/PVD/QNS | AVOID; unchanged. | PVD/QNS tactical opportunity labels do not erase the integrated adverse evidence. |

The portable fixture contains exact selected close observations, basis/lineage,
descriptive inputs, accepted technical records and source-row SHA256s. Baseline
source calculations were reproduced exactly for all eleven before correction.
Tests run close series → technical owner → projection → standing posture policy,
plus structural serialization → AI/cockpit/scenario and period-aware Markdown.

Wider bounded replay: 876 source records reproduced exactly, zero baseline policy
mismatches; 157 measurement deltas, 719 unchanged source measurements. There are
91 posture-token changes and 15 class-only changes; 770 posture/class pairs stay
unchanged. Every policy delta is within the equality cohort. The remaining 807
records lack the reproduced P3F9B binding and are excluded, never reinterpreted.
Full counts and deltas: [acceptance JSON](POST_DAILY_20261022_RESEARCH_QUALITY_ACCEPTANCE.json).

Reproduce on retained data without Daily/publication:

```powershell
python -m pytest -q tests/test_research_quality_20261022.py
```

Future reconstructed identities may change with the corrected source. Original
session, source, T0, handoff, strategy and production files were not rewritten.
All ratios, financial synthesis, share/price basis, cutoffs, execution restrictions
and private-position separation remain under their existing owners.

## Genuine evidence gaps

- CPI: only June/July first-party payloads retained; July 4.45% is stale and the
  canonical inflation axis is UNKNOWN. September needs exact first-party bytes,
  hash, release/period/value and retrieval/knowledge time; no press promotion.
- SBV credit/FX/rates/liquidity lack retained explicit metrics/locators; UNKNOWN.
- H1 exact fields do not establish compatible growth pairs. Historical momentum
  is non-voting, not a current financial direction. Same-session foreign flow is
  present in the post-handoff observer; preseal absence is a legitimate cutoff.
- SSI/EVF Q3 figures remain standalone/unreviewed candidates without established
  retained-document linkage/publication time for admission. Existing Q2 intake
  cannot silently admit them. Required: original document/SHA/route receipt,
  page-bound amount/unit/quarter/cumulative identity, explicit scope/assurance and
  independently retained knowledge time. PDF creation/upload is not publication.
- HPG Q2 page6 lines10/60/61 remain geometrically ambiguous; PAN share continuity
  and ACB's June30 dated shares do not establish current strict common shares.

No provider, OCR expansion, official evidence, strict valuation, PIT, capital or
execution authority was added. Owner merge/release remains required.

## Validation and recovery

The broad local run passed 6,708 tests (95 skipped, 50 deselected, 134 subtests).
Its 18 failures exposed stale source pins, wording assertions, the compact-doc
byte budget, a new diagnostic runner's dynamic loading, and host-local active-writer
bindings in launcher fixtures. The unnecessary new runner was removed. Active
source pins/transition hashes now identify this authorized correction; historical
archives and prior hashes remain unchanged. The compact budget and relevant
failed groups are rechecked separately. Launcher tests use an isolated test home,
including child processes; the actual operator binding and production guard are
unchanged. Targeted real-session/semantic checks and structural smoke are retained
in the development worktree's scratch logs; hosted CI independently gates the PR.
