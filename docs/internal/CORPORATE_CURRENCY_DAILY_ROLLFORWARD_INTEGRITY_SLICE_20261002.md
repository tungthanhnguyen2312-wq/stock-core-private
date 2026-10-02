# Daily corporate rollforward: retained integrity implementation slice

Status: IMPLEMENTATION_SLICE_VALIDATED; full milestone remains NEXT/incomplete. This supersedes the inspection-only status of the earlier continuation checkpoint only for the retained acquisition/materialization boundary. No completion or authority promotion is claimed.

Implemented in official_corporate_event_incremental_acquisition.py:

- verify_successful_acquisition binds the exact successful dated manifest to both source artifact identities and capture lists; source modules replay all raw SHA256 and self identities offline.
- Capture paths must resolve inside the raw store. Failed/missing sessions and manifest/source mismatch fail closed. No fetching or fallback occurs in verification.
- Materialization verifies retained sources before deriving context. It publishes complete temporary bytes via exclusive hard-link creation, never replacing a destination. Matching existing content is reused without byte or modification-time change; unexpected content fails CURRENT_CONTEXT_IMMUTABLE_CONFLICT. Temporary files are removed even on conflict.
- Missing materialization rebuilds offline without modifying raw captures. Successful source artifacts and manifests retain their previous format; context identity is unchanged.

Validation:

- python -m pytest tests/test_official_corporate_event_incremental_acquisition.py tests/test_official_acquisition_budget.py -q: 55 passed in 11.69 seconds.
- New cases cover both sources' missing/corrupt raw captures, manifest source/session mismatches, successful verification, matching context byte/mtime reuse, missing context recovery/raw byte and mtime preservation, conflicting context preservation and temporary cleanup. Materialization fixtures prohibit fetch calls.
- PR37 retained successful acquisition 2026-10-02 verified offline: 31 captures, attempt identity sha256:c32b0d39dd88896c78d328dc80aa33ee4c5aee7025743d8a361980c0794c17c0.
- Existing context reused without rewriting: current_official_event_context:6bc4608b7d2b3f1d9a414ddeed383e56c658baec2d6400677a6de6a0cf23e5f8. Coverage remains 186 observations / 174 names. No new HTTP or production Daily.
- py_compile and git diff --check passed. Roadmap --check: drift PASS, dirty-worktree warning reflected the implementation edits before committing.
- R4 160-driver/153-name replay, full offline Daily, dual-time/T0 proofs, Producer CI-equivalent and PR CI have not been run for this slice.

Remaining implementation, not an external blocker:

1. Add the one-invocation corporate rollforward result and bounded acquisition/reuse policy; actual VN knowledge time independent of target market session.
2. Integrate after valid exact-session snapshot, before corporate consumers. Propagate explicit selected identity/bytes through canonical Daily.
3. Implement frozen-market versus current-research overlay lanes, fix completed registry optional-field loophole, and remove authoritative latest lookups. Preserve missing historical optional fields.
4. Add civil/knowledge-date overlay namespace and explicit brief/dashboard consumption without posture or T0 mutation.
5. Complete owner 30-case matrix, retained R4 acceptance and full offline canonical Daily; CI selection; required docs/contracts and truthful roadmap COMPLETE.
6. Push PR, validate CI, merge, sync main, then perform owner ten-question bottleneck ranking and useful subsequent milestone.

Main remains c96c95ca4826709663b4788aab6edc1481e36229. Branch remains feature/corporate-currency-daily-rollforward-20261002 atop inspection checkpoint dcb2fe21d7475a08511f671f642444af31461be8. No historical registry, decision packet, prospective case, runtime publication, or posture was changed. Authority effect remains NONE / CURRENT_RESEARCH_EVIDENCE_ONLY. Standing autonomous release authorization persists.


## Continuation implementation: rollforward selection result

The next implementation commit adds corporate_currency_rollforward.py and its offline tests. It is not wired into Daily yet; the full milestone remains incomplete.

CorporateCurrencyRollforwardResult is a frozen dataclass carrying immutable receipt bytes, captured current context bytes, and a separate frozen-market selection copy. Consumers can obtain independent decoded values without changing the result or consulting latest. rollforward verifies and reuses the exact current civil-date SUCCESS, recovers missing materialization, or invokes the existing bounded acquisition engine once. Explicit prior-descriptive fallback requires a caller-provided governed maximum age; absent policy disables fallback. Prior source is explicitly stale. Corrupt current SUCCESS fails locally without refetch or silent fallback. Live acquisition refuses a historical injected civil date; knowledge observation advances to actual completion time after a real acquisition.

Receipt includes both temporal lanes, target session and actual knowledge observation/date, attempted versus reuse/recovery/failure action, verified selected source/context/byte identities and portable paths, current failure attempt identity/path, resource counts/policy identity, prior reference, age/freshness, historical-use prohibition, and authority NONE / CURRENT_RESEARCH_EVIDENCE_ONLY. No decision/posture fields are generated.

Validation: 69 focused tests passed (14 new rollforward cases plus the previous 55 acquisition/budget cases). Compile and diff checks passed. The helper reused real retained PR37 evidence with acquisition explicitly forbidden: exact attempt c32b0d39dd88896c78d328dc80aa33ee4c5aee7025743d8a361980c0794c17c0, exact context 6bc4608b7d2b3f1d9a414ddeed383e56c658baec2d6400677a6de6a0cf23e5f8, 31 verified captures, 3,216,925 retained bytes, 186 observations /174 names. No network, new evidence, raw rewrite, production Daily, registry, T0, product, or posture mutation.

Exact next code action: integrate rollforward once inside canonical_post_close_pipeline.acquire_and_materialize after snapshot validation and before independent components; explicitly pass result into canonical_daily_operation and enrichment. Bind completed registry's actual frozen optional selection separately, keep missing historical selections absent, and add knowledge-date overlay output/product consumption. Then complete full dual-lane offline Daily, registry and R4 acceptance, CI coverage/suite, docs closeout, PR release and post-merge bottleneck ranking. No PR or new CI run exists yet; main remains c96c95ca4826709663b4788aab6edc1481e36229. Execution capacity checkpoint; no external blocker and no approval request.


## Large-program continuation: canonical seam and frozen registry

Owner direction now is MARKET_DATA_PIT_FOUNDATION_AND_DAILY_OPERATIONALIZATION_V1. It replaces the narrow continuation queue. Release A remains Corporate Daily rollforward completion; do not start a growing PIT stack atop unreleased Release A. After validated Release A merges, create a fresh dedicated branch/worktree from verified new main for prospective accumulation and market-only eligibility/replay. The complete owner instructions remain the execution scope, including all authority dimensions, HOSE/HNX/UPCoM feasibility, prospective universe/action/factor retention, anti-look-ahead tests, feasibility dossier and strategic roadmap rebaseline.

This implementation continuation adds:

- canonical acquire_and_materialize invokes rollforward once after valid exact-session coverage and before independent Level-2 work when the canonical flag is enabled. Ordinary canonical orchestration passes the flag; the historical compatibility path does not. Result passes to enrichment and the final operation record receives the portable receipt.
- Enrichment retains a content-addressed current-corporate-knowledge-overlay-v1 sidecar under acquisition civil date. It uses captured context bytes, carries its own identity, is non-voting and explicitly forbidden for historical use. It is separate from the market-session decision namespace.
- Completed registry optional selections now come from the actual stored session selection, verified against the full frozen lock and self content hash. Missing historical optionals remain missing; newly discovered optional contexts are not backfilled. Registry bytes are unchanged on reuse.
- Completed-session corporate enrichment reads actual frozen optional paths. Corporate axis output moves from the shared retained path to the session enrichment path. Generic historical context discovery is bounded to directories no later than the target session; missing eligible context remains unavailable.
- Malformed acquisition manifests are caught inside the local rollforward failure boundary with zero retry/acquisition.

Validation completed:

- Combined canonical Daily, Level-2, rollforward, acquisition and budget non-retained selection: 146 passed /9 deselected in 28.78 seconds (before the final malformed-manifest case; that case subsequently passed).
- Updated post-close/rollforward non-retained selection: 80 passed /7 deselected in 4.93 seconds. This includes exact snapshot -> one rollforward -> Level-2 ordering; corporate unavailable result does not stop triage; immutable optional registry reuse/tampered lock rejection; historical discovery cutoff; separate knowledge-date overlay with frozen packet bytes unchanged.
- Level-2 selection independently: 29 passed /3 deselected.
- Compile and diff checks passed during implementation.
- A broader post-close run had seven missing retained-fixture setup errors. The working-dates test test_omitted_session_without_working_dates_fails_closed failed with FUTURE_SESSION instead of PROVIDER_EVIDENCE_UNAVAILABLE. It was reproduced unchanged on main c96c95c (same assertion); baseline, not fixed by this work.

Release A remains UNRELEASED/incomplete. No PR, merge, new main CI, production Daily, official HTTP acquisition, runtime publication, registry change, T0 mutation or authority promotion occurred. Main remains c96c95ca4826709663b4788aab6edc1481e36229. Current branch retains the earlier commits dcb2fe2 -> b3fa6b9 -> a28c0d8; this continuation is a subsequent coherent implementation commit. No external blocker prevents remaining engineering.

Exact next code actions:

1. Finish invocation selection binding for NEW sessions and remove residual rediscovery from the authoritative consumers; preserve exact historical knowledge cutoff semantics, including timestamp-level rather than directory-date-only proof.
2. Project the knowledge overlay into a separate current explanatory Corporate Intelligence axis/driver view and final brief/dashboard current product. Do not change a completed operation/T0 identity or posture. Current sidecar alone is not proof of user-facing consumption.
3. Complete full offline canonical Daily propagation and corruption/resume assertions, retained PR37 R4 acceptance (160 drivers /153 names), historical T0/hash proofs, CI guarding, and required contracts/docs/roadmap closeout.
4. Release A via validated PR/CI/merge/main sync. Then continue the large mission on fresh main/worktree: reuse R7 baseline once; operationalize prospective market/universe/action/factor continuity, implement market-only eligibility using existing replay machinery, characterize official historical source/right gates, report actual eligible windows or exact exclusion reasons, and rebaseline the roadmap. Do not claim PIT/raw/universe/factor/execution authority from this wiring.
