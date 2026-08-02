# Stock Lookup state

Last verified: **2026-08-03**, by an end-to-end production run of the supported operating
command against `dashboard-runtime` (reference session `2026-07-30`).

## Canonical state lines

`tools/handoff.py` parses these three lines by prefix. Keep the prefixes exactly as written.

- Active phase: P0 market-data basis qualification is the only remaining hard gate; P1 exact-session integrity and P1B/P1C (generated taxonomy sidecar, one-command operating workflow) are done.
- Active milestone: qualify `issuer_entity_type` for the ~1,289 tickers where it is unresolved, and retain `retained_earnings` systemically in the statement sync; neither depends on the blocked market-data basis.
- Production state: the production artifact set was regenerated and validated end to end on 2026-08-03 through `tools/operate_stocklookup.py`; `config/ticker_entity_profiles.csv` and every authoritative database are unchanged.

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
- **EODHD**: `MARKET_DATA_SOURCE_AUTHORITY_APPROVED = YES_PRIVATE_SHADOW_EODHD`. No live
  token was exercised in this milestone and none was printed, inspected or committed. The
  one bounded attempt on 2026-08-02 timed out before any payload qualified; that is a
  provider-responsiveness result, not evidence about authentication.
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

### Top remaining blockers, by tickers affected

1. **Issuer entity type unresolved — 1,289 tickers.** The generated taxonomy can only
   withhold a model, never grant one, so `corporate_vas` alone leaves Altman on
   `insufficient_evidence`. Unlocking this needs an authoritative issuer-type source, not
   more taxonomy work. Highest analytical value by a wide margin.
2. **`retained_earnings` not retained — 1,097 tickers.** The single input that blocks
   Altman at the screening tier. A systemic mapping/retention fix in the statement sync,
   not per-ticker PDF reading.
3. **`operating_cash_flow` missing — 319 tickers.** Blocks earnings quality.
4. **Price/volume basis unverified — every ticker.** Blocks the entire current-market tier.
   Needs a new market-data source authority; the existing provider routes are exhausted.

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

## Next highest-value milestone

Qualify `issuer_entity_type` for the ~1,289 tickers where it is unresolved, from an
authoritative source (exchange/issuer registration data), and retain `retained_earnings`
systemically in the statement sync. Together these are the only two gaps standing between
the current 3 eligible tickers and universe-wide historical distress screening — and
neither depends on the blocked market-data basis.
