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

These are fixed T0 analytical close boundaries. They are not live orders, stops,
an execution engine, or a new historical T0 reconstruction. Existing immutable
prospective snapshots remain unchanged. Dynamic watchlist rules remain explicitly
non-evaluable by the fixed-close evaluator.

## Replay checkpoint

The base implementation exactly reproduces the retained integrated identity:
`integrated_investment_decision_product/v1:cd0c92321fbef001be15477b876f46f3f1ab82961ce28b091daeb43a168d620f`.
The corrected replay identity is:
`integrated_investment_decision_product/v1:bbe1eadf8d2c03fc3e5a40187a3c01b2d9d16c76b0a7144eeeba554b909d86dd`.

| Measurement | Before | After |
|---|---:|---:|
| Integrated denominator | 1,683 | 1,683 |
| Evaluable structural triggers | 100 mixed watchlist conditions | 388 V3 conditions |
| Evaluable structural invalidations | 37 watchlist conditions | 845 V3 conditions |
| Delivered integrated denominator | 1,683 | 1,683 |
| Serialized trigger/invalidation conditions preserved in delivery | 0 / 0 | 1,683 / 1,683 |
| Summary/axis falsely AVAILABLE for P/E-diagnosis-only context | 74 | 0 |

The old count of 100 includes evaluable watchlist conditions on records without a
displayed V3 trigger. It is not the old count of structurally coherent triggers.
Every corrected evaluable condition equals its displayed structural level.
Research postures, fundamental states, tactical phases, evidence currency,
counter-thesis and exact-capability blockers are unchanged across all 1,683 records.
All decision identities change deterministically because source/condition provenance
changes, including unavailable conditions. No retained identity is rewritten.

HPG, VCB, SSI, POW and AAA are retained representative traces in the local replay
summary. For example, HPG's bearish invalidation preserves its swing-high method
and above-level direction; POW retains its bullish support invalidation direction.

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

179 focused/adjacent tests plus six canonical integration checks pass, covering source tampering, future/stale sessions,
incompatible contracts, missing direction/levels, non-finite values, bearish
comparators, watchlist divergence, downstream non-escalation and retention isolation.
Python compilation and whitespace checks pass. Retained input bytes and the
retained Daily product remain unchanged. No provider calls, publication, database
write or authority promotion occurs in the replay.

The final replay attributes every changed record field to condition serialization,
method propagation or their downstream identity/status references: zero unexplained
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
