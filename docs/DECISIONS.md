# Decisions

> **Superseded entries are marked in place.** The three 2026-08-03 P1H/P1I/P1J entries
> below record counts and share anchors that were never measured or were wrong; each
> carries a SUPERSEDED note pointing at the P1J.1 entry that corrects it. They are kept
> rather than deleted so the record of what was believed, and when, stays intact.

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
