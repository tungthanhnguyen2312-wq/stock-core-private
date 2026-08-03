# P1I — Market-Wide Current Shares Coverage

Milestone operations review. Date: **2026-08-03**. Base commit: `5d6c0b7` (Producer), `66733a4` (Consumer).
Runtime root: `C:\Projects\StockLookup\dashboard-runtime`.

---

## 1. File Allowlist

The following exact file allowlist governs all modifications for milestone P1I:

1. `stock-core-private/market_wide_current_shares_resolver.py`
2. `stock-core-private/market_wide_calculation_readiness.py`
3. `stock-core-private/canonical_financial_bundle_section.py`
4. `ai-core-private/builders/build_ticker_context.py`
5. `stock-core-private/tools/operate_stocklookup.py`
6. `stock-core-private/tests/test_p1i_market_wide_shares.py`
7. `stock-core-private/README.md`
8. `stock-core-private/docs/CLI_REFERENCE.md`
9. `stock-core-private/docs/POST_CLOSE_RUNBOOK.md`
10. `stock-core-private/docs/PIPELINE_ARCHITECTURE.md`
11. `stock-core-private/docs/STATE.md`
12. `stock-core-private/docs/ROADMAP.md`
13. `stock-core-private/docs/DECISIONS.md`
14. `stock-core-private/operations-review/p1i-market-wide-current-shares-20260803/P1I_OPERATIONS_REVIEW.md`

No other files will be modified.

---

## 2. Verified Baseline Production Checkpoints & Hashes

Production files remain strictly unchanged.

Baseline SHA-256 Hashes:

| Artifact | Expected Baseline SHA-256 |
| --- | --- |
| `vn_stock.db` | `533b458507953ab6cf3574fdfe434e98a36e2ef662472f3ed0f3cfabaffffc4d` |
| `analysis_bundle.json` | `813fcfc1b8364b9aa6d243526d4a7e65e6547b18d373f4f18313b21e89af1042` |
| `bundle_manifest.json` | `4beb68faca546a06f6ba284a46dea6ee6e126f3fe79b5828446cb78a8366edaa` |
| `focus_extract.json` | `c3dd3752b1c26d59bfb50f7753242a6e292773d287e68907f4c9e3596c9ccb02` |
| `statement_taxonomy_sidecar.json` | `d4e5e73fa72e1d007ec7a7717413d1f6c606b557281d3baf365f89782b97c499` |
| `data/official-evidence/manifest.json` | `97c8da62f1fb36a030bb5535ff92a5b46f7ea88a89b67c5715b091ba97ef424a` |

---

## 3. Workstream Execution Plan & Market Coverage

* **Workstream A**: Inventory retained current-share candidates (`current_common_shares_outstanding`, `metadata` table in `vn_stock.db`, official citations).
* **Workstream B**: Build authority resolver with explicit lanes (`qualified_official` > `provider_reported` > `unavailable`).
* **Workstream C**: Resolve current effective shares for target market session with full lineage and conflict checks.
* **Workstream D**: Produce deterministic market-wide coverage counts across all 1,683 active tickers.
* **Workstream E**: Project valuation readiness (Market Cap, P/E, P/B, EV, EV/EBITDA) fail-closed.
* **Workstream F**: Implement deterministic conflict handling (official vs provider, unit mismatches, stale observations).
* **Workstream G**: Connect Producer section export and Consumer context pass-through verbatim.
* **Workstream H**: Connect top-level post-close operator `tools/operate_stocklookup.py`.
