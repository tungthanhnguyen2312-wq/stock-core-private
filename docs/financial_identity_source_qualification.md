# Structured Financial Identity and Capital Structure Qualification

Audit date: 2026-07-26; library: `vnstock==4.0.4`. Bounded read-only probes
used HPG, PAN and VCB (bank). No production database was opened for writing.

| Call | Parameters | Observed result | Qualified identity | Not qualified |
|---|---|---|---|---|
| `Finance(source="KBS", symbol=ticker).income_statement()` | `period="quarter"` / `"year"` | quarter headers are `YYYY-Qn`; annual headers are `YYYY-Năm` | reporting frequency, when invocation and all period headers agree | consolidated/separate scope, publication date, restatement semantics, currency/unit fields |
| `Finance(source="VCI", symbol=ticker).income_statement()` | `period="quarter"` / `"year"` | quarter headers are `YYYY-Qn`; annual headers are `YYYY` | reporting frequency, when invocation and headers agree | consolidated/separate scope, publication date, restatement semantics, currency/unit fields |
| KBS/VCI balance/cash flow | same `period` parameter | KBS balance was empty for all three probes; cash-flow output was partial; VCI response did not add a scope field | none beyond response-specific frequency where headers validate | scope and completeness |
| `Company(source="VCI", symbol=ticker).overview()` | `random_agent=False`, `show_log=False` | one row per HPG/PAN/VCB with `issue_share`, `market_cap`, `symbol` | same-response observations and retrieval-time alignment | basic/diluted/treasury/effective share basis, market-cap as-of date, currency and unit |

The canonical mapper records provider, exact library version, public method,
parameters and observation time. It sets statement scope and share basis to
`unknown` where the response omits those semantics, preserves zero, and never
uses market cap divided by price. The currently retained runtime has no raw,
versioned financial-identity observations: historical `metadata` values lack
the required method/version/parameter provenance. The Consumer therefore must
not export them as qualified capital structure fields yet.

Representative live observations at probe time:

| Ticker | KBS/VCI frequency result | VCI overview fields |
|---|---|---|
| HPG | quarterly and annual response headers matched invocation | `issue_share=8,442,964,520`; `market_cap=175,613,662,016,000`; basis/as-of/unit unknown |
| PAN | quarterly and annual response headers matched invocation | `issue_share=250,673,166`; `market_cap=5,239,069,169,400`; basis/as-of/unit unknown |
| VCB | quarterly and annual response headers matched invocation | `issue_share=8,355,675,094`; `market_cap=452,042,022,585,400`; basis/as-of/unit unknown |
