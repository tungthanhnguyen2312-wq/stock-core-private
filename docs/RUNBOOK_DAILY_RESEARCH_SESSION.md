# Daily Research Session Operation

Use this runbook after a completed market session has been retained by the upstream
current-research contracts. The normal foreground command is the Daily Producer;
it resolves one explicit completed-session ledger entry, reuses exact accepted
artifacts, materializes the Daily Session Operation, and leaves the AI and
Dashboard delivery files together. It never schedules itself, infers completion
from the wall clock, or promotes a source authority.

## After market close: one normal command

1. Confirm that upstream approved acquisition/materialization has retained the
   completed session and that its exact artifacts have been entered in
   `config/daily_research_session_input_registry.json`. The `completed_sessions`
   ledger is the completion proof; a weekday, local time, or a "latest" filename
   is never proof.
2. Run one foreground command from `stock-core-private`:

   ```powershell
   python tools/run_daily_producer.py --session YYYY-MM-DD
   ```

   To select only the greatest explicitly governed completed session, use:

   ```powershell
   python tools/run_daily_producer.py --latest-completed-session
   ```

   This mode reads the ledger only. It does not guess holidays, close status, or
   provider sessions from the wall clock.
3. Read the concise terminal summary (`SESSION`, `STATUS`, `OPERATION_ID`,
   `MARKET_COVERAGE`, warnings, primary AI bundle, Dashboard projection, and
   blocked dimensions). `REFUSE_COMPLETED_SESSION_RUN` is a safe refusal; correct
   the governed completion/registry evidence rather than forcing a partial run.
4. Open the printed owner directory under
   `operations-review/daily-producer-runs-v1/<SESSION>/<run-hash>/`.
5. Upload `ai_research_session_bundle.json` to ChatGPT or Claude for normal
   human-review research.
6. A Dashboard projection is ready in `dashboard/current_decision_cockpit_projection.json`.
   Publish it only later through the separately governed, owner-authorized
   Dashboard release command.
7. Evaluate outcomes only when a genuinely later retained session exists through
   the separate prospective-learning contract.

`LATEST_COMPLETED_RUN.json` beside the session directories is navigation only.
It carries exact session, producer-run, and Daily Session Operation identities;
it is never analytical truth.

## Acquire versus reuse and failure handling

The Daily Producer is an orchestrator. It retains the source plan in its final
`run_manifest.json` and uses only these dispositions: `ACQUIRE_FOR_TARGET_SESSION`,
`REUSE_CURRENT_VALID_RETAINED`, `REUSE_HISTORICAL_CONTEXT`,
`OPTIONAL_UNAVAILABLE`, `BLOCKED`, and `NOT_APPLICABLE`.

- Session-dependent DNSE/current-market, screening, tactical, and triage inputs
  must be exact-session and identity-bound; their failure blocks dependent
  tactical/product delivery.
- Fundamental and catalyst context are reused with their retained undated or
  earlier/degraded labels. Corporate Intelligence, macro, flow, and explicit
  portfolio branches are localized optional dependencies where their existing
  contracts permit that state.
- Strict valuation stays blocked; the shadow proxy is not substituted. Missing
  macro or flow does not manufacture zeros or block unrelated tactical research.
- Each actual upstream source acquisition retains its own raw provider/endpoint,
  request/session, retrieval time, response status, raw payload/content hash, and
  parsed disposition under its existing source contract. The Producer records
  identities only and never overwrites raw evidence.

## Rerun / resume

Run the same command again. With the same registry identities, repository heads,
and explicit optional inputs it targets the same immutable operation and owner
delivery directory. Existing byte-identical artifacts are reused; a conflicting
partial or changed artifact fails closed. Do not alter a historical snapshot to
make a rerun pass.

## 1. Prepare the explicit session selection

Identify the completed target session and create or review one governed entry in
`config/daily_research_session_input_registry.json`. Each entry binds a relative artifact path
to its exact `artifact_identity`. Do not point to a similarly named or “latest” artifact.

The selection must include the current descriptive/recovered technical artifact, screening,
tactical classifier, triage, fundamental context, valuation context, and catalyst context. The
runner requires the descriptive identity selected by screening and tactical to match exactly.

## 2. Run the operation once

From `stock-core-private`:

```powershell
python tools/run_daily_research_session_operation.py --session YYYY-MM-DD
```

For a separately governed registry, provide one path rather than individual artifact paths:

```powershell
python tools/run_daily_research_session_operation.py --session YYYY-MM-DD --input-registry path\to\registry.json
```

The command prints the deterministic operation identity and output directory. Re-running with
the same retained identities, repository heads, and generation context reuses byte-identical
immutable outputs. A changed pre-existing output fails closed.

## 3. Inspect the result

Open the session output directory under
`operations-review/daily-research-session-operations-v1/YYYY-MM-DD/<operation-hash>/`:

- `run_manifest.json` — exact identities, source sessions, freshness/degraded states, coverage,
  repository heads, warnings, Consumer E2E, and output identities;
- `current_daily_decision_research_product_artifact.json` and
  `current_daily_decision_research_brief.md` — the human-review surface;
- `peer_relative_research_artifact.json` and `scenario_artifact.json` — rebuilt coherent
  current-session downstream inputs;
- `prospective_snapshot.json` — immutable current-decision prospective baseline.
- `ai_research_session_bundle.json` — the normal single-file ChatGPT/Claude upload;
  it is a compact, authority-labelled projection of the same operation, not a new analysis.
- `ai_research_full_universe.ndjson` — optional compact 1,683-ticker companion for
  out-of-cohort work; no raw provider payloads are included.
- `ai_research_bundle_manifest.json` — exact session/operation, SHA-256 values,
  source identities, file sizes, and authority warnings.
- `current_decision_cockpit_projection.json` — the deterministic Dashboard payload
  for the same operation.

Investigate a fail-closed lineage/session error by correcting the governed registry entry or
upstream retained artifact. Never substitute an older same-date artifact merely to make a run
pass.

## 4. Prospective learning and later outcomes

The operation seals the existing current-decision prospective contract with
`future_outcomes=PENDING_FUTURE_OBSERVATION`. It does not create outcomes, calibration, or a
backtest. Only after a genuinely later exact retained market session exists may the separate
prospective-attribution contract evaluate that frozen session.

## Boundaries

The product is human-review research only. Entry actions remain deterministic tactical states;
probability remains `UNKNOWN_UNCALIBRATED`; strict valuation, rankings, targets, sizing,
portfolio, execution, PIT, and backtesting remain unavailable.

## Daily human workflow

1. Open the released Decision Cockpit and review the retained market session, discovery,
   watchlist, ticker cards, limitations, and lineage.
2. For normal AI-assisted research, upload only `ai_research_session_bundle.json`.
3. For an arbitrary ticker outside the useful research set, upload the optional
   `ai_research_full_universe.ndjson`, or extract one compact row first:

   ```powershell
   python tools/extract_ai_ticker_context.py --bundle ai_research_full_universe.ndjson --ticker HPG --output hpg_ai_context.json
   ```

4. Treat any AI conclusion as human-review research. The bundle contains no target,
   calibrated probability, sizing, or execution authority.

## Daily producer workflow

One completed-session Producer run emits Product V2, the AI delivery files, and
the Dashboard projection together. It mechanically asserts AI/Dashboard parity
for session, Daily Session Operation, Product, and analytical input identities.
It has no scheduler, polling loop, background service, production database write,
or Dashboard publication behavior.
