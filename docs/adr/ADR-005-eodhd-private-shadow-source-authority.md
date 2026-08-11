# ADR-005: EODHD private-shadow market-data authority

> **SUPERSEDED — 2026-08-03.** The approval recorded below was withdrawn one day after this ADR
> was written. Current authority: `docs/DECISIONS.md`'s 2026-08-03 EODHD closure entry
> (`EODHD_ROUTE_STATUS: REJECTED_BY_OWNER`), reconfirmed by its 2026-08-11 reconciliation entry —
> "EODHD remains `REJECTED_BY_OWNER`; it is not a fallback, qualification route, or investigation
> target." No retest is authorized; the "Retest conditions" section below is inert. Kept for the
> historical record of the original, later-withdrawn approval — do not act on it and do not
> propose reopening EODHD on the strength of this file alone.

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
