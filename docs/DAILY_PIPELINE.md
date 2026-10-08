# Stock Lookup — Canonical Daily Pipeline

Canonical Daily order, including the Macro V1 corrective. Code governs this view.
Current-state facts: [ACTIVE_STATE.md](ACTIVE_STATE.md). Authority per output: [AUTHORITY.md](AUTHORITY.md).

[Long-term company economics evidence](long_term_company_economics_evidence_contract.md)
is offline opt-in only; it adds no Daily stage or consumer. October 8 Macro live
acceptance is independently verified; exact identities are in ACTIVE_STATE.

Released October-7 integration extends K2's existing fundamental builder with a
new session projection of the immutable annual baseline and qualified retained overlay.
Reviewed USD income fields remain currency-preserving context and are excluded from VND
canonical citations/valuation inputs. Reported disposal components and an audited annual
provision component follow the
[earnings contract](reported_earnings_component_context_contract.md): descriptive flags,
explicit period, recurrence UNKNOWN, no normalized EPS. This changes future construction only.
CI, valuation and downstream research receive that projection; corporate selection is
carried from the same frozen/attempt input binding into opportunity and K6 event context.
Completed locks cannot be replaced. AI context preserves exact-field citations and event
identity; Dashboard input manifests carry the bindings. No production Daily or publication
was performed for this checkpoint. [Offline proof](internal/CURRENT_OFFICIAL_EVIDENCE_PROJECTION_INTEGRATION_20261007.md).

Phase C resource architecture (released 2026-10-06) preserves this run order and all output identities.
IID identity is streamed, the writable binding spine is copied, and delivery UTF-8 rows are buffered.
T0 root/record hashes are verified while projecting only velocity axes; hashing and pretty writing
are record-bounded and immutable writers retain exact native bytes. Held-live Canonical heavy
path completed at 4.03 GiB private; actual Owner completion/handoff at 5.51 GiB in its separate
lifetime after Canonical exit. No new child boundary or production GC is required by measured
release behavior. No production Daily was run for this release and no host/feedback threshold changed.
[Whole measurements, ownership map and limits](internal/PHASE_C_WHOLE_PIPELINE_RESOURCE_CLOSEOUT_20261006.md).

**One production workflow, two front doors:** `stocklookup.ps1 daily` and the Desktop one-click both call
`tools.run_owner_daily.run_workflow`. Never run two writers at once. Runbook:
[OWNER_DAILY_ONE_CLICK.md](OWNER_DAILY_ONE_CLICK.md). Evening target for the first real session: ~16:00
Asia/Ho_Chi_Minh ([Monday contract](monday_live_readiness_closeout_contract.md)).

Legend — **Block**: failure stops the run at that stage. **Soft**: failure is component-local
`UNAVAILABLE`/`WARN`; the sealed Producer result, capture, marker and T0 keep their validity.
**Parent/child**: the Owner parent process, the Daily child (`daily_analysis_pipeline.py
--canonical-post-close`, runs the kernel), or a retained-only/tool subprocess (grandchild).

## A. Owner launcher (parent process, nine phases)

| # | Phase | Purpose | Block/Soft | Process | Retained output | Retry / recovery |
|---|---|---|---|---|---|---|
| 1 | Repository preflight | Safe-sync Producer, Consumer (`ai-core-private`) and Dashboard checkouts: right repo/origin/`main`, clean, `pull --ff-only`, never reset/rebase/stash/clean | Block | parent | durable journal `operations-review/owner-daily-journal-v1/journal.json` | fix checkout, rerun; journal records the stage before work starts |
| 1b | **Host preflight** (`OWNER_DAILY_HOST_PREFLIGHT_V1`), evaluated inside phase 1 after the repository preflights and before Canonical Daily BEGIN is shown (a non-READY result is reported as phase 1 FAILED, step `Host preflight`); `_run_daily` re-checks only when called without an accepted READY | Read-only commit / physical / pagefile / disk / writer observation | Block (BLOCKED refuses; **AMBER also refuses automatic launch**) | parent | stdout JSON only (no writes) | close browsers/IDEs, rerun; no override flag; completed-session replay does not launch acquisition and skips it |
| 2 | Canonical Daily | Spawn the Daily child and wait; the child runs section B | Block | child | see B | interrupted but already-complete Daily resumes publication from the journal; otherwise rerun (retained exact-session snapshot is reused, no duplicate acquisition) |
| 3 | Daily completion verification | Verify operation record, registry `COMPLETED_RETAINED_EVIDENCE`, runtime/trusted READY | Block | parent | none | fix and rerun; or `--replay-completed-session SESSION` |
| 4 | Producer state publication | Commit only the governed session registry (`commit_daily_state`), `NO_CHANGE` when identical | Block | parent | git commit of `config/daily_research_session_input_registry.json` | idempotent; resumed step re-verifies |
| 5 | Dashboard publication | `release_orchestrator` publishes to `market-dashboard`; public byte identity check | Block (independent of AI handoff) | parent→tool | `dashboard-runtime`, Dashboard repo | `REUSED_EXISTING_PUBLICATION` on replay |
| 6 | AI handoff build | Build/publish the compact private AI handoff; refuses without the exact retained Brief and Integrated Decision overlay (never recreated here) | Block | parent | `stocklookup-ai-handoffs` publication | `ALREADY_PUBLISHED_VERIFIED` on replay |
| 7 | Remote verification | Confirm the remote handoff is `READY_FOR_AI` at the exact session/SHA | Block | parent | none | rerun |
| 8 | Personal Action Center | Read-only owner view over retained artifacts | Soft | parent | action-center artifact | rerun |
| 9 | Open owner view | Open the local view | Soft | parent | none | — |

`FINAL STATUS: PASS` means the remote AI handoff is `READY_FOR_AI`. It says nothing about T0 (see
ACTIVE_STATE §3).

## B. Canonical Daily kernel (Daily child; `canonical_daily_operation.run_canonical_daily_operation`)

| # | Stage | Purpose | Block/Soft | Process | Retained output | Authority role | Retry / recovery |
|---|---|---|---|---|---|---|---|
| K1 | **Calendar / Phase A** | One bounded DNSE `working_dates` probe (retained as a calendar receipt); attempt eligibility, session resolution, 15:30 floor | Block | child | calendar receipt (`prospective-calendar-evidence-v1`) | `SCOPED` calendar | rerun when eligible; probe skipped on retained-resume |
| K2 | **Market acquisition** (`acquire_and_materialize`) | DNSE exact-session acquisition + Level-2 current-research chain (universe resolution, liquidity, technical coverage, descriptive, screening, tactical classifier, corporate intelligence, valuation inputs, sector leadership, relative research, risk register) | Block | child + tool grandchildren | exact-session snapshot, raw market evidence (immutable), Level-2 artifacts | `SCOPED` current-session evidence | retained snapshot reused; `DUPLICATE_MARKET_ACQUISITION` guard |
| K3 | **Listing + capture binding** (inside K2) | Same-session positive listing observations; immutable capture companions/bindings/market manifest | Soft for Daily completion; mandatory for capture | child | `prospective-market-evidence-v1`, capture batches | `SCOPED` capture inputs | incomplete capture stays incomplete; never invented |
| K4 | **Phase B gate** | Exact-session completion gate must be `READY` | Block | child | gate record (identity-bound) | `SCOPED` | wait for provider publication / rerun |
| K5 | **Register + freeze** | `register_session_inputs`, `validate_and_freeze_completed_session` | Block | child | registry entry (`COMPLETED_RETAINED_EVIDENCE`) | operational | idempotent |
| K6 | **Technical + enrichment + Integrated Decision** (`build_enrichment_components`) | Financial momentum, corporate event context, historical context (market bars; **Technical V1 before 2026-10-03, V2 from it**), then the Integrated Decision; canonical streaming write, verified working-view copy, classification summary | Block for the Integrated Decision (components are individually soft; absent IID raises before Producer) | child (in-process) | `integrated_investment_decision_product.json` (≈1.3 GB on 2026-10-02) + working view | `SCOPED` research posture | rerun; `*.tmp` unlinked on failure |
| K7 | Macro refresh | Presentation + explicit Macro V1 acquisition; actual research cutoff | Soft | child | presentation + regime context | `SCOPED` | degrades to unavailable/partial |
| K8 | **Daily Producer** (`run_daily_producer`, with pre-seal Daily Integrated Brief) | Seal the immutable run + operation directories and the Brief | Block (only `DailyProducerError`/`CanonicalPostCloseError` map to blocked stages; other exceptions, e.g. `MemoryError`, fail the child) | child (in-process; heaviest memory stage) | `daily-producer-runs-v1`, `daily-research-session-operations-v1`, `run_manifest.json` | `SCOPED` Producer verdicts | sealed identity-addressed; never re-sealed |
| K9 | Runtime + trusted-subset materialization | Release runtime artifacts; verify trusted subset | Block | child | `dashboard-runtime` bundle | `SCOPED` | rerun |
| K10 | **T0 snapshot** (`retain_prospective_decision_snapshot`) | Streamed canonical hash + pretty write of every full decision record | Soft (`UNAVAILABLE` + reason) | child | `prospective-decision-retention-v1/<session>/<digest>/` | `AUTHORITATIVE` for T0 content | **one-shot per session**; same-digest rerun idempotent, conflict fails |
| K11 | **T0 seal index** (writer callback) | Compact verified index + write receipt | Soft | child | `prospective_t0_seal_index.json`, write receipt | `SCOPED` pointer | explicit `tools/recover_t0_seal_index.py` |
| K12 | **Daily boundary / first marker** (`daily_boundary`) | Verify original evidence → immutable complete-session record → write-once first marker → readiness | Soft | child | `prospective-pit-capture-v1/` | `SCOPED` capture completeness | missing marker recovered from original evidence time; records immutable |
| K13 | **Thesis T0 sidecar** | Retained-only compact T0 projection (needs a verified seal index) | Soft; `NOT_APPLICABLE` before 2026-10-03 | tool child (64 KiB result cap) | `thesis-evidence-t0-v1/<session>/<digest>/` (`COMPLETE.json` last) | `NON_VOTING` | `ALREADY_RETAINED`; incomplete dir rebuilds |
| K14 | Decision packet | Retain verified pre-seal canonical packet (new sessions) | Block (no local handler) | child | decision packet | `SCOPED` | rerun |
| K15 | **Pre-handoff prospective collection + feedback #1** | Cohort collection and first outcome-feedback child | Soft | tool children (admission → Job Object, 1,200 s total deadline) | `prospective-research-cohort-collection-v1`, `prospective-decision-outcome-feedback-v1` | `NON_VOTING` | `ALREADY_COMPLETE` reuse on identical inputs |
| K16 | Tactical reversal shadow collection | A/B observation collector | Soft | tool child | tactical shadow store | `NON_VOTING` | idempotent store |
| K17 | **Handoff bundle** (`build_tiered_bundle`) | Write `session_handoff_bundle.json` (binds T0 status/identity, feedback status) and tier bundles | Block (no local handler) | child | handoff + tier bundles | `SCOPED` | rerun |
| K18 | **Post-handoff observers** | Signal velocity → current foreign flow (live DNSE) → flow/price divergence → **Volume & Flow V2** → **Thesis current** sidecar | Soft each | child + tool child (Thesis) | observer artifacts; `thesis-evidence-current-v1/…` | `NON_VOTING` | immutable writes; replay diagnostics never publish pointers |
| K19 | **Post-handoff outcome feedback #2** | Second feedback child (`INCREMENTAL` over #1) | Soft | tool child | `prospective-decision-outcome-feedback-post-handoff-v1` | `NON_VOTING` | `ALREADY_COMPLETE` reuse; resource/reap statuses are never evidence |
| K20 | Presentation projection + runtime restage | Re-join Workspace/Screener with the now-available axes into a **new** artifact set (never the sealed Producer dir) | Soft | child | `post-handoff-presentation-projection-v1` | `SCOPED` presentation | falls back to sealed bytes |

Heavy children (Thesis, feedback) are blocking calls that return only after the process is reaped, so
no two heavy children overlap. Feedback and Thesis run **after** capture, marker, T0 and seal; they can
never revise them.

## C. Resume and replay

- Completed-session verified replay: `tools/run_owner_daily.py --replay-completed-session SESSION`
  (or the shared launcher `tools/run_owner_daily.ps1 -ReplayCompletedSession SESSION`); it publishes from retained evidence, runs
  zero analytical Daily calls, and cannot rebuild T0.
- Read-only post-Daily acceptance: `python tools/run_first_real_session_acceptance.py` (see Monday
  contract; writes only a diagnostic report). Dry run: `--dry-run --session 2026-10-05 --cutoff … --output <scratch>`.
- Registration of an original calendar receipt (explicit, offline, owner-gated): `tools/register_working_dates_receipt.py`.
