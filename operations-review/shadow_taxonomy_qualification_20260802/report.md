# SHADOW_STATEMENT_TAXONOMY_AND_ALTMAN_APPLICABILITY_QUALIFICATION

UTC: 2026-08-02. Read-only milestone. No canonical profile, runtime database, evidence
store, bundle artifact, or Consumer/Dashboard wiring was modified.

## Decision

```
CANONICAL_PROFILE_BACKFILL_AUTHORIZED: NO
```

The root cause holds up and the classifier is stable, but the evidence base is still the
same 15 hand-curated profiles, and the measured unlock is roughly a fifth of what the prior
session projected. Neither supports writing generated classifications into a canonical
authority.

## Repository inspection (performed before any modification)

| | |
|---|---|
| Branch / HEAD | `main` / `04729e1b83f41590df500a6313b73ce13b1fdcff` |
| Upstream | `origin/main`, ahead 6, behind 0 -- nothing pushed |
| Working tree | `M tests/test_semantic_evidence_bridge.py` (line-endings only, pre-existing); untracked `dev/`, `operations-review/`, `tmp/` |
| `bfd0a1a` | Exists: 10 files, +601/-6, matching the prior report |
| Test run at pre-milestone HEAD | 1,164 tests, 5 failures + 22 errors = 27 failing names, reproduced twice |

**Correction to the prior session's own reporting.** Those 27 were previously described as
"pre-existing baseline failures". That is not established and is not claimed here. A
worktree at the pre-session commit `1b04355` resolves `runtime_root()` to a non-existent
path, so it reports 43 errors for path-availability reasons and is not comparable; a clean
same-directory pre-session baseline was never captured. The only claim this milestone makes
about the suite is:

> The failure/error name set is unchanged from the pre-milestone HEAD run.

Separately, running the affected modules directly at `1b04355` does confirm that
`test_entity_profiles_do_not_apply_corporate_sga_to_bank_or_insurance` fails there too, but
that is one test, not the set.

## Architecture change: three axes, previously conflated

`entity_type_classifier.py` claimed to derive `entity_type` from statement vocabulary.
That is a fail-open route -- vocabulary evidences *which form was filed*, and a form is not
an institution. Renamed to `statement_taxonomy_classifier.py` (v2.0.0) and narrowed:

```
statement_taxonomy   observed from item vocabulary        <- this module only
issuer_entity_type   config/ticker_entity_profiles.csv    <- unchanged authority
model_applicability  altman_applicability.py              <- new, see below
```

The classifier now emits `corporate_vas | credit_institution | securities_company |
financial_specialized_ambiguous | unknown`, never an `entity_type`, and carries ticker, source,
reporting period, statement scope, classifier version, matched positive and exclusion
markers, classification status, and abstention reason. A test asserts it can never emit an
`entity_type` key.

## Fail-open fix: Altman applicability is no longer `entity_type == "corporate"`

`altman_applicability.py` (new) gates Z' on entity type **and** industry. Z' retains
X5 = sales / total assets, the most industry-sensitive of its five terms, and was estimated
on manufacturing firms; the four-variable Z'' exists precisely because Z' does not transfer
to non-manufacturers. Z'' is deliberately not implemented.

| Outcome | When |
|---|---|
| `not_applicable` | confirmed financial institution |
| `eligible` | confirmed non-financial **and** industry in the manufacturing whitelist |
| `insufficient_evidence` | entity type unknown, industry unknown, or industry known but not manufacturing |

Industry comes from the retained `vn_stock.db:metadata.industry` (ICB-style, 1,678 of 1,683
tickers). Whitelisted: Basic Resources, Food & Beverage, Chemicals, Automobiles & Parts,
Personal & Household Goods. Deliberately excluded as mixed: Construction & Materials
(contractors + materials makers), Industrial Goods & Services, Health Care (pharma
manufacturing + hospitals + distribution). Excluding a real manufacturer costs a missing
score; including a non-manufacturer produces a wrong one.

HPG (Basic Resources) and VNM (Food & Beverage) both remain eligible, so the two existing
qualified results are unaffected.

## Taxonomy correction applied before checkpoint

The first shadow run labelled BVH (an insurer) `credit_institution`. It carries exactly one
credit marker, `loans_and_advances_to_customers` -- a line an insurer reports too -- and
zero deposit-taking, central-bank or interbank markers. The label asserted more than the
evidence supported.

Credit markers are now split. Only the exclusive set (`deposits_from_customers`,
`balances_with_the_sbv`, `placements_with_and_loans_to_other_credit_institutions`) may
assert `credit_institution`; the shared lending line alone yields
`financial_specialized_ambiguous` with `classification_status: abstained`. Insurance is
never named, because no exclusive insurance marker set has been validated. All five real
credit institutions in the manual set (BID, MBB, TCB, VCB, EVF) carry 4/4 exclusive
markers and are unaffected.

## Ticker accounting

| | |
|---|---|
| Raw payload files (`*_balance_sheet_quarter.parquet`) | 1,381 |
| Unique tickers among them | 1,381 (no duplicate ticker names) |
| Tickers classified | 1,380 |
| Omitted | 1 -- **BIO**, whose retained payload has no period columns at all, so no period yields a vocabulary to classify |

## Shadow results (measured, all retained periods)

- 1,380 tickers classified; every retained quarterly period evaluated, not just the latest.
- Resolved taxonomy: `corporate_vas` 1,297 / `securities_company` 41 /
  `credit_institution` 29 / unresolved 13.
- **Cross-period stability: 1,380 stable, 0 unstable.** No ticker's observed taxonomy
  changes across periods.
- The correction moved 13 tickers out of `credit_institution` into unresolved -- they had
  been labelled on the shared lending line alone.
- Confusion against the 15 manual profiles: bank->credit_institution (4),
  corporate->corporate_vas (8), finance_company->credit_institution (1),
  securities->securities_company (1), insurance->unresolved (1). Zero
  corporate/non-corporate disagreements.

**The 15-profile set remains a smoke test, not an accuracy measurement.** It contains one
securities company, one insurer, one finance company and four banks; it cannot evidence
behaviour on fund managers, holding companies with financial operations, template
migrations, or payloads missing markers.

## Measured Altman delta -- the prior "~1,100" projection was wrong

| | eligible | insufficient_evidence | not_applicable |
|---|---|---|---|
| Manual profiles only | 3 | 1,370 | 7 |
| With shadow overlay | 375 | 998 | 7 |

Newly eligible by applicability: **372**, not ~1,100. Still blocked after the overlay:
929 on `industry_not_qualified_manufacturing`, 76 on unresolved entity type.

**Applicability is not a score.** A ticker also needs all identities at one aligned
period/scope/currency/scale. Against the provider snapshot:

- 2025-Q4: 22 tickers have the seven snapshot-sourced inputs.
- 2024-Q4: 0.

So the realistic end-to-end unlock is bounded by `retained_earnings` availability (~51
tickers), not by 372. The correct framing for the earlier figure is
`estimated upper bound on applicability`, and even that was overstated by ~3x because it
ignored the industry dimension entirely.

## Provider attribution -- not changing documentation yet

All 1,381 retained balance-sheet payloads carry `source: VCI`, which conflicts with
`docs/data_capability_inventory.md` describing this domain as "KBS mapping". Per the review
requirement, the ingestion call flow (entrypoint -> provider constructor -> download ->
normalization -> persisted `source` field) has **not** been traced yet, so the documentation
is left unchanged. The field could be hard-coded, or the doc could be describing the mapping
layer rather than the raw provider. Recorded as an open question, not a correction.

## Milestone status

```
ENTITY_TYPE_ROOT_CAUSE:            CONFIRMED_AND_HIGH_IMPACT
STATEMENT_TAXONOMY_CLASSIFIER:     SHADOW_READY
CANONICAL_PROFILE_BACKFILL:        NOT_AUTHORIZED
UNIVERSE_WIDE_ALTMAN_Z_PRIME:      NOT_READY
HPG_VNM_POINT_IN_TIME_Z_PRIME:     READY_WITH_VARIANT_AND_SCOPE_WARNINGS
COVERAGE_SCANNER:                  READY
PROVIDER_ATTRIBUTION_KBS_VS_VCI:   OPEN_PENDING_CALL_FLOW_TRACE
```

## What would change the backfill decision

A materially larger labelled set than 15 -- covering fund managers, insurers, holding
companies with financial arms, and issuers that changed template -- plus a generated
sidecar (`generated_statement_profiles.jsonl`) carrying full provenance, with resolution
order `manual verified > generated high-confidence > unknown`. The sidecar is not created
in this milestone.
