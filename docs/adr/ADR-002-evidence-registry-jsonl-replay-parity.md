# ADR-002: Phase 2D JSONL Replay and Parity Design

## Status

Accepted design, implementation deferred. Baseline: Producer `main@b9ed366`; Evidence Registry MVP is read-only.

## Decision

Replay existing files into an **isolated temporary SQLite database**. SQLite is the smallest target: embedded, transactional, disposable, available with Python, and adequate for a single replay plus read-only dual-query comparison. PostgreSQL is deferred: it adds service lifecycle, credentials, migration, and concurrent-operation concerns that are not needed before authority cutover.

## Exact replay sources and order

1. `data/official-evidence/manifest.json`: parse object; validate schema; replay `records` in original array order while assigning `source_ordinal`, then index by `evidence_id`.
2. `data/financial-observations/observations.jsonl`: parse nonblank UTF-8 lines in line order; replay by `observation_id`.
3. Citation JSONLs, in this fixed file order and then line order: `qualification_citations.jsonl`, `share_basis_citations.jsonl`, `market_price_citations.jsonl`, `ebitda_component_citations.jsonl`; index by `citation_id`.
4. Recompute canonical/direct and derived lineage from the replayed observation and citation relations only, using the same entity profiles: HPG/VNM `corporate`, VCB `bank`. Derived rows have no independent source authority.

The replay input fingerprint is the ordered tuple `(relative path, SHA-256, nonblank line count or manifest record count)`. A different fingerprint starts a new replay; it never mutates the legacy file.

## Identity and idempotence

| Entity | Stable key | Duplicate policy |
|---|---|---|
| Document | `evidence_id` | Same complete payload/hash: idempotent; otherwise blocking conflict. |
| Observation | `observation_id` | Same complete payload: idempotent; otherwise blocking conflict. |
| Citation | `citation_id` | Same complete payload: idempotent; otherwise blocking conflict. |
| Registry fact | `ticker + period + metric + source + citation_id/observation_id` | Deterministic projection; no independent write. |
| Derived lineage | canonical metric + period + sorted input observation IDs + evidence IDs | Recomputed only; never replayed as authority. |

A superseding citation is accepted only when it names every replaced citation ID, retains the same identity and value, and its evidence document passes hash verification. Multiple successors, partial chains, value changes, or cross-metric supersession are blocking conflicts. Dangling document/observation references, malformed JSON, unsupported share identity semantics, document-hash mismatch, and a bank `customer_deposits -> total_debt` relation are fail-closed: the affected fact is not promoted and the parity run fails.

## Parity contract

The temporary store must reproduce legacy document, observation, citation, direct-fact, and derived-lineage counts; identity sets; raw values; document hashes; qualification status; and all document/citation/observation/supersession relationships. It must also prove HPG corporate, partial VNM, and VCB bank facts coexist without changing sector semantics.

Allowed differences: temporary storage primary keys, checkpoint/journal fields, ingestion timestamps, physical ordering where stable identity order is preserved, and explicit `replay_*` metadata. Blocking differences: any source identity/value/hash/status/relationship mismatch; missing or extra authoritative fact; changed derived input set; altered VNM partial state; deposits mapped to debt; enabled VCB EV/EBITDA, Net-Net, or corporate FCFF.

## Checkpoint, resume, rollback, recovery

The temporary store maintains a replay journal keyed by `(run_id, source_path, source_fingerprint, source_ordinal)`. A committed journal row makes an identical item idempotent on resume. Checkpoints occur only after each source file has committed. Resume rejects a changed source fingerprint. Rollback drops the isolated temporary database and journal; legacy files are never rewritten. Recovery preserves the failed temporary database and a machine-readable failure report for diagnosis, then starts a fresh isolated run after inputs are repaired through their normal append-only process.

## Smallest Phase 2D implementation slice

Create a temporary SQLite schema, replay the fixed sources, and run read-only legacy-vs-store queries against the parity specification. No dual-write, source-of-truth change, scheduler, API, migration, or production cutover is permitted.