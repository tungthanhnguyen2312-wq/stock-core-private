# Long-term company economics evidence

`long_term_company_economics_evidence/v1` · milestone
`LONG_TERM_COMPANY_ECONOMICS_EVIDENCE_MATRIX_V1` · authority effect **NONE**.
One offline, opt-in module, `long_term_company_economics_evidence.py`, and one main
suite, `tests/test_long_term_company_economics_evidence.py`. No Daily registration,
new financial engine, thesis reducer, portfolio engine, persistence or publication.

## Inputs and standing qualification

`build(ticker=..., knowledge_cutoff=..., official_rows=..., context_items=(),
valuation_context=None)` requires a timezone-bearing cutoff on every invocation.
Use the retained compact overlay
`derived/financial-evidence-currency-refresh-v1/qualified_official_facts.jsonl`.
This interface consumes already-qualified source-bound rows; it cannot qualify raw
PDF/OCR cells, independently authenticate source bytes or replace upstream extraction.
It reuses `market_wide_current_fundamental_research.project_session` with an empty
in-memory baseline. No baseline provider/annual ratios are imported or recalculated.
The existing frozen-cohort, semantic, assurance, period, currency/unit, component,
annual-context, canonical factual-authority and conflict gates all remain binding.
Row codes are never interpreted here as asset/debt identities. Superscript repair
is not performed. Exact line labels are owned by the upstream extraction contract.

Controlling upstream contracts: [official canonical qualification](financial_statement_canonical_contract.md),
[annual context](audited_annual_exact_field_context_contract.md),
[USD interim context](currency_preserving_interim_context_contract.md),
[reported earnings components](reported_earnings_component_context_contract.md),
[existing thesis items/lenses](thesis_evidence_matrix_stage_1_contract.md) and
[Portfolio Opportunity Cost](portfolio_opportunity_cost_research_contract.md).

Observation knowledge and retrieval must both be explicit and no later than cutoff.
Known publication is checked too; unknown publication stays null. Date-only publication
does not replace a retrieval/knowledge receipt. Post-cutoff rows are excluded **before**
conflict detection; a later revision cannot poison an earlier observation. A known
conflict blocks the exact fact. Duplicate rows and input order cannot alter output.
Source SHA, exact citation, page/line, knowledge/retrieval/publication times, period,
scope, assurance and all standing research/valuation restrictions survive projection.
Excluded rows retain references and reasons. No completed session is read or rewritten.

Optional `context_items` are envelopes containing `item` (verified `evidence_item/v1`),
`knowledge_available_at` and `observed_at` from the retained source receipt. Subject
ticker/session must match. Verification authenticates the item's content binding;
the caller remains responsible for supplying the actual retained receipt times.
Economics owns an independent, closed consumer input contract for these serialized
references. It checks canonical SHA-256 identity, schema/vocabulary, source pointers,
fitness, forbidden judgment keys, typed fact provenance and T0 seal/basis restrictions
without importing offline Stage 1. It constructs no thesis items or snapshots and
contains no adapter, reducer or lens engine. Stage 1 and its import guard are unchanged.
Provider Financial V2 (`financial_analysis_context/v2`), existing thesis references,
tactical states and sector context stay labelled
`RESEARCH_CONTEXT_ONLY_NOT_QUALIFIED_COMPANY_ECONOMICS`, even when upstream direction
fitness is true. No item state votes in this matrix. A single provider profit state,
sector leadership or tactical breakdown cannot support/challenge a structural thesis.

## Observed versus interpreted

Every dimension has separate `observation_status` and `interpretation_status`, each
using `KNOWN / PARTIALLY_KNOWN / UNKNOWN / NOT_APPLICABLE`. An additional
`current_observation_status` keeps historical coverage from filling a current gap.
Individual admitted observations are `KNOWN` for their exact field/period/scope/currency.
A dimension with any observations is `PARTIALLY_KNOWN`; current revenue plus total
profit in one identical period/scope/currency group establishes `KNOWN` **bounded
income observation**, without establishing long-run profitability. Historical-only
dimensions retain current `UNKNOWN`. Missing observations stay `UNKNOWN`.
`NOT_APPLICABLE` is reserved for a future source-qualified dimension applicability
contract; V1 never guesses it from issuer name, sector or absent evidence.

| Dimension | Official observation routing | Interpretation boundary |
|---|---|---|
| Business durability | No existing qualified multi-year observation | UNKNOWN |
| Revenue/profit economics | Revenue, total and parent-attributable profit | No multi-year/recurrence inference |
| Balance-sheet resilience | Assets, equity, cash, exact qualified short/long interest-bearing debt | No resilience from historical equity or missing debt |
| Cash generation/reinvestment | Operating cash flow | No reinvestment quality or current cash-flow inference |
| Earnings quality | Reported disposal/provision component | Recurrence/accounting bridge UNKNOWN |
| Cyclicality | No issuer-specific cycle proof in current contracts | No recovery from ticker/sector/provider profit |
| Management/capital allocation | No source-bound management/reinvestment record | No management-quality inference |
| Valuation fitness | Optional qualified existing relative research methods | Scoped research only; strict gates stay closed |
| Structural thesis invalidation | No source-owned structural invalidation proof supplied | No tactical-to-Core invalidation |

Financial observations alone leave structural interpretation `UNKNOWN`; partial facts
do not prove a 5–20 year thesis. No universal verdict or research action posture exists.

## Independent named flags

All six flags are separate objects with a status and reason. `KNOWN` means the named
condition is established within this object's boundary; `UNKNOWN` means unevaluated,
not false or opposing evidence. V1 establishes `INSUFFICIENT_STRUCTURAL_EVIDENCE`,
`EARNINGS_QUALITY_UNCERTAIN` and `VALUATION_UNQUALIFIED` independently.
`STRUCTURAL_THESIS_SUPPORTED`, `STRUCTURAL_THESIS_CHALLENGED` and
`CYCLICAL_RECOVERY_POSSIBLE` are deliberately `UNKNOWN`: none of the reused contracts
qualifies a multi-year company thesis or issuer cycle. This milestone does not invent
a directional reducer merely to activate those flags. Their names are supported in the
output; later activation requires a qualified source/method contract and separate scope.
Absence of a component never proves clean earnings. An uncertainty flag is not a
negative company-quality verdict.

Optional `valuation_context` is a timed envelope with `payload` equal to the existing
Portfolio Opportunity Cost strategic input. It reuses that module's `_strategic`
predicate: a declared relative label must agree with an actual qualified relative
method (`READY_RESEARCH_ONLY`) and percentile direction. Method name, unsupported
expensive label and market-cap size alone fail. This is the actual boundary used for
valuation-trim research; no trim case or action is produced here. Qualified relative
research yields observed `KNOWN`, interpreted `PARTIALLY_KNOWN` valuation fitness.
`VALUATION_UNQUALIFIED` still means **strict** valuation; current share continuity,
official denominator and other strict gates are not supplied/promoted by this object.

## Normalization

Always emit `NORMALIZED_ECONOMICS_NOT_QUALIFIED`. Exact component, period and scope
may be observed; that does not prove adjustment sign/direction, recurrence treatment,
reconciled accounting presentation or the appropriate denominator. These blockers
remain separately named. Preserve the reported signed amount and source component
direction, when present, as descriptive observations. A cash-flow reconciliation
provision is not automatically an income-statement expense available for add-back.
No impairments/provisions are added back. No normalized EPS, H1 annualization,
synthetic TTM, period joining, currency conversion, ratio, target, probability, score,
allocation, sizing, leverage, BUY/SELL/ADD/HOLD/TRIM/ROTATE or execution action.

## Retained issuer acceptance

Cutoffs: before `2026-10-07T15:00:00+07:00`, later `2026-10-08T15:00:00+07:00`.
Fixtures read the existing compact tracked overlay, not a retained-evidence rescan.
Production code contains no issuer values, identities, dates or fixture branches.

| Issuer | Later observations | Remaining evidence limits |
|---|---|---|
| PNJ | 3 reviewed 2026-H1 income facts; H1 provision 2,667,248,523,366 VND; historical FY2025 cash and OCF | Current balance/debt/OCF UNKNOWN; H1 remains interim; recurrence UNKNOWN |
| PVD | 3 reviewed 2026-H1 USD income facts; 4 audited FY2025 VND income/assets/equity facts | Separate periods/currencies; no conversion, joining, current balance/flow or cycle inference |
| FPT | Audited FY2025 revenue 70,112,825,100,710 VND and equity 43,748,040,747,539 VND; provision 651,406,282,654 VND | Parent earnings blocked on image-only glyphs; current official H1 income and strict share continuity absent |

Before-cutoff admitted counts PNJ/PVD/FPT = **3/3/0**; later counts = **6/7/3**.
All three retain uncertain quality, unqualified strict valuation, and insufficient
structural evidence. Durability, cyclicality, management and structural invalidation
stay UNKNOWN. FPT's current quality remains UNKNOWN despite its historical provision.
The FPT representation/parent glyph and share blockers are retained in the
[October 8 campaign](internal/STOCK_LOOKUP_AUTONOMOUS_CAMPAIGN_20261008.md).

Exact document identities and qualification knowledge times (UTC):

| Source | SHA-256 | Retained knowledge |
|---|---|---|
| PNJ H1 | `db877169e7c19b4b81d60b37d5aab8f9938129a66b582c2229ffffebdca2a43d` | Income `2026-09-29T11:31:14.408633Z`; provision `2026-10-08T01:03:28.804230+00:00` |
| PNJ annual | `309f86836d9f00b37e3cccb25da9e7ffd0dab6c531be995618542004acccdf1d` | Cash `2026-10-07T23:18:13.632873+00:00`; OCF `2026-10-07T23:37:11.859016+00:00` |
| PVD USD H1 | `a7360d2fc9a8a67a1535820813cda2bb8ef288466cd36c949e050c2f2a1b290a` | `2026-09-29T11:31:14.408633Z` |
| PVD VND annual | `6ee20a554891c449a8ee72fffe6358bc9b32145d066a7e52d8492d88f305139c` | Income `2026-10-07T23:18:13.632873+00:00`; balance `2026-10-07T23:37:11.859016+00:00` |
| FPT annual | `bb14bafff1a7849217f34cf4b50e0e3d69d91968f217a66d7c68f07d4c1af284` | Revenue/equity `2026-10-08T00:07:56.779802+00:00`; provision `2026-10-08T02:23:30.931096+00:00` |

All per-field exact citations and actual retrieval times are preserved in the output
and checked against the retained rows. `render_research_boundaries` prints these
references, observations, current gaps, interpretation blockers and independent flags.
Existing long/short thesis lens states and Portfolio Opportunity Cost are untouched;
this object may later be referenced but is currently non-voting and offline only.

## Verification and release

Run the main focused suite and affected official projection/annual component/Portfolio
regressions, then `py_compile`, `git diff --check` and native roadmap `--check`.
Record bounded test-process time/memory, without a concurrent full-suite process.
Complete the native roadmap state with the local `HEAD` checkpoint sentinel, no queue
or successor, and create one local checkpoint commit. Push, PR, merge and deployment
are separate approval classes; the next gate is explicit owner approval to push this
exact local candidate and open a PR. No release or production authority is implied.

Local acceptance on October 8: **114 focused tests passed**, including **35** in the
main matrix suite and the affected official projection, FPT annual component and
Portfolio Opportunity Cost suites. Pytest time **2.78 s**; sampled process lifetime
**4.20 s**, peak RSS **140,361,728 bytes** (~133.86 MiB), private memory
**344,092,672 bytes** (~328.15 MiB), sampled every 50 ms. These are test-process
measurements, not host/production peaks. No concurrent full suite, network financial
acquisition, PDF/OCR rescan, Owner Daily, database write, publication, WD Passport or
NAS access. `py_compile`, diff check and native roadmap check passed; the roadmap
dirty/sentinel warnings before commit resolve with the single local checkpoint.

## PR96 focused CI corrective (local checkpoint)

Approved predecessor `99b2c9adb0ef4f56720da0dac84617f1f53a82b2`, PR #96,
CI run `37771483898`: the active reading budget and production-root offline Stage 1
import guard exposed two candidate regressions. Neither guard nor its tests changed.
Historical roadmap paragraphs are retained verbatim below; ACTIVE_STATE host-local
paragraphs are rewrapped with identical words. The six active files total **101,820
bytes** on this Windows checkout (**101,401** with LF); ACTIVE_STATE has **319 lines**.

The independent consumer verifier above removes the Stage 1 runtime dependency.
Eight canonical full-output golden identities from the approved predecessor prove
PNJ/PVD/FPT at both cutoffs and valid context/valuation parity, including order and
duplicate determinism. Additional tests retain nested forbidden aliases, nonfinite
rejection, seal identity, source metadata, schema/fitness and authority restrictions.
No Stage 1 producer, reducer, snapshot verifier or authority was changed.

Final bounded validation: **284 passed, 1 deselected in 25.22 s**, including the
original **114** Economics/affected regressions, **23** new corrective proofs, active
control-plane checks and thesis matrix/Stage 2/portable acceptance regressions.
The deselected retained-evidence acceptance test requires the absent historical
`.stocklookup/scratch/thesis-evidence-matrix-20261002.ndjson`; an initial run passed
284 tests but reported that missing-fixture setup error. Final selection uses the
existing `-m 'not retained_evidence'` tier boundary; no storage restoration/rescan.
`py_compile`, diff check and native roadmap check pass: **ON_TRACK**, same COMPLETE
milestone, empty successor queue, authority NONE. Only current milestone notes change
in machine state to bind this corrective checkpoint.

The owner authorized a normal local corrective commit only. The remote PR retains
the predecessor until explicit approval to push the exact new local SHA to PR #96.
No new PR, push, merge, deployment, Daily, production/storage modification or successor.

## Retained prior checkpoint detail

The following historical detail moved verbatim from ROADMAP_CURRENT to keep the six-file
active reading set below its unchanged 100-KiB budget. It adds no execution or capability
authority. Current-state summaries and links remain in ROADMAP_CURRENT and ACTIVE_STATE.

## PRIOR — `OFFICIAL_FINANCIAL_DOCUMENT_REPRESENTATION_RECOVERY_V1` (COMPLETE)

Three language-counterpart PDFs are image-only. Zero facts recovered.
Disposition `OFFICIAL_REPRESENTATION_BOTTLENECK_CONFIRMED`.

## PRIOR — `QNS_2026_H1_OFFICIAL_DETAIL_RESOLVER_AND_FINANCIAL_EVIDENCE_V1` (COMPLETE)

One detail-page request rebound the retained QNS PDF (SHA `5a06a40f…`); no download, no new
OCR. Equity remains the only qualified 2026-H1 fact; other fields stay blocked on damaged headers.

## PRIOR — `VNM_QNS_POW_CURRENT_OFFICIAL_FINANCIAL_EVIDENCE_ACQUISITION_V1` (COMPLETE)

Fixed three-issuer 2026-H1/Q2 probe; no cohort expansion.
Reviewed consolidated H1 statements under the fixed OCR profile, known October 8:
VNM cash 4,535,672,366,831 VND (retained source) and QNS equity 10,647,823,148,609 VND
(owner-authorized detail page and one PDF). POW's seeded index answers 404. Strict shares
and valuation stay zero. Exact next gate: a POW first-party financial-statement index
locator; remaining VNM/QNS fields need undamaged headers, not repair.

## PRIOR — `ANNUAL_EARNINGS_COMPONENT_AND_SOURCE_FAITHFUL_OCR_NORMALIZATION_V1` (COMPLETE)

Audited FY2025 components may enter historical earnings-quality context when the row,
column, amount, unit, scope, assurance and citation are literal. FPT line 03
`Provisions` 651,406,282,654 VND is that component. It stays `FY2025 / AUDITED`,
recurrence UNKNOWN, and does not change current fields, P/E inputs, normalized EPS,
or completed October 7 records. Source-faithful superscript normalization is not
provable on the five retained cells and is not applied. `Số cudi ky` and `²0²5`
remain unqualified headers.

## PRIOR — `PNJ_VRE_REVIEWED_H1_PROVISION_COMPONENT_AND_TOTAL_ASSET_IDENTITY_V1` (COMPLETE)

The October-8 owner campaign delegates repeated bounded implementation and release.
HPG FY2025 audited capital note qualifies 7,675,465,855 ordinary outstanding shares
at December 31, 2025. It is later-known historical context, not a current denominator.
July 2's 8,442,964,520 is **listed** quantity; future promotion rejects the legacy
common label. Continuity from January 1 through October 7 remains unproven.
Strict shares/valuation stay zero; completed sessions and T0 remain immutable.
The previous bounded filing-acquisition milestone completed in PR #80; PR #81
closed its handoff. PNJ/PVD assurance and geometry now qualify six historical fields. Annual overlay2→10;
current fields9, annual exact metrics94 and strict valuation0 are unchanged.
PVD assets/equity and PNJ annual operating-flow code proof are complete; ambiguous
PNJ H1/PVD cash-flow values and debt remain blocked.
`queued_next=[]`; select the next remaining financial geometry/earnings-evidence lane under recorded
owner delegation. FPT annual revenue/equity qualification is complete; NVL reviewed H1 source assurance is qualified; exact fields remain blocked. Bounded share-basis assessment found no
qualifiable continuity chain. Retained H1 requalification adds PNJ/VRE provision components and VRE cash/equity/OCF,
known October 8 (not completed October 7); a 2026-template row-270 total-asset false-promotion path is closed.
No October-8 production Daily is authorized.
[Campaign and exact blockers](internal/STOCK_LOOKUP_AUTONOMOUS_CAMPAIGN_20261008.md).

**2026-10-06 release:**
`POST_FIRST_REAL_DAILY_PHASE_C_RESOURCE_ARCHITECTURE_RELEASE_V1` releases reviewed candidate
`3231616022213aac7f8c75e164c1f403566ee12c`
(`POST_FIRST_REAL_DAILY_PHASE_C_WHOLE_PIPELINE_RESOURCE_ARCHITECTURE_CLOSEOUT_V2` /
`RESIDUAL_PEAK_CORRECTIVE_READY`), continuing V1 `8ca12295` on
`perf/post-first-real-daily-phase-c-resource-simplification-20261006`. Whole retained heavy
path completed at 4.03 GiB private; separate actual Owner completion/handoff completed at
5.51 GiB, both under the unchanged 7-GiB guard. Historical production peak was about
10.23 GiB. Streaming all verified T0 records into seven-axis velocity context removes the
measured residual failure. Exact semantic parity. Authority effect none. Fresh provider
acquisition and production Daily orchestration stay outside this release. Host disk admission
was AMBER after retained scratch and must be READY before the next Daily.
[Whole model, benchmark scope, parity, maturity and review boundary](internal/PHASE_C_WHOLE_PIPELINE_RESOURCE_CLOSEOUT_20261006.md).
This commit is the release head. No new milestone starts. Capture depth2 stays
`DEPTH_PENDING`; retained first-real evidence below is historical and unchanged. V1's
[intermediate proof](internal/POST_FIRST_REAL_DAILY_PHASE_C_RESOURCE_SIMPLIFICATION_20261006.md)
remains preserved.

**Result** (read-only harness, cutoff `2026-10-05T16:00:00Z`):
- *Capture:* complete. `prospective_capture_complete_session:661a12b7fd0bbbde2a747e660b88f7b1eb33b57ad6d96fc3db4ddef844327d5d` (658 capture-complete tickers; 853 exact-session observed).
- *Marker:* published. `first_complete_capture_session:48a52e9458f361aa50bbaf5297ab98d5ccb9d5d6f76a1522cb8290bc7c7028c3`, session 2026-10-05, `written_at` `2026-10-05T11:31:02.861384+00:00`.
- *T0:* available. `prospective_decision_snapshot:1c496e3f7a2df9770e269ef20821805ef0cb8c76d34ebb2869d72fbb61e319f9`; seal index `prospective_t0_seal_index:afe7fe3b1cda2e2d7f8e10f7d61e8a77932ea9939eff13ede4de2327ba6e6fb6`.

Readiness count is 1 and `DEPTH_PENDING`. Representation tier is OPEN. `positive_listing` stays
`STILL_BLOCKED` (195 UNKNOWN exchange). `official_verification` stays conditional and closed;
`raw_as_traded` and `ca` stay closed. Calendar receipt is OPEN. Owner Daily journal is `COMPLETE`.

**Measured Canonical-child peak:** `peak_rss_bytes` `10985897984` (~10.23 GiB), above the 6.5–8.0 GiB
band. That band is unchanged. Publication-only resumes are not this measurement.

**Decision-intelligence closure:** coverage, historical context, calibration, the
evidence packet, and the workbench now share one research spine. Counts and limits:
[closure](internal/DECISION_INTELLIGENCE_COVERAGE_AND_CALIBRATION_CLOSURE_20261007.md).

**Portfolio research workbench:** `PORTFOLIO_RESEARCH_DECISION_WORKBENCH_FOUNDATION_V1`
is overlap and concentration research. It does not size or place orders. Details:
[workbench](internal/PORTFOLIO_RESEARCH_DECISION_WORKBENCH_FOUNDATION_20261006.md).

**Evidence packet:** `HUMAN_AI_DECISION_EVIDENCE_PACKET_CONVERGENCE_V2` keeps named
measurements, requires analogue disclosure, and does not delegate the capital decision.
No buy score and no CLI. Details:
[evidence packet](internal/HUMAN_AI_DECISION_EVIDENCE_PACKET_CONVERGENCE_V2_20261006.md).

**Outcome review:** `DECISION_OUTCOME_CALIBRATION_AND_FALSE_NEGATIVE_REVIEW_V1` is a
descriptive review of retained horizons 1, 3, 5, 10 and 20. It does not emit probabilities
or change production thresholds. The streamed 2026-10-06 recount is T5 9,590, T10 5,823,
T20 16. Details:
[outcome review](internal/DECISION_OUTCOME_CALIBRATION_AND_FALSE_NEGATIVE_REVIEW_20261006.md).

**Historical research panel:** `HISTORICAL_TEMPORAL_RESEARCH_PANEL_FOUNDATION_V1`
is research memory only. It is not PIT backtest authority. The retained small-file
slice is 2,445 reconstructed rows from 26 indexed sessions. NVL and PNJ remain
without cohort evidence. Details:
[panel foundation](internal/HISTORICAL_TEMPORAL_RESEARCH_PANEL_FOUNDATION_20261006.md).

**Current-research freshness:** `CURRENT_RESEARCH_FUNDAMENTAL_CI_VALUATION_FRESHNESS_CONVERGENCE_V1`
is a diagnostic contract only. It does not fill missing fundamentals. Retained 2026-10-06
valuation coverage stays sparse (13 official-qualified financial inputs, 5 research-usable P/E
rows, 0 price-and-qualified-share rows). Details:
[freshness contract](internal/CURRENT_RESEARCH_FUNDAMENTAL_CI_VALUATION_FRESHNESS_20261006.md).
The Forex idea bank is not a roadmap entry.
