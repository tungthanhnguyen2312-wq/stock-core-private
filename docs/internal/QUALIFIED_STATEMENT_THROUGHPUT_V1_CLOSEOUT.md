# Qualified quarterly statement throughput V1 — closeout

Scope: [contract](../qualified_quarterly_statement_throughput_v1_contract.md).
Machine results: [acceptance JSON](QUALIFIED_STATEMENT_THROUGHPUT_V1_ACCEPTANCE.json).

## Gates checked before writing

- **October23 Daily.** `COMPLETED_RETAINED_EVIDENCE` (main `e15c8f3a`); clean main checkout.
- **PR182/PR183.** Open and unmerged (heads `37068de7`/`a8c24f1a`); not edited.
  PR183 refactors `official_income_research_context`, so that function is untouched here.
- **Codex.** The shareholder-economics worktree holds uncommitted edits from 14:27, and its
  last session completed at 14:26. It was not entered. This branch avoids the files of
  Codex's lane.
- **Producer writer.** No other Producer writer was active.

## What was actually missing

Twenty-seven qualified overlay facts exist, but PR181 pairs only inside that stream:
zero pairs on October20/22/23. Q3/2026 has no retained focus-cohort statement bytes, so
no Q3 acquisition was attempted. The October13 GrokBot/agent dossiers list KBC as the
only opened Q3 filing, and KBC is outside the cohort. The measured gap is cross-document
pairing with the already qualified FY2024 originals.

## Prior-period rows (18 read, 14 qualified)

| Issuer | Prior rows qualified | Blocked (reason) |
|---|---|---|
| HPG | NI FY2022/2023/2024, revenue FY2024 | — |
| FPT | NI FY2025 (same year as current; no pair) | — |
| PVD | NI FY2022/2023/2024 (USD) | — |
| PAN, POW, QNS | NI and revenue FY2024 | — |
| NVL | NI FY2024 | Revenue FY2024: printed "Doanh thu thudn"; OCR damage is never repaired |
| VNM | — | NI and revenue FY2024: `annual_report` class, unit and label identity not proven |

HPG FY2022/2023 governed rows already carry the line-60 values of the semantic correction.

## Comparative observations (13 candidates, 4 without blockers)

| Document | Prior column | Status |
|---|---|---|
| HPG FY2025 p10 | revenue 138,855,112,131,387 | Equals the P3-E original FY2024 value |
| HPG FY2025 p10 | net income `1².0²0.0²3.6²1.²71` | `OCR_NUMERIC_AMBIGUITY` |
| FPT FY2025 p12 | revenue 62,848,794,351,367, labels `2025/2024` | Unblocked candidate |
| PVD FY2025 p9 | revenue 9,288,059,307,546 and NI 697,970,710,425 (VND, `Năm nay/Năm trước`) | Unblocked candidates |
| PNJ, PVD, VRE H1/2026 | H1/2025 columns labelled `Kỳ trước` | `COMPARATIVE_PERIOD_LABEL_NOT_YEAR_BOUND` |

## Before/after (October20/22/23, identical for each)

| Issuer | Before | After |
|---|---|---|
| HPG | UNKNOWN | MEASURED: revenue FY2025/FY2024 +12.43%; NI +29.08% |
| FPT | UNKNOWN | UNKNOWN: no qualified FY2024 revenue |
| PVD | UNKNOWN | UNKNOWN: FY2024 originals are USD, FY2025 is VND; no FX |
| PNJ, VRE | UNKNOWN | UNKNOWN: no qualified H1/2025 original |
| Others in cohort | no admitted current income | UNKNOWN |

Both HPG pairs are audited consolidated facts from different documents.

- **Revenue.** The comparative column matches the original after the observation becomes
  known. Sealed cutoffs predate the re-read, so they show `NOT_AVAILABLE`.
- **Net income.** The comparative cross-check is OCR-ambiguous. The original is
  independently qualified, so the pair stands with that limitation.

At the prospective 2026-10-26 cutoff, the disabled gates would preview:

- **Comparative-column gate.** FPT revenue +11.56%; PVD revenue +17.32% and NI +50.66%.
- **D-1 gate.** PNJ Q2 revenue up and NI down; NVL Q2 NI.

None reaches any consumer.

**Not changed.** TTM: no issuer has qualified standalone quarters, so it stays UNAVAILABLE
everywhere. Valuation: HPG share basis stays ineligible
(`CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN_THROUGH_PRICE_SESSION`), and valuation does
not read the pairing. Trajectory `earnings_direction`, votes and posture are unchanged.

## Historical parity

- **October23.** `project_session` without inputs reproduces the sealed identity `…ae8a8d02fc7ac469`.
- **October20/22.** Sealed by pre-PR181 code. Unmodified main and this branch produce the
  same non-sealed identities (`…ef40b904530bb9b0`, `…c2d4f784ab6535ab`). The difference
  is not caused by this change.
- **With inputs.** The delta is additive-only: removing the nested pairing and its lineage
  hash restores the plain projection.
- **Sealed files.** All three sealed files hash identically after replay.

## Validation

New suite: 14 tests, covering:

- wrong comparative period;
- wrong scope and currency;
- the D-1 tier;
- quarter, YTD and H1 mixing;
- a misidentified OCR row and a shared token;
- false reconciliation;
- restated replacement;
- historical known-at;
- missing components and semantic correction;
- the no-data case;
- opt-in wiring;
- portable real HPG data.

Structural dependency ratchets pass after removing the one core-to-root import. Daily
lazy-import closure passes with a process-local hermetic profile; the unchanged host
binding refuses the non-active checkout, as recorded in PR181.

Full CI focused selection plus Daily, fundamental and financial suites (285 targets,
hermetic markers): 6912 passed, 11 failed, 95 skipped. Breakdown of the 11:

- **Five frozen-source pins.** Caused by an edit to the frozen Daily caller. That edit was
  reverted; the five frozen-source and transition suites then pass.
- **Six that also fail on unmodified main.** One Level-2 materialization test, three
  post-close projection tests and two decision-convergence tests.

`test_market_wide_current_fundamental_research` fails only where the clean worktree lacks
gitignored `operations-review/` artifacts (for example the p2e entity classification).
Main, with those host files, passes the same tests. The edit to that module is opt-in and
was proven byte-identical.

## Owner decisions requested

1. **`OWNER_GATE_COMPARATIVE_COLUMN_AS_PRIOR_PERIOD_FACT`.** May an unblocked comparative
   column of a later audited/reviewed report, bound to the admitted row, stand as the
   prior-period value when no original is retained? This would add FPT and PVD annual
   directions now.
2. **Year binding for `Kỳ này/Kỳ trước` interim columns.** Without a decision, PNJ, PVD and
   VRE H1 stay blocked.
3. **`OWNER_GATE_D1_UNREVIEWED_QUARTERLY_DIRECTION_PREVIEW`.** A non-voting D-1 direction
   display (D-1 amendment).
4. **Q3/2026 acquisition.** Bounded acquisition from approved issuer routes once issuers
   publish. Quarterly statements are unreviewed, so they would enter the D-1 tier only.
5. **Daily activation.** Wire `load_prior_period_inputs` into the frozen Daily caller
   through the E2/E3 source-transition mechanism, after PR183 settles that fixture. Until
   then the pairing is reachable only through explicit `project_session` callers and
   replay.
6. **Trajectory population.** Whether the official trajectory may carry the research
   direction. It feeds triage and strategy, so it is not done here.

Authority effect NONE; production writes zero; no Daily, merge, deployment or dashboard.
