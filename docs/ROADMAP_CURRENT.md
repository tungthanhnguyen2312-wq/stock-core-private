# Stock Lookup — Current Roadmap

What happens next, and nothing else. No historical milestones (those live in [ROADMAP.md](ROADMAP.md) and
the machine state `ROADMAP_STATE.json`). Written 2026-10-04 on main `920d579`. **Nothing below
auto-starts.** A milestone starts only when `python tools/stocklookup_roadmap.py --can-start <ID>` allows
it or the owner records an explicit override (AI_RULES rule 11). Facts: [ACTIVE_STATE.md](ACTIVE_STATE.md).

## NOW — `FIRST_REAL_POST_RELEASE_CAPTURE_ACCEPTANCE` (PENDING)

The first ordinary successful post-release Daily on the actual session **2026-10-05**, around 16:00
Asia/Ho_Chi_Minh, under the unchanged Phase-A eligibility gate.

**Prerequisite:** a fresh `OWNER_DAILY_HOST_PREFLIGHT_V1 = READY` immediately before launch
(AMBER/BLOCKED do not launch; no override). Plus the other launch conditions in ACTIVE_STATE §1.

**What the run must demonstrate** (contract: [prospective_pit_capture_completeness_contract.md](prospective_pit_capture_completeness_contract.md),
[monday_live_readiness_closeout_contract.md](monday_live_readiness_closeout_contract.md)):
1. Exact bars, same-session listings and representation tier bound to the session.
2. The Daily's own `working_dates` probe retained as a calendar receipt.
3. One complete session record and the write-once first marker published; readiness advances exactly one
   session (complete count 0 → 1; marker was null).
4. Later official verification stays separate (not part of this acceptance).

**How to read the result** — report three independent lines, never a single "ready":
- *Capture:* complete / incomplete / late, with the record identity.
- *Marker:* published / already present / not published.
- *T0:* available (snapshot + seal index identities) / `UNAVAILABLE` with reason.
  A T0-less complete session is a legal outcome; it opens capture and marker rows only.

Run the read-only harness afterwards: `python tools/run_first_real_session_acceptance.py --session 2026-10-05 --cutoff <actual> …`
(write the report under `operations-review/first-real-session-acceptance-v1/<session>/`). Capability rows
that must stay blocked or unknown regardless: `pit_continuous_price`, `raw_as_traded`, `ca`,
`official_verification`; first capture alone cannot open broad PIT or RAW. Also record, from the telemetry,
the measured `peak_rss_bytes` of the Daily child: it is the first real measurement against the 6.5–8.0 GiB band.

## NEXT EVIDENCE GATE — time-driven, not milestones

These advance by accumulating real sessions, not by implementation:
- Contiguous governed capture depth at 20 / 21 / 50 / 60 / 120 / 250 sessions
  (`READY_FOR_BOUNDED_EVALUATION` is an invitation to a separately governed review, never authorization).
- Outcome maturity: T+20 / T+60 decisions mature only after their windows; foreign-flow 10 / 20-session cohorts.
- Calendar forward coverage: `CALENDAR_REFRESH_NEEDED` when known forward coverage drops below the
  60-session maximum outcome horizon (no invented refresh schedule).
- Later official verification of prospective RAW from exact retained ledgers.

## AFTER FIRST-REAL ACCEPTANCE — candidates, owner authorization required

1. **Record the first-real result** in this control plane (a small docs update; no runtime change).
2. **Control-plane simplification Phase B** (not started): move or archive historical narrative out of the default
   path (`STATE.md` / `DECISIONS.md` / `ROADMAP.md` dated sections), keep every machine marker, parser and
   `ROADMAP_STATE.json` contract working, update the drift/governance tests in the same change. Preserve history.
3. **Simplification Phase C** (not started): runtime/architecture simplification only where post-Monday
   measurements justify it. Inputs are the measured figures in [owner_daily_host_preflight_contract.md](owner_daily_host_preflight_contract.md)
   and [owner_daily_feedback_resource_containment_contract.md](owner_daily_feedback_resource_containment_contract.md)
   (per-session artifacts are large: Integrated Decision ≈1.3 GB, T0 ≈1.4 GB, feedback ≈0.5 GB; the Daily-child
   peak sits in the Producer delivery stage). Scope is decided after Monday, not before.

## LATER — blocked on evidence or an owner decision

- Corporate-action factor qualification → PIT-adjusted history, PIT backtest, execution replay.
- R7 / RAW / PIT / execution authority promotion (`AUTHORITY_PROMOTION_PENDING_EVIDENCE_OR_OWNER_APPROVAL`).
- Intrinsic / reverse valuation (needs governed FCFF/WACC/terminal inputs); official financial statement currency refresh.
- Execution-grade liquidity and canonical participation/horizon policy; capital/risk-budget bindings.
- Any new market-data provider (requires a new owner decision; EODHD rejected; Vnstock retired).
- Calibration use of prospective learning outputs (sample-limited; human review only).
