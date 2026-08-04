# KBS empirical price-and-volume basis qualification

**Date:** 2026-08-04 · **Provider:** KBS · **Source authority:** `observed_public_web_endpoint`
**Endpoint:** `GET https://kbbuddywts.kbsec.com.vn/iis-server/investment/stocks/{symbol}/data_day?sdate=DD-MM-YYYY&edate=DD-MM-YYYY`
**Requests issued:** 6 of a budget of 6 · **Tickers:** HPG, VNM, VCB · **Failures:** none

---

## 1. What changed, and what did not

Phase 1C (`operations-review/phase_1c_kbs_ohlcv_semantics_20260801T081200Z.md`) established
that KBS publishes no adjustment flag, no unit declaration and no trade-method metadata,
and that neither the provider nor the `vnstock` adapter certifies any of it. **That finding
is re-confirmed here**, against six freshly retrieved payloads: the response carries
`t/o/h/l/c/v/va` and nothing else.

What is superseded is the inference drawn from it — that the fields were therefore
unusable, and that every consumer must fail closed. Absence of documentation is a fact
about the provider's publishing, not about the numbers. The prior verdict is retained in
`provider_price_basis_registry._SUPERSEDED` under `phase1c_kbs_fields_unusable`, correct
for the proposition it actually established.

| Dimension | Before | After |
|---|---|---|
| `documented_semantics` | absent | absent (unchanged) |
| `field_identity` | treated as unusable | qualified |
| `empirical_semantics` | — | partially available |
| `descriptive_capability` | blocked | available |
| `technical_capability` | blocked | provider-scoped available |
| `liquidity_capability` | blocked | unavailable **by contract** |
| `is_actionable` | false | false (unchanged) |

---

## 2. Field identity and transformations

Raw provider fields, none of which carries a basis, unit or scope declaration:

| Raw | Identity | Normalised (this lane) | Repository/adapter transformation |
|---|---|---|---|
| `t` | session timestamp label | `kbs.session_date` | leading calendar date; clock component discarded, never read as an instant |
| `o` `h` `l` `c` | session open/high/low/close | `kbs.observed_*_vnd` | identity scale here. `vnstock` divides by 1000 and rounds to 2dp; `vn_stock_pipeline` multiplies by 1000 again |
| `v` | session volume count | `kbs.observed_daily_volume` | passthrough, nulls preserved. `vnstock` casts to int64 |
| `va` | session traded amount | `kbs.observed_daily_trading_value` | passthrough, nulls preserved. **`vnstock` 4.0.4 drops it** unless `get_all=True` |

Two corrections to the Phase 1C transformation map: `va` maps to `va`, not to `value`
(`_OHLC_MAP` has no `va` entry in the installed 4.0.4), and the `t` label is now returned
as `YYYY-MM-DD HH:MM`, not a bare date.

The `va` drop is why this lane goes to the raw payload rather than through the adapter: the
field carrying most of the unit evidence never reaches the pipeline.

---

## 3. Price basis

### Method

A HOSE order can only match at a tick multiple (10 / 50 / 100 VND by price band). A session
carrying an off-lattice price was therefore not quoted as displayed. That is a deductive
exclusion and needs nothing the provider declines to publish. The adjustment *dimension* is
then read off which qualified event kinds sit at the boundary between the off-lattice
prefix and the on-lattice suffix. **Event dates are inputs, never inferred from price.**

### Windows

| Window | Ticker | Range | Sessions | Off-lattice | Boundary | Verdict |
|---|---|---|---|---|---|---|
| W1 share event | HPG | 2026-05-18…06-02 | 12 | 5 | **2026-05-25** | `share_event_adjusted_observed` |
| W2 cash dividend | VCB | 2026-07-16…07-30 | 11 | 5 | **2026-07-23** | `cash_distribution_adjusted_observed` |
| W3 cash dividend | VNM | 2026-06-19…07-03 | 11 | 5 | **2026-06-26** | `cash_distribution_adjusted_observed` |
| W4 control + re-observation | HPG | 2026-07-20…07-30 | 9 | 0 | — | `inconclusive` |
| W5 control | VNM | 2026-07-20…07-31 | 10 | 0 | — | `inconclusive` |
| W6 divergence probe | VCB | 2026-07-01…07-17 | 13 | 13 | — | `inconclusive` |

Each boundary lands exactly on a separately recorded ex-right date:

- HPG `ISS` share issue, stock dividend 10%, ex 2026-05-25 — `corporate_event_records` `31135d0d…`
- VCB `DIV` cash dividend 450 VND, ex 2026-07-23 — `corporate_event_records` `11ff5ae3…`
- VNM `DIV` cash dividend 1,850 VND, ex 2026-06-26 — `corporate_event_records` `618ede7b…`

### The second, independent signal

**`va` is absent over exactly the off-lattice runs and present over exactly the on-lattice
ones — in all six windows, 66 sessions, zero exceptions.** Nothing in the lattice test looks
at `va`, and nothing about `va`'s presence looks at price values.

This also disposes of the retention hypothesis. If `va` were simply dropped for older data,
its presence would track the calendar. It does not: HPG 2026-07-20…30 carries `va`, while
the *later-dated* VCB 2026-07-16…17 does not. Presence tracks the ex-right boundary.

### Historical mutability

The W4 window reproduces the exact range of `operations-review/kbs_ohlcv_sample_hpg.json`
(retrieved 2026-08-01T01:11:52Z). Re-requested 2026-08-04T06:58:05Z: **9 sessions compared,
0 changed** in close, volume or trading value.

This is a **control**, not an immutability proof — no ex-right date falls inside it, so
`historical_mutability = not_observed`. The series is demonstrably restated at event
boundaries; what is absent is a rewrite test that *spans* one.

### Verdict

```
price_basis                   = empirically_event_adjusted
price_basis_qualification     = empirically_deduced
historical_mutability         = not_observed
observed_adjustment_dimensions= cash_distribution, share_related_event
provider_methodology          = unknown
coverage_generalization       = limited_to_tested_windows
raw_as_traded_eligible        = false
official_exchange_price       = false
confidence                    = moderate
```

### Rejected alternative explanations

- *Coincidental rounding of an as-traded price.* Rejected: the off-lattice runs are
  contiguous and terminate exactly at a qualified ex-right date, and `va` disappears over
  exactly the same runs.
- *An unqualified event nobody recorded.* Not excluded for any single window. Weakened by
  three windows across three tickers each matching a separately recorded event of the
  expected kind, and by two control windows producing no boundary.
- *`va` retention policy.* Rejected — see above.
- *Cross-provider equality means shared upstream, not independent agreement.* Not excluded.
  The comparison is therefore recorded as corroboration with **no authority effect**.

---

## 4. Volume and trading-value units

### What the test can and cannot constrain

`implied_average_price = (va × va_scale) / (v × v_scale)` depends only on the **quotient**
of the two scales. `(1, 1)` and `(1000, 1000)` predict the identical implied price for every
session that will ever exist. Treating the price-range test as if it selected both scales
would have been this milestone's easiest overclaim, so the quotient is named as its own
result and the absolute anchor is earned separately.

### Sample and outcome

- 66 sessions retrieved; 38 eligible (both `v` and `va` present and non-zero)
- 36 discriminating rows across **three** tickers at three price levels (~21k, ~55k, ~58k VND)
- 2 rows (5.26%, under the 10% ceiling) explained by **no** candidate — retained verbatim
- Surviving quotient: **1.0**, uniquely. All 14 competing quotients rejected outright.

### Breaking the degeneracy

`(1000, 1000)` implies HPG traded 27,485,500,000 shares on 2026-05-18 against a retained
issued-share count of 8,442,964,520 — 3.3× the entire company, past a deliberately loose
2× ceiling.

The share count (`vn_stock.db:metadata[HPG].shares_outstanding`, updated 2026-07-30) is
**not qualified for valuation and is not qualified by this milestone**. It is admissible
here because the tie it breaks is a factor of one thousand: the argument survives the figure
being wrong by any factor short of the one it rejects. It is a falsifier, not a measurement.

### Verdict

```
volume_unit               = shares            qualification = empirically_deduced
trading_value_unit        = VND               qualification = empirically_deduced
scale_quotient            = 1.0 (VND per share)
mean |implied − range midpoint| = 83.9 VND across 36 rows
per-ticker: HPG 15/15 · VNM 15/15 · VCB 6/6, all inside range independently
```

### The two contradictions, retained not resolved

| Session | Range | `v` | `va` | Implied | Most likely reading |
|---|---|---|---|---|---|
| HPG 2026-06-01 | 23,950–24,150 | 9,668,300 | 608,131,155,000 | 62,899 | `va` is **byte-identical to 2026-06-02's** — a stale or duplicated payload value |
| VNM 2026-07-31 | 60,100–61,300 | 4,479,800 | 384,777,740,000 | 85,892 | unresolved; consistent with `va` covering trades the OHLC range does not represent, or with `v` and `va` having different market scopes |

Neither row discriminates between candidate scales — each rejects all sixteen identically —
so neither votes on the unit question. The VNM row is exactly the kind of observation that
would *motivate* a market-scope investigation and cannot *settle* one: it is a single
observation with no confounder eliminated.

---

## 5. Volume adjustment

```
volume_adjustment_basis = not_observed
derived_from_price_adjustment = false
```

The only as-of pair available (W4, 9 sessions) spans no share event, and a control window
cannot demonstrate that a share event would leave volume alone.

**A separate result was obtained, and it is not the same claim.** On W6 (VCB 2026-07-01…17
— the exact 13 sessions the VCI lane proved were rewritten after the 2026-07-23 ex-date):

- all 13 KBS closes are off-lattice, and match the locally stored VCI rows **0/13**
- all 13 KBS volumes match those same stored rows **13/13, exactly**

The stored rows were written by daily runs before the ex-date, and the pipeline appends
rather than rewriting history. So within one provider, on one set of rows: **price restated,
volume not.** That demonstrates the two fields are restated on different schedules. It says
nothing about what a *share* event does to a volume, which is the open question.

---

## 6. Market scope — every dimension unknown, and why none was forced

| Dimension | Verdict |
|---|---|
| `continuous_matching_inclusion` | unknown |
| `opening_auction_inclusion` | unknown |
| `closing_auction_inclusion` | unknown |
| `negotiated_trade_inclusion` | unknown |
| `odd_lot_inclusion` | unknown |
| `total_exchange_volume_equivalence` | unknown |

```
volume_market_scope  = unknown
liquidity_actionable = false
```

Upgrading a dimension requires **at least two** admissible independent observations, each
with every one of `unit_mismatch`, `partial_day_data`, `delayed_update`, `pagination_limit`,
`revised_figures`, `ticker_or_date_mismatch` explicitly eliminated. Admissible evidence is a
retained official exchange total, separately labelled provider fields with a demonstrated
relationship, a complete intraday reconciliation, or another reproducible independent
observation. **Secondary financial websites and media reports are counted and never
qualify.**

Zero admissible observations exist for KBS. The VNM 2026-07-31 anomaly is one observation
with no confounder eliminated, which is precisely the case the rule exists to refuse.

Note that the unit result does *not* touch this. A share count that reconciles against a
traded amount reconciles identically whether the underlying figure counts matched orders
only or matched plus negotiated blocks. `assert_unit_does_not_qualify_scope` enforces it.

---

## 7. Capability matrix

**Available** under existing freshness/schema/provenance gates, all provider-namespaced and
all carrying the seven required warnings and seven provenance fields:

*Descriptive* — OHLCV display, historical chart, descriptive price statistics, descriptive
volume statistics, descriptive trading-value statistics (which must state its own coverage,
since `va` is present on only part of the history), provider-scoped relative volume,
provider-scoped price momentum, anomaly detection, cross-provider corroboration.

*Technical* — moving average, RSI, MACD, Bollinger Bands, technical-pattern research,
shadow analytics.

**Conditional**, available only with `return_type = provider_series_return` attached, and
raising on `raw_as_traded_return`, `official_exchange_return` or `total_shareholder_return`:
provider-series return, provider-series technical continuity. Corporate-action factors may
not be reapplied to the already-adjusted series without a compatible contract; none exists.

**Shadow-only eligibility, defined and not implemented.** Eight conditions, all required
together. No backtest is implemented by this milestone.

**Unavailable by contract** — no input opens these:

- *market composition not qualified*: days-to-liquidate, market impact, liquidity-adjusted
  sizing, negotiated-flow analysis, odd-lot analysis, liquidity-dependent ranking,
  volume-derived actionability upgrade, participation-rate sizing, executable-capacity
  claims, production backtest
- *provider-restated series*: point-in-time valuation, official exchange price claims,
  official total-return claims

An unregistered capability or consumer resolves to `unknown_or_ambiguous` and is refused.

---

## 8. Scope, and where the verdict stops

- Three tickers, all HOSE, all 2026. Older history, rights issues, par-value changes and
  other exchanges are untested.
- No first-party methodology exists, so which events the provider adjusts for — and which
  it silently does not — is unknown.
- The rewrite comparison spans no qualified share event.
- The verdict is KBS's alone. `assert_no_provider_inheritance` and
  `assert_no_generic_field_upgrade` refuse to let it travel to another provider or to a
  field that does not say whose number it is.
- An empirical deduction never becomes a documented one.
  `may_claim_official_semantics(empirically_deduced)` is false.

---

## 9. Evidence

Manifest: `evidence_manifest.json` (`manifest_sha256` covers all six entries).
Raw payloads under `raw/`, preserved verbatim and hash-addressed:

| Artifact | Ticker | Window | SHA-256 (16) |
|---|---|---|---|
| `kbs_daily_HPG_20260804T065801Z_044530e72b66bae7.raw.json` | HPG | W1 | `044530e72b66bae7` |
| `kbs_daily_VCB_20260804T065802Z_adc500119401d92e.raw.json` | VCB | W2 | `adc500119401d92e` |
| `kbs_daily_VNM_20260804T065804Z_c0a096ae295d2687.raw.json` | VNM | W3 | `c0a096ae295d2687` |
| `kbs_daily_HPG_20260804T065805Z_93c2387123dc9fbd.raw.json` | HPG | W4 | `93c2387123dc9fbd` |
| `kbs_daily_VNM_20260804T065806Z_b021c258c7226835.raw.json` | VNM | W5 | `b021c258c7226835` |
| `kbs_daily_VCB_20260804T065808Z_ad9a7e9c7c657683.raw.json` | VCB | W6 | `ad9a7e9c7c657683` |

Replay: `kbs_empirical_basis.replay()` verifies each artifact's hash before parsing and
returns a stable `replay_fingerprint`. It touches no clock, no network and no database.
Re-run with `python tools/run_kbs_empirical_basis.py --offline`.

---

## 10. Non-effects

No production database write. No bundle or dashboard publication. No change to official
exchange fields, liquidity outputs, sizing, rankings, recommendations, point-in-time
valuation or production backtesting. `is_actionable` is unchanged and no verdict here can
raise it. The VCI verdict is untouched. The Phase 1C report is retained unedited.

```
KBS_EMPIRICAL_BASIS: PARTIAL
```
