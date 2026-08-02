# ADR-005: EODHD private-shadow market-data authority

## Decision

The owner approved EODHD on 2026-08-02 as the candidate source authority for a
private HPG/VNM shadow path. The approved interface is the authenticated EOD
endpoint for `HPG.VN` and `VNM.VN`. Official endpoint semantics identify `close`
as unadjusted, `adjusted_close` as split-and-dividend adjusted, and `volume` as
split-adjusted trading volume. The repository adapter retains both price
namespaces and never substitutes one for the other.

## Safety boundary

The token is environment-only. Missing authentication, missing fields, mixed
sessions, ambiguous units, or a schema change remains fail closed. No production
ingestion, publication, redistribution, valuation, ranking, recommendation,
sizing, or backtest is authorized by this decision. Public or commercial use
requires separate confirmation that the account terms permit that use.

## Retest conditions

Retest after an endpoint/schema, provider contract, ticker identity, currency,
adjustment methodology, or adapter-version change. Qualification applies only
after an authenticated HPG/VNM payload passes the retained schema check.
