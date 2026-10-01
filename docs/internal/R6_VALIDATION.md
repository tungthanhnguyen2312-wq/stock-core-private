# R6 local validation

Stack base: `397c05cf6e47d4bdc5a0a471102dfcb8ac383956`.
Canonical semantics and corpus details: [contract](../empirical_setup_outcome_calibration_contract.md),
[portable retained acceptance](R6_PROSPECTIVE_LEARNING_ACCEPTANCE.json).

## Passing tiers

- 432 focused/integrated tests, including 47 R6 adversarial tests. Selection: R6, retention,
  outcome feedback, integrated prospective feedback, empirical calibration, outcome measurement,
  admission policy, current-decision snapshot, Integrated Decision product, R4/R5, Portfolio research
  hook, Canonical Daily and post-close pipeline tests.
- 25 retained-fixture regressions: learning ledger, durable case store, daily rollforward,
  case operations, cohort collection and research learning. Exact existing fixture paths were
  exposed only through a temporary test reader; writes to the source tree were refused.
  All 22 source files read by this tier retain their original SHA256 hashes.
- Final hermetic tier: `-m 'not retained_evidence and not provider_runtime'`, with the single
  independently reproduced baseline assertion below excluded. Nine explicit private/provider-tier
  cases remain outside this hermetic selection.
- `python -m py_compile` over all six changed implementation modules, the existing CLI and five
  changed/new test modules: PASS.
- `python tools/stocklookup_roadmap.py --check`: PASS (expected dirty-worktree warnings before
  checkpoint; current R6 COMPLETE / next R7).
- `git diff --check`: PASS.

Retained acceptance uses the existing CLI with explicit source root, acceptance output,
pre-change inventory and pre-change feedback. All 30,294 genuine cases are evaluated. A second
pass reverses input order without reacquisition and produces the same deterministic artifact
identity. All 138 source hashes are unchanged. The report binds the exact evaluated implementation
file hashes, which match this checkpoint's files.

## Supplemental baseline assertion

`tests/test_canonical_post_close_pipeline.py::test_omitted_session_without_working_dates_fails_closed`
expects PROVIDER_EVIDENCE_UNAVAILABLE, while the existing Daily gate returns FUTURE_SESSION.
The failure reproduces after loading the exact baseline Daily modules with their original
worktree paths. Every directly involved module and the session registry is byte-identical under
Git's content contract to the R5 base. No R6 change repairs or suppresses this unrelated policy
fixture. The final tier excludes this one assertion after proving the baseline failure.

Verified baseline Git blob identities:

- `canonical_post_close_pipeline.py`: `9de487ad34544ece23f9968f1ccfba9e825b27fa`
- `canonical_daily_operation.py`: `1d49ff3e9ebbd7461590d61cc1818f53b4376544`
- `daily_analysis_pipeline.py`: `ed96cb9611cffd08273be8226bda30dd93369ea1`
- `daily_execution_environment.py`: `bb2608b13c81d0608e59ebac1173f7bb24b5574f`
- `daily_research_session_operations.py`: `244242272f3417e436cc20fdd759c2a905fc1b65`
- `config/daily_research_session_input_registry.json`: `f29dd92e7cdd87ad4dbb43e1e707ca83515d79f4`

## Changed-file manifest

- `.github/workflows/producer-ci.yml`
- `empirical_setup_outcome_calibration.py`
- `integrated_decision_prospective_feedback.py`
- `integrated_investment_decision_product.py`
- `prospective_decision_outcome_feedback.py`
- `prospective_decision_outcome_measurement.py`
- `prospective_decision_retention.py`
- `tools/run_empirical_setup_outcome_calibration.py`
- `tests/test_prospective_learning_calibration_r6.py`
- `tests/test_empirical_setup_outcome_calibration.py`
- `tests/test_portfolio_aware_decision.py`
- `tests/test_prospective_decision_outcome_feedback.py`
- `tests/test_prospective_decision_outcome_measurement.py`
- `docs/STATE.md`
- `docs/ROADMAP.md`
- `docs/ROADMAP_STATE.json`
- `docs/SYSTEM_MAP.md`
- `docs/empirical_setup_outcome_calibration_contract.md`
- `docs/internal/R6_PROSPECTIVE_LEARNING_ACCEPTANCE.json`
- `docs/internal/R6_VALIDATION.md`

No historical T0 decisions/postures or live policy thresholds change. NEW products bind existing
policy-version metadata under the existing content hash; per-decision identity rules are
unchanged. No acquisition, live Daily, production/runtime write, publication/deploy, source/PIT/
liquidity/sizing/execution promotion, push, PR, merge or R7 work occurs.
