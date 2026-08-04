# KBS trading-value coverage and safe-aggregation contract

**Date:** 2026-08-04 · **Starting commit:** `800c746` · **Provider:** KBS
**Network requests issued: 0.** Entirely offline, from the six raw payloads retained at
`4a07141` plus a read-only session list from the production database.

---

## 1. Why this milestone

At `800c746`, `va`'s unit was qualified (VND, `empirically_deduced`) and its *availability*
was a sentence in a capability note: "any statistic must state its own coverage." That is
advice, and advice is not a gate.

The failure it leaves open is quiet. `va` is present on 38 of 66 retained sessions. A period
total computed over those 38 rows looks exactly like a complete one — same type, same
magnitude order, no marker distinguishing it. Coverage is now a required input rather than a
warning: an aggregate that claims a whole window must prove the window is covered, and one
that cannot has to rename itself.

---

## 2. Coverage inventory (Part A)

Classified from **raw bytes**, before any normalisation, across all six retained payloads.

| Raw-field state | Rows |
|---|---|
| `present_numeric` | **38** |
| `present_zero` | 0 |
| `present_null` | 0 |
| `field_omitted` | **28** |
| `malformed` | 0 |
| `row_missing` | 0 |

| Window | Ticker | Requested | Usable | Ratio | Coverage state |
|---|---|---|---|---|---|
| W1 share event | HPG | 12 | 7 | 0.583 | `partial_known` |
| W2 cash dividend | VCB | 11 | 6 | 0.545 | `partial_known` |
| W3 cash dividend | VNM | 11 | 6 | 0.545 | `partial_known` |
| W4 control + re-observation | HPG | 9 | 9 | 1.000 | `complete` |
| W5 control | VNM | 10 | 10 | 1.000 | `complete` |
| W6 divergence probe | VCB | 13 | 0 | 0.000 | `absent` |

Artifacts (hash-verified on read, unchanged): `044530e72b66bae7`, `adc500119401d92e`,
`c0a096ae295d2687`, `93c2387123dc9fbd`, `b021c258c7226835`, `ad9a7e9c7c657683`.

Every absence in the retained evidence is a **`field_omitted`** — the provider never sent
the key. There are no nulls, no zeros, no malformed values and no missing rows. Row presence
was checked against an independent session list (`vn_stock.db:ohlcv[source=VCI]`, read-only,
named in the artifact) purely to detect a dropped row; it never supplies a value.

### Normalized-field behaviour, which is a different fact

The `vnstock` adapter drops `va` for **every** row regardless of what the provider sent
(`get_all=False`). So a normalized absence is evidence about our configuration, not about
KBS. `row_coverage` carries `normalized_field_present` separately and
`raw_state_is_not_normalized_state` is asserted on every record.

### A defect found and fixed

`parse_daily_payload` could not distinguish `field_omitted` from `present_null` — both went
through `item.get("va")` to `None`. It also aborted the entire payload on a malformed `va`,
discarding perfectly good OHLC. Both are fixed: the state is decided first and the value is
read from it, so a defect in one optional field is now recorded rather than fatal, and the
four kinds of "no number" stay apart.

---

## 3. Coverage contract (Part B)

**Row level** — `trading_value_field_state`, `trading_value_observed`,
`trading_value_value`, `trading_value_unit`, `trading_value_qualification`,
`trading_value_usable_for_row_statistics`, `exclusion_reason`, plus
`normalized_field_present`.

`present_zero` is **usable**. A session that genuinely traded nothing is a measurement, and
excluding it would bias every mean upward while looking like prudence.

**Window level** — the six state counts, `requested_session_count`, `returned_row_count`,
`usable_count`, `coverage_ratio`, `missing_sessions`, `excluded_sessions`, `coverage_state`
∈ {`complete`, `partial_known`, `absent`, `conflicted`, `unknown`}. Deterministic: the ratio
and the serialised record are invariant under input row order.

**Dataset level** —

```
coverage_generalization         = limited_to_retained_windows
causal_explanation              = unknown
automatic_imputation_authorized = false      (constant, no input flips it)
missing_as_zero_authorized      = false      (constant)
cross_window_comparability      = limited
```

`limited`, not `qualified`: two windows are complete, three partial and one absent, so
comparing across them compares different amounts of observation.

---

## 4. The observed association, and what it is not (Part G)

```
observed_association = va_missing_on_tested_empirically_adjusted_rows
sessions_observed    = 66      exceptions_observed = 0
causal_explanation   = unknown
provider_methodology = unknown
coverage_generalization = limited_to_retained_windows
```

The association is perfect across 66 sessions, which is exactly why it needs a guard rather
than a paragraph — a perfect correlation is the most tempting thing in the world to explain.
Nothing observed distinguishes a provider that removes `va` when it adjusts, from two fields
sourced independently that happen to align, from any other arrangement.

**Corrections made in active source:**

| Location | Was | Now |
|---|---|---|
| `kbs_capability_matrix.py` | "the provider omits it exactly where it restated prices" | association wording + a pointer to the enforcing module |
| `docs/kbs_empirical_basis_qualification.md` | "presence tracks the boundary" | "presence is associated with the boundary"; mechanism unknown |
| `tools/run_kbs_empirical_basis.py` | "presence tracks the ex-right boundary" | "presence is associated with the ex-right boundary" |

**Frozen artifacts are not edited.** `KBS_EMPIRICAL_BASIS.md`, `capability_matrix.json`,
`basis_summary.json` and `kbs_superseded_verdicts.json` keep their wording; the correction is
recorded in `CORRECTED_CAUSAL_FRAMING` with `measurements_changed: false` and
`artifacts_rewritten: false`. Test 12b asserts the frozen report still contains its original
sentence, and re-runs the whole audit over active source so a regression fails the suite.

---

## 5. Aggregation rules (Part D)

| Class | Operations |
|---|---|
| `row_level_only` | display observed value, row implied average price, chart with gaps, presence-anomaly detection, coverage report |
| `partial_permitted_when_labelled` | average, rolling, dispersion, value/volume ratio, overlapping-session research comparison |
| `requires_complete_coverage` | period total, turnover for period, growth, cross-period comparison, `va`-based technical indicator |
| `unavailable_by_contract` | official market turnover, official VWAP, negotiated-vs-matched decomposition, liquidity metric, capacity metric, market impact, cross-ticker ranking, synthesis from price × volume |

A partial result must carry `statistic_scope = observed_rows_only`, `coverage_state`,
`covered_sessions`, `excluded_sessions` and
`not_comparable_to_complete_period_total = true`, plus its warning. `build_result` is the
only constructor, so the number and its metadata are made in the same call — there is no
path that produces one without the other.

**The relabelling that matters is blocked by arithmetic, not by a flag.** Flipping
`coverage_state` to `complete` *and* `statistic_scope` to `complete_window` together passes
every individual field check. `assert_result_labelled` now validates the claimed state
against the counts the result carries: a result reporting 2 covered of 3 requested cannot
call itself complete, and a complete result cannot carry excluded sessions.

---

## 6. No synthesis (Part E)

`va` is absent on exactly the rows whose retained price is an *empirically adjusted* price.
So price × volume there is not a restated turnover and not a historical one — it is the
product of a number the provider restated and a number it did not, whose meaning nobody has
established.

No such field is implemented. The identity is reserved and defined as forbidden:

```
kbs.reconstructed_price_times_volume
  source_field                     = derived
  provider_observed_trading_value  = false
  historical_interpretation        = unsupported
  implemented = false   authorized = false
```

`assert_no_synthetic_trading_value` refuses a derived value written into an observed field,
any `imputed` / `filled_from_price_times_volume` marker, and any attempt to mark the
reconstructed field as provider-observed or authorized. `impute()` exists only so the
refusal has an address. **No existing consumer creates such a field**, so nothing had to be
disabled or relabelled.

The unit work proved `va / v` lands inside the session range. That validated the *unit*; it
is not a licence to run the identity backwards.

---

## 7. Consumer and export gates (Part F)

Seven consumers classified. `opportunity_ranking.turnover_rank` and
`risk_liquidity.turnover_liquidity` are `unavailable_by_contract`; passthroughs are
row-level; `candlestick_patterns.gtgd20_ty_calc` and `stock_analyzer.turnover_features` are
partial-permitted with labels. An unregistered consumer is refused.

- **Legacy payloads fail closed for aggregates.** A payload with no `coverage_state` block
  cannot underwrite a window claim, because "no coverage block" and "full coverage" are
  indistinguishable in it and the safe reading is the pessimistic one. Row-level display
  still works — the numbers in it are real.
- **A consumer may narrow coverage, never widen it.** `assert_consumer_did_not_upgrade`
  refuses both a raised `coverage_state` and a raised `usable_count`.
- **Generic fields do not inherit.** `value`, `trading_value`, `turnover`,
  `market_turnover`, `total_value`, `official_market_turnover`, `exchange_turnover` all
  raise. Other providers raise.

---

## 8. Capability effects (Part E of the directive)

**Nothing regressed.** All 15 descriptive and technical capabilities remain available,
verified by tests 17–18: OHLCV display, historical chart, descriptive price/volume/value
statistics, relative volume, price momentum, anomaly detection, cross-provider
corroboration, moving average, RSI, MACD, Bollinger Bands, technical-pattern research,
shadow analytics. Conditional provider-series returns unchanged.

Unavailable, unchanged: official turnover and VWAP claims, liquidity and execution metrics,
market impact, cross-ticker ranking on incomplete `va`, point-in-time valuation, production
backtesting. `volume_market_scope` stays `unknown`; `liquidity_actionable` stays false;
`is_actionable` is untouched.

Trading-value coverage qualifies **coverage**. It does not qualify market scope and does not
unlock liquidity — asserted by tests 15 and 16.

---

## 9. Validation

| Suite | Tests |
|---|---|
| `test_kbs_trading_value_coverage.py` (new) | 26 |
| Basis, mutability, capability and Producer-gate sweep (15 suites, incl. the 26 above) | 420 |
| Consumer readiness and pass-through (4 suites) | 22 |
| **Total** | **442** |

Network-free proof: zero requests; the coverage module's parsed import graph is exactly
`{__future__, typing, evidence_qualification_tiers, kbs_empirical_basis}` — no `requests`,
`urllib`, `http`, `socket`, `sqlite3` or `subprocess`.

Evidence integrity: all six raw payload hashes re-verified against
`evidence_manifest.json` on every inventory build and in test 23b. Replay deterministic —
test 23 rebuilds every window from raw bytes and matches the recorded inventory field by
field.

---

## 10. Non-effects

No network request. No production database write, bundle or dashboard publication. No change
to rankings, recommendations, sizing, liquidity outputs, point-in-time valuation,
backtesting or `is_actionable`. The KBS price/unit/mutability contract from `800c746` is
preserved unchanged; the VCI verdict is untouched; the prospective mutability protocol is
unmodified.

```
KBS_TRADING_VALUE_COVERAGE: PASS
```
