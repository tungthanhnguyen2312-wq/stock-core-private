# Decisions

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
