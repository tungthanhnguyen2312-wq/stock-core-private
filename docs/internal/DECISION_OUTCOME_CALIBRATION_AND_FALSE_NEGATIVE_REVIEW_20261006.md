# Decision outcome calibration and false-negative review

Milestone `DECISION_OUTCOME_CALIBRATION_AND_FALSE_NEGATIVE_REVIEW_V1`.

Authority effect: none. This review is descriptive. It does not emit a probability,
a target price, or a replacement production threshold. `automatic_threshold_change`
is false.

Contract: `decision_outcome_calibration_review/v1`.

## Populations

Rows are classified into one of:

- `PROSPECTIVE_GENUINE` for `IMMUTABLE_INTEGRATED_T0` and `QUALIFIED_LEGACY_INTEGRATED_T0`
- `PIT_AUTHORITATIVE`
- `RECONSTRUCTED_RESEARCH`
- `EXPLANATORY_ONLY`

A row that claims both a prospective source type and a conflicting semantic tier is
unclassified and excluded. Cohorts also keep `source_type`, so legacy and immutable
prospective rows are not pooled. Horizon 60 is refused and is not an engine horizon.
Implemented horizons are 1, 3, 5, 10 and 20.

Sample labels are `INSUFFICIENT`, `EARLY_DESCRIPTIVE`, `RESEARCH_USABLE`, and
`CALIBRATION_CANDIDATE`. A large sample does not become authority. Matched-control
edge is the setup median minus the control median only when both sides are at least
`RESEARCH_USABLE` and share one regime. Otherwise the status is `UNQUALIFIED_SAMPLE`.

False-positive review counts retained T0 warnings on negative mature outcomes.
False-negative review counts retained supportive features while posture is `WAIT`,
`AVOID`, or `INSUFFICIENT_CURRENT_RESEARCH`. Missing warnings, features, drawdown,
false-reversal labels, and failed-breakout labels stay explicit.

## Recount of the retained 2026-10-06 feedback artifact

Source file, streamed one record at a time and not retained in memory:

`operations-review/prospective-decision-outcome-feedback-v1/2026-10-06/prospective_decision_feedback_artifact.json`

Measured 2026-10-07:

- records: 31,977
- shape: 19 decision sessions × 1,683 rows
- sources: `QUALIFIED_LEGACY_INTEGRATED_T0` 5,049; `IMMUTABLE_INTEGRATED_T0` 26,928
- populations in this file: `PROSPECTIVE_GENUINE` only
- unclassified rows: 0
- T60 fields: 0
- review cohorts: 255
- sample quality: `CALIBRATION_CANDIDATE` 19, `RESEARCH_USABLE` 41, `EARLY_DESCRIPTIVE` 19, `INSUFFICIENT` 176
- matched control: `UNQUALIFIED_SAMPLE` 240, `NOT_A_SETUP_COHORT` 15, computed edges 0
- cohorts with close-path MFE and MAE present: 46
- T0 warnings retained: 0 cohorts
- supportive-feature flags retained: 0 cohorts
- review identity: `decision_outcome_calibration_review:8bce077c9e430caa3ef2141460c9b2be3723dda486094297fee80fe110768b41`

`status == MATURE` on the named forward-close horizon:

| Horizon | Mature rows | Decision sessions |
|---|---:|---|
| T1 | 11,912 | 18 sessions, 2026-09-08 through 2026-10-02, excluding 2026-09-03 |
| T3 | 10,277 | 15 sessions |
| T5 | 9,590 | 14 sessions: 2026-09-03, 08, 09, 10, 11, 15, 16, 17, 18, 21, 22, 23, 24, 28 |
| T10 | 5,823 | 9 sessions: 2026-09-03, 08, 09, 10, 11, 15, 16, 17, 18 |
| T20 | 16 | 2026-09-03 only |

The earlier reference, recorded at cutoff 2026-10-06, was T5 10,338 / 15 sessions,
T10 6,544 / 10 sessions, and T20 16 / 1 session. T20 matches. T5 is 748 rows lower
and does not include 2026-09-29. T10 is 721 rows lower and does not include
2026-09-21. This artifact does contain 1,683 rows for each of those sessions; their
horizon status is not `MATURE`. T5 also has 751 `PRICE_BASIS_INCOMPATIBLE` rows and
T10 has 752. Those rows stay excluded. The gap is not closed by reclassification.

October 5 and October 6 do not appear as decision sessions in this 31,977-row
artifact, so this recount's pending-live count is 0. That absence is not maturity.
The separate post-close handoff already records the new chain as not mature at
T5, T10, and T20. This review does not invent those outcomes.

The result is not persisted. Storage is the cohort summary produced by the stream.
