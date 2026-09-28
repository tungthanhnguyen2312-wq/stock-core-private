# Stock Lookup North Star

Status: STRATEGIC_INTENT / NON-EXECUTION-AUTHORITY  
Date: 2026-09-28

This document defines the product destination, major capability gaps, and intended milestone ordering for Stock Lookup. It is deliberately compact so future agents can reference it instead of reconstructing strategy from chat history.

Execution truth remains in `docs/STATE.md`, `docs/ROADMAP_STATE.json`, `docs/ROADMAP.md`, `docs/DECISIONS.md`, and `docs/AI_RULES.md`. If this document conflicts with those files, execution must fail closed and the conflict must be reconciled explicitly.

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
- `vnstock`/legacy VCI/KBS runtime dependency is migration debt, not the target provider architecture. DNSE/Livespeed remains the primary market-data direction.

## 3. Current strategic maturity snapshot

These percentages are planning heuristics only. They are NOT execution authority, acceptance criteria, or promotion gates.

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

As of 2026-09-28:

- M1 Ordinary Daily live acceptance remains ACTIVE and is not complete.
- Canonical `origin/main` is older than the latest validated local Current Research chain.
- Latest reported local corrective checkpoint: `f1e715c`, status `READY_FOR_PROMOTION_REVIEW_AFTER_M1`.
- That local chain includes Current Research convergence, research P/B, Financial V2 input integrity, fundamental-state consumption reconciliation, and promotion hardening.
- No local analytical checkpoint becomes production authority until review/integration/promotion gates are completed.
- The next valid Ordinary Daily used for M1 should run on canonical main so M1 validates Daily plumbing independently from the local analytical-policy changes.

## 5. Major remaining capability gaps

### 5.1 Production continuity

- M1 Ordinary Daily live acceptance is still pending.
- Daily currently resolves one latest completed session; it is not a full automatic missed-session catch-up scheduler.
- Historical price windows can contain missed dates without recreating a complete missed-session research/decision artifact.
- A governed missed-session continuity/catch-up capability is required.

### 5.2 Financial evidence currency

- Financial analysis engines are more mature than the freshness of the current statement corpus.
- Stale-but-research-usable evidence must remain visible but cannot masquerade as current evidence.
- Financial refresh still carries legacy source/runtime debt.
- Current common-share / parent-equity / denominator semantics remain incomplete for exact valuation.

### 5.3 Valuation breadth

- Research P/B has broad coverage but remains research-only where required.
- P/E TTM, P/S TTM, EV/EBITDA, common-share basis, parent-equity basis, and sector-specific valuation need stronger qualified inputs.
- Multi-method valuation should come only after input-basis contracts are sound.

### 5.4 Historical PIT and market basis

- RAW_AS_TRADED is not promoted.
- ACTIVE_UNIVERSE remains incomplete.
- Historical reconstruction is useful but not equivalent to evidence known on the historical date.
- Execution-grade liquidity, turnover, sizing, leverage, and backtesting remain fail-closed where inputs are unqualified.

### 5.5 Corporate/event intelligence

- Official evidence acquisition and corporate-action lineage exist, but event intelligence is not yet a complete daily thesis-change layer.
- Ex-date/event-time semantics remain blocked where qualified official timing evidence is absent.
- Corporate/news/document research should evolve into a provenance-bound event and RAG layer.

### 5.6 Decision product

The system still needs a human-first Personal Investment Decision Workbench that exposes, per market/session and per ticker:

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

This is strategic ordering, not automatic execution authorization.

1. **M1 Ordinary Daily Live Acceptance**
   - prove the canonical Daily machinery, evidence currency, release identity, and decision-surface parity on a real ordinary session.

2. **Current Research Chain Promotion Review / Integration**
   - make the validated local chain reviewable;
   - exact-head review;
   - reconcile docs/state with current main;
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

5. **Personal Investment Decision Workbench**
   - consolidate market, ticker, valuation, event, counter-thesis, confirmation/invalidation, and missing-evidence views for daily human use.

6. **Corporate/Event Research and Financial RAG**
   - provenance-bound document/event synthesis;
   - sector/issuer question sets;
   - event-to-thesis change detection;
   - AI may summarize and challenge but not create factual authority.

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

## 7. TradingAgent-VN lessons

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

## 8. Anti-context-bloat rule

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

## 9. Definition of the finished product

Stock Lookup is close to its intended destination when a user can open it before/after a session and, without reconstructing context manually:

- see current market regime and what changed;
- see the strongest and weakest evidence for every portfolio/watchlist ticker;
- understand valuation and its basis;
- see current versus stale versus unknown evidence;
- see bull/bear thesis, confirmation, invalidation and catalyst;
- understand portfolio and risk implications;
- inspect provenance for every material claim;
- compare today's thesis with prior prospective snapshots;
- review calibrated historical outcomes without hindsight leakage;
- make the final investment decision themselves.

That is the product destination. GitHub polish, public adoption, or monetization are secondary to achieving this research and decision quality.
