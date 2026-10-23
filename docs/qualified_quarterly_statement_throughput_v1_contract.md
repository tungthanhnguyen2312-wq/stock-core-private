# Qualified quarterly statement throughput V1

Owner-admitted milestone `QUALIFIED_QUARTERLY_STATEMENT_THROUGHPUT_V1` (2026-10-23, after the
October23 Daily). One Producer writer, based on main `e15c8f3a`. PR182/PR183 stay open and
untouched; Codex's uncommitted shareholder-economics worktree is not used.

## Missing link

`official_income_research_context` (PR181) admits current reviewed/audited income facts.
It looks for a prior year only inside that same exact-field stream, so an FY2025 audited fact
never meets the FY2024 audited fact that is already qualified by another existing owner.
`stocklookup_core/financial/official_income_prior_period_pairing.py` is that read link. It is
not an intake, overlay, fact store or feature store.

- **Current side.** Only facts already admitted by `official_income_research_context`.
- **Prior side.** Only rows already qualified by existing owners:
  - governed official-evidence identity citations, joined to their document manifest;
  - P3-E promoted closeout citations, with the printed source fragment from the same manifest.

  Each row is re-checked for: an approved audited or reviewed statement document class;
  document SHA; consolidated or standalone scope; integer value with unit scale 1;
  explicit annual period; knowledge time at the cutoff; and the semantic-correction overlay.
  The printed label alone must prove the row identity through the existing
  `resolve_reported_row_identity` phrase set. Missing labels, OCR-damaged labels and parent
  labels stay blocked.
- **Pair rule.** The two sides must match on: accounting identity (line 10/60/61 concept);
  scope; currency; unit; period type; assurance; and identical prior-year bounds. They must
  come from different documents. Annual labels bind calendar bounds only as far as PR181
  already tolerates (`FISCAL_CALENDAR_NOT_PROVEN_BY_LABEL`).
- **Conflicts.** Conflicting qualified prior values refuse the pair. No winner is chosen.

## Comparative columns are evidence, not facts

`tools/run_comparative_column_observations.py` re-reads, offline and bounded, only the
retained pages behind admitted overlay income facts. It uses the existing OCR geometry engine.

- **Same-row binding.** A row is accepted only when its current-column value equals the
  admitted value.
- **What it records.** The same row's comparative token, the period labels, bounding boxes,
  materialization identity, `assurance_basis`, and `knowledge_available_at` (at least the
  re-read instant).
- **Never fixed.** Amounts are never repaired. Ambiguous tokens are `OCR_NUMERIC_AMBIGUITY`.
- **Year binding.** `Kỳ này/Kỳ trước` labels do not bind a year
  (`COMPARATIVE_PERIOD_LABEL_NOT_YEAR_BOUND`).
- **Shared token.** One comparative token shared across distinct rows at one box is
  `COMPARATIVE_TOKEN_SHARED_ACROSS_ROWS`.

Observations are `CANDIDATE_OWNER_GATE` with existing-consumer, official-fact and overlay use
false. Their only default effect is a restatement cross-check:

| Check result | Effect on the pair |
|---|---|
| `COMPARATIVE_COLUMN_MATCHES_ORIGINAL` | Corroborates. The pair is kept. |
| `COMPARATIVE_CROSS_CHECK_OCR_AMBIGUOUS` | Limitation. The pair is kept. |
| `COMPARATIVE_CROSS_CHECK_NOT_AVAILABLE` | No evidence. The pair is kept. |
| `PRIOR_PERIOD_DIFFERS_IN_LATER_REPORT` | The pair is refused. |

Reconciliation never proves identity, and a later column never replaces an original.

## Owner gates (disabled by default)

- `OWNER_GATE_COMPARATIVE_COLUMN_AS_PRIOR_PERIOD_FACT` treats an unblocked comparative
  observation as a prior-period value when no independently qualified original exists.
- `OWNER_GATE_D1_UNREVIEWED_QUARTERLY_DIRECTION_PREVIEW` pairs D-1 current and prior-year
  quarter rows from one unreviewed report.

When enabled, both feed only `owner_gated_preview`. They are never fed to `comparisons`,
votes, cards, valuation or TTM. No caller enables them.

## Consumer boundary

`project_session(prior_period_inputs=None)` is byte-identical to main. When a caller
supplies `load_prior_period_inputs(...)`, the projection gains two things:

- a source lineage hash;
- an additive `official_income_research_context.prior_period_pairing`.

Existing product summaries and cards copy that context verbatim. The pairing returns:

- `direction_status`, plus `earnings_direction_research` and `revenue_direction_research`;
- `ttm_inputs` (four consecutive qualified standalone quarters are required; synthetic Q4
  and YTD subtraction are not permitted);
- `vote_effect`, `strict_valuation_effect` and `ttm_effect`, all `NONE`.

Trajectory context, IID votes, posture, triage, valuation and completed sessions are unchanged.
A missing host evidence root becomes a load blocker, never a failure.

The Daily caller (`daily_session_level2_package.py`) is an E2/E3 frozen source, so V1 does
not wire it. Daily activation needs the governed frozen-source transition. It is a separate
Owner-gated step, and its transition fixture is also edited by open PR183.

## Not authorized

- Merge, Daily, production DB/runtime/dashboard writes, or sealed-session rewrites.
- Source or route approval, or a D-1 amendment.
- KBS relabel, DNSE replacement, OCR amount repair, FX, annualization, TTM or valuation inputs.
- Any authority promotion. Authority effect NONE.
