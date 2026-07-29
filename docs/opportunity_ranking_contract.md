# Evidence-Gated Opportunity Ranking Contract

Producer `opportunity_ranking` v1.0 orders only evidence-availability states for a supplied ticker set. It has six independent dimensions: financial quality, valuation, technical/current-market readiness, catalyst evidence, downside/invalidation, and data confidence. Ordering is the documented lexicographic vector of those state classes followed by ticker; it is not a score, recommendation, probability, target price, or portfolio-sizing signal.

Every available financial fact carries either direct observation/citation/evidence identity or complete deterministic derived component lineage. Missing, stale, unknown, conflicting, incomparable, or basis-incompatible inputs remain explicit unavailable/incomparable states. A qualified catalyst requires complete, current, source-backed event coverage; absence is never inferred. Current technical readiness requires actionable daily-market and technical freshness plus `market_technical=ready`.

For banks, financial quality may use only `bank_financial_quality`; an available corporate model or EV valuation method is a sector conflict. Consumer only deep-copies the Producer envelope. Bear/base/bull scenarios are conditional records with catalysts, downside, invalidation, and a time horizon; Facts, Data Warnings, Inferences, and Hypotheses remain separate.
