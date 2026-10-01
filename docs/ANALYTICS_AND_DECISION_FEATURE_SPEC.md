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
- Input identity (`financial_v2_semantic_observation_key/v1`, 2026-09-27): engine series
  join on ticker, provider, statement scope, currency, scale and statement family, never on
  `source_file`, which stays provenance on every feature. One series key, metric, period and
  period semantic is one observation: equal repeats collapse deterministically, different
  values drop that period (fail closed). Bridge-qualified quarters keep their operands' own
  source status (a `partial` operand is never engine-READY) and real payload provenance.
  A registry-composed fact (e.g. `total_interest_bearing_debt`) regains lineage only by
  exact component linkage (`exact_component_observation_linkage/v1`).
- Freshness: the Current Research FUNDAMENTAL dimension carries
  `financial_period_freshness/v1` in the `opportunity_axis_freshness` vocabulary. Within
  `MAX_COMPLETED_QUARTER_LAG` it is `CURRENT`; beyond it valid evidence stays
  `STALE_BUT_RESEARCH_USABLE` with its stale metrics named, never dropped or rewritten.
- Peers: a row whose statement scope was never labelled (`unknown`) keeps its own
  research value but never enters a cross-issuer peer cohort
  (`STATEMENT_SCOPE_UNKNOWN_NOT_PEER_COMPARABLE`).

### 3.2 Valuation and peer context

- `current_research_valuation_context.py`: method-level `P/E_TTM`, `P/S_TTM`,
  exact-lane `P/B`, distinct research-only `P/B_CURRENT_RESEARCH`, `P/E`, `P/S`,
  `EV/EBITDA`, `EV/Sales`; entity-class applicability;
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
| P/B | Exact-lane P/B and distinct `P/B_CURRENT_RESEARCH` over pinned VCI balance-sheet equity | Same | Research method requires a typed market-cap basis, non-conflicted VCI point-in-time equity within four completed quarters, explicit share class and NCI limitation; it grants no exact or target-price authority. |
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

### 6.4 Current Research decision input (`current_research_decision_input/v1`)

Added by `CURRENT_RESEARCH_DECISION_CONVERGENCE_V1` (2026-09-27, local, not promoted). Every
Integrated Decision record carries one Producer-owned `current_research_decision_input`: a pure
restatement of that record's own evidence. It computes no indicator, threshold, score, rank,
target or probability, is built after posture/trigger/invalidation, and never enters
`decision_identity`.

| Dimension | AVAILABLE when | Authority tier |
|---|---|---|
| MARKET | Exact-session bar retained for the decision session | `CURRENT_DESCRIPTIVE_ONLY` (RAW_AS_TRADED not promoted; PIT blocked) |
| TECHNICAL | Current-session tactical structure eligible (trend, momentum, relative strength, BOS/CHoCH, participation, trigger, invalidation as components) | `RESEARCH_QUALIFIED` deterministic inference |
| FUNDAMENTAL | Financial V2 direction, or the operational bridge where V2 is insufficient | `RESEARCH_QUALIFIED` (V2 READY) or `RESEARCH_PROXY` |
| VALUATION | At least one usable relative multiple or a producer peer-relative verdict | `EXACT_QUALIFIED` (READY method) or `RESEARCH_PROXY` |
| CORPORATE | Corporate-intelligence context evaluated (`PARTIAL` when its evidence session is stale) | `RESEARCH_QUALIFIED` |
| LIQUIDITY | Same-session descriptive liquidity research eligible; execution stays a separate sub-state | `CURRENT_DESCRIPTIVE_ONLY`; execution `NONE` |

States are `AVAILABLE` / `PARTIAL` / `BLOCKED` / `NON_APPLICABLE`, each with machine reason
codes. Rules that are not negotiable:

- **Market capitalisation is size context, never valuation.** A record whose only usable method is
  market cap has valuation `PARTIAL` (`SIZE_CONTEXT_ONLY`) and the Integrated Decision valuation
  summary is `UNAVAILABLE` with its causes named. A P/E that is not meaningful (negative/zero
  earnings) is `PARTIAL`, not a usable factor.
- **Readiness-engine multiples are single-period ratios.** `EV/EBITDA_CALC_READY` divides by one
  reporting period's EBITDA (never annualised); it is labelled
  `SINGLE_REPORTING_PERIOD_NOT_ANNUALIZED`, compared only within a same-period peer cohort, and
  blocked when that period is more than four completed quarters before the decision session. The
  engine's `pe`/`pb` stay reconciliation-only for the same reason.
- **Entity applicability** for fundamental and valuation methods reads the governed
  `current_research_entity_applicability/v1` (layered seed / promoted / legacy-recovery /
  scale-out authority, `CURRENT_STATE_ONLY`, historical PIT `NOT_ESTABLISHED`). A cross-source
  disagreement fails closed; unclassified issuers stay unresolved. The upstream exact-valuation
  lane keeps its own narrower entity verdict.
- **Evidence class** (research coverage, never an action posture): `FULL_CURRENT_RESEARCH`
  (technical + fundamental + valuation), `PARTIAL_MULTI_FACTOR_RESEARCH` (two of three),
  `TECHNICAL_MARKET_RESEARCH`, `FINANCIAL_RESEARCH_ONLY`, `INSUFFICIENT_CURRENT_EVIDENCE`,
  `OUTSIDE_CURRENT_RESEARCH_SCOPE`. `research_action_posture` remains the sole action authority;
  `action_posture_gated_by_current_evidence` marks records whose posture waits on current
  technical evidence while financial research evidence remains.

### 6.5 Fundamental signal consumption (`fundamental_signal_consumption/v1`)

Added by `INTEGRATED_FUNDAMENTAL_STATE_CONSUMPTION_RECONCILIATION_V1` (2026-09-27, local, not
promoted). `fundamental_signal_consumption_contract.py` is the one adapter from the fundamental
producers (the Financial V2 compact product and the operational bridge's `financial_context`) to
the Integrated Decision. Each producer state becomes one signal on exactly one axis:

| Axis | Meaning | Examples |
|---|---|---|
| LEVEL | An absolute condition, only where a producer classifies one | profitability `HEALTHY`/`STRESSED`; cash conversion |
| DIRECTION | Change, never quality | growth, net/gross margin, equity/assets, debt/equity, current ratio; NWC amount (`RISING`/`FALLING`, no polarity) |
| TRANSITION | Earnings sign transition, never growth | `LOSS_TO_PROFIT`, `PROFIT_TO_LOSS`, `LOSS_NARROWED`, `LOSS_WIDENED` |
| COMPOSITION | Mix trajectory with no producer polarity | securities FVTPL / margin-lending / brokerage mix |

Each signal keeps its producer field and value, applicability (`APPLICABLE` / `NON_APPLICABLE` /
`UNRESOLVED`, from the producer's own entity gating) and fitness: qualification, source feature,
as-of period, basis and `financial_period_freshness/v1` status. Rules that are not negotiable:

- **Direction never implies level.** No producer classifies an absolute leverage or margin level,
  so those levels stay `UNAVAILABLE` (`NO_PRODUCER_*_LEVEL_CLASSIFICATION`); an improving
  debt/equity ratio is never a safe debt level. A stressed level and an improving direction are
  carried together, never collapsed.
- **Transitions stay transitions.** A sign transition names its source feature and basis (a
  seasonally comparable basis first: same-quarter YoY, then TTM, then QoQ). Only a `CURRENT`
  same-quarter YoY or TTM `LOSS_TO_PROFIT` is the `TURNAROUND` state (the engine's own
  `TURNAROUND_CONTEXT` basis; `TURNAROUND` asserts a current event). Only a comparable-basis
  (same-quarter YoY or TTM) transition votes: a sequential (QoQ) flip of any sign -- `PROFIT_TO_LOSS`
  included -- is seasonality-prone and stays a visible observation (`research_observations`,
  `transitions` with `non_vote_reason`), never a vote or a posture driver (promotion hardening,
  2026-09-28; it voted at `66d0fc0`/`5729c52`). A stale transition is historical context only.
  Growth consensus reads positive-base growth features only.
- **Unknown stays unknown.** A value outside a producer's vocabulary is `UNKNOWN` and never votes.
- **Policy classes** (`fundamental_signal_policy_hardening/v1`, FUNDAMENTAL_SIGNAL_POLICY_HARDENING_V1,
  2026-09-28, the promotion-hardening successor of `66d0fc0`). Every producer state has one static
  class with a reason (`policy_table()`), narrowed per record:

  | Class | States |
  |---|---|
  | `CURRENT_DECISION_VOTE` | profitability level; growth consensus; net- and gross-margin direction; cash-conversion level (positive same-period earnings only); equity/assets and debt/equity direction; current-ratio direction; bank asset quality, funding, efficiency |
  | `TRANSITION_EVENT` | earnings sign transition |
  | `RESEARCH_EVIDENCE_ONLY` | NWC amount trajectory; NWC sign; FCF proxy direction; resilience composite; securities composition trajectories |
  | `UNKNOWN` | `capital_efficiency_state` (never state-ready) |

  Per record a signal is also `NON_APPLICABLE` (entity gating) or `UNKNOWN` (outside the
  vocabulary, unresolved entity, post-session or unresolvable period, undefined cash sign), and a
  stale decision-grade signal is `RESEARCH_EVIDENCE_ONLY`.
- **Freshness: only a `CURRENT` period votes.** Usable research history is not a current decision
  signal. A `STALE_BUT_RESEARCH_USABLE` signal never votes and never triggers `TURNAROUND`; it stays
  visible: a stale level stays a (labelled) strength or weakness, a stale direction or transition
  is `historical_context`, and every such signal is in `stale_research_evidence`, each dimension's
  `stale_research_evidence`, `evidence_freshness` and `historical_reason_codes` (narrative only,
  never support or counter-thesis). A period after the decision session, or none, never enters.
  `signal_freshness_voting` counts vote-capable signals as `CURRENT_VOTING` /
  `STALE_RESEARCH_ONLY` / `UNAVAILABLE_EXCLUDED`. No second age threshold exists.
- **Working capital.** The NWC amount trajectory is evidence only (`RISING`/`FALLING`, no
  polarity): rising receivables or inventory, or falling payables, raise the amount while quality
  may deteriorate, and cash composition matters; no governed quality/composition contract exists.
  The current-ratio direction votes as the `SHORT_TERM_LIQUIDITY` dimension: a short-term
  liquidity-ratio direction only, never general balance-sheet health and never an absolute
  liquidity level (`NO_GOVERNED_ABSOLUTE_LIQUIDITY_LEVEL`). An NWC amount can no longer cancel a
  current-ratio direction; a conflicting independent liquidity signal would be shown, not voted.
- **Sign transitions.** The engine and flow bridge classify an earnings (net income, PBT) sign
  change between two periods of one semantic series (metric, provider, scope, unit, period
  semantics, temporal order): prior positive and current negative is `PROFIT_TO_LOSS`, never a
  growth value below −100%; a TTM loss that narrowed or widened is `LOSS_NARROWED` /
  `LOSS_WIDENED` (it was `ZERO_BASE`). Revenue and OCF sign changes stay ordinary growth. Growth
  consensus excludes every sign-transition feature.
- **One dimension, one vote.** Dimensions are profitability, growth, margins, cash quality, capital
  structure, short-term liquidity and the bank families. Agreeing current measurements
  (equity/assets and debt/equity; net and gross margin) vote once; disagreeing ones are shown
  as a conflict and do not vote. Their reason codes stay visible either way. The engine's leverage
  fallback re-reads equity/assets and is evidence only (never a second vote).
- **One vote per balance-sheet observation** (`one_vote_per_balance_sheet_observation/v1`,
  promotion hardening). Capital-structure and short-term-liquidity directions are same-quarter YoY
  ratios of one balance sheet, and a single event (a short-term borrowing, a debt-funded asset, a
  dividend) moves both. Measured on the same balance-sheet observation and agreeing, they are one
  vote, counted as `CAPITAL_STRUCTURE.DIRECTION` (the member the deterioration gate names); the
  other stays visible (`vote_counted_once_with`, `derivation.vote_grouping`). Opposing, both stay
  (`OPPOSING_DIMENSIONS_PRESERVED`); on different observations, both count. No weight, score or
  threshold.
- **Evidence only.** The FCF proxy direction (the engine declares it never affects decisions), the
  NWC amount trajectory and sign, the resilience composite (it restates other signals) and
  securities composition trajectories are shown, never voted. A CFO/net-income sign is a cash
  level only over positive same-period earnings.
- **Evidence availability is not directional sufficiency.** `evidence_availability` is `AVAILABLE`
  when a research-usable decision-grade signal exists from any usable period (current or stale),
  with its polarity; `directional_sufficiency` is `INSUFFICIENT` when `fundamental_state` is.
  `fundamental_evidence_availability` (`fundamental_evidence_availability/v1`, promotion hardening)
  names what is known in five states: `CURRENT_DIRECTIONAL` (a direction is established),
  `CURRENT_NON_DIRECTIONAL` (current applicable evidence, no direction: neutral, conflicting or a
  sequential observation), `STALE_ONLY` (only non-current evidence: stale, or a fiscal label whose
  calendar period is unresolved), `NOT_APPLICABLE_ENTITY` (the entity family is not decision-
  applicable; its evidence stays research evidence) and `ABSENT`. It is on the Integrated Decision
  record, the FUNDAMENTAL axis context, the decision input and the capability map. The decision
  input's FUNDAMENTAL dimension is `AVAILABLE` on evidence, so an insufficient current direction
  never downgrades the evidence class. The FUNDAMENTAL axis blocker and the decision input's
  `direction_reason_codes` name the state: `FUNDAMENTAL_CONTEXT_ABSENT` (absent),
  `FUNDAMENTAL_STALE_EVIDENCE_ONLY_NO_CURRENT_DIRECTION`, `FUNDAMENTAL_CURRENT_DIRECTION_INSUFFICIENT`
  or `FUNDAMENTAL_ENTITY_NOT_DECISION_APPLICABLE`. Posture reads `fundamental_state` exactly as
  before; only posture branch 1's explanation (`why_now`) is worded by the five-state, so known
  evidence is never described as missing fundamental data.
- **Risk level is not direction** (`fundamental_risk_level`, `fundamental_risk_level_from_qualified_
  level_evidence_only/v1`). From qualified LEVEL evidence only -- profitability and cash conversion
  over positive same-period earnings -- never from a direction or the resilience composite (which
  reads margin and balance-sheet directions). Per dimension the current observation supersedes a
  non-current one: `ADVERSE_LEVEL_CURRENT`, `ADVERSE_LEVEL_KNOWN_NOT_CURRENT` (known adverse
  history stays known), `NO_QUALIFIED_ADVERSE_LEVEL` (constructive levels only; never "healthy":
  leverage, margin and liquidity levels stay unassessed), `LEVEL_UNKNOWN`. The negative-NWC sign
  stays a descriptive observation (the engine declares it no verdict). `IMPROVING` never implies a
  healthy level. The asymmetric-dislocation product reads survivability from this and from the
  five-state availability, never from `fundamental_state`: `QUALITY_DISLOCATION` needs a current
  constructive level without an adverse one; a known adverse level with a price breakdown is
  `DISTRESS_SPECULATIVE`; `FUNDAMENTAL_EVIDENCE_UNAVAILABLE` only when neither a direction nor a
  level is known.
- **Entity family applicability.** Industrial issuers use the corporate contract; banks and
  securities firms (limited family) only their specialist signals; insurers and finance companies
  (limited family) no decision signal family; an unclassified/generic record is unresolved -- its
  generic primitives (profitability level, equity/assets direction) stay research evidence and
  never vote, however many fields exist (`ENTITY_FAMILY_UNRESOLVED_RESEARCH_EVIDENCE_NOT_A_VOTE`;
  they voted at `5729c52`). The governed entity-aware operational bridge keeps its own gating.
- **Fiscal-period knowledge time** (`post_session_quarter_label_known_before_session_is_non_calendar_
  fiscal/v1`). The authoritative test is knowledge time, not the label. A quarter label whose
  calendar quarter ends after the decision session, carried by a record whose pinned period
  semantics were retained on or before the session (`period_semantics_knowledge_time` in the engine
  lineage), cannot be a calendar quarter: it is a non-calendar fiscal label, known research evidence
  whose calendar period (so currency) is unresolved -- no governed fiscal-year registry exists -- and
  it never votes (`NON_CALENDAR_FISCAL_PERIOD_KNOWN_BY_SESSION`). Without that knowledge proof the
  label fails closed as possible future information (`KNOWLEDGE_TIME_UNPROVEN_FAIL_CLOSED`).
- **Policy epoch** (`fundamental_decision_policy_version`, promotion hardening). Every Integrated
  Decision record carries the fundamental decision-policy epoch (`fundamental_promotion_hardening/v1`),
  and it enters `decision_identity`. Earlier records are never rewritten; their epoch is resolved from
  their own shape (`legacy_unversioned_fundamental_reader/v0`, `fundamental_signal_consumption/v1`,
  `fundamental_signal_policy_hardening/v1`). A fundamental state compared across epochs is
  `NOT_COMPARABLE_POLICY_CHANGE`: multi-session velocity compares the fundamental trajectory within
  the latest epoch only; the next-session posture transition labels a posture change whose
  fundamental state changed across epochs `NOT_COMPARABLE_POLICY_CHANGE`; outcome feedback and
  outcome measurement never pool fundamental states (or outcome groups) across epochs.
- **`fundamental_state` is derived, not replaced.** The standing policy runs over current dimension
  votes: `TURNAROUND` (current qualified transition); `DETERIORATING` (more adverse than favorable
  votes with profitability `STRESSED`, growth `WORSENING` or capital structure `WORSENING`);
  `IMPROVING` (favorable only, with growth, margins or short-term liquidity improving); `STABLE`
  (favorable only); `MIXED` (both); otherwise `INSUFFICIENT`. The record carries
  `fundamental_synthesis` (strengths, weaknesses, improving, deteriorating, transitions,
  historical context, context, stale research evidence, excluded, missing, non-applicable,
  consumption classes, evidence availability, derivation) beside it; when the operational bridge
  decides, the Financial V2 research evidence stays attached (`financial_v2_research_evidence`).
  The FUNDAMENTAL axis and decision input carry compact components. Posture thresholds and
  branches are unchanged.
- **Research P/B is labelled where it is surfaced.** When the Integrated Decision's
  `valuation_context_summary.pb_multiple` is the research P/B (`P/B_CURRENT_RESEARCH`, total owners'
  equity as reported, NCI not deducted), it carries `pb_basis` (method, equity definition, the
  method's own limitations, claim `RESEARCH_ONLY_NOT_EXACT_NOT_COMMON_SHAREHOLDER`) and the
  limitation `P_B_IS_RESEARCH_TOTAL_EQUITY_NCI_NOT_DEDUCTED_NOT_COMMON_SHAREHOLDER`; the value is
  unchanged and exact P/B stays blocked. The Daily brief and the dislocation product pass `pb_basis`
  with the multiple.

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


## Forward-driver explanatory contract (R4, 2026-10-01)

`forward_driver_context/v1` is owned by `current_corporate_intelligence_axis.py`.
The production chain is typed retained observations (`corporate_action_events.py`)
→ official ledger reconciliation (`official_corporate_action_ledger.py`) → retained
market-wide event adapters (`market_wide_current_corporate_intelligence.py`) → deduplicated,
conflict-checked `current_corporate_event_context.py` → classified corporate axis →
`integrated_investment_decision_product.evaluate_corporate_intelligence_context` →
Corporate Intelligence evidence-axis context and Current Research CORPORATE dimension.
R4 consumes the classified axis; it does not reread documents or rebuild those sources.

Each driver preserves ticker, decision/evidence sessions, exact event identity, source
identities/tier, canonical type/subtype/status and original status, all five labelled known
dates, original and decision-session freshness, temporal fitness/warnings, materiality,
conflicts, warnings, reasons and limitations. Missing dates remain null; malformed raw dates
remain visible with a local blocker. Record date never fills ex-date. Scheduled future execution
is valid planned context; a future observed announcement or executed/completed execution is
blocked. Dates alone never prove execution. Categories describe distributions, capital
structure, governance or other event context; other taxonomy types remain UNCLASSIFIED_DRIVER.

Qualification requires existing OFFICIAL_QUALIFIED source evidence, nonempty event/source
identity, compatible ticker, usable source and temporal fitness, resolved status/classification,
known valid dates, no conflicts, and ACTIVE or RESOLVED_RECENT freshness under the existing
90-day rule. Recency is evaluated at the decision session using the standing date precedence
(ex-date, execution date, record date, announcement date); no date is inferred. Earlier evidence
sessions remain explicitly PARTIAL; future/missing/invalid sessions fail closed. Historical or
unresolved observations remain visible with blockers and cannot inflate qualified coverage.
Qualification is dated research context, not directional thesis support or exact authority.

V1 retains INFORMATIONAL and MIXED only from the existing explicit classification; otherwise
its direction is UNKNOWN. POTENTIAL_CATALYST/POTENTIAL_RISK and bare event types cannot establish
SUPPORTIVE/ADVERSE. Conflicts force UNKNOWN. Pending/recent/historical/unresolved relevance
labels describe timing, not price effect. No driver votes, scores, thresholds, probabilities,
targets, strategy/valuation/portfolio inputs or posture changes are introduced. No evidence is
promoted and no proxy or non-applicable dimension is relabelled.

The Integrated Decision coverage includes the canonical denominator, qualified/no-qualified
ticker and observation counts, type/category/status/freshness/fitness/temporal/materiality/
direction distributions, and blocker prevalence (unique tickers per reason). Distributions
count all retained observations, including blocked observations; qualified counts are separate.
The per-context identity hashes the complete deterministic projection. Existing per-decision
identities exclude this explanatory projection and retain the original source identity. The
standing product content identity includes the new record and coverage fields and must change.

`tools/replay_forward_driver_context.py` takes exact retained input paths, verifies content
identities and corporate source binding, reproduces preexisting summaries/dimensions through
the production join, asserts the exact additive allowlist, and writes only to a separate scratch
directory. `tests/test_forward_driver_context.py` guards this contract in Producer CI. See
`docs/internal/R4_FORWARD_DRIVER_ACCEPTANCE.json` for the portable retained acceptance report.
