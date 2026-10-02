# Stock Lookup North Star

## 2026-10-02 PIT foundation strategic closure

The comprehensive evidence-first research and decision-support mission below remains
unchanged. The market PIT foundation extends provenance and continuity across the
existing product; technical features remain one lens among fundamentals, financial
quality, valuation, corporate drivers, macro/sector and portfolio/risk. Strategic
disposition: `PROSPECTIVE_PIT_PRIMARY / FULL_HISTORICAL_INTEGRATED_PIT_DEFERRED`.
The [14-capability dossier](internal/MARKET_PIT_FEASIBILITY_DOSSIER_20261002.md) states
actual evidence/time/rights/economic blockers. Future proposals are document-only;
older NEXT pointers below are historical context, not current execution authority.


## 2026-10-01 execution rebaseline

The October 1 ordinary Owner Daily live-acceptance gate is closed. PR #31 merged after
Producer CI #167 SUCCESS. The machine-readable roadmap now sets
`CURRENT_RESEARCH_COVERAGE_AND_DECISION_FITNESS_V1` as NEXT.

The strategic order from this point is:

`Decision Fitness → Fundamental/Current Valuation Depth → Corporate/Forward Drivers → Intrinsic/Scenario Valuation → Prospective Calibration → Portfolio/PIT/Execution Authority`.

Older dated maturity snapshots and "NEXT" references below are historical planning
context unless they agree with `docs/ROADMAP_STATE.json`.


Status: STRATEGIC_INTENT / NON-EXECUTION-AUTHORITY

Date: 2026-09-28 (rebaselined 2026-09-28 after M1 live acceptance)

This document defines the product destination, major capability gaps, and intended milestone ordering for Stock Lookup. It is deliberately compact so future agents can reference it instead of reconstructing strategy from chat history.

Execution truth remains in `docs/STATE.md`, `docs/ROADMAP_STATE.json`, `docs/ROADMAP.md`, `docs/DECISIONS.md`, and `docs/AI_RULES.md`. This document never overrides them. If this document conflicts with those files, execution must fail closed and the conflict must be reconciled explicitly.

`docs/PRODUCT_NORTH_STAR.md` (2026-09-13) remains the product operating-model and navigation reference (authority layering, AI handoff, public/private boundaries, do-not-recreate list). This file is the compact strategic sequence and capability-gap map. Neither silently overrides the other; surface any disagreement.

## 1. North Star

Stock Lookup should become a daily Vietnamese-equity research and decision-support system that helps a human investor:

1. understand market regime, breadth, liquidity, sector leadership, and risk;
2. analyze each stock across technical, fundamental, valuation, corporate/event, and risk lenses;
3. distinguish current facts, stale facts, proxies, unknowns, and later-acquired historical evidence;
4. form bull/bear theses with confirmation, invalidation, catalysts, downside, and missing evidence;
5. incorporate portfolio exposure, concentration, correlation, liquidity, and risk;
6. retain prospective decision snapshots and later evaluate outcomes without hindsight rewriting;
7. improve research quality through calibrated historical learning;
8. preserve provenance, point-in-time/knowledge-time semantics, deterministic numerical authority, and explicit uncertainty.

The product is not an AI stock-prediction engine and should not fabricate probabilities, target prices, facts, or trading authority. AI explains, synthesizes, challenges, and surfaces missing evidence; deterministic engines own formalizable calculations, eligibility, risk gates, and qualified metrics. Human approval remains the final decision layer.

Target flow:

```
qualified evidence/data
    -> canonical + temporal/use fitness
    -> deterministic market/technical/fundamental/valuation/event research
    -> integrated strategy/scenario/risk state
    -> AI research + counter-thesis
    -> human decision
    -> dashboard/monitoring
    -> prospective outcome journal
    -> calibrated learning
```

## 2. Strategic principles

- Evidence before inference.
- Knowledge time and observation time are separate.
- Current research, historical reconstruction, and PIT/backtest authority are separate modes.
- A missing or unqualified field blocks only dependent uses; it does not invalidate the whole issuer.
- Research proxy is never silently promoted to exact canonical fact.
- Current-session evidence may support scoped actionable research even when historical/PIT authority remains blocked.
- No provider/source becomes authoritative by side effect.
- One meaningful milestone at a time; no parallel roadmap branches unless there is a real architectural dependency.
- Production Daily, recovery replay, and historical backfill must remain operationally distinct.
- Policy changes must be versioned so outcome/velocity systems do not mistake code changes for issuer changes.
- The active `vnstock`/VNAI/VCI/KBS runtime is retired; historical provider-reported evidence remains a lineage-labeled research proxy. DNSE/Livespeed remains the primary market-data direction.
- Analytical knowledge frameworks guide method design; they never become authority layers (section 7).

## 3. Current strategic maturity snapshot

These percentages are planning heuristics only. They are NOT execution authority, acceptance criteria, or promotion gates. They were estimated before the 2026-09-28 M1 live acceptance and have not been recomputed.

| Capability | Approx. maturity |
|---|---:|
| Architecture / governance | 86% |
| Engineering / code discipline | 82% |
| Data provenance / temporal semantics | 76% |
| Market / technical / breadth research | 73% |
| Fundamental analysis | 69% |
| Production Daily / operations | 67% |
| Integrated investment research | 63% |
| Valuation | 64% |
| Corporate / event intelligence | 58% |
| Product UX for daily investor use | 52% |
| AI research experience | 48% |
| Portfolio / risk / sizing | 40% |
| Backtest / learning / calibration | 32% |

Overall North-Star maturity is approximately 66%. This number should not be used as a roadmap gate.

## 4. Current promotion boundary

As of 2026-09-28 (the authoritative record is `docs/STATE.md` / `docs/ROADMAP_STATE.json`):

- M1 (`CURRENT_DECISION_SURFACE_CONVERGENCE_V1`) is `COMPLETE / LIVE_ACCEPTED_2026_09_28`, accepted on the genuine 2026-09-28 ordinary Daily run on canonical main.
- Canonical Producer `main` is `66943d884461209cd6261db6f1b8a40a2986cf5a` (the 2026-09-28 retained session over the PR #8 merge `6c40644`).
- No authority was promoted by M1. DNSE/Livespeed stays primary; the optional Vnstock/KBS/VCI supplemental runtime stays deferred and security-review blocked; RAW_AS_TRADED, liquidity/sizing, ACTIVE_UNIVERSE, and valuation authority boundaries are unchanged.
- The validated local Current Research chain is verified locally: analytical checkpoint `f1e715c` on an unpushed branch forked from `6c40644`. It includes Current Research convergence, research P/B, Financial V2 input integrity, fundamental-state consumption reconciliation, signal-policy hardening, and promotion hardening.
- Next execution gate: `CURRENT_RESEARCH_CHAIN_PROMOTION_REVIEW_INTEGRATION_V1` = `NEXT / NOT_STARTED`. Its first action is an exact-head promotion/readiness review, not implementation.
- No local analytical checkpoint becomes production authority until review/integration/promotion gates are completed and the owner approves the merge.

## 5. Major remaining capability gaps

### 5.1 Production continuity

- One real ordinary Daily passed M1 live acceptance; one accepted session is not yet a continuity track record.
- Daily currently resolves one latest completed session; it is not a full automatic missed-session catch-up scheduler.
- Historical price windows can contain missed dates without recreating a complete missed-session research/decision artifact.
- A governed missed-session continuity/catch-up capability is required.

### 5.2 Financial evidence currency

- Financial analysis engines are more mature than the freshness of the current statement corpus.
- Stale-but-research-usable evidence must remain visible but cannot masquerade as current evidence.
- Financial refresh still carries legacy source/runtime debt.
- Current common-share / parent-equity / denominator semantics remain incomplete for exact valuation.
- Business-economics and forecasting inputs (drivers, unit economics, cost structure, mix) are largely absent from statutory statements; see section 7.6.

### 5.3 Valuation breadth

- Research P/B has broad coverage but remains research-only where required.
- P/E TTM, P/S TTM, EV/EBITDA, common-share basis, parent-equity basis, and sector-specific valuation need stronger qualified inputs.
- Multi-method intrinsic valuation (DCF/FCFF, FCFE, DDM, residual income) is a capability gap: no governed forecast, discount-rate, or terminal inputs are retained today.
- Multi-method valuation should come only after input-basis contracts are sound.

### 5.4 Historical PIT and market basis

- Broad, market-wide and historical RAW_AS_TRADED authority is not promoted. A qualified
  prospective cross-source subset is promoted only for scoped research where a retained DNSE
  same-session bar agrees with the independent official HOSE series.
- ACTIVE_UNIVERSE remains incomplete.
- Historical reconstruction is useful but not equivalent to evidence known on the historical date.
- Execution-grade liquidity, turnover, sizing, leverage, and backtesting remain fail-closed where inputs are unqualified.

### 5.5 Corporate/event intelligence

- Official evidence acquisition and corporate-action lineage exist, but event intelligence is not yet a complete daily thesis-change layer.
- Ex-date/event-time semantics remain blocked where qualified official timing evidence is absent.
- Corporate/news/document research should evolve into a provenance-bound event and RAG layer.

### 5.6 Decision product

The system still needs a human-first Personal Investment Decision Workbench that exposes, per market/session and per ticker, through the Long-Term and Short-Term lenses of section 7:

- what changed since the prior session;
- technical / market state;
- fundamental state and freshness;
- valuation state;
- corporate/event changes;
- bull thesis;
- bear/counter-thesis;
- confirmation;
- invalidation;
- catalyst/downside;
- portfolio impact;
- missing evidence;
- provenance/fitness warnings.

### 5.7 Portfolio and learning

- Portfolio exposure, concentration, correlation, liquidity-aware risk, and sizing are incomplete.
- Prospective decision snapshots and outcome measurement need policy-epoch-aware identity.
- Calibration and pattern learning require enough prospective samples and must remain PIT-safe.
- No small-sample playbook or strategy should become authoritative by automatic promotion.

## 6. Intended milestone sequence

This is strategic ordering, not automatic execution authorization. Only `docs/ROADMAP_STATE.json` records what is NEXT.

1. **M1 Ordinary Daily Live Acceptance** -- COMPLETE / LIVE_ACCEPTED_2026_09_28.
   - Proved the canonical Daily machinery, evidence currency, release identity, and decision-surface parity on a real ordinary session.

2. **Current Research Chain Promotion Review / Integration** -- NEXT / NOT_STARTED (`CURRENT_RESEARCH_CHAIN_PROMOTION_REVIEW_INTEGRATION_V1`).
   - exact-head promotion/readiness review first;
   - reconcile the chain's docs/state with current main;
   - CI and same-session before/after replay;
   - promote only after explicit owner approval.

3. **Missed Session Continuity and Catch-up**
   - detect missing completed sessions;
   - reconstruct each missing session with honest temporal qualification;
   - never rewrite later-acquired evidence as historically known.

4. **Financial Evidence Currency Refresh + Legacy Runtime Migration**
   - capability-first source routing;
   - advance qualified financial evidence to current statutory periods;
   - migrate away from legacy vnstock-dependent refresh paths;
   - do not re-enable vnstock by default.
   - Capability dependencies carried here: qualified inputs for Financial Quality and Growth Quality, current-period denominators, and the statement-derivable part of business-economics evidence (section 7.6).

5. **Personal Investment Decision Workbench**
   - consolidate market, ticker, valuation, event, counter-thesis, confirmation/invalidation, and missing-evidence views for daily human use;
   - organize them through the Long-Term and Short-Term product lenses (section 7) over one shared foundation;
   - method-lens valuation (section 7.5) and forecasting/scenario views enter here only as their inputs qualify; missing inputs are shown as missing.

6. **Corporate/Event Research and Financial RAG**
   - provenance-bound document/event synthesis;
   - sector/issuer question sets;
   - event-to-thesis change detection;
   - AI may summarize and challenge but not create factual authority.
   - Source for disclosed business drivers (capacity, volume, mix, pricing) where filings state them.

7. **Portfolio-Aware Research and Risk Context**
   - sector exposure;
   - concentration;
   - correlation;
   - volatility/drawdown context;
   - liquidity-aware risk only where inputs are qualified;
   - sizing authority remains separate.

8. **Prospective Decision Journal**
   - retain T0 evidence identity, policy version, thesis, confirmation, invalidation, portfolio context, and human decision state.

9. **Outcome Measurement and Calibration**
   - MFE/MAE;
   - benchmark-relative outcomes;
   - catalyst/invalidation outcomes;
   - policy-epoch-aware comparison;
   - empirical calibration only after sufficient samples.

10. **Historical PIT / Execution / Backtest Maturity**
    - RAW_AS_TRADED;
    - active-universe authority;
    - qualified liquidity/turnover;
    - execution assumptions;
    - sizing;
    - robust PIT backtests and portfolio optimization.

## 7. Investor Horizons and Analytical Reference Framework

### 7.1 Two horizons, one foundation

The product exposes two human research horizons over ONE shared evidence / feature / decision foundation:

- `LONG_TERM_INVESTOR`
- `SHORT_TERM_INVESTOR`

They are product/research lenses, NOT separate data stacks and NOT separate sources of authority. Both read the same retained evidence, fitness labels, and deterministic engine outputs. A lens organizes and explains; it may narrow a Producer verdict but never widen it. `research_action_posture` stays the single cross-surface action authority; a horizon-specific posture would need its own explicit, versioned contract change.

### 7.2 Long-Term lens

1. **Business Economics** -- how the business makes money; major revenue, volume, price, mix, capacity, and cost drivers; cyclicality and operating leverage where evidence supports it.
2. **Financial Quality** -- margins; ROE / ROA / ROIC where qualified; cash conversion and earnings quality; leverage and working capital.
3. **Growth Quality** -- separate price, volume, mix, capacity, acquisition, or other drivers when evidence exists; headline revenue/EPS growth is not a sufficient explanation.
4. **Capital Allocation** -- reinvestment, capex, dividends/buybacks where relevant, and return on incremental capital / value creation when inputs qualify.
5. **Competitive / Business Position** -- pricing power, moat, or market position only where defensible evidence exists; no fabricated qualitative authority.
6. **Valuation Lenses** -- relative valuation; DCF / FCFF; FCFE where qualified; DDM where applicable; residual-income style where appropriate; Graham / asset-based lenses where applicable; sector-specific methods where justified.
7. **Scenario and Downside** -- explicit operating assumptions; earnings/cash-flow and valuation sensitivity; bull/base/bear logic without fabricated probabilities.
8. **Long-Term Thesis** -- evidence for, evidence against, catalysts, invalidation, missing evidence.

### 7.3 Short-Term lens

Market regime / breadth; sector leadership; relative strength; trend; base / VCP / structure; breakout / retest / early reversal; participation / relative volume; flow where qualified; event/catalyst context; trigger; invalidation.

Reuse the existing governed tactical engines (market regime/breadth, sector leadership, sector-aware relative research, price-structure/breakout context, tactical entry classifier, relative volume, foreign flow, catalyst/event context, confirmation/invalidation boundaries). Do not build a second technical system. BOS/CHoCH/VCP stay deterministic technical inference, not proof of institutional behavior.

### 7.4 Analytical reference frameworks (CFA / CMA)

CFA- and CMA-style bodies of knowledge are ANALYTICAL REFERENCE FRAMEWORKS for method design only. Their concepts map into existing or future capabilities; they never become independent authority layers. Use generic analytical concepts only; do not reproduce curriculum text.

- CFA-style concepts: financial statement analysis; company analysis and forecasting; equity valuation; DCF / DDM / FCFF / FCFE; residual income; multiples; portfolio and risk analysis.
- Selected CMA-style concepts: decision analysis; cost-volume-profit logic; operating leverage; price-volume-mix; marginal economics; pricing sensitivity; capital budgeting; risk and uncertainty.

Not allowed: `CFA_ENGINE`, `CMA_ENGINE`, `CFA_SCORE`, `CMA_SCORE`, credentials or branding used as authority, or a universal stock score.

### 7.5 Method-lens output contract direction

Do not force every methodology into a /100 score. Method-native scoring is acceptable only when the methodology itself defines a deterministic scoring framework and missing components are handled explicitly (for example, a future CANSLIM contract).

Valuation lenses such as DCF/DDM should instead expose: applicability; readiness/status; input basis; assumptions; missing inputs; valuation result or range only where qualified; sensitivity dimensions; evidence/provenance; limitations.

Never fabricate a target price, a probability, or false precision.

### 7.6 Business-economics evidence semantics

Keep five kinds of content distinct. No new vocabulary is introduced here; each maps onto existing governed semantics:

| Kind | Existing governed semantics |
|---|---|
| Observed / source-backed fact | `FACT` claim type; retained observations with provenance (`observed_facts`) |
| Deterministic derived value | engine outputs under `feature_input_fitness_contract/v1` tiers (`READY`, `RESEARCH_PROXY`); fallbacks named `DERIVED_PROXY` |
| Explicit scenario assumption | `conditional_assumptions`, `case_status = CONDITIONAL`, `probability_status = UNKNOWN_UNCALIBRATED` |
| Analyst / AI inference | `INFERENCE` / `HYPOTHESIS` claim types |
| Unknown | `UNKNOWN` / `BLOCKED` / `NOT_APPLICABLE`; missing stays missing |

CMA-style inputs such as fixed/variable cost split, unit economics, ASP, product mix, contribution margin, project cash flows, or price elasticity usually cannot be recovered from statutory statements alone. When no retained source states them, they remain missing. AI must not manufacture business-economics inputs; a stated assumption is labelled as an assumption, never as a fact.

## 8. TradingAgent-VN lessons

TradingAgent-VN is a useful product/reference benchmark, not a replacement architecture.

### ADOPT / ADAPT

- **Decision / event ledger** -> missed-session continuity + prospective decision journal.
- **Analyst cards** -> Decision Workbench lenses: market/technical, fundamental, valuation, corporate/event, risk.
- **Conditional bull/bear debate** -> AI counter-thesis when evidence conflicts or decision impact is high; do not debate every ticker.
- **Portfolio-aware context** -> later portfolio/risk layer; research first, execution sizing only after authority.
- **Financial RAG** -> provenance-bound official-document research.
- **Daily report / CIO memo presentation** -> human-readable integrated investment memo, while preserving deterministic authority.
- **Episodic memory / calibration** -> prospective journal + outcome calibration, only after policy-epoch and PIT safeguards.

### DEFER

- Kelly/Markowitz or automated weight optimization until execution-grade liquidity, portfolio and risk inputs are qualified.
- Strategy/playbook promotion until sample sizes, regime segmentation, and calibration are robust.

### REJECT

- LLM as final BUY/SELL/target-weight authority.
- Fabricated `+X%` forecast outputs.
- Automatic trust of newly fetched provider data without semantic/use qualification.
- Calendar-quarter heuristics as a substitute for knowledge-time evidence.
- Automatic strategy promotion from very small samples.

TradingAgent-VN primarily changes the upper product/research layers. It does not require replacing the Stock Lookup evidence, temporal, deterministic, or authority core. Memory/calibration is the first area where the influence becomes architecturally deep.

## 9. Anti-context-bloat rule

Future handoffs and agent prompts should reference this file rather than restating the full strategic history.

A normal milestone prompt should contain only:

- exact executor / repository / milestone;
- starting checkpoint;
- objective;
- required contract;
- scope and safety gates;
- validation;
- expected final handoff.

Do not paste this document into every prompt.

Chat ideas remain proposals until explicitly reflected in an authoritative state/decision/roadmap update.

## 10. Definition of the finished product

Stock Lookup is close to its intended destination when a user can open it before/after a session and, without reconstructing context manually:

- see current market regime and what changed;
- see the strongest and weakest evidence for every portfolio/watchlist ticker;
- understand valuation and its basis;
- see current versus stale versus unknown evidence;
- see bull/bear thesis, confirmation, invalidation and catalyst;
- read each ticker through a Long-Term and a Short-Term lens without either lens inventing evidence;
- understand portfolio and risk implications;
- inspect provenance for every material claim;
- compare today's thesis with prior prospective snapshots;
- review calibrated historical outcomes without hindsight leakage;
- make the final investment decision themselves.

That is the product destination. GitHub polish, public adoption, or monetization are secondary to achieving this research and decision quality.

## 11. Basis, timeframes and thesis evidence architecture

The intended product flow stays broad: acquisition and provenance → temporal/use
fitness → deterministic technical, fundamental, financial-quality, valuation,
corporate and macro/sector research → strategy/scenarios/confirmation/invalidation
→ portfolio/risk → AI research and counter-thesis → human decisions → Daily,
dashboard and monitoring → prospective T0 → outcomes and calibration.

Every material price, volume, flow, financial, valuation, corporate and macro/sector
input should carry what it measures, source/dataset/route identity, relevant period
or timeframe, retrieval and actual knowledge/publication time, basis, freshness,
use-specific fitness and historical-cutoff legality. Calendar dates, financial period
ends and later source revisions never substitute for historical availability.

Price modes remain distinct: `RAW_AS_TRADED` supports actual traded observations,
session morphology, gaps, event reaction, swing/breakout/support levels;
`PIT_CA_ADJUSTED` is the preferred future comparable continuous basis with raw lineage;
`RETROSPECTIVE_ADJUSTED` remains a separately labelled research mode. Raw alone does
not qualify long-window indicators across corporate actions. Volume has its own
shares/lots/value/other/unknown unit and basis; price qualification cannot qualify it.

1D is tactical context, 1W trend/base context and 1M structural context; year-level
views have lower priority. Derived weekly/monthly bars and features retain each daily
constituent and never gain stronger fitness or future inputs. Candle research starts
with body, range, wicks, close location, gaps, ATR, volume, trend and location context.
Pattern names are derived labels, not automatic actions; Bearish Engulfing does not
become SELL. True volume profile requires complete trades/ticks or an explicitly
qualified granular volume-by-price approximation; daily OHLCV cannot supply it.

Observed flow may support persistence, acceleration, share and price divergence
analysis. It does not prove institutional motivation. Macro/sector data keep their
publication, period, revision and freshness roles distinct from issuer price timing.

A future thesis evidence matrix may organize Technical, Volume, Institutional Flow,
Fundamental, Valuation, Corporate, Macro/Sector, Liquidity/Portfolio and Evidence Quality
into SUPPORTS, OPPOSES, MIXED, UNKNOWN or NOT_APPLICABLE. Each axis retains horizon,
freshness and provenance; no universal score or independent action authority is implied.
Conflict detection and AI synthesis are subordinate to qualified evidence and the
standing `research_action_posture`.

The six [future program proposals](internal/MARKET_MULTI_TIMEFRAME_TECHNICAL_FLOW_THESIS_PROPOSALS.md)
extend existing engines and remain document-only. No technical roadmap implementation,
universal scoring, provider addition or automatic NEXT selection follows this update.
