# P1H — Current Share Basis and Valuation Readiness Activation

> ## SUPERSEDED 2026-08-03 by P1J.1
>
> The "3 qualified" current shares and the market caps built on them do not survive review: the
> anchors are FY2024 period-end figures that no ledger can carry to a session, two of the three
> literals were wrong, the session price was read as the ticker's newest close rather than the
> session's, and the market cap ignored the price basis when deciding its own qualification.
> See `operations-review/p1j1-share-authority-integrity-20260803/P1J1_OPERATIONS_REVIEW.md`.

Milestone operations review. Date: **2026-08-03**. Base commit: `a4d01cf` (Producer), `66733a4` (Consumer).
Runtime root: `C:\Projects\StockLookup\dashboard-runtime`.

---

## 1. File Allowlist

The following exact file allowlist governs all modifications for milestone P1H:

1. `stock-core-private/share_transition_bridge.py`
2. `stock-core-private/market_wide_calculation_readiness.py`
3. `stock-core-private/canonical_financial_bundle_section.py`
4. `stock-core-private/export_ai_bundle.py`
5. `ai-core-private/builders/build_ticker_context.py`
6. `stock-core-private/tools/operate_stocklookup.py`
7. `stock-core-private/tests/test_p1h_valuation_readiness.py`
8. `stock-core-private/README.md`
9. `stock-core-private/docs/CLI_REFERENCE.md`
10. `stock-core-private/docs/POST_CLOSE_RUNBOOK.md`
11. `stock-core-private/docs/PIPELINE_ARCHITECTURE.md`
12. `stock-core-private/docs/STATE.md`
13. `stock-core-private/docs/ROADMAP.md`
14. `stock-core-private/docs/DECISIONS.md`
15. `stock-core-private/operations-review/p1h-valuation-readiness-20260803/P1H_OPERATIONS_REVIEW.md`

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

* **Workstream A**: Resolve current effective shares using dated shares timeline and evidence authority order (`HPG`, `VNM`, `VCB`, unavailable cases).
* **Workstream B**: Resolve current-session market price input from runtime session anchor.
* **Workstream C**: Compute reconstructed current market capitalization (`resolved_session_price * current_effective_shares`) distinguishing snapshot vs historical.
* **Workstream D**: Activate valuation readiness for P/E, P/B, EV, and EV/EBITDA fail-closed.
* **Workstream E**: Market-wide classification counts across active universe.
* **Workstream F**: Producer section export, Consumer pass-through, and post-close operator integration.
