# Direct Vietnamese broker price-and-volume basis qualification pilot — VCI

**Date:** 2026-08-04 · **Producer HEAD at start:** `8aa5487` · **Pilot source:** VCI (Vietcap)
**Evidence:** `operations-review/vci-direct-basis-pilot-20260804/`

Facts, empirical observations, inferences and unknowns are labelled throughout. Nothing in
this milestone changed a production database, bundle, dashboard artifact, ledger, resolver
output, generic basis field, adjustment factor, ranking, recommendation, sizing input or
`is_actionable` gate.

---

## 1. Source matrix

| Dimension | VCI | TCBS |
| --- | --- | --- |
| Direct endpoint observed | **yes** — `POST /api/chart/OHLCChart/gap-chart`, `POST /api/market-watch/LEData/getAll` on `trading.vietcap.com.vn` | **no** — see §1.1 |
| Public access currently usable | yes, HTTP 200, 0 redirects, 0 retries | not established |
| Authentication required | no; no cookie, token or credential is sent or held | unknown |
| Historical OHLC available | yes | unknown |
| Daily volume available | yes (`v`, duplicated as `accumulatedVolume`) | unknown |
| Intraday matched trades available | yes, **server-capped at 100 rows** regardless of requested `limit` | unknown |
| Separate negotiated volume available | **no field observed** | unknown |
| Official semantic documentation | **absent** | absent |
| Stable field identity | yes across two retrievals 3 days apart (§3.1) | not established |
| Suitable for bounded pilot | **yes — selected** | no |

**Source authority classification (fact):** `observed_public_web_endpoint`. This is the
provider's own web-application API, reached over the established `vnstock` adapter path. It
is **not** a documented developer API. No first-party schema, data dictionary, SLA or
semantic declaration was found, so no verdict below may be promoted to an official-exchange
or canonical claim.

### 1.1 Why TCBS was not implemented

`vnstock` 4.0.4 — the pinned, installed provider library — **ships no TCBS quote explorer**
(`vnstock/explorer/` contains `fmarket, kbs, misc, msn, vci`). The repository already
records this: `vn_stock_pipeline.py:28` and `CHANGELOG.md:126` note that TCBS was dropped
from `Quote` in v4 and the failover moved to KBS. What survives in the library is a TCBS
*header profile* and TCBS branches inside `core/utils/transform.py` — evidence that a TCBS
path once existed, but **not** its URL.

The only TCBS endpoint recorded anywhere in this repository is
`https://apipubaws.tcbs.com.vn/tcanalysis/v1/margin/list`, which `blacklist_sync.py:22`
records as verified 404 on 2026-07-09. That gives host-level evidence and no path evidence
for a historical-bars endpoint.

Constructing a bars URL from that host plus a plausible path is available and was
**declined**: it would be fabricating an endpoint from a naming pattern, and any bytes it
returned would be attributed to a contract nobody observed. **TCBS is marked unavailable
for this milestone. Zero TCBS requests were made.**

Corroboration instead used the **already-local retained KBS artifact** (`operations-review/
kbs_ohlcv_sample_hpg.json`), read-only, as §5 explains. No KBS implementation lane was
opened.

---

## 2. Pilot execution

**Selected source and reason:** VCI. The repository's active price path already runs on it
(`vn_stock_pipeline.PRIMARY_SRC = "VCI"`), the direct endpoint is observable and unblocked,
and a prior retained raw payload from 2026-08-01 makes a genuine two-observation comparison
possible without any extra request.

**Network requests issued: 5.** Budget 8, never exceeded. All `POST`, all to
`trading.vietcap.com.vn`, all HTTP 200, **0 redirects, 0 retries** across every request. All
subsequent analysis (including two full re-runs) ran offline from the retained bytes.

| id | ticker | endpoint | non-secret parameters | returned range | raw artifact (sha256 prefix) |
| --- | --- | --- | --- | --- | --- |
| W1 control | HPG | gap-chart | `timeFrame=ONE_DAY, symbols=[HPG], to=1769817600, countBack=5` | 2026-01-26 → 2026-01-30 | `1f57e4fefeb75770` |
| W2 cash-dividend | VCB | gap-chart | `…, to=1785542400, countBack=25` | 2026-06-29 → 2026-07-31 | `eac0517aba7c5d6c` |
| W3 capital event | HPG | gap-chart | `…, to=1780358400, countBack=12` | 2026-05-18 → 2026-06-02 | `a1486eca4e74670e` |
| W4 intraday-aligned daily | HPG | gap-chart | `…, to=1785888000, countBack=3` | 2026-07-31 → 2026-08-04 | `fc61ef57abcf1a19` |
| W5 intraday | HPG | LEData/getAll | `symbol=HPG, limit=30000, truncTime=null` | in-progress session | `771a7d5701902a67` |

Headers sent: `Content-Type`, `Accept`, `User-Agent`, `Referer`, `Origin` — the provider's
own web-app origin. **No cookie, authorization header, token or credential was sent, and
none exists in this environment.** Response headers are redacted before persistence and a
test asserts no evidence artifact contains one.

### 2.1 Window selection evidence

Every window is selected from evidence already in this repository. **No corporate document
was acquired and no event date was inferred from price behaviour.**

- **W1 (no-event control):** `operations-review/vci_ohlcv_sample_hpg.json`, the retained raw
  VCI payload (sha256 `1f57e4fe…`, retrieved 2026-08-01T01:08:57Z per
  `docs/operations_review_hash_manifest.json`), which reproduces this exact request.
  `dashboard-runtime/vn_stock.db:corporate_event_records` holds **no** HPG event with an
  ex-right date in 2026-01.
- **W2 (cash dividend):** `corporate_event_records[provider=VCI, ticker=VCB, event_code=DIV,
  exright_date=2026-07-23, record_date=2026-07-24, value_per_share=450.0]`.
- **W3 (capital event):** `corporate_event_records[provider=VCI, ticker=HPG,
  event_code=ISS, exright_date=2026-05-25, record_date=2026-05-26, exercise_ratio=0.1]`.

These records carry `coverage_status = partial_unqualified_50_row_cap`: they are
provider-reported and adequate for *selecting a window*, not for asserting an official
event. That limitation is carried into every verdict below.

### 2.2 Transformation path

Raw → normalised is two declared steps and nothing else:

| raw field | normalised field | operation | parameters |
| --- | --- | --- | --- |
| `t` | `vci.session_date` | epoch seconds → calendar date | provider stamps daily bars at `00:00:00Z` |
| `o,h,l,c` | `vci.observed_{open,high,low,close}_vnd` | scale | **factor 1, rounding none** |
| `v` | `vci.observed_daily_volume` | passthrough | missing preserved as null, **no zero fill** |

`resampling_applied=false`, `forward_fill_applied=false`, `invented_sessions=0`.
Transformation code identity: `vci_direct_basis_pilot.normalize_daily/1.0.0`.

**Fact, and a correction to a prior report.** The *production* path is different and longer:
`vnstock`'s `ohlc_to_df` divides `o,h,l,c` by 1000 and rounds to 2 decimals, then
`vn_stock_pipeline.normalize` multiplies by `resolve_scale()` = 1000. Net effect on stored
prices is a **quantisation to 10 VND**, not an identity. Phase 1B recorded this as raw
responses "occasionally switch between thousands and units"; the retained payloads show the
provider consistently emitting VND and the wrapper doing the dividing. The pilot bypasses
that chain entirely and reads the provider's own numbers.

---

## 3. Price verdict

**Provider-level verdict: `split_and_dividend_adjusted`** for `vci.raw_open`,
`vci.raw_high`, `vci.raw_low`, `vci.raw_close`. Confidence: **high on the exclusion of
`raw_unadjusted`, high on the adjustment dimensions, low on mechanism and completeness.**

### 3.1 Supporting facts

**Fact (exchange rule, not a provider claim).** A HOSE common-stock order can only be
entered and matched at a tick multiple: 10 VND below 10,000; 50 VND from 10,000 to 49,950;
100 VND at 50,000 and above. A price that is not on that lattice was never a matched order
price.

**Empirical observation 1 — the returned prices are off-lattice.** VCB, W2, sessions
2026-06-29 → 2026-07-22: closes such as `61,485.40`, `58,411.13`, `56,229.39`, `54,047.65`.
HPG, W1, 2026-01-26 → 2026-01-30: `23,478.96`, `23,612.87`, `23,836.06`. None can be an
as-quoted price.

**Empirical observation 2 — the off-lattice prefix ends exactly at a qualified ex-date.**
Computed over all four price fields per session:

| window | ticker | last off-lattice session | first fully on-lattice session | qualified ex-date |
| --- | --- | --- | --- | --- |
| W2 | VCB | 2026-07-22 | **2026-07-23** | **2026-07-23** (cash, 450 VND/share) |
| W3 | HPG | 2026-05-22 | **2026-05-25** | **2026-05-25** (share issue, ratio 0.1) |

The same test run read-only over the whole stored VCI series in
`dashboard-runtime/vn_stock.db` reproduces this for a third ticker: VNM's fully-on-lattice
suffix begins **2026-06-26**, its qualified cash-dividend ex-date. Before those boundaries
the on-lattice rate is 43.8 % (HPG), 9.2 % (VNM) and 27.1 % (VCB) — consistent with values
distributed at random relative to the tick, not with quoted prices.

**Empirical observation 3 — historical values are rewritten retroactively.** This is the
decisive one, and it is a genuine two-observation comparison at two retrieval times:

`archive/runtime-backups/VNSTOCK_DATA_BACKUPS/20260719_223620/vn_stock.db` is a snapshot
taken 2026-07-19, **before** VCB's 2026-07-23 ex-date. `vn_stock_pipeline` fetches only from
each ticker's `MAX(date)` forward, so its historical rows are first-observation records. For
13 VCB sessions present in both that snapshot and the live 2026-08-04 payload:

| session | observed 2026-07-19 (pre-ex-date) | observed 2026-08-04 (post-ex-date) |
| --- | --- | --- |
| 2026-07-01 | 63,000 (on lattice) | 62,477.10 (off lattice) |
| 2026-07-02 | 62,100 | 61,584.57 |
| 2026-07-10 | 60,500 | 59,997.85 |
| 2026-07-17 | 58,500 | 58,014.45 |

**13 of 13 closes changed.** The same session, the same provider, two retrieval times
straddling one qualified cash dividend.

**Empirical observation 4 — the control is byte-stable.** W1 re-requested HPG
2026-01-26 → 2026-01-30 with the same parameters used on 2026-08-01. The response is
**byte-identical**: sha256 `1f57e4fefeb75770…`, the same hash the retained artifact carries
in `docs/operations_review_hash_manifest.json`. 0 of 5 sessions changed. With no intervening
event, the provider does not revise. So observation 3 is event-driven, not drift.

### 3.2 What this does not establish

- **No source documentation supports any of it.** The endpoint declares no adjustment
  status, no `is_adjusted` flag, no methodology. The verdict is an inference from arithmetic
  and timing, and it is labelled as one.
- The corroborating factor fit — a single constant ratio **0.9917** reproducing all 13 VCB
  sessions exactly, consistent with a standard cash-dividend back-adjustment against the
  last pre-ex close of 54,500 — is recorded with
  `event_window_fit_upgraded_verdict: false`. A fitted factor is not a contract.
- **Coverage is 3 events across 3 tickers, all in 2026.** Whether older history is adjusted
  the same way, whether rights issues or par-value changes behave identically, and whether
  the provider ever applies a *different* basis to a different symbol class are all
  untested.
- Whether the provider exposes a second, unadjusted price namespace: **no such field was
  observed**; the payload carries only `o,h,l,c,v,t,accumulatedVolume,accumulatedValue,
  minBatchTruncTime`. Absence in one endpoint is not absence from the provider.
- Daily-versus-intraday price reconciliation was **not** performed: W5 returned only the
  most recent 100 trades of an in-progress session.

### 3.3 Safe downstream eligibility

Unlocked, **provider-namespaced and shadow-only**: historical returns computed from the
qualified `vci.*` series, technical indicators on that same series, controlled source
comparison, anomaly detection, isolated shadow evaluation.

Not unlocked, unconditionally: production backtesting, market-impact models,
days-to-liquidate, portfolio or liquidity-based sizing, ranking, recommendations, price
targets, official-exchange claims, adjustment factors for any other source, generic
adjusted-return fields, `is_actionable`, production artifact replacement.

**Consequence worth stating plainly.** The production `ohlcv` table is populated from this
series and is therefore **not** a raw as-quoted series, which is what `phase3a-qualified-
vci-price-benchmark.json` asserts in its manifest (`price_basis:
"raw_as_quoted_no_adjustment_applied"`, 1,923,111 rows). That artifact is a storage
benchmark and was not modified here; the contradiction is recorded, not resolved.

---

## 4. Volume verdict

Field: `vci.observed_daily_volume` (raw `v`, duplicated by the provider as
`accumulatedVolume`).

| dimension | verdict | basis |
| --- | --- | --- |
| field identity | **qualified** | §4.1 |
| unit | **qualified — shares** | §4.2 |
| adjustment basis | **unknown** | §4.3 |
| market scope | **unknown** | §4.4 |
| `liquidity_actionable` | **false** | unconditional |

### 4.1 Field identity — qualified

The W4 daily bar for the in-progress session 2026-08-04 carries `v = 9,315,300`. The W5
intraday payload, retrieved **one second later**, reports `accumulatedVolume =
9,315,300.0` on its newest trade. Exact match. The daily `v` field *is* the running
session accumulator the matched-trade feed maintains — not a separately computed total.

### 4.2 Unit — qualified as shares, by the provider's own internal arithmetic

Across **99 of 99** consecutive trade pairs in the retained intraday sample:

- `Δ accumulatedVolume` equals the newer trade's `matchVol` exactly, and
- `Δ accumulatedValue` equals `matchVol × matchPrice` under exactly **one** scale, 10⁶.

Worked example: `Δ value = 207,547.31 − 207,509.655 = 37.655`; `1,700 × 22,150 =
37,655,000 VND = 37.655 × 10⁶`. Were `matchVol` a lot count, this identity would fail by a
factor of 100. So the quantity is a **share count** and `accumulatedValue` is in **millions
of VND**. This is an internal-consistency proof, not a cross-source agreement.

### 4.3 Adjustment basis — unknown

Volume also changed between the two VCB observations, but **not** in a way that identifies a
cause. Across the same 13 sessions: 13 distinct ratios spanning 1.00233 → 1.00764 — **not**
a single corporate-action factor, and not the reciprocal of the 0.9917 price factor. All 13
pre-event values are exact multiples of 100 (the HOSE round lot); **none** of the 13
post-event values is. That pattern is equally consistent with the earlier observation having
captured a mid-session accumulator rather than a session total. The two causes cannot be
separated from this evidence, so the verdict stays `unknown`.

**Provider revision behaviour for volume: observed.** Whatever the cause, a daily volume
already published is not final.

### 4.4 Market scope — unknown, and the reconciliation could not run

`reconcile_volume` returned **`intraday_sample_incomplete`**. `limit=30000` was requested;
the endpoint returned **100 rows** — a server-side cap. Observed intraday sum 146,900
against daily 9,315,300. That difference carries **no** scope information: pagination is not
exhausted, and excluding pagination is a precondition for any matched-versus-negotiated
inference. A test asserts a capped page cannot be read as a completed sample.

No separate negotiated, put-through, auction or odd-lot field appears anywhere in the
observed response ecosystem. Retained contract:

```text
volume_field_identity = qualified
volume_unit           = qualified   (shares)
volume_adjustment_basis = unknown
volume_market_scope   = unknown
liquidity_actionable  = false
```

Unresolved dimensions: matched-order inclusion, negotiated/put-through inclusion, auction
inclusion, odd-lot inclusion, provider revision semantics.

### 4.5 Safe downstream eligibility

Unlocked: provider-namespaced descriptive volume history, provider-namespaced volume trend,
data-quality comparison. Nothing liquidity- or sizing-related, under any condition.

---

## 5. Corroboration

**TCBS: unavailable** (§1.1). Zero requests.

**KBS: read-only comparison against an already-local artifact.** `kbs_ohlcv_sample_hpg.json`
(retrieved 2026-08-01T01:11:52Z) covers HPG 2026-07-20 → 2026-07-30 — 9 sessions, all
**after** HPG's last qualified event (2026-05-25). Against the stored VCI rows for the same
dates: **9/9 exact close matches, 9/9 exact volume matches.**

**Why this changes no authority.** Both series sit in the post-event region where an adjusted
series and an unadjusted one coincide by construction, so the agreement is uninformative
about basis. More fundamentally, agreement between two undocumented providers is
compatibility, not semantics. `apply_cross_provider_agreement` returns the verdict unchanged
and records `cross_provider_comparison_upgraded_verdict: false`; a test proves that even
total agreement over 250 sessions cannot lift an `inconclusive` verdict.

The KBS sample is also the reason no KBS lane was opened: its integer, on-lattice values for
those 9 sessions are the only KBS evidence used, and nothing was written from it.

---

## 6. Repository result

- **Starting commit:** `8aa5487` · **Final commit:** see `git log -1`
- **Files added:** `vci_direct_basis_pilot.py`, `tools/run_vci_basis_pilot.py`,
  `tests/test_vci_direct_basis_pilot.py`, this directory.
- **Files modified:** `docs/STATE.md`, `docs/DECISIONS.md`.
- **Tests:** `tests/test_vci_direct_basis_pilot.py` — **41 passing**, covering all 15
  required proofs. Relevant existing suites re-run: **133 passing, 14 subtests** across
  `test_price_basis_contract`, `test_price_basis_events`, `test_qualify_price_basis`,
  `test_ohlcv_basis_qualification`, `test_market_data_lineage`, `test_vn_stock_pipeline`,
  `test_risk_liquidity`, `test_analysis_readiness`, `test_point_in_time_market_risk`,
  `test_corporate_action_factors`, `test_corporate_actions`, `test_p1h_valuation_readiness`
  and the new module.
- **Determinism:** two consecutive `--offline` re-analyses produced byte-identical artifacts
  across all 10 files. Each raw artifact's filename embeds the first 16 hex of its own
  content hash, so the name is self-verifying.

---

## 7. Non-effects

Confirmed unchanged: production databases (`dashboard-runtime/vn_stock.db` mtime
2026-08-03 20:13, untouched; every read used a `mode=ro` URI), production bundles
(`analysis_bundle.json`, `bundle_manifest.json`, mtime 2026-08-03 20:14), dashboard
artifacts, official-document ledgers, resolver outputs, generic price basis, generic volume
basis, adjustment factors, ranking, recommendations, position sizing, `is_actionable`.
`price_basis_contract.qualify_price_basis` and `vci_volume_basis.declaration()` are
byte-unchanged and still return `unknown`/unverified; tests assert it.

---

## 8. Verdict

**`DIRECT_VN_BROKER_BASIS: PARTIAL`**

A provider-namespaced price basis is qualified to `split_and_dividend_adjusted` on
converging deductive and empirical evidence, with no source documentation behind it. Volume
field identity and unit are qualified; **volume market scope remains unknown** and the
intraday reconciliation could not complete against a 100-row server cap. Production and
actionability gates stay closed.

### Recommended next bounded milestone

**Exhaust the VCI intraday pagination for one ticker on one complete session, and settle
volume market scope.** The `truncTime` cursor is the documented paging parameter and the
100-row cap is now a measured fact, so the request count is bounded and predictable
(≈ session trade count ÷ 100 for one liquid ticker on one day). Completing that sample is
the single precondition for moving `volume_market_scope` off `unknown`, and it is the only
remaining blocker between the current PARTIAL and a full volume qualification. It needs no
new provider, no new document, and no widening of ticker scope.
