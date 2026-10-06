# Historical temporal research panel foundation

Milestone `HISTORICAL_TEMPORAL_RESEARCH_PANEL_FOUNDATION_V1`.

Authority effect: none. This panel is rebuildable research memory. It is not PIT
backtest authority, not RAW_AS_TRADED, and not a recommendation.

Contract: `historical_temporal_research_panel/v1` in
`historical_temporal_research_panel.py`.

## What it reads

Immediate session directories under the retained canonical post-close root.
Each session opens only:

- `session_handoff_bundle.json`
- `opportunity_research_bundle.json`

It does not recurse into `enrichment/`, and it does not open integrated-decision
bodies, historical-context files, T0 snapshot bodies, or velocity files.
The projection is not persisted. Storage choice is an in-memory JSON projection.
Parquet and DuckDB were not adopted: this slice is a few thousand small rows.

## Semantic tiers

Every row is classified as `PIT_AUTHORITATIVE`, `RECONSTRUCTED_RESEARCH`,
`EXPLANATORY_ONLY`, or `UNKNOWN`.

PIT is accepted only when the caller supplies a qualification id and separate
knowledge and event dates. Adjusted or restated history stays
`RECONSTRUCTED_RESEARCH`. A missing PIT qualification stays `UNKNOWN`.
`raw_as_traded` on the output is always false.

Cohort membership copied from the retained opportunity bundle is
`RECONSTRUCTED_RESEARCH`. Outcome values stay `NOT_OBSERVED` unless a caller
supplies an observed qualified result on an implemented horizon (1, 3, 5, 10,
20) and an evidence population. Horizon 60 is refused. Knowledge date is not
copied from event date.

A corporate-action boundary marks only the named calculation
(`price_basis`, `share_count`, `eps_denominator`, `valuation`, `returns`) as
`INCOMPARABLE`. The ticker row remains.

## Retained slice measured 2026-10-07

Read-only index of
`operations-review/canonical-post-close-v1` on this host:

- session directories opened: 28 (`2026-08-25` through `2026-10-06`)
- indexed sessions with a cohort file: 26
- sessions with no cohort file: 2 (`2026-08-25`, `2026-09-05`)
- ticker rows: 2,445
- row tiers: `RECONSTRUCTED_RESEARCH` 2,445; PIT 0; explanatory row tier 0; unknown row tier 0
- tactical states: `BASE_BUILDING` 623, `BREAKOUT_READY` 504, `EARLY_REVERSAL_CANDIDATE` 1,318
- duplicate cohort names collapsed: 0
- rebuild identity repeated:
  `historical_temporal_research_panel:de0e224db0a4ac3aee1ca802c09bea7fb85c477a04630f4354c73122ebca899e`

Present on every indexed row: market-regime descriptor, breadth counts, tactical
state, evidence tier, an explanatory uncertainty marker, and a pointer to the
retained prospective snapshot identity. Explicitly missing on every indexed row:
OHLCV, price basis, technical structure, participation, flow, relative strength,
financial period, knowledge date, share count, EPS denominator, valuation,
corporate event, announcement date, event date, execution state, strategy state,
trigger, confirmation, invalidation, sector regime, leadership concentration,
risk appetite, and outcome. Those gaps are not filled.

Focus names use the same generic cohort index. Retained membership counts:

| Ticker | Rows | Status |
|---|---:|---|
| HPG | 5 | PRESENT |
| PAN | 5 | PRESENT |
| POW | 10 | PRESENT |
| SSI | 4 | PRESENT |
| EVF | 5 | PRESENT |
| FPT | 3 | PRESENT |
| NVL | 0 | NO_RETAINED_COHORT_EVIDENCE |
| PNJ | 0 | NO_RETAINED_COHORT_EVIDENCE |
| QNS | 17 | PRESENT |

NVL and PNJ are absent from the retained entry-relevant cohort lists. No rows
were invented for them. `UPTREND_CONFIRMED` names are not in the small
opportunity bundle, so that state is outside this slice.

Primary consumer intended next: the outcome and calibration engine. This module
does not compute cohort metrics and does not rewrite production thresholds.
