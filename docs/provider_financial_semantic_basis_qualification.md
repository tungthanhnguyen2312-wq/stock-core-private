# Provider Financial Semantic Basis Qualification — contract

Status: **evaluated 2026-08-27, `OUTCOME_C_RETAINED_PROVIDER_ABSOLUTE_SEMANTICS_REMAIN_UNQUALIFIED`**.
Module: [`provider_financial_semantic_basis.py`](../provider_financial_semantic_basis.py). Tool:
[`tools/derive_provider_financial_semantic_basis_v1.py`](../tools/derive_provider_financial_semantic_basis_v1.py).
Tests: [`tests/test_provider_financial_semantic_basis.py`](../tests/test_provider_financial_semantic_basis.py).

This is a follow-on inside the existing Layer-3 canonical-financial-facts lane
(`canonical_financial_facts.py`, `canonical_financial_resolvers.py`, `canonical_fact_store.py`,
see [`market_wide_financial_normalization_contract.md`](market_wide_financial_normalization_contract.md))
and the current-fundamental-research inventory (`financial_fact_coverage_recovery.py`,
`market_wide_current_fundamental_research.py`). It adds no new financial model, valuation engine,
or provider, and promotes nothing to `OFFICIAL_QUALIFIED`.

## The question

Do already-retained provider (VCI/KBS) financial facts carry enough evidence — schema/library
evidence *and* multi-issuer official-anchor reconciliation — to qualify an **absolute** semantic
basis (currency, unit scale, statement scope, period duration) for a whole `(provider,
statement_family)` shape, so that facts of that shape become `PROVIDER_EXACT_RESEARCH_USABLE`
without each needing its own citation?

## The rule (both legs required, not either)

A shape may qualify only with:

1. **Provider-owned schema or explicit library-contract evidence** (`SCHEMA_EVIDENCE_BY_PROVIDER`
   in the module, cited to the installed `vnstock==4.0.4` source, not a live probe — see "Why a
   live probe was not needed" below); **and**
2. **Zero-disagreement, discriminating (≥2 issuers, ≥5x magnitude spread), reconciliation** against
   independently qualified official citations (`canonical_fact_store.load_official_citations`).

Either leg alone is explicitly insufficient. Leg 1 is a ratio/pattern identity (see
[`kbs_empirical_basis_qualification.md`](kbs_empirical_basis_qualification.md)'s own warning about
this exact trap for a different provider): "the numbers are internally consistent with a
hypothesis" is not "the numbers are independently anchored." Leg 2 alone, on a single ticker, is
explicitly excluded by the milestone brief ("no single-ticker proof may become market-wide
authority").

## Phase 1/2 — provider/endpoint schema matrix (evidence in `provider_financial_semantic_basis.py`)

| Provider | Statement family | Populated? | Currency/scale schema evidence | Duration evidence | Retained in our bytes? |
|---|---|---|---|---|---|
| KBS | income_statement | Yes (1,407/1,453 tickers, 96.8% of populated income statements) | `unit=1000` request param + `×1000.0` library multiplier (`vnstock/explorer/kbs/financial.py:566,367,259`); 99.97% of a 5,943-row market-wide sample are exact multiples of 1000 | `PeriodBegin`/`PeriodEnd` named in the endpoint's own `Head` objects (library docstring, `financial.py:160`); already wired as `SINGLE_QUARTER` in `market_wide_current_fundamental_research.KBS_KQKD_QUARTER_SEMANTICS`/`_period_basis` | **No** — vnstock's own parser consumes `Head`/`Audit`/`Unit` internally and returns only a DataFrame of item/period/value; the metadata never reaches `bctc_sync.py`, one layer above anything this repo's retention code touches |
| KBS | cash_flow | Yes (1,013/1,398, majority) | Same request/multiplier contract (shared `_fetch_financial_data`/`_parse_financial_response` code path) | Not independently re-verified for this endpoint; duration claim stays scoped to income_statement per the existing dict | No |
| KBS | balance_sheet | **No** — 0/1,493 KBS-sourced balance-sheet payloads ever populate; VCI supplies 100% | N/A (`NOT_APPLICABLE`) | N/A | N/A |
| KBS | financial_ratios | Reachable but out of scope (no canonical identity in `METRIC_REGISTRY` sources from it) | N/A (`NOT_APPLICABLE`) | N/A | N/A |
| VCI | balance_sheet | Yes (dominant: 1,381/1,745 quarterly) | **None** — zero occurrences of unit/scale/currency/multiplier anywhere in `vnstock/explorer/vci/financial.py`; only 13.6% of a 24,885-row sample are multiples of 1000 (full-precision VND, consistent with no rescaling) | `UNKNOWN` for every quarter (`VCI_INCOME_STATEMENT_SEMANTICS`, pre-existing) | No — nothing upstream to discard; the metadata was never there |
| VCI | income_statement / cash_flow | Rare (failover only, 46 / 347 tickers) | Same absence of schema evidence | `UNKNOWN` | No |

## Phase 2 — retained-metadata check result

**Nothing was discarded by this repository's retention code.** For both providers, the metadata
(KBS's `Head`/`Audit`/`Unit`; VCI has none to begin with) is consumed or absent one layer above
anything `bctc_sync.py`/`raw_financial_store.py` ever sees: `bctc_sync.py` calls
`vnstock.api.financial.Finance(...).<method>(period=...)`, which already returns a parsed
`pandas.DataFrame` — not the raw JSON. There is no retained raw byte on disk from which
`PeriodBegin`/`PeriodEnd`/`United`/`AuditedStatus`/`ReportDate`/`LastUpdate` could be recovered by
a code fix; recovering them requires a new request to the endpoint (Phase 4).

**One real, unrelated retention/propagation bug was found and fixed while checking this**:
`canonical_fact_store.load_official_citations`'s metric-name mapping had
`"cash_and_equivalents": "cash_and_equivalents"`, but `canonical_financial_facts.METRIC_REGISTRY`
spells the same balance-sheet line `cash_and_cash_equivalents` — the same pre-existing
two-spellings correspondence `financial_fact_coverage_recovery.OFFICIAL_PANEL_CANONICAL_METRIC_ALIAS`
already documents for a different consumer of the same pair of names. The citation therefore never
matched any built fact. Fixed to map to the correct name; this alone newly reconciles 5 additional
already-retained facts (NVL/PAN/POW/QNS cash, on top of HPG) — see Phase 3.

## Why a live probe (Phase 4) was not needed

The installed `vnstock==4.0.4` library **source code** is strictly better evidence than a fresh
live capture would be: it shows the *exact* transform applied (`unit=1000` request + `×1000.0`
multiplier), not merely a schema snapshot from one moment. A live probe could only additionally
confirm that `PeriodBegin`/`PeriodEnd` literally appear in the raw JSON (plausible — the library's
own docstring names them as real `Head` fields it simply does not extract) and read the literal
`United` code value. Neither would change the qualification outcome: leg 2 (reconciliation) is
blocked by data availability (see next section), not by remaining schema uncertainty, and a probe
cannot fix a retained-window-depth gap without acquiring broad new historical coverage — explicitly
out of scope for this milestone.

## Phase 3 — official-anchor reconciliation (real, retained evidence; `dashboard-runtime`, read-only)

Ran `canonical_fact_store.build_ticker_facts` fresh (current `official_citations`, zero network,
zero writes) for the 8 tickers that carry any official citation (FPT, HPG, NVL, PAN, POW, PVD,
QNS, VNM — bounded by construction, see module docstring).

**`(VCI, balance_sheet)`** is the only shape with any reconciliation evidence at all, via the
existing annual→Q4 alias for point-in-time stock metrics:

- `shareholders_equity`: **6 agree** exactly (FPT, HPG, NVL, PAN, POW, QNS; 8.86T–114.6T VND, a
  ~13x spread) — **2 disagree**: PVD by ~25,250x (16.05T retained vs. 635,711,153 cited — a real,
  unexplained contradiction, not rounding) and VNM by ~2.7% (36.17T vs. 37.17T).
- `cash_and_cash_equivalents` (after the naming fix above): **5 agree** exactly (FPT, HPG, NVL,
  PAN, POW; 539B–11.56T VND) — **2 disagree**, the *same* PVD/VNM.

A shape with reproducible counter-examples in its own tested sample is not "consistent
reconciliation." `(VCI, balance_sheet)` fails the qualification rule despite passing the
discriminating-anchor threshold (≥2 issuers, ≥5x spread) on its own — the two checks are
independent, and this shape is exactly why both are enforced.

Every other shape has **zero** reachable reconciliation, for a structural reason unrelated to
scale/currency uncertainty: the only retained official citations are annual, the only retained
provider payloads are quarterly. `data_bctc/*_year.parquet` do not exist for any ticker in the
runtime store — `bctc_sync.py`'s own `"[VÁ P0-1 12/07/2026]"` comment documents a real historical
filename-collision bug (`scrape --period year` used to overwrite the same-named quarter file) that
was fixed going forward but never backfilled. The stock-vs-flow alias that lets an annual citation
stand in for a Q4 balance-sheet fact cannot and does not extend to flow metrics (revenue,
net_income, operating_cash_flow) — "FY2024 revenue is not Q4 revenue" per
`load_official_citations`'s own docstring — so those metrics have no reachable anchor regardless of
provider.

## Phase 5 — semantic-basis contract registry (real result)

`tools/derive_provider_financial_semantic_basis_v1.py` produces one
`provider_financial_semantic_basis/v1` contract per observed shape:

| Shape | Verdict | Reason |
|---|---|---|
| `KBS:income_statement` | `PROVIDER_METADATA_PARTIAL` | duration resolved via schema evidence; currency/scale unreachable (no annual retained payload) |
| `KBS:cash_flow` | `PROVIDER_METADATA_PARTIAL` | same |
| `KBS:balance_sheet` | `NOT_APPLICABLE` | endpoint empirically empty market-wide |
| `KBS:financial_ratios` | `NOT_APPLICABLE` | no canonical identity sourced from this family |
| `VCI:balance_sheet` | `SEMANTIC_BASIS_UNRESOLVED` | real disagreement (PVD, VNM) inside its own tested sample |
| `VCI:income_statement` | `SEMANTIC_BASIS_UNRESOLVED` | no schema evidence, no reachable reconciliation |
| `VCI:cash_flow` | `SEMANTIC_BASIS_UNRESOLVED` | same |

**Zero shapes reach `PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED`.**

## Phase 6 — per-fact `PROVIDER_EXACT_RESEARCH_USABLE` (real result: proven correct, zero current beneficiaries)

Independent of the (failed) shape-wide qualification, a fact may still earn
`PROVIDER_EXACT_RESEARCH_USABLE` **per fact**, with zero generalization: it must itself be
`canonical_financial_facts.STATUS_QUALIFIED` (independently reconciled against a citation), backed
by `unit_authority == "official_citation_agreement"`, and its own `statement_scope` must be
independently resolved (not `unknown`) — belt-and-suspenders against a coincidental value match
masking a scope mismatch. `classify_provider_exact_research_usable` implements this; it is proven
correct by direct unit tests, and empirically finds 10 real qualifying facts today (FPT, HPG, NVL,
PAN, POW × `shareholders_equity`/`cash_and_cash_equivalents`) — **all for tickers that are already
`OFFICIAL_QUALIFIED`** in the p3f13 panel for the same identity, so **zero cells in the Phase-7
inventory actually change state**. QNS is a instructive near-miss: its `cash_and_cash_equivalents`
value matches its citation exactly, but its retained balance sheet carries no non-zero
minority-interest line, so `statement_scope` stays `unknown` and the belt-and-suspenders check
correctly withholds the tier even though the raw numbers agree.

The mechanism requires no further code change the day a `PROVIDER_TIER` (non-official-panel)
ticker gains its own official citation — today, every ticker with a citation is already
`OFFICIAL_TIER`, so the pools are disjoint by construction, not by an implementation gap.

Also worth flagging (not fixed here — out of this milestone's scope, since it concerns the
*official* evidence panel, not provider semantics): PVD's and VNM's `financial_identity_citations.jsonl`
entries for `shareholders_equity`/`cash_and_cash_equivalents` disagree with their own retained VCI
balance-sheet values, even though p3f13 marks both `OFFICIAL_QUALIFIED` for those identities. This
may be a citation data-entry issue (PVD's cited value, 635,711,153, is implausibly small for total
equity) or a genuine scope mismatch, and deserves separate review by whoever owns official-evidence
citation quality.

## Authoritative boundary (unchanged)

`OFFICIAL_QUALIFIED` still requires the existing official-evidence citation/panel path
(`p3f13_official_financial_evidence_scaleout.py`) — nothing here can produce it.
`PROVIDER_EXACT_RESEARCH_USABLE` carries only
`CURRENT_RESEARCH_NONAUTHORITATIVE_VALUATION_INPUT` plus the existing provider-research allowed
uses (`descriptive_context`, `provider_series_growth`, `sector_aware_research`,
`shadow_comparison`); it is explicitly `NOT_OFFICIAL_QUALIFIED`, `NOT_AUTHORITATIVE_VALUATION`,
`NOT_PIT`, and forbidden from `target_price`/`buy_sell_recommendation`/`cross_sectional_ranking`/
`portfolio_sizing`/`backtesting`/`execution_actionability`. `READY` on every current-valuation
metric is unaffected (verified: the rerun valuation artifact is byte-identical to the pre-milestone
one — `valuation_unchanged: true`).
