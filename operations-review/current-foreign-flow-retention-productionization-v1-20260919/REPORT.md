# Current Foreign-Flow Retention Productionization V1

`CURRENT_FOREIGN_FLOW_RETENTION_PRODUCTIONIZATION_V1 = IMPLEMENTATION_COMPLETE / NO_NETWORK_LIVE_ACCEPTANCE_PENDING`

Owner-directed, architecture-only milestone (this session, 2026-09-19). No live DNSE provider
call was made anywhere in this session, even though a real, valid
`C:\Users\tungt\.stocklookup\secrets.env` exists on this machine — every test that reaches the
`allow_network=True` code path either supplies explicit fake credentials with an injected fake
`request_get`, or explicitly redirects the credential file lookup to a path that does not exist.

## 1. Mission

Wire the existing (already-implemented, already-tested) foreign-flow retention foundation —
manifest, raw retention contract, raw→VALUE adapter, VALUE-only store — into one resumable,
bounded, network-off-by-default operational path, so that a later, separately owner-authorized
invocation can freeze the cohort, acquire the 11 unresolved tickers, resume safely, persist
qualified VALUE, verify exact-session freshness, rebuild Flow–Price, and expose compact status —
without any code change or manual file manipulation.

## 2. Architecture

```
current_foreign_flow_acquisition_manifest/v1      (IMMUTABLE — current_foreign_flow_retention.py)
        |  what should be acquired: 11-ticker cohort, frozen from owner_research_focus ∩
        |  current_research_official_universe_scope, for one reference_session.
        v
current_foreign_flow_enrichment_operation/v1      (MUTABLE  — current_foreign_flow_enrichment_operation.py)
        |  what has happened: per-ticker state, network usage, failure/conflict detail,
        |  rebuilt fresh from currently retained evidence on every invocation.
        |
        |-- network boundary: acquire_foreign_flow_for_manifest(..., allow_network=False)
        |       -> reuses tools/bulk_ingest_dnse_foreign_trading_raw.run() (unmodified),
        |          called once per pending ticker (stable per-ticker checkpoint scope)
        |-- adapter: current_foreign_flow_retention.normalize_exact_raw_page /
        |            write_exact_value_observation (unmodified)
        |-- verification: verify_ticker_current() reusing dnse_foreign_flow_store.build_series
        v
dnse_foreign_flow_store (VALUE-only, existing)  -->  flow_price_divergence_shadow/v1 (existing, unchanged)
                                                 -->  current_foreign_flow_positioning_bridge.py (new,
                                                      investigated, NOT wired into live Daily)
```

Placement in `canonical_post_close_pipeline.run_canonical_post_close`:

```
CORE DAILY (producer_result, tiered bundle, session_handoff_bundle.json written)
  -> run_multi_session_signal_velocity_shadow          (existing, unchanged)
  -> run_current_foreign_flow_enrichment(allow_network=enable_current_foreign_flow_live)  (NEW)
  -> run_flow_price_divergence_shadow                  (existing, unchanged; now sees any
                                                          freshly-acquired VALUE from the step above)
```

All three post-handoff steps are best-effort: an exception inside any of them is caught and
degrades to a visible `UNAVAILABLE` status; none can fail Core Daily, revise the immutable T0
decision snapshot, or block the AI handoff. `enable_current_foreign_flow_live` defaults to
`False` in `run_canonical_post_close` and is only set from the CLI's
`--enable-current-foreign-flow-live` flag, which the owner must pass explicitly.

## 3. Operation contract

`current_foreign_flow_enrichment_operation/v1` fields: `schema_version`, `contract_version`,
`reference_session`, `acquisition_manifest_identity`, `requested_tickers`, `excluded_tickers`,
`records` (per ticker), `counts`, `complete_count`, `pending_count`, `failed_count`,
`conflict_count`, `session_issue_count`, `network` (`allow_network`, `credentials_available`,
`credential_note`, `network_calls_made`), `authority_boundary`, `timestamps`, `status`,
`operation_identity`/`operation_sha256` (content hash excluding timestamps).

## 4. Per-ticker state machine

`PENDING`, `RAW_ALREADY_RETAINED`, `RAW_ACQUIRED`, `VALUE_ALREADY_RETAINED`, `VALUE_PERSISTED`,
`COMPLETE`, `FAILED_RETRYABLE`, `FAILED_TERMINAL`, `SESSION_MISSING`, `SESSION_MISMATCH`,
`RAW_CONFLICT`, `VALUE_CONFLICT`, `SKIPPED_ALREADY_COMPLETE`,
`NETWORK_DISABLED_PENDING_ACQUISITION`, `CREDENTIAL_UNAVAILABLE`. Every ticker in
`requested_tickers` terminates in exactly one state each call; `state_history` on each record
shows the transitions taken. Deterministic reduction to operation `status`:
`COMPLETE` (all complete) / `PARTIAL` (some complete) / `PENDING_NETWORK` (all pending, network
off or all credential-blocked-but-none-attempted) / `FAILED_OPERATIONAL` (all failed) /
`BLOCKED_CONFLICT` (conflicts present, nothing pending) / `UNAVAILABLE` (empty cohort or mixed
case none of the above matches) — see `current_foreign_flow_enrichment_operation._reduce_status`.

## 5. Network boundary

`acquire_foreign_flow_for_manifest(manifest, *, runtime_root, allow_network=False, ...)` is the
only function in this codebase permitted to reach the live DNSE foreign-trading endpoint for
this contract. No environment variable can enable it; the caller must pass the keyword
explicitly. Every ticker that needs acquisition under the default reports
`NETWORK_DISABLED_PENDING_ACQUISITION` — a status field, never an exception — so normal Daily is
always safe by construction.

## 6. Credential boundary

Credentials are resolved only inside the network path, only when `allow_network=True` and the
caller did not already supply `api_key`/`api_secret` (tests always do, to guarantee no real
network reach). Resolution reuses `dnse_secrets_env.ensure_credentials_loaded` /
`dnse_access.credential_status` / `credentials_for_request` unmodified. No secret is ever placed
in the returned operation record, a log line, or an exception message — only a boolean
`credentials_available` and the bounded reason `CREDENTIAL_UNAVAILABLE_UNDER_LIVE_FLAG`.

## 7. Raw acquisition integration

Reuses `tools/bulk_ingest_dnse_foreign_trading_raw.run()` verbatim, invoked once per pending
ticker (not once for the whole cohort): this keeps each ticker's raw-lake checkpoint scope
stable and independent of which other tickers are already complete, which is what makes
resuming a partially-completed operation correct without touching `bulk_ingest`'s own code. No
second HTTP client, retry policy, or pagination loop was written.

## 8. Raw → VALUE integration

Reuses `current_foreign_flow_retention.normalize_exact_raw_page` and
`write_exact_value_observation` verbatim. The adapter's existing constraint (a raw page must not
carry a `nextPageToken`) is preserved as-is: this milestone reads back exactly the first
retained page (cursor=`None`) for a work unit and feeds it to the unmodified adapter. A
genuinely multi-page raw session (proven possible and independently resumable at the raw layer)
therefore fails closed at the adapter step with `FAILED_TERMINAL:RAW_PAGE_PAGINATION_NOT_COMPLETE`
rather than silently normalizing an incomplete page — see §14 Known Limitations.

## 9. Store conflict policy

If no raw is retained for a ticker/session and a qualified exact-session VALUE observation
already is, it is trusted without reacquisition or re-derivation (`SKIPPED_ALREADY_COMPLETE`).
If raw IS retained (fresh this run, or from an earlier run), it is always re-normalized and
handed to `write_exact_value_observation`'s own conflict guard: identical content is a harmless
rewrite, differing content raises and is surfaced as `VALUE_CONFLICT` — the existing store's
data is never overwritten.

## 10. Post-Core-Daily placement

`run_current_foreign_flow_enrichment` runs strictly after `build_tiered_bundle` has written
`session_handoff_bundle.json` (the same binding gate the existing Signal-Velocity and
Flow-Price-Divergence observers already use), and before `run_flow_price_divergence_shadow` so a
same-day live acquisition's freshly-persisted VALUE is visible to that step's exact-session read
of the store. Its own failure is caught and reported as `UNAVAILABLE`; it cannot alter
`producer_result`, the decision packet, or the AI handoff.

## 11. Explicit activation mechanism

Option A from the brief: `canonical_post_close_pipeline.py`'s CLI gained
`--enable-current-foreign-flow-live` (default off). `run_canonical_post_close(...,
enable_current_foreign_flow_live=False)` is the corresponding function default. Promotion to an
automatic post-close step later is exactly flipping that one default plus an explicit STATE.md
disposition change — no other wiring is required.

## 12. Operator command

`tools/enrich_current_foreign_flow.py --session <YYYY-MM-DD> [--dry-run | --live]
[--retry-failed] [--resume] [--secrets-file PATH]`. Default (no `--live`) is a pure no-network
plan/status report. `--live` is the one flag that authorizes a real network call.

## 13. Resume / idempotency proof

`tests/test_current_foreign_flow_enrichment_operation.py::test_case_l_rerun_is_idempotent_and_makes_no_further_network_calls`
runs the full 11-ticker operation twice against the same `runtime_root`: the second run makes
zero additional network calls, reaches the same `COMPLETE` status with the same per-ticker
states, and the same `acquisition_manifest_identity`/`counts`.
`test_case_d_retained_raw_without_store_runs_adapter_only` proves a raw-retained-but-store-empty
ticker completes with zero network calls. `test_case_h_multipage_raw_resumes_then_adapter_fails_closed_on_pagination`
proves an interrupted 2-page raw fetch resumes without re-requesting page 0 (checkpoint-level
resume, reusing the already-tested `bulk_ingest` machinery), then documents the honest
single-page adapter limit.

## 14. Simulated 11/11 result (CASE A)

`test_case_a_eleven_of_eleven_success`: all 11 cohort tickers reach `COMPLETE`, operation status
`COMPLETE`, 11 network calls, and the store holds only VALUE fields (no `volume`/`room` key
anywhere in the retained observation).

## 15. Simulated partial result (CASE B)

`test_case_b_partial_success_reduces_to_partial_status`: 8 `COMPLETE`, 2 `FAILED_RETRYABLE`
(simulated HTTP 429 exhausting retries), 1 `SESSION_MISSING` (empty `foreigners` response) →
operation status `PARTIAL`. Matches the brief's example shape exactly (Core Daily unaffected,
foreign-flow enrichment `PARTIAL`).

## 16. Normal Daily zero-network proof

`tests/test_canonical_post_close_current_foreign_flow_enrichment.py::test_default_network_off_reports_pending_network_and_touches_no_network`
calls the pipeline step with its real default (`allow_network` omitted) and asserts
`network_calls_made == 0` and every ticker is `NETWORK_DISABLED_PENDING_ACQUISITION`; the
credential-resolution code path inside `acquire_foreign_flow_for_manifest` is provably never
entered when `allow_network` is `False` (it lives behind an `if allow_network:` guard), so no
`secrets.env` read is even attempted.

## 17. Flow positioning integration (Phase 13)

`current_foreign_flow_positioning_bridge.build_from_store()` projects the retained VALUE store
into `current_market_flow_positioning/v1`'s existing canonical-observation input shape (via
`canonical_market_evidence_integration.integrate_session_packet`), bridging only the
already-qualified `FOREIGN_BUY_VALUE`/`FOREIGN_SELL_VALUE`/`FOREIGN_NET_VALUE` triple for
exact-session-current tickers — never volume or room, never a fabricated dimension for an
absent ticker. It is tested (`tests/test_current_foreign_flow_positioning_bridge.py`) but
**deliberately not wired into live Daily**: `current_market_flow_positioning/v1` already has one
live producer (`tools/collect_market_evidence.py` via `build_enrichment_components`); adding a
second producer of the same contract-versioned artifact is a distinct future integration
decision, not made in this architecture-only milestone.

## 18. Flow–Price integration

Unchanged. `run_flow_price_divergence_shadow` already reads `dnse_foreign_flow_store` directly
and needed no modification; placing the new enrichment step immediately before it in the
pipeline is the entire integration. `test_case_k_flow_price_stays_honest_when_velocity_record_absent`
proves that after a successful store update, a Velocity-record-absent session still reports
`PRICE_EVIDENCE_INSUFFICIENT`/`RELATIONSHIP_NOT_EVALUABLE` rather than fabricating a relationship.

## 19. Handoff metadata

`session_handoff_bundle.json`'s `tier1["current_foreign_flow_enrichment"]` carries: `status`,
`operation_identity`, `manifest_identity`, `reference_session` (implicit via `session` field on
the wrapper result), `requested_count`, `complete_count`, `pending_count`, `failed_count`,
`conflict_count`, `network_calls_made`, `authority_boundary` — never the 11 full per-ticker
records.

## 20. Test counts

- New: 16 (`test_current_foreign_flow_enrichment_operation.py`, CASE A–L plus verification/
  status-reduction/snapshot-write unit coverage) + 2 (`test_current_foreign_flow_positioning_bridge.py`)
  + 4 (`test_canonical_post_close_current_foreign_flow_enrichment.py`) = **22 new tests**, all
  passing.
- Regression: 104 pre-existing tests across `test_current_foreign_flow_retention.py`,
  `test_dnse_foreign_flow_capability.py`, `test_dnse_foreign_flow_store.py`,
  `test_bulk_ingest_dnse_foreign_trading_raw.py`, `test_flow_price_divergence_shadow.py`,
  `test_multi_session_signal_velocity.py`, `test_current_market_flow_positioning.py`,
  `test_current_market_flow_positioning_scaleout.py` — all pass unchanged.
- `python tools/stocklookup_roadmap.py --check` after the `ROADMAP_STATE.json` update: `PASS`
  (drift check, dependency consistency, checkpoint existence, stale-next-pointers, multiple
  active writers all pass).
- Full `tests/test_canonical_post_close_pipeline.py` (broader, not directly targeted by this
  milestone): 55 passed / 1 failed. The one failure
  (`test_canonical_post_close_flag_never_invokes_legacy_step_runner`) is confirmed
  **pre-existing**: reproduced identically against a temporary detached worktree at the pristine
  starting commit `a0e883595d93d99bb4f32b5518634556be461f00`, before any change in this
  milestone. Its preflight gate requires `HEAD == origin/main`; this checkout was already
  intentionally kept several commits ahead of `origin/main` before this session began (per the
  owner's own starting instructions), so the gate fails closed regardless of this diff.

## 21. Files changed / added

New: `current_foreign_flow_enrichment_operation.py`, `current_foreign_flow_positioning_bridge.py`,
`tools/enrich_current_foreign_flow.py`, `tests/test_current_foreign_flow_enrichment_operation.py`,
`tests/test_current_foreign_flow_positioning_bridge.py`,
`tests/test_canonical_post_close_current_foreign_flow_enrichment.py`, this report. Modified:
`canonical_post_close_pipeline.py` (new step + CLI flag + handoff line),
`docs/STATE.md`, `docs/ROADMAP.md`, `docs/DECISIONS.md`, `docs/ROADMAP_STATE.json`.

## 22. Exact future live command

```
python tools/enrich_current_foreign_flow.py --session <next-completed-session> --live
```

or, folded into the normal owner-approved post-close run:

```
python canonical_post_close_pipeline.py --runtime-root <root> --session <next-completed-session> \
    --enable-current-foreign-flow-live
```

## 23. Live acceptance criteria (for the next, separately authorized session)

1. Manifest resolves to the exact governed 11-ticker cohort for that session.
2. At least one ticker reaches `COMPLETE` via a real DNSE round trip (raw retained, VALUE
   persisted, `verify_ticker_current` returns `CURRENT`).
3. A second, immediate rerun of the same command makes zero additional network calls and
   reaches the same terminal per-ticker states (idempotency, not just "ran twice").
4. `flow_price_divergence_shadow`'s next post-close run for that session shows
   `relationship_evaluable_count > 0` for at least the newly-acquired tickers.
5. Zero secrets appear in any written artifact or console output.
6. Normal Daily (no `--enable-current-foreign-flow-live`) for a different, later session still
   makes zero DNSE calls for this contract.

## 24. Authority status

`NONE` beyond `VALUE_ONLY_NON_ACTIONABLE`. No liquidity, sizing, execution, smart-money,
institutional-intent, or price-prediction authority is introduced or implied anywhere in this
milestone. `LIVE_OPERATIONAL` is explicitly not claimed until a real owner-authorized `--live`
run occurs and is validated against the criteria in §23.

## 25. Known limitations

- The VALUE adapter only supports a single, non-paginated raw page per ticker/session (reused
  from the pre-existing `current_foreign_flow_retention.py`, not changed here). A genuinely
  multi-page foreign-trading response for one session — not observed in the 2026-08-10 bounded
  pilots — fails closed rather than being silently truncated to page 0.
- `current_foreign_flow_positioning_bridge.py` is built and tested but not wired into live
  Daily; wiring it (or choosing not to) is a distinct future owner decision given the existing
  `collect_market_evidence.py`-fed producer of the same contract.
- `market_data_source_authority.DNSE_FOREIGN_FLOW_VALUE_AUTHORITY` still reads
  `"PRODUCTION_ENABLED_HPG_VNM_QNS"`, a decision-record narrative string from an earlier,
  narrower 2026-08-10 pilot. Nothing in this module or the retained store enforces it as a
  cohort gate (verified: no import of `market_data_source_authority` exists in
  `current_foreign_flow_retention.py`, `dnse_foreign_flow_store.py`, or this milestone's new
  files), so the broader 11-ticker owner-focus cohort is not blocked by it — but the string
  itself was not updated, since correcting a past decision record's language is outside this
  milestone's scope.
- No real DNSE round trip has ever been made against this specific 11-ticker cohort; §23 defines
  what the next live session must prove before `LIVE_OPERATIONAL` can be claimed.
