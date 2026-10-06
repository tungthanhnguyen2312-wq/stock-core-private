# Stock Lookup — Current Roadmap

What happens next, and nothing else. No historical milestones (those live in [ROADMAP.md](ROADMAP.md) and
the machine state `ROADMAP_STATE.json`). Written 2026-10-04 on main `920d579`. **Nothing below
auto-starts.** A milestone starts only when `python tools/stocklookup_roadmap.py --can-start <ID>` allows
it or the owner records an explicit override (AI_RULES rule 11). Facts: [ACTIVE_STATE.md](ACTIVE_STATE.md).

## NOW — `FIRST_REAL_POST_RELEASE_CAPTURE_ACCEPTANCE` (RECORDED 2026-10-05)

Recorded. The explicitly owner-authorized candidate-local Phase C below is complete and
awaits review. No successor milestone is active, and nothing here starts one.

**2026-10-06 candidate-local checkpoint:**
`POST_FIRST_REAL_DAILY_PHASE_C_RESOURCE_AND_ARTIFACT_SIMPLIFICATION_V1` is COMPLETE /
`PHASE_C_RESOURCE_SIMPLIFICATION_READY_FOR_REVIEW`. Branch `perf/post-first-real-daily-phase-c-resource-simplification-20261006`
starts from exact `802b11e00a2bb38db7f57644dca9f3ba463e1522`; canonical main is unchanged.
Bounded real-scale Producer private peak 4.15 GiB, five outputs byte-identical. Historical
Oct 6 child RSS peak is 9.93 GiB; the 10.23-GiB figure below is Oct 5 rerun. Whole-Daily
capacity is not requalified. [Resource map, parity, gates and review boundary](internal/POST_FIRST_REAL_DAILY_PHASE_C_RESOURCE_SIMPLIFICATION_20261006.md).
Next recommendation only: merge this Phase C candidate after review. No push/merge is
authorized here and `queued_next` stays empty. Read-only Oct 6 capture chain has depth 2,
`DEPTH_PENDING`; first-real evidence below remains historical and unchanged.

**Result** (read-only harness, cutoff `2026-10-05T16:00:00Z`):
- *Capture:* complete. `prospective_capture_complete_session:661a12b7fd0bbbde2a747e660b88f7b1eb33b57ad6d96fc3db4ddef844327d5d` (658 capture-complete tickers; 853 exact-session observed).
- *Marker:* published. `first_complete_capture_session:48a52e9458f361aa50bbaf5297ab98d5ccb9d5d6f76a1522cb8290bc7c7028c3`, session 2026-10-05, `written_at` `2026-10-05T11:31:02.861384+00:00`.
- *T0:* available. `prospective_decision_snapshot:1c496e3f7a2df9770e269ef20821805ef0cb8c76d34ebb2869d72fbb61e319f9`; seal index `prospective_t0_seal_index:afe7fe3b1cda2e2d7f8e10f7d61e8a77932ea9939eff13ede4de2327ba6e6fb6`.

Readiness count is 1 and `DEPTH_PENDING`. Representation tier is OPEN. `positive_listing` stays
`STILL_BLOCKED` (195 UNKNOWN exchange). `official_verification` stays conditional and closed;
`raw_as_traded` and `ca` stay closed. Calendar receipt is OPEN. Owner Daily journal is `COMPLETE`.

**Measured Canonical-child peak:** `peak_rss_bytes` `10985897984` (~10.23 GiB), above the 6.5–8.0 GiB
band. That band is unchanged. Publication-only resumes are not this measurement.

The next ordinary Daily is the next completed market session after a fresh READY host preflight.
It is not a new milestone. `queued_next` stays empty.

## NEXT EVIDENCE GATE — time-driven, not milestones

These advance by accumulating real sessions, not by implementation:
- Contiguous governed capture depth at 20 / 21 / 50 / 60 / 120 / 250 sessions
  (`READY_FOR_BOUNDED_EVALUATION` is an invitation to a separately governed review, never authorization).
- Outcome maturity: T+20 / T+60 decisions mature only after their windows; foreign-flow 10 / 20-session cohorts.
- Calendar forward coverage: `CALENDAR_REFRESH_NEEDED` when known forward coverage drops below the
  60-session maximum outcome horizon (no invented refresh schedule).
- Later official verification of prospective RAW from exact retained ledgers.

## AFTER FIRST-REAL ACCEPTANCE — candidates, owner authorization required

1. **Record the first-real result** — done in this control plane (docs only; no runtime change). Phase B is not started; candidate-local Phase C is complete above.
2. **Control-plane simplification Phase B** (not started): move or archive historical narrative out of the default
   path (`STATE.md` / `DECISIONS.md` / `ROADMAP.md` dated sections), keep every machine marker, parser and
   `ROADMAP_STATE.json` contract working, update the drift/governance tests in the same change. Preserve history.
3. **Simplification Phase C** (candidate-local complete, awaiting review): runtime/architecture simplification only where post-Monday
   measurements justify it. Inputs are the measured figures in [owner_daily_host_preflight_contract.md](owner_daily_host_preflight_contract.md)
   and [owner_daily_feedback_resource_containment_contract.md](owner_daily_feedback_resource_containment_contract.md)
   (per-session artifacts are large: Integrated Decision ≈1.3 GB, T0 ≈1.4 GB, feedback ≈0.5 GB; the Daily-child
   peak includes silent Producer/observer intervals). The local scope and measured allocation
   causes are recorded in the linked report; exact historical instruction attribution is unavailable.

## LATER — blocked on evidence or an owner decision

- Corporate-action factor qualification → PIT-adjusted history, PIT backtest, execution replay.
- R7 / RAW / PIT / execution authority promotion (`AUTHORITY_PROMOTION_PENDING_EVIDENCE_OR_OWNER_APPROVAL`).
- Intrinsic / reverse valuation (needs governed FCFF/WACC/terminal inputs); official financial statement currency refresh.
- Execution-grade liquidity and canonical participation/horizon policy; capital/risk-budget bindings.
- Any new market-data provider (requires a new owner decision; EODHD rejected; Vnstock retired).
- Calibration use of prospective learning outputs (sample-limited; human review only).
