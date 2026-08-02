# Decisions

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
- A corporate action may qualify for price continuity without qualifying a share transition, but still requires direct provider event identity plus official citation/hash, ex-date, and ratio lineage.
