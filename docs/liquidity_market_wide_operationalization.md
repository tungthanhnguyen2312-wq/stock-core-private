# Official-exchange liquidity, market-wide operationalization (`OFFICIAL_EXCHANGE_LIQUIDITY_MARKET_WIDE_OPERATIONALIZATION_V1`)

Status: `MARKET_WIDE_LIQUIDITY_OPERATIONALIZATION_PARTIAL` (2026-09-29). Session evaluated:
2026-09-28. Modules: `official_liquidity_market_wide.py` (pure logic), runner
`tools/run_liquidity_market_wide_operationalization.py` (`plan` / `probe` / `build` / `manifest`).
Contract reused, not re-invented: [`liquidity_authority_contract.md`](liquidity_authority_contract.md).
Public counts and hashes: [`liquidity_market_wide_publication_manifest.json`](liquidity_market_wide_publication_manifest.json).

The pipeline is operational over the maximum honestly qualified scope. That scope is HOSE in full and
a retained HNX/UPCoM cohort. It is not the whole market, because bulk HNX/UPCoM retrieval is not
authorized. At this milestone it granted no sizing, execution-capacity or PIT authority. The later
[`LIQUIDITY_EXECUTION_CAPACITY_AND_SIZING_V1`](liquidity_execution_capacity_and_sizing.md) opens only
policy-bounded current-session research envelopes; live and historical authority remains blocked.

## 1. Acquisition-rights gate

Access is not permission. Each exchange was judged separately for access, automated bulk
acquisition, internal retention and redistribution (`ACQUISITION_RIGHTS`, reviewed 2026-09-29).

| | HOSE | HNX / UPCoM |
|---|---|---|
| Access | public, no login | public, no login |
| robots | `www.hsx.vn/robots.txt`: all paths allowed; `api.hsx.vn` publishes none | `hnx.vn/robots.txt`: HTTP 404, no directive |
| Terms | no restrictive terms or licence found on the public site or its application bundle; no affirmative licence either | footer asks that HNX be contacted before information is published; HNX sells market data as fee-based packages; nothing authorizes bulk automated retrieval |
| Bulk acquisition | permitted only as bounded, paced, foreground retrieval for internal research | **not authorized** (`PUBLIC_ACQUISITION_NOT_AUTHORIZED`), no market crawl performed |
| Internal retention | private local only | only the evidence already retained by the prior bounded qualification probe |
| Redistribution | not established: raw bodies are never published | not established: raw bodies are never published |

External approval needed for HNX/UPCoM coverage: written permission or an information-service
agreement from HNX for automated retrieval of per-symbol end-of-day trading statistics, stating
whether internal research retention and derived-figure publication are allowed.

## 2. Governed universe (denominators kept distinct)

| Denominator | Count |
|---|---|
| Governed universe (Stock Lookup reference set) | 1,683 |
| Current official exchange-list presence (research denominator; `ACTIVE_UNIVERSE` stays UNKNOWN and is not manufactured) | 1,504 (HOSE 403, HNX 299, UPCoM 802) |
| Exchange-resolved (official master and DNSE agree, or official-only) | 1,504 |
| Source-supported (authorized route, or already retained) | 457 (HOSE 403, HNX 28, UPCoM 26) |
| Not routable | 179: 167 `SOURCE_NOT_SUPPORTED`, 12 `EXCHANGE_IDENTITY_CONFLICT` |

Exchange resolution: 1,444 agree, 60 official-only, 12 conflict, 167 unresolved. No transfer
evidence appeared this session. A ticker whose DNSE latest market differs from its official
exchange, with prior-market boards naming the official exchange, would be `TRANSFERRED_LISTING`.

## 3. Acquisition

The plan was frozen before any request: 364 HOSE `tradingresult` page-1 requests (the newest 20
sessions), one attempt each, one retry only for `HTTP_429/502/503/504/URLError/TimeoutError`, hard cap
400, 1.5 s spacing, consecutive-failure breaker, foreground only, no daemon, no pagination beyond
page 1. The 93 series retained by the prior probe were reused (hash-verified). Result: 364 requests, 364
`OK`, 0 retries. No DNSE, Vnstock, KBS or VCI call was made. Bodies are content-addressed under the
gitignored evidence directory with their own `.gitattributes`.

## 4. Coverage (target session 2026-09-28)

| Exchange | `EXACT_20_SESSION_WINDOW` | `PUBLIC_ACQUISITION_NOT_AUTHORIZED` |
|---|---|---|
| HOSE | 403 | 0 |
| HNX | 28 (retained cohort) | 271 |
| UPCoM | 26 (retained cohort) | 776 |

ADTV20 and ADV20 are exact for 457 tickers (HOSE 403, HNX 28, UPCoM 26). `ZERO_TRADING_VALID` is a
label on exact windows (HOSE 86, HNX 11, UPCoM 15): a published zero is a zero. No ticker landed in
`PARTIAL_WINDOW`, `MISSING_SESSION`, `TICKER_NOT_FOUND`, `HTTP_OR_SOURCE_FAILURE` or
`SEMANTIC_CONFLICT`. Those classes are implemented and tested. Nothing is forward-filled.

Current-session liquidity is eligible for 952 tickers (HOSE 392, HNX 217, UPCoM 343): 441 by exact
official reconciliation and 511 under the per-exchange DNSE board-unit contract. The other tickers
had no board active on the session.

## 5. Authority matrix (per ticker / exchange / field / window)

| Dimension | Before (foundation merge) | After |
|---|---|---|
| CURRENT_SESSION_LIQUIDITY_RESEARCH | ELIGIBLE, 952 scoped | ELIGIBLE, 952 (HOSE 392, HNX 217, UPCoM 343) |
| HISTORICAL_LIQUIDITY_RESEARCH | ELIGIBLE, 93-ticker cohort | ELIGIBLE 457 (HOSE 403, HNX 28, UPCoM 26); BLOCKED for the rest with a named reason |
| ADV_VOLUME_RESEARCH | PARTIAL, cohort | PARTIAL 457 (as-traded; no ex-date authority) |
| ADTV_RESEARCH | ELIGIBLE, 93 | ELIGIBLE 457 |
| EXECUTION_CAPACITY / POSITION_SIZING / PIT_BACKTEST | BLOCKED | BLOCKED (fail-closed guard) |

Board units were requalified on the wider evidence: HOSE G1 and G4 (401 and 399 exact tickers),
HNX G1, G3 and G4. HOSE G3 was never observed active, so it stays unqualified for HOSE. Put-through
boards keep the truncation caveat (value exact, volume a lower bound).

## 6. Daily integration

`official_exchange_liquidity_research/v1` is read offline by the post-close pipeline (same session,
self-verifying identity, authority boundary re-checked). It adds a `qualified_research` sub-block to
the LIQUIDITY dimension of `current_research_decision_input/v1`: current-session matched value and
volume, ADV20, ADTV20, current value to ADTV20 and current volume to ADV20 ratios, window coverage,
evidence currency, per-use fitness, reason codes and response-hash references. The ratio numerator is
the exact official row (or the qualified DNSE unit contract), and the 20-session window includes the
current session. The volume ratio is labelled as-traded and not corporate-action normalized.

Missing official evidence blocks only the liquidity-dependent use. It never changes another
dimension, the evidence class, the posture or `decision_identity`. A read-only assembly of the
retained 2026-09-28 Daily over all 1,683 tickers (write guard, zero provider calls) with and without
the artifact gave identical postures, decision identities, evidence classes and non-liquidity
dimensions. The LIQUIDITY dimension moved BLOCKED→AVAILABLE for 48 tickers and BLOCKED→PARTIAL for
60; 860 stayed AVAILABLE and 715 stayed BLOCKED.

## 7. Legacy liquidity consumers

`LEGACY_LIQUIDITY_CONSUMERS` classifies every module that references a close×volume `gtgd20` /
`avg_volume20` / `average_volume` proxy, and a test fails on any new unclassified one. The
migrated count is 0. No active research input is fully replaced: the proxy feeds legacy CLI
screens whose thresholds are tuned to it, a blank Dashboard column, and an AI-bundle risk block whose
coverage would shrink. Recorded as ACTIVE (`vn_indicators`, `stock_analyzer`, `ai_analyzer`,
`candle_scan`, `candlestick_patterns`, `canonical_dashboard_runtime_release`,
`screener_master_projection`, `risk_liquidity`), HISTORICAL_ONLY (registry/contract/matrix rows) or SHADOW
(KBS). The Daily decision input, which had no numeric liquidity, is where the qualified value is delivered.

## 8. G3 and board semantics

`G3` is the round-lot post-close board in the shared vocabulary. The Daily-facing measures count it
only where its unit is qualified for that exchange (HNX), never generalized to HOSE. Boards of a
prior market are excluded, and an exchange transfer is classified rather than routed. The DNSE
daily-OHLC volume registry row was corrected: `v` equals G1 × 10 shares (round-lot regular order
matching), verified on every G1-active reconciled ticker (HOSE 368/368, HNX 22/22, UPCoM 22/22),
and it excludes G3, odd lot and put-through. It is not an ADV/ADTV input.

## 9. Execution-capacity readiness

The readiness artifact classifies eleven dimensions per ticker. `ADTV20`, `ADV20` and
`CURRENT_LIQUIDITY` are `AVAILABLE_DATA` where qualified. `VOLATILITY_BASIS` is
`DATA_NOT_QUALIFIED` because the price basis is not RAW/PIT-qualified. `ORDER_SIZE_INPUT` and
`PORTFOLIO_CAPITAL_HOLDINGS_RISK_BUDGET` are `USER_INPUT_REQUIRED`. `PARTICIPATION_RATE_POLICY`,
`DAYS_TO_LIQUIDATE_POLICY`, `MARKET_IMPACT_MODEL` and `PRICE_LIMIT_INTRADAY_CONSTRAINTS` are
`POLICY_NOT_DEFINED`. `POINT_IN_TIME_LIQUIDITY_KNOWLEDGE` is `PIT_REQUIRED`. Those cells are the
bounded scope of a later sizing milestone. No size is emitted.

## 10. RAW/PIT candidate observations (not promoted)

The HOSE `tradingresult` rows also carry open, high, low, close, average price and foreign
buy/sell volume and value. Whether the prices are as-traded or adjusted is not stated by the source,
so nothing is promoted. They are a candidate dependency for a RAW/PIT milestone, to be checked
against retained ex-date evidence. The HNX route carries no price fields. Knowledge time is
`RETROSPECTIVE_RETRIEVAL_OF_OFFICIAL_POST_SESSION_PUBLICATION`. It is not backfilled into a PIT
knowledge time.

## 11. Remaining blockers and next step

- HNX/UPCoM bulk coverage (1,047 tickers) needs the HNX approval named in section 1.
- 179 governed tickers have no official exchange resolution.
- Sizing and execution need the `POLICY_NOT_DEFINED` policies and point-in-time liquidity knowledge.

Recommended next milestone, not started: `PROSPECTIVE_RAW_PIT_AUTHORITY_V1`. Point-in-time
liquidity knowledge is the blocker common to PIT_BACKTEST, sizing and any historical liquidity
claim, and only prospective, as-known-at retention of the official series can supply it.

## Operator runbook

Acquisition is operator-initiated and never part of the ordinary Daily. `--retained-root` is the
`operations-review` root holding the retained official universe and DNSE batches; `--prior-closure-dir` is
the retained foundation-milestone evidence directory.

```bash
python tools/run_liquidity_market_wide_operationalization.py plan  --retained-root <ops-review> --prior-closure-dir <closure-dir>
python tools/run_liquidity_market_wide_operationalization.py probe --retained-root <ops-review> --prior-closure-dir <closure-dir>
python tools/run_liquidity_market_wide_operationalization.py build --retained-root <ops-review> --prior-closure-dir <closure-dir> --verify-determinism
```
