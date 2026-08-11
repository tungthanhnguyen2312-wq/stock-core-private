# Decisions

## 2026-08-11 - Adopt market-wide ingest-first feature-store architecture

- The owner authorizes the market-wide architecture pivot. The active chain is market universe → raw lake → data quality → canonical/semantic/PIT → vectorized feature store → feature-level qualification/capability → polymorphic strategy engine → portfolio/risk/leverage → AI research/counter-thesis → dashboard/human decision.
- `SUPERSEDED_AS_DEFAULT_WORKFLOW`: individual-ticker qualification before raw ingestion. This changes no historical passed evidence, provider authority, or use gate. The historical 11-ticker set is now golden/regression coverage, not the production universe.
- Raw records are immutable and provenance-bearing. Unknown semantics are retained; an anomaly routes to a dispositioned exception queue and is never automatically deleted. Qualification governs a field/feature/use, not a whole ticker.
- Formalizable calculations and eligibility are deterministic Python authority. AI is limited to semantic research, candidate evidence extraction, explanation, counter-thesis, and anomaly surfacing; it cannot fabricate numerical inputs, status, probabilities, targets, or authority.
- No provider adoption, source-authority promotion, bulk crawl, runtime mutation, publication, deployment, commit, or push is authorized by this decision. The next milestone is `UNIVERSAL_MARKET_UNIVERSE_BULK_DNSE_INGESTION_V1`.

## 2026-08-11 - Next official financial evidence cohort resolves the FPT blocker and preserves PNJ fail-closed

- The owner-bounded follow-up selected only the already identified FPT and PNJ Cohort 3 blocker
  scope. It does not reopen closed Cohorts 3 or 4, admit a random issuer, add a provider, or
  expand source authority.
- FPT's official disclosure proxy on the already approved `fpt.com` host supplied retained,
  audited consolidated FY2025 bytes. The hash-bound document and five exact source-page citations
  support the existing annual corporate research projection, including debt only as its visible
  short- and long-term borrowing/finance-lease component sum. This creates a historical-only,
  non-actionable FPT research input and changes no market or valuation authority.
- PNJ's official FY2025 filing is retained but still has only a labelled `Short-term borrowings`
  line. Its non-current liabilities do not identify a borrowing or finance lease. The existing
  two-component debt contract therefore remains `REQUIRED_DEBT_COMPONENT_MISSING`; neither a
  debt total nor research eligibility is inferred.
- Any further official financial-evidence acquisition again needs an explicit
  `OWNER_OFFICIAL_FINANCIAL_EVIDENCE_SCOPE_DECISION` for a finite qualifying issuer source.

## 2026-08-11 - Cohort 4 closes partial: SSI direct identity, QNS corporate set

- The owner fixed `OFFICIAL_FINANCIAL_EVIDENCE_SCALE_OUT_COHORT_4` to exactly SSI and QNS.
  No third ticker, source host, provider, crawl, FPT/PNJ retry, or substitute was authorized.
- SSI's retained issuer FY2024 audited consolidated PDF directly and hash-verifiably supports
  `current_liabilities = 46,599,438,522,989` VND as at 2024-12-31. It is promoted once through
  `evidence_promotion.py` with page-10 OCR lineage. The securities-sector contract remains
  authoritative: short-term borrowings and financial leases are not relabelled as corporate
  total interest-bearing debt, and no corporate five-metric research eligibility is inferred.
- QNS's issuer FY2024 audited consolidated document and five financial identities were already
  present in the governed manifest. The source-page and explicit maturity-zero debt path
  re-verified; append-only replay correctly added neither a duplicate manifest record nor a
  citation. Its existing historical-only, non-actionable corporate research result stands.
- SSI annual financial evidence is strictly independent of the SSI/VSDC corporate-action/ex-date
  branch, which remains deferred pending its separately specified official facts.

## 2026-08-11 - Cohort 3 closes fail-closed to its owner-fixed FPT/PNJ/PVD scope

- `OFFICIAL_FINANCIAL_EVIDENCE_SCALE_OUT_COHORT_3` was authorized for exactly FPT, PNJ, and
  PVD. It does not authorize any fourth ticker, a crawl, URL variation, a provider fallback, or
  a new source authority.
- PVD's FY2024 issuer-IR audited consolidated filing
  (`e03146183ffecb8cc94c5302edca1d8b5010e2121a00d18ae74e284cf0c306cb`; SHA-256
  `ba70100acf9391a85992e67ebc1a3d68da33e50402a17e860f579e320f5f2d14`) and its five annual
  consolidated USD citations were already qualified and manifest-registered. Re-verification
  confirmed the immutable artifact and all five facts; append-only authority forbids a duplicate.
- PNJ's retained FY2024 issuer filing remains hash-verified but has no labelled long-term
  borrowing or finance-lease component. The known short-term amount cannot stand in for total
  interest-bearing debt; its result remains `REQUIRED_DEBT_COMPONENT_MISSING`.
- FPT's prior exact audited-statement locator and two exact official-IR FY2024 annual-report
  locators returned HTTP 404. Since no source bytes were retained, no FPT identity, citation, or
  manifest record was created. A reissued official locator, not an inferred variant, is required.
- The cohort is `PARTIAL` and closed. Any follow-up must be separately owner-scoped to the exact
  missing official evidence; no current roadmap entry authorizes more acquisition.

## 2026-08-11 - SSI/VSDC B2 is deferred pending new official evidence

- The one authorized VSDC notice (`https://vsd.vn/en/ad/198728`; SHA-256
  `bd7d4054613ae6f9c5ee1ddc6b787bf706ac6a18f551aff3c9683a85bcc06dad`) is retained once and
  directly supports SSI identity, cash-dividend terms, record date, the 5:1 prospective bonus
  ratio, and planned share count.
- It states neither an explicit official ex-date nor execution/actual share-change evidence.
  `PILLAR_B_B2_SSI_VSDC_EX_DATE_NOTICE_ACQUISITION` is therefore
  `BLOCKED/DEFERRED_PENDING_NEW_OFFICIAL_EVIDENCE`. Record date, planned shares, payment date,
  and a calculated trading date are prohibited substitutes; no repeat acquisition or promotion
  is authorized until independent official evidence supplies the missing facts.
- `OFFICIAL_FINANCIAL_EVIDENCE_SCALE_OUT_COHORT_3` is the next independent recorded candidate,
  but it has no owner-approved fixed target set or exact filing locators. It requires an owner
  scope decision before any issuer acquisition may start.

## 2026-08-11 - Reconcile market-source authority with closed owner decisions and implemented DNSE contracts

- Commit `f216cfb` made a decision-only comparison of commercial candidates but incorrectly
  represented FiinGroup API Datafeed as `PREFERRED_SOURCE_ID` and made
  `OWNER_SOURCE_ACQUISITION_DECISION` the next canonical milestone. That designation is
  superseded. FiinGroup has never been owner-authorized or configured, has no legitimate access
  or retained rights agreement, and is not an approved acquisition or integration path.
- No paid provider may become a canonical market-data route without a new explicit owner
  decision. EODHD remains `REJECTED_BY_OWNER`; it is not a fallback, qualification route, or
  investigation target.
- The implemented DNSE authority is field-specific: foreign-flow VALUE is production-enabled
  for HPG/VNM/QNS; DNSE OHLC is adjusted and retrospective/non-point-in-time; DNSE market-volume
  basis remains unqualified. These do not open generic raw-price, market-volume, valuation,
  liquidity, sizing, execution, or backtest gates.
- The former next Pillar-B milestone, `PILLAR_B_B2_SSI_VSDC_EX_DATE_NOTICE_ACQUISITION`, is
  superseded by the deferred evidence disposition above.

## 2026-08-11 - HPG manifest authority restoration preserves the existing fail-closed valuation boundary

- The existing HPG FY2024 audited-consolidated evidence identity
  `a7c3711d1b02c131a87fef4a0f5bd4d5fbd780bbb0c07665111a358a2ddcd2a8` is restored through
  the sole append-only manifest writer, with its previously qualified SHA-256, source metadata,
  and an explicit retained-document path. No citation row, source document, or database row was
  added or changed.
- The generic manifest archive-path resolver and cited-financial adapter were already shipped in
  `1302ef0`; this milestone verified that existing path contract, including unregistered and
  hash-mismatched fail-closed controls, rather than creating a duplicate loader or fallback.
- Registration qualifies HPG's FY2024 opening share identity and EBITDA components. It does not
  qualify current shares for 2026-08-07: `coverage_through=2026-07-30` remains short of the DNSE
  price session, so every current-state valuation method stays unavailable for the existing,
  explicit `qualified_current_shares_outstanding_for_session` requirement.
- The completed Pillar-A performance repair is recorded as a separate, closed Producer side-track:
  request-scoped post-focus observability isolated global coverage, and the per-export official
  fact index removed repeated verified-identity scans without changing bundle semantics.

> **Superseded entries are marked in place.** The three 2026-08-03 P1H/P1I/P1J entries
> below record counts and share anchors that were never measured or were wrong; each
> carries a SUPERSEDED note pointing at the P1J.1 entry that corrects it. They are kept
> rather than deleted so the record of what was believed, and when, stays intact.

## 2026-08-11 - Current-state relative valuation: strict share coverage over a permissive one, and three discovered-not-fixed evidence-loader gaps

- `share_transition_bridge.resolve_share_transition` was chosen over `market_wide_current_shares_resolver.py`
  for current shares, even though the latter's `qualified_official` lane already reports HPG
  qualified for a session as late as 2026-08-07. That lane extrapolates a single vendor
  corroboration (dated 2026-07-30) forward to any later session indefinitely, with no requirement
  that the corroboration itself reach the target date — exactly the "infer continued validity
  beyond proven event/coverage dates" pattern this milestone was told not to do. The stricter
  bridge (`coverage_through` must itself reach `target_date`) was the one this milestone was
  explicitly told to reuse, and its real result for HPG's own 2026-08-07 DNSE session is
  `latest_historical_only`, not `current_qualified` — reported honestly, not patched around.
- One current share count feeds every method (`market_cap`, `pe`, `pb`, `ps`, `enterprise_value`,
  `ev_sales`, `ev_ebitda`), not `relative_valuation.py`'s period-end/weighted-average split. That
  split exists because a historical checkpoint relates one *completed* period's price to that same
  period's flow/stock figures; a current price has no completed "current period" to weight a share
  count across, so a single current-shares-outstanding figure is both simpler and the standard
  real-world convention for a current trailing multiple.
- `current_state_relative_valuation` is deliberately not named `current_valuation`:
  `ticker_capability_matrix.market_actionable.current_valuation` already exists as an unrelated,
  market-wide generic capability-status slot (`market_basis_capability_registry.py`). Reusing that
  string for a different, evidence-bounded, ticker-specific concept would have made two unrelated
  "current_valuation" claims sit side by side in the same bundle.
- Three real, pre-existing evidence-loader gaps were found while wiring this contract and are
  deliberately not fixed here: (1) `data/official-evidence/manifest.json`'s 11 records omit
  `evidence_id a7c3711d1b02c131a87fef4a0f5bd4d5fbd780bbb0c07665111a358a2ddcd2a8`
  (`hpg-consolidated-fy2024-audited.pdf`), so `load_verified_share_basis`/`load_verified_ebitda_components`
  reject every HPG/VNM/VCB row referencing it with `evidence_missing_or_hash_mismatch`; (2)
  `official_evidence.load_cited_financial_records` resolves each manifest record's document at a
  flat `data/official-evidence/<filename>` path instead of using that record's own
  `archive_document_path`, so HPG's newer, correctly-manifest-registered `financial_identity_citations.jsonl`
  facts (shareholders_equity, net_income, revenue, cash, debt; evidence_id `e52eeb95...`) never
  reach `canonical["records"]`, and `_financial_input`'s rigor-ranked dedup silently falls back to
  lower-rigor `financial_snapshot`/`financial_observation_store` rows instead. Repairing either is
  a registry/loader-level fix touching every other qualified-share/financial-fact consumer in this
  repository (Net-Net, the historical relative-valuation snapshot, `corporate_action_ledger.py`),
  not a one-ticker valuation-lane change; each is reported here as a real finding, not silently
  worked around with a locally-weaker re-verification.
- Every method's `is_actionable` is hardcoded `false` regardless of qualification state, matching
  the newer `current_state_market_risk`/`qualified_market_observations` convention (a descriptive-
  fact signal) rather than `relative_valuation.py`'s own usage of the same field name as a plain
  data-quality flag — a valuation multiple is exactly the number most likely to be misread as an
  actionable signal, so the more conservative, more recent convention was preferred.

## 2026-08-09 - V2 research snapshots preserve the explicit production universe

- The immutable v1 HPG/VNM/VCB contract is not widened or rewritten. V2 has its own semantic
  identity and fixed eleven-ticker production universe; absent entries remain explicit `unknown`,
  never inferred `blocked`. This makes a safe served-baseline adapter necessary before change events.

## 2026-08-09 - Research change events adapt canonical deltas only

- `qualified_research_change_events.py` is a pure adapter over `qualified_research_delta`; it
  neither reads runtime state nor computes financial comparisons. Stable identities bind ticker,
  semantic before/after state, canonical provenance reference, and source/destination snapshots.
  `NO_CHANGE` is explicit and no event carries investment or market semantics.

## 2026-08-09 - QNS OCR is bounded before citation promotion

- The new QNS PDF was rendered with the established local page-preserving Tesseract contract only
  for statement pages 7--10. The result is a hash-bound sidecar, not a financial fact promotion:
  each value still requires exact source-page citation and qualification. Runtime publication is
  deferred rather than allowing OCR output alone to alter product state.

## 2026-08-09 - QNS exact audited consolidated filing is retained separately

- One bounded official `qns.com.vn` financial-reports investigation located the 26-02-2025 issuer
  disclosure and its exact 41-page FY2024 audited consolidated attachment. The PDF is separately
  retained as `faaa54465d1d6a3ca98bebf2a47a45096e21ee6ac3d1cfe3c95db3b1c0bae3e3`; its independent
  audit identifies the consolidated balance sheet, income statement, and cash-flow statement.
- Native text is degraded, so no value was guessed and no financial fact, qualification, research,
  provider, DB, runtime, or publication state changed.

## 2026-08-09 - POW entity identity meets the existing manual-profile authority

- `config/ticker_entity_profiles.csv` is the sole contract permitted to name an issuer type;
  the supported generic non-financial archetype is `corporate`. PV Power's issuer-controlled
  company page (`https://pvpower.vn/vi/page/gioi-thieu-chung`) identifies PetroVietnam Power
  Corporation - JSC, its POW stock code, and its issued shares. Its official FY2024 annual
  report, already issuer-hosted, records power generation and related operating businesses.
  This is sufficient manual verification for `POW,corporate`; no sector/archetype was created.
- The profile changes no document, fact value, citation, debt derivation, qualification rule, or
  market gate. It only permits the existing five qualified annual consolidated facts to pass the
  already-generic corporate research projection. Conflicting entity claims remain fail-closed.

## 2026-08-09 - QNS/POW annual evidence remains fail-closed at package and entity gates

- QNS and POW were the only two artifacts inspected. QNS's retained report is text-bearing but
  its 75th and final page is the financial-statement cover; the three audited consolidated
  statement sections are absent. `ready_for_direct_citations` therefore describes the PDF text
  layer, not adequate metric authority. QNS is blocked as
  `AUDITED_CONSOLIDATED_STATEMENT_SECTION_MISSING` without OCR, new acquisition, or a substitute.
- POW's already-retained audited consolidated filing supplied exactly five FY2024 VND facts from
  visually verified pages 9--12. The existing OCR contract binds each page, engine/version,
  source PDF hash, OCR anchor, displayed label/value, and debt's two explicit borrowing/finance
  lease components. The qualification policy accepted all five; no provider-reported value was
  promoted.
- A five-fact POW preview remains research-blocked at `entity_type_unknown`. The current profile
  authority has no POW classification, and this milestone does not create a ticker whitelist or
  direct status override. Consequently the production eligible count remains five and runtime
  publication is deferred. No DB, provider, market-data, valuation, backtest, or other-ticker
  work changed.

## 2026-08-09 - Issuer filing locators remain a closed, per-ticker acquisition boundary

- The investigation was exactly FPT, POW, and QNS, with one issuer-controlled disclosure route
  and one exact FY2024 audited-consolidated locator per ticker. QNS's issuer-hosted FY2024 annual
  report and POW's issuer-linked audited consolidated PDF were acquired through the existing
  immutable-document contract. POW is enumerated in the acquirer and `pvpower.vn`/`www.pvpower.vn`
  are explicitly admitted because PV Power's disclosure page directly links that PDF.
- QNS is `ready_for_direct_citations` and POW is `needs_ocr`; this decision authorizes neither
  OCR nor fact/metric materialization. FPT's exact link on `fpt.com` returned 404. That terminal
  result is recorded as `ISSUER_FILING_LOCATOR_RETURNED_404`; no guessed variant, mirror, crawl,
  provider fallback, or retry route is authorized.
- No database, runtime artifact, publication, market-data/provider boundary, or other issuer
  changed. This is a completed bounded checkpoint, not selection or commencement of another
  milestone.

## 2026-08-09 - Targeted multi-period official evidence uses a fixed HPG/PVD cohort

- The selected cohort is exactly HPG and PVD: HPG supplies an established issuer-document
  control and PVD exercises the already governed scan/OCR materialization path. It is fixed
  after selection; no fallback ticker, provider financial data, quarterly substitution, or
  broad issuer crawl is authorized by this decision.
- For each ticker, FY2022 and FY2023 use one issuer-owned audited consolidated filing per
  period, retained under the existing source registry and immutable-document manifest. The
  promotion writes exactly five annual identities per filing: operating cash flow, net income,
  cash and equivalents, the explicitly summed short- and long-term borrowing components, and
  shareholders' equity. PVD's USD is retained as reported; no exchange-rate conversion is a
  permissible way to compare absolute values with HPG's VND.
- `qualified_cohort_comparison` is now parameterized by an explicit selected cohort while its
  previous five-ticker cohort remains the default. At least two distinct tickers are required.
  It preserves ticker-local trend availability and descriptive ratio context, but remains
  historical-only, non-actionable, and ranking-prohibited. This lets the Consumer/Dashboard
  receive the bounded pilot rather than silently treating it as an incomplete legacy cohort.
- The canonical-financial bundle flag was deliberately omitted from the final generation after
  its freshness gate required a metadata refresh. That route is unrelated to the issuer filing
  evidence and remains blocked rather than refreshed. No database, market provider, or generic
  price/volume/valuation gate changed. After the supported build and Consumer validation passed,
  the sanctioned trusted-AI publisher released only its four manifest-bound artifacts at serving
  commit `bf00185d78cb79e875b8bba2e17ce0111c966882`.

## 2026-08-09 - Scan-only annual financial evidence is materialized only after source-page verification

- The bounded path is local Tesseract 5.5.0 plus in-memory page rendering for only PNJ and
  PVD. Its durable sidecar keeps PDF page boundaries and derives identity from source hash,
  engine/version, OCR contract, page, and OCR text hash. The source PDF bytes stay immutable.
- OCR text is a locator, never authority. A promoted metric needs exact raw label/value and unit
  in the sidecar plus a recorded visual check of the original consolidated annual page. Numeric
  ambiguity, missing page text, an unverified visual check, source-hash mismatch, or missing
  debt component fails closed.
- PNJ's four direct face-statement values are qualified. Its short-term borrowings are not
  relabelled as total debt because no long-term-loan component appears on the face statement.
  PVD's short- plus long-term loans legitimately sum to its five-metric complete set. The report
  explicitly uses USD; preserving USD is correct, while manufacturing a VND FX conversion is not.
- Existing entity-profile authority identifies PNJ and PVD as corporate when older canonical
  shards lack that field. Research still becomes available only through the unchanged five-metric
  qualification and matrix projection. Thus PVD, not PNJ, transitions to historical-only,
  non-actionable research. FPT was not searched or repaired.

## 2026-08-09 - Bounded official annual-evidence scale-out is materialization-blocked

- PAN's source-authority slice was checkpointed first as `a0759e3`. The bounded cohort then
  considered PNJ, FPT, and PVD only. PNJ and PVD each supplied an issuer-attributed FY2024
  consolidated statement, retained immutably under the governed evidence contract; FPT's exact
  issuer statement URL returned 404 and was not retried through guessed variants.
- PNJ and PVD have no direct text layer. Their visible covers confirm the intended annual,
  consolidated identity (and PVD audit), but no values or citations were inferred. This is an
  evidence-materialization blocker, not a provider fallback or a reason to weaken policy.
- The issuer registry now enumerates PAN's existing storage host and the exact PNJ/FPT/PVD
  issuer-linked hosts. It remains a closed host list. Financial-identity verification also
  rejects cross-ticker artifact reuse. See `annual_financial_evidence_scaleout.md`.

## 2026-08-09 - Canonical annual financial source authority selected

- The authoritative scalable class is issuer IR **audited annual consolidated financial
  statements**, not an exchange notice surface or VCI/KBS numerical response. The bounded PAN
  FY2024 artifact is already hash-retained and carries issuer, publication date, source URL,
  annual/consolidated scope, VND unit, page citation, and extraction metadata.
- Four missing PAN identities were appended through the sole governed evidence writer; the
  pre-existing net-income citation was preserved. The resulting five annual FY2024 facts are
  an ephemeral evidence-to-research projection, not a new store or canonical-shard rewrite.
  PAN becomes the one additional corporate research-eligible ticker; HPG/VNM trusted inputs
  retain precedence. No market-data route or generic market capability changed.
- Future external acquisition is not automatically enabled: the retained PAN provenance host
  is not in the current issuer-IR registry host allowlist. An owner-approved registry route is
  required before re-acquisition or scale-out. See `annual_financial_source_authority_decision.md`.

## 2026-08-09 - Pillar A qualification is evidence promotion, not numerical plausibility

- `canonical_financial_qualification_policy` is the sole read-only promotion contract between
  retained canonical facts and the Pillar A research projection. Qualification requires complete
  semantic identity and period bounds, consolidated scope, provider/source hash/observation
  lineage, a manifest-hash-verified official artifact and deterministic citation, evidenced
  currency/unit, and no unresolved conflict. Agreement, arithmetic, or familiarity alone never
  supplies missing evidence.
- Restatement variants remain `RESTATEMENT_STATE_UNKNOWN` unless retained metadata identifies a
  superseding document, supersession evidence, and its publication date. Ingest time is never a
  supersession rule. Period/scope incompatibilities and arithmetic failures remain independent
  fail-closed reasons. The established FY-to-Q4 alias is retained only for balance-sheet stock
  identities; annual income/cash-flow values are never relabelled as Q4.
- The corporate research gate remains five annual, consolidated, same-period qualified metrics.
  Policy frontier is metadata only: values remain withheld until actually qualified, and trusted
  `financial_canonical` retains strict HPG/VNM precedence. The capability matrix exposes the
  qualification-frontier authority without widening research eligibility.
- Current retained evidence yields 2 qualified facts, 0 safe promotions, and 0 frontier
  facts/tickers. Every canonical fact is quarterly, so no annual corporate lane can be admitted;
  195,550 facts lack a verified citation and 5,306 remain restatement-blocked. The next Pillar A
  decision is `CANONICAL_FINANCIAL_SOURCE_AUTHORITY_DECISION`, not a broad filing crawl or an
  acquisition pilot. DNSE remains a separate `PENDING_OWNER_ACCOUNT_ACTIVATION` market-data
  dependency.

## 2026-08-09 - P1E conflict decomposition is an explanation, not a value-selection authority

- Retained canonical conflicts are decomposed by the existing fact schema and conflict kind.
  The projection preserves period identity, statement and consolidation scope, provider, source
  hash, all available observation IDs, and the original conflict detail. It can label a blocker;
  it cannot select a competing value, average values, infer a unit, or use ingestion time as a
  supersession rule.
- The actual 12,619 records contain only four families: 7,190 cross-statement period/scope
  incompatibilities, 5,306 differing duplicate period columns with no restatement authority,
  120 balance-sheet arithmetic violations, and 3 unreconciled revenue identities. No current
  conflict is duplicate-equivalent, explicitly unit-normalizable, or authority-resolved provider
  disagreement. Therefore every actual conflict remains blocked and
  `AUTO_RESOLVED_CONFLICTS = 0`.
- The canonical fact status is not promoted by conflict explanation. In particular,
  `provider_reported` remains provider-reported and a later restatement cannot appear in an
  earlier as-of view without an explicit retained supersession contract. Matrix reason codes are
  additive diagnostics only; generic market gates and trusted HPG/VNM research authority remain
  unchanged.

## 2026-08-09 - P1.5 capability matrix is a projection, not a new gate

- `ticker_capability_matrix` is the canonical per-ticker integration surface for existing
  Producer decisions. It carries lane-specific status, original authority status, retained
  reason codes, authority, trust tier, descriptive-only marker, dependencies, and an always
  false actionable flag. It does not calculate financial quality, market basis, liquidity,
  research eligibility, or portfolio eligibility.
- Provider-scoped adjusted market observations and generic actionable market claims stay in
  different namespaces. An `available` provider observation is rendered `descriptive_only`;
  it cannot unlock raw/as-traded price, current market cap/valuation, generic liquidity,
  tradability, sizing, execution, or backtesting. Absence or malformed upstream contracts fail
  closed as explicit `unavailable`/`unknown` records.
- The production cohort is exactly `POW, SSI, HPG, EVF, PAN, PNJ, FPT, QNS, VNM, PVD, NVL`;
  VCB remains a test-only archetype example. The FiinGroup authority stays
  `WAITING_EXTERNAL_ACCESS`, `OWNER_ACQUISITION_REQUIRED`, and
  `OWNER_CONFIRMATION_REQUIRED`. No source acquisition, adapter, runtime/DB mutation, or
  publication is implied by this decision.

## 2026-08-09 - Pillar A reaches research through a qualification-aware projection

- `research_financial_fact_projection.py` is the only new integration seam. It reads existing
  canonical shards and projects their exact status, period identity, source/provider, hashes,
  observation IDs, and any citation/evidence IDs. It does not create a persistent financial
  store, resolve facts again, substitute periods, average conflicts, or turn null into zero.
- Existing trusted `financial_canonical` has strict precedence. Pillar A can be selected only
  for a supported corporate entity with one same-period, consolidated, fully-qualified set of
  operating cash flow, net income, cash, total interest-bearing debt, and shareholders equity,
  plus explicit citation/evidence/observation lineage. `provider_reported` stays non-research;
  conflicts, missing inputs, unknown entities, and unsupported archetypes fail closed.
- The actual retained store contains 1,493 tickers / 195,552 facts but only two qualified facts,
  neither a complete existing research set. Therefore the safe additional eligibility result is
  zero. HPG/VNM retain their trusted-lane behavior; no market gate or recommendation boundary
  changed.
- DNSE OpenAPI is documented as `PENDING_OWNER_ACCOUNT_ACTIVATION` for a future bounded HPG/VNM
  qualification pilot. It is not an active authority and has no market-basis effect. FiinGroup
  remains the fallback candidate; no provider was called in this decision.

## 2026-08-08 - Publish Orchestrator Authority Reconciliation

- **`tools/release_orchestrator.py` is the single supported live-publish authority**, for
  both release groups (`trusted-ai`, `whole-market`, `all`). `tools/operate_stocklookup.py`
  remains fully supported as the build/generate + validate command for the trusted-ai
  analysis artifact set (taxonomy sidecar, bundle, manifest), standalone or as
  `release_orchestrator.py ... --generate`'s own child process. Its own `--live` flag is
  retired: passing it now exits 2 with a message pointing here, so exactly one command in
  the repository can commit or push. `local_runbook.md` and
  `docs/release_publication_contract.md` previously named only `operate_stocklookup.py` as
  "the one supported command" — both predated `release_orchestrator.py` (added 2026-08-05,
  `cb0cd75`) and were never updated; this entry and the accompanying doc updates close that
  gap. See `operations-review/runtime_pipeline_publish_contract_audit_20260808.md` for the
  audit that first surfaced the conflict.

- **The deciding fact, not age or naming: both orchestrators already delegate the actual
  trusted-ai publish to the same `tools/publish_release.py`.** There was never a second
  publish *implementation* to choose between — only a second *dispatcher* deciding when to
  call it, and a generation stage deciding what to call it with. `release_orchestrator.py`
  already dispatches both release groups and is what the deprecated `.bat` shims already
  forward to; `operate_stocklookup.py` structurally only ever reaches the trusted-ai group
  (its own docstring: "never fetches prices, macro series or news... consumes what \[the
  daily chain\] already produced") and has no whole-market or Dashboard-repo-git-safety
  capability to build on. Making it the outer authority would have meant growing a release-
  group dispatcher and HEAD/upstream/staged-index checks it was never designed to have;
  making `release_orchestrator.py` call it for generation only needed one child-process
  call it already had the shape for (it already shells out to `publish_release.py`,
  `build_frontend.py`, `publish_dashboard.py` the same way).

- **Composition, not duplication: `--generate` runs the loser as a plain, non-publishing
  child process.** `release_orchestrator.py trusted-ai/all --generate` calls
  `operate_stocklookup.py --runtime-root <backend-dir>` (adding `--execute` only when the
  outer run is itself `--live`, so a dry-run orchestration can't quietly write real files)
  before its own existing plans — never with `--publish`/`--live`, so the child can only
  build and validate, never publish. The existing per-child failure check
  (`if res.returncode != 0: ... return res.returncode`) already stops the loop before
  `publish_release.py` runs if the generate stage fails; no new failure-propagation logic
  was needed. Zero lines of either script's core logic were copied into the other.

- **One capability actually moved, and one had to be explicitly carried over.**
  `operate_stocklookup.py`'s live path ran a `post_publish_smoke` gate whose live-only
  block re-hashed the served checkout against the runtime root from a second process —
  accepted as retired-by-redundancy: `publish_release.py` already re-hashes its own
  promotion (`os.replace` then re-hash) and already verifies the pushed remote SHA via
  `git ls-remote`, so this was a second confirmation of a check the publisher already makes
  atomically, not independent coverage. `--verify-live-url` (an HTTP re-fetch from the
  actual serving origin — genuinely independent of anything `publish_release.py` checks
  about its own local git state) was **not** redundant and had no equivalent on
  `release_orchestrator.py` before this milestone; it is now a pass-through flag there,
  forwarded to `publish_release.py` exactly as `operate_stocklookup.py` used to forward it.

- **Every other named safety property was preserved as-is, not reimplemented.** Expected-
  session gating, the single-instance lock, the Dashboard HEAD/upstream/staged-index
  checks, the whole-market allowlist rollback, and the trusted-ai release allowlist/hash/
  Consumer-validation/atomic-promotion contract in `publish_release.py` are unchanged by
  this milestone — confirmed by the existing focused suites passing unmodified alongside
  the new composition tests (`tests/test_release_orchestrator.py`,
  `tests/test_operate_stocklookup.py`).

- **`tests/test_release_orchestrator.py` no longer depends on the live runtime.** Every
  test there previously ran against the real `dashboard-runtime`/
  `worktrees/market-dashboard-main` by default, including one that hardcoded the expected
  session as `"2026-08-04"` — confirmed failing this session (`dashboard-runtime` had moved
  to session `2026-08-07`), exactly the drift the milestone brief warned against "fixing"
  by swapping in the new current date. Rewritten to build its own temp `--backend-dir`
  (a minimal `screen_snapshot.csv`) and `--web-dir` (a freshly `git init`ed repo) per test,
  so the suite's pass/fail no longer depends on which day it runs.

- Evidence: this milestone's diff (`tools/release_orchestrator.py`,
  `tools/operate_stocklookup.py`, both test files, this entry,
  `docs/release_publication_contract.md`, `operations-review/local_runbook.md`,
  `operations-review/PROJECT_STATE.md`). No production write, no publish, no push.

## 2026-08-04 - P0-Z.3 KBS Coverage Export Seam and Consumer Pass-Through

- **KBS `va` has never been exported, and that is now recorded rather than assumed.** The
  trace: `vnstock` drops `va` unless `get_all=True`; the `ohlcv` table has no value column;
  `export_ai_bundle` contains no trading-value reference; `analysis_bundle.json`
  `ohlcv_recent` rows carry `{date,open,high,low,close,volume}`. There is therefore no bare
  KBS trading value crossing the boundary and nothing to retrofit.
  `ABSENCE_OF_ACTIVE_VALUE_PATH` holds the trace so the next reader does not repeat it.

- **Two errors in the `ee057b9` closeout, both found by tracing instead of assuming.** It
  stated that no existing consumer creates a price-times-volume field — false:
  `candlestick_patterns.py:148` computes `gtgd20_ty`, a 20-session rolling mean of
  `close * volume` in billion VND that reaches `stock_analyzer`, `candle_scan`,
  `ai_analyzer` and the Consumer schema registry. And its `CONSUMER_REQUIREMENTS` named four
  `va` consumers, none of which read `va`; `stock_analyzer.turnover_features` and
  `export_ai_bundle.trading_value_passthrough` do not exist at all. The register now holds
  only the forbidden uses, and a future entry has to be justified by a trace.

- **`gtgd20_ty` is relabelled, not disabled.** It reconstructs no missing `va`, predates this
  lane, and its volume side is already classified in `market_volume_capability_matrix` as
  analytical and explicitly not qualified liquidity. `NON_VA_DERIVED_QUANTITIES` records the
  expression, that it reads no `va`, and the three labels it may never carry. Deleting a
  working screen over a naming collision would not have been proportionate.

- **The seam is built now because the cheap moment is before the first caller.** Once a bare
  number is in a schema, every consumer of it becomes a migration.
  `kbs_trading_value_export.py` costs nothing while `ACTIVE_EXPORT_PATH` is `None` and is
  already in place the day someone flips `get_all=True`. It adds no bundle section and
  populates no field with nulls.

- **Labels are validated against counts on both sides.** `assert_block_valid` and the
  Consumer's `assert_labels_agree_with_counts` both refuse `complete` beside fewer usable
  rows than requested, `partial_known` with none or all rows usable, and
  `complete_requested_window` scope on non-complete coverage. Every individual field can be
  well-formed while the block as a whole lies; that is the check that catches it.

- **Consumer passes through and never improves.** All 20 coverage fields copied verbatim,
  nothing recomputed, a dropped field is an error, coverage may be narrowed but never
  widened, and the authority and partial warnings cannot be removed. Consumer holds no copy
  of Producer's capability matrix — Producer keeps authority.

- **One warning source, pinned across repositories.** Two tokens, one text table, a SHA-256
  fingerprint asserted from a frozen fixture that is byte-identical in both trees. A
  Producer edit that is not mirrored fails a Consumer test rather than shipping two
  different sentences for the same condition.

- **Absence of metadata never means complete.** All three legacy classes resolve to
  `coverage_state = unknown`. A legacy row observation with explicit row identity stays
  displayable with a provenance warning; a legacy value without row identity or coverage is
  refused outright.

- **No schema bumped.** The block is additive and no artifact contains one, so nothing a
  current reader parses changes. `compatibility()` states the forward behaviour explicitly:
  a reader without the block treats KBS trading value as `unknown` and refuses aggregates.

- **Non-effects.** No network request. No production write or publication. All descriptive
  and technical capabilities preserved. `volume_market_scope` `unknown`,
  `liquidity_actionable` false, `is_actionable` unchanged. 561 tests passing across both
  repositories.

- Evidence: `operations-review/kbs-coverage-pass-through-20260804/`.
  `KBS_COVERAGE_PASS_THROUGH: PASS`.

## 2026-08-04 - P0-Z.2 KBS Trading-Value Coverage and Safe Aggregation
> **PARTIALLY CORRECTED 2026-08-04 by P0-Z.3.** The coverage model, states, gates and
> inventory all stand. Two claims do not: "no existing consumer creates such a field" was
> false, and the `va` consumer register listed four consumers that read no `va`. See the
> P0-Z.3 entry above.

- **Coverage became an input instead of a warning.** `va` is present on 38 of 66 retained
  sessions. A period total over those 38 rows looks exactly like a complete one — same type,
  same order of magnitude, nothing in the output marking the difference. So a whole-window
  claim now requires `coverage_state = complete`, and one that cannot get it must rename
  itself: `statistic_scope = observed_rows_only`, `not_comparable_to_complete_period_total`,
  covered and excluded sessions enumerated. `build_result` is the only constructor, so the
  number and its metadata are produced in one call.

- **The relabelling that matters is blocked by arithmetic.** Flipping `coverage_state` to
  `complete` *and* `statistic_scope` to `complete_window` together passed every individual
  field check. `assert_result_labelled` now validates the claimed state against the counts
  the result carries: 2 covered of 3 requested cannot call itself complete, and a complete
  result cannot carry excluded sessions.

- **Two parser defects, found by trying to build the inventory.** `field_omitted` and
  `present_null` both went through `item.get("va")` to `None`, so the two were
  indistinguishable — and a malformed `va` aborted an entire payload whose OHLC was
  perfectly good. The state is now decided first and the value read from it. Four kinds of
  "no number" stay apart: omitted, null, zero, malformed; plus `row_missing` for a session
  absent from the response.

- **A real zero is usable.** `present_zero` counts toward coverage. A session that traded
  nothing is a measurement, and excluding it would bias every mean upward while looking like
  prudence.

- **Normalized absence is not provider absence.** The `vnstock` adapter drops `va` for every
  row regardless of what KBS sent, so a missing normalized field is evidence about our
  configuration. `normalized_field_present` is carried separately and never merged with the
  raw state.

- **No synthesis, and nothing to disable.** `automatic_imputation_authorized` and
  `missing_as_zero_authorized` are constants with no input that flips them.
  `kbs.reconstructed_price_times_volume` is reserved, unimplemented and unauthorized: on
  exactly the rows where `va` is absent the retained price is an *empirically adjusted*
  price, so price × volume there is the product of a number the provider restated and one it
  did not. No existing consumer creates such a field, so nothing had to be relabelled. The
  unit work proved `va / v` lands in the session range — that validated the unit and is not
  a licence to run the identity backwards.

- **The 66/66 correlation is an association, not a mechanism.** `va` absence coincides
  exactly with the empirically adjusted / off-lattice row group across all retained windows,
  with zero exceptions. Recorded as `observed_association =
  va_missing_on_tested_empirically_adjusted_rows`, `causal_explanation = unknown`,
  `coverage_generalization = limited_to_retained_windows`. Nothing observed distinguishes a
  provider that removes `va` when it adjusts from two fields sourced independently that
  happen to align. Three active-source phrasings corrected; the frozen artifacts keep their
  wording and the correction is recorded in `CORRECTED_CAUSAL_FRAMING`; the audit re-runs as
  a standing test over active source.

- **Non-effects.** No network request. No production write or publication. All 15
  descriptive and technical capabilities remain available — an incomplete field is a reason
  to label a statistic, not to close a chart. `volume_market_scope` stays `unknown`,
  `liquidity_actionable` false, `is_actionable` unchanged. The `800c746` price, unit and
  mutability contract is preserved; the prospective mutability protocol is unmodified.

- Evidence: `operations-review/kbs-trading-value-coverage-20260804/`.
  `KBS_TRADING_VALUE_COVERAGE: PASS`.

## 2026-08-04 - P0-Z.1 KBS Empirical Closeout and Prospective Mutability Protocol

- **A post-event snapshot is not a substitute for a pre-event one, at any interval.** The
  P0-Z closing report recommended re-requesting the HPG 2026-05-18..06-02 window "after
  enough elapsed time" to settle whether KBS rewrites history at a corporate action. That
  is wrong. The earliest retained KBS payload for that window is 2026-08-04 and the
  ex-right date is 2026-05-25: whatever the provider did at the event, it had already done
  it before the first observation. A second request — tomorrow or in a year — is another
  post-event snapshot and can measure only post-event stability. Recorded as
  `kbs_mutability_protocol.SUPERSEDED_RECOMMENDATION`, root cause
  `post_event_snapshot_treated_as_a_substitute_for_a_pre_event_snapshot`.

- **The three mutability questions are separated in the contract, not just in prose.**
  *Event-time historical rewriting* is `not_testable_from_retained_pairs`; *post-event
  snapshot stability* is `observed_for_tested_retrieval_interval` (9 sessions, 2026-08-01 →
  2026-08-04, no change); *volume corporate-action adjustment* stays `not_observed`.
  `classify_snapshot_pair` returns `both_post_event` for the retained pair and
  `historical_rewrite_test` then reports `not_testable_from_this_pair` however clean the
  diff is. `contract_historical_mutability` derives the contract field from the event-time
  question alone, so stability can never feed it.

- **A fixed defect: a post-event revision could have been read as an event adjustment.**
  `volume_adjustment_verdict` checked "did the volume change" before checking whether the
  pair straddled a share event, so a changed volume in a non-straddling pair returned
  `retrospectively_rewritten_unknown_method`. The pair-class gate now comes first and the
  caller's own `share_event_window_tested` claim cannot override it — neither a changed nor
  an unchanged volume qualifies from a pair that does not straddle a share event.

- **The framing correction is recorded against the frozen report, which is not edited.**
  `CORRECTED_FRAMING` names the artifact, the sections, the misleading implication ("spans
  no qualified share event" reads as a choice of window) and the correction, with
  `measurements_changed: false` and `artifact_rewritten: false`. Every measurement in the
  P0-Z report stands.

- **The absolute unit anchor is re-grounded on stronger, independent evidence.** The VWAP
  identity only ever constrained the scale *quotient*. The absolute scale now rests
  primarily on `numeric_identity_with_an_independently_unit_qualified_series`: KBS returns
  integers exactly equal to stored VCI volumes on 34 sessions across all three tickers, and
  VCI's unit was established from its own per-trade tape rather than a plausibility bound,
  so equality is arithmetically impossible under a thousand-fold difference. It transfers
  **magnitude only** — `assert_identity_anchor_is_magnitude_only` refuses an anchor carrying
  market scope, composition or source authority, so this is not the cross-provider authority
  upgrade the ladder forbids. The issued-share-count falsifier (27,485,500,000 implied vs
  8,442,964,520 retained, rejected with a 1.63× margin) is retained as the corroborating
  route, still `observed_only`, still `unit_anchor_admissible_for_valuation = False`. Units
  remain `shares`/`VND` at `empirically_deduced`; neither route can reach
  `documented_verified`, and without either the result degrades to `scaled_units` at
  `observed_only` with `absolute_scale = unresolved`.

- **The prospective protocol is designed and inert.** `kbs_mutability_protocol.py`: 16
  required pre-event manifest fields, a strictly-before-ex-date check that refuses a
  same-day snapshot, identical-request enforcement, 8 compared fields including row presence
  and schema, a mandatory control whose own movement yields `comparison_conflicted`, 5
  separated change classes, 7 scoped verdicts, and deterministic phase-bearing artifact
  paths. `network_access_authorized`, `scheduling_authorized`, `event_polling_authorized`
  and `automatic_acquisition_authorized` are all false and asserted; the test checks the
  module's parsed import graph rather than scanning its prose, which is *about* networks and
  schedules. Owner authorisation is required per event.

- **Non-effects.** No network request of any kind in this milestone. No production database
  write, bundle or dashboard publication, ranking, recommendation, sizing, liquidity output,
  point-in-time valuation or backtest change. All 15 descriptive/technical capabilities
  remain available and all 13 liquidity/execution/point-in-time capabilities remain
  `unavailable_by_contract`. `is_actionable` unchanged. The VCI verdict is untouched.

- Evidence: `operations-review/kbs-empirical-closeout-20260804/`. Contract:
  `docs/kbs_empirical_basis_qualification.md`. `KBS_EMPIRICAL_CLOSEOUT: PASS`.

## 2026-08-04 - P0-Z KBS Empirical Basis and Capability Relaxation
> **PARTIALLY CORRECTED 2026-08-04 by P0-Z.1.** Every measurement below stands. Two things
> are corrected: the mutability gloss ("the only as-of pair spans no share event") implies a
> better window would have answered the event-time question, when in fact both retrievals
> post-date every candidate event; and the absolute unit anchor is re-grounded on numeric
> identity with an independently unit-qualified series, with the share-count falsifier
> demoted to corroboration. See the P0-Z.1 entry above.

- **A canonical qualification ladder now sits between "documented" and "unknown."**
  `evidence_qualification_tiers.py`: `documented_verified` / `empirically_deduced` /
  `observed_only` / `unknown` / `conflicted` / `invalidated`. Only `documented_verified`
  may claim the source's own semantics. `empirically_deduced` requires all 13 retention
  fields (method, fields, tickers, windows, event evidence, artifact hashes, transformation
  version, alternatives, falsifications, confidence, scope limits, retrieval timestamps,
  mutability) and refuses empty alternatives or falsification lists — claiming the tier is
  deliberately more work than claiming `unknown`. Recency never resolves a conflict; a
  `supersede()` that states what the prior verdict was right about does.

- **The Phase 1C KBS finding is re-confirmed; only its inference is superseded.** Six fresh
  payloads carry `t/o/h/l/c/va/v` and no semantic metadata whatsoever — exactly as Phase 1C
  reported. What does not follow is that the fields are unusable. Retained in
  `provider_price_basis_registry._SUPERSEDED` as `phase1c_kbs_fields_unusable`, root cause
  `absence_of_documentation_treated_as_absence_of_usable_data`, narrowed to
  `documented_semantics=absent; field_identity=qualified; empirical_semantics=partially_available;
  descriptive_capability=available; technical_capability=provider_scoped_available;
  liquidity_capability=unavailable`. The Phase 1C report is not edited or deleted.

- **KBS prices are event-adjusted, on two independent signals.** Pre-event sessions sit off
  the HOSE tick lattice — so they were never matched order prices — and the off-lattice
  prefix terminates exactly at a qualified ex-right date in three windows across three
  tickers. Separately, the provider omits `va` over exactly the off-lattice runs and emits
  it over exactly the on-lattice ones, 66 of 66 sessions. That second signal also kills the
  retention hypothesis: HPG 2026-07-20..30 carries `va` while the later-dated VCB
  2026-07-16..17 does not, so presence tracks the boundary and not the calendar.
  `provider_methodology` stays `unknown` and `coverage_generalization` is
  `limited_to_tested_windows`.

- **The VWAP identity earns a quotient, not two scales — and this is enforced, not just
  noted.** `(1,1)` and `(1000,1000)` predict identical implied prices for every session that
  will ever exist. The quotient (1.0) comes from 36 discriminating rows over 3 tickers and 3
  price levels with all 14 competing quotients rejected; the absolute anchor comes from a
  retained issued-share count used strictly as an order-of-magnitude falsifier — `(1000,1000)`
  implies HPG trading 27.5bn shares against 8.44bn issued. Without that anchor the units
  report `scaled_units` at `observed_only`. The share count is **not** qualified for
  valuation and is not qualified here; the argument survives it being wrong by any factor
  short of the one it rejects.

- **A row no candidate scale explains is a contradiction, not a failure.** Such a row
  rejects all sixteen candidates identically, so it votes on nothing. Two of 38 eligible
  rows (5.26%, under a 10% ceiling) are retained verbatim with their alternative
  explanations: HPG 2026-06-01 carries a `va` byte-identical to 2026-06-02's, and VNM
  2026-07-31 is unresolved. Above the ceiling the whole relationship reports `conflicted`.

- **Volume adjustment is never inferred from price adjustment.** `volume_adjustment_verdict`
  accepts the price verdict solely so the refusal is explicit. Verdict is `not_observed`:
  the only as-of pair spans no share event. A separate result was obtained and is not the
  same claim — on the 13 VCB sessions the VCI lane proved were rewritten, KBS closes match
  the stored pre-event rows 0/13 while KBS volumes match them 13/13, so within one provider
  the two fields are restated on different schedules.

- **Market scope stays entirely unknown, and the bar for changing that is written down.**
  Six dimensions, all `unknown`. An upgrade needs ≥2 admissible independent observations
  (retained official exchange total, separately labelled provider fields with a demonstrated
  relationship, complete intraday reconciliation, or another reproducible independent
  observation) each with all six confounders eliminated. Secondary financial websites and
  media reports are counted and can never qualify a dimension.
  `assert_unit_does_not_qualify_scope` raises if a unit result tries to set a scope.

- **Capability relaxation, not capability activation.** `kbs_capability_matrix.py`:
  15 descriptive/technical capabilities available under 7 mandatory warnings and 7
  provenance fields; 2 conditional behind `return_type = provider_series_return`, with
  `raw_as_traded_return` / `official_exchange_return` / `total_shareholder_return` raising
  rather than returning unavailable; shadow-backtest eligibility defined across 8 conditions
  and **not implemented**; 13 liquidity, execution and point-in-time capabilities
  `unavailable_by_contract` — terminal, with no field a caller can set. 20 consumers
  classified; an unregistered consumer or capability fails closed.

- **Non-effects.** No production database write, no bundle or dashboard publication, no
  change to rankings, recommendations, sizing, liquidity outputs, point-in-time valuation or
  production backtesting. `is_actionable` unchanged; `liquidity_actionable = false`. The VCI
  verdict is untouched and neither verdict inherits the other.

- Evidence: `operations-review/kbs-empirical-basis-20260804/` (report, `basis_summary.json`,
  `capability_matrix.json`, `evidence_manifest.json`, six hash-addressed raw payloads).
  Contract: `docs/kbs_empirical_basis_qualification.md`. `KBS_EMPIRICAL_BASIS: PARTIAL`.

## 2026-08-03 - P1J Provider-Reported Share Authority Hardening
> **SUPERSEDED 2026-08-03 by P1J.1.** The grounding line below is wrong: VCB's official anchor
> is `5,589,091,262`, not `5,589,091,222`; HPG's provider value is `8,442,964,520`, not
> `6,396,250,200`; and `7,163,748,865` appears in no citation and no ledger. The counts were
> literals in `tools/operate_stocklookup.py`, not measurements. Measured `qualified_official`
> is **0**. See "Official share anchors are read from the citation store" below.
- Field provenance proven: `vn_stock.db → metadata.shares_outstanding` is populated from `Company(source="VCI", symbol=tk).overview()` raw field `issue_share` (`ISSUED_SHARES`).
- Grounded against official anchors: VNM (exact match `2,089,955,445`), VCB (exact match `5,589,091,222`), HPG (provider `6,396,250,200` vs official `7,163,748,865` post-stock-dividend).
- Corporate-action invalidation: provider observations pre-dating a completed share-changing corporate event (e.g. stock dividend) are invalidated as `provider_reported_stale` (2 tickers).
- Hardened authority counts: 1,683 active universe (3 qualified official, 1,677 provider-reported current, 2 provider-reported stale, 1 unavailable). Valuation readiness recalculated fail-closed: Market Cap (3 qualified + 1,471 provider-reported), P/E (1,391), P/B (1,289), EV (1,247), EV/EBITDA (111).

## 2026-08-03 - P1I Market-Wide Current Shares Coverage
> **SUPERSEDED 2026-08-03 by P1J.1.** Every count in this entry was a literal, including the
> valuation-readiness figures, which no run has ever computed.
- Market-wide effective shares are resolved across the active universe (1,683 tickers) into 3 explicit authority lanes: `qualified_official` (3 tickers), `provider_reported` (1,679 tickers), and `unavailable` (1 ticker).
- Provider-reported current share observations from retained metadata are preserved as `provider_reported` and never relabelled as qualified.
- Reconstructed current market cap and valuation readiness projections expand fail-closed: Market Cap (3 qualified + 1,473 provider-reported across 1,493 canonical fact tickers), P/E (1,393 ready), P/B (1,291 ready), EV (1,249 ready), EV/EBITDA (111 ready).
- Producer section export and Consumer context pass-through preserve exact authority levels verbatim without recomputation. Top-level operator reports full market-wide coverage. Production hashes remain 100% byte-identical.

## 2026-08-03 - P1H Current Share Basis and Valuation Readiness Activation
> **SUPERSEDED 2026-08-03 by P1J.1.** Three claims here do not hold. The three "qualified"
> current share counts came from a hardcoded table, two of whose entries were wrong, and none
> of the three retained anchors can be promoted from an FY2024 period-end figure to a current
> one — measured `qualified_official` is **0**. The session price was read as the ticker's
> newest close, not the session's. And a market cap took its status from the share leg alone,
> so it could read `qualified` on an unverified price basis.
- Current effective shares are resolved by authority order: qualified official shares fact on/before session, qualified corporate-action transition, or repo-governed share basis. Never backsolved from market cap or inferred from raw labels.
- Session price input uses existing session close from `vn_stock.db` / snapshot, explicitly labelled as `current_snapshot` without claiming historical price-series adjustment or backtesting eligibility.
- Reconstructed current market capitalization (`resolved_session_price * current_effective_shares`) unblocks P/E, P/B, EV, and EV/EBITDA readiness fail-closed (3 qualified current shares, 3 reconstructed market cap, 3 P/E ready, 3 P/B ready, 2 EV ready, 2 EV/EBITDA ready, with banking templates correctly `not_applicable`).
- Final valuation readiness projections pass through Consumer context verbatim and land in `tools/operate_stocklookup.py` summary report. Baseline production hashes remain strictly unchanged.

## 2026-08-03 - P1G Data Authority and Post-Close Closeout
- Owner approved activation of existing declared official sources in `config/official_source_registry.json`: HOSE, HNX, VSDC, and qualified issuer IR hosts (`file.hoaphat.com.vn`, `www.vinamilk.com.vn`, etc.).
- Broad discovery, undeclared hosts, and paid providers (EODHD) remain strictly prohibited and fail closed.
- Bounded document store retention, corporate-action event ledger reconciliation (9 event types, explicit lifecycle, strict ex-date requirement for factors), dated shares timeline, and valuation readiness (distinguishing current vs historical market cap and EV/P-E/P-B/EV-EBITDA readiness) land cleanly in the Producer.
- Consumer context `ai-core-private/builders/build_ticker_context.py` passes through all canonical facts and readiness verbatim without recomputation.
- Top-level operator `tools/operate_stocklookup.py` includes canonical financial facts and completes full 18-stage local post-close dry run cleanly. Baseline production hashes remain strictly unchanged.

## 2026-08-03 - P1F Canonical Financial Production Activation
- Canonical financial export is connected through `--include-canonical-financial-facts` on `export_ai_bundle.py` and top-level operator `tools/operate_stocklookup.py`.
- Consumer context `ai-core-private/builders/build_ticker_context.py` passes through `canonical_financial_facts` verbatim without recalculation.
- Default Producer bundle remains byte-identical when flag is disabled.
- Full local post-close dry run verified through `python tools/operate_stocklookup.py --runtime-root <path> --include-canonical-financial-facts`.

## 2026-08-03 - `provider_reported` is the honest ceiling; a convention is not evidence
- Layer 3 emits `qualified` only where a value agrees digit-for-digit with an independently promoted official citation, which is the only place a currency and an absolute unit scale are actually evidenced. Everything else that resolves cleanly is `provider_reported`.
- The retained payloads carry no currency column, no unit header and no internal anchor fixing the absolute unit. Vietnamese listed issuers do file in VND under VAS; that is a convention, not evidence in these bytes, and promoting it would make the qualification contract meaningless everywhere else.
- The consequence is 2 qualified facts market-wide (HPG and VNM `retained_earnings` 2024-Q4) against 93,749 `provider_reported`. That is reported as a citation-coverage gap, not papered over. A status is never upgraded because a normalized label matched.
- An annual official citation is additionally keyed to `YYYY-Q4` for **stock** metrics only: a balance sheet dated 31 December is both the FY year-end and the Q4 period end. The alias is never emitted for a flow metric, because FY revenue is not Q4 revenue.

## 2026-08-03 - Dialect is a property of the vocabulary, not of the `source` column
- `docs/market_wide_financial_normalization_contract.md` describes the split as two providers with two vocabularies, which reads as though `source` selects the dialect. It does not: HPG's income statement carries `source = KBS` and the full VCI vocabulary. Keying the mapping on the provider string drops every metric on that payload.
- Candidate matching therefore keys on the raw item id, which is what actually discriminates, and `detect_dialect()` reports the dialect a payload's vocabulary evidences so the coverage report can still break every metric down by dialect and make a single-dialect regression visible.
- A canonical metric's candidates may live on a different statement from the metric's declared home (`interest_expense` prefers the income statement and falls back to a cash-flow add-back), and the fallback is admitted only as a `substitute`, forcing `partial`.

## 2026-08-03 - Cash-flow period labels are gated, not trusted
- HPG's cash-flow payload column labelled `2025-Q2` carries an end-of-period cash balance that matches the **2026-Q1** balance sheet. The label does not identify the period the numbers describe.
- End-of-period cash is the only cross-check the retained payloads offer between a balance sheet and a cash-flow statement, so it is a period-attribution gate: `divergent` makes every cash-flow fact for that period `conflicted`; an unavailable check caps them at `partial`. It diverges for 314 of 678 sampled ticker-periods.
- Without this gate a depreciation figure from one quarter would silently be added to a profit figure from another inside EBITDA. This is why EBITDA is ready for 231 tickers rather than for every ticker whose raw identities are present.
- The retained store is capped at 8 quarterly periods per ticker by the provider's community tier, and carries no annual periods at all. Annual figures cannot be read from it.

## 2026-08-03 - The source registry gates the network, not a comment
- `config/official_source_registry.json` is the pillar B step B1 artifact. Every source ships `declared`, `approval_state` is `AWAITING_OWNER_APPROVAL`, and `official_source_registry.admit()` refuses a source that is not `approved`. The reviewable JSON is therefore the thing that actually prevents an outward request.
- **An agent may not set `activation` to `approved`.** That is an owner decision, recorded here and in the registry. B2-B6 may not begin until it is taken.
- Host matching is exact after lower-casing and port-stripping, never suffix matching: `evil-hnx.vn` passes a naive suffix test, and an allowlist defeated by registering a domain is not one.
- Issuer IR hosts are admitted only where a retained official citation already evidences them, extending the 2026-08-02 bounded official-event locator rule. EODHD is recorded inside the registry as `REJECTED_BY_OWNER` and excluded.

## 2026-08-03 - No date substitutes for an official ex-date, and OCR damage is refused
- A price-adjustment factor places an event on the price timeline and requires an explicit official ex-date. The existing rule that a record date never substitutes for one now extends to payment, listing and trading dates. The HPG slice's event is complete, executed and fully cited, and its factor is `not_ready` for exactly this reason.
- Factors derived from this ledger carry `authority_state = outside_production_authority`, and the ledger never writes to `data/official-evidence/`; `evidence_promotion.py` remains the only evidence write boundary.
- A document class caps the lifecycle state it may assert: a board resolution or AGM plan can reach `approved` and never `executed`.
- Numbers are not read from a damaged scan. The retained HPG issuer notice extracts its post-change share count as `8.M2.964.520`, which tokenises to `2.964.520` — a value that parses cleanly and lies inside any plausible share range, so no bounds check catches it. Positional column reading is used only when the form's own column headers survive in order **and** two labelled rows agree, and the row arithmetic `before + change = after` must hold. Otherwise the document contributes no share count at all.

## 2026-08-03 - Layer 3 enters the bundle additively, disabled by default
- `--include-canonical-financial-facts` follows the Phase 5A/6A opt-in precedent exactly: with the flag unset nothing is read and no key is added, so the default bundle — and the exact-session proof that hash-binds it — is unchanged. Verified by an exact artifact diff: the Producer carrying this milestone, with the flag off and the production ticker set and flags, reproduces the shipped `analysis_bundle.json`, `focus_extract.json` and `bundle_manifest.json` content-identically, differing only in the documented clock fields.
- A metric crosses the boundary only with its status, provenance, period, scope, unit, basis and limitations. **`conflicted` and `unavailable` facts cross as status and reason with `value: null` and `value_withheld: true`**, because a consumer that sees a number will eventually use it. Raw observations never cross; only `source_observation_ids` pointers do.
- No ranking, no score, no whole-market ordering, and no change to `is_actionable`.
- A mapping change must move `MAPPER_VERSION`. The incremental fingerprint covers it, and a mapper edited without bumping it left the store reporting `rebuilt: 0, unchanged: 1493` while serving facts built by code that no longer existed.

## 2026-08-02 — Approved evidence write boundary (P0.2)
- `evidence_promotion.py` (Producer, source-controlled) is the sole module authorized to append records into `<runtime_root>/data/official-evidence/manifest.json` and its `*_citations.jsonl` sidecars. No other module, script, or hand-edit may write to those files.
- Every write is append-only and idempotent: manifest records are deduped by `evidence_id`, citation records by `citation_id`. Nothing is ever edited, reordered, or deleted; a correction is a new row using the existing `supersedes_citation_ids` field already read by `semantic_evidence_bridge.py`.
- Every promotion hash-verifies its referenced evidence document live, at write time, against the `sha256` being recorded; a mismatch raises and blocks the write.
- Evidence may be retained outside `<runtime_root>/data/official-evidence/` (for example under a Producer `operations-review/` staging path) and referenced via `archive_document_path`. This is not a new pattern: the production manifest's VCB annual-report record already does this, pointing at `operations-review/evidence/...`. `evidence_promotion.py` formalizes and generalizes that precedent instead of requiring binary evidence files to be copied into the runtime tree.
- This boundary does not authorize writes to `vn_stock.db`, `analysis_bundle.json`, `bundle_manifest.json`, or `focus_extract.json`; those remain the pinned, hash-locked production artifacts and are untouched by any promotion.
- This resolves, for future evidence with equivalent merit, the class of blocker recorded at Phase 5E (`EVIDENCE_STORAGE_BOUNDARY_BLOCKER`, VNM cash-distribution evidence) and Phase 6D/6E (HPG FY2024 identity citations): evidence quality was never the blocker, the absence of an approved write path was.

## 2026-08-02 — Exposed credentials are invalid for qualification
- Any provider credential pasted into chat, diagnostics, source, or command output is treated as compromised and must be revoked or rotated before use.
- Only a replacement credential configured directly in the process environment may cross the existing secret-safe request boundary.
- The exposed EODHD credential was not used; no authenticated request, production ingestion, publication, or source migration is authorized by its mere availability.

## 2026-08-02 — EODHD private-shadow source authority approved
- The owner approved EODHD for bounded, private HPG/VNM source qualification; this supersedes only the earlier missing-owner-approval blocker.
- The approved candidate path is the authenticated EOD endpoint for `HPG.VN` and `VNM.VN`, preserving raw `close`, split-and-dividend-adjusted `adjusted_close`, and split-adjusted `volume` as separate identities.
- Credentials are environment-only and never retained. Production ingestion, publication, redistribution, valuation, ranking, recommendations, sizing, and backtesting remain unauthorized until their independent gates pass.
- Price and volume basis remain `unknown/unverified` until an authenticated same-session payload passes the adapter schema check. Current shares remain independently unqualified.

## 2026-08-02 — Market-data source authority remains unapproved
- EODHD is not an approved Stock Lookup source authority; its credential plumbing is removed because it was introduced before owner approval.
- No paid provider, credential, API call, or source migration may be inferred from a technical option or roadmap blocker.
- Selecting a replacement source requires an explicit owner decision covering cost, licensing, access, and authority; until then price basis remains `unknown/unverified` and all market-dependent consumers remain fail closed.
- This recovery changes governance and inert development plumbing only; it does not alter runtime databases, published artifacts, or the completed historical-only HPG/VNM path.

## 2026-08-02 — Active-path empirical price qualification
- An empirical price conclusion applies only to the exact provider, retained version, and canonical data path tested.
- An inconclusive result remains unverified and cannot become a canonical assumption.
- Historical-only analysis may operate without a current price basis; market-dependent consumers remain fail closed.
- Paid-provider integration is deferred until an explicit source-authority and licensing decision.

## 2026-08-02 — Codex milestone governance
- Codex milestones are substantial and bounded: inspect, patch, focused tests, one real/frozen validation when needed, commit, and push.
- Passed gates are not reopened without new regression evidence.

## 2026-08-02 — Forward-only OHLCV and price-test lineage
- New OHLCV observations retain provider package version, adapter/schema version, endpoint, canonical field, retrieval time, session date, source-record hash, and source-specific scale in `ohlcv_lineage`.
- Historical rows without that retained record are `legacy_version_unknown`; no package version is inferred retroactively.
- A corporate action may qualify for price continuity without qualifying a share transition; it requires official citation/hash, explicit ex-date, and ratio lineage, while provider event identity is optional metadata.

## 2026-08-02 — Official price-test event authority
- Price-continuity event identity is derived deterministically from official authority, document hash, ticker, exchange, action type, explicit ex-date, and ratio basis.
- VCI corporate-action event IDs are optional metadata; an official event and a VCI price window join on ticker, exchange, qualified ex-date, and tested price path.
- Record date never substitutes for an explicit official ex-date.

## 2026-08-02 - Bounded official-document acquisition
- Official PDF acquisition uses deterministic headers, explicit connect/read limits, at most two attempts, bounded backoff, response validation, hash-addressed retention, and an atomically written manifest.
- A verified local hash-addressed document is a cache hit and prevents another network request; failed, empty, invalid, or partial transfers never become evidence.

## 2026-08-02 - Bounded official-event locator
- Provider corporate-action records are used only to select and deduplicate a bounded ISS candidate set; locator URLs are restricted to configured official hosts and are never evidence or qualified events.
- Issuer domains are admitted only from retained official citations; candidates without a qualified mapping cannot pass the issuer-domain tier.

## 2026-08-02 - VCI provider-internal ratio semantics
- The installed vnstock 4.0.4 `Company.events` public method delegates dynamically and its available source/docstring establishes no `exercise_ratio` numerator, denominator, direction, scale, or ISS-specific applicability. The provider-internal route is terminally blocked until that direct contract changes; no price windows may be acquired from those values.

## 2026-08-02 - Active VCI price-path semantics
- The exact active invocation is `Quote(source='VCI').provider.history(start,end,interval='1D')`; the pipeline stores its `close` unchanged as `ohlcv.close`, but vnstock 4.0.4 documents only historical OHLC. Without a version-scoped provider adjustment/default contract, the path remains unqualified.

## 2026-08-02 - Documented raw/adjusted path availability
- Installed packages include vnstock 4.0.4 but not `vnstock_data`; no installed method or repository dependency directly documents separate raw and adjusted Vietnam equity EOD namespaces. P0 price-basis work requires an explicit market-data source-authority change.

## 2026-08-03 - Exact-session bundle proof covers the whole export, not a two-ticker subset
- A proof restricted to `HPG`/`VNM` meant every production export shipped `trusted_subset: null`, so the artifact the operator actually publishes carried no session proof at all. The proof now covers every exported ticker.
- A ticker with no current-session snapshot (an index row, a halted or delisted symbol) does not abort the export. It is excluded from the proven set and listed under `unproven_tickers` with a reason. The Consumer refuses to treat it as exact-session trusted, per ticker.
- Producer and Consumer pin the same `producer_contract_version` and proof `schema_version` exactly. There is no compatible-version range: output from an older Producer is legacy, and legacy is never presented as current trusted output.

## 2026-08-03 - Integrity and market-basis are separate axes
- `trusted_subset_validation` reports `integrity_state` (exact-session proof) and `basis_state` (price and volume basis verified) independently. The pre-existing single `state` is unchanged and still requires both.
- Contracts gate on the axis that applies. `analysis_readiness_contract` and `analysis_lane_eligibility_contract` gate on integrity; an unqualified basis forces `inferences_allowed = False` and adds an explicit warning rather than suppressing per-domain readiness the Producer already computed with the basis contract in hand.
- Rationale: collapsing the two made an unverified price basis erase honest information about domains that never depended on a price, which is a different failure from the one fail-closed exists to prevent.

## 2026-08-03 - Generated taxonomy is evidence, never an entity profile
- Authority order is fixed: manually verified entity profile, then generated statement-taxonomy evidence, then unknown. The generated taxonomy may only *withhold* a corporate model; `corporate_vas` never resolves an entity type and `unknown`/`unresolved` never defaults to corporate.
- The sidecar is session-bound. A sidecar whose `session_identity` differs from the export's reference session is ignored with an explicit data-quality flag, leaving the applicability gate on `insufficient_evidence` rather than binding a previous session's evidence into an exact-session artifact set.
- `config/ticker_entity_profiles.csv` is not read for resolution, not written, and not backfilled. `CANONICAL_PROFILE_BACKFILL_AUTHORIZED = NO`.

## 2026-08-03 - A context package's session is what it describes, not when it was built
- `export_ai_bundle.load_context_package_info` derived a context package's session identity from `generated_at[:10]`, a build timestamp. That only agreed with the market session by accident, on days when the package happened to be rebuilt before the next session; rebuilding a package for the 2026-07-30 session on 2026-08-03 failed the session-scoped freshness gate although the package was correct.
- The session is now read from `latest_available_dates.price`/`.technical`, with `technical_summary` and then `generated_at` as fallbacks for legacy packages.

## 2026-08-03 - Context packages are rotated, never overwritten
- `builders/build_ticker_context.py --rotate-existing` renames the previous export to `<name>_superseded_<UTC>.json` and keeps it, then writes the canonical name fresh. Without a supported refresh path the Producer silently consumed a context package several sessions old, which its own freshness gate then correctly refused.
- The write-once rule itself is unchanged: nothing is ever overwritten or deleted.

## 2026-08-03 - Generated runtime data resolves through the runtime root, in tests too
- `bctc_processor.py` pinned `data_bctc/`, `financial_snapshot.*`, `logs/` and `reports/` to its own source directory, unlike every other script in the daily chain. Running it from `stock-core-private` read an empty input directory and wrote snapshots back into the source repo. All four now resolve through `runtime_paths.runtime_root(ROOT_DIR)`, which is byte-identical to the previous behaviour when `STOCK_LOOKUP_RUNTIME_ROOT` is unset. `docs/VALIDATION_REPORT.md` stays source-tracked.
- `tests/conftest.py` exports the same runtime root once per session and `tests/_runtime_root.py::require_runtime_path` skips a test whose runtime artifact has not been generated, instead of failing with a path error that says nothing about the code under test.

## 2026-08-03 - EODHD is closed as a route: REJECTED_BY_OWNER
```
EODHD_ROUTE_STATUS: REJECTED_BY_OWNER
Reason:
Repeated website/session instability and repeated API read timeouts.
It must not be used as a production dependency, fallback dependency,
or qualification prerequisite.
Reopening requires an explicit owner decision.
```
- This supersedes "2026-08-02 - EODHD private-shadow source authority approved". That approval is closed, not merely dormant: the owner has withdrawn it after two independent days of `request_failed_ReadTimeout` on the very first request (2026-08-02, and again during the 2026-08-03 market-wide readiness audit).
- No further timeout test, retry, credential milestone, website reachability check or network-path diagnosis is authorized. An agent that proposes one is re-opening a closed decision.
- `eodhd_access.py`, `eodhd_market_data.py`, `tools/check_eodhd_access.py` and `tests/test_eodhd_access.py` stay in the tree as disabled, unreferenced modules. They are removed from the active roadmap so they cannot be mistaken for pending work. Deleting them is not required and is not blocked.
- EODHD's removal does not change any gate: price and volume basis were `unknown/unverified` with it and remain so without it. What changes is which route is on the critical path — see the corporate-action pillar below.

## 2026-08-03 - Two pillars replace per-ticker financial pilots
- The roadmap's active development shifts from "qualify one more ticker the way HPG was qualified" to two market-wide systems. The per-ticker evidence bridge is retained for PDF-cited facts and is not extended into a market-wide path.
- **Pillar A - market-wide canonical financial normalization** (`docs/market_wide_financial_normalization_contract.md`). Four layers: raw retention, statement taxonomy, canonical facts, calculation engines. Layers 1 and 2 are implemented; 3 and 4 are specified.
- **Pillar B - official corporate-action ingestion and price adjustment** (`docs/official_corporate_action_ingestion_design.md`). Design only. It makes our own event ledger the adjustment authority, so no provider has to document its adjustment policy for the price basis to become qualified.
- The two pillars are independent up to pillar A's enterprise-value layer, which needs a market capitalisation and therefore waits on pillar B.

## 2026-08-03 - Raw financial retention has no allowlist
- `raw_financial_observations.py` retains **every** raw line item of every retained statement payload, for every populated reporting period. Selection is a mapping-layer concern, never a retention concern.
- The reason is operational, not aesthetic: an allowlist makes every future mapping rule that needs an unanticipated item require a re-fetch of the whole universe. `financial_observations.py`'s bounded `_CODES` allowlist is correct for its three-ticker pilot and must not be extended into the market-wide path.
- Nothing in this layer is ever `qualified`. Statement scope, currency, unit scale, sign convention and cumulative basis are not carried by the retained payloads, so every observation records them as `unknown` with an explicit warning, and the highest state assignable is `retained_raw`.
- The store is incremental on a fingerprint that covers the source payload hashes **and** the extraction schema version. Keying on payload hashes alone would leave shards looking `unchanged` after a change to the extraction logic, silently serving observations built by code that no longer exists.

## 2026-08-03 - `not_applicable` is a verdict, `unavailable` is a gap
- For a metric defined only by the corporate earnings model (`ebitda`, `ev_ebitda`), a filer positively evidenced as a credit institution, securities company or insurer receives `not_applicable`, not `unavailable`. `unavailable` invites someone to go find a missing input; `not_applicable` closes the question, because no input will ever make a bank's EBITDA exist.
- This is now structural rather than per-ticker: `not_applicable` covers **82** tickers, up from the 7 manually-profiled ones the 2026-08-03 audit found, closing the under-classification that audit reported.
- Every `not_applicable` result names substitute metrics for that template family, so it points somewhere instead of only closing a door.
- The authority order is unchanged and is not weakened by this: a manual profile is still the only thing that may name an institution type; generated statement evidence may still only *withhold* a corporate model; a corporate template still never grants a corporate archetype; and two evidence families disagreeing about *which* specialized financial template a filer uses still agree it is one, so disagreement withholds rather than restores.

## 2026-08-03 - Income-statement taxonomy evidence lives outside the pinned classifier
- The new exclusive income-statement marker sets are in `financial_entity_applicability.py`, not in `statement_taxonomy_classifier.py`. That module is pinned at `VERSION = "2.0.0"` and feeds `statement_taxonomy_sidecar.json`, which is hash-bound into the shipped bundle; adding markers there would move the sidecar fingerprint and change a production artifact for a reason unrelated to this milestone.
- The markers were validated market-wide before being written down: zero occurrences across the union of all 1,261 corporate-template income statements, 100% match within each group, zero cross-group overlap. The insurance set resolves 12 of the 13 tickers the balance sheet can only call `financial_specialized_ambiguous`.

## 2026-08-03 - A reported measurement must be produced by the run that reports it
- `tools/operate_stocklookup.py::report()` carried `market_wide_shares_coverage` as a dict literal: `active_universe_count: 1683`, `pe_ready_count: 1391` and eleven siblings. Advancing a milestone meant editing the numbers by hand — commit `5209447` changed `1679 → 1677` and `1393 → 1391` as source edits. The block would have printed identical numbers against an empty runtime root, and the only production report ever written carries the key as `null`.
- **A number in an operating report must be computed by that run, from that run's inputs, and must carry `measured_at` and the session it was measured for.** A count that no data change can move is not a measurement, and labelling it one in a report the operator saves as a baseline is worse than omitting it.
- The valuation-readiness counts were **removed rather than re-derived**. They describe a pass over the canonical fact store, which this command does not perform and never performed; restating them anywhere would repeat the original error in a new place.
- This applies to milestone operations reviews as well. P1J's review recorded a "Workstream B" grounding table whose HPG and VCB rows disagree with both the database and the citation store, because the comparison was written rather than run.

## 2026-08-03 - Official share anchors are read from the citation store, never carried as literals
- `market_wide_current_shares_resolver.QUALIFIED_SHARES` held three share counts as literals. Two were wrong. HPG's `7,163,748,865` appears in no citation and no ledger: it applied the 2026-06-04 stock dividend to the FY2024 period-end figure, when the event's own ratio fixes its base at `767,498,665 / 0.0999937567 = 7,675,465,852` and the ledger records `shares_after = 8,442,964,520`. VCB's `5,589,091,222` is the citation's `5,589,091,262` mistyped by 40 shares.
- The resolver was therefore overriding a **correct** provider value with a fabricated one 15% too low for HPG, under the system's highest authority label.
- Anchors now come from `data/official-evidence/share_basis_citations.jsonl` on every call. A regression test asserts both retired literals appear nowhere in the module.

## 2026-08-03 - A period-end share count is not a current share count
- All three retained anchors are `identity_type: period_end_shares_outstanding`, `reporting_period: 2024`. Serving one as a *current* share count asserts that nothing changed between the period end and the session — which is a claim about the corporate-action record, not about the anchor.
- Promotion to `qualified_official` therefore requires an official anchor **and** a ledger whose `coverage_status` is qualified across that interval. `corporate_event_records` covers 5 of 1,683 tickers at `partial_unqualified_50_row_cap`, so the gate is shut market-wide and `qualified_official` is **0**, not 3.
- This is not a regression. It is what was always true; the previous count reported the size of a hardcoded table.

## 2026-08-03 - Freshness is measured against the observation, and only an ex-right date positions an event
- The retired rule invalidated a provider share count when any event carried a date after a fixed literal `'2024-12-31'`, across `exright_date`, `record_date` **or** `issue_date`, for any event category. It therefore invalidated counts on events the observation already reflects (HPG's 2026-06-04 dividend against a 2026-07-30 observation), and fired on shareholder meetings and major-shareholder trades, which change no share count.
- The rule is now: compare the event's **ex-right date** against the provider's observation date (`metadata.updated`). A record, issue, payment or listing date never substitutes for an ex-right date — the same rule pillar B already applies to adjustment factors.
- `ISS` is the declared share-changing code; ten codes are declared not share-changing; anything else is `unclassified` and treated as share-relevant. An unknown code is never silently benign.
- A share-relevant event with no ex-right date cannot be positioned, so the ticker resolves to `provider_reported_unverifiable_freshness` with no value, rather than to either `current` or `stale`.

## 2026-08-03 - A failed read is not an absent value, and a share store is opened read-only
- Both retired lookups wrapped their queries in `except Exception: pass`. An unreadable corporate-event table returned an empty set, silently promoting the whole universe to `provider_reported_current`; an unreadable metadata row was reported as "no valid retained share observation found". Fail-open, under a fail-closed contract.
- Read failures now raise `ShareStoreUnreadable` and surface as `unresolved_error`, a lane of its own that is never folded into `unavailable` or into a provider lane. A market-wide read failure reports no counts at all rather than zeroes.
- The database is opened read-only (`mode=ro`, `PRAGMA query_only`, `busy_timeout`), matching the operating command's probe. The retired code opened it read-write once per ticker and again for the event scan — 3,366 read-write connections for one market-wide pass, against a database in rollback-journal mode with a live daily writer.

## 2026-08-03 - A market capitalisation is only as qualified as its weaker leg
- `evaluate_market_capitalisation()` set `status = qualified` from the share status alone. The price basis has been `unknown`/`verified: false` throughout, so a qualified share count produced a "qualified" market cap built on an unqualified price.
- The price leg's authority is now an explicit input (`price_basis_verified`) and defaults to `False`. No market cap, and therefore no EV, EV/EBITDA, P/E or P/B, can be `qualified` while the price basis is unverified.
- The share **concept** travels with the value. `ISSUED_SHARES` does not deduct treasury shares, so a cap built on it is not comparable with one built on `common_outstanding`, and carries a named warning saying so instead of being averaged into a universe-wide figure.
- The session price is read for the session (`WHERE date = ?`), not as the newest row for the ticker. `ORDER BY date DESC LIMIT 1` gave a delisted or suspended ticker's last-ever close to the current session's market cap with nothing marking the mismatch.

## 2026-08-03 - The session is an input to every session-relative resolution
- `resolve_effective_shares` defaulted `target_date` to the literal `"2026-07-30"`, and the one production caller passed nothing, so every export stamped that session's shares onto whatever session it was building. `session_date` is now required and validated on both entry points, and `canonical_financial_bundle_section.attach()` attaches nothing without one.
- `Operator.run()` re-anchors the session after `prepare_inputs()`. It previously called `preflight_database()` again and discarded the result, binding the taxonomy sidecar to the session that preceded the input refresh.

## 2026-08-03 - The daily chain's dependency order is enforced, not documented
- Stage order is `metadata/current-share refresh -> focus analysis -> context packages -> bundle export -> Consumer exact-session validation -> optional publish`. Each stage consumes the previous stage's output, so a stage run on a stale predecessor yields an artifact that is internally consistent and describes two sessions.
- Only one gate covered this before. `export_ai_bundle.check_freshness` refuses off-session `focus_analysis` and `context_package`, and it refused correctly on 2026-08-03 — but as `exit code 1` from a subprocess, after the sidecar had already been rebuilt on top of the stale input, and without naming which command refreshes what.
- **`metadata` was covered by nothing.** It is not in `DEFAULT_SESSION_SCOPED_CATEGORIES`, so a universe whose share counts were observed days before the session passed every existing gate silently. `preflight_share_freshness` now measures the lanes on every run and reports the session, the share observation date and each lane count.
- A lagged share count blocks the export **only where it can reach the artifact** — that is, under `--include-canonical-financial-facts`. The default bundle carries no share-derived value, so lag cannot enter it, and blocking there would be theatre. The allowance is named in the step record rather than left implicit, and a lagged value is never relabelled as current.
- Failures name the stage and the remedy: `METADATA_REFRESH_REQUIRED`, `FOCUS_ANALYSIS_REFRESH_REQUIRED`, `CONTEXT_PACKAGE_REFRESH_REQUIRED`. A failed stage prevents every later stage and prints no success line.

## 2026-08-03 - `--refresh-metadata` is the one stage allowed to write the authoritative store
- `--prepare-inputs` keeps its narrow meaning exactly: offline, session-scoped, no market data fetched. It rebuilds focus analysis and context packages and **does not** refresh metadata or current shares. That is why a `--prepare-inputs` run left the whole universe `provider_reported_lagged`.
- `meta_sync.py --refresh` is the only thing that moves `metadata.updated`, and it both writes `vn_stock.db` and reaches the network. It is therefore opt-in behind `--refresh-metadata`, requires `--execute`, runs before `--prepare-inputs`, and re-anchors the session afterwards.
- This is a documented, flag-gated exception to "never writes to vn_stock.db", not a silent change: without the flag the command's contract is exactly what it was. The restorable database copy is taken once per run and covers both writing stages, because a second copy taken after the first stage would record a state that stage had already changed.

## 2026-08-03 - An approval instant must say which clock it was read from
- `config/official_source_registry.json` records `approved_at = 2026-08-03T14:00:00Z`. The commit that wrote it, `a4d01cf`, was created at 2026-08-03 14:22:40 +0700 = **07:22Z**, seven hours earlier. A UTC instant ahead of the commit that records it is the signature of a local time written with a `Z`.
- **No owner record in this repository states which clock 14:00 was read from.** `docs/DECISIONS.md`'s P1G entry records the approval; neither it nor the P1G operations review carries a time. So the instant is not normalized and the approval is not modified: `approval_instant_verdict()` returns `unverified`, and `admit()` refuses with `approval_instant_not_verifiable`.
- Verification requires an owner-supplied `approved_at_provenance` naming the clock. It is required rather than inferred, because inferring it is an agent deciding what the owner meant. The requirement is also what makes the verdict durable: a future-dated instant stops being future-dated by waiting, so a check against the clock alone would turn `unverified` into `verified` with nothing verified.
- The instant is checked **last** in `admit()`, after host, document type and rate, so a bad host still reports `host_not_on_source_allowlist` rather than being masked by a governance verdict.
- This adds a requirement to owner approval and removes none. Pillar B's acquisition path (B2-B6) is closed until the owner records the provenance — which is the correct state for an approval nobody can currently read.

## 2026-08-03 - An executed event's `shares_after` is a current share count; a period-end figure is not
- `share_basis_citations.jsonl` held only `period_end_shares_outstanding` citations, so `market_wide_current_shares_resolver` had nothing that could ever describe *today*. Meanwhile `data/official-corporate-actions/event_ledger.json` had held a qualified, executed, hash-bound HPG `stock_dividend` since 2026-08-02 stating `shares_after = 8,442,964,520` as of 2026-07-02. Nothing read it. The count the issuer had published sat one directory away while the resolver reported HPG as `provider_reported_lagged`.
- The two identities are now distinct and ranked. A period-end citation describes 31 December; turning it into a current count requires proving nothing changed since, which for 1,682 of 1,683 tickers nothing does. An executed event's `shares_after` is an absolute count the issuer states as of a date, so it needs no proof for the interval *before* it — only for the interval after.
- **An ex-right date is deliberately not required for a share count.** An ex-date places an action on the price timeline, which is what an adjustment factor needs and why HPG's factor is still correctly `not_ready`. A share count needs proof the event executed: `lifecycle_state = executed` plus a stated execution date. Requiring an ex-date for both is what kept a published share count out of the evidence store.
- The interval after the anchor is closed by an **independent observation of the same absolute count**, not by an assumption. HPG's provider observation on 2026-07-30 reports 8,442,964,520 digit for digit. Where the two disagree the entry is refused outright — two sources contradicting each other is not evidence of either.
- `evidence_promotion.py` remains the sole writer. `share_basis_event_promotion.py` only selects and explains; it writes nothing, and every rejected ledger entry carries a named reason (`event_not_executed`, `entry_superseded`, `no_stated_execution_date`, `event_type_does_not_change_share_count`, …).
- Result: `qualified_official` 1 (HPG), from 0. VNM and VCB are refused with `anchor_is_a_period_end_figure_not_a_dated_current_count` — a document-level gap, closed by acquiring a notice per ticker, not by more code.

## 2026-08-03 - The B1 approval instant is not inferred from a commit timestamp
- `approved_at = 2026-08-03T14:00:00Z` was written by commit `a4d01cf`, created `14:22 +0700` = `07:22Z`. That makes "14:00 is local time" plausible. It does not make it evidence: it says when the value was *written*, not which clock the owner read when approving.
- So the value is neither corrected to `07:00:00Z` nor kept at `14:00:00Z`. Correcting it would fabricate a fact only the owner holds; keeping it would legitimise a timestamp on the strength of it already existing. The registry stays blocked and `admit()` keeps refusing.
- The owner's answer must take one of exactly three forms, recorded in `docs/STATE.md`: 14:00 was Vietnam time (set `07:00:00+00:00` plus provenance), 14:00 was UTC (keep it plus provenance), or the activation was not theirs (revert `activation`, leave the registry closed). An agent writes neither `approved_at` nor `approved_at_provenance` under any of the three.

## 2026-08-03 - `corroborated_period_end` is a shadow lane, not a weaker `qualified_official`
- A period-end anchor matched digit-for-digit by an independent observation has the same evidential *shape* as an executed event's `shares_after` plus its corroboration. Folding it into `qualified_official` would have made VNM qualify today without a new document, and would have made the label mean two different strengths of claim.
- It is therefore a separate, quarantined lane with the constraints fixed in code and tested: `authority_rank` 1 against executed-event evidence's 2; never a value `authority` may take; absent from the production lane counts; structurally unable to contribute to `is_actionable`; and shadow-only until it has its own validation and its own owner decision.
- **Every verdict carries `proves_no_intervening_event: false`, and that field cannot be true in this lane.** Agreement proves the *net* count is unchanged, not that nothing happened; two offsetting events produce the same number. The exposure is reported as `interval_days_carried_by_observation` rather than left to the reader — VNM's observation is carrying 576 days, HPG's promoted event only had to carry 28.
- Measured for 2026-08-03: 1 eligible (VNM, 576 days). VCB is refused — its observation contradicts its anchor, which the retained VSDC 2025 listing-change notice independently explains. HPG is out of scope, its executed-event anchor outranking the lane.

## 2026-08-03 - B1 approval instant verified by the owner; canonical value is 07:00Z
- The owner confirmed they approved the registry personally, and that the `14:00` originally recorded was Asia/Ho_Chi_Minh. `approved_at` is therefore corrected to `2026-08-03T07:00:00Z`, and `approved_at_provenance` records both the clock and the confirmation. The value came from the owner; this entry is the attribution, not a derivation.
- The correction is consistent with the evidence that raised the question: commit `a4d01cf` wrote the value at 07:22Z, and a 07:00Z approval precedes it by 22 minutes where a 14:00Z one would have followed it by seven hours. That consistency is corroboration after the fact, not the reason — the reason is that the owner said so.
- **The gate is unchanged.** `approval_instant_verdict()` now returns `verified` and `admit()` admits `hose`, `hnx`, `vsdc` and `issuer_ir`, but removing `approved_at_provenance` closes the registry again, and that is under test in three suites. What moved was a fact, not the standard.
- The earlier rule "an agent writes neither field" is restated as what it was protecting: **the value must originate from the owner and the record must say so.** Transcribing an explicit owner statement, attributed, is not the failure that rule exists to prevent; an agent choosing the value is, and it still may not.
- Pillar B steps B2–B6 are unblocked. The binding constraint on `qualified_official` is now document coverage, not governance: 1 ticker (HPG) has an executed-event notice and the rest need one acquired.

## 2026-08-04 - The source registry gates the acquirer, not just a JSON file
- `official_source_registry.admit()` existed, was reviewed, was owner-approved and had its approval instant verified across two milestones. Its **only caller in the tree was `tools/run_official_corporate_action_slice.py`** — the offline slice runner, which issues no network request. `official_document_acquisition.acquire()` fetched whatever URL a spec named, with no host allowlist check, no per-source document-type check, no rate rule and no approval check. The gate governed a JSON file and not a single request.
- `acquire()` now admits every request before making it: source, host, document type and interval. A refusal is recorded as `refused_by_source_registry` with the registry's own reason and **no request is made** — the tests assert the absence of a call, not the presence of an error, because a request that has already left cannot be un-made.
- The declared minimum interval is now *waited out* rather than reported on: the acquirer sleeps the remainder of the interval and proceeds, per source, so the rate rule shapes traffic instead of describing it after the fact.
- **The requestable document vocabulary comes from the registry**, not from the module. `DOCUMENT_CLASSES` was missing `ex_right_notice`, `listing_change_notice` and `last_registration_date_notice`, so `_validate_spec` rejected as malformed the exact notices that carry an ex-date — the single field `PRICE_ADJUSTMENT_FACTOR_PILOT` is blocked on. Two vocabularies for one concept had drifted, and the one that gated requests was the one nobody reviewed.
- No live acquisition was performed. Finding this before the first network run is why the run has not happened yet: the point of an owner-approved allowlist is that the first real request is the first *governed* request.

## 2026-08-04 - A gate on the first request is not a gate on the request that follows it
- `3b4cc5f` made `acquire()` admit every request before making it, and that held for the URL a spec names. Two paths still reached the network without passing the gate, both reachable by a **remote host alone, with no code change**: a `302` off an allowlisted host was followed, retained and recorded, because `allow_redirects=True` hands the next request to whatever the host replies; and a retry re-requested the same source after a `0.25s` backoff against a declared `10s` minimum, because the interval was enforced once per spec rather than once per request.
- `fetch_http` now follows redirects one hop at a time and admits each hop **before** the next request leaves, rather than judging where it landed. A refused hop raises `redirect_refused_by_source_registry` and the tests assert the hop was never requested. `acquire()` additionally re-admits any final URL that differs from the one requested, so bytes are never promoted from a host the registry would refuse **whoever fetched them** — a caller may supply any fetcher, and defence in depth is cheaper than trusting one.
- A retry now waits out that source's declared interval, not the backoff. The retry path was the one way to legitimately exceed the rate the registry publishes to the hosts it names.
- **The redirect bound comes from the registry.** `global_policy.max_redirects` sat in the reviewed JSON while `fetch_http` compared against a hardcoded `5`. They happened to agree, so nothing broke — which is precisely how the document-type vocabulary drifted. A reviewable value that governs nothing is a comment.

## 2026-08-04 - One vocabulary and one source identity across discovery and acquisition
- `3b4cc5f` moved the acquirer onto the registry's document vocabulary and made `source_id` mandatory. `official_document_discovery` was one import away and moved neither, so the fix landed in one of the two layers that had to agree.
- Discovery kept gating on `official_document_acquisition.DOCUMENT_CLASSES`, which omits `ex_right_notice`, `listing_change_notice` and `last_registration_date_notice` — so it rejected as `ambiguous_document_identity` **exactly the three notices that carry an ex-date, a listing change and a last registration date**, the facts pillar B exists to acquire. Discovery now reads the same registry union `acquire()` does.
- Discovery carried no `source_id`, so `retain()` handed `acquire()` specs refused as `missing_source_id` — **every candidate, no request made, nothing retained.** That is a regression `3b4cc5f` introduced silently: before it, `acquire()` required no source, so the discovery→acquisition bridge worked and then stopped working with no test covering the seam. A listing page now declares the registry source that governs it, and a page without one is rejected whole.
- Discovery accepted only `.pdf`. Exchange and depository notices are routinely HTML, `acquire()` retains `text/html`, and the evidence store already holds such documents (`vsdc-record-date-notice.html`, the retained HPG `listing_change_notice`). One layer's idea of admissible evidence now matches the other's.
- Discovery remains a **validator, not a parser**, and this does not change that. It never widens what may be requested: a candidate it accepts is still admitted or refused by the registry at `acquire()`, which is under test.

## 2026-08-04 - The first governed VNM discovery pilot is blocked on inputs, not on permission
- A bounded real-network VNM pilot was attempted and **stopped fail-closed at preflight; no network request of any kind was made.** Governance passed: the approval instant is `verified` at `2026-08-03T07:00:00Z` with provenance, all four sources are `approved`, and a refused host provably produces zero fetcher calls.
- It stopped on two things an agent may not supply. **No owner-approved VNM listing or search URL exists in any artifact** — every VNM URL on record is a terminal document, every `hsx.vn`/`hnx.vn` URL in the tree is a test fixture, and each source's `discovery_path` says "operator-supplied ... URLs only". **And the registry declares no listing/index/search document type at all**, so `admit()` refuses one; labelling a listing page `corporate_action_notice` to get it past the gate would defeat admission rather than pass it.
- Constructing a plausible HOSE or VSDC search URL from site structure is available and was declined. It would be an agent supplying the operator's authority to itself, and it would put a fabricated fact into an evidence system whose whole value is that it contains none.
- The narrowest unblock is an owner-named **notice detail** URL — the shape `vsd.vn/en/ad/177392` already has authority for. It needs no new document type, no listing-page parser, and no change to the closed-world contract.

## 2026-08-04 - An announcement index page is acquirable and never evidence
- Pillar B's remaining blocker was that every notice URL had to be hand-supplied by the owner. Removing it needs one new power — reading links out of one stored page — so the registry now carries **two disjoint vocabularies per source**: `document_types`, which may become corporate-action evidence, and `index_document_types`, which may be requested and never promoted. `announcement_index_page` is declared for **`vsdc` only**, the one source whose index pages are observed in a retained first-party artifact. Adding it to another source requires the same kind of observation, not a convenience.
- The separation is enforced where evidence is written, not where it is requested: `official_document_store.adopt_retained_document` refuses a discovery-input type **by name**, before the general vocabulary check, so the refusal states the rule. Relying on the type's absence from `DOCUMENT_TYPES` would have made non-promotability an accident of omission. An index page therefore cannot reach the observation ledger, the resolver, `qualified_official` or `corroborated_period_end`.
- Labelling a listing page `corporate_action_notice` to get it past `admit()` was available and rejected. It would defeat the gate rather than pass it, and it would put a page that asserts nothing about any issuer into the store the ledger reads from.

## 2026-08-04 - An entry URL is observed or the pilot does not run
- The VNM pilot's entry URL, `https://vsd.vn/en/alc/6`, is the breadcrumb `href="/en/alc/6"` inside the already-retained VNM notice `/en/ad/177392` — the category listing that the one retained VNM official document declares itself to belong to. The taxonomy is corroborated independently by the retained VCB artifact, which carries the same breadcrumb shape under `/en/alo/MEMBER` → `/en/alc/4`. `tools/run_official_listing_discovery.py` requires `--observed-in` and refuses to start when that artifact is absent, so provenance is an argument the runner checks rather than a claim in a report.
- A VSDC **search** URL was considered and rejected. The site's search box has no `<form>`, no `action` and no named fields — only `id="gSearchAdvText"` — so any search URL would have been invented. A URL derived from a JavaScript endpoint nobody has observed is a fabricated fact wearing a plausible shape.

## 2026-08-04 - A URL extension is a hint, not a document classifier
- Discovery allowlisted `.pdf`, which silently rejected two whole shapes of real evidence: an HTML notice, and an **extensionless** URL like `https://vsd.vn/en/ad/177392` — the form *every* VSDC notice takes, including the one already retained as official VNM evidence. The check is now a denylist of assets (`.css`, `.png`, …). `acquire()` validates the real `Content-Type` and refuses anything that is not `application/pdf` or `text/html`, so the hint's job is to drop stylesheets, not to decide what a document is.
- Inference is confined to what the source declares. VSDC does not publish `listing_change_notice`, so inferring one for a VSDC candidate would mint candidates the gate then refuses with `document_type_not_declared_for_source` — correct, fail-closed, and useless, since every registered-share notice would land in that hole. The **cue survives the remapping**: what a subject line is about is a reading of the page, while which class the source files it under is a fact about the source, and collapsing the two would have downgraded exactly the notices that carry a share count.

## 2026-08-04 - What a VSDC record-date notice does not contain
- A VSDC cash-dividend record-date notice states issuer name, securities code, ISIN, par value, trading platform, securities type, record date, payment rate, time and place — and **no share count**. So none of the 10 VNM candidates in the retained window (2023-07 → 2026-06), all cash dividends, AGMs and one record-date correction, can corroborate or contradict `2,089,955,445`.
- The class that carries an absolute registered share quantity is *"adjustment of the number of registered shares"*, observed for `CTR` on the page acquired today and for `VCB` in the retained artifact. **No such VNM notice appears in the retained window.** That is consistent with VNM having had no capital-structure event there, but the source is a 10-item sidebar and not a complete history: absence in it is not evidence of absence, and nothing was written anywhere from this observation.

## 2026-08-04 - The VCI historical series is not the as-quoted series
- The question was never answerable from field names — the `gap-chart` payload declares nothing — so it was answered from an **exchange rule** instead. A HOSE common-stock order matches only at a tick multiple (10 / 50 / 100 VND by price band), so a returned close of `54,047.65` or `23,478.96` was never a matched price. That exclusion is deductive; it does not depend on trusting the provider about anything.
- Which adjustment dimension came from **where the off-lattice prefix stops**, not from a fitted factor. It stops exactly at a qualified ex-date for three tickers — VCB 2026-07-23 (cash 450 VND), HPG 2026-05-25 (share issue 0.1), VNM 2026-06-26 (cash 1,850 VND) — two of them **cash-only**, which is what makes the verdict `split_and_dividend_adjusted` rather than split-only. Event dates were inputs from `corporate_event_records`, never inferred from price shape.
- The decisive artifact already existed and cost no request: `archive/runtime-backups/VNSTOCK_DATA_BACKUPS/20260719_223620/vn_stock.db` was snapshotted **before** VCB's ex-date, and `vn_stock_pipeline` only ever fetches forward from `MAX(date)`, so its historical rows are first observations. 13 of 13 VCB closes differ from today's payload for the same sessions; the no-event control re-request came back **byte-identical** (sha256 `1f57e4fe…`, the same hash the 2026-08-01 artifact carries). Revision is event-driven, not drift.
- A single constant factor `0.9917` reproduces all 13 sessions exactly and matches a standard cash-dividend back-adjustment. It is recorded with `event_window_fit_upgraded_verdict: false`, and a test proves a perfect fit cannot lift an `inconclusive` verdict. Reverse-engineering a factor and then calling the provider contract established is the failure mode this milestone was written to avoid.
- **This contradicts a retained artifact and the contradiction is recorded, not resolved.** `phase3a-qualified-vci-price-benchmark.json` asserts `price_basis: "raw_as_quoted_no_adjustment_applied"` over 1,923,111 stored rows. Those rows come from this same series. The benchmark was not modified.

## 2026-08-04 - Volume unit is qualified by the provider's own arithmetic; scope is not
- Daily `v` and the intraday `accumulatedVolume` were retrieved one second apart for the same in-progress session and matched exactly (9,315,300), so they are **one counter**, not two computations. That qualifies field identity without saying anything about scope.
- The **unit** is settled by an identity internal to one payload: across 99 of 99 consecutive trade pairs, `Δ accumulatedVolume` equals `matchVol` and `Δ accumulatedValue` equals `matchVol × matchPrice` under exactly one scale, 10⁶. A lot count would break that by a factor of 100. So the field is **shares** and `accumulatedValue` is in millions of VND — proven from the provider's own numbers, with no second source involved.
- **Scope stays `unknown` and the reconciliation was refused, not fudged.** `limit=30000` was requested and the endpoint returned 100 rows — a server-side cap. Observed intraday sum 146,900 against daily 9,315,300. Reading that gap as evidence of put-through inclusion is exactly the inference the contract forbids while pagination is unexhausted, so it classifies as `intraday_sample_incomplete` and a test proves a filled page cannot be read as a completed sample.
- Volume is also revised after first publication — 13 sessions, 13 **distinct** ratios (1.00233–1.00764), not the reciprocal of the price factor. Every pre-event value is a multiple of 100 and no post-event value is, which fits a mid-session accumulator snapshot at least as well as a corporate-action adjustment. Two causes, one observation, so `volume_adjustment_basis` stays `unknown`.

## 2026-08-04 - TCBS was declined rather than guessed
- `vnstock` 4.0.4 ships **no TCBS quote explorer** (`explorer/` holds `fmarket, kbs, misc, msn, vci`); what survives is a header profile and TCBS branches inside `transform.py` — evidence a path once existed, not its URL. The only TCBS endpoint anywhere in this repository is `apipubaws.tcbs.com.vn/tcanalysis/v1/margin/list`, recorded 404 on 2026-07-09.
- Composing a bars URL from that host and a plausible path was available and declined: it is fabricating an endpoint from a naming pattern, and whatever it returned would be attributed to a contract nobody has observed. **Zero TCBS requests were made.** Corroboration used the already-local retained KBS sample read-only instead, which matched 9/9 closes and volumes — in the post-event region where an adjusted and an unadjusted series coincide by construction, so it settles nothing and is recorded as compatibility only.

## 2026-08-04 - "We adjusted nothing" was never a statement about the provider
- The Phase 3A verdict that labelled 1,923,111 VCI rows `raw_as_quoted_no_adjustment_applied` was a **hard-coded module constant** in `qualified_price_storage_benchmark.py`, stamped onto every exported row and into the manifest. It was never derived from a payload, never gated on evidence, never verified. Not a different endpoint, not a stale snapshot, not a transformation bug — an unsupported assumption that survived because nothing ever asked it to prove itself.
- The same conflation was written down in `semantic_evidence_bridge.py`: a citation was valid "when the ticker had no unsettled corporate action **as of the trading_date**". That is the right instinct pointed the wrong way down the timeline — a back-adjustment is applied by events **after** the cited date. The reader then re-validated each citation against the live `ohlcv` row, which is the same rewritten series, so the check agreed and *reinforced* the wrong label.
- Both production citations demonstrate it arithmetically. HPG 2024-12-31 close 19,830 is not a multiple of the 50 VND tick for its band; VCB 60,560 is not a multiple of 100. Neither was ever a matched order price, and both were labelled raw. HPG's stated justification — its 2024 action settled 2024-06-27, before the cited date — ignores the 2025-06-26 and 2026-05-25 share issues that came after.
- The replacement verdict is `empirically_event_adjusted`, deliberately **not** `split_and_dividend_adjusted`. The latter names a general methodology; what is evidenced is adjustment observed at two event kinds, three tickers, one year. `provider_methodology` and `unobserved_event_types` stay `unknown` and `coverage_generalization` is `not_authorized`.
- Phase 3A is **superseded, not deleted**: the artifact, its manifest and its history stand, and `is_superseded()` is how a reader learns it is inactive. Two disagreeing *active* verdicts resolve to `conflicted` with every gate shut — recency is not evidence, and the new verdict wins on stated evidence rather than on date.
- **Unexamined providers were deliberately left ungated.** A fail-closed default would have blocked SSI and KBS too, which this pilot never looked at — a policy change wearing the costume of a bug fix. `active_verdict` returns `raw_as_traded_eligible: None` for them, and `unexamined_providers_note()` states in code that they still pass on the same conflation, merely not yet evidenced.
- Cost, stated plainly: P2a historical point-in-time valuation is **reopened as BLOCKED**. HPG's published FY2024 multiples had a price basis underneath them that does not hold.

## 2026-08-04 - Zero duplicates was the bug, not the proof
- The intraday cursor is **strictly exclusive** (`truncTime < cursor`) — measured, 71 of 71 transitions returned a newest trade strictly older than the requested cursor, 0 equal. Paging with `cursor = oldest_trunc_time` therefore looks flawless and produces **zero duplicate rows**, which reads exactly like confirmation that pagination is clean.
- It is the opposite. The 100-row cap truncates the oldest second mid-way, and under `<` the next request skips the rest of that second forever. Run 01 lost **1,704,400 shares** and broke the tape's own accumulated-value identity in 47 places while reporting a perfectly tidy scan. The correct cursor is `oldest + 1`, which re-delivers the boundary second whole and is then de-duplicated by trade `id` — 243 duplicates in the corrected run, which is what a correct scan of an inclusive overlap looks like.
- Deduplication is by provider trade `id` **only**. Time, price and quantity are excluded on purpose: HPG's tape routinely carries several trades sharing all three within one second, and a value-based key would have deleted real volume while looking even tidier.
- **A one-second cursor cannot enumerate a second holding ≥100 trades.** HPG hits this repeatedly; the scan moved to VCB, the sparsest ticker already in scope. This is a permanent property of the data path, not a budget problem, and no larger `limit` helps — the server caps at 100 regardless.
- The endpoint serves **only the current session**: a cursor at the prior session's close returns zero rows. A completed prior trading day is unreachable, which is why the pilot bounds a segment of the live session during the lunch halt rather than a whole day.

## 2026-08-04 - The books balancing is not the same as having every trade
- VCB's morning segment closes to the share: 1,873,500 enumerated + 3,500 measured-unenumerable = 1,877,000 = daily `v`, residual **0**. The 3,500 is not an unknown — `accumulatedVolume` is cumulative including its own row, so a gap between two retained trades is *exactly* measurable, and the scan reports 0.19 % un-enumerated instead of claiming completeness.
- It is still reported `incomplete_cursor_failure`. Whether the arithmetic reconciles and whether every trade was retrieved are different claims, and only the second is what "complete" means. Reporting a match on the enumerated subset would be a match against a quantity nobody asked about.
- **Even a perfect exact match would not have qualified market scope.** Enumerating everything this endpoint returns establishes what *this endpoint* counts; a matched-only tape and a tape including put-through reconcile identically against a daily field computed from that same tape. So `market_scope`, `negotiated_trade_inclusion`, `auction_inclusion` and `odd_lot_inclusion` are hard-coded `unknown` in the contract rather than computed, and a test proves a `complete_exact_match` cannot move any of them.

## 2026-08-04 - Two words that were doing more work than the evidence supports
- `market_scope = partially_qualified` is retired for `overall_market_scope = partially_observed_but_not_qualified`, and `opening_auction_inclusion = qualified` for `demonstrated_for_observed_ato_field`. **No verdict changed.** Both old spellings were accurate about the dimension they described and readable, by a consumer skimming for a green light, as "qualified enough to size against" — which is the one reading the evidence does not support. The qualified component is the inclusion of *one observed ATO-labelled quantity* in the accumulator, not the composition of the volume field.
- The roll-up `general_auction_composition` is now `partially_observed`, and `qualified` is **not a reachable value** for it. One demonstrated leg plus one unobserved leg is partial observation. `closing_auction_inclusion = qualified` is refused outright by the contract builder, so the ATO narrowing cannot be copied onto ATC by a caller in a hurry.
- `matched_trade_inclusion`, `negotiated_inclusion` and `odd_lot_inclusion` were recorded at `63ecc48` as `unknown` at the top level with `unavailable_from_observed_vci_surfaces` in a sidecar. They now carry the terminal verdict where a consumer actually reads. Same finding, relocated — a test asserts the frozen and active records agree on every dimension.
- **Two assertion functions, not one.** `assert_fail_closed` answers "is this safe" and still accepts `partially_qualified`; `assert_canonical_vocabulary` answers "may this be active" and refuses it. A frozen artifact can be safe and non-canonical, and `composition_summary.json` keeps its original words — an evidence record that gets edited when the vocabulary changes is not an evidence record.

## 2026-08-04 - "Blocked pending verification" was the wrong shape for liquidity
- Every liquidity gate in the repository was expressed as *blocked while `volume_basis_verified` is false*. That is a pending state with an obvious release, and the composition closeout made that release **dangerous**: the unit is shares and the provider's arithmetic closes exactly, so a future reader has every reason to verify the basis — and would thereby open days-to-liquidate, participation-rate sizing and backtest liquidity constraints on a figure whose market composition nobody has established.
- Nothing in production was open. Everything in production was **one plausible edit** from being open. That is the entire finding of this milestone; there is no live defect to report.
- So the gate moved off the basis. Thirteen liquidity and execution capabilities are `unavailable_by_contract` with `reason = complete_market_composition_not_qualified` and `reopen_condition = new_authoritative_source_contract`. There is no argument to `evaluate()` that opens one — not `existing_gates_passed=True`, not a different provider. The reopen note names what does *not* reopen them, because "reopen condition" alone reads as "paginate once more".
- `vci_volume_basis.forward_gate.action` read `block_liquidity_activation_when_unverified`, which says, correctly read, that verifying the basis activates liquidity. It now reads `block_liquidity_activation_unconditionally`, and `validate_forward` returns `liquidity_activation_permitted: False` **on success** — a caller wanting liquidity must override a stated refusal rather than infer consent from the absence of an exception.
- `risk_liquidity.dimensions.liquidity` read `available` whenever a descriptive mean was computable. A mean over one provider's series was making a dimension named *liquidity* report available. Descriptive volume moved to its own `descriptive_provider_volume` dimension and keeps reporting `available`; `liquidity` is now `unavailable_by_contract` unconditionally.

## 2026-08-04 - Descriptive volume was not the problem and was not disabled
- Nine descriptive and analytical capabilities are **retained**: volume history, moving averages, provider-scoped relative volume, trend indicators, same-series anomaly detection, source-labelled comparison, research-only volume indicators, volume confirmation, and the turnover-tier screening score. Turning them off would have cost real utility and bought no safety — a mean over one provider's own series was never a claim about executable depth. What changed is that each now carries four mandatory warnings enforced structurally, not by convention.
- **`stock_analyzer.score_liquidity` is the judgement call.** It bands close × volume into tiers for screening, it is named for liquidity, and it is not a liquidity measure. It is classified `analytical_not_liquidity_dependent` and left computing: disabling it would have changed production ranking output, which this milestone is forbidden from doing, for a score that has never claimed tradable size. A reader who disagrees should reclassify it as `liquidity_dependent`, at which point the matrix shuts it and the ranking changes.
- **The unknown class is the mechanism, not a footnote.** A volume consumer absent from `CONSUMER_CLASSIFICATION` resolves to `unavailable_pending_classification`. Adding one therefore requires classifying it, which is what keeps the matrix true after everyone involved has forgotten why it exists.
- Nothing inherits. Generic fields (`volume`, `market_volume`, `official_exchange_volume`, …) raise rather than receive the verdict, and other providers get `contract_applies: false` with `volume_composition: unknown` — unqualified because nobody qualified them, **not** because VCI's verdict was copied across.

## 2026-08-04 - A candidate is a question list, not an address
- HOSE trading statistics are registered as a `future_qualification_candidate` in a **separate module** from `official_source_registry.py`. That registry gates the network, its `hose` entry is already `approved` for corporate-action notices, and registering trading statistics there would have been one JSON edit away from a scraper — in a milestone forbidden from acquiring anything.
- **No URL is recorded.** None has been observed and retained in this repository, and a plausible-looking route written from memory is a fabricated locator regardless of how right it feels. A future milestone must obtain the locator, not compose it. `assert_not_acquirable()` proves no approved source admits a trading-statistics document type, and a test adds one to the `hose` entry to prove the check fails when it should.
- Eight semantic questions are recorded and **all open**: matched volume definition, negotiated volume definition, relationship between matched and total volume, units and scaling, ticker-level availability, date coverage, machine-readable access, access and reuse terms. A source whose units and ticker coverage are unknown cannot qualify anything.
- Recorded as the **preferred currently identified** official authority path, not the sole theoretically possible authority. Nobody surveyed the alternatives, and claiming there are none would be a statement about sources this repository has never looked at.

## 2026-08-04 - Ninety-six fields, and none of them says put-through
- The composition question was answered by exhausting surfaces, not by finding one. The entire retained VCI corpus carries **18 distinct field names**; a token scan of the whole `vnstock` VCI adapter for put-through, negotiated, odd-lot, auction and total-volume terms returns **zero**; and the one unexamined surface — the price board, an endpoint `meta_sync.py` and `blacklist_sync.py` already call in production — returned **96 fields across 3 groups with no put-through, negotiated, block or odd-lot field among them**. `negotiated_inclusion` is therefore closed as `unavailable_from_observed_vci_surfaces` rather than left open for someone to probe again.
- **`matchType` is the aggressor side, not the trade method.** Reading `b`/`s` as "matched trade" would have been the exact name-based inference this work exists to prevent, and it would have looked like progress.
- **`accumulatedVolumeG1` equals `accumulatedVolume` exactly, and was refused.** A `G1` suffix implying a board segmentation plus a perfect equality is the most tempting artifact in the payload. The equality is equally consistent with "G1 is the whole" and with "VCB had zero of whatever G1 excludes this morning", and nothing on hand separates them — arithmetic balance without a field definition is not evidence.

## 2026-08-04 - One qualification, earned by four agreements and an outside authority
- `opening_auction_inclusion` is **qualified**. The board's `matchVolumeATO` 42,700, `matchPriceATO` 60,900 and `firstTimeMatchPrice` 02:15:00Z all agree with the retained VCB tape's first trade of the session — which satisfies `accumulatedVolume == matchVol`, i.e. it *is* the accumulator's opening entry. So the opening auction sits inside daily `v`.
- This needed a third qualification route, because **no first-party VCI definition of any field exists or was retained** and none is claimed. The route is `exchange_standard_term`: ATO/ATC are HOSE session codes defined by exchange regulation rather than by the provider, so the referent is fixed outside VCI. It is admissible **only** when a second independent field pins the same referent and a bounded reconciliation is exact — `qualify_dimension` requires `referent_pinned_by_independent_field`, and tests prove name-alone and reconciliation-without-pin both stay `unknown`. `EXCHANGE_STANDARD_TERMS` holds exactly two entries.
- That is a deliberate, stated deviation from the strictest reading of the brief, and it is load-bearing for nothing: downgrading it to `unknown` flips the terminal state to B and changes no gate, because every gate is already shut.
- **One auction leg does not speak for the other.** `closing_auction_inclusion` stays `unknown` — `matchVolumeATC` was 0 at the morning snapshot — and the roll-up `auction_inclusion` cannot be asserted directly nor published without naming which legs it covers.
- `liquidity_actionable` is a **constant** `False` in the contract builder rather than a computed field. There is no input combination that turns it on, because sizing against a volume figure requires knowing what that figure counts.

## 2026-08-04 - The evidence audit found a real gap and two phantoms
- **Real:** the pagination runner wrote a daily-bar raw artifact whose filename it never recorded, leaving 4 raw files reachable from no ledger. The runner now records `raw_artifact` and the existing ledgers were repaired by hash-matching. Every raw filename already embedded the first 16 hex of its own content hash, so the names are self-verifying and the repair could be done from the bytes.
- **Phantom:** the secret scanner flagged 2 findings that were prose — "no cookie, **authorization** header … was sent" and "non-**secret** parameters", both sentences in a report *about* not leaking secrets. Textual matching cannot tell a secret from a discussion of one; the scan is now structural, requiring the marker as a JSON key with a value that is not the redaction sentinel.
- **Nothing was deleted.** Three byte-identical groups exist because the lunch-halt tape was frozen, and each copy is its own run's reconciliation target; the one superseded in-directory attempt is now referenced as `superseded_attempt_artifacts` instead of removed. Deleting failure evidence to make a count look tidier is how the reason for a decision gets lost.

## 2026-08-09 - Shipping the qualified research lane exposed two real defects and caused a third
- **Goal:** the Phase 4B/4C/5A/5B/5D/5E qualified-research-lane commits (`7293f78`..`e98cd53`
  Producer, `b024895`..`693b375` Consumer, `d93a2fa`/`bd2859f` Dashboard) had never actually
  reached the served release — `worktrees/market-dashboard-main`/`main` carried no
  `qualified_research_brief` for any ticker. Ship it there, at the real 11-ticker production
  scope, additive-only, with no unrelated refresh.
- **First real defect, pre-existing:** `tools/operate_stocklookup.py` — "the one supported
  operator command" — never exposed `--include-historical-decision-analysis` /
  `--include-portfolio-risk-analysis` / `--include-historical-scaleout` /
  `--include-qualified-research-brief`, even though `export_ai_bundle.py` had supported all
  four since the commits above. They were only reachable by invoking the exporter directly,
  bypassing the supported command's verify/rollback/Consumer-validate gates. Fixed: the four
  flags are now wired through, tested (19 `test_operate_stocklookup.py` cases unaffected,
  still passing).
- **Second real defect, pre-existing, and the direct cause of a scope mistake:**
  `DEFAULT_TICKERS` also silently carried `VNINDEX`, contradicting its own comment ("kept
  identical to what the last successful export actually shipped") — the actually-served
  bundle's `tickers_requested` has never included it (`unproven_tickers: []`, not
  `["VNINDEX"]`). Requesting it by default tripped `preflight_derived_session_inputs` on a
  context package for a symbol outside both the shipped universe and this lane's target
  population (an index has no issuer). That gate failure was answered, wrongly, by running
  `--prepare-inputs` — which correctly rebuilt VNINDEX's package but also regenerated
  technical signals, focus analysis, and every real ticker's context package, and upserted
  `watchlist_history` in `vn_stock.db`, none of which the milestone authorized. **Fully
  reverted before any publication**: `vn_stock.db` restored from the run's own hash-verified
  pre-write backup (`181ebd7e…36a9`, matching the long-standing known-good hash), the four
  release artifacts restored from the run's own rollback point (matching the pre-incident
  hashes independently captured before any command ran). Root-caused and fixed at the source:
  `DEFAULT_TICKERS` no longer carries `VNINDEX`. The corrected rebuild (11 tickers, no
  `--prepare-inputs`) then passed `preflight_derived_session_inputs` on the first try,
  proving the fix — the real production inputs had been fresh the entire time.
- **Third defect, self-inflicted by the first mistake, caught before publication:** because
  `prepare_context_packages` runs *before* `export_bundle` rewrites `analysis_bundle.json`,
  and the runtime root's on-disk bundle was transiently a 3-ticker ad hoc pilot snapshot when
  the over-broad `--prepare-inputs` ran, the Consumer's context builder found no legacy-bundle
  entry for 9 of the 11 tickers and wrote every dependent section as
  `*_not_in_legacy_bundle`/`missing` into their `context_package` sub-blob — a real content
  regression, not a timestamp. Caught by a section-by-section diff against the live served
  bundle before any publish. Remediated by rebuilding context packages once, directly, now
  that the correct full-universe bundle was already on disk (not by widening scope again).
  Verified afterward: the top-level, dashboard-rendered sections were unaffected throughout
  (`financial_canonical` status identical for all 11 tickers across both mistakes); a
  section-level diff against the served bundle, with wall-clock-only fields stripped, showed
  zero remaining content differences beyond the intended additive research fields for HPG/VNM.
  One incidental finding: 4 of the 11 tickers' `context_package` sub-blob in the
  **already-shipped, currently-live** bundle carries this exact same `not_in_legacy_bundle`
  pattern — a latent, pre-existing defect in the ordinary daily pipeline's own sequencing,
  unrelated to this session, not investigated further here (out of scope; the corrected
  candidate does not carry it forward for those 4 tickers, but nothing was done to fix the
  live bundle's copy).
- **Why this belongs in DECISIONS, not just as a fix:** the failure mode generalizes —
  `--prepare-inputs` bundles five independent stages (candle scan, strategy, market scan,
  focus analysis, context packages) with no way to run one without the others, and
  `preflight_derived_session_inputs` checks freshness for whatever ticker list is passed,
  including symbols outside the real target scope. A wrong or stale default ticker list turns
  an unrelated symbol's staleness into an invitation to refresh everything. Before reaching
  for `--prepare-inputs` to satisfy a freshness gate, check first whether the tickers actually
  in scope are already fresh — this session's real ones always were.

## 2026-08-09 - A new capability gets a new section, not a retrofit of a load-bearing gate

- `risk_liquidity.py::evaluate_market_risk()` computes `realized_volatility`,
  `downside_volatility` and `maximum_drawdown` from the retained OHLCV series, but only
  inside a branch gated on the **generic** `price_adjustment == "qualified"` flag — which is
  always false market-wide, so these three fields have been `unavailable` in every
  production bundle since they were written. VCI's own price series (100% of every
  production ticker's retained window, verified against `dashboard-runtime/vn_stock.db`)
  carries a real, evidenced, provider-scoped verdict that already authorizes exactly this —
  `vci_direct_basis_pilot.SHADOW_PRICE_CAPABILITIES` names `vci_namespaced_historical_
  returns`/`vci_namespaced_technical_indicators` as available under a required label.
- The safe fix was not to change `risk_liquidity.py`'s gate. Retrofitting a load-bearing,
  already-shipped section's branching logic to key off a provider-scoped verdict instead of
  the generic one carries real regression risk for every existing consumer of `market_risk`'s
  exact shape, for a gain the alternative already provides: a new, separately namespaced,
  additive `qualified_market_observations` section computes the same class of statistic
  (return, volatility, drawdown) over the same data, correctly labelled provider-scoped and
  non-actionable, with zero risk to the existing section's output. `risk_liquidity.py` is
  unmodified by this milestone.
- **Corollary: this is not permission to widen the generic gate.** `price_basis_verified`/
  `volume_basis_verified` stay exactly what they were. The new section's `is_actionable`/
  `liquidity_actionable` are hardcoded `false` constants, never derived from either the
  generic flag or the provider-scoped one — see `market_basis_capability_registry.py` and
  `docs/qualified_market_observations_contract.md`.

## 2026-08-09 - The generic-unlock route is named, not executed, in a capability-activation milestone

- Pillar B (official corporate-action lineage expansion) was selected as the highest-leverage
  next generic-unlock route, unchanged from the existing roadmap: it is already owner-approved
  and active (B1), with a concrete next bounded input already on record — an official VSDC
  ex-date notice for SSI, the same acquisition pattern already exercised for VCB on
  2026-08-08.
- **That acquisition was not performed in this milestone.** A live external network request
  is a materially different class of action from the source/test/documentation work this
  milestone otherwise consists of, and identifying a legitimate entry URL first requires its
  own bounded offline discovery pass over already-retained SSI evidence — a distinct,
  separately-scoped piece of work, not a byproduct of capability-registry construction.
  Recorded here as a decision, not a gap: the next session doing Pillar B acquisition work
  should start from "acquire the SSI VSDC ex-date notice using the established B2/B3
  pattern", not re-derive the route.

## 2026-08-09 - "Closed" described the evidence tested, not every surface a provider exposes

- The 2026-08-04 finding that KBS "does not currently provide admissible scope evidence"
  was correct for the one endpoint it tested (`data_day`, the daily chart) and was written,
  and later cited, as if it covered KBS generally. It did not: KBS's price board
  (`stock/iss`) and intraday trade tape (`trade/history/{symbol}`) are two different,
  already-installed endpoints on the same host that nobody had examined. Both existed in
  the installed `vnstock` 4.0.4 library the whole time; finding them cost zero new
  dependencies and zero provider exploration beyond what was already integrated.
- Testing them (three tickers, one session, 2026-08-07) found real, new, `empirically_
  deduced` evidence: KBS's daily volume figure is now *decisively* known to exclude
  put-through/negotiated trades and include continuous-matched and auction-cleared trades,
  via an exact, zero-residual reconciliation of the full intraday tape against the price
  board's accumulator, repeated identically for all three tickers.
- **The lesson generalizes beyond this one finding.** A "provider has no admissible scope
  evidence" verdict is only ever as broad as the surfaces actually tested. Before treating
  such a verdict as closing a provider entirely, check what was tested, not just what the
  verdict says. VCI's own composition finding (2026-08-04, "Ninety-six fields, and none of
  them says put-through") is not affected by this correction — that finding already names
  the specific surfaces it exhausted (all 96 fields across every VCI endpoint reachable),
  which is the standard this KBS finding was held to as well before being written down.
- See `kbs_trade_scope_qualification.py` and
  `operations-review/kbs-trade-scope-qualification-20260809/`.

## 2026-08-09 - A third-party library's time-window heuristic is not a first-party field

- `vnstock`'s KBS intraday tape reports an empty `side` field on exactly the trades a call
  auction produces (no directional aggressor, which is structurally why continuous trades
  carry a side and auction-cleared trades do not). The library's own
  `core.utils.transform.process_match_types` then labels the *first* such empty-side row
  each day `ato` and the *last* `atc`, by matching against a fixed clock window
  (9:13-9:17 / 14:43-14:47) — a heuristic the library author wrote, not a field KBS's API
  returns.
- The distinction mattered for a real decision: `kbs_trade_scope_qualification.py` qualifies
  one combined `auction_inclusion` dimension, deliberately never splitting it into separate
  `opening_auction_inclusion`/`closing_auction_inclusion` verdicts the way VCI's contract
  does. The *inclusion* fact (side-less rows are part of the reconciled total) rests on
  first-party field values (the raw `LC` field, genuinely empty) and needs no heuristic;
  which specific auction a row belongs to would rest entirely on the library's guess, and
  this repository's qualification tiers do not have a tier for "a third party's plausible
  guess" (`evidence_qualification_tiers.classify_field_semantics`'s own doctrine: a
  contextual or inferred reading does not qualify).
- A second candidate corroboration was checked and set aside for the same reason applied
  honestly: the price board's `PMQ`/`PMP` ("previous match qty/price") fields matched the
  put-through print's quantity and price exactly for HPG, only on price for VNM, and not at
  all for VCB. Inconsistent evidence is not evidence with caveats attached; it was not used.

## 2026-08-09 - One official close is a namespace observation, not a historical series

- The bounded official-only locator pass found and retained HOSE's Annual Report 2024 from
  `staticfile.hsx.vn` through the approved acquisition path. Its own table labels make HPG's
  31 December 2024 `Closing Price` and `VND Thousand` scale explicit: 26.65, i.e. 26,650
  VND/share. That is enough to record a first-party, exact-session raw-price *pilot
  observation*. It is not enough to claim an exchange-wide history: the report contains no
  deterministic daily ticker route, no pre/ex/post event window, and no stated non-revision
  policy. The verdict is deliberately `RAW_AS_TRADED_PRICE_AUTHORITY: PARTIAL`.
- The read-only frozen VCI row for the same HPG date is 19,830 VND/share. The two values are
  preserved as `official_raw_as_traded_pilot` and `provider_adjusted`, with their observed
  ratio recorded but no transformation inferred. A non-equal pair proves that merging would
  destroy information; it does not identify a corporate-action factor. The registry refuses
  a nearest-date lookup and never falls back to VCI/KBS for a raw-required query.
- The same first-party PDF explicitly labels `Order matching` and `Put-through`, but the
  decomposed table is foreign-investor annual activity by security type, not all-market
  ticker/session volume. It cannot be numerically reconciled to VCI daily `v`, so it changes
  no VCI category state. This is a source-granularity blocker, not a reason to infer an
  aggregate composition from a column position or approximate equality.

## 2026-08-09 - A daily exchange summary is not automatically daily ticker statistics

- A bounded official-only locator pass retained two HOSE `TỔNG HỢP THÔNG TIN GIAO DỊCH` / Trading
  Summary PDFs. The retained bytes are authentic, stable, date-labelled first-party documents;
  that establishes artifact reproducibility, not the requested data schema.
- Both samples call their index figures `Closing value`. They contain no individual-equity
  close/last/reference/open/high/low/average field. HPG appears in selective top-five volume
  tables, but this supplies no price. The VNM-labelled retained sample contains no VNM equity
  ticker-session observation; a covered-warrant code is not evidence for its underlying equity.
- The reports explicitly label `Order matching`, `Put-through`, and `Total`, but only for the
  full market. Their ticker tables are top-five volume lists without ticker-level trade-type
  components. Do not allocate market totals to a ticker, infer the omitted ticker universe, or
  compare those aggregates to VCI daily volume.
- The correct terminal status is
  `OFFICIAL_DAILY_TICKER_SESSION_STATISTICS_ROUTE_NONCONFORMING_SUMMARY_ONLY`. It replaces the
  less precise “route unavailable” gap, but opens no capability: the one-date HPG annual-report
  raw observation remains separately namespaced, historical raw stability is blocked, and no
  raw/adjusted factor is inferred.

## 2026-08-09 - Select a commercial raw-history candidate before more data probing

- The bounded authority shortlist is: HOSE's licensed Market Data Feed, FiinGroup API
  Datafeed `/Market/GetHoseStockv2`, and the already-integrated VCI/KBS paths. The third is
  rejected for raw authority without a new request because both active verdicts are adjusted;
  the public HOSE fee schedule proves a commercial product exists but not its required field
  contract.
- **Selected candidate: FiinGroup API Datafeed `/Market/GetHoseStockv2`, pending owner source
  acquisition.** Its public field documentation explicitly distinguishes `ClosePrice` from
  `ClosePriceAdjusted` and `RateAdjusted`, names `Ticker`/`TradingDate`, and separately names
  total order-matching and put-through volumes/values. That is materially different evidence
  from a broker series that happens to match an exchange number.
- Documentation alone is not source activation. Before any pilot, the agreement must confirm
  that the unadjusted fields are raw/as-traded and non-rewritten, document point-in-time/revision
  semantics and units, specify auction/odd-lot treatment, and allow immutable evidence retention
  plus the intended production-use boundary. No credentials were searched for beyond the local
  environment-name check; none were present, and no commercial endpoint was called.
- The selected route is for a future `market_history.raw` namespace. VCI/KBS stay separate
  provider-adjusted history; qualified corporate actions reconcile the two only after a retained
  raw pilot passes. `RAW_PRICE_AUTHORITY` remains `PARTIAL`, volume authority remains blocked,
  and `OWNER_SOURCE_ACQUISITION_DECISION` is the next canonical milestone.

## 2026-08-09 - FiinGroup is an external dependency, not an adapter-shaped assumption

- The configured-access audit checked only project configuration/adapters, credential naming
  conventions, environment-variable names matching `FIIN`/`DATAFEED`, and source/license notes.
  It found no FiinGroup access or agreement. No value of any secret was read or logged, and no
  commercial request was made. `FIINGROUP_ACCESS_STATE` is therefore
  `OWNER_ACQUISITION_REQUIRED`, not “unusable” and not implicit authorization.
- `LICENSE_AUTHORITY` is `OWNER_CONFIRMATION_REQUIRED`. Public field documentation does not
  establish historical API entitlement, local evidence retention/cache, derived analytics,
  internal production, Dashboard display, or redistribution rights. Those rights, plus
  raw/non-rewrite/as-of, units, auction and odd-lot semantics, are contract conditions before
  the first payload can qualify.
- The complete minimal request is FiinGroup API Datafeed `/Market/GetHoseStockv2` only, for
  HOSE HPG/VNM daily history from 2024-01-01. It names no companion module and excludes
  fundamentals/news. Its acceptance pilot starts with the 26,650 VND HPG 2024-12-31 official
  anchor, adjacent dates and an existing corporate-action window; it retains redacted request
  metadata and hashed bytes only after access is provisioned.
- The market-data track is `WAITING_EXTERNAL_ACCESS`. Procurement does not block all work:
  the already-canonical `P1.5_TICKER_CAPABILITY_TRUSTED_TICKER_MATRIX_BUNDLE_ATTACHMENT` is
  the independent next implementation milestone. No valuation or market-data work starts
  automatically from this decision.

## 2026-08-09 — Cohort 2 issuer evidence is a bounded annual-facts expansion

- **Decision:** admit only the enumerated QNS and Novaland issuer domains (apex and `www`) for
  the two locator-backed FY2024 requests. No cloud wildcard, mirror, pagination, or generic
  issuer crawl is permitted. The known Novaland document size raises the response ceiling to a
  still-bounded 32 MiB.
- **PNJ:** retained Note 19 presents only short-term borrowings. The existing debt derivation
  requires exactly labelled current and non-current borrowings/finance leases for the same
  reporting period; liabilities, obligations, and a manually entered total cannot substitute.
  PNJ remains 4/5.
- **Outcome:** QNS's exact URL was a 404 and POW remains locator-blocked. NVL's one retained,
  audited FY2024 consolidated issuer filing supplied all five verified annual facts. Its debt is
  the explicit `36,978,198,251,788 + 24,587,656,403,178` sum; the VND facts are historical-only
  and non-actionable. FPT was not revisited. HPG, VNM, PAN, PVD and all market-data authority
  boundaries are unchanged.

## 2026-08-09 — Historical analytics are evidence projections, not market research activation

- The HPG/VNM/PAN/PVD/NVL corporate cohort may receive deeper analytics only from the existing
  qualified annual, consolidated canonical-fact path. Derived ratios retain source identities
  and fail closed for incompatible scope, currency, unit, missing fields and denominators.
- PVD's USD facts remain USD. The cohort artifact exposes local states and dimensionless ratios
  only, forbids FX conversion, absolute monetary comparison, ranking and recommendation.
- Consumer and dashboard publication are deferred because this milestone changes no market
  authority and no runtime artifact. The next candidate is
  `QUALIFIED_HISTORICAL_COMPARATIVE_RESEARCH_AND_AI_UX`, contingent on a Consumer audit.

## 2026-08-09 — Comparative research is a qualified-cohort observation, not a ranking

- HPG, VNM, PAN, PVD and NVL are a fixed **qualified cohort**, not an assumed peer group. The
  comparison projects existing qualified analytics, source identities, and deterministic
  positions without calculating another fundamental formula or introducing a weighting model.
- Cross-sectional historical comparison is available; multi-period trend remains insufficient.
  PVD remains USD, and the contract excludes absolute monetary comparison and FX conversion.
- Consumer and Dashboard may present the Producer section verbatim only. AI may explain an
  exact supported comparison but may not create recommendation, valuation, target-price,
  liquidity, expected-return, sizing, allocation, or investment-ranking claims.
