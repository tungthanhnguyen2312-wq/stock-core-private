# Price Basis, Corporate Action Adjustment & Volume Semantics Contract

**Recorded:** 2026-07-28
**Component:** `stock-core-private` (Producer)
**Modules:** `price_basis_contract.py`, `export_ai_bundle.py`, `source_schema_guards.py`

---

## 1. Executive Summary & Core Rules

This contract establishes a deterministic, fail-closed metadata standard for price basis, corporate action adjustments, and historical volume semantics across all Producer outputs:

1. **Explicit Price Basis:** Every canonical price series or price-derived metric explicitly identifies its basis: `raw`, `adjusted`, or `unknown`.
2. **Fail-Closed on Unknown:** An unverified or unknown price basis remains `unknown` and `is_actionable=False`. Unverified price sources are never assumed to be adjusted.
3. **No Mixed-Basis Calculations:** Combining `raw` and `adjusted` price series in returns, moving averages, or ratios is prohibited in strict mode and flagged as `mixed_raw_and_adjusted_basis` in non-strict mode.
4. **Decoupled Volume Semantics:** Historical volume (`volume`) is qualified independently (`raw_shares_traded`, `adjusted_volume`, `unknown`). Corporate action adjustments on price do not imply volume adjustments.
5. **Backward Compatibility:** Legacy consumers receiving scalar price values or unverified metadata continue to parse existing fields, while new provenance envelopes explicitly expose uncertainty flags.

---

## 2. Qualified Semantics Matrix

| Domain / Series | Default Basis | Verification Requirement | Actionability Policy |
|---|---|---|---|
| OHLCV Raw Price Series | `unknown` | Requires explicit upstream provider basis token | Non-actionable for corporate-action-sensitive backtests when `unknown` |
| Upstream Corporate Events | `unqualified_no_price_adjustment_claim` | Retains raw event observations (ex-date, ratio, cash per share) | Does not automatically assert price series adjustment |
| Technical Indicators (SMA, RSI, RS) | Inherits Price Basis | Inherits from underlying price series | Marked `unverified_or_unknown_basis` if underlying series is `unknown` |
| Volume Series (`volume`) | `raw_shares_traded` | Qualified independently from price series | Independent volume basis token; not tied to price adjustment |

---

## 3. Shadow Qualification Representative Tickers

Shadow validation evaluates representative tickers under:
`operations-review/active-milestone/validation/price-basis/`

- **POW:** Normal corporate ticker (no major recent splits).
- **SSI:** Financial/securities ticker with multiple historical stock dividends & rights issues.
- **HPG:** Industrial ticker with frequent stock dividends and bonus issues.
- **VCB:** Major commercial bank ticker with complex bonus issue history.
