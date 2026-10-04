# Stock Lookup — Active State

Compact, authoritative view of what is true **now**. Read this first; it is small on purpose.
Written 2026-10-04 (Sunday) against Producer `main` `920d57917581a476e3ab6a9cf40d9ca53643ecb2`
(PR #60 merged). `git rev-parse origin/main` reads only the **local** remote-tracking ref and can be stale.
To verify the live remote head run `git fetch origin main` and then compare `git rev-parse origin/main`
(or ask the remote directly with `git ls-remote origin refs/heads/main`). The only change intended after
the SHA above is the docs-only control-plane PR that introduced this file.

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

- **CURRENT FACT — active operational gate:** `FIRST_REAL_POST_RELEASE_CAPTURE_ACCEPTANCE` = **PENDING**.
  It is the first ordinary successful post-release Daily on the actual session **2026-10-05
  (Monday)**, launched around **16:00 Asia/Ho_Chi_Minh** under the unchanged Phase-A eligibility
  gate (the 15:30 attempt floor is not lowered). Capture window: 15:00 on the session to 09:00 next
  civil day. Contract: [monday_live_readiness_closeout_contract.md](monday_live_readiness_closeout_contract.md),
  [prospective_pit_capture_completeness_contract.md](prospective_pit_capture_completeness_contract.md).
- **CURRENT FACT — no live Daily has run since 2026-10-02.** That run completed `READY` but its T0
  failed with `MemoryError` and stays permanently `UNAVAILABLE` (a 0-byte file is retained; never
  rebuilt). `ROADMAP_STATE.json`: `current = OWNER_DAILY_FEEDBACK_RESOURCE_CONTAINMENT_V1 / COMPLETE`,
  `queued_next = []`, `successor_disposition = FIRST_REAL_POST_RELEASE_CAPTURE_ACCEPTANCE_PENDING_NO_AUTOMATIC_SUCCESSOR`.
- **CURRENT FACT — no automatic successor.** Nothing starts because something else finished;
  every new milestone needs explicit owner authorization (AI_RULES rules 4, 11).

### Launch conditions (all must hold immediately before the live Daily)

1. **Fresh `OWNER_DAILY_HOST_PREFLIGHT_V1` = READY** (exit code 0). **AMBER (2) or BLOCKED (3) must
   not launch.** There is no override flag; the Owner launcher re-runs it before spawning the
   canonical child. Run `python -B tools/check_owner_daily_host_preflight.py` in the canonical main
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

- **CURRENT FACT — first marker is null and complete-capture count is 0.** `operations-review/prospective-pit-capture-v1`
  does not exist in the production root (checked 2026-10-04). Nothing creates a marker except a
  genuine Phase-B-READY Daily with capture-complete tickers.
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
  current-main Daily-child working band is **6.5–8.0 GiB, 8.0 a floor not a ceiling**; Monday is
  unmeasured. See the host-preflight contract.
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

1. A READY host preflight is not yet observed (last observation BLOCKED on commit headroom).
2. No additional documented blocker is currently known. That is not a launch permit: every runtime, evidence,
   session and window gate (Phase A/B, calendar, credentials, repository preflight, runtime/trusted release)
   must still pass at launch.

## 9. Next action

On 2026-10-05, around 16:00 Vietnam time: close ordinary background workloads → run host preflight →
launch only on READY → `stocklookup.ps1 daily` (or the Desktop one-click) alone → read the Vietnamese
final screen **and** the first-real acceptance report. If anything is red, send the displayed failure
summary and log path; never run two writers; never manually push generated files while it runs.

## 10. Owner approvals that remain open

- Explicit start of any post-Monday milestone (including simplification Phase B/C).
- Any further cleanup of host scratch / `Temp\*` / worktrees (only the five rehearsal directories were approved).
- R7 / RAW / PIT / execution authority promotion; any new provider; any threshold change to the host preflight.
