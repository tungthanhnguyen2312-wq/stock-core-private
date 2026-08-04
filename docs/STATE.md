# Stock Lookup state

Last verified: **2026-08-03**, by an end-to-end production run of the supported operating
command against `dashboard-runtime` (reference session `2026-07-30`).

## Canonical state lines

`tools/handoff.py` parses these three lines by prefix. Keep the prefixes exactly as written.

- Active phase: development runs on two pillars — A, market-wide canonical financial normalization (layers 1–4 complete and active); B, official corporate-action evidence, dated shares timeline, price adjustment factors, and provider share authority (measured and fail-closed as of P1J.1; **1 of 1,683 tickers has a qualified current share count** after B1.1, and the official ledger holds 1 qualified executed event). P0 market-data basis remains open and is the binding constraint: the **generic** price and volume basis are still `unknown`/`unverified`, so every current-market capability stays blocked — a **`vci.`-namespaced shadow** basis is qualified (P0-V/P0-W, below) and unlocks nothing generic. VCI is now recorded as **not raw-as-traded eligible**, which closed the previously-open P2a historical valuation path. **KBS is now recorded the same way** (P0-Z), from its own bounded lane and not inherited: `empirically_event_adjusted` at the `empirically_deduced` tier, with `volume_unit = shares` / `trading_value_unit = VND` and `volume_market_scope = unknown` — descriptive and provider-scoped technical use is available, liquidity and point-in-time use is unavailable by contract. P1 exact-session integrity, P1B/P1C/P1F/P1G/P1H/P1I/P1J/P1J.1 completed.
- Active milestone: P0-Z KBS empirical price-and-volume basis qualification and capability relaxation — **PARTIAL**. Reopens exactly one closed lane. Phase 1C's finding stands and is re-confirmed against six fresh payloads (no adjustment flag, no unit declaration, no trade-method metadata); what is superseded is the inference that the fields were therefore *unusable*. New canonical qualification ladder in `evidence_qualification_tiers.py` (`documented_verified` / `empirically_deduced` / `observed_only` / `unknown` / `conflicted` / `invalidated`); a verdict at `empirically_deduced` must carry all 13 retention fields or it is refused. Six bounded requests (budget 6), HPG/VNM/VCB, 66 sessions. **Price:** `empirically_event_adjusted`, `empirically_deduced` — pre-event prices sit off the HOSE tick lattice and the off-lattice prefix terminates exactly at a qualified ex-right date for HPG (2026-05-25 share issue), VCB (2026-07-23 cash) and VNM (2026-06-26 cash); independently, `va` is absent over exactly the off-lattice runs in all 66 sessions and its presence tracks the boundary, not the calendar. `provider_methodology = unknown`, `coverage_generalization = limited_to_tested_windows`, `raw_as_traded_eligible = false`, `historical_mutability = not_observed` (the 9-session re-observation is byte-identical but spans no event, so it is a control, not an immutability proof). **Units:** `volume_unit = shares`, `trading_value_unit = VND`, `empirically_deduced` — the VWAP identity earns only the scale *quotient* (1.0, from 36 discriminating rows over 3 tickers and 3 price levels, all 14 competing quotients rejected); the absolute anchor is earned separately from a retained issued-share count used strictly as an order-of-magnitude falsifier. 2 rows are explained by no candidate scale and are retained as contradictions, not resolved. **Volume adjustment:** `not_observed`, never derived from the price finding — but KBS restated prices on 13 VCB sessions while returning volumes byte-identical to the independently retained pre-event series, so the two fields demonstrably move on different schedules. **Market scope:** all 6 dimensions `unknown`; upgrading one needs 2 admissible independent observations with all 6 confounders eliminated, and secondary media are counted and never qualify. New `kbs_capability_matrix.py`: **15 descriptive/technical capabilities available** under 7 mandatory warnings and 7 provenance fields, **2 conditional** behind `return_type = provider_series_return` (the 3 forbidden return labels raise), shadow backtest **eligibility defined and not implemented** (8 conditions), **13 liquidity/execution/point-in-time capabilities `unavailable_by_contract`**; 20 consumers classified, unregistered ones fail closed. `is_actionable` unchanged, `liquidity_actionable = false`, no production write. 36 new tests; 389 tests passing across the validated suites (367 basis/capability/gate/export + 22 Consumer readiness and pass-through). See `operations-review/kbs-empirical-basis-20260804/` and `docs/kbs_empirical_basis_qualification.md`. Previous milestone: P0-Y market-volume and liquidity availability capability closeout — **PASS**. Converts the `63ecc48` VCI volume findings into system-wide capability boundaries. Two terminology corrections, no verdict changed: `market_scope = partially_qualified` → `overall_market_scope = partially_observed_but_not_qualified`, and `opening_auction_inclusion = qualified` → `demonstrated_for_observed_ato_field` (the narrow result — one observed ATO-labelled quantity is inside the provider accumulator; `general_auction_composition = partially_observed`, `closing_auction_inclusion = unknown`). `matched_trade_inclusion`, `negotiated_inclusion` and `odd_lot_inclusion` promoted from `unknown`-with-sidecar to top-level `unavailable_from_observed_vci_surfaces`. New `market_volume_capability_matrix.py`: **9 descriptive/analytical capabilities retained** under mandatory provider-scope warnings, **13 liquidity and execution capabilities `unavailable_by_contract`** with `reason = complete_market_composition_not_qualified`, `reopen_condition = new_authoritative_source_contract` — explicitly *not* reopenable by further VCI pagination or endpoint probing. 23 volume consumers classified; unregistered consumers fail closed. The latent path is the point: every liquidity gate was keyed to `volume_basis_verified`, which the shares finding invited someone to flip; `vci_volume_basis.validate_forward` now returns `liquidity_activation_permitted: False` on success, and `analysis_lane_eligibility` emits an unconditional liquidity-contract refusal that does not lift when the basis verifies. HOSE trading statistics registered in `official_authority_candidates.py` as a **future qualification candidate only** — no URL, `automatic_acquisition_authorized = false`, 8 open semantic questions, preferred (not sole) official authority path. No network request, no evidence artifact rewritten, `liquidity_actionable = false`, `further_vci_pagination_authorized = false`, `further_vci_endpoint_probe_authorized = false`. 553 tests + 11 subtests passing. See `operations-review/market-volume-capability-closeout-20260804/` and `docs/market_volume_capability_contract.md`.
- Production state: the production artifact set was regenerated and validated end to end on 2026-08-03 through `tools/operate_stocklookup.py` (with `--include-canonical-financial-facts` verified dry run) and is byte-unchanged by P1J; `config/official_source_registry.json` is approved; `config/ticker_entity_profiles.csv` and every authoritative database are unchanged.

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
- ~~**Historical point-in-time relative valuation.**~~ **BLOCKED 2026-08-04.** The HPG
  FY2024 multiples (`pe` 10.55, `pb` 1.11, `ps` 0.91, `ev_sales` 1.46, `ev_ebitda` 8.86)
  rested on a cited 2024-12-31 close of 19,830 accepted as raw as-quoted. It is not: 19,830
  is not on the 50 VND HOSE tick for its band, and HPG's 2025-06-26 and 2026-05-25 share
  issues both post-date it. The citation now rejects with
  `provider_series_retrospectively_rewritten`. The temporal-marker work on those envelopes
  (`historical_only`, `as_of_semantics`) was correct and is retained; the **price basis
  underneath them was not**. Re-enabling P2a needs a raw as-traded or documented-adjusted
  source, not a relabelling.
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
- **Only one ticker has a qualified current share count** (HPG, B1.1 — see below). For the
  other 1,682 the retained official anchors are
  FY2024 `period_end_shares_outstanding` citations, and promoting a period-end figure to a
  current one needs a corporate-action ledger proven complete over the interval.
  `corporate_event_records` holds 250 rows across **5 of 1,683 tickers** at
  `coverage_status = partial_unqualified_50_row_cap`, so the promotion gate is shut
  market-wide. The market-wide ceiling for current shares is `provider_reported`, whose
  concept is `ISSUED_SHARES` — treasury shares are not deducted, so it is not comparable with
  the `common_outstanding` anchors and never silently substitutes for them.

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
`approval_state.state = APPROVED` since commit `a4d01cf` (P1G): **all four sources — `hose`,
`hnx`, `vsdc`, `issuer_ir` — carry `activation: approved`**, and `official_source_registry.admit()`
now admits them, so the network path for official-document acquisition is open. An agent may not
set `activation` to `approved`; this paragraph previously still described the pre-P1G state and
contradicted the file it describes. EODHD is recorded in the registry itself as
`REJECTED_BY_OWNER` and excluded.

> **B1_APPROVAL_STATUS: VERIFIED — the acquisition path is open.** The owner confirmed on
> 2026-08-03 that they approved the registry personally and that the originally recorded
> `14:00` was Asia/Ho_Chi_Minh. The canonical instant is therefore `2026-08-03T07:00:00Z`,
> which is consistent with the commit that wrote it (`a4d01cf`, 07:22Z); the earlier
> `14:00:00Z` was a local time written with a `Z`. `approved_at_provenance` records the clock
> and the confirmation, `approval_instant_verdict()` returns `verified`, and `admit()` admits
> all four sources — `hose`, `hnx`, `vsdc`, `issuer_ir`.
>
> The gate itself is unchanged and still closes: removing `approved_at_provenance` returns the
> registry to refusing everything, and that is under test. What changed was a fact supplied by
> the owner, not the standard.

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

## Current-share authority (P1J.1, measured 2026-08-03)

From `market_wide_current_shares_resolver.resolve_market_wide_shares()`, measured on the call
against the retained runtime. Every earlier figure in this row of the roadmap was a literal in
`tools/operate_stocklookup.py`, not a measurement.

| lane | session 2026-08-03 (B1.1) |
| --- | --- |
| `qualified_official` — **HPG** | **1** |
| `provider_reported_lagged` | 1,679 |
| `provider_reported_unverifiable_freshness` (VCB, SSI) | 2 |
| `unavailable` | 1 |
| active universe | 1,683 |

The two sessions differ only in the provider observation's age: `metadata.updated` is
2026-07-30 for the whole universe, so against a 2026-08-03 session every provider value is four
days behind with no ledger covering the interval. Running `meta_sync.py` for the session moves
the universe back into `provider_reported_current`; nothing else does.

VCB and SSI are withheld because each carries an `ISS` (issuance) event with no ex-right date,
and a record, issue or payment date never substitutes for one.

### B1.1 — the first qualified current share count

**HPG = 8,442,964,520, effective 2026-07-02.** Not a period-end figure carried forward: the
issuer's own listing-change notice states `shares_after` outright, the official ledger holds it
as a qualified executed `stock_dividend` (event `b7a97e12…`, document `7d5eff9b…`, content hash
`cb41c96e…`, replay fingerprint stable), and the provider's independent 2026-07-30 observation
reports the same digits. Promoted through `evidence_promotion.py` — the sole write boundary —
into `share_basis_citations.jsonl` as `identity_type: current_shares_outstanding_after_event`.

The count had been sitting in the ledger since 2026-08-02 with nothing reading it: the resolver
looked only for `period_end_shares_outstanding`, so a published share count sat one directory
away while HPG resolved as `provider_reported_lagged`.

**VNM and VCB are not promoted**, and the reason is now specific:
`anchor_is_a_period_end_figure_not_a_dated_current_count`. Their FY2024 citations describe
31 December 2024; no retained document covers the interval to the session. Closing that needs an
official notice per ticker, not more code.

### `corroborated_period_end` — shadow lane, not an authority

A period-end anchor whose count an independent observation matches has the same *shape* as the
evidence that promotes an executed event, and not the same strength. It is measured but
quarantined: **shadow-only**, `authority_rank` 1 against executed-event evidence's 2, never a
value `authority` may take, never counted in the production lanes, and structurally unable to
raise `is_actionable`. Promoting it out of shadow needs its own validation and its own owner
decision.

Measured for session 2026-08-03: **1 eligible — VNM**, whose observation is carrying **576
days** (2024-12-31 → 2026-07-30). HPG is out of scope (its anchor is an executed event, which
outranks this lane). VCB is refused: its observation contradicts its anchor, which the retained
VSDC notice independently explains.

Every verdict carries `proves_no_intervening_event: false` and cannot be made to say otherwise.
Agreement proves the **net** count is unchanged, not that nothing happened — two offsetting
events produce the same number.

### Retained evidence is exhausted for share basis — audited 2026-08-03

HPG was the only ticker promotable from documents already on disk. **This audit is closed**;
do not re-scan these 38 documents unless a new source appears or the evidence contract changes.
The rest were checked and are insufficient:

- **VCB** — `operations-review/non-cash-corporate-action-official-evidence/vsdc-vcb-listing-change-execution.html`
  is a genuine VSDC notice for a 2025 share-issuing dividend (record date 2025-03-13, official
  trading date 2025-05-09) but states **no `shares_after` and no ratio**, so it cannot establish
  a count and deriving one would be backsolving. It does confirm documentarily that a
  share-changing event post-dates VCB's FY2024 anchor, which is why that anchor must not be
  promoted and why VCB's `provider_reported_unverifiable_freshness` verdict is right. It also
  carries a record date and a trading date but no ex-date — the pattern already on record.
- **VNM** — the retained 2026 reviewed interim statements (72 pages) do not restate the share
  count in any form; a digit search for `2,089,955,445` returns nothing. No newer anchor exists.
- `operations-review/governed-official-evidence-v1/` holds unadopted documents for PAN, SSI,
  VCB and VNM, but they are annual reports, audited statements and AGM resolutions — period-end
  sources, not executed-event notices, so adopting them would add anchors the promotion gate
  correctly refuses.

Everything beyond HPG therefore requires **acquiring** a notice, which requires the registry to
admit again, which requires the owner to record the approval instant's clock provenance.

**Retired figures.** `qualified_official 3`, `provider_reported_current 1,677`,
`provider_reported_stale 2`, `provider_reported_market_cap 1,471`, `pe_ready 1,391`,
`pb_ready 1,289`, `ev_ready 1,247`, `ev_ebitda_ready 111` were literals. The valuation-readiness
counts are not restated here because no run has ever computed them; a real measurement would be
a pass over the canonical fact store, which the operating command does not do.

## Next highest-value milestone

**Pillar B steps B2–B6 — official-document acquisition. Governed since 2026-08-04.** The
registry admits, and `acquire()` now consults it before every request (it previously
consulted nothing). The registry also supplies the requestable document vocabulary, so
`ex_right_notice`, `listing_change_notice` and `last_registration_date_notice` are
requestable for the first time — the ex-date the adjustment factor is blocked on could not
previously be asked for.

**The first live governed acquisition ran on 2026-08-04**: one VSDC announcement index page,
`https://vsd.vn/en/alc/6`, retained at
`sha256:97778a8215123f61db098e02682ff7e9518260aa728fa4a7224821ca1886cfd0` (51,080 bytes,
`text/html`, HTTP 200, no redirect, one request). The entry URL was **observed**, not assumed:
it is the breadcrumb `href="/en/alc/6"` inside the already-retained VNM notice
`/en/ad/177392`. The registry now declares `announcement_index_page` as an
`index_document_types` entry **for vsdc only**; index pages are acquirable discovery inputs and
are refused by `official_document_store.adopt_retained_document`, so one can never reach the
ledger, the resolver, `qualified_official` or `corroborated_period_end`.
`official_listing_page_parser.py` reads candidate links out of the stored bytes with no I/O.
See `operations-review/vnm-listing-discovery-20260804/`.

That page yielded **0 VNM candidates** — it is a chronological all-issuer feed whose 14 entries
were all dated 2026-08-03/04, and VNM's most recent VSDC announcement is 2026-06-17. The
capability is proven; this entry URL's recency window is the limit. An **offline** parse of the
already-retained VNM notice yields **10 deterministic VNM candidates**, none of which is a
capital-structure event: VSDC's VNM announcements from 2023-07 to 2026-06 are cash dividends,
AGMs and one record-date correction. A VSDC cash-dividend record-date notice carries issuer,
ISIN, par value, record date and payment rate and **no share count**, so none of the 10 can
corroborate `2,089,955,445`. The class that does carry an absolute registered share quantity is
"adjustment of the number of registered shares" (observed for CTR on the acquired page and for
VCB in the retained artifact); no such VNM notice appears in the retained window.

The constraint is coverage: almost nothing has been
acquired through it. The ledger
holds 250 rows across **5 of 1,683 tickers** at `partial_unqualified_50_row_cap`, which is the
single fact that keeps `qualified_official` current shares at 0 and keeps the adjustment factor
at `not_ready`. B6 remains the only route to a qualified price basis now that EODHD is closed,
and it is what unblocks market capitalisation and therefore EV, EV/EBITDA, P/E and P/B.

The first acquisition target is the ex-right date for the two `ISS` events already retained
without one (VCB, SSI). They are the only two tickers whose share count is withheld for a reason
a single document would resolve, so they measure the acquisition path end to end at minimum
cost.

Running second, and independent of it: qualify `issuer_entity_type` for the 1,218 tickers
where it is unresolved, from an authoritative source (exchange/issuer registration data).
Generated taxonomy cannot do this by construction — it may only withhold a model, never
grant one — so it needs a real issuer-type source, and it is the gate between 8 confirmed
applicable tickers and universe-wide historical screening.

Third: extend official-citation coverage beyond HPG and VNM. It is the only mechanism that
promotes a canonical fact above `provider_reported`, and at 2 qualified facts market-wide it is
the binding constraint on evidence-qualified financial analysis.

**Not next, and why.** Expanding official *share* authority to VN30/HNX30 reads like an
independent lane but is not: a dated official share anchor is a HOSE/HNX/VSDC document plus a
ledger that carries it forward, so it is B2–B6's output, not a parallel workstream. Running it
first would produce more FY2024 period-end anchors, and a period-end anchor with no ledger is
exactly what the three existing ones already are — none of which can be promoted to a current
share count.

Also not next: wiring the `canonical_financial_facts` section into the published bundle and the
Consumer. The section computes a current market cap from an unverified price basis and an
`ISSUED_SHARES` count; publishing it into the AI context before B1 would put an unqualified
number in front of a reader, which is the failure the fail-closed contract exists to prevent.
