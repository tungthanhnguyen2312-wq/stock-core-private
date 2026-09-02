# Analytics and Decision Feature Spec

> Product feature layout for the 2026-09-02 core-analytical-product rebaseline.
> Operational state remains `docs/STATE.md`. Sequencing remains `docs/ROADMAP.md`.
> Execution state remains `docs/ROADMAP_STATE.json`. Doctrine remains
> `docs/DATA_FIRST_DOCTRINE.md`. This spec must not silently redefine any of them.

**Status:** APPLIED as layout. Milestone 1 COMPLETE. Milestones 2–3 queued, not started.
**Mode:** Current Research / Product Mode, not Audit / PIT / Exact Mode.
**Expansion rule:** PRODUCT-CRITICAL FEATURE EXPANSION ONLY. Not a feature freeze.
**Scoring:** No universal scoring system is required. Threshold values are not data authority.
**UI:** Frozen until `INTEGRATED_INVESTMENT_DECISION_PRODUCT_V1`.

Near-term implementation order:

1. `CORE_FUNDAMENTAL_VALUATION_AND_PEER_CONTEXT_V1` — COMPLETE / COHERENT_PARTIAL_BY_RETAINED_EVIDENCE (checkpoint `5e58d79f69810d6800d1f58244c421acb0e4230f`, closeout `14cc93ccc5cec97c1de865b69eba958f5f18ee7a`)
2. `TACTICAL_MARKET_STRUCTURE_AND_BREAKOUT_V3` — QUEUED_NEXT, not started
3. `INTEGRATED_INVESTMENT_DECISION_PRODUCT_V1` — QUEUED_AFTER_TACTICAL, not started

Queued does not mean started. Do not start a later milestone merely because the
current one is ready.

---

## 1. Purpose

Stock Lookup’s Current Research product should let a human see, for a Vietnamese
listed equity:

- what the business is doing (fundamentals);
- how the market is pricing it versus peers and its own history (valuation);
- where price/volume/structure sit (tactical market structure);
- what would confirm or invalidate a setup;
- how that interacts with an explicit portfolio;
- what happened after prior comparable decisions (prospective feedback).

The product begins from retained evidence and deterministic engines. It does not
begin from a score, a rank, a target price, a probability, or a dashboard widget.

---

## 2. Modes and fitness

### 2.1 Two modes

| Mode | Allowed when | Blocked from |
|---|---|---|
| **Current Research / Product Mode** | Method, provenance, fitness, and limitations are explicit | Silent promotion to official, PIT, audit, sizing, or execution authority |
| **Audit / PIT / Exact Mode** | Required identities, timestamps, units, and official/PIT contracts qualify | Any proxy, mixed-unit, or unresolved-basis path |

Missing audit-grade authority blocks **only** the dependent exact use. It does
not globally disable unrelated Current Research features.

### 2.2 Proxies

Provider/research proxies may be used in Current Research when all of the
following are explicit on the emitted record:

- method id;
- provider/source identity;
- period/scope;
- fitness (`READY` / `RESEARCH_PROXY` / `BLOCKED_BY_EVIDENCE` / `NOT_APPLICABLE` / equivalent);
- limitations/warnings;
- incompatibility with exact use.

A fallback is a separately named `DERIVED_PROXY`, never an exact canonical metric
(`docs/AI_RULES.md` rule 10).

### 2.3 Units

Never invent monetary scale. Never invent unit compatibility. Never mix clearly
incompatible units, currencies, share bases, duration semantics, or statement
scopes in one ratio. A ratio constrains only the ratio. Absolute monetary terms
require an independent qualified anchor. Never invent PIT authority or execution
authority.

### 2.4 Layering

| Layer | Owns | Must not own |
|---|---|---|
| **Feature engine** | Measurements, identities, fitness, lineage, blockers | Buy/hold/avoid policy, numeric entry/exit thresholds as investment rules, scores |
| **Strategy layer** | Thresholds, policy, confirmation/invalidation rules, research-stance mapping | Recalculating measurements, dropping required warnings, widening fitness |

Threshold values are policy, not data authority.

### 2.5 Peers

Peer comparisons require comparable metric method, provider, and scope. Also
required, where already governed: same entity-class applicability, same
share-basis class, and same period/method identity. Existing
`current_research_valuation_context.attach_peer_relative` already requires
`MIN_COHORT_MEMBERS=5` and same-method keys. Milestone 1 added
`attach_engine_fundamental_peers` with the same compatibility gate over
headline ratios. Do not compare a READY same-provider margin to a mixed-provider
proxy, or a P/E on one share basis to a P/E on another.

### 2.6 Non-goals for this rebaseline

Do not open, as standalone milestones, unless they directly block one of the
three product milestones:

- Interest Coverage;
- Insurance specialist family;
- forensic accounting;
- monetary-basis as a standalone program;
- VCI-duration as a standalone program;
- absolute-liquidity / ADV20 / execution-capacity authority;
- further specialist micro-milestones.

Do not build a universal score, rank, target price, or probability surface.

---

## 3. Existing governed inputs (do not re-derive as if absent)

This spec consumes already-recorded capabilities. Counts below are historical
closeout facts, not a license to freeze those exact numbers forever.

### 3.1 Fundamental

- `financial_analysis_engine_v2.py` / `financial_analysis_context/v2`:
  net/PBT/gross margins, standalone-quarter and TTM growth, cash-flow sign and
  CFO-to-earnings, `free_cash_flow_proxy`, equity/cash/debt ratios, working
  capital / current ratio, same-provider ROA/ROE feature ids, mixed-provider
  ROA/turnover proxies, bank specialist family, securities specialist family.
- Milestone 1 added `same_provider_roe_avg_equity` / `same_provider_roa_avg_assets`
  (average of a quarter’s own beginning and ending same-provider balances,
  distinct from unmodified EOP proxies) plus per-ticker `history_context`.
- `market_wide_fundamental_feature_store/v1`: dimensionless same-native-series
  research proxies and P-I-T trajectories; not official authority.
- Documented limits: same-provider ROA/ROE READY remains rare because of the
  KBS-income / VCI-balance-sheet split; mixed-provider ROA is `RESEARCH_PROXY`;
  `VCI_PERIOD_DURATION_REMAINS_UNKNOWN`; FCF is a provider-native signed proxy,
  not authoritative free cash flow.

### 3.2 Valuation and peer context

- `current_research_valuation_context.py`: method-level `P/E_TTM`, `P/S_TTM`,
  `P/B`, `P/E`, `P/S`, `EV/EBITDA`, `EV/Sales`; entity-class applicability;
  explicit share-basis class; same-method peer percentile; milestone 1
  `attach_engine_fundamental_peers`.
- `QUALIFIED_TTM_VALUATION_RESEARCH_INTEGRATION_V1` prefers Financial V2 READY
  TTM over Feature Store TTM and never merges sources.
- Monetary-basis recovery: unresolved currency/scale blocks exact TTM/market-cap
  ratios (`TTM_MARKET_CAP_MONETARY_BASIS_INCOMPATIBLE`). Current Research may
  use a labelled proxy only with method, provenance, fitness, and limitations
  explicit. Never invent a scale.
- Implied reverse-DCF remains unavailable. Reverse-valuation intrinsic outputs
  remain a blocked capability.

### 3.3 Tactical / market structure

- Primary: unmodified nine-state `watchlist_tactical_entry_classifier.entry_state`.
- Secondary V2: `technical_structure_context.py` (close-only structure,
  contraction, breakout facts; `HIGH_LOW_BASIS_NOT_COMPATIBLE` blocks true ATR
  and Donchian), `tactical_setup_tags.py` (including relative-strength leader/
  laggard, sector leading/weakening, breakout failure, range compression),
  `tactical_confirmation_invalidation_boundaries.py`,
  `tactical_behavior_context.py`.
- V2 closeout: no universal RSI/ADX/MACD/relative-volume-multiplier gate.
- `MARKET_WIDE_RELATIVE_VOLUME_RESEARCH_V1`: same-provider dimensionless
  percentile and current/median-prior-20 acceleration; DNSE OHLC `v` native
  absolute unit remains UNKNOWN; not liquidity authority.
- Market/sector breadth and relative strength already exist in
  `market_wide_current_descriptive_research` and
  `current_market_sector_leadership_context`.
- Legacy `candle_scan.py` / `vn_indicators.py` / `stock_analyzer.py` BOS/CHoCH/SMC
  scoring is **not** governed product authority.

### 3.4 Decision, portfolio, feedback

- `opportunity_context/v1`, `security_decision_context/v1`,
  `investment_decision_workspace_projection/v1`,
  `screener_master_projection/v1`.
- Portfolio availability is separate from security attractiveness
  (`RESEARCH_LIQUIDITY_AND_EXPLICIT_PORTFOLIO_V1`).
- `prospective_decision_outcome/v1`: session-counted T+5/T+20/T+60 forward
  close return; close-path favorable/adverse **proxies**; true MFE/MAE =
  `UNAVAILABLE_HIGH_LOW_BASIS`. Real durable store at that closeout: 0 genuine
  non-fixture T0 cases.

Use these. Do not recreate them. Expand only where the product is still missing
a listed capability below.

---

## 4. Milestone 1 — `CORE_FUNDAMENTAL_VALUATION_AND_PEER_CONTEXT_V1`

**COMPLETE / COHERENT_PARTIAL_BY_RETAINED_EVIDENCE.** Do not reopen or regress
this closeout. Remaining gaps below are honest residuals for later product
milestones only if they block Tactical V3 or Integrated Decision.

### 4.1 Fundamental / growth / turnaround / margins / ROE / ROA / DuPont / cash / FCF / leverage / working capital

| Capability | Feature-engine measurement | Strategy-layer policy | Fitness rule |
|---|---|---|---|
| Growth | Same-provider standalone-quarter QoQ, same-quarter YoY, and four-consecutive-quarter TTM growth already in Financial V2 | Whether growth is “improving” as a stance input | No UNKNOWN-duration or cross-provider growth. No four-rows-back inference. |
| Turnaround states | Sign and direction of earnings, margins, and cash-flow series already emitted as IMPROVING/WORSENING/STABLE/UNAVAILABLE | Turnaround language as research context | Do not invent a recovery without a retained prior-period pair. |
| Margins | Gross / PBT / net / TTM net / TTM PBT margins; direction states | Margin expansion/compression as policy input | Same-provider, same-period, same-scope. Negative profit may yield a negative margin. |
| ROE / ROA exact | Milestone 1 `same_provider_roe_avg_equity` / `same_provider_roa_avg_assets` | Quality/peer context at declared fitness | Average of that quarter’s own beginning and ending same-provider balances. Missing beginning balance blocks; do not fall back to EOP. |
| ROE / ROA proxy | Unmodified EOP proxies and mixed-provider ROA/turnover proxies | Use only at declared `RESEARCH_PROXY` fitness | Do not silently upgrade mixed-provider ROA to READY. |
| DuPont | Explicit identity ROE = (NI/Sales) × (Sales/Assets) × (Assets/Equity) only when each component shares method/provider/scope/period semantics | Decomposition as explanation, never as a score | If average-balance is required and prior closing balance is unverified, emit `BLOCKED_BY_EVIDENCE` or a named EOP-proxy DuPont. Do not invent the average. |
| Cash quality | OCF sign, OCF growth, CFO-to-NI, TTM OCF | Cash-quality as evidence lists, not a health score | Same representation gate as Financial V2. |
| FCF | Existing `free_cash_flow_proxy` = OCF + provider-native signed CapEx | Direction as descriptive context | Corporate-only. Preserve native CapEx sign. Not authoritative FCF. |
| Leverage | Debt/equity, debt/assets, directions already in Financial V2 | Leverage as evidence, not a score | No total-liabilities-as-debt substitution. |
| Working capital | Net working capital, current ratio, trajectory states | Liquidity-research context only | Not execution-capacity liquidity. |

Banks, securities, insurance, and finance companies keep entity-class
applicability. Industrial formulas are `NOT_APPLICABLE` there. Existing bank and
securities specialist families stay available as specialist context; this
rebaseline does not add Insurance or Interest Coverage families.

### 4.2 P/E, P/B, P/S, EV multiples and peer/history context

| Capability | Feature-engine measurement | Strategy-layer policy | Fitness rule |
|---|---|---|---|
| P/E | Method-level P/E and P/E-TTM | Cheap/expensive language only against a declared comparable cohort or history | Negative/zero earnings → `PE_NOT_MEANINGFUL`. Do not block P/S merely because P/E is not meaningful. |
| P/S | Method-level P/S and P/S-TTM | Same | Entity-class applicability: industrial EV/P/S contracts do not gate banks/securities. |
| P/B | Method-level P/B | Same | Share-basis class must be explicit. |
| EV family | EV/Sales, EV/EBITDA where entity class applies | Same | Do not force industrial EV onto banks/securities. |
| Peer percentile | Same-method, same-provider-class, same-scope, same-entity-class, same-share-basis cohort; median and tie-aware percentile | Premium/discount as research context | Minimum cohort members remain governed (`MIN_COHORT_MEMBERS=5` unless an owner decision changes it). Incompatible units excluded, never rescaled by magnitude. |
| Own-history context | Milestone 1 same-ticker, same-method trailing distribution over retained compatible observations | Versus own history as research context | No PIT membership claim. Missing history is `INSUFFICIENT_HISTORY`, not zero. |

If TTM and current market cap lack independently known compatible currency/scale,
Current Research may keep the ratio `INPUT_BLOCKED` or emit a separately named
research proxy whose limitations include the unresolved basis. It may **not**
invent a scale.

Implied reverse-DCF / intrinsic value remains out of scope until an upstream
qualified intrinsic envelope exists.

---

## 5. Milestone 2 — `TACTICAL_MARKET_STRUCTURE_AND_BREAKOUT_V3`

QUEUED_NEXT. Not started. Product-critical expansion of governed tactical
measurement. Primary `entry_state` remains unmodified. V3 is secondary evidence,
like V2.

### 5.1 MA / ATR / NATR / RSI / MACD / relative strength

| Capability | Feature-engine measurement | Strategy-layer policy | Fitness rule |
|---|---|---|---|
| MA20 / MA50 / MA100 / MA200 | Close-based moving averages from the same qualified series | Trend policy may use MA relationship | Same retained price series and session identity. Adjusted/retrospective series stay labelled as such. Missing lookback is `INSUFFICIENT_HISTORY`. |
| ATR / NATR | True range / ATR / NATR only from compatible high/low/close | Stops/volatility policy | If `HIGH_LOW_BASIS_NOT_COMPATIBLE`, ATR/NATR stay blocked per record. Close-to-close volatility may exist as a named proxy, never labelled ATR. |
| RSI | RSI from the same qualified close series | Overbought/oversold policy | No universal RSI threshold inside the feature engine. |
| MACD | MACD line / signal / histogram from the same series | Cross/confirmation policy | Same. Feature engine emits values and states; strategy owns thresholds. |
| Relative strength | Market-relative and sector-relative momentum already governed by `current_market_sector_leadership_context` | Leader/laggard policy | Reuse the canonical `(below + 0.5 * equal) / n` percentile. Do not invent a second RS formula. |

### 5.2 Confirmed swings HH / HL / LH / LL, BOS, CHoCH

| Capability | Feature-engine measurement | Strategy-layer policy | Fitness rule |
|---|---|---|---|
| Confirmed swings | Fractal or equivalent swing high/low on a declared lookback, with confirmation lag explicit | Structure-state policy | Prefer compatible high/low. If high/low basis is incompatible, a close-only swing is a named proxy, not a silent substitute. |
| HH / HL / LH / LL | Ordered comparison of confirmed swings | Uptrend/downtrend structure policy | Deterministic; no score. |
| BOS | Break of structure: close (or qualified high/low) through the relevant confirmed swing in the **direction of** the current structure | Continuation policy | Deterministic technical inference. **Not** proof of institutional activity, absorbed liquidity, or order-flow. |
| CHoCH | Change of character: break **against** the current structure | Early-reversal warning policy | Same limitation as BOS. |

Do not import `stock_analyzer.py` scoring, room penalties, or confluence points
as product authority. If `vn_indicators.market_structure` is reused, reuse is
explicit, versioned, and stripped of recommendation language.

### 5.3 Base / VCP / pivot / breakout / failed-breakout

| Capability | Feature-engine measurement | Strategy-layer policy | Fitness rule |
|---|---|---|---|
| Base | Duration + range compression already sketched in V2 `base_context` / `RANGE_COMPRESSION` | Accumulate-in-base policy | Close-only bases remain labelled close-only. |
| VCP | Successive contraction of a declared range or realized-volatility window | VCP setup policy | Deterministic contraction pattern. **Not** proof of institutional absorption. |
| Pivot | Declared pivot price from confirmed swing or base high | Trigger policy | Pivot is a measured level, not a target. |
| Breakout | Session-over-session or close-through-pivot event already in V2 `breakout_context` | Initiate/confirmation policy | Actual trigger state stays distinct from an instrumented boundary (decision-quality corrective pass). |
| Failed breakout | Return back through the breakout level / V2 `BREAKOUT_FAILURE` | Invalidation policy | Descriptive. No implied win rate. |

### 5.4 Participation: relative volume / acceleration / dry-up / OBV / CMF

| Capability | Feature-engine measurement | Strategy-layer policy | Fitness rule |
|---|---|---|---|
| Relative-volume percentile | Existing same-session percentile and cohort-median flag | Elevated-volume policy | Dimensionless. Native `v` unit remains UNKNOWN. Not ADV/ADTV, not execution capacity. |
| 20-session acceleration | Existing current / median-prior-20 | Acceleration policy | Same. Zero baseline stays explicit, not a huge ratio. |
| Volume dry-up | Current volume below a declared self-relative baseline during compression | VCP/base confirmation policy | Strategy owns the dry-up threshold; feature engine owns the measurement and fitness. |
| OBV / CMF | On-balance volume / Chaikin money flow **where the retained series supports them** | Participation confirmation policy | Emit only when volume representation is same-provider and same-native-field. Otherwise `NOT_SUPPORTED` / `BLOCKED_BY_EVIDENCE`. Not liquidity authority. |

### 5.5 Market / sector breadth and relative strength

Reuse `market_wide_current_descriptive_research` and
`current_market_sector_leadership_context`. V3 may add compact per-ticker
packaging; it does not create a second breadth engine. Coverage must remain
visible. Insufficient sector cohorts stay `UNAVAILABLE`.

Market-regime tailwind/headwind remain contemporaneous context, never a gate
that overrides a ticker’s own structure (V2 rule, kept).

### 5.6 Trigger / invalidation

V2 already separates confirmation boundary, actual trigger state, and
technical invalidation. V3 may add structure-aware levels (pivot, BOS, failed
breakout, swing invalidation) as **measurements and candidate boundaries**.
Strategy maps them into research stance. Exact execution stops are not created.
Fixed stop percentages are not created.

---

## 6. Milestone 3 — `INTEGRATED_INVESTMENT_DECISION_PRODUCT_V1`

QUEUED_AFTER_TACTICAL. Not started. Final integration pass. Sole UI/Dashboard
unfreeze.

### 6.1 Join, do not rescore

Join, per ticker, with mixed-session freshness and explicit uncertainty
preserved:

- Milestone 1 fundamental + valuation/peer/history;
- Milestone 2 structure + volume + breadth + trigger/invalidation;
- existing catalyst/downside/liquidity-research-proxy axes;
- explicit portfolio interaction;
- prospective decision feedback when a genuine T0 case exists.

Decision packet axes (descriptive, not a score):

| Axis | Content |
|---|---|
| Market phase | Breadth/regime context already governed; contemporaneous only |
| Fundamental direction | Growth/margin/ROE-ROA/cash/leverage/working-capital states at declared fitness |
| Valuation context | Method-level multiples, peer percentile, own-history; blocked methods stay blocked |
| Participation | Relative volume, acceleration, dry-up, OBV/CMF where supported |
| Trigger | Actual trigger state, distinct from instrumented boundary |
| Invalidation | Retained technical/fundamental invalidation boundaries |
| Portfolio interaction | Availability and fit, never security attractiveness |
| Uncertainty | Missing/blocked/proxy/stale axes named per axis; never zero-filled |

Keep the six-label research-stance machine unless a later owner decision
retunes it. Data READY is not BUY. Missing fundamental evidence still routes
to `INSUFFICIENT_EVIDENCE`, not `HIGH_RISK_SPECULATION_ONLY`, per the
2026-08-31 decision-quality corrective pass.

No universal score, rank, target, or probability.

### 6.2 Portfolio interaction

Portfolio context remains **availability and fit**, never a security-attractiveness
input (`RESEARCH_LIQUIDITY_AND_EXPLICIT_PORTFOLIO_V1`). Emit at least:

- whether an explicit portfolio was provided;
- whether the ticker is already held;
- concentration / policy-breach flags already computable from the explicit
  portfolio contract;
- that exact position sizing and execution capacity stay blocked while
  `QUALIFIED_LIQUIDITY_INPUTS = NO`.

Do not convert research liquidity proxy into ADV20 or GTGD fills.

### 6.3 Forward-return / MFE / MAE / false-negative / false-positive feedback

Product capability, not a backtest:

| Measurement | Allowed now | Blocked now |
|---|---|---|
| `forward_return_5` / `forward_return_20` | Where T0 case is a validated durable envelope and later sessions share compatible price-basis identity; existing engine uses fifth and twentieth **later completed sessions** | Calendar-day horizons; mixed price basis; retroactive cases from workspace exports |
| `forward_return_10` | Product-critical expansion of the same session-counted contract | Not already implemented; do not alias T+5 or T+20 |
| Close-path favorable / adverse proxies | Named research proxies | Labelling them true MFE/MAE |
| True MFE / MAE | Only if high/low basis later qualifies | `UNAVAILABLE_HIGH_LOW_BASIS` today |
| False-negative / false-positive taxonomy | Compare retained T0 stance/trigger/invalidation to later evidence; count N. FN: setup/trigger existed and was not taken or was labelled wait/avoid, then favorable path. FP: initiate/accumulate was labelled and later invalidated or adverse path. | Win-rate authority, threshold retune, probability-of-success field |

The existing governed evaluator also defines T+60. Keep it as an additional
horizon; do not delete it to force a 5/10/20-only schema. Empty genuine T0
coverage is reported as empty, not as a 0% error rate.

Prospective false-negative/false-positive review is a **core product
capability** even while genuine T0 coverage is zero.

---

## 7. UI / Dashboard freeze

Until `INTEGRATED_INVESTMENT_DECISION_PRODUCT_V1` reaches the final integration
pass:

- no new Dashboard page, column set, or interaction redesign;
- Producer may add research artifacts and compact product fields;
- existing Workspace / Screener / publication paths stay frozen except for
  fail-closed bug fixes that do not expand actionability.

The final integration pass may surface the new measurements on existing
primary surfaces. It still must not introduce score, rank, target, probability,
sizing, or execution command.

---

## 8. Acceptance for each product milestone

A product-critical milestone is complete only if:

1. It answers at least one of doctrine §8 questions 4 or 5 (fitness-for-use or
   new deterministic analytical capability from already-qualified data).
2. Every emitted feature carries method, provenance, fitness, and limitations.
3. Blocked exact uses remain blocked; Current Research proxies are named as
   proxies.
4. No universal score is introduced. Thresholds remain policy, not data authority.
5. UI/Dashboard is untouched unless this is milestone 3.
6. Specialist micro-milestones were not opened except as a recorded direct
   blocker of this milestone.
7. Real retained replay reports denominator, zero silent drops, and explicit
   residuals. Do not invent coverage.

---

## 9. Authority boundary (unchanged)

This spec does not promote:

- `RAW_AS_TRADED` or historical PIT;
- exact execution-capacity liquidity or position sizing;
- `ACTIVE_UNIVERSE`;
- official financial-fact authority;
- reverse-valuation intrinsic outputs;
- OCR as a default coverage path;
- a new market-data provider.

Those remain the `docs/ROADMAP_STATE.json` `blocked_capabilities` register and
`docs/STATE.md` Section 3 invariants.
