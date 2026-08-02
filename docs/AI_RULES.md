# Codex working rules

1. Codex is the implementation executor.
2. Read [STATE.md](STATE.md), [ROADMAP.md](ROADMAP.md), and [DECISIONS.md](DECISIONS.md) before proposing work.
3. One session is one substantial bounded milestone; avoid chains of tiny audit/design/shadow prompts.
4. A normal milestone inspects, patches, runs focused tests, performs one real/frozen validation when needed, commits, and pushes.
5. Do not reopen a passed gate without regression evidence.
6. Never treat metadata, ordering, missing data, or fallback behavior as investment signals.
7. Price basis, volume basis, and current shares are persistent blockers until explicitly qualified.
8. Do not enable valuation, ranking, recommendations, sizing, or backtesting from unqualified inputs.
9. Write detailed diagnostics locally; keep final chat output compact.
10. Do not run full suites unless a real cross-cutting source regression justifies it.
11. Do not publish or deploy unless explicitly requested.
