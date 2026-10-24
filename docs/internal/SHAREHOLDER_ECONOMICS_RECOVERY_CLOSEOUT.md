# Shareholder economics WIP recovery and local closeout

Recovered on 2026-10-24; controlling scope: [original contract](../corporate_shareholder_economics_research_v1_contract.md).

## Provenance and scope

Original milestone: `CORPORATE_SHAREHOLDER_ECONOMICS_RESEARCH_V1`, explicitly admitted by
Owner on 2026-10-23. The matching 21-file WIP and original implementation request were
verified against the interrupted Codex session. That session stopped on a usage limit.
The previous chat is not running; the native writer check passes. No other worktree was edited.

Branch: `feat/corporate-shareholder-economics-research-v1`; recovered HEAD:
`a8c24f1ad84ce5405d47223a278e173a82a5bb35`; no upstream configured.
Remote main independently verified as `829500e7c132e4289147e5fa61764da47f3dce67`
(PR182/183/184 merged). The original base is an ancestor of that main.
This branch retains its original history. Compatibility was tested with an isolated archive
of merged main plus the changed source/test files, without editing any other checkout.
Main's financial pairing code and tests are present in that compatibility run.

## Capability disposition

- DONE: claim-local source/semantic/clock qualification, separate actual and proposed issuance,
  cash versus noncash conversion, bonus shares, rights entitlement, planned/received financing,
  earmarked/repaid debt, booked versus estimated obligations, reported versus planned profit,
  and dated issued/outstanding/treasury/voting/listed/tradable versus EPS duration shares.
- DONE: non-voting transport through Corporate Intelligence, Integrated Decision's existing
  forward-driver context, research input/packet, Workspace, AI primary/subsets and cockpit JSON.
  Existing financial exact-field and shares/valuation owners are reused. No parallel ledger,
  evaluator, source acquisition or denominator resolver was introduced.
- DONE: generic executed issuance no longer asserts cash raised without receipt evidence.
  Dated share facts cannot use a duration or charter-capital amount as an outstanding count.
- DONE: the old replay dynamic-execution architecture violation was removed. Pinned baseline
  projections run in a separate scratch-only Python process. Three presentation test mocks
  were corrected for the existing `evaluated_valuation` argument; their failure was reproduced
  on merged main before the correction.
- BLOCKED BY EVIDENCE: dossier figures in all five issuer previews remain candidate-only.
  PAN originals, HPG later share continuity, PNJ's repurchase-only provision and October plans,
  NVL's conversion/rights/cash/debt settlements and SSI's separate share identities cannot
  become live facts without their source-owner qualification. No new authority is claimed.
- NOT IMPLEMENTED / OUTSIDE ORIGINAL SCOPE: new ownership-register ingestion, charter-capital
  inference, general dividend acquisition, computed dilution, revised EPS/BVPS/P/B/market cap,
  price factors, historical PIT, policy votes, risk scoring or frontend publication.
- ACTIVE WORK: none after local closeout; successor queue remains empty.

## Actual October 22 acceptance

[Portable acceptance summary](SHAREHOLDER_ECONOMICS_RECOVERY_ACCEPTANCE.json) records 1,507
corporate records and 72 primary cards. All pre-existing fields compare equal to merged main
on the retained replay; the intentional executed-issuance reason correction is tested separately.
Of 72 cards, 2 have admitted explanatory claims and 70 remain UNKNOWN. PNJ exposes admitted
OCF and the aggregate cash-flow provision adjustment; the latter is not the repurchase-only
booked provision. NVL, SSI, HPG and PAN have no admitted new claims in those selected inputs.
Their opt-in offline previews exercise their distinct economics without qualifying the amounts.
Eight explicit retained/sealed input files retain identical before/after SHA-256 values.
Technical labels, posture, decision identity, valuation eligibility and numbers remain owned
by their existing engines. No ex-date, current outstanding count or market cap is inferred.

## Validation

Final focused/structural checks: 413 PASS, 5 skipped, 2 retained-evidence cases deselected;
2 subtests PASS. This covers the new capability, corporate axis, research packet, AI delivery,
Workspace/AI handoff, existing earnings/cash and share-denominator owners, architecture/layout,
reviewed launchers, frozen-source transition and native roadmap. Historical evidence suites
requiring absent worktree-local artifacts were not represented as passing. No Daily was run.
The import closure runs with an empty test USERPROFILE because the real host's active-workspace
binding correctly refuses imports as a production writer from a development checkout. The binding
and production environment were not edited.

- Merged-main compatibility: 206 PASS, 1 retained-evidence case deselected.
- Canonical presentation and cold/lazy import closure: 78 PASS, 6 retained-evidence cases deselected.
- Retained read-only replay: PASS; 1,507 record parity, 72 card parity, 8 file hashes unchanged.
- Hosted CI: NOT RUN (current Owner instruction forbids push).

## Checkpoint and next action

Implementation checkpoint and terminal disposition are recorded through the existing native
roadmap local-closeout command; no main release or successor admission is implied.
The recovery instruction permits local checkpoints only and supersedes the original push/PR
permission. No push, merge, deploy, production DB/data writes or Dashboard publication occurred.

A later Owner-authorized integration must reconcile native roadmap/compact documentation and
launcher/CI manifests with the newer main. The tested source is compatible; this is not a claim
that Git documentation/manifests have already been merged. Live use of additional issuer facts
requires existing source-owner evidence qualification. Frontend rendering/publication remains
separately unvalidated and unauthorized here.

## Changed files

- `.github/workflows/producer-ci.yml`
- `ai_research_session_delivery.py`
- `canonical_post_close_pipeline.py`
- `config/daily_path_launchers.json`
- `current_corporate_intelligence_axis.py`
- `docs/ACTIVE_STATE.md`
- `docs/AUTHORITY.md`
- `docs/CAPABILITIES.md`
- `docs/DAILY_PIPELINE.md`
- `docs/ROADMAP_CURRENT.md`
- `docs/ROADMAP_STATE.json`
- `docs/corporate_shareholder_economics_research_v1_contract.md`
- `docs/internal/SHAREHOLDER_ECONOMICS_RECOVERY_ACCEPTANCE.json`
- `docs/internal/SHAREHOLDER_ECONOMICS_RECOVERY_CLOSEOUT.md`
- `stocklookup_core/decision/current_research_ai_handoff_packet.py`
- `stocklookup_core/decision/current_research_decision_packet.py`
- `stocklookup_core/decision/investment_decision_workspace_projection.py`
- `stocklookup_core/research/shareholder_economics.py`
- `tests/fixtures/evidence_valuation_orchestration_source_transition_v1.json`
- `tests/fixtures/shareholder_economics_candidate_preview_v1.json`
- `tests/test_canonical_post_close_pipeline.py`
- `tests/test_evidence_valuation_source_transition.py`
- `tests/test_shareholder_economics.py`
- `tools/replay_corporate_shareholder_economics.py`
