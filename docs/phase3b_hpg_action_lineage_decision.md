# Phase 3B HPG Corporate-Action Factor Lineage Decision

## Status: DEFERRED_BY_SOURCE

Phase 3B is deliberately deferred. No current record may produce a price
adjustment factor, historical market cap, or per-share valuation input.

## Qualification contract

A lineage entry requires a stable event identity; source hash and provenance;
observed time; ex-date, record date, and declared effective-date semantics; an
explicit adjustment factor or fully evidenced source-stated formula; compatible
verified OHLCV price basis; and a distinct qualified share-basis identity. The
key is `ticker + provider + provider_event_id + action_type + effective_date +
factor_version`. Duplicate identity, missing dates, mixed/unknown basis,
unsupported action, or any absent lineage field fails closed. Period-end and
weighted-average shares are never interchangeable.

## Final bounded source review

Three issuer sources were checked. The downloaded issuer AGM resolution is
retained only in job-local evidence at
`operations-review/evidence/phase3b-final-hpg-action-20260728T163420Z/`:
`HPG_AGM_2024_resolution.pdf`, SHA-256 `62b6c056619e879cb4092decfad0089c90a40fd8f7abb7ce4114bb90b3c3ab0f`. It and the issuer's AGM
announcement confirm a 10% 2024 issuance plan. The issuer IR index authenticates
the resolution listing. None establishes an event-specific authoritative identity,
record/ex/effective-date semantics, or price-adjustment factor/formula.

The retained VCI observation `6708f3f80ec61045ab800ab1` has a 10% bonus-issue
ratio and dates but is explicitly `partial_unqualified_50_row_cap`.
`corporate_actions.py` retains that value only as a provider-stated ratio and
marks adjustment provenance unqualified. It cannot bridge the gap. VNM and VCB
remain fail-closed comparisons; VCB also remains outside corporate valuation.

No further acquisition round is authorized by this decision. A future Phase 3B
reopening requires a first-party issuer/exchange/regulator action notice with the
missing lifecycle and factor semantics. No production data, runtime sidecar,
Consumer, or Dashboard artifact was changed.
