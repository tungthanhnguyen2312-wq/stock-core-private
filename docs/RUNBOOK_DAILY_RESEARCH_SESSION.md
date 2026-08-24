# Daily Research Session Operation

Use this runbook only after a completed market session has been retained by the upstream
current-research contracts. This is a foreground, retained-evidence operation; it neither
acquires market data nor schedules itself.

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

One completed-session operation emits Product V2, the AI delivery files, and the Dashboard
projection together. A governed Dashboard publication remains a separate owner-authorized
release step; do not select a `latest` operation or manually combine artifacts.
