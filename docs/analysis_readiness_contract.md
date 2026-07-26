# Analysis Readiness Contract

`analysis_readiness` is additive and derives only from canonical freshness envelopes, existing Corporate Intelligence completeness/comparability gates, and Corporate Events coverage provenance. It carries an injected `reference_at` and per-domain `state`, `reason`, `required_inputs`, and `is_actionable` for market/technical, fundamental, Corporate Intelligence, Corporate Events, and combined AI analysis.

States are `ready`, `degraded`, `blocked`, and `unknown`. Ready requires every required canonical input to be explicitly actionable; readiness never upgrades an input whose canonical `is_actionable` is false. Missing/malformed envelopes are unknown; missing/unknown required inputs block. Stale evidence remains visible as degraded. Historical quarterly evidence is valid historical/fundamental context but degraded, never current technical readiness.

Corporate Intelligence retains complete/comparable snapshot gates. Corporate Events with `partial_unqualified_50_row_cap` are always degraded: never complete history, lifecycle evidence, absence-of-events evidence, or ready. Combined AI is ready only when every domain is ready; otherwise it preserves unknown, blocked, or degraded conservatively. Legacy bundles omit the optional section and Consumers resolve them as unknown. Null remains null; zero remains zero.
