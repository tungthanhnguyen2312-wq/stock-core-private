# Stock Lookup roadmap

## Active development: two pillars (2026-08-03)

Development has moved off per-ticker financial pilots. Adding a third HPG/VNM-style
qualified ticker is explicitly **not** the next milestone. The two systems below are, and
every P-gate below is now reached through one of them.

- **Pillar A — market-wide canonical financial normalization** — `docs/market_wide_financial_normalization_contract.md`.
  Layers 1 (raw retention, no allowlist) and 2 (statement taxonomy and model applicability)
  shipped 2026-08-03: 1,546,197 raw observations over 1,493 tickers, byte-reproducible,
  incremental. **Layer 3 (canonical facts) shipped 2026-08-03 as P1E**: 195,552 canonical facts
  with scope/sign/unit/basis resolved from evidence only, both dialects, six-value per-metric
  status, per-metric review queues. **Layer 4 readiness** is live as a reporting layer —
  EBITDA ready for 231 tickers (was 2), ROE for 1,321 — with no new valuation model. Serves
  P2a, P3, P4.
- **Pillar B — official corporate-action ingestion and price-adjustment engine** — `docs/official_corporate_action_ingestion_design.md`.
  **Step B1 shipped 2026-08-03** as a written, enforced, reviewable source registry that is
  `AWAITING_OWNER_APPROVAL`; B2–B6 are blocked on that approval. The immutable document store,
  typed event extraction and event ledger are built, and one bounded offline HPG slice produced
  1 qualified executed event with a fail-closed adjustment factor. Makes our own event ledger
  the adjustment authority, so no provider has to document its adjustment policy for the price
  basis to qualify. Serves P0, and through it P2b and P5.

The pillars are independent up to pillar A's enterprise-value layer, which needs a market
capitalisation and therefore waits on pillar B.

## P0 — Market-data basis and lineage — ACTIVE, now routed through pillar B
- Deliverables: provider/schema-version lineage; qualified corporate-action lineage; empirical active-path price test; volume semantics; source/version scale handling.
- **EODHD is closed as a route: `EODHD_ROUTE_STATUS: REJECTED_BY_OWNER`** (2026-08-03, `docs/DECISIONS.md`). The earlier private-shadow approval is withdrawn after two independent days of read timeouts. No further timeout test, retry, credential milestone, website check or network diagnosis is authorized; proposing one re-opens a closed decision. The disabled modules stay in the tree but are off this roadmap.
- The remaining route is **pillar B**: crawl HOSE/HNX/VSDC/issuer IR, build an immutable corporate-action event ledger, and compute `close_official_event_adjusted` ourselves alongside `close_raw`. Sequenced B1–B6 in the design doc.
- **B1 is delivered and blocked on an owner decision** (2026-08-03). `config/official_source_registry.json` declares all four source classes with hosts, document types, rates, timeouts, retries, robots/terms, retention and failure classification; `official_source_registry.admit()` refuses every source while `activation` is `declared`. Setting `activation` to `approved` is an owner decision recorded in `docs/DECISIONS.md` and may not be made by an agent. Nothing in B2–B6 may begin until then.
- **A second, independent blocker on market capitalisation surfaced in P1E**: no retained provider line carries a share count. `common_shares`/`paid_in_capital` are currency amounts, and converting them requires an assumed par value. Qualifying the price basis alone therefore does not produce a market capitalisation.
- Exit gates: `OHLCV_PROVIDER_VERSION_RETAINED = YES`; `QUALIFIED_PRICE_TEST_EVENTS >= 8`; `PRICE_BASIS_ACTIVE_PATH = DETERMINED_DOCUMENTED | DETERMINED_EMPIRICALLY`; `VOLUME_BASIS_ACTIVE_PATH = DETERMINED`; `NO_MARKET_CONSUMER_USES_UNQUALIFIED_BASIS = YES`.

### P0 sub-items (from the 2026-08-02 P0.1 audit)
- P0.1 (docs reconciliation): **done** 2026-08-02. STATE.md reviewed head corrected, Phase 0A-6E cross-reference table added (this file).
- P0.2 (approved evidence write boundary): **done** 2026-08-02. `evidence_promotion.py` + ADR in `docs/DECISIONS.md`; one real promotion executed (VNM cash dividend, resolves the Phase 5E blocker below). See STATE.md 2026-08-02 entries.
- P0.3 (bring `operations-review/` under version control or a hash-manifest): **done** 2026-08-02. Sizes measured before choosing an approach: `ai-core-private/operations-review/` (20KB, 4 files) tracked directly (ai-core-private commit `893541d`). `stock-core-private/operations-review/` (525MB, 216 files, includes a 203MB shadow `vn_stock.db` snapshot and large PDFs) and the top-level `operations-review/` (820MB, 823 files, no git repo of its own) were **not** bulk-committed -- that would permanently bloat git history with binaries. Instead: `tools/hash_manifest.py` (tested, 5 tests) generates a deterministic, git-tracked SHA-256 manifest per file; `docs/operations_review_hash_manifest.json` and `docs/top_level_operations_review_hash_manifest.json` are the committed manifests (56KB and 205KB). `--verify` mode re-checks a tree against its manifest and reports `missing_on_disk`/`hash_mismatch`/`present_on_disk_not_in_manifest`. The underlying large files remain local and untracked, same as before; what changed is that their integrity is now auditable. Re-run the generator whenever these trees change materially to refresh the manifest.

## P1 — Trusted current-session readiness — PARTIAL
- **Correction 2026-08-03**: the previous entry read "Completed: exact-session manifest structure, hash binding, Consumer validation". Hash binding and Consumer validation existed, but they did not establish exact-session association. Proof schema `1.0.0` checked only the bundle's own hash against its manifest, so a self-consistent stale pair, a manifest paired with a different bundle body, an artifact rewritten after manifest generation, an undeclared trusted artifact, or output from an older Producer all passed. The proof also covered only HPG/VNM, so every production export carried `trusted_subset: null` and was unverifiable by construction.
- Completed 2026-08-03: proof schema `1.1.0` + `producer_contract_version` pinned on both sides; the proof now covers every exported ticker with explicit `unproven_tickers` accounting; `required_artifacts` hash-binds the whole session artifact set; the Consumer verifies cross-artifact session/generated-at agreement, per-ticker session identity, every declared artifact hash, and the trusted-artifact namespace, with 31 named rejection reasons. Integrity and market-basis are now separate axes (`integrity_state` / `basis_state`) so an unverified price basis no longer suppresses honest non-market readiness. See `docs/exact_session_bundle_contract.md`.
- Completed: forward-retained daily/technical source timestamps for HPG/VNM.
- Remaining: direct share-transition coverage through the trusted session, and price/volume-qualified same-session current fields.
- Exit gate: `HPG_VNM_CURRENT_SUBSET_FULLY_QUALIFIED = YES`.

## P1B — Generated statement-taxonomy sidecar — DONE 2026-08-03
- `statement_taxonomy_sidecar.py` + `tools/build_statement_taxonomy_sidecar.py` produce a deterministic, provenance-carrying, session-bound sidecar over all 1,381 retained statement payloads (1,380 classified; BIO omitted with an explicit reason). It is `generated_evidence`, strictly below `config/ticker_entity_profiles.csv`, which was **not** modified. `CANONICAL_PROFILE_BACKFILL_AUTHORIZED` remains `NO`.
- The taxonomy now reaches the Altman applicability gate through the real bundle path (`evaluate_altman_z_score(..., statement_taxonomy=...)`), where it can only withhold applicability, never grant it. Before this it was computed by a shadow tool and discarded.
- See `docs/statement_taxonomy_sidecar_contract.md`.

## P1C — One-command operating workflow — DONE 2026-08-03
- `tools/operate_stocklookup.py` is the single supported operator entry point: preflight, single-instance lock, database quick-check, rollback point, offline input preparation, sidecar build, bundle export, artifact-hash verification, Consumer exact-session validation and context smoke, optional publish, post-publish smoke, deterministic operating report, rollback on any gate failure.
- It never fetches prices, macro series or news, and never writes to an authoritative store except the analyzer's own session-keyed `watchlist_history` table, which is only reachable behind `--prepare-inputs` and only after a verified, restorable copy of `vn_stock.db` is taken.
- Command and flags: `operations-review/local_runbook.md`.

### P1 sub-items (from the 2026-08-02 P0.1 audit)
- P1.1 (qualify HPG FY2024 current_liabilities / retained_earnings / profit_before_tax): **done** 2026-08-02. **Correction to an earlier entry in this same file**: it previously read "blocked -- needs a new bounded VCI/KBS sync", reasoning that `financial-observations/observations.jsonl` holds no raw observation for those `raw_item_id` values. The observation-store fact was right; the conclusion drawn from it was wrong. The "standalone PDF-cited fact" pattern already existed in production for exactly this case (`share_basis_citations.jsonl`, `ebitda_component_citations.jsonl` -- neither has an `observation_id` to cross-check against either), and `ebitda_component_citations.jsonl` already carried HPG's *and* VNM's `profit_before_tax` and `interest_expense`, so EBIT was already derivable. No external data acquisition was needed. Only two facts were genuinely absent; both were promoted from the already-retained PDF. See `docs/altman_z_prime_qualification.md`.
- P1.2 (activate Altman): **done** 2026-08-02 as `altman_z_prime`, for **both** core tickers and wired into the bundle. HPG FY2024 **Z' = 1.5006 (grey)**; VNM FY2024 **Z' = 2.8976 (grey, flagged `near_threshold`** -- 0.0024 below the 2.90 safe boundary, so the label is explicitly marked as not robust to small input revisions). Both computed end-to-end from the evidence store. Attached as `tickers[ticker].financial_distress_evidence` behind the **existing** `--include-fundamental-quality-evidence` flag -- no new CLI surface, default bundle output unchanged. SSI/EVF return `not_applicable` on entity_type; VCB returns `insufficient_evidence` naming `entity_type` (its entry carries `null`, and defaulting that to "corporate" would fail open on a bank). 17 tests. See `docs/altman_z_prime_qualification.md`.
- P1.3 (VNM cash-dividend promotion): **done** 2026-08-02, same work as P0.2.
- P1.4 (structurally enforce the price/volume-basis fail-closed gate, not just advisory warnings): **re-scoped and done 2026-08-02** after live investigation replaced the original plan. The originally-proposed `price_display`/`price_analytic` namespace split was not pursued: tracing the actual live default pipeline (not just the schema docs) showed `export_ai_bundle.py`'s ~30 `price_basis` call sites are almost entirely display/technical fields, which the project's own spec explicitly says must stay visible -- not a gap. Backtest/adjusted-return computation (`vnm_shadow_backtest.py`, `point_in_time_adjusted_prices.py`, `vnm_execution_contract.py`) was already fail-closed by design (per-row basis checks, qualified-evidence anchors, hardcoded `backtest_outputs: []`) and not wired into the default bundle.
  - **Found instead, live in production**: `risk_liquidity.py::evaluate_market_risk()` hardcoded `is_actionable=True` on `point_in_time_beta`/`point_in_time_correlation` for VNM whenever the underlying calculation produced a value, **completely ignoring `current_actionable`** (the project's own price/volume-basis gate) -- unlike every sibling metric in the same function (`realized_volatility` etc.), which correctly gates on it. Verified live against production `dashboard-runtime`: VNM was exposing `beta=0.0705`, `correlation=0.0610` with `is_actionable: true` in the default bundle, despite `price_basis` being globally `unknown/unverified`. This is a real instance of exactly the risk the original Blocker 1 ask was about (an adjusted-return-derived metric marked actionable while basis is unqualified), not a hypothetical one.
  - **Fixed**: both `is_actionable` assignments now read `bool(d.get("current_actionable"))` instead of a hardcoded `True`, with an explanatory warning attached when downgraded. The numeric `value` stays computed and visible (deterministic, lineage-tracked, same as `realized_volatility`'s pattern) -- only the actionability claim changed. Re-verified live: `is_actionable` is now `False` for VNM at the current (unqualified) basis state. Added a regression test (`tests/test_risk_liquidity.py::test_vnm_point_in_time_beta_correlation_is_actionable_follows_current_actionable_not_hardcoded_true`) that fails if this regresses. Full `tests/test_export_ai_bundle.py` re-run afterward: same 2 pre-existing failures as the untouched baseline (`test_all_consumers_use_same_canonical_rs_rating`, `test_hpg_material_share_mismatch_is_promoted_to_root_flags`), neither related to this change.
- P1.5 (ticker capability / trusted-ticker matrix): **done** 2026-08-02. `ticker_capability.py`, pure and tested (8 tests), not yet wired into `export_ai_bundle.py`'s opt-in attach chain. See STATE.md for the real matrix computed against production evidence.
- P1.6 (share-transition coverage through 2026-07-30): **not started**, requires new issuer/exchange evidence acquisition -- out of scope without an explicit bounded-acquisition decision.

## P1D — Market-wide raw financial observation store — DONE 2026-08-03
- Pillar A layers 1 and 2. `raw_financial_observations.py` (pure extraction, **no allowlist**), `raw_financial_store.py` (incremental gzip-JSONL shards keyed on payload hashes *and* extraction schema version), `financial_entity_applicability.py` (archetype + per-metric applicability), `market_wide_financial_coverage.py`, `tools/ingest_market_wide_financials.py`, `config/canonical_metric_candidates.csv`. 48 tests.
- Offline: reads only `data_bctc/*.parquet`, `screen_snapshot.csv`, `statement_taxonomy_sidecar.json` and two tracked config files; no network, no `vn_stock.db`, and it writes nothing the bundle reads. It is not part of the release path.
- Measured: 4,195 payloads → **1,546,197 raw observations over 1,493 tickers**; 1,308 of the 1,439 active-universe tickers have a shard; 1,198 have all three statement families; 1,493/1,493 shards byte-reproducible under `--check`; a rerun over unchanged inputs rebuilds 0.
- EBITDA / EV-EBITDA `not_applicable` went from **7** manually-profiled tickers to **82**, closing the under-classification the 2026-08-03 audit reported. Income-statement evidence additionally resolves 12 of the 13 `financial_specialized_ambiguous` tickers to `insurance`.
- Exit gate: `MARKET_WIDE_RAW_FINANCIAL_RETENTION = YES`.

## P1E — Canonical financial facts (pillar A layer 3) — NEXT
- Raw identity → canonical metric with statement scope, currency, unit scale, sign convention and cumulative-vs-discrete basis resolved; per-metric status in `qualified | provider_reported | partial | conflicted | unavailable | not_applicable`; exceptions to a review queue rather than per-ticker analysis.
- Two findings from P1D size this work and correct two entries in `docs/STATE.md`'s blocker list: the raw `depreciation_amortization` identity is present for **1,123** tickers (STATE.md records EBITDA as computable for 2), and the raw `retained_earnings` identity for **1,148** (STATE.md records 51 available / 1,097 missing). Both gaps are single-dialect mapping, not data acquisition — the retained cash-flow vocabulary splits into two mutually exclusive provider dialects that partition the universe exactly (905 + 338 = 1,243).
- Exit gate: `CANONICAL_FINANCIAL_FACTS_MARKET_WIDE = YES`.

## P2 — Point-in-time valuation alignment — SPLIT (see below)
- **Correction 2026-08-02**: this gate was recorded as flatly BLOCKED with "no P/E, P/B, EV, EV/EBIT may be produced", but production HPG has been publishing `pe` 10.55, `pb` 1.11, `ps` 0.91, `ev_sales` 1.46 and `ev_ebitda` 8.86 for some time -- deliberately, correctly, and under their own design docs (`historical_relative_valuation_snapshot.md`, `hpg_fy2024_ebitda_qualification.md`). The gate text, not the code, was wrong: it conflated two different things.
- **P2a -- historical point-in-time valuation: OPEN and qualified.** A multiple built from a *cited* historical close (HPG: 2024-12-31, `adjustment_status: raw_as_quoted_no_adjustment_applied`, with a recorded reason why raw is the correct basis at that date) aligned to the same period's qualified financials is legitimate evidence-backed analysis. It does not depend on the P0 price-basis blocker, because it never touches the current OHLCV series.
- **P2b -- current-market valuation: still BLOCKED.** Market cap from a *current* price, current shares, target prices, and cheap/expensive conclusions all remain unavailable until P0/P1 gates pass.
- Fixed 2026-08-02: available multiples were shipping with `warnings: []` and no temporal marker while the envelope's own `reference_at` was the current build time -- an FY2024 P/E of 10.55 was indistinguishable from a claim that HPG *currently* trades at 10.55x. Every available multiple now carries `historical_only: true`, `market_dependent: false`, `as_of_semantics`, and a warning naming its actual valuation date.
- Exit gate (P2b only): `VALUATION_ENABLED_WITH_QUALIFIED_TEMPORAL_INPUTS = YES`.

## P3 — Evidence-qualified investment analysis — HISTORICAL-ONLY COMPLETE
- FY2024 historical HPG/VNM work is complete; future catalysts, risks, and scenarios cannot enable market-dependent conclusions before P0/P1/P2.
- Exit gate: `MARKET_DEPENDENT_ANALYSIS_REQUIRES_P0_P1_P2 = YES`.

## P4 — Market Scan and ranking — DEFERRED
- No universal score, ranking, or recommendation before valuation and current-market gates qualify.
- Exit gate: `RANKING_INPUTS_QUALIFIED = YES`.

## P5 — Portfolio and platform expansion — DEFERRED
- Portfolio fit/sizing, backtesting, RAG, Dashboard v2, and infrastructure scaling are last priority.
- Exit gate: `PORTFOLIO_AND_PLATFORM_PREREQUISITES_QUALIFIED = YES`.

## Cross-reference: P0–P5 governance track vs. Phase 0A–6E working-session track

The dated `phase_*` milestones recorded under `operations-review/` (both `stock-core-private/operations-review/` and the top-level `operations-review/`) are working-session checkpoints, not a separate roadmap. Every one maps onto exactly one P0–P5 gate below; none stands outside this roadmap. Added 2026-08-02 (P0.1 audit) so no phase is orphaned from the governance gates it was actually working toward.

| Phase | Date (UTC) | What it did | Maps to | Producer/Consumer evidence |
|---|---|---|---|---|
| 0A — Data Truth & Artifact Coherence Audit | 2026-07-31 | End-to-end audit of export path vs. runtime artifacts, cross-cutting prerequisite for every later gate | Prerequisite to P0–P3 (audit, not a gate itself) | `operations-review/phase_0a_data_truth_audit_20260731T143000Z.md` |
| 0B — AI Semantic Hardening Closeout | 2026-07-31 | Producer export-path semantic safety contracts | Prerequisite to P0–P3 | `operations-review/phase_0b_closeout_20260731.md` |
| 1B — VCI OHLCV Source Semantics Qualification | 2026-08-01 | Qualified (blocked) VCI active price-path semantics | **P0** — market-data basis and lineage | `operations-review/phase_1b_vci_ohlcv_semantics_20260801T080900Z.md` |
| 1C — KBS OHLCV Source Semantics Qualification | 2026-08-01 | Qualified (blocked) KBS provider OHLCV semantics | **P0** — market-data basis and lineage | `operations-review/phase_1c_kbs_ohlcv_semantics_20260801T081200Z.md` |
| 3D — Consumer Contract-Shape Closure | 2026-08-01 | Fixed `opportunity_ranking`/`news_window_semantics` pass-through gaps, Consumer commit `1e1c646` | **P3** — evidence-qualified investment analysis (historical-only) | `ai-core-private` commit `1e1c646` |
| 4A — Analysis Engine & Market Scan V2 Design | 2026-08-01 | Design-only contract for five analysis lanes; no source/runtime change | **P4** — market scan and ranking (design scaffolding only; P4 itself stays DEFERRED) | `operations-review/phase_4a_analysis_engine_market_scan_v2_design_20260801T072613Z.md` |
| 4B — Analysis Lane Eligibility Gates | 2026-08-01 | `analysis_lane_eligibility.py`, Producer commit `bfce838`; `is_actionable` hardcoded `False` on every lane result | **P4** scaffolding, opt-in only, non-actionable by construction | Producer commit `bfce838` |
| 4C — Lane Shadow Validation | 2026-08-01 | Shadow pilot of lane eligibility against real bundle data | **P4** scaffolding | `operations-review/phase_4c_lane_shadow_20260801T081307Z/` |
| 4D — Consumer Lane Eligibility Pass-Through | 2026-08-01 | `build_ticker_context.py` wiring, Consumer commit `a6c4e33` | **P4** scaffolding | Consumer commit `a6c4e33` |
| 4E — Frozen Pilot | 2026-08-01 | Frozen end-to-end pilot of the lane layer | **P4** scaffolding | `operations-review/phase_4e_frozen_pilot_20260801T084520Z/` |
| 4F — Deterministic Shadow | 2026-08-01 | Determinism check on lane outputs | **P4** scaffolding | `operations-review/phase_4f_deterministic_shadow_20260801T090749Z/` |
| 4 — Closeout | 2026-08-01 | Closes 4A–4F as inert, opt-in, non-actionable scaffolding; does not activate P4 | **P4** stays DEFERRED | `operations-review/phase_4_closeout_20260801T091701Z.md` |
| 5A — Opt-In Lane Smoke | 2026-08-01 | Smoke test of opt-in lane attachment path | **P4** scaffolding / **P3** extension | `operations-review/phase_5a_opt_in_lane_smoke_20260801T093210Z/` |
| 5B — HPG Verified Period | 2026-08-01 | Verified-period resolution for HPG, commit `e8a351c`/`44d81cf` | **P3** extension | `stock-core-private` commits `e8a351c`, `44d81cf` |
| 5C — Generic Verified Period | 2026-08-01 | Generalized verified-period resolution across tickers | **P3** extension | `operations-review/phase_5c_generic_verified_period_20260801T101631Z/` |
| 5D — Distribution Evidence | 2026-08-01 | `distribution_evidence` contract, commit `1ca1307`; HPG/VNM cash+non-cash lanes, all `is_actionable=False` | **P3** extension (feeds future `income_defensive` lane under P4) | `operations-review/phase_5d_distribution_evidence_20260801T104910Z/validation_summary.json` |
| 5E — VNM Cash-Distribution Evidence Promotion | 2026-08-01 blocked; **resolved 2026-08-02 (P0.2)** | Originally blocked: evidence-qualified but no approved write boundary for `*_citations.jsonl`. Resolved by `evidence_promotion.py` (P0.2): VSD notice 177392 promoted into `manifest.json`/`cash_dividend_citations.jsonl`; `load_verified_cash_dividends()` now returns 1 event, 0 rejected; 4 pinned artifacts confirmed unchanged | **P3** extension, unblocked | `operations-review/phase_5e_vnm_cash_distribution_evidence_storage_boundary_blocker_20260801T111043Z.txt` (original blocker); `stock-core-private/evidence_promotion.py` + STATE.md 2026-08-02 P0.2 entry (resolution) |
| 6A — Qualified Fundamental Quality Model | 2026-08-01 | `fundamental_quality.py`, commit `7c44136` (Piotroski, Altman/Beneish stubs, bank variant) | **P3** extension | `stock-core-private` commit `7c44136` |
| 6B — Legacy Fundamental Quality Hardening | 2026-08-01 | Reconciled legacy quality output against Phase 6A contract, commit `477cc1c` | **P3** extension | `stock-core-private` commit `477cc1c` |
| 6C — Comparative DuPont / FY2023 Slice | 2026-08-01 | Case C: FY2023 does not qualify for HPG or VNM; no source change | **P3** extension (comparative-period sub-gate, decoupled from P0/Altman) | `operations-review/phase_6c_comparative_dupont_20260801T121408Z/phase_6c_report.md` |
| 6D — Financial Identity Expansion & Altman Readiness | 2026-08-01 | Case C: no new identity qualifies (only pre-existing `current_assets`, `total_liabilities`); Altman not attempted | **P3** extension; blocked one layer deeper than 5E — see 6E | `operations-review/phase_6d_financial_identity_altman_20260801T122147Z/phase_6d_report.md` |
| 6E — HPG Missing Financial Identity Retention | 2026-08-01 | Case B: read `current_liabilities`/`retained_earnings`/`profit_before_tax` directly off the retained FY2024 PDF; added mapping + derived-EBIT rule, commit `4351302`. Values are **not** promoted to `qualification_citations.jsonl` — mapping capability only | **P3** extension; **verified 2026-08-02 (P0.1 audit) not to be the same blocker class as 5E**: `dashboard-runtime/data/financial-observations/observations.jsonl` has zero rows with `raw_item_id` in `{current_liabilities, undistributed_earnings, profit_before_tax}` for HPG at any period 2018-2026 — no raw observation exists to attach a citation to, so `evidence_promotion.py` cannot unblock this the way it unblocked 5E. This is the data-acquisition gap Phase 6D itself named ("never retained by any upstream sync"), not a missing write boundary. Unlocking it requires either (a) a new bounded VCI/KBS sync capturing these raw items (external data acquisition, out of this milestone's scope), or (b) a defined, source-cited manual-observation path distinct from `evidence_promotion.py`'s citation-only scope | `stock-core-private` commit `4351302`; STATE.md 2026-08-02 P0.1 correction; observation-store query 2026-08-02 |

No `phase_*` artifact found under either `operations-review/` tree falls outside P0–P5; any future phase must be added to this table in the same milestone that creates it.
