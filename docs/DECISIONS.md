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
