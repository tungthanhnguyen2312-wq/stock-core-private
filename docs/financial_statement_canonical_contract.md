# Financial Statement Canonical Contract

Canonical records retain metric identity, value, source field/statement/source, fiscal period identity, scope, currency/unit scale, derivation and quality states, restatement state, and reason. Annual (`YYYY`), quarter (`YYYY-Qn`), and TTM (`YYYY-Qn-TTM`) are distinct identities. Period end is distinct from publication time; absent publication time is `null`, never inferred from file time. Scope and restatement default to `unknown`; consolidated and separate data are never combined.

Reported values remain reported. A TTM value is derived only from four consecutive compatible, standalone, reported quarterly values under one scope/source; no cumulative subtraction occurs. Duplicate identity conflicts are `incomparable`; malformed dates/numbers are unavailable. Null stays null and zero, including negative values, stays numeric. Legacy bundles omit this additive section and Consumers resolve it as missing.


### Explicit fallback after an unusable native text layer

A retained PDF can expose native text while its font maps corrupt identity labels.
Default TSV materialization still routes any native text to the native extractor.
An explicit bounded operator opt-in may re-run the existing native extractor against
verified immutable source bytes. Any native fact candidate or panel fact refuses OCR
fallback. Zero candidates permits a separate unchanged default rendered TSV pass;
no native/OCR tokens, labels or values are assembled together. Receipts preserve the
native artifact identity and selected native-page text hashes alongside rendered-image
and raw TSV token hashes. Hash mismatch/out-of-range pages fail before fallback.
Every existing period, unit, scope, code, geometry, numeric and assurance gate remains.

The fixed NVL H1 replay uses report6–7 and statements8–14. It qualifies reviewed
consolidated assurance only; all exact values remain blocked. Retention/assurance does
not create a financial field, earnings-quality score, current denominator or valuation.
The existing ingress report records native-fallback receipts; no parallel evidence store.
