# Shareholder economics / dilution research integration — local closeout

Owner scope: `CORPORATE_SHAREHOLDER_ECONOMICS_AND_DILUTION_RESEARCH_INTEGRATION_V1`.
Controlling [capability contract and invocation](../corporate_shareholder_economics_research_v1_contract.md#shareholder-economics-and-dilution-integration-v1-local-2026-10-24).

## Integration and reuse

Base is renamed Producer main `e86b5f96ab073fe5a0fd673351332466094aff82`.
Branch: `feat/shareholder-dilution-research-integration-v1`, dedicated development worktree.
Original checkpoint `119a9e1e641a9c71482756e7875e52f9acd0d93b`, original branch/worktree
and subsequent historical closeout `e8485f4d` remain preserved. The original checkout was clean;
no competing writer on its scope was found. Lightweight roadmap bootstrap reported ON_TRACK
with multiple-writer check PASS; other ahead worktrees were informational, not new admission.

The original projection and Corporate Intelligence → decision packet → Workspace/AI transport
were reused, not rebuilt. Additive source integration retains current main's prior-period pairing
and rename/consolidation changes. Compact-doc/CI/launcher conflicts were reconciled locally;
historical source pins and sealed evidence were preserved. The launcher AST rebind was checked
against main: resolved invocation paths and unresolved argv sites are identical.

New implementation extends the existing module/tool: qualified-point endpoint arithmetic,
exact-event planned/executed variance, explicit basic/diluted EPS, charter capital and
repurchase/cancellation identities; source-bound optional metadata; and offline candidate
inspection. It does not replace the existing share authority/transition resolver, valuation
owner or evidence qualification contracts. Source placement and dependency ratchets pass.

## User-visible result

The existing replay tool's `--inspect` mode emits `research_packet.json` and
`research_cards.md` under an explicitly chosen development scratch directory. It defaults to
HPG, PNJ, SSI, PVD, POW and QNS; fourteen reported issuers were inspected at the prospective
acceptance cutoff. Inputs are explicit, offline and immutable. Different results cannot
overwrite prior results, output paths cannot overlap inputs or escape scratch.

HPG/PVD cards expose the candidate EPS-versus-legal/accounting basis differences without
substituting either for a current denominator. PNJ distinguishes approval, inferred execution
and missing completion; non-observation is not zero buybacks. SSI distinguishes issuance end,
listing/trading and ex-date. QNS preserves parent versus consolidated treasury basis. POW
charter/par and PAN missing originals remain explicit blockers. No count or ex-date is guessed.

## Observations, candidates and blockers

- Hub issue 39, commit `4ba741960c9859fc370cc667d2cdeb10f70a91ea`, supplied 40 source
  entries, 35 events, 32 continuity points and 24 gaps. Seven original report-file hashes and
  the Hub commit clock are pinned. No Hub issue/report was modified; issue 38 was not touched.
- Five retained original PDFs match exact issuer/URL/byte hash in the supplied acquisition
  manifest: HPG FY2025/H1 2026, PNJ FY2025/Q2 2026, NVL Q2 2026. Matching bytes do not qualify
  the CSV's new quantities, lifecycle labels, dates, OCR or claimed eligible uses.
- One already-qualified HPG common-outstanding point is reused: 7,675,465,855 at 2025-12-31,
  audited source page 41, original citation/clocks unchanged. Publication remains null;
  subsequent continuity remains unproven. **Zero new qualified share fields** are created.
- New June/EPS/event quantities in the report remain candidate-only. Missing originals,
  exact-field/semantic receipts, publication/PIT, explicit ex-dates, execution and continuity
  block their dependent strict uses. Mirror/secondary copies remain non-authoritative.
- The historical October 23 inspection contains zero October 24 candidate values. The older
  HPG point may remain visible because its existing knowledge clock is earlier; this does not
  backfill or rewrite a sealed session.

## Validation

- Focused business/integration regression: **464 passed, 9 skipped, 8 deselected**. Eight skips
  require unavailable historical packet/handoff inputs in this clean development worktree;
  one is the Windows host lacking test-symlink creation permission. Eight retained/provider
  cases were excluded by the same hermetic marker selection used by CI, not claimed as passing.
- Repository layout: **25 passed**. Cold/lazy import and production-call-shape smoke:
  **11 passed**, using an empty scratch USERPROFILE only inside the test subprocess environment;
  the real active workspace/profile was never edited. Reviewed launcher regression: **1 passed**.
- Architecture ratchet and reviewed Daily launcher check: PASS. `py_compile`: PASS on the
  12 changed Python modules/tests; `git diff --check`: PASS.
- Read-only replay against exact main: **1,507 corporate records / 72 primary cards** retain
  every prior field after stripping the additive context. Two cards have admitted financial
  explanation, 70 remain UNKNOWN, unchanged from the original recovery. Eight explicit
  October 22 input hashes remain equal before/after.
- Three October 23 seal/manifest/bundle hashes and five matched original PDF hashes remain
  unchanged. [Portable acceptance summary](SHAREHOLDER_DILUTION_INTEGRATION_ACCEPTANCE.json).
- Hosted CI was NOT run: push/PR/release are outside this authorization. The new suites are
  included in the existing focused CI selection. No production Daily or AI was invoked.

## Checkpoint and release disposition

One local checkpoint commit contains this integration and closeout. No prior completion was
reopened or source authority promoted, and no successor was started. Existing native completion
history was not rewritten to fabricate an integration release/checkpoint receipt.

Code is ready for Owner-controlled PR/release review. Remaining gates are separately authorized
push and hosted exact-head CI, Owner review, and independent source-owner qualification for any
new official quantities. Those evidence gaps do not prevent the explicitly candidate-labelled
offline research product from being used. Production checkout, runtime, DB, snapshots, price
adjustment, strict valuation, execution/RAW/PIT and policy/eligibility gates remain unchanged.

## Changed surfaces

- Reused/extended: `stocklookup_core/research/shareholder_economics.py`,
  `tools/replay_corporate_shareholder_economics.py`.
- Reused transport: Corporate Intelligence, existing canonical enrichment, AI delivery,
  decision packet, Workspace and AI handoff modules.
- Tests: original shareholder suite, new dilution/Hub adversarial suite, labelled original
  replay preview, pinned Hub discovery index and existing HPG qualification receipt fixture.
- Active CI/launcher/source-transition bindings and necessary compact capability/authority
  documentation; original historical recovery acceptance/closeout retained unchanged.

STOP: no push, merge, deploy, Daily, authority promotion or next milestone.
