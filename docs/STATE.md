# Stock Lookup state

Last verified: **2026-08-03**, by an end-to-end production run of the supported operating
command against `dashboard-runtime` (reference session `2026-07-30`).

## Canonical state lines

`tools/handoff.py` parses these three lines by prefix. Keep the prefixes exactly as written.

- Active phase: development runs on two pillars — A, market-wide canonical financial normalization (layers 1–2 done as P1D, layer 3 done as P1E, layer 4 calculation readiness live, P1F canonical production activation completed); B, official corporate-action ingestion and price adjustment (step B1 delivered as a reviewable registry awaiting owner approval), which is now the only route to the P0 market-data gate. P1 exact-session integrity and P1B/P1C/P1F are done.
- Active milestone: pillar B step B1 sign-off — owner approval of `config/official_source_registry.json`. Every source is `declared`, `official_source_registry.admit()` refuses all of them, and B2–B6 cannot start until `activation` is `approved`. B6 is what unblocks market capitalisation, and therefore EV, EV/EBITDA, P/E and P/B, all currently at 0 tickers.
- Production state: the production artifact set was regenerated and validated end to end on 2026-08-03 through `tools/operate_stocklookup.py` (with `--include-canonical-financial-facts` verified dry run) and is byte-unchanged by P1F; `config/ticker_entity_profiles.csv` and every authoritative database are unchanged.

## Operate it

```powershell
python C:\Projects\StockLookup\stock-core-private\tools\operate_stocklookup.py --runtime-root C:\Projects\StockLookup\dashboard-runtime --execute --prepare-inputs
```

Drop `--execute` for a strict dry run; drop `--prepare-inputs` when the session inputs are
already fresh (it is the slow part — `candle_scan.py` alone is ~25 minutes over the full
universe); add `--publish` / `--publish --live` for the dashboard publisher. Exit codes:
`0` success · `1` gate failed (artifacts rolled back) · `2` bad invocation · `3` locked.
Full flag reference: `operations-review/local_runbook.md`. The command never fetches
prices, macro series or news; run the daily market chain first when the market data itself
is stale.

## Current production artifact set

Written into the runtime root by the command above, hash-bound to each other by the
exact-session proof in `bundle_manifest.json`:

| artifact | role |
| --- | --- |
| `analysis_bundle.json` | the full bundle the Consumer and Dashboard read |
| `bundle_manifest.json` | source hashes + the exact-session proof (`trusted_subset`) |
| `focus_extract.json` | the small truncation-resistant extract |
| `statement_taxonomy_sidecar.json` | generated statement-taxonomy evidence, session-bound |
| `reports/operate_stocklookup_latest.json` | deterministic operating report for the last run |

## What is live and usable

- **Exact-session bundle integrity.** Producer contract `stocklookup-producer/2026.08.03`,
  proof schema `1.1.0`, pinned identically on both sides. The proof covers **every**
  exported ticker with explicit `unproven_tickers` accounting, hash-binds the whole session
  artifact set, and the Consumer verifies cross-artifact session/`generated_at` agreement,
  per-ticker session identity, every declared artifact hash and the trusted-artifact
  namespace, with 31 named rejection reasons. See `docs/exact_session_bundle_contract.md`.
- **Generated statement taxonomy.** 1,381 payloads → 1,380 classified, 1 omitted (BIO, no
  reporting-period columns), byte-stable on unchanged inputs.
  `corporate_vas` 1,297 · `securities_company` 41 · `credit_institution` 29 ·
  `financial_specialized_ambiguous` 13. Authority level `generated_evidence`, strictly
  below `config/ticker_entity_profiles.csv`, which is **unchanged**;
  `CANONICAL_PROFILE_BACKFILL_AUTHORIZED = NO`. See `docs/statement_taxonomy_sidecar_contract.md`.
- **Altman Z' (1983 private-firm variant), historical-only.** Reachable through the
  authorized bundle path, not a standalone script. Verified live in the current production
  bundle: **HPG FY2024 Z' = 1.500557431830876 (grey)**; **VNM FY2024 Z' = 2.897596214248344
  (grey, `near_threshold` flagged** — 0.0024 below the 2.90 boundary). Financial filers
  never receive a score: SSI (securities), EVF (finance_company) and VCB (bank) all return
  `not_applicable`. Every non-eligible and every identity-blocked result carries its
  applicability verdict and a named reason. No Z'' variant exists and none was added.
- **Historical point-in-time relative valuation.** HPG FY2024 `pe` 10.55, `pb` 1.11,
  `ps` 0.91, `ev_sales` 1.46, `ev_ebitda` 8.86 — each carrying `price_as_of_date`
  (2024-12-31), `financial_period` (2024), `historical_only: true`,
  `market_dependent: false`, `as_of_semantics` and a warning naming the valuation date.
  `reference_at` is the build time and is never conflated with either.
- **Fundamental quality, fundamental-quality evidence, distribution evidence, corporate
  intelligence, corporate events, scenario analysis, analysis-lane eligibility** — all
  reachable through the bundle; the opt-in sections are enabled by the operating command.
- **Dashboard.** The company panel renders a Financial Distress section showing model
  variant, applicability, score, zone and the boundary warning, plus the generated
  statement taxonomy explicitly labelled as generated evidence. A filer the model does not
  apply to is never shown a score; a `status: available` result with no numeric score
  renders no number; malformed subsection data cannot break the section and all output
  stays escaped.

## What is blocked, and why

- **Price basis `unknown`, `verified: false`. Volume basis `unknown`, `verified: false`.**
  Unchanged by this milestone; no new direct source evidence was obtained. Everything
  current-market-dependent stays fail-closed for every ticker: current valuation, current
  return, adjusted return, beta, correlation, backtest, concentration, position sizing.
  `is_actionable` is `false` at the bundle root.
- The exact active VCI path, VCI corporate-action discovery, `exercise_ratio` semantics and
  official-URL discovery are **exhausted** as qualification routes. Do not reopen them.
  `VCI_PROVIDER_INTERNAL_ROUTE_BLOCKED_BY_RATIO_SEMANTICS`,
  `ACTIVE_PRICE_PATH_SEMANTICS_UNQUALIFIED`, `DOCUMENTED_RAW_ADJUSTED_PATH_UNAVAILABLE`.
- **EODHD is closed**: `EODHD_ROUTE_STATUS = REJECTED_BY_OWNER` (2026-08-03). The
  2026-08-02 private-shadow approval is withdrawn after read timeouts on two independent
  days. Do not test, retry, diagnose the network path, or propose a credential milestone;
  the modules remain in the tree, disabled and off the roadmap. The market-data gate is now
  routed through pillar B (`docs/official_corporate_action_ingestion_design.md`).
- **Trust state of the current production bundle is `untrusted_basis`.** Integrity is
  `exact_session_verified`; the basis axis is `unqualified`. Both are reported separately
  so an unverified price basis no longer suppresses honest non-market readiness.
- **Share-transition coverage** through the trusted session is still unproven for HPG and
  VNM (latest qualified historical identities only).

## Measured coverage (period 2025-Q4, 1,148 tickers with a snapshot row)

Screening tier, provider-reported — statement scope, restatement state and publication date
are unknown for this tier, so these are diagnostics, not evidence-qualified results.

| capability | runnable | blocked by |
| --- | --- | --- |
| liquidity screen | 1,113 (96.95%) | `current_assets`/`current_liabilities` 35 |
| leverage screen | 1,077 (93.82%) | `total_liabilities` 35, `equity`/`total_assets` 6 |
| DuPont ROE | 1,075 (93.64%) | `net_profit` 23, `revenue` 21 |
| earnings quality | 818 (71.25%) | `operating_cash_flow` 319, `net_profit` 23 |
| Altman Z' inputs complete | 22 (1.92%) | **`retained_earnings` 1,097** |

Input availability: `retained_earnings` 51 available / 1,097 missing · `ebit` 8 / 1,140 ·
`ebitda` 0 / 1,148 · `interest_expense` 266 / 882 · `operating_cash_flow` 829 / 319.

Altman applicability across the 1,380 classified tickers (real authority order, real
industry labels): **eligible 3 · not_applicable 83 · insufficient_evidence 1,294**.
The 83 reconcile exactly to 41 `securities_company` + 29 `credit_institution` +
13 `financial_specialized_ambiguous`. Of the 1,294, **1,289 are blocked on an unresolved
issuer entity type** and 5 on a non-qualified manufacturing industry.

Altman scores actually available in the production bundle: **2** (HPG, VNM) — eligibility
is necessary but not sufficient; a score also needs all seven qualified identities.

Current-market-dependent capabilities: **0 tickers**, blocked by market semantics.

## Market-wide raw financial retention (P1D, 2026-08-03)

Pillar A layers 1–2, from `data/market-wide-financials/coverage_report.json`. Raw identity
availability only — statement scope, currency, unit scale, sign and cumulative basis are all
still `unknown`, so **nothing here is an evidence-qualified value**.

| | |
| --- | --- |
| payloads discovered | 4,195 (1 unparsed: `BIO_balance_sheet.parquet`) |
| raw observations retained | 1,546,197 across 1,493 tickers |
| active universe (HSX 402 · HNX 299 · UPCOM 738) | 1,439 |
| in store **and** active universe | 1,308 |
| active universe with no retained payload at all | 131 |
| all three statement families | 1,198 of 1,308 |
| shards byte-reproducible under `--check` | 1,493 / 1,493 |

EBITDA / EV-EBITDA applicability over the 1,308: `not_applicable` **82** (was 7),
`applicable_subject_to_inputs` 8, `insufficient_evidence` 1,218. Archetype authority:
`manual_profile` 15 · `generated_statement_evidence` 75 · `unknown` 1,218.

Raw-identity coverage for the derived-EBITDA inputs, over the 1,226 tickers not ruled out:
`profit_before_tax` 1,202 · `depreciation_amortization` 1,123 · `interest_expense` 1,066 ·
**all three 1,016 (82.9%)**. Enterprise-value balance-sheet inputs complete for 1,148;
market capitalisation still blocked on the price basis.

### Two corrections this measurement forced on the blocker list above — both now closed by P1E

- The screening-tier table records `ebitda` as **0 available / 1,148** and EBITDA as
  computable for 2 tickers market-wide. The raw depreciation identity is present for
  **1,123** tickers. The retained cash-flow vocabulary splits into two mutually exclusive
  provider dialects that partition the universe exactly (905 `depreciation_of_fixed_assets_and_investment_properties`
  + 338 `depreciation_and_amortization` = 1,243). A mapping that knows one dialect reports
  ~73% on a metric present for ~100% of filers.
- The table records `retained_earnings` as **51 available / 1,097 missing**. The raw
  identity (`undistributed_earnings`) is present for **1,148** tickers. The blocker is in
  the snapshot projection, not the source data.

Both were mapping work, and P1E did it.

## Market-wide canonical financial facts (P1E, 2026-08-03)

Pillar A layer 3, from `data/canonical-financial-facts/`. Detailed evidence:
`operations-review/p1e-milestone-20260803/P1E_OPERATIONS_REVIEW.md`.

| | |
| --- | --- |
| tickers with a fact shard | 1,493 |
| canonical facts | 195,552 |
| `qualified` | **2** (HPG and VNM `retained_earnings` 2024-Q4) |
| `provider_reported` | 93,749 |
| `partial` | 5,004 |
| `conflicted` | 12,501 |
| `unavailable` | 84,296 |
| unresolved-metric queue (per metric, never per ticker) | 101,801 |
| conflict queue | 12,619 |

`provider_reported` is the honest market-wide ceiling and is **not** an evidence-qualified
value. The retained payloads carry no currency column, no unit header and no anchor fixing the
absolute unit; VND-under-VAS is a convention, not evidence in these bytes. The only route to
`qualified` is agreement with an independently promoted official citation, which today exists
for HPG and VNM only — HPG's provider 2024-Q4 `undistributed_earnings` matches the audited
FY2024 citation digit for digit (49,599,124,109,203), and VNM's likewise.

### Calculation readiness, 1,492 tickers

| capability | ready | note |
| --- | --- | --- |
| ROE | **1,321** | single-period, never annualised |
| EBITDA | **231** | was 2; reconciliation contract with full formula lineage |
| EBITDA / EV-EBITDA `not_applicable` | 83 | financial filers, a verdict not a gap |
| EV balance-sheet components | 1,338 | debt and cash ready; EV itself is not |
| market capitalisation · EV · EV/EBITDA · P/E · P/B | **0** | blocked, see below |

### Three findings P1E's measurements force

- **Provider is not dialect.** HPG's income statement carries `source = KBS` and the full VCI
  vocabulary. A mapping keyed on the `source` column drops every metric on that payload, so
  candidate matching keys on the raw item id and dialect is detected from the vocabulary.
- **Cash-flow period labels are not trustworthy.** HPG's cash-flow column labelled `2025-Q2`
  carries an end-of-period cash balance matching the *2026-Q1* balance sheet. Balance-sheet
  cash versus cash-flow end cash is therefore a period-attribution gate: divergent →
  `conflicted`, unverifiable → capped at `partial`. It diverges for 314 of 678 sampled
  ticker-periods, and it is the main reason EBITDA is 231 rather than ~1,000.
- **The provider tier caps retention at 8 periods** ("Community edition: Financial statements
  limited to 8 periods"). Every ticker has at most 8 quarterly periods and there are **no
  annual periods at all**, which is why annual figures cannot be read from the store.

### Top remaining blockers, by tickers affected

1. **Price/volume basis unverified — every ticker.** Blocks the entire current-market tier and
   now also market capitalisation, and therefore EV, EV/EBITDA, P/E and P/B at 0 tickers.
   EODHD is closed; the route is pillar B, gated on B1 owner approval.
2. **Issuer entity type unresolved — 1,218 tickers.** The generated taxonomy can only withhold
   a model, never grant one, so `corporate_vas` alone leaves Altman on
   `insufficient_evidence`. Needs an authoritative issuer-type source, not more taxonomy work.
3. **No retained line carries a share count.** `common_shares` and `paid_in_capital` are
   paid-in capital amounts in currency; converting them needs an assumed par value. This is an
   independent second blocker on market capitalisation, distinct from the price basis.
4. **131 active-universe tickers have no retained statement payload — now fully classified and
   closed as an acquisition item.** All **131 of 131** were probed through the authorized
   provider path and all **131 returned `source_empty_confirmed`** from both KBS and VCI across
   all three statement families; zero `payload_available`, `provider_error` or
   `retrieval_failure`. The gap is in the source, so no acquisition work, retry or credential
   change will close it — only a different statement source would. This also corrects
   `scrape_meta.csv`, which records all 131 as `empty` while `bctc_sync.call_api` returns
   `None` for any non-network exception, making a genuine empty source and a parse error
   indistinguishable there.

## Historical corrections that remain in force

- HPG FY2024 `current_liabilities` (75,225,243,262,689) and `retained_earnings`
  (49,599,124,109,203) are qualified in `data/official-evidence/financial_identity_citations.jsonl`,
  read from the retained hash-verified `hpg-consolidated-fy2024-audited.pdf` and
  cross-checked against the statement's own printed arithmetic. VNM's two identities were
  promoted the same way.
- `evidence_promotion.py` is the only approved evidence write boundary
  (`docs/DECISIONS.md`, "Approved evidence write boundary").
- `risk_liquidity.py::evaluate_market_risk()` no longer hardcodes `is_actionable=True` on
  `point_in_time_beta`/`point_in_time_correlation`; both follow `current_actionable`.
- Relative-valuation multiples carry explicit historical-only temporal labelling; an FY2024
  P/E is no longer indistinguishable from a current-market claim.
- `bctc_processor.py` resolves `data_bctc/`, `financial_snapshot.*`, `logs/` and `reports/`
  through the runtime root like the rest of the daily chain; it previously read and wrote
  them inside the source repository.

## Official corporate-action foundation (pillar B, 2026-08-03)

`config/official_source_registry.json` declares HOSE, HNX, VSDC and qualified issuer IR
domains with allowed hosts, document types, discovery path, request rate, timeouts, bounded
retry, robots/terms considerations, retention and failure classification.
`approval_state = AWAITING_OWNER_APPROVAL`; **every source is `declared`, not `approved`**, and
`official_source_registry.admit()` refuses a declared source, so the reviewable JSON is what
gates the network. An agent may not set `activation` to `approved`. EODHD is recorded in the
registry itself as `REJECTED_BY_OWNER` and excluded.

`official_document_store.py` retains official documents content-addressed by SHA-256, re-hashed
at adoption, never overwritten and never deleted; a correction is a new record with
`supersedes_document_id`. `corporate_action_events.py` extracts typed, cited observations with
an explicit lifecycle (`proposed → approved → announced → record_date_confirmed → executed`,
plus amended/cancelled/unknown) capped per document class.
`official_corporate_action_ledger.py` links, deduplicates, resolves supersession and replays
deterministically. It is separate from `corporate_action_ledger.py`, whose contract is unchanged.

**Bounded vertical slice, HPG, offline, no network request.** Two retained official documents
→ 2 documents adopted (store `verify` ok) → 2 observations → **1 qualified executed
`stock_dividend`**: `shares_issued` 767,498,665, `shares_after` 8,442,964,520, ratio
0.0999937567, five field-level citations, both source hashes, replay fingerprint stable across
runs. **Adjustment factor `not_ready`, blocked by `missing_explicit_official_ex_date`** —
neither document states an ex-date, and a record, payment, listing or trading date never
substitutes for one. The scanned issuer notice's OCR-damaged share counts are refused outright
rather than emitted. `PRICE_ADJUSTMENT_FACTOR_PILOT: NOT_READY`.

## Next highest-value milestone

**Pillar B step B1 sign-off** — owner approval of `config/official_source_registry.json`. It is
a governance decision, not code: the registry is written, enforced and reviewable, and until
`activation` is `approved` no document can be acquired from HOSE, HNX or VSDC, so B2–B6 cannot
start. B6 is the only remaining route to a qualified price basis now that EODHD is closed, and
it is what unblocks market capitalisation and therefore EV, EV/EBITDA, P/E and P/B.

Running second, and independent of it: qualify `issuer_entity_type` for the 1,218 tickers
where it is unresolved, from an authoritative source (exchange/issuer registration data).
Generated taxonomy cannot do this by construction — it may only withhold a model, never
grant one — so it needs a real issuer-type source, and it is the gate between 8 confirmed
applicable tickers and universe-wide historical screening.

Third: extend official-citation coverage beyond HPG and VNM. It is the only mechanism that
promotes a canonical fact above `provider_reported`, and at 2 qualified facts market-wide it is
the binding constraint on evidence-qualified financial analysis.
