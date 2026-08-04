# KBS trading-value coverage: export seam and Consumer pass-through

**Date:** 2026-08-04 · **Producer start:** `ee057b9` · **Consumer start:** `66733a4`
**Network requests: 0.** Entirely offline, from retained artifacts and read-only inspection.

---

## 1. Lineage (Phase 1)

Traced end to end before any edit.

| Stage | Carries `va`? |
|---|---|
| Raw KBS payload | **yes** — 38 of 66 retained sessions |
| `vnstock` `KbsQuote.history` | **no** — dropped unless `get_all=True` |
| `vn_stock_pipeline` → `ohlcv` table | **no** — columns are `ticker,date,open,high,low,close,volume,source` |
| `export_ai_bundle.py` | **no** — zero references to `va`, trading value or turnover |
| `analysis_bundle.json` | **no** — `ohlcv_recent` rows are `{date,open,high,low,close,volume}` |
| Consumer bundle loader / context | **no** |

**KBS `va` has never been exported.** There is no active value path, so there is no bare
number that lost its coverage meaning, and no legacy `va` aggregate to quarantine. Per the
directive, no product surface was invented; the narrowest future-safe seam was built instead
and the absence is recorded as data in `ABSENCE_OF_ACTIVE_VALUE_PATH`.

### What the trace *did* find

`gtgd20_ty` is the only trading-value-shaped quantity crossing the boundary:

```python
candlestick_patterns.py:148
df["gtgd20_ty_calc"] = (df["close"] * df["volume"]).rolling(20, min_periods=3).mean() / 1e9
```

It is **derived close × volume**, never reads `va`, and is computed over the stored OHLCV
series — overwhelmingly VCI rows. It reaches `stock_analyzer`, `candle_scan`, `ai_analyzer`
and the Consumer `schema_registry.json`.

**This corrects two errors in the `ee057b9` closeout.** That milestone stated "No existing
consumer creates such a field [price × volume]" — false; `candlestick_patterns` does. And
its `CONSUMER_REQUIREMENTS` listed four `va` consumers, none of which read `va`; two named
concepts that do not exist (`stock_analyzer.turnover_features`,
`export_ai_bundle.trading_value_passthrough`). The register was written from an assumption
and is now written from a trace.

`gtgd20_ty` is **relabelled, not disabled**. It reconstructs no missing `va` — it is an
independent screening metric predating this lane, already classified in
`market_volume_capability_matrix` as analytical-and-explicitly-not-qualified-liquidity.
`NON_VA_DERIVED_QUANTITIES` now records what it is and the three labels it may never carry;
removing a working screen over a naming collision would not have been proportionate.

---

## 2. Producer integration

**Location:** `kbs_trading_value_export.py`. No bundle section added, no schema bumped.

**Block:** `export_block_version`, `provider`, `source_field`, `source_field_identity`,
`trading_value_unit`, `trading_value_unit_qualification`, `coverage` (all 20 keys),
`warning_tokens`, `warnings`. Built by `build_row_block` (single observation) or
`build_window_block` (aggregate) — every count copied from the canonical
`kbs_trading_value_coverage.window_coverage` record, never recomputed.

**Statistic scopes**, one vocabulary shared with Consumer: `single_observed_row`,
`complete_requested_window`, `observed_rows_only`, `not_applicable`. A single row uses the
row form rather than a fabricated one-session window.

**Validation.** `assert_block_valid` checks shape, then labels **against counts** — the
load-bearing check, because every individual field can be well-formed while the block lies.
`complete` beside 2 usable of 3 requested raises; so does `partial_known` with 0 or all rows
usable; so does `complete_requested_window` scope on non-complete coverage. `assert_no_bare_value`
refuses a payload with a value and no coverage block, which is what makes the seam
load-bearing rather than optional.

**Warnings.** Two canonical tokens with one text table and a SHA-256 fingerprint. The
authority token is unconditional; the partial token is *added*, never substituted — a
partial result is both partial and provider-scoped.

**Legacy.** `legacy_row_observation` (explicit row identity → displayable with a provenance
warning, aggregates refused), `legacy_aggregate_without_coverage` (refused entirely),
`legacy_no_trading_value` (unaffected). Absence of metadata resolves to
`coverage_state = unknown` — **never** to complete.

**Determinism.** Repeated builds are byte-identical; the frozen fixture is asserted equal on
both sides.

---

## 3. Consumer integration

**Location:** `builders/kbs_trading_value_coverage_contract.py`, following the repository's
existing `*_contract.py` convention (`CONTRACT_VERSION`, pure module, fail-closed
normalizer).

**Pass-through.** `normalize_trading_value_contract` copies all 20 coverage fields verbatim
and recomputes nothing. A dropped field is an error, not a tolerated absence — asserted for
every required field individually.

**Validation.** `assert_labels_agree_with_counts` compares two things Producer already sent;
it is a corruption check, not a re-derivation. A forged block claiming `complete` over
partial counts is refused at load.

**No upgrade.** `assert_not_upgraded` permits narrowing and refuses widening, on both
`coverage_state` and `usable_count`.

**Warnings preserved.** `assert_warnings_preserved` refuses removal of the authority token,
the partial token, or the incomparability flag. `assert_warnings_pinned` compares the frozen
text fingerprint against Producer's, so an unmirrored Producer edit fails a test rather than
shipping two different warnings for the same condition.

**AI context.** `ai_context_block` labels the field
`kbs_provider_observed_trading_value` with `is_official_market_turnover: False`,
`is_qualified_liquidity_evidence: False`, `supports_market_scope_claim: False`,
`supports_actionability: False` — at *every* coverage state, including complete.

**Legacy.** Same three classes, cross-checked against Producer's classification in the
shared fixture. A bundle with no block resolves to `unknown` and refuses aggregates.

Consumer holds no copy of Producer's capability matrix. It holds a short blocked-claims
list and the pass-through logic; Producer keeps authority.

---

## 4. Capability effects

**Preserved:** single observed value display, coverage reporting, provider-scoped
observed-row statistics, charts with visible gaps, OHLCV display, moving averages, RSI,
MACD, Bollinger Bands, relative volume, price momentum, anomaly detection, cross-provider
corroboration, conditional provider-series returns.

**Blocked, unchanged:** complete-period claims under partial coverage, official turnover,
official VWAP, filling `va` from price × volume, market-scope claims, liquidity and capacity
metrics, days-to-liquidate, market impact, participation and position sizing, cross-ticker
rankings on incomplete `va`, point-in-time valuation, production backtesting,
recommendations, `is_actionable` upgrades.

`volume_market_scope` stays `unknown`. `liquidity_actionable` stays false. `is_actionable`
is untouched.

---

## 5. Schema compatibility

No schema version bumped. The block is additive and no artifact contains one today, so
nothing a current reader parses changes; bumping would signal a break that has not happened.
`compatibility()` records: backward-readable true; a reader without the block treats KBS
trading value as `coverage_state = unknown` and refuses aggregate claims; fails closed when
a value is present and the block absent; `unrelated_schemas_bumped: []`.

---

## 6. Cross-repository validation

| | Tests |
|---|---|
| Producer sweep (16 suites) | **445** |
| — of which new export seam | 25 |
| — of which coverage contract | 26 |
| Consumer sweep (5 suites) | **116** |
| — of which new pass-through | 16 |
| **Total** | **561** |

Frozen fixture `tests/fixtures/kbs_trading_value_export_block.json` is byte-identical in
both repositories and asserted by both: Producer that it still generates exactly this,
Consumer that it can load every field and cannot upgrade the verdict. Warning fingerprint
`1b7dcaba1bc5d019bea6f1de73eab88395337dc6552dfd6038ce3d9eaa8e6a3c` pinned on both sides.

Compile clean in both. No runtime bundle published; no temporary bundle written outside
`operations-review/` and `tests/fixtures/`.

---

## 7. Non-effects

No network request. No production database write, bundle or dashboard publication. No change
to official market fields, liquidity, sizing, rankings, recommendations, point-in-time
valuation, backtesting or `is_actionable`. The KBS price, volume, unit, mutability and
market-scope contracts from `ee057b9` are preserved unchanged; the VCI verdict is untouched;
the prospective mutability protocol is unmodified.

```
KBS_COVERAGE_PASS_THROUGH: PASS
```
