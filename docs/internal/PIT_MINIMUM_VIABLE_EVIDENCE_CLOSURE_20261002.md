# Minimum viable PIT evidence closure — October 2

Disposition: `PIT_MINIMUM_VIABLE_EVIDENCE_CLOSURE_COMPLETE`.
The four bounded investigations have terminal, source-specific outcomes. This
closes the authorized engineering investigation; external evidence and prospective
time still prevent a qualified SMA50/VNM region. No stronger authority is promoted.

The owner explicitly authorized this successor after the foundation's COMPLETE /
no-NEXT state, from main `8463a2fc24b87cc38bd8c7a57c0f78685f664e41`.
The override was recorded in STATE/ROADMAP_STATE before acquisition or implementation.
Future analytical proposals and full historical Integrated Decision PIT remain deferred.

## Volume: values retained / source unit undocumented

Checked the existing DNSE request allowlist, OHLC parser, volume reconciliation,
prospective receipt fitness, actual retained metadata, current vendor SDK client,
and [first-party OHLC documentation](https://developers.dnse.com.vn/docs/dnse/get-ohlc-history/).
The documentation's linked endpoint schema was also retained, rather than relying
on its initially rendered page. It labels `v` as volume per candle, with integer
values; it does not declare shares, lots, contracts, monetary value, normalization,
or matched-versus-total treatment. The endpoint covers stocks, derivatives and
indices; those instrument types do not supply a unit by themselves.

Exact scope: DNSE `/price/ohlc`, raw `v` → retained normalized `volume`, existing
21,092 receipt versions, August 24–October 1. Unit/basis remain UNKNOWN; qualified
volume remains **0**. Neither the schema's examples nor empirical reconciliation
grant a unit. No numeric scaling or receipt rewriting occurred. Other routes such
as trades are distinct capabilities and do not document this field by implication.

Evidence: schema bytes SHA-256
`eda0639d0400aedc68d5acc2a0e95d3d53b63113e8be5bdb005fce8d59d99ab4`,
retrieved `2026-10-02T03:40:02.319072+00:00`, plus its exact parent page/runtime/main
asset and SDK captures in the [source ledger](../../operations-review/pit-minimum-viable-evidence-closure-v1-20261002/source_capture_manifest.json).
Terminal reason: `SOURCE_UNIT_UNDOCUMENTED`, class `EXTERNAL_DATA_NOT_AVAILABLE`.
Reopen only with an explicit first-party route/field/unit/basis and instrument-scope
statement; prospective qualification begins when that evidence is actually known.

## Active status: explicit current statuses, no effective membership window

Reused the verified current official universe, selected October 2 HNX enumerable
listing and HOSE stock-master receipts, and the retained HNX security-status/profile
cohort. The selected listing retention still has **1,522** known-time observations.
HNX list presence has no trading-status column; its first-trading-date field does
not establish a complete listing/suspension/delisting chain. HOSE's stock master
contains `listingStatusId`/`reason`; the observed code 11 and current listing presence
do not establish effective-time ACTIVE or a historical normal-status universe.

The adjacent HNX issuer profile has separate explicit control/trading fields. The
retained 50-name cohort includes one NORMAL/ACTIVE profile (LCD), 26 restricted and
23 suspended profiles. Its exact LCD profile receipt is September 13 at **09:08:14Z**,
not the base listing receipt at 08:06:20Z. Effective/publication dates remain absent.
This explicit current status observation is preserved; no point observation is
expanded into a session or SMA50 membership interval. The six residual names remain
profile-unavailable. Listing presence and a current price never become ACTIVE.

Two bounded VBB/KLB search requests to the original admitted autocomplete path were
refused by the transport's no-automatic-redirect rule; no retry or redirect was
followed. The retained manifest already identifies the localized adjacent search
surface and issuer profiles. Current profile/status observations resolve field
vocabulary but do not replace dated effective decisions or transition history.
HOSE stock-master, current HNX/UPCoM lists, HNX issuer profile and status enrichment
are separate surfaces; none of the checked evidence supplies the missing window.

Terminal reason: `EXPLICIT_CURRENT_STATUS_RETAINED / EFFECTIVE_MEMBERSHIP_WINDOW_NOT_ESTABLISHED`,
class `EXTERNAL_DATA_NOT_AVAILABLE`. ACTIVE_UNIVERSE_AT_TIME for market-session
lookback use remains UNKNOWN. Reopen with exact dated official decisions/transitions
plus actual known time and board scope; do not backfill from later listing state.

## Calendar: exact forward source window retained and integrated

The existing DNSE `working_dates` capability was queried once. The response has
**257 explicit dates, October 2, 2026–October 1, 2027**, payload SHA-256
`fce46fe3c9003d094ff22910d122622566d33d39076437c06a459f2511c33d6d`,
retrieved `2026-10-02T03:36:48.399047+00:00`. Its linked first-party schema describes
a one-year forward trading-date list, not a historical query. Schema SHA-256
`7ffc05d537f8f6bc982dbf8108960e6c6eb5337482710b4309d189919fb40858`,
retrieved `2026-10-02T03:40:02.445723+00:00`.

The reusable retention and existing acceptance path now support an immutable
source-scoped calendar receipt. Its availability is the later of the actual API
and documentation receipt times. The chooser uses only one known source window;
it does not stitch the older June–September 4 governed ledger across the uncovered
September interval. The CLI verifies the retained response bytes against the receipt.
Neither the source payload nor schema provides exchange-specific coverage, holiday
reasons or completion/finality. November 24, 2026 is absent despite being a weekday;
we preserve that omission without claiming why. No weekday calendar is inferred.

Exact evidence use: `DNSE_FORWARD_WORKING_DATE_IDENTITY`, DNSE securities-market
scope with exchanges unspecified, October 2, 2026–October 1, 2027, known no earlier
than `2026-10-02T03:40:02.445723+00:00`. This is independent of price, RAW, volume,
ACTIVE and exchange-specific calendar authority. Existing governed configuration is
unchanged. Future dates do not count as acquired price sessions.

September 5–October 1 remains `HISTORICAL_CALENDAR_OUTSIDE_SOURCE_WINDOW`, class
`EXTERNAL_DATA_NOT_AVAILABLE`; use requiring an exchange-specific governed calendar
has `GOVERNANCE_CONFIGURATION` plus missing scope evidence. Reopen that gap only with
exact earlier retained working-date receipts or dated first-party session evidence.

## CA: three exact candidates, zero qualified real factors

Reused the frozen cohort, ledger/factor contract, official acquisition manifest and
both original retained document bodies, whose hashes were verified. The exact VBB
2026 notice was fetched once for bounded document adjacency; its bytes are identical
to the retained September 30 receipt. It provides no linked execution document.
The October 2 corporate acquisition is an event-index window, not term/lifecycle
evidence for these old events; its HNX disclosure-index acquisition was not attempted.
No assertion is made that every possible issuer archive was exhaustively searched.

| Exact candidate | Existing positive evidence | Missing contract evidence / terminal outcome |
|---|---|---|
| VBB BONUS, ex June 26, 2026 | Official ex-date, 100:10 new-share ratio, source publication June 19 08:39 +07 | `EXECUTED_LIFECYCLE_NOT_ESTABLISHED`; notice is record-date-confirmed; no share-change identity linking an executed ledger event. |
| KLB STOCK_DIVIDEND, ex September 24, 2025 | Explicit index ex-date; official executed listing-change document and added/total registered shares, effective October 27 | `OFFICIAL_EVENT_LINKED_TERMS_NOT_FOUND_IN_RETAINED_SCOPE`; `PUBLICATION_TIME_NOT_RECOVERABLE` for the required historical cutoff. Share-count arithmetic is not substituted for event-linked terms. |
| VBB STOCK_DIVIDEND, ex June 27, 2025 | Explicit retained index candidate identity/ex-date | `NO_EXACT_RETAINED_DOCUMENT_BINDING`; event-linked terms, publication cutoff and executed lifecycle not established in checked admitted evidence. |

All outcomes retain the original factor engine's NOT_QUALIFIED classifications and
source-event identities. Missing rights/cash inputs are not fabricated for stock
events. Class: `EXTERNAL_DATA_NOT_AVAILABLE`. Reopen only with an exact linked
official term/execution document and defensible publication/known time. Record dates,
planned dates and price moves never supply missing ex-dates, execution or factors.

## Actual eligibility and release validation

[Acceptance](PIT_MINIMUM_VIABLE_EVIDENCE_CLOSURE_ACCEPTANCE.json) binds actual source
hashes and before/after runs. There remain 21,092 receipt versions, 20,149 pairs,
1,334 tickers and 24 sessions. Both signal and gross input regions remain empty.
The exact exclusion counts are unchanged:

| Reason | Before | After |
|---|---:|---:|
| ACTIVE_UNIVERSE_UNKNOWN | 20,149 | 20,149 |
| CA_FACTOR_REQUIRED_UNAVAILABLE | 20,149 | 20,149 |
| LOOKBACK_WINDOW_INSUFFICIENT | 20,149 | 20,149 |
| PRICE_NOT_PIT_ELIGIBLE | 20,149 | 20,149 |
| KNOWLEDGE_CUTOFF_VIOLATION | 8,945 | 8,945 |
| SESSION_NOT_IN_GOVERNED_CALENDAR | 15,568 | 15,568 |
| SIGNAL_TICKER_SCOPE_NOT_SUPPORTED | 20,126 | 20,126 |
| VOLUME_NOT_PIT_ELIGIBLE (gross only) | 20,149 | 20,149 |

The SMA50 requirement remains 50, ticker scope remains VNM, and every existing
price/CA/universe/volume gate remains intact. Missing/future known-time evidence is
not all described as a future correction. No real replay or T0 feature lineage was
manufactured; the 6,026 existing scoped cross-source HOSE RAW bars remain unchanged.

Remaining classes: `FUTURE_TIME_ACCUMULATION` (24 observed sessions cannot supply
50 compatible sessions); `EXTERNAL_DATA_NOT_AVAILABLE` (units, effective membership,
September calendar, CA and original price/instrument scope); `EXTERNAL_DATA_RIGHTS`
(HNX/UPCoM historical bulk, unopened); `GOVERNANCE_CONFIGURATION` (exchange-specific
calendar scope and separately governed stronger-use promotion). Historical HOSE
RAW stays empirical scoped/basis undocumented. Full historical economics stays deferred.

Network: **11 foreground requests /627,318 retained response bytes**, zero retries
and zero followed redirects. Four pre-request plans bounded each exact acquisition
phase; aggregate usage remains below the original 12-request/8 MiB cap. One writer,
no polling/crawl/provider expansion. Git/GitHub release control is separate from these
source-acquisition counts. No Daily/publication/runtime/broker/order mutation.

Validation includes exact dates, no weekday fallback, actual calendar knowledge time,
no gap stitching, immutable bytes, unknown volume/no scaling, current status versus
membership, effective-window boundaries, CA missing terms/lifecycle and R7 regressions.
112 focused tests pass (two old optional document-body tests skip in the cold worktree).
The relevant session-gate and production-smoke selection passes 58 tests; one previously
documented unrelated omitted-session test is deselected (its existing FUTURE_SESSION /
PROVIDER_EVIDENCE_UNAVAILABLE mismatch was not changed). Producer CI's local full selection passes 1,524 tests /30 subtests; final calendar/market/R7 checks pass 103 tests after the last two guards. The final CLI re-run reproduces the exact retained after-artifact with all offline counters zero. Producer CI,
compile, roadmap and diff checks are release gates. The offline actual acceptance
guard reports network/provider/Vnstock counters zero. All 31 selected listing source
captures /3,216,925 bytes, original CA bodies and historical market input hashes are unchanged.

Exact next action: continue ordinary Daily accumulation with actual receipts; obtain
explicit DNSE OHLC volume units, dated official status transitions, historical calendar
evidence for the September gap, and the named event-linked CA documents. No further
automatic milestone, reconstructed history, or representative replay is authorized by
this closeout. Resume a bounded evidence gate only when its stated new source evidence
arrives; keep stronger runtime authority fail-closed.
