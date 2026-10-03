# Volume and institutional flow context V1

Owner-authorized `VOLUME_AND_INSTITUTIONAL_FLOW_CONTEXT_V1`, starting from
`20b168fe518ee58044010af0e812976ae5ea3ab9`. Canonical contract:
`volume_and_flow_context/v1`; evidence items: `volume_and_flow_evidence/v1`.
This is one separate, identified, descriptive research product. It does not
change Integrated Decision, action policy, rankings, portfolio fields or source
authority. The portable retained acceptance is
[VOLUME_FLOW_RETAINED_ACCEPTANCE_20261002.json](internal/VOLUME_FLOW_RETAINED_ACCEPTANCE_20261002.json).

## Source and identity contract

`volume_and_flow_context.py` owns the pure producer. `volume_and_flow_retained.py`
owns the retained adapter. Both are provider-free. The adapter receives explicit
source/runtime roots, verifies canonical content addresses and the frozen event
and classification bindings, and parses each price/technical corpus once.
Canonical histories are held for one instrument at a time. A single read-only
SQLite date index supplies the existing foreign-store continuity reference;
it supplies dates, never price, volume or participant measurements. When that
reference cannot cover an interval, the existing qualified non-exhaustive
completed-session fallback can prove only its standing narrow adjacency cases.
Silence in a non-exhaustive registry never means a missing day was a holiday.

One session artifact contains the complete declared universe, instrument records,
evidence items and explicit aggregate denominators. Each item binds instrument,
session, domain/sub-domain, horizon, participant, source/provider, measure and unit
semantics, exact source/technical identities, actual/required observations,
freshness, temporal/basis fitness, continuity, coverage scope, knowledge stage,
allowed use, status, blockers, descriptive technical relationship and content
identity. Canonical hashes use sorted JSON without wall-clock build time.
Reversed source inputs are normalized deterministically; conflicting/duplicate
sessions, bad nested identities and incompatible source bindings fail closed.

`research_references` verifies a batch once and returns compact identified owner/AI
references. The normal canonical post-handoff observer writes
`operations-review/volume-and-flow-context-v1/<session>/volume_and_flow_context.json`
and then adds its reference to the existing handoff bundle. It follows the
existing Velocity → foreign enrichment → flow/price observer sequence, adds no
acquisition and never inserts late evidence into Integrated Decision. Observer
failure is explicit `UNAVAILABLE` and non-blocking. Immutable artifact conflicts
are reported rather than overwritten. There is no action-path import from this
context producer.

## Volume measurements

`contextual_technical_feature_set/v1` continues to own native-volume current/mean/
median ratios, own-history distribution/rank and trend. Native-volume items
reference the exact verified feature/frame identity and path; they do not
recalculate that feature or copy its raw measurements into another engine.
The referenced percentile is own history, never the older cross-sectional raw
volume percentile that mostly reflects issuer size.

The added bounded family has 5- and 20-observation trajectories. Each observation
is divided by its preceding 20-bar median: a complete trajectory therefore
requires 25 or 40 exact compatible canonical bars. Every row stays in the window;
missing, incompatible, unqualified or CA-blocked rows are never skipped.
The released technical volume family's fitness is an additional ceiling.
Daily session continuity must be proven; W/M require sufficient exact completed
canonical periods and consecutive period boundaries. Having a weekly/monthly
candle does not establish a rolling volume window.

The producer reports the ratio sequence, expansion/contraction counts, current
state streak, own-history empirical percentile, equal-end-half mean change and
ratio, and rising/falling/flat trend. For the odd five-observation window, the
two first and two last observations are compared; the middle observation is
excluded from that comparison, but retained in the sequence/rank/counts.
Expansion `>=1.3` and contraction `<=0.7` reuse the standing expansion/compression
convention constants in `technical_structure_context.py`; no thresholds are
tuned or invented. These categorical observations carry no directional thesis
vote or action authority. Zero reference medians are explicitly undefined.

Unknown native units remain `UNKNOWN`. Compatible within-series dimensionless
statistics remain usable as descriptive context. Exact source-qualified shares
remain shares, without changing the authority of the source. Cross-source units
and bases cannot be combined. There is no shares/lots/VND conversion, total
traded-value estimate, raw cross-ticker volume comparison or market volume share.

## Qualified foreign VALUE and unavailable participants

Foreign evidence uses the existing DNSE value-only store contract, raw VND session
cumulative buy/sell amounts and their exact difference. Every observation must
bind the qualified source contract; shares or other measures cannot substitute
for VND. Foreign volume and room are excluded from the analytical index.
The bounded windows are 1/5/10/20 actual sessions and retain exact sessions and
trailing proven contiguous depth. A gap or insufficient contiguous depth reports
`INSUFFICIENT_HISTORY` with specific continuity diagnostics; no historic session
is invented or interpolated.

Usable windows report buy, sell, net, gross, net/gross, cumulative/mean/median net,
positive/negative/neutral counts, bounded buy/sell streaks and persistence. Equal
end-half mean net differences are descriptive acceleration/deceleration.
Own-history net percentile requires the 20-session window; shorter windows expose
`INSUFFICIENT_HISTORY` for that field. Zero gross value leaves net/gross undefined.
There is no universal flow score, buying-pressure rating or directional blend.

Foreign value divided by total traded value remains `BLOCKED` because compatible
matched/negotiated inclusion in the denominator is undocumented. Qualified value
does not qualify foreign volume, liquidity, sizing or participant intent.
`PROPRIETARY`, `DOMESTIC_INSTITUTIONAL` and `OTHER` are represented by explicit
`UNAVAILABLE / SOURCE_NOT_QUALIFIED` items, never inferred from native volume or a
historical pilot. Observed flow never establishes smart-money, accumulation,
distribution, insider behavior, institutional conviction or motives.

Flow/price relationships delegate to `flow_price_divergence_shadow/v1` and its
existing record/state/persistence methodology. Exact-session V1.2 Velocity inputs
are necessary for price relationships. There is no second divergence method.
Technical × volume joins bind the existing breakout/retest state, base state,
structure direction and repair state with observed participation, or explicitly
return `TECHNICAL_CONTEXT_UNAVAILABLE`. They produce no action score.

## Knowledge-stage and future thesis interface

Field/item-level `T0_SEALED` or `POST_T0_ENRICHED` is authoritative. A batch built
after handoff may contain both. A native-volume reference is T0 only when the
existing valid immutable snapshot's exact `integrated_decision_at_t0` payload
binds the same verified contextual technical identity for that instrument/session.
Snapshot validation and binding extraction occur once per batch. Caller assertions
that a source was known earlier are insufficient. Newly calculated trajectories
remain post-T0 even when their inputs existed earlier. Foreign items are always
post-T0. `t0_projection` validates the artifact and selects only usable T0 items;
it cannot admit a post-T0 item through the enclosing batch's stage.

The October 2 feature batch is retrospective. The genuine October 2 T0 snapshot
is unavailable, so all real acceptance items remain `POST_T0_ENRICHED`; their
T0 projection is empty. No historical T0 is reconstructed or registered. Genuine
mixed-stage/T0 behavior is exercised through explicit synthetic snapshot fixtures.

The future thesis adapter can directly identify domain (`VOLUME` or
`PARTICIPANT_FLOW`), sub-domain, horizon, observed state, fitness, source identity,
participant, unit semantics, knowledge stage, freshness, blockers, technical
relationship, market/sector scope and content identity. The producer assigns
neither `SUPPORTS` nor `OPPOSES`; the future matrix policy owns that mapping.

## Market and sector denominators

Volume breadth partitions by exact source/unit/basis/method signature and uses
normalized within-series states. Only current usable items enter the numerator
and eligible denominator. Every aggregate reports total cohort denominator,
eligible denominator, expansion numerator, coverage numerator/denominator,
percentages, source-item identities and exclusion reasons. Sector partitions use
the existing classification authority/namespace/label tuple. No new taxonomy or
minimum coverage threshold is introduced; every scope is explicitly a cohort,
with `is_market_representative=false`.

Foreign aggregation is exclusively `FOREIGN_FLOW_COHORT_CONTEXT`, with explicit
cohort names/count, current-qualified numerator, outside-cohort count and
exclusions. Same-VND, same-scope gross-flow concentration uses the current
qualified observed cohort gross value as its denominator. Sector counts are
observed cohort counts, not sector breadth. `FOREIGN_MARKET_BREADTH` is never
generated, and one or two observed issuers never imply sector-wide participation.

## October 2 retained acceptance

Universe denominator 1,683; CurrentResearch scope 1,503; outside scope 180.
Daily native-volume reference coverage remains 1,252, including 873 current names.
All 1,503 native unit labels remain UNKNOWN. Unknown units block economic/unit
conversion but do not block compatible dimensionless statistics. Native volume
blocks: 76 CA, 174 insufficient history, one unusable source/OHLC; incompatible
unit/source blocks are zero in the real source set and exercised synthetically.

| Volume family | Usable own-history contexts | Current contexts | Required observations |
| --- | ---: | ---: | ---: |
| Daily native reference | 1,252 | 873 | existing 20 |
| Daily short persistence | 12 | 0 | 25 |
| Daily medium persistence | 2 | 0 | 40 |
| Weekly rolling | 0 | 0 | existing/new exact gates |
| Monthly rolling | 0 | 0 | existing/new exact gates |

Short-window blocks: 88 CA, 189 insufficient history, 1,213 continuity
(1,205 unverifiable / 8 proven gaps), one source unavailable. Medium blocks:
144 CA, 260 insufficient history, 1,096 continuity (1,091 unverifiable / 5 gaps),
one source unavailable. The 12/2 usable histories are stale; they establish no
current persistence claim. Existing W/M lookback/calendar/CA ceilings remain intact.

The exact current foreign cohort is EVF, FPT, HPG, NVL, PAN, PNJ, POW, PVD, QNS,
SSI and VNM. The runtime actually retains seven recent sessions: September 23,
24, 28, 29, 30 and October 1, 2. HPG/QNS/VNM additionally retain the five genuine
August 3–7 pilot sessions; those observations do not bridge the later gap or
qualify another participant category. There are 12 distinct observed dates across
the store, not approximately eight. All 11 names have a proven five-session tail
September 28–October 2. The September 25 gap is not skipped.

| Foreign window | Mature/current | Cohort denominator | Outside cohort |
| --- | ---: | ---: | ---: |
| 1 | 11 | 11 | 1,672 |
| 5 | 11 | 11 | 1,672 |
| 10 | 0 | 11 | 1,672 |
| 20 | 0 | 11 | 1,672 |

Ten/twenty-session maturity is explicitly insufficient. Each other participant
category has zero qualified and 1,683 explicit unavailable records. Foreign
price relationships are unavailable in the real source set because genuine
October 2 retained Velocity/T0 price context is absent; synthetic tests exercise
persistent selling with resilience and buying with weakness/confirmation.

The principal same-semantic volume cohort has 1,453 names, 873 current usable
observations and 318 expansion observations: coverage 873/1,453; expansion
318/873. The other semantic partitions have zero usable current observations.
All sector denominators and exclusions are retained in acceptance. Foreign
coverage is 11/11 observed cohort, never 11/1,683 market participation. No reported
aggregate establishes representative full-market or full-sector breadth.

Cases are first lexicographic matches without outcome filtering: A32 high relative
volume, AAT low relative volume, DSG improving persistence/base participation,
ANV breakout with expansion, DAT breakout with contraction, EVF insufficient flow
history, A32 outside foreign cohort. Their exact dates, freshness and fitness
remain visible. Real foreign selling/resilience and buying/weakness categories
have no match and use synthetic tests only.

Full-cohort proof checks the exact original Integrated Decision bytes/content hash,
all 1,683 standing decision identities and the prior technical acceptance's
posture/trigger/invalidation/portfolio comparison digest. No mutation occurs.
Source bytes and all 1,503 contextual technical identities remain unchanged.
Provider/network requests, acquisition, publication and historical T0 writes are
zero. Stage 0 changes only newly evaluated descriptive coherence: WEAKENING is
recognized, and unknown/data-limited/unhandled sector states cannot silently
establish full alignment. Taxonomy now keeps DNSE foreign volume semantically
unresolved with display-only use, matching the existing governing contract;
qualified VALUE remains separately research-usable. No producer state is renamed.

## Validation and release

Focused synthetic coverage exercises exact units, rejected cross-source volumes,
CA ceilings, relative median/rank/sequence/persistence/acceleration, zero references,
gaps, exact counts, ordering, foreign identities/gross/ratios/streaks, relationship
delegation, technical joins, mixed-stage projection, source tampering, cohort
denominators, explicit unavailable participants and non-blocking normal observers.
The new suites and Stage 0 suites are registered in Producer CI.

Implementation checkpoint `e5e25abb6efd63fb0fee706512d6197d6747d343`. Full local Producer selection:
2,160 passed / 16 platform skips / 14 retained-provider deselections / 37 subtests
passed (673.34 seconds). Final affected selection 260 passed; final volume/flow
suites 64 passed. All 1,503 retained contexts pass the final strict nested bindings;
reversing retained record order preserves analytical identity. Two retained replays
completed. Final replay: context build 247.291039 seconds; whole acceptance
452.780395 seconds; process-lifetime peak RSS 808,951,808 bytes; one session artifact
70,975,510 bytes; 420,076,048 input bytes and 1,333,531,241 decision bytes parsed.
The final run overlapped local Producer tests. The exact Stage 0 descriptive replay
changes 20 outputs: 16 recognize WEAKENING and four explicitly report unknown/data
limits (two state changes, two reason-only changes). Historical decision bytes are
unchanged. Final CI verification is authoritative in the release PR checks. Measurements
cover the retained context builder and full comparison, not a complete financial
rebuild or live Daily. Release requires all four exact-head Producer CI jobs,
one PR, merge-main CI verification and local main synchronization.

Exact next gate is `THESIS_EVIDENCE_MATRIX_AND_CONFLICT_ENGINE_V1_STAGE_1`.
It is not started and `queued_next` remains empty.
