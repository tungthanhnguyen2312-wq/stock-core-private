# Analytical proposals and completed bar foundation

The first foundation, `MARKET_BAR_BASIS_AND_MULTITIMEFRAME_V1`, is COMPLETE under
the explicit October 2, 2026 owner override; see the
[contract and retained acceptance](../market_bar_basis_multitimeframe_contract.md).
The owner-selected `CONTEXTUAL_CANDLE_AND_TECHNICAL_FEATURES_V1` is now COMPLETE;
see its [single contract and retained acceptance](../contextual_technical_features_contract.md).
The remaining proposals are document only, not NEXT or active implementation.
Expected next owner-selection gate: `VOLUME_AND_INSTITUTIONAL_FLOW_CONTEXT_V1`;
no successor starts automatically.
None grants new authority, thresholds or strategy tuning.
Reuse existing deterministic technical/flow/decision engines and
the comprehensive [North Star](../NORTH_STAR.md). `research_action_posture` remains
the standing action authority. Exact evidence/use gates precede every new consumer.

| Proposal | Purpose and bounded scope | Required evidence / acceptance direction |
|---|---|---|
| MARKET_BAR_BASIS_AND_MULTITIMEFRAME_V1 | Explicit RAW_AS_TRADED / PIT_CA_ADJUSTED / RETROSPECTIVE_ADJUSTED modes; derive 1W/1M from original daily constituents | Basis, units, CA treatment, complete governed sessions, cutoff-safe constituent lineage; aggregate fitness never stronger than constituents |
| CONTEXTUAL_CANDLE_AND_TECHNICAL_FEATURES_V1 | Extend existing engines with primitive morphology and context; named patterns remain derived labels | Body/range/wicks/close-location/gaps, ATR, volume, trend and support/resistance/base location; deterministic invariants and feature-specific fitness; no Bearish Engulfing → SELL rule |
| VOLUME_AND_INSTITUTIONAL_FLOW_CONTEXT_V1 | Participation plus explicitly observed foreign/proprietary/institutional flow context | Shares/lots/value semantics, route/participant coverage, accumulation window, persistence/acceleration/share and divergence; no invented participant motive or institutional intent |
| THESIS_EVIDENCE_MATRIX_AND_CONFLICT_ENGINE_V1 | Organize evidence supporting/opposing a thesis across horizons; expose contradictions | Technical, Volume, Institutional Flow, Fundamental, Valuation, Corporate, Macro/Sector, Liquidity/Portfolio, Evidence Quality axes; SUPPORTS/OPPOSES/MIXED/UNKNOWN/NOT_APPLICABLE; freshness, provenance and horizon; no universal score |
| HISTORICAL_CA_PIT_SIGNAL_EVALUATION_V1 | Evaluate existing deterministic signals in a genuinely qualified bounded CA cohort | Known-time raw prices, original event terms/publication/ex-date/executed proof, comparable factor chain and membership; predeclared signal, representative gross outcomes, explicit exclusions; no tuning or broad historical promotion |
| INTRADAY_VOLUME_PROFILE_RESEARCH_V1 | Conditional future volume-by-price research only | Complete ticks/trades or qualified granular volume-by-price approximation with explicit coverage/completeness; daily OHLCV is not true volume profile; bounded trades_latest is not completeness proof |

1D supports tactical entries, gaps and session morphology; 1W supports trend/base
context; 1M supports structural context. Year-level context has lower priority.
Continuous indicator windows prefer qualified PIT CA-adjusted prices, while preserving
raw observations for traded levels and event reaction. Raw observation alone does not
establish a comparable long window spanning a corporate action.

Every feature records what it measures, period/timeframe, source identity, price/volume
basis, calculation inputs, retrieval/knowledge time, freshness and allowed use.
Technical inference remains evidence-organizing context, never institutional behavior
proof or an independent BUY/SELL authority. Macro/sector observations keep their own
publication/revision times; a latest release cannot be inserted into historical context.
AI may explain cross-axis conflicts and test counter-theses, but it does not manufacture
facts, weights, targets, probabilities or promotion decisions.
