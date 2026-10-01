# Current Research decision-quality program

Owner override: `CURRENT_RESEARCH_DECISION_QUALITY_AND_FRESHNESS_PROGRAM_20261001`.
Base: `59580f6cda300dce8013af284d2ce11e026e3029`.
Branch: `program/current-research-decision-quality-20261001`.
This is a program checkpoint, not a declaration that every Current Research gap is solved.
PR #28 and #29 remain independent pending-owner-merge corrections.

## Retained corpus findings

The governed completed session is 2026-09-30, with 1,683 integrated records.
The V3 projection supplies structural trigger and invalidation prices, while the
integrated product previously serialized conditions from the separate watchlist
entry classifier. Among records with displayed prices, 30 of 42 evaluable trigger
conditions and 35 of 37 evaluable invalidation conditions referenced different
prices. A watchlist condition can legitimately differ; attaching it as the
condition of another producer's measurement is the integration defect.

The V3 projection also dropped the producer's invalidation method. It therefore
obscured 542 swing-high/resistance and 303 swing-low/support measurements. These
have different analytical directions; a bearish structural thesis is invalidated
above resistance, not below support.

The Daily operation already delivers an integrated overlay alongside its narrower
entry-timing cards. Its shared projector, however, dropped both serialized
conditions from every integrated record. The AI handoff therefore retained prices
and condition identities/statuses in its decision input, without the actual
direction, reference level, reasons or separate watchlist rule needed to interpret them.

## Corrections and boundaries

1. The existing V3 projection preserves the exact invalidation method and exposes
   the direction already defined by the V3 producer. Unknown source semantics do
   not inherit a direction.
2. The integrated product serializes its V3 level and direction through the
   standing retained close-condition serializer/evaluator. It retains the old
   watchlist condition separately, verbatim. Source contract, self-identity,
   session, record eligibility, direction and finite positive level qualify this
   dependent use. Other axes and ticker coverage survive an unqualified condition.
3. The existing shared Daily/AI delivery projector retains the structural and
   watchlist conditions verbatim, including reasons and lineage. Other projected
   fields remain unchanged. No additional copied decision layer or card surface
   is introduced.
4. Second-pass valuation consistency: 74 records whose only valuation context is
   a P/E-not-meaningful diagnosis were labelled AVAILABLE by the summary/axis,
   while the standing decision-input dimension correctly reported PARTIAL.
   The owning summary now reports PARTIAL and preserves blocked-method reasons.
   Another usable multiple remains AVAILABLE; research posture is unchanged.
5. Financial history is not valuation history. The retained historical percentiles
   belong to current ratio, equity-to-assets, gross margin and net margin. Averaging
   them produced valuation-history labels on 1,195 records and a spurious valuation
   counter-thesis on 471. These cross-domain inferences are removed; the actual
   financial history remains in its own unchanged source. Comparable historical
   valuation inputs are not retained by the current-method-only producer.
6. The standing close evaluator rejects invalid numeric levels/observations and
   structural conditions evaluated from a different retained T0 session. It adds
   no outcome engine or reconstructed historical snapshot.
7. Missing sector leadership is UNKNOWN, not an observed IN_LINE state. The
   integrated summary and evidence axis retain upstream status, reasons, group
   classification key and coverage. Qualified market-wide breadth stays usable
   independently of the ticker's sector coverage gate.

These are fixed T0 analytical close boundaries. They are not live orders, stops,
an execution engine, or a new historical T0 reconstruction. Existing immutable
prospective snapshots remain unchanged. Dynamic watchlist rules remain explicitly
non-evaluable by the fixed-close evaluator.

## Replay checkpoint

The base implementation exactly reproduces the retained integrated identity:
`integrated_investment_decision_product/v1:cd0c92321fbef001be15477b876f46f3f1ab82961ce28b091daeb43a168d620f`.
The first five packages' replay identity is:
`integrated_investment_decision_product/v1:41d270a249602dbdb70c8fb7e875ed6e371236ba5f20c27c22c1141c3adfdf96`.

| Measurement | Before | After |
|---|---:|---:|
| Integrated denominator | 1,683 | 1,683 |
| Evaluable structural triggers | 100 mixed watchlist conditions | 388 V3 conditions |
| Evaluable structural invalidations | 37 watchlist conditions | 845 V3 conditions |
| Delivered integrated denominator | 1,683 | 1,683 |
| Serialized trigger/invalidation conditions preserved in delivery | 0 / 0 | 1,683 / 1,683 |
| Summary/axis falsely AVAILABLE for P/E-diagnosis-only context | 74 | 0 |
| Financial percentiles misread as valuation history | 1,195 | 0 |
| Spurious valuation-history counter-thesis | 471 | 0 |
| Unsupported neutral sector leadership labels | 845 | 0 |

The old count of 100 includes evaluable watchlist conditions on records without a
displayed V3 trigger. It is not the old count of structurally coherent triggers.
Every corrected evaluable condition equals its displayed structural level.
Through that five-package checkpoint, research postures, fundamental states, financial composite states, peer-relative
valuation, tactical phases, evidence currency and exact-capability blockers are
unchanged across all 1,683 records. Every counter-thesis item is unchanged except
the exact spurious `RATIOS_ELEVATED_VS_OWN_HISTORICAL_RANGE` tag removed from 471 records.
All decision identities change deterministically because source/condition provenance
changes, including unavailable conditions. No retained identity is rewritten.

HPG, VCB, SSI, POW and AAA are retained representative traces in the local replay
summary. HPG's bearish invalidation preserves its swing-high method and above-level
direction; POW retains its bullish support invalidation direction. HPG and POW's
high current-ratio/equity-to-assets percentiles no longer imply expensive valuation;
AAA's low financial percentiles no longer imply cheap own-history valuation.

The reusable replay is `tools/replay_current_research_structural_conditions.py`:

```powershell
python tools/replay_current_research_structural_conditions.py --retained-root $retainedRoot --output-root $externalResultRoot --session 2026-09-30
python tools/replay_current_research_structural_conditions.py --retained-root $retainedRoot --output-root $externalResultRoot --session 2026-09-30 --delivery-only
```

The output must be outside the retained root. It records baseline reproduction,
determinism, input hashes, coverage/distributions and representative traces. It
uses exact retained paths and the existing same-session queue resolver, never
provider acquisition or a recursive evidence scan. The final Daily queue differs
from the queue originally consumed by the integrated product; baseline identity
verification ensures the latter is reproduced rather than silently substituted.

## Verification and second pass

303 focused/adjacent tests plus six canonical integration checks pass, covering source tampering, future/stale sessions,
incompatible contracts, missing direction/levels, non-finite values, bearish
comparators, watchlist divergence, downstream non-escalation and retention isolation.
Python compilation and whitespace checks pass. Retained input bytes and the
retained Daily product remain unchanged. No provider calls, publication, database
write or authority promotion occurs in the replay.

The final replay attributes every changed record field to condition serialization,
method propagation, diagnosis availability, removal of cross-domain historical
inference or their downstream identity/status/reason references: zero unexplained
changes. Entity distribution stays 1,386 corporate, 28 bank, 41 securities, 13
insurance, one finance company and 214 unknown. Eighteen exact retained inputs
are byte-verified before/after. One sequential build observation is 11.56 seconds
for base and 5.24 seconds for corrected code; cache/order effects make this an
operational sanity observation, not a performance benchmark. No per-ticker I/O,
network acquisition, workers or polling is added.

The retained corporate axis contains no active stale catalyst/risk: it reports
historical/informational or unresolved context explicitly. No corporate freshness
change was justified by this corpus. Stronger liquidity, PIT, RAW_AS_TRADED and
sizing authority remain gated. New-session telemetry acceptance remains an external
time gate and is not polled by this program.

The fourth correction changes exactly 74 valuation summary/axis statuses, their
blocked reasons and downstream missing-factor explanations. Overall summary states
are 761 AVAILABLE / 74 PARTIAL / 848 UNAVAILABLE, versus 835 AVAILABLE / 848
UNAVAILABLE before. No diagnosis is discarded and no alternate method is blocked.

The further comparability pass keeps all peer-relative interpretations and financial
composite states unchanged. Valuation own-history states become UNAVAILABLE for
all records: the producer does not retain comparable valuation history. Exactly
367 false supporting tags and 471 false opposing tags are removed, with no other
supporting/opposing financial-composite reason changed. The explanatory unavailable
reason is explicit; financial-ratio histories themselves are not deleted or altered.

The adversarial outcome pass hardens the standing close evaluator used by the new
structural conditions. Boolean, non-finite and non-positive levels/closes cannot
produce an event. A structural condition's retained as-of session must match the
evaluation T0; moving it to an earlier start cannot introduce its level before it
was known. An invalid observation blocks only that observation, allowing a later
qualified close. Existing watchlist conditions without structural session lineage
keep their standing temporal contract. Feedback preserves the temporal blocker,
and calibration continues to use the same evaluator. These are counterfactual
integration checks, not claims of malformed retained prices or live outcomes.
At that outcome-hardening checkpoint, the full retained replay identity remained
`integrated_investment_decision_product/v1:af56722c6e8e1c34ae8b90efe3c5583cca1fe711aa2b1ef4c38439d2012bfea5`.

The research-priority second pass found no justified strategy substitution: its
FUNDAMENTAL_IMPROVEMENT rule requires revenue and earnings both expanding, while
the integrated Financial V2 direction combines different qualified dimensions.
All 22 eligible records retain comparable revenue/earnings pairs; 21 end in
2026-Q2 and ITD ends in 2025-Q4, within the governed four-quarter financial window.
Only five of these 22 have the integrated IMPROVING state. The difference does not
justify lowering requirements or replacing one measurement with another. No
strategy/priority code or authority was changed on this hypothesis.

The next retained-source pass removes unsupported IN_LINE labels on 845 records
(835 UNAVAILABLE, 10 DATA_LIMITED). All 838 observed leadership states remain
unchanged (22 LEADING, 764 MIXED, 52 WEAKENING). Market breadth, axis fitness,
postures and coherence states remain unchanged. The new status/reason/group fields
retain the producer's classification basis, including descriptive industry and
entity-class fallback groups; they do not promote a group into official sector
authority. The shared AI projector already carries this corrected evidence axis,
so no parallel delivery surface is added. Replay attributes only the summary/axis
fields and resulting content identities to this correction. The 26 populated
valuation peer cohorts contain 1,290 method members and no measured mixed
statement-scope/basis cohort; no speculative peer-rule change was made.

## Resumed tactical consistency package

The producer already computed whether the previous close was above the current
pivot, but discarded the measurement. The integration assumed every uptrend
TESTING_PIVOT was a retest of broken support, including 30 of 32 phase-labelled
retests with no retained close above the current pivot since its swing high.
The accumulation branch also accepted TESTING_PIVOT without a breakout witness.

The existing technical producer now retains `prior_close_above_pivot`. The existing
projection qualifies `pivot_retest_confirmed` only for an AVAILABLE TESTING_PIVOT
measurement with a true Boolean witness. The integrated phase and accumulation
branches require that witness and constructive structure. Unwitnessed resistance
approaches remain BREAKOUT_SETUP / EARLY_WATCH with their existing pivot confirmation
and invalidation conditions; no generic WAIT/AVOID is introduced for missing proof.
Failed breakouts and downtrends retain their standing adverse policy. The proof is
visible in the existing tactical evidence axis and therefore in shared AI delivery.
No pivot, proximity threshold, new classifier, or historical T0 is manufactured.

The same tactical synthesis incorrectly treated 92 triggered bearish BOS observations
as supporting evidence under TRIGGER_FIRED_CONFIRMED_BOS_TRIGGER. They now carry
BEARISH_BOS_TRIGGER_FIRED in opposing evidence and counter-thesis. Bullish BOS support
is unchanged; mixed pivot-breakout/bearish-BOS evidence keeps both actual directions.

| Measurement | Five-package checkpoint | Resumed tactical package |
|---|---:|---:|
| Integrated denominator | 1,683 | 1,683 |
| ACCUMULATE_ON_RETEST | 48 | 5 |
| EARLY_WATCH | 175 | 218 |
| RETEST_AFTER_BREAKOUT | 32 | 5 |
| BREAKOUT_SETUP | 258 | 285 |
| Bearish BOS triggers mislabelled as support | 92 | 0 |
| Material changed / unchanged records | — | 140 / 1,543 |

Exactly 43 postures change ACCUMULATE_ON_RETEST → EARLY_WATCH. Thirty-three phase
changes comprise 30 unsupported retests → setup and three witnessed early-bullish
tests → retest. All other posture counts stay unchanged. Fundamental states,
financial composite states, valuation, evidence currency, entity counts, market
regime/coherence and stronger authority blockers stay unchanged. Counter-thesis
changes versus the preceding checkpoint add only the exact bearish-trigger code.
All identity changes are deterministic source/condition/proof consequences, never
rewrites of retained identities.

The runner reproduces both the retained technical producer and original integrated
base exactly, then separately reproduces the preceding five-package identity.
It verifies every material transition against the newly-qualified producer witness,
every other changed field against precise allowlists, all 20 retained input hashes,
and all fixed-level/watchlist preservation checks. Final identity:
`integrated_investment_decision_product/v1:a2caac22ad63b0fd5ecdadb12255bfff2abcb8db3b897e0cfe926fe92d76d12c`.
Use the same reproduction commands above with an external output directory. The
runner is bounded explicitly to the governed 2026-09-30 diagnostic session. The
new producer output also appears as technical_structure_context_artifact.json.

Representative AAN/ASP change accumulation/retest → early-watch/setup; BTP keeps
WAIT but corrects retest → setup. HPG/VCB/SSI/AAA/F88 remain AVOID with explicit
bearish evidence; POW remains INITIATE_ON_BREAKOUT. All shared delivery records
preserve the corrected phase, opposing reasons, conditions and proof.

The measured integrated build is 4.85 seconds for original base and 5.29 seconds
for corrected code in one ordered replay: not a benchmark or evidence of Daily
degradation. The previous-close comparison was already computed by the producer;
retaining/consuming its Boolean adds no acquisition, per-ticker I/O or worker.

Next candidate: canonical Financial V2 already stores 1,676 READY_RESEARCH_ONLY
financial peer comparisons for 431 corporate issuers (all CURRENT under the standing
period policy). That wrapper field is not consumed by the integrated financial
context. Its engine-peer denominator is 1,492, versus the product denominator of
1,683; a future qualified join must retain all product tickers and explicitly keep
missing/specialist comparisons unavailable. Preserve method/cohort/period/minimum
count/freshness, source identity and proxy distinction. Never reinterpret financial
percentiles as valuation or create new direction votes. This candidate is mapped,
now completed by package 7 below; the program remains ACTIVE for continuation.

## Package 7: financial-peer evidence into decision and shared delivery

The canonical Financial V2 wrapper already produced financial peers, but Daily supplied
only its nested compact financial product to the Integrated Decision. The qualified
comparisons stopped at the wrapper. The existing producer now preserves its comparison
basis (entity, provider, method, period semantics, scope, currency/scale, fitness and
warnings) and partitions provider/entity/semantic differences explicitly. No new formula,
metric, classifier or peer engine is added. The retained numeric results and every
producer blocker reproduce unchanged against the exact retained engine identity.

The product adapter verifies canonical wrapper content identity, exact decision session,
nested compact content identity and engine linkage once. Each product ticker retains an
explicit peer context. Comparable current observations expose subject value, median,
tie-aware percentile, cohort, method and basis. Unavailable/proxy/specialist/stale/future
observations retain their status and exact reasons without creating negative evidence.
The peer context is added after posture/coherence and reaches the existing fundamental
evidence axis, Current Research dimension and shared AI/Daily projection verbatim. It
never adds votes, valuation-history labels, quality verdicts or actionable authority.

| Measurement | Package 6 | Package 7 |
|---|---:|---:|
| Governed decision records | 1,683 | 1,683 |
| Corporate records with consumed qualified financial-peer context | 0 | 431 |
| Usable financial comparisons consumed | 0 | 1,676 |
| PARTIAL / BLOCKED / UNAVAILABLE / NOT_APPLICABLE contexts | — | 431 / 962 / 207 / 83 |
| Posture / counter-thesis / WHY text changes | — | 0 / 0 / 0 |
| Records with no usable peer enrichment | — | 1,252 |
| Silent drops / unexplained changes | — | 0 / 0 |

AVAILABLE is zero because every eligible issuer still lacks at least one of the six
curated comparison metrics. Producer peers cover 1,492 engine tickers; the product
intersection is 1,476. Sixteen engine-only names are outside the governed decision
denominator. Missing product context remains explicit, never a selection filter.

ACC's margins lie above their same-basis peer medians while its adverse tactical AVOID
posture remains unchanged. AAA's below-median margins likewise do not force a posture.
HPG retains mixed above/below comparisons, F88/AAM their weak or absent evidence,
VCB/SSI corporate non-applicability, and small/period-incompatible cohorts their exact
producer blockers. Adversarial cases cover favorable ranks with failed confirmation,
unfavorable ranks with reversal, providers/periods/entities/scope/methods, missing peers,
small cohorts, stale/future periods, proxy distinction, wrapper tampering and delivery.

Replay tool: `tools/replay_current_research_financial_peers.py`, bounded to 2026-09-30,
uses external checkpoint/engine/output paths. It reuses the accepted package-6 projection,
verifies no-input product compatibility, qualifies existing peers, builds twice, verifies
precise per-record changed-path allowlists, and hashes all accepted retained inputs.
Final product identity:
`integrated_investment_decision_product/v1:e6aae60ff024441b7ff4c35d05af6905accf02f01dd4bec8b143ae561d6ffd14`.
Evidence-source identities change deterministically; retained identities are never rewritten.

Validation: 21 new adversarial tests; 185 focused/adjacent tests; prior 128-test
materialization/integrated/delivery gate; six canonical wiring checks. Python compilation,
roadmap and whitespace checks pass. No new provider acquisition, publication, database
write, liquidity/PIT/RAW_AS_TRADED/sizing promotion, cap/retry change or specialist expansion.
The same owner-authorized program continues with a bounded second pass.

## Package 8: corporate evidence availability and qualification

The Current Research corporate dimension treated every supplied summary as
research-qualified, even when the producer declared NO_QUALIFIED_CORPORATE_EVENT or
UNRESOLVED_EVIDENCE. The retained product has 404 no-event and 29 unresolved summaries
mislabelled in its `exact_or_qualified_dimensions`. Presence of a producer record is not
presence of qualified evidence. The existing dimension now respects producer fitness
and classification: no-event is BLOCKED/NONE; unresolved is PARTIAL descriptive context.
Informational/classified evidence remains usable, with its actual stale session preserved.
Missing/invalid/future evidence sessions cannot claim current qualification. No new
catalyst classification, event recency window or posture inference is introduced.

Full replay: 433 explanatory corrections, 1,250 unchanged records. Corporate dimension
counts change PARTIAL 1,507 / BLOCKED 176 to PARTIAL 1,103 / BLOCKED 580. All 1,683
per-ticker decision identities, postures, WHY text, counter-theses, peer comparisons,
fundamental/valuation synthesis and source events remain unchanged. The product identity
changes only for corrected explanatory dimensions and coverage:
`integrated_investment_decision_product/v1:7f05c3a73598d8b0921e43ed1a8abba270ea792abeeabb2be649fd995485d90b`.

The existing replay runner accepts `--corporate-qualification-checkpoint` pointing to
the accepted package-7 external output. It reproduces historical baseline using that
checkpoint's own projection namespace, builds the live full product twice, and checks
precise changed-path and per-record source-status assertions. No private source is copied
into a checkout or rewritten. Shared AI delivery carries the corrected dimension verbatim.

Eleven new tests cover no-event, unresolved, current informative/catalyst/risk/mixed,
stale, missing/invalid/future sessions, unavailable fitness, identity and delivery.
171 focused/adjacent tests pass. One existing supplemental private-evidence test cannot
run in the clean worktree and is excluded; no baseline evidence is repaired/recreated.
Authority promotion NONE; no acquisition/publication or cap/retry/scope change.

## Package 9: research-only fundamental observation provenance

Qualified working-capital and cash-flow amount trajectories reached the component view
as bare values without their fitness/period or the producer's reason for never voting.
The existing fundamental signal contract now retains `context_only_observations` beside
its unchanged legacy `context_only` values: source feature, producer value, period,
qualification/proxy, freshness, semantic definition and non-voting policy reason.
The existing Current Research components and shared AI projector carry this structure.
Future/unresolved-period/blocked observations cannot leak into the bare context view.
No direction vote, counter code, financial formula or policy epoch changes.

Full replay: 1,276 records enriched / 407 unchanged; working-capital direction 1,160,
working-capital level 1,276, free-cash-flow proxy direction 284, resilience composite 2.
All 1,683 decision identities, votes, states, postures, WHY text, counter-theses, peer
comparisons and corporate corrections remain unchanged. Existing producer policies
explicitly keep amount trajectories out of quality/action judgments.
Final product:
`integrated_investment_decision_product/v1:1a5d74eb50d35ebcc99ef3f14160bb76c0935700310a9ff83c6d53e47841247e`.

Seven new tests and 157 focused/adjacent regressions pass. The existing replay runner's
`--fundamental-context-checkpoint` points at the accepted package-8 external output;
historical checkpoint namespaces reproduce baseline identities without any retained
source mutation. Live builds are deterministic and every changed field is an additive
observation structure at the owning synthesis and its existing consumer component.

## Package 10: known periods of blocked peer comparisons

The peer producer intentionally omits its display `as_of_period` on blocked or
insufficient-cohort comparisons, but retains the underlying feature's period in the
comparison basis. The adapter previously labelled that evidence period unavailable.
It now copies the last retained basis period into the display/freshness envelope when
the display field is absent. It never reconstructs a report date or upgrades fitness.

Full replay corrects period metadata on 3,458 observations across 981 issuers:
3,286 NOT_COMPARABLE and 172 INSUFFICIENT_PEER_COUNT. 702 decision records are unchanged.
All comparison status/cohort counts, the 431 eligible denominator, fundamental policies,
corporate corrections, postures and per-ticker decision identities remain unchanged.
Known stale periods stay stale. Two additional tests prove small cohorts retain current
or stale basis periods while remaining ineligible for comparisons. 179 focused/adjacent
tests pass after the correction; the prior broader resumed tier passed 309 tests.

Final product identity:
`integrated_investment_decision_product/v1:cac6a6ad515bac4417c782965b29b3df469e64d7428e25699cc033c324ccbea7`.
The existing replay runner adds `--peer-period-checkpoint` for accepted package-9 output;
historical projection namespaces reproduce each required checkpoint and live output is
deterministic. Exact changed-path checks permit only period/freshness metadata, and
normalizing those fields back gives the identical prior context. All retained inputs
remain byte-identical. No acquisition, duplicate publication, source-authority promotion,
cap/retry change or HNX/UPCoM expansion occurs. Program remains ACTIVE for continuation.

## Package 11: counted market breadth in decision context

Bounded canonical-path measurement found market and sector labels already consumed,
but the market observation denominator and qualification stopped at the sector artifact.
The retained source observes 848 of 1,507 official members (659 missing, coverage
0.5627073656270737), MIXED_BREADTH. Sector status already survives: AVAILABLE 838 /
DATA_LIMITED 10 / UNAVAILABLE 835. Participation AVAILABLE 853 / NOT_AVAILABLE 830.
The governed session has no selected market-flow artifact: foreign, proprietary,
active-order, foreign-room and value-composition dimensions are unprovided, not neutral.
No new flow acquisition or inferred integration is performed.

The owning IID consumer now preserves the complete counted observation, source identity,
input lineage, session, limitations and PARTIAL status in market context, the evidence
axis and Current Research dimension. Shared delivery retains these structures verbatim.
Missing/inconsistent denominators, stale/future sessions and UNKNOWN/BLOCKED provider
status cannot supply a current market constraint. Stale sector labels are locally blocked.
Observed breadth remains contextual and never a forecast, cause or execution entitlement.

Full retained replay: 1,683 in/out, deterministic, zero drops/unexplained changes;
all 1,683 enriched, all per-ticker identities/postures/WHY/counters/phase/authority unchanged.
Source bytes unchanged. Product identity:
`integrated_investment_decision_product/v1:6d91e50f4d27d27047302faa397a6acb82b25c9f97e948bb1c2b81b3b4884208`.
Sixteen new adversarial tests pass; combined adjacent gate has 150 passes and one
unavailable historical private-fixture test (the empirical breadth runner reads its
absent August 20 artifact). That unrelated baseline is not repaired or repeatedly run.
October 1 is not a registered completed session; live telemetry acceptance remains pending.
Program stays ACTIVE; the next bounded review targets thesis/counter/confirmation coherence.
