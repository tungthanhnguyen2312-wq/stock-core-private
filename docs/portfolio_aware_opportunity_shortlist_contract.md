# Portfolio-Aware Opportunity Shortlist V1

Owner override: `OWNER_AUTHORIZATION_2026_09_09_PORTFOLIO_AWARE_OPPORTUNITY_SHORTLIST_V1`.

`portfolio_aware_opportunity_shortlist/v1` is a private, local-only, deterministic selection product. It composes same-session `integrated_investment_decision_product/v1`, `portfolio_aware_decision/v1`, and `asymmetric_dislocation_research/v1`; optional calibration is contextual only. It fails closed on session or identity disagreement, never recomputes inputs, and does not enter the canonical Daily path.

The shortlist preserves Portfolio V2 action and quantity semantics, including distinct research risk ceilings and non-qualified execution quantities. It does not use private cost basis, P&L, NAV, cash, margin values, or sizing amounts in its lexicographic ordering. Console output is identities and aggregates only.
