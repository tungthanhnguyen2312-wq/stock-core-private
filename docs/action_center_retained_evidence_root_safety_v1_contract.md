# Action Center retained-evidence root safety V1

Milestone `PERSONAL_ACTION_CENTER_QUALIFIED_DECISION_SURFACE_V1`, safety wave
`PERSONAL_ACTION_CENTER_QUALIFIED_DECISION_SURFACE_V1_S1_RETAINED_ROOT_SAFETY`.
Base: wave R1 checkpoint `267cf024` ([monetary-unit integrity](portfolio_monetary_unit_integrity_v1_contract.md)).
Owner pre-live-Daily safety exception, 2026-10-17. Authority effect NONE.

## Defect

The Owner workflow (phase 8, `tools/run_owner_daily.py::materialize_action_center`,
unchanged) passes the Producer checkout to
`personal_investment_decision_action_center.evaluate_from_retained_artifacts`.
Every evidence reader in that resolver used `repo_root/operations-review`. That
includes the latest completed session, the Integrated Decision, the descriptive,
sector-leadership and coverage-disposition artifacts, the previous descriptive
session, the governed sector snapshot, and the private portfolio and quant-risk
evaluations.

With the qualified workspace profile, the Daily writes that evidence under the
profile's `retained` role. The T: Producer checkout has no
`canonical-post-close-v1`. Phase 8 would therefore report `PARTIAL` with
`INTEGRATED_DECISION_ARTIFACT_NOT_RETAINED_FOR_SESSION`. This was reproduced read-only
for 2026-10-16.

## Rule

`retained_evidence_root(repo_root)` is the single resolution point. Every resolver
reader uses it.

- **Qualified profile.** `runtime_paths.workspace_profile()` re-qualifies the
  profile: absolute, non-redirected roles on the observed hot volume. Then:
  - `repo_root` must be the profile's Producer role
    (`ACTION_CENTER_REPO_ROOT_IS_NOT_THE_QUALIFIED_WORKSPACE_PRODUCER`).
  - A configured `STOCK_LOOKUP_RETAINED_EVIDENCE_ROOT` must equal the retained role
    (`RETAINED_EVIDENCE_ROOT_CONFLICTS_WITH_QUALIFIED_WORKSPACE`).
  - An unqualified profile refuses before any read.
  - There is no fallback to C:, to the checkout, or to a copy.
- **No profile.** The legacy contract of
  `daily_execution_environment.resolve_roots` is unchanged: the configured retained
  root if set, otherwise the checkout.

Paths, sessions, identities, seals and provenance checks of each reader are
unchanged. Nothing is copied, linked or written. The resolver stays read-only.
Owner focus config and private portfolio roots are not evidence and are unaffected.

## Acceptance

Synthetic tests in `tests/test_personal_investment_decision_action_center.py` cover:
- legacy resolution;
- legacy configured root;
- qualified profile reading the retained role with nothing created in the checkout;
- foreign checkout and conflicting environment refusals;
- unqualified-profile refusal;
- missing and corrupt Integrated Decision refusal;
- the unchanged phase-8 call shape.

Read-only real-profile acceptance (evidence kept outside Git):
- The T: profile resolves `T:\StockLookup\production-v1\retained-evidence`.
- The latest completed session is 2026-10-16.
- For 2026-10-14/15/16, the Integrated Decision header identity equals the identity
  that the single `LOCAL_COMPLETE` operation's manifest declares.
- Descriptive prices declare `UNVERIFIED_RESEARCH_PRICE`, so R1 keeps NAV weights and
  share envelopes unavailable.
- The C: checkout without a profile resolves to itself.

A full in-memory Action Center build on real data was not run during this check
because of host memory headroom. The first live T: Daily phase 8 is the end-to-end
acceptance.
