# Intrinsic & Sector Valuation Contract

Schema/method version: `1.0.0`. Only FCFF DCF and Net-Net have implemented evaluators, and only for explicit, qualified canonical inputs. FCFE, DDM, RNAV and SOTP are not represented because current sources lack qualified equity cash flow/dividend history, cost-of-equity, asset-component, forecast, and valuation provenance.

FCFF requires compatible standalone canonical operating cash flow and CapEx, qualified debt/cash, one known statement scope and period, plus sourced WACC, terminal growth and forecast FCFF. Net-Net requires compatible qualified current assets, cash, receivables, inventory, liabilities, and basic/diluted share count. Null stays null; zero and negative values are preserved; debt is never inferred from liabilities and CapEx never from investing cash flow.

Assumptions require an explicit source label. Terminal value requires `wacc > terminal_growth` and sensitivity dimensions. Forecast/scenario outputs are ranges only; no single target price, recommendation, or averaging is emitted. A stale/non-actionable price prevents actionability. Financial-sector inputs require a separately qualified variant. Legacy bundles resolve to unknown. Evaluation is deterministic for identical inputs/reference time.

Current runtime blocker: all canonical financial records have unknown statement scope; share metadata has no qualified basis; market-cap/debt/cash semantics, forecasts, WACC/beta/risk premium/terminal assumptions, dividend history, and reproducible RNAV/SOTP components are absent.
