# Official prior-period pairing Daily transition V1

Owner authorization 2026-10-24: `OFFICIAL_PRIOR_PERIOD_PAIRING_DAILY_FROZEN_SOURCE_TRANSITION_V1`.
Base main `829500e7c132e4289147e5fa61764da47f3dce67`; PR182/183/184 merged.
One isolated Producer writer. Implement Daily integration and historical research presentation
in one scope; local checkpoint and PR-ready handoff only. No push, merge, production Daily,
DB/runtime/publication writes, source/fact promotion or successor. The separate shareholder
milestone and worktree are not part of this change.

## Existing owners and exact transition

Reuse [qualified pairing](qualified_quarterly_statement_throughput_v1_contract.md),
[income research](official_income_statement_research_consumption_v1_contract.md),
[earnings/cash presentation](reviewed_interim_earnings_and_cash_research_v1_contract.md) and
[E2/E3 frozen source](e2_e3_foundation_seams_and_dependency_untangling_contract.md) contracts.
`daily_session_level2_package.materialize_independent_components` is the single caller:
only the existing uncompleted-session projection branch loads prior inputs. Completed locks
and occupied session projections are not regenerated. `load_prior_period_inputs` remains
the loader; `project_session` and `official_income_prior_period_context` remain the producers.
No parallel intake, evaluator or card owner is introduced.

Only this frozen Daily caller is admitted to the existing financial research source-transition
manifest. Its exact main bytes are archived and reproduce the unchanged E2/E3 pin. Existing
historical E4 V1/V2 digests are reproducible only through the historical verifier; active
execution always hashes the live source and cannot adopt old receipts. Launcher arguments,
retention paths, stream owners and production entrypoints are unchanged. The dependent
Thesis active E4-V2 pin is rebound to the exact combined live digest; its historical pin,
source archive and admission scope stay unchanged. The financial transition records the
prior declared digest, the independently recomputed main digest and the new live digest;
neither prior receipt is eligible for reuse. No verifier check or allowlist is relaxed.

## Qualification and no-input compatibility

Current and original prior facts must satisfy their existing source-owner gates, exact line
10/60/61 identity, fiscal/duration bounds, scope, assurance, currency, unit, independent
document, known-at cutoff, semantic correction, conflict and restatement checks. No FX,
quarter aggregation, OCR repair, year inference from relative labels or authority promotion.
Comparative columns are corroboration only, with their own observation clock. Comparative
and D-1 gates stay OFF; previews never reach a card, vote, trajectory, posture, recommendation,
valuation, sizing or TTM. Historical audited growth is not current earnings momentum.

A bundle without any qualified prior row known at the session cutoff is omitted at the Daily
projection call, preserving the existing no-input projection identity/behavior. Known qualified
prior inputs enable pairing and explicit claim-local UNKNOWN results. Missing host evidence is
a blocker, not a Daily failure. The loader reads explicit governed paths only.

## Presentation and acceptance

The existing `financial_research_card` carries the source pairing inside its existing
`fundamental_research_context.official_income` envelope only when the current facts and exact
cutoff still match. It never relabels a later pairing as earlier knowledge. Each pair retains
metric/accounting identity, both periods/values, change/ratio, scope, assurance, source hashes,
citations, locators, known-at clocks and comparative cross-check. UNKNOWN retains reason codes.
Existing primary, owner-focus, subset and cockpit projections carry this context.

At a new valid cutoff after 2026-10-23 19:13 ICT: HPG audited consolidated FY2025/FY2024 revenue
+12.43%, total PAT line60 +29.08%; revenue comparative match only when known, PAT OCR ambiguity
retained. Line61 is not substituted. FPT/PNJ/VRE lack independent compatible originals; PVD
keeps its currency mismatch; POW/QNS/PAN lack current qualified facts. No ticker-specific rule.
`vote_effect`, `strict_valuation_effect`, `ttm_effect` remain NONE; TTM remains unavailable
without four consecutive qualified standalone quarters. October20/22/23 sealed bytes stay
unchanged; pre-existing replay differences are reported separately from new regressions.

Validate positive/negative loader-to-caller-to-projection-to-card paths, source conservation,
E2/E3/E4 identities, knowledge time, policy parity, layout/launchers/CI and native roadmap.
Compact control-plane docs must stay within their 102400-byte aggregate budget.
