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
