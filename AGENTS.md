# Repository guardrails

Codex is the executor. Before work, read `docs/STATE.md`, `docs/ROADMAP.md`, `docs/DECISIONS.md`, and `docs/AI_RULES.md`; Producer owns P0 source qualification and canonical artifact authority.

- Work only inside this repository unless the task explicitly names another workspace location.
- Use `STOCK_LOOKUP_RUNTIME_ROOT` for runtime data; do not infer or hard-code a runtime path.
- Keep repository documentation portable, with relative repository links only. Put machine-specific procedures in local operator documentation.
- Do not edit databases, generated artifacts, backups, credentials, or deploy outputs unless explicitly requested.
