# Financial Statement Canonical Contract

Canonical records retain metric identity, value, source field/statement/source, fiscal period identity, scope, currency/unit scale, derivation and quality states, restatement state, and reason. Annual (`YYYY`), quarter (`YYYY-Qn`), and TTM (`YYYY-Qn-TTM`) are distinct identities. Period end is distinct from publication time; absent publication time is `null`, never inferred from file time. Scope and restatement default to `unknown`; consolidated and separate data are never combined.

Reported values remain reported. A TTM value is derived only from four consecutive compatible, standalone, reported quarterly values under one scope/source; no cumulative subtraction occurs. Duplicate identity conflicts are `incomparable`; malformed dates/numbers are unavailable. Null stays null and zero, including negative values, stays numeric. Legacy bundles omit this additive section and Consumers resolve it as missing.
