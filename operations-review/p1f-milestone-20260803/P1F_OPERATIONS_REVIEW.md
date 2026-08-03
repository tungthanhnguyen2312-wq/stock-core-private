# P1F — Canonical Financial Production Activation

Milestone operations review. Date: **2026-08-03**. Base commit: `9d7f245`.
Runtime root: `C:\Projects\StockLookup\dashboard-runtime`.

---

## 1. File Allowlist

The following exact file allowlist governs all modifications for milestone P1F:

1. `ai-core-private/builders/build_ticker_context.py`
2. `stock-core-private/tools/operate_stocklookup.py`
3. `stock-core-private/tests/test_consumer_canonical_financial_facts.py`
4. `stock-core-private/README.md`
5. `stock-core-private/docs/CLI_REFERENCE.md`
6. `stock-core-private/docs/POST_CLOSE_RUNBOOK.md`
7. `stock-core-private/docs/PIPELINE_ARCHITECTURE.md`
8. `stock-core-private/docs/STATE.md`
9. `stock-core-private/docs/ROADMAP.md`
10. `stock-core-private/docs/DECISIONS.md`
11. `stock-core-private/operations-review/p1f-milestone-20260803/P1F_OPERATIONS_REVIEW.md`

No other files are modified.

---

## 2. Production Baseline & Hash Verification

Production database files and published release artifacts remain strictly unchanged. Baseline SHA-256 hashes verified byte-for-byte before and after the milestone:

| Artifact | SHA-256 Baseline | Status |
| --- | --- | --- |
| `vn_stock.db` | `533b458507953ab6cf3574fdfe434e98a36e2ef662472f3ed0f3cfabaffffc4d` | **MATCH** |
| `analysis_bundle.json` | `813fcfc1b8364b9aa6d243526d4a7e65e6547b18d373f4f18313b21e89af1042` | **MATCH** |
| `bundle_manifest.json` | `4beb68faca546a06f6ba284a46dea6ee6e126f3fe79b5828446cb78a8366edaa` | **MATCH** |
| `focus_extract.json` | `c3dd3752b1c26d59bfb50f7753242a6e292773d287e68907f4c9e3596c9ccb02` | **MATCH** |
| `statement_taxonomy_sidecar.json` | `d4e5e73fa72e1d007ec7a7717413d1f6c606b557281d3baf365f89782b97c499` | **MATCH** |
| `screen_snapshot.csv` | `e5c86db3f218885ddfddda632ebce138ea0d51ff5ad3d50d48adce7aba192e95` | **MATCH** |
| `data/official-evidence/manifest.json` | `97c8da62f1fb36a030bb5535ff92a5b46f7ea88a89b67c5715b091ba97ef424a` | **MATCH** |

---

## 3. Producer Integration

`export_ai_bundle.py` carries `--include-canonical-financial-facts` which invokes `canonical_financial_bundle_section.attach`.
- Disabled by default.
- When enabled via `--include-canonical-financial-facts`, attaches `tickers[ticker].canonical_financial_facts`.
- Additive only: legacy keys are completely untouched.
- Shards & calculation readiness read from `data/canonical-financial-facts/`.

---

## 4. Consumer Integration

`ai-core-private/builders/build_ticker_context.py` integrates `canonical_financial_facts_contract` and `apply_bundle_canonical_financial_facts_contract`.
- Pass-through verbatim of `canonical_financial_facts` section from Producer `analysis_bundle.json` into `context["canonical_financial_facts"]`.
- Does NOT recalculate metrics or derive scores/ratios.
- Fails closed on malformed status (`malformed`, `corrupt`, `invalid`).
- Backward compatible: legacy bundles without the key return `None` and load cleanly.

Three required test cases:
1. EBITDA-ready non-financial company (AAH): EBITDA is `ready`, facts preserved verbatim.
2. Financial institution (VCB): EBITDA is `not_applicable`, ROE is `ready`, facts preserved verbatim.
3. Conflicted or unavailable canonical case (HPG): `conflicted`/`unavailable` statuses preserved with reason, values withheld.

---

## 5. Operator Integration

`stock-core-private/tools/operate_stocklookup.py` extended with one new flag:
`--include-canonical-financial-facts`

Execution sequence in dry-run mode and execute mode:
1. preflight safety and production hash baseline
2. market-session resolution
3. existing market/runtime build
4. canonical fact-store verification
5. Producer bundle build with canonical financials enabled
6. Consumer context generation
7. Consumer validation
8. four-artifact manifest validation
9. exact-session integrity validation
10. atomic publication preview only
11. final post-close summary

---

## 6. Execution Evidence & Validation Results

* **Producer Integration Tests**: `tests/test_canonical_financial_facts.py` (52/52 PASSED)
* **Consumer Integration Tests**: `tests/test_consumer_canonical_financial_facts.py` (5/5 PASSED)
* **Operator Unit Tests**: `tests/test_operate_stocklookup.py` (18/18 PASSED)
* **Producer Double Build**: Deterministic double-build section byte-identical (MATCH)
* **Full Local Post-Close Dry Run**: `python tools/operate_stocklookup.py --runtime-root ../dashboard-runtime --include-canonical-financial-facts` (PASSED)
* **Production Hashes Unchanged**: 7/7 production files byte-identical (MATCH)
* **Syntax/Compile Check**: `python -m compileall` (PASSED)
* **Git Diff Check**: `git diff --check` (PASSED)
