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
The corrected replay identity is:
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
Research postures, fundamental states, financial composite states, peer-relative
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

236 focused/adjacent tests plus six canonical integration checks pass, covering source tampering, future/stale sessions,
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
