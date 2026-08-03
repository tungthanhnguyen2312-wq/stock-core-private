# Market-wide canonical financial normalization — contract

Status: **layers 1–3 implemented 2026-08-03**; layer 4 is live as a readiness-reporting layer
that introduces no new model. Layer 3 shipped as P1E — see
`operations-review/p1e-milestone-20260803/P1E_OPERATIONS_REVIEW.md` for the measured result and
`docs/DECISIONS.md` (2026-08-03) for the four decisions it forced. Three statements in the
layer-3 section below were corrected by building it, and are marked inline.

This contract replaces the per-ticker evidence-bridge pattern for financial statements. That
pattern proved the qualification contract on HPG and VNM and is the right tool for a
PDF-cited fact; it is the wrong tool for 1,500 issuers, because it makes every additional
ticker a separate piece of manual work. What follows is the pipeline that does the same job
once, for everyone, and leaves only genuine exceptions in a review queue.

## The four layers

```
retained statement payloads  (data_bctc/*.parquet, already collected)
  │
  ├─ 1. raw retention          raw_financial_observations.py + raw_financial_store.py
  │      every line item, every period, full provenance, no allowlist
  │
  ├─ 2. statement taxonomy     statement_taxonomy_classifier.py (balance sheet)
  │      + financial_entity_applicability.py (income statement)
  │      which template the filing uses → which models may run at all
  │
  ├─ 3. canonical facts        NOT YET BUILT
  │      raw identity → canonical metric, with scope/unit/sign/period resolved
  │
  └─ 4. calculation engines    existing modules, fed market-wide instead of per ticker
```

Layer 1 is deliberately independent of layers 3 and 4. A mapping rule discovered next month
must be applicable to data already on disk, without re-fetching the universe from the
provider. That is the single most important property of this design.

## Layer 1 — raw retention

### Retention policy

`retention_policy = "all_raw_items"`. There is no allowlist. `financial_observations.py`
(the bounded Phase 14B pilot) keeps only the ~50 `item_id` values in its `_CODES` set; that
module is unchanged and still serves its pilot, but it is not the market-wide path and must
not be extended into one.

### Source

`<runtime_root>/data_bctc/<TICKER>_<family>_<frequency>.parquet`, where family is one of
`balance_sheet` / `income_statement` / `cash_flow`. These payloads are already collected by
the existing sync chain. Layer 1 performs **no network access at all** — it is a pure
re-projection of bytes already on disk. It never opens `vn_stock.db`.

A payload whose filename does not parse raises `PayloadNameError` and is reported in
`unparsed_payloads`; it is never silently skipped. One such file exists today
(`BIO_balance_sheet.parquet`, no frequency suffix).

### Observation identity

Identity fields, hashed into `identity_key`:

```
schema_version · ticker · provider · statement_family · reporting_frequency
reporting_period · period_type · period_variant_index · period_column
raw_item_id · item_id_occurrence · row_ordinal
```

`observation_id` additionally covers `raw_value` and `source_sha256`, so a revised value at
the same identity gets a new observation id while keeping the identity stable — which is
what makes restatement detection possible later.

No timestamp appears in any hashed field. Retrieval time comes from the payload's own
`scraped_at` column, never from the clock.

### The two identity hazards this layer exists to make visible

**`item_id` is not unique within a payload.** HPG's income statement carries `revenue`
twice — gross revenue on line 1 and net revenue on line 3 — and its balance sheet carries
`short_term_investments` twice. Over a 40-payload sample, 21 payloads had at least one
repeated `item_id`; market-wide, 237,466 of 1,546,197 observations (15.4%) sit on a repeated
id. Every observation therefore carries `row_ordinal` and `item_id_occurrence`, and repeated
ids are flagged `ambiguous_raw_item_id`. **A layer-3 mapping rule keyed on `raw_item_id`
alone is incorrect by construction** and must disambiguate on occurrence, label, or both.

**Reporting-period columns repeat.** A payload can carry both `2025-Q4` and `2025-Q4_1`.
Both normalize to `reporting_period = "2025-Q4"` and are distinguished by
`period_variant_index`. The index is assigned **from the suffix, not from column order** —
the payloads really do carry `2025-Q4_1` *before* `2025-Q4`, so ordering by position would
promote the writer's de-duplication artifact to primary. The unsuffixed column is index 0;
every other variant is flagged `duplicate_period_column`. Market-wide this affects 22,627
observations. They are restatement candidates and are never collapsed or dropped.

### What is deliberately left unknown

`statement_scope`, `raw_currency`, `raw_scale`, `cumulative_state` and `restatement_state`
are all `unknown`, with `statement_scope_unknown` and `currency_and_scale_unknown` on every
record. The retained payloads carry no evidence for any of them. The highest state this
layer can assign is `qualification_state = "retained_raw"`; nothing here is ever
`qualified`, and no consumer may treat a layer-1 observation as an evidence-qualified value.

### Store layout and the incremental contract

```
<runtime_root>/data/market-wide-financials/
    observations/<TICKER>.jsonl.gz    one deterministic shard per ticker
    ingest_state.json                 per-ticker input hashes and shard hashes
    coverage_report.json              deterministic coverage statistics
    coverage_by_ticker.csv            the same coverage, one row per ticker
```

Untracked generated runtime data, like `data/financial-observations/`. Current size: 205 MB
for 1,546,197 observations across 1,493 tickers.

A shard is rebuilt only when its `inputs_fingerprint` changes, or when the shard is missing
or its bytes no longer match `shard_sha256`. `inputs_fingerprint` covers the sorted
payload-name/SHA-256 pairs **and the observation and store schema versions** — keying on
payload hashes alone would leave every shard looking `unchanged` after a change to the
extraction logic itself, so the store would keep serving observations built by code that no
longer exists.

A shard whose ticker no longer has any payload is listed in `orphaned_shards` and **is never
deleted**. Removing retained observations is a data-loss decision that belongs to the
operator.

### Determinism

Shard bytes are gzip with `mtime=0` over canonical JSONL (sorted keys, no whitespace, LF).
A shard is byte-identical across rebuilds on identical inputs, on any machine, at any time —
verified for all 1,493 shards by `--check`. `generated_at` is the only clock-dependent field
in `ingest_state.json` and is excluded from `state_fingerprint`; two runs minutes apart
produce the same `state_fingerprint`.

## Layer 2 — statement taxonomy and model applicability

### Authority order — unchanged from `docs/statement_taxonomy_sidecar_contract.md`

1. `config/ticker_entity_profiles.csv` — the only thing that may **name** an issuer's
   institution type. Not modified by this milestone.
   `CANONICAL_PROFILE_BACKFILL_AUTHORIZED` remains `NO`.
2. Generated statement evidence — may only ever **withhold** a corporate model. A corporate
   template never grants a corporate archetype, and an absent archetype is never read as
   corporate.
3. Unknown — yields `insufficient_evidence`, never a default.

### Two evidence families

The shipped sidecar classifies the **balance sheet** only. That leaves 109 tickers with an
income statement but no retained balance sheet unclassified, and leaves the insurance
template permanently `financial_specialized_ambiguous` because no exclusive insurance marker
set exists on the balance sheet.

`financial_entity_applicability.py` adds the **income statement** as a second, independent
family. Its marker sets were derived from the retained payloads and validated market-wide
before being written down:

| family | markers | tickers matched | corporate contamination | cross-group overlap |
|---|---|---|---|---|
| `credit_institution` | 5 | 29 / 29 | 0 of 1,261 corporate income statements | 0 |
| `securities_company` | 5 | 41 / 41 | 0 | 0 |
| `insurance` | 5 | 12 / 12 | 0 | 0 |

Every marker was checked against the union of all 1,261 corporate-template income statements
and appears in none of them. The insurance set resolves 12 of the 13 tickers the balance
sheet can only call ambiguous; the 13th has no retained income statement and stays ambiguous.

The income-statement markers live in `financial_entity_applicability.py`, **not** in
`statement_taxonomy_classifier.py`. That module is pinned at `VERSION = "2.0.0"` and its
output feeds `statement_taxonomy_sidecar.json`, which is hash-bound into the shipped bundle;
adding markers there would move `classifier_version` and therefore the sidecar fingerprint,
changing a production artifact for a reason unrelated to this milestone.

### Disagreement fails closed

Two families evidencing different specialized templates yields
`template_family = "financial_specialized_conflicted"` and still withholds the corporate
models. Two families disputing *which* specialized financial template a filer uses still
agree that it is one; restoring EBITDA on a disagreement would be the fail-open direction.

### `not_applicable` is not `unavailable`

For `ebitda` and `ev_ebitda`:

| condition | status | authority |
|---|---|---|
| manual profile is `bank` / `securities` / `insurance` / `finance_company` | `not_applicable` | `manual_profile` |
| manual profile is `corporate` | `applicable_subject_to_inputs` | `manual_profile` |
| no manual profile, generated evidence names a specialized financial template | `not_applicable` | `generated_statement_evidence` |
| anything else | `insufficient_evidence` | `unknown` |

`unavailable` invites someone to go and find the missing input. `not_applicable` closes the
question: a bank has no EBITDA and no input will ever produce one. Every `not_applicable`
result names substitute metrics (`p_b`, `roe`, `net_interest_margin`, `cost_to_income_ratio`,
`combined_ratio`, …) so it points somewhere instead of only closing a door.

This closes the under-classification the 2026-08-03 market-wide readiness audit found:
`not_applicable` went from **7** manually-profiled tickers to **82**.

## Layer 3 — canonical facts (BUILT 2026-08-03)

> **Corrections this section forced when it was implemented.** Kept inline rather than rewritten,
> because the original reasoning is what the corrections are against.
>
> 1. **Provider does not select the dialect.** The table below is right that the vocabularies
>    partition the universe; it is wrong to read `source` as choosing between them. HPG's income
>    statement is `source = KBS` written in the VCI vocabulary. Matching keys on the raw item id;
>    `canonical_financial_facts.detect_dialect()` reports the vocabulary's own dialect.
> 2. **Scope, sign and basis are demonstrable; currency and absolute scale are not.** A non-zero
>    minority interest grants `consolidated`; the gross-profit identity demonstrates the sign
>    convention; beginning-of-period cash demonstrates the cumulative basis. Nothing in the
>    payloads fixes the currency or the absolute unit, so `provider_reported` is the ceiling
>    without an official citation.
> 3. **A fourth resolver was needed and is a gate, not a diagnostic.** Balance-sheet cash must
>    equal cash-flow end-of-period cash, or the cash-flow payload's period label is not
>    trustworthy. See `docs/DECISIONS.md`, 2026-08-03.
>
> Implemented by `canonical_financial_resolvers.py`, `canonical_financial_facts.py` and
> `canonical_fact_store.py`; operated by `tools/ingest_canonical_financial_facts.py`.

### Original specification

Target metric vocabulary and per-metric status:

```
qualified · provider_reported · partial · conflicted · unavailable · not_applicable
```

`config/canonical_metric_candidates.csv` is the seed: `canonical_metric`, `template_family`,
`statement_family`, `raw_item_id`, `dialect`, `priority`. It currently expresses raw-identity
*candidacy* only, which is what the coverage report measures. Turning a candidate into a
qualified fact additionally requires resolving statement scope, currency, unit scale, sign
convention and cumulative-vs-discrete basis — none of which the retained payloads carry.

### The two provider dialects

The retained payloads come from two providers (`VCI`, `KBS`) and the cash-flow vocabulary
splits into two mutually exclusive dialects that partition the universe exactly:

| canonical metric | dialect `vci_a` | dialect `kbs_b` |
|---|---|---|
| `depreciation_amortization` | `depreciation_of_fixed_assets_and_investment_properties` (905) | `depreciation_and_amortization` (338) |
| `operating_cash_flow` | `operating_cash_flow` | `net_cash_inflows_outflows_from_operating_activities` |
| `capital_expenditure` | `payment_for_fixed_assets_constructions_and_other_long_term_assets` | `purchases_of_fixed_assets_and_other_long_term_assets` |
| `interest_expense` (cash flow) | `borrowing_costs` | `interest_paid` |

905 + 338 = 1,243, the exact corporate cash-flow payload count. **A candidate set that knows
only one dialect reports ~73% coverage on a metric that is present for ~100% of filers.**
This is the single most consequential normalization finding of the milestone, and it is why
the coverage report breaks every metric down by dialect: a future single-dialect regression
is then visible instead of silent.

## Layer 4 — calculation engines (unchanged, fed differently)

No new model is introduced by this milestone. The existing engines (Piotroski, Altman Z',
DuPont, relative valuation, FCFF) keep their current contracts. What changes is that they
will be fed from layer 3 market-wide rather than from per-ticker evidence bridges.

Current-market-dependent outputs stay blocked regardless of this pipeline: enterprise value
needs market capitalisation, which needs a qualified price basis, which is pillar B's job
(`docs/DECISIONS.md`, official corporate-action ledger). The coverage report reports
`enterprise_value.blocked_by = market_capitalisation_requires_a_qualified_price_basis` rather
than implying EV is available.

## Operating it

```powershell
python tools\ingest_market_wide_financials.py --runtime-root <dashboard-runtime>
python tools\ingest_market_wide_financials.py --runtime-root <dashboard-runtime> --execute
python tools\ingest_market_wide_financials.py --runtime-root <dashboard-runtime> --check
```

Default is a strict dry run: the full plan is computed, including the hashes that decide
rebuilt-vs-unchanged, and nothing is written. `--check` re-derives every shard in memory and
distinguishes `shard_missing`, `shard_sha256_mismatch`, `content_drift` and
`not_byte_reproducible`. Exit codes: `0` success · `1` verification finding or extraction
failure · `2` bad invocation.

This tool is **not** part of `tools/operate_stocklookup.py`'s release path. It writes only
into its own store directory and produces nothing the bundle reads, so it cannot affect a
release. Wiring layer 3 into the bundle is a separate, explicit decision.

## Measured state, 2026-08-03

Universe from `screen_snapshot.csv` (active listed equity: HSX 402 · HNX 299 · UPCOM 738 =
1,439; membership deliberately does **not** depend on whether the ticker traded on the
reference date — a company that did not trade on Thursday still filed its statements).

| | |
|---|---|
| payloads discovered | 4,195 (1 unparsed) |
| tickers with a shard | 1,493 |
| raw observations retained | 1,546,197 |
| in store **and** active universe | 1,308 |
| active universe with no retained payload at all | 131 |
| with all three statement families | 1,198 of 1,308 |
| shards byte-reproducible under `--check` | 1,493 / 1,493 |

Archetype authority over the 1,308: `manual_profile` 15 · `generated_statement_evidence` 75 ·
`unknown` 1,218.

EBITDA / EV-EBITDA applicability over the 1,308: `not_applicable` 82 ·
`applicable_subject_to_inputs` 8 · `insufficient_evidence` 1,218.

Raw-identity coverage for the derived-EBITDA inputs, over the 1,226 tickers not ruled out:

| input | present |
|---|---|
| `profit_before_tax` | 1,202 |
| `depreciation_amortization` | 1,123 |
| `interest_expense` | 1,066 |
| **all three** | **1,016 (82.9%)** |

Two of these numbers contradict the current `docs/STATE.md` blocker list and are the reason
this milestone exists:

- STATE.md records `ebitda` as **0 available / 1,148** at the screening tier and EBITDA as
  computable for **2 tickers** market-wide. The raw depreciation identity is in fact present
  for **1,123** tickers. The gap was never data acquisition; it was a single-dialect mapping.
- STATE.md records `retained_earnings` as **51 available / 1,097 missing**, its second-largest
  blocker by tickers affected. The raw identity (`undistributed_earnings` on the balance
  sheet) is present for **1,148** tickers. The blocker is in the snapshot projection, not in
  the source data.

Neither statement is yet a qualified value — scope, unit and sign remain unresolved, which is
exactly layer 3's job. But the work needed is a mapping rule, not a data hunt, and that
distinction is what changes the roadmap.
