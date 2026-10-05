# Stock Lookup — Active State

Compact, authoritative view of what is true **now**. Read this first; it is small on purpose.
Written 2026-10-04 (Sunday) against Producer `main` `920d57917581a476e3ab6a9cf40d9ca53643ecb2`
(PR #60 merged). `git rev-parse origin/main` reads only the **local** remote-tracking ref and can be stale.
To verify the live remote head run `git fetch origin main` and then compare `git rev-parse origin/main`
(or ask the remote directly with `git ls-remote origin refs/heads/main`). The only change intended after
the SHA above is the docs-only control-plane PR that introduced this file.
The 2026-10-05 first-real closeout in this file was recorded after Producer `317118c788bdd46bd6de55dbff3888b92de1172d`
(PR #66). That sentence is not a live-head proof: fetch before trusting it.

## 0. How this file relates to the others

| Question | Answer lives in |
|---|---|
| What is active? | this file + [CAPABILITIES.md](CAPABILITIES.md) |
| What is authoritative? | [AUTHORITY.md](AUTHORITY.md) + the controlling contract it cites |
| What runs Daily? | [DAILY_PIPELINE.md](DAILY_PIPELINE.md) |
| What happens next? | [ROADMAP_CURRENT.md](ROADMAP_CURRENT.md) |
| What happened historically? | [HISTORICAL_INDEX.md](HISTORICAL_INDEX.md) → legacy STATE / ROADMAP / DECISIONS / `internal/` |

**Authority by domain** (one rule, no ladder and no new authority layer; identical in `AGENTS.md`):
- *Milestone execution state* (current / queued / blocked / startable, checkpoint verification):
  `docs/ROADMAP_STATE.json`, queried with `python tools/stocklookup_roadmap.py` (AI_RULES rule 11).
- *Capability semantics and authority limits*: the controlling contract (`docs/*_contract.md`, cited in
  `AUTHORITY.md`) and the code and tests that implement it.
- *Compact current-state docs* (`ACTIVE_STATE`, `CAPABILITIES`, `AUTHORITY`, `DAILY_PIPELINE`,
  `ROADMAP_CURRENT`): maintained navigation views of the two items above. They add **no** authority; if one
  disagrees with the first two, the first two govern and the view is corrected in the same change.
- *Preserved `STATE.md` / `ROADMAP.md` / `DECISIONS.md`*: history, rationale and recorded invariants; not the
  default current-state source. A compact view never overrides a recorded invariant: surface the conflict
  and obtain an explicit owner decision.
Chat memory is never authority. Legacy `STATE.md` banners pre-date some facts below (see §6): for a
current fact, verify against the sources above (or the re-verify command given with the fact), then correct
this view; never resolve a disagreement by which prose is newer.

Fact kinds used below: **CURRENT FACT** (verified in repo or by a stated read-only check),
**HOST-LOCAL** (true on the owner's Windows host, not tracked by git — re-verify before use),
**BLOCKED**, **DEFERRED**, **HISTORICAL**.

## 1. The operational gate

- **CURRENT FACT — active operational gate:** `FIRST_REAL_POST_RELEASE_CAPTURE_ACCEPTANCE` = **RECORDED**
  for session **2026-10-05**. The read-only harness (cutoff `2026-10-05T16:00:00Z`, report under
  `operations-review/first-real-session-acceptance-v1/2026-10-05/`, not in git) returned
  `capture_session` OPEN (`prospective_capture_complete_session:661a12b7fd0bbbde2a747e660b88f7b1eb33b57ad6d96fc3db4ddef844327d5d`,
  658 capture-complete tickers), `first_marker` OPEN, and `t0_snapshot_availability` OPEN
  (`prospective_decision_snapshot:1c496e3f7a2df9770e269ef20821805ef0cb8c76d34ebb2869d72fbb61e319f9`).
  Readiness `complete_session_count` advanced 0 → 1 and stays `DEPTH_PENDING`. `representation_tier`
  is OPEN (853 `SOURCE_NATIVE_SCALE_CONSISTENT`). `positive_listing` stays `STILL_BLOCKED`
  (HOSE 364, UPCOM 294, UNKNOWN 195). `official_verification`, `raw_as_traded`, and `ca` stay
  `STILL_BLOCKED`, which this gate does not treat as failure. Contract:
  [monday_live_readiness_closeout_contract.md](monday_live_readiness_closeout_contract.md),
  [prospective_pit_capture_completeness_contract.md](prospective_pit_capture_completeness_contract.md).
- **CURRENT FACT — Owner Daily 2026-10-05 is complete.** Journal stage `COMPLETE`, run
  `e244385f2a7441d697679d08826c88f9`, failure null, Producer `317118c788bdd46bd6de55dbff3888b92de1172d`.
  The 2026-10-02 Daily remains a prior session whose T0 failed with `MemoryError` and stays
  permanently `UNAVAILABLE` (a 0-byte file is retained; never rebuilt). `ROADMAP_STATE.json`:
  `current = OWNER_DAILY_FEEDBACK_RESOURCE_CONTAINMENT_V1 / COMPLETE`, `queued_next = []`,
  `successor_disposition = FIRST_REAL_POST_RELEASE_CAPTURE_ACCEPTANCE_RECORDED_2026_10_05_NO_AUTOMATIC_SUCCESSOR`.
- **CURRENT FACT — no automatic successor.** Nothing starts because something else finished;
  every new milestone needs explicit owner authorization (AI_RULES rules 4, 11).

### Launch conditions (all must hold immediately before the live Daily)

1. **Fresh `OWNER_DAILY_HOST_PREFLIGHT_V1` = READY** (exit code 0). **AMBER (2) or BLOCKED (3) must
   not launch.** There is no override flag; the Owner launcher re-runs it in phase 1, before
   Canonical Daily is shown as started. Run `python -B tools/check_owner_daily_host_preflight.py` in the canonical main
   checkout. Bands: [owner_daily_host_preflight_contract.md](owner_daily_host_preflight_contract.md).
2. Producer, Consumer (`ai-core-private`) and Dashboard (`market-dashboard`) checkouts pass the Owner
   repository preflight (`tools/run_owner_daily.py`): right repo/origin, on `main`, clean, fast-forwardable.
   Untracked-path allowances are **per checkout** and defined by `checkout_cleanliness_contract.py` as applied
   there: the Consumer allows only `.worktrees/` (`CONSUMER_APPROVED_UNTRACKED_PREFIXES`); Producer and
   Dashboard checks use the default `APPROVED_RUNTIME_EVIDENCE_PREFIXES` (specific `data/<store>/` evidence
   subdirectories, not all of `data/`). Any tracked change or other untracked file blocks. Do not assume an
   untracked path is approved; run the preflight and read its verdict.
3. No other Daily/Producer writer is running; launch the Daily alone, with ordinary browsers/IDEs/
   unrelated Python workloads closed.
4. Existing evidence/runtime/session/window gates pass (they are not bypassed by a READY host).
5. DNSE credential injection available through the existing local source (the Daily raises
   `DNSE_CREDENTIAL_INJECTION_REQUIRED` otherwise). Never print or commit credentials.

## 2. CURRENT FACT — release state of the Monday-critical work

| Item | State | Contract / evidence |
|---|---|---|
| Feedback resource containment | **COMPLETE** (PR #58). Streaming proof/projection, 1,200 s total deadline, Windows Job Object, whole-tree reap accounting, single-winner COMPLETE-last publication, `FEEDBACK_CALL_RELATION = INCREMENTAL`. Fail-soft; never gates capture/marker/T0. | [owner_daily_feedback_resource_containment_contract.md](owner_daily_feedback_resource_containment_contract.md) |
| Host preflight | **COMPLETE** (PR #59), wired into the Owner launcher. Read-only, point-in-time, not a lease. | [owner_daily_host_preflight_contract.md](owner_daily_host_preflight_contract.md) |
| First-real capture final guardrails | **COMPLETE** (PR #60). Commit bands tightened to READY ≥12.0 / AMBER 9.2–12.0 / BLOCKED <9.2 GiB; acceptance now exposes `t0_snapshot_availability` and never reports T0 leakage as vacuously OPEN. | `first_real_session_acceptance.py`, Monday contract |
| Thesis Stage 2 | **COMPLETE**; automatic Monday hook **ENABLED**, fail-soft (`thesis_production_runtime.AUTOMATIC_HOOK_ENABLED = True`). Non-voting. | [thesis_evidence_stage_2_production_contract.md](thesis_evidence_stage_2_production_contract.md) |
| Technical V2 + Volume & Flow V2 | **COMPLETE**. Production selects V2 for sessions ≥ **2026-10-03**, so **2026-10-05 is the first production V2 session**. October 2 V2 is `REPLAY_DIAGNOSTIC / NON_AUTHORITATIVE`. V1 is frozen. | [contextual_technical_features_v2_contract.md](contextual_technical_features_v2_contract.md), [volume_and_flow_context_v2_contract.md](volume_and_flow_context_v2_contract.md) |
| Prospective capture completeness | **COMPLETE (code)**; first real session pending. | capture contract above |
| Provider runtime | Vnstock/VNAI/KBS/VCI runtime **retired**; DNSE/Livespeed is the provider direction; EODHD rejected. | `ROADMAP_STATE.json` blocked_capabilities, AI_RULES rule 8 |

## 3. Capture, marker and T0 on the first real session

- **CURRENT FACT — the write-once first marker is published for 2026-10-05.** Identity
  `first_complete_capture_session:48a52e9458f361aa50bbaf5297ab98d5ccb9d5d6f76a1522cb8290bc7c7028c3`,
  bound capture `prospective_capture_complete_session:661a12b7fd0bbbde2a747e660b88f7b1eb33b57ad6d96fc3db4ddef844327d5d`,
  `written_at` `2026-10-05T11:31:02.861384+00:00`. Exactly one original T0 directory:
  `operations-review/prospective-decision-retention-v1/2026-10-05/1c496e3f7a2df9770e269ef20821805ef0cb8c76d34ebb2869d72fbb61e319f9/`.
  Do not replace the marker, the capture record, the seal index, the write receipt, or that T0.
- **CURRENT FACT — marker semantics are `CAPTURE_COMPLETENESS_ONLY`.** `first_complete_capture_session`
  is write-once and does **not** require T0: the contract lists its preconditions (Phase-B `READY`,
  supported calendar, exact market/listing/binding batches, ≥1 capture-complete ticker) and binds
  "any genuine T0" optionally. `t0_snapshot_identity=None` is accepted; a later non-`None` T0 that
  differs from the recorded value raises `RECOVERY_T0_BINDING_MISMATCH` (expected immutability).
- **CURRENT FACT — T0 availability is independent.** The T0 snapshot (`prospective_decision_retention`)
  is streamed, content-addressed and fail-soft: a failure becomes `UNAVAILABLE` and the Daily
  continues. T0 is **one-shot per session** — no later rebuild. The seal index
  (`prospective_t0_seal_index/v1`) is derived from the snapshot and also fail-soft.
- **Reporting rule for Monday:** report capture, marker and T0 as three separate lines. "Capture yes,
  marker yes, T0 unavailable" is a legal outcome; it must never be labelled T0/PIT-ready. Rows that
  stay blocked/unknown without T0: `t0_snapshot_availability`, `exact_t0_v2_seal_index`,
  `t0_native_volume`, `post_to_t0_leakage` (NOT_EVALUABLE), all `thesis_t0_*` rows. Separately, first capture
  alone does not open `pit_continuous_price`, `raw_as_traded` or `ca` (evidence-blocked today; their opening
  predicates are conjunctions over qualified evidence). `official_verification` is conditional and
  use-dependent: it opens only when exact retained official ledgers/bodies have been verified later and every
  current name is `VERIFIED_MATCH`; the contract keeps that verification a separate later step, so it is not
  expected from the first-real run. The terminal
  owner screen does **not** print T0 status; read the acceptance report and the journal `t0_snapshot`
  attestation.
- **Streaming T0 write at real scale** (scratch benchmark, `PERFORMANCE_ONLY_NON_AUTHORITATIVE`,
  2026-10-04): 1,683 records, 1.30 GiB output, +~6 MB working set over a 1.93 GiB resident decision
  graph, ≈326 s for build + write + seal index.

## 4. HOST-LOCAL facts (verified 2026-10-04; not tracked by git)

- **Calendar registration: COMPLETE (local).** The original October-2 DNSE `working_dates` response
  (257 forward dates, 2026-10-02 … 2027-10-01, raw SHA-256 `fce46fe3…33d6d`) was registered once via
  `tools/register_working_dates_receipt.py`, offline, `network_requests = 0`, `historical_extension = false`,
  `authority_effect = NONE`. Registration `governed_calendar_registration:5cceff48f1f72934b856cc2cede8f959a276ce9f39f431057f0d27a2baf54941`,
  receipt `dnse_working_dates_calendar_receipt:c324eb2a9825b965db63eabf5dd4fd213290351fb9f7b91442cf56ab10143ca3`,
  stored under git-ignored `operations-review/prospective-calendar-evidence-v1/`. The resolver returns
  `2026-10-02 → 2026-10-05` governed continuity = `TRUE` solely because of that receipt, and `UNKNOWN`
  for cutoffs before its documentation knowledge time (2026-10-02T03:40:02Z). The September 5 – October 1
  gap stays `UNSUPPORTED_CALENDAR_GAP`. It did not create capture, T0, foreign maturity or backfill.
  Re-verify (run from the production checkout root, read-only): `python -c "import prospective_pit_capture_retention as s,governed_session_chain as g;from pathlib import Path;c=s.calendar_evidence_at_cutoff(Path('.'),cutoff='2026-10-05T12:10:00Z');print(g.are_consecutive_governed_sessions('2026-10-02','2026-10-05','2026-10-05T12:10:00Z',c)['state'])"`.
  Monday's own Daily also retains its own `working_dates` probe; registration is **not** required for
  first capture or marker, it affects continuity rows only.
- **Rehearsal scratch (15.24 GiB) deleted**; C: free was 35.61 GiB afterwards. Other `Temp\claude\*`
  and `Temp\codex-*` directories were classified UNCERTAIN and left alone.
- **Last observed host preflight (2026-10-04, after the above): `BLOCKED`** — available commit 9.11 GiB
  (<9.2), physical 3.22 GiB (AMBER), C: free 35.61 GiB (READY), writers none. An observation, not a
  permit: re-run immediately before launch. Close browsers/IDEs until READY; do not alter thresholds
  or kill processes from the tool.
- **2026-10-05 Owner Daily attempts (16:08, 16:35): refused by host preflight `BLOCKED`** (commit
  1.74 GiB, physical 1.02 GiB, C: 17.29 GiB). Cause: an orphaned Git-Bash `find / -name …` left by an
  agent session (started 05:46) held ~12.6M handles → ~8 GB kernel paged pool, and kept deleted files
  delete-pending. After it was stopped: commit 6.51 GiB (BLOCKED), physical 2.27 GiB (BLOCKED), C:
  27.1 GiB (READY). Remaining load is ordinary owner apps; the gate and thresholds are unchanged.
  Agents must never run root-wide `find /` (or other unbounded scans) on this host.
- **2026-10-05 Owner Daily 18:00 (run `ad670e74…`, main `f2721f4`): host READY, Canonical Daily exit 1**
  in `build_tiered_bundle` (`AttributeError: 'str' object has no attribute 'resolve'`). First
  trading session at/after `PRODUCTION_V2_START_SESSION`, so the first production RETAINED T0 seal
  index, whose serialized `{"path": str}` reached `_rel` (which assumed `Path`). Already sealed before
  the crash and verified read-only: T0 `prospective_decision_snapshot:1c496e3f…` (seal index,
  write receipt, file hash), capture session, first-complete-capture marker (2026-10-05), Thesis T0.
  No tier bundle, operation record, journal completion, state commit or publication; local
  `dashboard-runtime` was promoted at 18:26. Corrective (branch
  `fix/owner-daily-20261005-recovery-v1`): `_rel` accepts `Path | str`; a V2 session reuses its
  verified original sealed T0 instead of re-minting one (the operation identity embeds producer HEAD,
  so any rerun after a merge would otherwise seal a conflicting second T0). Child peak ~10 GB was
  reached in the telemetry-silent enrichment→Producer→T0 window; attribution is a separate resource
  milestone.
- **2026-10-05 Owner Daily rerun 19:56 (main `c7362dd`): Canonical Daily `LOCAL_COMPLETE`**
  (operation `daily_research_session_operation:140adc8a…`, original T0 reused), Producer state and
  Dashboard published, then AI handoff `AI_HANDOFF_REQUIRED_FILE_MISSING`. The first attempt's own
  after-close rollforward had retained a post-cutoff event context (`…-20261005`), which hid the
  eligible `29f3a1bc…` (`…-20261002`) from the rerun; the completed lock therefore has no
  `event_context`, so the operation built no opportunity decision queue — while the handoff required
  it unconditionally. Corrective (branch `fix/owner-daily-final-recovery-20261005`): the event
  context is the newest candidate known by the unchanged 15:00 cutoff; the handoff requires the queue
  exactly when the sealed operation declares it (identity-checked) and otherwise publishes an
  explicit `NOT_DECLARED_BY_SEALED_OPERATION`. The completed 2026-10-05 lock is kept as recorded.
- **2026-10-05 Owner Daily completion (resume on `317118c`): PASS.** Canonical Daily was not rerun.
  Dashboard `origin/main` `5a050b46b2092e2d5bac2c0af216624447800c83`, `market_session` 2026-10-05,
  attestation `governed_publication_attestation:6daf0b708354b0384286a5c331c1765011602e446ffcd1ecd2322b3570955808`,
  Dashboard CI `37335772813` and Deploy Pages `37335959559` both success, public-byte identity PASS.
  AI handoff `origin/main` `9f379cc2b6f1655806ed42d63161c17479e79951`, `READY_FOR_AI`, queue
  `NOT_DECLARED_BY_SEALED_OPERATION`. Action Center
  `personal_investment_decision_action_center/v1:37ec23f5d430ce11b89520f171d8c4d8d0011c26b2b0feb59752e0efa435514a`.
  First real Canonical-child `peak_rss_bytes` = `10985897984` (~10.23 GiB), above the 6.5–8.0 GiB
  band. Later publication-only resumes peaked at `6840815616` and `2057273344` because they skipped
  Canonical Daily. Merged before that PASS: PR #64 `c316458` (companion run binding), PR #65
  `cc8f548` (hermetic host fixture; dashboard failure reason kept), PR #66 `317118c` (`gh run watch`
  conclusion). Producer CI `37335518993` on `317118c` succeeded. Volume-and-flow context and the
  Thesis T0 sidecar for this session stayed `UNAVAILABLE` (no `event_context` on the frozen lock;
  reused T0 source IID differs from the later IID). Both are fail-soft. The lock and the T0 were
  not rewritten.

## 5. BLOCKED (evidence-blocked; do not work around)

- Corporate-action factor chain: 0 qualified events → PIT-adjusted history, PIT backtest and execution
  replay stay blocked. Prospective raw-as-traded is qualified only for bars equal to the official HOSE
  series; historical raw is PARTIAL (HOSE, research grade).
- `ACTIVE_UNIVERSE` authority: `UNKNOWN` for all instruments (no official listing-status proof from DNSE).
- Reverse / intrinsic valuation outputs: no governed intrinsic evaluator output or FCFF inputs.
- Execution-grade liquidity, canonical participation/horizon policy, position sizing authority.
- Continuous-price and standing-signal PIT readiness. Official verification of prospective RAW is conditional
  on later exact retained official ledgers (a separate step), not blocked by design.
- Foreign-flow 10/20-session maturity and Friday-governed continuity beyond the registered receipt.

## 6. HISTORICAL — do not treat as current

- Legacy `STATE.md` banners say "calendar registration remains unexecuted / owner-gated": true when
  written; **superseded** by §4 (host-local, 2026-10-04).
- The 9,853,145,088-byte (~9.18 GiB) core peak is **STALE** (removed whole-string T0 write). The
  planning band remains **6.5–8.0 GiB, 8.0 a floor not a ceiling**. The first real Canonical-child
  measurement is `10985897984` bytes (§4). Do not lower host thresholds to fit it.
- **HISTORICAL — as checked 2026-10-04, first marker is null and complete-capture count is 0.**
  Superseded by §3 on 2026-10-05. The 2026-10-02 T0 remains `UNAVAILABLE`.
- **HISTORICAL — no live Daily had run since 2026-10-02** was true on 2026-10-04. Superseded by §1.
- `OWNER_DAILY_ONE_CLICK.md` says "at or after about 16:30"; the Monday contract targets ~16:00 under the
  15:30 attempt floor. Use the Monday contract for 2026-10-05.
- M1 live acceptance (2026-09-28, `DNSE_PRIMARY_UNCORROBORATED`), Thesis Stage 1 (offline, frozen),
  the R1–R7 program closeouts, Vnstock operation and every dated section of the giant narrative files.

## 7. DEFERRED

- Control-plane simplification **Phase B/C** (archive/move of history, runtime simplification): defined
  in [ROADMAP_CURRENT.md](ROADMAP_CURRENT.md), **not authorized, not started**.
- R7 authority promotion (`AUTHORITY_PROMOTION_PENDING_EVIDENCE_OR_OWNER_APPROVAL`).
- Any later analytical milestone, new provider, new authority, or calibration use of learning outputs.
- Worktree pruning (186 worktrees listed at last count) and artifact/scratch cleanup beyond what the owner approved.

## 8. Actual blockers right now

1. The 2026-10-05 Owner Daily is complete. No additional documented blocker is currently known
   for that session. A later ordinary Daily must still pass at launch: every runtime, evidence,
   session and window gate (Phase A/B, calendar, credentials, repository preflight, runtime/trusted release)
   still applies.
2. A later ordinary Daily still needs a fresh `OWNER_DAILY_HOST_PREFLIGHT_V1` = **READY**. The
   post-closeout observation was **BLOCKED**: writers `WRITER_STATE_UNKNOWN` (one encoded PowerShell
   child of the IDE; `active_writers` empty) and physical memory **AMBER** (~6.0 GiB available against
   the 6 GiB green band). Commit and disk were READY. Thresholds are unchanged. Close IDEs and other
   heavy processes, then re-run the preflight. **AMBER or BLOCKED must not launch.**

## 9. Next action

Do not launch the next session early. Before 15:00 Asia/Ho_Chi_Minh on the next civil day, the
calendar anchor is still 2026-10-05, so an ordinary launch idempotently replays that completed
publication. At or after 16:00 on the next trading day: close ordinary background workloads → run
host preflight → launch only on READY → `stocklookup.ps1 daily` (or the Desktop one-click) alone.
That launch resolves 2026-10-06 and does not replay 2026-10-05. Do not start Phase B/C.

## 10. Owner approvals that remain open

- Explicit start of any post-Monday milestone (including simplification Phase B/C).
- Any further cleanup of host scratch / `Temp\*` / worktrees (only the five rehearsal directories were approved).
- R7 / RAW / PIT / execution authority promotion; any new provider; any threshold change to the host preflight.
