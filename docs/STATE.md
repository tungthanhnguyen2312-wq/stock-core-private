# Stock Lookup state

## Universal market universe & bulk DNSE ingestion live milestone (2026-08-11)

`UNIVERSAL_MARKET_UNIVERSE_BULK_DNSE_INGESTION_V1: PARTIAL_LIVE`. The approved credential
loader found the approved credential file and authenticated without exposing a credential value.
Live, unfiltered DNSE discovery completed at 3,252 declared instruments and 3,250 distinct
instruments (two duplicate identities, zero malformed records), retaining 33 immutable raw
instrument-page observations and snapshot
`b2f0e33c3788b9f4a8fa52248e42514dab11ffad44b075df5b7d94630cbee4e7` under
`operations-review/dnse-phase1-live-20260811/data/market_raw_lake/universe/`. Raw market IDs
are retained as observed: `DVX=8`, `HCX=203`, `STO=1785`, `STX=312`, `UPX=942`. Classification
remains evidence-driven: `EQUITY=1660`, `UNKNOWN_SECURITY_GROUP=1590`.

The initial five-symbol smoke selected records without respecting the stock eligibility boundary
and received five HTTP 400 responses; those manifests/checkpoints are retained as evidence. The
selector was corrected to choose only directly observed `EQUITY` records for `type=STOCK`, never
to guess that unknown security groups are stocks. The corrected `A32, AAA, AAH, AAM, AAN` smoke
completed five raw OHLC retentions, and its same-scope restart performed zero refetches.

The bounded 30-day, 1D OHLC sweep then requested all 1,660 eligible equities. A process timeout
was resumed from its deterministic checkpoint rather than restarted: 1,527 instruments retained
successfully and 133 received isolated `http_status_400` failures, for 91.99% eligible-universe
coverage; there were no never-requested eligible symbols. The durable report is
`operations-review/dnse-phase1-live-20260811/data/market_raw_lake/coverage/DNSE__ohlc__phase1-live-ohlc-equity-20260811-resume1__0539c97f8548aafb.json`;
the associated manifest and checkpoint remain under the same runtime root. This is raw,
retrospective collection only: it promotes no canonical, PIT, feature, provider, database,
dashboard, deployment, or publication authority. Phase 2 remains owner-gated.

The command host reported a timeout while its first full-sweep process was still completing; the
subsequent resume consequently overlapped it for 330 units. All 1,862 retained OHLC raw files
(including the successful five-symbol smoke) are immutable and preserved, while coverage is based
on the 1,527 unique successful eligible symbols. A same-scope exclusive checkpoint lock now makes
any future concurrent invocation fail closed rather than refetch completed work.

## Universal market universe & bulk DNSE ingestion foundation (2026-08-11)

`UNIVERSAL_MARKET_UNIVERSE_BULK_DNSE_INGESTION_V1: PARTIAL`. Phase 1's first concrete
deliverables now exist. `dnse_instrument_universe.py` discovers the DNSE security master by
paginating `/market/instruments` with no filter, no hardcoded ticker list, and no assumed
total -- termination is driven entirely by the provider's own `total`/`page`/`pageSize`
fields, falling back to "stop on an empty page" when they are absent. `market_raw_lake.py` is a
new, generic, provider/dataset-agnostic immutable raw store: one Parquet file per fetched unit
under `data/market_raw_lake/`, a checkpoint rewritten atomically after every unit (resumable,
duplicate-avoiding), and a manifest per run. `tools/bulk_ingest_dnse_raw.py` is the first
concrete dataset adapter, bulk-ingesting OHLC (`resolution="1D"`, the only working daily-bar
token -- reused verbatim from `tools/dnse_market_data_probe.py`'s own documented finding) with
bounded exponential-backoff retry on transient failures, immediate whole-run abort on
`authentication_failed`, and per-symbol failure isolation for everything else.
`tools/discover_market_universe.py` is the paired universe-discovery CLI.

Two new supporting modules exist because reusing the established qualification-probe path
directly would have silently corrupted bulk data: `dnse_bulk_market_data.py` is a
non-truncating twin of `dnse_market_data.request_capability` (that function's
`_bound_large_lists` reduces any response array over 20 items to a 7-item sample -- correct for
a safe-to-print evidence file, wrong for raw retention, and the exact class of bug already
named once before as the "20-item evidence-redaction truncation trap"). `dnse_secrets_env.py`
is the first module in this repository allowed to read `secrets.env` itself -- every existing
DNSE tool instead assumes an external launcher already populated the process environment,
which a long-running bulk run cannot assume; it only injects the exact known credential key
names, never overrides an already-set variable, and never returns, logs, or prints a value.

Instrument classification is strictly evidence-driven: only `securityGroupId="ST"` (10 observed
examples, all common stock) maps to `EQUITY`; every other or unseen code is explicit
`UNKNOWN_SECURITY_GROUP` with the raw code retained -- never a guessed WARRANT/BOND/ETF/RIGHT/
DERIVATIVE. `marketId` (`"STO"`, `"UPX"`, ...) is carried verbatim as `exchange_raw` rather than
labelled HOSE/HNX/UPCOM, which is not yet first-party documented. 106 new focused tests cover
pagination/termination, classification including UNKNOWN, deterministic raw identity,
immutable/append-only semantics, checkpoint/restart, idempotent re-runs, partial provider
failure, retry/backoff, mid-run auth-abort, credential redaction, and coverage-report
composition; all pass, alongside the full existing Phase 0 foundation suite
(`test_market_wide_foundation.py`) and every DNSE-related suite (128 tests, 8 subtests) with
zero regressions and zero pre-existing files modified.

The one thing this milestone could not do from its execution environment: a real network sweep
against DNSE. Both new CLI tools correctly attempt the approved `secrets.env` mechanism at
`C:\Users\tungt\.stocklookup\secrets.env` and fail closed with `DNSE_CREDENTIAL_INJECTION_
REQUIRED` -- that path, and the Windows user profile it lives under, do not exist in this
sandboxed session, even though this same workspace's `operations-review/dnse-credential-auth-
probe-20260811/probe_results.json` shows a real `DNSE_AUTHENTICATION_PASS` earlier the same day
from a different execution context. No DNSE request was made, no universe was actually
discovered, and no raw OHLC observation was actually retained -- `dnse_bulk_market_data.py`'s
allowlist and signing are exercised only by mocked responses in tests. Next:
`tools/discover_market_universe.py --live` then `tools/bulk_ingest_dnse_raw.py --live
--universe-snapshot <path>` from an environment with real access to the approved credential
file, to produce the first live universe snapshot, raw OHLC retention, and coverage report.

## Market-wide ingest-first architecture pivot (2026-08-11)

`STOCK_LOOKUP_MARKET_WIDE_INGEST_FIRST_PIVOT: PASS_FOUNDATION`. The active architecture is now market universe → immutable raw lake → quality/exception queue → canonical/semantic/PIT → vectorized feature store → feature-level qualification → declarative strategies → portfolio/risk → AI research/counter-thesis → human decision. The older per-ticker qualification-first workflow is **SUPERSEDED_AS_DEFAULT_WORKFLOW**, while its passed evidence remains historical truth and the 11 historical tickers are golden/regression cases.

This source-only foundation adds `market_data_contracts.py`, `market_feature_store.py`, `config/feature_dictionary.json`, and focused tests. It does not ingest a universal universe, acquire a provider, mutate runtime data, promote source authority, publish, deploy, commit, or push. Existing raw financial retention is retained as a compatible precedent. See `docs/adr/ADR-20260811-market-wide-ingest-first-feature-store.md` and `docs/market_wide_ingest_first_architecture.md`.

## Next official financial evidence cohort (2026-08-11)

`NEXT_OFFICIAL_FINANCIAL_EVIDENCE_COHORT: PARTIAL`. Under the new owner-bounded follow-up to
the closed Cohort 3 FPT/PNJ blockers, FPT's official `fpt.com` disclosure proxy retained an
audited consolidated FY2025 filing as document
`7c7ec0a1e76045bbb655f46f807165962516f3b16833a005a57af59a0e6bce32`, SHA-256
`630f61f6ef9f07d5c593c3bf8f65bad1d56ecbb091921296ed5c4e830ea070a4`. Five source-page-
verified VND annual/consolidated identities are registered: cash, shareholders' equity, net
income, operating cash flow, and debt only as the explicit `19,169,697,497,955 +
1,903,789,988,184` borrowing/finance-lease component sum. FPT is historical-only and
non-actionable; no market, DNSE, valuation, target, probability, liquidity, sizing, release, or
Dashboard state changed.

PNJ's new official FY2025 audited consolidated filing is retained as document
`d838e40adfa470cab934840ce579d8c7690a9e4bee98a93ca020a2b8292c749b`, SHA-256
`2a0f8591ed1acacb4a14849ccf807e596020c162fe7ed6adee999acaffd8b551`, but its explicit balance-
sheet debt evidence remains short-term only. Generic non-current liabilities are not debt or a
finance lease, so PNJ remains `REQUIRED_DEBT_COMPONENT_MISSING` and non-eligible. No previously
closed issuer cohort was reopened. The next acquisition gate is a new
`OWNER_OFFICIAL_FINANCIAL_EVIDENCE_SCOPE_DECISION` tied to an exact qualifying official source.

## Research Snapshots v2 Producer completion (2026-08-11)

`RESEARCH_SNAPSHOTS_V2_PRODUCER_COMPLETION: PASS`. The generated Producer bundle now retains
`qualified_research_snapshot_v2`, a deterministic fixed-11-ticker baseline with stable identity.
Each row carries only the already-produced historical-research, raw-as-traded-price,
current-valuation, generic-liquidity, and foreign-flow-VALUE status/reason projections; it does
not carry raw/PIT OHLCV, volume fields, targets, probabilities, or inferred corporate-action
state. V2 change events continue to accept prior schema `2.0.0` baselines, so served-baseline
replay remains compatible while new snapshots are `2.1.0`.

The result is source-only: no runtime artifact was generated, no Consumer or Dashboard contract
changed, and no release, publication, authority promotion, source acquisition, or DNSE probe
occurred. Consumer/Dashboard pass-through and any publication remain separately owner-gated.

## Official financial evidence scale-out Cohort 4 (2026-08-11)

`OFFICIAL_FINANCIAL_EVIDENCE_SCALE_OUT_COHORT_4: PARTIAL`, closed to its fixed SSI/QNS scope.
The two minimum issuer documents were already retained through the approved `ssi.com.vn` and
`qns.com.vn` paths, so no external retry or discovery occurred. SSI's FY2024 audited
consolidated PDF (`3fd72890fe43b78071d641b8d89523d4aa28e340d4f1904a90667f8c1d794bf0`, SHA-256
`38e5b9ba2fc951120be813b09df05fa2d8b152b3b95443c6cd108de8abf03b74`) now has one newly
registered, source-page-verified annual consolidated VND identity: `current_liabilities =
46,599,438,522,989` at 2024-12-31. Its manifest identity is
`7a0e4853f1a837ecea71e764789181efdb00c1c916609a790c9688ebe74a8286`; citation identity is
`af35883a2028970cc100d168dd9965be38ff8a1d1d98d510faa2d72cfae695ad`.

SSI remains outside the corporate five-metric research contract: its securities-sector semantics
prohibit treating its funding lines as corporate `total_interest_bearing_debt` or inferring a
corporate research/valuation input set. This is a correct `not_applicable`, not a missing-value
substitute. It is independent of, and does not alter, the deferred SSI/VSDC corporate-action
notice. QNS's retained FY2024 audited consolidated PDF (SHA-256
`faaa54465d1d6a3ca98bebf2a47a45096e21ee6ac3d1cfe3c95db3b1c0bae3e3`) already had a qualified
manifest identity and all five annual consolidated VND facts, including the explicit-zero
long-term borrowing maturity-note component. Re-validation produced five qualified facts and an
available historical-only, non-actionable corporate research projection; append-only replay
added nothing.

No third ticker, provider, source authority, FPT/PNJ retry, runtime mutation, Consumer/Dashboard
change, or corporate-action/ex-date work occurred. Any further scale-out needs a separately
owner-scoped official-evidence decision.

## Official financial evidence scale-out Cohort 3 (2026-08-11)

`OFFICIAL_FINANCIAL_EVIDENCE_SCALE_OUT_COHORT_3: PARTIAL`, closed to its owner-fixed scope of
exactly FPT, PNJ, and PVD. PVD's already-retained FY2024 issuer-IR audited consolidated PDF
(`e03146183ffecb8cc94c5302edca1d8b5010e2121a00d18ae74e284cf0c306cb`, SHA-256
`ba70100acf9391a85992e67ebc1a3d68da33e50402a17e860f579e320f5f2d14`) hash-verifies against
the qualified manifest and its five existing annual consolidated USD citations. It remains the
existing historical-only, non-actionable research input; no duplicate registration was made.

PNJ's retained FY2024 issuer-IR PDF hash-verifies as
`71eb69f97fab83a36ed3dca032193cfc24754f416d24d4ad136f198ab2a73099`, but its qualified
review supplies only the labelled short-term borrowing component. The required labelled
long-term borrowing or finance-lease component is absent, so PNJ remains
`REQUIRED_DEBT_COMPONENT_MISSING` and no total-debt citation was inferred. FPT's existing exact
audited-statement locator and the two exact FY2024 annual-report locators supplied by its
official IR route all returned HTTP 404; no FPT bytes, hash, citation, or manifest record exist.
No URL variation, crawl, provider fallback, runtime mutation, or ticker expansion occurred.

This is a completed bounded pass, not a standing acquisition authorization. Further work needs a
new owner-scoped official-evidence decision: an FPT locator that yields retained audited
consolidated bytes and/or an official PNJ source that explicitly supplies the required debt
component.

## SSI/VSDC B2 evidence disposition (2026-08-11)

`PILLAR_B_B2_SSI_VSDC_EX_DATE_NOTICE_ACQUISITION` is
`BLOCKED/DEFERRED_PENDING_NEW_OFFICIAL_EVIDENCE`, not repeatable acquisition work. The exact
official VSDC notice `https://vsd.vn/en/ad/198728` is retained once in the approved
Producer-local acquisition manifest under immutable SHA-256
`bd7d4054613ae6f9c5ee1ddc6b787bf706ac6a18f551aff3c9683a85bcc06dad`. It directly identifies
SSI / `VN000000SSI1`, the 2025 cash dividend at 10% / VND 1,000 per share, record date
2026-08-18, the 5:1 prospective bonus issuance, and 500,219,550 planned shares.

The notice does not state an official ex-date and does not evidence an executed/actual share
change. Record date, planned shares, payment date, and a calculated trading date are not
substitutes. The typed observation therefore remains `record_date_confirmed`, with
`ex_date_absent`; it is not promoted into canonical evidence or an adjustment-factor ledger.
No SSI/VSDC request is actionable unless new official evidence independently supplies the
missing fields.

`OFFICIAL_FINANCIAL_EVIDENCE_SCALE_OUT_COHORT_3` is closed as recorded above. No subsequent
Producer-only milestone is authorized by the current roadmap; the next gate is the new
owner-scoped official-evidence decision stated above.

## Market-source authority reconciliation (2026-08-11)

`MARKET_SOURCE_AUTHORITY_RECONCILIATION: PASS`. Commit `f216cfb` incorrectly promoted the
documented FiinGroup commercial candidate to `PREFERRED_SOURCE_ID` and made
`OWNER_SOURCE_ACQUISITION_DECISION` canonical. That designation is superseded: FiinGroup has no
owner authorization, configuration, legitimate access, agreement, or rights, and is not an
approved acquisition/integration path. No paid provider may become canonical without a new
explicit owner decision.

DNSE foreign-flow VALUE is production-enabled for HPG/VNM/QNS under its retained,
provider-scoped contract. DNSE OHLC is `ADJUSTED_CONFIRMED` but raw-as-traded and point-in-time
unsafe; DNSE market-volume basis remains unqualified. EODHD remains `REJECTED_BY_OWNER`. Generic
price, volume, valuation, liquidity, sizing, execution, and backtest gates remain blocked. The
former next Pillar-B milestone is now deferred as recorded above: exact notice 198728 was
retained but lacks the required official ex-date and execution evidence.

## HPG evidence manifest restoration and Pillar-A performance closeout (2026-08-11)

`HPG_EVIDENCE_MANIFEST_AND_SHARED_LOADER_REPAIR: PASS`. The existing qualified HPG FY2024
audited-consolidated identity `a7c3711d...` is now registered exactly once through the existing
append-only `evidence_promotion.py` manifest authority. The record preserves its immutable PDF
hash `304a93a...`, source provenance, and explicit Producer-relative retained-document path.
The shared archive-document resolver was already repaired by `1302ef0`; this milestone verified
that path contract rather than adding a second loader path. Missing, malformed, and hash-mismatched
manifest evidence remains fail-closed.

HPG's opening FY2024 share identity and its three EBITDA components now resolve as qualified, but
current-state relative valuation remains `NOT_QUALIFIED`: evidence coverage ends on 2026-07-30,
before the qualified DNSE price session 2026-08-07. No current-share validity is inferred across
that gap and no valuation rule, runtime database, or published artifact changed.

The completed Pillar-A request-scoped performance side-track is also closed: post-focus timing
observability (`c6f54c6`) identified repeated verified-identity scans inside global coverage; the
per-export official-fact index (`1272622`) reduced `pillar_a_coverage_conflict` from 404.777s to
20.307s for HPG and 469.941s to 18.478s for VNM with byte-identical analytical bundles.

## HPG current-state relative valuation — built, wired, correctly not-yet-live (2026-08-11)

New `current_state_relative_valuation.py`: current market cap/P-E/P-B/P-S/EV/EV-Sales/EV-EBITDA
from the qualified DNSE current-state price (`dnse_current_state_price_analytics.py`, reused
verbatim) times official-evidence current common shares outstanding
(`share_transition_bridge.resolve_share_transition`, wired to production for the first time —
previously it had no caller anywhere in this repository), against already-qualified historical
canonical financial denominators. Every result explicitly carries
`as_of_semantics = "current_market_price_on_qualified_historical_fundamentals"` — never "TTM",
"forward", or "current earnings" — since it deliberately mixes a current price with an older
qualified period; uses one current share count for every metric (not the historical
period-end/weighted-average split, which does not apply to a still-open current period). Opt-in
via `export_ai_bundle.py --include-current-state-relative-valuation` (disabled by default),
attached as `tickers[ticker].current_state_relative_valuation` — distinct from the pre-existing
`relative_valuation` (historical point-in-time, untouched) and from
`ticker_capability_matrix.market_actionable.current_valuation` (an unrelated, market-wide generic
capability-status slot). Consumer pass-through (`apply_bundle_current_state_relative_valuation_contract`)
and a minimal `prompts/ai_analysis_templates.md` extension (one new paragraph, three new
prohibited-claims items) both added.

**Real result today: `NOT_QUALIFIED` for every method, for two independently-sufficient, evidenced
reasons — not a code defect in this new module.** (1) HPG's DNSE current price qualifies cleanly
(session 2026-08-07, 22,000 VND, `ADJUSTED_CONFIRMED`), but official current-share coverage
(`resolve_share_transition`, fed only by `share_basis_citations.jsonl` + the one real
`current_shares_outstanding_after_event` citation) reaches only 2026-07-30 — 8 days short of the
DNSE session, via the strictest, non-inferring reading of "coverage" this milestone was told to
use (deliberately *not* `market_wide_current_shares_resolver.py`'s more permissive
`qualified_official` lane, which extrapolates a stale vendor corroboration forward indefinitely —
exactly the "infer continued validity beyond proven coverage" pattern this project's rules
forbid). (2) Independently: `evidence_id a7c3711d1b02c131a87fef4a0f5bd4d5fbd780bbb0c07665111a358a2ddcd2a8`
(`hpg-consolidated-fy2024-audited.pdf`, backing HPG's period-end/weighted-average share citations
*and* its EBITDA-component citations) is absent from `data/official-evidence/manifest.json`'s 11
records entirely — `semantic_evidence_bridge.load_verified_share_basis`/`load_verified_ebitda_components`
both reject every HPG/VNM/VCB row with `evidence_missing_or_hash_mismatch`, confirmed by running
both loaders directly against the real runtime root. A related, third gap: `official_evidence.load_cited_financial_records`
reconstructs a flat `data/official-evidence/<filename>` path rather than using each manifest
record's own `archive_document_path`, so HPG's newer `financial_identity_citations.jsonl` facts
(shareholders_equity, net_income, revenue, cash, debt — all hash-verifiable, evidence_id
`e52eeb95...` *is* correctly manifest-registered) never reach `canonical["records"]` either; the
`_financial_input` dedup silently falls back to lower-rigor `financial_snapshot`/
`financial_observation_store` rows (`quality_state="unknown"`), which this module's reused
`relative_valuation._qualified()` correctly refuses. None of these three gaps are fixed here
(out of this milestone's scope — they are pre-existing, cross-cutting evidence-loader issues,
not part of this new module, and fixing them touches shared infrastructure other qualified-share/
financial consumers already depend on). The mechanism itself is proven correct and complete via
34 synthetic-input unit tests (real formulas, real numbers, once coverage/manifest gaps are
hypothetically closed) plus a real-evidence integration test that locks in today's exact blocker.

Historical comparability (`historical_comparison`) is separately `incomparable` today for its own
reason: the only existing historical HPG valuation checkpoint (`historical_relative_valuation_snapshot.md`,
`pe=10.55` etc.) has been `BLOCKED` since 2026-08-04 (see below) — confirmed live in production
(`relative_valuation.methods.*.state == "unavailable"` for HPG today).

Full shadow E2E run against the real `dashboard-runtime` (no network, no provider refresh, no DB
mutation, no publish): isolated Producer bundle build → Consumer ticker context → hand-authored
multi-angle synthesis response → `multi_angle_synthesis_boundary.accept_multi_angle_synthesis` —
**accepted**, zero rejection reasons, byte-identical across two independent end-to-end rebuilds.
`vn_stock.db` untouched by this milestone (its mtime-instability-on-read is a separately
pre-existing, already-test-documented environmental property, confirmed via `git stash` baseline
comparison, not caused by this work).

## Production-universe qualified research snapshots v2 (2026-08-09)

Legacy v1 HPG/VNM/VCB snapshots remain untouched. A deterministic v2 semantic snapshot now binds
the fixed 11-ticker production universe, explicit per-ticker research state, capability/brief
hashes, and source identity. It is source-only pending served-baseline integration and release.

## Qualified research change events (2026-08-09)

Producer now has a deterministic, presentation-safe adapter over canonical qualified-research
deltas. It emits only semantic capability, analytic, and conclusion transitions with hash-derived
event IDs and provenance references; identical or formatting-only briefs yield `NO_CHANGE`.
Consumer, Dashboard, runtime generation, and release remain pending integration.

## QNS targeted OCR materialization (2026-08-09)

The retained QNS FY2024 audited consolidated PDF was page-preserving OCR-materialized only on
pages 7--10 (balance sheet, income statement, cash-flow statement). The OCR sidecar is bound to
SHA-256 `faaa54465d1d6a3ca98bebf2a47a45096e21ee6ac3d1cfe3c95db3b1c0bae3e3`; QNS facts remain
unpromoted pending source-page citation construction, so research and live publication stay blocked.

## QNS audited consolidated filing recovery (2026-08-09)

One bounded official `qns.com.vn` financial-reports investigation retained the exact 41-page
FY2024 audited consolidated filing separately from the insufficient annual-report package:
`faaa54465d1d6a3ca98bebf2a47a45096e21ee6ac3d1cfe3c95db3b1c0bae3e3`. Direct text is degraded,
so five-metric materialization is deferred rather than guessed; no provider, DB, runtime, or
publication change occurred.

## POW entity authority and QNS audited filing recovery (2026-08-09)

`POW_ENTITY_AUTHORITY_AND_QNS_AUDITED_FILING_RECOVERY: PARTIAL`. The existing manual-profile
contract is the minimum and sole naming authority for `issuer_entity_type`. PV Power's official
company page identifies PetroVietnam Power Corporation as the POW listed share and a joint-stock
corporation; its official FY2024 annual report identifies ordinary power-generation and related
operating businesses. This supports the minimal `POW,corporate` manual profile without a new
archetype or changed financial fact. POW's five existing qualified FY2024 consolidated VND facts
now project to research eligibility; historical trend remains `insufficient_history` and generic
market gates remain blocked. QNS recovery is pending its one bounded official-source investigation.

## QNS/POW official financial materialization and research activation (2026-08-09)

`QNS_POW_OFFICIAL_FINANCIAL_MATERIALIZATION_AND_RESEARCH_ACTIVATION: PARTIAL`. QNS was
inspected by native text only: its retained 75-page annual-report package ends at the financial
statement cover and contains none of the audited consolidated balance-sheet, income-statement,
or cash-flow pages. It is therefore `AUDITED_CONSOLIDATED_STATEMENT_SECTION_MISSING`; no OCR,
metric, or provider fallback was used. POW's retained audited consolidated filing was materialized
only on source pages 9--12 using the existing page-preserving Tesseract contract. Five exact VND
FY2024 consolidated citations (cash, equity, net income, operating cash flow, and the explicit
short- plus long-term borrowing/finance-lease sum) qualify under the existing policy. POW remains
research-blocked at `entity_type_unknown`: it has no existing authoritative corporate profile, and
none was assigned manually. The production eligible count therefore remains **5**
(`HPG,VNM,PAN,PVD,NVL`); no historical analytics, capability-matrix promotion, runtime release,
DB mutation, provider call, or market-gate change occurred.

## Bounded issuer filing locator qualification backlog (2026-08-09)

`BOUNDED_ISSUER_FILING_LOCATOR_QUALIFICATION_BACKLOG: PARTIAL`. One bounded official-source
investigation was performed for exactly FPT, POW, and QNS. FPT's official IR reports page linked
the exact FY2024 audited consolidated filing, but the current issuer URL
`https://fpt.com/-/media/project/fpt-corporation/fpt/ir/information-disclosures/year-report/2025/march/20250314---fpt---audited-consolidated-financial-statements-for-2024.pdf`
returned 404; it is preserved as `ISSUER_FILING_LOCATOR_RETURNED_404` and was not varied. QNS's
issuer-published FY2024 annual report, containing the audited consolidated statements, was
retained as SHA-256 `a43f5b274524e3c7f754e037ddf143793f8c26a41b826b74b53b56c380f3aa4a`
(`ready_for_direct_citations`). PV Power's official FY2024 financial-statements page directly
linked its audited consolidated filing; `pvpower.vn` was explicitly admitted and the artifact was
retained as SHA-256 `e2f6e74e1702d406473a427c0036a543c5d49c57e3b9a03469fa97d597a9e1a3`
(`needs_ocr`). No OCR, financial-metric materialization, provider call, DB mutation, runtime
generation/publication, or other ticker investigation occurred.

## Targeted multi-period official financial evidence pilot (2026-08-09)

`TARGETED_MULTI_PERIOD_OFFICIAL_FINANCIAL_EVIDENCE_PILOT: PASS`. The fixed, two-ticker
pilot is HPG (existing issuer-evidence control) and PVD (the existing scan/OCR issuer path).
Each has an issuer-IR retained FY2022 and FY2023 audited consolidated filing; four immutable
records and exactly twenty page-cited annual identities (operating cash flow, net income,
cash and equivalents, total interest-bearing debt, and shareholders' equity) were appended
through `evidence_promotion.py`. HPG's text-bearing pages and PVD's source-page-verified OCR
sidecars bind every citation to its original PDF hash, reporting period, currency, and
consolidated scope. PVD remains USD; no FX conversion or absolute cross-currency comparison
was created.

The existing historical analytics and scenario contract now report an available HPG/PVD
comparison and ticker-local `trend_status=available`; both carry compatible annual periods
through FY2024 where independently retained evidence exists. The output is historical-only,
non-actionable, descriptive, and explicitly prohibits ranking, valuation, recommendation,
liquidity, or market claims. The supported operator regenerated and Consumer-validated the
two-ticker bundle (reference session 2026-08-07):
`analysis_bundle.json` `8a76fc00b5a590eaeb50266f8c62b4f9b4a0ad723cce1916ad9d3330145cb8f5`,
`bundle_manifest.json` `3eb1ff7cb08820f4b66f265e6066de93c34ef9ce321fb77eeb1ed3ba576eeb49`.
The sanctioned trusted-AI publisher then released those four allowlisted artifacts at serving
commit `bf00185d78cb79e875b8bba2e17ce0111c966882`; its exact-session, staged-hash, destination,
and remote-push checks passed, with zero unrelated serving-path drift.
An attempted canonical-financial bundle attachment stopped before generation because it would
require a prohibited metadata refresh; the operator rolled back and the delivered run omits
that unrelated lane. No provider call, market-data refresh, database mutation, or generic
market capability change occurred.

Last verified: **2026-08-03**, by an end-to-end production run of the supported operating
command against `dashboard-runtime` (reference session `2026-07-30`).

## Official financial evidence scale-out Cohort 2 (2026-08-09)

`OFFICIAL_FINANCIAL_EVIDENCE_SCALE_OUT_COHORT_2: PARTIAL`. PNJ's retained Note 19 confirms
only `Short-term borrowings`; no labelled long-term borrowing or finance-lease component exists,
so `REQUIRED_DEBT_COMPONENT_MISSING` remains a correctly preserved four-of-five blocker. Of the
bounded new pool, QNS's exact issuer-published FY2024 report URL returned 404 and was not varied;
POW has no exact audited-statement locator and remains `ISSUER_FILING_LOCATOR_REQUIRED`.
Novaland's issuer IR page directly linked one audited FY2024 consolidated PDF, retained as
SHA-256 `078fe614549d6f139b3cd3e9bdcd9f99a533b03c067c5018a989166cb2eab3d3`. Its five source-page
verified VND facts are complete, including debt only as `36,978,198,251,788 +
24,587,656,403,178 = 61,565,854,654,966`; NVL is therefore historical-only and non-actionable.
No provider, database, generated bundle, FPT route, or market gate changed. Next independent
Pillar A milestone: `OFFICIAL_FINANCIAL_EVIDENCE_SCALE_OUT_COHORT_3`.

## Annual financial evidence materialization hardening (2026-08-09)

`ANNUAL_FINANCIAL_EVIDENCE_MATERIALIZATION_HARDENING: PASS`. Local Tesseract 5.5.0
materialized only the retained scan-only PNJ/PVD FY2024 issuer filings into deterministic,
page-preserving sidecars, then promoted only source-page visually verified facts. PNJ is
four-of-five because its face statement has no labelled long-term-loan component, so debt
remains blocked. PVD is five-of-five in its explicitly reported USD and becomes an available,
historical-only, non-actionable Pillar A research input. The existing entity-profile authority
now covers PNJ/PVD as corporate for pre-profiled canonical shards; this does not set research
availability manually. PAN remains five-of-five; HPG/VNM trusted source precedence and every
generic market gate are unchanged. FPT remains `SOURCE_LOCATOR_REQUIRED`. No DB, provider,
DNSE, market-data refresh, or generated bundle was changed. Next: `OFFICIAL_FINANCIAL_EVIDENCE_SCALE_OUT_COHORT_2`.

## Bounded official financial evidence scale-out (2026-08-09)

`BOUNDED_OFFICIAL_FINANCIAL_EVIDENCE_SCALE_OUT: PARTIAL`. Checkpoint `a0759e3` preserved the
completed PAN source-authority vertical slice. PNJ and PVD then retained their issuer-owned
FY2024 consolidated statements (PVD explicitly audited); FPT's exact issuer filing returned
404. PNJ/PVD are scan-only `needs_ocr` artifacts, so no citations, qualified facts, or new
research eligibility were created. The issuer registry contains only the demonstrated PAN,
PNJ, FPT, and PVD domains/storage hosts, and the evidence bridge now refuses cross-ticker
artifact reuse. No DB, provider, market gate, or generated runtime publication changed.

## Canonical annual financial source authority (2026-08-09)

`CANONICAL_FINANCIAL_SOURCE_AUTHORITY_DECISION: PASS`. The selected authority is an issuer IR
audited annual consolidated financial statement, proven in a bounded retained PAN FY2024 pilot.
The governed artifact hash, manifest, page citations, VND unit, annual period, and consolidated
scope verify five required metrics; PAN's read-only research projection is now available for
FY2024. Four citations were append-promoted against the existing PAN artifact and the earlier
net-income citation remains unchanged. No provider/network request, database mutation,
canonical-shard mutation, or generated bundle publication occurred. Scale-out requires an
owner-approved registry host route before any new external issuer acquisition.

## P1.5 capability matrix (2026-08-09)

`P1_5_TICKER_CAPABILITY_MATRIX: PASS`. `export_ai_bundle.py` now attaches the additive,
deterministic `ticker_capability_matrix` to every member of the canonical production cohort:
`POW, SSI, HPG, EVF, PAN, PNJ, FPT, QNS, VNM, PVD, NVL`. It projects existing entity,
financial, historical-decision, provider-scoped market, research, portfolio, and market-basis
contracts without recomputing or promoting any result. Trust is lane-specific: qualified
provider observations remain `descriptive_only`, while generic valuation, liquidity, sizing,
execution, and backtest gates remain blocked.

`MARKET_DATA_TRACK: WAITING_EXTERNAL_ACCESS`. The selected FiinGroup route remains
`OWNER_ACQUISITION_REQUIRED` / `OWNER_CONFIRMATION_REQUIRED`; P1.5 made no provider call,
adapter, DB/runtime/generated-artifact change, or publication. The next independent roadmap
milestone is `CONNECT_PILLAR_A_MARKET_WIDE_CANONICAL_FACTS_TO_RESEARCH_ENGINE`.

## Pillar A research-engine connection (2026-08-09)

`PILLAR_A_RESEARCH_ENGINE_CONNECTION: PASS`. The new read-only
`research_financial_fact_projection` composes the existing market-wide canonical fact shards
into source-selection and capability-matrix input; it creates no persistent third store. A
Pillar A fact can enter the existing historical research input only when the unchanged
corporate metric set is fully `qualified`, same-period/consolidated, and carries explicit
citation/evidence/observation lineage. `provider_reported`, `partial`, `conflicted`, null, and
missing records remain distinct and fail closed. Existing trusted `financial_canonical` facts
win whenever available, preserving HPG/VNM behavior.

Actual read-only store state: 1,493 tickers, 195,552 facts, 1,492 tickers with facts, 15
known entity types, and only two qualified facts (HPG/VNM retained earnings). No ticker meets
the complete admissible Pillar A corporate research set, so additional full research eligibility
is **0**; this is a successful safety result, not a fallback to provider-reported facts.

Market gates remain unchanged. `DNSE_MARKET_DATA_ACCESS: PENDING_OWNER_ACCOUNT_ACTIVATION` is
recorded as the documented next qualification route; no credentials, SDK/API/provider calls, or
pilot occurred. FiinGroup remains a fallback candidate pending a future owner-enabled DNSE
HPG/VNM qualification pilot. The next canonical milestone is
`DNSE_HPG_VNM_MARKET_DATA_QUALIFICATION_PILOT`, blocked on owner account activation.

## P1E canonical-fact conflict decomposition and safe promotion (2026-08-09)

`PILLAR_A_CONFLICT_DECOMPOSITION: PASS`. The new read-only
`canonical_conflict_decomposition` projects canonical conflict records using the retained
semantic identity (ticker, metric, period/bounds/type, statement/scope, currency/scale,
provider, identity key, source hash, and observation IDs). It does not rewrite raw evidence,
choose a value, infer units, or promote a qualification tier. Its precise reason codes flow
through `research_financial_fact_projection` into `ticker_capability_matrix`.

Measured retained population: 1,145 conflicted tickers; 12,481 conflicted fact identities and
12,619 conflict records. Families are 7,190 cross-statement period/scope incompatibilities,
5,306 ambiguous differing restatement columns, 120 balance-sheet arithmetic violations, and
3 unreconciled revenue identities. All 5,306 restatement pairs have one provider/source hash
but different values and `restatement_state=unknown`, so no supersession can be selected. No
duplicate-equivalent, explicit unit/scale, or authority-resolved provider conflict is present:
`AUTO_RESOLVED_CONFLICTS: 0`; qualification, fact-status totals, research eligibility, and the
production 11-ticker membership remain unchanged.

`PILLAR_A_QUALIFICATION_EVIDENCE_PROMOTION_POLICY` is the next independent canonical
financial-data milestone. It must define a scalable minimum evidence path; it does not authorize
acquisition. DNSE remains separately `PENDING_OWNER_ACCOUNT_ACTIVATION`.

## Pillar A qualification evidence promotion policy (2026-08-09)

`PILLAR_A_QUALIFICATION_PROMOTION_POLICY: PASS`. The read-only
`canonical_financial_qualification_policy` is now the explicit contract between retained
canonical facts and the research projection. It requires semantic identity/bounds, consolidated
scope, provider and source hash, observation lineage, a hash-verified official artifact with a
deterministic citation, evidenced unit/currency, and no unresolved semantic, arithmetic, or
restatement conflict. It preserves the existing narrow annual-year-end-to-Q4 alias for
balance-sheet stock metrics only; it never aliases annual flow values to Q4. Explicit document,
supersession-evidence, and publication-date metadata are the minimum retained route through a
restatement; ingestion order is never a rule.

The corporate research lane remains annual, consolidated, same-period, and requires its five
fully-qualified metrics. The policy projects qualification reason codes and verified lineage
into the research adapter and capability matrix without rewriting a shard or admitting a
provider-reported value. Inventory over the current store: 195,552 facts; 2 already qualified;
0 safe promotions; 0 promotion-frontier facts/tickers; 195,550 facts missing a verified citation;
94,252 missing a source hash/artifact dimension; 5,306 restatement-blocked; 195,552 blocked from
the annual corporate lane by period/scope; and 123 arithmetic-blocked. The deterministic,
no-value candidate manifest is under `operations-review/`.

No retained canonical fact is annual, so there is no bounded retained-evidence promotion
frontier. The next canonical Pillar A milestone is
`CANONICAL_FINANCIAL_SOURCE_AUTHORITY_DECISION`; it must decide the authoritative annual-source
admission route before any bounded acquisition. DNSE remains separately
`PENDING_OWNER_ACCOUNT_ACTIVATION` and is not part of this decision.

## Canonical state lines

`tools/handoff.py` parses these three lines by prefix. Keep the prefixes exactly as written.

- Active phase: development runs on two pillars — A, market-wide canonical financial normalization (layers 1–4 complete and active); B, official corporate-action evidence, dated shares timeline, price adjustment factors, and provider share authority (measured and fail-closed as of P1J.1; **1 of 1,683 tickers has a qualified current share count** after B1.1, and the official ledger holds 1 qualified executed event). P0 market-data basis remains open and is the binding constraint: the **generic** price and volume basis are still `unknown`/`unverified`, so every current-market capability stays blocked — a **`vci.`-namespaced shadow** basis is qualified (P0-V/P0-W, below) and unlocks nothing generic. VCI is now recorded as **not raw-as-traded eligible**, which closed the previously-open P2a historical valuation path. **KBS is now recorded the same way** (P0-Z), from its own bounded lane and not inherited: `empirically_event_adjusted` at the `empirically_deduced` tier, with `volume_unit = shares` / `trading_value_unit = VND` and `volume_market_scope = unknown` — descriptive and provider-scoped technical use is available, liquidity and point-in-time use is unavailable by contract. P1 exact-session integrity, P1B/P1C/P1F/P1G/P1H/P1I/P1J/P1J.1 completed.
- Active milestone: Market-source authority reconciliation — **PASS** (2026-08-11; full narrative at the top of this file). Corrects a 2026-08-09 entry that incorrectly promoted FiinGroup API Datafeed to `PREFERRED_SOURCE_ID`/`OWNER_SOURCE_ACQUISITION_DECISION` — FiinGroup has no owner authorization, configuration, legitimate access, agreement, or rights, and is not an approved acquisition path; no paid provider becomes canonical without a new explicit owner decision. DNSE foreign-flow VALUE remains production-enabled for HPG/VNM/QNS; DNSE OHLC is `ADJUSTED_CONFIRMED` but raw-as-traded/point-in-time unsafe; DNSE market-volume basis remains unqualified; EODHD remains `REJECTED_BY_OWNER`. SSI/VSDC B2 evidence disposition: `PILLAR_B_B2_SSI_VSDC_EX_DATE_NOTICE_ACQUISITION` is `BLOCKED/DEFERRED_PENDING_NEW_OFFICIAL_EVIDENCE` after exact notice 198728; its missing official ex-date and execution evidence prohibit repeat acquisition and promotion. The next independent recorded candidate, `OFFICIAL_FINANCIAL_EVIDENCE_SCALE_OUT_COHORT_3`, is `AWAITING_OWNER_SCOPE_DECISION` because no fixed target set or exact filing locators are defined. Two further 2026-08-11 milestones sit above this line in the file and are not yet folded into it: **HPG evidence manifest restoration and Pillar-A performance closeout** (PASS — HPG's opening FY2024 share identity and its three EBITDA components now resolve as qualified) and **HPG current-state relative valuation** (built/wired, correctly `NOT_QUALIFIED`/not-yet-live — evidence coverage ends 2026-07-30, eight days short of the qualified DNSE session 2026-08-07). See the top of this file for both. Previous milestone: Generic Market Basis Unlock — raw price authority + volume trade-scope qualification — **PARTIAL**, network-bounded (11 read-only requests to an already-qualified KBS host), Producer-only. Two independent proofs, attacked directly rather than re-auditing the closed KBS/VCI adjusted findings. **PRICE (`RAW_AS_TRADED_PRICE_AUTHORITY: BLOCKED`, `EXPLICIT_RAW_ADJUSTED_NAMESPACE: ABSENT`):** every installed `vnstock` 4.0.4 provider explorer (vci, kbs, msn, fmarket, misc) was checked directly for an adjust/raw parameter or vocabulary — zero matches anywhere in any quote/trading module (the only recognized `adjustment_status` value repository-wide is the legacy, already-superseded `raw_as_quoted_no_adjustment_applied`). `config/official_source_registry.json`'s four approved sources (hose, hnx, vsdc, issuer_ir) declare only corporate-action/governance/financial-statement document types, none price-bearing, and the one registered future candidate (`official_authority_candidates.HOSE_TRADING_STATISTICS`) has no locator and was scoped for volume, not price. The blocker is a genuinely absent source, not an unqualified one — recorded as data in `market_basis_capability_registry.RAW_PRICE_NAMESPACE_INSPECTION`, not left as prose. **VOLUME — a real, new, bounded finding, KBS-scoped:** two KBS endpoints the closed P0-Z lane never examined (the price board `stock/iss` and the intraday trade tape `trade/history/{symbol}`, both already integrated in `vnstock`, same host `kbs_empirical_basis.py` already qualified) were tested for three tickers (HPG/VNM/VCB) on one session (2026-08-07). The intraday tape's full trading day sums — continuous buy/sell trades plus side-less auction-cleared trades — **exactly** to the price board's `volume_accumulated` (already known numerically identical to the qualified daily `v`), three times, zero residual. Separately-reported `put_through_qty` plays no part in any of the three sums: **KBS's daily reported volume demonstrably excludes negotiated/put-through trades** and demonstrably includes continuous-matched and auction-cleared trades. `odd_lot_inclusion` stays unknown (the dedicated endpoint is Sponsor-tier in the installed library, not probed). New `kbs_trade_scope_qualification.py` (pure classification, frozen evidence-verified contract mirroring `vci_volume_composition.py`'s own precedent — reconciliation results frozen as data rather than re-reading `operations-review/` at call time, so the capability matrix that imports this never depends on the evidence archive still being present); one new descriptive capability `kbs_volume_composition_disclosure` in `kbs_capability_matrix.py`; a new, additive `volume_trade_scope` field in its `matrix_snapshot()` that leaves the pre-existing, separately-guarded `volume_market_scope` field (a narrower, still-correct "unknown" finding scoped to the `data_day` endpoint alone) completely untouched. **Nothing about this changes what the currently-served production universe can do**: all 11 production tickers remain 100% VCI-sourced (unchanged from the prior milestone), so this KBS-scoped finding matters for KBS as the designated OHLCV failover provider and any future KBS-sourced ticker, not for HPG/VNM/etc. today. `days_to_liquidate`/`participation_rate_sizing`/`market_impact_estimation` and every other liquidity capability remain `unavailable_by_contract` for both providers — odd-lot (KBS) and full composition (VCI, unchanged, not re-probed) still block them, and one session is not yet a standing methodology. New deterministic, capability-specific authority-selection rule in `market_basis_capability_registry.py` (`select_price_authority`, 4 tiers: official raw → provider raw → provider-adjusted descriptive-only → blocked; `assert_no_fallback_merging` refuses two providers' answers collapsed into one). `HISTORICAL_VALUATION_UNLOCK: BLOCKED` (raw price authority absent is the binding constraint, unchanged). `ACTIONABLE_LIQUIDITY_UNLOCK: PARTIAL` (KBS-scoped, not production-relevant yet). Pillar B not touched — no acquisition this pass would have closed a *price* reconciliation gap specifically, per the milestone's own instruction not to acquire a document that "would merely add another known event without advancing raw/as-traded authority." 74 new tests (49 registry, 25 trade-scope module); consolidated regression 562/564 passing (the same 2 pre-existing, unrelated failures already flagged in the prior milestone, confirmed still untouched by this one's two Python source edits — `kbs_capability_matrix.py` additive-only, `market_basis_capability_registry.py` additive-only). See `operations-review/kbs-trade-scope-qualification-20260809/`. Previous milestone: Market Basis Capability Activation and Generic Unlock Gap Closure — **PASS**, network-free, both repositories, continuing from `M1_QUALIFIED_RESEARCH_LIVE_DELIVERY: PASS`. **Reconciles a coarse framing, not a new finding.** "Price/volume basis unknown, therefore nothing market-related is usable" was always too coarse: KBS's full price+volume capability matrix and VCI's volume-composition matrix were already qualified, and `provider_price_basis_registry.py` already held both providers' canonical price verdicts (`empirically_event_adjusted`, `empirically_deduced` tier, `raw_as_traded_eligible = false` for both) — but only `risk_liquidity.py` actually imported either matrix at runtime, and it gated its own return/volatility/drawdown computation on the **generic** `price_adjustment` flag rather than the provider-scoped verdict already available to it. The ~20 named entries in each matrix's `CONSUMER_CLASSIFICATION` were aspirational: zero real call-sites (`candlestick_patterns.*`, `vn_indicators.*`, `stock_analyzer.*`) import either module. **New `market_basis_capability_registry.py`**: one queryable registry composing both matrices unchanged, plus 8 new VCI *price* capability records (VCI never had a price matrix shaped like KBS's, only a flat eligibility list in `vci_direct_basis_pilot.py`) built entirely from `provider_price_basis_registry.py`'s already-established facts — no evidence re-derived. Adds the brief's Level 0-5 capability ladder as a read-only annotation and a 7-row generic-unlock gap table naming exact missing evidence per blocked capability (`RAW_AS_TRADED_PRICE_AUTHORITY_ABSENT`, `TRADE_TYPE_COVERAGE_UNQUALIFIED`, `POINT_IN_TIME_SHARE_BASIS_INCOMPLETE`, `GENERIC_PROVIDER_PROMOTION_NOT_AUTHORIZED`). **New `qualified_market_observations.py`**: the bounded, additive, non-actionable section this reconciliation activates — descriptive price/volume statistics plus (behind the `provider_series_return` label both matrices already require) window return, realized volatility and maximum drawdown, computed from a single-provider retained OHLCV window. **Verified 2026-08-09: all 11 production tickers are 100% VCI-sourced** in `dashboard-runtime/vn_stock.db` (a new read-only `load_ohlcv_provider_purity()` query, additive sibling field to `ohlcv_recent`, whose own shape is untouched). Fails closed on mixed-provider windows, unsupported providers, and fewer than 20 sessions; `is_actionable`/`liquidity_actionable` are hardcoded `False`, never computed. New opt-in `--include-qualified-market-observations`, wired through `export_ai_bundle.py` and (learning directly from the 2026-08-09 defect below about flags that never reach the supported command) through `tools/operate_stocklookup.py` at every touch-point the existing research-lane flags use — but unlike that lane, **not** restricted to `PILOT_TICKERS`, since this depends only on OHLCV provider purity, a property every production ticker already has. Consumer pass-through `apply_bundle_qualified_market_observations_contract` is verbatim, refuses (never widens) a malformed or non-`descriptive_only`/`provider_scoped` record, and treats a Producer `unavailable` verdict as a valid pass-through rather than a fallback trigger — a real `AttributeError`-on-malformed-input defect was found and fixed in its own shape check during this work. Generic-unlock route selected: **Pillar B, unchanged** — the concrete next input (an SSI VSDC ex-date notice, same acquisition pattern as VCB's 2026-08-08) was not executed here, deliberately: a live external network request is a different class of action from this milestone's source/test/doc scope. Volume trade-scope investigation required no new work — already closed by the 2026-08-04 "Ninety-six fields, and none of them says put-through" finding, now cited by name rather than re-probed. No Dashboard rendering; `risk_liquidity.py`'s existing output shape untouched. 85 new tests (73 Producer, 12 Consumer); 524/526 passing in the targeted Producer regression (2 pre-existing, unrelated failures — a date-relative fixture drift and a stale string assertion, confirmed via `git diff --stat` untouched by this milestone, flagged separately not fixed here); 418/428 passing in the full Consumer suite (10 pre-existing missing-generated-artifact failures, none touching the apply-chain this milestone extended). See `operations-review/market-basis-capability-activation-20260809/` and `docs/qualified_market_observations_contract.md`. Previous milestone: P0-Z.3 KBS coverage export seam and Consumer pass-through — **PASS**, network-free, both repositories. **The trace is the headline: KBS `va` has never been exported.** `vnstock` drops it before the pipeline, `ohlcv` has no value column, `export_ai_bundle` has no trading-value reference, and `analysis_bundle.json` `ohlcv_recent` rows are `{date,o,h,l,c,volume}`. So there is no bare number that lost its coverage meaning and no legacy `va` aggregate to quarantine; per the directive no product surface was invented, and `ABSENCE_OF_ACTIVE_VALUE_PATH` records the absence as data rather than leaving it to be inferred from silence. **Two errors in `ee057b9` corrected by the trace**: that closeout said "no existing consumer creates such a field [price × volume]" — false, `candlestick_patterns.py:148` computes `gtgd20_ty = (close*volume).rolling(20).mean()/1e9`; and its `CONSUMER_REQUIREMENTS` listed four `va` consumers, none of which read `va`, two of which named concepts that do not exist. The register is now written from a trace and holds only the forbidden uses; `gtgd20_ty` is **relabelled, not disabled** in `NON_VA_DERIVED_QUANTITIES` (it reconstructs no `va`, predates this lane, and its volume side is already classified analytical-not-liquidity in `market_volume_capability_matrix`). **New `kbs_trading_value_export.py`**: canonical 9-key block with a 20-key coverage sub-block, built only from canonical coverage logic; four shared statistic scopes (`single_observed_row` / `complete_requested_window` / `observed_rows_only` / `not_applicable`); `assert_block_valid` checks labels **against counts**; `assert_no_bare_value` refuses a value with no block; three legacy classes where absence of metadata resolves to `unknown`, never complete; two canonical warning tokens with one text table and a pinned SHA-256. **New Consumer `builders/kbs_trading_value_coverage_contract.py`**: copies all 20 fields verbatim, recomputes nothing, refuses a dropped field, refuses a widened verdict, refuses a stripped warning, and labels AI context `kbs_provider_observed_trading_value` with official-turnover / liquidity / market-scope / actionability all false at every coverage state. No schema bumped — the block is additive and absent everywhere today. 41 new tests; **561 passing** (Producer 445, Consumer 116) against a byte-identical frozen fixture in both repositories. See `operations-review/kbs-coverage-pass-through-20260804/`. Previous milestone: P0-Z.2 KBS trading-value coverage and safe-aggregation contract — **PASS**, network-free. Makes `va` availability structurally enforceable instead of dependent on a caller reading a note. **Inventory** (raw bytes, six retained payloads, 66 sessions): 38 `present_numeric`, 28 `field_omitted`, 0 zero / 0 null / 0 malformed / 0 missing rows. Windows: HPG W1 `partial_known` 0.583, VCB W2 `partial_known` 0.545, VNM W3 `partial_known` 0.545, HPG W4 `complete`, VNM W5 `complete`, VCB W6 **`absent` 0.000**. **Two parser defects fixed**: `field_omitted` and `present_null` both collapsed to `None`, and a malformed `va` aborted an entire payload whose OHLC was good — the state is now decided first and the value read from it. `present_zero` is *usable*: a session that traded nothing is a measurement, and excluding it would bias every mean upward. **New `kbs_trading_value_coverage.py`**: row/window/dataset coverage model, 5 `coverage_state` values, 24 classified operations (5 row-level, 5 partial-permitted-when-labelled, 5 requires-complete, 8 unavailable-by-contract), 7 classified consumers, legacy payloads fail closed for aggregates, consumers may narrow coverage but never widen it. `build_result` is the only constructor, so a number and its coverage metadata are made in the same call; `assert_result_labelled` validates the claimed state **against the counts it carries**, which is what blocks the one relabelling that matters (flipping `coverage_state` and `statistic_scope` together). **No synthesis**: `automatic_imputation_authorized` and `missing_as_zero_authorized` are constants; `kbs.reconstructed_price_times_volume` is reserved, unimplemented and unauthorized — on the rows where `va` is absent the retained price is an *adjusted* price, so price × volume is not a historical turnover. No existing consumer creates such a field. **Causal-language audit (Part G)**: the `va`/adjusted-row correlation is 66/66 with zero exceptions and is recorded as `observed_association = va_missing_on_tested_empirically_adjusted_rows` with `causal_explanation = unknown` and `coverage_generalization = limited_to_retained_windows`; three active-source overclaims corrected, frozen artifacts not edited (`CORRECTED_CAUSAL_FRAMING`), and the audit re-runs as a standing test. All 15 descriptive/technical capabilities remain available; `volume_market_scope` stays `unknown`, `liquidity_actionable` false, `is_actionable` unchanged. 26 new tests; 442 passing across the validated suites (420 basis/capability/gate/export + 22 Consumer readiness). See `operations-review/kbs-trading-value-coverage-20260804/`. Previous milestone: P0-Z.1 KBS empirical-basis closeout and prospective mutability protocol — **PASS**, network-free. Corrects one reasoning error and strengthens one anchor; no capability changed and no unknown dimension upgraded. **(1) The three mutability questions are now separate.** P0-Z reported `historical_mutability = not_observed` with the gloss "the comparison spans no qualified share event" — true, and misleading, because it implies a better *window* would have answered it. It would not: both retrievals (2026-08-01, 2026-08-04) post-date every qualified ex-right date in every tested window, so the pair is `both_post_event` and **no amount of elapsed time or window selection can produce a pre/post pair from this evidence**. `classify_snapshot_pair` now classifies the pair and `historical_rewrite_test` reports `event_time_rewriting = not_testable_from_this_pair` however clean the diff is; `post_event_snapshot_stability = observed_for_tested_retrieval_interval` is recorded separately as the real finding it is; `volume_adjustment_basis` stays `not_observed` and is now gated on the pair class first, so a post-event revision can no longer be read as a corporate-action adjustment. **(2) The absolute unit anchor is re-grounded.** The VWAP identity only ever earned the scale *quotient* (1.0); the absolute scale now rests primarily on `numeric_identity_with_an_independently_unit_qualified_series` — KBS returns integers exactly equal to stored VCI volumes on 34 sessions across all three tickers, and VCI's unit came from its own per-trade tape, so equality is impossible under a thousand-fold difference. It transfers **magnitude only**; VCI's market scope is not inherited. The issued-share-count falsifier (27.5bn implied vs 8.44bn issued, 1.63× margin) is retained as the corroborating route, still `observed_only` and still `unit_anchor_admissible_for_valuation = False`. Units stay `shares`/`VND` at `empirically_deduced` — neither route can reach `documented_verified`. **(3) New `kbs_mutability_protocol.py`**: the prospective pre/post observation protocol — 16 required pre-event manifest fields, a strictly-before-ex-date check, identical-request enforcement, 8 comparison fields, a mandatory control, 5 separated change classes, 7 scoped verdicts, deterministic phase-bearing artifact paths. **Inert by contract**: no network, scheduling, polling or automatic acquisition, asserted against the module's parsed import graph. The frozen P0-Z evidence report is **not edited**; the framing correction is recorded in `CORRECTED_FRAMING` and the withdrawn recommendation in `SUPERSEDED_RECOMMENDATION`. All 15 descriptive/technical capabilities remain available, all 13 liquidity/execution/point-in-time capabilities remain `unavailable_by_contract`, `is_actionable` unchanged. 26 new tests; 407 passing across the validated suites. See `operations-review/kbs-empirical-closeout-20260804/` and `docs/kbs_empirical_basis_qualification.md`. Previous milestone: P0-Z KBS empirical price-and-volume basis qualification and capability relaxation — **PARTIAL**. Reopens exactly one closed lane. Phase 1C's finding stands and is re-confirmed against six fresh payloads (no adjustment flag, no unit declaration, no trade-method metadata); what is superseded is the inference that the fields were therefore *unusable*. New canonical qualification ladder in `evidence_qualification_tiers.py` (`documented_verified` / `empirically_deduced` / `observed_only` / `unknown` / `conflicted` / `invalidated`); a verdict at `empirically_deduced` must carry all 13 retention fields or it is refused. Six bounded requests (budget 6), HPG/VNM/VCB, 66 sessions. **Price:** `empirically_event_adjusted`, `empirically_deduced` — pre-event prices sit off the HOSE tick lattice and the off-lattice prefix terminates exactly at a qualified ex-right date for HPG (2026-05-25 share issue), VCB (2026-07-23 cash) and VNM (2026-06-26 cash); independently, `va` is absent over exactly the off-lattice runs in all 66 sessions and its presence tracks the boundary, not the calendar. `provider_methodology = unknown`, `coverage_generalization = limited_to_tested_windows`, `raw_as_traded_eligible = false`, `historical_mutability = not_observed` (the 9-session re-observation is byte-identical but spans no event, so it is a control, not an immutability proof). **Units:** `volume_unit = shares`, `trading_value_unit = VND`, `empirically_deduced` — the VWAP identity earns only the scale *quotient* (1.0, from 36 discriminating rows over 3 tickers and 3 price levels, all 14 competing quotients rejected); the absolute anchor is earned separately from a retained issued-share count used strictly as an order-of-magnitude falsifier. 2 rows are explained by no candidate scale and are retained as contradictions, not resolved. **Volume adjustment:** `not_observed`, never derived from the price finding — but KBS restated prices on 13 VCB sessions while returning volumes byte-identical to the independently retained pre-event series, so the two fields demonstrably move on different schedules. **Market scope:** all 6 dimensions `unknown`; upgrading one needs 2 admissible independent observations with all 6 confounders eliminated, and secondary media are counted and never qualify. New `kbs_capability_matrix.py`: **15 descriptive/technical capabilities available** under 7 mandatory warnings and 7 provenance fields, **2 conditional** behind `return_type = provider_series_return` (the 3 forbidden return labels raise), shadow backtest **eligibility defined and not implemented** (8 conditions), **13 liquidity/execution/point-in-time capabilities `unavailable_by_contract`**; 20 consumers classified, unregistered ones fail closed. `is_actionable` unchanged, `liquidity_actionable = false`, no production write. 36 new tests; 389 tests passing across the validated suites (367 basis/capability/gate/export + 22 Consumer readiness and pass-through). See `operations-review/kbs-empirical-basis-20260804/` and `docs/kbs_empirical_basis_qualification.md`. Previous milestone: P0-Y market-volume and liquidity availability capability closeout — **PASS**. Converts the `63ecc48` VCI volume findings into system-wide capability boundaries. Two terminology corrections, no verdict changed: `market_scope = partially_qualified` → `overall_market_scope = partially_observed_but_not_qualified`, and `opening_auction_inclusion = qualified` → `demonstrated_for_observed_ato_field` (the narrow result — one observed ATO-labelled quantity is inside the provider accumulator; `general_auction_composition = partially_observed`, `closing_auction_inclusion = unknown`). `matched_trade_inclusion`, `negotiated_inclusion` and `odd_lot_inclusion` promoted from `unknown`-with-sidecar to top-level `unavailable_from_observed_vci_surfaces`. New `market_volume_capability_matrix.py`: **9 descriptive/analytical capabilities retained** under mandatory provider-scope warnings, **13 liquidity and execution capabilities `unavailable_by_contract`** with `reason = complete_market_composition_not_qualified`, `reopen_condition = new_authoritative_source_contract` — explicitly *not* reopenable by further VCI pagination or endpoint probing. 23 volume consumers classified; unregistered consumers fail closed. The latent path is the point: every liquidity gate was keyed to `volume_basis_verified`, which the shares finding invited someone to flip; `vci_volume_basis.validate_forward` now returns `liquidity_activation_permitted: False` on success, and `analysis_lane_eligibility` emits an unconditional liquidity-contract refusal that does not lift when the basis verifies. HOSE trading statistics registered in `official_authority_candidates.py` as a **future qualification candidate only** — no URL, `automatic_acquisition_authorized = false`, 8 open semantic questions, preferred (not sole) official authority path. No network request, no evidence artifact rewritten, `liquidity_actionable = false`, `further_vci_pagination_authorized = false`, `further_vci_endpoint_probe_authorized = false`. 553 tests + 11 subtests passing. See `operations-review/market-volume-capability-closeout-20260804/` and `docs/market_volume_capability_contract.md`.
- Production state: the production artifact set was regenerated and validated end to end on 2026-08-03 through `tools/operate_stocklookup.py` (with `--include-canonical-financial-facts` verified dry run) and is byte-unchanged by P1J; `config/official_source_registry.json` is approved; `config/ticker_entity_profiles.csv` and every authoritative database are unchanged.

## Latest market-basis route verification (2026-08-09)

`PILLAR_B_OFFICIAL_DAILY_TICKER_SESSION_STATISTICS_ROUTE_QUALIFICATION` finished with the
precise terminal blocker
`OFFICIAL_DAILY_TICKER_SESSION_STATISTICS_ROUTE_NONCONFORMING_SUMMARY_ONLY`. Two retained,
first-party HOSE daily Trading Summary PDFs are reproducible dated artifacts but expose index
closing values, aggregate matched/put-through totals, and selective top-five ticker volumes —
not a named-equity close or ticker-level trade-type totals. `RAW_AS_TRADED_PRICE_AUTHORITY`
therefore remains `PARTIAL` only for the prior HPG 2024-12-31 annual-report observation;
historical stability, generic actionable price/volume, valuation, and liquidity remain blocked.
No runtime or production artifact changed. Evidence:
`operations-review/official-daily-ticker-session-statistics-route-qualification-20260809/`.

## Market-data source-authority decision (2026-08-09)

`MARKET_DATA_SOURCE_AUTHORITY_DECISION: PASS`. The selected future raw-history candidate is
**FiinGroup API Datafeed `/Market/GetHoseStockv2`**, because its documented schema separates
unadjusted OHLC fields from `*Adjusted` fields and `RateAdjusted`, and names ticker/date plus
order-matching and put-through totals. This is only an owner-level commercial acquisition
decision: no credentials, contract, payload, raw namespace, or production integration exists
yet. `RAW_PRICE_AUTHORITY_SOURCE_SELECTED: YES` while `RAW_PRICE_AUTHORITY: PARTIAL` remains
the existing one-date HOSE HPG observation; `VOLUME_SCOPE_AUTHORITY_SOURCE_SELECTED: NO`, and
all generic/actionable gates remain blocked. The next canonical milestone is
`OWNER_SOURCE_ACQUISITION_DECISION`; see
`operations-review/market-data-source-authority-decision-20260809/`.

## FiinGroup raw-history access (2026-08-09)

`FIINGROUP_SOURCE_ACQUISITION_MILESTONE: PASS` with
`FIINGROUP_ACCESS_STATE: OWNER_ACQUISITION_REQUIRED` and
`LICENSE_AUTHORITY: OWNER_CONFIRMATION_REQUIRED`. No configured FiinGroup access, credential
reference, adapter, or agreement exists; no secret value or commercial endpoint was read or
called. The acquisition package is complete for only `/Market/GetHoseStockv2`, HOSE HPG/VNM
daily records from 2024-01-01 and the documented raw/adjusted/volume/provenance fields.
`MARKET_DATA_TRACK: WAITING_EXTERNAL_ACCESS`; all authority and downstream gates remain
blocked/partial exactly as before. While access is external, the parallel canonical work is
`P1.5_TICKER_CAPABILITY_TRUSTED_TICKER_MATRIX_BUNDLE_ATTACHMENT`, which has no raw-market-data
dependency. Evidence: `operations-review/fiingroup-raw-market-history-access-20260809/`.

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

## Qualified research lane (product capability layer, live 2026-08-09)

A separate numbering track from the Phase 0A-6E working-session labels in the P0-P5
cross-reference table above (`ROADMAP.md`): this is a **product capability** built on top
of the existing P3 evidence-qualified analysis, not a pillar-A/B market-data milestone. It
consumes exactly the same `financial_canonical`/`fundamental_quality` sections P3 already
produces; it adds no new evidence source and moves neither the price-basis nor volume-basis
blocker below. Producer commits `7293f78`..`e98cd53` (2026-08-09): a historical decision
contract (bear/base/bull, risks, catalysts, invalidation — all `historical_only`,
`is_actionable: false`), a Phase-4C-style risk/liquidity/portfolio gate (liquidity refuses
unconditionally on the unqualified price/volume basis above), a compact AI-facing brief, a
bounded scale-out selector, a snapshot-delta comparator, and immutable snapshot retention.
Consumer pass-through in `ai-core-private` (`b024895`..`693b375`) is generic per-ticker —
verified to carry no hidden pilot-ticker restriction.

**Shipped to the actual served production universe on 2026-08-09** — the previous
"production-active" claim for this lane (referenced in prior handoffs) was only ever true
against `dashboard-runtime` (the runtime root nothing serves); it had never reached
`worktrees/market-dashboard-main`/`main`, where the live site actually renders from. Fixed
via `tools/operate_stocklookup.py`, which previously exposed none of
`--include-historical-decision-analysis` / `--include-portfolio-risk-analysis` /
`--include-historical-scaleout` / `--include-qualified-research-brief` even though
`export_ai_bundle.py` had supported them since the commits above — they were only reachable
by invoking the exporter directly, bypassing the supported command's verify/rollback gates.
`DEFAULT_TICKERS` also silently included `VNINDEX`, which the actually-shipped release has
never carried (`unproven_tickers: []` in the live manifest, not `["VNINDEX"]`); requesting it
by default tripped the context-package freshness gate for a symbol outside both the shipped
universe and this lane's target population (an index has no issuer), inviting an unforced
`--prepare-inputs` run. Both are corrected in `tools/operate_stocklookup.py`.

Live scope: all 11 production tickers preserved (`POW SSI HPG EVF PAN PNJ FPT QNS VNM PVD
NVL`); research is additive-only to `HPG`/`VNM` (both `eligible`/`historically_mixed`) via the
existing `PILOT_TICKERS` gate. `VCB` was evaluated and deliberately **not** added — it sits
outside the currently-shipped 11-ticker universe, and folding a new ticker into that universe
is a separate scope decision from delivering the research lane, not a corrective one. The
other 9 tickers correctly show no research section (`entity_type` unresolved or
`financial_canonical` not yet qualified for them) and render the dashboard's existing
"unavailable" fallback. `--include-historical-scaleout` was evaluated and deliberately **not**
enabled for this release: under the current 15-row `config/ticker_entity_profiles.csv`
ceiling it selects 0 additional tickers from this universe (`HPG`/`VNM` are its only
eligible hits and both are already pilot-excluded), and its output key
(`historical_research_brief`) isn't read by the dashboard renderer — enabling it would have
added dead surface area, not delivered value. It remains an available, tested, opt-in flag
for when entity-archetype coverage actually grows.

**Why this matters for future sessions**: shipping this lane surfaced a real bug in
`prepare_context_packages` — it runs before `export_bundle` rewrites `analysis_bundle.json`,
so if the runtime root's on-disk bundle is transiently narrower than the ticker set being
prepared (as it was here, from an earlier untracked pilot export), the Consumer context
builder's `analysis_bundle.json` fallback logic marks every section it can't find as
`*_not_in_legacy_bundle`/`missing` — a real content defect, not a stale timestamp, and
present in 4 of the 11 tickers' embedded `context_package` sub-blob in the **already-shipped**
release too (unrelated pre-existing issue, confirmed same pattern in the live bundle, not
introduced by this delivery). Remediated by rebuilding context packages once the correct
full-universe bundle was in place. Do not run `prepare_context_packages` (part of
`--prepare-inputs`) while the runtime root's bundle is known to be narrower than the ticker
set being prepared.

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

**SSI FY2024 financial-identity evidence promotion (2026-08-08).** A hash-verified
issuer-hosted SSI audited FY2024 document directly supports consolidated VND
`current_liabilities=46,599,438,522,989` as at 2024-12-31. The approved manifest and citation
are active in the runtime financial-identity sidecar. The retained VCI Q4 value is numerical
corroboration only, not semantic provider qualification, because provider scope is unknown. This
stock identity alone has the existing year-end-to-Q4 alias; no canonical-fact store rebuild,
qualified-count change, readiness change, valuation, Consumer, or Dashboard output followed.

**PAN FY2024 financial-identity evidence promotion (2026-08-08).** A retained issuer-hosted audited
statement directly supports consolidated VND `net_income=1,167,068,107,309` for the year ended
2024-12-31. The retained annual VCI observation has the same total-profit-after-tax identity,
period, scope, unit, sign, and value. Its approved manifest and citation are active in the runtime
financial-identity sidecar. It is a flow identity, not a stock observation: no year-end-to-Q4
alias exists. No canonical-fact store rebuild, qualified-count change, readiness change,
valuation, Consumer, or Dashboard output followed.

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

## 2026-08-09 — Pillar B: OFFICIAL_EXCHANGE_RAW_PRICE_AUTHORITY_AND_VOLUME_SCOPE_PILOT — PARTIAL

One bounded official HOSE locator route succeeded: the retained exchange Annual Report 2024
at `staticfile.hsx.vn` (PDF SHA-256
`0ae9f3095d3d021b063c3ffe27d698b58dae825c89e00e457ab92d83dbb03427`,
14,708,074 bytes) names `Mã CK / Stock code`, `Giá đóng cửa / Closing Price
(31/12/2024)`, and `VND Thousand`. Its HPG row is therefore one explicit official
session-close observation: **2024-12-31, 26,650 VND/share**. The retained report is
reproducible and first-party, but it supplies neither a daily ticker history nor a
non-revision policy, so `RAW_AS_TRADED_PRICE_AUTHORITY = PARTIAL`, restricted to that
exact HPG/session record. It is not a generic raw price source.

The frozen VCI HPG row for that same session is 19,830 VND/share (ratio 0.7440900563 to
the official observation). This demonstrates distinct official-raw and provider-adjusted
namespaces; the two are preserved separately in `market_basis_capability_registry.py` and
cannot merge or fall back. `RAW_ADJUSTED_RECONCILIATION = PARTIAL`: no retained official
daily event window covers the already-qualified VCB 2026-07-23 cash-dividend ex-date, so a
corporate-action factor is neither inferred nor claimed.

The same report explicitly labels order matching and put-through, but only in annual
aggregate/foreign-investor tables. It does not provide ticker-session category totals that
can reconcile to VCI daily `v`; `VCI_TRADE_TYPE_COVERAGE = BLOCKED_DATA` and every VCI
component remains unknown. KBS remains `PARTIAL` (continuous and combined auction included,
put-through excluded, odd-lot unknown). Generic `price_basis_verified` and
`volume_basis_verified` remain false; no runtime, database, bundle, dashboard, provider
refresh, valuation, backtest, ranking, or sizing output changed. Full retained evidence and
field citations: `operations-review/official-exchange-raw-price-volume-pilot-20260809/`.

The only raw-price/share-basis intersection is HPG at 2024-12-31 (the official 26,650 VND
pilot observation plus its qualified FY2024 period-end 6,396,250,200 shares). It makes a
future bounded market-cap check conceivable but does not open valuation: date coverage,
official event-window history, and complete lineage remain absent. Thus
`HISTORICAL_VALUATION_UNLOCK = PARTIAL`; `ACTIONABLE_LIQUIDITY_UNLOCK = BLOCKED`.

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
without one (VCB, SSI). The VCB source path has now been exercised once, from a direct VSDC link
observed in an already-retained VCB notice: `https://vsd.vn/en/ad/180140` was retained on
2026-08-08 (69,107-byte HTML, SHA-256 `b0a69a5e…502b66f2`, HTTP 200). Its own text states
`Record date: 13/03/2025` and a 495-new-per-1,000 execution rate, but no explicit official
ex-date. B3 classified it from its own VSDC record-date language and emitted one unpromoted
typed observation: `stock_dividend`, `record_date=2025-03-13`, and
`stock_ratio=0.495` only because the execution-rate notation and the explicit "495 new shares
for every 1000" wording agree. Approval, ex-, payment, effective, and trading dates plus all
share counts remain unavailable; no date is substituted, no factor/share authority is promoted,
and no ledger or valuation gate changes. SSI has not been requested.

One bounded offline discovery pass over the retained VCB registered-securities certificate then
observed `https://vsd.vn/en/ad/182319`; one VSDC request retained that 65,592-byte HTML notice
(SHA-256 `b31e0e46…0eddfab3`). Its own body explicitly identifies the same dividend purpose and
`record date: 13/03/2025` as the first notice, and states `Trading Date official: 09/05/2025`.
The typed observations cross-link only through that document-stated composite reference, never
issuer, ISIN, arithmetic, chronology, or ratio. The date is a scheduled trading semantic, not
completion or an ex-date; `ex_date`, listing-effective date, share counts, current-share
authority, factor, ledger, valuation, and production remain unavailable/untouched.

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

## 2026-08-09 — Qualified historical fundamental analytic depth — DONE

The Producer now projects annual, consolidated, provenance-carrying corporate facts into a
pure historical analytics contract for HPG, VNM, PAN, PVD and NVL. It provides explicitly
qualified earnings/OCF states, OCF/NI applicability gates, debt/equity, cash/debt, net debt,
net-debt/equity, conditional scenarios and a descriptive no-ranking cohort matrix. PVD remains
USD and no FX conversion or monetary cross-currency comparison is emitted. Trend remains
`insufficient_history` until two complete qualified annual periods exist. Market gates, DNSE
status, evidence backlog and runtime publication are unchanged. See
`docs/qualified_historical_fundamental_analytics_contract.md`.

## 2026-08-09 — Qualified historical comparative research and AI UX — DONE

The fixed HPG/VNM/PAN/PVD/NVL cohort now has a Producer-owned, provenance-carrying qualified
cohort comparison. It distinguishes cross-sectional context from unavailable multi-period
trends, adds bounded cash-conversion and historical-stress sub-conclusions, and preserves PVD
as USD without absolute cross-currency comparison. Consumer pass-through and Dashboard rendering
remain non-actionable: no valuation, ranking, recommendation, liquidity, or market gate changes.
Evidence scale-out remains paused; PNJ/POW/QNS/FPT backlog and DNSE pending activation remain
unchanged. See `docs/qualified_cohort_comparison_contract.md`.
