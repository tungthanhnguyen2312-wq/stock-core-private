# Decision intelligence coverage and calibration closure

Milestone `DECISION_INTELLIGENCE_COVERAGE_AND_CALIBRATION_CLOSURE_V1`.

Authority effect: `NONE / DECISION_INTELLIGENCE_RESEARCH_COVERAGE_AND_CALIBRATION_ONLY`.

This closure joins the existing coverage, historical-panel, calibration, evidence-packet,
and portfolio-workbench contracts. It does not add a decision engine, a buy score, a
probability, a target price, or a weight. The optional local CLI is `DEFERRED`.

## Current coverage

Denominator is the 1,683-name universe status artifact for session 2026-10-06.
The valuation artifact's own 1,507-record denominator is not reused as the summary
denominator. Names absent from valuation, CI, or the event list stay `UNKNOWN`
unless that artifact records an explicit disposition.

Read-only join, not persisted:

| Count | Value |
|---|---:|
| financial current (official-qualified) | 13 |
| financial historical | 0 |
| provider-research financial | 507 |
| valuation research-usable | 855 |
| valuation strict-ready | 0 |
| denominator conflict | 2 |
| share-basis blocked | 1,507 |
| CI current | 0 |
| CI historical | 3 |
| event current | 35 |
| event historical | 137 |
| specialist-sector | 69 |
| completely missing | 741 |
| price current | 857 |
| technical stale | 596 |

Compact index size: 2,496,756 bytes. It stores statuses and source identities, not financial or CI bodies.

Share-basis blocked equals the valuation artifact's 1,507 records. Each of those records carries a retained share blocker, including qualified-official rows whose coverage is not proven through the price session. The 176 names outside that artifact stay unknown, not blocked.

## Historical panel

The existing panel identity is unchanged. Enrichment is an overlay.

- sessions opened: 28
- rows: 2,445
- rows with a feedback overlay: 1,764
- rows without an overlay: 681
- parent tiers are not upgraded
- outcome values sit in `outcome_namespace` and are not written back into the decision-time outcome field
- in-memory enriched row projection: 10,072,301 bytes
- field tiers in the overlay: `PROSPECTIVE_GENUINE` 14,112, `RECONSTRUCTED_RESEARCH` 8,016, `EXPLANATORY_ONLY` 6,654, `UNKNOWN` 60,723

OHLCV, valuation multiples, and corporate-event dates are still absent where no bounded projection carried them. Those fields stay missing. They are not reconstructed from a later session.

## T0 warnings and supportive features

The prior review reported warnings and supportive features absent on 255/255 cohorts because `compact_horizons` read only `t0_warnings` and boolean axis flags.

Retained feedback already has:

- `evidence_axes.status` of `FIELD_NOT_RETAINED_AT_T0` on the 2026-09-03 legacy slice
- `evidence_axes.status` of `RETAINED` from session 2026-09-08, with nested axis `state` values
- trigger and invalidation strings that are authority disclaimers, not setup warnings

The projection now keeps adverse and supportive axis families and ignores the two authority disclaimers as setup warnings. It does not invent codes. Old T0 files are not rewritten.

Recount of the same 31,977-row artifact:

- feedback rows with a setup-warning list: 30,294
- feedback rows with a supportive-feature flag: 30,294
- cohorts with setup warnings: 184 / 255
- cohorts with supportive features: 188 / 255
- earliest retained feature session: `2026-09-08`
- cohorts still `FEATURES_NOT_RETAINED`: 1

## Calibration

Mature rows are unchanged from the prior streamed recount: T1 11,912, T3 10,277, T5 9,590, T10 5,823, T20 16.

MFE and MAE are present on 46 cohorts.

False-positive and false-negative labels use the retained failure labels or the sign of the retained forward return. That sign was already the review's descriptive negative count. No new policy threshold was introduced.

- false-positive explainable rows: 9,055
- false-positive rows whose features were not retained: 15
- false-negative explainable rows: 6,688

## Matched control

Qualified edges: 0. The closure gate does not publish the older descriptive edge.

| Readiness | Cohorts |
|---|---:|
| INSUFFICIENT_CONTROL_POOL | 181 |
| OUTCOME_NOT_MATURE | 50 |
| SETUP_NOT_ELIGIBLE | 15 |
| UNQUALIFIED_SAMPLE | 7 |
| FEATURES_NOT_RETAINED | 1 |
| PRICE_BASIS_INCOMPATIBLE | 1 |
| CONTROL_READY | 0 |

## Focus names

These are generic readings of the 2026-10-06 join. Expected business facts that are not in the retained artifacts stay missing.

- HPG: official-current fundamental evidence and current exact-session price are both present. Share basis is blocked. Historical corporate action is retained. Earnings quality is `UNKNOWN`. The expected incomplete-price-confirmation fact is not what this session's coverage row says.
- PAN: official-current financial evidence and a research-usable valuation proxy are present. Earnings quality is `UNKNOWN`, so a non-recurring warning is not available to separate from the multiple.
- PNJ: no retained historical-panel cohort. Earnings quality is `UNKNOWN`. Current price is exact-session. Share basis is stale.
- POW: current fundamental evidence is separate from any base/recovery label. The coverage row does not itself carry a base/recovery state.
- SSI and EVF: specialist-sector valuation semantics are set. SSI valuation status is `BLOCKED` with `SECTOR_ENTITY_METHOD_NOT_SUPPORTED`.
- FPT: share-basis blocker is retained. A current corporate-action event is `UNKNOWN`.
- NVL: denominator conflict is true (`POSITIVE_DENOMINATOR_REQUIRED`) and share basis is stale. No retained cohort row.
- QNS: retained tactical states include `UPTREND`, `BREAKOUT_READY`, `DOWNTREND`, and `EARLY_BEARISH_REVERSAL`. `UPTREND` is not relabeled.

## Storage

Peak traced Python allocations during the read-only build: 208,789,331 bytes. Elapsed time: 31.0 seconds. The coverage index and enriched panel stay in memory and are not written back to retained evidence. Full T0 bodies and velocity bodies were not opened.

## CLI

`DEFERRED`. The milestone deadline leaves the thin read-only commands unbuilt. No background service was added.
