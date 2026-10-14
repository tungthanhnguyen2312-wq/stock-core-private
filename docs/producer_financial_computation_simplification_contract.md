# Producer financial computation simplification

Owner program `STOCKLOOKUP_PRODUCER_DEEP_SIMPLIFICATION`, 2026-10-14.
Native lane `STOCKLOOKUP_PRODUCER_DEEP_SIMPLIFICATION_20261014` is Codex-owned,
based on PR145 main `f582bfab80dac6d206083a0bd4a0ba57db199691` after five
successful post-merge Producer CI jobs. Conditional source push, PR and merge
are authorized. Daily, production publishing/writes, sealed-evidence changes,
authority promotion and automatic successors remain outside this scope.

## Existing owners and invariants

Six existing financial/valuation implementations retain their locations and
public call signatures. Issuer-local plain dictionaries borrow qualified row
references for the duration of one construction. There is no cross-call cache,
new framework, root shim, module movement or new analytical method.

Financial V2 keeps its strict lineage/provenance gate, normalized period semantics,
issuer/provider/scope/currency/scale/statement key and separate cross-statement
representation key. Equal repeated observations still select the minimum fact ID;
conflicting values exclude the period. The feature store separately retains its
truthy lineage gate, literal period semantics, source-file key and last-row winner.
Neither qualification rule is substituted for the other.

The shadowed annual builder/helper chain is removed from the active quarterly
feature module. Historical implementation remains in Git. Active quarterly fields,
including their existing method strings, duration uncertainty, blocked TTM and
Piotroski, retain their previous outputs. No annual inference is enabled.

Scoring and ranking use the same inclusive empirical rank. Valuation's three peer
joins keep their existing eligibility/basis/cohort keys, minimum sample count,
median and tie-aware rank. Pools are prepared once; nonfinite/unsupported scoring
inputs retain the comparison-scan fallback. Sector, currency, scale, period,
scope, source and issuer distinctions are preserved. Confidence never becomes
investment quality; no authority, recommendation, sizing or PIT use is widened.

## Acceptance and resource limits

The synthetic baseline records exact released-source hashes and 32 complete
output hashes across corporate/bank/securities, shuffled rows, duplicates,
conflicts, unknown semantics/provenance, empty and undersized cohorts, and all
three peer joins. Additional tests cover no stale cache, qualification passes,
ties, signed zero, nonfinite fallbacks and active quarterly labels. Existing
financial consumers, structural/import/frozen checks and hosted Producer CI gate
the exact candidate and post-merge source identities.

On isolated offline fixtures, engine/store selection traverses each issuer's rows
once instead of repeatedly; scoring sorts each feature pool once instead of
scanning it for every axis and output. Peer medians and sorted pools are reused.
Measurements include wall time, peak Python allocation, source identity and exact
output hashes. Issuer indexes trade a small bounded allocation increase for fewer
scans. These measurements do not assert Daily end-to-end speed or peak-memory
improvement. Root count and genuine compatibility cycles need not change.

Frozen source/launcher manifests, retained artifact identities, Owner entrypoints,
serialization settings and Consumer/Dashboard schemas are unchanged. The pinned
Owner handoff verifier requires its own governed contract decision before a future
streaming revision; it is a recommendation only, not another admission here.
