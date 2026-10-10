# Portable research case lifecycle and provenance correction V1

Milestone RESEARCH_CASE_LIFECYCLE_PORTABLE_ACCEPTANCE_V1; verified starting main
`6fcddb95d1cca3819c6bb67429cfe84d1ba0a3a0` (PR112; all four post-merge jobs PASS 38047543681).
Owner PROGRAM_LEAD_CONTINUATION_AND_STANDING_DELEGATION (2026-10-10) authorizes bounded
selection/admission, recoverable fixes, validation, commits and safe PR continuation.
Native admission records released workflow COMPLETE, one ACTIVE scope and empty queue.
Separate exact-HEAD merge, Daily/deploy/production runtime/store writes, trust promotion,
destructive/visibility/outside-program gates remain. One writer, dedicated checkout.

The actual expanded PR112 baseline has 61 historical-input-dependent failures. Its source
move was covered by parity and synthetic temporal tests but had no portable full review/case
lifecycle acceptance. Select that demonstrated correctness gap instead of another root slice.
The entire meaningful chain is decision packet → evidence-bound draft → recorded human review
→ workbench case creation → immutable durable updates/restart/trace → descriptive learning.

Portable inputs are fifteen fictitious FIX identifiers and TEST_FIXTURE source identities,
not market/issuer evidence. The existing thirteen-member panel invariant remains unchanged;
its labels only drive test branches. Every draft uses fixture=True and TEST_FIXTURE identity;
every later update uses fixture=True, TEST_FIXTURE kind and fixture: source identity. Temporary
stores are supplied under pytest tmp_path. Default retained loaders are explicitly forbidden.
No model is called and no real human draft/review, case or production observation is created.
These inputs do not relabel or replay the historical 523-member cohort.

Five new regressions fail on released main: changing a valid draft after review (including
revalidation under the same identity), altering reviewer payload with the recorded identity,
modifying caller-owned source objects after T0 creation, and stale ready status after changed-draft revalidation. The existing recorded policy
requires exact validated draft/recorded qualifying review and immutable cases:
[2026-08-22 workbench decisions](DECISIONS.md), corresponding [state invariant](STATE.md).
The same ACTIVE native notes explicitly extend the initial test-only plan for these recoverable
violations; no state/history/eligibility/authority rule is silently changed.

Fix only two existing source boundaries. Workbench create_case compares the supplied draft
with the stored validated body, the supplied review with the stored review body, and that review's
draft with the current draft. Readiness also requires the recorded review draft to match the current validated body. A changed draft needs validation and a fresh recorded review.
At create_research_case, detach all nested source objects before computing the existing identity.
Valid serialized cases/identities, schemas, validator policies and allowed review states stay
unchanged. Existing failure codes remain; no source-data trust or investment authority is granted.
No new engine/provider/framework, root migration or retained artifact/hash rewrite.

Acceptance includes complete happy paths, mixed cohort/session refusal, counter-evidence,
numeric/authority/investment draft rejection, current review gates, recovery with fresh review,
detached T0, temporal order, source registration, tamper/duplicate/writer lock, restart/claim trace
and fixture exclusion. A rehashed event with a missing parent must still fail chain validation.
Compare valid JSON/identities with released source and run affected existing regressions,
native/layout/offline/active controls, installed core tiers and four hosted jobs.
Root layout remains 519 files / 501 Python / 9 directories; no production runtime acceptance.

Historical replay retains the exact PR112 pinned-input reopening gate. Portable fixtures do not
prove historical replay, the real operating manifest, live AI/human review or production stores.
Fiscal/calendar/publication, strict shares/valuation/PIT evidence limits remain unchanged.
[Acceptance and durable next action](internal/RESEARCH_CASE_LIFECYCLE_PORTABLE_ACCEPTANCE_20261010.md).
