# Canonical market bars and CurrentResearch

`canonical_market_bar/v1` is a pure projection over retained daily observations,
not an acquisition or storage framework. `canonical_market_bars.py` owns D/W/M
periods, identities and conservative fitness. Existing tactical calculations and
Integrated Decision policy remain their existing owners.

Daily values are copied exactly. Weeks use Vietnamese civil Monday–Sunday bounds;
months use civil month bounds. Civil arithmetic groups observations only, never
creates a trading session. Multi-session open/close use the first/last actual
session, and high/low use exact extrema. Constituents retain their original row or
prospective snapshot identities, sessions and canonical bar identities. Exchange
and board come from the original observation; a current listing cannot backfill
an old instrument. Missing optional turnover stays missing; W/M does not infer it.

Only versions received by the explicit cutoff enter the bar. Future session dates
are also excluded. Corrections resolve by latest actual knowledge instant;
conflicting copies at the same instant are refused under `session_bar_integrity`.
Exact copies collapse. Ordering does not affect content identity. Daily observation
identity includes original provenance, so equal numbers with conflicting receipts
do not become an exact duplicate. Knowledge time is bounded by the latest selected
constituent and any timestamped calendar/event evidence used. Unknown daily receipt
times cannot qualify a cutoff-bound bar.

Price and native-volume compatibility require common source semantics and unit/basis.
Mixed price bases or instruments withhold OHLC. Common undocumented native volume
may be summed with exact original values retained, but remains `UNIT_UNDOCUMENTED`.
Mixed volume units/routes withhold volume independently. No lots/share conversion,
price repricing, inferred factor, or new source qualification occurs.

Source-qualified RAW stays RAW; naked RAW claims are explicitly unqualified.
Retrospective DNSE history stays `RETROSPECTIVE_ADJUSTED`, research only and
historically PIT ineligible. As-known, unknown, empirical and proxy labels survive.
`PIT_CA_ADJUSTED` is accepted only through the existing PIT factor/price validator,
with raw and factor lineage retained. The same derivation serves future qualified
inputs. Current real qualified factor count remains zero; requesting adjusted
PIT output returns `UNAVAILABLE / FACTOR_CHAIN_NOT_QUALIFIED`. This boundary does not
establish membership, signal lookback, execution or backtest eligibility.

Completeness means session coverage within the explicitly identified ledger scope.
It is separate from provider finality, whose undocumented state remains visible.
`COMPLETE` requires exact expected/observed sessions for the full period;
`INCOMPLETE_SESSION_COVERAGE` reports differences. Uncovered periods remain
`CALENDAR_SCOPE_UNKNOWN`. The current W/M is conservatively `PARTIAL_CURRENT_PERIOD`,
including its civil ending day. The governed replay ledger covers June 3–September 4;
its source scope is retained, and it is never expanded by weekday counts or price
presence. Its historical publication clock is undocumented and provides no PIT
calendar-time authority. The October 2 forward calendar cannot repair September.

Known price/share-affecting events retain exact event identities and crossing
warnings. Future events and informational AGM dates do not enter CA normalization.
Event absence means `UNKNOWN_EVENT_COVERAGE`, never proof of no action. Observed
RAW crossings retain traded values with comparability `NOT_ESTABLISHED`;
continuous-indicator use remains unestablished. No indicator program starts here.
Research use is the intersection of constituent permissions. Numeric availability
does not itself give a weak constituent a permitted analytical use.

The historical-context builder supplies `market_bar_research_projection/v1`:
latest observed D and latest completed W/M with explicit latest-period fallback,
counts and blockers. Integrated Decision verifies the parent and nested identities,
instrument, session and cutoff once per product and attaches the projection at
`market_sector_context.multi_timeframe` after decision construction. It is explicitly
non-voting and never changes posture or decision identity. Normal new Daily products
receive it after release; retained T0 artifacts are not rewritten.
The product attachment uses the actual snapshot acquisition cutoff. The existing
feature builders retain their standing calculation inputs; product request metadata
does not participate in the existing posture or decision-identity calculation.

## Retained acceptance

[Portable report](internal/MARKET_BAR_RETAINED_ACCEPTANCE_20261002.json) records exact
input hashes and actual counts. `tools/run_market_bar_acceptance.py` accepts explicit
evidence paths, parses each corpus once, blocks network/provider seams, and writes
only a separate report. The October 2 CurrentResearch projection uses October 1
retained observations; it is not a rewritten October 1 T0.

VNM/HPG/ALT contribute 249/249/97 daily observations. The prospective corpus has
18,514 versions, of which 21 VNM versions resolve to 20 daily sessions. Each of
VNM and HPG has 12 calendar-qualified complete weeks and two complete months;
latest complete W is August 24–30 and M is August. ALT has no complete W/M;
its September 29 dividend appears in the September monthly crossing with an
unknown calendar scope. Prospective VNM has no complete W/M under the retained
ledger and keeps its scoped RAW/as-known basis. All five input hashes remain
unchanged; three research attachments have zero posture/decision-field deltas,
zero T0 writes and zero network/provider calls.

[Production adapter report](internal/MARKET_BAR_PIPELINE_ACCEPTANCE_20261002.json)
also verifies the real historical-context builder over all 1,683 retained candidates:
1,453 have daily context, 898 have completed weekly context, and 560 have completed
monthly context. A bounded three-ticker Integrated Decision build using the actual
scratch Financial V2 and Tactical V3 evidence has zero differences in every other
decision field after attachment. The optional full financial/double-decision probe
hit a host `MemoryError`; the successful bounded adapter reuses the unchanged built
financial artifact and does not claim full-market financial replay acceptance.

Local Producer CI-equivalent validation: 1,560 passed, 30 subtests passed,
16 environment-dependent skips and 14 declared tier deselections. Compilation,
dependency-tier definitions, roadmap preflight and whitespace checks pass.

All 17 requested adversarial cases are covered by the focused bar tests, together
with future-correction, future-calendar/event/factor, original-instrument, nested
identity, weakest-fitness and whole-decision non-regression checks. Producer CI
includes this contract, session integrity and existing historical-context tests.
Retained-dependent historical tests now declare exact evidence-tier dependencies;
the omitted-session fixture explicitly removes checkout-dependent session selection.
No later proposal is authorized by completion of this milestone.
