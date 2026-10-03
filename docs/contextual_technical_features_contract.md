# Contextual candle and technical features

`contextual_technical_feature_set/v1` is an additive descriptive adapter over
`canonical_market_bar/v1`. Authority effect is
`NONE / DETERMINISTIC_DESCRIPTIVE_TECHNICAL_CONTEXT_ONLY`. It calculates no
recommendation, probability, target, universal score or participant intent.

## Bounded reconciliation

| Concept | Classification | Existing owner / adaptation |
| --- | --- | --- |
| D/W/M, cutoff, constituent, source, price/native-volume basis | REUSE_DIRECTLY | canonical_market_bars; one shared period series |
| Confirmed close swings, HH/LH/HL/LL, BOS/CHoCH, pivot, breakout/failure/retest | ADAPT_EXISTING | technical_structure_context/v2 pure V3 methods, independently per timeframe |
| Close-extrema support/resistance, base duration, compression, slope, close volatility | ADAPT_EXISTING | same V1/V3 methods and constants; no second tactical methodology |
| Native-volume median reference | ADAPT_EXISTING | mva_daily_research_bundle's within-series median convention |
| OHLC body/wick/location, observed gaps, true range/ATR, range distribution | NEW_PRIMITIVE_REQUIRED | contextual_technical_features; canonical qualified OHLC |
| Posture, trigger/invalidation, portfolio policy | REUSE_DIRECTLY | existing Integrated Decision and tactical owners, unchanged |

## Identity, evidence and fitness

Each timeframe binds instrument, as-of session, canonical source-bar identities,
constituent-identity digest, source, basis/units, cutoff/knowledge times, actual
lookback, corporate-action state, freshness and use boundary in an identified
input context. Each feature references that context and its precise bounded
calculation window, required/available lookback, status, reasons and allowed use.
No wall-clock run stamp participates. Canonical correction resolution precedes
features; equivalent/reversed input order yields identical values and bytes.

Daily uses the latest retained daily observation; its session remains explicit
and stale observations are descriptive only. W/M use only latest COMPLETE
calendar-qualified periods. Partial current periods remain visible but cannot
enter completed features. Invalid, incompatible or incomplete bars inside a
required window are never skipped to manufacture depth. Maximum retained
feature series is 252 bars; the existing swing owner retains its 250-bar cap.
All as-known/factor/calendar gates remain with the canonical bar owner.

Statuses distinguish AVAILABLE, DESCRIPTIVE_ONLY, INSUFFICIENT_HISTORY,
BLOCKED_BASIS, BLOCKED_CA_COMPARABILITY and SOURCE_FIELD_UNAVAILABLE. Undefined
zero-range/zero-denominator values remain null with NOT_APPLICABLE reasons.
Retrospective indicators remain current descriptive research, never historical
as-known. RAW morphology and observed gaps survive an observed CA crossing;
true range and comparable multi-bar interpretations are withheld. Raw rolling
continuous references require explicit qualification; an unknown event inventory
cannot establish economic continuity. Known unnormalized CA boundaries block
dependent structural windows. Qualified PIT-adjusted canonical fixtures use the
same engine; no real factor/source authority is promoted here.

## Measurements and descriptive conventions

Geometry includes OHLC, range, absolute body/direction, wicks/ratios, open/close
location, midpoint and distance. True range is max(high-low, abs(high-prior
close), abs(low-prior close)). ATR14 is the simple mean of 14 true ranges from
15 comparable bars, explicitly not Wilder smoothing. SMA20, five-bar SMA slope,
19-return realized volatility, existing self-relative volatility and 252-bar
high/low have independent lookback/fitness results.

Range compression/expansion reuses V3 0.7/1.3 constants. Support/resistance are
prior-window close extrema with exact contributing bar identities, age and
observation count; current OHLC tests/rejections are geometry around those
owned levels. Counts are exact extrema observations, not inferred touches.
Base duration/status and pivot-relative break/retest/failure reuse V3. Native
volume ratios/ranks remain dimensionless within compatible source/unit series;
unknown units are not converted to shares, lots or economic value.

Secondary labels use fixed primitive definitions: doji-like body/range <=0.1,
long-body >=0.7, rejection wick/range >=0.5; inside/outside and opposite-body
engulfing use explicit price inequalities. Every label exposes conditions,
source bars, timeframe, fitness and contextual evidence. Names have zero action
authority; Bearish Engulfing never implies SELL. No thresholds are tuned against
outcomes. Repair/reversal and D/W/M alignment are descriptive evidence states;
timeframes are neither averaged nor weighted.

## Integration and acceptance

Normal historical CurrentResearch construction computes canonical series once
and emits both its standing bar projection and contextual feature projection.
Integrated Decision verifies parent/nested identities, session/cutoff and exact
current source-bar binding once. It attaches context after standing decision
construction and references it on the existing TACTICAL_STRUCTURE evidence
axis. The existing policy/decision identity remains unchanged; full product
content identity changes additively under its standing contract. Prospective
retention keeps the enriched evidence axis without revising old T0 snapshots.

Milestone state is COMPLETE at implementation checkpoint
`db3670d9689b27bd2430233efdbc320c03accfbd`, from main
`66735a3f5df3e028bd0a2b0d9840d9caa8a91ade`. Release is gated on all four
Producer jobs for the final candidate and merged main; the final PR/merge identity
is bound by Git/GitHub, avoiding a self-referential checkpoint in this document.

## Real October 2 retained acceptance

[The single retained report](internal/CONTEXTUAL_TECHNICAL_RETAINED_ACCEPTANCE_20261002.json)
binds source content/byte hashes, cohort comparisons, feature-specific coverage,
canonical basis, fitness, deterministic cases and measured performance. The helper
`tools/run_contextual_technical_acceptance.py` uses the same canonical builder and
verified normal product adapter, under the offline provider/write guard. It uses
the frozen official event registry binding, not the derived event summary. It
parses each large corpus once, streams one record at a time and produces one
ignored compact feature batch, not one artifact per feature. The full financial
product is not rebuilt; normal historical construction, additive integration and
prospective retention are separately covered by hermetic product fixtures.

Full denominator is 1,683; CurrentResearch scope is 1,503. The other 180 remain
explicitly outside scope. Usable means AVAILABLE or DESCRIPTIVE_ONLY, never PIT,
economic-unit or action authority:

| Family | Daily | Completed weekly | Completed monthly |
| --- | ---: | ---: | ---: |
| Candle morphology | 1,453 | 898 | 560 |
| Observed gaps | 1,436 | 668 | 477 |
| Range volatility | 1,252 | 0 | 0 |
| Structure | 939 | 0 | 0 |
| Support/resistance | 939 | 0 | 0 |
| Base | 939 | 0 | 0 |
| Native-volume context | 1,252 | 0 | 0 |
| Any continuous-indicator child | 1,308 | 0 | 0 |
| Secondary morphology labels | 1,453 | 898 | 560 |
| Contextual interpretation | 939 | 0 | 0 |

Daily child coverage: ATR14 1,308; SMA20, 20-bar momentum and 19-return realized
volatility 1,252 each; five-bar SMA20 slope 1,225; self-relative volatility 1,170;
252-bar high/low zero. These available real series are RETROSPECTIVE_ADJUSTED;
qualified PIT-basis continuous children and usable real RAW series are zero.
Daily basis inventory includes one MIXED_OR_UNKNOWN blocked record and 49 without
a usable bar; W/M have 605/943 without a complete qualified period. Daily temporal
inventory is 907 current-session observations, 547 stale last observations and
49 unavailable (the mixed record is included in temporal inventory, not usable
candle count). All W/M selected periods have newer unqualified periods; the older
complete period remains explicit, never presented as October 2 complete history.

Known unnormalized CA windows block 389 daily structural/levels/base/interpretation
contexts, 76 daily volume/range windows and 52 entire continuous families. Daily
structure also has 174 insufficient histories and one unusable OHLC/basis record.
Weekly structure has 886 incomplete constituent windows, 12 short windows and 605
without a complete period. Monthly structure has 560 short windows and 943 without
a complete period. The governed session ledger ends September 4; an October
forward calendar cannot repair September or older periods. Unknown native-volume
units support only within-source dimensionless ratios. No missing values, factor
authority or calendar coverage are fabricated to increase coverage.

Representative cases are selected by first lexicographic matching ticker without
outcome filtering: AAM mature trend (66 matches), AAA established base (727), ABI
early repair/reversal (196), AAN deterioration (149), ANI insufficient history
(174) and A32 CA blocker (389). A32's latest observation is September 30 and ANI's
is September 3; those case dates/freshness remain visible. Real D/W/M disagreement
matches are zero because W/M structural windows are blocked. Divergent/aligned/
partial/unknown implementation cases are covered by synthetic canonical fixtures;
no synthetic case is represented as retained evidence.

Full-cohort before/after comparison verifies all 1,683 original decision identities
and exact records after removing only the two authorized additive adapter fields.
Policy, triggers, invalidations, portfolio fields, postures and denominator have
zero deltas. Unchanged posture distribution: AVOID 505,
INSUFFICIENT_CURRENT_RESEARCH 479, WAIT_FOR_CONFIRMATION 425, EARLY_WATCH 203,
HOLD_DO_NOT_ADD 27, INITIATE_ON_BREAKOUT 25, HOLD 11, ACCUMULATE_ON_RETEST 8.
The full product content address changes additively; standing decision identity
semantics remain unchanged. Every input byte hash is unchanged; provider/network
calls, historical T0 writes and canonical publication writes are zero.

Measured final replay: feature-build stage 263.848897 seconds (including source
stream/hash/setup); whole acceptance 489.829623 seconds; process-lifetime peak RSS
485,609,472 bytes (about 463.11 MiB). One 301,674,710-byte price corpus and one
1,333,531,241-byte decision corpus are parsed once; the member buffer cap is 16 MiB.
These are offline acceptance measurements, not live Daily or whole-product timing.

Validation: 92 new primitive/contract/integration/streaming cases; final focused
affected selection 298 passed / three retained tests deselected. Local hermetic
Producer selection 2,057 passed, 16 platform skips, 14 retained/provider deselections
and 30 subtests passed (523.37 seconds). Final exact-head CI runs the two new suites
alongside the standing Producer selection. Syntax, diff and roadmap checks are
required before release. Deterministic reversed input, genuine canonical PIT factor
fixtures, raw/retrospective/CA boundaries, complete/partial aggregates, nested
identity/source tampering, normal adapter non-regression and new immutable T0
retention are covered. No thresholds were tuned against outcomes.

Expected next proposal is `VOLUME_AND_INSTITUTIONAL_FLOW_CONTEXT_V1`, with explicit
owner selection/authorization required. `queued_next` remains empty and no next
milestone starts automatically. The retained PIT/raw/unit/calendar ceilings stay
closed until actual qualified evidence satisfies the existing use-scoped gates.
