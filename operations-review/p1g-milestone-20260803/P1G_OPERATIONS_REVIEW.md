# P1F — Canonical Financial Production Activation

Milestone operations review. Date: **2026-08-03**. Base commit: `cea7b2f` (Producer), `66733a4` (Consumer).
Runtime root: `C:\Projects\StockLookup\dashboard-runtime`.

---

## 1. File Allowlist

The following exact file allowlist governs all modifications for milestone P1G:

1. `stock-core-private/config/official_source_registry.json`
2. `stock-core-private/official_document_store.py`
3. `stock-core-private/corporate_action_events.py`
4. `stock-core-private/official_corporate_action_ledger.py`
5. `stock-core-private/share_transition_bridge.py`
6. `stock-core-private/market_wide_calculation_readiness.py`
7. `stock-core-private/canonical_financial_bundle_section.py`
8. `stock-core-private/export_ai_bundle.py`
9. `ai-core-private/builders/build_ticker_context.py`
10. `stock-core-private/tools/operate_stocklookup.py`
11. `stock-core-private/tests/test_p1g_data_authority.py`
12. `stock-core-private/tests/test_official_corporate_action_pillar.py`
13. `stock-core-private/README.md`
14. `stock-core-private/docs/CLI_REFERENCE.md`
15. `stock-core-private/docs/POST_CLOSE_RUNBOOK.md`
16. `stock-core-private/docs/PIPELINE_ARCHITECTURE.md`
17. `stock-core-private/docs/STATE.md`
18. `stock-core-private/docs/ROADMAP.md`
19. `stock-core-private/docs/DECISIONS.md`
20. `stock-core-private/operations-review/p1g-milestone-20260803/P1G_OPERATIONS_REVIEW.md`

No other files will be modified.

---

## 2. Baseline Production Checkpoints & Hashes

Production files remain strictly unchanged.

Baseline SHA-256 Hashes:

| Artifact | Expected Baseline SHA-256 |
| --- | --- |
| `vn_stock.db` | `533b458507953ab6cf3574fdfe434e98a36e2ef662472f3ed0f3cfabaffffc4d` |
| `analysis_bundle.json` | `813fcfc1b8364b9aa6d243526d4a7e65e6547b18d373f4f18313b21e89af1042` |
| `bundle_manifest.json` | `4beb68faca546a06f6ba284a46dea6ee6e126f3fe79b5828446cb78a8366edaa` |
| `focus_extract.json` | `c3dd3752b1c26d59bfb50f7753242a6e292773d287e68907f4c9e3596c9ccb02` |
| `statement_taxonomy_sidecar.json` | `d4e5e73fa72e1d007ec7a7717413d1f6c606b557281d3baf365f89782b97c499` |
| `screen_snapshot.csv` | `e5c86db3f218885ddfddda632ebce138ea0d51ff5ad3d50d48adce7aba192e95` |
| `data/official-evidence/manifest.json` | `97c8da62f1fb36a030bb5535ff92a5b46f7ea88a89b67c5715b091ba97ef424a` |

---

## 3. Workstream Execution Plan

* **Workstream A**: Activate official source registry (`HOSE`, `HNX`, `VSDC`, `ISSUER_IR`).
* **Workstream B**: Bounded official document acquisition for HPG & VNM.
* **Workstream C**: Corporate-action event ledger completion (support 9 event types, explicit lifecycle, ex-date enforcement).
* **Workstream D**: Dated shares-outstanding timeline.
* **Workstream E**: Official-event price adjustment factors (additive namespaces, strict ex-date requirement).
* **Workstream F**: Market-cap and valuation readiness (current vs historical market cap, EV/P-E/P-B/EV-EBITDA readiness).
* **Workstream G**: Producer & Consumer pass-through integration.
* **Workstream H**: Operator integration & final local post-close dry run.
