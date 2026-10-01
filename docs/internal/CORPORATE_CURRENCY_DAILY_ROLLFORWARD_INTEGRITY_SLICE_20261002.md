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
