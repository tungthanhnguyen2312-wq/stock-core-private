# PROSPECTIVE_RAW_PIT_AUTHORITY_V1

**Terminal disposition: `PROSPECTIVE_PIT_OPERATIONAL / HISTORICAL_PIT_PARTIAL`** (2026-09-29, canonical base
`ac9b8cf5473191fb054782e441e1f5145897c0c3`, Producer CI #113 SUCCESS). Counts, identities and hashes are in
[`prospective_raw_pit_publication_manifest.json`](prospective_raw_pit_publication_manifest.json). Raw exchange bodies and
per-ticker official prices stay in the gitignored local evidence root and are never staged.

## 1. How the blocker actually evolved

| Date | Statement | Later evidence |
|---|---|---|
| 2026-07-28 | Basis is `unknown` unless the provider states it. | Still true: neither DNSE nor HOSE documents its basis. |
| 2026-08-10 | DNSE OHLC is `ADJUSTED_RETROSPECTIVE` (bounded HPG/VCB windows). | Re-verified here at scale (section 5). |
| 2026-08-24 | `OUTCOME_D`: a record date exists but no explicit ex-date and no pre-event snapshot pair. | **Superseded in part.** The retained official event index carries an explicit ex-date for 4,438 of 4,444 events. The pre-event snapshot pair now exists: 21 dated Daily snapshots plus a same-night official HOSE series. |
| 2026-09-15 | Factor chain: 0 real events qualify (ratio, executed lifecycle and publication cutoff missing). | **Unchanged.** Ratio/cash terms are carried by 0 of 4,444 events; publication time by 0. |
| 2026-09-29 | Official HOSE `tradingresult` route located (liquidity work). | Carries `openPrice/highPrice/lowPrice/closePrice/averagePrice`; no basis statement located. |

The real remaining blocker is therefore not the ex-date. It is official terms, executed-lifecycle evidence and publication
(knowledge) time, plus PIT universe membership.

## 2. Prospective snapshot contract (`prospective_market_snapshot_contract.py`)

Three claims are kept apart on every record: `source_basis_claim` (what the source says: documented raw, documented
adjusted, or undocumented), `observation` (possession of exact bytes at a known time: payload SHA-256, byte length,
`knowledge_available_at`), and `revision` (never revised / revised / no comparable snapshot / basis unknown, scoped to the
tested sample). A receipt proves possession, not raw-as-traded.

Timing is deterministic. A bar retained at or after the 15:00 close and before the next session can open is
`PROSPECTIVE_SAME_SESSION_CAPTURE`; no session opens before 09:00 on the next calendar day, so this holds without a calendar
lookup until then. Later receipts are `RETROSPECTIVE_ACQUISITION` and keep only the revision-detection baseline.
`PROSPECTIVE_RAW_AS_TRADED_PRICE` additionally needs an independent official series that agrees and no adjusted-basis
evidence. The contract can never grant historical raw, PIT-adjusted history, PIT backtest or execution replay.

## 3. Authority dimensions (before / after)

| Dimension | Before | After |
|---|---|---|
| CURRENT_SESSION_PRICE_RESEARCH | descriptive only | qualified with prospective lineage (368/368 official HOSE agreement on 2026-09-28) |
| PROSPECTIVE_AS_KNOWN_PRICE_EVIDENCE | experiment/shadow only | **operational**: 18,514 post-close bars over 21 sessions with hashed known-time receipts |
| PROSPECTIVE_RAW_AS_TRADED_PRICE | not promoted | **qualified, cross-source scoped**: 6,026 bars equal to the official HOSE series; 12,488 stay as-known only |
| HISTORICAL_RAW_AS_TRADED_PRICE | not promoted | **partial, HOSE-scoped empirical** (research grade; basis undocumented by source) |
| CORPORATE_ACTION_EVENT_AUTHORITY | ex-date unqualified | partial: 4,438 explicit official ex-dates; 0 with terms; 0 with publication time |
| CORPORATE_ACTION_FACTOR_CHAIN | blocked | blocked (0 qualified events) |
| POINT_IN_TIME_ADJUSTED_HISTORY | blocked | blocked (needs a qualified chain; contract/readiness only) |
| RETROSPECTIVE_ADJUSTED_RESEARCH_HISTORY | research only | research only, now with revision evidence |
| PIT_BACKTEST_ELIGIBILITY | blocked | blocked |
| EXECUTION_REPLAY_ELIGIBILITY | blocked | blocked |

## 4. Sources and basis conclusions

* **DNSE daily OHLC (REST):** basis undocumented; the series re-fetched later is re-based after the fact (section 5). A
  same-day bar is what was known then, but it is not always final.
* **HOSE official `tradingresult`:** basis undocumented in anything retained. Route officiality is not used as evidence.
  Empirically (route-, field- and window-scoped, `empirically_deduced`): unadjusted across 46 tested tickers/events. For
  HPG (ex 2026-05-25, bonus) the official pre-ex close is 26.35 while the later DNSE series says 23.95 (ratio 0.90892);
  for VCB (ex 2026-07-23, cash) 54.5 versus 54.05 (0.99174). Post-ex closes are identical in both. Filed as
  `PROSPECTIVE_OFFICIAL_OBSERVATION`, basis UNKNOWN by the source, empirically unadjusted.
* **DNSE `trades_latest`:** session open/high/low agree with the official HOSE row for all 368 tickers that traded on
  2026-09-28 (35 had no matched trading); the last match equals the official close in all 368.

## 5. Revision tests (retained T0 versus later T1)

Across 21 retained Daily snapshots (2026-08-24 to 2026-09-24), the same ticker/session was compared as known at T0 versus re-fetched in the 2026-09-28 snapshot
(17,646 comparable pairs): 15,552 identical, 1,127 consistent-ratio, 967 inconsistent. The official series then separates
the causes: for 282 revised pairs (44 tickers) it equals T0, so the re-fetched DNSE series was re-based;
for 603 pairs it equals T1, so the **T0 bar itself was not final** (3.4% of comparable pairs, concentrated on the
2026-08-27/28 snapshots and 2026-09-15); 67 are unresolved. This is why DNSE-only same-day bars are never called raw.

Bounded probe re-request (HOSE, T0 2026-09-28 vs T1 2026-09-29): 10 tickers, 200 ticker-sessions, all
`NEVER_REVISED_OBSERVED_SAMPLE` over an interval of hours only. The result is scoped to that sample and is not generalised.

## 6. Corporate actions and factor chain

The retained event index (HNX rights event index, observed 2026-09-05) carries 4,438 explicit ex-dates but no
ratio or cash terms, no publication time, and only 69 events for HOSE-listed tickers. No ex-date is inferred from a record
date and no planned issuance is treated as executed. Observed re-basing ratios are consistency evidence only and are never
used as a factor. Factor-chain result: 0 events qualified. Qualifying one event needs official terms, an explicit ex-date,
executed-lifecycle evidence and a publication cutoff for that event.

## 7. Historical raw-as-traded recoverability

| Path | Verdict |
|---|---|
| DNSE Daily snapshots as known at T0 (2026-08-24 onward) | `RECOVERABLE_FOR_SUBSET`: 6,026 bars verified against the official series |
| HOSE official trading result | `RECOVERABLE_FOR_SUBSET`: HOSE-listed tickers, depth at least 100 sessions (HPG), research grade |
| DNSE REST history | `RETROSPECTIVE_ONLY` |
| HNX / UPCoM official routes | `NOT_LEGALLY_ACQUIRABLE` in bulk (no authorization; HNX approval needed) |
| DNSE Trades ticks | `INSUFFICIENT_EVIDENCE`: the local corpus holds one page-capped sample (100 rows) |
| Pre-2026-08-24 non-HOSE sessions | `NOT_AVAILABLE`: information loss, not engineering debt |

Snapshots dated 2026-08-20 and 08-21 are retained but excluded from comparison: they carry no price unit and are on a
1,000x scale, and no unit is invented.

## 8. Trades-derived OHLC

`reconstruct_daily_ohlc_from_trades` produces a `DERIVED_RAW_AS_TRADED_CANDIDATE` only when session completeness is proven
and no page sits at the cap; otherwise it fails closed (`SESSION_COMPLETENESS_NOT_PROVEN`,
`PAGE_AT_CAP_TRUNCATION_NOT_EXCLUDED`). It is never labelled official. No historical tick corpus is available locally,
so no historical reconstruction is claimed.

## 9. Daily integration

`canonical_post_close_pipeline` writes `prospective_market_snapshot_manifest` (local evidence root) from the session's
exact-session snapshot. It is component-local: any failure yields `UNAVAILABLE` for that component only, never a Daily
failure, and Current Research is unaffected. Without an official series no bar earns raw fitness. No new entrypoint,
loop or daemon.

## 10. PIT backtest and ACTIVE_UNIVERSE

PIT backtest stays blocked: no qualified factor chain, PIT universe membership unknown, and 21 sessions of history.
Price PIT does need exact listing-status authority for universe membership. Official HOSE presence narrows nothing that
the contract supports, so `ACTIVE_UNIVERSE` stays UNKNOWN.

## 11. Remaining blockers by type

* **Engineering can create:** ratio/cash terms per event (official announcement documents), HOSE event calendar, execution
  participation policy.
* **Only future calendar time can create:** announcement publication time per event, history depth for backtests.
* **External source or permission:** HNX/UPCoM official series, a documented HOSE basis statement, official listing-status
  route for ACTIVE_UNIVERSE, complete historical trade ticks.

## 12. Probe record

HOSE `tradingresult`, 14 requests planned, 14 made, 14 OK, 0 retries, budget 20, spacing 1.5 s, one foreground run.
Plan `19930c2eaf07a1f8ee1ffe68d792f9de355269dabaa132dbfad3d43c3ec93ac2`, ledger
`0a592f86c7fcca1a0af479faf16849268a777da1753303ccc13106e83b7ad555`. No DNSE, Vnstock, KBS, VCI or FHSC call.
