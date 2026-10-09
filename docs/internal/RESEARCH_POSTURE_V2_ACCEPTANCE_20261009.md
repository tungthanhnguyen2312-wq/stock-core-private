# Research Posture V2 synthetic acceptance — 2026-10-09

Same cohort: 36 deterministic synthetic fixtures, evaluated against the exact baseline `168e0f712e3b57c6a626f0e76f36f471136f3232` v1 implementation and candidate v2. No retained Daily, private owner data, provider or production writes.

Baseline source loaded offline from Git into scratch; unchanged tactical phase/inputs for each pair. This comparison measures ungated policy classification. Currency gates and consumer materialization are tested separately.

V1 distribution: `{'WAIT_FOR_CONFIRMATION': 18, 'HOLD': 1, 'EARLY_WATCH': 2, 'AVOID': 6, 'INITIATE_ON_BREAKOUT': 5, 'HOLD_DO_NOT_ADD': 2, 'INSUFFICIENT_CURRENT_RESEARCH': 1, 'ACCUMULATE_ON_RETEST': 1}`.

V2 distribution: `{'WAIT_FOR_CONFIRMATION': 20, 'EARLY_WATCH': 2, 'AVOID': 4, 'REDUCE': 1, 'INITIATE_ON_BREAKOUT': 5, 'HOLD_DO_NOT_ADD': 2, 'INSUFFICIENT_CURRENT_RESEARCH': 1, 'ACCUMULATE_ON_RETEST': 1}`.

| Fixture | V1 posture | V2 posture | V2 condition class |
|---|---|---|---|
| A1 | WAIT_FOR_CONFIRMATION | WAIT_FOR_CONFIRMATION | CONSTRUCTIVE_TREND_NO_FRESH_ENTRY |
| A5 | WAIT_FOR_CONFIRMATION | WAIT_FOR_CONFIRMATION | CONSTRUCTIVE_TREND_NO_FRESH_ENTRY |
| A6 | HOLD | WAIT_FOR_CONFIRMATION | CONSTRUCTIVE_TREND_NO_FRESH_ENTRY |
| A7 | WAIT_FOR_CONFIRMATION | EARLY_WATCH | BASE_UNCONFIRMED |
| B1 | WAIT_FOR_CONFIRMATION | WAIT_FOR_CONFIRMATION | EARLY_REVERSAL_AWAITING_HIGHER_LOW |
| B2 | EARLY_WATCH | EARLY_WATCH | EARLY_MONITOR_NO_TRIGGER |
| B3 | WAIT_FOR_CONFIRMATION | WAIT_FOR_CONFIRMATION | FUNDAMENTAL_DETERIORATION_VETO_NO_NEW_ENTRY |
| C1 | AVOID | AVOID | BEARISH_STRUCTURE_ADVERSE |
| D1 | WAIT_FOR_CONFIRMATION | WAIT_FOR_CONFIRMATION | DISTRIBUTION_RISK_NO_FRESH_ENTRY |
| D2 | AVOID | AVOID | DISTRIBUTION_OR_BREAKDOWN_WITH_DETERIORATION |
| E1 | WAIT_FOR_CONFIRMATION | WAIT_FOR_CONFIRMATION | FAILED_BREAKOUT_REBASE_REQUIRED |
| E2 | AVOID | REDUCE | FAILED_BREAKOUT_WITH_DETERIORATION |
| E3 | AVOID | AVOID | BEARISH_STRUCTURE_ADVERSE |
| F1 | INITIATE_ON_BREAKOUT | INITIATE_ON_BREAKOUT | FRESH_ENTRY_TRIGGER |
| F2 | WAIT_FOR_CONFIRMATION | WAIT_FOR_CONFIRMATION | FUNDAMENTAL_DETERIORATION_VETO_NO_NEW_ENTRY |
| F3 | WAIT_FOR_CONFIRMATION | WAIT_FOR_CONFIRMATION | PARTICIPATION_CONTRADICTION_NARROWS_ENTRY |
| F4 | WAIT_FOR_CONFIRMATION | WAIT_FOR_CONFIRMATION | BEARISH_BREADTH_NARROWS_FRESH_ENTRY |
| F5 | WAIT_FOR_CONFIRMATION | WAIT_FOR_CONFIRMATION | CONSTRUCTIVE_TREND_NO_FRESH_ENTRY |
| G1 | HOLD_DO_NOT_ADD | HOLD_DO_NOT_ADD | EXTENDED_NO_CHASE |
| G2 | INSUFFICIENT_CURRENT_RESEARCH | INSUFFICIENT_CURRENT_RESEARCH | UNQUALIFIED_TACTICAL_AND_FUNDAMENTAL |
| G3 | AVOID | WAIT_FOR_CONFIRMATION | UNQUALIFIED_TACTICAL_STRUCTURE |
| H1 | AVOID | AVOID | BEARISH_STRUCTURE_ADVERSE |
| R1 | ACCUMULATE_ON_RETEST | ACCUMULATE_ON_RETEST | CONFIRMED_RETEST_ENTRY |
| R2 | WAIT_FOR_CONFIRMATION | WAIT_FOR_CONFIRMATION | OBSERVATIONAL_NO_ENTRY |
| R3 | WAIT_FOR_CONFIRMATION | WAIT_FOR_CONFIRMATION | FUNDAMENTAL_DETERIORATION_VETO_NO_NEW_ENTRY |
| R4 | WAIT_FOR_CONFIRMATION | WAIT_FOR_CONFIRMATION | BEARISH_BREADTH_NARROWS_FRESH_ENTRY |
| T1 | WAIT_FOR_CONFIRMATION | WAIT_FOR_CONFIRMATION | CONSTRUCTIVE_TREND_NO_FRESH_ENTRY |
| T2 | INITIATE_ON_BREAKOUT | INITIATE_ON_BREAKOUT | FRESH_ENTRY_TRIGGER |
| T3 | HOLD_DO_NOT_ADD | HOLD_DO_NOT_ADD | EXTENDED_NO_CHASE |
| P1 | WAIT_FOR_CONFIRMATION | WAIT_FOR_CONFIRMATION | PARTICIPATION_CONTRADICTION_NARROWS_ENTRY |
| P2 | INITIATE_ON_BREAKOUT | INITIATE_ON_BREAKOUT | FRESH_ENTRY_TRIGGER |
| P3 | WAIT_FOR_CONFIRMATION | WAIT_FOR_CONFIRMATION | PARTICIPATION_CONTRADICTION_NARROWS_ENTRY |
| P4 | INITIATE_ON_BREAKOUT | INITIATE_ON_BREAKOUT | FRESH_ENTRY_TRIGGER |
| M1 | INITIATE_ON_BREAKOUT | INITIATE_ON_BREAKOUT | FRESH_ENTRY_TRIGGER |
| O1 | EARLY_WATCH | WAIT_FOR_CONFIRMATION | PENDING_DEFINED_CONFIRMATION |
| O2 | WAIT_FOR_CONFIRMATION | WAIT_FOR_CONFIRMATION | OBSERVATIONAL_NO_ENTRY |

WAIT is differentiated by classes, not universally replaced with bullish decisions. Base becomes early monitoring; healthy/no-trigger trends become constructive non-entry; unqualified bearish evidence loses AVOID; failed breakout plus deterioration gets its specific REDUCE row. Fresh breakout/retest and numeric boundaries remain unchanged.

Legacy missing-epoch identity matches baseline exactly: `decision:SYN:bb4e33e57612f4dd`.

## Matrix coverage and owner reconciliation

Grok attachment SHA-256: `eb0964c8d0d5fcc83eec8f09f301d793319f0e1634df2b4d2c134aacd89400ee`.
Its proposal adds no repository authority. Owner decisions prevail.

| Acceptance rows | Synthetic coverage |
|---|---|
| A1–A4 | Same full public artifact/identity for absent, held, not-held and unresolved private inputs; real downstream portfolio hold/no-add/unavailable |
| A5–A7 | Missing/MIXED/IMPROVING fundamentals; qualified base across five fundamental states; A7 owner override |
| A8–A9, C2–C3 | Current/dated/absent currency across five tactical inputs; real missing-evidence REDUCE gate |
| B1–B3, C1, D1–D2, E1–E3 | Downtrend breakout, early reversal, bearish BOS/sector contradiction, distribution, failed-breakout precedence |
| F1–F5 | Fresh trigger preserved; deterioration, available participation and qualified breadth narrow; missing/blocked evidence and no-trigger trend cannot invent negative entry votes |
| G1–G3, H1 | Extension, ineligibility/conflicts and simultaneous bullish trigger/bearish BOS |
| Added boundaries | Retest >0 invalidation; extension >5%; participation <=0.60/<=0.25; false trigger; narrow leadership; actual pending trigger; fallback observation |

Differences from Grok: BASE_UNCONFIRMED is early monitoring; all private context is
ignored in public artifacts (no ownership_context); failed breakout is excluded
from the general distribution/deterioration row; APPROACHING precedes generic
BREAKOUT_SETUP early watch to expose actual pending confirmation. No phase,
fresh-breakout/retest predicate, numeric threshold, fundamental vocabulary or
portfolio sizing policy is rewritten.

## Verification

- Integration/regression: 417 passed, 6 skipped, 1 deselected. This includes actual
  temporary Workspace/public index/detail/Screener/Brief/Action Center materialization,
  packet projection/replay, v1 identity and cross-epoch handling, and portfolio ceilings.
- Real synthetic Producer → session operation → packet → AI bundle/cockpit: passes
  for macro present/absent; source class/epoch remain unchanged in all projections.
- Latest policy/coherence tests including legacy v1 HOLD workspace read: 94 passed.
- Additional synthetic fitness/private-portfolio/shortlist/workbench/context: 56 passed,
  1 explicitly deselected retained-golden case. Three initially attempted legacy checks
  require missing August retained artifacts outside the hermetic selection; no retained
  artifacts were copied, created, opened successfully or replayed.
- `py_compile`: 21 changed/new Python files passed; `git diff --check` passed.
- Baseline AST comparison confirms unchanged tactical phase, fundamental synthesis/
  direction, valuation interpretation, evidence currency qualification, risk sizing,
  probe eligibility, research size envelope and margin economics/caps functions.
- Active reading set: 102,347 bytes, within 102,400; 320 Active State lines.
- Native admission/guard tests preserve unrelated historical JSON verbatim. Native
  roadmap check ON_TRACK/PASS, current CONDITIONAL_RESEARCH_POSTURE_V2 ACTIVE,
  queue empty. Dirty-worktree warnings are expected before the checkpoint.

Final full Producer CI hermetic selection (137 files, provider-import guard,
`not retained_evidence and not provider_runtime`): **3321 passed, 21 skipped,
15 deselected, 42 subtests passed**, 768.51 seconds. No failures. Skips reflect
platform-specific guards, absent HPG retained evidence and unavailable symlink APIs.
The subsequently added v1 HOLD workspace-read case and policy-epoch vocabulary
assertion passed in the focused 94-test run; the UTF-8-only comment correction
in the integrated test file passed its 59-test suite. Final governance guards:
49 passed. The earlier seven in-scope failures were corrected in this same job.

## Invariants and release boundary

Nine tokens unchanged, no v2 HOLD, no current instruction on absent evidence,
legacy v1 readable, no universal score/target/probability or new authority.
Private holdings influence only downstream portfolio research. Add/probe ceilings,
leverage and execution-qualified quantities remain unchanged. No production Daily,
replay, write, T0 reseal, deployment or merge occurred. Existing primary worktree,
data/OCR/Vault and historical authority documents are untouched.

Capacity Phase 1 engineering is COMPLETE at PR99/main
`168e0f712e3b57c6a626f0e76f36f471136f3232` with post-merge CI 37893984528 success;
zero production reclaim/activation. Posture V2 stays ACTIVE pending owner merge/release;
there is no queued or automatic successor. One feature branch/PR is authorized.
