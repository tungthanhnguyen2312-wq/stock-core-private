# Canonical universe tiers and membership ledger

`canonical_universe_tiers.py` is the C.2 boundary between C.1's promoted
instrument candidates and later freshness, feature, strategy, and research
consumers. It accepts only an explicit, hash-valid C.1 artifact. It never
reads `vn_stock.db`, discovers a legacy ticker list, fetches a provider, or
writes a dashboard/runtime path.

## Tier DAG

```text
MASTER_OBSERVED
  -> LISTED_EQUITY_CANDIDATE
  -> ACTIVE_UNIVERSE
  -> FRESH_DATA_UNIVERSE
       -> FEATURE_QUALIFIED_UNIVERSE
       -> STRATEGY_ELIGIBLE_UNIVERSE[tier_scope]
FEATURE_QUALIFIED_UNIVERSE -> RESEARCH_QUALIFIED_UNIVERSE
```

Feature-qualified and strategy-eligible are siblings. Strategy membership
always has a non-empty `tier_scope`; it is not implicitly derived from feature
membership.

## States and reasons

Every candidate appears in every generated snapshot as exactly one of
`INCLUDED`, `EXCLUDED`, `UNKNOWN`, or `NOT_APPLICABLE`. These states are never
collapsed. In particular, `UNKNOWN_SECURITY_GROUP` is
`UNKNOWN/instrument_type_unknown`.

Non-equity `instrument_class` values get a class-specific exclusion reason where the classifier
vocabulary supports it -- `ETF`/`WARRANT`/`RIGHT`/`BOND`/`DERIVATIVE` map to
`instrument_type_etf`/`instrument_type_warrant`/`instrument_type_right`/`instrument_type_bond`/
`instrument_type_derivative` respectively, matching `dnse_instrument_universe.INSTRUMENT_CLASSES`
exactly. **None of these five has an empirically-observed member as of this writing** -- every
non-`EQUITY` DNSE `securityGroupId` currently resolves to `UNKNOWN_SECURITY_GROUP`, never one of
these five strings; the mapping exists so the reason vocabulary is ready the day a new
`securityGroupId` is first classified, not because any instrument is excluded this way today. A
class string outside this table, the equity/unknown buckets, and the index/synthetic bucket below
still fails closed to the generic `instrument_type_not_equity`.

`INDEX`/`SYNTHETIC`/`INDEX_OR_SYNTHETIC` inputs are all `NOT_APPLICABLE` for the equity-candidate
tier, but the two families are evidenced differently and get distinct reason codes as of the
2026-08-17 semantic-evidence qualification:

- **`INDEX`** -> `NOT_APPLICABLE/index_confirmed_not_applicable`, `quality_status =
  "provider_reported"`. Evidenced: `dnse_security_group_semantics.py` only ever emits literal
  `INDEX` for a no-`securityGroupId` record whose own `name` field was individually confirmed to
  start with the Vietnamese word for "index" (`"Chỉ số"`) against known market index names — see
  `docs/dnse_security_group_semantics_contract.md`. This is a real classification, not a
  placeholder.
- **`SYNTHETIC`/`INDEX_OR_SYNTHETIC`** -> `NOT_APPLICABLE/index_or_synthetic_reserved_unqualified`,
  `quality_status = "unqualified"` (never `provider_reported`). **Still reserved/future-only, not a
  proven classification**: no current classifier authority
  (`dnse_instrument_universe.INSTRUMENT_CLASSES`, nor `dnse_security_group_semantics.py`) has ever
  emitted either of these two specific values. Do not read this branch's presence as evidence that
  a synthetic instrument class is distinguished from `UNKNOWN_SECURITY_GROUP` today; it is not.

**`ACTIVE_UNIVERSE` -- and every tier downstream of it (`FRESH_DATA_UNIVERSE`,
`FEATURE_QUALIFIED_UNIVERSE`, `STRATEGY_ELIGIBLE_UNIVERSE`, `RESEARCH_QUALIFIED_UNIVERSE`) --
cannot resolve any candidate to `INCLUDED` from C.1 output alone, as of this writing, for any
instrument, regardless of `instrument_class`.** This is fail-closed by design, not a defect: C.1
never marks any provider's `exchange` or `listing_status` observation as usable (see
`docs/canonical_instrument_reconciliation_contract.md`), so `ACTIVE_UNIVERSE` always lands
`UNKNOWN/listing_status_unknown` (or `UNKNOWN/exchange_unknown` if listing status were ever
qualified without exchange). A catalog record or a fresh price bar does not prove active listing.
Promoting any instrument past `LISTED_EQUITY_CANDIDATE` requires a new, separately-qualified
listing-status or exchange-label evidence source entering C.1 through its own retained-input
reconciliation -- out of scope for this foundation milestone.

The controlled reason registry is exported as `REASON_REGISTRY`
(`NON_EQUITY_CLASS_REASONS` is its class-specific subset). Ledger events must use a registered
reason code; optional `reason_detail` may only add context, never replace the code.

## Ledger row fields

Every membership row (in a snapshot) and every ledger event carries `instrument_class` and
`exchange` as first-class fields, carried verbatim from the source C.1 candidate's own selected
values -- never a new normalization or inferred value. Neither field is part of a ledger event's
identity/dedup hash (same treatment as `quality_status`): a C.1 rerun that only changes one of
these two values, with tier/state/reason_code unchanged, does not by itself append a new ledger
event. Consumers that need pre-C.1 raw-provenance detail beyond these two fields still join back to
the source C.1 artifact via `source_c1_artifact_id`/`dataset_reference`.

## Ledger and identity continuity

Each snapshot produces event-style membership entries for included, excluded,
unknown, and not-applicable records. A later artifact may take an explicit
prior C.2 artifact and preserves every prior event while appending only unseen
state events. No implicit `latest` artifact is read.

`instrument_identity_key` is a hash of the sorted provider identity set. It is
separate from the C.1 candidate ID, so it survives a C.1 reconciliation-rule
version change when provider identities remain the same.

## Denominators and storage

Every snapshot records `universe_tier`, `tier_scope`, `universe_version`, C.1
artifact identity, `as_of_session`, `generated_at`, all four state counts, and
reason breakdowns. All counts partition the C.1 `MASTER_OBSERVED` count:

```text
included + excluded + unknown + not_applicable == total
```

Two consumer statistics are comparable only when tier, universe version,
as-of session, and tier scope match exactly. The helper
`snapshots_comparable()` enforces this identity rule.

Artifacts are immutable and content-addressed at:

```text
data/canonical_universe_tiers/artifacts/<content-hash>.json
```

The adapter requires explicit C.1, output, session, generation-time, and
optional prior-ledger paths.
