# Decisions

## 2026-08-03 - P1H Current Share Basis and Valuation Readiness Activation
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
