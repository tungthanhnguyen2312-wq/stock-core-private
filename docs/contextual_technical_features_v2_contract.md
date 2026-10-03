# Contextual technical features V2

`contextual_technical_feature_set/v2` and `contextual_technical_inputs/v2` are pure,
non-voting descriptive siblings of the frozen V1 contracts. The paired milestone
starts from main `bb3dea293ce9c7f757d3bd9e6f1f9fb22af82517`. Authority effect:
`NONE / DESCRIPTIVE_SEMANTIC_VERSION_MIGRATION_ONLY`.

`contextual_technical_dispatch.py` selects V1 for production sessions before
October 3, 2026 and V2 for subsequent newly constructed sessions. This date is a
version boundary, never a first-capture marker. Each new projection contains one
technical version. Historical V1 readers remain available. A mixed batch raises
`TECHNICAL_VERSION_MIXED`; an unknown version fails explicitly. An explicit V2
October 2 build is labeled `REPLAY_DIAGNOSTIC` and `NON_AUTHORITATIVE`.

## Frozen ownership and primitives

`contextual_technical_features.py`, `volume_and_flow_context.py` and
`technical_structure_context.py` retain their exact source content and behavior.
The V2 sibling reuses only stable morphology, numeric fitness, distributions,
level geometry and the unchanged tactical owner's bounded formulas. It does not
build a complete V1 context and relabel it. Canonical bar identities, source,
price basis, corporate-action restrictions, native volume units and knowledge
cutoffs remain binding. Every constituent within a feature's required window is
checked; missing or incompatible rows are never skipped to manufacture history.

Strict tactical swing comparisons, `EARLY_BULLISH_REVERSAL` /
`EARLY_BEARISH_REVERSAL`, BOS/CHoCH, pivots, breakouts, posture policy, triggers and
invalidations are unchanged. `tactical_owner_market_structure_state` is retained
verbatim for reconciliation. V2 descriptive swing relations use the owner's
actual last and previous confirmed high and low prices: `HIGHER`, `LOWER`,
`EQUAL`, `UNKNOWN`. Exact equality has no tolerance. Their composite is HH/HL,
LH/LL, HH/LL range expansion, LH/HL range contraction, unresolved equality,
insufficient confirmed swings or unknown. HH/LL and LH/HL do not imply reversal.

Trend is `UP`, `DOWN`, `NO_CLEAN_AGREEMENT` or `UNKNOWN`. A qualified SMA20 and
existing five-bar slope must agree with price for UP/DOWN. Without qualified
continuous comparability, an actual confirmed HH/HL or LH/LL sequence can supply
the descriptive reading; insufficient swings stay unknown. The old `RANGE`
reading becomes `NO_CLEAN_AGREEMENT`.

## Range and setup

`range_consolidation` explicitly names `BOUNDED_CLOSE_RANGE_DURATION`, preserving
the owner's bounded trailing-close algorithm, boundaries, range duration and
ATR normalization. Its states are `RANGE_FORMING`, `RANGE_ESTABLISHED`,
`RANGE_EXITED_BY_CLOSE`, `FAILED_BREAKOUT_CONTEXT`. It makes no classical base or
price-target claim. The volatility vocabularies distinguish `OHLC_RANGE_*`,
`CLOSE_RANGE_*` and `REALIZED_VOLATILITY_*`.

Setup uses the following first matching rule. R11 records
`NO_SETUP_RULE_MATCHED`, plus precise missing trend/swing reasons.

| Rule | Condition | Setup |
|---|---|---|
| R0 | Structure unusable | UNKNOWN / STRUCTURE_UNAVAILABLE |
| R1 | Actual failed breakout | FAILED_BREAKOUT_DETERIORATION |
| R2 | Bearish CHoCH, bearish BOS or breakdown event | BEARISH_STRUCTURE_BREAK |
| R3 | Bullish CHoCH | REVERSAL_ATTEMPT |
| R4 | Bullish BOS | CONFIRMED_IMPROVEMENT |
| R5 | Actual re-entry above support | EARLY_REPAIR |
| R6 | LH/LL or DOWN reading | CONTINUING_DETERIORATION |
| R7 | Beyond the owner's extension threshold | EXTENDED |
| R8 | HH/HL and UP | ESTABLISHED_TREND |
| R9 | Established bounded range | RANGE_CONSOLIDATION |
| R10 | No clean agreement and expansion, contraction or equal swings | SIDEWAYS |
| R11 | No rule matched | UNKNOWN |

Each frame exposes swing, BOS, CHoCH, breakout, event, slope and trend availability,
including unavailable-frame diagnostics. Conflicts preserve contradictory facts;
they do not create votes. Unknown trend does not default to sideways. Bearish
events precede range consolidation. Early repair requires actual re-entry.

`context_observations` contains orientation-free support/resistance tests, closed
range locations, boundaries and an actual prior-close-above-pivot retest.
Supporting/contradicting/confirmation/invalidation lists and `repair_context` are
absent. Pattern labels remain secondary morphology without action or predictive
authority. Local volume retains measurements, distribution, mean/median ratios,
status, native unit and source/window pointers. Its definition is
`LAST_20_INCLUDING_CURRENT`; participation interpretation belongs to Volume & Flow.

## Temporal and multi-timeframe fitness

Daily distinguishes current session, stale observation and no observation. W/M
distinguish current completed period, immediately previous completed period,
stale older completed period and no completed period. Selected/reference/previous
period bounds use canonical civil week/month arithmetic. `periods_behind` counts
civil periods; stale daily observations do not invent trading-session counts.
Later-period completeness counts describe actual retained canonical periods.

Multi-timeframe comparison requires usable structure and appropriate temporal
fitness: current D, current or immediately previous completed W/M. Compatible
price basis, unit, instrument and source are required for comparison. No eligible
frame and one frame have distinct states. Two frames distinguish same reading,
opposing UP/DOWN and different non-opposing readings. Three frames additionally
name opposing readings present. UNKNOWN and NO_CLEAN_AGREEMENT do not establish
opposition. Basis mismatch is explicitly not evaluated. There are no weights,
scores or automatic decision implications.

`VOCABULARY_MANIFEST` is machine readable. Strict verifiers and exhaustive mapping
tests reject unknown future semantic values. Product attachment follows standing
decision construction and identity calculation. The normal full T0 retention
path keeps the actual attached V2 projection; decision identity excludes this
explanation. Existing T0 bytes and V1 identities never migrate in place.

## Acceptance and future gate

The [combined retained acceptance](internal/TECHNICAL_VOLUME_FLOW_V2_MIGRATION_ACCEPTANCE.json)
records all 1,683 decisions, 1,503 technical contexts, swing ties, owner/V2 matrix,
setup transitions, availability, temporal/MTF states, representative cases,
foreign/cohort coverage, exact policy parity and measured performance. Scratch
batches are indexed/streamed, not stored per ticker. No source acquisition, live
Daily, production publication or historical T0 registration occurs.

`FIRST_REAL_POST_RELEASE_CAPTURE_ACCEPTANCE` remains pending. It must additionally
verify genuine exact V2 retention, paired V2 flow routing and exclusion of POST
evidence from T0. The existing PIT capture clock and eligibility ceilings remain
unchanged. Thesis Matrix Stage 1 is not started.
