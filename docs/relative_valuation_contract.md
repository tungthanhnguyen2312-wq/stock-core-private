# Relative Valuation Contract

Schema and method version: `1.0.0`. This additive contract evaluates P/E, P/B, P/S, EV/EBITDA and EV/Sales only from a direct provider observation with declared multiple semantics, or from qualified current price, qualified basic/diluted share count, and compatible canonical financial records. It never fills a canonical gap from `financial_latest`.

An observation requires source, provenance, `as_of_date`, actionable current price, and a financial period and statement scope where a financial denominator is used. Annual, quarterly and TTM records are never mixed; `consolidated`, `separate`, and `unknown` scopes are never mixed. Negative earnings/EBITDA are incomparable; zero and null denominators remain unavailable. EV methods additionally require documented market-cap, debt, and cash semantics. A numerical multiple is not automatically actionable.

Historical or peer ranges require a deterministic, provenance-carrying universe and at least three comparable observations for that method. A documented IQR 1.5 fence may exclude an outlier from a displayed range, never from raw evidence. Historical observations remain historical rather than stale solely for age. No peer universe is inferred from a label, ticker order, or values.

Each method exposes identity, source/provenance, observation date, period/scope, state (`available`, `unavailable`, `inapplicable`, `incomparable`, or `malformed`), missing inputs, warnings, reference range, and `is_actionable`. Percentiles, implied per-share values, recommendations, and a single target price are not emitted unless a later contract explicitly qualifies them. Legacy bundles resolve to conservative `unknown`.

Current runtime limitation: snapshot P/E/P/B and metadata market-cap/share fields have no qualified denominator, share-basis, enterprise-value, or peer/history provenance. Canonical financial statement scope is `unknown`. Therefore current production methods are unavailable/unknown; this contract does not infer those semantics.
