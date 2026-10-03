# Prospective PIT capture completeness V1

`PROSPECTIVE_PIT_CAPTURE_COMPLETENESS_V1` starts from main
`799f727d1d783cedcf5327ab8ff9a86478aa9096` under the October 3 owner directive.
Its terminal disposition is `PROSPECTIVE_PIT_CAPTURE_COMPLETENESS_COMPLETE`;
authority effect is `NONE / CAPTURE_COMPLETENESS_ONLY`. This release lets future
Daily operations begin a truthful maturity clock. It grants no signal evaluation,
backtest, execution, source promotion or trading authority.

Implementation: `prospective_pit_capture.py`,
`prospective_pit_capture_retention.py`, `governed_session_chain.py`, and the existing
Daily/eligibility/feedback consumers. One bounded
[offline acceptance artifact](internal/PROSPECTIVE_PIT_CAPTURE_COMPLETENESS_ACCEPTANCE.json)
records actual retained evidence separately from synthetic fixtures.

## Immutable capture and the first marker

Existing market receipts, snapshots and T0 records remain byte-for-byte immutable.
The compact companion references their original identities and canonical hash
domains; it does not copy full OHLC history or overwrite old receipt fitness.
`operations-review/prospective-pit-capture-v1` holds exact families for bindings,
listing observations, later verifications, complete sessions, readiness, calendar
revisions, and the first marker. Old and new companion-free receipts never acquire
missing evidence merely through elapsed time.

The release boundary `2026-10-03` is only an earliest permitted session. It is not
a fabricated first capture. A companion must bind the exact original ticker,
session, snapshot, observation and immutable receipt identity; actual provider,
route, normalized request shape, provider-payload hash, canonical transform,
representation fingerprint and actual I/O knowledge time are retained. The native
payload hash uses its declared canonical payload domain, not an invented raw HTTP
byte hash. A request identifying another symbol is refused.

The conservative capture window runs from 15:00 Vietnam time on the session to
09:00 the next civil day. It does not extend over weekends or holidays. Companion
knowledge, listing knowledge and completion must be within that window. Later
records remain later evidence; a forged extended window cannot backfill T0.
The earliest complete companion establishes effective capture knowledge; original
request time alone cannot establish it.

`first_complete_capture_session.json` is write-once, published only after an actual
Phase B `READY` gate with verified gate/source identities, supported governed
calendar, exact immutable market/listing/binding batches, and at least one capture
complete ticker. The complete-session record binds those batches, actual completion
time, exact-session coverage, market snapshot and any genuine T0 decision snapshot.
Replay cannot move the marker or rewrite a complete record. A price manifest,
projected session, incomplete capture or software release never establishes it.

## Representation and permitted scale use

| Tier | Required evidence | Scope |
|---|---|---|
| `ECONOMIC_UNIT_DOCUMENTED` | Actual scoped provider/route/field/unit documentation identity, known before the bar | Only documented economic uses with their other gates |
| `SOURCE_NATIVE_SCALE_CONSISTENT` | Homogeneous OHLC representation, exact transform, route/request shape and stable fingerprint | Same-series registered invariant predicates |
| `UNKNOWN_OR_INCONSISTENT` | Missing, mixed or changing representation; unexplained integrity tripwire | No qualified scale use |

A literal `VND` payload claim, plausible price magnitude, official numeric ratio or
common market convention cannot establish documented monetary units. Stable native
scale never establishes global RAW, price-times-volume economics, liquidity,
transaction costs, VND thresholds or absolute cross-provider comparisons.

Calculation contracts classify `INVARIANT`, `COVARIANT_1`, and `NOT_SCALE_SAFE`.
Returns/log returns, close/SMA and breakout comparisons, normalized distance,
ATR/close and same-series structure comparisons are invariant under a common
positive scale factor. Absolute SMA/ATR covary; economic and cross-series
operations require independent semantics. This registry declares no signals.
The standing VNM signal retains its SMA50, RAW/volume/ACTIVE/CA requirements.

`K = 2.0` is a two-way adjacent-close integrity tripwire: a ratio above K or below
1/K makes the series inconsistent unless a qualified, executed official factor
with explicit ex-date, prior-binding/current-fingerprint identities and original
knowledge cutoff explains it within K. It never detects or repairs a unit.
Representation changes require new qualification; arbitrary factor magnitudes do
not excuse arbitrary jumps.

## Positive listing presence

Exact selected HNX official equity and HOSE stock-master observations supply
`LISTED_PRESENT_AT_SESSION`, exchange, raw status and literal unit claim with
source-row identity and actual knowledge time. Presence requires that observation
on the same local session and known at the relevant cutoff. Prior/later rows do not
establish same-session presence. Missing means `UNKNOWN`; neither a current status
code nor a normalized ACTIVE flag establishes an effective ACTIVE interval.

Future component requirements explicitly declare `membership_claim=LISTED_PRESENT`,
`membership_mode=POSITIVE_PRESENCE_EVERY_SESSION`, scale behavior and registered
calculation. Every required governed session needs matching positive listing and
exchange evidence. The old default ACTIVE-interval gate remains unchanged.

## Later official verification and multidimensional RAW

Separate verification consumes only exact already-retained selected operator
ledgers/raw bodies. Optional
`config/prospective_market_official_verification_registry.json` maps explicit
sessions to exact ledger paths; there is no newest-file search or official fetch.
Ledger and body hashes, official native row, original capture identities and actual
later verification time remain visible. Official seconds-based report dates and
native values are preserved without a `/1000` price guess.

States are `VERIFIED_MATCH`, `VERIFIED_MISMATCH`, `PENDING_OFFICIAL_EVIDENCE`,
`OFFICIAL_EVIDENCE_UNAVAILABLE`, or `NOT_VERIFIABLE_AT_THIS_SCALE`. Numeric ratios
are diagnostic unless both sides independently document comparable units.
Mismatch rows remain retained and counted, including older sessions and names
without complete captures. Later evidence never changes original T0 knowledge.

RAW dimensions remain independent: prospective observation/capture fitness,
representation tier, source basis claim, official match, scoped empirical
unadjusted finding, and CA comparability. Single-bar morphology requires less
evidence than continuous returns/rolling price transforms. Multi-session invariant
calculations require qualified interval CA comparability even if a caller disables
the optional CA flag. The future component gate currently accepts explicit
known-time, source-bound `NO_APPLICABLE_CA_PROVEN` interval evidence; missing proof
fails closed. Full factor qualification and existing stronger gates remain intact.
No combination here promotes global RAW, PIT backtest or execution authority.

## Calendar and shared completed-session chain

The existing bounded Daily `working_dates` request retains its exact response
bytes and actual response-completion time. It performs no additional request,
retry, crawl or calendar service. If the existing probe did not execute or yielded
no raw body, this feature creates no calendar receipt. The known retained October 2
schema/response hash is admitted only with its exact original knowledge time.
Verified calendar receipts require immutable raw/hash/date consistency and actual
API/documentation knowledge cutoffs; weekday inference is prohibited.

Overlapping approximately one-year windows retain older depth through their union.
Disagreements are explicit revisions with present/absent source identities.
Disjoint coverage is separate; neither a September gap nor inconsistent dates are
silently stitched. Actual captures and forward projected dates remain separate.

`governed_session_chain/v1` offers `next_n_sessions(after, n, as_of)`, strict
`window_ending`, and `realized_prefix_after`. Only verified complete records known
by the cutoff enter the chain. Missing required capture, calendar dispute and
unsupported coverage produce explicit states. Projected targets are never realized
evidence. Feedback returns, excursions, outcome conditions/maturity, outcome
measurement and learning use the same strict prefix for cohorts at/after the first
marker. Cohorts before that marker explicitly retain
`LEGACY_RETAINED_SESSION_MODE`, including their original sparse retained-session
semantics and immutable outputs. Future cohorts do not reuse legacy terminal-cache
proofs that permit sparse maturation.

## Normal Daily boundary and readiness

Selected listing observations are available before companion capture. Corporate
rollforward failure still retains immutable raw market evidence without making an
incomplete capture complete. After Phase B and genuine T0 retention, normal Daily
invokes one shared boundary: complete-session/marker publication then deterministic
readiness. The direct canonical post-close entry uses that same boundary. Readiness
references are additive returned fields and separate retained artifacts, excluded
from the sealed legacy Daily operation record to preserve replay identity.

Readiness states: `NOT_CAPTURED`, `CAPTURING`, `DEPTH_PENDING`, and
`READY_FOR_BOUNDED_EVALUATION`. The latter is an invitation for separately governed
component review, never evaluation authorization. Counts at 20/21/50/60/120/250
sessions describe contiguous compatible capture and positive-listing depth.
Per-ticker exchange, tier, official state, RAW allowed uses, CA blockers and top
exclusions accompany explicit gaps, mismatches and legacy incomplete counts.
Continuous-price and standing-signal readiness remain false without stronger
evidence. There are no new evaluation signals.

Calendar refresh tests the latest actually known source window from the current
capture/requested session against the actual registered maximum outcome horizon:
60 sessions (union 1/3/5/10/20/60). Insufficient forward coverage reports
`CALENDAR_REFRESH_NEEDED`. No buffer, invented scheduled refresh, daemon or monitor
acquisition is added.

The run-scoped index reads compact capture batches once, retains at most 250
history entries per ticker, and reads full receipts only for the latest day's RAW
state. All verification batches are streamed once so older mismatches stay counted.
Existing legacy eligibility reuses one market-version index without changing its
output identities. The compact companion stores one close integrity reference and
lineage, not another full historical OHLC corpus.

## CA seam, acceptance and release

CA result is `INTEGRATION_SEAM_ONLY`. Existing source-record identities do not
establish stable official event identities, linked terms, executed lifecycle and
original publication knowledge. A future event-version integration needs those
identities, actual first-observed time and explicit change lineage; existing
retained event observations remain available. No historical event investigation,
first-seen backfill or qualified factor is invented.

Offline acceptance verifies the exact R7 legacy corpus (21,092 receipt versions,
20,149 pairs, 1,334 tickers, 24 sessions), identical zero signal/gross regions and
exclusions, preserved 6,026 old scoped RAW bars, 908 original primary receipts,
protected decision/research/technical/flow source bytes and original retained T0
files. October 2 genuine T0 remains unavailable. Hermetic fixtures cover scaling,
cutoffs, listings, official mismatch, calendar revisions/gaps, strict shared
maturation, marker idempotence, normal Daily and legacy replay. Network/provider/
Vnstock-import counters are zero.

Synthetic load is explicitly separate: 256 tickers x 260 sessions, index capped at
250 sessions/64,000 pairs, 250 batch scans and 256 latest receipt scans. Its measured
times/peak memory are recorded in the artifact; it ran concurrently with local
Producer tests and is not a live Daily or full financial-product benchmark.

Actual release readiness: first marker null, complete sessions zero, all six depth
counts zero, standing eligible regions zero, and no evaluation authorization.
`FIRST_REAL_POST_RELEASE_CAPTURE_ACCEPTANCE = PENDING`: the first ordinary
successful post-release Daily must bind exact bars/listings/representation, retain
the existing probe if executed, publish one complete session and first marker,
advance readiness exactly one session, and keep later official verification
separate. Release does not wait for that future session or run a live Daily.

Release requires one substantial PR, all four exact-candidate Producer CI jobs,
merge, all four merge-main jobs, and synchronized local main. The implementation
checkpoint in `ROADMAP_STATE.json` is a real commit, not a circular claimed final
SHA. Next gate is `CONTEXTUAL_TECHNICAL_SEMANTIC_HARDENING_V2`, then
`THESIS_EVIDENCE_MATRIX_AND_CONFLICT_ENGINE_V1_STAGE_1`; both remain unstarted.
