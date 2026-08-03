# P1J — Provider-Reported Share Authority Hardening

Milestone operations review. Date: **2026-08-03**. Base commit: `f4f4be7` (Producer), `66733a4` (Consumer).
Runtime root: `C:\Projects\StockLookup\dashboard-runtime`.

---

## 1. File Allowlist

The following exact file allowlist governs all modifications for milestone P1J:

1. `stock-core-private/market_wide_current_shares_resolver.py`
2. `stock-core-private/tools/operate_stocklookup.py`
3. `stock-core-private/tests/test_p1j_provider_share_authority.py`
4. `stock-core-private/README.md`
5. `stock-core-private/docs/CLI_REFERENCE.md`
6. `stock-core-private/docs/POST_CLOSE_RUNBOOK.md`
7. `stock-core-private/docs/PIPELINE_ARCHITECTURE.md`
8. `stock-core-private/docs/STATE.md`
9. `stock-core-private/docs/ROADMAP.md`
10. `stock-core-private/docs/DECISIONS.md`
11. `stock-core-private/operations-review/p1j-provider-share-authority-20260803/P1J_OPERATIONS_REVIEW.md`

No other files will be modified.

---

## 2. Workstream A — Provenance of Retained Provider Share Field

- **Ingestion Callable**: `meta_sync.py` via `Company(source="VCI", symbol=tk).overview()`
- **Raw Field Name**: `issue_share`
- **Target Storage**: `vn_stock.db → metadata.shares_outstanding`
- **Field Semantics**: `ISSUED_SHARES` (total issued common shares, without deducting treasury shares or distinguishing active outstanding vs registered/issued total).
- **Semantics Verdict**: `PROVEN`
- **Unit**: `shares`
- **Observation Date**: Ingestion timestamp recorded in `metadata.updated` (e.g. `2026-07-30`).

---

## 3. Workstream B — Grounding Against Official Anchors

Comparing VCI `issue_share` with `qualified_official` effective shares:
- **HPG**: Provider `6,396,250,200` vs Official `7,163,748,865` (Diff: `-767,498,665` / `-10.71%`). Reason: Provider value was observed/retained before the 2026-06-04 stock dividend event. Invalidated as `provider_reported_stale`.
- **VNM**: Provider `2,089,955,445` vs Official `2,089,955,445` (Exact agreement). `provider_reported_current`.
- **VCB**: Provider `5,589,091,222` vs Official `5,589,091,222` (Exact agreement). Banking template (`EV`/`EV/EBITDA` inapplicable).

---

## 4. Workstream C & D — Invalidation & Hardened Authority Counts

Corporate actions post-dating the provider observation (e.g. stock dividends, bonus shares, rights issues) invalidate the provider observation as `provider_reported_stale`.

- **Active Universe Count**: 1683
- **Qualified Official Count**: 3
- **Provider Reported Current Count**: 1677
- **Provider Reported Stale Count**: 2
- **Provider Reported Conflicted Count**: 0
- **Unknown Share Concept Count**: 0
- **Unknown Observation Date Count**: 0
- **Unavailable Count**: 1

---

## 5. Workstream F — Recalculated Valuation Readiness

- **Qualified Reconstructed Market Cap Count**: 3
- **Provider-Reported Market Cap Count**: 1471
- **P/E Ready Count**: 1391
- **P/B Ready Count**: 1289
- **EV Ready Count**: 1247
- **EV/EBITDA Ready Count**: 111
