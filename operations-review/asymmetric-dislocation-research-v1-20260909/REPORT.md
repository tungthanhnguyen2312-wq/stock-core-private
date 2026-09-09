# Asymmetric Dislocation Research V1

`ASYMMETRIC_DISLOCATION_RESEARCH_V1 = COMPLETE / RESEARCH_ONLY / READY_FOR_LATER_PRODUCT_INTEGRATION`

Owner override: `OWNER_AUTHORIZATION_2026_09_09_ASYMMETRIC_DISLOCATION_RESEARCH_V1`.

## Contract

New standalone, read-only artifact `asymmetric_dislocation_research/v1`
(`asymmetric_dislocation_research.py`). It computes **zero** new financial ratio,
technical indicator, or catalyst classification. Every evidence axis is a pure,
descriptive join over one already-governed `integrated_investment_decision_product/v1`
per-ticker record for a single retained session:

| New axis | Reused source (verbatim) |
| --- | --- |
| `economic_survivability_context` | `fundamental_state` / `financial_composite_context` (`financial_analysis_product_integration/v1`) |
| `valuation_dislocation_context` | `valuation_context_summary` (`current_research_valuation_context/v1`) |
| `market_dislocation_context` | `tactical_phase` / `market_structure_state` / `breakout_state_v3` / RSI zone (`market_structure_breakout_product_projection/v1`, `tactical_momentum_context/v1`) |
| `corporate_intelligence_context` | `corporate_intelligence_context` (`current_corporate_intelligence_axis/v1`) |
| `recovery_catalyst_context` | descriptive join of the three axes above (fundamental turnaround, improving structure, active catalyst); explicit `RECOVERY_EVIDENCE_ABSENT` when none apply |
| `risk_invalidation_context` | `invalidation` (`tactical_confirmation_invalidation_boundaries/v1`) + Corporate Intelligence risk read |
| `scenario_asymmetry_context` | `ASYMMETRY_NOT_QUANTIFIED` by default (calibration cohorts remain `INSUFFICIENT_SAMPLE`); passes through an already-retained `current_evidence_bound_scenario/v1` boundary verbatim, when supplied |
| `sector_model_applicability` | descriptive-only join to `entity_classification_contract.py`; no new family-specific formula is ever applied here -- the upstream fundamental/valuation engines are already family-aware |

### Classification and evidence rules

Seven deterministic primary states, one per ticker, with a strict priority order (see
`classify_dislocation()`): `QUALITY_DISLOCATION` (cheap + non-deteriorating
survivability + confirmed price weakness), `TURNAROUND_EVIDENCE_FORMING` (explicit
financial turnaround, self-sufficient), `CYCLICAL_RECOVERY_FORMING` (improving tactical
structure + non-deteriorating fundamentals + recovery corroboration),
`DISTRESS_SPECULATIVE` (confirmed price breakdown with weak/unknown survivability),
`VALUE_TRAP_RISK` (cheap valuation with deteriorating fundamentals -- cheapness never
rescues a deteriorating read), `NO_QUALIFIED_DISLOCATION`, and `INSUFFICIENT_EVIDENCE`
(fired only when a critical axis -- survivability or valuation -- is unusable *and*
there is no countervailing market/risk evidence at all; a single missing axis never by
itself forces this when other axes corroborate a state). Oversold RSI alone is
tracked (`oversold_only`) but never treated as reversal/basing evidence and never
qualifies a state by itself. A qualified corporate catalyst never upgrades a state on
its own (`CATALYST_PRESENT_BUT_NO_ECONOMIC_SUPPORT_EVIDENCED` is appended instead).

### Ordering semantics

`RANKING_ORDERING_SEMANTICS` in `asymmetric_dislocation_research.py`: lexicographic
`(primary_research_state tier, valuation_dislocation state, -len(reason_codes), ticker)`
among `ELIGIBLE_RESEARCH_CANDIDATE` records only
(`QUALITY_DISLOCATION` > `TURNAROUND_EVIDENCE_FORMING` > `CYCLICAL_RECOVERY_FORMING` >
`DISTRESS_SPECULATIVE`; `CHEAP` > `MID` > `UNAVAILABLE` > `EXPENSIVE`). No weighted
score, vote count, probability, or target price is computed anywhere.

## Real market-wide result

Session `2026-09-09` (latest governed `COMPLETED_RETAINED_EVIDENCE` session per
`config/daily_research_session_input_registry.json`), read-only against the retained
`integrated_investment_decision_product/v1` artifact
(`integrated_investment_decision_product/v1:21e8014c0afb1bbbcc04acfa8a98e926186e839868b7d34e235be870bd11e3c6`).
No provider/network acquisition; `tools/run_asymmetric_dislocation_research.py`.

- Denominator: **1,683**
- State distribution: `NO_QUALIFIED_DISLOCATION` 689, `INSUFFICIENT_EVIDENCE` 614,
  `CYCLICAL_RECOVERY_FORMING` 185, `VALUE_TRAP_RISK` 152, `DISTRESS_SPECULATIVE` 23,
  `QUALITY_DISLOCATION` 14, `TURNAROUND_EVIDENCE_FORMING` 6
- Evidence-qualified count: 1,471 (survivability known or valuation available)
- Missing-evidence tickers: 864 (`VALUATION_EVIDENCE_UNAVAILABLE` 756,
  `FUNDAMENTAL_EVIDENCE_UNAVAILABLE` 320 -- some tickers carry both)
- Candidate count (eligible research states only): **228**
- Reason-code distribution: see `market_wide_summary_20260909.json`

Full per-ticker artifact: `asymmetric_dislocation_research_20260909.json`.

## Boundaries confirmed

No modification to canonical Daily Producer orchestration, Daily Brief generation, AI
delivery, the Integrated Investment Decision production path, AI/public handoff, or
Portfolio V2 decision semantics -- this milestone added two new files and one test
file only; no existing module was edited. No Dashboard/AI publication. No
probability/target fabrication (unit-tested). No execution/liquidity/PIT authority
promotion. No calibration-threshold optimization. Not activated in canonical Daily.
