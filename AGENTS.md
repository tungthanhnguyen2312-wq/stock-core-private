# Repository guardrails

Active architecture: read `docs/market_wide_ingest_first_architecture.md` with the listed
governance files. The former ticker-by-ticker qualification-first workflow is
`SUPERSEDED_AS_DEFAULT_WORKFLOW`; qualification is now feature/use-level while raw provenance is
retained.

Codex is the executor. Before work, read `docs/STATE.md`, `docs/ROADMAP.md`, `docs/DECISIONS.md`, and `docs/AI_RULES.md`; Producer owns P0 source qualification and canonical artifact authority. If this checkout is part of the full StockLookup workspace (siblings: `ai-core-private`, `dashboard-runtime`, `operations-review`, `archive`), also read `docs/WORKSPACE_GOVERNANCE.md` — it points to the workspace-level agent working contract and current project state, which take precedence over anything in this repo's own docs for cross-repo questions.

- Work only inside this repository unless the task explicitly names another workspace location.
- Use `STOCK_LOOKUP_RUNTIME_ROOT` for runtime data; do not infer or hard-code a runtime path.
- Keep repository documentation portable, with relative repository links only. Put machine-specific procedures in local operator documentation.
- Do not edit databases, generated artifacts, backups, credentials, or deploy outputs unless explicitly requested.
