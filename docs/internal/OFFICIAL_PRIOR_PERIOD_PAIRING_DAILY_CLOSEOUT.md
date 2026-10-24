# Official prior-period pairing Daily transition — local closeout

[Contract](../official_prior_period_pairing_daily_frozen_source_transition_v1_contract.md) ·
[portable retained acceptance](OFFICIAL_PRIOR_PERIOD_PAIRING_DAILY_ACCEPTANCE.json)

## Scope and repository

Milestone: `OFFICIAL_PRIOR_PERIOD_PAIRING_DAILY_FROZEN_SOURCE_TRANSITION_V1`.
Base main: `829500e7c132e4289147e5fa61764da47f3dce67` (PR182/183/184 merged).
Branch: `feat/official-prior-period-pairing-daily-v1`, isolated development worktree,
no upstream. Production, trial-integration and shareholder-economics checkouts are untouched.
Only local implementation, validation, checkpoint and PR-ready handoff are authorized.

## Implemented behavior

The existing new-session projection branch of `materialize_independent_components` now
loads the existing qualified prior-period owners. No qualified prior input known at the cutoff
means the optional argument is omitted: the old projection and identity remain unchanged.
Completed locks and occupied projections do not load or adopt newer inputs.

`official_income_prior_period_context` remains the sole pairing engine. Current facts are
rechecked at the requested cutoff; a cached later current context cannot leak future facts.
Prior rows must carry the qualified contract/state. Unreadable semantic corrections refuse
prior loading rather than bypassing corrections or failing the whole Daily.

The existing `financial_research_card` carries the source-owned pairing through its existing
income envelope only for identical facts and exact cutoff. Primary/subset/cockpit surfaces
preserve it. Pairs expose line identity, periods, values/change/ratio, scope, assurance,
original hashes/citations, locators, knowledge clocks and comparative cross-check; UNKNOWN
retains the specific reasons. Historical reported change is explicitly separate from current
earnings momentum. Vote, trajectory, posture, triage, sizing, recommendation, strict valuation
and TTM are not fed by this context. Both Owner gates remain disabled.

## Frozen-source transition and defects found

The existing financial research transition admits only the Daily caller added by this scope.
Its exact main bytes are archived. E2/E3 pins and historical E4 V1/V2 digests are unchanged;
active execution hashes the changed caller and cannot reuse old receipts.

The Thesis active E4-V2 pin was already stale on merged main: the declared digest
`23595d916d6e49400cbcb2d1b5b62c4eef4241a8afee6e129b76ea1df609154d`
differed from main's actual digest
`e03461b30787196d26e3368d031e7dc0d9d90bba649af83eb5a17e91d57b86a0`.
The caller change now produces
`ebb592d0ceddc67f9186184c6e13f093c18ff0ddb749ccfc4e6b6cb49599a693`.
The dependent active pin is updated exactly; historical pins, source archives, closed source
scope and verifier checks are preserved. A regression test reconstructs the base digest from
Git source bytes and rejects both old receipts. No source/fact authority is promoted.

One existing Level-2 test used the real repository as its execution root for completed
August26 reacquisition. The standing completion guard correctly rejects that fixture
(as also recorded by PR184). Its fixture now uses an isolated execution root; production
completion enforcement is unchanged. No broader Daily refactor was introduced.

## Actual acceptance

Prospective research session 2026-10-26 at 15:00 ICT, using already-retained inputs:

| Case | Result |
|---|---|
| HPG revenue FY2025/FY2024 | +12.43%, audited consolidated, independent originals; comparative MATCH |
| HPG total PAT line60 FY2025/FY2024 | +29.08%, audited consolidated; comparative OCR_AMBIGUOUS, no repair; line61 not substituted |
| FPT, PNJ, VRE | UNKNOWN: NO_INDEPENDENTLY_QUALIFIED_PRIOR_PERIOD_FACT |
| PVD | UNKNOWN: PRIOR_CURRENCY_DIFFERS_NO_FX for the incompatible original |
| POW, QNS, PAN | UNKNOWN: NO_ADMITTED_CURRENT_OFFICIAL_INCOME_FACT |

The new session is an acceptance replay, not an executed future Daily. October20/22/23
cross-checks remain NOT_AVAILABLE because the October23 comparative observation was not
known at their cutoffs. Four-session plain projection identities equal unmodified merged-main
identities. Removing only pairing and its source lineage restores the entire plain projection,
including pre-existing trajectories, numerical inputs and context.

All three sealed projection identities differ from newer main in exactly the same way before
and after this milestone. October20/22 predate PR181; October23 also predates PR183's added
earnings/cash context. The October23 source-lineage/other fields are preserved; it is not
rewritten to match newer main. The replay hashes 130 explicit retained/sealed files across
October20/22/23 and input owners; before/after hashes are equal. Production writes: zero.

## Validation and handoff

Final combined regression: **1095 PASS, 2 skipped, 4 retained-evidence cases deselected**.
Command: `python -B -m pytest -q -p no:cacheprovider -m "not retained_evidence"` with the
following focused suites (empty runtime and process-local empty USERPROFILE for cold imports):

- `test_official_prior_period_pairing_daily`, `test_official_income_prior_period_pairing`,
  `test_official_income_research_consumption`, `test_ai_research_session_delivery`, `test_daily_session_level2_package`;
- `test_foundation_seams`, `test_e4_infrastructure`, `test_e5_runtime_seams`, `test_e6_financial_boundary`,
  `test_retention_reader_transition`, `test_thesis_evidence_source_transition`, `test_evidence_valuation_source_transition`;
- `test_active_control_plane`, `test_repository_layout`, `test_roadmap_execution_state`,
  `test_daily_lazy_import_closure`, `test_official_financial_source_integrity`,
  `test_current_research_ai_handoff_packet`, `test_investment_decision_workspace_projection`.

Retained replay PASS: 130 file hashes conserved; HPG and all UNKNOWN representative cases
pass at valid cutoffs; all four plain projections match independently executed merged main.
Launcher hashes and `git diff --check` PASS. Active reading set: 102077 bytes before the
final compact closeout label (limit 102400). Native roadmap: ON_TRACK, writer check PASS. No production Daily, DB writes, dashboard
publication, push, merge or hosted CI were run. Active control-plane docs remain within the
102400-byte aggregate budget. Implementation checkpoint: `e51369a407e398f34bda2211070a5bff1238b6f6` (21 changed files).
Native roadmap records COMPLETE / LOCAL_IMPLEMENTATION_COMPLETE_NOT_PROMOTED;
the successor queue stays empty.

PR-ready title: **Integrate qualified prior-period pairing into Daily historical research cards**

PR-ready description: New, uncompleted Daily sessions now join existing qualified independent
prior-period facts and carry their non-voting historical revenue/profit direction into existing
research cards. Empty/unqualified inputs preserve the prior projection identity; exact source
transition archives preserve historical digests while current execution rejects prior receipts.
HPG's retained audited FY2025/FY2024 evidence gives +12.43% revenue and +29.08% total PAT;
missing/mismatched evidence stays UNKNOWN. No financial/source authority, current vote,
valuation, trajectory, TTM or completed-session artifact changes.

Remaining evidence limits: absent independent originals, mismatched currencies and current
qualified-quarter coverage remain UNKNOWN/UNAVAILABLE. These are explicit data limits, not
unfinished integration. Hosted CI, push/PR creation and any production activation require a
later Owner instruction. No next milestone is started.

## Changed files

- `.github/workflows/producer-ci.yml`
- `ai_research_session_delivery.py`
- `config/daily_path_launchers.json`
- `daily_session_level2_package.py`
- `docs/ACTIVE_STATE.md`
- `docs/AUTHORITY.md`
- `docs/CAPABILITIES.md`
- `docs/DAILY_PIPELINE.md`
- `docs/ROADMAP_CURRENT.md`
- `docs/ROADMAP_STATE.json`
- `docs/internal/OFFICIAL_PRIOR_PERIOD_PAIRING_DAILY_ACCEPTANCE.json`
- `docs/internal/OFFICIAL_PRIOR_PERIOD_PAIRING_DAILY_CLOSEOUT.md`
- `docs/official_prior_period_pairing_daily_frozen_source_transition_v1_contract.md`
- `stocklookup_core/financial/official_income_prior_period_pairing.py`
- `tests/fixtures/financial_research_source_transition_v1.json`
- `tests/fixtures/financial_research_v1_sources/daily_session_level2_package.py.txt`
- `tests/fixtures/thesis_evidence_production_source_transition_v1.json`
- `tests/test_daily_session_level2_package.py`
- `tests/test_official_prior_period_pairing_daily.py`
- `tests/test_thesis_evidence_source_transition.py`
- `tools/replay_official_prior_period_pairing_daily.py`

## Hosted CI correction — PR185

Owner subsequently authorized push, PR creation and scoped CI corrections. Initial hosted
run 40050094813 passed four jobs; focused regressions had 6718 passes and one docs failure:
the closeout heading replaced the required NOW horizon. The heading now preserves NOW
and labels this same milestone LOCAL COMPLETE. No roadmap admission, implementation,
policy, authority or runtime behavior changes. The active-control-plane suite and native
roadmap check are rerun before pushing the correction.
