# VCI price-contract reconciliation and one-session intraday pagination pilot

**Date:** 2026-08-04 · **Starting commit:** `028eb08` · **Provider:** VCI only
**Evidence:** this directory and `operations-review/vci-intraday-pagination-20260804/`

---

# Part A — the price conflict

## A1. Old verdict and provenance

`raw_as_quoted_no_adjustment_applied`, asserted over **1,923,111 VCI rows, 1,686 tickers,
2014-06-25 → 2026-07-28**, in two places:

* `operations-review/phase3a-qualified-vci-price-benchmark.json` → `manifest.price_basis`;
* `qualified_price_storage_benchmark.py` line 9 → **module constant `BASIS`**, stamped onto
  every exported row and into all five benchmark SQL workloads as a literal.

## A2. Root cause

**An unsupported assumption, in the specific form of conflating "no local adjustment" with
"provider raw".** Not a different endpoint, not a different snapshot, not stale evidence,
not a transformation bug.

The label was a hard-coded constant. It was never derived from a payload, never gated on
evidence, and never verified. What it truthfully recorded is that *the export applies no
adjustment of its own*. It was then read as a statement about VCI.

The same conflation was written down explicitly in `semantic_evidence_bridge.py`, which
until today carried this comment above `_SUPPORTED_ADJUSTMENT_STATUSES`:

> *"A citation is only valid under this status when the ticker had no unsettled corporate
> action as of the trading_date."*

That is the right instinct pointed the wrong way down the timeline. A back-adjustment is
applied by events that happen **after** the cited date. A citation can be perfectly correct
when written and be silently restated by the provider months later. The reader also
re-validated each citation against the live `ohlcv` row — which, being the same rewritten
series, agreed and so *reinforced* the wrong label.

**Both production citations demonstrate it.** The runtime holds exactly two market-price
citations, both VCI, both labelled raw:

| citation | close | HOSE tick for band | on lattice? |
| --- | --- | --- | --- |
| HPG 2024-12-31 | 19,830 | 50 | **no** |
| VCB 2024-12-31 | 60,560 | 100 | **no** |

Neither could have been a matched order price. HPG's stated justification — its only 2024
action settled 2024-06-27, before the cited date — is exactly the wrong-direction error:
HPG had share issues on **2025-06-26** and **2026-05-25**, both after it.

## A3. Active replacement verdict

`provider_price_basis_registry:VCI@1.0.0`:

```text
source_field_identity          = observed
historical_mutability          = retrospectively_rewritten
price_basis                    = empirically_event_adjusted
observed_adjustment_dimensions = [cash_distribution, share_related_event]
provider_methodology           = unknown
unobserved_event_types         = unknown
coverage_generalization        = not_authorized
raw_as_traded_eligible         = false
official_exchange_price        = false
```

`empirically_event_adjusted` is deliberately **not** `split_and_dividend_adjusted`. The
latter names a general methodology; what is evidenced is that adjustments were observed at
two event kinds across three tickers in 2026. Which events VCI adjusts for — and which it
silently does not — is `unknown`, so the verdict says what was seen and nothing more.

## A4. Supersession treatment

The Phase 3A verdict is recorded in `_SUPERSEDED` with its asserted value, both assertion
sites, its scope, the root cause, the superseding evidence and the date. **Nothing was
deleted**: the benchmark artifact, its manifest and its history are untouched, and
`is_superseded("phase3a_vci_price_basis")` is how a reader learns it is not active.

Two contradictory *active* verdicts cannot coexist: `resolve_active` returns
`conflicted` with `raw_as_traded_eligible: false` and the reason
`two_active_verdicts_disagree_and_recency_is_not_evidence`, and
`assert_single_active_verdict` raises. **The newer verdict is not chosen for being newer** —
it is chosen because Phase 3A was superseded on stated evidence.

## A5. Affected consumers and corrected behaviour

| consumer | before | after |
| --- | --- | --- |
| `semantic_evidence_bridge.load_verified_market_price` | accepted any citation whose `adjustment_status` was the legacy label | rejects with `provider_series_retrospectively_rewritten`; **both** production citations now reject |
| `corporate_action_factors` | derived cash-dividend factors from that reference price | second, independent gate — an adjustment factor built on an already-adjusted reference would double-count the very event it prices |
| `export_ai_bundle` (via the bridge) | emitted the citation and its status into the bundle | receives nothing to emit |
| `point_in_time_adjusted_prices` / `_returns` / `_benchmark` / `_market_risk` | consumed verified VCI prices | consume none |
| `historical_valuation_snapshot` (P2a) | published HPG FY2024 multiples off the cited close | blocked; `docs/ROADMAP.md` P2a reopened, design doc banner-superseded |
| `ohlcv_basis_qualification.qualify` | could emit a verified raw verdict for VCI | cannot; limitation states the reason |
| `qualified_price_storage_benchmark` | hard-coded constant | reads the registry → `empirically_event_adjusted` |

**Deliberately not changed.** Providers with no established verdict (`SSI`, `KBS`, …) are
*not* blocked. `active_verdict` returns `raw_as_traded_eligible: None` for them — unknown,
not false. Blocking them would be a policy change disguised as a bug fix, and this pilot
examined none of them. They still pass on `adjustment_status` alone, which is the same
conflation, merely not yet evidenced; `unexamined_providers_note()` says so in the code.

---

# Part B — one-session intraday pagination

## B1. Endpoint semantics established

| property | finding | how |
| --- | --- | --- |
| cursor direction | backward | `truncTime` returns older trades, newest first |
| **boundary** | **strictly exclusive (`truncTime < cursor`)** | run 01: newest returned trade was strictly older than the requested cursor **71 / 71** transitions, equal **0** |
| page size | **hard 100-row server cap** | `limit=30000` returns 100 |
| history reach | **current session only** | a cursor at the prior session's close (2026-08-03 14:45 ICT) returns **0 rows** |
| `accumulatedVolume` | cumulative **including** its own row | the session's first trade satisfies `accVol == matchVol` |
| trade identity | `id`, unique and time-ordered | available on every row |

**A completed prior trading day is therefore not reachable through this endpoint.** At
execution time (11:30–12:15 ICT) the current session was in its lunch halt, so the pilot
bounds the **morning session, open → 11:30 ICT halt**: a segment with a *provable* start
boundary and a frozen end.

## B2. The exclusive boundary is a trap, and run 01 fell into it

Paging with `cursor = oldest_trunc_time` produces **zero duplicates**, which reads like
confirmation that pagination is clean. It is the opposite. Under `<`, the 100-row cap
truncates the oldest second mid-way and the remainder of that second is then skipped
forever. Run 01 (HPG, 73 requests) lost **1,704,400 shares** and broke the tape's own
value identity at **47** places. Run 01 is retained as
`run-01-exclusive-boundary-discovery/`. The corrected cursor is `oldest + 1`.

## B3. HPG could not be exhausted, and the reason is structural

Run 02 (HPG, corrected cursor) recovered the identity — **1,898 / 1,898** value pairs —
and then halted fail-closed on `cursor_did_not_advance` at 10:56:30 ICT: a whole page fell
inside **one second**. The cursor's only resolution is one second and the page cap is 100
rows, so a second holding ≥100 matched trades cannot be enumerated. HPG's tape has
several. That is a permanent property of this data path, not a budget problem.

The scan therefore moved to the sparsest ticker already inside the approved pilot scope
(probe: VCB max 9 trades/s vs VNM 67 vs HPG ~100). Still one symbol and one date per run.

## B4. Run 03 — VCB, 2026-08-04 morning session

| | |
| --- | --- |
| ticker / session | **VCB**, 2026-08-04, open → 11:30 ICT halt |
| request cap | **98**, computed before the first request from 1,877,000 shares ÷ 359 mean ≈ 5,228 trades ÷ 100 × 1.5 + 20 |
| requests made | **31** |
| pages | 31, all 100 rows except the last |
| start cursor | 1785817800 (11:30:00 ICT) |
| stop reason | **`session_start_boundary_reached`** — the first trade satisfies `accVol == matchVol` |
| raw rows | 3,038 |
| unique rows | **2,795** |
| duplicate boundary rows | **243** (the intended overlap), **0 conflicting** |
| dedup key | provider trade `id` **only** |
| offline replay | every page hash re-verified; summary byte-identical across two runs (`5d84e7107abe6542`) |

`truncTime` span 09:15:00 → 11:29:5x ICT. Accumulators strictly monotonic.

## B5. Volume reconciliation

| quantity | value |
| --- | --- |
| daily historical `v` | **1,877,000** |
| sum of enumerated trade quantities | **1,873,500** |
| final / max accumulated volume | **1,877,000** |
| measured un-enumerated quantity | **3,500** (exactly one gap) |
| enumerated + un-enumerated | **1,877,000** |
| **residual vs daily `v`** | **0 — closes exactly** |
| value-identity pairs | **2,793 / 2,793** matching, 1 skipped at the gap |

The single gap is 3,500 shares inside second 1785812196 (**09:56:36 ICT**), between trade
ids `502849993` and `502850027` — the dense second the one-second cursor cannot resolve.
It is not an unknown: the accumulator makes it **exactly measurable**, so the scan reports
0.19 % un-enumerated rather than claiming completeness.

**Verdict: `incomplete_cursor_failure`**, reason
`dense_seconds_exceed_the_one_second_cursor_resolution`. Reported as incomplete even
though the arithmetic closes to the share, because *the books balancing* and *every trade
being retrieved* are different claims and only the second one is what "complete" means.

## B6. Volume contract

```text
volume_field_identity            = qualified
volume_unit                      = shares
endpoint_session_completeness    = incomplete    (morning segment only; afternoon unreachable)
endpoint_segment_completeness    = incomplete    (one dense second un-enumerable)
daily_to_intraday_reconciliation = unknown       (enumeration incomplete)
corporate_action_adjustment      = unknown
matched_trade_inclusion          = unknown
negotiated_trade_inclusion       = unknown
auction_inclusion                = unknown
odd_lot_inclusion                = unknown
market_scope                     = unknown
liquidity_actionable             = false
```

**Pagination is not sufficient for market-scope qualification, and a complete exact match
would not have been either.** Enumerating every trade the endpoint returns tells you what
*this endpoint* counts; it cannot tell you what the *exchange* counted, because both a
matched-only tape and a tape including put-through would reconcile identically against a
daily field computed from that same tape. `market_scope_upgrade_requires` names the only
three routes: direct field semantics naming the included trade types, a first-party source
definition, or a separately identified endpoint with a demonstrable relationship. A test
proves a `complete_exact_match` leaves every composition dimension `unknown`.

## B7. Downstream eligibility

Unchanged from `028eb08` and unlocked by nothing here: provider-namespaced descriptive
volume history, volume trend, data-quality comparison. Blocked unconditionally: liquidity,
sizing, ranking, recommendations, backtesting, `is_actionable`, production replacement.

---

# Repository result

* **Starting commit** `028eb08` · **final commit** see `git log -1`
* **Added:** `provider_price_basis_registry.py`, `vci_intraday_pagination.py`,
  `tools/run_vci_intraday_pagination.py`, `tests/test_vci_contract_reconciliation.py`,
  this directory, `operations-review/vci-intraday-pagination-20260804/` (3 runs).
* **Modified:** `semantic_evidence_bridge.py`, `corporate_action_factors.py`,
  `ohlcv_basis_qualification.py`, `qualified_price_storage_benchmark.py`,
  `tests/test_ohlcv_basis_qualification.py`,
  `tests/test_historical_relative_valuation_snapshot.py`, `docs/ROADMAP.md`,
  `docs/historical_relative_valuation_snapshot.md`, `docs/STATE.md`, `docs/DECISIONS.md`.
* **Tests:** `test_vci_contract_reconciliation.py` **33 passing** (all 15 required proofs);
  full relevant set **372 passing + 25 subtests** across 20 modules.
* **Network:** 100 requests total — 6 reconnaissance, 73 (run 01) + 21 (run 02) + 31
  (run 03) paginated, 3 daily bars. No request exceeded a pre-computed cap. All later
  analysis ran offline.

# Non-effects

No change to production databases (`vn_stock.db` read `mode=ro` throughout), production
bundles, dashboard artifacts, rankings, recommendations, position sizing, price targets,
generic official-exchange fields, or `is_actionable`. The two production market-price
citations are now **rejected at read time**; the citation file itself was not modified.

---

**`VCI_CONTRACT_RECONCILIATION: PAGINATION_INCOMPLETE`**

Part A is fully resolved: one active verdict, the old one superseded with provenance, every
active consumer corrected, regressions in place. Part B established the endpoint's
semantics and its hard limit, and reconciled the tape to the share — but did not enumerate
every trade, so the honest token is the pagination one.

## Recommended next bounded milestone

**Determine whether VCI exposes a market-summary or put-through surface whose relationship
to `accumulatedVolume` is demonstrable — and if not, close `market_scope` as
permanently unresolvable through this provider.** Every other dimension of the volume
contract is now qualified or exactly measured; `market_scope` is the sole remaining
`unknown`, and this pilot proved it cannot be reached by more pagination. That makes it
either a one-endpoint question or a closed one, and both answers are worth having before
any liquidity-dependent capability is reconsidered.
