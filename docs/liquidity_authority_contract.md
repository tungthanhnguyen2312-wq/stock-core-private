# Liquidity authority contract (`liquidity_authority_contract/v1`)

Status: `AUTHORITY_CLOSURE_LIQUIDITY_FOUNDATION_V1` (2026-09-28). The terminal disposition is
`LIQUIDITY_AUTHORITY_PARTIALLY_PROMOTABLE`. Modules: `official_exchange_trading_statistics.py`
(source adapter) and `liquidity_authority_contract.py` (provider-neutral contract). Runner:
`tools/run_liquidity_authority_closure.py` (`plan` / `probe` / `build`). Evidence:
`operations-review/liquidity-authority-closure-v1-20260928/`.

Market-wide operationalization of this contract: [`liquidity_market_wide_operationalization.md`](liquidity_market_wide_operationalization.md).

## Sources

| Source | Route | Grain | Components | Units |
|---|---|---|---|---|
| HOSE (official, public) | `GET api.hsx.vn/mk/api/v1/market/securities/tradingresult/{SYM}?pageIndex=n&pageSize=20` | one dated row per session, newest first | `main*` = MATCHED_ROUND_LOT, `oddlot*` = MATCHED_ODD_LOT, `bigLot*` = PUT_THROUGH_ROUND_LOT, `bigLot*_OL` = PUT_THROUGH_ODD_LOT, `total*` = TOTAL | shares, VND |
| HNX / UPCoM (official, public) | `POST hnx.vn/ModuleIssuer/Report_NY/ThongTinTongHopListSearch_Datas` (`p_market` `NY` / `UC`) | one dated row per session, newest first | Khớp lệnh = MATCHED_ALL, Thỏa thuận = PUT_THROUGH_ALL, Tổng = TOTAL | shares, thousand VND (scaled exactly to VND) |
| DNSE `trades_latest` (retained, not re-called) | per board, latest cumulative tick | current session | board → component (below) | raw units (below) |

Every official row must close exactly: its components must sum to the published total, or the row
is flagged and never used. For HOSE, MATCHED_ALL and PUT_THROUGH_ALL are exact sums of HOSE's own
published parts. HNX figures are never relabelled as HOSE figures, and HOSE figures are never
relabelled as HNX ones. HNX's order matching (MATCHED_ALL) includes odd-lot and post-close trades,
so it has no separate round-lot figure (`NOT_PUBLISHED_SEPARATELY_BY_OFFICIAL_SOURCE`).

## DNSE board units (qualified per exchange by exact official reconciliation)

| Board | Component | Shares per raw unit | Value |
|---|---|---|---|
| G1 | MATCHED_ROUND_LOT (regular) | 10 | `grossTradeAmount` × 10⁹ VND |
| G3 | MATCHED_ROUND_LOT (HNX post-close) | 10 | × 10⁹ VND |
| G4 | MATCHED_ODD_LOT | 1 | × 10⁹ VND |
| T1, T3 | PUT_THROUGH_ROUND_LOT | 10 | × 10⁹ VND |
| T4 | PUT_THROUGH_ODD_LOT | 1 | × 10⁹ VND |
| T6 | PUT_THROUGH_ODD_LOT | 10 (fractional raw) | × 10⁹ VND |

A unit is `QUALIFIED_BY_EXACT_OFFICIAL_RECONCILIATION` for an (exchange, board) only when volume
and value are exact on at least 3 distinct tickers, with no conflict. Put-through raw quantities can
be fractional (e.g. `matchQtty` 4.1 = 41 shares), while the cumulative `totalVolumeTraded` is an
integer that floors them. Put-through volume is therefore
`SCALE_CONFIRMED_CUMULATIVE_QUANTITY_TRUNCATED_LOWER_BOUND_ONLY`: the value is exact and the volume
is only a lower bound. The derived TOTAL is never attributed to a board. An instrument that moved
exchange keeps its old market's boards in `trades_latest`; the contract binds the market of the
latest tick and sets the others aside. DNSE daily OHLC `v` equals G1 × 10 shares: it excludes G3,
odd lot and put-through.

## Trailing features

These use official components only, over the governed session calendar, with no calendar-day
imputation and no zero-fill. A published zero row is a zero; a missing row is missing.
`ADTV20_MATCHED_ALL_VND` (order matching including odd lot, put-through excluded) is the
cross-exchange comparable feature. The contract also emits `ADV20_MATCHED_ALL_SHARES`,
`ADTV20_MATCHED_ROUND_LOT_VND` (HOSE only), `ADTV20_TOTAL_VND`, and the 60-session variants where
official depth is retained. The governed calendar is extended past 2026-09-04 only with sessions
that both HOSE and HNX published. On the overlap, the official set must equal the base ledger
exactly.

## Dimension fitness (vocabulary and guard reused from `dnse_trades_liquidity_basis`)

| Dimension | Rule |
|---|---|
| CURRENT_SESSION_LIQUIDITY_RESEARCH | ELIGIBLE when boards are active. The basis is one of `OFFICIAL_EXCHANGE_RECONCILED_ABSOLUTE_UNITS`, `DNSE_UNIT_CONTRACT_APPLIED_NOT_INDIVIDUALLY_RECONCILED` or `PROVIDER_RAW_COUNTERS_ONLY_UNITS_UNQUALIFIED`. |
| HISTORICAL_LIQUIDITY_RESEARCH | ELIGIBLE with an official series and an exact 20-session window. PARTIAL if the window is incomplete. BLOCKED if the series is not acquired. |
| ADTV_RESEARCH | ELIGIBLE when `ADTV20_MATCHED_ALL_VND` is an `EXACT_WINDOW`. PARTIAL if coverage-restricted. BLOCKED otherwise. |
| ADV_VOLUME_RESEARCH | At most PARTIAL: official shares are as-traded, and no ex-date authority can rule out a share-count event in the window. |
| EXECUTION_CAPACITY, POSITION_SIZING, PIT_BACKTEST | Always BLOCKED (`assert_fail_closed`). |

Knowledge time is `RETROSPECTIVE_RETRIEVAL_OF_OFFICIAL_POST_SESSION_PUBLICATION`. The official
series supports "as of today" research. It does not show what was known at a past decision time.
PIT, RAW_AS_TRADED, execution and sizing are unchanged.
`sizing_readiness_envelope()` lists what sizing still needs: a participation-rate policy, a max
days-to-liquidate policy, a market-impact model, the order size, an intraday/price-limit profile
and point-in-time liquidity knowledge. It emits no size.
